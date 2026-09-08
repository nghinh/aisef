"""A story run is **one transaction**, not seven separate writes.

A single run touches seven state stores: worktree, git branch, sprint record,
evidence files, attempt status, subprocess, and commit/merge ledger. They must
be consistent with each other, but nothing enforces consistency — so when a run
dies mid-way, each store stops at a different point. Observed on e9:

* process killed -> story stuck at ``running`` forever;
* worktree merged into main branch -> ledger still says ``failed``, and the
  cost of that attempt is lost;
* re-running an already-merged story -> new worktree branches from a branch
  that already contains the work, diff is empty, story can never pass again.

The fix borrows from *revertible effects*: each step records its own
**inverse**, and the journal is machine-readable state for reconstructing how
far a run got. No general-purpose runtime — the scope is exactly the stores
AISEF actually owns.

One deliberate boundary: **do not pretend to revert the irrevertible.** Once
a merge is on the main branch, the correct action is to *roll forward* so
status catches up, not to try rolling back.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

JOURNAL_DIR = "journal"

#: Steps of a run, in order. This list is the contract: reading the journal
#: and comparing against it tells where a run stopped and what remains.
#:
#: ``candidate.frozen`` carries the candidate SHA and comes **before** all
#: verification steps (ADR-004 R1): evidence only means something when it
#: points to a specific build. Previously this step was named
#: ``commit.created`` and came *after* ``review.completed`` — the candidate
#: was frozen after grading, so there was no way to say "this evidence
#: belongs to this build."
STEPS = (
    "attempt.started",
    "worktree.created",
    "status.running",
    "changes.detected",
    "candidate.frozen",
    "verification.completed",
    "review.completed",
    "merge.completed",
    "attempt.committed",
)

#: Step marking that work has reached the main branch. From this point on,
#: reverting is wrong: the work is outside the transaction's scope.
POINT_OF_NO_RETURN = "merge.completed"

ABORTED = "attempt.aborted"
RECONCILED = "attempt.reconciled"


@dataclass
class Entry:
    seq: int = 0
    step: str = ""
    at: float = 0.0
    attempt: int = 0
    data: dict = field(default_factory=dict)
    #: Action needed to undo this step. Empty means the step left nothing
    #: to undo (e.g. a purely informational milestone).
    undo: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "step": self.step,
            "at": round(self.at, 3),
            "attempt": self.attempt,
            "data": self.data,
            "undo": self.undo,
        }


@dataclass
class Journal:
    story_id: str
    entries: list[Entry] = field(default_factory=list)

    def steps(self) -> list[str]:
        return [e.step for e in self.entries]

    def last(self, step: str) -> Entry | None:
        for e in reversed(self.entries):
            if e.step == step:
                return e
        return None

    def reached(self, step: str) -> bool:
        return self.last(step) is not None

    @property
    def needs_merge(self) -> bool:
        """Story has a worktree (thus needs merge) but has not merged yet.

        `DONE` is written when the gate passes, before merge — so status alone
        cannot answer "has the code reached the main branch." Running directly
        in the project (`--no-isolate`) has no merge step and no
        `worktree.created`, so returning False is correct.
        """
        # `commit.created` (old name) only occurs in worktree branches, so it
        # also proves a worktree exists — for old journals missing the first step.
        # `candidate.frozen` **cannot** be used here: it is recorded even when
        # running directly in the project (`--no-isolate`), where there is
        # nothing to merge.
        co_worktree = self.reached("worktree.created") or self.reached("commit.created")
        return co_worktree and not self.merged()

    @property
    def attempt_no(self) -> int:
        return max((e.attempt for e in self.entries), default=0)

    def open_attempt(self) -> int:
        """Attempt number of the open (unclosed) attempt. 0 if no attempt is in progress.

        Closed means ``attempt.committed``, ``attempt.aborted`` or
        ``attempt.reconciled`` appears **after** the most recent
        ``attempt.started``.
        """
        mo = 0
        for e in self.entries:
            if e.step == "attempt.started":
                mo = e.attempt
            elif e.step in (STEPS[-1], ABORTED, RECONCILED) and e.attempt == mo:
                mo = 0
        return mo

    def merged(self) -> bool:
        """Whether this story's work has reached the main branch.

        The most important question when re-running: a new worktree branching
        from a branch that already contains the work produces an empty diff,
        and the story can never pass the review gate again. Knowing it merged
        lets us skip instead of retrying blindly.
        """
        return self.reached(POINT_OF_NO_RETURN)


class JournalStore:
    """Read/write ``journal/{story}.jsonl``. Append-only, never modified."""

    def __init__(self, artifact_root: Path | str):
        self.root = Path(artifact_root) / JOURNAL_DIR

    def path(self, story_id: str) -> Path:
        return self.root / f"{story_id}.jsonl"

    def record(self, story_id: str, entry: Entry) -> Entry:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(story_id)
        entry.at = entry.at or time.time()
        with path.open("a", encoding="utf-8") as fh:
            entry.seq = self._next_seq(path)
            fh.write(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return entry

    def _next_seq(self, path: Path) -> int:
        highest = 0
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    highest = max(highest, int(json.loads(line).get("seq") or 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return highest + 1

    def read(self, story_id: str) -> Journal:
        j = Journal(story_id=story_id)
        path = self.path(story_id)
        if not path.is_file():
            return j
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue  # one corrupt line is not worth losing the entire journal
            j.entries.append(Entry(
                seq=int(raw.get("seq") or 0),
                step=str(raw.get("step") or ""),
                at=float(raw.get("at") or 0.0),
                attempt=int(raw.get("attempt") or 0),
                data=raw.get("data") or {},
                undo=raw.get("undo") or {},
            ))
        return j

    def story_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))


# ------------------------------------------------------------ transactions


@dataclass
class Reconciled:
    story_id: str
    action: str = ""      # "" | "roll-forward" | "undo" | "status-fix"
    detail: str = ""

    def line(self) -> str:
        return f"{self.story_id}: {self.action} — {self.detail}"


class StoryRunTransaction:
    """A story run, recording each step with its inverse in the journal.

    Intentionally holds **no state only in memory**: when the process dies
    the object dies with it, but the journal survives. Everything needed
    for cleanup must be on disk from the moment the step happens, not when
    it fails.
    """

    def __init__(
        self,
        story_id: str,
        *,
        artifact_root: Path | str,
        attempt: int = 1,
    ):
        self.story_id = story_id
        self.store = JournalStore(artifact_root)
        self.attempt = attempt
        self.committed = False

    def __enter__(self) -> "StoryRunTransaction":
        self.record("attempt.started")
        return self

    def record(self, step: str, *, undo: dict | None = None, **data) -> Entry:
        return self.store.record(self.story_id, Entry(
            step=step, attempt=self.attempt, data=data, undo=undo or {},
        ))

    def commit(self) -> None:
        self.record("attempt.committed")
        self.committed = True

    def abort(self, reason: str) -> None:
        self.record(ABORTED, reason=reason)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.committed:
            self.abort(f"{exc_type.__name__}: {exc}" if exc_type else "abnormal termination")
        return False  # do not swallow exceptions


def reconcile_story(
    story_id: str,
    *,
    artifact_root: Path | str,
    state,
    worktrees=None,
) -> Reconciled | None:
    """Bring a story back to a consistent state after an incomplete run.

    Three situations, three different actions:

    1. **Already merged** — work is outside the transaction scope. Roll
       forward so status catches up, do not try to revert. This is exactly
       the case observed on e9: worktree merged but ledger still says ``failed``.
    2. **In progress, not merged** — remove temporary resources (worktree)
       and reset status to ``pending`` for retry. The branch is **not**
       deleted: committed work in it must not vanish due to cleanup.
    3. **No open attempt** — only fix status if it is stuck at
       ``running``/``verifying`` from a dead process.
    """
    from .state import StoryStatus

    j = JournalStore(artifact_root).read(story_id)
    rec = state.load().stories.get(story_id)
    if rec is None:
        return None
    cur = rec.state

    if j.merged() and cur is not StoryStatus.DONE:
        _to_done(state, story_id)
        JournalStore(artifact_root).record(story_id, Entry(
            step=RECONCILED, attempt=j.attempt_no,
            data={"action": "roll-forward", "from": cur.value},
        ))
        return Reconciled(story_id, "roll-forward",
                          "already merged to main branch, rolling status forward")

    in_progress = j.open_attempt()
    stale = cur in (StoryStatus.RUNNING, StoryStatus.VERIFYING)
    if not in_progress and not stale:
        return None

    if worktrees is not None and (in_progress or stale):
        # Branch is kept: commits in it are real work.
        worktrees.remove(story_id, delete_branch=False)
    if cur is not StoryStatus.DONE:
        state.reset_for_retry(story_id)
    JournalStore(artifact_root).record(story_id, Entry(
        step=RECONCILED, attempt=j.attempt_no,
        data={"action": "undo", "from": cur.value},
    ))
    return Reconciled(
        story_id, "undo",
        f"incomplete run at `{j.steps()[-1] if j.entries else '?'}`, cleaned up and back to pending",
    )


def reconcile_all(
    *,
    artifact_root: Path | str,
    state,
    worktrees=None,
) -> list[Reconciled]:
    """Reconcile all stories that have a journal. Runs at the start of each `aisef run`.

    This is where a process killed in a previous run gets cleaned up: without
    this step, a story stuck at ``running`` forever and no command can unstick
    it.
    """
    store = JournalStore(artifact_root)
    out = []
    for sid in store.story_ids():
        r = reconcile_story(
            sid, artifact_root=artifact_root, state=state, worktrees=worktrees
        )
        if r:
            out.append(r)
    return out


def _to_done(state, story_id: str) -> None:
    """Advance status to ``done`` through valid state transitions.

    Follows the state machine instead of overwriting: the record must retain
    a valid transition trail, otherwise it is no longer evidence.
    """
    from .state import StoryStatus

    cur = state.load().stories[story_id].state
    if cur is StoryStatus.DONE:
        return
    if cur is StoryStatus.VERIFIED:
        state.transition(story_id, StoryStatus.DONE)
        return
    if cur is not StoryStatus.VERIFYING:
        state.reset_for_retry(story_id)
        state.transition(story_id, StoryStatus.RUNNING)
        state.transition(story_id, StoryStatus.VERIFYING)
    state.transition(story_id, StoryStatus.VERIFIED)
    state.transition(story_id, StoryStatus.DONE)
