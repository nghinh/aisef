"""RFC §10, §10.3 — the owner routing table (F2, amended by ARCHITECTURE-EXCEPTION-V2-001).

Routing is keyed on the typed **measurement point** (§10.3, §26) and **`ContractSatisfaction`** (§10.1) — never on the
raw `BehaviorVerdict`, which this module does not name (static check NO_RAW_VERDICT_ROUTING), and never on an
INDETERMINATE reason alone. At the parent the obligation role (§11, F6) decides a PRECONDITION_ABSENT row.

| point | outcome | role | route |
|---|---|---|---|
| any | not attempted | — | nothing to charge (§10) |
| any | UNRUNNABLE | — | PROBE_UNRUNNABLE — ENVIRONMENT |
| any | INVALID_SPEC | — | PROBE_INVALID_SPEC — see `owner.TAXONOMY` |
| PARENT | SATISFIED / UNSATISFIED | any | a StoryAdmission disposition (§13), not an owner row |
| PARENT | INDETERMINATE(PRECONDITION_ABSENT) | INTRODUCE | READY — expected pre-state, no failure owner |
| PARENT | INDETERMINATE(PRECONDITION_ABSENT) | PRESERVE, VERIFY | PRECONDITION_BROKEN — PLAN |
| CANDIDATE | SATISFIED | any | nothing to charge |
| CANDIDATE | UNSATISFIED | any | CONTRACT_UNSATISFIED — DEVELOPER |
| CANDIDATE | INDETERMINATE(PRECONDITION_ABSENT) | any | SUBJECT_ABSENT_AT_CANDIDATE — DEVELOPER |
| POST_MERGE | SATISFIED | any | nothing to charge |
| POST_MERGE | UNSATISFIED | any | POST_MERGE_REGRESSION — INTEGRATION |
| POST_MERGE | INDETERMINATE(PRECONDITION_ABSENT) | any | POST_MERGE_SUBJECT_LOST — INTEGRATION |
| any | INDETERMINATE(NON_CONTROLLER_SIGNAL) | any | NON_CONTROLLER_SIGNAL — INTEGRATION, never retried (V2-003) |

Anything outside these rows — an untyped result, point or role, a parent PRECONDITION_ABSENT without a role, an
INDETERMINATE reason with no row — **fails closed** with `UnroutableOutcome`: never defaulted, never DEVELOPER.
"""

from __future__ import annotations

from dataclasses import dataclass

from aisef2.arch.enums import (
    ContractSatisfaction, MeasurementPoint, ObligationRole, ProbeExecutionStatus, StoryAdmissionDisposition,
)
from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.errors import InvariantError
from aisef2.product.outcome import RESULT_TYPES, IndeterminateReason, ProbeResult, contract_satisfaction
from aisef2.product.spec import ProductProofSpec


class UnroutableOutcome(InvariantError):
    """An outcome with no routing row. Fail closed: no owner is charged and nothing is retried."""


STORY_ADMISSION = "STORY_ADMISSION"


@dataclass(frozen=True, slots=True)
class Route:
    failure: Classification | None
    decided_by: str | None
    disposition: StoryAdmissionDisposition | None
    rule: str


_P, _C, _M = MeasurementPoint.PARENT, MeasurementPoint.CANDIDATE, MeasurementPoint.POST_MERGE
_S, _U, _I = ContractSatisfaction.SATISFIED, ContractSatisfaction.UNSATISFIED, ContractSatisfaction.INDETERMINATE
_PA = IndeterminateReason.PRECONDITION_ABSENT
_NCS = IndeterminateReason.NON_CONTROLLER_SIGNAL
#: §9.3 (V2-003): the probe executed; the subject's process ended by a signal the controller did not send. The reason
#: routes to one owner at every measurement point — INTEGRATION, never retryable — because the evidence says only who
#: did *not* send the signal. Still measurement-point aware (V2-001): each point keeps its own row and its own rule.
_V3 = "§9.3, §10.3 (V2-003): executed, then a signal the controller did not send — the behavioural truth the "\
      "contract needs cannot be derived, and no cause may be invented"
_ADMISSION = STORY_ADMISSION

#: (point, satisfaction, reason, role or None for any role) -> (failure code, disposition, decided_by, rule)
_EXECUTED: dict[tuple, tuple[FailureCode | None, StoryAdmissionDisposition | None, str | None, str]] = {
    (_P, _S, None, None): (None, None, _ADMISSION, "§10.3, §13: at the parent a StoryAdmission disposition"),
    (_P, _U, None, None): (None, None, _ADMISSION, "§10.3, §13: at the parent a StoryAdmission disposition"),
    (_P, _I, _PA, ObligationRole.INTRODUCE): (None, StoryAdmissionDisposition.READY, _ADMISSION,
                                              "§10.3: INTRODUCE over an absent required subject is the expected "
                                              "pre-state — READY"),
    (_P, _I, _PA, ObligationRole.PRESERVE): (FailureCode.PRECONDITION_BROKEN,
                                             StoryAdmissionDisposition.PRECONDITION_BROKEN, _ADMISSION,
                                             "§10.3, §13: a behaviour cannot be preserved over a subject that is gone"),
    (_P, _I, _PA, ObligationRole.VERIFY): (FailureCode.PRECONDITION_BROKEN,
                                           StoryAdmissionDisposition.PRECONDITION_BROKEN, _ADMISSION,
                                           "§10.3, §13: a behaviour cannot be verified over a subject that is gone"),
    (_P, _I, _NCS, None): (FailureCode.NON_CONTROLLER_SIGNAL, StoryAdmissionDisposition.PROBE_INVALID, _ADMISSION,
                           _V3 + " — at the parent it fails closed as PROBE_INVALID, so no story is admitted on it"),
    (_C, _S, None, None): (None, None, None, "§10.3: SATISFIED at the candidate is not a failure"),
    (_C, _U, None, None): (FailureCode.CONTRACT_UNSATISFIED, None, None, "§10.3: UNSATISFIED at the candidate"),
    (_C, _I, _PA, None): (FailureCode.SUBJECT_ABSENT_AT_CANDIDATE, None, None,
                          "§10.3 (V2-001): the admitted implementation did not establish the subject"),
    (_C, _I, _NCS, None): (FailureCode.NON_CONTROLLER_SIGNAL, None, None,
                           _V3 + " — the product criterion is not proved, and no developer budget is charged"),
    (_M, _S, None, None): (None, None, None, "§10.3: SATISFIED after merge is not a failure"),
    (_M, _U, None, None): (FailureCode.POST_MERGE_REGRESSION, None, None, "§10.3, §26: a regression after merge"),
    (_M, _I, _PA, None): (FailureCode.POST_MERGE_SUBJECT_LOST, None, None,
                          "§10.3 (V2-001): a subject verified at the candidate is gone after merge"),
    (_M, _I, _NCS, None): (FailureCode.NON_CONTROLLER_SIGNAL, None, None,
                           _V3 + " — a regression after merge is never inferred without evidence"),
}


def route(result: ProbeResult | None, spec: ProductProofSpec, point: MeasurementPoint,
          role: ObligationRole | None = None) -> Route:
    if not isinstance(point, MeasurementPoint):
        raise UnroutableOutcome(f"unknown measurement point {point!r}")
    if role is not None and not isinstance(role, ObligationRole):
        raise UnroutableOutcome(f"unknown obligation role {role!r}")
    if result is None:
        return Route(None, None, None, "§10: not attempted — chargeable to no one")
    if not isinstance(result, RESULT_TYPES):
        raise UnroutableOutcome(f"{type(result).__name__} is not a typed probe result")
    if result.status is ProbeExecutionStatus.UNRUNNABLE:
        return Route(classify(FailureCode.PROBE_UNRUNNABLE), None, None, "§10.3: the observation harness cannot run")
    if result.status is ProbeExecutionStatus.INVALID_SPEC:
        return Route(classify(FailureCode.PROBE_INVALID_SPEC), None, None, "§10: not evaluable by this probe")
    satisfaction = contract_satisfaction(result, spec)
    row = _EXECUTED.get((point, satisfaction, result.reason, role)) or \
        _EXECUTED.get((point, satisfaction, result.reason, None))
    if row is None:
        raise UnroutableOutcome(f"no routing row for {point.value} {satisfaction.value} with reason "
                                f"{result.reason!r} and role {role!r}")
    code, disposition, decided_by, rule = row
    return Route(None if code is None else classify(code), decided_by, disposition, rule)
