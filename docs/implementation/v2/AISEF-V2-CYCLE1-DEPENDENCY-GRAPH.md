# AISEF V2 — Cycle-1 dependency graph

**Generated from [`cycle1-manifest.json`](cycle1-manifest.json) by `validation/v2/plan_validate.py`.**
Do not hand-edit: `--check` fails on drift.

Scheduling model: a package is runnable when every declared dependency is complete **and** its phase's
barrier phase is evidence-complete. Parallelism is permitted **within a phase only**.

---

## 1. Phase barriers

| phase | packages | barrier | exit condition |
|---|---|---|---|
| **P0** Freeze / conformance scaffolding | 5 | — | architecture baseline mechanically identifiable and protected |
| **P1** Semantic core | 4 | P0 | polarity, NEG-1/2/3, compiler --check, hash stability, satisfaction mutation |
| **P2** Probe + admission | 5 | P1 | CAL-1, CAL-2, subject/harness separation, no provider call before admission, PRE_SATISFIED, layout invariance |
| **P3** Journal / projections | 5 | P2 | unknown-required refusal, time never folded, incremental == full, reference models, projection mutation |
| **P4** Story / run transaction | 6 | P3 | RUN-1, RUN-2, crash cases, range emptiness, budgets as projections |
| **P5** Engineering quality / invariants | 5 | P4 | TEST-1, TEST-2, collection-cause classification, vacuity three-valued, I-IX armed and uncontainable |
| **P6** Orchestration integration / V1 migration | 3 | P5 | single authoritative path, generated migration table, six removal proofs |
| **P7** Q0-Q3 | 1 | P6 | all four rungs green on the exact candidate |
| **P8** Q4 differential | 1 | P7 | 100000/100000, 0 unexplained |
| **P9** Q5 reproduction | 1 | P8 | reproduction green, tools re-executed |
| **P10** LedgerLock regression | 1 | P9 | verdicts separate, no generalization claim, no cohort sealed |

A phase is complete only when all of its packages are complete, all required evidence artefacts exist,
and all of its exit checks are green.

## 2. Phase exit checks

**P0** — freeze manifest digests equal the approval record; V1 evidence guard rejects every V1 mutation; enum catalog --check green in both directions; F1-F11 conformance reports 11 definite states; every Q0 checker calibrated against a known-bad fixture

**P1** — NEG-1, NEG-2, NEG-3 green; no planning module imports BehaviorVerdict for routing; compiler --check round-trip byte-identical; semantic_hash stable across processes; satisfaction-mapping mutants fully killed; routing table total; no did-not-run -> developer edge

**P2** — CAL-1 and CAL-2 green; missing subject vs missing harness separated; probe UNRUNNABLE -> ENVIRONMENT; INVALID_SPEC -> PLAN/INTEGRATION; no provider/request before story admission; scenarios A and K green; test-layout invariance: product verdicts identical across layouts

**P3** — unknown required event refuses reconstruction; ignorable skipped; no projection reads time; incremental == full fold on every generated journal; 6/6 reference models agree and are calibrated; every control-critical projection mutation-tested; stale cache never treated as authority

**P4** — RUN-1 and RUN-2 green; acquisition during dispose rejected; D-024 reproducer red-before/green-after; writer-close failure and CLEAN failure each leave the sentinel OPEN; SS-64 and D-006 reproducers green; range emptiness OS-asserted on Linux and Windows CI

**P5** — TEST-1 and TEST-2 green; four collection-cause cases green; vacuity NON_VACUOUS / VACUOUS / INDETERMINATE; no developer artefact executed at the parent; an invariant violation demonstrated escaping try/except

**P6** — migration table --check green with zero defaulted rows; no old gate remains authoritative; no developer test determines ProductProof; no parent-side developer test execution; no latest-evidence selection; no side retry counters; every control decision journal-backed

**P7** — Q0, Q1, Q2, Q3 green on the exact candidate; zero unaudited mutation survivors; every probe digest calibrated

**P8** — 100000/100000 matched; 0 unexplained, 0 invariant violations, 0 exceptions, 0 silent skips; one kernel digest

**P9** — reproduction green; no recorded tool result replayed; assertConsumed green

**P10** — delivery_verdict and plan_quality_verdict recorded separately; no generalization claim recorded; no cohort sealed

## 3. Package graph

| package | phase | level | declared dependencies |
|---|---|---|---|
| `WP-0.1` | P0 | 1 | — |
| `WP-0.4` | P0 | 2 | `WP-0.1` |
| `WP-0.2` | P0 | 3 | `WP-0.4` |
| `WP-0.3` | P0 | 4 | `WP-0.2` |
| `WP-0.5` | P0 | 5 | `WP-0.3` |
| `WP-1.1` | P1 | 6 | `WP-0.3` |
| `WP-1.2` | P1 | 7 | `WP-1.1` |
| `WP-1.3` | P1 | 8 | `WP-1.2` |
| `WP-1.4` | P1 | 9 | `WP-1.3` |
| `WP-2.1` | P2 | 10 | `WP-1.3` |
| `WP-2.2` | P2 | 11 | `WP-2.1` |
| `WP-2.3` | P2 | 12 | `WP-2.2` |
| `WP-2.4` | P2 | 13 | `WP-2.3` |
| `WP-2.5` | P2 | 14 | `WP-2.4` |
| `WP-3.1` | P3 | 15 | `WP-1.4` |
| `WP-3.2` | P3 | 16 | `WP-3.1` |
| `WP-3.3` | P3 | 16 | `WP-3.1` |
| `WP-3.4` | P3 | 17 | `WP-3.3` |
| `WP-3.5` | P3 | 18 | `WP-3.4` |
| `WP-4.1` | P4 | 19 | `WP-3.4` |
| `WP-4.2` | P4 | 20 | `WP-4.1` |
| `WP-4.3` | P4 | 20 | `WP-4.1` |
| `WP-4.4` | P4 | 21 | `WP-4.3` |
| `WP-4.5` | P4 | 21 | `WP-3.4`, `WP-4.3` |
| `WP-4.6` | P4 | 21 | `WP-4.3`, `WP-3.2` |
| `WP-5.1` | P5 | 22 | `WP-1.4` |
| `WP-5.2` | P5 | 23 | `WP-5.1` |
| `WP-5.3` | P5 | 23 | `WP-5.1` |
| `WP-5.4` | P5 | 24 | `WP-5.2`, `WP-5.3` |
| `WP-5.5` | P5 | 25 | `WP-5.4`, `WP-3.4` |
| `WP-6.1` | P6 | 26 | `WP-2.3` |
| `WP-6.2` | P6 | 27 | `WP-6.1`, `WP-4.6`, `WP-5.5`, `WP-2.5` |
| `WP-6.3` | P6 | 28 | `WP-6.2` |
| `QP-7` | P7 | 29 | `WP-6.3` |
| `QP-8` | P8 | 30 | `QP-7` |
| `QP-9` | P9 | 31 | `QP-8` |
| `QP-10` | P10 | 32 | `QP-9` |

*Level* is the earliest completion step under barriers, unit cost per package.

## 3a. Additional scheduling constraints

| constraint | why | enforced by |
|---|---|---|
| WP-0.4 completes before any package other than WP-0.1 executes | the V1 evidence guard must exist before there is anything to guard against | check C guard_ancestry (explicit transitive ancestry) |
| WP-0.5 completes before any Q0 checker is trusted | an uncalibrated checker is invisible false assurance | WP-0.5 is the last package of P0, so the P0 barrier gates every later package |
| WP-3.5 is authored after, and independently of, WP-3.4, from the RFC text only | a reference model written from the projection source is not independent evidence | declared dependency (ordering) + AST no-import check (mechanical); authorship independence is procedural |
| WP-2.1 prototypes a second probe kind before the rest of P2 builds on it | if a second kind does not fit the F5-frozen protocol that is a STOP, and should be found early | WP-2.1 exit criterion; every later P2 package depends on WP-2.1 |
| WP-4.2 exercises the Windows path in CI from its first commit | Windows is a real constraint, established in V1 | WP-4.2 exit criterion requires OS-asserted emptiness on Linux and Windows CI |
| WP-2.4 asserts no provider/request precedes story admission against an in-memory JournalWriter double; WP-6.3 re-verifies against the durable journal | the journal lands in P3, after P2; a test double adds no semantics and never exists in a production path | WP-6.3 removal proof 'every control decision journal-backed' |

## 4. Critical path

**Length 32 packages.**

`WP-0.1` → `WP-0.4` → `WP-0.2` → `WP-0.3` → `WP-0.5` → `WP-1.1` → `WP-1.2` → `WP-1.3` → `WP-1.4` → `WP-2.1` → `WP-2.2` → `WP-2.3` → `WP-2.4` → `WP-2.5` → `WP-3.1` → `WP-3.3` → `WP-3.4` → `WP-3.5` → `WP-4.1` → `WP-4.3` → `WP-4.6` → `WP-5.1` → `WP-5.3` → `WP-5.4` → `WP-5.5` → `WP-6.1` → `WP-6.2` → `WP-6.3` → `QP-7` → `QP-8` → `QP-9` → `QP-10`

Barriers make the path longer than a purely semantic graph would. That is deliberate:
correctness and evidence ordering have priority over elapsed time.

## 5. Parallel sets

| phase | level | packages that may run in parallel |
|---|---|---|
| P3 | 16 | `WP-3.2`, `WP-3.3` |
| P4 | 20 | `WP-4.2`, `WP-4.3` |
| P4 | 21 | `WP-4.4`, `WP-4.5`, `WP-4.6` |
| P5 | 23 | `WP-5.2`, `WP-5.3` |

Parallel execution additionally requires disjoint write scopes and disjoint evidence scopes, and is
never permitted across a phase barrier. `WP-3.5` carries an extra authorship-independence constraint.

## 6. Validation results

| check | result |
|---|---|
| A dependency_direction | **PASS** |
| B phase_barrier_completeness | **PASS** |
| C guard_ancestry | **PASS** |
| D orchestration_semantics | **PASS** |
| E qualification_chain | **PASS** |
| F1–F11 coverage | **11/11** |
| total problems | **0** |
