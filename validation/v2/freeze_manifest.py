"""WP-0.1 — freeze manifest: make the approved AISEF V2 architecture baseline mechanically identifiable.

Recomputes, from the RFC at HEAD, the two digests the owner approval record binds, and enumerates the frozen
items F1-F11. Drift in the normative body or the freeze table fails; an edit to the non-normative status preamble
does not, because the normative digest starts at the first normative heading.

2.1 (ARCHITECTURE-EXCEPTION-V2-007): the lineage continues in closure-evidence/v2/v2.1/ and the current manifest is
written there. The 2.0 manifest (the V2-006 freeze, pinned by the Cycle-2 baseline guard) is history: its bytes are its
blob at v2.0.0 and the lineage it froze is the head of the current one.

    python -P validation/v2/freeze_manifest.py            # write the 2.1 manifest (refuses an existing file)
    python -P validation/v2/freeze_manifest.py --check    # fail on any drift
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RFC_REL = "docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md"
APPROVAL_REL = "closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json"
MANIFEST_REL = "closure-evidence/v2/v2.1/AISEF-V2-FREEZE-MANIFEST.json"
#: The 2.0 manifest: history, never written here. HISTORY_BLOB is its git blob at HISTORY_TAG (`git rev-parse
#: v2.0.0:<path>`, asserted against the tag by tests/v2/p0/test_freeze_manifest.py), pinned so that a tree without git
#: objects — a mutation run's copy — checks the same history.
HISTORY_MANIFEST_REL = "closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json"
HISTORY_TAG, HISTORY_BLOB = "v2.0.0", "cc609ebf5e0f961bccebbc943cc163d0fc9b838a"
#: Approved amendments, oldest first — the architecture-exception mechanism. Each binds the record it amends (by
#: sha256), its exception record (by sha256) and before/after digests. The original approval record never changes.
AMENDMENTS = ("closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-001.json",
              "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-002.json",
              "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-003.json",
              "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-005.json",  # V2-004 was superseded, never applied
              "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-006.json",
              "closure-evidence/v2/v2.1/AISEF-V2-RFC-AMENDMENT-V2-007.json")
EXCEPTIONS = ("closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-001.json",
              "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-002.json",
              "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-003.json",
              "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-005.json",
              "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-006.json",
              "closure-evidence/v2/v2.1/ARCHITECTURE-EXCEPTION-V2-007.json")
#: Every file the baseline is identified from.
BASELINE_FILES = (RFC_REL, APPROVAL_REL, MANIFEST_REL, HISTORY_MANIFEST_REL, *AMENDMENTS, *EXCEPTIONS)

# The digest rules are stated in the approval record; these constants must match them (asserted by the tests).
NORMATIVE_MARK = "## 1. Executive architecture decision"
FREEZE_TABLE_BEGIN = "## Normative freeze table"
FREEZE_TABLE_END = "## Adversarial regression cases"
FROZEN_IDS = [f"F{i}" for i in range(1, 12)]

_ROW = re.compile(r"^\| \*\*(F\d+)\*\* \| (.+?) \| (.+?) \|$")


class FreezeError(Exception):
    """The architecture baseline cannot be identified."""


def _section(text: str, begin: str, end: str | None) -> str:
    if text.count(begin) != 1:
        raise FreezeError(f"marker {begin!r} must occur exactly once, found {text.count(begin)}")
    i = text.index(begin)
    if end is None:
        return text[i:]
    if text.count(end) != 1:
        raise FreezeError(f"marker {end!r} must occur exactly once, found {text.count(end)}")
    j = text.index(end)
    if j <= i:
        raise FreezeError(f"marker {end!r} precedes {begin!r}")
    return text[i:j]


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def normative_digest(text: str) -> str:
    return sha256(_section(text, NORMATIVE_MARK, None))


def freeze_table_digest(text: str) -> str:
    return sha256(_section(text, FREEZE_TABLE_BEGIN, FREEZE_TABLE_END))


def freeze_items(text: str) -> list[dict]:
    table = _section(text, FREEZE_TABLE_BEGIN, FREEZE_TABLE_END)
    items = []
    for line in table.splitlines():
        m = _ROW.match(line)
        if m:
            items.append({"id": m.group(1), "row_sha256": sha256(line),
                          "item": m.group(2).strip(), "why": m.group(3).strip()})
    return items


def _lf_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def lineage(root: pathlib.Path = ROOT) -> tuple[dict, list[dict], list[str]]:
    """The effective approved digests after every amendment, the lineage itself, and every broken link."""
    approval = json.loads((root / APPROVAL_REL).read_bytes().replace(b"\r\n", b"\n"))
    eff = {"rfc_normative_digest": approval["rfc"]["rfc_normative_digest"],
           "freeze_table_digest": approval["freeze_table"]["digest_sha256"]}
    links = [{"record": APPROVAL_REL, "sha256": _lf_sha(root / APPROVAL_REL), **eff}]
    problems: list[str] = []
    for rel in AMENDMENTS:
        prev = links[-1]
        a = json.loads((root / rel).read_bytes().replace(b"\r\n", b"\n"))
        if (a["amends"]["path"], a["amends"]["sha256"]) != (prev["record"], prev["sha256"]):
            problems.append(f"{rel} does not amend {prev['record']} at its current sha256")
        exc = root / a["exception"]["path"]
        if not exc.exists() or _lf_sha(exc) != a["exception"]["sha256"]:
            problems.append(f"{rel}: exception record {a['exception']['path']} is missing or changed")
        for key in ("rfc_normative_digest", "freeze_table_digest"):
            if a[key]["before"] != eff[key]:
                problems.append(f"{rel}: {key} 'before' is not the previously approved digest")
            eff[key] = a[key]["after"]
        links.append({"record": rel, "sha256": _lf_sha(root / rel), "exception": a["exception"]["path"],
                      "frozen_items_changed": a["frozen_items_changed"], **eff})
    return eff, links, problems


def build(root: pathlib.Path = ROOT) -> dict:
    text = (root / RFC_REL).read_text(encoding="utf-8")
    # The committed (LF) bytes: a Windows autocrlf checkout of the same record must give the same identity.
    approval_bytes = (root / APPROVAL_REL).read_bytes().replace(b"\r\n", b"\n")
    approval = json.loads(approval_bytes)
    items = freeze_items(text)
    effective, links, _ = lineage(root)
    return {
        "manifest": "AISEF V2 — ARCHITECTURE FREEZE MANIFEST",
        "work_package": "WP-0.1",
        "rfc": RFC_REL,
        "approval_record": APPROVAL_REL,
        "approval_record_sha256": hashlib.sha256(approval_bytes).hexdigest(),
        "rfc_normative_digest": normative_digest(text),
        "freeze_table_digest": freeze_table_digest(text),
        "approved_rfc_normative_digest": effective["rfc_normative_digest"],
        "approved_freeze_table_digest": effective["freeze_table_digest"],
        "approval_lineage": links,
        "history": {"path": HISTORY_MANIFEST_REL, "sha256": _lf_sha(root / HISTORY_MANIFEST_REL), "tag": HISTORY_TAG,
                    "rule": f"the 2.0 manifest (the V2-006 freeze) is history: byte-identical to its blob at "
                            f"{HISTORY_TAG}, its lineage the head of this one"},
        "reviewed_commit": approval["rfc"]["reviewed_commit"],
        "frozen_items": items,
        "rules": {
            "normative_body": f"sha256 from {NORMATIVE_MARK!r} to EOF",
            "freeze_table": f"sha256 from {FREEZE_TABLE_BEGIN!r} up to {FREEZE_TABLE_END!r}",
            "non_normative": "everything above the normative mark is status metadata and is not digested",
        },
    }


def history_problems(root: pathlib.Path = ROOT) -> list[str]:
    """The 2.0 manifest is history: its LF bytes are its blob at HISTORY_TAG, it recorded no drift, and the lineage it
    froze is the head of the current one."""
    path = root / HISTORY_MANIFEST_REL
    if not path.exists():
        return [f"{HISTORY_MANIFEST_REL} is missing"]
    data = path.read_bytes().replace(b"\r\n", b"\n")
    out = []
    if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != HISTORY_BLOB:
        out.append(f"{HISTORY_MANIFEST_REL} differs from its blob at {HISTORY_TAG}: the 2.0 freeze is history, "
                   "never rewritten")
    old = json.loads(data)
    if (old.get("rfc_normative_digest"), old.get("freeze_table_digest")) \
            != (old.get("approved_rfc_normative_digest"), old.get("approved_freeze_table_digest")):
        out.append(f"{HISTORY_MANIFEST_REL} records a drifted baseline")
    frozen = old.get("approval_lineage") or []
    if not frozen or lineage(root)[1][:len(frozen)] != frozen:
        out.append(f"the lineage {HISTORY_MANIFEST_REL} froze is not the head of the current lineage")
    return out


def check(root: pathlib.Path = ROOT) -> list[str]:
    problems: list[str] = []
    try:
        m = build(root)
    except (FreezeError, OSError, KeyError, json.JSONDecodeError) as exc:
        return [f"cannot identify the architecture baseline: {exc}"]
    problems += lineage(root)[2]
    if m["rfc_normative_digest"] != m["approved_rfc_normative_digest"]:
        problems.append("RFC normative body differs from the approved content")
    if m["freeze_table_digest"] != m["approved_freeze_table_digest"]:
        problems.append("F1-F11 freeze table differs from the approved content")
    ids = [i["id"] for i in m["frozen_items"]]
    if ids != FROZEN_IDS:
        problems.append(f"frozen items must be exactly {FROZEN_IDS}, found {ids}")
    committed = root / MANIFEST_REL
    if not committed.exists():
        problems.append(f"{MANIFEST_REL} is missing")
    elif committed.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") != render(m):
        problems.append(f"{MANIFEST_REL} is stale: regenerate it")
    return problems + history_problems(root)


def render(m: dict) -> str:
    return json.dumps(m, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
        for p in problems:
            print(f"FAIL  {p}")
        print("freeze manifest: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    m = build()
    if m["rfc_normative_digest"] != m["approved_rfc_normative_digest"] \
            or m["freeze_table_digest"] != m["approved_freeze_table_digest"] or lineage(ROOT)[2] \
            or history_problems(ROOT):
        print("REFUSED: the RFC at HEAD does not match the approval record; a manifest will not bless drift")
        return 1
    if MANIFEST_REL == HISTORY_MANIFEST_REL or not MANIFEST_REL.startswith("closure-evidence/v2/v2.1/"):
        print(f"REFUSED: {MANIFEST_REL} is not a 2.1 path; a 2.0 record is never rewritten")
        return 1
    out = ROOT / MANIFEST_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out, "x", encoding="utf-8") as f:
            f.write(render(m))
    except FileExistsError:
        print(f"REFUSED: {MANIFEST_REL} exists; a record is never overwritten (remove it to re-bind)")
        return 1
    print(f"wrote {MANIFEST_REL}: {len(m['frozen_items'])} frozen items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
