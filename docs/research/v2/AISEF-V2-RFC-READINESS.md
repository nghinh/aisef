# AISEF V2 — RFC readiness

Board resolution §16. Verdict on whether the architecture is ready for the final RFC to be written.

---

## Verdict

# NOT_READY_FOR_RFC

**Five blockers, all of them owner decisions that this correction pass surfaced.** None is research; none
requires another study. Each is stated with a recommended answer, so the review is cheap.

The reason for a negative verdict rather than a conditional green one: three of the five are design decisions I
made or qualified inside this pass, not decisions the board issued. An RFC written on unapproved design
decisions is precisely the "ProofSpec becomes another plan artefact that is wrong" failure, one level up. The
board asked what is unresolved; these are.

---

## Blockers

### B1 · The candidate-side vacuity control (board §5) — my proposal, unapproved

**What.** Dropping RED-at-parent removes the signal that caught `FAM-EVIDENCE-SEMANTICS` (SS-81): tests that
pass against an empty implementation. I propose replacing it with a **candidate-side** control — neutralise the
story's own product hunks in a scratch copy of the candidate, keep the developer's test files intact, run them,
require failure.

**Why it blocks.** It is a new gate in cycle 1 and it is mine, not the board's. If it is rejected, the honest
consequence must be recorded in the RFC: **the SS-81 family is unguarded in cycle 1** until engineering-test
sensitivity lands, and sensitivity is currently deferred.

**Recommendation.** Accept. Cost is one extra test run per story, it depends on no parent-side file topology,
and it preserves a measured protection.

### B2 · The mechanical definition of test "relevance" (board §5)

**What.** The board's adequacy gate includes "tests are relevant to changed behavior". As written that is prose,
and prose in a control position violates invariant VII. I propose: *relevance holds when the story's tests cover
at least one changed line **and** at least one changed branch of the story's own diff, by coverage intersection
against the diff hunks.*

**Why it blocks.** Whatever the definition is, it decides a gate, so it must be fixed before interfaces freeze.

**Recommendation.** Accept the coverage-intersection definition for cycle 1; revisit when sensitivity testing
lands, at which point sensitivity subsumes it.

### B3 · `IdentityGrade` — `VERIFIED` vs `ATTESTED` (board §10)

**What.** The board requires content-addressed capability identity. Some identities cannot be content-addressed
from our side — a hosted model's weights being the obvious case. I propose grading each capability `VERIFIED`
(digest computed locally) or `ATTESTED` (remote self-report plus a locally measured preflight fingerprint), with
a `RunSpec` carrying the minimum grade and every verdict stating it.

**Why it blocks.** This *qualifies* the correction as issued. Either the board accepts the boundary, or it must
say what a content address for a hosted model would mean.

**Recommendation.** Accept. Declaring a weaker real identity is the same principle as declaring `partial`
sandbox enforcement rather than claiming full.

### B4 · The terminal sink (board §8)

**What.** The board asks what records `RunScope`'s own teardown failure. I propose a separate, tiny, append-only,
fsync'd file owned by `RunScope`, written with minimal machinery that shares no code with the journal, holding
only `terminal/ok` and `terminal/failure{stage, error}`; plus a `run/dispose-begin` marker in the journal; plus a
next-run preflight obligation to report `TORN` runs.

**Why it blocks.** It introduces a second durable artefact outside the journal, which cuts against "the journal
is the only authority". The cut is deliberate and narrow, but it is an architectural exception and needs
approval rather than assumption.

**Recommendation.** Accept, with the exception stated explicitly in the RFC: the terminal sink is **not**
evidence and may never be cited by a gate; it exists solely so that a journal failure is detectable.

### B5 · A plan-drift budget (new open question, created by board §3)

**What.** `PRE_SATISFIED` correctly stops a plan defect from failing delivery, and records `PLAN_DRIFT` instead.
The consequence is new: **a plan can now be substantially wrong while every story succeeds.** There is no
threshold at which accumulated drift means the plan itself failed.

**Why it blocks.** Without a threshold, plan quality is observable but not qualifiable, and "the plan was good"
becomes an unfalsifiable claim. This is a direct side effect of a correction and it should not be discovered
after implementation.

**Recommendation.** Define a drift budget per plan before the RFC — a simple first form: a plan fails
plan-quality qualification when `PRE_SATISFIED` obligations exceed *k%* of `INTRODUCE` obligations, or when any
single story is fully `PRE_SATISFIED`. The values are the board's to set; the *existence* of a threshold is the
architectural decision.

---

## Open items that do **not** block the RFC

These belong in the RFC's own scope and can be settled while writing it.

1. **Probe taxonomy** — which probe kinds exist for each `Subject.kind` (`python_callable`, `cli_invocation`,
   `http_route`, `file_artifact`, `process_effect`), and their observation-harness definitions.
2. **`PLAN_DRIFT` attribution** when the dependency DAG admits more than one candidate introducer; `UNATTRIBUTED`
   is defined as the fallback, but the tie-break rule is not.
3. **Journal compaction** — shadowing events are specified; retention and the compaction trigger are not.
4. **Windows equivalents** for measured range emptiness and OS-level teardown assertions. The mechanisms exist
   (Job objects, `TerminateJobObject`, `isJobEmpty`); the mapping is unwritten. Windows is a real constraint for
   this project and the RFC must not defer it silently.
5. **V1 proof-mode migration table** — `CHANGE_REQUIRED` / `PRESERVE_REQUIRED` / `NEGATIVE_INVARIANT` →
   `ObligationRole` + `Polarity`. The mapping is mechanical; it must be generated and `--check`ed, not
   hand-written.
6. **Where probes live** relative to the product tree, and how a probe change is qualified without invalidating
   accumulated product evidence.

---

## Architecture items proposed for freeze

Frozen means: changing it later invalidates evidence written under it. Each needs owner sign-off before
implementation begins.

| # | Item | Why it must freeze |
|---|---|---|
| F1 | `Event` envelope and the event vocabulary | Every journal is written under it |
| F2 | `ProbeExecutionStatus` × `BehaviorVerdict` product, its six legal states, and the owner routing table | Everything routes on it; `UNRESOLVABLE` is deleted |
| F3 | The `Owner` set (PLAN, DEVELOPER, ENVIRONMENT, PROVIDER, REVIEW, SECURITY, INTEGRATION) — **capped**; a new member requires a cited measured defect | Budgets and retries derive from it |
| F4 | `BehaviorContract` → `ProductProofSpec` compiler contract, and the inputs to `semantic_hash` | It is what `--check` compares against, and what makes product evidence survive re-planning |
| F5 | `Probe` protocol: the observation-harness / subject split, `enforcement()`, `ProbeResult` fields | The split is what keeps product absence out of the environment budget |
| F6 | `PlanObligation` shape, `ObligationRole`, `ParentExpectation` | The planning plane's entire vocabulary |
| F7 | `StoryAdmissionDisposition` set | The gate ordering and budget routing depend on it |
| F8 | `RunScope` / `StoryScope` ownership split and the disposal ordering contract | Correcting it later re-parents every resource |
| F9 | The four cited identities (`semantic_hash`, `plan_hash`, revision SHAs, `runspec_hash`) | Comparability of every verdict |
| F10 | Invariants **I–IX**, each with its named enforcement mechanism | An invariant without a mechanism is the A5 anti-pattern |
| F11 | The six control-critical projections, as a **closed** list | Only these may be cited by a gate |

Invariant IX is new in this pass: **no developer artefact is executed at the parent revision.** It is the
clean statement of what corrections §1, §2 and §5 achieve together, and it is the invariant that makes
PLAN-V2.1-DEFECT-001 unrepeatable.

---

## What would move this to READY_FOR_RFC

Five decisions: B1, B2, B3, B4 accepted or replaced, and B5's threshold *existence* agreed. Nothing else is
outstanding. No further external research is needed, and no further study of DeepSeek Harness or Cordis would
change any of the five — all five are AISEF-specific and lie in the design space that study showed the external
system does not occupy.
