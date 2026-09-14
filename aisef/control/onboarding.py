"""Onboarding digest — the staleness clock for G6 (owner ruling 4, 2026-09-14).

G6 says one person who did not implement AISEF must run the canonical public
workflow and leave a record. That record then has to stay valid for a while,
which raises the question this module answers: **when does it stop being
valid?** The ruling replaced "one minor version" with

    the validated version shares MAJOR.MINOR with the closure release, **and**
    a deterministic *onboarding digest* has not materially changed.

"Materially" is the whole design. A byte digest over the README would let a
comma make a volunteer's afternoon worthless, and after the second false alarm
nobody reads the alarm — which is the failure mode
``docs/BENCH-PREREGISTRATION-C2.md`` §1.2 names. So the digest covers the
*executable* onboarding surface and nothing else:

* the commands the public docs tell a newcomer to run, with their flags — read
  out of fenced code blocks and out of list items, never out of paragraphs;
* the ten config defaults ``docs/closure-gate.json`` names, because a changed
  default silently changes what the next participant experiences.

Prose is not hashed at all. That is stronger than "whitespace collapsed": it
makes a typo fix, a reworded sentence, a reflowed paragraph and a rewritten
comment on a command line *structurally* incapable of moving the digest, rather
than merely unlikely to.

**This is the opposite convention to G5.1's pre-registration pin on purpose.**
That one is byte-exact inside its frozen region because the protected value is
the text itself, and a typo fix there *must* break the pin
(``BENCH-PREREGISTRATION-C2.md`` §1.3). Here the protected value is a person's
work, and a typo fix must *not* break it. Two digests, two conventions, and
copying either one into the other's place breaks it.

Sources and the ten keys are read from ``docs/closure-gate.json`` — the approved
contract — never duplicated here, so the contract stays the single place they
are named.

Regenerate the recorded value::

    python3 -m aisef.control.onboarding --write

Reference test: ``tests/test_onboarding_digest.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTRACT_PATH = "docs/closure-gate.json"
EVIDENCE_PATH = "closure-evidence/onboarding-digest.json"

#: A line counts as a documented command when it starts with one of these.
#: Deliberately narrow: ``docker``, ``playwright`` and ``aisef/kit/catalog.json``
#: appear as inline code in the same prose and are *not* commands, so a bare
#: prefix match would drag the prose back in through the side door.
COMMAND_RE = re.compile(
    r"""^(?:
          aisef(?:\s|$)              # the CLI itself
        | pip\s+install\b
        | python3\s+-m\b
        | git\s+clone\b
        | AISEF_[A-Z0-9_]+=          # env-prefixed invocation
    )""",
    re.VERBOSE,
)

#: ``closure-gate.json`` names ``section:Quick Start``; ``README.md`` has no
#: heading by that name — the section that *is* the quick start is ``Six steps``.
#: Aliased rather than renamed: the contract is approved, and the README heading
#: is linked from elsewhere. Reported to the owner as a naming discrepancy.
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "quick start": ("quick start", "six steps"),
    # ``extract: canonical_cli_workflow`` is not a heading either; §17 of the
    # usage guide is the canonical verb-and-flag list.
    "canonical_cli_workflow": ("reference: all commands",),
}


def _norm_heading(text: str) -> str:
    """`## 17. Reference: all commands` -> `reference: all commands`."""
    return re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", text.strip()).strip().lower()


def _section(markdown: str, title: str) -> str:
    """The body of the heading matching *title*, up to the next same-or-higher one."""
    wanted = SECTION_ALIASES.get(title.lower(), (title.lower(),))
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    level = 0
    for line in lines:
        head = re.match(r"^(#{1,6})\s+(.*)$", line)
        if head and level:
            if len(head.group(1)) <= level:
                break
            out.append(line)
            continue
        if head and _norm_heading(head.group(2)) in wanted:
            level = len(head.group(1))
            continue
        if level:
            out.append(line)
    return "\n".join(out)


def _strip_comment(line: str) -> str:
    """Drop a trailing ``#`` comment, ignoring a ``#`` inside quotes."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and i and line[i - 1].isspace():
            return line[:i]
    return line


#: Inline code is harvested from **list items only** — never from paragraphs.
#: The external-validation protocol writes its steps as ``- `aisef doctor` ``
#: bullets, so inline code cannot be ignored; but a paragraph that merely
#: *mentions* a verb in backticks ("``aisef gate`` currently requires
#: ``--replay``") is prose, and harvesting it would let a reword raise a false
#: STALE — exactly the alarm this digest exists not to raise.
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def _commands(region: str) -> list[str]:
    """Documented commands in *region*, in document order.

    Continuation lines ending in ``\\`` are joined first, so a wrapped
    invocation keeps its flags.
    """
    text = re.sub(r"\\\n\s*", " ", region.replace("\r\n", "\n").replace("\r", "\n"))
    candidates: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            candidates.append(line)
        elif LIST_ITEM_RE.match(line):
            candidates.extend(re.findall(r"`([^`]+)`", line))
    out = []
    for raw in candidates:
        cmd = " ".join(_strip_comment(raw).split())
        if cmd and COMMAND_RE.match(cmd):
            out.append(cmd)
    return out


def _defaults(keys: Sequence[str], defaults: Mapping[str, Any]) -> list[str]:
    missing = [k for k in keys if k not in defaults]
    if missing:
        raise KeyError(f"onboarding defaults absent from config.DEFAULTS: {missing}")
    return [f"{k}={json.dumps(defaults[k], sort_keys=True)}" for k in keys]


def _sha(items: Sequence[str]) -> str:
    return hashlib.sha256(("\n".join(items) + "\n").encode("utf-8")).hexdigest()


def compute_onboarding_digest(
    root: str | Path,
    defaults: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Digest the public onboarding surface of the tree at *root*.

    *defaults* overrides ``aisef.config.DEFAULTS`` (tests inject a moved value).
    """
    root = Path(root)
    spec = json.loads((root / CONTRACT_PATH).read_text(encoding="utf-8"))["onboarding_digest"]
    if defaults is None:
        from aisef.config import DEFAULTS as defaults  # noqa: N811  (late: avoids a cycle)

    keys = list(spec["onboarding_defaults"])
    sources: list[dict[str, Any]] = []
    payload: list[str] = []
    for src in spec["sources"]:
        extract = src["extract"]
        if extract == "onboarding_defaults":
            items = _defaults(keys, defaults)
        else:
            text = (root / src["path"]).read_text(encoding="utf-8")
            title = extract.split(":", 1)[1] if extract.startswith("section:") else extract
            items = _commands(_section(text, title))
        payload.append(f"# {src['path']}::{extract}")
        payload.extend(items)
        sources.append(
            {"path": src["path"], "extract": extract, "items": len(items), "sha256": _sha(items)}
        )
    return {
        "_comment": (
            "Onboarding digest for closure gate G6.1 freshness (owner ruling 4). Covers the "
            "documented commands of the public onboarding surface plus the ten named config "
            "defaults -- never prose, so a typo fix cannot invalidate a real participant's "
            "validation. Regenerate: python3 -m aisef.control.onboarding --write"
        ),
        "contract": f"{CONTRACT_PATH}#onboarding_digest",
        "algorithm": "sha256",
        "digest": _sha(payload),
        "sources": sources,
    }


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[2]
    result = compute_onboarding_digest(root)
    out = root / EVIDENCE_PATH
    if "--write" in argv:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {EVIDENCE_PATH} — {result['digest']}")
        return 0
    print(result["digest"])
    if out.is_file():
        recorded = json.loads(out.read_text(encoding="utf-8")).get("digest")
        if recorded != result["digest"]:
            print(f"STALE: {EVIDENCE_PATH} records {recorded}")
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
