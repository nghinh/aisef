# AISEF V2 — RFC readiness

Board resolution §16, updated after **AISEF V2 — OWNER RESOLUTION OF RFC BLOCKERS** (owner decisions B1–B5 plus
the StaticPlanAdmission normalization).

---

## Verdict

# READY_FOR_OWNER_FREEZE

The five RFC blockers were resolved by owner decisions B1–B5 (§1). The owner approval review then found **four
blocking semantic / implementability defects**, all four are corrected in the RFC (§0), and the three required
reviews — consistency, implementability, simplification — pass with no unresolved contradiction and no circular
prerequisite.

The normative document is [`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md`](../../architecture/AISEF-V2-ARCHITECTURE-RFC.md).
It supersedes this and the other proposal documents for implementation decisions; they are design history.

---

## 0. Owner approval review — four defects corrected

All four were real. Two of them (A, C) were **polarity or absence errors of exactly the kind this architecture
exists to eliminate, reintroduced by me one layer down.**

### A · Contract satisfaction distinct from raw behaviour verdict

`StoryAdmission` routed directly on `BehaviorVerdict`, which is **inverted for every `MUST_NOT_HOLD`
contract**: `candidate_expectation` is `REFUTED` for a prohibition, so "`SATISFIED` at parent ⇒ `PRE_SATISFIED`"
was backwards. A prohibition that is *being violated* at the parent would have been recorded as already
satisfied.

Corrected: `ContractSatisfaction` = `SATISFIED` / `UNSATISFIED` / `INDETERMINATE`, **derived** as
`behavior_verdict == candidate_expectation` and never stored separately. Every planning decision routes on it.
`ParentExpectation` renamed to `UNSATISFIED_AT_PARENT` / `SATISFIED_AT_PARENT` / `UNCONSTRAINED`. Regression
case **NEG-1**.

### A2 · Negative-invariant absence was a blanket rule

"Every `MUST_NOT_HOLD` probe requires its subject to exist" is correct for *"the CLI MUST NOT write to stdout"*
and **wrong** for *"a forbidden file MUST NOT exist"*, where absence is the entire point.

Corrected: `SubjectAbsence` = `REQUIRES_SUBJECT` / `ABSENCE_IS_DECIDABLE`, declared per contract, bound into
`contract_hash` and `semantic_hash`, and **never inferred from polarity**. It applies to positive contracts too
(*"file X MUST exist"*). No new architecture plane. Regression cases **NEG-2**, **NEG-3**.

### B · Probe calibration was polarity-wrong and circular

Two defects. "Every spec must show `REFUTED`" would have **passed** a `MUST_NOT_HOLD` probe that always returns
`REFUTED` — a probe that can never fail a prohibition. And `StaticPlanAdmission` required every spec's
calibration before plan freeze while the RFC also said most such records come from `StoryAdmission`, which runs
only after plan freeze.

Corrected: calibration must demonstrate **contrast** to `candidate_expectation`, and it splits into
`ProbeCapabilityCalibration` (probe digest × observation class, committed positive **and** negative fixtures,
exists before any plan — required by `StaticPlanAdmission`) and `SpecFalsifiabilityEvidence` (per spec, produced
by Q2, **never** a plan-freeze prerequisite, required before a spec backs Q6 product evidence). Regression cases
**CAL-1**, **CAL-2**.

### C · Engineering test execution was boolean — this re-created SS-96

The draft mapped "tests do not execute" to `INADEQUATE` with owner `DEVELOPER`. That is the SS-96 shape exactly:
absence charged as a developer failure. It is the defect the whole architecture removes, reintroduced inside my
own adequacy gate.

Corrected with the same two-axis discipline used for probes: `TestExecutionStatus` (`EXECUTED` / `UNRUNNABLE`),
with `TestOutcome` and `TestSelection` defined only when `EXECUTED`. A missing runner is `ENVIRONMENT` with
environment retry — never `DEVELOPER`, never `INADEQUATE`, and never `INCOMPLETE`, because an `UNRUNNABLE`
mandatory execution is an environment outcome rather than a non-blocking quality result. A developer-authored
selection or collection defect is classified through `TestSelection`, not by prose; a collection failure whose
cause cannot be determined is owner `INTEGRATION`. **No "did not run ⇒ developer" path exists anywhere.**
Regression cases **TEST-1**, **TEST-2**.

### D · RunScope lifetime order

The draft made the `JournalWriter` the outermost boundary, so the run lease was released **before** the writer
closed — a second run could acquire ownership while the first was still writing.

Corrected: the **run lease** is the outer boundary. Begin: lease → `OPEN` sentinel (fsync) → `JournalWriter` →
`RunSpec` → execution. Shutdown: all StoryScopes disposed → `run/dispose-begin` → `run/end` → **writer closes
successfully** → sentinel `CLEAN` → **lease released last**. A failed writer close or an unrecordable `CLEAN`
leaves the sentinel `OPEN`, so the next run conservatively reports `TORN`. Regression cases **RUN-1**,
**RUN-2**.

### Freeze table

**No F12.** Five existing items adjusted mechanically: **F2** gains the `ContractSatisfaction` derivation;
**F4** gains `SubjectAbsence`; **F5** gains the two corrected calibration contracts; **F6** expresses
`ParentExpectation` as a contract-satisfaction expectation; **F8** gains the lease / sentinel / journal lifetime
order.

### Reviews

**Consistency** — no polarity inversion at any routing site, no circular prerequisite, and the three sites where
absence could be charged to a developer were each checked. **Implementability** — every prerequisite exists
before the operation requiring it, verified as a table; one classification rule (15.0.4) may be unavailable for
non-Python targets and falls back safely to owner `INTEGRATION`. **Simplification** — four types added, each
required by a named defect; defect D added none; nothing else added.

---

## 1. Blocker resolutions

### B1 · Candidate-side vacuity — **MODIFIED and accepted**

Not a boolean gate. A typed result: `NON_VACUOUS` / `VACUOUS` / `INDETERMINATE`.

`NON_VACUOUS` may be concluded **only** when the reconstructed candidate is runnable, the developer test harness
executes, the intended story-owned tests actually execute, and the failure is an assertion or behavioural failure
attributable to removing the story's product changes. Collection failure, import failure, invalid reconstruction,
tool failure and environment failure are all `INDETERMINATE` and are **never** proof of non-vacuity. Tests that
execute and still pass after neutralisation are `VACUOUS`.

**The owner's framing dissolves my original concern.** I raised B1 because dropping RED-at-parent appeared to
leave the SS-81 family unguarded. That was true of V1's architecture and is not true of V2's:
**SS-81-style false PRODUCT assurance is structurally removed because `DeveloperTests` no longer decide
`ProductProof`.** A vacuous developer test can no longer certify a behaviour, because it certifies nothing. The
vacuity control is therefore **engineering-quality evidence only**, `VACUOUS` may block
`EngineeringTestAdequacy` under policy, and `INDETERMINATE` is incomplete engineering evidence — never a product
failure.

### B2 · Test relevance — **MODIFIED and accepted**

"Changed line **and** changed branch" is rejected as universal, because branch coverage is not defined for every
valid change. A typed result: `RELEVANT` / `IRRELEVANT` / `UNMEASURABLE`.

Cycle-1 minimum: `RELEVANT` when at least one **actually executed** story-owned developer test intersects at
least one **executable** changed line of the story diff. Branch intersection is recorded as stronger evidence
where the capability exists and the changed code has instrumentable branches, but is not required. Non-line-
addressable artefacts use a capability-specific measurement. Where the measurement capability is absent or
`PARTIAL`, the result is `UNMEASURABLE`.

**Capability absence is never converted into `IRRELEVANT`.** That is `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE`
applied to the relevance measurement itself, and it is the same rule that B1 applies to vacuity.

### B3 · Identity grade — **accepted, extended to three grades**

`VERIFIED` / `ATTESTED` / `OPAQUE`, frozen.

`OPAQUE` is the addition and it is the one that matters operationally: an implementation that may change behind a
route, such as a dynamic model-combo route. It is permitted for development and regression work and **must not**
support Q6 qualification, sealed evaluation cohorts, or generalization claims.

**Comparability requires all three of:** the same resolved capability identity tuple, the same `IdentityGrade`,
and the same enforcement identity. Same grade alone is insufficient — this is stricter than my proposal, which
compared on grade alone.

### B4 · Terminal sink — **accepted, refined to `RunTerminationSentinel`**

The refinement is **better than what I proposed and fixes a real weakness in it.** My design recorded failure,
which makes correctness depend on successfully writing a record *after* a failure has already occurred — exactly
when writing is least likely to work.

The owner's inversion records **success**: an `OPEN` sentinel is created and fsync'd before execution proceeds,
and is marked `CLEAN` only after every `StoryScope` has disposed and the journal's `run/end` is durably written.
Absence of `CLEAN` is therefore the signal, and it requires nothing to be written at failure time. A best-effort
`FAILED{stage,error}` record may still be written, but no correctness property depends on it.

The sentinel is **not evidence and not authoritative state**. The journal remains the sole authority for run
state, and no gate may cite the sentinel as product, plan or qualification evidence. It answers exactly one
question: *was clean termination durably observed outside the journal?*

### B5 · Plan drift — **accepted as `PlanQualityPolicy`, no global percentage**

No universal framework-level threshold. A `PlanQualityPolicy` carries at minimum
`max_pre_satisfied_introduce_ratio`, `max_fully_pre_satisfied_stories` and `max_unattributed_plan_drift`.

`delivery_verdict` and `plan_quality_verdict` are **separate and the separation is mandatory**: a project may
have `delivery = PASS` with `plan_quality = FAIL`. Ordinary execution records and reports `PLAN_DRIFT`.
Qualification and sealed evaluation **must preregister** thresholds before results are observed, and a
qualification with no preregistered plan-quality thresholds **may make no claim that the plan was qualified**.

---

## 2. New-contradiction check

The owner authorised `READY_FOR_RFC` "unless a NEW architectural contradiction is discovered". One interaction
required resolution; it resolved without a contradiction, and two candidates were checked and cleared.

**Interaction found — where do `INDETERMINATE` and `UNMEASURABLE` land?** B1 and B2 each introduce a
third value that is neither pass nor fail, and B1 states `INDETERMINATE` is "never product failure". So
`EngineeringTestAdequacy` cannot be a boolean either. Resolution, without a new verdict axis:

- `EngineeringTestAdequacy` produces `ADEQUATE` / `INADEQUATE` / `INCOMPLETE`.
- `INADEQUATE` (tests fail, `VACUOUS`, or `IRRELEVANT`) may block under policy, owner `DEVELOPER`.
- `INCOMPLETE` (`INDETERMINATE` or `UNMEASURABLE`) **never blocks and is never charged to the developer**; it is
  recorded and reported as a reduction in engineering-quality coverage.

I considered adding an `engineering_quality_verdict` alongside `delivery_verdict` and `plan_quality_verdict`, and
rejected it under the simplification rule: removing it makes no measured defect expressible again, because the
components are already recorded per story and no gate needs a third aggregate.

**Cleared — `9router/ds/deepseek-v4-pro` under B3.** V1's W1 profiles used a fixed model route on a router. That
grades `ATTESTED`, not `OPAQUE`: provider, endpoint, declared model id, fixed route, adapter identity and a
preflight fingerprint are all bindable. So a future W1-equivalent remains Q6-eligible. A `mycombo`-style dynamic
combination route grades `OPAQUE` and is excluded from Q6 — which is a real restriction on route choice, and it
is correct.

**Cleared — Q0 and project admission.** The owner's normalization separates
`StaticPlanAdmissionEngine` (qualified by Q0/Q1) from `StaticPlanAdmissionResult` (produced by a project at plan
time, before plan freeze). Q0 never executes a project's admission. Applied throughout.

---

## 3. Items that remain RFC responsibilities, not blockers

Unchanged from the previous pass, and explicitly **not** blockers: the probe taxonomy per `Subject.kind`;
`PLAN_DRIFT` attribution tie-breaks; journal compaction and retention; Windows equivalents for measured range
emptiness and OS-level teardown assertions; the V1 proof-mode migration table; and where probes live relative to
the product tree. Each is an implementation decision the RFC records and the implementation settles.
