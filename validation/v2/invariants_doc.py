"""docs/implementation/v2/INVARIANTS-V2.md from the invariant registry (WP-5.5), with a --check twin.

    python -P validation/v2/invariants_doc.py            # write the document
    python -P validation/v2/invariants_doc.py --check    # exit 1 when the document drifted from the registry
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.invariants import registry as reg  # noqa: E402


def check(root: pathlib.Path = ROOT) -> list[str]:
    path = root / reg.DOC_REL
    if not path.exists():
        return [f"{reg.DOC_REL} is missing"]
    if path.read_text(encoding="utf-8") != reg.render():
        return [f"{reg.DOC_REL} drifted from aisef2/invariants/registry.py"]
    return []


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
        for p in problems:
            print(f"FAIL  {p}")
        print("invariants document: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    (ROOT / reg.DOC_REL).write_text(reg.render(), encoding="utf-8")
    print(f"wrote {reg.DOC_REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
