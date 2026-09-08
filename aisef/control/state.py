"""Progress state store — single source of truth for what is done.

State lives **on disk**, not in process memory. This is required for:

* stopping mid-run and resuming exactly where it left off;
* control plane is a fire-once CLI, not a daemon (decision D2);
* multiple surfaces (Desktop, CLI, CI) sharing the same progress view.

Two guarantees on writes:

1. **Atomic** — write to a temp file then ``replace``. If interrupted, the
   old file stays intact; never leaves behind truncated JSON.
2. **Exclusive lock** — parallel stories each update state on completion;
   without locking, two near-simultaneous writes would lose one.

Lock uses ``fcntl.flock`` on Unix, ``msvcrt.locking`` on Windows (via
``aisef._compat``).  Both auto-release when the process dies.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

from aisef._compat import flock_ex_nb, flock_un
from pathlib import Path
from typing import Iterator

STATE_FILE = "sprint-status.json"
LOCK_SUFFIX = ".lock"


def machine_id() -> str:
    """Unique machine identifier for claims — hostname + pid."""
    import socket
    return f"{socket.gethostname()}:{os.getpid()}"
LOCK_TIMEOUT_SECONDS = 30


class StoryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    #: Passed the gate, but **not yet** on the main branch. Before 2026-09-05
    #: this status did not exist: `done` was written at gate pass, before merge
    #: — if merge conflicted, the story was "done" but code stuck on the story
    #: branch with nobody aware (bug 42). Now `done` is written only **after**
    #: `merge.completed`.
    VERIFIED = "verified"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in (StoryStatus.DONE, StoryStatus.BLOCKED, StoryStatus.FAILED)

    @property
    def satisfies_dependents(self) -> bool:
        """Only fully completed stories unlock their dependents."""
        return self is StoryStatus.DONE


#: Valid state transitions. Prevents meaningless jumps like
#: pending -> done without going through verifying.
ALLOWED: dict[StoryStatus, frozenset[StoryStatus]] = {
    StoryStatus.PENDING: frozenset({StoryStatus.RUNNING, StoryStatus.BLOCKED}),
    StoryStatus.RUNNING: frozenset({StoryStatus.VERIFYING, StoryStatus.FAILED, StoryStatus.BLOCKED}),
    # `verifying -> done` direct path is only for non-isolated runs (`--no-isolate`):
    # no dedicated branch means no merge step. With a worktree, `run.py`
    # goes through `verified`.
    StoryStatus.VERIFYING: frozenset({
        StoryStatus.VERIFIED, StoryStatus.DONE, StoryStatus.FAILED, StoryStatus.BLOCKED,
    }),
    # merge complete -> done; merge conflict resolved by human -> back to pending for re-merge
    StoryStatus.VERIFIED: frozenset({StoryStatus.DONE, StoryStatus.PENDING, StoryStatus.BLOCKED}),
    # failed with retries remaining goes back to pending
    StoryStatus.FAILED: frozenset({StoryStatus.PENDING, StoryStatus.BLOCKED}),
    StoryStatus.BLOCKED: frozenset({StoryStatus.PENDING}),
    StoryStatus.DONE: frozenset(),
}


class TransitionError(ValueError):
    """Invalid state transition."""


class LockTimeout(TimeoutError):
    """Could not acquire lock within the allowed timeout."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StoryRecord:
    id: str
    epic_id: str = ""
    status: str = StoryStatus.PENDING.value
    attempts: int = 0
    wave: int = 0
    worktree: str = ""
    evidence: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0
    blocked_reason: str = ""
    claimed_by: str = ""
    updated_at: str = field(default_factory=_now)

    @property
    def state(self) -> StoryStatus:
        return StoryStatus(self.status)


@dataclass
class SprintState:
    stories: dict[str, StoryRecord] = field(default_factory=dict)
    current_epic: str = ""
    active_epics: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # --------------------------------------------------------- queries

    def by_status(self, status: StoryStatus, *, epic: str = "") -> list[StoryRecord]:
        return [r for r in self.stories.values()
                if r.state is status and (not epic or r.epic_id == epic)]

    def of_epic(self, epic_id: str) -> list[StoryRecord]:
        return [r for r in self.stories.values() if r.epic_id == epic_id]

    def done_ids(self) -> set[str]:
        return {r.id for r in self.stories.values() if r.state.satisfies_dependents}

    def totals(self) -> dict[str, int]:
        counts = {s.value: 0 for s in StoryStatus}
        for r in self.stories.values():
            counts[r.status] += 1
        return counts

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.stories.values())

    def cost_outliers(self, multiple: float) -> list[StoryRecord]:
        """Stories costing more than `multiple` times the median — a sign to review.

        Uses median, not mean: a single extremely expensive story would pull
        the mean up and mask itself.
        """
        costs = sorted(r.cost_usd for r in self.stories.values() if r.cost_usd > 0)
        if len(costs) < 3:
            return []
        mid = len(costs) // 2
        median = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2
        if median <= 0:
            return []
        return [r for r in self.stories.values() if r.cost_usd > median * multiple]


class StateStore:
    """Read/write state with exclusive locking and atomic writes."""

    def __init__(self, artifact_root: Path | str):
        self.root = Path(artifact_root)
        self.path = self.root / STATE_FILE
        self.lock_path = self.root / (STATE_FILE + LOCK_SUFFIX)

    # --------------------------------------------------------- locking

    @contextmanager
    def _locked(self, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    flock_ex_nb(fd)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(
                            f"could not acquire lock {self.lock_path} after {timeout}s"
                        ) from None
                    time.sleep(0.05)
            yield
        finally:
            try:
                flock_un(fd)
            finally:
                os.close(fd)

    # --------------------------------------------------------- read, write

    def load(self) -> SprintState:
        if not self.path.is_file():
            return SprintState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Corrupted file: starting fresh is better than running on half-baked state.
            return SprintState()
        stories = {
            sid: StoryRecord(**rec) for sid, rec in (raw.get("stories") or {}).items()
        }
        self._migrate_done_before_merge(stories)
        return SprintState(
            stories=stories,
            current_epic=raw.get("current_epic", ""),
            active_epics=raw.get("active_epics") or [],
            started_at=raw.get("started_at", _now()),
            updated_at=raw.get("updated_at", _now()),
        )

    def _migrate_done_before_merge(self, stories: dict[str, StoryRecord]) -> None:
        """Legacy records wrote `done` at gate pass, before merge. A story marked
        `done` whose journal says it hasn't merged is `verified` under the new
        semantics — fix on read, once, so every status query sees the same truth."""
        from .journal import JournalStore  # avoid circular import

        doi = False
        store = JournalStore(self.root)
        for sid, rec in stories.items():
            if rec.state is StoryStatus.DONE and store.read(sid).needs_merge:
                rec.status = StoryStatus.VERIFIED.value
                rec.updated_at = _now()
                doi = True
        if doi:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            payload["stories"] = {sid: asdict(r) for sid, r in stories.items()}
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
            tmp.replace(self.path)

    def save(self, state: SprintState) -> None:
        state.updated_at = _now()
        payload = {
            "stories": {sid: asdict(r) for sid, r in state.stories.items()},
            "current_epic": state.current_epic,
            "active_epics": state.active_epics,
            "started_at": state.started_at,
            "updated_at": state.updated_at,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @contextmanager
    def transaction(self) -> Iterator[SprintState]:
        """Read — modify — write under a single lock.

        Reading inside the lock is mandatory: reading outside then writing
        would overwrite changes made by another process in between.
        """
        with self._locked():
            state = self.load()
            yield state
            self.save(state)

    # --------------------------------------------------------- operations

    def register(self, story_id: str, epic_id: str = "", wave: int = 0) -> None:
        with self.transaction() as st:
            if story_id not in st.stories:
                st.stories[story_id] = StoryRecord(id=story_id, epic_id=epic_id, wave=wave)

    def reset_for_retry(self, story_id: str) -> bool:
        """Reset an incomplete story to ``pending`` for retry. Returns True if changed.

        Retry is a valid entry point, but the state machine has no edge going
        directly from ``failed`` or from an abandoned ``running`` to ``running``.
        Without this path, every transition in a retry run would be rejected
        — and since `_safe_transition` swallows errors, the story still runs,
        still merges, but the record stays at the old failure, and the new
        run's cost never gets recorded.

        Leftover ``running``/``verifying`` belong to dead processes: the new
        run reclaims them. ``done`` is not touched — done is done.
        """
        with self.transaction() as st:
            rec = st.stories.get(story_id)
            # `verified` is work that **passed the gate**, awaiting merge — not
            # an incomplete run. Resetting it to pending would re-run a finished story.
            if rec is None or rec.state in (StoryStatus.DONE, StoryStatus.VERIFIED):
                return False
            if rec.state is StoryStatus.PENDING:
                return False
            rec.status = StoryStatus.PENDING.value
            rec.blocked_reason = ""
            rec.claimed_by = ""
            rec.updated_at = _now()
            return True

    def transition(
        self,
        story_id: str,
        to: StoryStatus,
        *,
        reason: str = "",
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        evidence: str = "",
        worktree: str = "",
        attempts: int = 0,
    ) -> StoryRecord:
        """Transition state; rejects invalid jumps.

        `attempts` is the **developer turn count** for this run, accumulated
        into the record. Previously counted each time `run` touched a story
        (entered RUNNING) — dogfood 01-02 had two turns but recorded 1,
        e9 01-05 had four turns but recorded 1 (P2-11).
        """
        with self.transaction() as st:
            rec = st.stories.get(story_id)
            if rec is None:
                rec = StoryRecord(id=story_id)
                st.stories[story_id] = rec

            current = rec.state
            if to is not current and to not in ALLOWED[current]:
                raise TransitionError(f"{story_id}: {current.value} → {to.value} is not a valid transition")

            if attempts:
                rec.attempts += attempts

            rec.status = to.value
            rec.updated_at = _now()
            if reason:
                rec.blocked_reason = reason
            if cost_usd:
                rec.cost_usd += cost_usd
            if duration_ms:
                rec.duration_ms += duration_ms
            if evidence:
                rec.evidence = evidence
            if worktree:
                rec.worktree = worktree
            return rec

    def claim(self, story_id: str, owner: str = "") -> bool:
        """Claim a pending story for execution — atomic compare-and-swap.

        Returns True on success (PENDING -> RUNNING + claimed_by).
        Returns False if the story is not pending or already claimed by another machine.
        """
        owner = owner or machine_id()
        with self.transaction() as st:
            rec = st.stories.get(story_id)
            if rec is None or rec.state is not StoryStatus.PENDING:
                return False
            rec.status = StoryStatus.RUNNING.value
            rec.claimed_by = owner
            rec.updated_at = _now()
            return True

    def release(self, story_id: str) -> None:
        """Release claim when story completes or fails — clears claimed_by."""
        with self.transaction() as st:
            rec = st.stories.get(story_id)
            if rec is not None:
                rec.claimed_by = ""

    def set_current_epic(self, epic_id: str) -> None:
        with self.transaction() as st:
            st.current_epic = epic_id
            if epic_id and epic_id not in st.active_epics:
                st.active_epics.append(epic_id)

    def finish_epic(self, epic_id: str) -> None:
        with self.transaction() as st:
            if epic_id in st.active_epics:
                st.active_epics.remove(epic_id)
            if st.current_epic == epic_id:
                st.current_epic = st.active_epics[-1] if st.active_epics else ""

    def epic_stories(self, epic_id: str) -> list[StoryRecord]:
        state = self.load()
        return [r for r in state.stories.values() if r.epic_id == epic_id]
