"""RFC §13 — StoryAdmission: a runtime gate at the story's exact frozen parent SHA (F7).

* **Probes run here**, and only here in the planning plane: each obligation's probe, at the parent revision named by
  its full SHA (`RevisionRef` refuses an abbreviated one).
* **Routing is on `ContractSatisfaction`, never the raw verdict** (§10.1). This module does not name the verdict type
  (static check NO_RAW_VERDICT_ROUTING); owners come from the F2 routing table at `MeasurementPoint.PARENT`.
* **The disposition table** (`classify`) is §13's, row for row. A typed INDETERMINATE keeps its declared row; one with
  no declared routing is PROBE_INVALID, never a developer outcome. PLAN_CONTRADICTION is raised when the parent
  cannot be reconciled with the plan's own record: a PRESERVE measured UNSATISFIED whose introducing story already
  committed (§13's example). §22 names no failure code for PLAN_CONTRADICTION, so none is charged: it blocks.
* **No developer call before admission** (§13). Every evaluation and the admission itself are emitted to a sink;
  `ordering_problems` fails any `provider/request` that is not preceded by this story's `story/admitted` permitting
  it, and `request_developer` refuses to emit one. A developer call is permitted when the story is admitted and at
  least one obligation is READY — READY, or PRE_SATISFIED with remaining work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import (
    ContractSatisfaction, Enforcement, EventType, MeasurementPoint, ObligationRole, ParentExpectation,
    ProbeExecutionStatus, StoryAdmissionDisposition,
)
from aisef2.control.owner import Classification, FailureCode, classify as owner_of
from aisef2.control.routing import STORY_ADMISSION, UnroutableOutcome, route
from aisef2.errors import InvariantError
from aisef2.plan.obligation import Plan, PlanObligation
from aisef2.probe.protocol import ExecutionEnv, HarnessProbe, ProbeRecord, RevisionRef, run_probe
from aisef2.product.contract import plain
from aisef2.product.outcome import InvalidSpec, contract_satisfaction
from aisef2.product.spec import ProductProofSpec

D = StoryAdmissionDisposition
_S, _U = ContractSatisfaction.SATISFIED, ContractSatisfaction.UNSATISFIED
#: §13, the rows keyed by (role, expected, measured satisfaction). The INDETERMINATE and probe-status rows are the F2
#: routing table's (control/routing.py) and are read from it.
TABLE: dict[tuple[ObligationRole, ParentExpectation, ContractSatisfaction], StoryAdmissionDisposition] = {
    (ObligationRole.INTRODUCE, ParentExpectation.UNSATISFIED_AT_PARENT, _U): D.READY,
    (ObligationRole.INTRODUCE, ParentExpectation.UNSATISFIED_AT_PARENT, _S): D.PRE_SATISFIED,
    (ObligationRole.PRESERVE, ParentExpectation.SATISFIED_AT_PARENT, _S): D.READY,
    (ObligationRole.PRESERVE, ParentExpectation.SATISFIED_AT_PARENT, _U): D.PRECONDITION_BROKEN,
    (ObligationRole.VERIFY, ParentExpectation.UNCONSTRAINED, _S): D.READY,
    (ObligationRole.VERIFY, ParentExpectation.UNCONSTRAINED, _U): D.READY,
}
BLOCKING = (D.PRECONDITION_BROKEN, D.PLAN_CONTRADICTION, D.PROBE_UNRUNNABLE, D.PROBE_INVALID)


@dataclass(frozen=True, slots=True)
class Decision:
    disposition: StoryAdmissionDisposition
    failure: Classification | None
    satisfaction: ContractSatisfaction | None
    rule: str


@dataclass(frozen=True, slots=True)
class ObligationAdmission:
    criterion_id: str
    record: ProbeRecord
    decision: Decision


@dataclass(frozen=True, slots=True)
class StoryAdmissionResult:
    story_id: str
    parent_sha: str
    obligations: tuple[ObligationAdmission, ...]
    admitted: bool
    developer_call_permitted: bool


def classify(obligation: PlanObligation, result, spec: ProductProofSpec, introducer_committed: bool) -> Decision:
    """§13: the disposition of one obligation from its probe result at the parent. Routes on satisfaction only; owners
    are the F2 routing table's at MeasurementPoint.PARENT."""
    try:
        routed = route(result, spec, MeasurementPoint.PARENT, obligation.role)
    except UnroutableOutcome:
        routed = None
    if result.status is ProbeExecutionStatus.UNRUNNABLE:
        return Decision(D.PROBE_UNRUNNABLE, routed.failure, None, "§13: probe UNRUNNABLE -> PROBE_UNRUNNABLE, owner "
                                                                  "ENVIRONMENT")
    if result.status is ProbeExecutionStatus.INVALID_SPEC:
        return Decision(D.PROBE_INVALID, routed.failure, None, "§13: probe INVALID_SPEC -> PROBE_INVALID")
    satisfaction = contract_satisfaction(result, spec)
    if satisfaction is ContractSatisfaction.INDETERMINATE:
        if routed is None:
            return Decision(D.PROBE_INVALID, owner_of(FailureCode.PROBE_INVALID_SPEC), satisfaction,
                            "§13: an INDETERMINATE with no declared routing is PROBE_INVALID, never a developer outcome")
        return Decision(routed.disposition, routed.failure, satisfaction, routed.rule)
    row = TABLE.get((obligation.role, obligation.expected_parent, satisfaction))
    if row is None or routed is None or routed.decided_by != STORY_ADMISSION:
        raise UnroutableOutcome(f"§13 has no row for {obligation.role.value} expecting "
                                f"{obligation.expected_parent.value} measured {satisfaction.value}")
    if row is D.PRECONDITION_BROKEN and introducer_committed:
        return Decision(D.PLAN_CONTRADICTION, None, satisfaction,
                        "§13: a PRESERVE measured UNSATISFIED whose introducing story already committed")
    failure = owner_of(FailureCode.PRECONDITION_BROKEN) if row is D.PRECONDITION_BROKEN else None
    return Decision(row, failure, satisfaction, f"§13: {obligation.role.value} expecting "
                                                f"{obligation.expected_parent.value}, measured {satisfaction.value}")


class MemorySink:
    """The in-memory event sink StoryAdmission writes to until the journal (P3) exists. Append-only."""

    def __init__(self) -> None:
        self._events: list[tuple[EventType, dict]] = []

    def emit(self, event_type: EventType, data: Mapping) -> None:
        if not isinstance(event_type, EventType):
            raise InvariantError("an event has a typed EventType")
        self._events.append((event_type, dict(data)))

    @property
    def events(self) -> tuple[tuple[EventType, dict], ...]:
        return tuple(self._events)


def ordering_problems(events) -> list[str]:
    """§13: no `provider/request` for a story unless that story's `story/admitted` came first and permitted it."""
    permitted: dict[str, bool] = {}
    out = []
    for n, (event_type, data) in enumerate(events):
        if event_type is EventType.STORY_ADMITTED:
            permitted[data["story_id"]] = data["developer_call_permitted"]
        elif event_type is EventType.PROVIDER_REQUEST and permitted.get(data["story_id"]) is not True:
            out.append(f"event {n}: provider/request for {data['story_id']} before a story/admitted permitting it")
    return out


def request_developer(sink: MemorySink, story_id: str, data: Mapping | None = None) -> None:
    """Emit a developer `provider/request` — refused unless this story's admission permitted it."""
    if ordering_problems(sink.events + ((EventType.PROVIDER_REQUEST, {"story_id": story_id}),)):
        raise InvariantError(f"no developer call for {story_id}: story/admitted has not permitted one")
    sink.emit(EventType.PROVIDER_REQUEST, {"story_id": story_id, **(data or {})})


def admit_story(plan: Plan, story_id: str, parent: RevisionRef, *, specs: Mapping[str, ProductProofSpec],
                probes: Mapping[str, HarnessProbe], env: ExecutionEnv, committed_stories: frozenset[str],
                sink: MemorySink) -> StoryAdmissionResult:
    """Run every obligation of `story_id` at `parent` and emit its dispositions. Nothing is routed on a raw verdict."""
    if not isinstance(parent, RevisionRef):
        raise InvariantError("StoryAdmission runs at a RevisionRef — the story's exact frozen parent, by full SHA")
    mine = [o for o in plan.obligations if o.story_id == story_id]
    if not mine:
        raise InvariantError(f"story {story_id} has no obligation in plan {plan.id}")
    introducer = {o.product_proof_spec_id: o.story_id for o in plan.obligations if o.role is ObligationRole.INTRODUCE}
    admissions = []
    for o in mine:
        spec = specs[o.product_proof_spec_id]
        probe = probes.get(spec.probe_id)
        record = run_probe(probe, spec, parent, env) if probe is not None else ProbeRecord(
            spec.id, spec.semantic_hash, spec.probe_id, spec.probe_digest, parent.sha, Enforcement.UNAVAILABLE,
            InvalidSpec(f"probe {spec.probe_id} is not in the harness catalogue"))
        decision = classify(o, record.result, spec, introducer.get(o.product_proof_spec_id) in committed_stories)
        sink.emit(EventType.PROBE_EVALUATED, {"story_id": story_id, "criterion_id": o.criterion_id,
                                              "record": plain(record)})
        admissions.append(ObligationAdmission(o.criterion_id, record, decision))
    admitted = not any(a.decision.disposition in BLOCKING for a in admissions)
    call = admitted and any(a.decision.disposition is D.READY for a in admissions)
    result = StoryAdmissionResult(story_id, parent.sha, tuple(admissions), admitted, call)
    sink.emit(EventType.STORY_ADMITTED, {"story_id": story_id, "parent": parent.sha, "admitted": admitted,
                                         "developer_call_permitted": call,
                                         "dispositions": {a.criterion_id: a.decision.disposition.value
                                                          for a in admissions}})
    return result
