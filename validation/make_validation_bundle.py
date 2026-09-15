#!/usr/bin/env python3
"""Build the immutable external-validation bundle for one public release (V1-F).

Everything a participant needs to validate **exactly one** release, generated
from the release manifest so the bundle cannot disagree with what was
published: version, tag, `release_source_sha`, wheel and sdist digests, the
clean-install command pinned to that version, the canonical workflow, the
evidence to capture, the report template with its identity block, and the
rules for recording success and failure. `bundle.json` carries the same
identity plus `instructions_digest` — the SHA-256 the participant copies into
the report and G6.1 recomputes from the directory (the report itself is
excluded from it). The product version and the protocol version are separate
fields on purpose; v1.1.0 is the protocol's.

    python3 validation/make_validation_bundle.py            # for pyproject's version
    python3 validation/make_validation_bundle.py 1.7.2      # explicit

Refuses to overwrite an existing bundle: it is immutable once a participant
may have read it. A new release gets a new directory.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import planes  # noqa: E402

PROTOCOL_VERSION = "v1.1.0"
TEMPLATE = ROOT / "docs/TEMPLATE-EXTERNAL-VALIDATION-REPORT.md"


def _version() -> str:
    return re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)


def instructions(m: dict) -> str:
    v, tag, sha = m["version"], m["tag"], m["release_source_sha"]
    wheel, sdist = m["artifacts"]["wheel"], m["artifacts"]["sdist"]
    return f"""# External validation — AISEF {v} (bundle, immutable)

This bundle validates **one** public release and nothing else. Do not use the
repository's latest documentation for the steps; use this directory. If a
step here disagrees with a page on the website, that disagreement is a finding.

## Identity of what you are validating

| field | value |
|---|---|
| Product version | **{v}** |
| Release tag | **{tag}** |
| Release source SHA | `{sha}` |
| Package source | public PyPI, project `aisef` |
| Wheel | `{wheel['filename']}` · sha256 `{wheel['sha256']}` |
| Sdist | `{sdist['filename']}` · sha256 `{sdist['sha256']}` |
| Protocol version | {PROTOCOL_VERSION} (the protocol's version, not the product's) |

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
~/aisef-trial-venv/bin/pip install --no-cache-dir "aisef=={v}"
~/aisef-trial-venv/bin/aisef --version      # must print: aisef {v}
```

Run the version check with your shell **outside** any AISEF source checkout.
Do **not** validate from a git checkout, an editable install, an unpublished
wheel or a worktree: the package under test is the public one. If you want to
confirm you have the published bytes:

```sh
~/aisef-trial-venv/bin/pip download --no-deps --no-cache-dir -d /tmp/aisef-dl "aisef=={v}"
shasum -a 256 /tmp/aisef-dl/{wheel['filename']}      # must equal the wheel sha256 above
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
"""


def build(version: str, *, force: bool = False) -> Path:
    manifest = ROOT / "closure-evidence" / "releases" / f"{version}.json"
    if not manifest.is_file():
        raise SystemExit(f"{manifest.relative_to(ROOT)} does not exist — record the manifest first "
                         f"(validation/record_closure_evidence.py manifest)")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    out = ROOT / "closure-evidence" / "external-validation" / version
    if out.exists() and not force:
        raise SystemExit(f"{out.relative_to(ROOT)} exists — a bundle is immutable; a new release gets a new one")
    out.mkdir(parents=True, exist_ok=True)
    (out / "INSTRUCTIONS.md").write_text(instructions(m), encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    template = (template.replace("`<e.g. 1.7.2>`", f"`{m['version']}`")
                .replace("`<e.g. v1.7.2>`", f"`{m['tag']}`")
                .replace("`<40-hex commit from bundle.json>`", f"`{m['release_source_sha']}`")
                .replace("| Wheel sha256 | `<from bundle.json>` |",
                         f"| Wheel sha256 | `{m['artifacts']['wheel']['sha256']}` |")
                .replace("| Sdist sha256 | `<from bundle.json>` |",
                         f"| Sdist sha256 | `{m['artifacts']['sdist']['sha256']}` |"))
    # The digest covers the template, so the template cannot carry the digest:
    # the participant copies it from bundle.json, which the digest excludes.
    (out / "REPORT-TEMPLATE.md").write_text(template, encoding="utf-8")
    digest, names = planes.bundle_digest(out, exclude=("REPORT.md", "bundle.json"))
    (out / "bundle.json").write_text(json.dumps({
        "schema_version": 1,
        "product_version": m["version"], "release_tag": m["tag"],
        "release_source_sha": m["release_source_sha"],
        "wheel_sha256": m["artifacts"]["wheel"]["sha256"],
        "sdist_sha256": m["artifacts"]["sdist"]["sha256"],
        "protocol_version": PROTOCOL_VERSION,
        "instructions_digest": digest, "instructions_files": names,
        "record_path": f"closure-evidence/external-validation/{version}/REPORT.md",
        "_note": ("instructions_digest is the SHA-256 over `name:sha256(bytes)` of the files listed, "
                  "sorted; REPORT.md and this file are excluded. G6.1 recomputes it from the directory."),
    }, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    path = build(args[0] if args else _version(), force=force)
    print(f"bundle at {path.relative_to(ROOT)} — instructions_digest "
          f"{json.loads((path / 'bundle.json').read_text())['instructions_digest'][:12]}")
