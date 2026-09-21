"""RFC §22 — the typed failure taxonomy. Every failure code has exactly one owner and one retryability, fixed here.

* The `Owner` set is frozen (F3, `aisef2.arch.enums`) and capped; this module uses it and never extends it.
* **Retryability is a property of the typed code**, decided once in `TAXONOMY`. No other kernel module assigns,
  passes or keys a `retryable` (static check RETRYABLE_ONLY_IN_TAXONOMY). The retry budget a retryable failure
  charges is its owner's; owners never consume each other's budgets (invariant IV).
* `MISSING_CREDENTIAL` and `INVALID_CREDENTIAL` are distinct because the fix differs; the latter is never
  retryable (§22, D-006).
* A value from outside the taxonomy never becomes a control code: `flatten` maps it to `UNKNOWN` and keeps the
  original as data. `UNKNOWN` is owned by INTEGRATION and not retryable — "cause cannot be determined => INTEGRATION,
  never DEVELOPER" (§15, TEST-2 companion).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aisef2.arch.enums import Owner
from aisef2.errors import InvariantError


class FailureCode(Enum):
    PROBE_UNRUNNABLE = "PROBE_UNRUNNABLE"
    PROBE_INVALID_SPEC = "PROBE_INVALID_SPEC"
    CONTRACT_UNSATISFIED = "CONTRACT_UNSATISFIED"
    PRECONDITION_ABSENT = "PRECONDITION_ABSENT"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Classification:
    code: FailureCode
    owner: Owner
    retryable: bool
    rule: str

    @property
    def budget(self) -> Owner | None:
        """The budget a retry charges: the owner's own, and only when the code is retryable."""
        return self.owner if self.retryable else None


TAXONOMY: dict[FailureCode, Classification] = {c.code: c for c in (
    Classification(FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT, retryable=True,
                   rule="§10: UNRUNNABLE -> ENVIRONMENT (the only row that may); environment retry policy (§15 TEST-1)"),
    Classification(FailureCode.PROBE_INVALID_SPEC, Owner.INTEGRATION, retryable=False,
                   rule="§10: INVALID_SPEC -> PLAN / INTEGRATION. INTEGRATION: §12 checks 2, 6 and 9 establish "
                        "contract->spec integrity and probe availability before plan freeze, so a spec that reaches "
                        "a probe unevaluable is a harness integration fault; §14: PROBE_INVALID is a hard blocker"),
    Classification(FailureCode.CONTRACT_UNSATISFIED, Owner.DEVELOPER, retryable=True,
                   rule="§10: failure at the candidate -> DEVELOPER; §10.1: failure means ContractSatisfaction "
                        "UNSATISFIED, never a raw verdict"),
    Classification(FailureCode.PRECONDITION_ABSENT, Owner.PLAN, retryable=False,
                   rule="§10: INDETERMINATE -> PLAN or INTEGRATION, by reason. PLAN: §13 routes PRECONDITION_ABSENT to "
                        "PRECONDITION_BROKEN, a hard plan blocker (§14); §10.2 forbids a vacuous verdict, so the "
                        "missing subject is a plan fact, never a developer failure"),
    Classification(FailureCode.MISSING_CREDENTIAL, Owner.ENVIRONMENT, retryable=True,
                   rule="§22: distinct from INVALID_CREDENTIAL because the fix differs — provide the credential in "
                        "the environment"),
    Classification(FailureCode.INVALID_CREDENTIAL, Owner.PROVIDER, retryable=False,
                   rule="§22: MUST NOT be retryable (D-006: credential rejection charged to quality attempts)"),
    Classification(FailureCode.UNKNOWN, Owner.INTEGRATION, retryable=False,
                   rule="§22: a non-AISEF error flattens to UNKNOWN; §15: cause undetermined -> INTEGRATION, "
                        "never DEVELOPER"),
)}


def classify(code: FailureCode) -> Classification:
    """The one place a failure's owner and retryability are read from. Fails closed on anything untyped."""
    if not isinstance(code, FailureCode) or code not in TAXONOMY:
        raise InvariantError(f"{code!r} is not a typed failure code; flatten it to UNKNOWN first")
    return TAXONOMY[code]


def flatten(value: object) -> tuple[FailureCode, object]:
    """A typed code stays itself; anything else becomes UNKNOWN, with the original kept as data (§22)."""
    return (value, None) if isinstance(value, FailureCode) else (FailureCode.UNKNOWN, value)
