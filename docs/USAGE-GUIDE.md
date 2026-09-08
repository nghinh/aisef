# AISEF Usage Guide

**AISEF** stands for **AI Software Engineering Framework**. The installable
package, Python module, and CLI command are all named `aisef`.

This guide is written for someone who has **never used** the framework, and
tries not to skip a single step. Each section tells you: what to type, how long
to wait, what to expect on screen, and what to do when it doesn't look right.

Reading conventions:

- `bash` blocks are commands to type in the terminal. Run one block at a time, read the output, then move on.
- The symbols `✅ ○ ⚠ ✗ –` are the **six gate outcomes** of the framework, not decoration. Their meaning is in [§10](#10-reading-story-gates-six-outcomes).
- Where it says "wait a few minutes", an agent session is running and **costs money**; real costs are in [§14](#14-real-costs-and-how-to-reduce-them).

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
12. [Verification, packaging, and acceptance](#12-verification-packaging-and-acceptance)
13. [Improvement loops and post-release changes](#13-improvement-loops-and-post-release-changes)
14. [Real costs and how to reduce them](#14-real-costs-and-how-to-reduce-them)
15. [Troubleshooting](#15-troubleshooting)
16. [Reference: all commands](#16-reference-all-commands)
17. [Reference: all configuration keys](#17-reference-all-configuration-keys)
18. [Glossary](#18-glossary)

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
| An agent client: `claude` (recommended) or `opencode` | **yes, to run agents** | `claude --version` | agent commands exit with code 2 and the message "claude is not installed on this machine" |
| Docker | no | `docker info` | tests run directly on the host; the framework records this as **degraded** with the name of each missing guarantee |
| Playwright + Chromium | no, unless the project has a UI | `npx playwright --version` | can't extract a visual contract from mockups |

Install the Claude Code client following Anthropic's instructions, then log in once:

```bash
claude --version
```

If this command doesn't work yet, every agent step below will fail — finish
this part first.

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

You should see a list of subcommands (`setup`, `doctor`, `plan`, `run`, …).
The package, Python module, and CLI command are all named `aisef`. There is no
`--version` flag; to inspect the environment, use `aisef doctor`.

If you previously installed version 0.1.0 (when the command was called
`aisdlc`): the old alias was removed in 0.3.0. Run `aisef compile` in each
project to point hooks to the new name.

The framework has **no Python dependencies** beyond the standard library.

For contributors who want to modify the framework:

```bash
git clone <repo> aisef && cd aisef && pip install -e .
python3 -m unittest discover -s tests -q
```

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
to `~/.cache/aisef/references` (about 93 MB, shared across all projects). If
the machine has no network:

```bash
aisef setup --no-fetch          # use only what's already on disk
AISEF_REFERENCES=/path/to/repo aisef setup   # point to a pre-downloaded copy
```

To preview without writing anything:

```bash
aisef setup --dry-run
```

When it finishes you'll see a summary line like
`installed 152 · kept 0 · removed 0`, a line `rules: CLAUDE.md, AGENTS.md`, and
the path to the `.ai/config.json` it just wrote. Running `aisef setup` again
does **not** duplicate skills.

Important: `.ai/config.json` is generated with **every command left blank**
(`tools.test`, `tools.lint`, `verify.*`). The framework deliberately does not
guess your test command — "not configured" must be visible, not silently treated
as "passed". The next step is to fill them in.

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

And for a Python project:

```json
{
  "tools.test": "python -m pytest -v --cov=src --cov-report=term",
  "tools.lint": "ruff check .",
  "verify.unit": "python -m pytest -v",
  "coverage.min": 0.85
}
```

Three things worth knowing right away:

- **The test command must print individual test names.** The "criteria has test"
  gate reads test names to determine which acceptance criteria have been
  demonstrated. Vitest needs `--reporter=verbose`, pytest needs `-v`. Without
  test names in the output, the gate item is ○, not ✅.
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

All keys are listed in [§17](#17-reference-all-configuration-keys).

---

## 7. `aisef compile` and `aisef doctor`

```bash
aisef compile
```

Generates hooks/plugins for the client, connecting the framework's **eight
guards** to the agent session. Guards run on the framework side, not the client
side — the client is not trusted.

| When | Guard | What it blocks |
|---|---|---|
| before each agent tool use | `write-scope` | writes outside the story's allowed scope |
| | `destructive` | destructive commands (`rm -rf`, `git push`, changing remotes…) |
| | `secret` | writing API keys, tokens, or private keys into files |
| | `git-stage` | unauthorized staging/committing outside the workflow |
| | `injection` | content containing prompt-injection attempts targeting the agent |
| | `process-ref` | writing story/epic codes into source code |
| after each tool use | `diff-scope` | actual changes exceeding the allowed scope |
| when the agent is about to stop | `completion` | stopping when tests aren't green after the last edit |

At the end it prints a capability report, for example:

```
  capabilities not at native level:
     dir_allowlist: unsupported
     tool_allowlist: emulated
     turn_limit: unsupported
```

This is **not an error**. It says: this client cannot natively restrict a few
things, so the framework records the exact guarantee level it achieves instead
of pretending. The main guards (blocking out-of-scope writes, blocking
destructive commands) still run.

Run `aisef compile` again whenever you upgrade the package.

```bash
aisef doctor
```

Read each line as follows:

- `✅` — present and sufficient.
- `○` — missing an **optional** item, with the install command shown. For example
  `○ playwright + chromium` only matters for projects with a UI.
- `✗` — missing a **required** item; the last line will say `✗ missing: …`.

The final line is the verdict: `✅ ready` or a list of what's still missing.

---

## 8. Planning step: `aisef plan`

```bash
aisef plan
```

This command runs **five consecutive phases**, each phase being an agent session
that stops at the next human gate:

| Phase | Produces | Gate waiting for your approval |
|---|---|---|
| `project-context` | `project-context.md` | (no gate) |
| `prd` | `prd.md` | `prd` |
| `architecture` | `architecture.md` | `architecture` |
| `ux` | `DESIGN.md`, `EXPERIENCE.md` | `ux-spec` |
| `epics` | `epics.md` | `epics` |
| `stories` | `stories.index.json` + one file per story | `stories` |

All files go into the `_bmad-output/` directory of the project.

When the command stops, check which gate is waiting:

```bash
aisef gates
```

The table shows eight gates. For example, in a freshly created project:

```
  ⏳ prd            pending              [missing: prd.md]
  ⏳ architecture   pending              [missing: architecture.md]
  ⏳ ux-spec        pending              [missing: DESIGN.md, EXPERIENCE.md]
  ⏳ epics          pending              [missing: epics.md]
  ⏳ stories        pending              [missing: stories.index.json]
  ⏳ mockups        pending              [missing: design-contract.json]
  ⏳ readiness      pending              [missing: stories.index.json, design-contract.json]
  ⏳ pre-deploy     pending              [missing: pre-deploy-report.json]

Next gate to address: prd
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
  no story exceeds the size threshold.

Fast run without stopping at any gate (use only for experimentation):

```bash
aisef plan --auto-approve all
```

Auto-approvals are **always** marked `auto`, so you can later tell which
documents were never read by a human.

---

## 9. Mockup step (UI projects)

Skip this section if your project has no UI.

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

The gate items you'll encounter most often:

| Item | What it checks |
|---|---|
| `evidence on correct candidate` | all test results were actually run against the code version being scored |
| `guard ran` | guards actually evaluated write operations during the session |
| `test` | the last test run passed, and it happened after the last file edit |
| `no existing tests broken` | tests that were already green before remain green and still exist |
| `lint` | lint is clean |
| `write scope` | the story didn't write outside its `write_scope` |
| `mockup match` | the actual screen matches the visual contract |
| `real tests` | no test is an empty assertion |
| `criteria has test` | each acceptance criterion has a test carrying its code |
| `test actually verifies story` | that test **actually** verifies the part of the story just written, rather than just tagging an existing test with the criterion code |
| `review` | the independent review session has no blocking items |
| `security` | the security review session found no high-severity issues |
| `preservation` | behavior from other stories wasn't broken by this story |

The `test actually verifies story` item often confuses newcomers. It exists to
catch an easy cheat: tagging a criterion code onto a test that **was already
green** and claiming "the criterion has a test". The framework runs a
counterfactual: if that test still passes without the story's implementation,
then it proves nothing, and the gate item is ✗ with the test name.

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
   security review session runs too.
6. The story gate scores. If it passes, the branch merges into the main branch;
   if it fails, it retries up to `run.max_retries` times, each retry including
   the specific failure reason.

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
`No stories registered yet.` A project in progress prints something like:

```
Progress: 10/12 stories done
Current epic: EPIC-RP-01

  done        10
  failed      2

Cost: $254.11
⚠️  1 story costs more than 3.0× the median:
    STORY-01-04      $79.67

✗ 2 stories didn't pass:
    STORY-RP-04      failed   still failing after 3 attempts
```

**When a story fails**, follow this order:

```bash
aisef evidence STORY-01-03           # history: which items ✗, why
aisef gate STORY-01-03               # re-score on recorded evidence, no model call
```

Then classify:

- **Failed due to test environment** (e.g., flaky end-to-end test under load):
  no need to pay for a new coding session — just re-verify the existing code:

  ```bash
  aisef run --verify-only --story STORY-01-03 --repeat 3
  ```

  `--repeat 3` runs each check three times; if results differ across runs, the
  gate records ⚠ "flaky" with the test name, instead of blaming the story.

- **Failed due to bad planning** (story lacks write access to a file it must
  edit, contradictory acceptance criteria): fix `_bmad-output/stories.index.json`
  and the story file, re-approve the `stories` gate, then run again.

- **Failed due to bad code**: let the framework retry, or run an improvement
  loop from [§13](#13-improvement-loops-and-post-release-changes).

To see what the agent is given:

```bash
aisef ctx --story STORY-01-03        # code map around the write scope
aisef skill --story STORY-01-03      # skills routed to this story
```

---

## 12. Verification, packaging, and acceptance

```bash
aisef qa
```

Runs all declared verification types: `unit`, `sit`, `api-contract`, `e2e`,
`uat`, `perf`, `security`, `mutation`, `accessibility`, `migration`, `sbom`,
`image-scan`. Types without a declared command show ○ and are **not** counted
as passing.

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

## 13. Improvement loops and post-release changes

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

**Changing requirements after release**:

```bash
aisef change FR-3 "Slugs must preserve underscores"
```

This command records the change in `docs/requirements.md`, marks the `prd` gate
and all downstream gates as `stale`, and generates a delta story
(`STORY-CH-01`) covering exactly `FR-3`. The original story **keeps** its
`DONE` status — history is not rewritten.

---

## 14. Real costs and how to reduce them

Real measurements on a notes project (Claude Code client):

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

Ways to reduce cost:

- Run **one epic** first before running them all; your project's numbers can't
  be derived from the table above.
- Build mockups in batches with `--only`, and approve early.
- Cut scope at the `prd` gate, not while stories are running.
- Set a ceiling for improvement loops: `improve.cost_cap_usd`.
- If a story fails due to the environment, use `--verify-only` instead of
  re-running the whole story.

---

## 15. Troubleshooting

| You see | It means | What to do |
|---|---|---|
| `✗ claude is not installed on this machine`, exit code 2 | no agent client on the machine | install the client, run `claude --version` until it works |
| `✗ no docs/requirements.md` | no input file | create the file per [§4](#4-creating-a-project-and-writing-the-input) |
| `aisef gates` shows `stale` | document changed after approval, or an upstream gate was just re-approved | re-read, then `aisef approve <gate>` |
| `stories` gate won't let you run | a machine gate caught a planning error | read the reason, fix `stories.index.json`, re-approve |
| Gate item ○ `coverage` | test command doesn't print coverage numbers | add `--coverage` (vitest/c8) or `--cov` (pytest) to `tools.test` |
| Gate item ○ `criteria has test` | runner doesn't print test names | add `--reporter=verbose` (vitest) or `-v` (pytest) |
| Gate item ✗ `test actually verifies story` | test only tagged a code onto an existing test | have the story write a new test for the criterion; if the existing test genuinely proves enough, declare the trace: `aisef evidence <code> --link "<test name>" --why "…"` |
| Gate item ⚠ with "unrunnable" | missing tool or environment | set up the environment, then re-run; **don't** lower the threshold to get past it |
| Verification reports "degraded" | running outside Docker, missing some guarantees | set up Docker; or declare `sandbox.pre_deploy_degraded_waiver` with a real reason |
| `Port ... is already in use` during e2e | an old dev process is still alive | find and kill it (`lsof -nP -i :5199`), then re-run |
| Story `blocked` after multiple attempts | usually bad planning, not bad code | read `aisef evidence <story>`, fix the story/write scope, re-approve the `stories` gate |
| Merge conflict at end of batch | two stories declared overlapping `write_scope` | this signals a planning problem — split the scopes, then re-run |
| Abnormally high cost for one story | story too large for one session | split the story; the size threshold is `story.max_complexity` |

Exit codes for all commands: `0` success, `1` bad arguments or missing input,
`2` not ready (gate not met, missing tool).

---

## 16. Reference: all commands

All commands accept `--project <directory>` (default: current directory).

**Preparation**

```bash
aisef doctor                              # check the environment
aisef setup [--references DIR] [--no-fetch] [--dry-run]
aisef init                                # write default .ai/config.json
aisef compile [--client claude|opencode|all] [--bin PATH]
```

**Planning and human gates**

```bash
aisef plan [--client c] [--auto-approve all|<list>] [--force]
aisef mockup [--client c] [--only <screen_id>] [--force]
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
aisef gate <story> [--attempt n] | --all | --replay
aisef guard <guard-name>                  # called by the framework via hooks
```

**Verification and release**

```bash
aisef qa [--only <type>] [--story S] [--story-level]
aisef devsecops [--client c] [--install-spec X] [--bin PATH] [--force]
aisef pre-deploy [--skip-qa] [--epic E]
```

**Observation**

```bash
aisef status
aisef report [--out FILE]
aisef evidence <id> [--story S] [--link TEST --why "..." --by ai]
aisef issues [--format md|csv] [--epic E] [--status gap,reopened] [--out FILE]
aisef ctx [--story S | --file F] [--budget N]
aisef skill [--story S] [--scan --client c --batch N]
aisef doc <package> [--topic T] [--story S]
aisef change FR-x "description"
```

---

## 17. Reference: all configuration keys

Values in parentheses are defaults.

**Verification and thresholds**

| Key | Default | Meaning |
|---|---|---|
| `tools.test` · `tools.lint` · `tools.sast` | `""` | project's real commands; empty means not configured |
| `verify.<type>` (12 types) | `""` | command for each verification type |
| `verify.waived` | `""` | waived types, comma-separated |
| `verify.waiver_reason` | `""` | reason for waivers; required when any type is waived |
| `verify.baseline` | `true` | run tests at the baseline commit before the story edits, to know which tests were already green |
| `verify.nop` | `true` | enable the "test actually verifies story" counterfactual |
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

**Execution**

| Key | Default | Meaning |
|---|---|---|
| `run.max_parallel` | `3` | stories running in parallel |
| `run.max_turns` | `40` | maximum turns in one agent session |
| `run.timeout_seconds` | `1800` | maximum time for one session |
| `run.max_retries` | `2` | retry count for one story |
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
| `sandbox.pre_deploy_degraded_waiver` | `""` | reason for accepting verification outside Docker at the final gate |

**Context, improvement loops, and clients**

| Key | Default | Meaning |
|---|---|---|
| `context.max_index_chars` | `2000` | character limit for the evidence index loaded into the prompt |
| `context.max_preservation_chars` | `1200` | character limit for the behavior preservation list |
| `context.max_repo_map_chars` | `0` | limit for the code map; `0` disables it |
| `improve.max_loops` | `3` | maximum improvement loops per epic |
| `improve.flat_loops` | `2` | stop when this many consecutive loops show no improvement |
| `improve.cost_cap_usd` | `0.0` | cost ceiling for improvement loops; `0` means unlimited |
| `route.developer_model` · `route.reviewer_model` · `route.designer_model` | `""` | force a specific model for each role |
| `clients.env_allow` | `[]` | environment variables allowed to pass into agent sessions |
| `skills.offer` · `skills.inline` | `false` | two skill suggestion mechanisms; measured as not beneficial yet, so disabled |

---

## 18. Glossary

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
  again).
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

---

Related documents in the repository: `README.md` (summary, English) and `README.vi.md` (Vietnamese version), `docs/SOLUTION.md` (full
design), `docs/FAILURE-TAXONOMY.md` (real failures encountered and how to prevent recurrence),
`CHANGELOG.md` (changes between versions and what to do when upgrading).
