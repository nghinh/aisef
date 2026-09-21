# AISEF V2 — Cycle-1 evidence plan

What each phase must produce before the next may begin. Every artefact is written under
`closure-evidence/v2/`; **nothing under `closure-evidence/hardening/` or any other V1 path is written, moved or
rewritten** — `WP-0.4` enforces that mechanically.

Per-package detail is in [`cycle1-manifest.json`](cycle1-manifest.json); the frozen-item mapping is in the
[traceability matrix](AISEF-V2-CYCLE1-TRACEABILITY.md).

---

## 1. Evidence per phase

### P0 — the baseline is identifiable and protected

| artefact | asserts |
|---|---|
| `AISEF-V2-FREEZE-MANIFEST.json` | the RFC normative digest and freeze-table digest at HEAD equal the approval record; 11 items enumerated |
| `arch-catalog.md` + `--check` | every frozen enum and member, fail-closed in **both** directions |
| `F-CONFORMANCE.json` | 11/11 frozen items report a definite state; none can pass by absence |
| `V1-EVIDENCE-BASELINE.json` | sha256 of every V1 evidence file; any mutation is rejected |
| `Q0-CHECKER-CALIBRATION.json` | every Q0 checker has a committed fixture it demonstrably rejects |

**Gate to P1:** a one-byte edit inside the RFC normative body fails CI; a status-header edit does not.

### P1 — the semantics are correct, including polarity

| artefact | asserts |
|---|---|
| `P1-CONTRACT-SHAPES.json` | `contract_hash` binds `subject_absence`; unapproved contracts cannot compile; no control path reads prose fields |
| `P1-SPEC-COMPILER.json` | compile is deterministic across processes; `--check` byte-identical; a spec cannot hold a story or plan field |
| `P1-OUTCOME-POLARITY.json` | **NEG-1, NEG-2, NEG-3**; a verdict is unconstructible outside `EXECUTED`; satisfaction mutation fully killed |
| `P1-ROUTING-TABLE.json` | routing total over the legal state space; `REFUTED`↛`ENVIRONMENT`; `UNRUNNABLE`↛`DEVELOPER`; unmapped outcomes fail closed |

**Gate to P2:** a static check proves no planning module imports `BehaviorVerdict` for routing.

### P2 — probes and admission, with calibration that can say no

| artefact | asserts |
|---|---|
| `P2-PROBE-PROTOCOL.json` | missing subject ⇒ `EXECUTED`+`REFUTED`; missing harness ⇒ `UNRUNNABLE`; enforcement bound into every result; developer paths rejected |
| `P2-CALIBRATION.json` | **CAL-1** an always-`REFUTED` prohibition probe is rejected; contrast rule proven for both polarities |
| `P2-STATIC-ADMISSION.json` | 9/9 static checks; no probe executes in the engine; **CAL-2** asserted — no plan-freeze path needs spec falsifiability |
| `P2-STORY-ADMISSION.json` | disposition table total; abbreviated parent SHA refused; no `provider/request` before admission |
| `P2-PLAN-DRIFT.json` | scenario **A** (early upstream implementation) and **K** (fully pre-satisfied story); zero developer budget on any `PRE_SATISFIED` path |

**Gate to P3:** test-layout invariance — permuted developer-test layouts give byte-identical product verdicts.

### P3 — the record is the authority

| artefact | asserts |
|---|---|
| `P3-JOURNAL-WRITER.json` | `seq == index` at four layers; append-site validation; no update/delete verb exists |
| `P3-FORMAT-COMPAT.json` | unknown **required** event ⇒ refuse to reconstruct; unknown `ignorable` ⇒ skip |
| `P3-FOLD-ORACLE.json` | incremental state == `fold(prefix)` on every generated journal; no projection reads `time` |
| `P3-CONTROL-PROJECTIONS.json` | 6/6 implemented; a seventh cannot be cited by a gate; mutation fully killed |
| `P3-REFERENCE-MODELS.json` | 6/6 reference models, each calibrated; AST no-import constraint enforced |

**Gate to P4:** an injected projection defect is caught by its reference model.

### P4 — resources and runs are owned and provably released

| artefact | asserts |
|---|---|
| `P4-STORY-SCOPE.json` | acquisition during dispose rejected; disposal failure recorded, never swallowed; deterministic sibling order |
| `P4-RANGE-EMPTINESS.json` | D-024 reproducer red-before / green-after; OS-asserted emptiness on **Linux and Windows CI**; escaped children reported as residuals |
| `P4-RUN-LIFETIME.json` | **RUN-1** and **RUN-2**; writer-close failure leaves `OPEN`; `CLEAN` failure leaves `OPEN`; lease released last |
| `P4-RUNSPEC-IDENTITY.json` | scenario **H**; `OPAQUE` bars Q6; enforcement level changes break comparability |
| `P4-BUDGETS.json` | SS-64 and D-006 reproducers; no side retry counter exists anywhere |
| `P4-INTERRUPTION.json` | repairing the same journal twice is byte-identical; no interruption leaves a gap; abandonment recorded |

### P5 — engineering quality, with no absence charged to a developer

| artefact | asserts |
|---|---|
| `P5-TEST-EXECUTION.json` | **TEST-1**, **TEST-2**; four collection-cause cases; **no "did not run ⇒ developer" edge exists anywhere** |
| `P5-RELEVANCE.json` | capability absence ⇒ `UNMEASURABLE`, never `IRRELEVANT`; branch coverage not required universally |
| `P5-VACUITY.json` | three-valued result; no parent revision is ever checked out (invariant IX) |
| `P5-ADEQUACY.json` | `UNRUNNABLE` produces no `AdequacyOutcome`; `INCOMPLETE` never blocks; tdd-chronology cannot block under any policy |
| `P5-INVARIANTS.json` | I–IX armed in every tier; **an invariant violation demonstrated escaping a `try/except`** |

### P6 — one authoritative path

| artefact | asserts |
|---|---|
| `P6-MIGRATION-TABLE.json` | generated, `--check` green, zero silently-defaulted rows, `SubjectAbsence` never inferred |
| `P6-ORCHESTRATION.json` | end-to-end story through the real path; scenario **L**; confinement derived from scope, not omittable |
| `P6-OLD-PATH-REMOVAL.json` | six removal proofs; the audit fails closed on any authority it cannot enumerate |

The six removal proofs are the cycle's real acceptance test: no old gate authoritative · no developer test
determines `ProductProof` · no parent-side developer test execution · no latest-evidence selection · no side
retry counters · every control decision journal-backed.

### P7–P10 — qualification

| artefact | asserts |
|---|---|
| `Q0-Q3/SUMMARY.json` | four rungs green on the exact candidate; zero unaudited mutation survivors; every probe digest calibrated; a rung that cannot run reports `UNRUNNABLE`, never `FAILED` |
| `Q4/DIFFERENTIAL.json` | 100 000/100 000 matched; 0 unexplained, 0 invariant violations, 0 exceptions, 0 silent skips; one kernel digest |
| `Q5/REPRODUCTION.json` | only the model stream replayed; tools re-executed and diffed; final workspace state compared; `assertConsumed` |
| `P10/LEDGERLOCK-REGRESSION.json` | `delivery_verdict` and `plan_quality_verdict` recorded **separately**; `plan_quality_verdict = NOT_CLAIMED` absent preregistered thresholds; no generalization claim; no cohort sealed |

---

## 2. Adversarial cases → evidence

The nine RFC regression cases, mapped to where each is discharged. Every one is a conformance case in Q1
(`QP-7`) as well as in its owning package.

| case | owning package | evidence |
|---|---|---|
| NEG-1 prohibition violated at parent ⇒ `READY` | `WP-1.3` | `P1-OUTCOME-POLARITY.json` |
| NEG-2 prohibition absent, `ABSENCE_IS_DECIDABLE` | `WP-1.3` | `P1-OUTCOME-POLARITY.json` |
| NEG-3 `REQUIRES_SUBJECT`, subject absent | `WP-1.3` | `P1-OUTCOME-POLARITY.json` |
| CAL-1 always-`REFUTED` probe rejected | `WP-2.2` | `P2-CALIBRATION.json` |
| CAL-2 no plan needs a post-freeze artefact | `WP-2.3` | `P2-STATIC-ADMISSION.json` |
| TEST-1 runner missing ⇒ `ENVIRONMENT` | `WP-5.1` | `P5-TEST-EXECUTION.json` |
| TEST-2 assertions fail ⇒ `DEVELOPER` | `WP-5.1` | `P5-TEST-EXECUTION.json` |
| RUN-1 crash after `run/end`, before `CLEAN` | `WP-4.3` | `P4-RUN-LIFETIME.json` |
| RUN-2 second run blocked by the lease | `WP-4.3` | `P4-RUN-LIFETIME.json` |

Scenarios A, K, L and H from the earlier adversarial review are discharged by `WP-2.5` (A, K), `WP-6.2` (L) and
`WP-4.4` (H).

---

## 3. V1 defect reproducers carried forward

Cycle 1 re-proves, against the new implementation, defects V1 measured. Each is **red before, green after**:

| reproducer | package | why it matters |
|---|---|---|
| D-024 cleanup races a live writer | `WP-4.2` | the family the ordered stack and measured emptiness exist for |
| SS-64 cap falls through to another stage | `WP-4.5` | budgets as projections cannot disagree with the journal |
| D-006 credential rejection charged to quality | `WP-4.5` | retryability is a taxonomy property |
| SS-81(A) collection failure from a missing third-party dep | `WP-5.1` | must be `ENVIRONMENT`, not a developer failure |
| `PLAN-V2.1-DEFECT-001` test placement changes proof semantics | `WP-2.4` (layout invariance) + `WP-5.3` (invariant IX) | the defect that ended V1 delivery qualification |
| `AC-STORY-04-01-2` `PLAN_OVERLAP` | `WP-2.5` | now `PRE_SATISFIED` + `PLAN_DRIFT`, not a stop |

---

## 4. What this evidence does not claim

Stated explicitly, so the record does not imply coverage it lacks.

- **No generalization claim.** No sealed cohort is started. `QP-10` is regression only, and LedgerLock is
  permanently `DEVELOPMENT`.
- **No `plan_quality` qualification** unless thresholds are preregistered; otherwise the verdict is
  `NOT_CLAIMED`.
- **Non-Python targets** get weaker collection-cause classification, falling back to `INTEGRATION`.
- **Reference-model independence is partly procedural.** The no-import rule is mechanical; authorship
  independence is not.
- **The residuals in RFC §34 are unchanged by cycle 1** — a contract faithful to a wrong requirement, a
  projection and its model wrong identically, undetectable remote drift, journal-and-sentinel both failing, and
  orphans from a hard-killed harness.
