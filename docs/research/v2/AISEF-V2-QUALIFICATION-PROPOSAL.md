# AISEF V2 — qualification proposal

Owner decisions §13 (the Q0–Q6 ladder) and §14 (LedgerLock's classification). A design proposal; nothing here
has been built.

The governing rule is the owner's: **do not put expensive qualification before semantic correctness has been
proven.** V1's own history is the argument. Run 1 of PLAN-V2 spent a developer session and six minutes of a
paid run to discover `AC-STORY-04-01-2` was `PLAN_OVERLAP`. V2.1 run 1 spent 0/16 of a full run discovering
`PLAN_PRECONDITION_MISSING`. Both are rows in a table computable from the frozen baseline at zero cost
([`AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md`](AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md) §5). The ladder exists to
make that ordering structural rather than a matter of judgement under schedule pressure.

---

## 1. The ladder

Each rung states what it proves, what it costs, and **what it refuses to run without**. A rung may not be
attempted while a lower rung is failing — that is the whole point of the ordering, and it should be enforced by
the harness, not by discipline.

### Q0 — Static admissibility · seconds · no execution

**Proves:** the artefacts are internally consistent and the plan is admissible.

- Every `ProofSpec` is the canonical derivation of its `BehaviorContract`, verified `--check` style against the
  committed artefact — the pattern of DeepSeek's nine `verify-*-catalog` gates
  (`scripts/gen-cordis-catalog.ts:1167-1192`).
- Catalogs are **fail-closed in both directions**: something present in reality but absent from the catalog, and
  something in the catalog no longer present, are both hard errors (`gen-cordis-catalog.ts:55-59`). Applied to
  the invariant register, the criterion→behaviour ownership map, the fault matrix and the capability registry.
- **Plan admission**: every criterion carries a measured baseline verdict equal to its declared
  `required_at_baseline`; any `PLAN_OVERLAP` or `PLAN_PRECONDITION_MISSING` row refuses the plan.
- Static verification of the run specification: expressions only in declared interpolation positions, parse-only
  checking without execution, no credential material inline — the three checks of
  `scripts/verify-cordis-config.ts:503-544` and `scripts/verify-config-source-ownership.ts:23`.
- Provenance guards: a frozen artefact cannot change without its manifest in the same commit
  (`scripts/check-vendor-manifest.sh`).

**Refuses to run without:** nothing. Q0 is the floor.

**Precondition on the checkers themselves.** Every Q0 checker must have been **observed failing on a known-bad
input** before it is trusted to pass anything, and the checker set carries its own mutation budget. This is the
same obligation Q2 places on probes, and for the same reason: a checker that cannot be observed refusing is a
cheap, fast, invisible source of false assurance. The calibration inputs are committed fixtures, and a checker
whose calibration fixture no longer fails it is itself a Q0 failure.

*This precondition was added by the adversarial review — see
[`AISEF-V2-ARCHITECTURE-RECOMMENDATION.md`](AISEF-V2-ARCHITECTURE-RECOMMENDATION.md) §20, change 3. The original
proposal had no mitigation for a wrong checker, which the review identified as a real gap.*

**Why this rung is new.** V1 had no Q0. The ownership audit and the plan audit existed but ran as one-off
scripts, and the admission measurement did not exist at all.

### Q1 — Semantic conformance · minutes · offline, deterministic

**Proves:** the kernel's decisions match the approved policy, not merely its own past behaviour.

- The reference model implements the **owner's policy**, independently of the kernel. V1 learned this the
  expensive way: the first conformance model mirrored the kernel, so it reported 0 mismatches while SS-96 was
  live. The owner's correction stands as a rule: *the reference model must implement the approved owner policy,
  not mirror the current kernel behavior*, and the model must be mechanically prevented from importing kernel
  decision modules (V1 asserted this with an AST check; keep it).
- Targeted scenarios over the real kernel, comparing per-criterion decision, failure owner, typed outcome, retry
  target, developer budget, environment budget, terminal class and evidence freshness.
- **The from-scratch fold oracle**: incremental state must equal `fold(journal_prefix)` at every decision point
  (`packages/core/session/tests/derived-cache.spec.ts:17-27`). AISEF asserts this nowhere today.
- **Invariants armed in every test**, in-process, before anything else mounts
  (`scripts/test-invariants.ts:60,125-205`), and **uncontainable** — every `except` boundary re-raises them
  (`packages/runtime-diagnostics/invariants/src/index.ts:50-66`;
  `packages/settings/settings/src/index.ts:833-841`).

**Refuses to run without:** Q0 green.

### Q2 — Adequacy · hours · offline

**Proves:** the checks are strong enough to notice if the product were wrong.

- **Mutation of the product**, with every survivor either killed by a new meaningful assertion or recorded as an
  audited equivalent carrying a justification. V1's standard — 871 generated, 862 killed, 9 audited — is the
  bar, and the owner's rule holds: *do not classify message-only mutations as equivalent if the message itself is
  part of the structured gate-feedback contract.*
- **Probe calibration**: every `ProofSpec`'s probe must have been *observed refuting* at a known revision before
  it is trusted to affirm. Q0's admission measurement produces most of these as a by-product. A probe never
  observed to say no is inadmissible.

**Refuses to run without:** Q1 green.

### Q3 — Fault behaviour · hours · offline, no money

**Proves:** the typed-outcome and ownership routing is right under failure, not only under success.

- A **local fault-injection provider** with named behaviours, modelled on
  `packages/test-support/llm-mock-server/src/index.ts:16-41` (24 behaviours: connection reset, stream
  disconnect, partial EOF, stall, malformed event, rate limit, auth error, context overflow, quota…). This is
  the rung that converts `FAM-PROVIDER` from expensive hand-diagnosed live evidence into deterministic offline
  evidence. Copy the honesty label too: a weighted profile is "configurable test pressure, **not a claim about
  production incident frequency**" (`:56-68`).
- Tool, sandbox and environment faults, including missing tools, unrunnable scanners, and a capability reporting
  `PARTIAL`.
- **Interruption and crash repair**: synthetic closers must be typed (`OUTCOME_UNKNOWN` vs `NOT_STARTED`),
  deterministic (timestamps reused) and idempotent — repairing the same journal twice must be byte-identical
  (`packages/core/session/src/repair.ts:87-88,119-133`).
- **Disposal failures**, asserted against the OS: `kill(pid,0)`/`ESRCH` liveness and `existsSync` on temp
  directories after both abort and terminate
  (`packages/subprocess/subprocess-local/tests/process-exit.spec.ts:20-55`;
  `linux-scope.spec.ts:250-260`). This is the only evidence that actually discriminates an orphan.

**Refuses to run without:** Q2 green.

### Q4 — Differential at scale · ~6 hours on 8 workers · offline

**Proves:** the conformance of Q1 holds across the reachable state space, not only on chosen scenarios.

100 000 generated traces compared against the reference model; the exit criteria are V1's and they were met:
0 unexplained divergences, 0 invariant violations, 0 exceptions, 0 silent skips, one kernel digest, contiguous
non-overlapping seed ranges, and full coverage of reachable states, fault kinds and compound pairs.

**Refuses to run without:** Q3 green. And — V1's rule, kept — a kernel change at any point invalidates a
completed Q4 and requires a fresh one from scratch.

### Q5 — Real-execution reproduction · minutes to hours · no provider spend

**Proves:** the whole system, running for real, reproduces recorded behaviour — with the model as the only
substituted component.

- **Only the model stream is replayed.** Tools, subprocesses, the filesystem and the sandbox are real
  (`packages/test-support/llm-replay/src/index.ts:1095-1097`;
  `packages/test-support/session-snapshot/src/launcher.ts:136-143`).
- **Recorded tool results are never replayed** — they are re-executed and diffed
  (`llm-replay/src/index.ts:458-499`). A system checked against its own recorded tool output is certifying
  itself. The final workspace state is part of the comparison
  (`session-snapshot/src/workspace.ts:47-71`).
- **Request-header class pinning with a bounded drift budget**, and the forcing rule that session-dependent
  composition must declare a separate class instead of quietly widening one
  (`session-snapshot/src/manifest.ts:12-52`; `suite.ts:10-17`). What we send the model is the largest
  uncontrolled variable in every AISEF run; this is the control for it.
- **`assertConsumed`** — a reproduction that bound fewer sessions or drove a different number of model calls
  than recorded fails, rather than scoring as the same run (`llm-replay/src/index.ts:1100-1114`).
- Determinism by **normalization after the fact**, not by faking the clock: zero the timestamps and durations,
  tokenize cwd (including the macOS `/private` alias), session ids and spill paths, and strip ambient proxy
  variables so a local proxy cannot decide an outcome
  (`session-snapshot/src/normalize.ts:162-199,341-378`; `scripts/test-proxy-environment.ts:1-23`).

**One correction to their design, not to be copied.** Their replay binds scripts **by call order, not by request
matching** (`llm-replay/src/index.ts:1030-1061`), so a materially changed request that still makes the same
number of calls can bind the same scripts. If AISEF replays provider output, bind by a **hash of the request**.
Keep `assertConsumed` and the header-class pinning regardless; they are what makes their positional scheme
survivable.

**Refuses to run without:** Q4 green.

### Q6 — Live delivery qualification · real money · the only rung that spends

**Proves:** a specific model, on a specific workload, under a frozen kernel and an admitted plan, completes
delivery.

Preconditions, all of them: Q0–Q5 green on the exact candidate; kernel frozen with tree and wheel digests
recorded; plan frozen with a complete admission table; execution profile resolved and **content-hashed** —
not name-identified, which is where DeepSeek's profile model is weaker than ours and must stay so
(`packages/boot/app-boot/src/profile.ts:5-14,79`); provider preflight passing on the exact fixed route.

The profile hash must include **the capability enforcement levels actually resolved** (`FULL` / `PARTIAL` /
`UNAVAILABLE`), so a run qualified under partial sandboxing can never be compared with one under full
enforcement. *Added by the adversarial review — see
[`AISEF-V2-ARCHITECTURE-RECOMMENDATION.md`](AISEF-V2-ARCHITECTURE-RECOMMENDATION.md) §20, change 2.*

**What Q6 can and cannot conclude.** It can conclude that *this* model, on *this* workload, did or did not
deliver. It cannot conclude anything about models or workloads it did not run — and V1's final verdict already
separated those two claims correctly: the assurance kernel was QUALIFIED while W1 delivery qualification was
NOT REACHED and not reachable from that workload. Keep that separation as a structural property of the verdict
record, with `assurance_kernel` and `delivery` as distinct fields that cannot be collapsed into one headline.

---

## 2. Cost ordering, stated as the property to preserve

| rung | wall clock | provider spend | may be re-run freely |
|---|---|---|---|
| Q0 | seconds | none | yes |
| Q1 | minutes | none | yes |
| Q2 | hours | none | yes |
| Q3 | hours | none | yes |
| Q4 | ~6 h / 8 workers | none | yes |
| Q5 | minutes–hours | none | yes |
| Q6 | hours | **real** | **no — see §3** |

Everything through Q5 is free of provider cost. That is not an accident of the design; it is the design. The
single most valuable thing Q3 buys is moving `FAM-PROVIDER` — which cost this programme two abandoned profiles
and three unexplained tool-smoke timeouts — out of Q6 and into a rung that costs nothing and is deterministic.

---

## 3. LedgerLock's classification (§14)

**LedgerLock is a DEVELOPMENT / REGRESSION BENCHMARK. It is not a final unseen holdout benchmark. This
classification must be preserved.**

It is not a judgement call, it is a fact about what was done, and the record says so:

- The workload has been run repeatedly across many profiles — `deepseek-ro-1/2`, `minimax-ro-1/2`,
  `gpt55-ro-1`, `gpt56sol-ro-1`, `v21-run1`, `v21-run2` and more.
- Its **plan was revised in response to run outcomes**: PLAN-V2 → PLAN-V2.1, after diagnostic run 1 stopped on
  `AC-STORY-04-01-2`.
- The ownership audit that produced PLAN-V2.1 was performed **with knowledge of observed model behaviour** —
  the owner explicitly fenced this ("no mode change based solely on observed model output"), which is precisely
  the fence you need when a workload is no longer unseen. My own audit error is on record here: I judged
  `AC-STORY-01-01-4/-5` KEEP_CHANGE partly on the diagnostic run's green measurement, and run 1 falsified that
  within six minutes.

None of that is misconduct. It is the ordinary, correct use of a development benchmark — and it is exactly what
makes it unusable as a holdout. A benchmark you have tuned against measures your tuning.

### Enforcing the classification mechanically

A classification that lives in a document drifts. Make it a field with a guard:

```python
class WorkloadRole(Enum):
    DEVELOPMENT = "DEVELOPMENT"   # may be run, inspected, and planned against, without limit
    HOLDOUT     = "HOLDOUT"       # sealed; consumed once; any second use demotes it

@dataclass(frozen=True)
class WorkloadRegistration:
    id: str
    role: WorkloadRole
    content_hash: str            # seals a HOLDOUT
    runs: tuple[str, ...]        # every run id that has ever touched it
    demoted_from: str | None     # set when a HOLDOUT is re-used
```

Three rules:

1. **A `HOLDOUT` is consumed once.** A second run against it rewrites `role` to `DEVELOPMENT`, records
   `demoted_from`, and emits the change to the journal. Demotion is automatic and irreversible; nobody has to
   remember.
2. **Inspecting a `HOLDOUT`'s contents, or planning against it, demotes it** — the same rule, because reading it
   is how contamination happens.
3. **A generalization claim may cite only `HOLDOUT` evidence.** A qualification verdict that cites a
   `DEVELOPMENT` workload may claim regression coverage and nothing more, and the verdict record must say which
   role backed it.

This is the bidirectional fail-closed rule of Q0 applied to benchmarks: a claim without holdout evidence and a
holdout with more than one run are both errors.

### What a holdout would have to be

If AISEF ever wants a generalization claim, it needs a workload that has **never** been used to choose a
proof mode, a plan structure, a profile, a prompt or a retry budget. Given how V1 proceeded, no existing AISEF
workload qualifies, and no amount of re-labelling creates one. That is a cost to be paid deliberately in a
future cycle, not a gap to be quietly reclassified — and it should be recorded now, before anyone needs the
answer to be different.
