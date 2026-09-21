# AISEF V2 — architecture catalog

**Generated from `aisef2/arch/enums.py` by `validation/v2/gen_arch_catalog.py`. Do not hand-edit:** `--check`
fails in both directions — a member in code but not here, and a member here but not in code. WP-0.3 separately
requires the code to agree with the frozen RFC.

| vocabulary | frozen item | RFC | members |
|---|---|---|---|
| `Polarity` | F4 | §7 | `MUST_HOLD`, `MUST_NOT_HOLD` |
| `SubjectAbsence` | F4 | §7 | `REQUIRES_SUBJECT`, `ABSENCE_IS_DECIDABLE` |
| `SubjectKind` | F4 | §7 | `python_callable`, `cli_invocation`, `http_route`, `file_artifact`, `process_effect` |
| `Enforcement` | F5 | §9 | `FULL`, `PARTIAL`, `UNAVAILABLE` |
| `ProbeExecutionStatus` | F2 | §10 | `EXECUTED`, `UNRUNNABLE`, `INVALID_SPEC` |
| `BehaviorVerdict` | F2 | §10 | `SATISFIED`, `REFUTED`, `INDETERMINATE` |
| `ContractSatisfaction` | F2 | §10.1 | `SATISFIED`, `UNSATISFIED`, `INDETERMINATE` |
| `ObligationRole` | F6 | §11 | `INTRODUCE`, `PRESERVE`, `VERIFY` |
| `ParentExpectation` | F6 | §11 | `UNSATISFIED_AT_PARENT`, `SATISFIED_AT_PARENT`, `UNCONSTRAINED` |
| `StoryAdmissionDisposition` | F7 | §13 | `READY`, `PRE_SATISFIED`, `PRECONDITION_BROKEN`, `PLAN_CONTRADICTION`, `PROBE_UNRUNNABLE`, `PROBE_INVALID` |
| `Vacuity` | F1 | §15 | `NON_VACUOUS`, `VACUOUS`, `INDETERMINATE` |
| `Relevance` | F1 | §15 | `RELEVANT`, `IRRELEVANT`, `UNMEASURABLE` |
| `AdequacyOutcome` | F1 | §15 | `ADEQUATE`, `INADEQUATE`, `INCOMPLETE` |
| `TestExecutionStatus` | F1 | §15.0 | `EXECUTED`, `UNRUNNABLE` |
| `TestOutcome` | F1 | §15.0 | `PASSED`, `FAILED` |
| `TestSelection` | F1 | §15.0 | `STORY_TESTS_RAN`, `NO_STORY_TESTS_MATCHED`, `STORY_TESTS_NOT_COLLECTABLE` |
| `Owner` | F3 | §22 | `PLAN`, `DEVELOPER`, `ENVIRONMENT`, `PROVIDER`, `REVIEW`, `SECURITY`, `INTEGRATION` |
| `IdentityGrade` | F9 | §23 | `VERIFIED`, `ATTESTED`, `OPAQUE` |
| `EventType` | F1 | §20.1 | `run/begin`, `run/spec-resolved`, `run/dispose-begin`, `run/interrupted`, `run/end`, `plan/static-admitted`, `plan/frozen`, `story/begin`, `story/admitted`, `story/plan-drift`, `story/resource-acquired`, `story/resource-released`, `story/commit`, `story/rollback`, `story/retry`, `story/dispose`, `story/end`, `capability/resolved`, `probe/evaluated`, `proof/verified`, `provider/request`, `provider/result`, `tool/invoked`, `tool/result`, `tests/adequacy`, `gate/check`, `gate/decision`, `failure/observed`, `invariant/violated` |
| `InvariantId` | F10 | §4 | `I`, `II`, `III`, `IV`, `V`, `VI`, `VII`, `VIII`, `IX` |
| `ControlProjection` | F11 | §21 | `story_state`, `failure_owner`, `budgets`, `retry_target`, `terminal_state`, `qualification_counters` |

21 vocabularies, 103 members.
