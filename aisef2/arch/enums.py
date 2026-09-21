"""Frozen vocabularies of the AISEF V2 architecture (F1–F11).

Transcribed from the approved RFC. This module is the code-side source of truth; it is **checked**, not trusted:

* WP-0.2 renders `docs/implementation/v2/arch-catalog.md` from it and `--check` fails in both directions;
* WP-0.3 extracts every frozen vocabulary from the RFC itself and requires exact agreement.

Adding, removing or renaming a member is a change to a frozen item (F1–F11) and requires an ARCHITECTURE_EXCEPTION.
"""

from enum import Enum


class Polarity(Enum):  # RFC §7 · F4
    MUST_HOLD = "MUST_HOLD"
    MUST_NOT_HOLD = "MUST_NOT_HOLD"


class SubjectAbsence(Enum):  # RFC §7 · F4
    REQUIRES_SUBJECT = "REQUIRES_SUBJECT"
    ABSENCE_IS_DECIDABLE = "ABSENCE_IS_DECIDABLE"


class SubjectKind(Enum):  # RFC §7, Subject.kind · F4
    PYTHON_CALLABLE = "python_callable"
    CLI_INVOCATION = "cli_invocation"
    HTTP_ROUTE = "http_route"
    FILE_ARTIFACT = "file_artifact"
    PROCESS_EFFECT = "process_effect"


class Enforcement(Enum):  # RFC §9 · F5
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ProbeExecutionStatus(Enum):  # RFC §10 · F2
    EXECUTED = "EXECUTED"
    UNRUNNABLE = "UNRUNNABLE"
    INVALID_SPEC = "INVALID_SPEC"


class BehaviorVerdict(Enum):  # RFC §10 · F2
    SATISFIED = "SATISFIED"
    REFUTED = "REFUTED"
    INDETERMINATE = "INDETERMINATE"


class ContractSatisfaction(Enum):  # RFC §10.1 · F2
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    INDETERMINATE = "INDETERMINATE"


class MeasurementPoint(Enum):  # RFC §10.3 · F2 (amended — ARCHITECTURE-EXCEPTION-V2-001)
    PARENT = "PARENT"
    CANDIDATE = "CANDIDATE"
    POST_MERGE = "POST_MERGE"


class ObligationRole(Enum):  # RFC §11 · F6
    INTRODUCE = "INTRODUCE"
    PRESERVE = "PRESERVE"
    VERIFY = "VERIFY"


class ParentExpectation(Enum):  # RFC §11 · F6
    UNSATISFIED_AT_PARENT = "UNSATISFIED_AT_PARENT"
    SATISFIED_AT_PARENT = "SATISFIED_AT_PARENT"
    UNCONSTRAINED = "UNCONSTRAINED"


class StoryAdmissionDisposition(Enum):  # RFC §13 · F7
    READY = "READY"
    PRE_SATISFIED = "PRE_SATISFIED"
    PRECONDITION_BROKEN = "PRECONDITION_BROKEN"
    PLAN_CONTRADICTION = "PLAN_CONTRADICTION"
    PROBE_UNRUNNABLE = "PROBE_UNRUNNABLE"
    PROBE_INVALID = "PROBE_INVALID"


class Vacuity(Enum):  # RFC §15 · F1 (payload enum)
    NON_VACUOUS = "NON_VACUOUS"
    VACUOUS = "VACUOUS"
    INDETERMINATE = "INDETERMINATE"


class Relevance(Enum):  # RFC §15 · F1 (payload enum)
    RELEVANT = "RELEVANT"
    IRRELEVANT = "IRRELEVANT"
    UNMEASURABLE = "UNMEASURABLE"


class AdequacyOutcome(Enum):  # RFC §15 · F1 (payload enum)
    ADEQUATE = "ADEQUATE"
    INADEQUATE = "INADEQUATE"
    INCOMPLETE = "INCOMPLETE"


class TestExecutionStatus(Enum):  # RFC §15.0 · F1 (payload enum)
    EXECUTED = "EXECUTED"
    UNRUNNABLE = "UNRUNNABLE"


class TestOutcome(Enum):  # RFC §15.0 · F1 (payload enum)
    PASSED = "PASSED"
    FAILED = "FAILED"


class TestSelection(Enum):  # RFC §15.0 · F1 (payload enum)
    STORY_TESTS_RAN = "STORY_TESTS_RAN"
    NO_STORY_TESTS_MATCHED = "NO_STORY_TESTS_MATCHED"
    STORY_TESTS_NOT_COLLECTABLE = "STORY_TESTS_NOT_COLLECTABLE"


class Owner(Enum):  # RFC §22 · F3 — capped; a new member requires a cited measured defect
    PLAN = "PLAN"
    DEVELOPER = "DEVELOPER"
    ENVIRONMENT = "ENVIRONMENT"
    PROVIDER = "PROVIDER"
    REVIEW = "REVIEW"
    SECURITY = "SECURITY"
    INTEGRATION = "INTEGRATION"


class IdentityGrade(Enum):  # RFC §23 · F9
    VERIFIED = "VERIFIED"
    ATTESTED = "ATTESTED"
    OPAQUE = "OPAQUE"


class EventType(Enum):  # RFC §20.1 · F1
    RUN_BEGIN = "run/begin"
    RUN_SPEC_RESOLVED = "run/spec-resolved"
    RUN_DISPOSE_BEGIN = "run/dispose-begin"
    RUN_INTERRUPTED = "run/interrupted"
    RUN_END = "run/end"
    PLAN_STATIC_ADMITTED = "plan/static-admitted"
    PLAN_FROZEN = "plan/frozen"
    STORY_BEGIN = "story/begin"
    STORY_ADMITTED = "story/admitted"
    STORY_PLAN_DRIFT = "story/plan-drift"
    STORY_RESOURCE_ACQUIRED = "story/resource-acquired"
    STORY_RESOURCE_RELEASED = "story/resource-released"
    STORY_COMMIT = "story/commit"
    STORY_ROLLBACK = "story/rollback"
    STORY_RETRY = "story/retry"
    STORY_DISPOSE = "story/dispose"
    STORY_END = "story/end"
    CAPABILITY_RESOLVED = "capability/resolved"
    PROBE_EVALUATED = "probe/evaluated"
    PROOF_VERIFIED = "proof/verified"
    PROVIDER_REQUEST = "provider/request"
    PROVIDER_RESULT = "provider/result"
    TOOL_INVOKED = "tool/invoked"
    TOOL_RESULT = "tool/result"
    TESTS_ADEQUACY = "tests/adequacy"
    GATE_CHECK = "gate/check"
    GATE_DECISION = "gate/decision"
    FAILURE_OBSERVED = "failure/observed"
    INVARIANT_VIOLATED = "invariant/violated"


class InvariantId(Enum):  # RFC §4 · F10 — value is the numeral; the title is in INVARIANT_TITLE
    I = "I"  # noqa: E741
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"
    VI = "VI"
    VII = "VII"
    VIII = "VIII"
    IX = "IX"


INVARIANT_TITLE = {
    InvariantId.I: "Requirement Authority",
    InvariantId.II: "Semantic Determinism",
    InvariantId.III: "Independent Evidence",
    InvariantId.IV: "Typed Ownership",
    InvariantId.V: "Reproducible Qualification",
    InvariantId.VI: "Immutable Provenance",
    InvariantId.VII: "No Prose As Control State",
    InvariantId.VIII: "Memory Is Context, Never Evidence",
    InvariantId.IX: "No Developer Artefact Is Executed At The Parent Revision",
}


class ControlProjection(Enum):  # RFC §21 · F11 — a CLOSED list; only these may be cited by a gate
    STORY_STATE = "story_state"
    FAILURE_OWNER = "failure_owner"
    BUDGETS = "budgets"
    RETRY_TARGET = "retry_target"
    TERMINAL_STATE = "terminal_state"
    QUALIFICATION_COUNTERS = "qualification_counters"


#: Every frozen vocabulary: name -> (enum, frozen item, RFC section). The catalog and the F-conformance checks
#: are driven from this table, so a vocabulary absent from it is absent from both — and WP-0.3 fails on that.
VOCABULARIES = {
    "Polarity": (Polarity, "F4", "§7"),
    "SubjectAbsence": (SubjectAbsence, "F4", "§7"),
    "SubjectKind": (SubjectKind, "F4", "§7"),
    "Enforcement": (Enforcement, "F5", "§9"),
    "ProbeExecutionStatus": (ProbeExecutionStatus, "F2", "§10"),
    "BehaviorVerdict": (BehaviorVerdict, "F2", "§10"),
    "ContractSatisfaction": (ContractSatisfaction, "F2", "§10.1"),
    "MeasurementPoint": (MeasurementPoint, "F2", "§10.3"),
    "ObligationRole": (ObligationRole, "F6", "§11"),
    "ParentExpectation": (ParentExpectation, "F6", "§11"),
    "StoryAdmissionDisposition": (StoryAdmissionDisposition, "F7", "§13"),
    "Vacuity": (Vacuity, "F1", "§15"),
    "Relevance": (Relevance, "F1", "§15"),
    "AdequacyOutcome": (AdequacyOutcome, "F1", "§15"),
    "TestExecutionStatus": (TestExecutionStatus, "F1", "§15.0"),
    "TestOutcome": (TestOutcome, "F1", "§15.0"),
    "TestSelection": (TestSelection, "F1", "§15.0"),
    "Owner": (Owner, "F3", "§22"),
    "IdentityGrade": (IdentityGrade, "F9", "§23"),
    "EventType": (EventType, "F1", "§20.1"),
    "InvariantId": (InvariantId, "F10", "§4"),
    "ControlProjection": (ControlProjection, "F11", "§21"),
}
