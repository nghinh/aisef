"""Orchestrate a full sprint: epics run sequentially, stories within an epic
run in parallel waves.

Three decisions shape this module:

* **Sequential epics** — stories in later epics typically depend on earlier
  ones; running epics concurrently causes unpredictable merge conflicts at
  the end of a wave.
* **Within an epic, independent stories run in parallel** (waves). Independent
  means no dependency **and** non-overlapping write scopes — both conditions
  are precomputed by the scheduler and recorded in ``stories.index.json``.
* **Each story gets its own worktree; merge is sequential at wave end.**
  A merge conflict is **evidence that ``write_scope`` was declared
  incorrectly**, so we stop and report rather than auto-resolve.

Resumable: state lives on disk; already-completed stories are not re-run.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path

from ..clients.base import ClientAdapter
from ..config import Config
from ..control import complexity
from ..control.approvals import STORIES_INDEX
from ..control.design_contract import load as load_contract
from ..control.journal import (
    Entry as JEntry,
    JournalStore,
    StoryRunTransaction,
    reconcile_all,
)
from ..control.normalize import Story, parse_architecture_file
from ..control.preflight import STORY_NOT_EXECUTABLE, check_story, screen_owners
from ..control.state import StateStore, StoryStatus, TransitionError
from ..control.worktree import GitError, WorktreeManager
from ..harness.prompts import load_catalog
from .implement import StoryOutcome, implement_story, verify_only as verify_only_story
from .plan import ARTIFACT_ROOT


@dataclass
class Plan:
    """Execution plan loaded from `stories.index.json`."""

    stories: dict[str, Story] = field(default_factory=dict)
    waves: dict[str, list[list[str]]] = field(default_factory=dict)
    epic_order: list[str] = field(default_factory=list)
    error: str = ""

    def epic_of(self, story_id: str) -> str:
        story = self.stories.get(story_id)
        return story.epic_id if story else ""


def load_plan(artifact_root: Path | str) -> Plan:
    path = Path(artifact_root) / STORIES_INDEX
    if not path.is_file():
        return Plan(error=f"missing {STORIES_INDEX} — run `aisef plan` first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return Plan(error=f"{STORIES_INDEX} corrupted: {e}")

    plan = Plan(waves=data.get("waves") or {})
    for raw in data.get("stories", []):
        plan.stories[raw["id"]] = Story(
            id=raw["id"],
            epic_id=raw.get("epic_id", ""),
            title=raw.get("title", ""),
            acceptance_criteria=raw.get("acceptance_criteria", []),
            verification_contract=raw.get("verification_contract", []),
            covers=raw.get("covers", []),
            write_scope=raw.get("write_scope", []),
            depends_on=raw.get("depends_on", []),
            screens=raw.get("screens", []),
        )
    plan.epic_order = [e["id"] for e in data.get("epics", [])]
    if not plan.waves:
        plan.error = plan.error or "index has no waves (dependency graph broken?)"
    return plan


@dataclass
class WaveReport:
    epic_id: str
    index: int
    outcomes: list[StoryOutcome] = field(default_factory=list)
    merge_conflicts: dict[str, list[str]] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(o.done for o in self.outcomes) and not self.merge_conflicts


@dataclass
class RunReport:
    waves: list[WaveReport] = field(default_factory=list)
    stopped_at: str = ""
    error: str = ""
    #: Stories whose state was reconciled from a previous interrupted run.
    #: Printed rather than swallowed: the reader needs to know which stories
    #: had their state corrected and why.
    reconciled: list = field(default_factory=list)

    @property
    def outcomes(self) -> list[StoryOutcome]:
        return [o for w in self.waves for o in w.outcomes]

    @property
    def cost_usd(self) -> float:
        return sum(o.cost_usd for o in self.outcomes)

    @property
    def ok(self) -> bool:
        return not self.error and not self.stopped_at and all(w.ok for w in self.waves)

    def summary(self) -> str:
        if self.error:
            return f"run wave: ✗ {self.error}"
        lines = []
        for r in self.reconciled:
            lines.append(f"↺ {r.line()}")
        for w in self.waves:
            head = f"{w.epic_id} · wave {w.index}"
            if len(w.outcomes) > 1:
                head += f" ({len(w.outcomes)} stories in parallel)"
            lines.append(head)
            lines += [o.summary() for o in w.outcomes]
            for sid in w.skipped:
                lines.append(f"  ○ {sid}: already done, skipped")
            for sid, files in w.merge_conflicts.items():
                lines.append(
                    f"  ✗ {sid}: merge conflict {', '.join(files[:5])} — this is "
                    f"evidence of incorrect write_scope, not something to resolve manually"
                )
        if self.stopped_at:
            lines.append(f"\n⏸ stopped at {self.stopped_at}")
        if self.cost_usd:
            lines.append(f"cost: ${self.cost_usd:.2f}")
        return "\n".join(lines)


def run_epic(
    epic_id: str,
    plan: Plan,
    *,
    project: Path,
    client: ClientAdapter,
    config: Config,
    state: StateStore,
    worktrees: WorktreeManager | None,
    artifact_root: Path,
    report: RunReport,
    verify_only: bool = False,
    repeat: int = 1,
) -> bool:
    """Run one epic to completion. Returns False to stop the entire sprint.

    ``verify_only``: re-verification pass (ADR-004 R13) — does not open a
    developer session; re-scores the candidate at HEAD of the story branch.
    Everything else (worktree, gates, merge, ``done``, journal) follows
    **this same path** — no separate code path.
    ``repeat``: only meaningful for re-verification — each check runs k times.
    """
    architecture = None
    arch_file = artifact_root / "architecture.md"
    if arch_file.is_file():
        architecture = parse_architecture_file(arch_file)
    contract = load_contract(artifact_root)
    catalog = load_catalog()
    state.set_current_epic(epic_id)

    for index, wave_ids in enumerate(plan.waves.get(epic_id, []), 1):
        wave = WaveReport(epic_id=epic_id, index=index)
        report.waves.append(wave)

        todo = []
        can_merge_lai = []
        for sid in wave_ids:
            state.register(sid, epic_id, wave=index)
            trang_thai = state.load().stories[sid].state
            if trang_thai is StoryStatus.DONE:
                wave.skipped.append(sid)  # resumable: skip already-done stories
            elif trang_thai is StoryStatus.VERIFIED:
                # Already passed the gate but not yet merged to main (merge
                # conflict on a prior run, user has since resolved it).
                # Only re-merge — work already lives on the story branch,
                # and the worktree may have been cleaned up.
                if worktrees is not None:
                    can_merge_lai.append(sid)
                else:
                    wave.skipped.append(sid)
            else:
                # Reset to `pending` first: no valid transition goes directly
                # from `failed` or from a dead `running` process to `running`.
                # Without this step, retries complete their work but every
                # state write is silently rejected.
                state.reset_for_retry(sid)
                todo.append(sid)

        if todo:
            _run_wave(
                todo, plan,
                project=project, client=client, config=config, state=state,
                worktrees=worktrees, artifact_root=artifact_root,
                architecture=architecture, contract=contract, catalog=catalog,
                wave=wave, verify_only=verify_only, repeat=repeat,
            )

        # Remove worktrees of **failed** stories before exiting. They sit
        # inside the project tree, and `.gitignore` only hides them from
        # git — vitest, eslint, tsc all scan directories directly and pick
        # up tests from in-progress stories. Measured on e9: the pre-deploy
        # gate reported "unit tests red" for exactly this reason — tests
        # were not red, it was reading the wrong tree.
        #
        # Commit remaining work to the branch before removing: the branch
        # preserves the work, the directory is disposable — `create`
        # reconstructs it from the branch when needed.
        if worktrees is not None:
            for o in wave.outcomes:
                if o.done:
                    continue
                story = plan.stories.get(o.story_id)
                worktrees.commit_story(
                    o.story_id,
                    f"{o.story_id}: dở dang, chốt để không mất",
                    paths=list(story.write_scope) if story else None,
                )
                worktrees.remove(o.story_id, delete_branch=False)

        if not all(o.done for o in wave.outcomes):
            report.stopped_at = f"{epic_id} · wave {index}"
            return False

        if worktrees is not None:
            journal = JournalStore(artifact_root)
            done_ids = [o.story_id for o in wave.outcomes if o.done]
            # Stories completed in a previous run but not yet merged: only
            # re-merge, **do not** re-commit — their work already lives on
            # the story branch, and the worktree may have been cleaned up.
            # Candidates were frozen right after the developer session
            # (ADR-004 R1) so there is usually nothing left to commit here.
            # Still called: any residual must reach the main branch, and
            # this step no longer writes to the journal — `candidate.frozen`
            # is the commit checkpoint.
            for sid in done_ids:
                story = plan.stories.get(sid)
                worktrees.commit_story(
                    sid,
                    f"{sid}: {story.title if story else ''}".strip(": "),
                    paths=list(story.write_scope) if story else None,
                )
            for result in worktrees.merge_wave(can_merge_lai + done_ids):
                if not result.merged:
                    wave.merge_conflicts[result.story_id] = result.conflicts
                    report.stopped_at = f"{epic_id} · wave {index} (merge)"
                    return False
                # Point of no return: work has left the transaction boundary.
                # Record **immediately** after merge, before cleaning up the
                # worktree — if the process dies between these two steps, the
                # next run must be able to see that the merge happened,
                # otherwise it re-runs a completed story and sees an empty diff.
                n = journal.read(result.story_id).attempt_no
                journal.record(result.story_id,
                               JEntry(step="merge.completed", attempt=n))
                # `done` is written **only after** the line above. G12
                # invariant: in `sprint-status.json`, `done` never appears
                # before `merge.completed` in the journal.
                _safe_transition(state, result.story_id, StoryStatus.DONE)
            for sid in can_merge_lai + done_ids:
                worktrees.remove(sid)
                n = journal.read(sid).attempt_no
                journal.record(sid, JEntry(step="attempt.committed", attempt=n))

    return True


def _run_wave(
    story_ids: list[str],
    plan: Plan,
    *,
    project: Path,
    client: ClientAdapter,
    config: Config,
    state: StateStore,
    worktrees: WorktreeManager | None,
    artifact_root: Path,
    architecture,
    contract,
    catalog,
    wave: WaveReport,
    verify_only: bool = False,
    repeat: int = 1,
) -> None:
    owned = screen_owners(plan.stories.values())
    fan_in = complexity.fan_in_counts(plan.stories.values())

    def one(story_id: str) -> StoryOutcome:
        story = plan.stories[story_id]
        co = complexity.score_story(story, project=project, owned=owned,
                                    fan_in=fan_in.get(story_id, 0))

        # Gate **before** opening a worktree or calling the model. The
        # `stories` gate already ran the same checks, but project config
        # can change after that gate approved — and every dollar spent on
        # an unexecutable story is wasted.
        pf = check_story(story, project=project, config=config, owned=owned,
                         fan_in=fan_in.get(story_id, 0))
        if not pf.executable:
            out = StoryOutcome(story_id=story_id)
            out.blocked_reason = (
                f"{STORY_NOT_EXECUTABLE}: "
                + "; ".join(m.line() for m in pf.missing)
            )
            _safe_transition(state, story_id, StoryStatus.BLOCKED,
                             reason=out.blocked_reason)
            return out

        # A single run is **one transaction**. The journal lives on disk so
        # it survives even a killed process — that is exactly when it matters.
        with StoryRunTransaction(story_id, artifact_root=artifact_root) as tx:
            workdir = project
            if worktrees is not None:
                # Re-verification: **do not** bring main into the branch —
                # the candidate is HEAD of the story branch, the exact
                # version that was scored and reviewed.
                workdir = worktrees.create(story_id, refresh=not verify_only).path
                tx.record("worktree.created", path=str(workdir),
                          undo={"worktree.remove": story_id})

            if not state.claim(story_id):
                out = StoryOutcome(story_id=story_id)
                out.blocked_reason = "already claimed by another machine"
                return out
            tx.record("status.running", undo={"status.reset": "pending"})

            run_fn = partial(verify_only_story, repeat=repeat) if verify_only else implement_story
            outcome = run_fn(
                story,
                project=project,
                workdir=workdir,
                artifact_root=artifact_root,
                client=client,
                config=config,
                catalog=catalog,
                architecture=architecture,
                contract=contract,
            )
            tx.record(
                "verification.completed",
                ok=outcome.done,
                attempts=outcome.quality_attempts,
                cost_usd=round(outcome.cost_usd, 4),
            )
            tx.record("review.completed", blocked=[
                f for a in outcome.attempts for f in a.review_findings
            ][:5])
            # Story-level gate calibration (ADR-004 R5): predicted score vs
            # actual developer attempts. Recorded here because this is the
            # first place both values are available, and the story's evidence
            # was just written. Failures are ignored — a calibration table is
            # not worth aborting a run. Re-verification has no developer
            # attempts to calibrate against.
            if not verify_only:
                try:
                    complexity.record(artifact_root, story, score=co, config=config)
                except OSError as e:
                    print(f"story size calibration {story_id}: {e}", file=sys.stderr)

            _safe_transition(state, story_id, StoryStatus.VERIFYING,
                             cost=outcome.cost_usd, attempts=outcome.quality_attempts)
            # Passing the gate != done. With worktrees there is still a
            # pending merge — write `verified`; `done` is written at wave
            # end after `merge.completed`. Without isolation there is no
            # merge step: `done` immediately.
            if outcome.done:
                qua_cong = StoryStatus.DONE if worktrees is None else StoryStatus.VERIFIED
            else:
                qua_cong = StoryStatus.FAILED
            _safe_transition(state, story_id, qua_cong, reason=outcome.blocked_reason)
            # Failed story: transaction closes immediately, nothing owed.
            # Passed story still owes commit and merge — closed at wave end.
            if not outcome.done:
                tx.commit()
        return outcome

    workers = max(1, min(config["run.max_parallel"], len(story_ids)))
    if workers == 1:
        wave.outcomes = [one(sid) for sid in story_ids]
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        wave.outcomes = list(pool.map(one, story_ids))


def _safe_transition(state: StateStore, story_id: str, to: StoryStatus, **kw) -> None:
    """Write state, but do not let a state-machine error abort the entire run.

    State records exist for the reader and for resumption; an invalid
    transition deserves a log entry, not a lost run.
    """
    try:
        state.transition(story_id, to, cost_usd=kw.get("cost", 0.0), reason=kw.get("reason", ""),
                         attempts=kw.get("attempts", 0))
    except TransitionError as e:
        # Log it. Silently swallowing this masked a real bug: a story would
        # complete and merge, but the state record stayed at its old failure.
        print(f"state {story_id}: {e}", file=sys.stderr)


def run_sprint(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    only_epic: str = "",
    sequential: bool = False,
    isolate: bool = True,
) -> RunReport:
    """Run an entire sprint: epics sequentially, stories within an epic in waves."""
    project = Path(project)
    artifact_root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    if sequential:
        cfg = Config({**cfg.values, "run.max_parallel": 1})

    report = RunReport()
    plan = load_plan(artifact_root)
    if plan.error:
        report.error = plan.error
        return report

    worktrees = None
    if isolate:
        try:
            worktrees = WorktreeManager(project)
        except GitError as e:
            report.error = f"{e} — story isolation requires a git repo; use --no-isolate if intentional"
            return report

    state = StateStore(artifact_root)

    # Reconcile state from a previous interrupted run **before** doing
    # anything else. Without this, stories stuck in `running` stay stuck
    # forever with no command to recover them; and stories that already
    # merged but whose record says `failed` get re-run on a worktree
    # branched from a branch that already contains the work — empty diff,
    # can never pass.
    report.reconciled = reconcile_all(
        artifact_root=artifact_root, state=state, worktrees=worktrees
    )

    epics = [only_epic] if only_epic else (plan.epic_order or sorted(plan.waves))
    unknown = [e for e in epics if e not in plan.waves]
    if unknown:
        report.error = f"epic not in plan: {', '.join(unknown)}"
        return report

    for epic_id in epics:
        if not run_epic(
            epic_id, plan,
            project=project, client=client, config=cfg, state=state,
            worktrees=worktrees, artifact_root=artifact_root, report=report,
        ):
            break
        state.finish_epic(epic_id)
    return report


def run_verify_only(
    project: Path | str,
    client: ClientAdapter,
    *,
    story_id: str,
    config: Config | None = None,
    repeat: int = 1,
) -> RunReport:
    """Re-verify a single story against its frozen candidate (ADR-004 R13).

    Does not open a developer session. Routes through ``run_epic`` with a
    plan reduced to a single wave of one story, so merge, ``done``,
    ``attempt.committed``, and worktree cleanup use **the same code** as a
    normal run — not a copy that can drift.
    ``repeat`` = k: each verification check runs k times on the same SHA to
    distinguish "red because of code" from "red because of load" (bug 22) —
    see ``implement.verify_only``.

    Rejects with an error code when there is nothing to re-verify: story
    never had a candidate (no story branch or ``candidate.frozen`` marker),
    or is already ``done``.
    """
    project = Path(project)
    artifact_root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    report = RunReport()
    plan = load_plan(artifact_root)
    if plan.error:
        report.error = plan.error
        return report
    story = plan.stories.get(story_id)
    if story is None:
        report.error = f"story not in plan: {story_id}"
        return report
    try:
        worktrees = WorktreeManager(project)
    except GitError as e:
        report.error = f"{e} — re-verify requires a git repo: candidate is HEAD of story branch"
        return report

    state = StateStore(artifact_root)
    report.reconciled = reconcile_all(
        artifact_root=artifact_root, state=state, worktrees=worktrees
    )
    rec = state.load().stories.get(story_id)
    if rec is not None and rec.state is StoryStatus.DONE:
        report.error = f"{story_id} already done — nothing to re-verify"
        return report
    journal = JournalStore(artifact_root).read(story_id)
    if not worktrees.has_branch(story_id) or not journal.reached("candidate.frozen"):
        report.error = (
            f"{story_id}: no candidate to re-verify — need a developer session "
            f"that froze a candidate on branch `{worktrees.branch_for(story_id)}` "
            f"(run `aisef run` first)"
        )
        return report

    mot = replace(plan, waves={story.epic_id: [[story_id]]})
    run_epic(
        story.epic_id, mot,
        project=project, client=client, config=cfg, state=state,
        worktrees=worktrees, artifact_root=artifact_root, report=report,
        verify_only=True, repeat=repeat,
    )
    return report
