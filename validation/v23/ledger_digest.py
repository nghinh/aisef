"""The canonical ruling digest of a DRAFT owner-ledger entry (ROUND-AUTH seq 13 drafts, docs/v2.3/drafts/).

    python3 -P validation/v23/ledger_digest.py FILE.md [FILE.md ...]

digest = sha256 of json.dumps({seq, id, decision, subject_to, cost}, sort_keys=True, separators=(",", ":"),
ensure_ascii=False) encoded UTF-8 — the ruling's content only: `authority` (the owner's own words), `approver` and
any later field are outside it, so the owner can quote their approval without moving the digest of what they approve.
Every ```json block of each file is one entry; a block missing a ruling field is refused (exit 1).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

FIELDS = ("seq", "id", "decision", "subject_to", "cost")
_BLOCK = re.compile(r"^```json\n(.*?)^```", re.M | re.S)


def canonical(entry: dict) -> bytes:
    missing = [k for k in FIELDS if k not in entry]
    if missing:
        raise KeyError(f"not a ruling entry: missing {missing}")
    return json.dumps({k: entry[k] for k in FIELDS}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest(entry: dict) -> str:
    return hashlib.sha256(canonical(entry)).hexdigest()


def entries(markdown: str) -> list[dict]:
    return [json.loads(b) for b in _BLOCK.findall(markdown.replace("\r\n", "\n"))]


def main(argv: list[str] | None = None) -> int:
    rc = 0
    for f in (sys.argv[1:] if argv is None else argv):
        try:
            found = entries(pathlib.Path(f).read_text(encoding="utf-8"))
            if not found:
                raise ValueError("no ```json block")
            for e in found:
                print(f"{digest(e)}  seq {e['seq']} {e['id']}  {f}")
        except (OSError, ValueError, KeyError) as e:
            print(f"REFUSED  {f}: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
