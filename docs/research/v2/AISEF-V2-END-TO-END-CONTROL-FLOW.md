# AISEF V2 — end-to-end control flow

Board resolution §14. Every station from approved requirements to run completion, with every outcome it can
produce. Objects and ownership are defined in
[`AISEF-V2-NORMALIZED-METAMODEL.md`](AISEF-V2-NORMALIZED-METAMODEL.md); the corrections this reflects are in
[`AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md`](AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md).

> ## ⚠ Superseded for implementation decisions
>
> [`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md`](../../architecture/AISEF-V2-ARCHITECTURE-RFC.md) is
> normative. Owner decisions B1–B5 changed four stations: **S4** produces a `StaticPlanAdmissionResult` from the
> project's execution of the engine (Q0/Q1 qualify the engine, never run the project's admission); **S6/S18**
> use the `RunTerminationSentinel`, `OPEN` fsync'd before execution and `CLEAN` only after all disposal and a
> durable `run/end`; **S10** is typed `ADEQUATE` / `INADEQUATE` / `INCOMPLETE`, where `INCOMPLETE`
> (`INDETERMINATE` vacuity or `UNMEASURABLE` relevance) never blocks and is never charged to the developer; and
> **S17/S18** record `delivery_verdict` and `plan_quality_verdict` separately.

**Outcome vocabulary.** `BLOCK` — stops and does not proceed. `RETRY` — may re-attempt against a named budget.
`SKIP MODEL` — proceeds without any developer model call. `REQUIRE HUMAN` — cannot proceed without a human
decision. `FAIL ENVIRONMENT` — a typed environment failure, chargeable to no developer or plan budget.
`FAIL PRODUCT` — the product is wrong, chargeable to the developer.

---

## 1. The flow

```
  ┌─ DESIGN TIME (per requirement set) ────────────────────────────────────────┐
  │  S1  requirements approved                        REQUIRE HUMAN            │
  │  S2  contracts approved                           REQUIRE HUMAN            │
  │  S3  ProductProofSpecs generated                  BLOCK                    │
  └────────────────────────────────────────────────────────────────────────────┘
                                   │
  ┌─ PLAN TIME (per plan) ─────────┼───────────────────────────────────────────┐
  │  S4  StaticPlanAdmission  ◄── no probes execute   BLOCK                    │
  │  S5  plan freeze                                  BLOCK · REQUIRE HUMAN    │
  └────────────────────────────────────────────────────────────────────────────┘
                                   │
  ┌─ RUN TIME ─────────────────────┼───────────────────────────────────────────┐
  │  S6  run begin (lease, journal, RunSpec)          BLOCK · FAIL ENVIRONMENT │
  │                                   │                                        │
  │    ┌─ PER STORY ─────────────────┼─────────────────────────────────────┐   │
  │    │  S7   story parent freeze                     BLOCK               │   │
  │    │  S8   StoryAdmission  ◄── probes, exact SHA   BLOCK · SKIP MODEL  │   │
  │    │             │                                  · FAIL ENVIRONMENT │   │
  │    │             ├──────────── PRE_SATISFIED (all) ──────────┐         │   │
  │    │             ▼                                           │         │   │
  │    │  S9   developer execution (optional)   RETRY · FAIL PRODUCT       │   │
  │    │  S10  engineering-test adequacy        RETRY · FAIL PRODUCT       │   │
  │    │  S11  candidate proof                  FAIL PRODUCT · FAIL ENV    │   │
  │    │  S12  independent verification         BLOCK (disagreement)       │   │
  │    │             │◄──────────────────────────────────────────┘         │   │
  │    │  S13  review / security                RETRY · FAIL PRODUCT       │   │
  │    │  S14  merge                            BLOCK · FAIL ENVIRONMENT   │   │
  │    │  S15  post-merge proof                 BLOCK · FAIL PRODUCT       │   │
  │    │  S16  transaction disposal             FAIL ENVIRONMENT           │   │
  │    │  S17  story complete                                              │   │
  │    └───────────────────────────────────────────────────────────────────┘   │
  │  S18  run complete                                BLOCK                    │
  └────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Station by station

### S1 · Requirements approved
**Produces:** `Requirement` with `requirement_hash`.
**Outcomes:** `REQUIRE HUMAN` — the owner approves; nothing downstream may proceed without it.
**Notes:** models may propose text; they never author or approve. No control path reads `Requirement.text` (O1).

### S2 · Contracts approved
**Produces:** `BehaviorContract` + `ContractApproval` binding `requirement_hash` and `contract_hash`.
**Outcomes:** `REQUIRE HUMAN`. Model-produced adversarial reviews are recorded as advisory journal refs.
**Why a human gate:** a contract can faithfully encode a wrong reading of a requirement, and nothing below can
detect it (adversarial scenario F).

### S3 · ProductProofSpecs generated
**Produces:** `ProductProofSpec` with `semantic_hash`, by a pure compile of the approved contract.
**Outcomes:** `BLOCK` when the committed spec does not match a fresh derivation (`--check`), when the contract
lacks a valid approval (O6), or when the named probe does not resolve.
**Notes:** no story or parent information may appear here (O2).

### S4 · StaticPlanAdmission
**Executes no probes.** Checks: requirement coverage; contract→spec integrity; ownership with unique
`INTRODUCE` per spec; acyclic dependency DAG; contradictions; probe availability **by digest**; schema;
traceability; plan structure.
**Outcomes:** `BLOCK` on any failure. No SHA of a future story's parent is invented.
**Catches:** adversarial scenario **D** (missing probe) before any execution.

### S5 · Plan freeze
**Produces:** `plan_hash`.
**Outcomes:** `BLOCK` if S4 did not pass. `REQUIRE HUMAN` — the owner accepts the plan.
**Notes:** after freeze, no object in the planning plane may change. A revision produces a new `plan_hash` and
leaves every `semantic_hash` intact.

### S6 · Run begin
**Acquires, in order:** run lease → `JournalWriter` (owned by `RunScope`) → terminal sink → `RunSpec`
resolution → `run/begin`, `run/spec-resolved`.
**Outcomes:** `BLOCK` if the lease cannot be taken (another run owns this workload).
`FAIL ENVIRONMENT` if a capability cannot be resolved at all.
**Notes:** `RunSpec` carries capability digests, resolved enforcement levels and the run's minimum
`IdentityGrade`. A run whose grade is `ATTESTED` is comparable only with other `ATTESTED` runs.

### S7 · Story parent freeze
**Produces:** the story's exact `parent_sha` (full, never abbreviated).
**Outcomes:** `BLOCK` if the parent cannot be resolved to a full SHA, or if a predecessor story has not reported
a terminal state.

### S8 · StoryAdmission — the first point where probes run
**Runs** every obligation's probe against `parent_sha`, producing `(ProbeExecutionStatus, BehaviorVerdict)`.
**Outcomes:**

| disposition | outcome | owner | budget |
|---|---|---|---|
| `READY` | proceed to S9 | — | — |
| `PRE_SATISFIED` (some obligations) | proceed to S9 on the remainder; record `PLAN_DRIFT` | PLAN (drift) | **none** |
| `PRE_SATISFIED` (all obligations) | **SKIP MODEL** → `STORY_ALREADY_SATISFIED`, jump to S12 | PLAN (drift) | **none** |
| `PRECONDITION_BROKEN` | `BLOCK` | PLAN | none |
| `PLAN_CONTRADICTION` | `BLOCK` | PLAN | none |
| `PROBE_UNRUNNABLE` | `FAIL ENVIRONMENT`, `RETRY` against the environment budget | ENVIRONMENT | environment |
| `PROBE_INVALID` | `BLOCK` | PLAN / INTEGRATION | none |

**Hard rule:** no `provider/request` event may precede the admission record for this story (O8).
**Covers:** adversarial **A**, **C**, **K**.

### S9 · Developer execution — optional
**Runs** the developer agent inside the `StoryScope`.
**Outcomes:** `RETRY` against the **developer quality budget** only when the failure's typed owner is
`DEVELOPER`. `FAIL PRODUCT` on budget exhaustion. A provider failure here is owner `PROVIDER` and retries
against the provider budget; an environment failure is owner `ENVIRONMENT`. Retryability is a property of the
typed code, never a decision at this station.
**Skipped entirely** when S8 returned `PRE_SATISFIED` for every obligation.

### S10 · Engineering-test adequacy
**Checks:** tests execute at the candidate; tests pass; `relevance` (coverage intersection with the story's own
diff — at least one changed line and one changed branch); `vacuity` (the candidate-side control: neutralise the
story's product hunks, keep the test files, the tests must fail); regressions green.
**Outcomes:** `RETRY` (developer budget) then `FAIL PRODUCT`.
**Never** consults parent-side state (O3, invariant IX). `process/tdd-chronology` is recorded here as evidence
and blocks nothing.
**Covers:** adversarial **B**.

### S11 · Candidate proof
**Runs** each obligation's probe at `candidate_sha`, in the implementer's scope.
**Outcomes:** `EXECUTED/SATISFIED` proceeds. `EXECUTED/REFUTED` is `FAIL PRODUCT` → `RETRY` on the developer
budget. `EXECUTED/INDETERMINATE` is owner PLAN or INTEGRATION by reason and does not charge the developer.
`UNRUNNABLE` is `FAIL ENVIRONMENT`. `INVALID_SPEC` is `BLOCK`.

### S12 · Independent verification
**Re-runs** each probe in a verifier `StoryScope` that shares no worktree, sandbox or process range with the
implementer's, and compares.
**Outcomes:** agreement → proceed. Disagreement → `BLOCK`, verdict `INDETERMINATE`, owner `INTEGRATION`. A
mismatch of `probe_id`, `probe_digest` or `semantic_hash` is `PROBE_MISMATCH` — a harness integrity failure, not
a statement about the product.
**Never** arbitrated by a model; never resolved by re-running until the two agree.
**Also the station reached directly** from a fully `PRE_SATISFIED` story, so an already-correct behaviour is
still independently verified before the story is called complete.

### S13 · Review and security
**Runs** reviewer and security capabilities in **read-only** scopes whose confinement is derived from the scope,
not passed as a parameter.
**Outcomes:** `RETRY` (review or security budget, per typed owner) → `FAIL PRODUCT` on exhaustion. A scanner
that executed and produced findings is `EXECUTED` — never `UNRUNNABLE` (this is SS-92's shape and the two-axis
rule prevents it). A scanner that could not run is `FAIL ENVIRONMENT`.

### S14 · Merge
**Outcomes:** `BLOCK` on conflict — owner `INTEGRATION`, never `DEVELOPER`. `FAIL ENVIRONMENT` on VCS failure.

### S15 · Post-merge proof
**Re-runs** the story's obligations at the merged revision, plus every `PRESERVE` obligation of prior stories
that the merge could affect.
**Outcomes:** `BLOCK` on any regression — owner `INTEGRATION`. `FAIL PRODUCT` if the story's own obligation is
now refuted.
**Measurement-point note:** post-merge is valid for *integration* claims. It is **not** valid for
*refusal-correctness* claims — SS-95 was exactly that error, a "false BLOCK" metric measured only at trunk,
where a blocked story's code never arrives. The claim determines the measurement point, and the verdict records
which point was used.

### S16 · Transaction disposal
**Unwinds** the `StoryScope` resource stack in reverse acquisition order: processes reaped and the range proved
empty → sandbox → worktree → scratch. Each release emits `story/resource-released` through the **RunScope**
journal, including failures.
**Outcomes:** `FAIL ENVIRONMENT` on a disposal failure; the story's product verdict is unaffected, and residuals
are named for the next run's preflight.
**Covers:** adversarial **J**.

### S17 · Story complete
**Emits** `story/end` with the terminal class, the four cited identities, and any `PLAN_DRIFT`.

### S18 · Run complete
**Writes** `run/dispose-begin`, disposes `RunScope` (journal writer released last, after the lease), writes
`run/end` and the terminal sink record.
**Outcomes:** `BLOCK` if any story lacks a terminal state.
**Notes:** a journal ending at `run/dispose-begin` with no `run/end` is itself evidence of an incomplete
teardown; the next run's preflight reports it `TORN`.

---

## 3. Every outcome, by station

| station | BLOCK | RETRY | SKIP MODEL | REQUIRE HUMAN | FAIL ENV | FAIL PRODUCT |
|---|---|---|---|---|---|---|
| S1 requirements | | | | ● | | |
| S2 contracts | | | | ● | | |
| S3 specs generated | ● | | | | | |
| S4 static admission | ● | | | | | |
| S5 plan freeze | ● | | | ● | | |
| S6 run begin | ● | | | | ● | |
| S7 parent freeze | ● | | | | | |
| S8 StoryAdmission | ● | ● (env) | ● | | ● | |
| S9 developer | | ● | | | ● | ● |
| S10 test adequacy | | ● | | | | ● |
| S11 candidate proof | ● | ● | | | ● | ● |
| S12 verification | ● | | | | | |
| S13 review/security | | ● | | | ● | ● |
| S14 merge | ● | | | | ● | |
| S15 post-merge | ● | | | | | ● |
| S16 disposal | | | | | ● | |
| S17 story complete | | | | | | |
| S18 run complete | ● | | | | | |

**Two properties readable from the table.**

*Only four stations can charge the developer* (S9, S10, S11, S13), and each does so only when the failure's
typed owner is `DEVELOPER`. Admission, verification, merge and disposal cannot — which is
`INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` and the SS-96 fix expressed as a property of the flow rather than of one
branch.

*Human approval appears only at design and plan time* (S1, S2, S5). No station inside the run requires a human,
so an unattended run either completes or reaches a typed terminal state. That is what makes long autonomous runs
answerable after the fact.

---

## 4. Interruption at any station

An operator interrupt or crash at any point produces the same shape: bounded escalating shutdown, synthetic
typed closers distinguishing `OUTCOME_UNKNOWN` from `NOT_STARTED`, timestamps reused so repair is idempotent,
every synthetic event marked synthetic, then `run/interrupted` and a terminal class. A second interrupt during
disposal abandons — **and records that it was abandoned**. No station may leave a gap.
