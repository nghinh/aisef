"""V2.0 release: the authority inventory of the release tree — validation/v2/old_path_audit.py's inventory, written
beside the release records instead of over the sealed P6 one.

    python -P validation/qualification/release_inventory.py --write   # -> closure-evidence/v2/release/AUTHORITY-INVENTORY.json
    python -P validation/qualification/release_inventory.py --check   # both directions + the six static proofs

closure-evidence/v2/P6-AUTHORITY-INVENTORY.json stays as sealed: it is the P6 tree's inventory. The release adds
authorities (the product runtime, aisef2/app), so its tree is audited against its own inventory, by the same audit:
`old_path_audit.compare` (reality vs the committed rows, both directions) and `old_path_audit.proofs`.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY_REL = "closure-evidence/v2/release/AUTHORITY-INVENTORY.json"


def _opa():
    spec = importlib.util.spec_from_file_location("aisef_v2_old_path_audit", ROOT / "validation/v2/old_path_audit.py")
    mod = sys.modules.get(spec.name) or importlib.util.module_from_spec(spec)
    if spec.name not in sys.modules:
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    return mod


def check(root: pathlib.Path = ROOT) -> list[str]:
    opa = _opa()
    path = root / INVENTORY_REL
    if not path.exists():
        return [f"{INVENTORY_REL} is missing: generate it"]
    inv = opa.inventory(root)
    problems = opa.compare(json.loads(path.read_text(encoding="utf-8")), inv)
    pr = opa.proofs(root, inv)
    problems += [f"PROOF {name} does not hold statically" for name in opa.PROOFS if not pr[name]["static"]]
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    opa = _opa()
    if "--write" in argv:
        inv = opa.inventory()
        bad = [r["id"] for r in inv["rows"] if r["disposition"] not in opa.DISPOSITIONS]
        if bad:
            print(f"release inventory: FAIL (unclassifiable {bad[:5]}, not written)")
            return 1
        (ROOT / INVENTORY_REL).write_text(opa.render(inv), encoding="utf-8")
        print(f"wrote {INVENTORY_REL}: {inv['summary']}")
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("release inventory: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
