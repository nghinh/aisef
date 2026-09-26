# AISEF V1 defect families vs. external patterns

Owner decision §5. For every named V1 defect family, what the DeepSeek Harness / Cordis patterns would have done:
**PREVENT** (the defect becomes unexpressible), **REDUCE** (it stays possible but narrower or less likely),
**DETECT** (it still occurs, but the system surfaces it instead of being silently wrong), **NOT HELP** (no
bearing — stated explicitly, because a pattern that is innocent of a family is worth recording).

Rows are the 22 families of [`V1-DEFECT-FAMILY-REGISTER.md`](V1-DEFECT-FAMILY-REGISTER.md). Columns are the
patterns registered in §1, each with a source citation. Sources:
[`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) and
[`DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md`](DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md).

A verdict here is an assessment of the *pattern*, not a commitment to adopt it. Adoption decisions are in
[`AISEF-V2-EXTERNAL-ARCHITECTURE-MATRIX.md`](AISEF-V2-EXTERNAL-ARCHITECTURE-MATRIX.md).

---

## 1. Pattern register

| id | Pattern | Source |
|---|---|---|
| **P01** | Child scope is an effect of its parent — one structural ownership tree, transitive disposal | `vendor/cordis/src/fiber.ts:265` |
| **P02** | Resources acquired as labelled effects returning disposers; reverse order, awaited, idempotent *within a group* | `fiber.ts:418-441` |
| **P03** | No acquisition while the owner is tearing down (`INACTIVE_EFFECT`) | `fiber.ts:418-422` |
| **P04** | Capability = name + availability predicate, bound to the owner's lifetime; consumers declare `inject` and wait in `PENDING` | `service.ts:42-58`, `registry.ts:29-51` |
| **P05** | A capability declares its real enforcement level and **refuses rather than degrades** | `sandbox-local/src/index.ts:181-186,233-237`; `subagent/src/out-of-process.ts:57-63` |
| **P06** | "The command did not run" is checked **before** "the command was denied" | `bash-sandbox/src/index.ts:119-123` |
| **P07** | Fail-closed selection: no usable runner ⇒ error, never the unwrapped command | `sandbox/src/index.ts:124-157` |
| **P08** | Ownership is a process **range**; `waitForExit` means the range is empty, not the child exited | `subprocess-local/src/spawn.ts:418-421`; `index.ts:199-205` |
| **P09** | Graceful-first ladder (EOF → grace → TERM → grace → KILL → unbounded wait), children drained child-first | `subagent-acp/src/run.ts:185-212`; `subagent/src/index.ts:333-348` |
| **P10** | Spawn spec with **no defaults** — argv, cwd, stdio, grace, signal, env all explicit | `subprocess/src/types.ts:71-107` |
| **P11** | Structural env scrub at the single spawn seam + deterministic child env | `subprocess/src/index.ts:66-80`; `bash-local/src/index.ts:27-32` |
| **P12** | Layered timeouts producing a **typed outcome naming the layer**, never abandoning the work | `guard/timeout-policy/src/index.ts:55-80`; `bash-local/src/index.ts:255-267` |
| **P13** | Authority only narrows: restriction intersects, approval pinned, only explicit overrides propagate, depth persisted, capture synchronous | `subagent/src/child-agent.ts:50-59,200-252` |
| **P14** | Append-only store whose interface has **no update and no delete verb**; logical deletion is a new event | `session-persistence/src/index.ts:147-198`; `session/src/types.ts:439-441` |
| **P15** | `seq === index`, enforced independently at 4 layers; `time` is never the ordering key | `session/src/index.ts:567-581,743`; `storage-contract.ts:145-151` |
| **P16** | Validation at the **append site** — a bad event fails before the log grows | `session/src/index.ts:713-715,749` |
| **P17** | Every read model is a pure fold; caches explicitly non-authoritative; from-scratch oracle test | `session-projection-cache/src/index.ts:9-14`; `tests/derived-cache.spec.ts:17-27` |
| **P18** | Unknown **required** event ⇒ refuse to reconstruct; only explicit `ignorable` is skippable | `session/src/types.ts:478-487` |
| **P19** | Deterministic typed crash closers: `TOOL_OUTCOME_UNKNOWN` vs `TOOL_NOT_STARTED`, timestamps reused | `session/src/repair.ts:15-18,87-88,119-133` |
| **P20** | Kernel-held write lease acquired **before** the cold read | `session-persistence-jsonl/src/lease.ts`; `agent-loop/src/index.ts:894-904` |
| **P21** | Fork cut at the last completed structural boundary; refused inside an open turn (`OPEN_TURN`) | `session/src/index.ts:1286-1294` |
| **P22** | Raw vs resolved config as a first-class distinction, deep-frozen, with per-value layer provenance | `settings/src/index.ts:436,730-766`; `launch-environment/src/index.ts:31-52` |
| **P23** | Static verification of composition: interpolation positions, parse-only expression check, resolution, plane separation | `scripts/verify-cordis-config.ts:104-162,503-544` |
| **P24** | Generated catalogs with `--check` twins, **fail-closed in both directions** | `scripts/gen-cordis-catalog.ts:55-59,1167-1192` |
| **P25** | Request-header **class pinning** with a bounded drift budget; session-dependence must be declared | `session-snapshot/src/manifest.ts:12-52`; `suite.ts:10-17` |
| **P26** | Identity by **name only**, no content hash (profiles, presets) — *listed as a pattern to reject* | `app-boot/src/profile.ts:5-14,79` |
| **P27** | The code taxonomy owns retryability; `MISSING_CREDENTIAL` vs `INVALID_CREDENTIAL` split "because the fix differs" | `llm/src/error.ts:41-48`; `retry-policy.ts:18-24` |
| **P28** | Foreign codes are not our taxonomy ⇒ flatten to `UNKNOWN`; route on the code, never on the message | `adapter-failure.ts:104-107`; `llm/src/error.ts:13-22` |
| **P29** | The failure is recorded as a durable typed event in a `finally`, whatever the control path does | `agent-loop/src/agent.ts:328-345` |
| **P30** | Invariant violations are **uncontainable** and name the owning package | `invariants/src/index.ts:50-66,137-142`; `settings/src/index.ts:833-841` |
| **P31** | Invariants armed **in every test run** of every tier, before any root plugin activates | `scripts/test-invariants.ts:60,125-205` |
| **P32** | A named, enumerated fault-injection surface (24 behaviours), with the distribution labelled as test pressure not incident rate | `llm-mock-server/src/index.ts:16-68` |
| **P33** | Replay mocks **only** the model stream; tools are re-executed for real and diffed; the fixture is both input and expected output | `llm-replay/src/index.ts:458-499,1095-1097`; `suite.ts:3-4` |
| **P34** | `assertConsumed` — the reproduction must consume exactly the recorded call structure | `llm-replay/src/index.ts:1100-1114` |
| **P35** | Teardown asserted against the OS: `kill(pid,0)`/`ESRCH` liveness, `existsSync` on temp dirs | `subprocess-local/tests/process-exit.spec.ts:20-55`; `linux-scope.spec.ts:250-260` |
| **P36** | Cost and latency are **projections of the log**, with loud failure on count misalignment and orphan-result rejection | `session-stats/src/types.ts:22-39`; `token-meter/src/route-pricing.ts:29-45` |
| **P37** | Provenance enforced at commit time: vendored source cannot change without its manifest in the same commit | `scripts/check-vendor-manifest.sh` |
| **P38** | Event bus as control: `waterfall` listeners can veto built-in behavior by not calling `next()` — *pattern to reject* | `vendor/cordis/src/events.ts:224-242`; `agent-loop/src/agent.ts:448-464` |
| **P39** | Plugins mounted by runtime string, invisible to static checking, compensated by a hand-maintained mirror list — *pattern to reject* | `scripts/verify-cordis-config.ts:40-55` |
| **P40** | Declared-but-unenforced metadata (`applies: 'restart'` is read by nobody) — *pattern to reject* | `settings/src/types.ts:45`; no consumer |

---

## 2. The matrix

Read each row as: *against this family, these patterns would have done this.* Blank buckets are omitted.

| # | Family | PREVENT | REDUCE | DETECT | NOT HELP (notable) |
|---|---|---|---|---|---|
| 1 | `FAM-IDENTITY` | P15, P26-inverted | P22, P20 | P24, P25, P34, P37 | P05, P09, P11, P12, P32 |
| 2 | `FAM-OUTCOME` | P05, P06, P19 | P27, P28 | P17, P31 | P08, P20, P22, P25, P37 |
| 3 | `FAM-PROSE` | P28 | P16, P22 | P23, P24 | P08, P09, P12, P35, P36 |
| 4 | `FAM-RETRY` | P27 | P05, P06, P12 | P36, P31 | P14, P15, P21, P25 |
| 5 | `FAM-RECOVERY` | P18, P21 | P19, P20, P17 | P34, P35 | P05, P11, P23, P32 |
| 6 | `FAM-OWNERSHIP` | P01, P10 | P13, P11 | P23, P35 | P15, P18, P27, P32, P36 |
| 7 | `FAM-TOOL` | P05, P07, P10 | P04, P06 | P23, P32 | P14, P15, P21, P25, P36 |
| 8 | `FAM-PROCESS` | P01, P03, P08 | P02, P09, P12 | P35 | P18, P22, P25, P27, P28 |
| 9 | `FAM-SCHEDULER` | P01 | P13 | P23, P24 | P08, P12, P19, P32, P36 |
| 10 | `FAM-APPROVAL` | P13, P22 | P14 | P24, P25 | P08, P09, P11, P32, P35 |
| 11 | `FAM-RELEASE` | P14, P18 | P15, P37 | P24 | P05, P08, P11, P12, P32 |
| 12 | `FAM-BENCH` | P25, P33 | P26-inverted | P34, P24 | P02, P03, P09, P11, P19 |
| 13 | `FAM-JUDGE` | P28 | P13 | P23 | P08, P14, P15, P20, P35 |
| 14 | `FAM-TYPED-OUTCOMES` | P05, P06 | P28 | P31, P32 | P14, P20, P21, P25, P37 |
| 15 | `FAM-BUDGET` | P36 | P27, P12 | P17, P31 | P03, P11, P18, P23, P35 |
| 16 | `FAM-EVIDENCE-SEMANTICS` | P15, P16 | P19 | P17, P34 | P09, P11, P13, P32, P35 |
| 17 | `FAM-QUALIFICATION` | — | P29, P27 | P32, P36 | P01, P02, P03, P11, P21 |
| 18 | `FAM-QUALIFICATION-MEASUREMENT` | P17, P36 | P14 | P24, P34 | P05, P08, P09, P11, P13 |
| 19 | `FAM-PROOF-PLACEMENT` | — | — | — | *everything — see §3.19* |
| 20 | `FAM-PLAN-OWNERSHIP` | — | — | P24 | *nearly everything — see §3.20* |
| 21 | `FAM-PROVIDER` | — | P12, P27 | P29, P32, P36 | P01, P14, P15, P23, P35 |
| 22 | `FAM-MODEL-CAPABILITY` | — | — | P25, P34, P36 | *everything else — see §3.22* |

"P26-inverted" means the *opposite* of their pattern: content-hashed identity rather than name-only. Their
pattern as written would make these families worse, which is why it is a REJECT in §1.

---

## 3. Where the verdict needs the reasoning

Most cells above are mechanical. These are not.

### 3.2 `FAM-OUTCOME` — PREVENT, and by three independent mechanisms

SS-96 was: a check reported `FAILED` for evidence that did not execute, and because `_absent_stages` returns `[]`
once anything has FAILED, an environment failure was charged to the developer's quality budget. Three separate
harness patterns each break that chain on their own. **P06** puts "did not run" ahead of "was refused" as a
check-order rule. **P05** makes the capability itself say `partial`/`unavailable` rather than producing a result
that looks like a verdict. **P19** gives the interrupted case a typed `TOOL_OUTCOME_UNKNOWN` instead of a gap
that a later reader has to interpret. Any one of them turns the SS-96 chain into an expressible, named state.

This is also the strongest convergent evidence in the whole study: two independently designed agent systems
arrived at the same distinction, which supports treating `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` as a
domain-level requirement rather than an AISEF idiosyncrasy.

### 3.4 `FAM-RETRY` — PREVENT by P27 specifically

D-006 was "credential rejection charged to quality attempts". **P27** is the precise counter: retryability is a
property of the error code, fixed once in the taxonomy, and credentials are split into `MISSING_CREDENTIAL` and
`INVALID_CREDENTIAL` *because the fix differs*, with the latter deliberately non-retryable. A call site cannot
decide to retry something the taxonomy says is not retryable. Note what this does **not** do: it says nothing
about *whose budget* pays, because the harness has no owner concept (§J.5 of the harness study). P27 prevents the
retry; AISEF's owner field is still what prevents the mis-charge.

### 3.8 `FAM-PROCESS` — PREVENT, and this is the cleanest structural win available

D-024 was "TemporaryDirectory cleanup races a writer inside a session's `.git`". **P08** makes that race
unexpressible: cleanup cannot proceed because emptiness of the whole descendant *range* has not been proven, and
proving it is a measured operation (`kill(pid,0)` polling, `TasksCurrent`, `isJobEmpty`), not an inference from
the direct child's exit code. **P01** and **P03** close the two adjacent shapes — a resource acquired outside any
scope, and a resource acquired while its scope is already tearing down. **P35** is the test form: assert against
the OS that the pid is gone and the directory is absent.

### 3.12 `FAM-BENCH` — P33 is the load-bearing one

D-003/D-015/D-016 are cohort contamination and holdout integrity. **P33** is the deepest answer and it is a
refusal rather than a mechanism: tool results are recorded but **never replayed** — they are re-executed for
real and diffed. A system that replays its own recorded tool results is checking itself against its own prior
output, which is self-certification wearing a test's clothes. **P25** (request-header class pinning with a
bounded drift budget) is the complementary control: it makes the *input* side of a comparison byte-stable and
forces any session-dependence to be declared instead of quietly widening a class.

### 3.13 `FAM-JUDGE` — P28 prevents the mechanism, not the policy

D-002 was "a blocking gate decision can rest on the model reviewer alone". **P28** — *foreign codes are not our
taxonomy; anything that is not a `HarnessError` flattens to `UNKNOWN`* — prevents the *mechanism* by which model
or third-party text becomes a control code. It does not prevent the *policy* choice of letting a model's verdict
block a gate; no external pattern addresses that, because the harness has no gate. The policy half stays an
AISEF-specific invariant.

### 3.17 `FAM-QUALIFICATION` — no PREVENT is available, and that is the finding

SS-94 (a provider outage reported as the model's stop) and SS-95 (false-BLOCK measured only at trunk) are
defects in *the measuring apparatus*. Nothing in the harness prevents them, because the harness does not qualify
anything — it has no equivalent of W0/W1. **P29** and **P27** reduce SS-94's shape by making the failure's
class a recorded, typed fact rather than something the measurer infers. **P32** and **P36** detect: an offline
fault-injection surface lets the measurer's own classification be tested against known-injected faults, and
log-derived accounting cannot disagree with the log. The residual — *who verifies the verifier* — is untouched by
anything external and is handled in the adversarial review of
[`AISEF-V2-ARCHITECTURE-RECOMMENDATION.md`](AISEF-V2-ARCHITECTURE-RECOMMENDATION.md).

### 3.19 `FAM-PROOF-PLACEMENT` — no external pattern helps at all

PLAN-V2.1-DEFECT-001: a criterion's parent proof state depends on whether the developer's test file imports the
product at module level, because whether a test *collects* at the parent SHA is a property of the file, not of
the criterion. I looked for an analogue and there is none. DeepSeek Harness has no proof obligations, no
criteria, and no notion of a claim whose truth is evaluated at two revisions. The nearest structural cousin is
**P21** (a fork cut only at a completed boundary), which is about *when* a state is well-defined, not about
*what* a claim is about.

**This is the most important negative result of the study.** The defect that ended V1's delivery qualification
lies in a design space the external system does not occupy, so the fix must be ours: the Behavior Contract and
Canonical ProofSpec of
[`AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md`](AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md) exist precisely to make a
proof obligation's semantics independent of where a developer puts a file (ARCH-LESSON-001). No amount of
borrowing substitutes for that work.

### 3.20 `FAM-PLAN-OWNERSHIP` — likewise almost nothing

`PLAN_OVERLAP` and `PLAN_PRECONDITION_MISSING` are defects in a *plan*: a criterion assigned to a story that does
not own the behaviour it asserts. The harness has no plan. **P24** is the only transferable piece, and only by
analogy: the *bidirectional* fail-closed catalog rule ("present in reality but absent from the catalog" and
"present in the catalog but absent from reality" are both hard errors) is the right shape for a criterion-to-
behaviour ownership map, and it is exactly what our ownership audit does when it refuses a criterion with no
`BEHAVIOUR` entry. Everything else about plan ownership is ours to design.

### 3.21 `FAM-PROVIDER` — REDUCE and DETECT only, by construction

Provider instability cannot be prevented by any harness. What the patterns give is (a) **P12**, a typed timeout
that names which layer fired and never abandons the work, (b) **P27**, retryability decided by the code rather
than at the call site, and (c) **P32**, the decisive one for us: a local fault-injection server with 24 named
behaviours means the *kernel's own provider-failure routing* can be qualified offline and deterministically,
instead of being diagnosed by hand against a live endpoint at $80 a run. That converts a whole class of expensive
live evidence into cheap semantic evidence, which is directly what the owner's §13 asks for.

### 3.22 `FAM-MODEL-CAPABILITY` — nothing prevents it; three things measure it honestly

The W1 verdict's §C conclusion — the model does not complete the delivery workload even when kernel, plan,
environment and provider are sound — is a capability ceiling, not a defect. No architecture removes it. What
**P25**, **P34** and **P36** do is make the *claim* rigorous: class-pinned request headers mean two runs are
comparable, `assertConsumed` means a run that took a different shape is not silently scored as the same run, and
log-derived accounting means the cost of the ceiling is measured rather than estimated. The honest use of these
patterns is to make "the model could not do it" a defensible measurement rather than an impression.

---

## 4. Patterns that are innocent

Recorded deliberately: measuring every candidate and reporting the ones with no effect is part of how this
programme works.

- **P02 (labelled effects, reverse-order disposal)** helps `FAM-PROCESS` and `FAM-OWNERSHIP` and *nothing else*.
  It is easy to over-credit because it is the most visible Cordis idea. It also does **not** solve ordering
  between sibling resources — see [`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §2.
- **P11 (env scrubbing)** is worth adopting on its own merits but is innocent of every family in the register:
  none of our 22 arose from environment leakage. It appears in the NOT-HELP column nine times.
- **P09 (the kill ladder)** touches only `FAM-PROCESS`. Its value is operational, not defect-family coverage.
- **P32 (fault injection)** does not *prevent* a single family. Its entire value is turning live, expensive,
  hand-diagnosed evidence into offline deterministic evidence — a qualification-economics win, not a correctness
  win.
- **P20 (write lease)** bears only on `FAM-RECOVERY` and `FAM-IDENTITY`, though it also underwrites two of my own
  standing operational rules, which the register does not cover because they never became product defects.
- **P37 (commit-time provenance guard)** detects for `FAM-RELEASE` and `FAM-IDENTITY` only. It is cheap and worth
  having; it is not a broad control.

And the four rejected patterns, for completeness: **P26** (name-only identity) would actively worsen
`FAM-IDENTITY` and `FAM-BENCH`; **P38** (bus-as-control) would worsen `FAM-JUDGE`, `FAM-RETRY` and every
determinism property; **P39** (runtime-string plugin mounting) would worsen `FAM-SCHEDULER` and `FAM-TOOL` by
putting composition beyond static reach; **P40** (declared-but-unenforced metadata) is the general form of the
failure that makes an invariant register worthless, and is the reason **P31** matters.
