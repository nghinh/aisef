# AISEF V2 — architecture recommendation

Owner decisions §6 (evaluate the 20 proposed V2 concepts), §8 (do not copy blindly), §9 (anti-patterns),
§17 (A–L), §18 (top-level invariants) and §20 (adversarial self-review).

Evidence: [`DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md`](DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md),
[`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md),
[`V1-DEFECT-FAMILY-REGISTER.md`](V1-DEFECT-FAMILY-REGISTER.md),
[`AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md`](AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md),
[`AISEF-V2-EXTERNAL-ARCHITECTURE-MATRIX.md`](AISEF-V2-EXTERNAL-ARCHITECTURE-MATRIX.md). Pattern ids `P01`–`P40`
are defined in the defects-vs-patterns document §1.

This is a recommendation. Nothing here has been implemented, and §21 of the owner decision applies: no RFC, no
V2 code.

---

# §6 — The 20 proposed V2 concepts

Each answers the owner's six questions. "Unrelated" means DeepSeek Harness does not occupy the problem space —
which is itself a finding, not a gap in the study.

### 1. Requirement Authority
**Confirmed?** By analogy only. **Contradicted?** No. **Improved?** Yes, by one rule worth stealing: an agent
preset's trust "comes from the root a preset was discovered under … otherwise a locally authored preset could
claim to be a shipped one" (`packages/preset/agent-presets/src/metadata.ts:11-14`). Authority derives from
*where a thing was admitted*, never from what it says about itself.
**Borrow:** discovery-root trust. **Risks:** requirements are prose; without a hard rule that no control path
reads `Requirement.text`, authority silently becomes control state. Enforce it as a static check (§Q0), not a
convention.

### 2. Behavior Contract
**Confirmed?** No counterpart exists. **Contradicted?** No. **Improved?** Structurally: schemastery validation
turns raw config into a validated value *before* activation (`vendor/cordis/src/fiber.ts:41-61`) — the same
raw → validated → frozen shape a contract needs. **Borrow:** validate-then-freeze, and reject async validation
so the admission point is determinate. **Risks:** (a) a contract faithful to a *wrong* requirement is
undetectable by anything below it; (b) contract sprawl — one per assertion is not obviously the right
granularity; (c) `Subject.locator` re-introducing file placement unless a story is forbidden from moving the
subject it implements.

### 3. Canonical ProofSpec
**Confirmed?** Yes, by the strongest available analogue: nine generated catalogs each with a `--check` twin that
diffs byte-for-byte, and a table that is **fail-closed in both directions**
(`scripts/gen-cordis-catalog.ts:55-59,1167-1192`). **Improved?** Yes — derive the spec, commit it, and let drift
fail the build. **Borrow:** P24 wholesale. **Risks:** the owner's own §20 question — a ProofSpec is just another
plan artefact and can be wrong. The only real answers are plan admission (measure the baseline) and probe
calibration (§8 below); neither is optional.

### 4. Harness-owned deterministic probes
**Confirmed?** Yes in spirit. DeepSeek's primary filesystem control is a **harness-owned pre-write fence**, not a
post-hoc diff (`packages/fs/fs-sandbox/src/index.ts:122-144`), and capabilities declare `partial` enforcement
rather than claiming success (`packages/sandbox/sandbox-local/src/index.ts:181-186,233-237`).
**Borrow:** the declared enforcement level, bound into the record. **Risks:** the probe suite becomes a second
product with its own defects; a probe that always affirms is invisible without calibration; probe/product
coupling can drift silently.

### 5. Proof semantics independent of developer tests
**Confirmed?** Unrelated — and this is the study's most important negative result. DeepSeek has no proof
obligations and no claim evaluated at two revisions, so `FAM-PROOF-PLACEMENT` has no external analogue
(see defects-vs-patterns §3.19). **Borrow:** nothing. **Risks:** the locator objection of concept 2; and the
temptation to treat harness probes as "tests the developer didn't write", which is a relabelling unless
calibration makes it real.

### 6. Product correctness vs plan/process correctness separation
**Confirmed?** Yes, three times independently: "did not run" checked before "was denied"
(`packages/shell/bash-sandbox/src/index.ts:119-123`); disposal failures kept distinct from result failures and
aggregated only when both fail (`packages/subagent/tool-subagent/src/index.ts:226-237`); invariant violations
separated from ordinary errors and made uncontainable
(`packages/settings/settings/src/index.ts:833-841`). **Improved?** Yes — all three are the same move at
different layers. **Risks:** separation multiplies terminal states. Keep the outcome lattice small and require
every new terminal to cite a measured defect.

### 7. Event-sourced story execution
**Confirmed?** Strongly and in detail — the log is the only authority, every read model a pure fold, the one
durable cache explicitly disclaimed (`packages/session/session-projection-cache/src/index.ts:9-14`).
**Contradicted?** In one specific place: their event **bus** carries control (a `waterfall` listener can veto
built-in behavior by not calling `next()`, and `agent/request-error` decides retry that way —
`vendor/cordis/src/events.ts:224-242`; `packages/core/agent-loop/src/agent.ts:448-464`). Adopt the log, reject
the bus. **Borrow:** P14–P19 entire. **Risks:** journal growth; a single-writer constraint imposed by dense
`seq`; projection cost over long journals.

### 8. Story Transaction
**Confirmed?** Yes — a child scope is an effect of its parent, so ownership is one tree and disposal is
transitive (`vendor/cordis/src/fiber.ts:265`). **Improved?** Yes, by two corrections *we* must make: their
sibling disposal is concurrent (`fiber.ts:675-684`) and swallows failures into a logger. **Borrow:** labelled
effects, refusal to acquire during teardown, graceful-first ladder, child-first drain, range-emptiness.
**Risks:** a hard-killed harness still leaks; ordered disposal is a discipline in the stack, not a property of
the type system.

### 9. Typed retry budgets
**Confirmed?** Half. Retryability as a property of the **code taxonomy** is confirmed and improved:
`DEFAULT_RETRYABLE_CODES`, and `MISSING_CREDENTIAL` split from `INVALID_CREDENTIAL` "because the fix differs",
the latter deliberately non-retryable (`packages/llm/llm/src/error.ts:41-48`). That is D-006 made
unexpressible. **Contradicted?** No — but they have **no owner concept at all** (harness study §J.5), so
*budgets by owner* is ours alone and has no external validation. **Risks:** owner mis-assignment simply moves
the mis-charge; typed ownership is only as good as the assignment rule.

### 10. Immutable Evidence Bundle
**Confirmed?** Yes — the persistence seam has no update and no delete verb at all
(`packages/session/session-persistence/src/index.ts:147-198`), logical deletion is a new shadowing event, and
provenance is enforced at commit time (`scripts/check-vendor-manifest.sh`). **Borrow:** P14, P37.
**Risks:** unbounded growth; compaction must be a shadowing event, never a rewrite, or immutability is theatre.

### 11. Read-only reviewer / security execution
**Confirmed?** Yes — deployment default `read-only`, per-call policy so different actors run at different modes
simultaneously, subagent approval pinned to `'never'`, authority only narrows
(`packages/sandbox/sandbox-policy/src/index.ts:113,164-171`;
`packages/subagent/subagent/src/child-agent.ts:229-252`). **Contradicted?** Partially, and instructively: their
hook path passes **no** policy, so hooks silently run at the deployment default and the fallback workspace root
(`packages/shell/bash-sandbox/src/index.ts:86`). Borrow the property; reject the optional-parameter mechanism —
derive confinement from the scope. **Risks:** their `read-only` is **filesystem-only**; network is unconfined
(harness study §G.10). Any AISEF read-only claim must name the weakest path that could violate it.

### 12. Post-merge canonical verification
**Confirmed?** Unrelated — no merge concept. Nearest analogue: the snapshot suite compares the **final workspace
state**, not only the log (`packages/test-support/session-snapshot/src/workspace.ts:47-71`).
**Risks:** this is where SS-95 lived — "false BLOCK = 0" was measured only at trunk, but a blocked story's code
never reaches trunk, so the metric could not discriminate. Post-merge verification is valid for *integration*
claims and invalid for *refusal-correctness* claims. The measurement point must be chosen per claim and recorded.

### 13. Behavior-aware parallel scheduling
**Confirmed?** Largely unrelated. Nearest: arbitration of concurrent same-id creation with the loser rolled back
(`packages/core/agent-loop/tests/scope-lifecycle.spec.ts:415`) and the write lease (P20).
**Risks:** high. `FAM-SCHEDULER` (D-031) was *declared* scope versus *effective* scope, and parallelism
multiplies exactly that. Dense `seq` also forces a single writer per story. **Recommendation: DEFER.** Of the
twenty concepts this has the worst benefit-to-risk ratio before the rest of the architecture exists. *(This
verdict was changed by the adversarial review — see §20.)*

### 14. ExecutionProfile identity
**Confirmed?** Partially: they freeze per-session composition once a turn has run
(`packages/preset/agent-presets/src/index.ts:740-751`). **Contradicted?** Yes, and **ours is the right side**:
profiles and presets are identified by **directory name with no content hashing anywhere**
(`packages/boot/app-boot/src/profile.ts:5-14,79`). A profile can change content under a stable name — fatal for
a qualification record. **Borrow:** per-value layer provenance in the resolved snapshot
(`packages/util/launch-environment/src/index.ts:31-52`). **Risks:** profile identity must also include the
**capability enforcement levels** actually resolved, or two runs under different sandbox enforcement compare as
equal. *(Added by the adversarial review — see §20.)*

### 15. Provider circuit breaker
**Confirmed?** Improved: a bounded transport retry budget with typed exhaustion, `TIMEOUT` classification of a
stalled body, and clean partial EOF exposed as non-default-retryable `STREAM_CLOSED`
(`packages/llm/llm-retry/tests/transport-recovery.spec.ts:178-230`). **Contradicted?** Their retry decision
lives on a waterfall and therefore depends on the plugin set — reject that mechanism, keep the taxonomy.
**Borrow:** the fault-injection server (P32) so the breaker is qualified offline rather than against a live
endpoint. **Risks:** a breaker that trips silently becomes an unexplained stop — SS-94's exact shape. Tripping
must be a typed recorded event with an owner.

### 16. Holdout qualification workloads
**Confirmed?** Unrelated. Handled in
[`AISEF-V2-QUALIFICATION-PROPOSAL.md`](AISEF-V2-QUALIFICATION-PROPOSAL.md) §3.
**Risks:** the only real risk is re-labelling. AISEF has **no** qualifying holdout today and cannot create one
by decision; the `WorkloadRole` guard makes demotion automatic so nobody has to remember.

### 17. Developer tests as engineering evidence, not semantic oracle
**Confirmed?** Yes, and more directly than I expected. The artefact that pins behaviour in DeepSeek is the
**harness-owned snapshot corpus** — with repository-wide ownership and storage invariants
(`scripts/session-snapshot-corpus.corpus.ts:1`) — while package unit tests never decide a snapshot. Two
instruments, two questions, exactly the V2 split. **Borrow:** the corpus-ownership rule.
**Risks:** developers may stop writing meaningful tests once those tests no longer decide anything; the TDD
check must keep its own teeth.

### 18. Mutation testing as test-sensitivity evidence
**Confirmed?** No — **contradicted by absence**. They use a **100% per-file** coverage gate instead: "100% or it
doesn't merge … Per-file so a well-covered big file can't subsidize a bare one. Every v8 ignore comment must
carry a reason" (`vitest.config.ts:350-363`). **Improved?** Ours is stronger: coverage says a line ran, mutation
says the line's behaviour is noticed. **Borrow:** *per-file* thresholds rather than aggregate, and *every
exclusion carries a reason* — the same discipline as our audited equivalent mutants.
**Risks:** mutation cost grows with the product, and target selection becomes a judgement call that can quietly
exclude weak areas.

### 19. Adaptive execution without adaptive requirements
**Confirmed?** Yes, twice. Sandbox widening is **strictly monotone** and goes through approval before anything
executes (`packages/sandbox/sandbox/src/escalation.ts:1-31`); and containment adapts per platform while
`warnFallback` states precisely what is no longer guaranteed
(`packages/subprocess/subprocess-local/src/index.ts:230-247`). **Borrow:** adapt the *mechanism*, declare the
*guarantee change*. **Risks:** adaptation that changes what is measured must enter the profile identity, or the
claim silently changes while the record looks identical.

### 20. Qualification ladder Q0–Q6
**Confirmed?** Unrelated as qualification, confirmed as *instinct*: eight test tiers, keyless replay as the
parallel default, credentialed e2e self-skipping and serialized, record mode the only one that loads `.env`
(`vitest.snapshot.config.ts:24-65`; `vitest.e2e.config.ts:5-45`). Cheap and deterministic first; expensive and
live last. **Borrow:** the tiering, and "the expensive tier self-skips rather than failing when credentials are
absent". **Risks:** rigidity. A rung that cannot run blocks everything above it — which is intended — but it
must produce a typed `UNRUNNABLE`, never a `FAILED`.

---

# §8 — Do not copy blindly

| Pattern | Verdict | Reasoning |
|---|---|---|
| **Everything-as-a-plugin** | **REJECT for the kernel** | Their composition is an empty base plus patches (`apps/cli/src/profile-boot.ts:82-85`) — right for a product that ships many surfaces. AISEF's gate is the thing being qualified; a replaceable gate means the qualified artefact is not the one that ran. Capability *implementations* may be substitutable; the **decision** may not. |
| **Dynamic plugin discovery** | **REJECT** | Their own checker records the cost: packages mounted by runtime string are "invisible to yml-row scanning", compensated by a hand-maintained mirror list, and the failure it prevents is a platform-conditional defect "keyless Linux CI hides … until a macOS boot" (`scripts/verify-cordis-config.ts:40-55`). Static verifiability is worth more to us than extensibility. |
| **Runtime hot replacement** | **REJECT for anything a run depends on** | Their own manifest says loader mutations are "eager, non-transactional … plugin activation failures can leave a partially applied tree" (`vendor/README.md`, item 8). A partially applied configuration silently changes what a qualification run measured. |
| **Cordis runtime dependency** | **REJECT** | TypeScript; pre-release (`4.0.0-rc.7`); the copy in production use is a **locally patched fork carried without its upstream tests** (0 spec files under `vendor/`). Adopt the four principles, implement them ourselves in ~200 lines under our own mutation and fault-matrix budget. |
| **TypeScript rewrite** | **REJECT** | No demonstrated AISEF problem is caused by Python. The cost is concrete and large: a rewrite discards 100 000 differential traces, 871 mutants, 102 fault cells and a tree-hash-bound W0 — all of which are bound to the current product tree. |
| **Dynamic configuration mutation** | **REJECT during a run** | Their settings hot-publish, chokidar watching and per-namespace re-resolution (`packages/settings/settings-file/src/index.ts:238-263`) are right for an interactive product. During a qualification run, configuration must be resolved once, hashed, and frozen. Outside a run, reload freely. |
| **Model-visible session architecture** | **REJECT as evidence; LIMIT as context** | They ship model-facing runtime introspection and session-history search (`packages/extensions/tool-cordis/src/index.ts:27-80`; `packages/session-query/tool-session-query/src/index.ts:1-4`). The read-only boundary is good. The danger is the next step: anything an agent reads about the harness is **context**, and under invariant VIII it can never enter an evidence field. |
| **Interactive-agent assumptions** | **REJECT** | PTY semantics, approval prompts, human-driven resume, terminal-shaped output. AISEF runs unattended for hours. Their escalating shutdown with a second-signal override (`apps/cli/src/process-shutdown.ts:52-75`) is the one interactive affordance worth keeping — and only because it makes operator interruption a *typed terminal state* instead of a gap. |

---

# §9 — Architectural anti-patterns (mandatory section)

For each: why it is acceptable in their domain, why it is risky for AISEF, and the AISEF alternative.

**A1 · Concurrent sibling disposal with swallowed failures.**
`vendor/cordis/src/fiber.ts:675-684` — a fiber's effects are disposed with `Promise.all` and every error goes to
`ctx.logger.error`. *Acceptable there:* a plugin runtime wants teardown to complete even if one plugin misbehaves,
and a logged error is actionable for a developer. *Risky here:* our resources have hard ordering (processes before
sandbox before worktree), and a swallowed cleanup failure **is** how an orphan is born — `FAM-PROCESS` in one
line. *Alternative:* an explicit ordered resource stack disposed in reverse, each awaited, each failure emitted as
a typed `story/resource-released` event able to fail `DISPOSE`.

**A2 · The event bus as a carrier of control.**
`events.ts:224-242` — a `waterfall` listener that does not call `next()` vetoes built-in behavior; retry is
decided this way at `agent-loop/src/agent.ts:448-464`. *Acceptable there:* extensibility is the product.
*Risky here:* the outcome depends on which plugins are loaded and in what order they registered, and the record
does not say. That is a direct violation of Semantic Determinism. *Alternative:* control in explicit kernel code;
the journal records and never dispatches.

**A3 · Name-only identity for profiles and presets.**
`packages/boot/app-boot/src/profile.ts:5-14,79`; no hashing anywhere in those paths. *Acceptable there:* a user
edits their own profile directory and expects the name to keep meaning it. *Risky here:* a profile can change
content under a stable name, so two qualification records citing the same profile may describe different runs —
`FAM-IDENTITY` and `FAM-BENCH` together. *Alternative:* content-hashed `ExecutionProfile` identity, which AISEF
already has and must keep.

**A4 · Policy as an optional per-call parameter.**
`packages/hooks/hook-protocol/src/runner.ts:87` passes no `sandboxPolicy`, so hooks silently run at the
deployment default and the fallback workspace root (`packages/shell/bash-sandbox/src/index.ts:86`).
*Acceptable there:* a forgotten parameter yields a *more* restrictive default, so the failure is inconvenience,
not exposure. *Risky here:* the same shape is `FAM-SCHEDULER` — declared scope versus effective scope — and for
us the wrong default can silently change what a run measured. *Alternative:* derive confinement structurally from
the owning `StoryScope`; where a parameter is unavoidable, make it non-optional so omission is a type error.

**A5 · Declared-but-unenforced metadata.**
`packages/settings/settings/src/types.ts:45` declares `applies: 'live' | 'restart'`; no consumer reads it.
*Acceptable there:* a harmless unfinished affordance. *Risky here:* readers reason as though a declared property
holds. An invariant register nobody arms is exactly this failure at scale. *Alternative:* P31 — arm invariants in
every test run — plus a Q0 check that every declared property has at least one enforcing consumer.

**A6 · Dynamic mounting compensated by a hand-maintained mirror.**
`scripts/verify-cordis-config.ts:40-55`. *Acceptable there:* the adaptive backend chooser is a genuine product
requirement and the mirror is a pragmatic patch. *Risky here:* a mirror list is a second source of truth that
drifts, and the thing it mirrors is invisible to the checker by construction. *Alternative:* composition stays
expressible as data; if something must be chosen at runtime, the *choice* is recorded in the journal and enters
the profile identity.

**A7 · Vendoring a framework without its tests, then patching it.**
0 spec files under `vendor/`, and `vendor/README.md` item 6 logs three reentrant-disposal gaps they fixed
themselves. *Acceptable there:* 1227 harness-level spec files are a real safety net, and owning the framework
beats being surprised by it. *Risky here:* we would be modifying code whose own qualification evidence we do not
carry, inside a system whose entire value is qualification evidence. *Alternative:* do not vendor a framework at
all — implement the four Cordis principles in our own tree, under our own mutation budget.

**A8 · Positional replay binding.**
`packages/test-support/llm-replay/src/index.ts:1030-1061` binds scripts by call order, not by request matching.
*Acceptable there:* compensated by `assertConsumed` and by request-header class pinning, and a false pass costs a
missed regression. *Risky here:* a false pass costs a false qualification. *Alternative:* if AISEF replays
provider output, bind by a hash of the request; keep `assertConsumed` and class pinning regardless.

**A9 · Non-transactional configuration application.**
`vendor/README.md` item 8: loader mutations "do not restore previous plugins or options"; "plugin activation
failures can leave a partially applied tree". *Acceptable there:* the user sees the failure and retries.
*Risky here:* an unattended run continuing under a half-applied configuration produces evidence about a system
that never fully existed. *Alternative:* configuration is resolved once, validated, hashed and frozen before the
run begins; a resolution failure is a typed terminal state, never a partial start.

**A10 · Write-behind durability for the record of truth.**
`packages/session/session-persistence-jsonl/src/storage.ts:36` — up to 200 ms of lag, absorbed by crash repair.
*Acceptable there:* interactive latency matters and repair is well designed. *Risky here:* a gap at a decision
point is exactly the SS-96 condition, and we are not latency-bound. *Alternative:* synchronous writes at decision
boundaries; keep their crash-repair machinery anyway, for the cases synchrony cannot cover.

---

# §17 — Final architecture recommendation

### A. What from AISEF v1 should remain unchanged

1. **Typed failure ownership** (PLAN / DEVELOPER / ENVIRONMENT / PROVIDER / REVIEW / SECURITY / INTEGRATION).
   It has **no counterpart in DeepSeek Harness** (harness study §J.5) and V1 proved its necessity: without an
   owner field, SS-96 is not even expressible.
2. **Content-hashed `ExecutionProfile` identity.** Strictly stronger than their name-only scheme (§A3).
3. **Fail-closed everywhere** — the kernel refusing an abbreviated SHA, refusing a stale gate, refusing a plan
   without a complete audit. Confirmed independently by P07.
4. **Mutation testing as the adequacy standard**, including audited equivalents with justifications.
5. **No self-certification**, and the rule that recorded tool results are never replayed — confirmed by P33.
6. **The reference model must implement the owner's policy, not mirror the kernel.** This was learned expensively
   and is the reason SS-96 was eventually caught.
7. **Separating the assurance-kernel verdict from the delivery verdict**, as the V1 final verdict did.

### B. What should be refactored

1. **Evidence storage → an append-only journal** with dense `seq`, append-site validation and no mutation verb.
2. **Gate state → projections** of that journal, with the from-scratch oracle asserted.
3. **Budgets and cost → projections**, not counters (SS-64).
4. **Retry routing → driven by the typed outcome's `owner` and `retryable`**, never by the observing stage.
5. **Invariants → armed in-process in every test**, and made uncontainable.
6. **Process handling → range ownership** with measured emptiness before any filesystem teardown.

### C. What should be replaced

1. **The proof instrument.** Developer tests stop deciding criteria; harness-owned probes decide them. This is
   the one genuine replacement, and it is the whole reason for V2.
2. **Plan freezing → plan admission**, with a measured baseline verdict per criterion.
3. **Ad-hoc scope cleanup → the Story Transaction** with an ordered resource stack.

### D. What should be removed

1. **Any path where a check reports `FAILED` for evidence that did not execute.** SS-96's fix removed one; the
   `Verdict` lattice removes the shape.
2. **Any control decision that reads prose.** Enforced by a Q0 walker, not by review.
3. **Any inference of "parent state" from developer-authored artefacts.**
4. **Time-ordered evidence selection** (`last`, newest, HEAD) — replaced by dense `seq` and full SHAs.
5. **Summary-only gate reporting.** One row per check; a decision cites its inputs by seq.

### E. DeepSeek Harness patterns to adopt

P05, P06, P08, P09, P10, P11, P12, P13, P14, P15, P16, P17, P18, P19, P20, P21, P24, P25, P27, P28, P29, P30,
P31, P32, P34, P35, P36, P37. The highest-value five, in order: **P31** (invariants armed everywhere — cheapest
by far), **P19** (typed deterministic crash closers), **P25** (request-header class pinning), **P08** (process
range emptiness), **P27** (taxonomy owns retryability).

### F. Cordis concepts to adapt

P01 (child scope is an effect of its parent), P02 (labelled effects — *adapted*: explicit ordering across
siblings), P03 (no acquisition during teardown), P04 (capability seam — *adapted*: recorded resolution plus
versioning), P22 (raw vs resolved — *adapted*: one hashed `RunSpec`), P23 (static verification of composition).

### G. What should NOT be copied

P26, P38, P39, P40, plus the eight §8 items and the ten §9 anti-patterns. In one sentence: **do not copy
anything whose value is extensibility purchased with non-determinism.**

### H. Minimum architecture change to solve the known V1 limitations

Six changes, each traceable to a measured defect. This is the recommended scope of cycle 1, and nothing else.

| # | Change | Defect it closes |
|---|---|---|
| 1 | Behavior Contract + Canonical ProofSpec + harness-owned probes | `FAM-PROOF-PLACEMENT` (PLAN-V2.1-DEFECT-001) |
| 2 | Plan admission with measured baselines | `FAM-PLAN-OWNERSHIP` (`PLAN_OVERLAP`, `PLAN_PRECONDITION_MISSING`) |
| 3 | Append-only journal + projections + from-scratch oracle | `FAM-EVIDENCE-SEMANTICS`, `FAM-BUDGET`, `FAM-QUALIFICATION-MEASUREMENT` |
| 4 | Story Transaction with ordered disposal and measured range emptiness | `FAM-PROCESS`, `FAM-OWNERSHIP`, `FAM-RECOVERY` |
| 5 | Invariants armed in every test and uncontainable | `FAM-OUTCOME`, and A5's whole class |
| 6 | Q0 static admissibility + local fault injection (Q3) | `FAM-PROVIDER`, `FAM-QUALIFICATION`, and the cost ordering itself |

Everything else in this study is either already done (§A), or waits.

### I. What would be over-engineering

- A plugin architecture for the kernel, or any general extension mechanism.
- Behaviour-aware parallel scheduling before the rest exists (concept 13, DEFER).
- A Cordis-equivalent framework in Python; four principles are not a framework.
- Event sourcing of anything *other* than the story journal.
- A full RPC/service mesh between capabilities; in-process protocols suffice.
- Distributed or multi-writer journals; dense `seq` requires a single writer and that is fine.
- A 100% line-coverage gate on top of mutation testing.
- Introspection APIs for the model beyond what a task needs.

### J. Top 10 architectural risks of AISEF V2

1. **The probe suite becomes a second product** with its own untested defects. *Mitigation:* calibration,
   product-mutation, and a hard cap on probe kinds in cycle 1.
2. **ProofSpec becomes another wrong plan artefact.** *Mitigation:* derived-not-authored plus admission; but
   a contract faithful to a wrong requirement remains undetectable — state it rather than imply coverage.
3. **Complexity exceeds what one reviewer can hold.** *Mitigation:* §H's six changes and nothing else; every new
   terminal state must cite a measured defect.
4. **Two-environment verification disagrees constantly** for environmental reasons, and the pressure to
   "just retry until they agree" is enormous. *Mitigation:* `INDETERMINATE`/`INTEGRATION` stops the story; fix
   determinism, never tolerance.
5. **The journal grows past practical replay**, making the from-scratch oracle unaffordable. *Mitigation:*
   shadowing compaction plus sampled oracle checks — and the oracle must run on *some* full journal regularly.
6. **Admission cost pushes people to skip it** under schedule pressure. *Mitigation:* Q0 refuses; there is no
   `--force`.
7. **Owner mis-assignment moves the mis-charge instead of removing it.** The owner field is only as good as the
   rule that assigns it, and V1 shows assignment is hard.
8. **Capability enforcement levels are recorded but not compared**, so runs under `PARTIAL` and `FULL`
   silently mix. *Mitigation:* enforcement levels enter `RunSpec` identity (§20).
9. **A hard-killed harness leaves orphans** and no design here prevents it. *Mitigation:* next-run preflight
   detection; accept and record the residual.
10. **No holdout exists**, so no generalization claim is currently supportable — and the temptation to
    re-label LedgerLock will recur. *Mitigation:* the `WorkloadRole` guard with automatic demotion.

### K. Invariants V2 must guarantee

See §18 below.

### L. What should be frozen before implementation begins

Freeze these six, in this order, each reviewed by the owner before any code:

1. The **`Event` envelope** and the event vocabulary — changing it later invalidates every journal.
2. The **`Verdict` lattice** and the **`Owner` set** — everything routes on these.
3. The **`BehaviorContract` → `ProofSpec`** derivation function — it is what `--check` compares against.
4. The **`Probe` protocol**, including `enforcement()` and the fields of `ProbeResult`.
5. The **`StoryScope` acquisition/disposal contract**, including ordering and the refusal during teardown.
6. The **eight top-level invariants** of §18, with their enforcement mechanism named for each.

Everything else can change during implementation. These six cannot, because evidence written under them must
remain readable and comparable.

---

# §18 — Refined top-level invariants

Each is restated with the refinement the study produced, and — the part V1 was missing — **the mechanism that
enforces it**. An invariant without a named mechanism is A5.

**I · REQUIREMENT AUTHORITY.** Only frozen requirements and approved behavior contracts define product truth,
**and authority derives from where an artefact was admitted, never from what it claims about itself**
(`packages/preset/agent-presets/src/metadata.ts:11-14`).
*Mechanism:* Q0 static check — no kernel module may read `Requirement.text`; contract admission records the
approving document's content hash.

**II · SEMANTIC DETERMINISM.** Proof verdicts must not depend on developer-controlled test topology —
**refined:** nor on which components happen to be loaded, nor on wall-clock ordering, nor on the environment's
incidental state.
*Mechanism:* harness-owned probes; no control on an event bus; `seq` not `time`; deterministic child environment;
`RunSpec` hashing.

**III · INDEPENDENT EVIDENCE.** The actor producing code cannot define the evidence that certifies the behavior
it implemented — **refined:** and the verifying actor must run in a scope it acquired itself, with the
independence being *structural*, not a parameter a caller can omit (§A4).
*Mechanism:* `StoryScope`-derived confinement; `VerifiedProof.agreement`; disagreement is `INDETERMINATE`.

**IV · TYPED OWNERSHIP.** PLAN, DEVELOPER, ENVIRONMENT, PROVIDER, REVIEW, SECURITY and INTEGRATION must not
consume each other's retry budgets — **refined:** retryability and budget target are properties of the typed
outcome, fixed in the taxonomy, never decided at the observing stage
(`packages/llm/llm/src/error.ts:41-48`).
*Mechanism:* `failure/observed` carries `owner` and `retryable`; the retry engine reads only those two fields;
`INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` remains a separate armed invariant.

**V · REPRODUCIBLE QUALIFICATION.** Same kernel + workload + plan + execution profile must yield comparable
evidence — **refined:** *comparable* requires that the **capability enforcement levels** actually resolved are
part of the identity, so a run under `PARTIAL` sandboxing is never compared with one under `FULL`.
*Mechanism:* `capability/resolved` events; enforcement levels folded into the `RunSpec` hash; request-header
class pinning with a bounded drift budget (P25).

**VI · IMMUTABLE PROVENANCE.** Every decision must resolve to immutable identities for parent, candidate, proof
spec, profile and kernel — **refined:** identities are content hashes or full SHAs, never names or abbreviations,
and a frozen artefact cannot change without its manifest changing in the same commit.
*Mechanism:* the store has no update/delete verb; commit-time provenance guard (P37); `spec_hash` on every
verdict.

**VII · NO PROSE AS CONTROL STATE.** Natural-language model output may suggest a condition but must not itself be
authoritative control evidence when deterministic verification is possible — **refined and generalized:** *no
value from outside our taxonomy may become a control code*, whether it comes from a model, a tool, an SDK or a
configuration file (`packages/llm/llm/src/adapter-failure.ts:104-107`).
*Mechanism:* foreign codes flatten to `UNKNOWN`; a Q0 walker rejects an expression or directive in any position
that is not a declared interpolation point (`scripts/verify-cordis-config.ts:503-525`).

**VIII · MEMORY IS CONTEXT, NEVER EVIDENCE.** — **refined:** this extends to anything an agent *reads about the
harness*. Introspection output, session-history search results and prior-run summaries are context; only the
harness's own records are evidence.
*Mechanism:* evidence fields accept only harness-produced typed records; any agent-sourced text entering an
evidence field is an `invariant/violated`.

---

# §20 — Adversarial self-review

Conducted as a separate pass, as a skeptical board. The falsification attempts against the proof chain are in
[`AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md`](AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md) §9; what follows attacks
the rest and records the changes it forced.

**Against event sourcing.** *"You are replacing a bug you understand with a fold you don't."* Fair. The specific
new failure mode is a **projection defect**: a correct journal read wrongly, which is worse than a wrong counter
because it looks authoritative. V1 has no experience of this class. The from-scratch oracle catches
incremental/full divergence but **not** a projection that is consistently wrong in both modes. *Residual,
unmitigated:* a projection wrong in the same way everywhere. Partial mitigation: projections are pure functions
and therefore directly mutation-testable, which counters is the one thing side counters never were.

**Against Story Transaction.** *"Ordered disposal is a comment, not a type."* Correct, and admitted in the
proposal (§2.5). Also: making a child scope a resource of its parent means a mis-parented scope is now a *silent*
leak, where a flat list at least showed everything. The tree is more correct and less obvious.

**Against capability seams.** *"You have created a place where a provider swap is invisible."* That is precisely
DeepSeek's weakness — name-only resolution — and the counter is `capability/resolved` plus versioning. But there
is a second, sharper risk the board should record: **`PARTIAL` enforcement is an invitation.** A capability that
can declare itself partially enforcing will, under schedule pressure, be used partially enforcing, and the
qualification record will contain runs that are not comparable. **This forced a change to invariant V** — see
below.

**Against plugin architecture.** Nothing to falsify; we reject it for the kernel. The residual risk is drift: a
capability registry is one refactor away from being a plugin system. The guard is §17 I's explicit
over-engineering list.

**Against typed retry budgets.** *"Ownership assignment is the hard part and you have not solved it."* Accepted.
Making retryability a taxonomy property (P27) removes one whole failure mode — a call site inventing its own
judgement — but the *owner* of a failure is still assigned by code that can be wrong, and V1 shows assignment is
where the difficulty lives. No external pattern helps. This stays risk J.7 and is not claimed as solved.

**Against holdout qualification.** *"A holdout used once is a sample of size one."* True. A single holdout run
supports a much weaker claim than it appears to, and the `WorkloadRole` guard does not fix that — it only stops
contamination. Any generalization claim must state its sample size, and the honest statement today is that AISEF
has no holdout and therefore no generalization claim at all.

**Where the verifier becomes a new source of false assurance.** Three places, and only two have mechanisms.
(a) A probe that always affirms — mitigated by calibration. (b) A ProofSpec derived faithfully from a wrong
contract — mitigated by admission only when the baseline disagrees, which a *consistently* wrong contract will
not. (c) **A Q0 checker that is itself wrong** — and this had **no** mitigation in the proposal, which is a real
gap the adversarial pass found.

**How V2 avoids becoming too complex to trust.** One test, applied to every element: *name the measured V1 defect
it closes.* §17 H does this for all six recommended changes. Anything that cannot cite a measured defect belongs
in §17 I. Concretely, this pass moved one concept out of scope and one into a stricter form.

### Changes forced by this review

1. **Concept 13 (behavior-aware parallel scheduling) is DEFERred**, not merely flagged. It cites no measured V1
   defect it would close, and it amplifies `FAM-SCHEDULER`, the family whose V1 instance (D-031) was declared
   versus effective scope.
2. **Invariant V now requires capability enforcement levels in the identity.** Without it, `PARTIAL` enforcement
   silently produces incomparable qualification records — the `PARTIAL`-is-an-invitation risk above. This is
   also added to concept 14's risks and to risk J.8.
3. **Q0 checkers get the same obligation as probes.** A checker must have been **observed failing** on a known-bad
   input before it is trusted to pass anything, and checkers carry their own mutation budget. Without this, Q0 is
   a new, cheap, invisible source of false assurance — the gap noted in (c) above. This is now a precondition of
   Q0 in [`AISEF-V2-QUALIFICATION-PROPOSAL.md`](AISEF-V2-QUALIFICATION-PROPOSAL.md).
4. **The `Verdict` lattice and `Owner` set are capped**: each is frozen (§17 L) and a new member requires a cited
   measured defect. This is the concrete answer to "too complex to trust".
5. **Two residuals are recorded as unmitigated** rather than argued away: a projection consistently wrong in both
   incremental and full modes, and a Behavior Contract faithful to a wrong requirement. Both are human-review
   dependencies, and the record should say so.
