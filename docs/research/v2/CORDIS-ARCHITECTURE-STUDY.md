# Cordis — architecture study

**Revision studied.** Cordis `4.0.0-rc.7`, as vendored into DeepSeek Harness at
`vendor/cordis`, from `cordiverse/cordis` `packages/core` commit
`56b3d4f725681cf4556c1a8695a709cc3b6eed74`. Retrieved 2026-09-21. All paths below are relative to the harness
checkout pinned in [`SOURCES-PINNED.json`](SOURCES-PINNED.json).

The whole core is **2694 lines** across nine files: `context.ts` 146, `events.ts` 352, `fiber.ts` 754,
`index.ts` 14, `logger.ts` 271, `reflect.ts` 418, `registry.ts` 337, `service.ts` 115, `utils.ts` 287. Its size is
itself a finding: the lifecycle model that matters to AISEF is small enough to be read end to end and, if we want
it, re-derived in Python without importing a framework.

Labels used below: **FACT** — read from source at the cited line. **OBSERVATION** — a pattern across several
facts. **INFERENCE** — my reading, not stated in the source. **AISEF** — recommendation.

---

## 1. The core abstraction: a fiber owns effects

**FACT** (`vendor/cordis/src/fiber.ts:183-200`). A `Fiber` is "the runtime instance of one plugin application".
It carries `uid`, its own `ctx`, validated `config`, a lifecycle `state`, a `dispose` function, a `store` of
resolved service implementations, and `inertia` — "the in-flight load/unload transition, if one is currently
running".

**FACT** (`fiber.ts:147-154`). The lifecycle is an explicit state enum:

```
PENDING   waiting for required services
LOADING   the plugin callback is running
ACTIVE    loaded and providing
FAILED    the callback or its config threw
UNLOADING disposers are running
DISPOSED  removed, cannot restart
```

**FACT** (`fiber.ts:402-441`). `ctx.effect(execute, label)` is the unit of resource ownership. Its contract, from
the doc comment and the body:

- `execute` runs immediately and may return a disposer, a promise of one, or a (possibly async) iterable yielding
  several — generator effects register each yielded disposer *as it is produced* (`fiber.ts:77-93`);
- the collected disposers run **in reverse registration order**, either when the returned disposer is called or
  when the fiber unloads, whichever comes first (`fiber.ts:431`);
- disposal is **idempotent and joinable**: `if (disposing) return disposalTask` (`fiber.ts:427-428`);
- disposal is **sequenced and awaited** — each disposer is chained onto the previous one's promise
  (`fiber.ts:432-439`);
- every effect carries a **label** and builds a tree: `const meta: EffectMeta = { label, children: [] }`, and a
  nested effect pushes itself into `meta.children` (`fiber.ts:443-452`, type at `fiber.ts:95-101`).

**FACT** (`fiber.ts:418-422`). Creating an effect while the owner is `UNLOADING` throws
`CordisError('INACTIVE_EFFECT')` — "cannot create effect on inactive context" (`fiber.ts:172`). You cannot
acquire a resource in a scope that is tearing down.

**FACT** (`fiber.ts:265`). A **child fiber is itself an effect of its parent**:

```ts
this.dispose = parent.fiber.effect(() => {
  const remove = runtime.fibers.push(this)
  return async () => { /* … unload this fiber … */ }
}, 'ctx.plugin()')
```

**OBSERVATION.** That single line is the architectural centre of gravity. Because a child scope is registered as
an effect of its parent, there is exactly **one ownership tree**, disposal is transitive by construction, and
"what does this scope own" is answerable at runtime from labelled `EffectMeta` nodes rather than from a
hand-maintained cleanup list at each call site.

**AISEF.** This is the property AISEF v1 lacked. Our orphan-process family (F5 / INV-L.1), our retry-hygiene
family (D-034) and our reviewer-environment cleanup all had the same shape: *cleanup enumerated by hand, per
site, with no structural record of what was acquired*. A `StoryScope` whose worktree, sandbox, tool grants,
provider session, subprocesses, scratch storage, evidence writer and reviewer environment are each acquired as a
labelled effect of that scope gives us transitive teardown and a diagnosable ownership tree for free. See
[`AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md`](AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md).

---

## 2. Two disposal orders, and only one of them is ordered

This is the most important limit of the pattern, and it is easy to miss.

**FACT** (`fiber.ts:431`). *Within one effect*, disposers run sequentially, in reverse order, each awaited.

**FACT** (`fiber.ts:675-684`). *Across the effects of one fiber*, `_unload()` runs them **concurrently** and
**swallows every failure into the logger**:

```ts
private async _unload() {
  await Promise.all(this._disposables.clear().map(async (dispose) => {
    try { await composeError(async (info) => { … await runDisposable(dispose) }, …) }
    catch (reason) { this.ctx.logger.error(reason) }
  }))
```

**INFERENCE.** Cordis therefore guarantees *reverse order within a resource group*, not *ordering between the
resources a scope owns*. If a scope owns both a sandbox and the worktree the sandbox mounts, nothing in the
framework stops the worktree disposer from running first.

**AISEF — ADAPT, do not adopt.** AISEF's Story Transaction has hard ordering requirements: processes must be
reaped before the sandbox is torn down, the sandbox before the worktree is removed, and the evidence writer must
outlive all of them so that a teardown failure is still recordable. Two consequences:

1. Model the story's resources as a **nested chain** (each acquisition an effect registered inside the previous
   one) so reverse-order sequencing applies, or carry an explicit ordered resource list. Do not rely on
   sibling-effect disposal order.
2. **Do not swallow disposal failures.** In an assurance system a failed cleanup *is* the evidence — it is how
   orphans are born. A disposal failure must become a typed event on the evidence stream and must be able to fail
   the transaction's `DISPOSE`, not merely reach a logger.

---

## 3. Capability seam: name-based services bound to fiber lifetime

**FACT** (`service.ts:42-58`). A `Service` registers itself **in its constructor** via
`self.ctx.reflect.provide(name, self, this[symbols.check])`, and the doc comment states it "is registered
immediately and is automatically removed with the owning fiber" (`service.ts:8-9`).

**FACT** (`service.ts:15`, `reflect.ts:277`). `provide(name, value, check)` takes an **availability predicate**.
A capability can declare itself present-but-unusable rather than absent.

**FACT** (`reflect.ts:286`, `service.ts:61-63`). Services are keyed by a **Symbol per isolate scope**:
`this.ctx.root[symbols.isolate][name] ??= Symbol(name)`, and a service's filter compares
`ctx[symbols.isolate][this.name]` against its own. A child scope that rebinds the name to a different symbol sees
a different implementation. This is the substitution seam — the same mechanism serves tests, multi-tenancy and
per-scope overrides.

**FACT** (`reflect.ts:252-258`). Only the fiber that provided a service may `set` it; setting an unprovided name
throws `cannot set property "<name>" without provide`.

**FACT** (`registry.ts:29-51`). Consumers declare dependencies as an `inject` map of *service name → optional
intercept config*, contributed by a decorator onto a plugin class or function. Combined with `FiberState.PENDING`
("waiting for required services", `fiber.ts:141`), a consumer does not run until its declared capabilities exist.

**FACT — negative.** Searching `provide`/`inject` across `reflect.ts` and `registry.ts` surfaces **no version
field of any kind**. Capability resolution is by **name only**.

**AISEF — ADAPT.** The seam itself is right for us, and it maps cleanly onto the components the owner listed:
Canonical Proof Engine, Probe Engine, Sandbox, LLM Provider, Shell, Evidence Store, Reviewer, Security Scanner,
Execution Environment. Three deliberate divergences:

1. **Resolution must be recorded, not just performed.** Cordis answers "who provides `sandbox`?" dynamically at
   property access. An assurance system must be able to say *in the evidence* which implementation answered, at
   which version, for this story. AISEF's `ExecutionProfile` already does this for model routes; v2 should extend
   the same treatment to every capability and bind the resolved set into the profile identity hash.
2. **Versioning is ours to add.** A name-only seam means a provider swap is invisible to the record. We need a
   capability contract with an explicit version and a conformance test suite per contract (see §K of the harness
   study for how they test providers).
3. **Keep the availability predicate.** `[Service.check]` is exactly AISEF's `UNRUNNABLE` vs `FAILED`
   distinction expressed at the seam: a capability that is present but cannot run should say so, and that answer
   must remain typed all the way to the gate. This is SS-96 restated as an architectural property.

---

## 4. Configuration is validated before activation, not during

**FACT** (`fiber.ts:50-62`). `resolveConfig(runtime, config)` validates raw config against the plugin's
standard-schema *before the plugin runs*, throws `ValidationError` listing every issue with its path
(`fiber.ts:19-36`), and returns the **validated value** — which is what the fiber stores as `config`, keeping the
raw form separately as `_config` (`fiber.ts:190-192`, "the raw plugin config, re-resolved before each
activation").

**OBSERVATION.** This is exactly the shape the owner asked us to look for:
`raw configuration → resolved specification → frozen execution`. Cordis keeps both forms and re-resolves the raw
one at each activation, so a reload cannot silently inherit a previously resolved value.

**FACT** (`fiber.ts:52-56`). Async config validation is explicitly refused: `throw new TypeError('Async config
validation is not supported')`.

**AISEF — ADOPT the shape.** AISEF v1 already separates a profile's raw settings from its measured identity, but
it does so in the W1 harness, not in the kernel. In v2 the kernel itself should hold the distinction: a
`ResolvedRunSpec` produced once from raw config, validated, hashed, and the hash bound into every decision — with
no code path that reads raw config during execution. The "no hidden defaults during execution" property is worth
more to us than to them: their failure mode is a confusing runtime, ours is unreproducible qualification.

---

## 5. Failure semantics

**FACT** (`fiber.ts:156-173`). Cordis has one framework error class, `CordisError`, with a **stable
machine-readable code**, and exactly one code defined: `INACTIVE_EFFECT`. Plugin config failures use the separate
`ValidationError`.

**FACT** (`fiber.ts:141-145`). `FAILED` is a first-class lifecycle state — "the callback or its config threw" —
distinct from `DISPOSED`.

**FACT** (`fiber.ts:680-683`, `fiber.ts:119-137`). Two places deliberately contain failures rather than
propagate: disposer errors go to `ctx.logger.error`, and `emitPluginDisposed` wraps each observer callback so
"one callback cannot starve peers or interrupt ownership cleanup" (stated in `vendor/README.md`, local
modification 6).

**INFERENCE.** Cordis's error model is *coded but thin*: a stable code for the one framework invariant it
enforces, a typed lifecycle state for plugin failure, and best-effort containment everywhere else. It has no
notion of *who is responsible* for a failure.

**AISEF — the gap is ours to fill.** AISEF v1's typed-ownership model (PLAN / DEVELOPER / ENVIRONMENT /
PROVIDER / REVIEW / SECURITY / INTEGRATION) is **more advanced than anything in Cordis**, and this cycle proved
why it matters: SS-96 was precisely a check that reported `FAILED` for evidence that never executed, which routed
an environment failure into the developer's retry budget. Nothing in Cordis would have prevented that, because
Cordis has no owner concept. Keep ours; borrow only the discipline of *stable machine-readable codes* attached to
framework-level invariant violations.

---

## 5.5 The event bus is control flow, not notification — and that settles §11

**FACT** (`events.ts:32`). Five dispatch modes: `emit | parallel | serial | bail | waterfall`.

**FACT** (`events.ts:183-242`), read from the implementations:

| Mode | Semantics | Failure handling |
|---|---|---|
| `emit` | sync, **returned promises discarded** (`.map(cb => cb(...args))`, line 194) | an async listener's rejection is unobserved |
| `parallel` | `Promise.allSettled`, then `throw new AggregateError` (lines 184-187) | aggregated and propagated — the only mode that does |
| `serial` | awaits each in order, stops at the first bail value | first bail wins; later listeners never run |
| `bail` | sync, stops at the first bail value | same |
| `waterfall` | composes listeners around an innermost `next` | **"a listener that does not call `next()` vetoes the rest of the chain, including the built-in behavior"** (lines 228-229) |

**FACT** (`events.ts:13`). `isBailed(value)` — a listener bails by returning anything non-null, non-false,
non-undefined. Bailing is not a distinguished signal; it is *any truthy return value*.

**FACT** (`events.ts:245-302`). Listeners are registered as **effects on the current fiber** and removed
automatically on unload; registering on a disposed fiber throws `CordisError('INACTIVE_EFFECT')`. The set of
active listeners is therefore a function of which fibers are loaded.

**OBSERVATION.** Three of the five modes let a listener change what the system does: `serial` and `bail` by
short-circuiting, `waterfall` by refusing to call `next()` and thereby suppressing the built-in behavior.
Combined with `EventOptions.prepend` (`events.ts:113`), the outcome of a dispatch depends on **which plugins are
loaded and in what order they registered**. Cordis's bus is a general extension mechanism, not an audit trail.

**INFERENCE + AISEF — this answers §11 of the owner's decision directly, and answers it in the negative.**
AISEF v2 must not put control decisions on an event bus of this shape. Under Semantic Determinism, the answer to
"why did this story fail?" may not depend on listener registration order, and no component may veto a gate by
declining to call `next()`. The correct split:

- **Control** stays in explicit, typed, totally-ordered kernel code — the gate decides, and it is the only thing
  that decides. No subscription may alter a verdict.
- **Record** is an append-only journal with deterministic projections. Writing an event must have no effect on
  control flow; a projection is a pure function of the journal prefix.
- The one Cordis property worth carrying over is **ownership**: a journal writer should be a labelled effect of
  the scope it records, so it is closed exactly once and cannot outlive its story.

**A correction to an earlier reading of mine.** I first framed this as "event sourcing versus append-only journal
plus deterministic projections", and recommended the journal. That framing was wrong, and the harness's own
session layer is what corrects it: DeepSeek Harness *is* genuinely event-sourced, and the strict form it uses —
log is the only authority, every read model a pure fold, caches explicitly disclaimed as non-authoritative — **is
the journal-plus-projections design**, not an alternative to it. See
[`DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md`](DEEPSEEK-HARNESS-ARCHITECTURE-STUDY.md) §C and §D for the evidence.

So the rejection above is narrower than it first appeared, and it is worth stating precisely: **reject the
extensible dispatch bus as a carrier of control decisions; adopt event sourcing of state in its strict form.**
The two live in the same repository and do not conflict, because one is an extension mechanism and the other is
a record. The detailed argument, including the ~20 named events, is in
[`AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md`](AISEF-V2-EVENT-AND-STORY-TRANSACTION-PROPOSAL.md).

---

## 6. What the harness had to fix in it

**FACT** (`vendor/README.md`, "Local modifications", item 6). DeepSeek Harness locally hardened
`cordis/src/fiber.ts` to close "three reentrant disposal gaps": an effect's owner-list wrapper is now registered
*before* its setup body runs so an unload begun from inside setup awaits setup and every collected cleanup;
synchronous setup failure removes the wrapper and rolls back collected cleanup; async cleanup stays owner-visible
until quiescence; and **effect creation is rejected while the owner is `UNLOADING`**.

**FACT** (`vendor/README.md`, item 8). Their loader's "entry/group/tree mutations follow the pinned eager,
**non-transactional** implementation and do not restore previous plugins or options", and "plugin activation
failures can leave a partially applied tree".

**FACT — negative.** `find vendor -name '*.spec.ts' -o -name '*.test.ts'` returns **0**. The framework was
vendored **without its tests**, then modified. The safety net is the harness's own suite — 1227 spec files across
`packages/` and `apps/`, with the lifecycle cases at `packages/boot/app-boot/tests/`.

**OBSERVATION.** Two lessons, in opposite directions:

- *In favour of the model*: a team that runs this framework in production found reentrant disposal hard enough to
  need four separate hardenings. If we implement StoryScope disposal ourselves we will meet the same gaps, and we
  now know their names.
- *Against copying wholesale*: they patched a framework whose test suite they do not carry, and their
  configuration reload is explicitly non-transactional with partial-application failure modes. For AISEF, where a
  partially applied configuration would silently change what a qualification run measured, that is not
  acceptable.

---

## 6.5 How they make a dynamic composition statically verifiable

Cordis itself offers no static guarantee about what a composition will do. The harness builds one on top, and this
is the most directly transferable material in the whole study.

**FACT** (`package.json:140,146-149`). Four npm scripts: `verify-cordis-config`, `gen-cordis-catalog` /
`verify-cordis-catalog` (`--check`), `gen-cordis-api` / `verify-cordis-api` (`--check`). Every generated artefact
has a `--check` twin, so a generated file that drifts from its source fails the build rather than rotting.

**FACT** (`docs/cordis-api/`). The framework's API documentation — `context.md`, `events.md`, `fiber.md`,
`registry.md`, `service.md`, plus `.zh.md` and `.i18n.yaml` — is **generated from the pinned vendor declarations**
(`scripts/cordis-core-api.ts:1`, "Generate detailed Cordis core API pages from pinned vendor declarations"), with
JSDoc completeness enforced by `checkParams` / `checkReturns` / `reportViolations`. The documentation of a
vendored dependency cannot disagree with the vendored source.

**FACT** (`scripts/verify-cordis-config.ts:1-11`). The header states the semantic rule being enforced:

> the Loader interpolates a plugin entry's `config` (after declared injections activate) and the entry `disabled`
> field (at every mount decision) — "Every other entry metadata field stays static, so an expression there remains
> truthy data and silently changes composition."

**FACT** (`verify-cordis-config.ts:503-525`). `metadataExpressionErrors()` walks `id`, `name`, `group`, `inject`,
`intercept`, `isolate` recursively and rejects any `!!js` expression node with `"!!js is not interpolated here"`.
For `disabled`, a top-level expression is allowed and is **parse-checked without executing it**
(`new Script(...)`, with the comment "Compilation only — constructing a Script does not execute its source",
line 536), while an expression *nested below* `disabled` is rejected because "an expression nested anywhere below
it never evaluates, so it must stay literal".

**OBSERVATION.** The defect class they mechanized is: *a value that looks like a control directive, sitting in a
position where nothing evaluates it as control, and therefore silently acting as truthy data*. That is AISEF's
**No Prose As Control State** invariant (§18) in a different syntax. They did not state the principle and hope;
they wrote a checker that walks every position and names each offending path.

**FACT — the counter-example they could not check** (`scripts/cordis-core-api.ts:40-57`, and
`verify-cordis-config.ts` `CHOOSER_BACKEND_PACKAGES`). One package mounts backends *by runtime string*, so those
dependencies are "invisible to yml-row scanning". Their remedy is a **hand-maintained mirror list** in the
checker, with the failure it prevents spelled out: "keyless Linux CI (which only ever resolves `browse`) hides a
dropped `-native` dependency until a macOS boot."

**INFERENCE — this is the argument against dynamic discovery, made by the people who shipped it.** Where
composition is expressed as data, a checker can verify it. Where composition is computed at runtime, the checker
goes blind and the team pays in hand-maintained mirrors that can themselves drift. Their own comment records a
platform-conditional composition defect that CI structurally cannot see.

**FACT** (`scripts/check-vendor-manifest.sh`). Provenance is enforced by a commit-level guard: any staged change
under `vendor/*/src` or a vendored `bin.js` without a `vendor/README.md` change in the **same commit** fails —
"the manifest's local-modification log is the contract".

**AISEF — ADOPT all four, they are cheap.**

1. Every derived artefact gets a `--check` mode, and CI runs it. AISEF's Canonical ProofSpec will be derived from
   Behavior Contracts; a derived ProofSpec that has drifted from its contract must fail the build, not be
   silently regenerated.
2. Declare the interpolation positions of the run specification explicitly, then **write the walker** that
   rejects an expression, template, or prose directive anywhere else. This is the enforcement mechanism our
   "No Prose As Control State" invariant has been missing.
3. Parse-check without executing: validate the form of anything evaluable at the earliest resolvable point.
4. Provenance as a commit guard: modifying a frozen or vendored artefact without updating its manifest in the
   same commit should be mechanically impossible. AISEF's closure-evidence discipline is currently a rule I
   follow; it should be a hook.

---

## 7. Answering the owner's four questions

**Could AISEF benefit from Cordis concepts without adopting Cordis itself?** Yes, and it should. The valuable
parts are four architectural principles, not framework mechanisms: (a) a single ownership tree in which a child
scope is an effect of its parent; (b) resources acquired as labelled effects that return disposers; (c)
acquisition forbidden during teardown; (d) configuration validated into a resolved form before activation, with
the raw form re-resolved rather than inherited.

**Could similar lifecycle semantics be implemented in Python?** Yes. `contextlib.AsyncExitStack` already gives
reverse-order, awaited, idempotent teardown of a registered stack; `ExitStack.pop_all` gives transfer of
ownership; a labelled wrapper around `enter_context` gives the `EffectMeta` tree. The two things we must add
ourselves are the ones Cordis does *not* give us anyway: ordering guarantees across sibling resources, and
disposal failures as typed evidence rather than log lines.

**Which concepts are principles vs framework-specific mechanisms?**

| Principle (portable) | Mechanism (Cordis-specific, do not port) |
|---|---|
| child scope is an effect of its parent | `Fiber`/`registry` plugin model, `uid` bookkeeping |
| labelled effect tree for diagnosability | `symbols.effect`, `EffectMeta` propagation via `collect` |
| no acquisition while unloading | `CordisError('INACTIVE_EFFECT')` thrown from `effect()` |
| capability = name + availability predicate, bound to owner lifetime | `reflect` Proxy, `symbols.isolate` symbol keying |
| consumer declares required capabilities; does not run until they exist | `inject` decorator metadata, `FiberState.PENDING` |
| raw config → validated resolved config → activation | `standard-schema` / schemastery integration |
| composition expressed as data, so a checker can walk it | `!!js` YAML tag, Loader entry schema |
| every derived artefact has a `--check` twin | `gen-cordis-*.ts --check`, tsx script wiring |
| provenance enforced at commit time | `check-vendor-manifest.sh` + `vendor/README.md` log |

**Is a Cordis runtime dependency warranted for AISEF?** No. It is TypeScript, it is pre-release
(`4.0.0-rc.7`), the copy in production use is a *locally patched fork carried without tests*, and AISEF's kernel
is Python with a frozen-tree qualification discipline that a third-party runtime would sit awkwardly inside.
Adopt the four principles; implement them in ~200 lines of our own, under our own mutation and fault-matrix
qualification.

---

## 8. Open questions this study did not settle

1. Whether Cordis's `Fiber.inertia` join semantics are sufficient under *concurrent* disposal of the same scope
   from two callers. The harness's hardening note implies they found edge cases; their regression tests
   (`packages/boot/app-boot/tests/`) are the place to check, and that is a follow-up.
2. No upstream Cordis paper or formal specification was located in the vendored material; the manifest cites only
   repositories and commits. If a paper exists it was not part of this checkout, and no conclusion here rests on
   one.
