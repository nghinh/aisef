# AISEF Usage Guide

Optional [long-term memory guide](MEMORY.md): `aisef memory` is **frozen** and OFF by default — the code stays and keeps its bug and security fixes, no new capability is added. Includes configuration, CLI, provenance, security and retrieval-only benchmark limitations; memory is never gate evidence. Cross-references: [research/plan](MEMORY-RESEARCH-PLAN.md), [validation report](MEMORY-VALIDATION.md), [ADR-007](ADR-007-scoped-advisory-memory.md).

**AISEF** stands for **AI Software Engineering Framework**. The installable
package, Python module, and CLI command are all named `aisef`.

This guide is written for someone who has **never used** the framework, and
tries not to skip a single step. Each section tells you: what to type, how long
to wait, what to expect on screen, and what to do when it doesn't look right.

Reading conventions:

- `bash` blocks are commands to type in the terminal. Run one block at a time, read the output, then move on.
- The symbols `✅ ○ ⚠ ✗ –` are the **six gate outcomes** of the framework, not decoration. Their meaning is in [§10](#10-reading-story-gates-six-outcomes).
- Where it says "wait a few minutes", an agent session is running and **costs money**; real costs are in [§15](#15-real-costs-and-how-to-reduce-them).

---

## Table of contents

1. [What this framework does](#1-what-this-framework-does)
2. [Preparing your machine](#2-preparing-your-machine)
3. [Installation](#3-installation)
4. [Creating a project and writing the input](#4-creating-a-project-and-writing-the-input)
5. [`aisef setup` — load skills, generate rules](#5-aisef-setup--load-skills-generate-rules)
6. [Configuring `.ai/config.json`](#6-configuring-aiconfigjson)
7. [`aisef compile` and `aisef doctor`](#7-aisef-compile-and-aisef-doctor)
8. [Planning step: `aisef plan`](#8-planning-step-aisef-plan)
9. [Mockup step (UI projects)](#9-mockup-step-ui-projects)
10. [Reading story gates: six outcomes](#10-reading-story-gates-six-outcomes)
11. [Implementation step: `aisef run`](#11-implementation-step-aisef-run)
12. [Brownfield projects (existing codebases)](#12-brownfield-projects-existing-codebases)
13. [Verification, packaging, and acceptance](#13-verification-packaging-and-acceptance)
14. [Improvement loops and post-release changes](#14-improvement-loops-and-post-release-changes)
15. [Real costs and how to reduce them](#15-real-costs-and-how-to-reduce-them)
16. [Troubleshooting](#16-troubleshooting)
17. [Reference: all commands](#17-reference-all-commands)
18. [Reference: all configuration keys](#18-reference-all-configuration-keys)
19. [Glossary](#19-glossary)

---

## 1. What this framework does

You provide **one file** describing the software you want (`docs/requirements.md`).
The framework orchestrates an agent through the entire lifecycle: writing
product docs, designing, building mockups, splitting stories, writing code,
running verification, packaging, and **leaving evidence for every step**.

The underlying principle, explaining why everything is arranged the way it is:

> Where judgment is needed, delegate to the model. Where guarantees are needed, write code.

This is why there are **two kinds of gates** ("cổng"):

- **Machine gates**: scored by code, no human asked. Examples: "every requirement
  must have a covering story", "no writes outside the allowed scope", "tests
  must pass after the last edit". The machine scores first, then the human
  reviews.
- **Human gates**: you read and sign off. There are **eight**, in this exact
  order:
  `prd → architecture → ux-spec → epics → stories → mockups → readiness → pre-deploy`.

Approval is **state on disk**, not a reply in a chat session. It is tied to the
**content hash** of the document: editing the document after approval
automatically invalidates it (`stale`), and re-approving an upstream gate makes
every downstream gate `stale` too. You don't need to remember this —
`aisef gates` always tells you.

Three invariants you will encounter repeatedly throughout this guide:

- **not configured ≠ passed** — if you haven't declared a test command, the gate item is ○, not ✅.
- **unrunnable ≠ failed** — missing Docker shows ⚠, not ✗.
- **not yet fixed ≠ unfixable** — a failed story is recorded with a reason, not deleted.

---

## 2. Preparing your machine

Four things, only **two** are required.

| Item | Required? | Check with | What if missing |
|---|---|---|---|
| Python ≥ 3.11 | **yes** | `python3 --version` | can't install the package |
| `git` | **yes** | `git --version` | can't run `aisef run` (each story needs its own worktree) |
| An agent client: `claude` or `opencode` | **yes, to run agents** | `claude --version` | agent commands exit with code 2 and the message "claude is not installed on this machine" |
| Docker | no | `docker info` | tests run directly on the host; the framework records this as **degraded** with the name of each missing guarantee |
| Playwright + Chromium | no, unless the project has a UI | `npx playwright --version` | can't extract a visual contract from mockups |

Install the Claude Code client following Anthropic's instructions, then log in once:

```bash
claude --version
```

If this command doesn't work yet, every agent step below will fail — finish
this part first.

**Which client.** Both are real, and the difference is what the harness can
measure, not whether it works:

- `claude` is **tier 1**: it decides a release. All 10 guards block at source
  (`blocks_at_source: true` in `_bmad-output/compile-report.json`).
- `opencode` is **tier 2 in V1**: supported, does not block a release, because
  cost and turns are not measurable from the harness on it. It is not
  experimental — the `todo-oc` dogfood project merged **7 of 7** stories through
  it. 9 of 10 guards block at source; OpenCode's plugin API has no blocking
  equivalent of `Stop`, so the `completion` guard is re-asked afterwards from
  evidence instead of stopping the action. `aisef compile` says so per client
  ([§7](#7-aisef-compile-and-aisef-doctor)).

Two OpenCode specifics worth knowing before the first run: `run.max_turns` is
enforced by the adapter counting turns on the event stream (the CLI has no
`--max-turns`, so the number was ignored before 1.4.0), and the host's
`ANTHROPIC_*` variables are **not** passed to it — see
[§6](#6-configuring-aiconfigjson).

---

## 3. Installation

Install in a virtual environment to avoid touching the system Python:

```bash
python3 -m venv ~/.venvs/aisef
source ~/.venvs/aisef/bin/activate
pip install aisef
```

Verify the installation:

```bash
aisef --help
```

You should see a list of **33** subcommands (`setup`, `doctor`, `plan`, `run`, …
all of them in [§17](#17-reference-all-commands)).
The package, Python module, and CLI command are all named `aisef`.
`aisef --version` prints the version; to inspect the whole environment, use
`aisef doctor`.

This guide describes **1.7.2** (released 2026-09-15; 1.0.0 was 2026-09-08, and
1.2.x, 1.3.0, 1.3.1, 1.4.0, 1.5.0, 1.6.0, 1.7.1 came between). 1.7.2 changes
nothing in the CLI or the workflow described here: it corrects the framework's
own project-closure gate, which identified a release by the repository's HEAD
commit instead of by the product it ships (`CHANGELOG.md`, D-022). 1.7.0 was
tagged but its release CI failed, so it never reached PyPI — if you see that
number anywhere it is not a release. Check what you actually have, and read the number rather than
assuming:

```bash
aisef --version
```

Worth doing after every upgrade, because the failure it catches is silent: if an
older `aisef` is still first on `PATH` — a `pipx` install left behind, say — every
guard it records comes from the old rules and answers successfully, so nothing
tells you. In 1.6.0 the harness no longer hands the agent a binary merely named
`aisef`; it hands over the launcher it is itself running from.

If you previously installed version 0.1.0 (when the command was called
`aisdlc`): the old alias was removed in 0.3.0. Run `aisef compile` in each
project to point hooks to the new name.

The framework has **no Python dependencies** beyond the standard library.

### How long the first ten minutes actually takes — measured, not estimated

On a clock, 2026-09-12, macOS (Darwin 25.5, Python 3.14.7), with an **empty**
pip cache so the number is not flattered:

| step | command | measured |
|---|---|---|
| virtualenv | `python3 -m venv .venv` | 2.0 s |
| install | `pip install --no-cache-dir aisef` | 2.1 s |
| initialise | `aisef init --stack python` | 0.1 s |
| diagnose | `aisef doctor` | 1.2 s |
| **write `docs/requirements.md`** | — | **your work**, and the only part a clock cannot help with |
| diagnose again | `aisef doctor` | 1.1 s → `✅ ready` |

That is about **six seconds of machine time**. The "ten minutes" is almost
entirely one task: writing down what you want. A four-line `requirements.md` is
enough to turn `doctor` green.

Two things `doctor` tells you on that first run, both worth reading:

- `docker daemon — not running` and `sandbox provider — local`: tools run
  outside isolation and evidence is marked *degraded*. Fine for a trial, not
  for an acceptance run.
- Until 1.3.1 the `tools.test` written by `init` printed no test names, so two
  gate checks came up "not configured". The presets now include `-v`; coverage
  still needs a plugin and is still yours to declare.

`init` writes **4 keys** into `.ai/config.json` (`tools.test`, `tools.lint`,
`sandbox.image`, `sandbox.allow_hosts`), of which exactly **one must be
declared**: `tools.test`. Version 1.3.0 on PyPI still wrote all 68 defaults;
1.3.1 does not.

For contributors who want to modify the framework:

```bash
git clone <repo> aisef && cd aisef && pip install -e .
python3 -m unittest discover -s tests -q     # 3122 tests, OK (skipped=19) — measured 2026-09-15 on 1.7.2
```

(A checkout run from a git *worktree* skips about 60 more, because `.gitignore`
keeps `references/*` and the benchmark directories out of it.)

---

## 4. Creating a project and writing the input

The framework works **inside a project directory**. That directory must be a
git repository (because each story runs in its own `git worktree`).

```bash
mkdir ~/projects/notes && cd ~/projects/notes
git init
mkdir docs
```

Now write the single input file: `docs/requirements.md`. This is **prose** —
you don't need to follow any template. The planning phase will turn it into a
product document with numbered requirements `FR-1`, `FR-2`, etc. The more
specific you are, the fewer open questions later.

A complete example, enough to run for real:

```markdown
# Personal notes application

A web app that runs entirely on the user's machine, with no accounts and
no server. Data is stored in the browser.

## Users and what they do

The user is an individual jotting quick notes throughout the day. They need
to create notes, edit content, search by keyword, and delete things they
no longer need.

## Functional requirements

- Create a new note with a title and body.
- Edit a note, auto-save after the user stops typing for 800 milliseconds.
- Delete a note, with a confirmation step and a trash bin that retains items for 7 days.
- Full-text search on title and body, case-insensitive and accent-insensitive.
- Note list sorted by most recently edited.

## Constraints

- Must work offline.
- Must not send data off the user's machine.
- Supported browsers: latest Chrome, Firefox, Safari.

## Preferred technology

React + TypeScript + Vite, testing with Vitest, end-to-end testing with Playwright.
```

Three tips for this file:

1. **State your constraints** (offline, privacy, browser support) — they become
   non-functional requirements and will be tested.
2. **State your technology preferences if you have any.** If you don't, the agent
   picks for you, and you'll have little room to complain later.
3. **Don't write design.** Don't describe database tables or function names;
   that's the architecture step's job.

---

## 5. `aisef setup` — load skills, generate rules

```bash
aisef setup
```

This command: detects the project's technology stack from `docs/requirements.md`,
selects matching skills from the catalog, **filters out attack skills**, installs
them into the project, generates `CLAUDE.md` and `AGENTS.md` (the rules the
agent must follow), and writes a default `.ai/config.json`.

On the first run on a given machine, it downloads the reference skill repository
to `~/.cache/aisef/references` (91 MB by `du -sh` on 2026-09-14, shared across
all projects). If the machine has no network:

```bash
aisef setup --no-fetch          # use only what's already on disk
AISEF_REFERENCES=/path/to/repo aisef setup   # point to a pre-downloaded copy
```

To preview without writing anything:

```bash
aisef setup --dry-run
```

Real output, run on the React + Vitest `requirements.md` from [§4](#4-creating-a-project-and-writing-the-input):

```
Detected stack: frontend: react · undetermined: backend, database, deploy
  ⚠️  undetermined: backend, database, deploy
     — architecture phase will decide; not guessing here

will install 137 skills:
  aisef        1
  bmad         34
  security     87
  superpowers  10
  ui-ux        5
  karpathy     skipped — reference only (license: none)

installed 137 · unchanged 0 · removed 0 · total 137
rules: CLAUDE.md, AGENTS.md
wrote .../.ai/config.json
```

The count depends on the detected stack, so yours will differ. Running
`aisef setup` again does **not** duplicate skills — the second run reports them
under `unchanged`.

Important: on a fresh project `.ai/config.json` is written with exactly **one
key**, and it is empty:

```json
{
  "tools.test": ""
}
```

The framework deliberately does not guess your test command — "not configured"
must be visible, not silently treated as "passed". (`aisef init --stack <name>`
is the other door: it writes four keys with real values for a known stack. See
[§6](#6-configuring-aiconfigjson).) The next step is to fill it in.

**Commit the installed skills.** Each story runs in a `git worktree`, which is a
fresh checkout: an uncommitted skill directory simply does not exist where the
agent session runs. The same applies to the files `aisef compile` writes
(`.claude/settings.json`, `.opencode/plugin/`) — uncommitted, the session runs
with no guard at all, and the story then fails `guard ran` after you have paid
for it. Since 1.5.0 `aisef run` says so before the first session starts, but
committing is still yours to do:

```bash
git add .ai .claude .opencode AGENTS.md CLAUDE.md
git commit -m "aisef setup: skills, rules, guard hooks"
```

One consequence to expect: your linter will now read 137 skill directories as
project source. The `node`, `react` and `python` presets already exclude
`.claude`, `.aisef` and `.opencode`; a hand-written `tools.lint` must do the same.

---

## 6. Configuring `.ai/config.json`

This is the step most often skipped — and skipping it means gates will report
○ "not configured" forever. Open `.ai/config.json` and enter the **real
commands** for your project.

Four groups of keys to address immediately:

| Key | Meaning | Example (React + Vitest) |
|---|---|---|
| `tools.test` | test command used by the agent and gates | `npm test --silent` |
| `tools.lint` | lint / type-check command | `npx tsc --noEmit` |
| `verify.unit`, `verify.e2e`, … | command for **each verification type** at step 5 | `npx playwright test tests/e2e` |
| `app.dev_command`, `app.base_url` | how to start the app for mockup comparison and e2e runs | `npm run dev -- --port 5199 --strictPort`, `http://localhost:5199` |

Example of a working configuration for a React project:

```json
{
  "tools.test": "npx vitest run --reporter=verbose --coverage",
  "tools.lint": "npx tsc --noEmit",
  "verify.unit": "npx vitest run --reporter=verbose",
  "verify.e2e": "npx playwright test tests/e2e",
  "verify.accessibility": "npx playwright test tests/a11y",
  "verify.perf": "npm run bench",
  "app.dev_command": "npm run dev -- --port 5199 --strictPort",
  "app.base_url": "http://localhost:5199",
  "coverage.min": 0.85,
  "run.max_retries": 2
}
```

And for a Python project. `aisef init --stack python` gets you the first two lines
already, minus the coverage flags:

```json
{
  "tools.test": "python3 -m pytest -v --cov=src --cov-report=term",
  "tools.lint": "ruff check . --exclude .claude --exclude .aisef --exclude .opencode",
  "verify.unit": "python3 -m pytest -v",
  "coverage.min": 0.85
}
```

Two details in there are deliberate, not noise. `python3`, not `python`: macOS and
most current Linux distributions have only the former, and the preset picks the
interpreter `shutil.which` finds. And the `--exclude` flags keep the linter off the
skill directories `aisef setup` installed — the measured case was a Node project
where `npx eslint .` reported 116 `no-undef` errors inside skill scripts and failed
a story's lint check.

Three things worth knowing right away:

- **The test command must print individual test names.** The `criteria have tests`
  gate reads test names to determine which acceptance criteria have been
  demonstrated. Vitest needs `--reporter=verbose`, pytest needs `-v`. Without
  test names in the output, the gate item is ○, not ✅. Names are read from
  **every** suite whose output a parser recognises, so an e2e-only criterion is
  fine — but that suite still has to print them.
- **If you want coverage numbers, the test command must print them**
  (`--coverage` or `--cov`); without them the `coverage` item is ○ with a
  message pointing to the exact fix.
- **A verification type left blank means "not configured"**, and the pre-deploy
  gate will block because of it. If a type genuinely doesn't apply (e.g., no
  `api-contract` for a project with no backend), **waive it explicitly**:

```json
{
  "verify.waived": "api-contract,uat",
  "verify.waiver_reason": "2026-09-06, local-first app with no backend so these two types don't apply — signed: Nghi"
}
```

A waiver without a reason is blocked by the gate. Waived types show ◇ and
**never** become ✅ — you accept responsibility, not a passing grade.

One more thing to know before a verification type goes in: a command that matches
**no tests** is reported as unrunnable, not as failing. `verify.accessibility` is
typically `playwright test --grep @a11y`, and until some story writes an `@a11y`
test that command finds nothing — every story of the project used to be told
accessibility had failed. It still blocks the story, which is the honest outcome;
the reason now names both possibilities.

**If you run OpenCode against an Anthropic-compatible endpoint**, you need one
more key. Since 1.5.0 an API key goes only to the client that authenticates with
it: `claude` receives `ANTHROPIC_*`, `opencode` receives nothing, and the shared
allowlist keeps only `LC_` and `AISEF_`. A client that can read such a key uses it
*instead of* its own login, so the run would bill an account nobody chose. To pass
them deliberately:

```json
{
  "clients.env_allow": ["ANTHROPIC_"]
}
```

All keys are listed in [§18](#18-reference-all-configuration-keys).

---

## 7. `aisef compile` and `aisef doctor`

```bash
aisef compile
```

Generates hooks/plugins for the client, connecting the framework's **ten
guards** to the agent session. Guards run on the framework side, not the client
side — the client is not trusted. (Any document saying nine is from before 1.6.0;
`python3 -c "from aisef.harness.guardrails import GUARD_MATCHERS; print(len(GUARD_MATCHERS))"`
settles it.)

| When | Guard | What it blocks |
|---|---|---|
| before each agent tool use | `write-scope` | writes outside the story's allowed scope |
| | `destructive` | destructive commands (`rm -rf`, `git push`, changing remotes…) |
| | `secret` | writing API keys, tokens, or private keys into files |
| | `git-stage` | unauthorized staging/committing outside the workflow |
| | `injection` | content containing prompt-injection attempts targeting the agent |
| | `process-ref` | writing story/epic codes into source code |
| | `egress` | outbound network connections to hosts not in the allowlist |
| | `tool-bypass` | running your declared test/lint/sast command directly instead of through `aisef tool` — **new in 1.6.0**, see below |
| after each tool use | `diff-scope` | actual changes exceeding the allowed scope |
| when the agent is about to stop | `completion` | stopping when tests aren't green after the last edit |

Real output of `aisef compile --client all` on the project from
[§5](#5-aisef-setup--load-skills-generate-rules):

```
client: claude
  wrote .../.claude/settings.json
  guards blocking before action: destructive, egress, git-stage, injection, process-ref, secret, tool-bypass, write-scope
  guards blocking at other hooks: completion (Stop), diff-scope (PostToolUse)
client: opencode
  second-tier in V1: cost/turns not measurable from harness — supported, does not block release
  wrote .../.opencode/plugin/aisef-guard.ts
  guards blocking before action: destructive, egress, git-stage, injection, process-ref, secret, tool-bypass, write-scope
  guards blocking at other hooks: diff-scope (PostToolUse)
  ⚠️  guards post-hoc only: completion
     — not wired into this client's hooks at all; the rule is re-asked afterwards from evidence (story gate, `aisef verify`), which cannot stop the action, only fail the story
  capabilities not at native level:
     dir_allowlist: unsupported
     tool_allowlist: emulated
     turn_limit: unsupported

report: .../_bmad-output/compile-report.json

⚠️  some clients can only be checked later — lower assurance, noted in report
```

Three things to read out of that, none of them an error:

- **Hook coverage is per client.** Claude wires all ten; OpenCode wires nine,
  because its plugin API has no blocking equivalent of `Stop`. `completion` is
  therefore *post-hoc* there — the rule is still asked, from evidence, after the
  fact. If you read `blocks_at_source` from `compile-report.json`, OpenCode
  reports `false`: the flag means **all** of them block, not most. The count of
  guards actually wired is `guards_wired` (10 and 9 respectively), and that is
  what the `guard ran` gate check reads.
- **"capabilities not at native level"** says this client cannot natively restrict a
  few things, so the framework records the exact guarantee level it achieves
  instead of pretending. `turn_limit: unsupported` refers to the CLI flag; the
  adapter still enforces `run.max_turns` by counting turns itself.
- The guards that matter most (out-of-scope writes, destructive commands) block at
  source on both.

### The `tool-bypass` guard, and why you will meet it

If the agent runs your project's declared test command directly, it is blocked with
the recorded command to use instead. Reproduced here on a project whose
`tools.test` is `npm test --silent`:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"npm test --silent"}}' \
  | AISEF_STORY_ID=STORY-01-02 aisef guard tool-bypass
```

```
aisef guard tool-bypass: `npm test --silent` is the project's test command run
directly, so nothing about it is recorded — and the gate reads evidence, not
claims. Run `/…/bin/aisef tool test` instead: it runs the same command and records
the result, which is what the `TDD`, `test` and `coverage` checks read. Narrowing a
run for debugging (extra arguments, a single file) is not blocked.
```

(The message names the launcher by absolute path, not the bare word `aisef` — that
is the 1.6.0 fix against an older `aisef` on `PATH` answering by the old rules.)

It exists because the prompt already said this and the prompt was ignored. Measured
on `todo-cli` across ten sessions: the developer ran `npm test` **ten times** and
`aisef tool test` **zero** times, so every `test` event in that story's evidence
came from the harness's own verify pass — one green run per candidate — and
red-before-green had nothing to compare. The `TDD` check failed ten sessions in a
row over a working implementation. A rule only the prompt states is not a rule.

Two boundaries, both deliberate:

- **Narrowing for debugging is not blocked**, because recording a subset as `test`
  would make part of a suite look like a green one. What counts as narrowing is a
  *positional* argument the declared command does not have: `python -m pytest -v
  tests/x.py -k foo`, `npx vitest run tests/a.test.ts` and `npm test --
  tests/a.ts` are all allowed where the bare declared command is not. A
  **flag-only** difference is not narrowing and stays blocked — `npm test
  --silent` is the whole suite, spelled differently.

  *Corrected 2026-09-14 (bug 156).* Until then `npm test -- tests/a.ts` **was**
  blocked, because the command key collapsed `npm` / `pnpm` / `yarn` / `bun` to
  `(manager, script)` and discarded everything after the script name — while the
  block message the developer reads ended with "Narrowing a run for debugging …
  is not blocked". On a Node project there was therefore no legal way to narrow a
  run while debugging, which is the same dead end as bug 118. The collapse is
  kept, so a flag-only difference still cannot slip past; the distinction is now
  drawn on positional arguments instead.
- **It does not fire in review sessions.** It applies only where a story id is
  present, because evidence is recorded per story and a reviewer deliberately has
  none — `aisef tool test` would record nothing for it either.

Run `aisef compile` again whenever you upgrade the package, and **commit what it
wrote** ([§5](#5-aisef-setup--load-skills-generate-rules)).

```bash
aisef doctor
```

Real output on the same project:

```
Environment:
  ✅ python >= 3.11 — 3.14.7
  ✅ git
  ✅ claude CLI — /opt/homebrew/bin/claude
  ✅ opencode CLI — /Users/…/.opencode/bin/opencode
  ✅ agent credential — ANTHROPIC_API_KEY set in the environment — these outrank the client's own login; unset them to use it
  ○ docker daemon — not running — sandbox will degrade, lower guarantees
  ○ playwright + chromium — playwright not installed — run: npm i -D playwright && npx playwright install chromium — cannot extract mockup contracts
Project:
  ✅ project directory — /…/notes
  ○ sandbox provider — local — guarantees at WORKSPACE_WRITE: none; MISSING network_none, non_root, secrets_absent — tools run outside isolation, evidence marked degraded
  ✅ docs/requirements.md — /…/notes/docs/requirements.md
  ✅ config — defaults → /…/notes/.ai/config.json
Installed skills:
  ✅ has skills — 137 directories
  ✅ framework skills up to date — matches source
  ✅ no offensive skills — clean

✅ ready
```

Read each line as follows:

- `✅` — present and sufficient.
- `○` — missing an **optional** item, with the install command shown. For example
  `○ playwright + chromium` only matters for projects with a UI.
- `✗` — missing a **required** item; the last line will say `✗ missing: …`.

The final line is the verdict: `✅ ready` or a list of what's still missing.

Two lines above are worth pausing on. `agent credential` names the variable it
found — the name only, never the value — because an `ANTHROPIC_*` variable in your
environment outranks the client's own login, so a run can authenticate against an
account you did not choose. And `sandbox provider — local` lists the guarantees it
is *missing* rather than silently proceeding: with Docker not running, every tool
run exposes the host's credentials to the agent and all evidence is marked
`degraded`. Fine for a trial, not for an acceptance run.

---

## 8. Planning step: `aisef plan`

```bash
aisef plan
```

This command runs **five agent phases** — each one a session that stops at the next
human gate — and then one step the framework does itself:

| Step | Produces | Gate waiting for your approval |
|---|---|---|
| `project-context` (agent) | `project-context.md` | (no gate) |
| `prd` (agent) | `prd.md` | `prd` |
| `architecture` (agent) | `architecture.md` | `architecture` |
| `ux` (agent) | `DESIGN.md`, `EXPERIENCE.md` | `ux-spec` |
| `epics` (agent) | `epics.md` | `epics` |
| story split (**code, no model call**) | `stories.index.json` + one file per story | `stories` |

The five phase ids are the ones the code carries
(`python3 -c "from aisef.phases.plan import PHASES; print([p.id for p in PHASES])"`);
the split is file splitting and parallel-wave computation, which is deterministic
and so costs nothing. It re-runs every time, because `epics.md` may have been
edited.

All files go into the `_bmad-output/` directory of the project.

**If your repository already has code in it**, run `aisef baseline` before
`aisef plan` — [§12](#12-brownfield-projects-existing-codebases). Planning reads
`docs/requirements.md` and nothing else, so without the baseline it plans as if the
directory were empty; since 1.5.0 `aisef plan` warns when it sees code, or even
just a `package.json`, but the warning is not the fix.

When the command stops, check which gate is waiting:

```bash
aisef gates
```

The table shows eight gates. Real output on a freshly created project:

```
Approval gates — /…/notes/_bmad-output

  ⏳ prd            pending              [missing: prd.md]
  ⏳ architecture   pending              [missing: architecture.md]
  ⏳ ux-spec        pending              [missing: DESIGN.md, EXPERIENCE.md]
  ⏳ epics          pending              [missing: epics.md]
  ⏳ stories        pending              [missing: stories.index.json]
  ⏳ mockups        pending              [missing: design-contract.json]
  ⏳ readiness      pending              [missing: stories.index.json, design-contract.json]
  ⏳ pre-deploy     pending              [missing: pre-deploy-report.json]

Next gate to handle: prd
  aisef review prd
```

Four states: `pending` (waiting), `approved` (signed off), `stale` (was approved
but the document changed since, or an upstream gate was just re-approved),
`changes_requested` (you sent it back with notes). The last line always tells
you what to do next.

Read a gate's document:

```bash
aisef review prd
aisef review prd --lines 200      # show more lines
```

Approve, or send back with a reason:

```bash
aisef approve prd --note "read it, scope looks right"
aisef reject prd --note "missing soft-delete requirement; add an FR for the trash bin"
```

Then continue:

```bash
aisef plan
```

`plan` always **resumes from where it left off** — it won't redo a phase that
already has its document. To force a redo, add `--force`.

What to look for at each gate:

- **`prd`** — does the `FR-…` list match what you want? Anything extra? This
  is the cheapest place to cut scope.
- **`architecture`** — technology and module boundaries. Get this wrong and
  every story will be wrong.
- **`ux-spec`** — `EXPERIENCE.md` lists **screens**; the number of screens
  drives mockup cost.
- **`epics`** — epic and story breakdown; read to see the execution order.
- **`stories`** — `stories.index.json` is the machine-readable format: each
  story has acceptance criteria, `covers` (which requirements it covers),
  `write_scope` (directories it may write to), `depends_on`. Machine gates
  have already checked: no dependency cycles, every `FR` has a covering story,
  no story exceeds the size threshold, **no story has zero acceptance criteria**
  (zero is an error, not a small story — `criteria have tests` would have nothing
  to look for), no criterion describes a placeholder ("returns not implemented"),
  and no `write_scope` entry points outside the project.

  Read the **warnings** here too, not just the errors. The most useful one is new
  in 1.6.0: two stories in one epic declaring exactly the same write scope. It is
  a warning rather than a block, because splitting one file across two stories is
  sometimes right — but on a full six-epic run, 4 of 13 stories died because their
  criteria had already been delivered by an earlier story, more than every other
  cause combined. The shape to distrust is "implement command X" followed by
  "error cases of command X" against the same file: any competent implementation
  of the first covers both, and the second then has no legal move, because its
  tests are green before its own code exists. Merging that pair here costs
  nothing; discovering it during `aisef run` costs two sessions per story.

Fast run without stopping at any gate (use only for experimentation):

```bash
aisef plan --auto-approve all
```

Auto-approvals are **always** marked `auto`, so you can later tell which
documents were never read by a human.

---

## 9. Mockup step (UI projects)

**If your project has no graphical surface — a CLI, a library, a service — say so
in the document rather than skipping this step.** `EXPERIENCE.md` must carry the
line:

```markdown
**Screens:** none — no graphical surface
```

The `ux` prompt asks a CLI, a library or a service for exactly that line. With it,
the mockup gate passes with a warning and writes an empty contract without needing
a browser. Without it, a command-line tool gets its commands mapped onto screens
and every story comes out carrying a browser, a mockup-map and an accessibility
contract for something with no DOM. A UI project that simply *forgot* its screen
table is still an error — which is why the document declares the absence instead of
the gate guessing from an empty list.

For everything else:

```bash
aisef mockup
```

Each screen in `EXPERIENCE.md` becomes an HTML file, gets screenshotted, and is
then distilled into `design-contract.json` — the **visual contract** that
frontend stories must match. The real cost is about $1.50–$2.30 per screen, so
for 20 screens, build in batches:

```bash
aisef mockup --only list-screen,editor-screen
aisef mockup --force --only list-screen      # rebuild one screen
```

Approve the two remaining gates:

```bash
aisef review mockups
aisef approve mockups
aisef approve readiness
```

`readiness` is the final checkpoint before code gets written — after it comes
real money and real code.

---

## 10. Reading story gates: six outcomes

When a story finishes, the framework prints a table. Six symbols, each with a
**different** meaning, and only two of them are blocking:

| Symbol | Name | Meaning | Blocks the story? |
|---|---|---|---|
| ✅ | PASSED | evidence exists, and it says the item passed | no |
| ✗ | FAILED | evidence exists, and it says the item failed | **yes** |
| ⚠ | UNRUNNABLE | couldn't run: missing tool or environment | **yes** |
| ○ | UNCONFIGURED | command not declared; **not configured ≠ passed** | doesn't block the story, but blocks at `pre-deploy` |
| ◇ | WAIVED | explicitly waived by a human, with a recorded reason | no |
| – | NOT_APPLICABLE | doesn't apply (e.g., story has no UI…) | no |

There are **sixteen** checks, and the table prints them in this order
(`python3 -c "from aisef.control.gate import qualification_table as q; print(list(q()))"`):

| Item | What it checks |
|---|---|
| `evidence matches candidate` | all test results were actually run against the code version being scored |
| `guard ran` | guards actually evaluated write operations during the session |
| `test` | the last test run passed, and it happened after the last file edit |
| `no baseline regression` | tests that were already green before remain green and still exist |
| `lint` | lint is clean |
| `write scope` | the story didn't write outside its `write_scope` |
| `mockup map` | the actual screen matches the visual contract |
| `real tests` | no test is an empty assertion |
| `criteria have tests` | each acceptance criterion has a test carrying its code |
| `coverage` | coverage is at or above `coverage.min`; ○ when the runner prints no number |
| `TDD` | the story's tests were red before the code that makes them green |
| `tests verify story` | that test **actually** verifies the part of the story just written, rather than just tagging an existing test with the criterion code |
| `<kind>` | **one row per verification kind the story declares** — you will see `e2e`, `accessibility`, `sit` … by name, not the literal word `<kind>` |
| `security` | the security review session found no high-severity issues |
| `review` | the independent review session has no blocking items |
| `preservation` | behavior from other stories wasn't broken by this story |

By kind: **8 deterministic, 6 structural, 1 security, and exactly 1 model
judgement** — `review`. Every check carries three qualification controls
(positive, negative, environment), so the table behind the gate is 16 × 3 = **48
cells**; a count of 48 somewhere is not a mistaken count of the checks.

The `tests verify story` item often confuses newcomers. It exists to
catch an easy cheat: tagging a criterion code onto a test that **was already
green** and claiming "the criterion has a test". The framework runs a
counterfactual (the "nop control"): if that test still passes without the story's
implementation, then it proves nothing, and the gate item is ✗ with the test name.

`TDD` is the weaker proxy for the same question, so since 1.6.0 a **passing nop
control satisfies `TDD`**, and the gate says which evidence proved it. When the nop
control could not answer — `⚠`, `–` or `○` — `TDD` stands alone again. Before that
fix a story could be blocked by the weaker of the two with no legal move left.

`criteria have tests` reads test **names**, and it reads them from every suite whose
output a parser recognises, not just the unit runner — a browser story whose
criteria can only live in e2e titles is fine. The requirement is unchanged: each
criterion needs a test bearing its code, green at this build. A red suite
contributes nothing, and neither does a failed test inside a green one.

### What the model review is, and is not

`review` is one of sixteen checks and the only one a model decides. Since 1.6.0 the
reviewer's own judgement is scored as a check would be — six closed classes against
the same three controls — by replaying recorded sessions with no model calls:

```bash
python3 -m aisef.control.reviewer_qual ~/projects/notes/_bmad-output
```

Over 145 recorded reviewer sessions on the four dogfood corpora:

| measure | value |
|---|---|
| false block | **10.5 %** (6 of 57 blocks) — a **floor**, not an estimate: it needs positive evidence of reversal |
| miss | **34–39 %** (27 of 70 passes) |
| undecided | 12.4 %, and never scored as a pass |
| identical tree, consecutive reviews | of 20 pairs, **11 reversed the verdict** |

Read that plainly: the review is not a safety net. It misses roughly a third of
defective candidates, and on the same tree twice it disagrees with itself more often
than not. What holds a story is the other fifteen checks — deterministic ones, run
against a frozen SHA. Treat a blocking review item as a lead worth reading, not as
proof, and treat a passing review as nothing at all.

Since 1.6.0 both review prompts also receive `proven`: the story's
criterion-tagged tests that are green at that exact candidate. That is not
absolution — a green test can sit over broken code, which is worth reporting — but a
blocking item contradicting one of them must now name the test and say why it does
not cover the case.

---

## 11. Implementation step: `aisef run`

```bash
aisef run
```

What happens for **each** story:

1. The framework creates a separate `git worktree` and a branch `story/<code>`.
2. It opens a **completely new** agent session (carrying no context from the
   previous story).
3. The agent writes a failing test first, then code to make it pass; guards
   block any attempt to write outside the allowed scope.
4. The framework **freezes** that code version (a specific SHA) and runs every
   check against exactly that version.
5. A separate **independent review** session reads the changes; a dedicated
   security review session runs too. Both are one check each out of sixteen, and
   the review's measured reliability is in
   [§10](#10-reading-story-gates-six-outcomes) — read it before you rely on it.
6. The story gate scores. If it passes, the branch merges into the main branch;
   if it fails, it retries up to `run.max_retries` times, each retry including
   the specific failure reason.

Four things about that loop that only show up once you run it:

- **A failed story keeps its branch** so the next attempt builds on the last one.
  If you amend the story's acceptance criteria — which is exactly what the
  plan-deadlock message asks for — the branch is now **dropped**, and `run.log`
  says so. The criteria are fingerprinted into evidence each run. Carrying old
  commits across a contract change once cost a whole attempt to discover and
  another to undo. `--verify-only` is exempt: it grades the candidate already there.
- **A session that ran out of turns is still graded** if it left committed work.
  Running out of turns is not the same as writing bad code; the gate decides that,
  and half-finished work still fails `test`, `criteria have tests`, the nop control
  and review. Only infrastructure statuses return early.
- **Two consecutive sessions that write nothing stop the story.** A session that
  ran clean and wrote nothing has decided, and re-opening it with identical context
  returns the same decision. A cut session breaks the streak, because that one had
  work in flight.
- **Two graded attempts failing `tests verify story` on the same criteria stop the
  story immediately**, as a plan deadlock that names the criteria. No test can be
  red at the branch point for behaviour already on the main branch, so there is no
  session to buy.

**Infrastructure failures have their own retry budget**, `run.infra_retries`. A
session lost to the client — a provider 502, a rate limit, a tool call the CLI
could not parse — scores nothing, so it is not a quality attempt; but the budget for
them used to be `max_retries + 1`, which meant tolerating a flaky client required
paying for more quality attempts too. The default `-1` keeps that old coupling, so
this only matters if you have measured your client's own failure rate: the C-1b
cohort lost **22–32 %** of sessions to unparsed tool calls on OpenCode/mycombo, and
a story there can spend everything on sessions that produced no verdict.

```json
{
  "run.infra_retries": 6
}
```

Set a number only with a measurement behind it. Raising it blindly makes things
worse in one specific way that was measured: before the no-op stop above, a story
raised to survive a 22–32 % cut rate spent six sessions on a verdict it already had
after two.

Run variations:

```bash
aisef run --epic EPIC-01        # only one epic
aisef run --sequential          # disable parallel runs (easier to read logs)
aisef run --force               # run even if the stories gate isn't approved (for testing only)
```

Check progress and cost at any time (this command is **free**):

```bash
aisef status
```

A project with no stories registered simply says
`No stories registered yet.` Real output from the `todo-cli` dogfood project:

```
Progress: 7/13 stories done (2 not started)
Active epics: EPIC-03, EPIC-04, EPIC-05, EPIC-06

  done        7
  failed      4

Cost: $0.00
Agent runs: ok 150 · infra 12 · max_turns 3

✗ 4 stories not passing:
    STORY-03-02      failed   deadlock due to plan: criteria AC-STORY-03-02-1, … are
      already satisfied at the branch point — their tests pass with the story's code
      absent, and a second session confirmed it. … fix the criteria or drop the story,
      then re-run.
    STORY-05-02      failed   sessions kept producing nothing to grade: the session
      wrote nothing (8 turns) — the tree is exactly as the session found it, so the
      gate has nothing to grade. Re-running it would return the verdict it already
      returned.
```

Note `Cost: $0.00`. That is not a free run — it is the provider reporting no price.
Across the four dogfood corpora the provider priced **0 %** of sessions in three of
them and 1 of 180 in the fourth. When the dollar column is empty, the question "what
did the money buy" is still answerable, in tokens, by `aisef cost`
([§15.2](#152-aisef-cost--what-the-spend-bought)). `Agent runs: ok … · infra … ·
max_turns …` is the line that actually tells you how the sessions ended.

Where the attempts went, in one table:

```bash
aisef status --attempts
```

```
Attempts: 72 across 11 stories
  gate                    30  (42%)
  no gate verdict         26  (36%)
  passed                   7  (10%)
  infra                    6  (8%)
  max_turns                3  (4%)
  blocked by:
    TDD                   16
    tests verify story    16
    review                16
    security              10
    criteria have tests    9
    lint                   6
    test                   6
    no baseline regression   5
    preservation           4
    write scope            2
    sit                    2
    coverage               1
  attempts per story: STORY-01-01 25 · STORY-03-02 13 · STORY-01-02 7 · …
```

Read the `no gate verdict` row first: those attempts were paid for and never
scored, which is a different problem from failing a check.

**When a story fails**, follow this order:

```bash
aisef evidence STORY-01-03           # history: which items ✗, why
aisef gate STORY-01-03 --replay      # re-score on recorded evidence, no model call
```

`gate` re-evaluates each recorded round with today's rules and diffs the result
against what was recorded, check by check — which is how a check silently drifting
from `passed` to `unconfigured` becomes visible. Real output:

```
STORY-01-01 attempt 1 · candidate fb4a7d4 · recorded: FAIL · now: FAIL
  check                            | recorded | now
  evidence matches candidate       |   ✅    | ✅
  guard ran                        |   –    | –
  test                             |   ✅    | ✅
  no baseline regression           |   ✅    | ✅
  lint                             |   ✅    | ✅
  write scope                      |   ✅    | ✅
  mockup map                       |   ✅    | ✅
  real tests                       |   ✅    | ✅
  criteria have tests              |   ✗    | ✗
  coverage                         |   ○    | ○
  TDD                              |   ✗    | ✗
  tests verify story               |   ✗    | ✗
  e2e                              |   ✅    | ✅
  accessibility                    |   ✗    | ✗
  security                         |   ✅    | ✅
  review                           |   ✅    | ✅
  preservation                     |   –    | –
  diff: none — kết cục từng mục giống bản ghi
```

(That last line is still Vietnamese in 1.6.0; it means "every item's outcome matches
the record". When a check *has* drifted it names the check instead:
`diff: evidence matches candidate`.)

`aisef replay <story>` is the same thing under its older, frozen name; `--all`
re-scores every story that has evidence. Note the two `<kind>` rows — `e2e` and
`accessibility` — appearing by name.

Then classify:

- **Failed due to test environment** (e.g., flaky end-to-end test under load):
  no need to pay for a new coding session — just re-verify the existing code:

  ```bash
  aisef run --verify-only --story STORY-01-03 --repeat 3
  ```

  `--repeat 3` runs each check three times; if results differ across runs, the
  gate records ⚠ "flaky" with the test name, instead of blaming the story.

- **Failed due to bad planning** (story lacks write access to a file it must
  edit, contradictory acceptance criteria, criteria another story already
  delivered): fix `_bmad-output/stories.index.json` and the story file, re-approve
  the `stories` gate, then run again. `aisef status` names this case explicitly as
  `deadlock due to plan` and lists the criteria. Amending the criteria drops the
  story's old branch, which is what you want.

- **Failed due to bad code**: let the framework retry, or run an improvement
  loop from [§14](#14-improvement-loops-and-post-release-changes).

To see what the agent is given:

```bash
aisef ctx --story STORY-01-03        # code map around the write scope
aisef skill --story STORY-01-03      # skills routed to this story
```

---

## 12. Brownfield projects (existing codebases)

Everything above assumes a **greenfield** project — an empty repo. If you are
bringing AISEF into an **existing codebase** (≥ 3 source files), the framework
detects this automatically and switches to **brownfield mode**.

### 12.1 Running the baseline scan

Before planning, run the baseline command to snapshot the current state of your
codebase:

```bash
aisef baseline
```

This command:

1. **Detects** that the project is brownfield (≥ 3 source files, config files,
   `package.json` / `pyproject.toml` / etc.)
2. **Scans** the codebase using a code graph provider (see below)
3. **Writes** `_bmad-output/baseline.md` — a structured summary of the current
   architecture, modules, dependencies, and technology stack

The baseline file is the foundation for all brownfield planning. Without it,
the framework treats the project as greenfield and will try to generate
everything from scratch.

### 12.2 Choosing a code graph provider

The framework supports pluggable code graph providers via the
`context.graph_provider` config key:

| Value | Provider | What it does |
|---|---|---|
| `"auto"` (default) | Picks the best available | Uses Graphify if installed, otherwise falls back to Basic |
| `"graphify"` | Graphify CLI | Full dependency graph, function-level impact analysis. Requires `graphify` on PATH (`uv tool install graphifyy`) |
| `"basic"` | Built-in regex | Parses Python/JS imports with regex. Always available, no extra install |

To set the provider:

```json
{
  "context.graph_provider": "auto"
}
```

To install Graphify (recommended for large codebases):

```bash
uv tool install graphifyy
graphify .                          # build the graph once
```

You can also specify the provider on the command line:

```bash
aisef baseline --provider graphify
```

### 12.3 Incremental graph updates

After each merge or significant change, update the graph incrementally instead
of rebuilding from scratch:

```bash
aisef baseline --incremental
```

This is fast and keeps the impact analysis accurate.

### 12.4 How brownfield changes the planning pipeline

Once `_bmad-output/baseline.md` exists, `aisef plan` automatically:

- **Switches intent** from `"create"` to `"update"` for artifacts that already exist
- **Injects brownfield context** into every planning prompt, including the
  baseline summary and these rules:
  - Preserve existing architecture, code, and behavior — only change what the
    change request requires
  - Code is ground truth; existing docs may be stale — record contradictions
  - Generate **delta** artifacts, not full regenerations
- **Skips** phases whose artifacts already exist (unless you pass `--force`)

You don't need to change your workflow — just run `aisef baseline` before
`aisef plan`, and the framework handles the rest.

### 12.5 Blast radius analysis

When implementing stories in a brownfield project, the framework adds
**blast radius analysis** to every story prompt. This means:

1. The code graph provider identifies all files/modules affected by the story's
   `write_scope`
2. This impact list is injected into the developer, reviewer, and security
   reviewer prompts
3. The agent is instructed to run regression tests on affected files and not
   modify anything outside `write_scope` unless necessary for compatibility

### 12.6 Post-release changes in brownfield projects

`aisef change` is brownfield-aware. When you change a requirement:

```bash
aisef change FR-3 "Slugs must preserve underscores"
```

In a brownfield project, the generated delta story automatically includes:
- A reference to the baseline for context
- A blast-radius analysis step
- Instructions to preserve existing behavior

### 12.7 Complete brownfield workflow (step by step)

```bash
# 1. Go into your existing project
cd ~/projects/my-existing-app

# 2. Make sure it's a git repo
git init   # skip if already a repo

# 3. Install AISEF and set up
pip install aisef
aisef setup
aisef compile

# 4. Write what you want to change (not the whole app — just the change)
cat > docs/requirements.md << 'EOF'
# Add dark mode support

The application already works. We need to add a dark mode toggle
that respects the user's OS preference and persists the choice.

## Functional requirements

- Add a dark/light mode toggle in the header.
- Default to the user's OS color scheme preference.
- Persist the user's choice in localStorage.
- All existing screens must render correctly in both themes.

## Constraints

- Must not break any existing functionality.
- Must not change the existing component API.
EOF

# 5. Run the baseline scan
aisef baseline

# 6. (Optional) Install Graphify for better impact analysis
uv tool install graphifyy
graphify .
aisef baseline --provider graphify

# 7. Configure your tools
# Edit .ai/config.json with your test/lint commands (see §6)

# 8. Plan — the framework detects brownfield and generates delta plans
aisef plan

# 9. Review and approve gates as usual (see §8)
aisef gates
aisef approve prd --note "delta scope looks right"
# ... approve each gate

# 10. Run implementation — stories include blast radius analysis
aisef run

# 11. After stories merge, update the graph incrementally
aisef baseline --incremental
```

---

## 13. Verification, packaging, and acceptance

```bash
aisef qa
```

Runs all declared verification types: `unit`, `sit`, `api-contract`, `e2e`,
`uat`, `perf`, `security`, `mutation`, `accessibility`, `migration`, `sbom`,
`image-scan`. Types without a declared command show ○ and are **not** counted
as passing; a declared command that matched **no tests** shows ⚠ with a reason
naming both possibilities, not ✗.

One caution about running a full `aisef qa` pass mid-project: it records evidence
for kinds a given story does not declare, at whatever build is current. Before 1.6.0
those records sat at that SHA permanently and made `evidence matches candidate`
block every later story of the project. Only checks the gate actually scores for a
story can make its evidence stale now — but if you are on an older version, this is
the symptom.

```bash
aisef qa --only unit,e2e             # run selected types
aisef qa --story STORY-01-03         # record evidence for one story
```

Generate operational artifacts:

```bash
aisef devsecops
```

Generates CI pipeline, `Dockerfile`, deployment configuration, and
`docs/RUNBOOK.md`. The runbook must contain four sections: symptoms, diagnosis,
remediation, escalation — missing any section causes the final gate to block.

Final gate:

```bash
aisef pre-deploy
```

It checks: all stories done, all human gates approved, verification suite
passing, whether verification ran inside Docker, `Dockerfile` exists, CI exists,
runbook exists.

Accepting **part of** the project (e.g., only the first epic):

```bash
aisef pre-deploy --epic EPIC-01
```

Stories outside the declared scope are listed as "outside acceptance scope" —
**neither done nor missing**. This isn't relaxing the gate; it forces you to
state exactly what you're accepting. The scope is recorded in the report and the
approval is tied to it.

```bash
aisef approve pre-deploy --note "accepting EPIC-01 per report dated …"
aisef report
```

`aisef report` generates `docs/ACCEPTANCE-REPORT.md`: a traceability table
from requirements → stories → test coverage, a gate table, costs, and the
behavior ledger.

Look up a specific item:

```bash
aisef evidence FR-3                  # lifecycle of one requirement
aisef evidence AC-STORY-01-02-1      # one acceptance criterion
aisef evidence qa:e2e                # one verification type
aisef issues --format csv            # gap/regression table as a file
```

---

## 14. Improvement loops and post-release changes

**Improvement loops** progressively close the gaps (GAP) recorded in the
behavior ledger:

```bash
aisef improve --epic EPIC-01 --max-loops 3
```

Each loop: run verification → read the behavior ledger → generate **one** fix
story for **one** behavior currently at GAP → run that story like any regular
story → re-run verification → write `LOOP-REPORT-<n>.md`. The loop stops by
code when: no gaps remain, the maximum number of loops is reached, two
consecutive loops show no improvement, the cost ceiling is exceeded, or the fix
story is stuck because of planning.

Before each loop from the second onward, the framework pauses and asks you
(`aisef approve improve`); add `--auto` to skip the pause.

### Which kind of absence a GAP is

New in 1.6.0: a non-green behaviour now says **which** absence it is, and the three
kinds get three different repairs. This matters because only one of them is worth a
paid agent session.

| `gap_kind` | Means | What closes it |
|---|---|---|
| `unbuilt` | nothing landed proves the behaviour: a red test, a green test on an unlanded candidate, a red project check | a repair story — the expensive one |
| `untested` | the run was readable and no test name carries this code | a **test-only** story: the write scope *is* the verification paths, and the scope guard enforces that. Write the tagged test and stop |
| `untraced` | the harness cannot link behaviour → test (the runner printed no test names, or a declared trace is absent from this run) | a metadata edit, **never** a story |

`improve` keeps `untraced` out of the paid queue entirely, and when the queue empties
it names them separately with the fix, so you never read "no gaps left" over a
metadata problem:

```
no gap with specific verifier remaining in epic — 5 gap(s) only missing traceability
— harness metadata fix, not a repair story: AC-STORY-02-02-1, AC-STORY-02-02-2,
AC-STORY-02-02-3, AC-STORY-02-02-4, AC-STORY-02-02-5 [cannot read test names from
runner output: tool not installed or cannot load (not found) — set up the environment
or fix the command and retry] (`aisef evidence AC-STORY-02-02-1 --link "<test id>"
--why "…"`, or make the runner print test names)
```

That output is from a real corpus, and it is the whole point of the feature: all five
were the criteria of **one** story whose test reporter was not installed. Without the
distinction, `improve` would have opened five paid repair stories for a missing
plugin.

Nothing is hand-written for this — `gap_kind` is projected from the reason sentence
the ledger already wrote, so `ledger.json` gains no new editable field. Unknown
reasons default to `unbuilt` on purpose: mislabelling a real defect as a cheap
harness fix would hide it, while the reverse only wastes money.

`aisef issues` prints the counts in its header and adds a `gap_kind` column
(appended last, so a tracker importing the CSV by position keeps working):

```bash
aisef issues --format md
```

```
# Gap / regression · 27 behaviours · unbuilt 23 · untested 4 · untraced 0
```

**Do not print those three numbers beside `gap` alone.** They classify every
non-green behaviour, so they sum to `gap + reopened`. One corpus on disk has 1 gap
and 8 reopened, and "1 gap · unbuilt 9" is a false line.

**Changing requirements after release**:

```bash
aisef change FR-3 "Slugs must preserve underscores"
```

This command records the change in `docs/requirements.md`, marks the `prd` gate
and all downstream gates as `stale`, and generates a delta story
(`STORY-CH-01`) covering exactly `FR-3`. The original story **keeps** its
`DONE` status — history is not rewritten.

---

## 15. Real costs and how to reduce them

### 15.1 What a run costs, when the provider prices it

Real measurements on a notes project (Claude Code client). Read them as orders of
magnitude, not as a quote: that corpus is no longer on this machine, so the numbers
cannot be re-derived, and nothing here is a per-story prediction for your project.

| Task | Cost |
|---|---|
| `project-context` | ~$1.50 |
| `prd` | ~$1.90 |
| `architecture` | ~$2.80 |
| `ux` | ~$3.70 |
| `epics` (18 stories) | ~$4.50 |
| mockup, per screen | $1.50–$2.30 |
| backend story, per attempt | $2.00–$2.70 |

Two things worth remembering: planning costs about $14 **before a single line
of code**, and mockups are more expensive than they feel because each screen
re-reads the entire design document set.

**Many providers report no price at all**, and that is the common case, not the
exception. On the four dogfood corpora on disk the provider priced 0 % of sessions in
three of them and 1 of 180 in the fourth, so `aisef status` prints `Cost: $0.00`,
`cost.warn_multiple` has no median to compare against and `improve.cost_cap_usd`
never engages. That does not make the spend unknowable — it makes the unit tokens
instead of dollars, which is what the next section is for.

### 15.2 `aisef cost` — what the spend bought

```bash
aisef cost
```

New in 1.6.0. It joins the two records nothing had joined before: which behaviours
hold (the ledger) and what a run consumed (the budget). It records nothing of its
own — every number is recomputed from `evidence/*.jsonl` — so running it is free and
repeatable. `--out FILE` also writes the Markdown.

The interesting part is what it **refuses** to do. It reads its unit off the
evidence:

```
# Spend attribution — `todo`

Unit: **input tokens** — the provider priced 1% of 180 sessions (0.79 USD recorded
in total), so dollars here would be invented. With `p` = price per 1M input tokens
and `q` = per 1M output:

    cost ≈ 85.15 × p + 0.500 × q

Cache reads are 46% of prompt tokens (73,140,237 cached vs 85,146,657 fresh); most
price lists charge them far less, so they are counted separately.
```

`cost_usd` is a unit only at **full** coverage. A partial dollar record is worse than
an empty one: averaged over a corpus it is wrong by two orders of magnitude rather
than merely missing. So you get the price formula and your own price list, never a
fabricated dollar. It refuses in a second direction too — a corpus whose client does
not report cached tokens bills every re-sent prompt as fresh `input`, so its totals
are a sum over turns of the whole context and are not comparable with a caching
corpus. The report says so on the corpus where it is true:

```
⚠ At 4% cache, this client bills re-sent context as fresh `input`: the totals below
are a sum over turns of the whole prompt and are **not** comparable with a corpus
that caches.
```

Then the answer, per corpus, with causes named rather than bucketed:

```
Net VERIFIED per M input tokens: **0.16**

44 verified · 3 gap · 0 reopened → net **44** behaviours for 267,031,421 across 97
sessions (3,185 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 21 | 668 | 58,192,453 | 22% |
| gate-blocked | 51 | 1,472 | 122,063,305 | 46% |
| turn-cap | 13 | 920 | 86,300,591 | 32% |
| env-failed | 2 | 63 | 164,723 | 0% |
| planning | 10 | 62 | 310,349 | 0% |

Spend on stories that ended with a net VERIFIED behaviour: **100%**.
```

A session's own exit outranks the gate verdict that follows it, deliberately: a
session the turn cap killed never reached the gate on its merits, and charging its
tokens to "the gate blocked this" would hide the cap. Below that come a per-story
table and a `What the gate blocked on` table counting blocks per check — which is
where you find out that `review` was 39 of the blocks in one corpus.

The headline across all four corpora: only **4–22 % of spend bought an attempt the
gate passed** (`passed` share: 4 %, 16 %, 20 %, 22 %). 78–96 % went to sessions no
gate ever passed, and the named causes are gate-blocked rework (32–67 %), turn-cap
exhaustion (52 % of one corpus, in 3 sessions of 165) and environment failures (37 %
in one corpus against 2 % in another). The `Spend on stories that ended with a net
VERIFIED behaviour` line reads 14 %, 16 % and 25 % on three corpora and 100 % on the
fourth.

What is **not** a cost driver: review and security **retry** rounds, which are under
0.15 % of spend everywhere. Worth knowing before economising there:

```bash
python3 -c "
from pathlib import Path
from aisef.control.attribution import build
a = build(Path.home()/'projects/notes/_bmad-output')
tot = a.total().amount(a.unit)
print({r: round(100*s.amount(a.unit)/tot, 3) for r, s in sorted(a.by_role.items())})"
```

```
{'?': 2.585, 'developer': 83.31, 'review': 11.226, 'review-retry': 0.043, 'security': 2.835}
```

Two readings this command does not support. The unit is per corpus and is never
averaged across kinds, so do not add two corpora together. And the per-story `net`
column can be negative: a story that reopened more behaviours than it verified cost
money and left the project worse, which is the number to look for first.

### 15.3 Ways to reduce cost

- Run **one epic** first before running them all; your project's numbers can't
  be derived from the table above.
- Build mockups in batches with `--only`, and approve early.
- Cut scope at the `prd` gate, not while stories are running.
- Set a ceiling for improvement loops: `improve.cost_cap_usd` — and note it reads
  cost from evidence, so it does nothing on a provider that prices nothing.
- If a story fails due to the environment, use `--verify-only` instead of
  re-running the whole story.
- **Fix the plan before paying for retries.** Measured across a full six-epic run,
  the single largest cause of dead stories was criteria an earlier story had already
  delivered — more than every other cause combined. Reading the `stories` gate's
  same-write-scope warning costs nothing.
- **Watch the turn cap.** One corpus spent 52 % of its tokens in 3 sessions of 165
  that hit `run.max_turns`. `aisef status --attempts` tells you how many attempts end
  that way; raising the cap is sometimes right, but a session that spends forty turns
  reading the harness's own evidence files is a prompt problem, not a budget one.

---

## 16. Troubleshooting

| You see | It means | What to do |
|---|---|---|
| `✗ claude is not installed on this machine`, exit code 2 | no agent client on the machine | install the client, run `claude --version` until it works |
| `✗ no docs/requirements.md` | no input file | create the file per [§4](#4-creating-a-project-and-writing-the-input) |
| `aisef gates` shows `stale` | document changed after approval, or an upstream gate was just re-approved | re-read, then `aisef approve <gate>` |
| `stories` gate won't let you run | a machine gate caught a planning error | read the reason, fix `stories.index.json`, re-approve |
| Gate item ○ `coverage` | test command doesn't print coverage numbers | add `--coverage` (vitest/c8) or `--cov` (pytest) to `tools.test` |
| Gate item ○ `criteria have tests` | runner doesn't print test names | add `--reporter=verbose` (vitest) or `-v` (pytest) |
| Gate item ✗ `tests verify story` | test only tagged a code onto an existing test | have the story write a new test for the criterion; if the existing test genuinely proves enough, declare the trace: `aisef evidence <code> --link "<test name>" --why "…"` |
| Gate item ✗ `TDD`, while the nop control passed | you are before 1.6.0 | upgrade: a passing nop control now satisfies `TDD`, and the gate says which evidence proved it |
| `aisef guard tool-bypass: … is the project's test command run directly` | the agent ran your declared command instead of `aisef tool test`; nothing was recorded | this is the guard working. Use `aisef tool test`. To narrow a run for debugging, change the command's own identity (`pytest tests/x.py -k foo`); with `npm`/`yarn`/`pnpm`/`bun` the script name *is* the identity, so call the underlying runner |
| Story `failed`, reason `deadlock due to plan` | the story's criteria are already satisfied at its branch point — usually an earlier story shipped the behaviour | fix or drop the criteria named in the message, then re-run. Amending them drops the stale branch automatically |
| Story `failed`, reason `sessions kept producing nothing to grade` | the session ran clean and wrote nothing — a decision, not a fault | do not re-run it; read the last graded verdict. Two consecutive no-op sessions stop the story on purpose |
| Attempts ending at `max_turns` | `run.max_turns` (default 40) reached | the session is still graded if it committed work. Check `aisef status --attempts`; if the agent was reading `_bmad-output/` to work out gate rules, raising the cap does not help |
| `Cost: $0.00` on a real run | the provider reported no price, not a free run | use `aisef cost` ([§15.2](#152-aisef-cost--what-the-spend-bought)); it switches to input tokens and hands you the price formula |
| Every story of the project fails `evidence matches candidate` | before 1.6.0, one full `aisef qa` pass could leave kinds the story never re-runs pinned at an old SHA | upgrade; only checks the gate scores for a story can make its evidence stale now |
| OpenCode sessions authenticate against the wrong account, or cannot authenticate | since 1.5.0 `ANTHROPIC_*` goes only to `claude` | if that is deliberate, declare `"clients.env_allow": ["ANTHROPIC_"]` |
| Gate item ⚠ with "unrunnable" | missing tool or environment | set up the environment, then re-run; **don't** lower the threshold to get past it |
| Verification reports "degraded" | running outside Docker, missing some guarantees | set up Docker; or declare `sandbox.pre_deploy_degraded_waiver` with a real reason |
| `Port ... is already in use` during e2e | an old dev process is still alive | find and kill it (`lsof -nP -i :5199`), then re-run |
| Story `blocked` after multiple attempts | usually bad planning, not bad code | read `aisef evidence <story>`, fix the story/write scope, re-approve the `stories` gate |
| Merge conflict at end of batch | two stories declared overlapping `write_scope` | this signals a planning problem — split the scopes, then re-run |
| Abnormally high cost for one story | story too large for one session | split the story; the size threshold is `story.max_complexity` |

Exit codes for all commands: `0` success, `1` bad arguments or missing input,
`2` not ready (gate not met, missing tool). One deliberate exception: `aisef guard`
exits `2` on a usage error too, because in the hook protocol any code other than 2
means "not blocked" — a mistyped guard name must block, not silently pass.

---

## 17. Reference: all commands

`aisef --help` lists 34 verbs. The 33 below are the ones a project uses; the
34th, `aisef closure`, scores the framework repository's own project-closure
gate and is documented in `docs/SOLUTION.md` and `docs/PROJECT-CLOSURE-GATE.md`,
not here. Every verb accepts `--project <directory>` (default: current
directory), **before or after** the verb.

**Preparation**

```bash
aisef doctor                              # check the environment
aisef setup [--references DIR] [--no-fetch] [--dry-run]
aisef init [--stack react|python|go|node]  # write .ai/config.json (4 keys)
aisef compile [--client claude|opencode|all] [--bin PATH]
aisef baseline [--provider auto|graphify|basic] [--incremental] [--force]
```

**Planning and human gates**

```bash
aisef plan [--client c] [--auto-approve all|<list>] [--force]
aisef mockup [--client c] [--only <screen_id>] [--auto-approve all|<list>] [--force]
aisef gates
aisef review <gate> [--lines N]
aisef approve <gate> [--note "..."] [--force]
aisef reject <gate> --note "..."
aisef auto-approve all|<list>
```

**Implementation**

```bash
aisef run [--client c] [--epic E] [--sequential] [--no-isolate] [--force]
aisef run --verify-only --story S [--repeat K]
aisef improve --epic E [--max-loops N] [--auto] [--client c] [--force]
aisef tool test|lint|sast [--story S] [--lines N]
aisef verify [--write-scope ...] [--story S]
aisef gate <story> --replay [--attempt n]   # or: aisef gate --replay --all
aisef replay <story> [--attempt n] | --all  # same thing, the frozen v0.5.0 name
aisef guard <guard-name>                    # called by the framework via hooks
```

`aisef gate` currently requires `--replay`; without it it says so and exits.
`aisef guard` accepts these ten names: `completion`, `destructive`, `diff-scope`,
`egress`, `git-stage`, `injection`, `process-ref`, `secret`, `tool-bypass`,
`write-scope` — and reads the hook event on stdin.

**Verification and release**

```bash
aisef qa [--only <type>] [--story S] [--story-level]
aisef devsecops [--client c] [--install-spec X] [--bin PATH] [--force]
aisef pre-deploy [--skip-qa] [--epic E]
```

**Observation**

```bash
aisef status [--attempts]                 # --attempts: where attempts ended, by check
aisef cost [--out FILE]                   # what the spend bought (§15.2)
aisef report [--out FILE]
aisef evidence <id> [--story S] [--link TEST --why "..." --by NAME]
aisef issues [--format md|csv] [--epic E] [--status gap,reopened,verified] [--out FILE]
aisef ctx [--story S | --file F] [--budget N]
aisef skill [--story S] [--scan --client c --batch N]
aisef doc <package> [--topic T] [--tokens N] [--story S]
aisef change FR-x "description"
aisef dashboard [--out FILE] [--projects DIR ...]   # HTML dashboard; --projects merges
```

**Frozen / experimental**

```bash
aisef memory status|recall|search|show|capture|consolidate|audit|forget|providers \
  [--story S] [--role developer|reviewer|security|designer] [--tool T] [--json]
```

Scoped advisory memory is **frozen and off by default** — not "experimental, coming
soon". The code stays and keeps its bug and security fixes; no new capability is
added, and it is never gate evidence. Full documentation in
[MEMORY.md](MEMORY.md).

`docs/STABILITY.md` freezes 14 of the 34 verbs as a contract (`doctor`, `setup`,
`init`, `compile`, `run`, `status`, `dashboard`, `guard`, `gate`, `replay`, `skill`,
`doc`, `change`, `baseline`). The contract permits adding subcommands, so the other
20 are not frozen — but they are real, and this section is the list.

---

## 18. Reference: all configuration keys

There are **70** keys, and the number is guarded by a test (`tests/test_meta.py`, against `docs/STABILITY.md`):

```bash
python3 -c "from aisef.config import DEFAULTS; print(len(DEFAULTS))"    # → 70
```

Every key is part of the frozen contract: keys may be added, never removed or
renamed. What you write in `.ai/config.json` is merged over the defaults, so the file
should carry only what your project actually decided — that is why `aisef init` writes
four keys and not sixty-nine. A **retired** key still loads: it warns, naming the
measurement that retired it, and is ignored. Two are retired today,
`skills.inline` (1.4.0) and `story.max_context_tokens`.

Values shown are the defaults.

**Verification and thresholds**

| Key | Default | Meaning |
|---|---|---|
| `tools.test` · `tools.lint` · `tools.sast` | `""` | project's real commands; empty means not configured |
| `verify.<type>` (12 types) | `""` | command for each verification type |
| `verify.waived` | `""` | waived types, comma-separated |
| `verify.waiver_reason` | `""` | reason for waivers; required when any type is waived |
| `verify.baseline` | `true` | run tests at the baseline commit before the story edits, to know which tests were already green |
| `verify.nop` | `true` | enable the `tests verify story` counterfactual (the nop control) |
| `verify.clean_tree` | `true` | project-level verification runs in a clean worktree built from the SHA |
| `coverage.min` | `0.85` | coverage threshold |
| `security.block_severities` | `["critical","high"]` | security finding severities that block |
| `security.semantic_review` | `true` | enable a dedicated security review session |

**Story sizing**

| Key | Default | Meaning |
|---|---|---|
| `story.max_acceptance_criteria` | `8` | maximum acceptance criteria per story |
| `story.max_write_scope_paths` | `10` | maximum paths in write scope |
| `story.max_screen_states` | `8` | maximum screen states |
| `story.max_complexity` | `16.0` | maximum complexity score; exceeding it blocks the gate and demands splitting |
| `story.verified_touched_weight` | `0.0` | how much a neighbouring VERIFIED behaviour adds to a story's complexity. **Calibrated and deliberately left at 0**: on the corpora measured, no weight ≤ 1.0 changes a single verdict, and the first verdict any larger weight changes is a *false* block. Catching 11 of 15 real regressors costs blocking 7 of 17 clean stories. Raise it only with your own table |

**Execution**

| Key | Default | Meaning |
|---|---|---|
| `run.max_parallel` | `3` | stories running in parallel |
| `run.max_turns` | `40` | maximum turns in one agent session. Enforced on OpenCode since 1.4.0 by the adapter counting turns itself |
| `run.timeout_seconds` | `1800` | maximum time for one session |
| `run.max_retries` | `2` | quality retries for one story |
| `run.infra_retries` | `-1` | separate budget for sessions lost to the client (provider 502, rate limit, unparsable tool call). They score nothing, so they are not quality attempts. `-1` keeps the old coupling to `max_retries + 1`; raise it only with a measured client failure rate — see [§11](#11-implementation-step-aisef-run) |
| `run.cost_cap_usd` · `run.turn_cap` · `run.wall_clock_cap_seconds` | `0.0` · `0` · `0.0` | in-flight budget caps checked before every paid call; `0` disables. Warns at 80 % of a declared cap, once per dimension. The cost cap does nothing on a provider that reports no price |
| `run.qualify_preflight` | `false` | opt-in: run the unified qualification policy before the first attempt |
| `cost.warn_multiple` | `3.0` | warn when one story costs more than this multiple of the median |

**Application and mockups**

| Key | Default | Meaning |
|---|---|---|
| `app.dev_command` | `""` | command to start the app for screen comparison |
| `app.base_url` | `http://localhost:5173` | app URL |
| `app.ready_timeout_seconds` | `60` | how long to wait for the app to be ready |

**Sandboxing**

| Key | Default | Meaning |
|---|---|---|
| `sandbox.provider` | `"docker"` | where to run commands: `docker` or `local` |
| `sandbox.use_docker` | `true` | use a container for tools |
| `sandbox.allow_degraded` | `true` | allow running when some guarantees are missing, with explicit logging |
| `sandbox.image` | `""` | container image |
| `sandbox.tools_network` | `false` | allow tools network access |
| `sandbox.allow_hosts` | `[]` | hosts tools may reach; also what the `egress` guard allows. `localhost` is exempt by all its names, IPv6 included — nothing leaves the machine |
| `sandbox.pre_deploy_degraded_waiver` | `""` | reason for accepting verification outside Docker at the final gate |

The Docker provider passes 5 of 5 isolation guarantees; the local provider passes 2
of 5 and reports the other three as `unsupported` rather than pretending. Every local
run exposes the host's credentials to the agent. That is a closed decision, not a
pending fix — the honest report *is* the feature.

**Context, improvement loops, and clients**

| Key | Default | Meaning |
|---|---|---|
| `context.max_index_chars` | `2000` | character limit for the evidence index loaded into the prompt |
| `context.max_preservation_chars` | `1200` | character limit for the behavior preservation list |
| `context.max_repo_map_chars` | `0` | limit for the code map; `0` disables it |
| `context.map_provider` | `""` | external command rendering the code map (tree-sitter, serena…): stdin JSON → stdout text. Empty uses the built-in; a broken command falls back to the built-in and the prompt slot says it is coarse |
| `context.graph_provider` | `"auto"` | code graph provider for brownfield: `auto`, `graphify`, or `basic` |
| `review.impact_provider` | `""` | external command for the reviewers' impact analysis; same fall-back rule as above |
| `improve.max_loops` | `3` | maximum improvement loops per epic |
| `improve.flat_loops` | `2` | stop when this many consecutive loops show no improvement |
| `improve.cost_cap_usd` | `0.0` | cost ceiling for improvement loops; `0` means unlimited. Read from evidence, so inert on a provider that reports no price |
| `route.developer_model` · `route.reviewer_model` · `route.security_model` · `route.designer_model` | `""` | force a specific model for each of the four roles |
| `clients.env_allow` | `[]` | environment variable **prefixes** allowed into agent sessions, on top of each adapter's own (`claude`: `ANTHROPIC_`; `opencode`: nothing) and the shared `LC_`, `AISEF_` |
| `skills.offer` | `false` | suggest skills to the agent; A/B measured no gain, so off. The second mechanism, `skills.inline`, was **retired in 1.4.0** after two A/B runs reported `used` 0/0 in both branches |
| `memory.*` (6 keys) | off | scoped advisory memory, frozen and off by default — [MEMORY.md](MEMORY.md) |

---

## 19. Glossary

- **Story** — a unit of work with its own acceptance criteria, write scope, and
  dependencies. Each story runs in a new agent session.
- **Epic** — a group of stories. Epics run sequentially; stories within an epic
  run in parallel when their write scopes don't overlap.
- **Acceptance criteria (AC)** — statements describing the conditions for a story
  to pass, coded as `AC-<story>-<number>` and required to appear in test names.
- **Candidate** ("ung vien") — a specific code version (a SHA) against which all
  checks run. Evidence not tied to a candidate proves nothing about any specific
  version.
- **Machine gate / human gate** ("cong may" / "cong nguoi") — see
  [§1](#1-what-this-framework-does).
- **Behavior ledger** ("so hanh vi") — a table tracking each behavior:
  `VERIFIED` (proven), `GAP` (not yet), `REOPENED` (was proven, now broken
  again). It is a **projection**: every consumer rebuilds it from evidence, so
  `ledger.json` on disk is a convenience, not the truth.
- **`gap_kind`** — which *absence* a non-green behavior is: `unbuilt` (nothing
  landed proves it), `untested` (no test name carries the code), `untraced` (the
  harness cannot link behavior to test). Only `unbuilt` is worth a paid repair
  story. See [§14](#14-improvement-loops-and-post-release-changes).
- **Nop control** — the counterfactual behind `tests verify story`: run the story's
  tests at the parent SHA, with the story's code absent. A test still green there
  proves nothing about the story.
- **Evidence** ("bang chung") — `.jsonl` files recording every tool run, agent
  session, and gate conclusion. This is what all reports read — not the agent's
  words.
- **Guard** — a framework command that blocks an incorrect operation just before
  it happens.
- **Degraded** ("suy bien") — runs but lacks some isolation guarantees; always
  lists which guarantees are missing, never silently.
- **Explicit waiver** ("mien tuong minh") — a human accepts responsibility for a
  verification type not being run, with a reason recorded in evidence. Shows ◇,
  never becomes ✅.
- **Worktree** — a separate working tree for one story, so two stories running
  in parallel don't step on each other.
- **Brownfield** — an existing codebase (≥ 3 source files). The framework
  detects this and switches to delta mode: preserve existing architecture,
  generate only what the change request requires.
- **Greenfield** — a new project with no existing code. The default mode.
- **Baseline** — a snapshot of the current codebase state, written to
  `_bmad-output/baseline.md` by `aisef baseline`. Required for brownfield
  planning.
- **Blast radius** — the set of files/modules affected by a story's
  `write_scope`, determined by the code graph provider's impact analysis.
- **Code graph provider** — a pluggable module that builds a dependency graph
  of the codebase. Used for impact analysis and blast radius. Two
  implementations: Graphify (CLI, full graph) and Basic (regex imports,
  always available).

---

Related documents in the repository: `README.md` (summary, English) and `README.vi.md` (Vietnamese version), `docs/SOLUTION.md` (full
design), `docs/FAILURE-TAXONOMY.md` (real failures encountered and how to prevent recurrence),
`CHANGELOG.md` (changes between versions and what to do when upgrading).
