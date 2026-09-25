"""The single authoritative story path (WP-6.2; RFC §5, §13–§17, §25, §26). One function, `run_story`, takes a story
from its frozen plan through admission at the parent, the developer, the two-party proof at the candidate, the
engineering-quality checks, the reviewer, the scanner, the merge and the post-merge proof, to its journaled decision
and disposal. Every stage writes typed events to the run's journal (format 3); every decision that needs history reads
a projection; a failure is one typed code from the taxonomy, retried only against the budget it names (`budget.charge`)
and otherwise rolled back. No V1 code is consulted; the only legacy entry is the seam, checked before the story
begins. Nothing here names a raw verdict: product truth is read through the binding and routed by measurement point."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from aisef2.arch.enums import ControlProjection as P, EventType as T, MeasurementPoint, Owner, SubjectAbsence
from aisef2.control import budget
from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.errors import InvariantError
from aisef2.journal.format2 import OperationOutcome as O
from aisef2.orchestrate import gate, seam
from aisef2.orchestrate.adapters import (
    Developer, Merger, ProviderOutage, ResourceUnavailable, Reviewer, Scanner, Workspace, confine, unconfine,
)
from aisef2.orchestrate.merge import merge, reprove
from aisef2.orchestrate.proof import Party, Proof, Ranged, obligations_of, prove
from aisef2.orchestrate.quality import Dependencies, DeveloperTests, Runner, TestsPolicy, assess
from aisef2.orchestrate.review import review
from aisef2.orchestrate.security import scan
from aisef2.plan.drift import CompletedStory, continue_story
from aisef2.plan.obligation import Plan
from aisef2.plan.story_admission import admit_story
from aisef2.probe.protocol import ExecutionEnv, RevisionRef
from aisef2.product.spec import ProductProofSpec


@dataclass(frozen=True, slots=True)
class StoryInputs:
    """What a story is proved with: its specs and probe factories (a factory takes the harness's `on_range` and gives
    a Probe), the execution environment, the developer's tests and the regression tests at the candidate, the test
    runner, and — only through the seam — any V1 proof modes with their typed declarations."""
    specs: Mapping[str, ProductProofSpec]
    probes: Mapping[str, Callable[[Callable], object]]
    env: ExecutionEnv
    story_tests: DeveloperTests
    regression_tests: DeveloperTests
    deps: Dependencies
    runner: Runner
    completed: Mapping[str, tuple[CompletedStory, ...]] = field(default_factory=dict)
    legacy: Mapping[str, str] = field(default_factory=dict)
    declarations: Mapping[str, SubjectAbsence] = field(default_factory=dict)
    migration_table: Mapping | None = None


@dataclass(frozen=True, slots=True)
class Adapters:
    developer: Developer
    reviewer: Reviewer
    scanner: Scanner
    merger: Merger
    workspace: Workspace


@dataclass(frozen=True, slots=True)
class Policy:
    limits: Mapping[Owner, int | None]
    tests: TestsPolicy
    tool_timeout_s: float = 120.0


@dataclass(frozen=True, slots=True)
class Attempt:
    story_id: str
    number: int
    outcome: str                     # COMMIT, ROLLBACK or RETRY — the story_state projection's word
    failure: FailureCode | None
    revision: str | None
    proofs: tuple[Proof, ...]
    checks: tuple[int, ...]
    decision_seq: int


@dataclass(frozen=True, slots=True)
class StoryResult:
    story_id: str
    attempts: tuple[Attempt, ...]
    measured: Mapping[str, CompletedStory]   # spec id -> what this story measured at the parent and after the merge

    @property
    def committed(self) -> bool:
        return self.attempts[-1].outcome == "COMMIT"

    @property
    def revision(self) -> str | None:
        return self.attempts[-1].revision


class _Sink:
    """What StoryAdmission and continuation write through: the run's journal, nothing beside it."""

    def __init__(self, run) -> None:
        self._run = run

    def emit(self, event_type, data) -> None:
        self._run.append(event_type, data)


class _Held:
    """Process ranges a stage starts, acquired into the story's scope as they start and released when the stage
    returns (§17.1) — the harness's `on_range` for the admission's probes and the test runners. Each range is
    acquired under a name distinct within the attempt: its own, the stage's, and its position in the stage."""

    def __init__(self, scope, stage: str) -> None:
        self.scope, self.stage, self._held = scope, stage, []

    def __call__(self, process_range) -> None:
        name = f"{process_range.name} [{self.stage} {len(self._held) + 1}]"
        self._held.append(self.scope.acquire(Ranged(process_range, name)))

    def release(self) -> None:
        for r in reversed(self._held):
            if self.scope.held and self.scope.held[-1] == r.name:
                self.scope.release(r)
        self._held.clear()


def _committed(run) -> frozenset[str]:
    return frozenset(s for s, st in run.state(P.STORY_STATE).items() if st["outcome"] == "COMMIT")


def _freeze_plan(run, plan: Plan) -> None:
    if not any(e.type == T.PLAN_FROZEN.value for e in run.events):
        run.append(T.PLAN_FROZEN, {"plan_id": plan.id, "plan_hash": plan.plan_hash,
                                   "roles": {o.criterion_id: o.role.value for o in plan.obligations}})


def _fail(run, story_id: str, failure: Classification, detail: str):
    data = {"story_id": story_id, "code": failure.code.value, "detail": detail}
    if failure.code is FailureCode.UNKNOWN:
        data["original"] = detail.rsplit(" ", 1)[-1] or "unknown"  # the flattened error's type name, kept as data (§22)
    return run.append(T.FAILURE_OBSERVED, data)


def run_story(run, plan: Plan, story_id: str, inputs: StoryInputs, adapters: Adapters, policy: Policy) -> StoryResult:
    """The story through the one path, attempt after attempt while the journal's budget permits a retry."""
    seam.admit_legacy(inputs.legacy, inputs.migration_table, inputs.declarations)  # before the story begins
    if not any(o.story_id == story_id for o in plan.obligations):
        raise InvariantError(f"story {story_id} has no obligation in plan {plan.id}")
    _freeze_plan(run, plan)
    attempts: list[Attempt] = []
    measured: dict[str, CompletedStory] = {}
    while True:
        attempt = _attempt(run, plan, story_id, inputs, adapters, policy, measured)
        attempts.append(attempt)
        if attempt.outcome != "RETRY":
            return StoryResult(story_id, tuple(attempts), dict(measured))


def _attempt(run, plan: Plan, story_id: str, inputs: StoryInputs, adapters: Adapters, policy: Policy,
             measured: dict[str, CompletedStory]) -> Attempt:
    ws, merger = adapters.workspace, adapters.merger
    base = merger.base()
    run.append(T.STORY_BEGIN, {"story_id": story_id, "parent": base})
    number = run.state(P.STORY_STATE)[story_id]["attempt"]
    scope = run.story(story_id)
    checks: list[int] = []
    proofs: list[Proof] = []
    failure: Classification | None = None
    detail = ""
    revision = None
    at_parent: dict[str, object] = {}
    at_merge: dict[str, object] = {}
    try:
        scratch = scope.acquire(ws.scratch(f"scratch-{story_id}"))
        impl = scope.acquire(ws.checkout(f"wt-{story_id}", base))
        verifier_wt = scope.acquire(ws.checkout(f"verifier-wt-{story_id}", base))
    except ResourceUnavailable as e:
        failure, detail = classify(FailureCode.RESOURCE_ACQUISITION_FAILED), f"resources: {e}"
        checks.append(gate.check(run, story_id, "resources", False, detail))
    if failure is None:
        held = _Held(scope, "admission")
        implementer = Party(scope, lambda on_range: _probe(inputs, on_range), "implementer")
        verifier = Party(scope, lambda on_range: _probe(inputs, on_range), "verifier")
        specs = inputs.specs
        obligations = obligations_of(plan, story_id)
        probes = {pid: make(held) for pid, make in inputs.probes.items()}
        try:
            admission = admit_story(plan, story_id, RevisionRef(base, str(impl.path)), specs=specs, probes=probes,
                                    env=inputs.env, committed_stories=_committed(run), sink=_Sink(run))
        finally:
            held.release()
        for a in admission.obligations:
            at_parent[obligations[a.criterion_id][0]] = a.decision.satisfaction
        blocking = next((a for a in admission.obligations if a.decision.failure is not None), None)
        checks.append(gate.check(run, story_id, "admission", admission.admitted,
                                 "admitted" if admission.admitted else f"{blocking.criterion_id}: "
                                                                        f"{blocking.decision.disposition.value}"))
        if not admission.admitted:
            failure, detail = blocking.decision.failure, f"admission: {blocking.decision.disposition.value}"
        else:
            continuation = continue_story(plan, admission, inputs.completed, _Sink(run))
            candidate = base
            if continuation.developer_work:
                request = run.append(T.PROVIDER_REQUEST, {"story_id": story_id,
                                                          "criteria": list(continuation.developer_work),
                                                          "budget_owner": Owner.DEVELOPER.value}).seq
                try:
                    implemented = adapters.developer.implement(story_id, continuation.developer_work, str(impl.path))
                except ProviderOutage as e:
                    failure, detail = classify(FailureCode.PROVIDER_UNAVAILABLE), f"developer outage: {e}"
                    run.append(T.PROVIDER_RESULT, {"story_id": story_id, "outcome": O.FAILED.value, "synthetic": False,
                                                   "detail": detail}, source_seqs=(request,))
                    checks.append(gate.check(run, story_id, "developer", False, detail))
                else:
                    run.append(T.PROVIDER_RESULT, {"story_id": story_id, "outcome": implemented.outcome.value,
                                                   "synthetic": False, "detail": implemented.detail},
                               source_seqs=(request,))
                    if implemented.outcome is O.COMPLETED:
                        candidate = implemented.candidate
                    checks.append(gate.check(run, story_id, "developer", implemented.outcome is O.COMPLETED,
                                             implemented.detail))
            if failure is None:
                try:
                    ws.move(impl, candidate)
                    ws.move(verifier_wt, candidate)   # the verifier's own checkout, never the implementer's
                except ResourceUnavailable as e:
                    failure, detail = classify(FailureCode.RESOURCE_ACQUISITION_FAILED), f"candidate checkout: {e}"
                    checks.append(gate.check(run, story_id, "candidate", False, detail))
            if failure is None:
                for cid in continuation.verify_at_candidate:
                    spec_id, role = obligations[cid]
                    p = prove(run, story_id, cid, specs[spec_id], role, implementer=implementer, verifier=verifier,
                              candidate=candidate, implementer_root=str(impl.path), verifier_root=str(verifier_wt.path),
                              env=inputs.env, point=MeasurementPoint.CANDIDATE)
                    proofs.append(p)
                    checks.append(gate.check(run, story_id, f"proof:{cid}", p.failure is None,
                                             "verified" if p.failure is None else p.failure.code.value))
                    if p.failure is not None:
                        failure, detail = p.failure, f"proof of {cid}: {p.failure.code.value}"
                        break
            if failure is None:
                tests_held = _Held(scope, "tests")
                try:
                    q = assess(run, story_id, str(verifier_wt.path), ws.diff(base, candidate), inputs.story_tests,
                               inputs.regression_tests, inputs.deps, inputs.runner, policy.tests,
                               interpreter=inputs.env.interpreter, timeout_s=policy.tool_timeout_s, on_range=tests_held)
                finally:
                    tests_held.release()
                checks.append(gate.check(run, story_id, "quality", q.failure is None,
                                         q.assembly.outcome.value if q.assembly.outcome else "no AdequacyOutcome"))
                if q.failure is not None:
                    failure, detail = q.failure, f"engineering quality: {q.failure.code.value}"
            if failure is None:
                confined = confine(story_id, str(verifier_wt.path))   # derived from the story's own checkout (§25)
                try:
                    rv = review(run, story_id, confined, adapters.reviewer, continuation.verify_at_candidate)
                    checks.extend(rv.checks)
                    if rv.failure is not None:
                        failure, detail = rv.failure, f"review: {rv.failure.code.value}"
                    else:
                        sc = scan(run, story_id, confined, adapters.scanner, str(scratch.path),
                                  timeout_s=policy.tool_timeout_s, attempt=number)
                        checks.extend(sc.checks)
                        if sc.failure is not None:
                            failure, detail = sc.failure, f"security: {sc.failure.code.value}"
                finally:
                    unconfine(confined)
            if failure is None:
                m = merge(run, story_id, merger, candidate)
                checks.append(m.check)
                if m.failure is not None:
                    failure, detail = m.failure, f"merge: {m.failure.code.value}"
            if failure is None:
                merged = m.merge.revision
                try:
                    ws.move(impl, merged)
                    ws.move(verifier_wt, merged)
                except ResourceUnavailable as e:
                    failure, detail = classify(FailureCode.RESOURCE_ACQUISITION_FAILED), f"merged checkout: {e}"
                    checks.append(gate.check(run, story_id, "post-merge", False, detail))
                    merger.revert(merged)
                else:
                    ps, cs = reprove(run, story_id, plan, specs, merged=merged, implementer=implementer,
                                     verifier=verifier, implementer_root=str(impl.path),
                                     verifier_root=str(verifier_wt.path), env=inputs.env, committed=_committed(run))
                    proofs.extend(ps)
                    checks.extend(cs)
                    for p in ps:
                        at_merge[p.spec_id] = p.satisfaction
                    broken = next((p for p in ps if p.failure is not None), None)
                    if broken is not None:
                        failure, detail = broken.failure, f"post-merge {broken.criterion_id}: {broken.failure.code.value}"
                        merger.revert(merged)
                    else:
                        revision = merged
    decision_seq = gate.decision(run, checks, failure is None)
    if failure is None:
        run.append(T.STORY_COMMIT, {"story_id": story_id, "revision": revision})
        outcome = "COMMIT"
    else:
        observed = _fail(run, story_id, failure, detail)
        charge = budget.charge(run.events, story_id, policy.limits)
        if charge.retry:
            run.retry(story_id, policy.limits)
            outcome = "RETRY"
        else:
            run.append(T.STORY_ROLLBACK, {"story_id": story_id}, source_seqs=(observed.seq,))
            outcome = "ROLLBACK"
    run.append(T.STORY_DISPOSE, {"story_id": story_id})
    scope.dispose()
    run.append(T.STORY_END, {"story_id": story_id})
    for spec_id in set(at_parent) | set(at_merge):
        measured[spec_id] = CompletedStory(story_id, at_parent.get(spec_id), at_merge.get(spec_id))
    return Attempt(story_id, number, outcome, failure.code if failure else None, revision, tuple(proofs),
                   tuple(checks), decision_seq)


def _probe(inputs: StoryInputs, on_range):
    """The party's probe: cycle 1 proves a story with one probe kind (python_callable), so one factory serves both
    parties; each party gets its own instance, wired to the scope through `on_range`."""
    factories = list(inputs.probes.values())
    if len(factories) != 1:
        raise InvariantError("cycle 1 proves a story with exactly one probe factory")
    return factories[0](on_range)
