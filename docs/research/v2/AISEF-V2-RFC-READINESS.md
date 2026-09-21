# AISEF V2 — RFC readiness

Board resolution §16, updated after **AISEF V2 — OWNER RESOLUTION OF RFC BLOCKERS** (owner decisions B1–B5 plus
the StaticPlanAdmission normalization).

---

## Verdict

# READY_FOR_RFC

All five blockers are resolved by owner decision. **No new architectural contradiction was found** while
applying them — the check performed is recorded in §2 below, including the one place the decisions interact and
how that interaction resolves.

The final RFC is at [`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md`](../../architecture/AISEF-V2-ARCHITECTURE-RFC.md)
and supersedes this and the other proposal documents for implementation decisions. They are retained as design
history.

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
