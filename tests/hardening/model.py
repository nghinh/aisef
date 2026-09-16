"""Reference state model of the Assurance Kernel (docs/ASSURANCE-KERNEL.md §6) — Phase 6.

A pure-Python, deterministic, seedable model of one story's life: stages, typed stage outcomes,
evidence records carrying their full identity tuple, retry budgets, recovery, lease and merge. It is
the SPECIFICATION the kernel is checked against:

* `test_state_model.py` drives it with thousands of seeded random traces and asserts the ten owner
  properties after EVERY transition (a violation is a specification bug — hard failure);
* the conformance half of that file runs the real `implement_story` through the synthetic client on
  scripted scenarios and compares the real terminal class against this model's — a mismatch not
  covered by a registered defect is a new kernel defect.

No git, no files, no model calls. Nothing here is imported by the product.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# ------------------------------------------------------------ vocabulary (Phase 4)

PENDING, RUNNING, VERIFYING, VERIFIED, DONE, BLOCKED, FAILED, ORPHANED, WAITING_HUMAN = (
    "pending", "running", "verifying", "verified", "done", "blocked", "failed", "orphaned", "human_required")
DEVELOP, FREEZE, VERIFY, REVIEW, SECURITY, GATE, MERGE, COMPLETE, RECOVERY, HUMAN = (
    "DEVELOP", "FREEZE", "VERIFY", "REVIEW", "SECURITY", "GATE", "MERGE", "COMPLETE", "RECOVERY", "HUMAN_REQUIRED")

PASS, QUALITY_BLOCK, UNRUNNABLE, ENVIRONMENT_FAILURE, INFRA_FAILURE, AUTH_FAILURE, NOOP, PLAN_CONFLICT, \
    ISOLATION_BREACH, MERGE_CONFLICT, HUMAN_REQUIRED = (
        "PASS", "QUALITY_BLOCK", "UNRUNNABLE", "ENVIRONMENT_FAILURE", "INFRA_FAILURE", "AUTH_FAILURE", "NOOP",
        "PLAN_CONFLICT", "ISOLATION_BREACH", "MERGE_CONFLICT", "HUMAN_REQUIRED")

MAX_RETRIES = 2          # quality attempts beyond the first
INFRA_BUDGET = MAX_RETRIES + 1   # the real kernel's default: `run.max_infra_retries < 0 → max_retries + 1`
MAX_REVIEW_RETRIES = 2
MAX_TOOL_RETRIES = 2     # tool-stage re-runs per candidate (real: implement.MAX_TOOL_RETRIES); never the infra budget
MAX_NOOP = 2
REQUIRED_PROOFS = ("test", "lint", "scope", "review", "security")

# events the trace generator may inject, by stage
EVENTS = {
    DEVELOP: ["DEVELOP_CHANGED", "DEVELOP_NOOP", "DEVELOP_TIMEOUT", "DEVELOP_CRASH", "DEVELOP_AUTH", "DEVELOP_CONTEXT",
              "DEVELOP_SCOPE_VIOLATION", "DEVELOP_TRUNK_COMMIT", "DEVELOP_ZERO_OUTPUT", "DEVELOP_MAX_TURNS_WORK",
              "DEVELOP_MAX_TURNS_UNTOUCHED", "DEVELOP_BUDGET", "DEVELOP_RATE_LIMIT",
              "PROCESS_DEATH", "LEASE_EXPIRED", "CONTRACT_CHANGE", "STALE_REPLAY", "WRONG_CANDIDATE_EVIDENCE"],
    VERIFY: ["TEST_PASS", "TEST_FAIL", "TEST_UNRUNNABLE", "PROCESS_DEATH", "CORRUPT_EVIDENCE"],
    REVIEW: ["REVIEW_PASS", "REVIEW_BLOCK", "REVIEW_BLOCK_OUTSIDE", "REVIEW_STUCK", "REVIEW_UNRUNNABLE", "REVIEW_MUTATE",
             "REVIEW_MALFORMED", "REVIEW_BUDGET", "PROCESS_DEATH"],
    SECURITY: ["SECURITY_PASS", "SECURITY_BLOCK", "SECURITY_UNRUNNABLE", "SECURITY_MALFORMED", "SECURITY_BUDGET", "PROCESS_DEATH"],
    GATE: ["GATE_EVALUATE", "PROCESS_DEATH"],
    MERGE: ["MERGE_OK", "MERGE_CONFLICT", "PROCESS_DEATH"],
    HUMAN: ["HUMAN_ARBITRATION", "HUMAN_DECLINES"],
    ORPHANED: ["RECLAIM"],
}


@dataclass
class Record:
    """One piece of evidence with its full identity tuple (docs/ASSURANCE-KERNEL.md §3)."""
    stage: str
    outcome: str
    candidate: int
    epoch: int
    tree_state: int
    env: int
    baseline_root: int
    stale: bool = False
    seq: int = 0

    def fresh_for(self, s: "Story") -> bool:
        return (not self.stale and self.candidate == s.candidate and self.epoch == s.epoch
                and self.tree_state == s.tree_state and self.env == s.env and self.baseline_root == s.baseline_root)


@dataclass
class Story:
    status: str = PENDING
    stage: str = DEVELOP
    epoch: int = 1
    candidate: int = 0            # 0 = none frozen yet; the integrated parent is 100
    tree_state: int = 0           # 0 = clean; a hash of out-of-scope dirt otherwise
    env: int = 1
    baseline_root: int = 100
    baseline_epoch: int = 1
    lease_live: bool = True
    quality_attempts: int = 0
    graded_candidates: set = field(default_factory=set)
    reviewed_candidates: set = field(default_factory=set)   # candidates the reviewer took a position on (a verdict)
    infra_attempts: int = 0
    review_executions: int = 0
    security_executions: int = 0
    #: verifier executions on the CURRENT candidate — the retry bound is per candidate (the real `review_attempt`)
    review_execs_here: int = 0
    security_execs_here: int = 0
    tool_execs_here: int = 0          # tool-stage executions on the current candidate (SS-14: bounded, not infra)
    #: review QUALITY_BLOCK per candidate: True when its findings point outside the write scope
    block_outside: dict = field(default_factory=dict)
    prev_graded_candidate: int = 0   # the graded candidate before the current one, 0 = none / an ungraded session between
    last_session_graded: bool = False  # the previous developer session produced a candidate (real: attempts[-2] not infra)
    noop_streak: int = 0
    merged: bool = False
    human_reason: str = ""
    terminal_reason: str = ""
    records: list[Record] = field(default_factory=list)
    stage_log: list[str] = field(default_factory=list)   # the stage every event was applied in
    last_event: str = ""
    last_outcome: str = ""
    developer_sessions: int = 0
    trace: list[tuple[str, str, str]] = field(default_factory=list)   # (event, outcome, next stage/status)

    # -------------------------------------------------- evidence helpers
    def fresh(self, stage: str) -> Record | None:
        for r in reversed(self.records):
            if r.stage == stage and r.fresh_for(self):
                return r
        return None

    def record(self, stage: str, outcome: str) -> Record:
        r = Record(stage, outcome, self.candidate, self.epoch, self.tree_state, self.env, self.baseline_root,
                   seq=len(self.records) + 1)
        self.records.append(r)
        return r

    def invalidate_dependent(self) -> None:
        """The evaluated state changed: every verdict computed over another state is stale for control."""
        for r in self.records:
            if not r.fresh_for(self):
                r.stale = True

    @property
    def terminal(self) -> bool:
        return self.status in (DONE, BLOCKED, FAILED)


class Kernel:
    """Applies the Phase 4 transition table. Every public transition ends in `_check()` when driven by
    the test harness; the model itself only records what happened."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.s = Story()
        self.s.status = RUNNING
        self.s.stage = DEVELOP

    # -------------------------------------------------- trace generation
    def choose_event(self) -> str:
        s = self.s
        if s.status == ORPHANED:
            return "RECLAIM"
        if s.stage == HUMAN or s.status == WAITING_HUMAN:
            return self.rng.choice(EVENTS[HUMAN])
        pool = EVENTS[s.stage]
        # bias toward the common path so traces reach later stages often enough
        weights = [6 if e.endswith(("_CHANGED", "_PASS", "MERGE_OK")) else 1 for e in pool]
        return self.rng.choices(pool, weights=weights)[0]

    # -------------------------------------------------- the transition table
    def apply(self, event: str) -> None:
        s = self.s
        s.last_event = event
        stage_before = s.stage
        out = getattr(self, "_" + event.lower())()
        s.last_outcome = out
        s.stage_log.append(stage_before)
        s.trace.append((event, out, s.status if s.terminal else s.stage))

    # generic
    def _process_death(self) -> str:
        s = self.s
        s.lease_live = False
        s.status = ORPHANED                  # T31: claim → ORPHANED on reconcile; nothing else changes
        return INFRA_FAILURE

    def _lease_expired(self) -> str:
        return self._process_death()

    def _reclaim(self) -> str:
        s = self.s
        s.lease_live = True
        s.status = RUNNING
        s.stage = DEVELOP if s.candidate == 0 else GATE   # T2 + T6': re-grade what is frozen before any new session
        return PASS

    def _contract_change(self) -> str:
        s = self.s
        s.epoch += 1                          # T32: new epoch — branch dropped, baseline recaptured at the parent
        s.candidate = 0
        s.tree_state = 0
        s.baseline_root = 100
        s.baseline_epoch = s.epoch
        s.invalidate_dependent()
        s.stage = DEVELOP
        return HUMAN_REQUIRED

    def _stale_replay(self) -> str:
        """Inject an old record again (duplicate/reordered event): it must not become fresh evidence."""
        s = self.s
        if s.records:
            old = s.records[0]
            s.records.append(Record(old.stage, old.outcome, old.candidate, old.epoch, old.tree_state, old.env,
                                    old.baseline_root, stale=old.stale, seq=len(s.records) + 1))
            s.invalidate_dependent()
        return PASS

    def _wrong_candidate_evidence(self) -> str:
        s = self.s
        s.records.append(Record("test", PASS, candidate=s.candidate + 777, epoch=s.epoch, tree_state=s.tree_state,
                                env=s.env, baseline_root=s.baseline_root, seq=len(s.records) + 1))
        s.invalidate_dependent()
        return PASS

    def _corrupt_evidence(self) -> str:
        s = self.s
        if s.records:
            s.records[-1].stale = True        # an unreadable record is no record
        return UNRUNNABLE

    # developer
    def _freeze(self) -> None:
        s = self.s
        # the deadlock pair is "two CONSECUTIVE graded attempts": an infra / no-op / capped session between them
        # breaks the pair (the real kernel reads attempts[-1] and attempts[-2] and requires neither to be infra)
        # the deadlock pair is two consecutive REVIEWED positions (real: deadlock_reason pairs graded attempts whose
        # reviewer produced a verdict; infra cuts, no-op decisions and review-absent candidates are not positions —
        # SS-63; a capped session without a candidate IS a graded attempt without findings and breaks the pair)
        if not s.last_session_graded:
            s.prev_graded_candidate = 0
        elif s.candidate in s.reviewed_candidates:
            s.prev_graded_candidate = s.candidate
        elif s.candidate not in s.graded_candidates:
            s.prev_graded_candidate = 0
        s.last_session_graded = True
        s.candidate = 1000 * s.epoch + s.developer_sessions
        s.review_execs_here = s.security_execs_here = s.tool_execs_here = 0
        s.invalidate_dependent()              # a new candidate: every verdict over the old one is stale
        s.stage = VERIFY
        self._charge_quality()                # a frozen candidate is a non-infra attempt, whatever grading then says

    def _gate_evaluate(self) -> str:
        return self._gate()

    def _develop_changed(self) -> str:
        s = self.s
        s.developer_sessions += 1
        s.noop_streak = 0
        self._freeze()                        # T5 → T13
        return PASS

    def _develop_scope_violation(self) -> str:
        s = self.s
        s.developer_sessions += 1
        s.noop_streak = 0
        s.tree_state = 7                      # out-of-scope dirt stays in the tree; freeze keeps in-scope only (T12/T13)
        self._freeze()
        s.record("violation", QUALITY_BLOCK)
        return PASS

    def _develop_noop(self) -> str:
        s = self.s
        s.developer_sessions += 1             # a no-op decision is not a position (real: infra-flagged, filtered by deadlock_reason)
        s.infra_attempts += 1                 # a session with nothing to grade spends the same budget as an infra cut
        if s.candidate == 0:
            s.noop_streak += 1                # nothing frozen: a decision, stated (T6)
            if s.noop_streak >= MAX_NOOP:
                s.status, s.terminal_reason = BLOCKED, "no-op: nothing to grade twice"
            elif s.infra_attempts >= MAX_RETRIES + 1:
                s.status, s.terminal_reason = BLOCKED, "no-op: budget exhausted"
            return NOOP
        verdict = s.fresh("gate")
        if verdict is None:                   # T6': stale or absent verdict → re-grade the frozen candidate
            s.infra_attempts -= 1             # a graded session is not a "nothing to grade" session
            self._charge_quality()            # ...it is a developer attempt whose tree the gate scores
            # a re-graded no-op IS a graded position: the same candidate blocked twice for the same out-of-scope
            # reason pairs with its previous grade (real: deadlock_reason pairs graded attempts; seed 2531)
            s.prev_graded_candidate = s.candidate if s.candidate in s.graded_candidates else 0
            s.last_session_graded = True
            s.stage = VERIFY
            return NOOP
        if verdict.outcome == QUALITY_BLOCK:  # T6: proven unresolved work, decision stated
            s.noop_streak += 1
            if s.noop_streak >= MAX_NOOP:
                s.status, s.terminal_reason = BLOCKED, "no-op: developer declined proven work twice"
            elif s.infra_attempts >= MAX_RETRIES + 1:
                s.status, s.terminal_reason = BLOCKED, "no-op: budget exhausted"
            return NOOP
        s.stage = GATE                        # a fresh passing verdict: nothing to do but proceed
        return NOOP

    def _develop_timeout(self) -> str:        # provider cut → infra (T9)
        return self._infra()

    def _develop_crash(self) -> str:
        return self._infra()

    def _infra(self) -> str:
        s = self.s
        s.developer_sessions += 1
        s.noop_streak = 0                      # the no-op streak (the real kernel counts TRAILING no-ops); an infra cut is not a position
        s.infra_attempts += 1
        if s.infra_attempts >= MAX_RETRIES + 1:
            s.status, s.terminal_reason = FAILED, "recurring infrastructure error"
        return INFRA_FAILURE

    def _develop_context(self) -> str:        # environment limitation, not quality (INV-G.4)
        return self._infra()

    def _develop_rate_limit(self) -> str:     # provider back-pressure → infra, retried after the delay
        return self._infra()

    def _develop_max_turns_work(self) -> str:
        """The cap hit after the session moved the tree: the work is graded (lỗi 130 — a turn counter is not a verdict)."""
        return self._develop_changed()

    def _develop_max_turns_untouched(self) -> str:
        """The cap hit with nothing written: the session was the developer's and produced no candidate — a quality
        attempt without a verdict (ADR-005 V11 (B): a free capped retry lets a thrashing agent retry forever)."""
        s = self.s
        s.developer_sessions += 1
        s.last_session_graded = False
        s.noop_streak = 0
        s.quality_attempts += 1
        if s.quality_attempts > MAX_RETRIES:
            s.status, s.terminal_reason = FAILED, "did not pass gate"
        return QUALITY_BLOCK

    def _develop_zero_output(self) -> str:
        """Tokens, no tool calls, no files: the model cannot use tools — a configuration failure, fatal and free."""
        s = self.s
        s.developer_sessions += 1
        s.status, s.terminal_reason = BLOCKED, "zero output: model cannot use tools"
        s.human_reason = "environment"
        return ENVIRONMENT_FAILURE

    def _budget(self) -> str:
        """A run-level cost cap is an operator decision, not a developer fault: typed, terminal, uncharged (INV-G.5)."""
        s = self.s
        s.status, s.terminal_reason = BLOCKED, "budget cap"
        s.human_reason = "budget"
        return HUMAN_REQUIRED

    def _develop_budget(self) -> str:
        self.s.developer_sessions += 1
        return self._budget()

    def _review_budget(self) -> str:
        self.s.review_executions += 1
        return self._budget()

    def _security_budget(self) -> str:
        self.s.security_executions += 1
        return self._budget()

    def _develop_auth(self) -> str:           # T10 fatal
        s = self.s
        s.developer_sessions += 1
        s.status, s.terminal_reason = BLOCKED, "credential rejected"
        s.human_reason = "auth"
        return AUTH_FAILURE

    def _develop_trunk_commit(self) -> str:   # T11
        s = self.s
        s.developer_sessions += 1
        s.status, s.terminal_reason = BLOCKED, "isolation breach"
        return ISOLATION_BREACH

    # deterministic verification
    def _after_test(self) -> None:
        s = self.s
        r = s.fresh("review")
        if r is None or r.outcome == UNRUNNABLE:
            s.stage = REVIEW                  # no verdict yet (or an absence): the reviewer runs
        else:
            self._after_review()              # a fresh verdict is kept on a tool re-run (reuse)

    def _test_pass(self) -> str:
        s = self.s
        s.tool_execs_here += 1
        s.record("test", PASS)
        s.record("lint", PASS)
        s.record("scope", QUALITY_BLOCK if s.tree_state else PASS)
        self._after_test()
        return PASS

    def _test_fail(self) -> str:
        s = self.s
        s.tool_execs_here += 1
        s.record("test", QUALITY_BLOCK)
        s.record("lint", PASS)
        s.record("scope", QUALITY_BLOCK if s.tree_state else PASS)
        self._after_test()                    # the reviewer and the security pass still run: one complete round of feedback
        return QUALITY_BLOCK

    def _test_unrunnable(self) -> str:        # T16: tool stage failure — never a developer attempt (INV-G.3)
        s = self.s
        s.tool_execs_here += 1
        s.record("test", UNRUNNABLE)
        s.record("lint", PASS)
        s.record("scope", QUALITY_BLOCK if s.tree_state else PASS)
        self._after_test()                    # the verifiers still run; the gate decides what the absence means (SS-14)
        return ENVIRONMENT_FAILURE

    # review — every review outcome is recorded; the security pass runs once per candidate; the GATE decides
    # what a missing verdict means (stage-local retry, bounded) and what a block means (developer, deadlock)
    def _after_review(self) -> None:
        s = self.s
        r = s.fresh("security")
        s.stage = GATE if r is not None and r.outcome != UNRUNNABLE else SECURITY   # an absence is re-run (INV-G.2)

    def _review_pass(self) -> str:
        s = self.s
        s.review_executions += 1
        s.review_execs_here += 1
        s.reviewed_candidates.add(s.candidate)
        s.record("review", PASS)
        self._after_review()
        return PASS

    def _review_block(self, outside: bool = False) -> str:
        s = self.s
        s.review_executions += 1
        s.review_execs_here += 1
        s.record("review", QUALITY_BLOCK)
        s.reviewed_candidates.add(s.candidate)
        s.block_outside[s.candidate] = outside
        self._after_review()
        return QUALITY_BLOCK

    def _review_block_outside(self) -> str:   # findings point outside the write scope — beyond the agent's reach
        return self._review_block(outside=True)

    def _review_stuck(self) -> str:           # T19: a structured [stuck] verdict is a plan finding, decided at the gate
        s = self.s
        s.review_executions += 1
        s.review_execs_here += 1
        s.reviewed_candidates.add(s.candidate)
        s.record("review", PLAN_CONFLICT)
        self._after_review()
        return PLAN_CONFLICT

    def _review_unrunnable(self) -> str:      # T20/T21: no verdict — nothing was said; the gate retries the stage
        s = self.s
        s.review_executions += 1
        s.review_execs_here += 1
        s.record("review", UNRUNNABLE)
        self._after_review()
        return UNRUNNABLE

    def _review_mutate(self) -> str:          # T20: tree restored, the execution said nothing about the candidate
        return self._review_unrunnable()

    def _review_malformed(self) -> str:       # no structured verdict: never PASS, never BLOCK — a retry of the verifier
        return self._review_unrunnable()

    # security
    def _security_pass(self) -> str:
        s = self.s
        s.security_executions += 1
        s.security_execs_here += 1
        s.record("security", PASS)
        s.stage = GATE
        return PASS

    def _security_block(self) -> str:
        s = self.s
        s.security_executions += 1
        s.security_execs_here += 1
        s.record("security", QUALITY_BLOCK)
        s.stage = GATE
        return QUALITY_BLOCK

    def _security_unrunnable(self) -> str:    # INV-G.2: no verdict; the gate retries the security stage, never the developer
        s = self.s
        s.security_executions += 1
        s.security_execs_here += 1
        s.record("security", UNRUNNABLE)
        s.stage = GATE
        return UNRUNNABLE

    def _security_malformed(self) -> str:     # no structured verdict: nothing was said — never PASS, never BLOCK
        return self._security_unrunnable()

    # gate
    def _charge_quality(self) -> None:
        """`quality_attempts` is the real kernel's `StoryOutcome.quality_attempts`: every developer SESSION whose
        tree gets graded — a new candidate, or the same candidate re-graded after a no-op over a stale verdict
        (T6') — whatever grading then says (PASS, QUALITY_BLOCK, a stage that could not run, a review that never
        ended). Infra exits (crash, timeout, auth, context) never reach the gate and are never charged (INV-G.4).
        The exhaustion decision (MAX_RETRIES) is taken only on QUALITY_BLOCK."""
        s = self.s
        s.graded_candidates.add(s.candidate)
        s.quality_attempts += 1

    def _gate(self) -> str:
        s = self.s
        proofs = {p: s.fresh(p) for p in REQUIRED_PROOFS}
        review = proofs["review"]
        if review is not None and review.outcome == PLAN_CONFLICT:                 # T19: [stuck] → owner
            s.record("gate", PLAN_CONFLICT)
            s.status, s.terminal_reason, s.human_reason, s.stage = WAITING_HUMAN, "plan conflict", "plan", HUMAN
            return PLAN_CONFLICT
        if all(r is not None and r.outcome == PASS for r in proofs.values()):
            s.record("gate", PASS)
            s.status, s.stage = VERIFIED, MERGE          # T24
            return PASS
        if any(r is not None and r.outcome == QUALITY_BLOCK for r in proofs.values()):
            s.record("gate", QUALITY_BLOCK)              # T25
            if (review is not None and review.outcome == QUALITY_BLOCK and s.block_outside.get(s.candidate)
                    and s.prev_graded_candidate and s.block_outside.get(s.prev_graded_candidate)):
                # two consecutive attempts blocked for the same out-of-scope reason: the next attempt cannot fix it
                s.status, s.terminal_reason, s.human_reason, s.stage = WAITING_HUMAN, "plan conflict", "plan", HUMAN
                return PLAN_CONFLICT
            if s.quality_attempts > MAX_RETRIES:
                s.status, s.terminal_reason = FAILED, "did not pass gate"
                return QUALITY_BLOCK
            self._recover()                              # T3: hygiene before the next developer attempt
            s.stage = DEVELOP
            return QUALITY_BLOCK
        # only absences remain: retry the stage that said nothing, bounded, never the developer (INV-G.1/G.2/G.3)
        s.record("gate", UNRUNNABLE)
        if proofs["test"] is not None and proofs["test"].outcome == UNRUNNABLE:
            if s.tool_execs_here >= 1 + MAX_TOOL_RETRIES:                      # bounded per candidate, never infra budget
                s.status, s.terminal_reason = BLOCKED, "environment: test tool unrunnable"
                s.human_reason = "environment"
            else:
                s.stage = VERIFY                                             # re-run the tool stage; fresh verdicts are kept
            return UNRUNNABLE
        if review is not None and review.outcome == UNRUNNABLE:
            if s.review_execs_here >= 1 + MAX_REVIEW_RETRIES:
                s.status, s.terminal_reason = BLOCKED, "REVIEW_UNRUNNABLE"
            else:
                s.stage = REVIEW
            return UNRUNNABLE
        if s.security_execs_here >= 1 + MAX_REVIEW_RETRIES:
            s.status, s.terminal_reason = BLOCKED, "SECURITY_UNRUNNABLE"
        else:
            s.stage = SECURITY
        return UNRUNNABLE

    def _recover(self) -> None:
        s = self.s
        if s.tree_state:
            s.tree_state = 0
            s.record("recovery", PASS)
            s.invalidate_dependent()                     # INV-K.2 — the verdict over the dirty tree is stale

    # merge
    def _merge_ok(self) -> str:
        s = self.s
        if s.status != VERIFIED or s.fresh("gate") is None or s.fresh("gate").outcome != PASS:
            return UNRUNNABLE                            # the model refuses to merge without a fresh passing gate
        s.merged = True
        s.status, s.stage = DONE, COMPLETE               # T29
        return PASS

    def _merge_conflict(self) -> str:                    # T30
        s = self.s
        s.status, s.terminal_reason = WAITING_HUMAN, "merge conflict"
        s.human_reason = "merge"
        s.stage = HUMAN
        return MERGE_CONFLICT

    # human
    def _human_arbitration(self) -> str:                 # T33 → T32
        s = self.s
        s.status = RUNNING
        s.human_reason = ""
        s.terminal_reason = ""
        return self._contract_change()

    def _human_declines(self) -> str:
        s = self.s
        s.status, s.terminal_reason = BLOCKED, f"owner declined: {s.human_reason}"
        return HUMAN_REQUIRED


# ------------------------------------------------------------ the ten properties

def check_properties(k: Kernel) -> list[str]:
    """Return every violated property after the last transition (empty = all hold)."""
    s, v = k.s, []
    ev, out = s.last_event, s.last_outcome
    stage_before = s.stage_log[-1] if s.stage_log else DEVELOP
    # 1. UNRUNNABLE review can never become developer quality failure
    if ev in ("REVIEW_UNRUNNABLE", "REVIEW_MUTATE", "REVIEW_MALFORMED") and (s.stage == DEVELOP and not s.terminal):
        v.append("P1: review unrunnable routed to the developer")
    if ev.startswith("REVIEW_") and out == UNRUNNABLE and s.quality_attempts != getattr(k, "_q_before", s.quality_attempts):
        v.append("P1: review unrunnable charged quality")
    # 2. recovery that changes evaluated state invalidates dependent evidence
    for r in s.records:
        if r.stage == "gate" and not r.stale and not r.fresh_for(s) and s.status not in (DONE,):
            v.append("P2: a gate verdict over another state is still fresh")
            break
    # 3. no PASS on foreign evidence (candidate/epoch/env)
    if s.status in (VERIFIED, DONE):
        for p in REQUIRED_PROOFS:
            r = s.fresh(p)
            if r is None or r.outcome != PASS:
                v.append(f"P3/P7: {s.status} without a fresh passing {p}")
    # 4. resume cannot change the baseline within the epoch
    if s.baseline_epoch != s.epoch:
        v.append("P4: baseline epoch drifted from the story epoch")
    # 5. no-op cannot terminate on stale evidence
    if s.terminal and s.terminal_reason.startswith("no-op: developer declined"):
        g = s.fresh("gate")
        if g is None or g.outcome != QUALITY_BLOCK:
            v.append("P5: no-op terminal without a fresh QUALITY_BLOCK")
    # 6. RUNNING requires a live lease
    if s.status == RUNNING and not s.lease_live:
        v.append("P6: RUNNING with a dead lease")
    # 7. covered by P3 for DONE; plus merged flag
    if s.status == DONE and not s.merged:
        v.append("P7: DONE before merge")
    # 8. verification/review/security never mutate the candidate
    if stage_before in (VERIFY, REVIEW, SECURITY) and ev not in ("CONTRACT_CHANGE",) and getattr(k, "_c_before", s.candidate) != s.candidate:
        v.append("P8: candidate changed during verification")
    # 9. PLAN_CONFLICT is never developer remediation
    if out == PLAN_CONFLICT and s.stage == DEVELOP:
        v.append("P9: plan conflict became developer work")
    # 10. environment failure is not behavioural evidence
    if ev == "TEST_UNRUNNABLE" and (s.quality_attempts != getattr(k, "_q_before", s.quality_attempts) or (s.stage == DEVELOP and not s.terminal)):
        v.append("P10: environment failure charged/routed as behaviour")
    return v


def run_trace(seed: int, max_steps: int = 40) -> tuple[Kernel, list[str]]:
    """Drive one seeded trace; return the kernel and every violation seen (empty = clean)."""
    k = Kernel(seed)
    violations: list[str] = []
    for _ in range(max_steps):
        if k.s.terminal:
            break
        k._q_before = k.s.quality_attempts
        k._c_before = k.s.candidate
        k.apply(k.choose_event())
        bad = check_properties(k)
        if bad:
            violations.extend(f"seed {seed} step {len(k.s.trace)} {k.s.last_event}: {b}" for b in bad)
    return k, violations
