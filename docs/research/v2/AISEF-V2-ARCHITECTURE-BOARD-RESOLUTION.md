# AISEF V2 — architecture board resolution

Response to **AISEF V2 — ARCHITECTURE BOARD RESOLUTION / FINAL DESIGN CORRECTION BEFORE RFC**. One bounded
design-correction pass. No V2 implementation; no RFC.

> ## ⚠ Superseded for implementation decisions
>
> The owner has since issued **AISEF V2 — OWNER RESOLUTION OF RFC BLOCKERS** (B1–B5) and authorised the final
> RFC. [`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md`](../../architecture/AISEF-V2-ARCHITECTURE-RFC.md) is
> now normative; this document is design history. The owner decisions changed five things here:
>
> | § here | Owner decision | Change |
> |---|---|---|
> | §5 vacuity control | **B1 MODIFY** | Not a boolean gate. Typed `NON_VACUOUS` / `VACUOUS` / `INDETERMINATE`; collection, import, reconstruction, tool and environment failures are `INDETERMINATE`, never proof of non-vacuity. Engineering-quality evidence only — SS-81-style false *product* assurance is already structurally removed because developer tests no longer decide product proof. |
> | §5 relevance | **B2 MODIFY** | "Changed line **and** changed branch" rejected as universal. Typed `RELEVANT` / `IRRELEVANT` / `UNMEASURABLE`; cycle-1 minimum is executed-test ∩ executable changed line. Capability absence is never `IRRELEVANT`. |
> | §10 identity | **B3 ACCEPT + extend** | Three grades: `VERIFIED` / `ATTESTED` / `OPAQUE`. `OPAQUE` (e.g. dynamic model-combo routes) is barred from Q6, sealed cohorts and generalization claims. Comparability needs identity tuple **and** grade **and** enforcement identity — grade alone is insufficient. |
> | §8 terminal sink | **B4 ACCEPT + refine** | Renamed `RunTerminationSentinel` and **inverted**: it records *success*. `OPEN` fsync'd before execution; `CLEAN` only after all disposal and a durable `run/end`. Correctness no longer depends on writing a record after a failure. |
> | §3 / §12 drift | **B5 ACCEPT** | `PlanQualityPolicy` with named thresholds; **no universal framework k%**. `delivery_verdict` and `plan_quality_verdict` are separate and the separation is mandatory. Qualification must preregister thresholds or make no plan-quality claim. |
> | §2 / §6 admission | normalization | `StaticPlanAdmissionEngine` (qualified by Q0/Q1) is distinct from `StaticPlanAdmissionResult` (produced by a project at plan time). Q0 never executes a project's admission. |

This document was **authoritative over the earlier proposals** where they disagree. The earlier documents have
been updated and each now points here.

**Disposition: 12 corrections, 12 accepted. Two accepted with a stated qualification (§5, §10), and one
accepted with an added mechanism I am proposing (§5).** Nothing rejected — and §0 below explains why that is a
finding rather than deference.

---

## 0. Why nothing was rejected

Rubber-stamping a review is a failure mode, so the disposition needs a reason. Each correction either cites a
*measured* V1 defect my draft did not close, or names an *impossibility* in the draft:

| § | What it is | Grounding |
|---|---|---|
| 1 | Factoring error | `ProofSpec` held `required_at_baseline`, a plan fact, inside a product object |
| 2 | **Impossibility** | My single admission required the parent SHA of every story before execution. Those SHAs do not exist yet. The draft was unimplementable as written. |
| 3 | Measured | `AC-STORY-04-01-2` — run 1 stopped at 10/16 on a behaviour already green at the parent |
| 4 | Measured | SS-92: a bandit scan that **executed** (51 187 lines, exit 1) recorded `TOOL_UNRUNNABLE`. That is exactly the conflation of execution status with verdict. |
| 5 | Measured | PLAN-V2.1-DEFECT-001 — RED-at-parent is the *remaining* reason to execute a developer artefact at the parent |
| 6 | Category error in my draft | I placed plan admission — which runs probes — inside a rung I labelled "no execution" |
| 7 | Design limitation | Consumed-once cannot express a preregistered *n*-run protocol; a sample of one is not a claim |
| 8 | **Impossibility** | The journal writer was owned by the scope whose teardown it must record |
| 9 | Gap I recorded but did not close | My §20 listed "a projection consistently wrong in both modes" as unmitigated |
| 10 | Measured | SS-65 (P1, `INV-N.DEFAULT-CAPABILITY`) — a managed image whose contents decided whether bandit existed |
| 11 | Gap I recorded but did not close | My §20 listed "a contract faithful to a wrong requirement" as unmitigated |
| 12 | Process | — |

Two of the twelve (§2, §8) are defects that would have surfaced only at implementation time, which is the
argument for having run this pass before the interfaces froze.

---

## 1. Product proof and plan obligation are separate planes — ACCEPTED

The draft's `ProofSpec` carried `required_at_baseline`. That is a statement about *a story's position in a
plan*, not about the product. Merging them meant a product fact could not be reused across plans, and a plan
revision changed a product identity.

**Product plane.**

```python
@dataclass(frozen=True)
class ProductProofSpec:
    id: str                       # "PPS-" + digest(canonical form)
    contract_id: str
    probe_id: str
    probe_version_digest: str     # content-addressed; see §10
    probe_input: Mapping[str, Any]
    candidate_expectation: BehaviorVerdict   # SATISFIED for MUST_HOLD, REFUTED for MUST_NOT_HOLD
    compiler_id: str              # identity of the BehaviorContract -> ProductProofSpec compiler
    compiler_digest: str
    semantic_hash: str            # binds contract semantics + probe identity + input + expectation
```

It contains **no** story id, no parent expectation, no ownership. A `ProductProofSpec` is a durable fact about
the product and survives every plan revision.

**Planning plane.**

```python
class ObligationRole(Enum):
    INTRODUCE = "INTRODUCE"   # this story is expected to make the behaviour true
    PRESERVE  = "PRESERVE"    # the behaviour is already true and must remain so
    VERIFY    = "VERIFY"      # this story must confirm it, owning neither introduction nor preservation

@dataclass(frozen=True)
class PlanObligation:
    criterion_id: str
    product_proof_spec_id: str
    story_id: str
    role: ObligationRole
    expected_parent: ParentExpectation   # REFUTED_AT_PARENT | SATISFIED_AT_PARENT | UNCONSTRAINED
    depends_on: tuple[str, ...]          # criterion ids that must complete first
    ownership_rationale: str             # prose, for human review; never read by control
```

**Cardinality.** One `ProductProofSpec` may be referenced by many `PlanObligation`s. **INTRODUCE ownership must
be unique within a plan** (a Q0 static check). `PRESERVE` and `VERIFY` references may be many, and across
different plans the same spec may carry different roles — see adversarial scenario L.

**Consequence for identity.** A verdict cites a `semantic_hash` (product) *and* a `plan_hash` (planning).
Re-planning changes the second and not the first, so product evidence accumulated under one plan remains valid
under the next. The draft could not express that.

---

## 2. Two-stage admission — ACCEPTED

The draft was unimplementable: it required a measured baseline verdict per criterion *before freezing the plan*,
which presumes every story's parent SHA already exists. Only the first story's parent is known before execution.

### A. StaticPlanAdmission — before any agent call, no probe execution

Checks, all static:

1. requirement coverage — every approved `Requirement` maps to ≥1 `BehaviorContract`;
2. `BehaviorContract` → `ProductProofSpec` integrity (`--check` against the committed derivation);
3. ownership — every criterion has exactly one story; **INTRODUCE ownership is unique per spec**;
4. dependency DAG — acyclic, and every `depends_on` resolves;
5. contradictions — no two obligations in the same story assert incompatible parent expectations for the same
   spec; no `PRESERVE` ordered before its `INTRODUCE`;
6. proof-capability availability — every `probe_id` resolves and its digest matches (**catches scenario D
   before execution**);
7. schema and traceability — every criterion reaches a `Requirement` through a contract;
8. plan structure — stories form a total order or an explicit DAG; no orphan criteria.

**No future parent SHA is invented.** No probe runs. This is genuinely static and belongs in Q0.

### B. StoryAdmission — immediately before each story, at that story's exact frozen parent SHA

Probes run here, against a real revision. This is a **runtime gate**, not a ladder rung; its *implementation* is
qualified by Q0 and Q1 (correction §6).

```python
class StoryAdmissionDisposition(Enum):
    READY                = "READY"
    PRE_SATISFIED        = "PRE_SATISFIED"
    PRECONDITION_BROKEN  = "PRECONDITION_BROKEN"
    PLAN_CONTRADICTION   = "PLAN_CONTRADICTION"
    PROBE_UNRUNNABLE     = "PROBE_UNRUNNABLE"
    PROBE_INVALID        = "PROBE_INVALID"
```

Classification, per obligation, from the measured `(ProbeExecutionStatus, BehaviorVerdict)` pair of §4:

| role | expected at parent | measured | disposition |
|---|---|---|---|
| INTRODUCE | REFUTED | `EXECUTED/REFUTED` | `READY` |
| INTRODUCE | REFUTED | `EXECUTED/SATISFIED` | `PRE_SATISFIED` (§3) |
| INTRODUCE | REFUTED | `EXECUTED/INDETERMINATE` (precondition absent) | `READY` — the subject not existing is the expected pre-state |
| PRESERVE | SATISFIED | `EXECUTED/SATISFIED` | `READY` |
| PRESERVE | SATISFIED | `EXECUTED/REFUTED` | `PRECONDITION_BROKEN` |
| VERIFY | UNCONSTRAINED | any `EXECUTED/*` | `READY` |
| any | — | `UNRUNNABLE` | `PROBE_UNRUNNABLE` — owner `ENVIRONMENT` |
| any | — | `INVALID_SPEC` | `PROBE_INVALID` — owner `PLAN`/`INTEGRATION` |

`PLAN_CONTRADICTION` is raised when the measured parent state cannot be reconciled with the plan's own record:
for example a `PRESERVE` measured `REFUTED` whose introducing story already reported `COMMIT`, or two
obligations in this story requiring incompatible parent states for the same spec.

**No developer model call may begin** until StoryAdmission yields `READY`, or a valid `PRE_SATISFIED`
disposition with remaining work.

---

## 3. PRE_SATISFIED is not a delivery failure — ACCEPTED

**The rule.** An `INTRODUCE` obligation measured `SATISFIED` at the actual parent produces:

- `PRE_SATISFIED` on that obligation,
- `PLAN_DRIFT` recorded against the plan, attributed through the dependency DAG to whichever completed story
  actually introduced the behaviour (or to `UNATTRIBUTED` when none can be identified),
- **no developer budget consumed**, and
- **no requirement to make correct code wrong.**

If other obligations remain, the story continues on those. If *every* obligation is already satisfied, the story
ends `STORY_ALREADY_SATISFIED`: each obligation is verified independently at the candidate (which equals the
parent), and the developer call is skipped entirely.

**How this preserves product correctness while still exposing plan quality.** The two planes of §1 are exactly
what makes this safe. The *product* claim is untouched: every behaviour is still proved present by an
independent harness probe at the candidate revision, by the same `ProductProofSpec`, at the same
`semantic_hash`. What changes is the *plan* claim: the plan said this story would introduce the behaviour and it
did not need to. That is recorded as a plan-quality datum, not as a product defect and not as a developer
failure. Product correctness is measured by probes; plan correctness is measured by drift. Conflating them was
V1's error.

**Measured consequence.** V1's diagnostic run 1 of PLAN-V2 stopped at **10/16**, `stop_owner = PLAN`, on
`AC-STORY-04-01-2` — "declared CHANGE_REQUIRED for a behaviour already green at the story's parent —
PLAN_OVERLAP". Under this correction that is `PRE_SATISFIED` + `PLAN_DRIFT`, the story continues, and the run is
not terminated by it.

**What remains a hard plan blocker:** `PRECONDITION_BROKEN`, `PLAN_CONTRADICTION`, `PROBE_INVALID`, and a
`ProductProofSpec` whose contract no longer compiles. Nothing else.

---

## 4. Probe execution status and behaviour verdict are separate axes — ACCEPTED

The draft's single `Verdict` enum conflated them, and the measured V1 instance is **SS-92**: a bandit scan that
*executed*, scanned 51 187 lines and exited 1 was recorded `TOOL_UNRUNNABLE` because its output quoted a line
containing a missing-tool marker. Execution status and observation are different questions.

```python
class ProbeExecutionStatus(Enum):
    EXECUTED     = "EXECUTED"      # the observation harness ran to completion
    UNRUNNABLE   = "UNRUNNABLE"    # the observation harness could not run
    INVALID_SPEC = "INVALID_SPEC"  # the spec is not evaluable by this probe

class BehaviorVerdict(Enum):
    SATISFIED     = "SATISFIED"
    REFUTED       = "REFUTED"
    INDETERMINATE = "INDETERMINATE"   # ran, and cannot decide — carries a reason
```

`BehaviorVerdict` is defined **only** when status is `EXECUTED`. The legal product is six states:

| status | verdict | meaning | owner on failure |
|---|---|---|---|
| EXECUTED | SATISFIED | observed present | — |
| EXECUTED | REFUTED | **observed absent** | DEVELOPER (at candidate) / plan disposition (at parent) |
| EXECUTED | INDETERMINATE | ran; cannot decide; reason required | PLAN or INTEGRATION, by reason |
| UNRUNNABLE | — | could not look | **ENVIRONMENT** |
| INVALID_SPEC | — | not evaluable | PLAN / INTEGRATION |
| *(absent)* | — | not attempted | not chargeable to anyone |

### The separation that makes this work

A probe declares its **observation harness** (what must function for it to look) separately from its **subject**
(what it looks at).

- The harness failing → `UNRUNNABLE`. Interpreter missing, sandbox unavailable, tool absent, timeout of the
  probe itself.
- The subject being absent → an **observation**, not a failure. `EXECUTED` + `REFUTED` for a `MUST_HOLD`
  contract.

This is what dissolves the draft's `UNRESOLVABLE`. **`UNRESOLVABLE` is removed.** A missing module is a
perfectly good observation that the behaviour is absent, and it is charged to the product, never to the
environment. The rule that makes the charge safe in the other direction is unchanged from SS-96:
**`REFUTED` requires `EXECUTED`, and only `UNRUNNABLE` routes to `ENVIRONMENT`.** Product absence can never be
charged as an environment failure because `UNRUNNABLE` carries no verdict at all; environment failure can never
be charged to the developer because `REFUTED` is unreachable without a completed observation.

### The vacuity trap, closed

V1's defect record states the trap precisely: *"the prohibition is satisfied by an absent package, but a test
that imports that package cannot be collected and is read as red."* A `MUST_NOT_HOLD` contract over a subject
that does not exist must **not** return a vacuous `SATISFIED`.

**Rule.** Subject existence is an explicit **precondition** of every `MUST_NOT_HOLD` probe. When the precondition
fails, the probe returns `EXECUTED` + `INDETERMINATE(PRECONDITION_ABSENT)`. At StoryAdmission for an
`INTRODUCE` role that is the expected pre-state and yields `READY`; at the candidate it is a product failure,
because a negative invariant cannot be established over a subject that was supposed to exist.

That single rule is the whole of PLAN-V2.1-DEFECT-001, answered without reference to any file.

---

## 5. Engineering test adequacy replaces universal hard TDD — ACCEPTED, with one added mechanism

**Accepted.** RED-at-parent chronology ceases to be a universal delivery blocker.

This closes something the draft left half-done. Corrections §1–§2 move *product* parent state to harness probes;
RED-at-parent was the **remaining** reason to execute a developer-authored artefact at the parent revision.
Removing it yields a clean invariant, which I propose adding to §18:

> **IX · NO DEVELOPER ARTEFACT IS EXECUTED AT THE PARENT REVISION.**
> Parent state is observed only by harness-owned probes. No verdict, product or process, may depend on whether
> a developer-authored file exists, imports, or collects at the parent.

### The gate

```python
@dataclass(frozen=True)
class EngineeringTestAdequacy:
    tests_execute_at_candidate: bool
    tests_pass: bool
    relevance: RelevanceResult        # mechanical; see below
    vacuity: VacuityResult            # see the added mechanism
    regressions_green: bool
    sensitivity: SensitivityResult | None   # optional; deferred from cycle 1
```

**Qualification on "relevant to changed behaviour".** As written this is prose, and prose in a control position
violates invariant VII. It needs a mechanical definition. I propose:

> `relevance` holds when the story's tests cover at least one changed line **and** at least one changed branch of
> the story's own diff, measured by coverage intersection against the diff hunks.

Coverage intersection is cheap, deterministic and already available. It is weaker than sensitivity but it is not
prose.

### The added mechanism: the vacuity control moves to the candidate

**This is my own addition and it is offered for review, not assumed.**

Dropping RED-at-parent removes a real signal. V1's `FAM-EVIDENCE-SEMANTICS` (SS-81) is precisely "a control can
PASS on tests that never executed at the parent SHA" — the nop control existed to catch tests that would pass
against an empty implementation. Deferring mutation sensitivity out of cycle 1 (§12) would leave that unguarded.

**Proposal: run the vacuity control at the candidate instead of the parent.** Take the candidate, neutralise the
story's own product hunks in a scratch copy, leave the developer's test files intact, and run those tests. They
must fail.

Why this is not the parent problem in disguise: at the candidate the test file exists and its imports exist,
because the developer wrote both. Collection semantics are therefore stable, and the outcome depends on the
*product* hunks, which is the question we actually want answered. The same information as RED, obtained without
any dependence on parent-side file topology.

Cost is one extra test run per story. If the board rejects this, the honest consequence must be recorded: the
SS-81 family is unguarded in cycle 1 until sensitivity testing lands.

### Migration from the current TDD policy

1. V1's `TDD` gate check is renamed `process/tdd-chronology` and becomes **recorded evidence**, not a blocker.
   Its implementation (including the SS-96 fix in `_tdd_check`) is retained unchanged; only its authority
   changes.
2. The `nop` control is repointed from the parent to the candidate, as above.
3. V1's per-criterion proof modes (`CHANGE_REQUIRED` / `PRESERVE_REQUIRED` / `NEGATIVE_INVARIANT`) map onto
   `ObligationRole` (`INTRODUCE` / `PRESERVE` / `VERIFY`) plus `Polarity` on the contract. The mapping is
   mechanical and should be generated, then `--check`ed.
4. Organisations wanting strict TDD keep it as a policy flag that gates on `process/tdd-chronology`. AISEF's
   product verdict never consults it.

---

## 6. Qualification ladder cleaned up — ACCEPTED

My Q0 contained plan admission, which runs probes, while I labelled the rung "no execution". That is the exact
error named. Corrected ladder:

| rung | contents | executes probes? | spends |
|---|---|---|---|
| **Q0 STATIC INTEGRITY** | schemas; provenance; catalogs (bidirectional fail-closed); static traceability; ownership graph incl. unique INTRODUCE; no-prose-control walker; **checker calibration fixtures**; StaticPlanAdmission rules | **no** | nothing |
| **Q1 SEMANTIC CONFORMANCE** | `ProductProofSpec` semantics; **StoryAdmission engine**; independent policy model (must not import the kernel's decision modules — keep V1's AST check); adversarial micro-workloads; **test-layout invariance**; **critical projection reference model** (§9) | yes, on fixtures | nothing |
| **Q2 ADEQUACY** | product mutation; **probe calibration**; engineering-test sensitivity | yes | nothing |
| **Q3 FAULT INJECTION** | named provider faults; tool/sandbox/environment faults; interruption and repair idempotence; disposal failures asserted against the OS | yes | nothing |
| **Q4 DIFFERENTIAL AT SCALE** | 100k traces vs the reference model | model-level | nothing |
| **Q5 REAL EXECUTION REPRODUCTION** | only the model stream replayed; tools re-executed and diffed; header-class pinning; `assertConsumed` | yes | nothing |
| **Q6 LIVE DELIVERY** | real provider, real money | yes | **real** |

**StaticPlanAdmission and StoryAdmission are runtime gates, not rungs.** Their *rules* are checked in Q0 and
their *engine* is qualified in Q1. A qualification run exercises them; the ladder qualifies them.

**Test-layout invariance** is new and it is ARCH-LESSON-001 made executable: a Q1 conformance suite that takes a
fixture story, permutes where the developer's tests live (same directory, separate directory, module-level
import vs function-level, no test file at all), and asserts **every product verdict is identical**. This is the
scenario-B answer, and it is the cheapest possible regression guard for the defect that ended V1.

---

## 7. Sealed evaluation cohort replaces consumed-once holdout — ACCEPTED

Consumed-once cannot express "three preregistered runs, ≥2/3", which is the protocol an honest claim needs. A
sample of one is not a claim.

```
SEALED ──► EVALUATING ──► EXPOSED ──► DEVELOPMENT
```

**Preregistration**, written and hashed **before** any run, freezes: kernel identity; workload identity;
requirements; plan policy; execution profile (content-addressed, §10); prompts; model route; run count;
thresholds; oracle; metrics.

```python
@dataclass(frozen=True)
class EvaluationCohort:
    id: str
    state: CohortState
    preregistration_hash: str
    frozen_inputs: Mapping[str, str]     # name -> content hash
    planned_runs: int
    threshold: str                       # e.g. ">=2/3 delivery complete"
    runs_completed: tuple[str, ...]
    results_read_at: float | None
    exposed_reason: str | None
```

**Rules.**

1. Running the preregistered repetitions does **not** demote. `SEALED → EVALUATING` on the first run;
   `EVALUATING` persists until `runs_completed == planned_runs`.
2. No framework modification is permitted between runs of a cohort. A change to any `frozen_inputs` hash during
   `EVALUATING` invalidates the cohort's completed runs and requires a fresh preregistration.
3. **Mechanised demotion.** Reading results sets `results_read_at`. Any change to a `frozen_inputs` hash **after**
   `results_read_at` transitions the cohort to `EXPOSED` automatically, with `exposed_reason` recorded. That is
   the operational definition of "inspected results and then modified the system", and it needs no one to
   remember it.
4. `EXPOSED` workloads may still be run and are useful for regression; they may never back a generalization
   claim. `EXPOSED → DEVELOPMENT` is a labelling step only.
5. **Generalization requires multiple independently sealed workloads and must state its sample size**, per
   workload and in total. A single cohort of three runs supports a claim about that workload only.

**LedgerLock is `DEVELOPMENT`, permanently.** Its plan was revised in response to run outcomes (PLAN-V2 →
PLAN-V2.1) and its ownership audit was performed with knowledge of observed model behaviour. No re-labelling is
available, and none should be sought.

---

## 8. Story transaction journal ownership fixed — ACCEPTED

The draft had the journal writer owned by the `StoryScope` whose teardown it must record. That is circular and
would have failed at implementation.

**RunScope** owns: `JournalWriter`, the run-level lease, run identity, the terminal sink (below).
**StoryScope** owns: worktree, sandbox, process ranges, provider/agent sessions, tool grants, scratch,
reviewer/security scopes. A `StoryScope` **emits through the RunScope journal** and owns no writer.

**Ordering rule.** The `JournalWriter` is acquired first in `RunScope` and released last. `RunScope` disposal may
not begin until every `StoryScope` has reported a terminal disposal outcome; a `StoryScope` that cannot report
one is recorded as a typed residual and `RunScope` disposal proceeds.

### What records RunScope's own teardown failure

The regress is real and has a bounded answer, not an infinite one.

1. **`run/dispose-begin`** is written to the journal before RunScope teardown starts. A journal that ends with
   `dispose-begin` and no `run/end` is, by itself, evidence that teardown did not complete.
2. **A terminal sink** — a separate, tiny, append-only, fsync'd file owned by `RunScope` and written with the
   minimum possible machinery (open, write, fsync, close; no projections, no validation, no compression). It
   receives exactly two kinds of record: `terminal/ok` and `terminal/failure{stage, error}`. It is the only
   thing that can record a `JournalWriter` failure, because it shares none of its code.
3. **Next-run preflight** is required to scan for runs whose journal lacks `run/end` and whose terminal sink is
   absent or reports failure, and to report them as `TORN` with the surviving residuals named.

**Residual, stated not argued away:** if both the journal write and the terminal-sink write fail (a full disk, a
revoked mount), nothing in-process records it. Detection then rests entirely on (3). This is the same class as
the hard-kill residual and is recorded as such.

---

## 9. Projection assurance strengthened — ACCEPTED

The from-scratch fold oracle detects `incremental != full replay`. It cannot detect
`incremental == full == consistently wrong`. My §20 recorded that as unmitigated; this closes it for the
projections that matter.

**Control-critical projections** (exactly six, and the list is frozen):

1. story state, 2. failure owner, 3. budgets, 4. retry target, 5. terminal state, 6. qualification counters.

Each gets, in **Q1**, an **independent small reference model** implementing the owner's policy, subject to V1's
hard-won rule: *the reference model must implement the approved owner policy, not mirror the implementation*,
and must be mechanically prevented from importing the projection module (V1 enforced the analogous constraint
with an AST check; keep it). Each is additionally **mutation-tested** — projections are pure functions, which
makes them directly mutation-testable, something side counters never were — and **calibrated**: each must have
been observed producing the opposite answer on a known input.

**Non-control reporting projections are not duplicated.** Cost note: this is cheaper than it looks, because V1
already carries a conformance reference model for gate semantics; this extends its scope rather than creating a
second apparatus.

**Residual:** reference model and projection wrong in the same way. Mitigated only by independent authorship and
the no-import rule; recorded, not claimed solved.

---

## 10. Capability identity is content-addressed — ACCEPTED, with an attestation boundary

"A version label is metadata, not proof of identity" is correct, and SS-65 (P1, `INV-N.DEFAULT-CAPABILITY`) is
the measured V1 instance: a managed image whose *contents* decided whether bandit existed, pinned by digest
(`aisef-verify-python:84adf1d8eaf9`, `sha256:37c5e07a…`).

`RunSpec` binds, where practical: implementation digest; package/binary identity; container/image digest; probe
implementation identity; resolved enforcement level; relevant environment/toolchain identity.

**Qualification — the attestation boundary.** Some capability identities **cannot** be content-addressed from
our side. A hosted model behind an API is the obvious case: we can record the route and the declared model id,
but we cannot digest the weights. Claiming otherwise would be a false identity, which is worse than an honest
weak one.

```python
class IdentityGrade(Enum):
    VERIFIED  = "VERIFIED"    # digest computed locally over the artefact we execute
    ATTESTED  = "ATTESTED"    # remote self-report plus a locally measured fingerprint
```

Rules: every capability entry carries a grade; a `RunSpec` carries the **minimum** grade across its
capabilities; **a qualification verdict must state the grade of its capabilities**, and two runs are comparable
only at the same grade. For `ATTESTED` capabilities the preflight response fingerprint (declared model id,
declared limits, tool-calling behaviour) is recorded so that *detectable* drift is detected.

This is the honest answer to adversarial scenario H, and it follows the same principle as the harness's
`partial` sandbox enforcement: declare the real strength, do not claim the nominal one.

---

## 11. Human semantic gate — ACCEPTED

My §20 recorded "a Behavior Contract faithful to a wrong requirement" as an irreducible residual with no
mechanism. This converts it into a named gate, which is strictly better.

```python
@dataclass(frozen=True)
class ContractApproval:
    requirement_id: str
    requirement_hash: str
    contract_id: str
    contract_hash: str
    approver: str          # a human identity
    approved_at: float
    model_reviews: tuple[str, ...]   # journal refs to model-produced adversarial reviews — advisory only
```

**Models may** propose contracts, adversarially review them, and identify ambiguity in a requirement. **Models
do not own authority.** A `ProductProofSpec` may not be compiled from a contract lacking a valid
`ContractApproval`, and the approval binds the **exact hashes** of both the requirement and the contract, so any
edit to either invalidates it. This is invariant I (Requirement Authority) given an enforcement mechanism, and
it is consistent with invariant VIII: a model's review is context and advice, never evidence of correctness.

---

## 12. Revised cycle-1 scope

The discipline is preserved: **a measured V1 defect, or defer.**

### Effect of each correction on cycle 1

| § | Effect on cycle-1 scope | Note |
|---|---|---|
| 1 Split planes | **Modifies** changes 1 and 2 | Re-factoring, no new component |
| 2 Two-stage admission | **Modifies** change 2 | Removes an impossible requirement; net simpler |
| 3 PRE_SATISFIED | **Modifies** change 2 | Dispositions only; no new component |
| 4 Two axes | **Modifies** changes 1 and 3 | Type change; `UNRESOLVABLE` deleted |
| 5 Test adequacy | **Modifies** change 1; **adds** the candidate-side vacuity control | Sensitivity testing **DEFERRED** |
| 6 Ladder cleanup | **Adds no implementation scope** | Ordering and naming |
| 7 Sealed cohort | **Adds no cycle-1 scope** — **DEFERRED** | No sealed workload exists; record the lifecycle now |
| 8 Journal ownership | **Modifies** changes 3 and 4; **adds** the terminal sink | Sink is ~50 lines and records a failure we currently cannot |
| 9 Projection reference model | **Modifies** change 3 | Six projections, bounded; extends V1's existing model |
| 10 Content-addressed identity | **Modifies** change 4 | Image + probe digests in cycle 1 (SS-65); toolchain identity **DEFERRED** |
| 11 Human semantic gate | **Adds** an approval record | Cheap; no engine |
| 12–14 | Documentation | This pass |

### The six cycle-1 changes, restated

| # | Change | Measured defect |
|---|---|---|
| 1 | Behavior Contract + **ProductProofSpec** + harness-owned probes with the **two-axis** outcome; `UNRESOLVABLE` removed; `MUST_NOT_HOLD` precondition rule | PLAN-V2.1-DEFECT-001; SS-92; SS-96 |
| 2 | **StaticPlanAdmission** (Q0) + **StoryAdmission** (runtime) with `PRE_SATISFIED` / `PLAN_DRIFT` | `AC-STORY-04-01-2` (PLAN_OVERLAP); `AC-STORY-01-01-4/-5` (PLAN_PRECONDITION_MISSING) |
| 3 | Append-only journal + projections + from-scratch oracle + **reference model for the six control-critical projections** | SS-64; SS-77; SS-81 |
| 4 | Story Transaction with **RunScope-owned journal**, terminal sink, ordered disposal, measured range emptiness, **image + probe digests in RunSpec** | D-024/025/027; SS-65 |
| 5 | Invariants armed in every test and uncontainable | SS-96 and the A5 class |
| 6 | Q0 static integrity + Q1 **test-layout invariance** + local fault injection (Q3) | PLAN-V2.1-DEFECT-001; FAM-PROVIDER |

Plus two small additions: the **candidate-side vacuity control** (§5, pending board acceptance) and the
**ContractApproval record** (§11).

**Deferred, explicitly:** engineering-test sensitivity testing; sealed-cohort machinery; toolchain identity;
behaviour-aware parallel scheduling (unchanged from the previous pass).

---

## 15. Adversarial checks

Deterministic answers, each traced to the mechanism that produces it.

**A · Upstream story implements downstream behaviour early.**
Downstream StoryAdmission measures `EXECUTED/SATISFIED` on an `INTRODUCE` obligation → `PRE_SATISFIED` +
`PLAN_DRIFT`, attributed via the dependency DAG to the completed story that introduced it. The story proceeds on
its remaining obligations; if none remain, `STORY_ALREADY_SATISFIED` with independent verification at the
candidate. No developer budget consumed, no correct code made wrong, delivery unaffected, plan quality recorded.

**B · Developer moves tests between files.**
No product verdict changes. Invariant IX: no developer artefact executes at the parent, and product verdicts
come from harness probes whose `probe_input` names the subject, not a file. Q1's **test-layout invariance**
suite asserts this by permuting layouts over a fixture story. `EngineeringTestAdequacy.relevance` may change
(coverage intersection is layout-sensitive in principle), and that is a **process** outcome that can never alter
a product verdict.

**C · Product surface does not yet exist.**
The probe's observation harness runs; the subject is absent. `EXECUTED` + `REFUTED` for `MUST_HOLD`.
`EXECUTED` + `INDETERMINATE(PRECONDITION_ABSENT)` for `MUST_NOT_HOLD` — never a vacuous `SATISFIED`. Never
`UNRUNNABLE`, never charged to `ENVIRONMENT`. At StoryAdmission with role `INTRODUCE`, both are the expected
pre-state → `READY`.

**D · Probe implementation missing.**
Caught **statically** in Q0 (StaticPlanAdmission check 6: every `probe_id` resolves and its digest matches), so
the plan never freezes. If it somehow reaches runtime, StoryAdmission returns `PROBE_INVALID`, owner
`PLAN`/`INTEGRATION`, and **no model call occurs**. Never a developer failure.

**E · Probe always returns SATISFIED.**
Three independent catches. (i) **Calibration** — each `ProductProofSpec` requires a record of its probe
observed `REFUTED` at a known revision; a probe never observed refuting makes its specs inadmissible in Q0.
(ii) **Product mutation** in Q2 — a mutant that breaks the behaviour must be refuted by the covering probe;
otherwise the survivor names the too-weak contract. (iii) `INTRODUCE` obligations produce a refuting observation
at StoryAdmission as a by-product, so a lying probe is contradicted by ordinary operation.

**F · BehaviorContract wrong but internally consistent.**
Not machine-detectable, by construction. The named control is the **human semantic gate** (§11): approval binds
exact requirement and contract hashes; models may adversarially review but hold no authority. Recorded as the
irreducible residual; the architecture claims no coverage it does not have.

**G · Projection consistently wrong in both folds.**
For the six control-critical projections: an **independent reference model** in Q1, authored against the owner's
policy, mechanically barred from importing the projection, plus mutation and calibration (§9). Residual: both
wrong in the same way — recorded, not claimed solved. Non-control projections carry no such guarantee and must
not be cited as evidence.

**H · Provider implementation changes, version string unchanged.**
`IdentityGrade` (§10). Local capabilities are `VERIFIED` by digest, so the change is caught. A hosted model is
`ATTESTED`: the preflight fingerprint (declared model id, limits, tool-calling behaviour) is recorded and
*detectable* drift is detected; undetectable drift is a stated residual. Comparability is restricted to the same
grade, and a verdict must state its grade. Within a cohort, any change to a frozen identity hash invalidates
completed runs (§7 rule 2).

**I · Three preregistered holdout runs produce different results.**
This is the expected case. The **preregistered threshold decides** (e.g. ≥2/3), and variance is reported as part
of the result. Adjusting the threshold after seeing results sets `results_read_at`-triggered `EXPOSED` (§7
rule 3) and forfeits the claim. The verdict states *n* and the observed distribution, never a single headline.

**J · StoryScope teardown fails while writing teardown evidence.**
The writer is owned by `RunScope` and is still alive (§8) — this is precisely the circularity the correction
removed. If the journal write itself fails, the **terminal sink** records it. If that also fails, the journal
ends at `run/dispose-begin` with no `run/end`, and the **next run's preflight** reports the run `TORN` with
residuals named. The chain is finite and the final residual is stated.

**K · Story is 100% PRE_SATISFIED.**
`STORY_ALREADY_SATISFIED`. Every obligation independently verified at the candidate; developer call skipped;
no developer budget; `PLAN_DRIFT` recorded for each obligation; the story counts as delivery-complete for the
**product** and as non-productive in the **plan-quality** metric. The two planes of §1 make this expressible
without contradiction — V1 could only express it as a stop.

**L · Same ProductProofSpec is INTRODUCE in one plan and PRESERVE in another.**
Legal and expected. A `ProductProofSpec` is a product fact; the role is a plan fact (§1). Within one plan
`INTRODUCE` ownership must be unique (Q0 check 3); across plans there is no constraint. The product verdict is
identical in both; only the plan disposition and the parent expectation differ. Verdict records cite both
`semantic_hash` and `plan_hash`, so evidence from the first plan remains valid under the second.

---

## Unresolved risks after this pass

1. **A contract faithful to a wrong requirement** — mitigated by a human gate, not solved (F).
2. **Reference model and projection wrong identically** — mitigated by independent authorship, not solved (G).
3. **Undetectable remote capability drift** — bounded by `ATTESTED` grading, not solved (H).
4. **Journal and terminal sink both failing** — detected only by the next run's preflight (J).
5. **Hard-killed harness leaves orphans** — unchanged from the previous pass; detection, not prevention.
6. **Ownership assignment remains the hard part.** Typed ownership is only as good as the rule that assigns an
   owner, and V1 showed assignment is where the difficulty lives. No external pattern helps.
7. **`PARTIAL` enforcement and `ATTESTED` identity are invitations.** Both are honest grades; both, under
   schedule pressure, will be used, and comparability quietly narrows. The guard is that verdicts must state
   their grade — a documentation guard, which is the weakest kind.
8. **Plan drift has no threshold yet.** `PLAN_DRIFT` is now recorded rather than fatal (§3), which is correct,
   but a plan can now be substantially wrong while every story succeeds. A drift budget needs defining before
   plan quality can be qualified — this is a new open question created by correction §3, and it should be
   answered in the RFC.
