"""V2.1 release: the authority inventory of the release tree — validation/v2/old_path_audit.py's inventory, written
beside the release records instead of over the sealed P6 one or the released 2.0 one.

    python -P validation/qualification/release_inventory.py --write   # -> closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json (a new file)
    python -P validation/qualification/release_inventory.py --check   # both directions + the six static proofs + the 2.0 history

closure-evidence/v2/P6-AUTHORITY-INVENTORY.json stays as sealed: it is the P6 tree's inventory. The 2.0 release's
(RELEASE_2_0_REL) stays as released: history, byte-identical to its pin and to its blob at tag v2.0.0 (pinned as
well, so a tree without git objects, such as a mutation run's copy, checks the same history). Each release adds
authorities (2.0 the product runtime, aisef2/app; 2.1 bundle_cli.migrate and review_verify.verify, whose limits
validation/qualification/authority_limits.py enforces), so its tree is audited against its own inventory, by the same
audit: `old_path_audit.compare` (reality vs the committed rows, both directions) and `old_path_audit.proofs`.

The release inventory is content-addressed: `INVENTORY_SHA256` pins its LF-normalised sha256, and check() refuses a
file with any other digest before it compares. `--write` creates the file exclusively (never over one: a new
inventory is a deleted file regenerated, in the commit that pins it) and never rewrites this source: it prints the
new digest, and the constant is updated by hand in the same commit as the inventory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY_REL = "closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json"
#: the LF-normalised sha256 of INVENTORY_REL: the one release inventory this tree is audited against
INVENTORY_SHA256 = "9eaf87693c079b64fb7282a4459977d58ca120fb3569fa58a658fac3ff6eb51a"
#: the 2.0 release's inventory, history: never rewritten, byte-identical to this pin and to its blob at tag v2.0.0
RELEASE_2_0_REL = "closure-evidence/v2/release/AUTHORITY-INVENTORY.json"
RELEASE_2_0_SHA256 = "6dba7d62cae22d505033d09ca26fcb8ad4e79df49491a9aa519a6f75de51015c"
TAG_2_0 = "ca2631374602da45dae75b7f6907ff4729d0b2f7"     # tag v2.0.0, by its commit (a tag can be moved)
#: its git blob at TAG_2_0 (`git rev-parse v2.0.0:<RELEASE_2_0_REL>`, asserted against the tag by
#: tests/v2/test_v21_authority_limits.py, outside every mutation kill set): history_problems needs no git
RELEASE_2_0_BLOB = "97f680948a3c2d1553100130b299905f6dc5d942"


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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
    problems = []
    if (got := digest(path)) != INVENTORY_SHA256:
        problems.append(f"the release inventory is not the content-addressed one: {INVENTORY_REL} has sha256 {got}, "
                        f"release_inventory.INVENTORY_SHA256 pins {INVENTORY_SHA256}")
    inv = opa.inventory(root)
    problems += opa.compare(json.loads(path.read_text(encoding="utf-8")), inv)
    pr = opa.proofs(root, inv)
    problems += [f"PROOF {name} does not hold statically" for name in opa.PROOFS if not pr[name]["static"]]
    return problems


def history_problems(root: pathlib.Path = ROOT) -> list[str]:
    """The 2.0 release inventory is history: its bytes (LF-normalised) are RELEASE_2_0_SHA256 and RELEASE_2_0_BLOB,
    its blob at v2.0.0."""
    path = root / RELEASE_2_0_REL
    if not path.exists():
        return [f"{RELEASE_2_0_REL} (the 2.0 release inventory, history) is missing"]
    data = path.read_bytes().replace(b"\r\n", b"\n")
    problems = []
    if (got := hashlib.sha256(data).hexdigest()) != RELEASE_2_0_SHA256:
        problems.append(f"the 2.0 release inventory is history and was changed: {RELEASE_2_0_REL} has sha256 {got}, "
                        f"release_inventory.RELEASE_2_0_SHA256 pins {RELEASE_2_0_SHA256}")
    if (blob := hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()) != RELEASE_2_0_BLOB:
        problems.append(f"{RELEASE_2_0_REL} is not its blob at v2.0.0 ({TAG_2_0[:12]}): git blob {blob}, "
                        f"release_inventory.RELEASE_2_0_BLOB pins {RELEASE_2_0_BLOB}")
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
        (ROOT / INVENTORY_REL).parent.mkdir(parents=True, exist_ok=True)
        try:
            with (ROOT / INVENTORY_REL).open("x", encoding="utf-8") as fh:
                fh.write(opa.render(inv))
        except FileExistsError:
            print(f"release inventory: FAIL ({INVENTORY_REL} exists: --write creates it and never writes over one)")
            return 1
        print(f"wrote {INVENTORY_REL}: {inv['summary']}")
        print(f"sha256 {digest(ROOT / INVENTORY_REL)}: set release_inventory.INVENTORY_SHA256 to it in the same commit")
    problems = check() + history_problems()
    for p in problems:
        print(f"FAIL  {p}")
    print("release inventory: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
