# External validation of AISEF 1.7.4 — read this first

This folder is a frozen, self-contained bundle for validating **one** public
release. Every document in it was copied verbatim from the release tag
`v1.7.4`. Do not use the repository's current documentation or website for the
steps; use this folder. If something here disagrees with what the software
does, that disagreement is a finding — write it down.

## What you are validating

| field | value |
|---|---|
| Product version | **1.7.4** |
| Release tag | **v1.7.4** |
| Release source SHA | `9dcd402d9e922ba4d5541f9f4cb85078b902168c` |
| Install target | `aisef==1.7.4` from **public PyPI** (project `aisef`) |
| Wheel | `aisef-1.7.4-py3-none-any.whl` · sha256 `200928a2eb8bc8abe8a5a0fe2704c053379e2f699ece92818872995e58ec5950` |
| Sdist | `aisef-1.7.4.tar.gz` · sha256 `163ffa28e7e986959913755757a06bc0029679d24d4c2890dc3322d4e40b75ae` |
| Protocol version | v1.1.0 (the protocol's own version, not the product's) |

The same values, plus this folder's `instructions_digest`, are in the handoff
record `1.7.4.bundle.json` next to this folder. Section 1 of your report
copies them from there.

## Who may do this

A person external to the implementation of AISEF: not an AISEF implementer or
contributor, and not an AI agent. Nothing else about you is required beyond
what the report template asks.

## Environment

- Python >= 3.11 and `git`
- one AI coding agent on your `PATH`, logged in and able to spend: Claude Code
  (`claude`) or OpenCode (`opencode`)
- a fresh virtual environment, and a fresh working directory that is **not**
  inside any git checkout of AISEF
- Docker is optional; without it AISEF uses its `local` sandbox and labels its
  evidence *degraded* — report that as observed
- 30–60 minutes; the deterministic steps spend nothing, the first model call
  (`aisef plan`) is billed to your own account

## Install — public PyPI only

```sh
python3 -m venv ~/aisef-trial-venv
~/aisef-trial-venv/bin/pip install --no-cache-dir "aisef==1.7.4"
~/aisef-trial-venv/bin/aisef --version      # expected: aisef 1.7.4
```

Do **not** install from a git clone, an editable checkout, a local wheel or
any unpublished artifact: the thing under test is the public package. To
confirm you have the published bytes:

```sh
~/aisef-trial-venv/bin/pip download --no-deps --no-cache-dir -d /tmp/aisef-dl "aisef==1.7.4"
shasum -a 256 /tmp/aisef-dl/aisef-1.7.4-py3-none-any.whl      # expected: the wheel sha256 above
```

## The run

Follow the documents in this folder, in this order, exactly as written:

1. `README.md` — *Install* and *Quick Start*;
2. `QUICKSTART.md` — steps 1–8 spend nothing, step 9 onward spends money;
3. `USAGE-GUIDE.md` — the full lifecycle reference, when a step needs more;
4. `PROTOCOL.md` — § Protocol is the run procedure, § Finding classification
   is the P0–P3 ladder you classify findings with.

Where a document links to a file that is not in this folder, that is a finding
(*undocumented step* or *confusion point*), not something to go and look up.
Where the software's own output tells you the next command, the software wins
over the document, and the difference is a finding too.

## What to record

- a terminal transcript of every command and its output, wrong turns included
- `aisef --version` and `aisef doctor` output from the venv
- which agent CLI and model you used, and whether Docker was present
- wall-clock time and roughly what the model calls cost
- every point where you were blocked, guessed, or had to read something
  outside this folder and the software's own `--help`
- anything the software reported that you believe is wrong — a gate that
  passed when it should not have is the single most valuable finding

## Recording the result

Copy `REPORT-TEMPLATE.md` to `REPORT.md` **in this folder** and fill it in.
Rules:

- `REPORT.md` is the only file you add here; attach transcripts or screenshots
  separately (a folder or archive handed back with the report), never inside
  this folder;
- section 1's identity rows are copied from `1.7.4.bundle.json`;
- **success** means the lifecycle completed from an empty project to a
  gate-verified result with zero author interventions — say so in section 10;
- **failure** means any step you could not complete, or completed only with
  help — record it as a finding with the P0–P3 ladder from `PROTOCOL.md`;
- *not measured* is a legitimate value; a guess is not;
- nobody edits your report afterwards; a correction is a dated addendum at
  the end.
