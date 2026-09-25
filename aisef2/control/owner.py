"""RFC §22 — the typed failure taxonomy. Every failure code has exactly one owner and one retryability, fixed here.

* The `Owner` set is frozen (F3, `aisef2.arch.enums`) and capped; this module uses it and never extends it.
* **Retryability is a property of the typed code**, decided once in `TAXONOMY`; no other kernel module assigns,
  passes or keys it (static check RETRYABLE_ONLY_IN_TAXONOMY). A retry charges its owner's own budget (invariant IV).
* **The retry count is never here.** How many retries a path allows comes from the resolved execution policy
  (RunSpec, project or evaluation configuration). `RESOLVED_BY_POLICY` marks a code whose retryability itself is
  that policy's decision.
* Credentials are execution configuration (owner decision, P1 review): `MISSING_CREDENTIAL` and
  `INVALID_CREDENTIAL` are both ENVIRONMENT, and an invalid credential is never retryable (§22, D-006). A provider
  owns a failure only through a provider-side code (`PROVIDER_UNAVAILABLE`).
* Probe-outcome codes follow §10.3 (ARCHITECTURE-EXCEPTION-V2-001): the owner depends on the measurement point.
* A value from outside the taxonomy never becomes a control code: `flatten` maps it to `UNKNOWN` and keeps the
  original as data. `UNKNOWN` is INTEGRATION and not retryable — never DEVELOPER (§15, TEST-2 companion).
* ARCHITECTURE-EXCEPTION-V2-005 (owner, 2026-09-25) added the nine codes the orchestration path needs and journal
  format 3 can carry: verifier disagreement and instrument mismatch (§16), merge conflict (§26), the two
  engineering-quality codes (§15.3), review and security findings and a capability that cannot run (§25), and a
  resource the controller could not acquire (§17.1). Journal formats 1 and 2 keep exactly the code set they were
  written with (`FORMAT_2_CODES`); only format 3 carries the nine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aisef2.arch.enums import Owner
from aisef2.errors import InvariantError


class Retryability(Enum):
    RETRYABLE = "RETRYABLE"
    NOT_RETRYABLE = "NOT_RETRYABLE"
    RESOLVED_BY_POLICY = "RESOLVED_BY_POLICY"


class FailureCode(Enum):
    PROBE_UNRUNNABLE = "PROBE_UNRUNNABLE"
    PROBE_INVALID_SPEC = "PROBE_INVALID_SPEC"
    CONTRACT_UNSATISFIED = "CONTRACT_UNSATISFIED"
    SUBJECT_ABSENT_AT_CANDIDATE = "SUBJECT_ABSENT_AT_CANDIDATE"
    PRECONDITION_BROKEN = "PRECONDITION_BROKEN"
    PLAN_CONTRADICTION = "PLAN_CONTRADICTION"
    POST_MERGE_REGRESSION = "POST_MERGE_REGRESSION"
    POST_MERGE_SUBJECT_LOST = "POST_MERGE_SUBJECT_LOST"
    NON_CONTROLLER_SIGNAL = "NON_CONTROLLER_SIGNAL"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    # ARCHITECTURE-EXCEPTION-V2-005 — journal format 3 only
    VERIFIER_DISAGREEMENT = "VERIFIER_DISAGREEMENT"
    PROBE_MISMATCH = "PROBE_MISMATCH"
    MERGE_CONFLICT = "MERGE_CONFLICT"
    TESTS_UNRUNNABLE = "TESTS_UNRUNNABLE"
    TESTS_INADEQUATE = "TESTS_INADEQUATE"
    REVIEW_FINDING = "REVIEW_FINDING"
    SECURITY_FINDING = "SECURITY_FINDING"
    CAPABILITY_UNRUNNABLE = "CAPABILITY_UNRUNNABLE"
    RESOURCE_ACQUISITION_FAILED = "RESOURCE_ACQUISITION_FAILED"


#: The codes journal formats 1 and 2 were written with — their validators admit exactly these (V2-005 §12, FMT3-5).
FORMAT_2_CODES: frozenset[str] = frozenset({
    "PROBE_UNRUNNABLE", "PROBE_INVALID_SPEC", "CONTRACT_UNSATISFIED", "SUBJECT_ABSENT_AT_CANDIDATE",
    "PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "POST_MERGE_REGRESSION", "POST_MERGE_SUBJECT_LOST",
    "NON_CONTROLLER_SIGNAL", "MISSING_CREDENTIAL", "INVALID_CREDENTIAL", "PROVIDER_UNAVAILABLE", "UNKNOWN"})
#: The nine codes ARCHITECTURE-EXCEPTION-V2-005 approved, exactly; a tenth is a STOP (owner resolution §7, §20).
V2_005_CODES: frozenset[str] = frozenset({
    "VERIFIER_DISAGREEMENT", "PROBE_MISMATCH", "MERGE_CONFLICT", "TESTS_UNRUNNABLE", "TESTS_INADEQUATE",
    "REVIEW_FINDING", "SECURITY_FINDING", "CAPABILITY_UNRUNNABLE", "RESOURCE_ACQUISITION_FAILED"})


@dataclass(frozen=True, slots=True)
class Classification:
    code: FailureCode
    owner: Owner
    retryability: Retryability
    rule: str

    @property
    def budget(self) -> Owner | None:
        """The budget a retry would charge — the owner's own — unless the code is never retryable."""
        return None if self.retryability is Retryability.NOT_RETRYABLE else self.owner


R, N, P = Retryability.RETRYABLE, Retryability.NOT_RETRYABLE, Retryability.RESOLVED_BY_POLICY
TAXONOMY: dict[FailureCode, Classification] = {c.code: c for c in (
    Classification(FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT, retryability=R,
                   rule="§10, §10.3: the observation harness cannot run -> ENVIRONMENT (the only probe outcome that "
                        "may route there)"),
    Classification(FailureCode.PROBE_INVALID_SPEC, Owner.INTEGRATION, retryability=N,
                   rule="§10: INVALID_SPEC -> PLAN / INTEGRATION. INTEGRATION: §12 checks 2, 6 and 9 establish "
                        "contract->spec integrity and probe availability before plan freeze, so a spec that reaches "
                        "a probe unevaluable is a harness integration fault; §14: PROBE_INVALID is a hard blocker"),
    Classification(FailureCode.CONTRACT_UNSATISFIED, Owner.DEVELOPER, retryability=R,
                   rule="§10.3: CANDIDATE, UNSATISFIED -> DEVELOPER; §10.1: failure is ContractSatisfaction "
                        "UNSATISFIED, never a raw verdict"),
    Classification(FailureCode.SUBJECT_ABSENT_AT_CANDIDATE, Owner.DEVELOPER, retryability=R,
                   rule="§10.3 (V2-001): CANDIDATE, admitted obligation, required subject absent -> DEVELOPER: the "
                        "admitted implementation did not establish the subject the proof requires"),
    Classification(FailureCode.PRECONDITION_BROKEN, Owner.PLAN, retryability=N,
                   rule="§10.3, §13: PARENT, PRESERVE or VERIFY over a required subject that is absent -> "
                        "PRECONDITION_BROKEN, PLAN; §14: a hard plan blocker"),
    Classification(FailureCode.PLAN_CONTRADICTION, Owner.PLAN, retryability=N,
                   rule="§13: the parent cannot be reconciled with the plan's own record (a PRESERVE measured "
                        "UNSATISFIED whose introducing story committed) -> PLAN; §14: a hard plan blocker; owner "
                        "decision (P2 review): never retryable, so it consumes no budget"),
    Classification(FailureCode.POST_MERGE_REGRESSION, Owner.INTEGRATION, retryability=N,
                   rule="§26, §10.3: POST_MERGE, UNSATISFIED -> a regression after merge, INTEGRATION"),
    Classification(FailureCode.POST_MERGE_SUBJECT_LOST, Owner.INTEGRATION, retryability=N,
                   rule="§10.3 (V2-001): POST_MERGE, a subject verified at the candidate is gone -> INTEGRATION"),
    Classification(FailureCode.NON_CONTROLLER_SIGNAL, Owner.INTEGRATION, retryability=N,
                   rule="§9.3, §10.3 (V2-003): the probe executed and the subject's process ended by a signal the "
                        "controller did not send. The evidence establishes only that the controller did not send it — "
                        "not whether the product, the operating system, a resource limit or another actor did — so "
                        "DEVELOPER would invent product causality and ENVIRONMENT would repeat the defect V2-003 "
                        "removes; INTEGRATION is the fail-closed owner of an executed proof whose causal reading "
                        "cannot be established, and it is never retryable: a retry would measure the same thing"),
    Classification(FailureCode.MISSING_CREDENTIAL, Owner.ENVIRONMENT, retryability=P,
                   rule="§22 + owner decision (P1 review): a missing credential is execution configuration -> "
                        "ENVIRONMENT; whether it is retried is the resolved execution policy's decision"),
    Classification(FailureCode.INVALID_CREDENTIAL, Owner.ENVIRONMENT, retryability=N,
                   rule="§22: MUST NOT be retryable (D-006); owner decision (P1 review): a rejected, revoked or wrong "
                        "credential is execution configuration, not provider failure -> ENVIRONMENT"),
    Classification(FailureCode.PROVIDER_UNAVAILABLE, Owner.PROVIDER, retryability=R,
                   rule="§22 + owner decision (P1 review): a provider owns a failure only through a provider-side "
                        "code — the provider is unavailable"),
    Classification(FailureCode.UNKNOWN, Owner.INTEGRATION, retryability=N,
                   rule="§22: a non-AISEF error flattens to UNKNOWN; §15: cause undetermined -> INTEGRATION, "
                        "never DEVELOPER"),
    # ---- ARCHITECTURE-EXCEPTION-V2-005 (owner resolution of the WP-6.2 schema stop, 2026-09-25, §7)
    Classification(FailureCode.VERIFIER_DISAGREEMENT, Owner.INTEGRATION, retryability=N,
                   rule="§16 rule 3 (V2-005): implementer and verifier disagree -> INDETERMINATE, INTEGRATION, stop; "
                        "never arbitrated, never rerun until agreement, never flattened to UNKNOWN"),
    Classification(FailureCode.PROBE_MISMATCH, Owner.INTEGRATION, retryability=N,
                   rule="§16 rule 2 (V2-005): the two results do not share probe_id, probe_digest and semantic_hash — a "
                        "harness integrity failure, not a statement about the product; never flattened to UNKNOWN"),
    Classification(FailureCode.MERGE_CONFLICT, Owner.INTEGRATION, retryability=N,
                   rule="§26 (V2-005): a merge conflict is INTEGRATION, never DEVELOPER; no developer budget; from the "
                        "typed merge outcome, never from stderr text"),
    Classification(FailureCode.TESTS_UNRUNNABLE, Owner.ENVIRONMENT, retryability=R,
                   rule="§15.3 (V2-005): a mandatory developer-test execution is UNRUNNABLE -> no AdequacyOutcome, an "
                        "environment failure with its own provenance; the environment retry policy applies"),
    Classification(FailureCode.TESTS_INADEQUATE, Owner.DEVELOPER, retryability=R,
                   rule="§15.3 (V2-005): INADEQUATE under a blocking project policy -> DEVELOPER, the developer quality "
                        "budget; INCOMPLETE is never a failure code (recorded in tests/adequacy only)"),
    Classification(FailureCode.REVIEW_FINDING, Owner.REVIEW, retryability=R,
                   rule="§25 (V2-005): a corroborated reviewer finding -> REVIEW; a model review alone is never the "
                        "sole blocking authority (D-002)"),
    Classification(FailureCode.SECURITY_FINDING, Owner.SECURITY, retryability=R,
                   rule="§25 (V2-005): a scanner that executed and produced a typed blocking finding -> SECURITY; the "
                        "code comes from the adapter's typed result, never from scanner text"),
    Classification(FailureCode.CAPABILITY_UNRUNNABLE, Owner.ENVIRONMENT, retryability=R,
                   rule="§25 (V2-005): a review or security capability that cannot run for a local or environment "
                        "reason -> ENVIRONMENT; a provider outage stays PROVIDER_UNAVAILABLE"),
    Classification(FailureCode.RESOURCE_ACQUISITION_FAILED, Owner.ENVIRONMENT, retryability=R,
                   rule="§17.1 (V2-005): a StoryScope or controller resource the harness could not acquire -> "
                        "ENVIRONMENT; never derived from stderr text"),
)}


def classify(code: FailureCode) -> Classification:
    """The one place a failure's owner and retryability are read from. Fails closed on anything untyped."""
    if not isinstance(code, FailureCode) or code not in TAXONOMY:
        raise InvariantError(f"{code!r} is not a typed failure code; flatten it to UNKNOWN first")
    return TAXONOMY[code]


def flatten(value: object) -> tuple[FailureCode, object]:
    """A typed code stays itself; anything else becomes UNKNOWN, with the original kept as data (§22)."""
    return (value, None) if isinstance(value, FailureCode) else (FailureCode.UNKNOWN, value)
