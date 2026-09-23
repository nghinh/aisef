# AISEF V2 — Architecture RFC

**Status: APPROVED — FROZEN.** Owner decision *AISEF V2 — OWNER ARCHITECTURE FREEZE* (2026-09-21), reviewing
commit `2fe672c`. **F1–F11 are frozen.** This document is the architecture baseline for Cycle-1 implementation.
The immutable approval record is
[`closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json`](../../closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json),
content-addressed by its `.sha256` sidecar.

**Amended by `ARCHITECTURE-EXCEPTION-V2-001`** (owner decision *AISEF V2 — P1 OWNER REVIEW CORRECTION*,
2026-09-21): F2 owner routing is keyed by measurement point (§10.3). The original approval record is unchanged; the
approval lineage is
[`closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-001.json`](../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-001.json).

**Amended by `ARCHITECTURE-EXCEPTION-V2-002`** (owner decision *AISEF V2 — P2 OWNER REVIEW CORRECTION*,
2026-09-22): F5 distinguishes a harness timeout from a subject observation deadline (§9.2). Approval lineage:
[`closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-002.json`](../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-002.json).

**Supersedes** the proposal documents under [`docs/research/v2/`](../research/v2/) for all implementation
decisions; those are retained as design history and are linked throughout.

**Not implemented.** No V2 code exists. No file under `aisef/` is modified by this RFC.

> **Change rule after freeze.** An implementation bug is fixed in the implementation. A missing test is added. A
> missing verifier already required by this RFC is added. **A contradiction in a frozen semantic is a STOP.**
> F1–F11 **MUST NOT** be modified silently; any change requires an `ARCHITECTURE_EXCEPTION` record naming the
> frozen item, the contradiction, a concrete reproducer, why the implementation cannot conform, the evidence
> compatibility impact, a proposed replacement, and owner approval. **No architecture exception is approved by
> default.**
>
> **Non-normative preamble.** Everything above the heading *1. Executive architecture decision* is status
> metadata. The normative body is digested separately (`rfc_normative_digest`) so that recording approval
> provably changes no normative content.

Normative language: **MUST**, **MUST NOT**, **SHOULD**, **MAY**. A statement without one of these is
explanatory.

**Design history.**
[External study](../research/v2/DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md) ·
[Cordis study](../research/v2/CORDIS-ARCHITECTURE-STUDY.md) ·
[V1 defect families](../research/v2/V1-DEFECT-FAMILY-REGISTER.md) ·
[defects vs patterns](../research/v2/AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md) ·
[adopt/adapt/reject matrix](../research/v2/AISEF-V2-EXTERNAL-ARCHITECTURE-MATRIX.md) ·
[board resolution](../research/v2/AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md) ·
[meta-model](../research/v2/AISEF-V2-NORMALIZED-METAMODEL.md) ·
[control flow](../research/v2/AISEF-V2-END-TO-END-CONTROL-FLOW.md) ·
[RFC readiness](../research/v2/AISEF-V2-RFC-READINESS.md)

---

## 1. Executive architecture decision

AISEF V2 separates **four planes** that V1 conflated, and that conflation is the direct cause of the two defects
that ended V1's delivery qualification.

1. **Requirement plane** — human authority. Prose, never read by control.
2. **Product plane** — durable facts about the product: `BehaviorContract` → `ProductProofSpec`, evaluated by
   harness-owned probes. Survives every re-plan.
3. **Planning plane** — story ownership and parent expectations: `PlanObligation`. Revising a plan MUST NOT
   invalidate product evidence.
4. **Record plane** — an append-only journal that is the sole authority for run state, with every read model a
   pure fold.

Three consequences define the system:

- **Developer tests no longer decide product correctness.** Harness-owned probes do. Developer tests become
  engineering-quality evidence, gated by `EngineeringTestAdequacy`.
- **No developer-authored artefact is executed at the parent revision** (invariant IX). This is what makes
  `PLAN-V2.1-DEFECT-001` unrepeatable.
- **Execution status and behaviour verdict are separate axes.** A missing module is a completed observation that
  the behaviour is absent, not an environment failure.

V2 is event-sourced for **state** and explicitly **not** event-driven for **control**. Writing an event MUST NOT
affect control flow; no subscriber may change a decision by existing.

---

## 2. V1 failure model and goals

V1's assurance kernel was **QUALIFIED** (candidate `f52df75ff242`, product tree `4359f347`, 100 000/100 000
differential traces matched with 0 unexplained divergences, mutation 862/871 killed plus 9 audited equivalents,
fault matrix 102/102, suite 3702). W1 delivery qualification was **NOT REACHED and not reachable from that
workload**.

The 22 named defect families are in [`V1-DEFECT-FAMILY-REGISTER.md`](../research/v2/V1-DEFECT-FAMILY-REGISTER.md).
Two ended delivery qualification:

- **`FAM-PROOF-PLACEMENT`** — `PLAN-V2.1-DEFECT-001`. A criterion's parent state was read from the criterion's
  *tests*, and whether a test collects at the parent is a property of its *file*. The same frozen criterion
  measured GREEN when its test file did not import the product and RED when it did — twice, five hours apart, on
  identical plan text. Recorded as **ARCH-LESSON-001**: *proof obligation semantics must be independent of
  developer-chosen test file placement.*
- **`FAM-PLAN-OWNERSHIP`** — `PLAN_OVERLAP` (run 1 of PLAN-V2 stopped at 10/16 on a behaviour already green at
  the story's parent) and `PLAN_PRECONDITION_MISSING` (V2.1 run 1, 0/16).

And one crossing defect that shaped the outcome model: **SS-96** (P1) — a check reported `FAILED` for evidence
that did not execute, routing an environment failure into the developer's quality budget. It produced
`INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE`.

**Goals.** (G1) Make those three defect shapes unexpressible. (G2) Make product evidence survive re-planning.
(G3) Make every failure carry a typed owner and a retryability decided once in the taxonomy. (G4) Make
qualification cheap before it is expensive. (G5) Preserve everything V1 got right.

---

## 3. Non-goals

V2 **MUST NOT** pursue any of the following. Each was evaluated and rejected with reasons in the
[matrix](../research/v2/AISEF-V2-EXTERNAL-ARCHITECTURE-MATRIX.md) and
[recommendation](../research/v2/AISEF-V2-ARCHITECTURE-RECOMMENDATION.md) §8–§9.

- A plugin architecture for the kernel. Capability *implementations* may be substitutable; the **decision** MUST
  NOT be.
- Dynamic plugin discovery, runtime hot replacement, or dynamic configuration mutation during a run.
- A Cordis runtime dependency or any third-party framework in the kernel.
- A TypeScript rewrite. No measured defect is attributable to Python, and a rewrite discards the 100k traces,
  871 mutants and 102 fault cells bound to the current tree.
- Model-visible session architecture as evidence. Introspection output is context, never evidence.
- Interactive-agent affordances (approval prompts, human-driven resume, PTY semantics) inside a run.
- Behaviour-aware parallel scheduling in cycle 1 — deferred; it cites no measured defect and amplifies
  `FAM-SCHEDULER`.
- Distributed or multi-writer journals. Dense `seq` requires a single writer per run.
- A 100% line-coverage gate. Mutation adequacy is the stronger standard and is retained.

---

## 4. Top-level invariants

Nine. Each **MUST** have an enforcement mechanism; an invariant without one is a documented intention, not an
invariant. All nine **MUST** be armed in-process during every test run and **MUST** be uncontainable: every
`except` boundary in the kernel MUST re-raise an invariant violation.

| # | Invariant | Mechanism |
|---|---|---|
| **I** | **Requirement Authority.** Only frozen requirements and approved behaviour contracts define product truth. Authority derives from where an artefact was admitted, never from what it claims about itself. | `ContractApproval` binding both hashes (§6); Q0 static check that no kernel module reads `Requirement.text` |
| **II** | **Semantic Determinism.** Proof verdicts MUST NOT depend on developer-controlled test topology, on which components are loaded, on wall-clock ordering, or on incidental environment state. | Harness-owned probes; no control on an event bus; `seq` not `time`; deterministic child environment; `runspec_hash` |
| **III** | **Independent Evidence.** The actor producing code MUST NOT define the evidence that certifies the behaviour it implemented. | `VerifiedProof` in a verifier scope; confinement derived from the scope, never a passable parameter |
| **IV** | **Typed Ownership.** PLAN, DEVELOPER, ENVIRONMENT, PROVIDER, REVIEW, SECURITY and INTEGRATION MUST NOT consume each other's retry budgets. Retryability and budget target are properties of the typed outcome, fixed in the taxonomy. | `failure/observed` carries `owner` and `retryable`; the retry engine reads only those two fields |
| **V** | **Reproducible Qualification.** Same kernel + workload + plan + execution profile MUST yield comparable evidence. Comparability requires the same capability identity tuple, the same `IdentityGrade`, and the same enforcement identity. | `capability/resolved` events; `runspec_hash` (§23); request-header class pinning |
| **VI** | **Immutable Provenance.** Every decision MUST resolve to immutable identities for parent, candidate, proof spec, profile and kernel. Identities are content hashes or full SHAs, never names or abbreviations. | Journal has no update or delete verb; commit-time provenance guard; `semantic_hash` on every verdict |
| **VII** | **No Prose As Control State.** No value from outside the AISEF taxonomy may become a control code — whether from a model, a tool, an SDK or a configuration file. | Foreign codes flatten to `UNKNOWN`; Q0 walker rejects expressions outside declared interpolation positions |
| **VIII** | **Memory Is Context, Never Evidence.** Anything an agent reads about the harness is context. Only harness-produced records are evidence. | Evidence fields accept only harness-produced typed records; violation is `invariant/violated` |
| **IX** | **No Developer Artefact Is Executed At The Parent Revision.** No verdict, product or process, may depend on whether a developer-authored file exists, imports or collects at the parent. | Probe API accepts no developer-authored path; candidate-side vacuity control (§15); Q1 test-layout invariance suite |

---

## 5. Planes and normalized meta-model

```
REQUIREMENT   Requirement ── ContractApproval ── BehaviorContract
                                                      │ compile (pure, --check'd)
PRODUCT                                      ProductProofSpec ◄── Probe
                                                      │ referenced by
PLANNING       Plan ── PlanObligation ────────────────┘
                        │
ADMISSION      StaticPlanAdmissionEngine → StaticPlanAdmissionResult   (plan time, no probes)
                        │
               StoryAdmission                                          (run time, probes, exact parent SHA)
                        │
EXECUTION      StoryTransaction ── DeveloperTests ── CandidateProof ── VerifiedProof
                        │
RECORD                Journal ──► Projection ──► QualificationEvidence
                        ▲
                     RunSpec
```

Object-by-object authorship, approval, freeze points, identities and edit rights are normative and are given in
[`AISEF-V2-NORMALIZED-METAMODEL.md`](../research/v2/AISEF-V2-NORMALIZED-METAMODEL.md) §2. Two rules from it are
restated here because everything else depends on them:

- **A product fact MUST NOT carry a plan fact.** `ProductProofSpec` holds no story id and no parent expectation.
- **`DeveloperTests` is the only object a model or developer may author, and it decides nothing about product
  correctness.** That is invariant III as a property of the table rather than a rule someone follows.

### 5.1 The four cited identities

Every product verdict **MUST** cite exactly four:

| identity | answers | changes when |
|---|---|---|
| `semantic_hash` | what was proved | the contract's semantics, the probe, or its input change |
| `plan_hash` | why this story was asked to prove it | the plan is revised — **never** invalidates product evidence |
| `parent_sha` / `candidate_sha` | about which revision | the code moves |
| `runspec_hash` | under which resolved capabilities | any capability identity, grade or enforcement level changes |

---

## 6. Requirement authority and ContractApproval

```python
@dataclass(frozen=True)
class Requirement:
    id: str
    text: str            # prose; MUST NOT be read by any control path
    source: str          # approved document + content hash
    requirement_hash: str
```

```python
@dataclass(frozen=True)
class ContractApproval:
    requirement_id: str
    requirement_hash: str
    contract_id: str
    contract_hash: str
    approver: str                     # a human identity
    approved_at: float
    model_reviews: tuple[str, ...]    # journal refs to model adversarial reviews — advisory only
```

- A `ProductProofSpec` **MUST NOT** be compiled from a contract lacking a valid `ContractApproval`.
- The approval **MUST** bind the exact hashes of both objects; any edit to either invalidates it.
- Models **MAY** propose contracts, adversarially review them, and identify ambiguity. Models **MUST NOT** hold
  approval authority.

**Why a human gate.** A contract can faithfully encode a wrong reading of a requirement, and nothing below it
can detect that. This residual is irreducible (§34) and the gate is its only control.

---

## 7. BehaviorContract

```python
class Polarity(Enum):
    MUST_HOLD     = "MUST_HOLD"
    MUST_NOT_HOLD = "MUST_NOT_HOLD"

@dataclass(frozen=True)
class Subject:
    kind: Literal["python_callable", "cli_invocation", "http_route", "file_artifact", "process_effect"]
    locator: str        # resolves against a revision; names the product, never a test

class SubjectAbsence(Enum):
    """Whether the contract is decidable when its subject does not exist.

    MUST be declared explicitly. MUST NOT be inferred from polarity.
    """
    REQUIRES_SUBJECT     = "REQUIRES_SUBJECT"      # the subject must exist for the contract to be decidable
    ABSENCE_IS_DECIDABLE = "ABSENCE_IS_DECIDABLE"  # subject absence is itself a valid observation

@dataclass(frozen=True)
class BehaviorContract:
    id: str
    requirement_ids: tuple[str, ...]
    subject: Subject
    stimulus: Mapping[str, Any]
    observable: Mapping[str, Any]
    polarity: Polarity
    subject_absence: SubjectAbsence
    rationale: str      # prose, for human review; MUST NOT be read by control
    contract_hash: str
```

- A contract **MUST NOT** name a test file, test function, directory layout, or any developer-chosen artefact.
- **A story MUST NOT change the locator of a contract it implements.** Moving a subject is a contract change and
  requires re-approval and re-admission. Without this rule, `Subject.locator` re-introduces file placement.
- `subject_absence` **MUST** be declared by the contract author and **MUST** be bound into `contract_hash` and,
  through it, into `semantic_hash`. It **MUST NOT** be inferred from `polarity`: both
  *"the CLI exists but MUST NOT write to stdout"* (`REQUIRES_SUBJECT`) and *"a forbidden module MUST NOT exist"*
  (`ABSENCE_IS_DECIDABLE`) are `MUST_NOT_HOLD`, and they need opposite handling when the subject is absent. The
  same applies to positive contracts: *"file X MUST exist"* is `MUST_HOLD` with `ABSENCE_IS_DECIDABLE`.

---

## 8. ProductProofSpec

```python
@dataclass(frozen=True)
class ProductProofSpec:
    id: str                                  # "PPS-" + digest(canonical form)
    contract_id: str
    probe_id: str
    probe_digest: str                        # content-addressed; §23
    probe_input: Mapping[str, Any]
    candidate_expectation: BehaviorVerdict   # SATISFIED for MUST_HOLD, REFUTED for MUST_NOT_HOLD
    compiler_id: str
    compiler_digest: str
    semantic_hash: str
```

- `ProductProofSpec` **MUST** be derived by a pure compile of an approved `BehaviorContract`. It **MUST NOT** be
  hand-authored or edited.
- The committed spec **MUST** be verified against a fresh derivation (`--check`) in Q0. Drift fails the build.
- It **MUST NOT** contain a story id, a plan id, or any parent expectation.
- A `ProductProofSpec` **MAY** be referenced by many `PlanObligation`s, in the same plan and across plans.

---

## 9. Probe protocol

```python
class Enforcement(Enum):
    FULL = "FULL"; PARTIAL = "PARTIAL"; UNAVAILABLE = "UNAVAILABLE"

class Probe(Protocol):
    id: str
    digest: str
    def enforcement(self) -> Enforcement: ...
    def harness_preconditions(self) -> tuple[str, ...]: ...
    def evaluate(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> ProbeResult: ...
```

**The observation-harness / subject split is normative and is what keeps product absence out of the environment
budget.**

- A probe **MUST** declare its **observation harness** — what must function for it to look at all — separately
  from its **subject**, which is what it looks at.
- Failure of the observation harness — the interpreter cannot launch, a required probe tool is unavailable, the
  sandbox is unavailable, or the probe/watchdog infrastructure itself fails or times out before it obtains an
  observation — **MUST** produce `UNRUNNABLE` *(amended — V2-002)*.
- Absence of the subject **MUST NOT** produce `UNRUNNABLE`. It is an observation.
- Expiry of the subject's bounded observation window **MUST NOT** produce `UNRUNNABLE`. It is an observation
  (§9.2) *(amended — V2-002)*.
- A probe **MUST** declare its real `enforcement()` level and **MUST** refuse a request it cannot honour rather
  than degrade silently.
- Probes are harness-owned. The probe API **MUST NOT** accept a developer-authored path (invariant IX).

### 9.1 Calibration — two levels

Calibration must demonstrate **contrast to the candidate expectation**, not a fixed verdict. A probe for a
`MUST_NOT_HOLD` contract has `candidate_expectation = REFUTED`, so "must be observed producing `REFUTED`" would
*pass* a probe that always returns `REFUTED` — the exact failure calibration exists to catch (case **CAL-1**).

**General rule.** A calibration demonstration **MUST** produce the verdict that **contrasts** with the spec's
`candidate_expectation`:

| `candidate_expectation` | the counterexample MUST produce |
|---|---|
| `SATISFIED` | `REFUTED` |
| `REFUTED` | `SATISFIED` |

#### 9.1.1 `ProbeCapabilityCalibration` — qualifies an implementation

```python
@dataclass(frozen=True)
class ProbeCapabilityCalibration:
    probe_id: str
    probe_digest: str
    observation_class: str                  # the class of observation this record qualifies
    positive_fixture: str                   # committed fixture where the observable IS present  -> SATISFIED
    negative_fixture: str                   # committed fixture where the observable is ABSENT   -> REFUTED
    demonstrated_at: float
```

- Qualifies a **probe implementation at a given digest** against committed positive **and** negative fixtures
  for each observation class it supports. A probe that cannot produce **both** verdicts on those fixtures is not
  qualified for that class.
- These records exist **before any project plan is written**, because they belong to the probe, not to a
  project. `StaticPlanAdmission` **MAY** therefore require them (§12, check 9).

#### 9.1.2 `SpecFalsifiabilityEvidence` — qualifies one spec

```python
@dataclass(frozen=True)
class SpecFalsifiabilityEvidence:
    spec_id: str
    semantic_hash: str
    mechanism: Literal["controlled_product_mutation", "fixture_construction", "other_qualified"]
    counterexample_ref: str                 # journal or fixture locator
    observed: BehaviorVerdict               # MUST contrast with candidate_expectation
```

- Project- and spec-specific evidence that **this** `ProductProofSpec` can reject a controlled counterexample.
- It **MUST NOT** be a prerequisite for plan freeze.
- It **MUST** be required by Q2 before that spec may back Q6-qualified product evidence (§27, §36).

**Why the split.** The previous draft required every spec's calibration record in `StaticPlanAdmission` *before
plan freeze*, while also stating that most such records are produced by `StoryAdmission`, which only runs
*after* plan freeze. That was circular and impossible (case **CAL-2**). Probe-level calibration is available
before a plan exists; spec-level falsifiability belongs to qualification, not to admission.

### 9.2 Harness timeout vs subject observation deadline *(amended — ARCHITECTURE-EXCEPTION-V2-002)*

A timeout of the **observation harness** and a deadline reached by the **subject** are different facts.

- **Harness failure or harness timeout.** The observation mechanism itself cannot operate or cannot obtain an
  observation — the interpreter cannot launch, a required probe tool is unavailable, the sandbox is unavailable,
  the probe or watchdog infrastructure fails. ⇒ `UNRUNNABLE`, owner **`ENVIRONMENT`**, no `BehaviorVerdict`.
- **Subject observation deadline.** The harness dispatched the subject and observed it, but the subject did not
  complete or emit the expected observation within the bounded observation window the `ProductProofSpec` declares.
  ⇒ **`EXECUTED`**. The `BehaviorVerdict` **MUST** be the one the spec's observable assigns to an expired window.
- There **MUST NOT** be a global rule *subject timeout ⇒ `REFUTED`*, and **MUST NOT** be *subject timeout ⇒
  `UNRUNNABLE`*. A subject timeout **MUST NEVER** become `ENVIRONMENT` merely because a timeout occurred.
- A `ProductProofSpec` whose observable cannot assign semantics to its bounded observation window is
  `INVALID_SPEC`, and **SHOULD** be rejected as early as possible — at `StaticPlanAdmission` (§12), before any
  probe runs.
- No new `Owner`, no new architecture plane.

### 9.3 Signal provenance after dispatch *(amended — ARCHITECTURE-EXCEPTION-V2-003)*

A process that ends by a signal says **what** happened, never **who** did it. The controller knows one thing
mechanically: whether *it* sent that signal. Its own signal ledger (the owned process range, §17.1) is the single
authority; the signal number is not.

- **Before `DISPATCHED`.** The observation mechanism failed before it could observe the subject ⇒ `UNRUNNABLE`,
  owner **`ENVIRONMENT`**, no `BehaviorVerdict`. Unchanged by this amendment (§9.2).
- **After `DISPATCHED`, the controller's ledger holds the terminating signal.** The controller stopped its own
  observation: an **interruption**, not a measurement. No `ProbeResult`, no `BehaviorVerdict` and no owner **MUST**
  be produced; the operation closes through the interruption path (§20.2) — `OUTCOME_UNKNOWN` once dispatched — and
  the provenance is kept in the journal.
- **After `DISPATCHED`, the ledger does not hold it.** The harness observed that the subject's process ended by a
  signal the controller did not send ⇒ **`EXECUTED`** + `INDETERMINATE(NON_CONTROLLER_SIGNAL)`.
  - It **MUST NOT** be `UNRUNNABLE` and **MUST NOT** be `ENVIRONMENT` merely because the process exited by a signal.
  - There **MUST NOT** be a global rule *signal exit ⇒ `REFUTED`*: the evidence does not say the subject refuted the
    contract, only that the observation was spoiled.
  - The reason is named for what is known — the controller did not send it — and **MUST NOT** claim the subject sent
    it: the operating system, a resource limit or another actor are not excluded.
- One authority: a probe **MUST NOT** keep a second signal ledger, PID tree or interruption state machine.
- No new `Owner`, no new `ProbeExecutionStatus`, no new `BehaviorVerdict`, no new architecture plane.

---

## 10. Two-axis proof outcomes

```python
class ProbeExecutionStatus(Enum):
    EXECUTED     = "EXECUTED"
    UNRUNNABLE   = "UNRUNNABLE"
    INVALID_SPEC = "INVALID_SPEC"

class BehaviorVerdict(Enum):
    SATISFIED     = "SATISFIED"
    REFUTED       = "REFUTED"
    INDETERMINATE = "INDETERMINATE"   # ran; cannot decide; a reason is REQUIRED
```

`BehaviorVerdict` is defined **only** when status is `EXECUTED`. It **MUST** be represented so that it cannot
exist otherwise — the verdict lives inside the `EXECUTED` variant. Six legal states:

| status | verdict | meaning | owner on failure |
|---|---|---|---|
| EXECUTED | SATISFIED | observed present | — |
| EXECUTED | REFUTED | observed absent | DEVELOPER at candidate; a plan disposition at parent; INTEGRATION after merge (§10.3) |
| EXECUTED | INDETERMINATE | ran; cannot decide; reason required | by measurement point and, at the parent, obligation role (§10.3) — never by reason alone |
| UNRUNNABLE | — | could not look | **ENVIRONMENT** |
| INVALID_SPEC | — | not evaluable by this probe | PLAN / INTEGRATION |
| *(absent)* | — | not attempted | chargeable to no one |

**Normative routing.** `REFUTED` **MUST** require `EXECUTED`. Only `UNRUNNABLE` **MAY** route to `ENVIRONMENT`.
`UNRUNNABLE` **MUST NOT** route to `DEVELOPER`. This is `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` and it makes
SS-96 and SS-92 unexpressible in both directions.

**`UNRESOLVABLE` is deleted.** A missing module is a completed observation that the behaviour is absent.

### 10.1 ContractSatisfaction — the derived semantic that planning routes on

`BehaviorVerdict` is a statement about **the observable named in the contract**. It is *not* a statement about
whether the contract is met, because `candidate_expectation` is `SATISFIED` for `MUST_HOLD` and `REFUTED` for
`MUST_NOT_HOLD`. Routing planning decisions on the raw verdict is therefore **polarity-inverted for every
negative contract**.

```python
class ContractSatisfaction(Enum):
    SATISFIED     = "SATISFIED"
    UNSATISFIED   = "UNSATISFIED"
    INDETERMINATE = "INDETERMINATE"     # typed and reason-bearing

def contract_satisfaction(result: ProbeResult, spec: ProductProofSpec) -> ContractSatisfaction:
    if result.status is not ProbeExecutionStatus.EXECUTED:
        raise InvariantError("contract satisfaction is undefined for a probe that did not execute")
    if result.behavior_verdict is BehaviorVerdict.INDETERMINATE:
        return ContractSatisfaction.INDETERMINATE          # reason preserved
    return (ContractSatisfaction.SATISFIED
            if result.behavior_verdict == spec.candidate_expectation
            else ContractSatisfaction.UNSATISFIED)
```

- `ContractSatisfaction` **MUST** be **derived**, never separately recorded, so it cannot drift from the raw
  verdict and the spec it was computed against. The journal records `ProbeResult` and the `spec_id`; the
  satisfaction is recomputed.
- **`StoryAdmission` and every planning decision MUST route on `ContractSatisfaction`, never on raw
  `BehaviorVerdict`.**
- The derivation function is frozen under **F2**, because re-deriving old evidence under a changed mapping would
  silently re-interpret it.

### 10.2 Subject absence

Whether a contract is decidable with its subject absent is declared by `BehaviorContract.subject_absence` (§7)
and **MUST NOT** be inferred from polarity.

- **`REQUIRES_SUBJECT`** — subject absence means the contract cannot be decided. The probe **MUST** return
  `EXECUTED` + `INDETERMINATE(PRECONDITION_ABSENT)`. It **MUST NOT** return a vacuous verdict.
- **`ABSENCE_IS_DECIDABLE`** — subject absence is a valid observation. The probe **MUST** report the verdict the
  observation implies, and `ContractSatisfaction` follows §10.1 normally.

This replaces the previous blanket rule that *every* `MUST_NOT_HOLD` probe requires its subject to exist. That
rule was correct for *"the CLI exists but MUST NOT write to stdout"* and wrong for *"a forbidden file MUST NOT
exist"*, where absence is the whole point (cases **NEG-2**, **NEG-3**).

V1's defect record states the trap the `REQUIRES_SUBJECT` branch closes: *"the prohibition is satisfied by an
absent package, but a test that imports that package cannot be collected and is read as red."* AISEF's own
`AC-STORY-01-01-4/-5` were `REQUIRES_SUBJECT` prohibitions over a subject the story was to create, so they
resolve to `INDETERMINATE(PRECONDITION_ABSENT)` — decided by the contract's declaration, not by any file.

A second typed reason is named by §9.3 *(ARCHITECTURE-EXCEPTION-V2-003)*: `NON_CONTROLLER_SIGNAL` — the harness
dispatched the subject and the process then ended by a signal the controller did not send. Like
`PRECONDITION_ABSENT` it is a member of `IndeterminateReason`, never free text, and it carries explicit routing
(§10.3); it is never inferred from a signal number.

### 10.3 Owner routing by measurement point *(amended — ARCHITECTURE-EXCEPTION-V2-001, V2-003)*

The same observation means different things depending on where it is measured (§26). Owner routing **MUST** be
keyed on the typed measurement point and, at the parent, on the obligation role (§11). It **MUST NOT** be inferred
from an `INDETERMINATE` reason alone.

```python
class MeasurementPoint(Enum):
    PARENT     = "PARENT"       # StoryAdmission at the story's frozen parent (§13)
    CANDIDATE  = "CANDIDATE"    # candidate proof (§16)
    POST_MERGE = "POST_MERGE"   # post-merge proof (§26)
```

| measurement point | outcome | role | meaning | owner |
|---|---|---|---|---|
| PARENT | `INDETERMINATE(PRECONDITION_ABSENT)` | INTRODUCE | READY — the expected pre-state | — |
| PARENT | `INDETERMINATE(PRECONDITION_ABSENT)` | PRESERVE, VERIFY | PRECONDITION_BROKEN | PLAN |
| PARENT | `SATISFIED`, `UNSATISFIED` | any | a StoryAdmission disposition (§13) | — |
| CANDIDATE | `UNSATISFIED` | any admitted | the implementation does not meet the contract | DEVELOPER |
| CANDIDATE | `INDETERMINATE(PRECONDITION_ABSENT)` | any admitted | the implementation did not establish the subject the contract requires | DEVELOPER |
| POST_MERGE | `UNSATISFIED` | any | a regression after merge (§26) | INTEGRATION |
| POST_MERGE | `INDETERMINATE(PRECONDITION_ABSENT)` | any | a subject verified at the candidate is gone after merge | INTEGRATION |
| any | `INDETERMINATE(NON_CONTROLLER_SIGNAL)` | any | executed, then a signal the controller did not send: the behavioural truth cannot be derived and no cause may be invented — never retried, no budget charged, and at the parent PROBE_INVALID | INTEGRATION |
| any | probe `UNRUNNABLE` | any | the observation harness cannot run | ENVIRONMENT |

- `SATISFIED` at the candidate or after merge is not a failure.
- An `INDETERMINATE` with any other reason has no row here and **MUST** fail closed — never `DEVELOPER` by default.
  StoryAdmission's `PLAN_CONTRADICTION` / `PROBE_INVALID` routing (§13) is unchanged.
- **Why V2-001.** The previous row routed `INDETERMINATE` to "PLAN or INTEGRATION, by reason". For an `INTRODUCE`
  obligation over a `REQUIRES_SUBJECT` contract, StoryAdmission correctly returns `READY` at the parent; if the
  developer never creates the subject, the candidate probe returns `INDETERMINATE(PRECONDITION_ABSENT)` and was
  charged to `PLAN` — the admitted implementation's failure charged to the plan.

---

## 11. Planning plane and PlanObligation

```python
class ObligationRole(Enum):
    INTRODUCE = "INTRODUCE"
    PRESERVE  = "PRESERVE"
    VERIFY    = "VERIFY"

class ParentExpectation(Enum):
    """Expected ContractSatisfaction at the parent. MUST NOT encode a raw BehaviorVerdict."""
    UNSATISFIED_AT_PARENT = "UNSATISFIED_AT_PARENT"
    SATISFIED_AT_PARENT   = "SATISFIED_AT_PARENT"
    UNCONSTRAINED         = "UNCONSTRAINED"

@dataclass(frozen=True)
class PlanObligation:
    criterion_id: str
    product_proof_spec_id: str
    story_id: str
    role: ObligationRole
    expected_parent: ParentExpectation
    depends_on: tuple[str, ...]
    ownership_rationale: str          # prose; MUST NOT be read by control

@dataclass(frozen=True)
class Plan:
    id: str
    baseline: str                     # full SHA
    obligations: tuple[PlanObligation, ...]
    plan_quality_policy: PlanQualityPolicy      # §29
    plan_hash: str
```

- **`INTRODUCE` ownership MUST be unique per `ProductProofSpec` within a plan.**
- `PRESERVE` and `VERIFY` references **MAY** be many.
- Across plans there is **no** constraint: the same spec **MAY** be `INTRODUCE` in one plan and `PRESERVE` in
  another. The product verdict is identical in both; only the plan disposition differs.

---

## 12. StaticPlanAdmission

**The engine and the result are distinct objects and MUST NOT be conflated.**

- **`StaticPlanAdmissionEngine`** — harness code. Its rules are checked in Q0 and its behaviour is qualified in
  Q1. Q0 and Q1 **MUST NOT** execute any project's admission.
- **`StaticPlanAdmissionResult`** — produced when a concrete project executes the engine at **plan time**,
  before plan freeze.

```python
@dataclass(frozen=True)
class StaticPlanAdmissionResult:
    plan_id: str
    engine_digest: str
    checks: tuple[CheckResult, ...]
    admitted: bool
    result_digest: str
```

The engine **MUST** execute no probes and **MUST NOT** invent a future story's parent SHA. Checks:

1. requirement coverage — every approved `Requirement` maps to ≥1 `BehaviorContract`;
2. contract → spec integrity (`--check` against the committed derivation);
3. ownership — every criterion has exactly one story; `INTRODUCE` uniqueness per spec;
4. dependency DAG acyclic; every `depends_on` resolves;
5. contradictions — no incompatible parent expectations for the same spec in one story; no `PRESERVE` ordered
   before its `INTRODUCE`;
6. **proof-capability availability** — every `probe_id` resolves and its `probe_digest` matches;
7. schema and traceability — every criterion reaches a `Requirement` through an approved contract;
8. plan structure — an explicit order or DAG; no orphan obligations;
9. **`ProbeCapabilityCalibration`** exists and is valid for every referenced probe digest, for the observation
   class each spec uses (§9.1.1).

`SpecFalsifiabilityEvidence` (§9.1.2) **MUST NOT** be a plan-freeze prerequisite. It is produced by
qualification, not by admission, and requiring it here would demand an artefact that `StoryAdmission` — which
runs only after plan freeze — would have to supply (case **CAL-2**).

A plan **MUST NOT** freeze unless `admitted` is true.

---

## 13. StoryAdmission

Runs immediately before each story, against that story's **exact frozen parent SHA**. This is a **runtime
gate**, not a ladder rung.

```python
class StoryAdmissionDisposition(Enum):
    READY               = "READY"
    PRE_SATISFIED       = "PRE_SATISFIED"
    PRECONDITION_BROKEN = "PRECONDITION_BROKEN"
    PLAN_CONTRADICTION  = "PLAN_CONTRADICTION"
    PROBE_UNRUNNABLE    = "PROBE_UNRUNNABLE"
    PROBE_INVALID       = "PROBE_INVALID"
```

**Routing is on `ContractSatisfaction` (§10.1), never on raw `BehaviorVerdict`.**

| role | expected | measured `ContractSatisfaction` | disposition |
|---|---|---|---|
| INTRODUCE | UNSATISFIED_AT_PARENT | `UNSATISFIED` | READY |
| INTRODUCE | UNSATISFIED_AT_PARENT | `SATISFIED` | **PRE_SATISFIED** (§14) |
| PRESERVE | SATISFIED_AT_PARENT | `SATISFIED` | READY |
| PRESERVE | SATISFIED_AT_PARENT | `UNSATISFIED` | PRECONDITION_BROKEN |
| VERIFY | UNCONSTRAINED | determinate (`SATISFIED` or `UNSATISFIED`) | READY |
| INTRODUCE | — | `INDETERMINATE(PRECONDITION_ABSENT)` | READY — for a `REQUIRES_SUBJECT` contract the subject not existing is the expected pre-state |
| PRESERVE / VERIFY | — | `INDETERMINATE(PRECONDITION_ABSENT)` | PRECONDITION_BROKEN — a behaviour cannot be preserved over a subject that is gone |
| any | — | `INDETERMINATE(other reason)` | PLAN_CONTRADICTION or PROBE_INVALID, by reason |
| any | — | probe `UNRUNNABLE` | PROBE_UNRUNNABLE — owner ENVIRONMENT |
| any | — | probe `INVALID_SPEC` | PROBE_INVALID — owner PLAN / INTEGRATION |

Typed `INDETERMINATE` reasons retain explicit routing; a bare `INDETERMINATE` with no declared routing **MUST**
be treated as `PROBE_INVALID`, never as a developer outcome.

`PLAN_CONTRADICTION` **MUST** be raised when the measured parent state cannot be reconciled with the plan's own
record — for example a `PRESERVE` measured `REFUTED` whose introducing story already reported `COMMIT`.

**No `provider/request` event MUST precede this story's `story/admitted` event.** No developer model call may
begin until the disposition is `READY`, or `PRE_SATISFIED` with remaining work.

---

## 14. PRE_SATISFIED and PLAN_DRIFT semantics

An `INTRODUCE` obligation whose **`ContractSatisfaction` at the actual parent is `SATISFIED`** (§10.1 — not the
raw `BehaviorVerdict`) **MUST**:

- be recorded `PRE_SATISFIED`;
- emit `story/plan-drift` attributed through the dependency DAG to the completed story that introduced the
  behaviour, or `UNATTRIBUTED` when none can be identified;
- consume **no** developer budget;
- **MUST NOT** require that correct code be made incorrect.

If other obligations remain, the story continues on those. If every obligation is `PRE_SATISFIED`, the story
ends `STORY_ALREADY_SATISFIED`: every obligation **MUST** still be independently verified at the candidate
(§16), and the developer call is skipped.

**Why this is safe.** The product claim is untouched — every behaviour is still proved by an independent probe
at the candidate, under the same `semantic_hash`. What changes is the plan claim. Product correctness is
measured by probes; plan correctness is measured by drift (§29). Conflating them was V1's error, and it stopped
run 1 of PLAN-V2 at 10/16.

**Hard plan blockers remain:** `PRECONDITION_BROKEN`, `PLAN_CONTRADICTION`, `PROBE_INVALID`, and a spec whose
contract no longer compiles. Nothing else.

---

## 15. EngineeringTestAdequacy

Developer tests are engineering-quality evidence. They **MUST NOT** decide product correctness.

**SS-81-style false *product* assurance is structurally removed**, because a vacuous developer test now
certifies nothing: `ProductProof` comes from probes. The controls below therefore govern **engineering quality
only**.

```python
class Vacuity(Enum):
    NON_VACUOUS   = "NON_VACUOUS"
    VACUOUS       = "VACUOUS"
    INDETERMINATE = "INDETERMINATE"

class Relevance(Enum):
    RELEVANT     = "RELEVANT"
    IRRELEVANT   = "IRRELEVANT"
    UNMEASURABLE = "UNMEASURABLE"

class AdequacyOutcome(Enum):
    ADEQUATE   = "ADEQUATE"
    INADEQUATE = "INADEQUATE"
    INCOMPLETE = "INCOMPLETE"

@dataclass(frozen=True)
class EngineeringTestAdequacy:
    execution: TestExecution                   # §15.0 — the execution axis
    vacuity: Vacuity                           # defined only when execution is EXECUTED
    relevance: Relevance                       # defined only when execution is EXECUTED
    regressions: TestExecution                 # same typed rules as the story's own tests
    sensitivity: SensitivityResult | None       # deferred from cycle 1
    outcome: AdequacyOutcome | None             # defined ONLY when execution is EXECUTED
```

### 15.0 Test execution is typed, not boolean

The previous draft used booleans `tests_execute_at_candidate` and `tests_pass`, and mapped "tests do not
execute" to `INADEQUATE` with owner `DEVELOPER`. **That re-created SS-96 inside the adequacy gate** — the exact
defect this architecture exists to remove, reintroduced one layer down. It is corrected here with the same
two-axis discipline §10 applies to probes.

```python
class TestExecutionStatus(Enum):
    EXECUTED   = "EXECUTED"      # the runner ran to completion and reported a result set
    UNRUNNABLE = "UNRUNNABLE"    # the runner, tool or environment could not execute

class TestOutcome(Enum):         # defined ONLY when EXECUTED
    PASSED = "PASSED"
    FAILED = "FAILED"

class TestSelection(Enum):       # defined ONLY when EXECUTED
    STORY_TESTS_RAN             = "STORY_TESTS_RAN"
    NO_STORY_TESTS_MATCHED      = "NO_STORY_TESTS_MATCHED"       # developer selector/definition defect
    STORY_TESTS_NOT_COLLECTABLE = "STORY_TESTS_NOT_COLLECTABLE"  # see the classification rule below

@dataclass(frozen=True)
class TestExecution:
    status: TestExecutionStatus
    outcome: TestOutcome | None          # None unless EXECUTED
    selection: TestSelection | None      # None unless EXECUTED
    owner_on_failure: Owner | None
    reason: str | None
```

**Normative rules.**

1. Runner, tool or environment cannot execute (interpreter absent, test framework missing, sandbox
   unavailable, runner crash before reporting) ⇒ `UNRUNNABLE`, owner **`ENVIRONMENT`**, environment retry
   policy. It **MUST NOT** be owner `DEVELOPER` and **MUST NOT** be `INADEQUATE` merely because it did not run.
2. The command executes and the story's tests fail ⇒ `EXECUTED` + `FAILED`, an engineering-quality failure that
   **MAY** be `INADEQUATE` with owner `DEVELOPER`.
3. The command executes but the intended story tests do not actually run ⇒ classified through
   `TestSelection`, **never by prose**. `NO_STORY_TESTS_MATCHED` is a developer-authored selector or definition
   defect, owner `DEVELOPER`.
4. `STORY_TESTS_NOT_COLLECTABLE` **MUST** be classified by the cause of the collection failure, which the runner
   reports: an unresolvable import that resolves to a **declared environment dependency** is `UNRUNNABLE` /
   `ENVIRONMENT` (this is SS-81(A)'s shape); one that resolves to the **project's own source tree** is owner
   `DEVELOPER`; if the cause cannot be determined, the result is owner **`INTEGRATION`** and **MUST NOT** be
   charged to the developer.
5. **Regression execution MUST follow the same rules.** A regression suite that cannot run is `ENVIRONMENT`,
   never a quality failure.
6. **No "did not run ⇒ developer" path may exist anywhere in the adequacy gate.** This is
   `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` applied to developer tests, and it is armed as an invariant.

`AdequacyOutcome` is **defined only when `execution.status is EXECUTED`**. An `UNRUNNABLE` mandatory test
execution is an **environment outcome**, not a non-blocking quality result, and **MUST NOT** be reported as
`INCOMPLETE`.

### 15.1 Vacuity — the candidate-side control

The experiment: take the candidate, neutralise the story's own product hunks in a scratch copy, leave the
developer's test files intact, run the story-owned tests.

`NON_VACUOUS` **MAY** be concluded **only** when **all** hold:

1. the reconstructed candidate is runnable;
2. the developer test harness **executes**;
3. the intended story-owned tests **actually execute**;
4. the failure is an assertion or behavioural failure **attributable to removal of the story's product changes**.

Conditions 2 and 3 are **the typed values of §15.0**, not a separate prose judgement: they hold exactly when
the neutralised run reports `TestExecutionStatus.EXECUTED` and `TestSelection.STORY_TESTS_RAN`.

Collection failure, import failure, invalid reconstruction, tool failure and environment failure **MUST** yield
`INDETERMINATE` and **MUST NOT** be treated as proof that tests are non-vacuous.

Tests that execute successfully and still **pass** after neutralisation **MUST** yield `VACUOUS`.

The control runs at the **candidate**, never at the parent (invariant IX). At the candidate the test file and
its imports exist because the developer wrote both, so collection semantics are stable and the outcome depends
on the product hunks — which is the question being asked.

### 15.2 Relevance

Cycle-1 minimum: `RELEVANT` when at least one **actually executed** story-owned developer test intersects at
least one **executable changed line** of the story diff.

- Branch intersection **SHOULD** be recorded as stronger evidence where the capability exists and the changed
  code contains instrumentable branches. It **MUST NOT** be required universally — branch coverage is not
  defined for every valid change.
- Non-line-addressable artefacts **MUST** use a capability-specific relevance measurement.
- Where the required measurement capability is unavailable or `PARTIAL`, the result **MUST** be `UNMEASURABLE`.
- **Capability absence MUST NOT be converted into `IRRELEVANT`.**
- Mutation/sensitivity evidence **MAY** supersede this heuristic when it lands (§33).

### 15.3 Outcome

Evaluated **only** when `execution.status is EXECUTED` (and likewise for `regressions`).

- `INADEQUATE` — `EXECUTED` + `FAILED`, `NO_STORY_TESTS_MATCHED`, a developer-caused
  `STORY_TESTS_NOT_COLLECTABLE`, `VACUOUS`, `IRRELEVANT`, or regressions `EXECUTED` + `FAILED`. **MAY** block
  under project policy; owner `DEVELOPER`.
- `INCOMPLETE` — `INDETERMINATE` vacuity or `UNMEASURABLE` relevance, i.e. **optional or secondary
  measurements** only. **MUST NOT** block. **MUST NOT** be charged to the developer. Recorded and reported as
  reduced engineering-quality coverage.
- `ADEQUATE` — otherwise.

When `execution.status is UNRUNNABLE` the gate produces **no** `AdequacyOutcome`: it emits an environment
failure with owner `ENVIRONMENT` and defers to the environment retry policy (§22).

`process/tdd-chronology` (V1's RED→GREEN check) is **recorded evidence only**. It **MUST NOT** block. An
organisation **MAY** enforce it as policy; AISEF's product verdict **MUST NOT** consult it.

---

## 16. CandidateProof and VerifiedProof

```python
@dataclass(frozen=True)
class CandidateProof:
    spec_id: str
    candidate_sha: str
    result: ProbeResult

@dataclass(frozen=True)
class VerifiedProof:
    spec_id: str
    candidate_sha: str
    implementer_result: ProbeResult
    verifier_result: ProbeResult
    agreement: bool
    verdict: BehaviorVerdict | None    # set only when agreement is True
```

Independence **MUST** be all three of:

1. **Environment independence** — the verifier's probe runs in a sandbox and worktree acquired by its own
   `StoryScope`, never one the implementer touched. Confinement **MUST** be derived from the scope, not passed
   as an omittable parameter.
2. **Instrument identity** — both results **MUST** carry the same `probe_id`, `probe_digest` and
   `semantic_hash`. Any mismatch is `PROBE_MISMATCH`, a harness integrity failure, not a statement about the
   product.
3. **Disagreement is never resolved in favour of either party.** `agreement == False` **MUST** yield
   `INDETERMINATE`, owner `INTEGRATION`, and stop the story. It **MUST NOT** be arbitrated by a model or settled
   by re-running until the results agree.

A `STORY_ALREADY_SATISFIED` story **MUST** still produce `VerifiedProof` for every obligation.

---

## 17. Story Transaction

Lifecycle: `BEGIN → ACTIVE → (COMMIT | ROLLBACK | RETRY) → DISPOSE → ENDED`.

- **BEGIN** — emit `story/begin` with the parent as a **full SHA**. Abbreviated SHAs **MUST** be refused.
- **ACTIVE** — every acquisition emits `story/resource-acquired`; every capability resolution emits
  `capability/resolved`. The transaction owns resources and records; it **MUST NOT** be a control authority.
- **COMMIT** — permitted only when every obligation owned by the story has a `VerifiedProof` with
  `agreement == True` and a verdict matching `candidate_expectation`. A commit **MUST NOT** depend on a
  developer test verdict.
- **ROLLBACK** — restores the parent state. The recorded owner **MUST** be the owner of the failure that caused
  it, never the stage that observed it.
- **RETRY** — permitted only against the budget named by the failure's typed outcome (§22).
- **DISPOSE** — see §18.

### 17.1 Resource ordering

`StoryScope` **MUST** hold an **explicit ordered resource stack**, disposed in reverse acquisition order, each
release awaited. Sibling disposal order **MUST NOT** be left to concurrency — the external study found exactly
that weakness in Cordis's `_unload()`, which disposes a fiber's effects with `Promise.all` and swallows failures
into a logger.

Required ordering: **processes reaped and the range proved empty → sandbox → worktree → scratch.**

- A worktree **MUST NOT** be removed until the process range that could write to it is **provably** empty.
  Emptiness **MUST** be measured (`kill(pid,0)`/`ESRCH`, `TasksCurrent`, `isJobEmpty`), never inferred from the
  direct child's exit code. This makes D-024's cleanup race unexpressible.
- Acquisition while the scope is disposing **MUST** be refused (`INACTIVE_ACQUIRE`).
- Disposal failures **MUST** be emitted as typed `story/resource-released` events and **MUST NOT** be swallowed.
  A disposal failure **MAY** fail `DISPOSE`.
- Teardown **MUST** be graceful-first: cooperative signal → bounded grace → SIGTERM → grace → SIGKILL →
  **unbounded wait**. A range that will not empty after SIGKILL is a fact to block on and report.
- Residuals that could not be released **MUST** be named, and the next run's preflight **MUST** report them.

---

## 18. RunScope and StoryScope

| scope | owns |
|---|---|
| **RunScope** | `JournalWriter`, run-level lease, run identity, `RunSpec`, `RunTerminationSentinel` |
| **StoryScope** | worktree, sandbox, process ranges, provider/agent sessions, tool grants, scratch, reviewer/security scopes |

- A `StoryScope` **MUST NOT** own a journal writer. It **MUST** emit through the `RunScope` journal.
- `RunScope` disposal **MUST NOT** begin until every `StoryScope` has reported a terminal disposal outcome; a
  `StoryScope` that cannot report one **MUST** be recorded as a typed residual and `RunScope` disposal proceeds.

### 18.1 Lifetime order — the run lease is the outer boundary

**The run lease, not the `JournalWriter`, is the outermost ownership boundary and is released last.** A lease
released before the writer closes would let a second run acquire ownership while the first is still writing
(case **RUN-2**).

**Begin order (normative):**

1. acquire the **run lease**;
2. create and **fsync** an `OPEN` `RunTerminationSentinel`;
3. open the `JournalWriter`;
4. resolve and freeze `RunSpec`;
5. normal run execution.

The lease **MUST** be acquired before **every** state read whose later write depends on ownership.

**Successful shutdown order (normative):**

1. every `StoryScope` disposed;
2. append and fsync `run/dispose-begin` as appropriate;
3. append and fsync `run/end`;
4. **close the `JournalWriter` successfully**;
5. mark and fsync the sentinel `CLEAN`;
6. **release the run lease LAST**.

**Failure behaviour.** If the `JournalWriter` close fails, the sentinel **MUST** remain `OPEN`. If `CLEAN`
cannot be durably recorded, the sentinel **MUST** remain `OPEN`. In both cases the next run's preflight
conservatively reports **TORN** (case **RUN-1**).

This ordering also removes the circularity of the original draft, where the writer recording a scope's teardown
was owned by that scope.

---

## 19. RunTerminationSentinel

A small, durable record **outside** the journal. It is **not evidence** and **not authoritative state**.

**Protocol.**

1. At run begin, **after the run lease is held** (§18.1), create and **fsync** an `OPEN` sentinel **before** the
   `JournalWriter` is opened and before normal execution proceeds.
2. At successful termination, in this order: (a) all `StoryScope`s have disposed; (b) `run/dispose-begin` and
   `run/end` are durably written and fsync'd; (c) the `JournalWriter` **closes successfully**; (d) **only then**
   mark and fsync the sentinel `CLEAN`; (e) the run lease is released **last**.
3. If the `JournalWriter` close fails, or `CLEAN` cannot be durably recorded, the sentinel **MUST** remain
   `OPEN`.
4. A best-effort `FAILED{stage, error}` record **MAY** be written. **No correctness property may depend on
   successfully writing a failure record after a failure has already occurred.**
5. Next-run preflight: `OPEN` without `CLEAN` **MUST** be reported as a **TORN** run.

**TORN is conservative, and MUST be read as such.** It states that clean termination was not durably observed
*outside* the journal. It does **not** state that the journal is incomplete: a run may have a durable `run/end`
and still be `TORN` because the process died before `CLEAN` (case **RUN-1**). The journal remains the authority
for what the run did; the sentinel only reports whether termination was observed.

**Constraints.**

- The journal remains the **sole authority** for run state.
- No gate **MUST** cite the sentinel as product, plan or qualification evidence.
- The sentinel answers exactly one question: *was clean termination durably observed outside the journal?*

**Residual.** Where the journal write, the sentinel write and filesystem observability all fail — a full disk, a
revoked mount, a host loss — nothing in-process records it and the next run's preflight cannot see it either.
This is stated in §34 and is not claimed covered.

---

## 20. Event journal

```python
@dataclass(frozen=True)
class Event:
    seq: int                            # dense: seq == index. MUST NOT be a timestamp.
    type: str                           # the discriminant
    data: Mapping[str, Any]             # JSON-lossless; validated at the append site
    time: float                         # recorded; MUST NOT be read by any projection
    ignorable: bool = False             # explicit author-side claim that a reader may skip this type
    source_seqs: tuple[int, ...] = ()
```

Normative properties:

1. **`seq == index`**, enforced independently at assignment, seed admission, append and decode.
2. **`time` MUST NOT be read for ordering** by any projection. Enforced by a Q0 static check.
3. **Validation at the append site.** A bad event **MUST** fail before the log grows.
4. **An unknown event type without `ignorable: true` MUST cause a reader to refuse to reconstruct.** A format
   version bump is a **writer-side obligation**, never a reader capability question.
5. **The store MUST have no update and no delete verb.** Logical deletion is a new shadowing event.
6. **Writes MUST be synchronous at decision boundaries.** Write-behind is not acceptable for a record whose gaps
   are the SS-96 condition.

### 20.1 Vocabulary

**Run:** `run/begin`, `run/spec-resolved`, `run/dispose-begin`, `run/interrupted`, `run/end`.
**Plan:** `plan/static-admitted`, `plan/frozen`.
**Story:** `story/begin`, `story/admitted`, `story/plan-drift`, `story/resource-acquired`,
`story/resource-released`, `story/commit`, `story/rollback`, `story/retry`, `story/dispose`, `story/end`.
**Capability and proof:** `capability/resolved`, `probe/evaluated`, `proof/verified`.
**Execution:** `provider/request`, `provider/result`, `tool/invoked`, `tool/result`, `tests/adequacy`.
**Control and integrity:** `gate/check`, `gate/decision`, `failure/observed`, `invariant/violated`.

`gate/check` **MUST** be one row per check. A summary-only record is prohibited. `gate/decision` **MUST** cite
its inputs by `seq`.

### 20.2 Interruption

Synthetic closers **MUST** distinguish `OUTCOME_UNKNOWN` from `NOT_STARTED`, **MUST** reuse the last real
event's timestamp so repair is idempotent, and **MUST** be marked synthetic so a closer can never be mistaken
for a measurement. Shutdown is bounded and escalating; a second interrupt during disposal abandons **and records
that it was abandoned**.

---

## 21. Control-critical projections

Every read model is a pure fold of a journal prefix. Caches are **fold shortcuts, never authorities**: a cached
row may be stale — its `seq` says how stale — but never wrong, and a version mismatch **MUST** discard the row
rather than migrate it.

**Exactly six projections are control-critical, and the list is closed** (F11):

1. story state · 2. failure owner · 3. budgets · 4. retry target · 5. terminal state · 6. qualification counters
(including plan-quality metrics, §29).

For each of the six:

- an **independent reference model** **MUST** exist in Q1, implementing the approved owner policy — **not**
  mirroring the implementation — and **MUST** be mechanically prevented from importing the projection module;
- it **MUST** be mutation-tested;
- it **MUST** be calibrated: observed producing the opposite answer on a known input.

Non-control reporting projections **MUST NOT** be duplicated and **MUST NOT** be cited by a gate.

**The from-scratch oracle** — incremental state **MUST** equal `fold(journal_prefix)` at every decision point —
is required for all projections and is asserted in the test suite and sampled in qualification runs.

---

## 22. Typed Owner, retry and budget model

```python
class Owner(Enum):
    PLAN = "PLAN"; DEVELOPER = "DEVELOPER"; ENVIRONMENT = "ENVIRONMENT"; PROVIDER = "PROVIDER"
    REVIEW = "REVIEW"; SECURITY = "SECURITY"; INTEGRATION = "INTEGRATION"
```

- The `Owner` set is **capped**. A new member **MUST** cite a measured defect.
- Every `failure/observed` **MUST** carry `owner` and `retryable`.
- **Retryability is a property of the typed code, fixed once in the taxonomy.** A call site **MUST NOT** decide
  it. Credentials **MUST** distinguish `MISSING_CREDENTIAL` from `INVALID_CREDENTIAL` because the fix differs;
  the latter **MUST NOT** be retryable. This makes D-006 — "credential rejection charged to quality attempts" —
  unexpressible.
- The retry engine **MUST** read only `owner` and `retryable`. Routing follows the typed outcome, never the
  stage that observed it.
- Budgets **MUST** be projections of the journal, never side counters. SS-64 was a cap that disagreed with what
  happened; a projection cannot disagree with its own log.
- **No value from outside the AISEF taxonomy may become a control code.** A non-AISEF error **MUST** flatten to
  `UNKNOWN`, with the original retained as data.

---

## 23. RunSpec and capability identity grades

```python
class IdentityGrade(Enum):
    VERIFIED = "VERIFIED"
    ATTESTED = "ATTESTED"
    OPAQUE   = "OPAQUE"

@dataclass(frozen=True)
class CapabilityIdentity:
    name: str
    grade: IdentityGrade
    tuple_: Mapping[str, str]     # the binding below, by grade
    enforcement: Enforcement

@dataclass(frozen=True)
class RunSpec:
    capabilities: tuple[CapabilityIdentity, ...]
    aggregate_min_grade: IdentityGrade
    settings: Mapping[str, Any]           # resolved, with per-value layer provenance
    runspec_hash: str
```

**`VERIFIED`** — AISEF can compute a digest over the actual artefact it executes. Binds the digest.

**`ATTESTED`** — the provider exposes a stable declared capability/model identity that AISEF cannot
independently digest. **MUST** bind at minimum: provider; endpoint / provider identity; declared
model/capability id; fixed route; client/adapter identity; relevant provider/deployment identity when exposed;
and a **locally measured preflight fingerprint**. The fingerprint is a **drift detector**, not proof of model
weights.

**`OPAQUE`** — the implementation may change behind a route or cannot be stably identified; dynamic model-combo
routes are the canonical example. `OPAQUE` is permitted for development and regression work and **MUST NOT**
support Q6 qualification, sealed evaluation cohorts, or generalization claims.

**Comparability.** Two runs are comparable only with the **same resolved capability identity tuple**, the
**same `IdentityGrade`**, and the **same enforcement identity**. Same grade alone is insufficient.

`RunSpec` **MUST** carry every individual grade and the aggregate minimum grade. A qualification verdict **MUST**
state the aggregate grade.

A version label is metadata, not proof of identity. SS-65 (P1, `INV-N.DEFAULT-CAPABILITY`) is the measured V1
instance: a managed image whose contents decided whether bandit existed.

---

## 24. Capability enforcement levels

Every capability **MUST** declare `FULL`, `PARTIAL` or `UNAVAILABLE`, and **MUST** refuse a request it cannot
honour rather than degrade silently. The resolved level **MUST** be emitted as `capability/resolved` and
**MUST** enter `runspec_hash`.

A run qualified under `PARTIAL` enforcement **MUST NOT** be compared with one under `FULL`.

**Claims must name their weakest path.** Any isolation property asserted in a qualification record **MUST** name
the weakest path that could violate it, or **MUST NOT** be asserted. The external study's design note states the
principle: a boundary an ordinary tool call defeats is not a control, it is a false claim in the evidence.

---

## 25. Reviewer and security isolation

- Reviewer and security capabilities **MUST** run in read-only scopes whose confinement is **derived from the
  scope**, not passed as an omittable parameter. An optional policy parameter means every caller is a place the
  default can silently win — the external study found exactly that leak in DeepSeek's hook path.
- Authority **MUST** only narrow. A child scope **MUST NOT** hold an authority its parent did not hold.
  Restriction intersects; approval is pinned; only explicit overrides propagate; delegation depth is persisted
  so a resumed parent cannot delegate as top-level; and the capture **MUST** be taken synchronously before the
  first await.
- **A scanner that executed and produced findings is `EXECUTED`.** It **MUST NOT** be recorded `UNRUNNABLE`.
  This is SS-92's shape and §10's two-axis rule prevents it.
- A blocking decision **MUST NOT** rest on a model reviewer alone (D-002).

---

## 26. Merge and post-merge proof

- A merge conflict is owner `INTEGRATION`, never `DEVELOPER`.
- After merge, the story's obligations **MUST** be re-proved at the merged revision, together with every
  `PRESERVE` obligation of prior stories the merge could affect. A regression is owner `INTEGRATION`.
- **The measurement point MUST be chosen per claim and recorded in the verdict.** Post-merge is valid for
  *integration* claims. It is **not** valid for *refusal-correctness* claims: SS-95 measured "false BLOCK = 0"
  only at trunk, where a blocked story's code never arrives, so the metric could not discriminate.

---

## 27. Qualification ladder Q0–Q6

A rung **MUST NOT** be attempted while a lower rung is failing. A rung that cannot run **MUST** produce a typed
`UNRUNNABLE`, never a `FAILED`.

| rung | contents | executes probes? | provider spend |
|---|---|---|---|
| **Q0 Static integrity** | schemas; provenance; catalogs (fail-closed **both** directions); static traceability; ownership graph incl. unique `INTRODUCE`; no-prose-control walker; `time`-not-read check; **checker calibration fixtures**; the `StaticPlanAdmissionEngine` **rules** | **no** | none |
| **Q1 Semantic conformance** | `ProductProofSpec` semantics; the **`StaticPlanAdmissionEngine`** and **`StoryAdmission` engine**; independent policy model (barred from importing kernel decision modules); adversarial micro-workloads; **test-layout invariance**; **reference models for the six control-critical projections** | yes, on fixtures | none |
| **Q2 Adequacy** | product mutation with audited equivalents; **`ProbeCapabilityCalibration`** for every probe digest and observation class; **`SpecFalsifiabilityEvidence`** for every spec that will back Q6 product evidence; engineering-test sensitivity | yes | none |
| **Q3 Fault injection** | named provider faults from a local fault server; tool/sandbox/environment faults; interruption and repair idempotence; disposal failures asserted against the OS | yes | none |
| **Q4 Differential at scale** | 100 000 generated traces vs the reference model; 0 unexplained, 0 invariant violations, 0 exceptions, 0 silent skips, one kernel digest | model-level | none |
| **Q5 Real-execution reproduction** | only the model stream replayed; **tools re-executed and diffed, never replayed**; final workspace state compared; request-header class pinning with a bounded drift budget; `assertConsumed`; determinism by normalization, not a faked clock | yes | none |
| **Q6 Live delivery** | real provider, real model | yes | **real** |

**Q0 and Q1 qualify the admission engines. They MUST NOT execute a project's admission.** A project executes the
engine at plan time (§12) and at story time (§13).

**Test-layout invariance** (Q1) **MUST** permute where a fixture story's developer tests live — same directory,
separate directory, module-level import, function-level import, no test file at all — and assert that **every
product verdict is identical**. This is ARCH-LESSON-001 made executable.

**Checker calibration** (Q0): every Q0 checker **MUST** have been observed failing on a committed known-bad
fixture, and the checker set carries its own mutation budget. A checker whose calibration fixture no longer
fails it is itself a Q0 failure.

**Q6 preconditions:** Q0–Q5 green on the exact candidate; kernel frozen with tree and wheel digests; plan frozen
with a `StaticPlanAdmissionResult`; `RunSpec` resolved and content-addressed with `aggregate_min_grade` **not**
`OPAQUE`; provider preflight passing on the exact fixed route.

**Q6 conclusions.** Q6 concludes that *this* capability set, on *this* workload, did or did not deliver. It
**MUST NOT** conclude anything about capabilities or workloads it did not run. `assurance_kernel` and `delivery`
**MUST** remain distinct fields that cannot be collapsed into one headline — as V1's final verdict correctly
did.

---

## 28. Evaluation cohort and holdout lifecycle

```
SEALED ──► EVALUATING ──► EXPOSED ──► DEVELOPMENT
```

```python
@dataclass(frozen=True)
class EvaluationCohort:
    id: str
    state: CohortState
    preregistration_hash: str
    frozen_inputs: Mapping[str, str]          # name -> content hash
    planned_runs: int
    threshold: str                            # e.g. ">=2/3 delivery complete"
    plan_quality_policy: PlanQualityPolicy    # §29 — MUST be preregistered
    runs_completed: tuple[str, ...]
    results_read_at: float | None
    exposed_reason: str | None
```

Preregistration is written and hashed **before** any run and **MUST** freeze: kernel identity; workload identity;
requirements; plan policy; execution profile (content-addressed); prompts; model route; run count; thresholds;
oracle; metrics; and the `PlanQualityPolicy`.

1. Running the preregistered repetitions **MUST NOT** demote the cohort.
2. No framework modification is permitted between runs. A change to any `frozen_inputs` hash during
   `EVALUATING` **MUST** invalidate completed runs and require a fresh preregistration.
3. **Mechanised demotion:** reading results sets `results_read_at`; any change to a `frozen_inputs` hash
   **after** that timestamp **MUST** transition the cohort to `EXPOSED` with `exposed_reason` recorded.
4. `EXPOSED` workloads **MAY** be run for regression and **MUST NOT** back a generalization claim.
5. A cohort whose `aggregate_min_grade` is `OPAQUE` **MUST NOT** be sealed.
6. **Generalization requires multiple independently sealed workloads and MUST state its sample size**, per
   workload and in total.

---

## 29. PlanQualityPolicy

```python
@dataclass(frozen=True)
class PlanQualityPolicy:
    max_pre_satisfied_introduce_ratio: float | None
    max_fully_pre_satisfied_stories: int | None
    max_unattributed_plan_drift: int | None
```

Metrics, all projections of the journal (§21, projection 6):

- `PRE_SATISFIED` `INTRODUCE` obligations ÷ total `INTRODUCE` obligations;
- fully `PRE_SATISFIED` implementation stories;
- `UNATTRIBUTED` `PLAN_DRIFT` count.

**There is no universal framework-level threshold.** Values belong to the evaluation protocol and **MAY** later
be calibrated from reference workloads.

**Verdicts MUST be separate:**

```python
@dataclass(frozen=True)
class RunVerdict:
    delivery_verdict: Literal["PASS", "FAIL", "NOT_REACHED"]
    plan_quality_verdict: Literal["PASS", "FAIL", "NOT_CLAIMED"]
```

A project **MAY** have `delivery = PASS` and `plan_quality = FAIL`, and that distinction is **mandatory**.

- **Ordinary execution:** record and report `PLAN_DRIFT`. `plan_quality_verdict` **MAY** be `NOT_CLAIMED`.
- **Qualification and sealed evaluation:** thresholds **MUST** be preregistered before results are observed. A
  qualification with no preregistered plan-quality thresholds **MUST** set `plan_quality_verdict =
  NOT_CLAIMED` and **MUST NOT** claim the plan was qualified.

---

## 30. LedgerLock classification

**LedgerLock is a DEVELOPMENT / REGRESSION BENCHMARK, permanently. It is not a holdout and MUST NOT be sealed.**

This is a fact about what was done, not a judgement: it has been run repeatedly across many profiles; its plan
was revised in response to run outcomes (PLAN-V2 → PLAN-V2.1); and its ownership audit was performed with
knowledge of observed model behaviour. A benchmark you have tuned against measures your tuning.

No re-labelling is available and none **MUST** be sought. AISEF currently has **no** qualifying sealed workload
and therefore supports **no** generalization claim.

---

## 31. Migration from V1

| V1 | V2 | Notes |
|---|---|---|
| Per-criterion proof modes `CHANGE_REQUIRED` / `PRESERVE_REQUIRED` / `NEGATIVE_INVARIANT` | `ObligationRole` `INTRODUCE` / `PRESERVE` / `VERIFY` + `Polarity` on the contract | Mapping is mechanical; it **MUST** be generated and `--check`ed, not hand-written |
| `TDD` gate check | `process/tdd-chronology`, recorded only | Implementation retained unchanged, including the SS-96 fix in `_tdd_check`; only its authority changes |
| `nop` control at the parent | candidate-side vacuity control (§15.1) | Same information, no parent-side developer execution |
| Criterion parent state from developer tests | `StoryAdmission` probe at the exact parent SHA | Closes `PLAN-V2.1-DEFECT-001` |
| `PLAN_OVERLAP` hard stop | `PRE_SATISFIED` + `PLAN_DRIFT` | Would have let run 1 of PLAN-V2 continue past 10/16 |
| `UNRESOLVABLE` | deleted | A missing subject is a completed observation |
| Evidence files under `closure-evidence/` | append-only journal + projections | V1 evidence is **frozen and MUST NOT be migrated or rewritten**; it is cited by hash |
| `ExecutionProfile` content hash | `RunSpec` with per-capability identity, grade and enforcement | Strictly extends V1; the content-hash property is retained |
| 57 invariants | invariants I–IX plus the existing register, armed in every test | `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` becomes structural via §10 |

**V1 artefacts MUST NOT be modified.** The frozen kernel, W0 records, Phase-12 evidence, V1 plans and V1
qualification evidence remain byte-identical and are referenced by hash.

---

## 32. Cycle-1 implementation scope

Six changes. Every one cites a measured V1 defect. **Scope MUST NOT expand without a measured defect.**

| # | Change | Measured defect |
|---|---|---|
| 1 | `BehaviorContract` + `ProductProofSpec` + harness-owned probes; two-axis outcomes; `UNRESOLVABLE` removed; `MUST_NOT_HOLD` precondition rule | `PLAN-V2.1-DEFECT-001`; SS-92; SS-96 |
| 2 | `StaticPlanAdmissionEngine`/`Result` + `StoryAdmission` with `PRE_SATISFIED` / `PLAN_DRIFT` | `AC-STORY-04-01-2`; `AC-STORY-01-01-4/-5` |
| 3 | Append-only journal + projections + from-scratch oracle + reference models for the six control-critical projections | SS-64; SS-77; SS-81 |
| 4 | Story Transaction with `RunScope`-owned journal, `RunTerminationSentinel`, ordered disposal, measured range emptiness, image and probe digests in `RunSpec` | D-024/025/027; SS-65 |
| 5 | Invariants I–IX armed in every test and uncontainable | SS-96 and the declared-but-unenforced class |
| 6 | Q0 static integrity + Q1 test-layout invariance + local fault injection (Q3) | `PLAN-V2.1-DEFECT-001`; `FAM-PROVIDER` |

Plus two small additions: `EngineeringTestAdequacy` with the candidate-side vacuity control and line-intersection
relevance (§15); and the `ContractApproval` record (§6).

---

## 33. Deferred scope

Deferred **MUST NOT** mean forgotten; each is listed with what would trigger it.

| item | trigger to revisit |
|---|---|
| Engineering-test **sensitivity** (mutation at story scope) | when Q2 mutation infrastructure is stable and its cost per story is measured |
| Sealed-cohort **machinery** | when a workload that has never been tuned against exists |
| **Toolchain identity** in `RunSpec` | a measured defect attributable to toolchain drift |
| **Behaviour-aware parallel scheduling** | a measured defect it would close; it currently amplifies `FAM-SCHEDULER` |
| Branch-coverage relevance as a requirement | when full branch-coverage capability exists across target languages |
| Journal **compaction** | when journal size measurably affects the from-scratch oracle |

---

## 34. Security and failure residuals

Stated, not argued away. A system that claims coverage it does not have is the failure mode this whole
architecture exists to prevent.

1. **A `BehaviorContract` faithful to a wrong requirement.** Not machine-detectable. Control: the human semantic
   gate (§6). Residual: irreducible.
2. **A projection and its reference model wrong in the same way.** Control: independent authorship and the
   no-import rule (§21). Residual: real.
3. **Undetectable remote capability drift.** Control: `ATTESTED` binding plus preflight fingerprint; `OPAQUE`
   barred from Q6 (§23). Residual: a provider may change behaviour without changing anything we can observe.
4. **Journal, sentinel and filesystem observability all failing.** Control: next-run preflight (§19). Residual:
   undetectable in that case.
5. **A hard-killed harness leaves orphans.** No disposer runs. Control: next-run preflight detection, not
   prevention.
6. **Owner assignment remains the hard part.** Typed ownership is only as good as the rule that assigns an
   owner, and V1 showed assignment is where the difficulty lives.
7. **`PARTIAL` enforcement and `ATTESTED` identity are invitations.** Both are honest grades; under schedule
   pressure both will be used and comparability narrows quietly. The guard — verdicts must state their grade —
   is a documentation guard, the weakest kind.
8. **Probe and product may drift together.** A probe maintained alongside the code it observes can lose
   independence. Control: probe calibration and product mutation (§9.1, Q2). Residual: partial.

---

## 35. Compatibility and versioning

- **Journal format.** Adding a **required** event type or payload field is a **format version bump** and is a
  writer-side obligation. Adding an `ignorable` event type is not. A reader meeting an unknown required type
  **MUST** refuse to reconstruct.
- **`semantic_hash` compatibility.** Changing a contract's semantics, a probe's identity, or a probe's input
  produces a new `ProductProofSpec` id. Evidence under the old id remains valid **for the old id** and
  **MUST NOT** be silently reused for the new one.
- **`plan_hash` compatibility.** A plan revision **MUST NOT** invalidate product evidence. This is the
  load-bearing compatibility property of the plane split.
- **Probe versioning.** A probe change bumps `probe_digest` and therefore every dependent `semantic_hash`.
  Accumulated evidence is preserved against the previous digest; re-proving is required for the new one. How to
  make this affordable is an implementation question (§36, Q4).
- **Frozen artefacts.** A frozen artefact **MUST NOT** change without its manifest changing in the same commit,
  enforced by a commit-time guard and a CI check.

---

## 36. Acceptance criteria for implementation

Implementation of cycle 1 is complete when **all** hold:

1. Q0 green, with every checker calibrated against a committed known-bad fixture.
2. Q1 green, including the **test-layout invariance** suite and reference models for all six control-critical
   projections.
3. Q2: product mutation with **zero unaudited survivors**; a valid `ProbeCapabilityCalibration` for every probe
   digest and observation class in use; and `SpecFalsifiabilityEvidence` for every `ProductProofSpec` that will
   back Q6-qualified product evidence. Neither is a plan-freeze prerequisite.
4. Q3: the fault matrix green, including interruption idempotence and OS-asserted disposal.
5. Q4: a fresh 100 000-trace differential with 0 unexplained divergences and 0 invariant violations, on the
   exact candidate.
6. Q5: real-execution reproduction green, with tools re-executed rather than replayed.
7. All nine invariants armed in every test tier and demonstrably uncontainable — a test **MUST** show an
   invariant violation escaping a `try/except` boundary.
8. The freeze table below implemented exactly as specified, with a Q0 check that each frozen shape matches.
9. No file under `aisef/` from the V1 frozen tree modified except as recorded in an approved migration record;
   all V1 closure evidence byte-identical.
10. `delivery_verdict` and `plan_quality_verdict` emitted separately for every run.

**Open implementation questions — not architectural blockers.** The probe taxonomy per `Subject.kind`;
`PLAN_DRIFT` attribution tie-breaks; journal compaction and retention; Windows equivalents for measured range
emptiness and OS-level teardown assertions; the generated V1 proof-mode migration table; where probes live
relative to the product tree and how a probe change is re-proved affordably.

---

## Normative freeze table

Frozen means: changing it later invalidates evidence written under it. Each **MUST** have owner sign-off before
implementation begins. Items marked *(adjusted)* changed mechanically as a consequence of owner decisions B1–B5;
**no new freeze item was added**. Items marked *(amended — V2-001)* changed through `ARCHITECTURE-EXCEPTION-V2-001`;
items marked *(amended — V2-002)* changed through `ARCHITECTURE-EXCEPTION-V2-002`; items marked *(V2-003)* through
`ARCHITECTURE-EXCEPTION-V2-003`.

| # | Frozen item | Why evidence compatibility requires it |
|---|---|---|
| **F1** | `Event` envelope, the event vocabulary, **and the typed enumerations carried in event payloads** *(adjusted; a payload enum gained one member — V2-003)* | Every journal is written under them; a payload enum change re-interprets existing events |
| **F2** | `ProbeExecutionStatus` × `BehaviorVerdict`, its six legal states, the owner routing table **keyed by `MeasurementPoint` (§10.3)** *(amended — V2-001, V2-003)*, **and the `ContractSatisfaction` derivation** *(adjusted)* | Everything routes on it; `UNRESOLVABLE` is deleted. Re-deriving old evidence under a changed satisfaction mapping would silently re-interpret it |
| **F3** | The `Owner` set — capped; a new member requires a cited measured defect | Budgets and retries derive from it |
| **F4** | `BehaviorContract` → `ProductProofSpec` compiler contract and the inputs to `semantic_hash`, **including `SubjectAbsence`** *(adjusted)* | It is what `--check` compares against and what makes product evidence survive re-planning. Absence semantics change what a spec means when the subject is missing |
| **F5** | `Probe` protocol: observation-harness / subject split, **including harness timeout vs subject observation deadline (§9.2) and signal provenance after dispatch (§9.3)** *(amended — V2-002, V2-003)*, `enforcement()`, `ProbeResult` fields, **and the two calibration contracts — `ProbeCapabilityCalibration` and `SpecFalsifiabilityEvidence`, each demonstrating contrast to `candidate_expectation`** *(adjusted)* | The split keeps product absence out of the environment budget; a changed calibration contract re-interprets whether existing probes were ever qualified |
| **F6** | `PlanObligation` shape, `ObligationRole`, and `ParentExpectation` **expressed as a contract-satisfaction expectation, never a raw verdict** *(adjusted)* | The planning plane's vocabulary. Raw-verdict expectations are polarity-inverted for every negative contract |
| **F7** | `StoryAdmissionDisposition` set | Gate ordering and budget routing depend on it |
| **F8** | `RunScope` / `StoryScope` ownership split, the disposal ordering contract, and the **run lease / sentinel / journal lifetime order — lease acquired first and released last** *(adjusted)* | Re-parenting resources later invalidates every disposal record; the lifetime order defines both what TORN means and when a second run may acquire ownership |
| **F9** | The four cited identities, **including per-capability identity tuples, `IdentityGrade` and the aggregate minimum** *(adjusted)* | Comparability of every verdict |
| **F10** | Invariants **I–IX**, each with its named enforcement mechanism | An invariant without a mechanism is a documented intention |
| **F11** | The six control-critical projections, as a **closed** list | Only these may be cited by a gate |

---

## Adversarial regression cases

Deterministic worked examples. Each **MUST** be implemented as a conformance case in Q1.

### Polarity

**NEG-1 · `MUST_NOT_HOLD`, forbidden behaviour PRESENT at parent.**
Contract: *"the CLI MUST NOT write to stdout"*, `polarity = MUST_NOT_HOLD`, so
`candidate_expectation = REFUTED`. At the parent the CLI does write to stdout, so the observable is present:
`BehaviorVerdict = SATISFIED`. Satisfaction = `SATISFIED != REFUTED` ⇒ **`UNSATISFIED`**.
Role `INTRODUCE`, expected `UNSATISFIED_AT_PARENT` ⇒ **`READY`**.
**Never `PRE_SATISFIED`.** Routing on the raw verdict would have produced `PRE_SATISFIED` here — the inversion
this correction removes.

**NEG-2 · `MUST_NOT_HOLD`, forbidden behaviour ABSENT at parent, `ABSENCE_IS_DECIDABLE`.**
Contract: *"a forbidden module MUST NOT exist"*. `candidate_expectation = REFUTED`. The module is absent, which
is a valid observation for this contract: `BehaviorVerdict = REFUTED`. Satisfaction = `REFUTED == REFUTED` ⇒
**`SATISFIED`**. Role `INTRODUCE` ⇒ **`PRE_SATISFIED`** + `PLAN_DRIFT`, no developer budget consumed. Correct:
the prohibition already holds and the story has nothing to introduce.

**NEG-3 · `MUST_NOT_HOLD` over an existing subject, `REQUIRES_SUBJECT`, subject absent.**
Contract: *"the CLI MUST NOT write to stdout"*, but the CLI does not exist at the parent. The probe executes and
its declared precondition fails ⇒ `EXECUTED` + **`INDETERMINATE(PRECONDITION_ABSENT)`**, so satisfaction is
`INDETERMINATE`. Role `INTRODUCE` ⇒ **`READY`** (the subject not existing is the expected pre-state). Role
`PRESERVE` or `VERIFY` ⇒ `PRECONDITION_BROKEN`. **No vacuous verdict is produced in any case.** This is AISEF's
own `AC-STORY-01-01-4/-5`.

### Owner routing by measurement point *(amended — V2-001)*

Contract: a `REQUIRES_SUBJECT` contract whose subject does not exist; its probe returns
`EXECUTED` + `INDETERMINATE(PRECONDITION_ABSENT)` wherever the subject is absent.

**OWNER-MP-1 · parent, `INTRODUCE`, subject absent.** ⇒ **`READY`**, no failure owner, no developer failure: the
subject not existing is the expected pre-state.

**OWNER-MP-2 · candidate, after an admitted `INTRODUCE`, subject still absent.** ⇒ **`DEVELOPER`**: the admitted
implementation failed to establish the subject the proof requires. Never `PLAN`.

**OWNER-MP-3 · post-merge, a subject verified at the candidate disappears.** ⇒ **`INTEGRATION`**.

**OWNER-MP-4 · the probe's observation harness cannot inspect the subject.** ⇒ `UNRUNNABLE`, **`ENVIRONMENT`**, at
every measurement point.

### Harness timeout vs subject observation deadline *(amended — V2-002)*

**TIME-1 · the harness cannot launch the subject.** ⇒ `UNRUNNABLE` / **`ENVIRONMENT`**, no verdict.

**TIME-2 · the subject launches; a positive response contract exceeds its deadline.** ⇒ `EXECUTED`; contract
**`UNSATISFIED`**.

**TIME-3 · the subject launches; a forbidden-event contract reaches its deadline with no event.** ⇒ `EXECUTED`;
contract satisfaction according to that negative spec — the forbidden event was not observed, so **`SATISFIED`**.

**TIME-4 · the same physical subject timeout under different specs** may yield different `ContractSatisfaction`:
each spec's observable, polarity and window decide it.

**TIME-5 · a subject timeout MUST NEVER become `ENVIRONMENT`** merely because a timeout occurred.

### Calibration

**CAL-1 · a `MUST_NOT_HOLD` probe that always returns `REFUTED`.**
Such a probe always reports satisfaction `SATISFIED` — it can never fail a prohibition.
`ProbeCapabilityCalibration` requires the probe to produce the **contrast** to `candidate_expectation`, i.e.
`SATISFIED`, on a committed negative fixture where the forbidden behaviour **is** present. The always-`REFUTED`
probe cannot, so it is **not qualified** for that observation class and `StaticPlanAdmission` check 9 rejects
every plan referencing it. The previous rule — "must be observed producing `REFUTED`" — would have **passed**
this probe.

**CAL-2 · no plan may require a `StoryAdmission`-produced artefact to freeze.**
`StaticPlanAdmission` requires only `ProbeCapabilityCalibration`, which belongs to the probe and exists before
any project plan is written. `SpecFalsifiabilityEvidence` is produced by Q2 and is required only before a spec
backs Q6-qualified product evidence. There is therefore **no path** on which plan freeze depends on an artefact
that only exists after plan freeze.

### Engineering tests

**TEST-1 · the test runner is missing.**
`pytest` (or the configured runner) is not installed. ⇒ `TestExecutionStatus.UNRUNNABLE`, owner
**`ENVIRONMENT`**, environment retry policy. `AdequacyOutcome` is **not defined**. The result is
**never `DEVELOPER`**, **never `INADEQUATE`**, and **never `INCOMPLETE`** — an `UNRUNNABLE` mandatory execution
is an environment outcome, not a non-blocking quality result.

**TEST-2 · tests execute and assertions fail.**
⇒ `EXECUTED` + `FAILED` + `STORY_TESTS_RAN`. `AdequacyOutcome = INADEQUATE`, owner **`DEVELOPER`**, chargeable
to the developer quality budget, and **MAY** block under project policy.

*(Companion case, from rule 15.0.4:* the runner executes but the story's tests fail to collect because they
import a module that does not exist. If that module resolves to a declared environment dependency ⇒
`UNRUNNABLE` / `ENVIRONMENT`. If it resolves to the project's own source tree ⇒ `DEVELOPER`. If the cause cannot
be determined ⇒ owner `INTEGRATION`, never `DEVELOPER`.)*

### Run lifetime

**RUN-1 · crash after a durable `run/end` but before `CLEAN`.**
The journal is complete and authoritative. The sentinel is still `OPEN`, so the next run's preflight reports the
run **TORN**. This is deliberately conservative: `TORN` says clean termination was not observed outside the
journal, **not** that the journal is incomplete.

**RUN-2 · a second run attempts to start while the first still holds its lease.**
The lease is released **last**, after `CLEAN` (§18.1). A `run/end` in the journal is therefore **not** sufficient
for a second run to acquire ownership: the second run blocks on the lease until the first has closed its writer,
marked the sentinel and released. Under the previous ordering — writer outermost, lease inner — the second run
could have started while the first was still writing.

---

## Review 1 — CONSISTENCY

*No circular prerequisite or polarity inversion.*

**Polarity.** Every planning decision now routes on `ContractSatisfaction` (§10.1), a derived value defined as
`behavior_verdict == candidate_expectation`. Checked at each routing site: `StoryAdmission` (§13),
`PRE_SATISFIED` (§14), commit conditions (§17), post-merge (§26). No site reads a raw `BehaviorVerdict` to make
a planning decision. `ParentExpectation` no longer encodes a raw verdict (§11).

**Circularity.** The one circular prerequisite — spec calibration required before plan freeze, produced after
plan freeze — is removed by the two-level split (§9.1). `StaticPlanAdmission` check 9 now requires only
`ProbeCapabilityCalibration`, whose inputs are committed fixtures belonging to the probe.

**Absence handling.** `SubjectAbsence` is declared per contract and bound into `contract_hash` and
`semantic_hash`. No rule infers it from polarity. The `REQUIRES_SUBJECT` branch preserves the
`PLAN-V2.1-DEFECT-001` closure; the `ABSENCE_IS_DECIDABLE` branch stops the previous rule from over-blocking
legitimate absence contracts.

**Absence never charged to the developer.** Three sites were checked for the SS-96 shape: probe execution
(§10 — only `UNRUNNABLE` routes to `ENVIRONMENT`, and `REFUTED` requires `EXECUTED`); test execution (§15.0 —
corrected; the previous draft had "did not execute ⇒ `INADEQUATE`/`DEVELOPER`", which was the defect); and
relevance measurement (§15.2 — capability absence is `UNMEASURABLE`, never `IRRELEVANT`).

**Terminology.** `INDETERMINATE` appears on three types — `BehaviorVerdict`, `ContractSatisfaction` and
`Vacuity`. They remain **separate enums** with different owners and are never routed on by bare name. This was
noted in the previous pass and is unchanged.

No unresolved contradiction remains.

## Review 2 — IMPLEMENTABILITY

*Every prerequisite exists before the operation that requires it.*

| operation | prerequisite | exists because |
|---|---|---|
| compile `ProductProofSpec` | approved `BehaviorContract` incl. `SubjectAbsence` | §6 approval precedes §8 compile |
| `StaticPlanAdmission` check 6 | probe resolves, `probe_digest` matches | probes are harness artefacts, committed |
| `StaticPlanAdmission` check 9 | `ProbeCapabilityCalibration` | belongs to the probe, committed with its fixtures, exists before any plan |
| plan freeze | `StaticPlanAdmissionResult` | produced by the project at plan time (§12) |
| `StoryAdmission` | frozen plan, exact `parent_sha`, probes | §13 runs after §12 and after the story's parent is frozen (S7) |
| `ContractSatisfaction` | `ProbeResult` + `spec.candidate_expectation` | both present at every routing site |
| Q6 product evidence | `SpecFalsifiabilityEvidence` | produced in Q2, which precedes Q6 in the ladder |
| open `JournalWriter` | run lease held, sentinel `OPEN` fsync'd | §18.1 begin order |
| mark sentinel `CLEAN` | all StoryScopes disposed, `run/end` durable, writer closed | §18.1 shutdown order |
| release run lease | sentinel `CLEAN` | released last, §18.1 |
| next-run preflight `TORN` | sentinel readable | created and fsync'd at begin, before anything else can fail |

**No operation depends on an artefact produced later.** The one instance that did — CAL-2 — is corrected.

**One implementability note, not a blocker.** Rule 15.0.4 classifies a collection failure by whether the
unresolvable import resolves to a declared environment dependency or to the project's own source tree. That
requires the runner's structured collection-error output and a resolvable dependency manifest. Both exist for
Python; for other target languages the classification may be unavailable, in which case the rule's own fallback
applies — owner `INTEGRATION`, never `DEVELOPER`. The fallback is safe, so this is an implementation question
(§36), not an architectural gap.

## Review 3 — SIMPLIFICATION

*No new component unless required by the corrections above.*

Four types were added by these corrections. Each is required by a named defect family and none introduces a
plane, a service or a new architectural layer:

| added | required by | if removed |
|---|---|---|
| `ContractSatisfaction` (derived function, not stored) | defect A | every negative contract routes backwards; NEG-1 fails |
| `SubjectAbsence` (one contract field) | defect A2 | legitimate "MUST NOT exist" contracts become undecidable; NEG-2 fails |
| `ProbeCapabilityCalibration` / `SpecFalsifiabilityEvidence` (split of one existing concept) | defect B | plan freeze depends on a post-freeze artefact; CAL-1 and CAL-2 fail |
| `TestExecution` / `TestOutcome` / `TestSelection` (types replacing two booleans) | defect C | "did not run ⇒ developer" returns, i.e. SS-96 inside the adequacy gate; TEST-1 fails |

Defect D added **no** type — it reorders existing acquisitions.

**Nothing else was added.** No new freeze item (F12 was not created); five existing items were adjusted
mechanically. The cycle-1 scope (§32) is unchanged in count and content; corrections A–D change how three of its
six changes behave, not what they are.

**Carried forward from the previous pass, unchanged.** `ContractApproval` remains the one component with **no
measured V1 defect behind it**, retained on board instruction as the only control for residual §34.1. Recorded
here rather than hidden. The candidate-side vacuity control remains the weakest-justified component and is still
the first thing to cut if cycle 1 runs long — correction C strengthens that judgement, since vacuity is now
explicitly a secondary measurement whose `INDETERMINATE` never blocks.
