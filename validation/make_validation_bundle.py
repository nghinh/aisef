#!/usr/bin/env python3
"""Build the immutable external-validation bundle for one public release (V1-F).

Everything a participant needs to validate **exactly one** release, and
nothing that could disagree with what was published:

* ``closure-evidence/external-validation/<version>/`` — the bundle directory.
  ``INSTRUCTIONS.md`` (cover sheet generated from the release manifest), then
  the public documentation **frozen verbatim from the release tag** —
  ``README.md``, ``QUICKSTART.md``, ``USAGE-GUIDE.md``, ``PROTOCOL.md`` — and
  ``REPORT-TEMPLATE.md`` with the release identity pre-filled. The participant
  writes ``REPORT.md`` into this directory and nothing else.
* ``closure-evidence/external-validation/<version>.bundle.json`` — the
  handoff record, **outside** the directory: identity, install target,
  protocol version, report schema, per-file digests and
  ``instructions_digest``. It sits outside because G6.1 recomputes
  ``instructions_digest`` over every file in the directory except
  ``REPORT.md`` — a file inside the directory cannot carry that digest
  without changing it. Measured on 2026-09-15 before the first handoff: the
  first generator put ``bundle.json`` inside, and the probe-side digest
  (``44fa8736…``) differed from the recorded one (``77295c3f…``), so a
  correctly filled report would have read FAILED.

The digest is computed here with the **same call** the probe makes
(``planes.bundle_digest(dir, exclude=("REPORT.md",))``), and a regression test
asserts the two agree on a generated bundle.

    python3 validation/make_validation_bundle.py            # for pyproject's version
    python3 validation/make_validation_bundle.py 1.7.2      # explicit
    python3 validation/make_validation_bundle.py 1.7.3 --docs HEAD   # docs from HEAD

``--docs <ref>`` freezes the four public documents and the template from that
commit instead of the release tag. The product is identified by the tag; the
documentation is its own plane (owner adjustment 8) and may be corrected after
the tag — the 1.7.3 tag's quickstart still said *Expect: aisef-1.7.2*, which
a participant would have read as an error. The record names both commits
explicitly: ``release_source_sha`` (the product) and ``bundle_source_sha``
(the exact commit the frozen files were taken from — never "current HEAD"),
and ``instructions_digest`` binds whatever was frozen; later HEAD movement
cannot alter it.

Refuses to overwrite an existing bundle: it is immutable once a participant
may have read it. A new release gets a new directory; a handoff defect found
after handoff invalidates that run and gets a new versioned bundle.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import planes  # noqa: E402

PROTOCOL_VERSION = "v1.1.0"

#: Public documents frozen into the bundle, verbatim from the release tag —
#: the protocol's run procedure says the tester follows README → Quick Start
#: → User Guide, so those are what the bundle carries, at the release point.
FROZEN = {
    "README.md": "README.md",
    "QUICKSTART.md": "docs/EXTERNAL-VALIDATION-QUICKSTART.md",
    "USAGE-GUIDE.md": "docs/USAGE-GUIDE.md",
    "PROTOCOL.md": "docs/EXTERNAL-VALIDATION-v1.1.0.md",
}
TEMPLATE = "docs/TEMPLATE-EXTERNAL-VALIDATION-REPORT.md"

#: Identity rows the report must carry, in the template's own words.
IDENTITY_ROWS = ("Product version", "Release tag", "Release source SHA", "Wheel sha256",
                 "Sdist sha256", "Protocol version", "Instructions digest")


def _version() -> str:
    return re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)


def _at_tag(tag: str, path: str) -> str:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{tag}:{path}"], capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"{path} does not exist at {tag}: {p.stderr.decode(errors='replace').strip()}")
    return p.stdout.decode("utf-8")


def instructions(m: dict, version: str) -> str:
    v, tag, sha = m["version"], m["tag"], m["release_source_sha"]
    wheel, sdist = m["artifacts"]["wheel"], m["artifacts"]["sdist"]
    return f"""# External validation of AISEF {v} — read this first

This folder is a frozen, self-contained bundle for validating **one** public
release. Every document in it was copied verbatim from the release tag
`{tag}`. Do not use the repository's current documentation or website for the
steps; use this folder. If something here disagrees with what the software
does, that disagreement is a finding — write it down.

## What you are validating

| field | value |
|---|---|
| Product version | **{v}** |
| Release tag | **{tag}** |
| Release source SHA | `{sha}` |
| Install target | `aisef=={v}` from **public PyPI** (project `aisef`) |
| Wheel | `{wheel['filename']}` · sha256 `{wheel['sha256']}` |
| Sdist | `{sdist['filename']}` · sha256 `{sdist['sha256']}` |
| Protocol version | {PROTOCOL_VERSION} (the protocol's own version, not the product's) |

The same values, plus this folder's `instructions_digest`, are in the handoff
record `{version}.bundle.json` next to this folder. Section 1 of your report
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
~/aisef-trial-venv/bin/pip install --no-cache-dir "aisef=={v}"
~/aisef-trial-venv/bin/aisef --version      # expected: aisef {v}
```

Do **not** install from a git clone, an editable checkout, a local wheel or
any unpublished artifact: the thing under test is the public package. To
confirm you have the published bytes:

```sh
~/aisef-trial-venv/bin/pip download --no-deps --no-cache-dir -d /tmp/aisef-dl "aisef=={v}"
shasum -a 256 /tmp/aisef-dl/{wheel['filename']}      # expected: the wheel sha256 above
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
- section 1's identity rows are copied from `{version}.bundle.json`;
- **success** means the lifecycle completed from an empty project to a
  gate-verified result with zero author interventions — say so in section 10;
- **failure** means any step you could not complete, or completed only with
  help — record it as a finding with the P0–P3 ladder from `PROTOCOL.md`;
- *not measured* is a legitimate value; a guess is not;
- nobody edits your report afterwards; a correction is a dated addendum at
  the end.
"""


def build(version: str, *, force: bool = False, docs_ref: str = "") -> Path:
    manifest = ROOT / "closure-evidence" / "releases" / f"{version}.json"
    if not manifest.is_file():
        raise SystemExit(f"{manifest.relative_to(ROOT)} does not exist — record the manifest first "
                         f"(validation/record_closure_evidence.py manifest)")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    tag = m["tag"]
    src_ref = docs_ref or tag
    docs_sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{src_ref}^{{commit}}"],
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
    if not docs_sha:
        raise SystemExit(f"cannot resolve {src_ref!r} to a commit")
    out = ROOT / "closure-evidence" / "external-validation" / version
    record = out.parent / f"{version}.bundle.json"
    if (out.exists() or record.exists()) and not force:
        raise SystemExit(f"{out.relative_to(ROOT)} exists — a bundle is immutable; a new release gets a new one")
    if out.exists():
        for p in out.iterdir():
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)
    (out / "INSTRUCTIONS.md").write_text(instructions(m, version), encoding="utf-8")
    for name, src in FROZEN.items():
        (out / name).write_text(_at_tag(src_ref, src), encoding="utf-8")
    template = (_at_tag(src_ref, TEMPLATE)
                .replace("`<e.g. 1.7.2>`", f"`{m['version']}`")
                .replace("`<e.g. v1.7.2>`", f"`{tag}`")
                .replace("`<40-hex commit from bundle.json>`", f"`{m['release_source_sha']}`")
                .replace("| Wheel sha256 | `<from bundle.json>` |",
                         f"| Wheel sha256 | `{m['artifacts']['wheel']['sha256']}` |")
                .replace("| Sdist sha256 | `<from bundle.json>` |",
                         f"| Sdist sha256 | `{m['artifacts']['sdist']['sha256']}` |")
                .replace("`<instructions_digest from bundle.json>`",
                         f"`<instructions_digest from {version}.bundle.json, next to this folder>`")
                .replace("Copy the\nvalues from the bundle's `bundle.json`; do not type them from memory.",
                         f"Copy the\nvalues from `{version}.bundle.json` next to this folder; do not type them from memory."))
    (out / "REPORT-TEMPLATE.md").write_text(template, encoding="utf-8")
    # The digest the probe will recompute: every file in the directory except
    # the participant's REPORT.md. Nothing that carries the digest may be inside.
    digest, names = planes.bundle_digest(out, exclude=("REPORT.md",))
    files = {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in names}
    record.write_text(json.dumps({
        "schema_version": 2,
        "product_version": m["version"], "release_tag": tag,
        "release_source_sha": m["release_source_sha"],
        "install_target": f"aisef=={m['version']}", "pypi_project": "aisef",
        "wheel": {"filename": m["artifacts"]["wheel"]["filename"], "sha256": m["artifacts"]["wheel"]["sha256"]},
        "sdist": {"filename": m["artifacts"]["sdist"]["filename"], "sha256": m["artifacts"]["sdist"]["sha256"]},
        "wheel_sha256": m["artifacts"]["wheel"]["sha256"],
        "sdist_sha256": m["artifacts"]["sdist"]["sha256"],
        "protocol_version": PROTOCOL_VERSION,
        "bundle_dir": f"closure-evidence/external-validation/{version}",
        "instructions_digest": digest,
        "instructions_digest_rule": ("sha256 over `name:sha256(bytes)` of every file in bundle_dir except REPORT.md, "
                                     "sorted by path; the same call the closure probe makes "
                                     "(aisef.control.planes.bundle_digest)"),
        "files": files,
        "bundle_source_sha": docs_sha,
        "frozen_from": {"tag": tag, "sha": m["release_source_sha"],
                        "docs_ref": src_ref, "docs_sha": docs_sha,
                        "sources": {**{k: v for k, v in FROZEN.items()}, "REPORT-TEMPLATE.md": TEMPLATE}},
        "report_schema": {
            "path": f"closure-evidence/external-validation/{version}/REPORT.md",
            "template": f"closure-evidence/external-validation/{version}/REPORT-TEMPLATE.md",
            "identity_rows": list(IDENTITY_ROWS),
            "metrics": "every row of PROTOCOL.md § Metrics, labels unchanged",
            "participant_line": "a `Participant:` row asserting external, human status (G6.2)",
            "findings": "a table with a `severity` column on the protocol's P0-P3 ladder (G6.3)",
        },
        "attachments": "handed back separately; never placed inside bundle_dir",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    docs_ref = ""
    if "--docs" in args:
        i = args.index("--docs")
        docs_ref = args[i + 1]
        del args[i:i + 2]
    path = build(args[0] if args else _version(), force=force, docs_ref=docs_ref)
    rec = json.loads((path.parent / f"{path.name}.bundle.json").read_text())
    print(f"bundle at {path.relative_to(ROOT)} ({len(rec['files'])} files) — "
          f"instructions_digest {rec['instructions_digest'][:12]} · record {path.name}.bundle.json")
