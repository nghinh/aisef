# Participant quickstart — external validation (G6)

You are about to run AISEF end to end on a small project you have never built,
using only the public documentation. This page is the shortest path plus the
outputs you should actually see, so you can tell "AISEF is broken" apart from
"I made a typo".

**Your job is to report what happened, not to make it work.** A step that fails
is the most valuable thing you can produce. Do not fix the framework, do not read
its source, and do not ask an AISEF author for help until you have been stuck on
one step for ten minutes — and when you do ask, the help you get is recorded as a
**P1** finding.

Record everything in a copy of
[`TEMPLATE-EXTERNAL-VALIDATION-REPORT.md`](TEMPLATE-EXTERNAL-VALIDATION-REPORT.md),
saved as `docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md`. The full protocol and the
observer's rules are in
[`EXTERNAL-VALIDATION-v1.1.0.md`](EXTERNAL-VALIDATION-v1.1.0.md); the reference
manual, if you want it, is [`USAGE-GUIDE.md`](USAGE-GUIDE.md).

## Before you start

- Python >= 3.11 (`python3 --version`).
- `git`.
- One AI coding agent on your `PATH`: Claude Code (`claude`) or OpenCode
  (`opencode`), already logged in and able to spend.
- About 30–60 minutes, of which roughly 10 are machine time and the rest is
  reading and one model run.
- Docker is **optional**. Without it, AISEF drops to the `local` sandbox
  provider and labels its evidence *degraded*. That is a correct outcome for a
  trial, not a failure — report it as observed, not as a defect.
- Money: steps 1–8 below spend **nothing**. Step 9 (`aisef plan`) is the first
  command that calls a model and it is billed to your own account. Know your
  budget before you type it.

## Steps 1–8 — deterministic, no money

Every output below was produced on macOS with Python 3.14.7 and `aisef` from
PyPI. Yours should match in shape; version and paths will differ.

Steps 1, 2, 4, 5, 7 and 8 (`gates`) were **re-run and re-verified on 1.7.1** on
2026-09-15 and behave exactly as written. Step 8's `aisef setup` line still
carries its 1.6.0 measurement: re-running it means a ~93 MB reference fetch,
which was not repeated, so treat that one count as indicative rather than
freshly measured.

**1. Clean venv.**

```bash
python3 -m venv ~/.venvs/aisef
source ~/.venvs/aisef/bin/activate
pip install aisef
```

Expect: `Successfully installed aisef-1.7.1`, and no other package pulled in —
AISEF has no dependencies outside the standard library. (Verified 2026-09-15:
`pip list` in that venv shows exactly `aisef==1.7.1` and nothing else.)

If pip claims the version does not exist, add `--no-cache-dir`: a stale index
cache can hide a freshly published release.

**2. Confirm what you got.**

```bash
aisef --version        # → aisef 1.7.1
which aisef            # → …/.venvs/aisef/bin/aisef
```

If `which` points somewhere you did not install (an old `pipx`, a system
Python), stop and fix your `PATH` first. An older `aisef` earlier on `PATH`
answers every command successfully with the wrong rules, so nothing tells you.

**3. Make an empty project and go into it.**

```bash
mkdir -p ~/projects/notes && cd ~/projects/notes
git init
```

Git is not optional: each story runs in its own `git worktree`.

**4. Diagnose before configuring.** Run this on purpose *before* anything
exists, so you see what an unprepared project looks like.

```bash
aisef doctor
```

Expect the last line to be `✗ missing: docs/requirements.md` and the exit status
to be `2`. Everything above it is a checklist; `○` means degraded-but-usable,
`✗` means blocking.

**5. Write the config.**

```bash
aisef init --stack python
```

Expect `wrote …/.ai/config.json` and `stack: python — test/lint/sandbox
configured`, with four keys in the file. `aisef init` **without** `--stack`
writes only `tools.test: ""` — one key — and you then have to fill it in
yourself, so pass the flag.

**6. Write the one input file.** This is the only part of the run that is your
own work. Prose is fine; there is no template. Four lines is enough.

```bash
mkdir -p docs
cat > docs/requirements.md <<'EOF'
# Personal notes application

A small command-line notes tool. A user can add a note, list notes, and delete
a note by id. Notes are stored in a local JSON file. Python, no network.
EOF
```

**7. Diagnose again.**

```bash
aisef doctor
```

Expect the last line to be `✅ ready` and the exit status `0`. If it is not,
stop here and report it: everything after this point assumes `ready`.

**8. Install skills and wire the guards.**

```bash
aisef setup
aisef compile
aisef gates
```

- `aisef setup` fetches the pinned reference repositories into
  `~/.cache/aisef/references` (about 93 MB, once per machine — the first run is
  the slow one), detects your stack, installs skills, and writes `CLAUDE.md` and
  `AGENTS.md`. Expect `installed 150 · unchanged 0 · removed 0 · total 150` and
  `✅ done`. On an offline machine use `aisef setup --no-fetch`.
- `aisef compile` writes the client's hook or plugin config. Expect
  `guards blocking before action:` followed by eight guard names, and a warning
  that OpenCode cannot host the `completion` guard natively. That warning is
  expected, not a defect.
- `aisef gates` lists the eight human gates, all `⏳ pending`, and exits `2`.
  Exit code 2 here means "a human still has to act", not "error".

**This is the end of the free path.** Nothing so far has called a model. If any
of steps 1–8 did not behave as described, that is a **framework** finding and
worth more than the rest of the run.

## Step 9 onward — this spends money

```bash
aisef plan            # PRD → architecture → UX → epics → stories
aisef gates           # which gate is waiting for you
aisef review prd      # read what it wrote
aisef approve prd     # …then approve, or `aisef reject prd --note "..."`
```

`aisef plan` starts a model session and stops at the first gate that needs a
human. Repeat review/approve until `aisef gates` has nothing pending, then:

```bash
aisef run             # implement the stories
aisef qa              # the verification suite
aisef pre-deploy      # the final gate
aisef report          # acceptance report + behaviour ledger
```

Two notes that will otherwise cost you a confused hour:

- `aisef verify` is **not** the lifecycle verification step. It is a per-story
  post-check, and with no `--write-scope` it prints `✅ post-check passed` on a
  project where nothing has been built. The suite is `aisef qa`.
- `aisef pre-deploy` refuses while any human gate is unapproved, and says which.
  That is the gate working.

Write down what each phase cost (`aisef cost`) and how long it took.

## When something fails

Work through this in order, and record every step of it.

1. **Read the whole message.** AISEF's failures name the missing thing and
   usually the command that supplies it. `○` is degraded, `✗` is blocking.
2. **Re-run `aisef doctor`.** Most mid-run failures are an environment fact that
   changed (Docker stopped, credential expired, `PATH` shifted).
3. **Check the exit status**, not just the text. `0` pass · `2` a gate refuses or
   a human is needed · anything else is a bug worth reporting.
4. **Look in [`USAGE-GUIDE.md`](USAGE-GUIDE.md) §16 Troubleshooting** — and if
   the answer is not there, that absence is itself a finding: write down what you
   searched for.
5. **Do not read the framework's source.** If the only way forward is reading
   `aisef/`, the run has found a P1 and you should say so.
6. **Ten-minute rule.** Stuck longer than ten minutes on one step → ask for
   minimal unblocking help, and record it as **P1** with the help you were given,
   verbatim.

Report a command exactly as you typed it, with its exit status and its output.
"It didn't work" cannot be fixed; `aisef compile` + `rc=1` + the traceback can.

## How to classify what you found

Use the protocol's ladder — [`EXTERNAL-VALIDATION-v1.1.0.md` § Finding
classification](EXTERNAL-VALIDATION-v1.1.0.md#finding-classification). It is the
only severity scale in this project; do not invent a second one, and do not
assign taxonomy numbers — those are assigned centrally.

| severity | you should pick it when | examples from this walkthrough |
|---|---|---|
| **P0** | you cannot install; data was lost; a security hole; **a gate reported the wrong result** | `pip install aisef` fails; `aisef pre-deploy` passes with nothing built; a guard lets the agent write outside its scope |
| **P1** | you could not finish the lifecycle without help from an AISEF author | a required step is documented nowhere; a command only works with a flag no document mentions; you had to read the source |
| **P2** | you finished, but a step was confusing or the docs were wrong | `aisef init`'s key count differs from what the guide says; an output you could not interpret |
| **P3** | cosmetic, or a nice-to-have | a typo; a message that could be phrased better |

The two that decide the gate are **P0 and P1** — an unresolved one of either
blocks closure (G6.3). When you are unsure between two levels, pick the higher
one and say why; the owner can lower it, but nobody can recover a finding you
downgraded into silence.

## What makes your run count

- You are a **person**, not an agent, and you did not write any part of AISEF.
  An AI agent cannot satisfy this gate, by rule.
- You ran the commands yourself, on your own machine.
- The report is yours: your words in the questionnaire, your numbers in the
  metrics table, and the failures left in.
