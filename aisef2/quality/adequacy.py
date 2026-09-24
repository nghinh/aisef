"""RFC §15 / §15.3 — EngineeringTestAdequacy, assembled from typed facts (WP-5.4).

Developer tests are engineering-quality evidence. They never decide product correctness: nothing here imports a
product proof, a probe result or a verdict, and a story's COMMIT never depends on what is assembled here (§17).

The two-axis rule is load-bearing (the SS-96 boundary): first, did the mandatory executions actually execute; only
then may an `AdequacyOutcome` exist. "Could not execute" is never "executed and was inadequate".

Precedence, deterministic and total over the typed inputs (WP-5.1's `TestExecution` for the story's tests and for
the regressions, WP-5.3's `Vacuity`, WP-5.2's `Relevance`):

1. **Mandatory execution availability.** The story's execution UNRUNNABLE, or the regression execution UNRUNNABLE
   ⇒ `outcome = None`; the owner is the one the typed execution already carries (ENVIRONMENT); no developer quality
   charge, no developer retry charge, not INADEQUATE, not INCOMPLETE, not ADEQUATE.
2. **Developer-owned engineering defects (§15.3)** ⇒ INADEQUATE, owner DEVELOPER: the story's tests EXECUTED and
   FAILED; NO_STORY_TESTS_MATCHED; STORY_TESTS_NOT_COLLECTABLE whose typed owner is DEVELOPER; VACUOUS; IRRELEVANT;
   and, under the same typed rules for the regression execution (§15 `regressions`, §15.0 rule 5), regressions
   FAILED, a regression selection that matched nothing, a regression collection failure typed DEVELOPER. IRRELEVANT is a measurement *of the story tests that executed* (§15.2), so it is
   a defect only when the story's tests actually ran (STORY_TESTS_RAN); when they did not, the selection's own typed
   classification governs — a collection failure whose typed owner is INTEGRATION is never charged to the developer
   (§15.0 rule 4), and nothing is read from prose to decide it. VACUOUS needs no such guard: the shape refuses a
   vacuity value for tests that did not run (§15.1).
3. **Optional / secondary measurement gaps** ⇒ INCOMPLETE, no owner, never blocking, never charged: INDETERMINATE
   vacuity, UNMEASURABLE relevance, or a regression selection not collected for a cause typed INTEGRATION (reduced
   regression coverage; a DEVELOPER-typed one is a defect above), and nothing else.
4. **Otherwise ADEQUATE**, constructed positively: the story's tests passed, NON_VACUOUS, RELEVANT, the regressions
   ran and passed. The shape checks that construction on every ADEQUATE it accepts.

A hard defect dominates a secondary gap: FAILED tests with UNMEASURABLE relevance are INADEQUATE, failed regressions
with INDETERMINATE vacuity are INADEQUATE. `process/tdd-chronology` (V1's RED→GREEN check) is recorded when supplied
and read for nothing. Blocking is project policy, not semantics: INADEQUATE *may* block; INCOMPLETE never does.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from aisef2.arch.enums import AdequacyOutcome, Owner, Relevance, TestExecutionStatus, TestOutcome, TestSelection, Vacuity
from aisef2.errors import InvariantError
from aisef2.quality.test_execution import TestExecution

__all__ = ["EngineeringTestAdequacy", "Assembly", "assemble", "may_block"]

_UNRUNNABLE = TestExecutionStatus.UNRUNNABLE
_RAN, _NONE_MATCHED, _NOT_COLLECTABLE = (TestSelection.STORY_TESTS_RAN, TestSelection.NO_STORY_TESTS_MATCHED,
                                          TestSelection.STORY_TESTS_NOT_COLLECTABLE)


def _defects(execution: TestExecution, vacuity: Vacuity, relevance: Relevance, regressions: TestExecution) -> list[str]:
    """§15.3's INADEQUATE triggers present in the typed facts (empty: none). The regression execution is read under the
    same typed rules as the story's own (§15 `regressions`, §15.0 rule 5; owner ruling on the WP-5.4 regression
    dimension): FAILED, a selector that matched nothing, a collection failure typed DEVELOPER."""
    out = []
    if execution.outcome is TestOutcome.FAILED:
        out.append("the story's tests executed and failed")
    if execution.selection is _NONE_MATCHED:
        out.append("no story test matched the story's declared tests")
    if execution.selection is _NOT_COLLECTABLE and execution.owner_on_failure is Owner.DEVELOPER:
        out.append("the story's tests could not be collected for a cause typed as the developer's")
    if vacuity is Vacuity.VACUOUS:
        out.append("the story's tests are VACUOUS: they pass without the story's product change")
    if relevance is Relevance.IRRELEVANT and execution.selection is _RAN:
        out.append("the story's tests are IRRELEVANT: none touches the story's change")
    if regressions.outcome is TestOutcome.FAILED:
        out.append("regressions executed and failed")
    if regressions.selection is _NONE_MATCHED:
        out.append("no regression test matched the regression selection")
    if regressions.selection is _NOT_COLLECTABLE and regressions.owner_on_failure is Owner.DEVELOPER:
        out.append("the regressions could not be collected for a cause typed as the developer's")
    return out


def _gaps(vacuity: Vacuity, relevance: Relevance, regressions: TestExecution) -> list[str]:
    """§15.3's INCOMPLETE triggers present (empty: none): the optional / secondary measurements, and a regression
    selection that could not be collected for a cause that is not the developer's (reduced regression coverage,
    charged to nobody). Read only after `_defects`, so the developer-typed collection failure never lands here."""
    out = []
    if vacuity is Vacuity.INDETERMINATE:
        out.append("vacuity is INDETERMINATE")
    if relevance is Relevance.UNMEASURABLE:
        out.append("relevance is UNMEASURABLE")
    if regressions.selection is _NOT_COLLECTABLE:
        out.append(f"the regressions could not be collected, owner {regressions.owner_on_failure.value}: {regressions.reason}")
    return out


def _adequate(execution: TestExecution, vacuity: Vacuity, relevance: Relevance, regressions: TestExecution) -> bool:
    """ADEQUATE constructed positively: the story's tests passed, NON_VACUOUS (which the shape ties to the tests having
    run), RELEVANT, the regressions ran and passed."""
    return (execution.outcome is TestOutcome.PASSED and vacuity is Vacuity.NON_VACUOUS
            and relevance is Relevance.RELEVANT and regressions.outcome is TestOutcome.PASSED
            and regressions.selection is _RAN)


@dataclass(frozen=True)
class EngineeringTestAdequacy:
    """RFC §15, field for field. The shape itself refuses an outcome where the RFC defines none, and an outcome the
    typed facts do not assemble to."""
    execution: TestExecution                    # §15.0 — the execution axis
    vacuity: Vacuity | None                     # defined only when execution is EXECUTED
    relevance: Relevance | None                 # defined only when execution is EXECUTED
    regressions: TestExecution                  # same typed rules as the story's own tests
    sensitivity: None                           # deferred from cycle 1 (§33): nothing may claim it
    outcome: AdequacyOutcome | None             # defined ONLY when the mandatory executions are EXECUTED

    def __post_init__(self) -> None:
        if not isinstance(self.execution, TestExecution) or not isinstance(self.regressions, TestExecution):
            raise InvariantError("an adequacy is assembled from typed executions (§15.0)")
        if self.sensitivity is not None:
            raise InvariantError("sensitivity evidence is deferred from cycle 1 (§33): nothing may claim it")
        if self.execution.status is _UNRUNNABLE:
            if self.vacuity is not None or self.relevance is not None or self.outcome is not None:
                raise InvariantError("UNRUNNABLE story execution: no vacuity, no relevance, no AdequacyOutcome — an "
                                     "environment outcome, never a quality result (§15.0 rule 1, §15.3)")
            return
        if not isinstance(self.vacuity, Vacuity) or not isinstance(self.relevance, Relevance):
            raise InvariantError("an EXECUTED story execution carries a typed Vacuity and a typed Relevance (§15)")
        if self.vacuity is not Vacuity.INDETERMINATE and self.execution.selection is not _RAN:
            raise InvariantError("NON_VACUOUS and VACUOUS are said of story tests that actually ran (§15.1 conditions "
                                 "2–3; WP-5.3's baseline): tests that did not run have INDETERMINATE vacuity")
        if self.regressions.status is _UNRUNNABLE:
            if self.outcome is not None:
                raise InvariantError("UNRUNNABLE regression execution: no AdequacyOutcome — an environment outcome "
                                     "under the same typed rules (§15.0 rule 5, §15.3)")
            return
        defects = _defects(self.execution, self.vacuity, self.relevance, self.regressions)
        if self.outcome is AdequacyOutcome.INADEQUATE:
            if not defects:
                raise InvariantError("INADEQUATE names a developer-owned defect of §15.3; the typed facts carry none")
        elif self.outcome is AdequacyOutcome.INCOMPLETE:
            if defects:
                raise InvariantError("a developer-owned defect is INADEQUATE; a secondary gap never hides it (§15.3)")
            if not _gaps(self.vacuity, self.relevance, self.regressions):
                raise InvariantError("INCOMPLETE is exactly an INDETERMINATE vacuity, an UNMEASURABLE relevance, or a regression "
                                     "selection not collected for a cause that is not the developer's (§15.3)")
        elif self.outcome is AdequacyOutcome.ADEQUATE:
            if not _adequate(self.execution, self.vacuity, self.relevance, self.regressions):
                raise InvariantError("ADEQUATE is constructed positively: the story's tests passed, NON_VACUOUS, "
                                     "RELEVANT, the regressions ran and passed (§15.3)")
        else:
            raise InvariantError("both mandatory executions EXECUTED: the AdequacyOutcome is defined (§15.3)")


def may_block(outcome: AdequacyOutcome | None) -> bool:
    """§15.3: INADEQUATE MAY block under project policy — no policy object exists in aisef2, so nothing here decides
    blocking; INCOMPLETE MUST NOT block; ADEQUATE and no outcome do not block."""
    return outcome is AdequacyOutcome.INADEQUATE


@dataclass(frozen=True)
class Assembly:
    """The assembled adequacy, the chronology recorded as evidence, and the reason nothing reads. Owner, blocking
    permission and chargeability are read from the typed facts, never from `reason`."""
    adequacy: EngineeringTestAdequacy
    chronology: Mapping | None           # process/tdd-chronology, recorded verbatim when supplied; never consulted
    reason: str

    def __post_init__(self) -> None:
        if self.chronology is not None:
            object.__setattr__(self, "chronology", MappingProxyType(dict(self.chronology)))

    @property
    def outcome(self) -> AdequacyOutcome | None:
        return self.adequacy.outcome

    @property
    def owner(self) -> Owner | None:
        """The owner the typed facts carry: the UNRUNNABLE execution's own (ENVIRONMENT) when there is no outcome,
        DEVELOPER for INADEQUATE, nobody otherwise."""
        if self.adequacy.execution.status is _UNRUNNABLE:
            return self.adequacy.execution.owner_on_failure
        if self.adequacy.regressions.status is _UNRUNNABLE:
            return self.adequacy.regressions.owner_on_failure
        return Owner.DEVELOPER if self.adequacy.outcome is AdequacyOutcome.INADEQUATE else None

    @property
    def may_block(self) -> bool:
        return may_block(self.adequacy.outcome)

    @property
    def developer_chargeable(self) -> bool:
        """Eligible for the developer quality budget under existing policy (§15.3): exactly INADEQUATE."""
        return self.owner is Owner.DEVELOPER


def assemble(execution: TestExecution, vacuity: Vacuity | None, relevance: Relevance | None, regressions: TestExecution,
             *, chronology: Mapping | None = None) -> Assembly:
    """The only assembly, in the precedence the module docstring states."""
    if execution.status is _UNRUNNABLE:
        adequacy = EngineeringTestAdequacy(execution, vacuity, relevance, regressions, None, None)
        return Assembly(adequacy, chronology, "the story's tests could not execute: an environment outcome, no "
                                              "AdequacyOutcome — " + execution.reason)
    if regressions.status is _UNRUNNABLE:
        adequacy = EngineeringTestAdequacy(execution, vacuity, relevance, regressions, None, None)
        return Assembly(adequacy, chronology, "the regressions could not execute: an environment outcome, no "
                                              "AdequacyOutcome — " + regressions.reason)
    defects = _defects(execution, vacuity, relevance, regressions)
    if defects:
        adequacy = EngineeringTestAdequacy(execution, vacuity, relevance, regressions, None, AdequacyOutcome.INADEQUATE)
        return Assembly(adequacy, chronology, "INADEQUATE: " + "; ".join(defects))
    gaps = _gaps(vacuity, relevance, regressions)
    if gaps:
        adequacy = EngineeringTestAdequacy(execution, vacuity, relevance, regressions, None, AdequacyOutcome.INCOMPLETE)
        note = ("" if execution.selection is _RAN else
                f"; the story's tests were not collected, owner {execution.owner_on_failure.value}: {execution.reason}")
        return Assembly(adequacy, chronology, "INCOMPLETE (reduced engineering-quality coverage, never blocking, "
                                              "charged to nobody): " + "; ".join(gaps) + note)
    adequacy = EngineeringTestAdequacy(execution, vacuity, relevance, regressions, None, AdequacyOutcome.ADEQUATE)
    return Assembly(adequacy, chronology, "ADEQUATE: the story's tests ran and passed, NON_VACUOUS, RELEVANT, the "
                                          "regressions ran and passed")
