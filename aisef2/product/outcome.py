"""RFC §10, §10.1, §10.2 — two-axis probe outcomes and the derived `ContractSatisfaction` (F2).

* **Two axes.** `ProbeExecutionStatus` says whether the probe looked; `BehaviorVerdict` says what it saw. The verdict
  exists only inside `Executed`: an `Unrunnable` or `InvalidSpec` result has no verdict attribute at all.
* **INDETERMINATE carries a required typed reason.** The RFC names one, `PRECONDITION_ABSENT` (§10.2); a reason is
  a member of `IndeterminateReason`, never free text.
* **ContractSatisfaction is derived, never stored** (§10.1): `contract_satisfaction(result, spec)` recomputes it from
  the recorded result and the spec's `candidate_expectation`. It is undefined — `InvariantError` — for a probe that
  did not execute. Planning routes on it, never on the raw verdict, which is polarity-inverted for every
  MUST_NOT_HOLD contract.
* **Subject absence** (§10.2) is governed by the contract's declaration, carried in the spec, never by polarity —
  and a decided verdict never comes from the declaration alone: `on_subject_absent(spec, observed=...)` is the only
  result a probe may report when the subject does not exist, and for `ABSENCE_IS_DECIDABLE` its verdict is what the
  probe observed by evaluating the spec's observable over the absent subject.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Union

from aisef2.arch.enums import BehaviorVerdict, ContractSatisfaction, ProbeExecutionStatus, SubjectAbsence
from aisef2.errors import InvariantError
from aisef2.product.spec import ProductProofSpec


class IndeterminateReason(Enum):
    """Why an EXECUTED probe could not decide (§10: "a reason is REQUIRED"). Named by the RFC, §10.2."""
    PRECONDITION_ABSENT = "PRECONDITION_ABSENT"
    #: §9.3 (ARCHITECTURE-EXCEPTION-V2-003): the harness dispatched the subject and the process then ended by a signal
    #: the controller did not send. What is known is exactly that — not who sent it — so the name says no more.
    NON_CONTROLLER_SIGNAL = "NON_CONTROLLER_SIGNAL"


@dataclass(frozen=True, slots=True)
class Executed:
    """The probe looked. The only place a `BehaviorVerdict` can exist."""
    behavior_verdict: BehaviorVerdict
    reason: IndeterminateReason | None = None
    status: ClassVar[ProbeExecutionStatus] = ProbeExecutionStatus.EXECUTED

    def __post_init__(self) -> None:
        if not isinstance(self.behavior_verdict, BehaviorVerdict):
            raise InvariantError("an executed probe reports a BehaviorVerdict")
        if self.behavior_verdict is BehaviorVerdict.INDETERMINATE:
            if not isinstance(self.reason, IndeterminateReason):
                raise InvariantError("INDETERMINATE requires a typed IndeterminateReason")
        elif self.reason is not None:
            raise InvariantError("only INDETERMINATE carries a reason")


@dataclass(frozen=True, slots=True)
class Unrunnable:
    """The observation harness failed; the probe could not look (§9). `detail` is data, never control."""
    detail: str
    status: ClassVar[ProbeExecutionStatus] = ProbeExecutionStatus.UNRUNNABLE


@dataclass(frozen=True, slots=True)
class InvalidSpec:
    """The spec is not evaluable by this probe. `detail` is data, never control."""
    detail: str
    status: ClassVar[ProbeExecutionStatus] = ProbeExecutionStatus.INVALID_SPEC


ProbeResult = Union[Executed, Unrunnable, InvalidSpec]
RESULT_TYPES = (Executed, Unrunnable, InvalidSpec)


def contract_satisfaction(result: ProbeResult, spec: ProductProofSpec) -> ContractSatisfaction:
    """RFC §10.1, frozen under F2: SATISFIED iff the verdict equals the spec's candidate expectation."""
    if not isinstance(result, RESULT_TYPES) or result.status is not ProbeExecutionStatus.EXECUTED:
        raise InvariantError("contract satisfaction is undefined for a probe that did not execute")
    if result.behavior_verdict is BehaviorVerdict.INDETERMINATE:
        return ContractSatisfaction.INDETERMINATE
    return (ContractSatisfaction.SATISFIED
            if result.behavior_verdict == spec.candidate_expectation
            else ContractSatisfaction.UNSATISFIED)


def on_subject_absent(spec: ProductProofSpec, *, observed: BehaviorVerdict | None) -> Executed:
    """RFC §10.2: what a probe reports when the subject does not exist.

    REQUIRES_SUBJECT: the contract cannot be decided -> INDETERMINATE(PRECONDITION_ABSENT). A probe offering a verdict
    anyway would be reporting a vacuous one, so `observed` must be None.
    ABSENCE_IS_DECIDABLE: absence is a completed observation, and its verdict is `observed` — what the probe saw when it
    evaluated the spec's observable over the absent subject. The declaration never supplies it: there is no default.
    """
    if SubjectAbsence(spec.probe_input["subject_absence"]) is SubjectAbsence.REQUIRES_SUBJECT:
        if observed is not None:
            raise InvariantError("REQUIRES_SUBJECT: an absent subject has no verdict; reporting one is vacuous")
        return Executed(BehaviorVerdict.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT)
    if observed is None or observed is BehaviorVerdict.INDETERMINATE:
        raise InvariantError("ABSENCE_IS_DECIDABLE: the verdict is what the probe observed on the spec's observable; "
                             "there is no default")
    return Executed(observed)
