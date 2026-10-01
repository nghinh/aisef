# DeepSeek Harness — architecture study

**Revision studied.** `deepseek-ai/deepseek-harness` commit `ddefc45fbc7f8e46dd73185e68295696d1297887` (branch
`master`, package `dsh` 0.1.6-alpha.2), retrieved 2026-09-21. Framework layer vendored at `vendor/cordis`
(Cordis 4.0.0-rc.7 from `cordiverse/cordis` `56b3d4f725681cf4556c1a8695a709cc3b6eed74`). Full manifest in
[`SOURCES-PINNED.json`](SOURCES-PINNED.json). Shape: pnpm monorepo, 60 packages, 4 apps, 1227 spec files.

Companion documents: [`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) (the framework layer and its
static-verification tooling) and [`V1-DEFECT-FAMILY-REGISTER.md`](V1-DEFECT-FAMILY-REGISTER.md) (the 22 AISEF
families referenced below).

Labels: **FACT** — read from source at the cited line. **OBSERVATION** — a pattern across facts.
**INFERENCE** — my reading, not stated in the source. **AISEF** — recommendation. All paths are relative to the
harness checkout.

**Contents** (the owner's areas A–L; written in the order the evidence arrived, not alphabetically):
[G. Sandbox, shell, process](#g-sandbox-shell-and-process-execution) ·
[F. Subagents](#f-subagents) ·
[A. Core architecture](#a-core-architecture) ·
[B. Capability seams](#b-capability-seams) ·
[C. Session model](#c-session-model) ·
[D. Event and message model](#d-event-and-message-model) ·
[E. Replay and reproducibility](#e-replay-and-reproducibility) ·
[I. Configuration and profile model](#i-configuration-and-profile-model) ·
[J. Error model](#j-error-model) ·
[K. Testing strategy](#k-testing-strategy) ·
[L. Observability and diagnostics](#l-observability-and-diagnostics)

---

## G. Sandbox, shell and process execution

### G.1 The spawn seam applies no defaults

**FACT.** The process abstraction is a Cordis service seam `ctx.subprocess` — an abstract class with exactly
three methods, `resolveExecutable`, `spawn` (synchronous handle) and `spawnTerminal` (PTY)
(`packages/subprocess/subprocess/src/index.ts:117-163`). Its spec type requires argv, cwd, per-stream stdio,
`graceMs`, `signal` and `env` **explicitly; no field is defaulted**
(`packages/subprocess/subprocess/src/types.ts:71-107`), and `cwd` rejects null bytes
(`packages/subprocess/subprocess-local/src/runner-launch.ts:306`).

**AISEF — ADOPT.** `FAM-TOOL` (D-009, D-013, D-028) is the family where a verification command is trusted to be
runnable in an environment nobody described. A spawn spec that cannot be constructed without naming its
execution environment removes the ambient-default path that family lives in. This costs us nothing: AISEF
already knows the values; it just does not currently require them.

### G.2 Ownership is a process *range*, not a child handle

**FACT.** POSIX children are spawned `detached: platform !== 'win32'`
(`packages/subprocess/subprocess-local/src/spawn.ts:465`) — each child is its own session and process-group
leader. Signals go to the negative pgid with a direct-child fallback (`spawn.ts:130-155`).

**FACT.** `waitForExit()` resolves only when the **managed range** is empty, not when the direct child settles
(`spawn.ts:418-421`, contract at `types.ts:188-195`). Ownership is released on whole-range emptiness
(`packages/subprocess/subprocess-local/src/index.ts:199-205`). On Windows-Job mode, emptiness is proved by
polling `isJobEmpty` every 10 ms (`spawn-runner.ts:323,368-372`) — the only mode that observes descendants that
escaped the process group. On Linux, by polling the transient unit's `TasksCurrent` with backoff to 5 s
(`linux-scope.ts:342-433`).

**FACT.** `terminate()` returns `void` — it is fire-and-forget (`types.ts:187`). Proving termination is a
separate verb, `waitForExit()`.

**OBSERVATION.** Two properties, both deliberate: *ask to stop* and *prove it stopped* are different calls, and
*stopped* is defined over the whole descendant range rather than the process you happen to hold a handle to.

**AISEF — ADOPT, this is the fix for `FAM-PROCESS`.** D-024 was "TemporaryDirectory cleanup races a writer
inside a session's `.git`". That race exists precisely because AISEF waits on the direct child and then removes
the directory, while a grandchild still holds a write. The harness's answer is structural: the cleanup cannot
proceed because emptiness of the *range* has not been proven. Our `StoryScope` disposal (see
[`AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md`](AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md)) must
adopt the same definition: a worktree may not be removed until the process range that could write to it is
provably empty, and "provably" means measured, not assumed from the direct child's exit code.

### G.3 The kill ladder, and what it does on each platform

**FACT.** `bindManagedProcess` owns escalation (`spawn.ts:346-366`): **SIGTERM → wait `graceMs` → SIGKILL**,
both delivered to the whole managed range. `graceMs` for bash is 3000 ms
(`packages/shell/bash-local/src/index.ts:35`). After the direct child settles, still-open collected pipes get a
further `graceMs` before the outcome is forced (`spawn.ts:403-410`) — a guard against an inherited fd held by a
survivor.

**FACT.** Platform divergence is explicit, not incidental:

| mode | stop mechanism | citation |
|---|---|---|
| POSIX fallback | `kill(-pgid)`, then direct child | `spawn.ts:130-155` |
| Windows fallback | `taskkill /PID <pid> /T /F` — **no staging**, outcome deliberately unchecked | `spawn.ts:113-122` |
| Linux scope | `systemctl --user kill --kill-whom=all --signal=…` | `linux-scope.ts:219-225` |
| Windows Job | IPC `{type:'terminate'}` → `TerminateJobObject` | `windows-job.ts:92`, `spawn-runner.ts:346-353` |
| PTY | descendants TERM → grace → KILL → re-scan, then the shell | `subprocess-local/src/terminal.ts` |

**AISEF.** We already learned the Windows/POSIX split the expensive way (CI on Windows; the memory rule "Windows
là ràng buộc thật"). The transferable part is that the harness makes the *weaker* platform's weakness explicit
rather than pretending the ladder is uniform — see G.4.

### G.4 Capability honesty: the system says what it cannot enforce

This is the single most important pattern in the harness for AISEF, and it appears in three independent places.

**FACT — containment.** `selectContainmentMode` chooses `linux-scope`, `windows-job`, or `fallback`
(`subprocess-local/src/index.ts:209-228`); all of darwin and all Windows *terminals* fall back. `warnFallback`
then states precisely what is no longer guaranteed (`index.ts:230-247`):

> "…descendants that escape the process group or direct-parent tree are not guaranteed to terminate or delay
> `waitForExit()`"

with reason `'macOS has no supported persistent process-range owner'`.

**FACT — sandbox.** Two runners declare `partial` enforcement rather than claiming success: landlock on older
ABI (`sandbox-local/src/index.ts:233-237`) and `windows-acl`, because `WRITE_RESTRICTED` must keep `Everyone` in
the restricting list and NTFS hard links alias paths (`index.ts:181-186`).

**FACT — subagents.** Out-of-process providers advertise `NO_START_CAPABILITIES`
(`packages/subagent/subagent/src/out-of-process.ts:57-63`), so a request needing `agentOptions`, `outputSchema`,
`maxDepth`, `toolFilter` or `persona` is **rejected up front rather than silently ignored**
(`packages/subagent/subagent/src/index.ts:676-692`).

**OBSERVATION.** Three subsystems, one rule: a capability reports its actual enforcement level, and a request it
cannot honour is refused rather than degraded.

**AISEF — ADOPT as a first-class contract property.** This is `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` and
`FAM-OUTCOME` / `FAM-TYPED-OUTCOMES` seen from the provider side rather than the gate side. AISEF v1 fixed the
*gate* (SS-96: no check may report FAILED for evidence that did not execute). The harness shows the other half:
**the capability itself declares `full` / `partial` / `unavailable`, and that declaration is part of the
evidence.** Combined with Cordis's `[Service.check]` availability predicate
([`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §3), the v2 capability contract should carry an
enforcement level that the Evidence Store records, so a run qualified under `partial` sandboxing can never be
compared against one qualified under `full`.

### G.5 "The command did not run" is checked before "the command was denied"

**FACT.** Each sandbox backend carries its own stderr dialect (`DENIAL_SIGNATURES`,
`sandbox-local/src/index.ts:205-213`) and separate structured `RUNNER_FAILURE_RULES` (`index.ts:231-240`). The
consumer checks **runner failure first** — "the command did not run" — and only then denial
(`packages/shell/bash-sandbox/src/index.ts:119-123`).

**OBSERVATION / AISEF.** That check order *is* SS-96's invariant, implemented as a consumer discipline. It is
independent convergent evidence that the distinction between "did not execute" and "executed and was refused" is
an architectural requirement of any sandboxed agent system, not an AISEF idiosyncrasy. **CONFIRM and keep** —
and note that they enforce it by convention at one call site, where we enforce it by typed outcome in the
kernel. Ours is the stronger form; do not weaken it.

### G.6 Fail-closed sandbox selection

**FACT.** Selection is platform-first, probe-second:
`PLATFORM_CHAINS = { linux: ['bwrap','landlock'], darwin: ['seatbelt'], win32: ['windows-acl'] }`
(`sandbox-local/src/index.ts:159-166`); a single-candidate chain is selected **without probing**
(`index.ts:150-158`). No usable runner yields `SandboxUnavailableError` / `SANDBOX_UNAVAILABLE` — it **never
returns the unwrapped argv** (`packages/sandbox/sandbox/src/index.ts:124-144,152-157`).

**FACT.** Policy travels **per call**, not per provider, so bash can run `read-only` while a child agent runs
`workspace-write` simultaneously (`sandbox/src/index.ts:61-72`). Resolution order in `ctx.sandboxPolicy`:
explicit approved mode > the session's last `sandbox/mode` event > deployment default `read-only`
(`packages/sandbox/sandbox-policy/src/index.ts:113,164-171`). The session override lives as a **session-log
event**, not external config (`sandbox-policy/src/session-mode.ts:44-55`).

**AISEF — CONFIRM fail-closed; ADAPT the per-call policy (see G.7).** Storing the override as a log event rather
than mutable config is the right shape and matches our Immutable Provenance invariant: the effective mode at any
point is a function of the log prefix, which is exactly a deterministic projection.

### G.7 Where their per-call policy leaks — and why AISEF must not copy it verbatim

**FACT.** Hook commands execute through `ctx.shell` (`packages/hooks/hook-protocol/src/runner.ts:87`) and pass
**no** `sandboxPolicy`. `SandboxBashExecutor.resolve` therefore stamps `this.ctx.sandboxPolicy.resolve()` with no
session (`packages/shell/bash-sandbox/src/index.ts:86`), so hooks run under the **deployment default** mode and
the **fallback workspace root** (`process.cwd()`), not the calling session's mode or cwd.

**INFERENCE.** This is a latent defect of exactly the shape AISEF names `FAM-SCHEDULER` ("the scheduler uses
*declared* scope, not *effective* scope", D-031) and `FAM-OWNERSHIP`. An optional policy parameter means every
caller is a place the default can silently win, and static analysis cannot tell a deliberate omission from a
forgotten one.

**AISEF — ADAPT, do not copy.** Keep per-scope policy, but **derive it from the scope rather than passing it**:
the confinement a call runs under should be a property of the `StoryScope` the caller is executing inside
(Cordis-style structural ownership), not an argument that can be omitted. Where a parameter is unavoidable, make
it non-optional in the type so an omission is a compile error rather than a default. This is also the argument
for §18's Typed Ownership invariant being about *structure*, not about diligence.

### G.8 Timeouts are layered, classified, and never abandoned

**FACT.** Three independent layers:

1. **Executor** — `using d = deadline(spec.signal, spec.timeoutMs, 'BASH_TIMEOUT')`
   (`bash-local/src/index.ts:229`); the derived signal goes into the spawn spec (`:194`). Expiry drives the same
   TERM → grace → KILL ladder (`spawn.ts:373-374`). Defaults: `timeoutMs` 120 000, cap `maxTimeoutMs` 600 000,
   clamped in `resolve()` (`:107-108,149`).
2. **Tool-level** — `packages/guard/timeout-policy/src/index.ts:55-80` swaps a derived deadline onto
   `exec.signal` for *any* tool call and replaces the result with a structured `TOOL_TIMEOUT` when its own timer
   fired. Critically, it **never races or abandons the tool promise** (`:73-76`).
3. **Pipe drain** — a post-exit `graceMs` window before the outcome is forced (`spawn.ts:403-410`).

**FACT.** The result is **classified, not thrown**: `timedOut: timeoutOf(d.signal,'BASH_TIMEOUT') !== undefined`,
with `aborted` distinguished for an outer deadline (`bash-local/src/index.ts:255-267`). Background (`start`) runs
ignore `timeoutMs` entirely — "callers stop them through `kill()` or `spec.signal`" (`:285-287`).

**AISEF — ADOPT two properties.** (a) A timeout produces a **typed outcome that names which layer fired**, not an
exception — AISEF's provider incidents this cycle (three tool-smoke timeouts at the 300 s cap on
`ds/deepseek-v4-pro`, `FAM-PROVIDER`) were classified correctly only because the driver did it by hand; the
kernel should do it. (b) A timeout must never abandon the underlying work — abandoning is how orphans
(`FAM-PROCESS`) and double-charged budgets (`FAM-BUDGET`, SS-64) are produced.

### G.9 Environment scrubbing is structural, not a reporting rule

**FACT.** One canonical base, `scrubbedParentEnv()` (`packages/subprocess/subprocess/src/index.ts:66-80`):

```ts
if (value !== undefined && !SENSITIVE_ENV_PATTERN.test(key) && !key.toUpperCase().startsWith(DSH_ENV_PREFIX))
  env[key] = value
```

with `SENSITIVE_ENV_PATTERN = /KEY|PASSWORD|SECRET|TOKEN/i` (`:47`). Every `DSH_*` name is stripped
case-insensitively (Windows rationale at `:55-60`). Proxy variables are re-added afterwards (`:75-78`). Explicit
spec `env` merges **after** the scrub, so a deliberately forwarded credential survives and `undefined` acts as a
tombstone (`types.ts:99-106`). The runner bootstrap additionally strips all `NODE_*`/`TSX_*` names before
re-entering (`runner-launch.ts:23,74-79`). Bash adds `ENV_OVERRIDES = { NO_COLOR:'1', TERM:'dumb', PAGER:'cat',
GIT_PAGER:'cat' }` (`bash-local/src/index.ts:27-32,198`).

**AISEF — ADOPT.** AISEF's credential handling is a discipline I follow when reporting. Theirs is a structural
property of the one function every spawn goes through, with "deliberately forwarded" expressible and "removed"
expressible as a tombstone. Deterministic environment (`NO_COLOR`, `TERM=dumb`, `PAGER=cat`) is also directly
relevant to our Semantic Determinism invariant: tool output that varies with the terminal is evidence that
varies with the terminal.

### G.10 Network: the boundary they deliberately did not ship

**FACT — negative, and load-bearing.** There is **no egress restriction anywhere**. bwrap passes `--unshare-pid`
but **not** `--unshare-net` (`packages/sandbox/sandbox-local/src/profiles.ts:17`); the seatbelt profile begins
`(allow default)` and denies only `file-write*` (`profiles.ts:51-57`); landlock grants are filesystem paths only
(`profiles.ts:30-36`). The mode vocabulary is explicitly file-effects-only — "Network and process visibility are
outside this vocabulary" (`packages/sandbox/sandbox/src/index.ts:23-29`). The design note records the reasoning:

> a web-only network knob while bash `curl` runs free would be a false boundary
> — `.agents/notes/implemented/feature/2026-07-14-cross-family-fs-sandbox.md:56`

**AISEF — ADOPT the principle, and audit ourselves against it.** *Do not ship a boundary the weakest path
defeats.* A control that can be bypassed by an ordinary tool call is not a control; it is a claim in the
evidence that is false. This belongs in the anti-patterns section and is a direct obligation on AISEF v2: every
isolation property we assert in a qualification record must name the weakest path that could violate it, or not
be asserted.

### G.11 Filesystem access control: three layers, and the primary one is pre-write

**FACT.** `SandboxedFileSystem.checkedTarget` (`packages/fs/fs-sandbox/src/index.ts:122-144`) runs **before**
`writeText`/`editText` reach the syscall. Under `workspace-write` it **re-canonicalizes the path now** and
requires containment under `writableRoots(policy)`, then passes the *fresh* target downstream so the checked
identity is the mutated one:

```ts
const fresh = await this.resolve(target.displayPath)
for (const root of writableRoots(policy)) { if (await isPathUnder(fresh.targetKey, root)) { contained = true; break } }
if (!contained) throw new FsError(..., 'FS_SANDBOX_DENIED')
```

The module header states this is **containment, not a kernel boundary**, and that a residual ancestor-symlink
TOCTOU is accepted (`fs-sandbox/src/index.ts:9-18`). Reads are never fenced (`:6-8`). Writable roots come from
one shared helper so the fs fence and the Seatbelt profile **cannot drift** (`packages/sandbox/sandbox/src/roots.ts:1-12`).

**FACT.** Layer 2 is the kernel runners of G.6; layer 3 is optional `PreToolUse` / `PostToolUse` hooks that can
`deny` before or `block` after (`packages/hooks/hooks-claude-code/src/index.ts:239-251`).

**FACT.** A separate observation policy enforces read-before-write, keyed by session: unseen/absent ⇒
`createIfAbsent`, seen ⇒ `replaceIfVersion` at the observed version
(`packages/fs/fs-observation-policy/src/index.ts:62-70`). Without the plugin, mutations are unconditional
(`:1-6`).

**AISEF — three takeaways.** (a) **Re-canonicalize at the moment of use and check the fresh identity** — this is
`FAM-IDENTITY` ("a control decision selects its evidence by … position/spelling instead of by an exact
identity") applied to paths. (b) **One shared source for the writable-root set** so the enforcement layer and
the policy description cannot disagree — the same "derive, don't duplicate" discipline as the `--check` twins in
[`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §6.5. (c) **Document the accepted residual
risk in the module that carries it** — their TOCTOU note is a model for how AISEF should record the limits of a
claim next to the code that makes it.

### G.12 Orphans: what they guarantee, and where they do not

**FACT.** Two reapers: normal fiber disposal calls `terminate()` on every live handle **and awaits
`waitForExit()` on the range** — "so even a surviving descendant cannot outlive the fiber"
(`subprocess-local/src/index.ts:104-135`); and `process.prependListener('exit', onHostExit)` (`:79`) sends
synchronous SIGKILL to every live range and terminal (`:87-102`).

**INFERENCE (agent-reported, and consistent with the source).** A hard-killed harness (SIGKILL, hard crash)
leaves the tree running: `process.on('exit')` does not fire and there is no supervisor process. The only
mitigation is bwrap's `--die-with-parent` (`profiles.ts:17`), which covers sandboxed bash on Linux only. No
orphan reaper exists (searched `packages/subprocess`, `packages/boot`, `apps/cli/src`, and `orphan` repo-wide).

**AISEF.** AISEF's `FAM-PROCESS` closure (INV-L.1) faces the identical residual. The honest position is theirs:
name the uncovered case rather than claim coverage. For v2, the cheap improvement over their design is to make
the *next* run's preflight detect and report a previous run's surviving range, so the gap becomes a typed
observation instead of silence.

### G.13 Harness-level signal handling

**FACT.** The only production `SIGINT`/`SIGTERM` handlers are in the CLI boot path
(`apps/cli/src/profile-boot.ts:290-291`), installed **before** `boot()` settles, deliberately (`:285-286`).
`interrupt` aborts a startup controller and calls `ProcessShutdown.interrupt` (`:281-284`), which is escalating
(`apps/cli/src/process-shutdown.ts:52-75`): first signal → dispose the app fiber with a **5 s** budget
(`PROCESS_SHUTDOWN_TIMEOUT_MS`, `:4`) then `process.exit`; a **second** signal while disposal is pending
force-exits immediately (`:70-73`).

**FACT.** There is no explicit signal forwarding to children. Propagation is structural: fiber dispose →
`LocalSubprocessRuntime` teardown effect (`subprocess-local/src/index.ts:77-84`) → `disposeManagedProcesses` →
the per-range ladder.

**INFERENCE.** Because POSIX children are `detached: true`, a terminal Ctrl-C reaches only the harness's own
process group, **not** the children. That is what makes range ownership meaningful, but it means the harness's
own teardown is the *only* path that stops the tree.

**AISEF — ADOPT the escalating shutdown with a bounded budget and a second-signal override.** AISEF runs for
hours and the operator will interrupt. A bounded disposal budget that still writes the evidence, plus an
explicit "press again to abandon" path that *records that it was abandoned*, turns an operator interrupt from an
unexplained gap in the record into a typed terminal state.

---

## F. Subagents

### F.1 Spawning

**FACT.** The seam is `ctx.subagents`, a named-provider registry
(`packages/subagent/subagent/src/index.ts:198`). `SubagentRuntime.start(name, request)` (`:591-621`) is: resolve
provider → `assertCapabilities` → depth check → snapshot descriptor → `await provider.start(resolved)` → append
the child to the parent's catalog → wrap in lifecycle observation. Provider ownership ends exactly at
fulfillment: a rejection yields no run and emits **no lifecycle events** (`:580-586`).

**FACT.** Both in-process providers delegate to one function, `startInProcessRun`
(`packages/subagent/subagent-in-process-driver/src/index.ts:104-152`), differing only in the seed:
`spawn` passes `{}` — a fresh child, `inheritsParentContext = false`
(`packages/subagent/subagent-spawn-in-process/src/index.ts:50,54-59`); `fork` passes the parent's
**completed-turn prefix** — everything up to and including the last `turn/end`, with the in-flight unbalanced
turn excluded (`packages/subagent/subagent-fork-in-process/src/index.ts:48-55,71,76-83`).

**FACT.** Out-of-process providers (`subagent-claude-code`, `-codex`, `-acp`, `-dsh-sdk`) spawn a real CLI
through the **same `ctx.subprocess` seam**, inheriting the env scrub and managed-range teardown
(`packages/subagent/subagent-acp/src/run.ts:349-356`;
`packages/subagent/subagent-claude-code/src/process.ts:46-61`).

**OBSERVATION.** `fork` cutting at the last `turn/end` is a real design decision: a child never inherits a
partially-formed turn. The boundary is *structural in the log*, not a timestamp or a token count.

**AISEF — ADOPT the cut rule.** AISEF's `FAM-RECOVERY` (D-034, D-035, OBS-R13) is "a resume recomputes or changes
evaluated state without invalidating the evidence that depended on it". A resume or fork point defined as *the
last completed structural boundary in the journal* is exactly the discipline that family needs, and it composes
with the append-only journal in
[`AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md`](AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md).

### F.2 Inheritance is explicit, narrowing-only, and captured synchronously

**FACT** — all in `packages/subagent/subagent/src/child-agent.ts`:

| | inherited? | citation |
|---|---|---|
| conversation context | provider-dependent (`spawn` no, `fork` completed-turn prefix) | `subagent-fork-in-process/src/index.ts:48-55` |
| cwd | yes, from the parent header | `child-agent.ts:147` |
| session | **no** — fresh `SessionId`, with `parentSession` lineage and `origin:'subagent'` | `child-agent.ts:139-156` |
| model / effort / maxTokens | from the parent's latest request header; a route change without an explicit effort **clears** the inherited effort | `child-agent.ts:69-120` |
| tools | preset join then narrowed: `composeFrom(childCtx, parent.ctx)` then `childCtx.tools.restrict(toolFilter)` — nearest scope wins, restriction intersects | `child-agent.ts:200-219` |
| sandbox mode | only the parent session's **explicit** override — never deployment defaults, never one-shot grants — replayed onto the child's own log as `source:'delegation'` | `child-agent.ts:246-252,264-277` |
| approval policy | **pinned to `'never'`** whenever approval is composed | `child-agent.ts:229-232,251` |
| permission preset | only `auto` / `danger-full-access` | `child-agent.ts:224-225,249` |
| depth | `parent + 1`, capped, and **persisted** so a resumed parent cannot delegate as top-level | `child-agent.ts:50-59,154-155` |

**FACT.** The capture is taken **synchronously before the first await**, so a later parent policy switch belongs
to the parent's future, not the child's past (`child-agent.ts:236-245`, called at
`in-process-driver/src/index.ts:119`).

**FACT.** The child is told in its runtime context that it cannot widen: *"your permission scope was fixed when
you were started and cannot be widened from inside this session — operations that require approval are rejected
automatically"* (`child-agent.ts:172-176`).

**OBSERVATION.** Four independent mechanisms enforce one property — **authority only narrows**: restriction
intersects, approval is pinned to `never`, only explicit overrides propagate, and depth is persisted so a resume
cannot launder a child into a root.

**AISEF — ADOPT, this is Typed Ownership made operational.** Three of our families are authority-widening in
disguise: `FAM-JUDGE` (a blocking decision resting on the model reviewer alone), `FAM-APPROVAL` (acceptance scope
implied rather than bound), and `FAM-SCHEDULER` (declared vs effective scope). A v2 rule that *no child scope may
hold an authority its parent did not hold, and every capture is taken at a determinate synchronous point* closes
the shape all three share. The persisted-depth detail is the specific answer to resume-time laundering and costs
one field.

### F.3 Isolation is logical for in-process children

**FACT.** A child gets a separate session id and log (`in-process-driver/src/index.ts:113`) and a separate Cordis
child context whose registrations are "owned by the child's scope and therefore invisible to its parent and
siblings" (`child-agent.ts:186-188`). But in-process children share the OS process, `ctx.subprocess` and the
filesystem provider. Only out-of-process children are separate OS processes with their own scrubbed env
(`subagent-acp/src/run.ts:344-356`).

**AISEF.** State the equivalent plainly in our own records. AISEF's reviewer and developer sessions are logically
separated; where they share a process or a worktree, the qualification record must say so, because
`FAM-BENCH` (cohort contamination) is what happens when a separation that is only logical is reported as
physical.

### F.4 Failure propagation: fail-closed by default arm

**FACT.** A subagent failure does **not** fail the parent turn — it becomes an error *tool result*.
`stopReasonError` maps every non-`completed` reason to a message and carries **an explicit default arm**, so an
unknown future stop reason is a failure rather than partial-output-as-success
(`packages/subagent/tool-subagent/src/index.ts:157-174`). `settleForegroundRun` throws that message and the
registry converts the throw to `isError` (`:212-215`), with the child's partial output and provider diagnostic
riding along (`:184-196`).

**FACT.** Disposal failures are kept **separate** from result failures: both are `allSettled` and combined into
an `AggregateError` only when both fail (`tool-subagent/src/index.ts:226-237`). During `start`, a catalog-append
failure disposes the run and surfaces the catalog error, logging rather than throwing a secondary disposal
failure (`subagent/src/index.ts:604-618`).

**FACT.** For out-of-process runs, `settleRunResult` guarantees `result` **never rejects after publication** —
transport failures are flattened to `stopReason:'error'` with a 4 KiB-capped diagnostic
(`out-of-process.ts:19-42,192-219`).

**OBSERVATION.** The default arm is the notable line. An unmatched stop reason resolving to *failure* rather than
*success with partial output* is fail-closed applied to the one place it is usually forgotten: the `default:` of
a mapping over an open enum.

**AISEF — ADOPT the default arm as a rule, and note the divergence from Cordis.** `FAM-OUTCOME` is our largest
family (six members) and every one of them is an unmapped or mis-mapped case resolving to the permissive side.
Separately: the harness keeps disposal failures distinguishable, where Cordis's `_unload()` swallows them into a
logger ([`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §2). They fixed the framework's weakness
at the consumer. AISEF should fix it at the kernel: a disposal failure is typed evidence and can fail a
transaction's `DISPOSE`.

### F.5 Cancellation tears down the whole range, child-first

**FACT.** The parent's `exec.signal` is handed straight into `subagents.start` for foreground delegation
(`packages/subagent/tool-subagent/src/index.ts:564-567`); background one-shots get their own `AbortController`
wired to job cancel (`:550-556`). Foreground calls **always** dispose after collection (`:226`).

**FACT.** The out-of-process cancel ladder is the clearest statement of the pattern
(`subagent-acp/src/run.ts:185-212`): **stdin EOF → bounded `eofGraceMs` wait on the managed range →
`child.terminate()` (SIGTERM → grace → SIGKILL) → unbounded `waitForExit()`**. The tier-1 EOF window exists
precisely to let the child reap *its own* descendants first (`:186-188`). `dispose()` is idempotent and memoized
(`out-of-process.ts:245-258`). Parent teardown drains descendants **child-first** with a scoped admission cutoff
(`subagent/src/index.ts:333-348`).

**AISEF — ADOPT the graceful-first ladder and the child-first drain.** A cooperative shutdown tier before the
signal ladder lets a well-behaved child clean up its own resources, which is the only way a nested scope's
cleanup can be ordered correctly — and it is the mechanism that makes G.2's range-emptiness requirement
achievable rather than merely strict. "Unbounded `waitForExit()` last" is the right terminal: after SIGKILL to
the range, waiting forever is correct, because a range that will not empty after SIGKILL is a fact worth
blocking on and reporting, not one to time out and forget.

### F.6 Minor findings

**FACT.** `killGroup()` (`spawn.ts:97-104`) is exported but referenced only from `tests/spawn.spec.ts:10`;
production goes through `signalTree`. Dead code, noted only as an instance of seam drift a `--check`-style
guard would catch.

---

## A. Core architecture

**FACT.** A pnpm monorepo of 60 packages and 4 apps. The framework layer (Cordis and its ecosystem) is
**vendored** at `vendor/`, with the rationale stated in `vendor/README.md`: "so that the harness fully owns its
framework layer (auditable, patchable, pinned)". Eight local modifications are logged there, and a commit hook
(`scripts/check-vendor-manifest.sh`) rejects any staged change under `vendor/*/src` that does not update that log
in the same commit.

**FACT.** Composition is **data, not code**. The application's base entry list is *empty*
(`apps/cli/src/profile-boot.ts:82-85`); everything the process runs arrives as YAML patches, assembled in a fixed
precedence order (`packages/boot/app-boot/src/profile-context.ts:63-74`) and applied in one flattened
`applyEntryPatches` call (`packages/boot/app-boot/src/index.ts:373-380`).

**OBSERVATION.** Three structural decisions reinforce each other: own the framework (vendor), express composition
as data (YAML patches), and verify the data statically (§I.3). None of the three works alone. Vendoring without
the static checks would just be a fork; data-driven composition without vendoring would leave the loader's
semantics outside their control.

**AISEF — take the second and third, we already have the first.** AISEF's kernel is its own code, which is the
strongest form of "own your framework". What we lack is composition-as-verifiable-data: our execution profile is
data, but the *set of components a run uses* is implicit in the code path taken. §I.3's checker pattern is the
thing to import.

---

## B. Capability seams

**FACT.** Every substitutable capability is a Cordis service on `ctx`: `ctx.subprocess`
(`packages/subprocess/subprocess/src/index.ts:117-163`), `ctx.sandboxPolicy`
(`packages/sandbox/sandbox-policy/src/index.ts`), `ctx.subagents`
(`packages/subagent/subagent/src/index.ts:198`), `ctx.fs`, `ctx.shell`, `ctx.sessions`, `ctx.tools`, `ctx.llm`,
`ctx.settings`, `ctx.logger`. Implementations are plugins; a seam typically has a local and a remote
implementation (`LocalSubprocessRuntime` / `SshSubprocessRuntime`; `LocalSandboxProvider` /
`SshSandboxProvider`).

**FACT.** Substitution is by **name within an isolate scope**, with no version field anywhere
(see [`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §3).

**FACT — the seam boundary is defended at the type level in one place that matters.** `harnessErrorCode` states:
"Trust only Harness-owned codes; third-party SDK codes are not our taxonomy" — anything that is not a
`HarnessError` flattens to `'UNKNOWN'` (`packages/llm/llm/src/adapter-failure.ts:104-107`). Likewise
`ToolFailure.info` is derived **only** from `HarnessError`, and foreign SDK codes are rejected
(`packages/core/tools/src/index.ts:644-651`).

**AISEF — ADOPT this boundary rule verbatim.** `FAM-PROSE` (D-018, D-026: "free-form model or tool text is matched
by substring and the match *creates control state*") and `FAM-JUDGE` are both failures of exactly this boundary:
text from outside the system became a control code inside it. The harness's rule — *a code from outside our
taxonomy is `UNKNOWN`, never a control decision* — is the enforceable version of our **No Prose As Control
State** invariant at the capability seam, and it belongs in the v2 capability contract.

---

## C. Session model

### C.1 A session is a log, and nothing else

**FACT.** `class Session` is a plain class, not a service, whose only state of record is a private array
(`packages/core/session/src/index.ts:446-449`):

```ts
export class Session {
  private log: SessionEvent[] = []
  /** Single incremental owner of surface acceptance and projection state. */
  private readonly surfaceManager: SurfaceManager
```

**FACT.** The header — cwd, lineage, preset, delegation depth — is deliberately **outside** the log, "a storage
concern, not replayable conversation state" (`index.ts:461-462`). `SessionStore` is an in-memory
`Map<SessionId, SessionEntry>` (`index.ts:908-909`).

### C.2 Persistence: JSONL, append-only, no update and no delete

**FACT.** One directory per session; the log file's name carries the format generation
(`session.v3.jsonl.zstd`, `packages/session/session-persistence-jsonl/src/format.ts:41-59`). Line 1 is the header
record, lines 2..n one JSON record per event — "every event occupies one row" (`format.ts:312-323`). The config
root is **required with no default**, because "a default of `process.cwd()` would scatter session files"
(`packages/session/session-persistence-jsonl/src/index.ts:88-99`).

**FACT.** The persistence seam **has no update and no delete operation at all**. Service API: `create` / `open` /
`flush` / `stat` / `list` (`packages/session/session-persistence/src/index.ts:147-198`). Handle API: `read` /
`append` / `flush` / `close` (`.../handle.ts:83-116`). The physical write is `O_APPEND` plus `fsync`
(`session-persistence-jsonl/src/index.ts:1246-1261`).

**FACT.** The only two truncations are byte-level, never record edits: `rollbackAppend` on a failed write
(`index.ts:1276-1284`) and `truncateTornTail` discarding an incomplete crash tail (`index.ts:1287-1296`).

**FACT.** Logical deletion is always a **new appended event**: compaction shadows a range with a
`{op:'replace', startSeq, endSeq}` marker on a new event, and the old events remain in the log
(`packages/core/session/src/types.ts:439-441`; `index.ts:823-831`); `feedback/message-delete` is a tombstone
folded at read time (`packages/feedback/message-feedback/src/index.ts:97-115`).

**AISEF — ADOPT the seam shape.** A storage interface that *cannot express* update or delete makes
`FAM-RELEASE` ("closure bookkeeping bound to a commit can never be current once committed") and
`FAM-IDENTITY` structurally harder to reach. AISEF's closure-evidence discipline is currently enforced by rules I
follow; an append-only evidence handle with no mutation verb would enforce it by type.

### C.3 Cross-process exclusion, then cold read

**FACT.** Resume takes **write ownership first**, then cold-reads the whole log from 0
(`packages/core/agent-loop/src/index.ts:894-904`). Exclusion is a kernel-held directory lock, `SessionWriteLease`
(`packages/session/session-persistence-jsonl/src/lease.ts`, acquired at `index.ts:872-874`).

**AISEF — ADOPT.** This is the answer to the class of problem behind my own standing rules ("do not commit while
a test run is in progress", "git stash is shared between worktrees", `FAM-RECOVERY`). A lease taken *before*
reading means two runs cannot both believe they own a story's evidence. AISEF v2's Evidence Store should hold a
lease per story scope, acquired before any read that a later write depends on.

### C.4 Crash repair produces typed *unknown* outcomes, deterministically

**FACT.** Layering is explicit: "Semantic crash repair is the agent layer's job: persistence hands back the
physically valid log" (`agent-loop/src/index.ts:900-903`). The repair scans for an open turn and appends
synthetic closers (`packages/core/session/src/repair.ts:29-135`): a `tool/result` error per dangling call,
distinguishing **`TOOL_OUTCOME_UNKNOWN` from `TOOL_NOT_STARTED`** (`:15-18,119-122`), then `step/end`, then
`turn/end {kind:'interrupted'}` (`:130-133`). Closer timestamps **reuse the last real event's time so the
closers are deterministic** (`:87-88`).

**FACT.** A non-owning cold read (query/UI) applies the same repair without going live
(`packages/session-query/session-query/src/cold-read.ts:31-57`).

**OBSERVATION / AISEF — ADOPT, this is INV-ABSENCE for interrupted runs.** `TOOL_OUTCOME_UNKNOWN` is precisely
"we do not know whether this executed" expressed as durable evidence instead of a gap. AISEF v1's interrupted
runs leave the record silent, which is exactly the condition under which a later gate has to guess — the SS-96
shape. Two properties to copy: the *distinction* between started-unknown and never-started, and the
*deterministic timestamp* so that repairing the same log twice yields byte-identical closers.

---

## D. Event and message model

### D.1 A discriminated union over `type`, with 59 generated and verified members

**FACT.** `SessionEventMap` (`packages/core/session/src/types.ts:269-406`) is a merge-extensible map keyed by
event-type string; `SessionEvent<T>` (`:470-493`) is a mapped-type discriminated union whose discriminant is
`type` — "a proper discriminated union over `type` … so `switch (event.type)` narrows `event.data` without casts"
(`:460-461`). The core vocabulary is 59 types, **generated and verified** against a committed catalog
(`packages/core/session/src/known-event-types.ts:22-81`, gate `verify-persistence-catalog`).

**FACT.** Identity/correlation fields on the envelope: `seq`, `time`, `type`, `data`, optional `ignorable`, plus
`turn` / `step` on loop events, `callId` on `tool/call` correlated through `message.source.callId` on
`tool/result`, `message.id`, and `sourceEventSeqs` — "complete non-empty set of known earlier source-event seqs"
(`types.ts:453-454`). There is **no separate trace or correlation id**; correlation is
`(sessionId, seq, turn, step, callId)`.

### D.2 An unknown required event means *refuse to reconstruct*

**FACT** (`types.ts:478-487`). A reader that meets an unrecognized event type **without** `ignorable: true` must
refuse to reconstruct the session, because "an unrecognized required event may change how the rest of the log is
interpreted". The format-version bump is stated as a **writer-side obligation**, not a reader capability question
(`types.ts:73-87`).

**OBSERVATION.** This is the single sharpest line in the repository for assurance purposes. A logging system
skips unknown rows; this one refuses. The `ignorable` flag makes "safe to skip" an explicit, per-event,
author-side claim rather than a reader's assumption.

**AISEF — ADOPT unconditionally.** `REPLAY-DRIFT` (`FAM-RELEASE`) is the family where an older reader silently
mis-derives a newer record. A v2 evidence record must carry the same rule: an unknown **required** field or event
makes the verifier refuse to produce a verdict, and only explicitly-`ignorable` additions are skippable. "Silently
read a newer log wrong" becomes a designed-out failure mode rather than a discipline.

### D.3 `seq === index`, enforced at four layers; `time` is never the ordering key

**FACT.** The sequence is dense and monotonic and the invariant is enforced independently four times:

1. assignment — `seq: SessionSeq(this.log.length)` (`index.ts:743`);
2. seed admission — throws `seed event at index ${index} has seq ${snapshot.seq}…; seed must be contiguous from
   0`, with the rationale "the `seq = log.length` contract the whole system relies on" (`index.ts:567-581`);
3. persistence append — `assertContiguous`
   (`packages/session/session-persistence/src/storage-contract.ts:145-151`);
4. decode — a seq gap against the running row count is rejected
   (`packages/session/session-format-v1-to-v2/src/codec.ts:104-107`).

**FACT.** `time` is `Date.now()` (`index.ts:744`) and is **zeroed wholesale** in committed fixtures
(`packages/test-support/session-snapshot/src/normalize.ts:359-361`). Corpus fixtures omit `seq` and `time`
entirely; the loader re-derives them from file position
(`packages/test-support/llm-replay/src/index.ts:260-263`). Position in the file *is* the sequence.

**AISEF — ADOPT, this is the structural answer to `FAM-IDENTITY`.** Our largest identity family is "a control
decision selects its evidence by chronological recency (`last`, newest, HEAD)". The harness's answer is not
"order by time more carefully" — it is *never order by time at all*, and make position the identity with four
independent enforcement points. For v2: no projection may read `time` to decide ordering, and the journal's
contiguity must be asserted at write, at load, and at decode.

### D.4 Validation happens at the append site

**FACT.** "The event log is the durable source of truth, so a bad event fails at the append site rather than
later during a backend flush" (`index.ts:713-715`). Every `data` payload is runtime-checked as lossless JSON
(`:729-736`) and the surface transition is pre-validated **before the log grows** (`:749`).

**AISEF — ADOPT.** An evidence record that cannot be written is a louder, earlier and more localizable failure
than one that cannot be read back. This is also the cheapest defence against `FAM-EVIDENCE-SEMANTICS` (SS-81).

### D.5 Every read model is a pure fold, and every cache is disclaimed

**FACT.** Message history, request header, route metadata and the ordered surface are all folds keyed on log
position or a generation counter (`index.ts:775-862`; `surface.ts:631-646`). Pure offline equivalents are the
documented authority: `foldSurface(events, projections)` (`surface.ts:544-559`) and
`foldRequestHeader(events, from?)` — "this is the pure offline reconstruction path; the live session tracks the
same fold incrementally" (`packages/core/session/src/request-header.ts:63-69`).

**FACT.** The one durable state cache disclaims itself (`packages/session/session-projection-cache/src/index.ts:9-14`):

> "The cache is a fold shortcut, never an authority: a row is possibly stale (its `seq` says how stale) but never
> wrong, so every write path is fail-soft … and a `ver` mismatch **discards** the row instead of migrating it."

The SQLite full-text index is likewise "the **disposable** session full-text read model", reset in place on
version change (`packages/session-query/session-query-sqlite/src/schema.ts:1,7-8`).

**FACT — the equivalence is tested, with a from-scratch oracle**
(`packages/core/session/tests/derived-cache.spec.ts:17-27`):

```ts
/** From-scratch oracle: replay the log into a fresh session and derive. */
function scratch(session: Session): unknown {
  return Session.create(SessionId(`…`), session.snapshotEvents()).deriveMessages()
}
… expect(session.deriveMessages()).toEqual(scratch(session))
```

**FACT — even the mutable-looking things are folds.** The pending-input queue is a projection:
`ReactLoopInbox.mutate` computes a candidate, **appends the event, and returns — it never writes back to a field**
(`packages/core/agent-loop/src/inbox.ts:218-242`); readers go through
`this.projections.stateOf(this.session, 'inbox')` (`:187-195`). The system prompt's current value is read back
out of the surface rather than from a field (`packages/core/agent-loop/src/runtime-context.ts:64-98`).

**AISEF — ADOPT all four properties, and adopt the oracle test as a qualification technique.** The oracle —
*incremental state must equal a from-scratch fold of the same log* — is a cheap, high-yield property that AISEF
does not currently assert anywhere. It is the exact check that would have caught the class of staleness bugs
behind `FAM-RECOVERY` and `FAM-QUALIFICATION-MEASUREMENT`. Concretely, for v2: the kernel's live gate state must
equal `fold(journal_prefix)` at every decision point, asserted in the test suite and sampled in qualification
runs.

**Honest caveat, from the source.** Durable writes are asynchronous write-behind with
`LIVE_WRITE_BATCH_MAX_DELAY_MS = 200` (`packages/session/session-persistence-jsonl/src/storage.ts:36,86-94`), so
the durable log can lag the in-memory log by up to 200 ms — which is precisely what the crash-repair path exists
to absorb. AISEF's evidence writes should be synchronous at decision boundaries; we are not latency-bound and the
trade they made is not one we need.

### D.6 Where the event bus *is* used as control — and why we should not

**FACT.** `agent/request-error` is dispatched as a **waterfall** returning a `RequestErrorAction`; the failure is
rethrown as an `LlmError` only if **no listener** returns `{kind:'retry'}`
(`packages/core/agent-loop/src/agent.ts:448-464`). This is the seam `llm-retry` mounts
(`packages/llm/llm-retry/src/index.ts:243`).

**INFERENCE.** Whether a failed model request is retried is therefore a function of *which plugins happen to be
loaded*. For their purposes that is a feature. For a qualification system it is a defect generator: the same log,
the same failure and a different plugin set give different behaviour, and the record does not say which set was
present.

**AISEF — REJECT, and this is the concrete instance behind §11's conclusion.** Retry policy is control. It must
be a typed decision in the kernel derived from the failure's code and owner, recorded in the journal, and not
something a subscriber can change by existing. See §J.2 for the part of their retry design that *is* worth
taking.

---

## E. Replay and reproducibility

### E.1 Only the model stream is mocked

**FACT.** The replay adapter replaces **only** `llm.stream`, as a routed adapter or a catch-all waterfall
(`packages/test-support/llm-replay/src/index.ts:1095-1097`). Everything else is real: a real subprocess
(`packages/test-support/session-snapshot/src/launcher.ts:136-143`), a fresh `mkdtemp` workspace, sessions root
and spill root per scenario, with `DSH_HOME` pinned inside the temp cwd
(`.../harness.ts:240-250,274-275`).

**FACT — the clock and randomness are *not* mocked.** No `useFakeTimers`, `setSystemTime` or `Math.random` stub
exists in the snapshot support. Determinism is achieved **after the fact, by normalization**:
`normalize.ts:341-378` zeroes `createdAt`, `time`, `time0`, every `dt[]` entry, embedded stream timings and
`hook/result.durationMs`; `scrubString` (`:162-199`) tokenizes cwd in all spellings including the macOS
`/private` alias, spill paths, session ids and stray UUIDs into `{{cwd}}`, `{{spillLocator:…}}`, `{{session:N}}`.
Ambient proxy variables are stripped from every vitest process "so a developer's Clash/squid cannot decide
outcomes" (`scripts/test-proxy-environment.ts:1-23,53-60`).

**FACT.** Values that must be genuinely fresh *and* echoed by the model are resolved at replay time from the live
request via `{{fromRequest:<regex>}}` placeholders, last match wins
(`llm-replay/src/index.ts:532-533,550-583,615`).

### E.2 Tool results are recorded but never replayed

**FACT.** `deriveReplayScript` reads **only** `assistant/message`, `assistant/attempt` and explicitly-marked
`compaction/summary` events; it skips `tool/call` and `tool/result` entirely
(`llm-replay/src/index.ts:458-499`). Tools are **re-executed for real** against the temp workspace, and the fresh
`tool/result` rows are diffed against the fixture. The final workspace state is captured and compared as well
(`snapshots/session/fs-delete-recreate/snapshot.yml:8-9`;
`packages/test-support/session-snapshot/src/workspace.ts:47-71`).

**OBSERVATION.** A tool-behaviour regression appears as a `tool/result` diff in the reproduced log, not as a
silently-satisfied recording.

**AISEF — this is the most important reproducibility finding in the study, and it validates a choice we already
made.** Replaying recorded tool results would be self-certification: the system would be checked against its own
prior output rather than against the world. Their line is exactly ours. Two transferable specifics: **(a) the
fixture is simultaneously the replay input and the expected output** (`suite.ts:3-4`), which halves the
maintenance surface and makes drift visible in one artefact; **(b) the final workspace state is part of the
comparison**, not only the log.

### E.3 Consumption is asserted, not assumed

**FACT.** `assertConsumed()` fails the test if the fresh run bound fewer sessions, or drove a different number of
model calls, than were recorded (`llm-replay/src/index.ts:1100-1114`).

**FACT — the weakness, stated plainly.** Binding is **by call order, not by request matching**: a new live
session claims the next unclaimed script and each call takes `boundState.cursor++`
(`llm-replay/src/index.ts:1030-1061`). The incoming request is inspected only for `{{fromRequest:}}` resolution
and subagent-id inference (`:1075-1076`).

**INFERENCE.** Positional binding means a materially changed request that still makes the same number of calls in
the same order binds the same scripts and can still pass. The mitigations are `assertConsumed` and the
full-normalized-log comparison — and, most importantly, the request-header class pinning of §I.5, which is what
actually detects a changed request.

**AISEF — ADAPT with a correction.** Take `assertConsumed`; do **not** take positional binding without the header
pinning that compensates for it. If AISEF ever replays provider output, bind by a hash of the request, not by
call index.

### E.4 Production reconstruction and test replay are different things

**FACT.** The production resume path genuinely reconstructs state by replaying the full log
(`agent-loop/src/index.ts:868-942`, seed admission at `session/src/index.ts:560-591`, which accepts a seed
"incrementally through the same transition as a live append and a full-log fold", `:582-591`). The snapshot tier
does **not** exercise reconstruction-from-log except through the `session.v2.jsonl` migration fixtures.

**AISEF.** Worth stating because it is an easy thing to conflate: *behavioural reproduction* (same inputs → same
observable outputs) and *state reconstruction* (log → identical internal state) are separate properties needing
separate evidence. AISEF's Phase 12 differential testing is the first; the from-scratch oracle of §D.5 is the
second. Our qualification ladder should name both.

---

## I. Configuration and profile model

### I.1 Two layering systems, both with stated precedence

**FACT.** *Composition* (what code runs) layers bundle patches → per-profile `cordis.patch.yml` →
`$DSH_HOME/cordis.patch.yml` → `--patch` overlays in argv order → an env-derived telemetry patch
(`packages/boot/app-boot/src/profile-context.ts:63-74`), with the precedence rationale documented at
`apps/cli/src/profile-boot.ts:185-191`. *Environment* layers inherited process env > invoking-directory `.env` >
`$DSH_HOME/.env` (`packages/boot/app-boot/src/index.ts:201-212`); bootstrap-only prefixes (`DSH_`, `XDG_`,
`DYLD_`, `BASH_FUNC_`) may come **only** from the inherited env (`:134`, narrow proxy exemption at `:143`). The
result is a **frozen snapshot recording which layer supplied each value**
(`packages/util/launch-environment/src/index.ts:31-52`). *Settings* layer schema defaults → composition `base` →
user document section (`packages/settings/settings/src/index.ts:3-5`, merge at `:287-296`).

**AISEF — ADOPT the provenance-carrying snapshot.** Recording *which layer supplied each value* turns "what was
the configuration" from an inference into a fact. AISEF's `ExecutionProfile` records the resolved values; it
should record their origins too, because `FAM-APPROVAL` ("acceptance scope implied rather than bound") and
`FAM-IDENTITY` both get harder when every effective value names its source.

### I.2 Raw and resolved are first-class, and the distinction is load-bearing

**FACT.** The settings provider stores a **raw document** per namespace
(`packages/settings/settings/src/index.ts:730-737`) and a separate `resolved` value produced by `deepFreeze` at
registration, on write and on external publish (`:436,676,718`); the wire view exposes `value` (resolved),
`user` (raw) and `base` (`.../types.ts:38-43`). `bumpRevision` deliberately tracks the **raw** section
independently of resolved-value equality, because "storing an override equal to the composition base leaves the
resolved value alone but changes what the document says" (`:762-766`).

**FACT.** Immutability is applied per seam, not once globally: `ProfileResolutionGeneration` is the "complete
**immutable** fallback table for one profile launch" (`packages/boot/app-boot/src/profile.ts:101-113`);
`PreparedLlmCall.config` is "detached, **deep-frozen** … with any adapter-owned default materialized"
(`packages/llm/llm/src/index.ts:167-169`); a loop-built request "arrives deep-frozen (mutation throws)"
(`:63-66`), enforced at runtime (`packages/core/agent-loop/src/invariant.ts:23-28`).

**INFERENCE.** There is **no single global resolved-runtime-spec object**. The nearest thing is
`renderConfigDump` (`packages/boot/app-boot/src/index.ts:403-467`), which composes the effective entry list
*exactly as `boot()` would* and renders it as loadable YAML with `# ==` comments naming which file and which
patch layer contributed each run of rows (`:382-395`) — a diagnostic, not the runtime object.

**AISEF — ADOPT the distinction; go further than they did.** The `bumpRevision` insight is subtle and directly
ours: *a change that leaves the effective value identical can still change what was approved*. That is
`FAM-APPROVAL` in one sentence. But for a qualification system the per-seam approach is not enough: AISEF needs
**one** resolved, hashed `RunSpec`, because a qualification claim is about a whole run, not about a seam. Build
what `renderConfigDump` produces, then bind its hash into every verdict.

### I.3 Static verification of composition

Covered in detail in [`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §6.5. The additional checks
worth naming here, all in `scripts/verify-cordis-config.ts`:

**FACT.** *Plane separation* (`:119-162`): no shipped agent-preset row may repeat a row the host composition
still runs. The docstring records two real incidents — an `isolate` realm shadowing a host route, and a host
registry contribution re-registering per live session until it threw — and the decisive observation: **"Neither
changes a tool catalog, so no catalog assertion can see them."**

**FACT.** *Client-half declaration* (`:104-118`): a `packages/client/*` package exporting `./client` must declare
`dsh.client`, otherwise "its bundle is never served and **no error is raised anywhere**".

**FACT.** `scripts/verify-config-source-ownership.ts:23` bans inline `apiKey|baseURL|apiKeyEnv|authToken|headers:
!!js` in shipped config, because inlining "bypasses both ladders" — the credentials seam and the env snapshot.

**OBSERVATION.** All three target the same shape: **a defect that produces no error and no observable signal**.
That is the category a test suite structurally cannot reach, and it is why they wrote checkers instead of tests.

**AISEF — ADOPT the category, not just the checks.** Ask, for each v2 invariant: *if this were violated, what
would fail?* Where the answer is "nothing would fail, the system would just be quietly wrong", a runtime test
cannot help and a static check is required. Several AISEF families are in exactly that category —
`FAM-SCHEDULER` (declared vs effective scope), `FAM-OWNERSHIP` (files nobody authored), `FAM-BENCH` (cohort
contamination). None of them raises an error at the moment it goes wrong.

### I.4 Profiles and presets are identified by **name**, with no content hash

**FACT.** A profile is a directory `$DSH_HOME/profiles/<name>`; its identity is the directory basename
(`packages/boot/app-boot/src/profile.ts:5-14,79`). An agent preset's id is its directory name, and its **trust
comes from the root it was discovered under** — explicitly not writable by the preset itself, "otherwise a
locally authored preset could claim to be a shipped one"
(`packages/preset/agent-presets/src/metadata.ts:11-14`). A grep for `createHash|sha256|digest(` across
`packages/preset/agent-presets/src` and `packages/boot/app-boot/src` returns **nothing**.

**FACT.** Per-session composition is frozen once a turn has run: `RemoteError('agent-preset/locked', 'session
"…" has already started; its agent preset is fixed')` (`packages/preset/agent-presets/src/index.ts:740-751`).

**AISEF — REJECT the identity scheme; keep ours; ADOPT the trust-from-discovery-root rule.** Name-only identity
means a profile directory can change content under a stable name, which for a qualification record is fatal:
`FAM-IDENTITY` and `FAM-BENCH` both live there. AISEF's content-hashed `ExecutionProfile` identity is strictly
stronger and must stay — this is a "what stays" answer for §17. Conversely, *trust derived from where an artefact
was discovered rather than from what it says about itself* is exactly right and is a good shape for AISEF's
distinction between shipped plans and run-authored ones.

### I.5 Request-header classes — bounding legitimate drift

**FACT.** The snapshot manifest (`packages/test-support/session-snapshot/src/manifest.ts:12-52`) pins a
**request-header class**: "stable class name shared only by byte-identical request headers". Exactly one scenario
per class pins the tokenized header sequence and the tokenized `system/message` sequence, and `changes` /
`promptChanges` **bound the number of legitimate drifts**. The suite doc states the rule:
"session-dependent composition must declare a separate class instead of escaping coverage" (`suite.ts:10-17`).

**AISEF — ADOPT; this is the highest-value single technique in the harness for us.** What we send the model is
the largest uncontrolled variable in every AISEF run, and prompt or profile drift between runs is a standing
threat to `FAM-BENCH` and to any comparison of two qualification runs. Class-pinning gives three things at once:
byte-identity as the class criterion, a bounded and therefore reviewable drift budget, and the forcing rule that
any session-dependence must be *declared* rather than silently widening the class.

### I.6 Runtime mutation: three paths, and one dead declaration

**FACT.** Settings hot-publish re-resolves every namespace on file change
(`packages/settings/settings-file/src/index.ts:238-263`; `settings/src/index.ts:700-727`); watchers are
**serialized per watcher in commit order** so "a slow stale invocation can never apply after a newer one"
(`:796-814`). Cordis `Fiber.update()` validates and then **restarts** the plugin
(`vendor/cordis/src/fiber.ts:737-750`). HMR clears the ESM/CJS caches with a rollback snapshot and re-plugs each
affected fiber under its previous parent, preserving config
(`packages/boot/hmr/src/index.ts:406,470-497,520-533`).

**FACT — invalid configuration is handled differently per phase, deliberately:**

| Phase | Behaviour | Citation |
|---|---|---|
| boot, required entry | fatal `StartupError` | `app-boot/src/index.ts:746-763,854-869` |
| boot, optional entry | one warning, siblings keep running | `:857-859` |
| patch file present but unparsable | throws — "must fail loud at boot, never be silently skipped" | `:282-284` |
| named `--patch` absent | throws (vs. absent optional layer = ok) | `:309` vs `:289` |
| hot reload, section invalid | keep last good, warn, siblings commit | `settings-file/src/index.ts:305-314` |
| hot reload, document unparsable | reload warns and keeps last good; a **write** fails loud rather than overwriting | `:316-321` |
| hot reload, fiber schema rejection | previous config retained | `app-boot/tests/config-reload.spec.ts:232` |

**FACT — a dead capability declaration.** The settings seam declares `applies: 'live' | 'restart'`
(`packages/settings/settings/src/types.ts:45`, default `'live'` at `index.ts:432`), but **no consumer acts on
`'restart'`** — a grep outside tests returns only the declaration, the default and the generated catalog.

**AISEF — two lessons, one positive and one negative.** Positive: *the failure mode of bad configuration should
depend on the phase*, and "keep the last good value and warn" is right for a live reload while "fail loud" is
right at boot and on write. Negative, and this belongs in the anti-patterns section: **a declared property that
nothing enforces is worse than no declaration**, because readers reason as though it holds. AISEF has the same
exposure wherever an invariant is documented but not armed — which is exactly why their
`scripts/test-invariants.ts` (§K.2) matters.

---

## J. Error model

### J.1 Typed, code-routed, with an explicit "not our taxonomy" boundary

**FACT.** The base class carries a stable machine-routable code
(`packages/llm/llm/src/error.ts:13-22`):

```ts
export class HarnessError extends Error {
  /** Stable machine-routable failure class (e.g. `RATE_LIMIT`); route on this, never by parsing `message`. */
  readonly code: string
```

Subclasses include `LlmError`, `ToolNotFoundError` (`UNKNOWN_TOOL`), `ToolOutputError`
(`INVALID_TOOL_OUTPUT`), `ToolArgsError`, `JsonSchemaError`, `CodeRunFailedError`, `TeamError`, `WebError`.
Alongside them, `RemoteError<Code>` is a **code-discriminated union** over a merge-extensible
`RemoteErrorDetailsMap` where each owner package merges its own domain codes next to the throwing code
(`packages/typert/protocol/src/remote-error.ts:11-48`, 23 augmenting modules) — "discrimination is always by
`code`, never by `instanceof`", with structural cross-realm identification via `remoteErrorOf`.

**FACT.** Serializable value forms exist separately from the classes: `LlmFailure`
`{message, code, status?, providerRetryAfterMs?, requestId?, offloadImages?}`
(`packages/llm/llm/src/adapter-failure.ts:63-91`), `ToolFailure` / `ToolErrorInfo` `{name, code, reason?}`
(`packages/core/tools/src/index.ts:470-482`), `RemoteResult<T>` `{ok:true,value} | {ok:false,error}`
(`packages/typert/protocol/src/types.ts:75-77`).

**AISEF — CONFIRM.** "Route on the code, never by parsing the message" is our `FAM-PROSE` invariant stated as a
class comment. Keep ours; note the convergence.

### J.2 Retryability is a property of the taxonomy, not of the call site

**FACT.** `DEFAULT_RETRYABLE_CODES = [EMPTY_RESPONSE, 'RATE_LIMIT', 'SERVER', 'TIMEOUT', 'TRANSPORT']`
(`packages/llm/llm/src/retry-policy.ts:18-24`), matched directly at
`packages/llm/llm-retry/src/index.ts:215`.

**FACT.** Credentials are split into `MISSING_CREDENTIAL` and `INVALID_CREDENTIAL` **because "the fix differs"**,
and the latter is deliberately **non-retryable** (`packages/llm/llm/src/error.ts:41-48`).

**AISEF — ADOPT, this is `FAM-RETRY` D-006 exactly.** Our D-006 was "credential rejection charged to quality
attempts". The harness prevents that shape by making retryability a property of the code, decided once in the
taxonomy, rather than a decision at each call site. For v2: every typed outcome must carry (a) its owner and
(b) whether it is retryable and against which budget — and the retry engine must read only those two fields.
This also generalizes the SS-96 fix: routing follows the typed outcome, never the stage that observed it.

### J.3 Failures are both an exception and a durable event

**FACT.** `Agent.throwError` emits `agent/error` and then rethrows
(`packages/core/agent-loop/src/agent.ts:219-224`). Independently, the turn's failure is **always** recorded as
structured data in the log, in a `finally` (`agent.ts:328-345`):

```ts
turnEnds = { kind: 'error',
  error: error instanceof LlmError ? error.failure : { message: errorChain(error), code: 'UNKNOWN' } }
```

Failed model attempts that committed no message are preserved as `assistant/attempt` events
(`packages/core/session/src/types.ts:330-335`); tool failures are recorded as `tool/result` with
`error?: {name, code, reason?}` (`:355-366`).

**AISEF — ADOPT the `finally`.** *The control path may throw, but the record is written unconditionally.* AISEF's
biggest evidential gaps are the runs that ended abnormally — and a failure that is only an exception is a failure
that leaves no evidence. Combined with §C.4's typed closers, this makes "the run ended badly" a first-class
recorded state rather than an absence.

### J.4 Internal-defect errors are uncontainable, and they name their owner

**FACT.** `InvariantError` carries the **owning npm package name**
(`packages/runtime-diagnostics/invariants/src/index.ts:50-66`), formatted
`invariant violated by "<packageName>": <message>`. Ownership is reserved at registration, enforced unique
(`:140-142`), and a blank or whitespace name is rejected (`:137-139`). 39 packages ship a companion.

**FACT.** `INVARIANT` is treated as fatal and **un-containable everywhere**: the settings listener fan-out
contains every failure *except* `INVARIANT`, which is rethrown after all listeners have run
(`packages/settings/settings/src/index.ts:833-841`); the settings-file reload rethrows `INVARIANT` while warning
on everything else (`packages/settings/settings-file/src/index.ts:310`).

**AISEF — ADOPT both properties.** An invariant violation that can be swallowed by a `catch` in a listener is not
an invariant. AISEF's 57 invariants should be carried by an error type that every containment boundary is
required to re-raise, and that names the module whose contract was broken. This is also the principled version of
"no self-certification": the component that violated the invariant cannot decide to continue.

### J.5 What they do *not* have, and we do

**FACT — negative, and load-bearing for §17.** There is **no unified failure-class enum** spanning
model / tool / provider / environment / user / config / internal; classification is per-seam plus a `code`
string. There is **no distinct environment-failure class** — environment problems surface as ordinary
`HarnessError` or Node `ErrnoException` in the owning package with no shared taxonomy. And apart from
`InvariantError.packageName` for internal defects, there is **no runtime blame or owner tag on model, tool,
provider or config failures** at all. The weaker signals that exist are `ToolErrorInfo.name` (the throwing class),
owner-namespaced `RemoteError` codes (`session/not-found`, `agent-preset/locked`), and
`AgentCancelCause = {kind:'user'|'parent'|'hook'|'disposed'}` (`packages/core/session/src/types.ts:186-190`).

**AISEF — this is the clearest "what stays" conclusion in the study.** AISEF's typed failure ownership
(PLAN / DEVELOPER / ENVIRONMENT / PROVIDER / REVIEW / SECURITY / INTEGRATION) has **no counterpart in DeepSeek
Harness**, and V1 proved why it is necessary: SS-96 was an environment failure routed to a developer budget, and
without an owner field the defect is not even expressible. Do not weaken it, do not replace it with a per-seam
code scheme, and treat the harness's per-seam codes as a *complement* to owners rather than a substitute —
a code says what went wrong, an owner says whose budget pays and what may be retried.

---

## K. Testing strategy

### K.1 Eight tiers, and a 100% per-file coverage gate

**FACT.** Eight vitest configs. Unit/integration: 1424 spec files, `pool: 'forks'`, split into a `thread-safe`
project and a `process-bound` project whose membership is an explicit 8-file allowlist for suites touching
"process-global state, process APIs, or timing-sensitive process I/O" (`vitest.config.ts:123-192`).
Windows-unsupported suites are excluded by **explicit list, not glob** (`:22-60`). E2E: 213 files, real API,
self-skipping without credentials, `retry: 2` (`vitest.e2e.config.ts:5-45`). Plus expected-output, snapshot, web,
web-stress, perf and bench tiers.

**FACT.** Coverage is **100% per file** on statements, branches, functions and lines
(`vitest.config.ts:356-363`), with the policy stated at `:350-352`: "100% or it doesn't merge … Per-file so a
well-covered big file can't subsidize a bare one. Every v8 ignore comment must carry a reason".

**AISEF.** Our suite is 3702 tests with a mutation score of 862/871 killed and 9 audited equivalents — a stronger
adequacy signal than line coverage. The transferable parts are (a) **per-file** rather than aggregate thresholds,
which prevents exactly the subsidy effect, and (b) **every exclusion carries a reason**, which is the same
discipline as our audited equivalent mutants. Do not adopt a 100% line-coverage gate; it would buy us less than
the mutation gate we already run.

### K.2 Invariants are armed in every test run

**FACT.** *Every* unit, e2e, expected and snapshot config injects `./scripts/test-invariants.ts` as a setup
file. That file **monkey-patches `RegistryService.prototype.plugin`** (`scripts/test-invariants.ts:60`) to mount
the invariant registry plus the test's owning package companion **before any root plugin activates**
(`:125-169`), with a readiness barrier injected into each gated plugin (`:193-205`).
`scripts/test-invariants.spec.ts` mounts all 39 companions (`:104,117`).

**OBSERVATION.** Invariants are not a separate suite that runs sometimes. They are armed during every test of
every tier, so any test in the repository can be the one that catches a violation.

**AISEF — ADOPT.** This is the single cheapest upgrade available to us. AISEF's 57 invariants are checked by the
differential model over generated traces; they are *not* armed during the ordinary 3702-test suite. Arming them
in-process for every test turns our whole suite into invariant coverage at near-zero marginal cost, and it is the
mechanism that makes §I.6's "a declared property that nothing enforces" failure impossible.

### K.3 Fault injection is a named, enumerated surface

**FACT.** Three provider tiers: an in-process scripted adapter with `'hang'`, `'hang-slow'` ("a stand-in for slow
real-world teardown") and `HangAfter` entries
(`packages/core/agent-loop/tests/mock-adapter.ts:65-80`); an HTTP/SSE fault-injection server with **24 named
behaviours** — `connection_reset, stream_disconnect, empty, empty_body, stream_eof, partial_eof,
partial_disconnect, stall, malformed_json, malformed_event, wrong_content_type, rate_limit, server_error,
service_unavailable, auth_error, invalid_request, context_overflow, quota_exceeded, success, reasoning_success,
tool_call_success, max_tokens, slow_success, random`
(`packages/test-support/llm-mock-server/src/index.ts:16-41`); and the record/replay adapter.

**FACT.** The weighted `random` profile is explicitly labelled "configurable test pressure, **not a claim about
production incident frequency**" (`:56-68`).

**FACT.** These drive real recovery tests against the real adapter
(`packages/llm/llm-retry/tests/transport-recovery.spec.ts:87-230`), including "recovers from a true refused
connection after the endpoint starts during backoff", "retries a wire-valid content-less completion without
committing an empty message", "exposes a clean partial EOF as non-default-retryable `STREAM_CLOSED`", "turns a
stalled body into `TIMEOUT` and succeeds on the next request", and "stops after the configured transport retry
budget is exhausted".

**AISEF — ADOPT the mock server; note the honesty label.** `FAM-PROVIDER` cost this programme two abandoned
profiles and three tool-smoke timeouts, and every one of those was diagnosed by hand against a live provider. A
local fault-injection server with named behaviours would let the *kernel's* provider-failure routing be qualified
deterministically, offline and for free — which is exactly the semantic evidence the owner's §13 asks to come
before expensive qualification. The disclaimer on the weighted profile is also worth copying verbatim into our
fault matrix: a distribution over injected faults is test pressure, never an incident-rate claim.

### K.4 Lifecycle is tested against the real process table

**FACT.** `processExists(pid)` is implemented with `process.kill(pid, 0)` / `ESRCH`, and `waitForGone` fails with
`managed pid ${pid} is still alive` (`packages/subprocess/subprocess-local/tests/process-exit.spec.ts:20-55`;
same predicate in `native-windows.spec.ts:47`, `native-containment.spec.ts:57`). Real file cleanup is asserted
with `existsSync(...)` after both abort and terminate
(`packages/subprocess/subprocess-local/tests/linux-scope.spec.ts:250-260,305,982,1001,1058`). Scope teardown has
30 named cases including "rolls back both registries and the scope when asynchronous creation fails", "owner
unload aborts a pending setup and publishes nothing" and "create leaves no lifecycle state when session
preparation fails" (`packages/core/agent-loop/tests/scope-lifecycle.spec.ts:131,262,487,657`). There are cases
named "never spawns the process when `tasks.start` preflight throws (**no orphan, by construction**)"
(`packages/shell/tool-bash/tests/tools.spec.ts:544`) and one that tolerates the residual: "settles on the decided
result even when a setsid-escaped orphan holds stdio open past close"
(`packages/experimental/ptc-runtime-python/tests/runtime.spec.ts:3502`).

**AISEF — ADOPT the assertion style.** `FAM-PROCESS` is closed in AISEF by invariant INV-L.1 and the fault
matrix. What we do not do is assert *against the operating system* that a named pid is gone and a named directory
is absent after teardown. That is a handful of lines and it is the only form of evidence that actually
discriminates an orphan.

### K.5 Concurrency and contract testing

**FACT.** Concurrency is tested directly: "keeps both namespaces when two providers write the same document
concurrently", "waits for a busy writer lock instead of failing", "does not steal an old writer lock"
(`packages/settings/settings-file/tests/concurrency.spec.ts:37,60,72`), teardown-during-create and lock release
on create failure (`lock-race.spec.ts:70,104,113`), and "lets the final enter arbitrate unsupported concurrent
same-id creation and rolls the loser back" (`scope-lifecycle.spec.ts:415`).

**FACT.** Property-based testing (`fast-check`) appears in only **5 files**, confined to the core
invariant-bearing packages (`llm`, `agent-loop`, `tools`, `session`, `schedule/recurrence`).

**FACT.** Contract tests exist per seam (`storage-contract.spec.ts`, `service-contracts.spec.ts`,
`client-contract.client.spec.ts`, `contract-regressions.spec.ts`, `cordis-catalog-contract.spec.ts`), but
**INFERENCE**: the strongest plugin-composition contract enforcement is *static* (§I.3), not a per-plugin
conformance suite.

**AISEF.** The lock tests are the template for the exclusion work in §C.3. The absence of a per-plugin
conformance suite is a gap we should *not* copy: if AISEF v2 has substitutable capability providers, each
contract needs a conformance suite that every implementation must pass, because unlike them we will compare
qualification results across providers.

### K.6 Nine `--check` gates

**FACT.** `verify-cordis-catalog`, `verify-cordis-api`, `verify-config-catalog`, `verify-tool-catalog`,
`verify-persistence-catalog`, `verify-session-format-catalog`, `verify-module-graph`, `verify-scoped-events`,
`verify-dependency-catalog` — each fails if the committed artefact differs byte-for-byte (`package.json`).
`gen-cordis-catalog.ts`'s `SERVICE_PAGE` table is **fail-closed both ways**: a discovered `ctx.<key>` absent from
the table *and* a table entry no longer discovered are both hard errors (`:55-59`, policy at `:846-910`).

**AISEF — ADOPT the bidirectional fail-closed rule.** "Present in reality but not in the catalog" and "present in
the catalog but not in reality" are *both* errors. AISEF's plan-to-criterion mapping, invariant register and
fault matrix all need this property: the ownership audit that refused my new AC for having no `BEHAVIOUR` entry
was this rule working, and it should be the rule everywhere, in both directions.

---

## L. Observability and diagnostics

### L.1 Human logs, structured telemetry, and correlation carried in the log

**FACT.** The console logger is printf-style and human-oriented, not JSON; the record handed to exporters is
`{sn, ts, name, type, level, args, fiber?}` (`vendor/cordis/src/logger.ts:29-38`), formatted with `util.inspect`
(`vendor/logger-console/src/index.ts:9-18`). A second in-memory exporter at boot captures only `warn`/`error`,
outlives root disposal, and is attached to `StartupError.startup.messages`
(`packages/boot/app-boot/src/index.ts:748,927-933`).

**FACT — negative.** There is **no W3C trace context and no request-spanning trace id**. Correlation is carried
in the durable log instead, as branded ids: `SessionId` + `turn` + `step` on every loop event, `ToolCallId`
pairing `tool/call` ↔ `tool/result`, `ProviderRequestId` "retained for diagnostics across package boundaries",
`LlmAttemptId` "unique within one Agent lifecycle", `MessageId` "carried by one message across inbox, log, and
model-request boundaries" (`packages/llm/llm/src/brand.ts:15-64`).

**FACT.** The structured channel is `SessionTelemetryRecord` with `channel: 'ledger'|'ops'`, a **pre-mapped**
severity and a deliberately minimal attribute set (`packages/session/session-telemetry/src/index.ts:51-79`).
Redaction is a waterfall extension point that ships **no rules of its own** and is **fail-closed** — a throwing
listener withholds that record (`:24-45`). Telemetry is opt-out via **any non-empty** `DSH_TELEMETRY_DISABLED`,
because "a privacy switch prefers off-by-mistake over on-by-mistake"
(`packages/boot/app-boot/src/profile-context.ts:41-55`).

**AISEF — ADOPT two things.** (a) *Correlation belongs in the durable record, not in the logs.* AISEF's evidence
already carries story, attempt and stage identity; the missing piece is a branded id per provider request and
per attempt, so a provider incident can be joined to the exact decision it affected — which is what made the
three `ds/deepseek-v4-pro` timeouts this cycle expensive to diagnose. (b) *A safety switch should fail in the
safe direction and say so in a comment.* The `DSH_TELEMETRY_DISABLED` reasoning is the general rule for every
AISEF flag that can disable a check.

### L.2 Cost and latency are projections of the log

**FACT.** `packages/llm/token-meter` is a "single replay-aware token-meter service for request and surface
pressure" (`src/index.ts:1-5`); `priceSurface` returns both a routed-model price and a fixed-heuristic price per
node and **throws loud** if pricing answers a different occurrence count than asked, because "misalignment would
silently misprice nodes" (`src/route-pricing.ts:29-45`). Provider `TokenUsage` is recorded on
`assistant/message` events (`packages/core/session/src/types.ts:326`).

**FACT.** `SessionStatsProjection` folds latency **from the complete durable log**: `turns`, `steps`, `llmMs`
(`step/start` → `assistant/message`), `toolMs` (`tool/call` → `tool/result` matched by `callId`), `ttftMs`,
`decodeMs`/`decodeTokens` (`packages/session/session-stats/src/types.ts:22-39`). Its tests cover `callId`
pairing, **orphan-result rejection**, and leftover pruning at `turn/end`
(`packages/session/session-stats/tests/projection.spec.ts:284`).

**AISEF — ADOPT, and this is the structural fix for `FAM-BUDGET`.** SS-64 was "a budget cap reached inside a
retried verifier session is ignored" — a side-counter that disagreed with what happened. If cost and time are
*projections of the journal* rather than counters maintained alongside it, that disagreement is not expressible.
The "throw loud on count misalignment" rule is the same idea applied to pricing, and orphan-result rejection is
the same idea applied to pairing.

### L.3 Inspection facilities

**FACT.** Four: model-facing read-only runtime discovery `cordis_inspect_list` / `cordis_inspect_query`, which
can query service methods, event modes, tool schemas and live Slot trees but **cannot invoke business services or
modify the runtime** (`packages/extensions/tool-cordis/src/index.ts:27-80`); an experimental Cordis runtime
inspector exposing the fiber tree (`packages/experimental/inspector/src/index.ts:16-35`); model-facing
workspace-authorized session-history search (`packages/session-query/tool-session-query/src/index.ts:1-4`); and
`renderConfigDump` (§I.2).

**AISEF — note the read-only boundary.** A model-facing introspection tool that can read the runtime but not act
on it is a good pattern and a bad temptation: it is the shortest path from "the agent can see the harness" to
"the agent's report about the harness becomes evidence". Under **Memory Is Context, Never Evidence**, anything an
agent reads about the harness is context; only the harness's own records are evidence. If AISEF v2 ships
introspection, it must be read-only *and* its output must be unable to enter an evidence field.

