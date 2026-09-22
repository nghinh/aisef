# AISEF V2 — Cycle-1 traceability matrix

**Generated from [`cycle1-manifest.json`](cycle1-manifest.json) by `validation/v2/plan_validate.py`.**
Do not hand-edit: `--check` fails on drift.

Architecture baseline: RFC normative digest `1133dd2de2fd9f8e…`, freeze-table digest
`529f5986520e82b7…`, approval record `c23191bd71bc299d…` amended by `AISEF-V2-RFC-AMENDMENT-V2-001.json`, `AISEF-V2-RFC-AMENDMENT-V2-002.json`.

**33 implementation + 4 qualification = 37 packages. F1–F11 coverage: 11/11.**

---

## 1. Frozen item → packages → tests → evidence → V1 defect families

### F1 — 9 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-3.1` | 20, 20.1 | a seq gap on decode is rejected; the writer API exposes no update/delete (asserted by introspection) | `closure-evidence/v2/P3-JOURNAL-WRITER.json` |
| `WP-3.2` | 20, 35 | unknown required type -> refuse to reconstruct (never partial); unknown ignorable type -> skipped and reconstruction proceeds | `closure-evidence/v2/P3-FORMAT-COMPAT.json` |
| `WP-4.6` | 17.1, 20.2 | interrupt mid-tool -> OUTCOME_UNKNOWN, never a gap; interrupt before dispatch -> NOT_STARTED | `closure-evidence/v2/P4-INTERRUPTION.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |
| `QP-8` | 27 | 0 unexplained divergences, 0 invariant violations, 0 exceptions, 0 silent skips | `closure-evidence/v2/Q4/DIFFERENTIAL.json` |
| `QP-9` | 27 | a changed request that drives the same call count does not silently pass (bind by request hash); a tool-behaviour regression appears as a diff, not a satisfied recording | `closure-evidence/v2/Q5/REPRODUCTION.json` |

**V1 defect families:** `FAM-EVIDENCE-SEMANTICS`, `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-PROCESS`, `FAM-RECOVERY`, `FAM-RELEASE`, `FAM-SCHEDULER`

### F2 — 9 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.2` | 4, 10, 10.1, 11, 13, 15.0, 22, 23 | adding an enum member without regenerating fails --check; removing a member still listed in the catalog fails --check | `docs/implementation/v2/arch-catalog.md + CI --check` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-1.3` | 10, 10.1, 10.2 | NEG-1 MUST_NOT_HOLD violated at parent -> UNSATISFIED (never PRE_SATISFIED); NEG-2 MUST_NOT_HOLD absent + ABSENCE_IS_DECIDABLE -> SATISFIED | `closure-evidence/v2/P1-OUTCOME-POLARITY.json` |
| `WP-1.4` | 22, 10 | REFUTED can never route to ENVIRONMENT; UNRUNNABLE can never route to DEVELOPER | `closure-evidence/v2/P1-ROUTING-TABLE.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `WP-6.3` | 31, 32 | no old gate remains authoritative; no developer test determines ProductProof | `closure-evidence/v2/P6-OLD-PATH-REMOVAL.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |
| `QP-8` | 27 | 0 unexplained divergences, 0 invariant violations, 0 exceptions, 0 silent skips | `closure-evidence/v2/Q4/DIFFERENTIAL.json` |

**V1 defect families:** `FAM-BUDGET`, `FAM-EVIDENCE-SEMANTICS`, `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-OUTCOME`, `FAM-PROOF-PLACEMENT`, `FAM-PROSE`, `FAM-RETRY`, `FAM-SCHEDULER`, `FAM-TYPED-OUTCOMES`

### F3 — 10 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.2` | 4, 10, 10.1, 11, 13, 15.0, 22, 23 | adding an enum member without regenerating fails --check; removing a member still listed in the catalog fails --check | `docs/implementation/v2/arch-catalog.md + CI --check` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-1.4` | 22, 10 | REFUTED can never route to ENVIRONMENT; UNRUNNABLE can never route to DEVELOPER | `closure-evidence/v2/P1-ROUTING-TABLE.json` |
| `WP-4.5` | 22, 21 | SS-64 reproducer: a cap reached inside a retried stage cannot fall through to another stage; D-006 reproducer: credential rejection is not charged to the developer quality budget | `closure-evidence/v2/P4-BUDGETS.json` |
| `WP-5.1` | 15.0 | TEST-1 runner missing -> UNRUNNABLE / ENVIRONMENT, never DEVELOPER, never INADEQUATE, never INCOMPLETE; TEST-2 assertions fail -> EXECUTED/FAILED -> INADEQUATE / DEVELOPER | `closure-evidence/v2/P5-TEST-EXECUTION.json` |
| `WP-5.2` | 15.2 | capability absence yields UNMEASURABLE, never IRRELEVANT; a change with no instrumentable branch is not penalised | `closure-evidence/v2/P5-RELEVANCE.json` |
| `WP-5.3` | 15.1 | tests pass under neutralisation -> VACUOUS; collection/import/reconstruction/tool/environment failure -> INDETERMINATE, never NON_VACUOUS | `closure-evidence/v2/P5-VACUITY.json` |
| `WP-5.4` | 15, 15.3, 31 | UNRUNNABLE mandatory execution is not reported as INCOMPLETE; INCOMPLETE never blocks and never charges the developer | `closure-evidence/v2/P5-ADEQUACY.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-BUDGET`, `FAM-EVIDENCE-SEMANTICS`, `FAM-OUTCOME`, `FAM-PROSE`, `FAM-RETRY`, `FAM-TOOL`, `FAM-TYPED-OUTCOMES`

### F4 — 5 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-1.1` | 6, 7 | editing rationale alone changes contract_hash (bound) and is detected; an unapproved contract cannot be compiled | `closure-evidence/v2/P1-CONTRACT-SHAPES.json` |
| `WP-1.2` | 8, 35 | a contract edit that leaves the spec unchanged is impossible (hash binds it); attempting to set a story field on a spec is a type error | `closure-evidence/v2/P1-SPEC-COMPILER.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-EVIDENCE-SEMANTICS`, `FAM-IDENTITY`, `FAM-PROOF-PLACEMENT`, `FAM-PROSE`

### F5 — 6 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-0.5` | 27 (Q0), 9.1 | a checker that always passes is rejected by its calibration | `closure-evidence/v2/Q0-CHECKER-CALIBRATION.json` |
| `WP-2.1` | 9, 24 | PROBE-ABS-1 observation harness unavailable (interpreter or tool missing, sandbox cannot execute, cannot inspect) -> UNRUNNABLE / ENVIRONMENT, no BehaviorVerdict; PROBE-ABS-2 REQUIRES_SUBJECT, subject absent -> EXECUTED + INDETERMINATE(PRECONDITION_ABSENT); never UNRUNNABLE, never a blanket verdict | `closure-evidence/v2/P2-PROBE-PROTOCOL.json` |
| `WP-2.2` | 9.1, 9.1.1, 9.1.2, 27 (Q2) | CAL-1 a MUST_NOT_HOLD probe that always returns REFUTED is REJECTED; a probe that always returns SATISFIED is rejected for MUST_HOLD classes | `closure-evidence/v2/P2-CALIBRATION.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-BENCH`, `FAM-JUDGE`, `FAM-OUTCOME`, `FAM-QUALIFICATION`, `FAM-TOOL`

### F6 — 8 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.2` | 4, 10, 10.1, 11, 13, 15.0, 22, 23 | adding an enum member without regenerating fails --check; removing a member still listed in the catalog fails --check | `docs/implementation/v2/arch-catalog.md + CI --check` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-2.3` | 11, 12 | duplicate INTRODUCE ownership for one spec is rejected; a cyclic dependency DAG is rejected | `closure-evidence/v2/P2-STATIC-ADMISSION.json` |
| `WP-6.1` | 31 | a hand edit to the table fails --check; an unmapped V1 mode is reported, never silently defaulted | `docs/implementation/v2/v1-proofmode-migration.md + closure-evidence/v2/P6-MIGRATION-TABLE.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `WP-6.3` | 31, 32 | no old gate remains authoritative; no developer test determines ProductProof | `closure-evidence/v2/P6-OLD-PATH-REMOVAL.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-APPROVAL`, `FAM-BUDGET`, `FAM-EVIDENCE-SEMANTICS`, `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-PLAN-OWNERSHIP`, `FAM-PROOF-PLACEMENT`, `FAM-PROSE`, `FAM-SCHEDULER`

### F7 — 7 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.2` | 4, 10, 10.1, 11, 13, 15.0, 22, 23 | adding an enum member without regenerating fails --check; removing a member still listed in the catalog fails --check | `docs/implementation/v2/arch-catalog.md + CI --check` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-2.4` | 13 | an abbreviated parent SHA is refused; probe UNRUNNABLE -> PROBE_UNRUNNABLE / ENVIRONMENT | `closure-evidence/v2/P2-STORY-ADMISSION.json` |
| `WP-2.5` | 14, 29 | upstream story implements downstream behaviour early -> PRE_SATISFIED + PLAN_DRIFT (scenario A); fully pre-satisfied story -> STORY_ALREADY_SATISFIED, developer call skipped (scenario K) | `closure-evidence/v2/P2-PLAN-DRIFT.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-OUTCOME`, `FAM-PLAN-OWNERSHIP`, `FAM-PROSE`, `FAM-SCHEDULER`

### F8 — 8 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-4.1` | 17, 17.1, 18 | acquisition during dispose is rejected; a disposal failure is recorded and can fail DISPOSE | `closure-evidence/v2/P4-STORY-SCOPE.json` |
| `WP-4.2` | 17.1 | a grandchild holding a write prevents worktree deletion (D-024 reproducer); a setsid-escaped child is detected and reported as a residual | `closure-evidence/v2/P4-RANGE-EMPTINESS.json` |
| `WP-4.3` | 18, 18.1, 19 | RUN-1 crash after durable run/end but before CLEAN -> sentinel OPEN -> next run reports TORN; RUN-2 second run blocked while the first holds its lease, even with run/end present | `closure-evidence/v2/P4-RUN-LIFETIME.json` |
| `WP-4.6` | 17.1, 20.2 | interrupt mid-tool -> OUTCOME_UNKNOWN, never a gap; interrupt before dispatch -> NOT_STARTED | `closure-evidence/v2/P4-INTERRUPTION.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-OWNERSHIP`, `FAM-PROCESS`, `FAM-RECOVERY`, `FAM-SCHEDULER`

### F9 — 7 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-1.2` | 8, 35 | a contract edit that leaves the spec unchanged is impossible (hash binds it); attempting to set a story field on a spec is a type error | `closure-evidence/v2/P1-SPEC-COMPILER.json` |
| `WP-4.4` | 23, 24 | scenario H: provider implementation changes with an unchanged version string -> detected for VERIFIED, graded ATTESTED otherwise; an OPAQUE capability blocks Q6 eligibility | `closure-evidence/v2/P4-RUNSPEC-IDENTITY.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |
| `QP-9` | 27 | a changed request that drives the same call count does not silently pass (bind by request hash); a tool-behaviour regression appears as a diff, not a satisfied recording | `closure-evidence/v2/Q5/REPRODUCTION.json` |

**V1 defect families:** `FAM-EVIDENCE-SEMANTICS`, `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-SCHEDULER`, `FAM-TOOL`

### F10 — 4 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-5.5` | 4 | an invariant violation escapes a try/except boundary (the required demonstration); an invariant with no named mechanism fails registration | `closure-evidence/v2/P5-INVARIANTS.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |

**V1 defect families:** `FAM-JUDGE`, `FAM-OUTCOME`, `FAM-PROSE`

### F11 — 10 packages

| package | RFC §§ | key adversarial tests | evidence artifact |
|---|---|---|---|
| `WP-0.1` | status header, Normative freeze table | a one-byte edit inside the normative body fails the check; a status-header edit does NOT fail the check | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.3` | Normative freeze table | a renamed enum member fails its F check; an added Owner member fails F3 | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-3.3` | 21 | a stale cache is never treated as authority; a version-mismatched cache row is discarded, not migrated | `closure-evidence/v2/P3-FOLD-ORACLE.json` |
| `WP-3.4` | 21, 29 | a seventh projection cannot be cited by a gate; budgets derived from the journal cannot disagree with it (no side counter exists) | `closure-evidence/v2/P3-CONTROL-PROJECTIONS.json` |
| `WP-3.5` | 21, 27 (Q1) | the AST check fails if a reference model imports the projection; an uncalibrated reference model is rejected | `closure-evidence/v2/P3-REFERENCE-MODELS.json` |
| `WP-4.5` | 22, 21 | SS-64 reproducer: a cap reached inside a retried stage cannot fall through to another stage; D-006 reproducer: credential rejection is not charged to the developer quality budget | `closure-evidence/v2/P4-BUDGETS.json` |
| `WP-6.2` | 5, 26, 32 | scenario L: same spec INTRODUCE in one plan and PRESERVE in another gives identical product verdicts; a merge conflict is never charged to DEVELOPER | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `WP-6.3` | 31, 32 | no old gate remains authoritative; no developer test determines ProductProof | `closure-evidence/v2/P6-OLD-PATH-REMOVAL.json` |
| `QP-7` | 27 | a rung that cannot run reports UNRUNNABLE, never FAILED; test-layout invariance: permuted test layouts give identical product verdicts | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |
| `QP-8` | 27 | 0 unexplained divergences, 0 invariant violations, 0 exceptions, 0 silent skips | `closure-evidence/v2/Q4/DIFFERENTIAL.json` |

**V1 defect families:** `FAM-BUDGET`, `FAM-EVIDENCE-SEMANTICS`, `FAM-IDENTITY`, `FAM-JUDGE`, `FAM-QUALIFICATION`, `FAM-QUALIFICATION-MEASUREMENT`, `FAM-RECOVERY`, `FAM-RETRY`, `FAM-SCHEDULER`

---

## 2. Package → phase → dependencies → evidence

| package | phase | depends on | evidence |
|---|---|---|---|
| `WP-0.1` | P0 | — | `closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json` |
| `WP-0.2` | P0 | `WP-0.4` | `docs/implementation/v2/arch-catalog.md + CI --check` |
| `WP-0.3` | P0 | `WP-0.2` | `closure-evidence/v2/F-CONFORMANCE.json` |
| `WP-0.4` | P0 | `WP-0.1` | `closure-evidence/v2/V1-EVIDENCE-BASELINE.json` |
| `WP-0.5` | P0 | `WP-0.3` | `closure-evidence/v2/Q0-CHECKER-CALIBRATION.json` |
| `WP-1.1` | P1 | `WP-0.3` | `closure-evidence/v2/P1-CONTRACT-SHAPES.json` |
| `WP-1.2` | P1 | `WP-1.1` | `closure-evidence/v2/P1-SPEC-COMPILER.json` |
| `WP-1.3` | P1 | `WP-1.2` | `closure-evidence/v2/P1-OUTCOME-POLARITY.json` |
| `WP-1.4` | P1 | `WP-1.3` | `closure-evidence/v2/P1-ROUTING-TABLE.json` |
| `WP-2.1` | P2 | `WP-1.3` | `closure-evidence/v2/P2-PROBE-PROTOCOL.json` |
| `WP-2.2` | P2 | `WP-2.1` | `closure-evidence/v2/P2-CALIBRATION.json` |
| `WP-2.3` | P2 | `WP-2.2` | `closure-evidence/v2/P2-STATIC-ADMISSION.json` |
| `WP-2.4` | P2 | `WP-2.3` | `closure-evidence/v2/P2-STORY-ADMISSION.json` |
| `WP-2.5` | P2 | `WP-2.4` | `closure-evidence/v2/P2-PLAN-DRIFT.json` |
| `WP-3.1` | P3 | `WP-1.4` | `closure-evidence/v2/P3-JOURNAL-WRITER.json` |
| `WP-3.2` | P3 | `WP-3.1` | `closure-evidence/v2/P3-FORMAT-COMPAT.json` |
| `WP-3.3` | P3 | `WP-3.1` | `closure-evidence/v2/P3-FOLD-ORACLE.json` |
| `WP-3.4` | P3 | `WP-3.3` | `closure-evidence/v2/P3-CONTROL-PROJECTIONS.json` |
| `WP-3.5` | P3 | `WP-3.4` | `closure-evidence/v2/P3-REFERENCE-MODELS.json` |
| `WP-4.1` | P4 | `WP-3.4` | `closure-evidence/v2/P4-STORY-SCOPE.json` |
| `WP-4.2` | P4 | `WP-4.1` | `closure-evidence/v2/P4-RANGE-EMPTINESS.json` |
| `WP-4.3` | P4 | `WP-4.1` | `closure-evidence/v2/P4-RUN-LIFETIME.json` |
| `WP-4.4` | P4 | `WP-4.3` | `closure-evidence/v2/P4-RUNSPEC-IDENTITY.json` |
| `WP-4.5` | P4 | `WP-3.4`, `WP-4.3` | `closure-evidence/v2/P4-BUDGETS.json` |
| `WP-4.6` | P4 | `WP-4.3`, `WP-3.2` | `closure-evidence/v2/P4-INTERRUPTION.json` |
| `WP-5.1` | P5 | `WP-1.4` | `closure-evidence/v2/P5-TEST-EXECUTION.json` |
| `WP-5.2` | P5 | `WP-5.1` | `closure-evidence/v2/P5-RELEVANCE.json` |
| `WP-5.3` | P5 | `WP-5.1` | `closure-evidence/v2/P5-VACUITY.json` |
| `WP-5.4` | P5 | `WP-5.2`, `WP-5.3` | `closure-evidence/v2/P5-ADEQUACY.json` |
| `WP-5.5` | P5 | `WP-5.4`, `WP-3.4` | `closure-evidence/v2/P5-INVARIANTS.json` |
| `WP-6.1` | P6 | `WP-2.3` | `docs/implementation/v2/v1-proofmode-migration.md + closure-evidence/v2/P6-MIGRATION-TABLE.json` |
| `WP-6.2` | P6 | `WP-6.1`, `WP-4.6`, `WP-5.5`, `WP-2.5` | `closure-evidence/v2/P6-ORCHESTRATION.json` |
| `WP-6.3` | P6 | `WP-6.2` | `closure-evidence/v2/P6-OLD-PATH-REMOVAL.json` |
| `QP-7` | P7 | `WP-6.3` | `closure-evidence/v2/Q0-Q3/SUMMARY.json` |
| `QP-8` | P8 | `QP-7` | `closure-evidence/v2/Q4/DIFFERENTIAL.json` |
| `QP-9` | P9 | `QP-8` | `closure-evidence/v2/Q5/REPRODUCTION.json` |
| `QP-10` | P10 | `QP-9` | `closure-evidence/v2/P10/LEDGERLOCK-REGRESSION.json` |

---

## 3. V1 defect family → packages

| family | packages |
|---|---|
| `FAM-APPROVAL` | `WP-2.3` |
| `FAM-BENCH` | `WP-2.2` |
| `FAM-BUDGET` | `WP-1.4`, `WP-3.4`, `WP-4.5`, `WP-6.3` |
| `FAM-EVIDENCE-SEMANTICS` | `WP-1.2`, `WP-3.1`, `WP-5.2`, `WP-5.3`, `WP-5.4`, `WP-6.3` |
| `FAM-IDENTITY` | `WP-0.4`, `WP-1.2`, `WP-3.1`, `WP-4.3`, `WP-4.4`, `WP-6.2`, `WP-6.3` |
| `FAM-JUDGE` | `WP-2.2`, `WP-5.5`, `WP-6.2`, `WP-6.3` |
| `FAM-OUTCOME` | `WP-1.3`, `WP-1.4`, `WP-2.1`, `WP-2.4`, `WP-5.1`, `WP-5.4`, `WP-5.5` |
| `FAM-OWNERSHIP` | `WP-4.1` |
| `FAM-PLAN-OWNERSHIP` | `WP-2.3`, `WP-2.4`, `WP-2.5`, `WP-6.1` |
| `FAM-PROCESS` | `WP-4.1`, `WP-4.2`, `WP-4.6` |
| `FAM-PROOF-PLACEMENT` | `WP-1.1`, `WP-1.3`, `WP-6.1` |
| `FAM-PROSE` | `WP-0.2`, `WP-1.1`, `WP-5.5` |
| `FAM-QUALIFICATION` | `WP-0.5`, `WP-3.5` |
| `FAM-QUALIFICATION-MEASUREMENT` | `WP-3.3`, `WP-3.4`, `WP-3.5` |
| `FAM-RECOVERY` | `WP-3.3`, `WP-4.3`, `WP-4.6` |
| `FAM-RELEASE` | `WP-0.4`, `WP-3.1`, `WP-3.2` |
| `FAM-RETRY` | `WP-1.4`, `WP-3.4`, `WP-4.5` |
| `FAM-SCHEDULER` | `WP-2.3`, `WP-6.2` |
| `FAM-TOOL` | `WP-2.1`, `WP-4.4`, `WP-5.1` |
| `FAM-TYPED-OUTCOMES` | `WP-1.3`, `WP-5.1` |

20 of the 22 registered families are directly addressed by cycle-1 packages. The remainder
are measured rather than prevented (`FAM-PROVIDER`, `FAM-MODEL-CAPABILITY`), governed by the
evaluation-cohort lifecycle which is deferred (`FAM-BENCH`), or addressed by the ladder as a whole.
