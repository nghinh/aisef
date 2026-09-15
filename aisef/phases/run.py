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
from ..control.budget import BudgetConfig, BudgetGuard, BudgetLedger
from ..control.design_contract import load as load_contract
from ..control.journal import (
    Entry as JEntry,
    JournalStore,
    StoryRunTransaction,
    reconcile_all,
)
from ..control.qualification import (
    Decision as QDecision,
    Inputs as QInputs,
    MergeAttempt as QMerge,
    PHASE_RUN,
    Profile as QProfile,
    StorySnapshot as QStory,
    qualify as q_qualify,
)
from ..control.normalize import Story, parse_architecture_file
from ..control.preflight import STORY_NOT_EXECUTABLE, check_story, screen_owners
from ..control.state import StateStore, StoryStatus, TransitionError
from ..control.worktree import GitError, RunOwnedError, WorktreeManager, run_ownership
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

    def stories_for(self, epic_id: str) -> list[str]:
        """Story ids belonging to ``epic_id`` in declaration order."""
        return [sid for sid, s in self.stories.items() if s.epic_id == epic_id]


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


# ── qualification helpers ──────────────────────────────────────


def _build_qstories(state: StateStore) -> list[QStory]:
    """Project ``StateStore`` status onto the snapshot the policy reads."""
    snap = state.load()
    out: list[QStory] = []
    for sid, entry in snap.stories.items():
        out.append(QStory(
            story_id=sid,
            status=entry.state.value,
            has_candidate=bool(getattr(entry, "candidate", "")),
            verification_ok=bool(getattr(entry, "verification_ok", False)),
        ))
    return out


def _build_qinputs_snapshot(state: StateStore, artifact_root: Path) -> None:
    """Touch the state file so ``state.load()`` returns a non-empty snapshot.

    Pre-flight policy reads from disk only — empty stores always return
    ``STOP all stories done``, which is wrong when the sprint is about
    to begin.  This helper makes the initial state visible.
    """
    try:
        state.load()
    except Exception:
        pass


def _build_qstories_from_plan(plan: "Plan", state: StateStore,
                              *, epics_hint: list[str]) -> list[QStory]:
    """Story snapshots for pre-flight qualification.

    The plan is authoritative for "what stories exist"; the state is
    authoritative for "which are done".  Stories not yet registered are
    projected as ``pending``; the policy treats pending as "ready to
    verify" in this path (handled by the caller).
    """
    snap = state.load()
    out: list[QStory] = []
    considered: set[str] = set()
    for epic in epics_hint:
        for sid in plan.stories_for(epic):
            entry = snap.stories.get(sid)
            # Unregistered / ``pending`` projects to ``failed`` so the
            # policy sees a fresh retry candidate — without this mapping
            # pending falls into "unexpected state" and the run refuses
            # to start.  ``attempt=0`` on the profile keeps this retry
            # cheap.
            raw = entry.state.value if entry else "pending"
            status = raw if raw in ("done", "verified", "failed",
                                    "verifying", "running", "blocked") else "failed"
            out.append(QStory(
                story_id=sid, status=status,
                has_candidate=bool(getattr(entry, "candidate", "")),
                verification_ok=bool(getattr(entry, "verification_ok", False)),
            ))
            considered.add(sid)
    for sid, _story in plan.stories.items():
        if sid in considered:
            continue
        out.append(QStory(story_id=sid, status="failed"))
    return out


def _run_preflight_qualify(plan: "Plan", state: StateStore, cfg: Config,
                           epics_hint: list[str]):
    """Run the unified qualification policy against the plan snapshot.

    Returns the policy ``Verdict``.  Caller decides how to act on it.
    """
    return q_qualify(
        QProfile(
            phase=PHASE_RUN,
            attempt=0,
            max_retries=int(cfg.get("run.max_retries", 2)),
        ),
        QInputs(
            artifact_root_exists=True,
            run_ownership_ok=True,
            plan_error="",
            stories=tuple(_build_qstories_from_plan(plan, state, epics_hint=epics_hint)),
        ),
    )


# ── budget guard helper ────────────────────────────────────────


def make_budget_guard(project: Path, cfg: Config) -> BudgetGuard:
    """Build a ``BudgetGuard`` from project config; caller invokes
    ``guard.configure`` once and ``guard.reserve`` per paid call."""
    cap_usd = float(cfg.get("run.cost_cap_usd", 0.0) or 0.0)
    cap_turns = int(cfg.get("run.turn_cap", 0) or 0)
    cap_seconds = float(cfg.get("run.wall_clock_cap_seconds", 0.0) or 0.0)
    guard = BudgetGuard(BudgetLedger(project))
    if cap_usd or cap_turns or cap_seconds:
        guard.configure(BudgetConfig(
            cap_usd=cap_usd, cap_turns=cap_turns, cap_seconds=cap_seconds,
        ))
    return guard


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

    for index, wave_ids in _effective_waves(plan, epic_id, project=project,
                                            config=config, state=state,
                                            artifact_root=artifact_root):
        wave = WaveReport(epic_id=epic_id, index=index)
        report.waves.append(wave)

        todo = []
        can_merge_lai = []
        for sid in wave_ids:
            state.register(sid, epic_id, wave=index)
            trang_thai = state.load().stories[sid].state
            if trang_thai is StoryStatus.DONE:
                # Bỏ qua story đã xong là điều kiện để chạy lại được — nhưng chỉ
                # khi nó **vẫn còn** xong. Tiêu chí bị sửa sau khi story đã trộn
                # làm mã tiêu chí mang nội dung khác, và bằng chứng ghi công cho
                # mã ấy giờ chứng minh hành vi khác (lỗi 159). Chạy lại không gỡ
                # được: việc cũ nằm trên nhánh chính nên người viết mã mở ra thấy
                # xanh sẵn. Nên dừng và nói, để người vận hành gắn lại mã hoặc
                # trả tiêu chí về — đây là quyết định của họ, không của khung.
                story_da_xong = plan.stories.get(sid)
                _, truot = (_done_criteria_drift(story_da_xong,
                                                 artifact_root=artifact_root)
                            if story_da_xong is not None else (False, []))
                if truot and not report.stopped_at:
                    report.stopped_at = (
                        f"{epic_id} · wave {index} ({sid}): acceptance criteria changed "
                        f"since this story was marked done — {', '.join(truot)} now carry "
                        f"different criteria, so the tests credited to them prove "
                        f"something else. Re-tag the tests or restore the criteria the "
                        f"codes were written for; re-running cannot fix it, the work is "
                        f"already on the main branch (lỗi 159)")
                    from ..harness.runlog import run_log

                    run_log(artifact_root, f"story={sid} STOPPED {report.stopped_at}")
                    return False
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
            candidates = {}
            for sid in can_merge_lai + done_ids:
                history = journal.read(sid)
                frozen = history.last("candidate.frozen")
                verified = history.last("verification.completed")
                valid = (frozen is not None and verified is not None
                         and verified.seq > frozen.seq and verified.attempt == frozen.attempt
                         and verified.data.get("ok") and not frozen.data.get("error"))
                candidates[sid] = str(frozen.data.get("sha") or "") if valid else ""
            merge_results: list = []
            for result in worktrees.merge_wave(can_merge_lai + done_ids, candidates=candidates):
                merge_results.append(result)
                if not result.merged:
                    wave.merge_conflicts[result.story_id] = result.conflicts
                    report.stopped_at = f"{epic_id} · wave {index} (merge): {result.message}"
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
                if sid in plan.stories:
                    from ..memory import capture_advisory
                    capture_advisory(project, plan.stories[sid], config)

            # Unified qualification policy (phase 2/4): same rule used by
            # `improve` and `pre-deploy` consults this call. Only consulted
            # when there is merge work or non-done outcomes — the inline
            # ``all(o.done)`` check stays authoritative for the success
            # path so a normal "all waves done" run does not pick up a
            # spurious stop here. The verdict is recorded in the run log
            # so reviewers can answer "why did the harness stop here"
            # from disk instead of guessing.
            from ..harness.runlog import run_log
            verdict = q_qualify(
                QProfile(phase=PHASE_RUN, attempt=0,
                         max_retries=int(config["run.max_retries"])),
                QInputs(
                    stories=tuple(QStory(
                        story_id=o.story_id,
                        status=(state.load().stories[o.story_id].state.value
                                if o.story_id in state.load().stories else "pending"),
                        has_candidate=bool(o.attempts and o.attempts[-1].candidate),
                        verification_ok=o.done,
                        review_blocking=sum(
                            len(a.review_findings or []) for a in o.attempts),
                        security_blocking=sum(
                            len(a.security.blocking()) for a in o.attempts
                            if a.security is not None),
                    ) for o in wave.outcomes),
                    merges=tuple(QMerge(m.story_id, m.merged, tuple(m.conflicts))
                                 for m in merge_results),
                ),
            )
            run_log(artifact_root,
                    f"wave={epic_id}/w{index} qualified={verdict.decision.value} "
                    f"reason={verdict.reason}")
            if verdict.decision is QDecision.HUMAN and not report.stopped_at:
                report.stopped_at = (
                    f"{epic_id} · wave {index} (human): {verdict.reason}")
                return False

    return True


#: Note kind recording which criteria the story branch was written against.
_CONTRACT_NOTE = "story:contract"


def _contract_fingerprint(story: Story) -> str:
    """Hash of the acceptance criteria — what this story's tests must prove.

    The criteria only, not the whole story card: the card also carries the
    harness-added scope paths, and those move with framework upgrades while
    saying nothing about what the story is.
    """
    import hashlib

    text = "\n".join(str(c).strip() for c in (story.acceptance_criteria or []))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _contract_identities(story: Story) -> dict[str, str]:
    """Danh tính bền **từng** tiêu chí: mã vị trí -> vân tay nội dung.

    Vì sao cần bên cạnh vân tay cả cụm (lỗi 159): vân tay cả cụm chỉ nói *có gì
    đổi*, nên nó đủ để bỏ nhánh cũ đi (lỗi 143) nhưng không nói được **mã nào**
    giờ mang tiêu chí khác. Một story đã `DONE` và đã trộn vào nhánh chính không
    còn nhánh nào để bỏ, nên câu duy nhất còn trả lời được là "mã nào trượt".
    """
    from ..control.acceptance import identities

    return identities(story.id, [str(c) for c in (story.acceptance_criteria or [])])


def _done_criteria_drift(
    story: Story, *, artifact_root: Path
) -> tuple[bool, list[str]]:
    """`(có mốc, các mã đã trượt)` của một story **đã xong**.

    Lỗ mà lỗi 143 không bịt được: nó bỏ *nhánh* story khi tiêu chí đổi, nên ca
    "lượt sau kế thừa việc viết cho tiêu chí khác" đã xong. Việc của một story
    đã trộn vào nhánh chính thì không còn nhánh nào để bỏ — bản án `DONE` đứng
    trên bằng chứng đã trượt danh tính, và vòng chạy sau *bỏ qua* nó không một
    tiếng. Đo trên marks-cli STORY-01-02: rút `AC-1.2-1` sau khi đã trộn.

    `có mốc` là `False` khi ghi chú hợp đồng không mang `codes` — corpus chạy
    trước bản sửa này. *Không đo được* phải khác *đo ra không sao*: trộn hai cái
    lại thì mọi dự án cũ lặng lẽ thành hợp lệ, đúng lớp lỗi đạt-sai đang sửa.
    """
    from ..control.acceptance import drift
    from ..harness.observe import NOTE, EvidenceStore

    last = EvidenceStore(artifact_root).read(story.id).last(NOTE, _CONTRACT_NOTE)
    truoc = (last.detail if last else {}).get("codes") or {}
    if not truoc:
        return False, []
    return True, drift(truoc, _contract_identities(story))


def _drop_branch_written_for_other_criteria(
    story: Story, *, worktrees: WorktreeManager, artifact_root: Path
) -> None:
    """Discard a story branch whose commits were written against other criteria.

    A failed story keeps its branch on purpose: the next attempt builds on the
    last one. But when the operator amends the story — which is exactly what the
    plan-deadlock message asks them to do — those commits answer a question no
    longer being asked, and criteria **codes** survive renumbering. Measured on
    todo-oc STORY-04-02 2026-09-14: after AC-1 was dropped and AC-2/AC-3 merged,
    the branch still carried `AC-STORY-04-02-1: textarea has a visible
    placeholder` — a test that now satisfies the *criteria have tests* check for
    a criterion about button opacity, while the criterion it claims to cover has
    no test at all. The developer opened a tree where everything was already
    green and wrote nothing. No gate can read prose and catch this; the only
    honest move is to not carry the old work over.
    """
    from ..harness.observe import NOTE, Event, EvidenceStore
    from ..harness.runlog import run_log

    store = EvidenceStore(artifact_root)
    now = _contract_fingerprint(story)
    last = store.read(story.id).last(NOTE, _CONTRACT_NOTE)
    truoc = last.detail if last else {}
    before = str(truoc.get("fingerprint") or "")
    # `codes` là bản vá muộn (lỗi 159): các corpus đã chạy có ghi chú *không*
    # mang nó, và nếu chỉ ghi khi vân tay đổi thì chúng **không bao giờ** có
    # mốc so — tức câu "mã nào trượt" mãi không trả lời được ở đúng những dự án
    # đã có việc để mất. Nên vẫn ghi lại để điền mốc, nhưng không bỏ nhánh: mốc
    # thiếu là khiếm khuyết bản ghi, không phải tiêu chí đã đổi.
    if before == now and truoc.get("codes"):
        return
    if before and before != now and worktrees.has_branch(story.id):
        worktrees.remove(story.id, delete_branch=True)
        run_log(artifact_root,
                f"story={story.id} criteria changed since the last attempt — "
                f"story branch discarded, starting from the base again")
    store.record(story.id, Event(kind=NOTE, name=_CONTRACT_NOTE,
                                 detail={"fingerprint": now,
                                         "codes": _contract_identities(story)}))


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
    from ..harness.runlog import run_log
    run_log(artifact_root, f"wave={wave.epic_id}/w{wave.index} START stories={','.join(story_ids)}")

    owned = screen_owners(plan.stories.values())
    fan_in = complexity.fan_in_counts(plan.stories.values())

    def one(story_id: str) -> StoryOutcome:
        story = plan.stories[story_id]
        co = complexity.score_story(story, project=project, owned=owned,
                                    fan_in=fan_in.get(story_id, 0), config=config)

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
            if worktrees is not None and not verify_only:
                _drop_branch_written_for_other_criteria(
                    story, worktrees=worktrees, artifact_root=artifact_root)
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
            last = outcome.attempts[-1] if outcome.attempts else None
            tx.record("review.completed", blocked=[
                f for a in outcome.attempts for f in a.review_findings
            ][:5], outcome=("REVIEW_UNRUNNABLE" if last is not None and last.review_unrunnable
                             else "BLOCK" if last is not None and last.review_findings
                             else "PASS" if last is not None and last.ok else "NONE"),
                review_executions=sum(1 for a in outcome.attempts if a.review_attempt),
                developer_attempts=outcome.quality_attempts)
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
        if not outcome.done or worktrees is None:
            from ..memory import capture_advisory
            capture_advisory(project, story, config)
        return outcome

    workers = max(1, min(config["run.max_parallel"], len(story_ids)))
    if workers == 1:
        wave.outcomes = [one(sid) for sid in story_ids]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            wave.outcomes = list(pool.map(one, story_ids))
    passed = sum(1 for o in wave.outcomes if o.done)
    wave_cost = sum(o.cost_usd for o in wave.outcomes)
    run_log(artifact_root, f"wave={wave.epic_id}/w{wave.index} DONE {passed}/{len(wave.outcomes)} passed ${wave_cost:.2f}")


def _effective_waves(plan: "Plan", epic_id: str, *, project: Path, config: Config,
                     state: StateStore, artifact_root: Path | None = None):
    """Yield `(index, story_ids)` for the epic: the planned waves, each
    re-split by **effective** write scope at the moment it is about to run.

    The plan's waves were cut from declared scopes. The guard grants every
    test-bearing story the shared verification config files while the sprint
    is bootstrapping (`normalize.bootstrap_grants`), so in a fresh tree every
    story of the first wave may create `conftest.py`/`pytest.ini` — three did
    on LedgerLock, with different content, and their merges would have
    collided (lỗi 185 / D-031). Stories holding the same grant do not run
    together: the first runs alone, merges, and — the tree now bootstrapped
    — the rest run in parallel as planned. A lazy generator so each split is
    computed **after** the previous group merged.
    """
    from ..control import scheduler
    from ..control.normalize import bootstrap_grants, bootstrapping

    for index, ids in enumerate(plan.waves.get(epic_id, []), 1):
        pending = list(ids)
        while pending:
            bootstrap = bootstrapping(project) and not any(
                r.state is StoryStatus.DONE for r in state.load().stories.values())
            sched = []
            grants: dict[str, list[str]] = {}
            for sid in pending:
                story = plan.stories.get(sid)
                declared = tuple(story.write_scope) if story else ()
                grants[sid] = (bootstrap_grants(story, project, config, bootstrap=bootstrap)
                               if story else [])
                sched.append(scheduler.Story(id=sid, write_scope=declared + tuple(grants[sid])))
            group = [s.id for s in scheduler.build_waves(sched)[0]] if sched else []
            if len(group) < len(pending) and artifact_root is not None:
                from ..harness.runlog import run_log

                held = sorted({g for sid in group for g in grants.get(sid, [])})
                run_log(artifact_root, (
                    f"epic={epic_id} wave {index} split: {', '.join(group)} first"
                    + (f" (may create {', '.join(held)})" if held else "")
                    + f"; {', '.join(s for s in pending if s not in group)} after it merges"))
            yield index, group
            pending = [s for s in pending if s not in group]


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


def _qualify_wave(
    outcomes: list[StoryOutcome],
    *,
    state: StateStore,
    merges: list | None = None,
    attempt: int = 0,
    max_retries: int = 0,
) -> QDecision:
    """Apply the unified qualification rule to a finished wave.

    Bespoke ``run_epic`` checks — merge conflicts, blocked stories, done /
    not-done boundary — collapse into one call. The verdict is translated
    into the existing ``stopped_at`` / ``merge_conflicts`` surface so old
    readers and reports still work; new ones read the same Verdict in
    evidence via the ``run.qualified`` journal step recorded by the caller.
    """
    snaps: list[QStory] = []
    for o in outcomes:
        rec = state.load().stories.get(o.story_id)
        status = rec.state.value if rec is not None else "pending"
        review_blocking = sum(
            len(a.review_findings or []) for a in o.attempts
        )
        security_blocking = 0
        for a in o.attempts:
            if a.security is not None:
                security_blocking += len(a.security.blocking())
        snaps.append(QStory(
            story_id=o.story_id, status=status,
            has_candidate=bool(o.attempts and o.attempts[-1].candidate),
            verification_ok=o.done,
            review_blocking=review_blocking,
            security_blocking=security_blocking,
        ))
    return q_qualify(
        QProfile(phase=PHASE_RUN, attempt=attempt, max_retries=max_retries),
        QInputs(
            stories=tuple(snaps),
            merges=tuple(QMerge(m.story_id, m.merged, tuple(m.conflicts))
                         for m in (merges or [])),
        ),
    ).decision


def run_sprint(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    only_epic: str = "",
    sequential: bool = False,
    isolate: bool = True,
) -> RunReport:
    try:
        with run_ownership(project):
            return _run_sprint_owned(project, client, config=config, only_epic=only_epic,
                                     sequential=sequential, isolate=isolate)
    except RunOwnedError as exc:
        return RunReport(error=str(exc))


def _run_sprint_owned(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    only_epic: str = "",
    sequential: bool = False,
    isolate: bool = True,
) -> RunReport:
    """Run an entire sprint: epics sequentially, stories within an epic in waves."""
    from ..harness.runlog import run_log

    project = Path(project)
    artifact_root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    if sequential:
        cfg = Config({**cfg.values, "run.max_parallel": 1})

    report = RunReport()
    # `client=` is the single most load-bearing fact about a run and was the
    # one thing its own log did not say: reading a finished corpus, which client
    # produced it had to be inferred from which config directories exist on disk.
    run_log(artifact_root, f"sprint START client={client.id} "
                           f"epics={only_epic or 'all'} parallel={not sequential} isolate={isolate}")
    plan = load_plan(artifact_root)
    if plan.error:
        report.error = plan.error
        run_log(artifact_root, f"sprint ERROR {plan.error}")
        return report

    worktrees = None
    if isolate:
        try:
            worktrees = WorktreeManager(project)
        except GitError as e:
            report.error = f"{e} — story isolation requires a git repo; use --no-isolate if intentional"
            run_log(artifact_root, f"sprint ERROR {report.error}")
            return report

    state = StateStore(artifact_root)

    report.reconciled = reconcile_all(
        artifact_root=artifact_root, state=state, worktrees=worktrees
    )

    epics_hint = [only_epic] if only_epic else (plan.epic_order or sorted(plan.waves))

    thieu = _missing_tools(project, cfg)
    if thieu:
        report.error = ("verification tools missing where they will run — "
                        + "; ".join(thieu) + " — fix the environment (`aisef doctor`) "
                        "before paying for a session (D-028)")
        run_log(artifact_root, f"sprint ERROR {report.error}")
        return report

    # Pre-flight qualification is **available** (see
    # ``_run_preflight_qualify``), but the wiring is opt-in via config
    # ``run.qualify_preflight=true`` so existing tests and callers are
    # unaffected.  The hook is the single change surface when the
    # operator wants the new gate active.
    if bool(cfg.get("run.qualify_preflight", False)):
        qverdict = _run_preflight_qualify(plan, state, cfg, epics_hint)
        if qverdict.is_terminal:
            run_log(artifact_root, f"sprint QUALIFY {qverdict.decision.value} {qverdict.reason}")
            if qverdict.decision is QDecision.HUMAN:
                report.error = f"qualify: {qverdict.reason}"
            else:
                report.stopped_at = qverdict.reason
            return report

    epics = epics_hint
    unknown = [e for e in epics_hint if e not in plan.waves]
    if unknown:
        report.error = f"epic not in plan: {', '.join(unknown)}"
        run_log(artifact_root, f"sprint ERROR {report.error}")
        return report

    for epic_id in epics:
        run_log(artifact_root, f"epic={epic_id} START")
        if not run_epic(
            epic_id, plan,
            project=project, client=client, config=cfg, state=state,
            worktrees=worktrees, artifact_root=artifact_root, report=report,
        ):
            run_log(artifact_root, f"epic={epic_id} STOPPED at={report.stopped_at}")
            break
        state.finish_epic(epic_id)
        run_log(artifact_root, f"epic={epic_id} DONE")
    # Refresh the ledger projection on disk. It is derived from evidence and
    # every consumer rebuilds it, so nothing depends on the file — but the file
    # is an artifact people read and commit, and after a sprint it said every
    # behaviour was a `gap` while the projection held 34 verified and 5
    # reopened (todo-cli 2026-09-13, lỗi 129). An artifact that contradicts the
    # machine's own view is worse than an absent one; writing it costs one call.
    try:
        from ..control import ledger as ledger_mod

        led = ledger_mod.build(artifact_root)
        led.write(artifact_root)
        led.index(artifact_root)
    except OSError as e:                     # a read-only artifact dir must not
        run_log(artifact_root, f"ledger refresh skipped: {e}")   # fail the sprint
    run_log(artifact_root, f"sprint DONE ${report.cost_usd:.2f} stopped={report.stopped_at or 'no'}")
    return report


def _missing_tools(project: Path, cfg: Config) -> list[str]:
    """Declared tools absent from the **declared** image, one line each.

    Only when the project declares `sandbox.image`: an explicitly chosen
    environment is checked before any session is paid for. With no image
    declared the provider picks a default and `aisef doctor` is the place to
    look — a probe per `aisef run` would tax every test fixture for a
    question the fixture never asked.
    """
    if not str(cfg.get("sandbox.image", "") or "").strip():
        return []
    from ..harness import verify_image

    return [tc.line for tc in verify_image.check_tools(project, cfg, build=True)
            if not tc.ok]


def run_verify_only(
    project: Path | str,
    client: ClientAdapter,
    *,
    story_id: str,
    config: Config | None = None,
    repeat: int = 1,
) -> RunReport:
    try:
        with run_ownership(project):
            return _run_verify_only_owned(project, client, story_id=story_id,
                                          config=config, repeat=repeat)
    except RunOwnedError as exc:
        return RunReport(error=str(exc))


def _run_verify_only_owned(
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
    if not worktrees.has_branch(story_id) or not (
            journal.reached("candidate.frozen") or journal.reached("commit.created")):
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
