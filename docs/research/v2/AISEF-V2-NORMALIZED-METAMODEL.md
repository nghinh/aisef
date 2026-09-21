# AISEF V2 — normalized meta-model

Board resolution §13. One authoritative model of the fifteen objects, their planes, and their ownership. Where
this disagrees with the earlier proposals, this and
[`AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md`](AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md) govern.

**Rule for reading it: no cell may be ambiguous.** "May model edit?" and "may developer edit?" are `NO` unless
stated otherwise, and a `NO` means the system must make it impossible, not merely discouraged.

---

## 1. Planes

```
  REQUIREMENT PLANE      Requirement ─── ContractApproval ─── BehaviorContract
        (human authority)                                          │
                                                                   │ compile (pure, --check'd)
                                                                   ▼
  PRODUCT PLANE                                           ProductProofSpec
        (durable product facts;                                    │
         survive every re-plan)                                    │ referenced by
                                                                   ▼
  PLANNING PLANE           Plan ─── PlanObligation ──────────────► (spec id + role)
        (story ownership,              │
         parent expectations)          │
                                       ▼
  ADMISSION PLANE     StaticPlanAdmission (no probes)  →  StoryAdmission (probes, exact parent SHA)
                                       │
                                       ▼
  EXECUTION PLANE      StoryTransaction ─── DeveloperTests ─── CandidateProof ─── VerifiedProof
                                       │
                                       ▼
  RECORD PLANE                      Journal ──► Projection ──► QualificationEvidence
                                       ▲
                                    RunSpec (identity of everything the run resolved)
```

Two boundary rules carry most of the weight:

- **A product fact never carries a plan fact.** `ProductProofSpec` holds no story id and no parent expectation.
  Re-planning changes `plan_hash` and never `semantic_hash`.
- **No developer artefact is executed at the parent revision** (invariant IX). Parent state is observed only by
  harness-owned probes.

---

## 2. Authorship and mutability

### Table A — normative status, authorship, approval, edit rights

| # | Object | Normative or derived | Author | Approver | Model may edit? | Developer may edit? |
|---|---|---|---|---|---|---|
| 1 | **Requirement** | **Normative** | Owner (human) | Owner | **NO** — may propose text for human authoring | **NO** |
| 2 | **BehaviorContract** | **Normative** | Human, optionally from a model proposal | **Human** (`ContractApproval`, binds both hashes) | **NO** — may propose and adversarially review; advisory only | **NO** |
| 3 | **ProductProofSpec** | **Derived** (pure compile of 2) | Compiler | none — validity is the `--check` | **NO** | **NO** |
| 4 | **Plan** | **Normative** (planning plane) | Planner (human or model-assisted) | Owner, at plan freeze | Propose only; never edit a frozen plan | **NO** |
| 5 | **PlanObligation** | **Normative** (planning plane) | Planner | Owner, with the Plan | Propose only | **NO** |
| 6 | **StaticPlanAdmission** | **Derived** (a measurement of 4+5 and 3) | Harness | none | **NO** | **NO** |
| 7 | **StoryAdmission** | **Derived** (a measurement at the parent SHA) | Harness | none | **NO** | **NO** |
| 8 | **DeveloperTests** | **Normative** as process evidence; **never** product semantics | **Developer agent** | none | **YES — this is the only object a model authors** | **YES** |
| 9 | **CandidateProof** | **Derived** (probe output at the candidate) | Harness probe | none | **NO** | **NO** |
| 10 | **VerifiedProof** | **Derived** (independent re-observation + agreement) | Harness, in a verifier scope | none | **NO** | **NO** |
| 11 | **StoryTransaction** | **Derived** (a record of resource lifecycle) | Harness (`StoryScope`) | none | **NO** | **NO** |
| 12 | **Journal** | **Normative** — the only authority for state | Harness (`RunScope`-owned writer) | none | **NO** | **NO** |
| 13 | **Projection** | **Derived** (pure fold of 12) | Harness | none | **NO** | **NO** |
| 14 | **RunSpec** | **Derived** (resolution of configuration + capabilities) | Harness | Owner, by approving the profile | **NO** | **NO** |
| 15 | **QualificationEvidence** | **Derived** (ladder outputs + verdict) | Harness | Owner, by accepting a verdict | **NO** | **NO** |

**The single row that matters most is 8.** `DeveloperTests` is the only object a model or developer may author,
and it is the only object that decides nothing about product correctness. Every object that decides product
correctness is authored by the harness or approved by a human. That is invariant III (Independent Evidence)
stated as a property of the table rather than as a rule someone follows.

### Table B — freeze, identity, consumers

| # | Object | Mutable before freeze? | Freeze point | Identity / hash | Consumers |
|---|---|---|---|---|---|
| 1 | Requirement | Yes, by the owner | Requirement approval | `requirement_hash` (content) | BehaviorContract; traceability checks |
| 2 | BehaviorContract | Yes, until approved | `ContractApproval` | `contract_hash` (content) | Compiler → ProductProofSpec; human review |
| 3 | ProductProofSpec | No — regenerated, never edited | On its contract's approval | `semantic_hash` = f(contract semantics, probe id + digest, input, expectation) | Probes; PlanObligation; CandidateProof; Q0 `--check` |
| 4 | Plan | Yes, until plan freeze | Plan freeze, after StaticPlanAdmission passes | `plan_hash` | StoryAdmission; scheduler; plan-quality metrics |
| 5 | PlanObligation | With the Plan | With the Plan | `(criterion_id, plan_hash)` | StoryAdmission; verdict attribution |
| 6 | StaticPlanAdmission | No — a measurement | On production (precedes plan freeze) | digest of the result set | Plan freeze gate; Q0 |
| 7 | StoryAdmission | No — a measurement | On production, per story | `(story_id, parent_sha, plan_hash)` | Story gate; budget routing; `PLAN_DRIFT` |
| 8 | DeveloperTests | Yes, throughout the story | At story commit | tree digest of the test files at the candidate | `EngineeringTestAdequacy`; `process/tdd-chronology` |
| 9 | CandidateProof | No | On production | `(semantic_hash, candidate_sha, probe_digest)` | VerifiedProof; gate |
| 10 | VerifiedProof | No | On production | as 9, plus verifier scope id | Story gate; QualificationEvidence |
| 11 | StoryTransaction | No | At `story/end` | `(run_id, story_id)` | Journal; residual reporting; next-run preflight |
| 12 | Journal | **Append-only; never mutable** | Each append is final; `run/end` closes it | `(run_id, seq)`; dense `seq == index` | Every projection; replay; audit |
| 13 | Projection | No — recomputed | N/A (a pure function) | `(projection_id, journal_prefix_seq)` | Gate (six control-critical only); reporting |
| 14 | RunSpec | Yes, until run begin | `run/spec-resolved` | `runspec_hash`, incl. capability digests and `IdentityGrade` | Every decision; comparability of verdicts |
| 15 | QualificationEvidence | No | At verdict acceptance | digest over cited artefact hashes | Owner; release decisions; cohort records |

---

## 3. The four identities a verdict must cite

Every product verdict cites exactly four, and they are deliberately separable:

| identity | answers | changes when |
|---|---|---|
| `semantic_hash` | *what was proved* | the contract's semantics, the probe, or its input change |
| `plan_hash` | *why this story was asked to prove it* | the plan is revised — **never** invalidates product evidence |
| `candidate_sha` / `parent_sha` | *about which revision* | the code moves |
| `runspec_hash` | *under which resolved capabilities* | any capability digest or enforcement level changes |

This is what makes correction §1 pay for itself: a re-plan invalidates `plan_hash` only, so accumulated product
evidence survives. In the draft, every re-plan invalidated everything.

---

## 4. Ownership rules stated as prohibitions

Each is an enforcement obligation, with the mechanism named. A rule without a mechanism is the anti-pattern A5
identified in the study.

| # | Prohibition | Mechanism |
|---|---|---|
| O1 | No control path reads `Requirement.text`, `BehaviorContract.rationale`, or `PlanObligation.ownership_rationale` | Q0 static walker over kernel imports and field reads |
| O2 | No `ProductProofSpec` field may name a story, a plan or a parent expectation | Type definition + Q0 schema check |
| O3 | No developer-authored artefact is executed at the parent revision | Probe API accepts no developer path; Q1 test-layout invariance suite |
| O4 | `BehaviorVerdict` is defined only when `ProbeExecutionStatus == EXECUTED` | Type: verdict lives inside the `EXECUTED` variant |
| O5 | `REFUTED` may never route to `ENVIRONMENT`; `UNRUNNABLE` may never route to `DEVELOPER` | Armed invariant (`INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE`), uncontainable |
| O6 | A `ProductProofSpec` may not be compiled from an unapproved contract | Compiler requires a valid `ContractApproval` binding both hashes |
| O7 | `INTRODUCE` ownership is unique per spec within a plan | StaticPlanAdmission check 3 |
| O8 | No developer model call before `StoryAdmission` yields `READY` or a valid `PRE_SATISFIED` with remaining work | Story gate ordering; journal shows admission before any `provider/request` |
| O9 | The `JournalWriter` is owned by `RunScope`, never by a `StoryScope` | Scope construction; `RunScope` disposal ordered last |
| O10 | No projection reads `Event.time` | Q0 static check over projection modules |
| O11 | Only the six control-critical projections may be cited by a gate | Gate accepts a closed enum of projection ids |
| O12 | Agent-sourced text may not enter an evidence field | Evidence fields accept only harness-produced typed records; violation is `invariant/violated` |

---

## 5. Where each V1 defect family is now structurally excluded

Cross-check against [`V1-DEFECT-FAMILY-REGISTER.md`](V1-DEFECT-FAMILY-REGISTER.md); listed only where the
meta-model itself does the work.

| family | excluded by |
|---|---|
| `FAM-IDENTITY` | dense `seq`; four cited identities; content-addressed capabilities (O2, §3) |
| `FAM-OUTCOME`, `FAM-TYPED-OUTCOMES` | two-axis outcome (O4, O5) |
| `FAM-PROSE`, `FAM-JUDGE` | O1, O12; foreign codes flatten to `UNKNOWN` |
| `FAM-RETRY`, `FAM-BUDGET` | retryability in the taxonomy; budgets as projections; O5 |
| `FAM-PROOF-PLACEMENT` | O3 + the `MUST_NOT_HOLD` precondition rule |
| `FAM-PLAN-OWNERSHIP` | O7 + StoryAdmission dispositions + `PLAN_DRIFT` |
| `FAM-EVIDENCE-SEMANTICS` | append-site validation; candidate-side vacuity control |
| `FAM-PROCESS`, `FAM-OWNERSHIP` | StoryScope ordered stack; measured range emptiness; O9 |
| `FAM-RELEASE` | append-only journal with no mutation verb; provenance guard |
| `FAM-QUALIFICATION-MEASUREMENT` | projections not counters + reference models (O11) |

`FAM-BENCH` is not excluded by the meta-model; it is governed by the evaluation-cohort lifecycle.
`FAM-PROVIDER` and `FAM-MODEL-CAPABILITY` are not excludable by any architecture — they are measured, not
prevented.
