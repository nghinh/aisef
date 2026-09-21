"""RFC §10 — the owner routing table (F2) over the legal probe-outcome space.

Routing is on **`ContractSatisfaction`** (§10.1), never on the raw `BehaviorVerdict`: this module does not name the
raw verdict at all (static check NO_RAW_VERDICT_ROUTING), so a MUST_NOT_HOLD contract routes exactly like a
MUST_HOLD one with the same satisfaction.

| site | outcome | route |
|---|---|---|
| any | not attempted | nothing to charge (§10) |
| any | UNRUNNABLE | PROBE_UNRUNNABLE — ENVIRONMENT (§10: the only row that may route there) |
| any | INVALID_SPEC | PROBE_INVALID_SPEC — see `owner.TAXONOMY` |
| PARENT | EXECUTED, any satisfaction | a plan disposition decided by StoryAdmission (§10, §13), not an owner row |
| CANDIDATE | SATISFIED | nothing to charge |
| CANDIDATE | UNSATISFIED | CONTRACT_UNSATISFIED — DEVELOPER |
| CANDIDATE | INDETERMINATE(PRECONDITION_ABSENT) | PRECONDITION_ABSENT — PLAN |

Anything outside these rows — an untyped result, an unknown site, an INDETERMINATE reason with no row — **fails
closed** with `UnroutableOutcome`: it is never defaulted to an owner, and never to DEVELOPER.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aisef2.arch.enums import ContractSatisfaction, ProbeExecutionStatus
from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.errors import InvariantError
from aisef2.product.outcome import RESULT_TYPES, IndeterminateReason, ProbeResult, contract_satisfaction
from aisef2.product.spec import ProductProofSpec


class Site(Enum):
    PARENT = "PARENT"
    CANDIDATE = "CANDIDATE"


class UnroutableOutcome(InvariantError):
    """An outcome with no routing row. Fail closed: no owner is charged and nothing is retried."""


STORY_ADMISSION = "STORY_ADMISSION"


@dataclass(frozen=True, slots=True)
class Route:
    failure: Classification | None
    decided_by: str | None
    rule: str


_CANDIDATE: dict[tuple[ContractSatisfaction, IndeterminateReason | None], FailureCode | None] = {
    (ContractSatisfaction.SATISFIED, None): None,
    (ContractSatisfaction.UNSATISFIED, None): FailureCode.CONTRACT_UNSATISFIED,
    (ContractSatisfaction.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT): FailureCode.PRECONDITION_ABSENT,
}


def route(result: ProbeResult | None, spec: ProductProofSpec, site: Site) -> Route:
    if not isinstance(site, Site):
        raise UnroutableOutcome(f"unknown routing site {site!r}")
    if result is None:
        return Route(None, None, "§10: not attempted — chargeable to no one")
    if not isinstance(result, RESULT_TYPES):
        raise UnroutableOutcome(f"{type(result).__name__} is not a typed probe result")
    if result.status is ProbeExecutionStatus.UNRUNNABLE:
        return Route(classify(FailureCode.PROBE_UNRUNNABLE), None, "§10: could not look")
    if result.status is ProbeExecutionStatus.INVALID_SPEC:
        return Route(classify(FailureCode.PROBE_INVALID_SPEC), None, "§10: not evaluable by this probe")
    satisfaction = contract_satisfaction(result, spec)
    if site is Site.PARENT:
        return Route(None, STORY_ADMISSION, "§10: a plan disposition at the parent; §13 decides it")
    key = (satisfaction, result.reason)
    if key not in _CANDIDATE:
        raise UnroutableOutcome(f"no routing row for {satisfaction.value} with reason {result.reason!r}")
    code = _CANDIDATE[key]
    return Route(None if code is None else classify(code), None, "§10 at the candidate, on ContractSatisfaction")
