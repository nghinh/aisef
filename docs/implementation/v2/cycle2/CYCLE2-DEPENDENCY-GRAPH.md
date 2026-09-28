# CYCLE-2 DEPENDENCY GRAPH

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). Hand-written from
[`cycle2-manifest.json`](cycle2-manifest.json); the Cycle-1 generator (`validation/v2/plan_validate.py --generate`)
encodes Cycle-1-specific checks and is not run on this proposal. Generalising it is the first task of WP-2.0.1 so that,
once authorized, this document is regenerated and `--check` fails on drift as it did in Cycle 1.

Scheduling model (unchanged from Cycle 1): a package is runnable when every declared dependency is complete **and**
its phase's barrier phase is evidence-complete. Parallelism is permitted within a phase, and across C2-P1 / C2-P2 /
C2-P4 because their write scopes and evidence scopes are disjoint.

## 1. Phase barriers

| phase | packages | barrier | exit condition |
|---|---|---|---|
| **C2-P0** Freeze / registry / reference fixture | 3 | — (Cycle-1 baseline immutable) | baseline bound; registry closed and Q0-checked; reference fixture proven |
| **C2-P1** file_artifact probe | 1 | C2-P0 | three classes calibrated; FM2-FILE green |
| **C2-P2** cli_invocation probe | 2 | C2-P0 | DESIGN-CHECK-1 proven on Linux and Windows; four classes calibrated; FM2-CLI-* green |
| **C2-P3** process_effect probe | 2 | C2-P2 | closed vocabulary; three classes calibrated; FM2-EFFECT, FM2-PYC-2 green |
| **C2-P4** python_callable extensions | 1 | C2-P0 | all classes calibrated at the new digest; Cycle-1 hashes untouched |
| **C2-P5** Contract authoring aid / PLAN-V2.2 proposal | 2 | C2-P4 (and C2-P1..P3 by dependency) | proposal statically admitted; falsifiability complete |
| **C2-P6** Q0–Q3 | 1 | C2-P5 | four rungs green on five platforms |
| **C2-P7** Q4 | 1 | C2-P6 | 100,000/100,000, one kernel digest |
| **C2-P8** Q5 | 1 | C2-P7 | reproduction green with the extended corpus |
| **C2-P9** LedgerLock regression rerun | 1 | C2-P8 | verdicts separate; no generalization; no cohort |
| **C2-P10** External-validation machinery | 2 | C2-P6 | lifecycle mechanised; no workload selected |

## 2. Package graph

```
WP-2.0.1 (freeze manifest)
 ├─► WP-2.0.2 (registry + Q0 checkers)
 │    ├─► WP-2.1.1 (file_artifact) ─────────────────────────────┐
 │    ├─► WP-2.2.1 (cli harness) ─► WP-2.2.2 (cli classes) ─────┤
 │    │        └─► WP-2.3.1 (effect harness) ─► WP-2.3.2 ◄──────┼── WP-2.0.3 (reference fixture)
 │    └─► WP-2.4.1 (python_callable ext.) ──────────────────────┤
 └─► WP-2.0.3 (reference fixture)                               ▼
                                                     WP-2.5.1 (authoring aid, V2.2 proposal)
                                                          └─► WP-2.5.2 (falsifiability) ◄── WP-2.0.3
                                                                   └─► QP-2.6 (Q0–Q3)
                                                                         ├─► QP-2.7 (Q4) ─► QP-2.8 (Q5) ─► QP-2.9 (LedgerLock rerun)
                                                                         └─► WP-2.10.1 (cohort machinery) ─► WP-2.10.2 (profile freeze)
```

## 3. Critical path

WP-2.0.1 → WP-2.0.2 → WP-2.2.1 → WP-2.3.1 → WP-2.3.2 → WP-2.5.1 → WP-2.5.2 → QP-2.6 → QP-2.7 → QP-2.8 → QP-2.9.

The scenario probe (C2-P3) is on the critical path because 32 of the 77 LedgerLock criteria need it and it shares the
protocol-channel design with the CLI probe. C2-P1 and C2-P4 are off the critical path and can absorb slack.

## 4. Owner decision gates on the graph

| gate | blocks | if declined |
|---|---|---|
| DECISION-2 (fault step) | WP-2.3.1's `fault` step, two criteria | the step is omitted; the two criteria are restated by the plan author (WP-2.5.1 records them as unprovable) |
| DECISION-3 (test-named criteria) | WP-2.5.1's migration of six criteria | the six stay out of ProductProof; C2-P9 reports them as not provable by design |
| DECISION-5 (PlanQualityPolicy) | QP-2.9's plan_quality_verdict | NOT_CLAIMED, as in Cycle 1 |
| DECISION-6 (digest vs second probe id) | WP-2.4.1 | a second probe id `probe.python_callable_ext` keeps the Cycle-1 digest live |
| RFC §33 trigger for cohort machinery | WP-2.10.1 | C2-P10 stays a design; the external-validation plan remains a plan |

## 5. Rollback ancestry

Every package's rollback rule is "revert this package's commits; no downstream package may have consumed its evidence
artifact; if one has, revert that package too". Because every Cycle-2 artefact lives under `closure-evidence/v2/cycle2/`
and every probe in its own module, a rollback never touches a Cycle-1 file — the freeze manifest (WP-2.0.1) fails CI
if one changes.
