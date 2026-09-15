# External validation — AISEF 1.7.2 (bundle, immutable)

This bundle validates **one** public release and nothing else. Do not use the
repository's latest documentation for the steps; use this directory. If a
step here disagrees with a page on the website, that disagreement is a finding.

## Identity of what you are validating

| field | value |
|---|---|
| Product version | **1.7.2** |
| Release tag | **v1.7.2** |
| Release source SHA | `d092b25fb94ec463347e6a5a04d1cc43a7fc2df8` |
| Package source | public PyPI, project `aisef` |
| Wheel | `aisef-1.7.2-py3-none-any.whl` · sha256 `d97ca56db1499f7eaf97ee0e1a4c3eff54acf08a7c6c66bd892c6943c1db63f9` |
| Sdist | `aisef-1.7.2.tar.gz` · sha256 `7fe16a4f1fd26a56e5cba9717592082f503336ca41c517de395192ce189ef7a6` |
| Protocol version | v1.1.0 (the protocol's version, not the product's) |

Copy these values into §1 of `REPORT.md` exactly; the closure gate compares
them with the release manifest and refuses a record that names another release.

## Who may do this

A genuinely external **person**: not an AISEF implementer, not an AISEF
contributor, not an AI agent. A simulated participant measures nothing.

## Prerequisites

- Python >= 3.11 and `git`
- one AI coding agent on your `PATH`, logged in and able to spend: Claude Code
  (`claude`) or OpenCode (`opencode`)
- 30–60 minutes; Docker optional (without it AISEF uses the `local` sandbox and
  labels its evidence *degraded* — report that as observed, it is not a defect)
- money: the deterministic steps spend nothing; the first model call is
  `aisef plan`, billed to your own account

## Clean install — public PyPI only

```sh
python3 -m venv ~/aisef-trial-venv
~/aisef-trial-venv/bin/pip install --no-cache-dir "aisef==1.7.2"
~/aisef-trial-venv/bin/aisef --version      # must print: aisef 1.7.2
```

Run the version check with your shell **outside** any AISEF source checkout.
Do **not** validate from a git checkout, an editable install, an unpublished
wheel or a worktree: the package under test is the public one. If you want to
confirm you have the published bytes:

```sh
~/aisef-trial-venv/bin/pip download --no-deps --no-cache-dir -d /tmp/aisef-dl "aisef==1.7.2"
shasum -a 256 /tmp/aisef-dl/aisef-1.7.2-py3-none-any.whl      # must equal the wheel sha256 above
```

## Canonical workflow

In an empty directory of your own, in this order. Steps 1–8 spend nothing.

```sh
mkdir aisef-trial && cd aisef-trial && git init
~/aisef-trial-venv/bin/aisef doctor
~/aisef-trial-venv/bin/aisef init
# write docs/requirements.md — a small product you would actually build
~/aisef-trial-venv/bin/aisef setup
~/aisef-trial-venv/bin/aisef compile
~/aisef-trial-venv/bin/aisef gates
~/aisef-trial-venv/bin/aisef plan            # first model call
~/aisef-trial-venv/bin/aisef review prd      # then approve, per the output
~/aisef-trial-venv/bin/aisef run --epic EPIC-01
~/aisef-trial-venv/bin/aisef qa
~/aisef-trial-venv/bin/aisef pre-deploy --epic EPIC-01
```

Where the tool tells you the next command, follow the tool. "I had to ask an
author" **is** a finding — write down where you got stuck; do not get unstuck
quietly.

## Evidence to capture

- a terminal transcript of every command and its output, wrong turns included
- `aisef --version` and `aisef doctor` output from the clean venv
- which agent CLI and model you used, and whether Docker was present
- wall-clock time and roughly what the model calls cost
- every point where you were blocked, guessed, or read something outside this
  bundle and the shipped `--help`
- anything the framework reported that you believe is **wrong**; a gate that
  passed when it should not have is the most valuable finding possible

## Recording the result

Fill in `REPORT-TEMPLATE.md` and save it in this directory as `REPORT.md`.
Rules:

- **success** = the lifecycle above completed from an empty project to a
  gate-verified result with **zero** author interventions; say so in §10;
- **failure** = any step you could not complete, or completed only with help;
  record it as a finding with the severity ladder in §5 (P0 cannot install /
  data loss / security / incorrect gate result; P1 cannot complete without
  author help; P2 friction; P3 cosmetic);
- **not measured** is a legitimate value; a guess is not;
- the §1 identity rows must carry the values from `bundle.json` in this
  directory — the closure gate reads them.

The report is yours. Nobody edits it afterwards; a correction is a dated
addendum at the end.
