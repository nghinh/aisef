# AISEF V2 — external architecture matrix

Owner decision §7. Every pattern extracted from the external study, with the ten required fields. Because ten
columns do not fit one readable table, the matrix is split into **Table A** (what the pattern is and how DeepSeek
implements it) and **Table B** (what it means for AISEF), keyed by the same pattern id. The pattern register and
source citations are in [`AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md`](AISEF-V1-DEFECTS-VS-EXTERNAL-PATTERNS.md)
§1; full evidence in [`DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md`](DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md) and
[`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md).

**Decisions used.** `ADOPT` — take it substantially as designed. `ADAPT` — take the principle, change the
mechanism for a stated reason. `REJECT` — do not take it, with the reason. `CONFIRM` — AISEF already does this;
the external system is independent convergent evidence, and the value of the row is that it stops us weakening
what we have. `DEFER` — worth doing, not in the first V2 cycle.

**V2 components** named in the last column: **Kernel** (gate and control), **ProofEngine**, **ProbeEngine**,
**StoryTx** (Story Transaction / StoryScope), **Journal** (append-only evidence store and projections),
**CapReg** (capability registry and contracts), **RunSpec** (resolved, hashed execution specification),
**Provider**, **Runtime** (sandbox, process, filesystem), **QualHarness**, **StaticVerifier** (new),
**InvRuntime** (new, invariants armed in-process).

---

## Table A — pattern, source, problem solved, DeepSeek implementation

| id | Pattern | Source | Problem it solves | How DeepSeek implements it |
|---|---|---|---|---|
| P01 | Child scope is an effect of its parent | `vendor/cordis/src/fiber.ts:265` | Cleanup enumerated by hand per call site; no record of what a scope owns | `this.dispose = parent.fiber.effect(…, 'ctx.plugin()')` — one ownership tree, transitive disposal |
| P02 | Labelled effects returning disposers | `fiber.ts:418-441` | Resource release order and idempotence | Disposers collected, `.splice(0).reverse()`, chained and awaited; `disposing` flag; `EffectMeta{label,children}` |
| P03 | No acquisition during teardown | `fiber.ts:418-422` | A resource acquired into a dying scope is leaked by construction | `CordisError('INACTIVE_EFFECT')` thrown when `state === UNLOADING` |
| P04 | Capability = name + availability predicate, owner-bound | `service.ts:42-58`, `registry.ts:29-51` | Substitutable implementations; consumers running before their dependencies exist | `ctx.reflect.provide(name, self, check)` in the constructor; `inject` map; `FiberState.PENDING` |
| P05 | Declared enforcement level; refuse rather than degrade | `sandbox-local/src/index.ts:181-186,233-237`; `out-of-process.ts:57-63` | A capability silently doing less than it claims | `partial` for landlock-old-ABI and windows-acl; `NO_START_CAPABILITIES` rejects unsupported requests up front |
| P06 | "Did not run" checked before "was denied" | `bash-sandbox/src/index.ts:119-123` | Absence read as a behavioural result | Separate `RUNNER_FAILURE_RULES` and `DENIAL_SIGNATURES`, consulted in that order |
| P07 | Fail-closed capability selection | `sandbox/src/index.ts:124-157` | Falling back to an unprotected path when protection is unavailable | `SANDBOX_UNAVAILABLE`; the unwrapped argv is never returned |
| P08 | Ownership is a process **range** | `spawn.ts:418-421`; `subprocess-local/src/index.ts:199-205` | Cleanup racing a surviving grandchild | `waitForExit()` resolves on range emptiness, measured by `kill(pid,0)` / `TasksCurrent` / `isJobEmpty` |
| P09 | Graceful-first ladder, child-first drain | `subagent-acp/src/run.ts:185-212`; `subagent/src/index.ts:333-348` | Killing a tree before its members can clean up | EOF → bounded grace → TERM → grace → KILL → unbounded wait; descendants drained before the parent |
| P10 | Spawn spec with no defaults | `subprocess/src/types.ts:71-107` | Ambient environment deciding what a command means | argv, cwd, per-stream stdio, `graceMs`, `signal`, `env` all required |
| P11 | Structural env scrub; deterministic child env | `subprocess/src/index.ts:66-80`; `bash-local/src/index.ts:27-32` | Credential leakage into children; output that varies with the terminal | `SENSITIVE_ENV_PATTERN`, `DSH_*` stripped, explicit `env` merged after with `undefined` as tombstone; `NO_COLOR`/`TERM=dumb`/`PAGER=cat` |
| P12 | Layered typed timeouts that never abandon | `timeout-policy/src/index.ts:55-80`; `bash-local/src/index.ts:255-267` | A timeout that loses the work and the reason | Executor, tool-level and pipe-drain layers; result classified `timedOut`/`aborted`; the tool promise is never raced away |
| P13 | Authority only narrows | `child-agent.ts:50-59,200-252` | A delegate acquiring authority its parent lacked | Restriction intersects; approval pinned to `'never'`; only explicit overrides propagate; depth persisted; capture synchronous before the first await |
| P14 | Append-only store with no update/delete verb | `session-persistence/src/index.ts:147-198`; `types.ts:439-441` | Records edited after the fact | Service API is create/open/flush/stat/list; `O_APPEND`+fsync; deletion is a new shadowing event or tombstone |
| P15 | `seq === index`, four enforcement layers; `time` never orders | `session/src/index.ts:567-581,743`; `storage-contract.ts:145-151` | Selecting evidence by recency | Assignment, seed admission, append assertion, decode check; fixtures omit `seq`/`time` and re-derive from file position |
| P16 | Validation at the append site | `session/src/index.ts:713-715,749` | A bad record discovered only at read time | Payload JSON-losslessness and surface transition validated before the log grows |
| P17 | Pure folds; caches disclaimed; from-scratch oracle | `session-projection-cache/src/index.ts:9-14`; `tests/derived-cache.spec.ts:17-27` | Derived state drifting from the record | Every read model a fold; cache "possibly stale but never wrong", version mismatch discards; test asserts incremental == replay-from-scratch |
| P18 | Unknown **required** event ⇒ refuse to reconstruct | `session/src/types.ts:478-487` | An old reader silently mis-deriving a newer record | `ignorable?: true` is an explicit author-side claim; anything else unknown aborts reconstruction |
| P19 | Deterministic typed crash closers | `session/src/repair.ts:15-18,87-88,119-133` | An interrupted run leaving a gap a later reader must interpret | Synthetic `tool/result` with `TOOL_OUTCOME_UNKNOWN` vs `TOOL_NOT_STARTED`, then `step/end`, then `turn/end{interrupted}`; timestamps reuse the last real event |
| P20 | Write lease before the cold read | `lease.ts`; `agent-loop/src/index.ts:894-904` | Two processes both believing they own a record | Kernel-held directory lock acquired before reading the log |
| P21 | Fork cut at the last completed boundary | `session/src/index.ts:1286-1294` | Resuming from a partially-formed state | Boundary is an inclusive seq; a prefix ending inside an open turn is refused (`OPEN_TURN`); an `end-seed` marker is appended |
| P22 | Raw vs resolved config, frozen, with per-value provenance | `settings/src/index.ts:436,730-766`; `launch-environment/src/index.ts:31-52` | Not knowing what was actually in force, or that a no-op edit still changed the document | Raw section and deep-frozen resolved value stored separately; revision tracks raw independently; env snapshot records the supplying layer |
| P23 | Static verification of composition | `scripts/verify-cordis-config.ts:104-162,503-544` | Defects that raise no error and produce no signal | Walks every entry; rejects `!!js` outside the one interpolated position; parse-checks without executing; validates resolution and plane separation |
| P24 | Generated catalogs, `--check` twins, fail-closed both ways | `gen-cordis-catalog.ts:55-59,1167-1192` | Derived artefacts drifting from their source | Nine `verify-*` gates diff byte-for-byte; a discovered key absent from the table *and* a table entry no longer discovered are both hard errors |
| P25 | Request-header class pinning with bounded drift | `manifest.ts:12-52`; `suite.ts:10-17` | Silent change in what is sent to the model | "Stable class name shared only by byte-identical request headers"; one pinning scenario per class; `changes`/`promptChanges` bound legitimate drift; session-dependence must declare a new class |
| P26 | Identity by name only | `profile.ts:5-14,79` | (nothing — it is a convenience) | Profile identity is the directory basename; no content hashing anywhere in these paths |
| P27 | The code taxonomy owns retryability | `llm/src/error.ts:41-48`; `retry-policy.ts:18-24` | Each call site inventing its own retry judgement | `DEFAULT_RETRYABLE_CODES`; `MISSING_CREDENTIAL` vs `INVALID_CREDENTIAL` split "because the fix differs", the latter non-retryable |
| P28 | Foreign codes are not our taxonomy | `adapter-failure.ts:104-107`; `llm/src/error.ts:13-22` | Third-party or model text becoming a control decision | "Route on this, never by parsing `message`"; non-`HarnessError` flattens to `UNKNOWN`; foreign SDK codes rejected |
| P29 | Failure recorded in a `finally` | `agent-loop/src/agent.ts:328-345` | A failure that is only an exception leaves no evidence | The turn always ends with a durable `turn/end{kind:'error', error}`, whatever the control path did |
| P30 | Invariant errors uncontainable, owner-named | `invariants/src/index.ts:50-66,137-142`; `settings/src/index.ts:833-841` | An invariant a `catch` can swallow | `invariant violated by "<package>"`; ownership reserved and unique; every containment boundary re-raises `INVARIANT` |
| P31 | Invariants armed in every test run | `scripts/test-invariants.ts:60,125-205` | Invariants that hold only in the suite written for them | `RegistryService.prototype.plugin` patched so the registry and the owning package's companion mount before any root plugin activates, in every tier |
| P32 | Named fault-injection surface | `llm-mock-server/src/index.ts:16-68` | Failure handling only testable against a live endpoint | 24 named behaviours over HTTP/SSE; weighted profile labelled "test pressure, not a claim about production incident frequency" |
| P33 | Replay mocks only the model; tools re-executed and diffed | `llm-replay/src/index.ts:458-499,1095-1097`; `suite.ts:3-4` | Replaying recorded tool output = checking the system against itself | The script derives from assistant settlements only; `tool/call`/`tool/result` skipped; tools run for real; fixture is both input and expected output; final workspace state compared |
| P34 | `assertConsumed` | `llm-replay/src/index.ts:1100-1114` | A reproduction that took a different shape scoring as the same run | Fails if fewer sessions bound or a different number of model calls driven than recorded |
| P35 | Teardown asserted against the OS | `process-exit.spec.ts:20-55`; `linux-scope.spec.ts:250-260` | "Cleanup ran" proved by reading the cleanup code | `process.kill(pid,0)`/`ESRCH` liveness with `managed pid ${pid} is still alive`; `existsSync` on temp dirs after abort *and* terminate |
| P36 | Cost and latency as projections of the log | `session-stats/src/types.ts:22-39`; `route-pricing.ts:29-45` | A side counter disagreeing with what happened | `llmMs`/`toolMs` folded from the log, `toolMs` matched by `callId` with orphan-result rejection; pricing throws loud on occurrence-count misalignment |
| P37 | Commit-time provenance guard | `scripts/check-vendor-manifest.sh` | A frozen artefact changing without its record | Staged change under `vendor/*/src` without `vendor/README.md` in the same commit fails the hook |
| P38 | Event bus as control (`waterfall` veto) | `events.ts:224-242`; `agent-loop/src/agent.ts:448-464` | (extensibility — at the cost of determinism) | A listener that does not call `next()` vetoes the rest of the chain including built-in behavior; retry happens iff some listener returns `{kind:'retry'}` |
| P39 | Plugins mounted by runtime string | `verify-cordis-config.ts:40-55` | (nothing — it is a consequence of dynamic discovery) | Composition invisible to static checking; compensated by a hand-maintained `CHOOSER_BACKEND_PACKAGES` mirror |
| P40 | Declared-but-unenforced metadata | `settings/src/types.ts:45` | (nothing) | `applies: 'live' \| 'restart'` is declared and defaulted; no consumer reads it |

---

## Table B — AISEF relevance, decision, reason, risks, families, component

| id | AISEF relevance | Decision | Reason | Risks | V1 families addressed | V2 component |
|---|---|---|---|---|---|---|
| P01 | High — our cleanup is per-call-site | **ADOPT** | Makes "what does this story own" answerable at runtime; disposal transitive by construction | Effect trees hide cost; a mis-parented scope is now a silent leak rather than a loud one | 6, 8, 9 | StoryTx |
| P02 | High | **ADAPT** | Take labelled disposers; ordering across sibling effects is **not** guaranteed by the pattern | Over-trusting it: a worktree disposer can run before the sandbox that mounts it | 6, 8 | StoryTx |
| P03 | High | **ADOPT** | A resource acquired into a dying scope is leaked by construction; cheap to enforce | Legitimate teardown-time work (writing final evidence) must be modelled outside the scope | 8 | StoryTx |
| P04 | High | **ADAPT** | Seam shape is right; we must record *which* implementation answered and add versioning | Name-only resolution hides a provider swap from the record | 2, 7, 14 | CapReg |
| P05 | **Highest** | **ADOPT** | A capability that declares `partial` makes silent under-enforcement unexpressible; refusing beats degrading | A `partial` level invites runs that are qualified against a weaker guarantee unless the level is bound into the record | 2, 7, 14 | CapReg, Runtime, Journal |
| P06 | **Highest** | **CONFIRM** | Independent convergent evidence for `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE`; ours is the stronger typed form | Weakening ours toward a convention at one call site | 2, 14 | Kernel |
| P07 | High | **CONFIRM** | AISEF already fails closed; the row exists to stop us adding a fallback under schedule pressure | — | 7 | Runtime |
| P08 | **Highest** | **ADOPT** | Directly makes D-024's cleanup race unexpressible; emptiness is measured, not inferred | Range emptiness can block indefinitely — which is correct, but needs a typed terminal state | 8 | Runtime, StoryTx |
| P09 | High | **ADOPT** | Lets a nested scope clean up its own resources first, which is what makes P08 achievable | Grace windows lengthen teardown; a hostile child can exhaust tier 1 | 8 | Runtime, StoryTx |
| P10 | Medium-high | **ADOPT** | Removes the ambient-default path `FAM-TOOL` lives in; we already know the values | Verbosity at call sites; mitigated by constructing specs from the scope | 6, 7 | Runtime, RunSpec |
| P11 | Medium | **ADOPT** | Turns our credential discipline into a structural property of one function | `/KEY\|PASSWORD\|SECRET\|TOKEN/i` is a heuristic; a differently-named secret passes | — (innocent of all 22) | Runtime |
| P12 | High | **ADOPT** | A typed timeout naming its layer, that never abandons the work | More layers = more places a deadline can be mis-derived | 4, 8, 15, 21 | Runtime, Kernel |
| P13 | **Highest** | **ADOPT** | Four mechanisms enforcing one property — authority only narrows — with a synchronous capture point | Persisted depth is state that must itself survive resume correctly | 9, 10, 13 | StoryTx, CapReg |
| P14 | High | **ADOPT** | An interface with no mutation verb enforces our closure-evidence discipline by type | Compaction/shadowing must then be designed carefully, or the log grows without bound | 5, 10, 11, 18 | Journal |
| P15 | **Highest** | **ADOPT** | The structural answer to our largest family: never order by time; make position the identity, enforced 4× | Dense sequences make distributed or parallel writers hard — accept a single writer per story | 1, 16 | Journal |
| P16 | High | **ADOPT** | A record that cannot be written fails earlier and more locally than one that cannot be read | Validation cost on the hot path | 3, 16 | Journal |
| P17 | **Highest** | **ADOPT** | The from-scratch oracle is a cheap, high-yield property AISEF asserts nowhere today | An oracle over a long journal is slow; sample it | 2, 5, 15, 16, 18 | Journal, QualHarness |
| P18 | **Highest** | **ADOPT** | Makes "silently read a newer record wrong" a designed-out failure mode | Every new required field becomes a format bump; that is the intended cost | 5, 11 | Journal |
| P19 | **Highest** | **ADOPT** | `TOOL_OUTCOME_UNKNOWN` is INV-ABSENCE for interrupted runs; deterministic closers make repair idempotent | A synthetic event must be visibly synthetic or it becomes fake evidence | 2, 5 | Journal, Kernel |
| P20 | Medium-high | **ADOPT** | Two runs cannot both believe they own a story's evidence | Lease loss mid-run must be a typed terminal state, not a crash | 1, 5 | Journal, StoryTx |
| P21 | High | **ADOPT** | A resume point defined as the last completed structural boundary is what `FAM-RECOVERY` needs | Requires the journal to have unambiguous completed boundaries — design them first | 5 | Journal, StoryTx |
| P22 | High | **ADAPT** | Take raw/resolved and per-value provenance; go further with **one** hashed `RunSpec`, because a qualification claim is about a whole run | A global resolved spec is a bottleneck; it is also the point | 1, 10 | RunSpec |
| P23 | **Highest** | **ADOPT** | The only control for defects that raise no error; several of our families are in that category | A checker is code that can itself be wrong, and it needs its own tests | 3, 6, 7, 9, 13 | StaticVerifier |
| P24 | **Highest** | **ADOPT** | Bidirectional fail-closed is the right rule for our plan map, invariant register and fault matrix | Generated artefacts must be committed, or the `--check` has nothing to diff | 1, 10, 11, 12, 18, 20 | StaticVerifier, QualHarness |
| P25 | **Highest** | **ADOPT** | What we send the model is our largest uncontrolled variable; class pinning bounds and reviews its drift | Class proliferation; each new class is coverage that must be maintained | 1, 10, 12, 22 | QualHarness, RunSpec |
| P26 | — | **REJECT** | Name-only identity lets a profile change content under a stable name; fatal for a qualification record. Ours is stronger and stays | — | would worsen 1, 12 | RunSpec |
| P27 | **Highest** | **ADOPT** | D-006 exactly: retryability decided once in the taxonomy, not at each call site | Retryability alone does not say *whose budget pays* — our owner field still must | 4, 14, 15, 21 | Kernel, Provider |
| P28 | **Highest** | **ADOPT** | The enforceable form of **No Prose As Control State**, at the seam | Flattening to `UNKNOWN` loses diagnostic detail unless the original is kept as data | 3, 13 | CapReg, Provider |
| P29 | **Highest** | **ADOPT** | Our biggest evidential gaps are runs that ended abnormally | A `finally` that itself fails must not mask the original failure | 2, 17, 21 | Kernel, Journal |
| P30 | **Highest** | **ADOPT** | An invariant a `catch` can swallow is not an invariant; naming the owning module is typed ownership for internal defects | An uncontainable error ends the run — correct, but it must still write evidence (see P29) | 2, 17 | InvRuntime |
| P31 | **Highest** | **ADOPT** | Cheapest upgrade available: arms our 57 invariants across the whole 3702-test suite at near-zero marginal cost | Slower tests; an invariant that fires everywhere makes every test a potential failure site (intended) | 2, 15, 17 | InvRuntime |
| P32 | High | **ADOPT** | Converts expensive live provider evidence into offline deterministic evidence — exactly the owner's §13 ordering | A mock's fault vocabulary is a model of reality and will be incomplete | 17, 21 | QualHarness, Provider |
| P33 | **Highest** | **CONFIRM** | Never replay recorded tool results — that is self-certification. Their refusal matches ours; the row exists to keep it | Re-executing tools makes replay slower and environment-sensitive; that is the price of real evidence | 12 | QualHarness |
| P34 | High | **ADOPT** | A reproduction that took a different shape must not score as the same run | — | 5, 12, 18, 22 | QualHarness |
| P35 | High | **ADOPT** | The only evidence that actually discriminates an orphan; a handful of lines | Platform-specific; needs a Windows equivalent | 8 | QualHarness, Runtime |
| P36 | **Highest** | **ADOPT** | SS-64 was a side counter disagreeing with what happened; a projection cannot disagree with its own log | Projections over long journals cost time; cache them under P17's disclaimer | 4, 15, 17, 18, 21 | Journal, Kernel |
| P37 | Medium | **ADOPT** | Makes our closure-evidence rule a hook instead of a discipline I follow | A hook is bypassable with `--no-verify`; pair with a CI check | 1, 11 | StaticVerifier |
| P38 | — | **REJECT** | Control must not depend on which subscribers are loaded. Their own `agent/request-error` waterfall is the concrete instance: whether a request is retried depends on the plugin set | — | would worsen 4, 13, 16 | Kernel |
| P39 | — | **REJECT** | Composition beyond static reach; their own comment records a platform-conditional defect CI cannot see, patched with a hand-maintained mirror | — | would worsen 7, 9 | CapReg |
| P40 | — | **REJECT** | A declared property nothing enforces is worse than no declaration, because readers reason as though it holds. This is the general form of the failure P31 prevents | — | would worsen 2, 17 | — |

---

## Summary

**40 patterns: 30 ADOPT, 3 ADAPT, 3 CONFIRM, 4 REJECT.**

- **ADOPT (30)** — P01, P03, P05, P08, P09, P10, P11, P12, P13, P14, P15, P16, P17, P18, P19, P20, P21, P23,
  P24, P25, P27, P28, P29, P30, P31, P32, P34, P35, P36, P37
- **ADAPT (3)** — P02 (sibling disposal order is not guaranteed), P04 (add recorded resolution and versioning),
  P22 (one hashed `RunSpec` rather than per-seam freezing)
- **CONFIRM (3)** — P06, P07, P33
- **REJECT (4)** — P26, P38, P39, P40

**The three CONFIRM rows matter as much as the adoptions.** P06 (absence before denial), P07 (fail-closed) and
P33 (never replay tool results) are places where AISEF v1 already reached the right answer, in two cases
expensively. Their purpose in this matrix is to be cited the next time a schedule argues for a fallback path or a
faster replay.

**What no external pattern supplies.** Typed failure *ownership*, proof obligations, plans, and gates have no
counterpart in DeepSeek Harness. Families 19 (`FAM-PROOF-PLACEMENT`) and 20 (`FAM-PLAN-OWNERSHIP`) — the two that
ended V1's delivery qualification — appear in the "families addressed" column of almost nothing. That work is
ours, and it is the subject of
[`AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md`](AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md).
