# AISEF V1 — defect family register

Supporting artefact for the external architecture study. It fixes the **rows** of the defect-family matrix in
[`AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md`](AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md) so that the matrix scores
external patterns against *named, evidenced* families rather than invented ones.

**Provenance.** Families 1–18 are read from AISEF's own frozen evidence under `closure-evidence/`: the
architectural family map (`closure-evidence/hardening/defect-family-map.json`, Phase 2, 13 families) plus five
further `family:` labels carried on individual findings. Families 19–22 are **named in this study**; each is
grounded in a specific frozen record but had no `FAM-` label because V1's family map covered the assurance kernel
only, and these live outside it. They are marked `NEW HERE`.

Nothing in this register modifies V1 evidence. It only reads it.

---

## Kernel families (from `defect-family-map.json`, Phase 2)

| # | Family | Cause (verbatim from the map, condensed) | Exemplar |
|---|---|---|---|
| 1 | `FAM-IDENTITY` | A control decision selects its evidence by chronological recency (`last`, newest, HEAD) or by position/spelling instead of by an exact identity. | D-004, D-021, D-023, D-033 |
| 2 | `FAM-OUTCOME` | An absence, an environment failure or a non-verdict is mapped onto the two-valued pass/fail axis instead of a typed outcome. | D-001, D-005, D-008, D-010, D-012, D-029 |
| 3 | `FAM-PROSE` | Free-form model or tool text is matched by substring/regex and the match *creates control state*, outranking a structured source. | D-018, D-026 |
| 4 | `FAM-RETRY` | A failure of one stage is routed to a retry of another stage or charged to the wrong budget; the only recovery path is "open a developer session again". | D-006, D-032 |
| 5 | `FAM-RECOVERY` | A resume recomputes or changes evaluated state without invalidating the evidence that depended on the previous state. | D-034, D-035, OBS-R13 |
| 6 | `FAM-OWNERSHIP` | Paths written by the harness, tools or pre-existing dirt are attributed to the developer/story, so scope checks and diffs act on files nobody authored. | D-011, D-030, SS-93 |
| 7 | `FAM-TOOL` | A configured verification command is trusted to be runnable in the declared environment; its absence is read as a behavioural result. | D-009, D-013, D-028 |
| 8 | `FAM-PROCESS` | Process lifecycle and liveness — cleanup racing a live writer, orphans, unreaped children. | D-024, D-025, D-027 |
| 9 | `FAM-SCHEDULER` | The scheduler uses *declared* scope, not *effective* scope. | D-031 |
| 10 | `FAM-APPROVAL` | Approval and pre-registration binding — acceptance scope implied rather than bound. | D-014, D-017 |
| 11 | `FAM-RELEASE` | Release and closure identity — bookkeeping bound to a commit can never be current once committed. | D-007, D-019, D-020, D-022 |
| 12 | `FAM-BENCH` | Benchmark integrity — cohorts merged by task name, holdout contamination. | D-003, D-015, D-016 |
| 13 | `FAM-JUDGE` | Model output as control authority — a blocking gate decision rests on the model reviewer alone. | D-002, F-7, OBS-OC-2 |

## Further kernel families (labelled on individual findings, post-Phase-2)

| # | Family | Cause | Exemplar |
|---|---|---|---|
| 14 | `FAM-TYPED-OUTCOMES` | A stage that **executed** is recorded as unrunnable because its output text contains a marker of absence. Sibling shape of SS-23, fixed there only for `test`. | SS-92 (bandit scanned 51 187 lines, exit 1, recorded `TOOL_UNRUNNABLE` because a quoted test line read `not found: Ghost`) |
| 15 | `FAM-BUDGET` | A cap reached inside one stage falls through to another stage's routing because absence-gated logic goes empty once any check FAILED. | SS-64 |
| 16 | `FAM-EVIDENCE-SEMANTICS` | A control passes on evidence that did not execute at the identity it claims to be about. | SS-81 ("can PASS on tests that never executed at the parent SHA") |
| 17 | `FAM-QUALIFICATION` | The qualification harness mislabels *why* a run stopped, or measures an exit criterion at a place where it cannot discriminate. | SS-94 (a provider outage reported as the model's stop), SS-95 (false-BLOCK measured only at trunk) |
| 18 | `FAM-QUALIFICATION-MEASUREMENT` | A measurement derives its population by parsing human-facing output that structurally cannot contain it. | SS-77 (`aisef status` prints only stories that are NOT passing; the DONE set was always empty) |

## Delivery-side families — `NEW HERE`

V1's family map stops at the assurance kernel. These four are what W1 proved exist outside it, and V2 must
address them or repeat them.

| # | Family | Cause | Grounding record |
|---|---|---|---|
| 19 | `FAM-PROOF-PLACEMENT` `NEW HERE` | A proof obligation's semantics depend on **where the developer put the test file**, not on the criterion. A criterion's parent state is read from its tests, and whether a test collects at the parent is a property of its *file*. | `ARCH-LESSON-PROOF-PLACEMENT.json`; PLAN-V2.1-DEFECT-001; two runs of the identical frozen plan reached opposite parent states for AC-STORY-01-01-4/-5 |
| 20 | `FAM-PLAN-OWNERSHIP` `NEW HERE` | A criterion is assigned to a story that does not own the behaviour it asserts: either the behaviour is already green at the parent (`PLAN_OVERLAP`) or its precondition is owned elsewhere (`PLAN_PRECONDITION_MISSING`). | W1 verdict §B: run 1 of PLAN-V2 stopped on AC-STORY-04-01-2 `PLAN_OVERLAP`; V2.1 run 1 stopped 0/16 on `PLAN_PRECONDITION_MISSING` |
| 21 | `FAM-PROVIDER` `NEW HERE` | The run's outcome is determined by provider behaviour — route refusal, usage limits, tool-calling availability — and must not be chargeable to any developer or plan budget. | `W1-DELIVERY-FAILURE-DECOMPOSITION.json` (gpt56sol 400 route refusal; gpt55 abandoned after two 429 interruptions); three tool-smoke timeouts on `ds/deepseek-v4-pro` during V2.1 |
| 22 | `FAM-MODEL-CAPABILITY` `NEW HERE` | The model does not complete the delivery workload even when kernel, plan, environment and provider are all sound — a capability ceiling, not a defect in any component. | W1 verdict §C; 0 of 2 valid V2.1 runs delivery-complete; `deepseek-ro-1/2` 11/16, `minimax-ro-1/2` 11/16 and 7/16 |

---

## Cross-family note

`SS-96` carries no single family label because it **is** a crossing: `FAM-OUTCOME` (a check reported FAILED for
evidence that did not execute) propagating into `FAM-RETRY` (an environment failure charged to the developer's
quality budget) through `FAM-BUDGET`'s absence-gated routing (`_absent_stages` returns nothing once any check
FAILED). It is the single most instructive V1 defect for V2 design: three families, one line of code, and the
fix was one branch.

The invariant it produced — `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE`, "no gate check may report FAILED for
evidence that did not execute" — is a V2 top-level candidate, and is the reason the capability seam in
[`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §3 must keep an availability predicate.
