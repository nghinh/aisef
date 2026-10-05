*English · [Tiếng Việt](README.vi.md)*

# AISEF — AI Software Engineering Framework

AISEF builds software with coding agents and refuses to take their word for it. The package on PyPI, the Python
module and the command are all called `aisef`.

The principle behind every decision in this repository:

> **If it needs judgement, give it to the model. If it needs a guarantee, write code.**

**AISEF 2.0** makes that principle the runtime. `aisef run` executes an owner-approved plan on a git repository:
for each story a developer session changes the code, and the V2 kernel decides — from independent probes of the
product, never from the developer's word or the developer's own tests — whether the story is delivered, retried or
rolled back. Every decision is written to a hash-chained journal, and `aisef run --verify` re-derives the whole run
from it.

```bash
pip install aisef==2.0.0
```

- [Using AISEF 2.0](docs/v2/USAGE.md) · [Hướng dẫn tiếng Việt](docs/v2/USAGE.vi.md)
- [What changed in 2.0](CHANGELOG.md) · [Known limitations](#known-limitations-of-20)
- [Architecture RFC](docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md) · [Release process](docs/v2/RELEASE-PROCESS.md)
- [The 1.x framework (legacy surface and planning tools)](#the-v1-framework-legacy-surface-and-planning-tools)

## What AISEF 2.0 does

`aisef run` is the authoritative execution path. One run, in order:

1. **Inputs are sealed before anything runs.** The project bundle (requirements, behaviour contracts, the human
   approvals that bind them, the plan) is loaded and every hash re-checked; the requirements document must be the
   one the plan was approved against; the repository is cloned at the plan's baseline and never written.
2. **The plan is admitted statically.** Nine admission checks run before any model is called; a plan that does not
   admit is refused with its reasons.
3. **The model route is attested.** The preflight lists the provider's models and sends a few one-token probes; the
   route is accepted only if every answer was served by the declared model under one deployment fingerprint.
   Anything else is an *identity stop*: no session starts.
4. **Stories run in dependency order.** For each story the developer session (OpenCode, on the one attested route)
   changes the code inside a confined workspace. Then the kernel proves the candidate:
   - **ProductProof** — harness-owned probes (a Python callable, a CLI invocation, a process effect, a file artifact)
     check each behaviour contract against the candidate. Candidate code runs only in the probe's agent process; the
     verdict comes from a controller that never imports it, over an authenticated channel, so the code under test
     cannot manufacture a passing result.
   - **Engineering test adequacy** — the developer's tests must run, must not be vacuous, and must be relevant; they
     are evidence of engineering quality, never of product correctness.
   - **Preservation** — after the merge, every behaviour earlier stories proved is proved again; a regression rolls
     the story back.
5. **Failures have owners.** Every failure is typed (PLAN, DEVELOPER, ENVIRONMENT, PROVIDER, INTEGRATION, REVIEW,
   SECURITY) and consumes only its owner's retry budget; a retry tells the developer, in public facts, which
   criterion failed — never the proof's hidden stimulus.
6. **Spend is accounted, not estimated.** Requests, turns and tokens are re-derived from the evidence before and
   during every session; a ceiling reached, or spend that cannot be accounted for, ends the run.
7. **Everything is kept.** The run directory holds the raw journal, every candidate and merge in the clone, every
   session stream and the preflight ledger. `aisef run --verify` re-derives the verdict from the journal alone.

Behind it are nine kernel invariants, armed in every test run — among them *Requirement Authority* (only approved
contracts define product truth), *Independent Evidence* (the actor that writes the code never defines the evidence
that certifies it), *Typed Ownership*, *Immutable Provenance* and *No Prose As Control State* (no model output ever
becomes a control code). See the [architecture RFC](docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md) §4.

## Get started

Needs Python 3.11+, `git` 2.31+ and — for a live run — the [OpenCode](https://opencode.ai) client on `PATH` and an
OpenAI-compatible provider endpoint. `aisef run` is supported on **Linux and macOS**.

```bash
aisef run --check  --project bundle.json --settings run.json --repo ./myproject   # inputs + admission, no provider request
aisef run          --project bundle.json --settings run.json --repo ./myproject --out ./runs/r1
aisef run --verify --project bundle.json --out ./runs/r1                          # re-derive a finished run
```

- **`bundle.json`** (`aisef-v2-project/1`) — the project: requirements document, behaviour contracts, the human
  approvals binding each contract to its requirements, the plan (baseline commit and proof obligations per story),
  the public facts a developer may be told, and per story its dependencies and test paths.
- **`run.json`** (`aisef-v2-run/1`) — the one model route, the provider identity, the budget ceilings, the per-owner
  retry limits, timeouts and the turn cap. Nothing is defaulted.
- **Exit status** — `0` delivered (PASS; `--check` ready; `--verify` VERIFIED) · `1` not delivered (FAIL or
  NOT_REACHED; `--verify` REFUTED) · `2` refused before the run began (an input that does not hold, an unadmitted
  plan, an identity stop).

Field-by-field formats, the run directory and every refusal: [docs/v2/USAGE.md](docs/v2/USAGE.md).

## How 2.0 was qualified

Release candidate RC2 (`1565bcc`) was frozen with its wheel and sdist digests and qualified as shipped:

| check | result |
|---|---|
| full test suite, hermetic, on the exact candidate | 5,454 tests, 0 failed |
| CI | Linux (Python 3.11–3.14), macOS, Windows, lint, wheel — all green |
| mutation testing of the changed release-critical code | 261 targets, 6,463 / 6,463 mutants killed, 0 survivors |
| qualification rungs Q0–Q3 (static integrity, semantic conformance, adequacy, fault injection) | GREEN on Linux and Windows |
| Q4 — the kernel's control-critical projections against an independent reference model, 100,000 generated runs | 100,000 / 100,000 matched |
| Q5 — real re-execution of a recorded 12-run corpus, model stream replayed | 12 / 12 reproduced, no drift |
| reproducible build | three independent rebuilds byte-identical to the frozen wheel and sdist |
| clean install | installed wheel: version, CLI, `aisef run --check / run / --verify` offline — PASS |
| live release smoke (7 stories, 67 proof obligations, real model route) | 6 of 7 stories delivered; the final product satisfied **all 59 acceptance specs**; 0 false acceptances; one correct story rolled back by a plan criterion's false positive — see below |

The evidence is in [`closure-evidence/v2/release/`](closure-evidence/v2/release/), starting from
[`V2.0-FINAL-RELEASE-REPORT.md`](closure-evidence/v2/release/V2.0-FINAL-RELEASE-REPORT.md).

## What 2.0 claims, and what it does not

**Claimed:** deterministic, evidence-bound orchestration and product verification; candidate code cannot control
a verdict channel; raw run evidence is preserved and re-verifiable.

**Threat model:** a trusted operator; generated code may be faulty or opportunistic.

**Not claimed:** generalisation across arbitrary workloads; model quality; superiority over V1; hostile
multi-tenant isolation; full isolation against a malicious process of the same OS user; protection against the
machine's owner. `plan_quality_verdict` is always `NOT_CLAIMED` in 2.0.

### Known limitations of 2.0

- **AISEF 2.0 runs bundles; it does not author them.** A V2 project bundle (contracts, approvals, plan) is prepared
  and approved outside `aisef run`; there is no automatic conversion from a 1.x project.
- **Plan criteria that read Python source with line patterns can refute correct code.** In the 2.0 release smoke a
  correct story was rolled back because a "stdlib only" criterion matched a docstring line beginning with
  `from …` as an import (S6-SMOKE-2-FALSE-ROLLBACK-S10A). The kernel failed closed — no incorrect code reached the
  delivered product — but the story did not land. Syntax-aware criteria are planned for 2.1 (V21-37).
- **A regression found after the merge goes back to nobody.** It is owned by INTEGRATION and not retryable, so the
  developer neither learns the failing criterion nor gets a retry (V21-38, planned for 2.1).
- **Platforms.** A live `aisef run` is claimed on Linux and macOS; on Windows the package installs and the kernel's
  test suite runs, but a live run is not part of the 2.0 claim.
- **Probes** run with the standard library and the candidate's own source (no third-party project dependencies).
  The model review and the scanner (`ruff`, when installed) are informational and never block.

The full 2.1 backlog, with a reproducer for every item: [docs/v2/V2.1-BACKLOG.md](docs/v2/V2.1-BACKLOG.md).

## Coming from AISEF 1.x

- `aisef run` is now V2. V1's execution is `aisef legacy run …` (same options as 1.x `aisef run`), and the
  improvement loop is `aisef legacy improve …`. Every other 1.x command — `doctor`, `setup`, `plan`, `mockup`,
  `approve`, `qa`, `report`, … — is unchanged.
- V1 projects are not V2 bundles: V2 runs approved behaviour contracts and an admitted plan, not V1 story files.
- V2 writes nothing into the project repository; its results are the run directory and the clone's `main`.

## Install

```bash
pip install aisef
```

Or run from a source checkout:

```bash
git clone <repo> aisef && cd aisef && pip install -e .
python3 -m unittest discover -s tests -q   # a few minutes, opens no container (tests/__init__.py)
AISEF_TEST_DOCKER=1 python3 -m unittest tests.test_sandbox tests.test_tools -q   # plus the real-Docker tests
```

The reference skill repositories need **no manual clone**: `aisef setup` fetches
them into `~/.cache/aisef/references` at the exact commit pinned by
`aisef/kit/catalog.json` (about 91 MB by `du -sh` on 2026-09-15, once for every project). Offline machines
and CI can point elsewhere with `AISEF_REFERENCES=/path`, or use
`aisef setup --no-fetch` to work with whatever is already on disk.

No Python dependencies beyond the standard library. Optional: `docker`
(isolation when running tests) and `playwright` (extracting the visual contract
from mockups). When either is missing the framework **says so plainly** instead
of pretending it still verified anything.

## Layout

```
aisef2/                 the V2 kernel and runtime
  app/                  what `aisef run` executes: bundle, settings, preflight, client, run, verify, CLI
  product/              requirement authority, behaviour contracts, ProductProof specs
  probe/                harness-owned probes (python callable, CLI invocation, process effect, file artifact)
  plan/                 plan obligations, static and per-story admission, plan drift
  runtime/              run and story scopes, the termination sentinel, the run spec
  orchestrate/          the story runner: one authoritative orchestration path
  control/              failure ownership, retryability, routing
  journal/              the append-only, hash-chained journal and its projections
  quality/              engineering test adequacy
  invariants/           the nine invariants, armed in every test tier
aisef/                  the 1.x framework: planning pipeline, gates, guards, legacy execution
docs/v2/                using, releasing and the 2.1 backlog
closure-evidence/v2/    every qualification record of 2.0
```

---

## The V1 framework (legacy surface and planning tools)

Everything below describes the 1.x framework that 2.0 still ships. Its planning pipeline (`plan`, `mockup`,
`approve`, `gates`, …) and tools are unchanged; its execution runs only behind the named legacy surface,
`aisef legacy run` / `aisef legacy improve`, never by default. [Scoped long-term memory](docs/MEMORY.md)
(`aisef memory`) is **off by default and frozen** since 2026-09-12 — advisory context, never gate evidence.

Each 1.x project's input is **one file**, `docs/requirements.md`; the output is a working application plus
evidence for every step that produced it. Step-by-step guide: [`docs/USAGE-GUIDE.md`](docs/USAGE-GUIDE.md)
(English) or [`docs/HUONG-DAN-SU-DUNG.md`](docs/HUONG-DAN-SU-DUNG.md) (Vietnamese).

### What makes it different: the harness

Most agent tooling is a prompt plus a loop. AISEF is a **harness**: the run-time
scaffolding around the model that decides what the model sees, what it may
touch, what counts as done, and what is written down afterwards. Everything in
this repository belongs to exactly one of six harness groups, and that list is
the acceptance yardstick for the project itself.

| # | Harness group | What lives there | Where |
|---|---|---|---|
| 1 | **Instructions & rule files** | the engineering constitution compiled into `CLAUDE.md` / `AGENTS.md`, the pinned skill catalog, four agent roles each with its own fresh session, versioned prompts | `kit/`, `harness/routing.py` |
| 2 | **Tools** | three evidence-producing tools (`test`, `lint`, `sast`) the agent calls as `aisef tool <name> --story S`, plus documentation lookup; every tool carries prose on when to call it, how to read its result, and when *not* to call it | `harness/tools.py` |
| 3 | **Sandboxes & execution environments** | four permission levels, an `ExecutionProvider` contract, and five **named guarantees** (`network_none`, `read_only_fs`, `non_root`, `no_host_mount`, `secrets_absent`). A provider that cannot offer one says which one is missing; a degraded run is labelled, never silent. Isolation on a machine without Docker is **not** on the roadmap — [ADR-011](docs/ADR-011-sandbox-local-provider.md) says why, and what the `local` provider does and does not promise | `harness/sandbox.py` |
| 4 | **Orchestration logic** | role routing where **reviewer ≠ developer**, a story state machine, wave scheduling by dependency *and* write scope, and handoff packets whose every context slot declares its source | `control/`, `phases/` |
| 5 | **Guardrails / hooks** | ten guards on three lifecycle moments, each a standalone command returning an exit code, compiled into whatever the client supports, defined in one place | `harness/guardrails.py` |
| 6 | **Observability** | structured events with provenance, cost and latency per session, every check bound to the **SHA of the candidate** it ran on, the behaviour ledger, handoff and verdict records, and a benchmark corpus | `harness/observe.py`, `control/ledger.py`, `tests/bench/` |

Two consequences worth stating plainly. Guards live in group 5 on the framework
side, so **the client is never trusted** — a client that cannot host
pre-execution guards is recorded as offering weaker assurance instead of being
assumed fine. And group 6 binds every result to a commit, so "the tests passed"
always means "they passed on *this* code", never "they passed at some point".

### Harness of harness: the framework improves the framework

A single story passing its gate is not the interesting part. The hard problem is
what happens **after** an epic is declared done: a later story quietly breaks an
earlier one, a criterion has a test that never actually exercised it, a gap
stays open because nobody is looking for it.

AISEF answers that with a second loop wrapped around the first (ADR-004,
absorbed from the *Harness-of-Harness* line of work and measured here):

- **Frozen candidate.** Each attempt freezes a SHA; every check records the
  candidate it ran on. Evidence from another SHA is stale, which is a different
  outcome from a failure.
- **Behaviour ledger.** Every acceptance criterion, requirement, verification
  kind and screen has a state: VERIFIED, GAP or REOPENED. The ledger is a
  projection of the evidence, rebuilt every time, never a second source of truth.
- **Bounded improvement loop.** `aisef legacy improve --epic E` reads the ledger,
  generates **one** repair story for one gap, runs it like any other story, and
  re-verifies. It stops in code: no gaps left, loop budget spent, marginal
  improvement ≤ 0 for N consecutive loops, cost cap exceeded, or the plan itself
  is blocked.
- **Preservation.** A story that touches files owned by verified behaviour of
  other stories must leave those behaviours green — checked at the gate, not
  hoped for.
- **Negative control on tests.** A test that carries a criterion's code but was
  already green before the story wrote a line proves nothing; the gate detects
  that and says so, naming the test.
- **Qualified gates.** All 16 gate checks have three controls each (positive,
  negative/mutant, environment), so "is the gate itself scoring correctly" is a
  question answered by a command.

### Six steps

```bash
cd /path/to/your/project

aisef doctor                       # is the environment complete
aisef setup                        # detect stack, install skills, write CLAUDE.md + AGENTS.md
aisef compile                      # wire guards into the client (hooks / plugin)

aisef plan                         # PRD → architecture → UX → epics → stories
aisef gates                        # which gate is waiting for a human
aisef review prd                   # read the artifact
aisef approve prd                  # approve it

aisef mockup                       # one HTML per screen + visual contract
aisef approve mockups
aisef approve readiness

aisef legacy run                   # V1 implement: epics in sequence, stories in parallel
aisef legacy run --verify-only --story STORY-01-07   # re-verify a frozen candidate, no developer session
aisef qa                           # the verification suite
aisef devsecops                    # CI + Dockerfile + deployment + runbook
aisef pre-deploy                   # the final gate
aisef report                       # acceptance report + behaviour ledger + INDEX.md
aisef evidence STORY-01-04         # history of one story or one behaviour (AC-…, FR-…, qa:e2e)
aisef issues --format csv          # gaps and regressions from the ledger → _bmad-output/ISSUES.csv
```

To run without stopping for approvals: `aisef plan --auto-approve all`. Automatic
approvals are **always** marked `auto`, so it stays possible to tell which
documents no human ever read.

On a **greenfield** project, `app.dev_command` and `app.base_url` have no value
until the architecture picks a stack — `aisef mockup` and the readiness gate
will both say so, and the readiness gate refuses approval until they are set.
Once the first story has created the manifest, install the project's
dependencies **at the project root**: the baseline run, the nop control and the
clean verification tree all resolve `node_modules` / `.venv` from there, and
without them they can only report that there is nothing to run.

### Brownfield (existing codebase)

```bash
aisef baseline                     # analyse existing code → _bmad-output/baseline.md
aisef baseline --provider graphify # use Graphify graph (install: uv tool install graphifyy)
aisef baseline --incremental       # update graph after merge, without rebuilding baseline
```

When `baseline.md` exists, `aisef plan` automatically enters delta mode:
existing artifacts are kept, prompts include brownfield context and
`intent: "update"`, and the `blast_radius` slot in story prompts shows
impact analysis from the codebase graph before implementation.

### Once there is code

```bash
aisef doc vitest --topic coverage --story STORY-01-02
```

Looks up the library's real documentation (context7, cached) instead of guessing
API names; with `--story` the lookup becomes evidence. When a requirement changes
after release:

```bash
aisef change FR-3 "Slugs must keep underscores"
```

Writes the change into `docs/requirements.md`, marks the PRD (the `prd` gate and
everything downstream become `stale`), and generates a delta story
`STORY-CH-01` with `covers=[FR-3]` — the old story stays `DONE`.

```bash
aisef legacy improve --epic EPIC-01 --max-loops 3      # [--auto] does not stop at the human gate
```

Evidence-driven improvement loop (ADR-004 R3): QA → behaviour ledger → **one**
repair story for one GAP/REOPENED behaviour (`STORY-RP-01` inside `EPIC-RP-01`,
generated by code) → `run` like any other story → QA → a `loops[]` marker plus
`LOOP-REPORT-<n>.md`. The loop stops in code: no gaps left, `improve.max_loops`
reached, marginal improvement ≤ 0 for `improve.flat_loops` consecutive loops,
`improve.cost_cap_usd` exceeded, or the repair story is blocked by the plan
(handed back to a human with the reviewer's words). Loops from the second one on
need `aisef approve improve` unless `--auto`.

```bash
aisef legacy run --verify-only --story STORY-01-07
```

When a story fails only because of the measuring environment (end-to-end tests
sensitive to machine load), there is no need to pay for a developer session that
rebuilds code that already exists (ADR-004 R13): the re-verification run takes
the candidate at the head of the story branch, re-runs exactly the checks that
were ✗ or missing at that SHA, keeps the review and security verdicts from the
same SHA, and scores the full gate. Passing merges as usual; failing marks
`failed` and does not consume `run.max_retries`.

### Gates

Eight gates, each with two layers. The **machine gate** runs first — it catches
what machines catch better than people (dependency cycles, requirements that
cannot be verified, stories that declare no write scope). The **human gate**
runs afterwards, on something already clean.

Approval is **state on disk**, not a question inside a chat session: the approver
may be a different person, at a different time, on a different machine. An
approval record is bound to the artifact's **content hash** — editing a document
after approval voids it, and re-approving an upper layer marks every layer below
`stale`.

### Guards

Ten guards, each a command returning an exit code, wired into three lifecycle
moments:

| Moment | Guards |
|---|---|
| before every tool call | `write-scope` · `destructive` · `secret` · `git-stage` · `injection` · `process-ref` (rule 6) · `egress` (network destination allowlist) · `tool-bypass` (running the project's test/lint command directly instead of through `aisef tool`, which records nothing) |
| after every tool call | `diff-scope` |
| when the agent tries to stop | `completion` |

Guards live on the framework side, not the client side — the client is not
trusted. Both Claude Code and OpenCode have **proven on a real agent** that
guards block *before* the tool runs rather than detecting afterwards. A client
that cannot host pre-execution guards gets `aisef verify`, which re-runs
everything against the diff, and `aisef compile` records the lower level of
assurance in its report instead of staying silent — capability is **declared and
tested**, defaulting to "unproven", never to "probably fine". Since v1.0.0
OpenCode is a **first-class** client: guards block, conformance 10/10 (parity
with Claude — see ADR-006 §4), and `--format json` gives a machine-readable
stream (tools, tokens, cost per provider). One guard is the exception:
OpenCode's plugin API has no blocking equivalent of `Stop`, so `completion`
is not wired there — the compile report lists it as post-hoc, and the story
gate re-asks the same question from evidence, which fails the story instead
of stopping the session.

### Real bugs already hit

189 bugs found by measurement on real agents, grouped into eleven cause
classes with a regression check each (179–185 came from the first dogfood run
of the public 1.7.2 package and are fixed in 1.7.3; 186 came from the second
run, on 1.7.3, and is fixed in 1.7.4; 187 came from the clean OpenCode replay
of that run, on 1.7.4, and is fixed in 1.7.5; 188 came from the same replay
continued on 1.7.5, and is fixed in 1.7.6; 189 came from the same replay
continued on 1.7.6 and is **open** — reproduced deterministically, not yet fixed in
any release): `docs/FAILURE-TAXONOMY.md`. A new bug adds
a line there in the same commit as its test. Changes per version, and what to do
when upgrading: `CHANGELOG.md`.

The framework applies the same standard to itself. `docs/PROJECT-CLOSURE-GATE.md`
is the owner-approved contract for calling the engineering project complete, and
`aisef closure` scores its 27 criteria from evidence on disk without calling a
model. On 1.7.6 it passes 24 of 27; the three open criteria are external
validation by a person outside the project, which no amount of internal work can
satisfy. (1.7.2 read 23 of 27: its first dogfood run found three P1 defects,
D-026, D-028 and D-029, fixed in 1.7.3; the second run, on 1.7.3, found D-032,
fixed in 1.7.4; the clean OpenCode replay of that run, on 1.7.4, found D-033,
fixed in 1.7.5; the same replay continued on 1.7.5 found D-034, fixed in 1.7.6.) A release is identified by the product it ships — a content digest over
the tag's tree and the wheel/sdist digests on PyPI — not by which commit is HEAD,
so recording evidence about a release does not invalidate it (D-022, fixed in 1.7.2).

### Client conformance

Hooks and plugins are **compiled artifacts** — being syntactically valid does not
mean the client runs them. Bug 31 is the most recent example: a wheel install
compiled a hook pointing at a path that did not exist, valid syntax, and **no
guard ran at all**. Unit tests cannot catch this class by definition. The
conformance suite runs ten probes on a real client, a real worktree, real
guards, with `.claude/` never committed:

```bash
AISEF_CONFORMANCE=1 python3 -m unittest tests.conformance -v
```

Results land in `docs/CONFORMANCE.md` — every cell is one agent session, read
from disk (files present or gone), from the `tool_use` stream, and from evidence
the guards wrote themselves, never from what the agent said. The scratch project
and raw logs of each probe stay in `.conformance/<client>/` (changeable with
`AISEF_CONFORMANCE_DIR`) so a ✗ can be inspected instead of guessed at. The suite
deliberately does **not** inherit `CLAUDE_*` variables from the session that
launched it — running conformance from inside a Claude session is a real
scenario, and a child inheriting the parent's flags measures the wrong thing.
This repository's V1 release gate reads that table in code
(`AISEF_RELEASE=1 python3 -m unittest tests.test_release_gate`): the `claude`
column must show ten ✅ and the table must be no older than 14 days. On the 2.0
release path the V2 release gate replaces it ([docs/v2/RELEASE-PROCESS.md](docs/v2/RELEASE-PROCESS.md)). Both
Claude and OpenCode are first-class clients (10/10 conformance). CI:
`.github/workflows/conformance.yml` runs weekly.

### Releasing

Package, Python module and command all share the name **`aisef`** (since 0.2.0;
0.1.0 installed as `aisef` but was typed `aisdlc` — that alias was removed in
0.3.0). Release conditions are read by command, not by
feeling — from 2.0 they are the V2 ones, in
[docs/v2/RELEASE-PROCESS.md](docs/v2/RELEASE-PROCESS.md): only an exact
`vX.Y.Z` tag reaches production PyPI, and only after the test matrix, a clean
install of the staged artifact and the V2 release gate (the owner's recorded
authorization) pass inside `.github/workflows/release.yml`; RC and dev tags
(`v*rc*`, `v*-rc*`, `v*.dev*`) run `.github/workflows/staging.yml`, which never
publishes. Publication uses *trusted publishing* — no token lives in the
repository.

The V1 gate stays for the legacy surface and no longer gates a release:

```bash
AISEF_RELEASE=1 AISEF_ACCEPTANCE=<acceptance project> python3 -m unittest tests.test_release_gate -q
```

`AISEF_ACCEPTANCE` points at the dogfood project that has been accepted (v0.1.0:
`e9`, scope EPIC-01): the gate reads `pre-deploy-report.json` (passed, has a
declared scope, waivers carry reasons) and the `pre-deploy` approval bound to
that exact report. Unset, it skips with a named reason — which is not a pass.

The dogfood regression corpus (`tests/dogfood/`, enabled with
`AISEF_DOGFOOD=1`) rebuilds the `par` sample project from the inputs stored in
the repository and compares against the measured baseline — run it before every
tag.

#### What the benchmarks measured

Four cohorts, four null or inconclusive results, reported because a null is a result:

| cohort | model | tasks | AISEF pass@1 | bare pass@1 |
|---|---|---|---|---|
| v0.3.0 | frontier | easy | 1.00 | 1.00 |
| v1.3 simulator | scripted weak agent | 12 hard | — (by construction, no guards involved) | — |
| **C-1 (2026-09-12)** | **non-frontier, real** | **12 hard** | **0.64** | **0.69** |
| **C-2 (2026-09-15)** | **non-frontier, real, G5.3-qualified pair** | **12 hard** | **0.97** | **1.00** — [INCONCLUSIVE](docs/BENCH-REPORT-C2.md): 11 of 12 tasks at the ceiling, no resolution to measure a difference |

On [C-1](docs/BENCH-REPORT-C1.md): nine of twelve tasks tie, AISEF loses two
and wins one, and at three attempts per task that −0.05 is not distinguishable
from noise. The harnessed arm spent **44% more turns and 51% more wall-clock**
to get there. The guard fired **once in 72 attempts**, on a `__pycache__`
cleanup. Neither arm wrote a single file outside its declared scope.

Two things that reading needs:

- **20 of the 24 failures, in both arms, were sessions the CLI cut** when the
  model emitted a tool call it could not parse. This cohort measures a
  model↔CLI integration defect at least as much as it measures a harness.
- **Bench mode runs one agent session with no reviewer, no security pass and
  no gate.** So C-1 measures the *guard* layer, not the *gate* layer. The gate
  layer is where the measured cost is: on a real 10-story project, **67% of
  input tokens** went into attempts the gate then blocked, `review` being 18 of
  31 blocks ([E4](docs/E4-COST-DECOMPOSITION.md)).

So the honest positioning, on the evidence available today: AISEF does not make
an agent solve more. What it does, measurably, is refuse to call unfinished work
done, and leave evidence that says why.

#### Known limitations of 1.x

Declared here because every claim needs evidence; what has not been proven is
called unproven (owner decision 2026-09-06, `docs/RELEASE-PLAN-v0.1.0.md` §0):

- **The closure corpus is `marks-cli`** (owner ruling 2 in
  `docs/PROJECT-CLOSURE-GATE.md`): 7 of 7 stories done and merged, pre-deploy
  passed with its scope declared, and the PRE_DEPLOY gate signed by the owner on
  2026-09-14 — closure criteria G4.1–G4.7 all read PASSED from that project's
  evidence. *Historically* (v0.1.0–v1.0.0) the dogfood acceptance scope was
  EPIC-01 of `e9` (7 stories); EPIC-02..05 of `e9` never ran, and `e9` is no
  longer on disk.
- **OpenCode is a first-class client since v1.0.0**: conformance 10/10 (parity
  with Claude, see ADR-006 §4). *This entry listed a known agent-side
  limitation — "OpenCode + Serena writes `.serena/` files outside declared
  `write_scope`; the harness correctly rejects these" — until 2026-09-14. It is
  closed: `.serena` is inside `HARNESS_OWNED`, so the harness no longer rejects
  an MCP server's own notes.*

  ```
  python3 -c "from aisef.harness.guardrails import HARNESS_OWNED; print('.serena' in HARNESS_OWNED)"   # → True
  git log --oneline -S'".serena"' -- aisef/harness/guardrails.py   # → ea4d035, released in v1.3.0
  ```

  What replaced it is narrower: `HARNESS_OWNED` is a hard-coded inventory with
  no config escape hatch, so the *next* tool that writes outside it needs
  another framework commit. See
  [ROADMAP-POST-1.0 § 3](docs/ROADMAP-POST-1.0.md).
- **An agent inside a container still has no credential isolation** (S1): V1
  runs the agent on the host and only the verification suite in a container;
  `doctor` and `pre-deploy` name the missing guarantees instead of staying
  silent. As of 2026-09-13 this is a **decision, not a backlog item** — building
  isolation for the `local` provider is rejected with reasons in
  [ADR-011](docs/ADR-011-sandbox-local-provider.md); sensitive projects run
  Docker.
- **`mutation` is UNRUNNABLE in the acceptance environment** (the tool is not
  installed); it is waived with a reason in `verify.waiver_reason`, shown as ◇,
  and never becomes ✅. `image-scan` is the same case (docker scout requires a
  login, trivy and grype are absent).
- **`skills.offer` is off** (A/B measured no gain) and **`skills.inline` is
  gone** — two A/B runs on real agents reported `used` 0/0 while the inlined
  branch added ~8.8k prompt characters, so the flag and its code were removed
  in 1.4.0; an old project that still declares it loads with a warning.
  **`repo_map` is off** (`context.max_repo_map_chars = 0`, its A/B deferred).
- **`coverage`**: the harness reads the number the runner prints
  (`--coverage`/`--cov`); a project that has not enabled it gets ○ "not
  configured", which is not a pass.

### When a gate blocks

A blocking gate is the framework working, not the framework broken. Three common
cases and the correct response:

| The gate says | It means | Do this |
|---|---|---|
| `mockup has N unresolved spots` | the mockup hit a question nobody answered and **marked** it instead of deciding alone | answer the question (usually in the PRD/UX `open_questions`), fix the document, rebuild the mockup |
| `story touches a requirement blocked by an open question` | an epic assigned an FR the PRD records as undecided | answer the question, or drop that FR from the story |
| `merge conflict in …` | two stories edited the same file | the `write_scope` was declared wrong — fix it in the story, do **not** just resolve the conflict |

`--force` exists on `approve` and `legacy run` for deliberate overrides. Using it is a
decision, and it is recorded: the approval keeps the note, and the acceptance
report shows each gate's true state.

### Running in parallel

Epics run sequentially. Inside an epic two stories share a wave only when they
have **no dependencies left** *and* **disjoint write scopes** — without the
second condition they edit the same file and whoever merges last loses. Every
story runs in its own git worktree; merges happen one at a time at the end of the
wave. A merge conflict must not be resolved silently: it is **evidence that a
`write_scope` was declared wrong**.

### Layout of the 1.x package

```
aisef/
  cli/              commands grouped by phase, every command one-shot, no daemon
  config.py         thresholds and configuration, typed and validated
  clients/          Claude Code · OpenCode; capabilities are **declared**, never assumed
  control/          gates, approvals, scheduling, worktrees, BMAD document normalisation
  harness/          prompts · tools · sandbox · guards · observability · mockup mapping
  kit/              skill catalog, two-stage security filter, constitution, prompts, own skills
  phases/           plan · mockup · implement · run · qa · deploy · report
docs/
  SOLUTION.md              the whole design and why it is shaped this way
  EXECUTION-PLAN.md        execution plan and the state of each item
  REQUIREMENTS-EVIDENCE.md R1–R14 → runnable tests
  SPIKE-REPORT.md          results of the seven feasibility spikes
  HUONG-DAN-SU-DUNG.md     step-by-step user guide (Vietnamese)
  DANH-GIA-360-VA-LO-TRINH.md  360° assessment and roadmap (Vietnamese)
```

### Evidence, not self-report

Every gate reads `_bmad-output/evidence/{story}.jsonl` — each test run, each file
edit, each model call with its cost and latency, each mockup comparison. An
agent saying "done" counts for nothing.

Concretely, a story is finished only when: tests are green **and** green after
the last edit · lint is clean · changes stayed inside the declared scope · the
real screen renders every component the mockup promised · an independent review
(a separate session, forbidden to edit code) has no blocking findings · and no
test is empty of assertions.
