# External validation handoff — AISEF 1.7.1

> **Superseded 2026-09-15, kept as history.** 1.7.1 will not be externally
> validated: the closure gate's release-identity defect (D-022) is fixed in
> 1.7.2, and G6 now binds a record to one exact release through an immutable
> bundle at `closure-evidence/external-validation/<version>/`. Use that bundle,
> not this sheet. Nothing below has been edited.

Everything a participant needs, without any knowledge of this repository.

> **Placement note (for the project owner, not the participant).** This file
> lives under `closure-evidence/` rather than `docs/` on purpose: the closure
> target `5c5ba52` is frozen and tagged, and the gate treats any change outside
> `closure-evidence/` and the criteria file as a source change that would stale
> every commit-bound piece of evidence and break `tag == target`. Send the
> participant the three linked documents below; this page is the cover sheet.

## What is being validated

| | |
|---|---|
| **Product version** | **1.7.1** |
| **Release tag** | **v1.7.1** |
| **Release commit SHA** | **`5c5ba52fa0c98bd276b074b7bc3e1d112dd49fd5`** |
| Source of the package | **public PyPI**, project `aisef` |
| Wheel | `aisef-1.7.1-py3-none-any.whl` · sha256 `064c27f0f9663c1b1a9ef3a6e766c6d05a8b4b07c1bdd044d01a48b21a97ce39` |
| Sdist | `aisef-1.7.1.tar.gz` · sha256 `4026bb3752a4726ac2a6a4d162ebbcd92902dd422a2709189376117184c67f0a` |
| Protocol version | v1.1.0 (the *protocol's* version, not the product's) |

**1.7.0 was never published.** It was tagged, its release CI failed, nothing
reached PyPI, and `https://pypi.org/pypi/aisef/1.7.0/json` returns 404. If you
see 1.7.0 anywhere, it is not a release. Validate **1.7.1**.

## Who may do this

A genuinely external person: someone who did not implement AISEF, is not an
AISEF contributor, and is **not an AI agent**. The point of this gate is that
every other gate is the author measuring the author. A simulated participant
measures nothing.

## Prerequisites

- Python >= 3.11 (`python3 --version`)
- `git`
- One AI coding agent on your `PATH`, already logged in and able to spend:
  Claude Code (`claude`) or OpenCode (`opencode`)
- ~30–60 minutes; roughly 10 of machine time
- Docker is **optional**. Without it AISEF drops to the `local` sandbox and
  labels its evidence *degraded*. That is a correct outcome to report as
  observed, not a defect.
- Money: the deterministic steps spend **nothing**. The first model call is
  `aisef plan`, billed to your own account. Know your budget before you type it.

## Clean install — from public PyPI only

```sh
python3 -m venv ~/aisef-trial-venv
~/aisef-trial-venv/bin/pip install --no-cache-dir "aisef==1.7.1"
~/aisef-trial-venv/bin/aisef --version      # must print: aisef 1.7.1
```

Two things that will mislead you if you skip them:

* `--no-cache-dir` — a stale pip index cache can hide a freshly published
  version, or make a withdrawn one look installable. This happened during the
  release and cost a confusing hour.
* Run the version check with your shell **outside** any AISEF source checkout.
  A leftover `aisef.egg-info` in a source tree is resolved ahead of your venv
  and will report the wrong version.

Do **not** validate from a git checkout, an editable install, an unpublished
wheel, or a closure worktree. The package under test is the public one.

## Canonical first run

Follow **`docs/EXTERNAL-VALIDATION-QUICKSTART.md`** in order:

* *Before you start* → prerequisites
* *Steps 1–8* → deterministic, spends nothing
* *Step 9 onward* → the first model call, billed to you
* *When something fails* → do this before reporting
* *How to classify what you found* → the P0/P1/P2/P3 ladder

Its recorded outputs were produced with `aisef 1.6.0`; yours will say 1.7.1 and
paths will differ. Shape should match — where it does not, that is exactly the
kind of finding worth writing down.

## Expected outcome

You complete the lifecycle from an empty project to a gate-verified result
without asking an AISEF author anything. "I had to ask" **is** a finding, and
naming where you got stuck is more valuable than getting unstuck quietly.

## Evidence to capture

- the exact commands you ran and their output (a terminal transcript is ideal)
- `aisef --version` from the clean venv
- `aisef doctor` output
- which agent CLI and model you used, and whether Docker was present
- wall-clock time, and roughly what the model calls cost you
- every point where you were blocked, guessed, or consulted something outside
  the shipped docs
- anything the framework reported that you believe is **wrong** — a gate that
  passed when it should not have is the single most valuable thing you can find

## Report

Fill in **`docs/TEMPLATE-EXTERNAL-VALIDATION-REPORT.md`** and save it as:

```
docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md
```

That filename carries the **protocol** version v1.1.0 and does not change with
the product version. Inside the report, state plainly:

```
AISEF product version validated: 1.7.1
release tag:  v1.7.1
release SHA:  5c5ba52fa0c98bd276b074b7bc3e1d112dd49fd5
```

Classify findings with the ladder in
**`docs/EXTERNAL-VALIDATION-v1.1.0.md` § Finding classification**. Use its
words, not your impression of severity.

## After the report exists

The project owner runs `aisef closure`. G6.1 checks the report exists at the
declared path with the protocol's metric fields, G6.2 that the participant is a
genuine external person, and G6.3 that no P0/P1 onboarding blocker is left
unresolved. Any P0/P1 you find is fixed before the project can close — finding
one is a success for this exercise, not a setback.
