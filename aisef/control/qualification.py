"""Unified qualification policy — one decision rule for run/repair/verify.

Three phases used to each carry their own collection of ad-hoc checks:

* ``run`` decided blocked/continue from ``preflight`` only; the rest of the
  loop relied on inline state writes.
* ``improve`` rebuilt the same question out of ``stop_reason`` plus a
  ``qualification`` list growing since 2026-09-05 (stale candidate, missing
  evidence, missing kinds, infrastructure failures, product failures outside
  the queue).
* ``deploy`` decided pass/fail out of a long sequence of gate checks that
  duplicated the same questions (approval, story status, QA, runbook,
  Dockerfile, isolation, waiver).

Three callers, six answer shapes, and one shared question: **given what is on
disk, what should the harness do next?** This module is the answer. It is a
**pure function** over the inputs it already needs to read, so it can be
tested without a project, without a worktree, and without a model call.

Backward compatibility: the existing entry points still produce their original
shapes (PreDeployReport, ImproveReport.qualification, run.py state
transitions). They ask ``qualify`` and translate the Decision into their
existing surface; old callers that bypass ``qualify`` keep working. The new
return type is **additive** — old persistence formats remain valid.

Six outcomes, one symbol table:

* ``retry_infra`` — the infrastructure (network, daemon, timeout) is the
  problem; the agent's work is fine, the harness should try again.
* ``repair`` — a behavior is GAP or REOPENED in the ledger, with a verifier
  that can prove it (test, mockup, FR). Generate one repair story.
* ``verify`` — the candidate is ready to be checked: tests, lint, mockup,
  security, review. Use when the harness has finished an attempt.
* ``merge`` — the verification passed and the branch needs to land on main.
* ``stop`` — the run cannot make progress. Name the reason.
* ``human`` — the harness cannot decide; a person must (approval, scope,
  stuck plan, waived kind).

Every non-empty Decision carries a ``reasoning`` trace (which input triggered
which branch) and ``used_inputs`` — the names of the inputs that were
actually read. Reviewers can answer "why did the harness stop here" from
disk, and tests can assert on individual inputs without re-stating the
whole scene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Decision(str, Enum):
    RETRY_INFRA = "retry_infra"
    REPAIR = "repair"
    VERIFY = "verify"
    MERGE = "merge"
    STOP = "stop"
    HUMAN = "human"

    @property
    def blocks(self) -> bool:
        """Whether this Decision stops the current caller's loop."""
        return self in (Decision.STOP, Decision.HUMAN)


# Phases that ask qualify — they each translate the Decision into their
# own surface (PreDeployReport, ImproveReport.qualification, run.py state).
PHASE_RUN = "run"
PHASE_REPAIR = "repair"
PHASE_PRE_DEPLOY = "pre-deploy"
PHASES = (PHASE_RUN, PHASE_REPAIR, PHASE_PRE_DEPLOY)


@dataclass(frozen=True)
class StorySnapshot:
    """The minimum a phase must tell qualify about one story.

    ``status`` is one of ``StoryStatus`` values, but kept as a plain string
    so the module does not depend on a circular import — phases already
    import this module.
    """

    story_id: str
    status: str
    has_candidate: bool = False
    verification_ok: bool = False
    review_blocking: int = 0
    security_blocking: int = 0


@dataclass(frozen=True)
class BehaviorGap:
    """One GAP or REOPENED from the ledger (ADR-004 R2)."""

    behavior_id: str
    status: str                     # "gap" | "reopened"
    has_verifier: bool = False      # queue-eligible (ac/fr/nfr/mockup)


@dataclass(frozen=True)
class ApprovalSnapshot:
    """Approval state for one human gate."""

    gate: str
    status: str                     # "approved" | "stale" | "pending" | "rejected"


@dataclass(frozen=True)
class QaSnapshot:
    """A condensed view of one project-level QA run."""

    candidate: str = ""
    clean_tree: str = ""
    release_ready: bool = False
    failed_kinds: tuple[str, ...] = ()
    unrunnable_kinds: tuple[str, ...] = ()
    unconfigured_kinds: tuple[str, ...] = ()
    waived_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergeAttempt:
    """Outcome of one merge into the main branch."""

    story_id: str
    merged: bool
    conflicts: tuple[str, ...] = ()


@dataclass
class Profile:
    """Caller-specific inputs that change the rule.

    Every field is optional; defaults are conservative (continue / stop
    safely). Phases pass only what they actually know.
    """

    phase: str = PHASE_RUN
    #: Max attempts allowed (run only). When attempt_count >= max_retries,
    #: a non-passing result becomes ``stop`` rather than ``retry_infra``.
    attempt: int = 0
    max_retries: int = 2
    #: Stop conditions for the repair loop (improve only).
    max_loops: int = 0
    flat_loops: int = 0
    cost_cap_usd: float = 0.0
    cost_spent_usd: float = 0.0
    loops_completed: int = 0
    #: ``True`` when ``--auto`` was passed (no human gate before next round).
    auto: bool = False
    #: Degraded waiver text (deploy only). Empty = no waiver accepted.
    degraded_waiver: str = ""
    #: Required verification kinds (deploy only): kinds the deploy scope
    #: explicitly requires. Empty = accept what the QA run produced.
    required_kinds: tuple[str, ...] = ()


@dataclass
class Inputs:
    """Structured inputs to qualify. Every field is optional; callers pass
    only what they actually know. ``used_inputs`` records which ones were
    read."""

    candidate: str = ""                              # SHA expected
    evidence_present: bool = True                    # at least one event recorded
    evidence_matches_candidate: bool = True          # last events point to candidate
    artifact_root_exists: bool = True
    run_ownership_ok: bool = True
    plan_error: str = ""                             # stories.index.json error
    epic_not_in_plan: bool = False
    stories: tuple[StorySnapshot, ...] = ()
    behaviors: tuple[BehaviorGap, ...] = ()
    approvals: tuple[ApprovalSnapshot, ...] = ()
    qa: QaSnapshot | None = None
    merges: tuple[MergeAttempt, ...] = ()
    infra_failure: str = ""                          # short reason, empty = none
    plan_stuck: str = ""                             # reviewer's [stuck] tag, empty = none


@dataclass
class Verdict:
    """Result of ``qualify``. ``reasoning`` is a short list of phrases
    naming which branch produced which conclusion; ``used_inputs`` names
    the input fields the rule actually consulted. Both are present so a
    reviewer can answer "why" from disk and a test can assert on a single
    branch without restating the whole scene."""

    decision: Decision
    reason: str = ""
    reasoning: list[str] = field(default_factory=list)
    used_inputs: list[str] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        """``stop`` or ``human`` — caller should exit its loop."""
        return self.decision in (Decision.STOP, Decision.HUMAN)


# ------------------------------------------------------------ branches


def _stop(reason: str, used: list[str], trace: list[str]) -> Verdict:
    return Verdict(Decision.STOP, reason, trace, used)


def _human(reason: str, used: list[str], trace: list[str]) -> Verdict:
    return Verdict(Decision.HUMAN, reason, trace, used)


def _retry_infra(reason: str, used: list[str], trace: list[str]) -> Verdict:
    return Verdict(Decision.RETRY_INFRA, reason, trace, used)


def _repair(reason: str, used: list[str], trace: list[str]) -> Verdict:
    return Verdict(Decision.REPAIR, reason, trace, used)


def _verify(reason: str, used: list[str], trace: list[str]) -> Verdict:
    return Verdict(Decision.VERIFY, reason, trace, used)


def _merge(reason: str, used: list[str], trace: list[str]) -> Verdict:
    return Verdict(Decision.MERGE, reason, trace, used)


# ------------------------------------------------------------ policy


def qualify(profile: Profile, inputs: Inputs) -> Verdict:
    """Decide what the harness should do next.

    Pure: same inputs, same decision, no side effects, no model calls,
    no disk reads. Order of branches is fixed; each branch returns the
    first applicable answer.
    """
    trace: list[str] = []
    used: list[str] = []

    # 1. Infrastructure failure. The model is not the problem — retry the
    #    attempt, do not consume ``max_retries`` (ADR-004 R11). Only the
    #    ``run`` phase knows how to do this without state corruption.
    if inputs.infra_failure:
        used.append("infra_failure")
        trace.append(f"infra_failure: {inputs.infra_failure}")
        if profile.phase == PHASE_RUN:
            return _retry_infra(inputs.infra_failure, used, trace)
        return _stop(f"infra: {inputs.infra_failure}", used, trace)

    # 2. Plan or artifact broken. The harness cannot continue without a
    #    plan, an artifact root, or ownership.
    if inputs.plan_error:
        used.append("plan_error")
        trace.append(f"plan_error: {inputs.plan_error}")
        return _stop(f"plan: {inputs.plan_error}", used, trace)
    if not inputs.artifact_root_exists:
        used.append("artifact_root_exists")
        return _stop("artifact_root missing", used, trace)
    if not inputs.run_ownership_ok:
        used.append("run_ownership_ok")
        return _human("another run owns this project", used, trace)
    if inputs.epic_not_in_plan:
        used.append("epic_not_in_plan")
        return _stop("epic not in plan", used, trace)

    # 3. Phase-specific policy. Each branch returns directly; ``merge`` and
    #    ``repair`` are only valid in the phases that consume them.
    if profile.phase == PHASE_RUN:
        return _qualify_run(profile, inputs, trace, used)
    if profile.phase == PHASE_REPAIR:
        return _qualify_repair(profile, inputs, trace, used)
    if profile.phase == PHASE_PRE_DEPLOY:
        return _qualify_pre_deploy(profile, inputs, trace, used)
    return _stop(f"unknown phase: {profile.phase}", used, trace)


def _qualify_run(profile: Profile, inputs: Inputs, trace: list[str],
                 used: list[str]) -> Verdict:
    """Story-level decisions: blocked, merge, verify, stop."""

    # 3a. Merge conflicts. Evidence that ``write_scope`` was misdeclared
    #     (ADR-004 R7) — human must review, never auto-resolve.
    for m in inputs.merges:
        if not m.merged:
            used.append("merges")
            trace.append(f"merge conflict {m.story_id}: {', '.join(m.conflicts[:3])}")
            return _human(
                f"merge conflict in {m.story_id}: {', '.join(m.conflicts[:3])} — "
                "write_scope misdeclared",
                used, trace)

    # 3b. Stories. Anything not DONE / VERIFIED needs a closer look.
    not_done = [s for s in inputs.stories
                if s.status not in ("done", "verified")]
    for s in not_done:
        used.append("stories")
        if s.status == "blocked":
            return _stop(f"story blocked: {s.story_id}", used,
                         [*trace, f"{s.story_id}: blocked"])
        if s.status == "failed" and profile.attempt > profile.max_retries:
            return _stop(
                f"max_retries ({profile.max_retries}) reached on {s.story_id}",
                used, [*trace, f"{s.story_id}: failed beyond max_retries"])
        if s.status == "failed":
            trace.append(f"{s.story_id}: failed, attempt {profile.attempt}")
        elif s.status == "running":
            trace.append(f"{s.story_id}: running")
        elif s.status == "verifying":
            trace.append(f"{s.story_id}: verifying")

    # 3c. Verified with blocking findings — author must respond to the
    #     reviewer/security in another attempt.
    blocked_verified = [s for s in inputs.stories
                        if s.status == "verified"
                        and (s.review_blocking or s.security_blocking)]
    if blocked_verified:
        used.append("stories")
        return _verify(
            f"{len(blocked_verified)} verified story/ies with blocking findings: "
            + ", ".join(s.story_id for s in blocked_verified[:3]),
            used, trace)

    # 3d. Verification if every unfinished story has a candidate.
    pending = [s for s in not_done
               if s.status in ("failed", "verifying", "running")]
    if pending:
        used.append("stories")
        return _verify(
            f"{len(pending)} story/ies ready for verification: "
            + ", ".join(s.story_id for s in pending[:3]),
            used, trace)

    # 3e. Every unfinished story has a candidate and no blockers — the
    #     next step is merge (or, in non-isolated runs, done).
    ready = [s for s in inputs.stories
             if s.status == "verified" and s.has_candidate and s.verification_ok
             and not s.review_blocking and not s.security_blocking]
    if ready:
        used.append("stories")
        return _merge(
            f"{len(ready)} story/ies ready to merge: "
            + ", ".join(s.story_id for s in ready[:3]),
            used, trace)

    # 3f. Nothing left to do this phase.
    if not not_done:
        return _stop("all stories done for this phase", used, trace)
    return _stop("stories in unexpected state: "
                 + ", ".join(f"{s.story_id}={s.status}" for s in not_done[:3]),
                 used, trace)


def _qualify_repair(profile: Profile, inputs: Inputs, trace: list[str],
                    used: list[str]) -> Verdict:
    """Improvement-loop decisions: continue / repair / stop / human."""

    # 3a. The QA suite did not produce evidence — cannot pick a gap.
    if inputs.qa is not None:
        if not inputs.qa.candidate or inputs.qa.candidate != inputs.candidate:
            used.append("qa.candidate")
            return _stop("candidate evidence is missing or stale", used, trace)
        if inputs.qa.clean_tree and inputs.qa.clean_tree != inputs.candidate:
            used.append("qa.clean_tree")
            return _stop("requested clean-tree evidence unavailable", used, trace)

    # 3b. Required kinds missing — same condition the old ``qualification``
    #     list grew. Surfaced once, by code, not duplicated per phase.
    if inputs.qa is not None and profile.required_kinds:
        used.append("required_kinds")
        for kind in profile.required_kinds:
            if kind in inputs.qa.waived_kinds:
                continue
            if kind in inputs.qa.unconfigured_kinds or kind in inputs.qa.unrunnable_kinds:
                return _stop(f"required evidence missing: {kind}", used,
                             [*trace, f"required kind: {kind}"])

    # 3c. Plan is stuck — reviewer returned [stuck] twice with no movement.
    if inputs.plan_stuck:
        used.append("plan_stuck")
        return _human(
            f"plan stuck: {inputs.plan_stuck}", used, trace)

    # 3d. Stoppers read from disk: max_loops, flat_loops, cost cap.
    if profile.max_loops and profile.loops_completed >= profile.max_loops:
        used.append("max_loops")
        return _stop(
            f"reached improve.max_loops = {profile.max_loops}", used, trace)
    if profile.cost_cap_usd and profile.cost_spent_usd >= profile.cost_cap_usd:
        used.append("cost_cap_usd")
        return _stop(
            f"reached improve.cost_cap_usd = ${profile.cost_cap_usd:.2f}", used,
            trace)

    # 3e. Eligible gap → one repair story (R3).
    queue = [b for b in inputs.behaviors
             if b.status in ("gap", "reopened") and b.has_verifier]
    if queue:
        used.append("behaviors")
        return _repair(
            f"{len(queue)} eligible gap(s); next: {queue[0].behavior_id}",
            used, [*trace, f"queue head: {queue[0].behavior_id}"])

    # 3f. Gaps outside the queue (project-level qa:*) → human.
    outside = [b for b in inputs.behaviors
               if b.status in ("gap", "reopened") and not b.has_verifier]
    if outside:
        used.append("behaviors")
        return _human(
            f"{len(outside)} project-level gap(s) outside auto-repair queue: "
            + ", ".join(b.behavior_id for b in outside[:3]),
            used, trace)

    # 3g. Human gate ``improve`` between rounds >= 2.
    if profile.loops_completed >= 1 and not profile.auto:
        for a in inputs.approvals:
            if a.gate == "improve" and a.status != "approved":
                used.append("approvals")
                return _human(
                    f"awaiting human approval of `improve` gate "
                    f"before round {profile.loops_completed + 1}",
                    used, trace)

    return _stop("no GAP/REOPENED remaining in epic", used, trace)


def _qualify_pre_deploy(profile: Profile, inputs: Inputs, trace: list[str],
                        used: list[str]) -> Verdict:
    """Project-level decisions: pass / stop / human."""

    # 3a. Stories. Anything not DONE fails the gate.
    not_done = [s for s in inputs.stories
                if s.status not in ("done", "verified")]
    if not_done:
        used.append("stories")
        return _stop(
            f"{len(not_done)} story/ies not done: "
            + ", ".join(s.story_id for s in not_done[:3]),
            used, trace)

    # 3b. Required kinds — deploy scope. Project-level kinds only; the
    #     gate does not score stories individually here.
    if inputs.qa is not None and profile.required_kinds:
        used.append("required_kinds")
        missing: list[str] = []
        for kind in profile.required_kinds:
            if kind in inputs.qa.waived_kinds:
                continue
            if kind in inputs.qa.failed_kinds:
                missing.append(f"{kind}: failed")
            elif kind in inputs.qa.unrunnable_kinds:
                missing.append(f"{kind}: unrunnable")
            elif kind in inputs.qa.unconfigured_kinds:
                missing.append(f"{kind}: unconfigured")
        if missing:
            return _stop("required kinds not met: " + ", ".join(missing),
                         used, trace)

    # 3c. Human gates. Empty profile.required_kinds means all gates.
    pending = [a for a in inputs.approvals
               if (not profile.required_kinds or a.gate in profile.required_kinds)
               and a.status != "approved"]
    if pending:
        used.append("approvals")
        return _human(
            f"not approved: {', '.join(a.gate for a in pending[:3])}",
            used, trace)

    # 3d. Release readiness is the project-level verifier answer.
    if inputs.qa is not None and not inputs.qa.release_ready:
        used.append("qa.release_ready")
        return _stop("verification not release-ready", used, trace)

    return _stop("deploy gate met", used, trace)


__all__ = [
    "Decision",
    "Verdict",
    "PHASES",
    "PHASE_RUN",
    "PHASE_REPAIR",
    "PHASE_PRE_DEPLOY",
    "Profile",
    "Inputs",
    "StorySnapshot",
    "BehaviorGap",
    "ApprovalSnapshot",
    "QaSnapshot",
    "MergeAttempt",
    "qualify",
]