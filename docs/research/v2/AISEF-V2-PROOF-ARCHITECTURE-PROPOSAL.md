# AISEF V2 — proof architecture proposal

Owner decision §10. The chain is
**Requirement → Behavior Contract → Canonical ProofSpec → Harness-owned Probe → Plan/Story → Agent
Implementation → Candidate Proof → Independent Verification.**

This document proposes concrete interfaces for each link and states what each one is *for*. It is a design
proposal, not an implementation; nothing here has been built.

---

## 0. The defect this architecture exists to make unexpressible

V1's delivery qualification ended on `PLAN-V2.1-DEFECT-001`, recorded in
`closure-evidence/hardening/ARCH-LESSON-PROOF-PLACEMENT.json`:

> A criterion's parent state is read from the criterion's TESTS, and whether a test can be collected at the
> parent is a property of its FILE, not of the criterion.

Two runs of a byte-identical frozen plan reached **opposite** parent states for `AC-STORY-01-01-4` and `-5`,
because in one run the developer's test file imported the product at module level and in the other it did not.
The lesson was stated as **ARCH-LESSON-001**:

> Proof obligation semantics must be independent of developer-chosen test file placement.

Everything below follows from taking that seriously, plus one observation the external study supplies:
DeepSeek Harness has **no** analogue of this problem space (see
[`AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md`](AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md) §3.19). There is nothing
to borrow. The patterns we borrow — typed outcomes, fail-closed catalogs, append-only evidence — harden the
*plumbing* around this chain; the chain itself is ours to get right.

### The root cause, stated as a rule

V1 used **one artefact for two jobs**: the developer's tests were simultaneously (a) evidence that the developer
practised TDD and (b) the instrument that decided whether a criterion held. Those jobs have incompatible
requirements. (a) must be written by the developer, or it proves nothing about the developer. (b) must *not* be
written by the developer, or it proves nothing about the product.

**V2's central rule: the instrument that decides a criterion is owned by the harness. Developer tests prove
developer discipline and never decide a criterion.**

---

## 1. Requirement

A Requirement is owner-authored prose. It carries **authority** and no control semantics — this is the
**Requirement Authority** and **No Prose As Control State** invariants meeting: the requirement is why a contract
exists, and is never itself read by any control path.

```python
@dataclass(frozen=True)
class Requirement:
    id: str                 # "FR-11"
    text: str               # prose, owner-authored
    source: str             # the approved document + its content hash
```

No field of `Requirement` may be read by the kernel during a run. It exists to be *cited* by a Behavior Contract
and to be reviewable by a human.

---

## 2. Behavior Contract

A Behavior Contract is the first machine-checkable object in the chain. It states one observable behaviour of an
addressable subject, and its **polarity**.

```python
class Polarity(Enum):
    MUST_HOLD     = "MUST_HOLD"      # the behaviour is required to be present
    MUST_NOT_HOLD = "MUST_NOT_HOLD"  # the behaviour is required to be absent (negative invariant)

@dataclass(frozen=True)
class Subject:
    """What the contract is about — addressable without reference to any test file."""
    kind: Literal["python_callable", "cli_invocation", "http_route", "file_artifact", "process_effect"]
    locator: str            # "aisef.control.gate:evaluate" | "aisef run --dry" | "GET /health" | path
    # A Subject must resolve at any revision, or resolution failure is UNRESOLVABLE (never FAILED).

@dataclass(frozen=True)
class BehaviorContract:
    id: str                      # "BC-0041"
    requirement_ids: tuple[str, ...]
    subject: Subject
    stimulus: Mapping[str, Any]  # inputs/preconditions, fully serialisable
    observable: Mapping[str, Any]# the asserted observation
    polarity: Polarity
    rationale: str               # prose, for humans; never read by control
```

**Why `Subject` is a separate type.** A contract must be *about* something that exists independently of the
plan, the story and any test. `Subject.locator` resolves against a revision; a locator that does not resolve
yields `UNRESOLVABLE`, which is an environment/plan outcome and never a developer failure
(`INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE`).

**What is forbidden.** A `BehaviorContract` may not name a test file, a test function, a directory layout, or
any developer-chosen artefact. If a contract cannot be stated without naming one, it is not yet a contract — it
is a description of a test.

---

## 3. Canonical ProofSpec

The ProofSpec is **generated deterministically from the contract**. It is the only object the kernel consults
when deciding whether a criterion holds.

```python
@dataclass(frozen=True)
class ProofSpec:
    id: str                      # derived: "PS-" + blake2b(canonical_bc)[:16]
    contract_id: str
    probe_id: str                # which harness-owned probe evaluates this
    probe_input: Mapping[str, Any]
    expected_at_candidate: Verdict     # SATISFIED (MUST_HOLD) | REFUTED (MUST_NOT_HOLD)
    required_at_baseline: Verdict      # what the baseline MUST show for this spec to be admissible
    spec_hash: str               # binds probe_id + probe_input + both expectations
```

Three properties, each deliberate:

1. **Derived, not authored.** `ProofSpec = canonicalise(BehaviorContract)` is a pure function. That makes it
   `--check`-able exactly as DeepSeek's nine `verify-*-catalog` gates are
   (`scripts/gen-cordis-catalog.ts:1167-1192`): a committed ProofSpec that no longer matches its contract fails
   the build. Drift between "what we agreed" and "what we check" becomes impossible rather than unlikely.
2. **`required_at_baseline` is a field, not an inference.** This is the direct fix for `FAM-PROOF-PLACEMENT`.
   V1 *inferred* the parent state from whatever the developer's tests did at the parent SHA. V2 *declares* it
   and then *measures* it (§5).
3. **`spec_hash` binds the instrument.** Changing the probe or its inputs changes the spec id. A verdict records
   the spec hash it was produced under, so no verdict can be reused across a changed obligation.

### Verdict is a typed lattice, not a boolean

```python
class Verdict(Enum):
    SATISFIED    = "SATISFIED"     # the observable was present
    REFUTED      = "REFUTED"       # the observable was absent, and we know it
    UNRESOLVABLE = "UNRESOLVABLE"  # the subject does not resolve at this revision
    UNRUNNABLE   = "UNRUNNABLE"    # the probe could not execute (tool, sandbox, environment)
    INDETERMINATE= "INDETERMINATE" # the probe ran and could not decide — a probe defect, reported as such
```

`UNRESOLVABLE`, `UNRUNNABLE` and `INDETERMINATE` are **never** developer failures and are never chargeable to a
developer budget. This is SS-96's invariant carried into the proof layer, and it is the same distinction
DeepSeek enforces as a check-order rule at `packages/shell/bash-sandbox/src/index.ts:119-123`.

---

## 4. Harness-owned Probe

A Probe is the instrument. It is harness code, in the harness's tree, under the harness's tests and mutation
budget. The developer cannot write it, edit it, move it, or influence where it lives.

```python
class Probe(Protocol):
    id: str
    version: str                 # part of the capability contract; see CapReg
    def enforcement(self) -> Enforcement: ...   # FULL | PARTIAL | UNAVAILABLE
    def evaluate(self, spec: ProofSpec, at: RevisionRef, env: ExecutionEnv) -> ProbeResult: ...

@dataclass(frozen=True)
class ProbeResult:
    verdict: Verdict
    probe_id: str
    probe_version: str
    spec_hash: str
    revision: str                # full SHA, never abbreviated
    enforcement: Enforcement
    evidence_ref: str            # journal locator for raw output
    owner_on_failure: Owner | None   # PLAN | DEVELOPER | ENVIRONMENT | PROVIDER | ...
```

`enforcement()` is borrowed directly from DeepSeek's sandbox and subagent seams
(`packages/sandbox/sandbox-local/src/index.ts:181-186,233-237`;
`packages/subagent/subagent/src/out-of-process.ts:57-63`): a capability declares what it can actually enforce and
**refuses rather than degrades**. A probe that can only partially evaluate its contract says so, and the
enforcement level is bound into the record — so a criterion proved under `PARTIAL` can never be compared with one
proved under `FULL`.

**The developer's tests are not absent from V2.** They remain a required, separately-gated obligation: the TDD
control still checks that a red run preceded the green one, that the tests are bound to the story, and that they
execute at the candidate. What changes is that their verdict decides *the TDD check*, and never *the criterion*.
Two instruments, two questions, two outcomes.

---

## 5. Plan admission — the measurement that must happen before a plan is frozen

This is the proposal's load-bearing addition and the answer to both plan families.

**Rule.** A plan may not be frozen until, for every criterion it contains, the harness has **measured** the
baseline probe verdict and it equals `ProofSpec.required_at_baseline`.

```python
@dataclass(frozen=True)
class AdmissionRow:
    criterion_id: str
    spec_id: str
    story_id: str
    declared_baseline: Verdict
    measured_baseline: Verdict
    measured_at: str             # baseline revision, full SHA
    outcome: Literal["ADMITTED", "PLAN_OVERLAP", "PLAN_PRECONDITION_MISSING",
                     "BASELINE_UNRUNNABLE", "BASELINE_UNRESOLVABLE"]
```

What each mismatch means, and why each is a *plan* outcome and not a developer one:

| declared | measured | outcome | reading |
|---|---|---|---|
| `REFUTED` | `SATISFIED` | `PLAN_OVERLAP` | the behaviour is already present at the baseline; this story has nothing to change |
| `REFUTED` | `UNRESOLVABLE` | `PLAN_PRECONDITION_MISSING` | the subject does not exist yet; another story must create it first |
| `SATISFIED` | `REFUTED` | `PLAN_PRECONDITION_MISSING` | a must-hold invariant is already broken at the baseline; not this story's job |
| any | `UNRUNNABLE` | `BASELINE_UNRUNNABLE` | environment, never a plan or developer failure; the plan is simply not yet admissible |

**This is exactly what would have caught both V1 plan defects, before any model call and at zero provider cost.**
`AC-STORY-04-01-2` was `PLAN_OVERLAP` — a behaviour already green at the story's parent — and run 1 of PLAN-V2
spent six minutes and a developer session to discover it. `AC-STORY-01-01-4/-5` was
`PLAN_PRECONDITION_MISSING`, discovered 0/16 into a run. Both are single rows in an admission table that can be
computed from the frozen baseline alone.

It is also the **bidirectional fail-closed** rule of `gen-cordis-catalog.ts:55-59` applied to plans: a criterion
with no owning story and a story asserting a criterion the baseline already satisfies are *both* errors. AISEF's
V1 ownership audit already enforced one direction — it correctly refused a new AC that had no `BEHAVIOUR` entry.
Admission enforces the other.

---

## 6. Plan and Story

```python
@dataclass(frozen=True)
class Criterion:
    id: str                  # "AC-STORY-01-01-4"
    spec_id: str             # exactly one ProofSpec
    story_id: str            # exactly one owning story

@dataclass(frozen=True)
class Plan:
    id: str
    baseline: str            # full SHA
    criteria: tuple[Criterion, ...]
    admission: tuple[AdmissionRow, ...]   # one row per criterion, all ADMITTED
    plan_hash: str
```

**Ownership is total and unique**: every ProofSpec has exactly one owning story, every story's criteria are
admissible at its own predecessor state. `Plan.admission` is not commentary — a plan whose admission table is
absent, incomplete, or contains a non-`ADMITTED` row is not a plan and the kernel refuses it, the same way W0
refuses an abbreviated SHA.

---

## 7. Candidate Proof and Independent Verification

```python
@dataclass(frozen=True)
class CandidateProof:
    spec_id: str
    candidate: str                 # full SHA
    result: ProbeResult            # produced in the implementer's environment

@dataclass(frozen=True)
class VerifiedProof:
    spec_id: str
    candidate: str
    implementer_result: ProbeResult
    verifier_result: ProbeResult   # independent environment, no shared state
    agreement: bool
    verdict: Verdict               # only SATISFIED/REFUTED when agreement is True
```

**Independence means three specific things**, each checkable rather than asserted:

1. **Environment independence** — the verifier's probe runs in a sandbox and worktree acquired by *its own*
   `StoryScope`, never one the implementer touched. Enforced structurally, as a scope property, not as a
   parameter someone might forget — which is the correction the harness's own hook-policy leak teaches
   (`packages/shell/bash-sandbox/src/index.ts:86`, see
   [`DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md`](DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md) §G.7).
2. **Instrument identity** — both results must carry the same `probe_id`, `probe_version` and `spec_hash`. A
   disagreement in any of those is not a disagreement about the product; it is a `PROBE_MISMATCH` and an
   integrity failure of the harness.
3. **Disagreement is never resolved in favour of either party.** `agreement == False` yields
   `INDETERMINATE`, owner `INTEGRATION`, and stops the story. It is never arbitrated by a model, and never
   settled by re-running until they agree.

---

## 8. Who verifies the verifier?

The owner's §20 asks this, and it is the question a proof architecture must answer or admit it cannot.

**Three mechanisms, none of which is the probe vouching for itself.**

**(a) Probe calibration — a probe must demonstrate it can say no.** For every ProofSpec, the harness holds a
calibration record showing the probe returning the *opposite* verdict at a known revision. For a `MUST_HOLD`
contract, that is the baseline where the behaviour is absent — which the admission measurement of §5 already
produces as a by-product. A probe that has never been observed to refute anything is not qualified to affirm
anything, and its ProofSpecs are inadmissible. This makes "a probe that passes everything" structurally
detectable instead of merely unlikely.

**(b) Mutation of the product, not of the probe.** The probe set is qualified by mutating the *product* and
requiring that each mutant be caught by at least one probe, with survivors audited and justified — the discipline
already applied to AISEF's kernel (871 mutants, 862 killed, 9 audited equivalents). A probe suite with survivors
in the behaviour it claims to cover is under-specified, and the survivor names exactly which contract is too
weak.

**(c) Invariants that a containment boundary cannot swallow.** Borrowed from
`packages/runtime-diagnostics/invariants/src/index.ts:50-66` and `settings/src/index.ts:833-841`: an invariant
violation carries the owning module's name and **every** `except` boundary in the kernel is required to re-raise
it. A probe cannot catch its own invariant violation and continue. Armed in every test run, as
`scripts/test-invariants.ts` does (`:60,125-205`), this turns the whole suite into invariant coverage.

**What remains unanswered, stated plainly.** None of the three protects against a *contract* that is faithful to
a *wrong requirement*. If the Behavior Contract asserts the wrong observable, every probe, calibration and
mutation below it will agree perfectly on the wrong thing. That residual is irreducibly human: it is why
`Requirement` carries authority, why `BehaviorContract.rationale` exists for review, and why contract review is a
human gate rather than a computed one. V2 should say so in the record rather than imply coverage it does not
have — the same honesty DeepSeek shows in the module comment that admits an accepted ancestor-symlink TOCTOU
(`packages/fs/fs-sandbox/src/index.ts:9-18`).

---

## 9. Falsification attempts against this design

Per §20, the obligation is to try to break the proposal, not to defend it.

**"The harness-owned probe is just a test the developer didn't write — you have moved the problem."**
Partly true, and the part that is true is the point. The problem moved from *an artefact the developer controls*
to *an artefact the harness controls and qualifies*. What makes that a real move rather than a relabelling is
§8(a): the probe must be observed refuting before it is trusted affirming, and the observation is the admission
measurement, not a claim. V1's developer tests had no such obligation and could not have one, because the
developer wrote them for the story they were proving.

**"Admission doubles the baseline cost of every plan."**
It does add one probe run per criterion at the baseline. Against V1's actual numbers that is trivially worth it:
run 1 of PLAN-V2 burned a developer session and six minutes to discover a `PLAN_OVERLAP` that admission computes
statically, and V2.1 run 1 burned 0/16 of a full run on a `PLAN_PRECONDITION_MISSING`. Admission also produces
the calibration records of §8(a) as a by-product, so its true marginal cost is lower than it looks.

**"`Subject.locator` is just a path — you have re-introduced file placement."**
This is the sharpest objection and it needs a hard answer. A locator names *the product's* addressable surface,
which is what the requirement is about, and it is authored in the contract under review — never chosen by the
implementing agent. The rule that makes this binding: **a contract's locator may not be changed by the story that
implements it.** If implementing a story requires moving the subject, that is a contract change, which requires
re-admission. Without that rule the objection lands.

**"`required_at_baseline` can be declared wrong."**
Yes — and then admission measures a mismatch and refuses the plan. That is the design working. The dangerous case
is declaring `required_at_baseline` to *match* a wrong measurement, i.e. writing the plan around what the baseline
happens to do. This is not detectable by the architecture and must be a review rule: the baseline expectation
follows from the contract's polarity and the story's position, and must be derivable without consulting a
measurement.

**"Two probe runs in two environments will disagree for environmental reasons, constantly."**
Likely, at first, and the design deliberately makes that loud: disagreement is `INDETERMINATE`/`INTEGRATION` and
stops the story rather than being averaged away. The mitigation is not tolerance but determinism —
`RunSpec` hashing, the deterministic child environment of
[`DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md`](DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md) §G.9, and enforcement levels
bound into the record. If disagreement stays common after that, the finding is that our environments are not
reproducible, which is worth knowing loudly rather than hiding in a retry.

**"This is more architecture than the problem needs."**
The honest test is whether each piece is traceable to a measured V1 defect. `BehaviorContract` and
harness-owned probes answer `FAM-PROOF-PLACEMENT` (PLAN-V2.1-DEFECT-001, measured). Admission answers
`FAM-PLAN-OWNERSHIP` (`PLAN_OVERLAP` and `PLAN_PRECONDITION_MISSING`, both measured). The typed `Verdict`
lattice answers `FAM-OUTCOME` and `FAM-TYPED-OUTCOMES` (SS-96, SS-92, measured). `spec_hash` and full-SHA
revisions answer `FAM-IDENTITY` and `FAM-EVIDENCE-SEMANTICS` (SS-81, measured). Calibration answers §20's
"who verifies the verifier". Nothing here is speculative generality — but the ordering in
[`AISEF-V2-QUALIFICATION-PROPOSAL.md`](AISEF-V2-QUALIFICATION-PROPOSAL.md) still applies: prove the semantics
before spending anything on scale.
