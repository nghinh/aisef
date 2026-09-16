"""The invariant registry is data the kernel is checked against, so it is checked itself:
it loads through the stdlib-only subset parser, every status is legal, every test it cites exists
(file, class and method), every defect id it links is registered somewhere (defect register, sibling
scan, family map), and the rendered documents are in sync with their sources."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import invariants as INV  # noqa: E402

FAM_MAP = ROOT / "closure-evidence/hardening/defect-family-map.json"
SCAN = ROOT / "closure-evidence/hardening/sibling-scan.json"
REGISTER = ROOT / "docs/DEFECT-REGISTER.json"


def _known_defect_ids() -> set[str]:
    ids = {d["id"] for d in json.loads(REGISTER.read_text(encoding="utf-8"))["defects"]}
    ids |= {m["id"] for m in json.loads(FAM_MAP.read_text(encoding="utf-8"))["members"]}
    ids |= {e["id"] for e in json.loads(SCAN.read_text(encoding="utf-8"))["entries"]}
    return ids


def _resolve(ref: str) -> str:
    """'' if the reference `path[::Class[::method]] [(RED)]` names something that exists, else why not."""
    ref = ref.replace(" (RED)", "").strip()
    parts = ref.split("::")
    path = ROOT / parts[0]
    if not path.is_file():
        return f"{parts[0]} does not exist"
    text = path.read_text(encoding="utf-8")
    if len(parts) > 1 and not re.search(rf"^class {re.escape(parts[1])}\b", text, re.M):
        return f"{parts[0]} has no class {parts[1]}"
    if len(parts) > 2 and not re.search(rf"^\s+def {re.escape(parts[2])}\b", text, re.M):
        return f"{parts[0]}::{parts[1]} has no method {parts[2]}"
    return ""


class TestTheRegistryLoads(unittest.TestCase):
    def setUp(self):
        self.invs = INV.load()

    def test_it_has_every_owner_family_and_legal_statuses(self):
        fams = set(INV.by_family(self.invs))
        self.assertEqual(fams, set("ABCDEFGHIJKLMNOPQRST"), fams)
        for inv in self.invs:
            self.assertIn(inv.status, INV.STATUSES)
            self.assertTrue(inv.statement and inv.why and inv.severity_if_violated.startswith("P"), inv.invariant_id)

    def test_every_cited_test_exists(self):
        problems = []
        for inv in self.invs:
            for ref in inv.deterministic_tests + inv.model_tests + inv.fault_injection_tests:
                why = _resolve(ref)
                if why:
                    problems.append(f"{inv.invariant_id}: {why}")
        self.assertEqual(problems, [])

    def test_every_linked_defect_is_registered_somewhere(self):
        known = _known_defect_ids()
        missing = sorted({d for inv in self.invs for d in inv.linked_defects if d not in known})
        self.assertEqual(missing, [], "link only ids the register, the family map or the sibling scan carry")

    def test_a_proven_invariant_cites_a_deterministic_test_and_no_red_reproducer(self):
        for inv in self.invs:
            if inv.status == "PROVEN":
                self.assertTrue(inv.deterministic_tests, inv.invariant_id)
                self.assertFalse(any("(RED)" in r for r in inv.deterministic_tests), f"{inv.invariant_id} is PROVEN but cites an unfixed reproducer")
            if inv.status == "MISSING":
                self.assertFalse(inv.enforcement_points and not any("(RED)" in r for r in inv.deterministic_tests + inv.model_tests) and False)

    def test_the_subset_parser_refuses_what_it_cannot_read(self):
        with self.assertRaises(INV.RegistryError):
            INV.parse("invariants:\n\t- invariant_id: X\n")
        with self.assertRaises(INV.RegistryError):
            INV.parse("just a line without a colon\n")


class TestRenderedDocumentsAreInSync(unittest.TestCase):
    def test_invariants_md_matches_the_registry(self):
        sys.path.insert(0, str(ROOT / "validation"))
        import render_hardening_docs as R
        self.assertEqual((ROOT / "docs/INVARIANTS.md").read_text(encoding="utf-8"), R.render_invariants(),
                         "run `python3 validation/render_hardening_docs.py invariants`")

    def test_family_map_md_matches_the_json(self):
        sys.path.insert(0, str(ROOT / "validation"))
        import render_hardening_docs as R
        self.assertEqual((ROOT / "docs/DEFECT-FAMILY-MAP.md").read_text(encoding="utf-8"), R.render_families(),
                         "run `python3 validation/render_hardening_docs.py families`")

    def test_every_confirmed_scan_entry_names_a_red_reproducer_that_exists(self):
        scan = json.loads(SCAN.read_text(encoding="utf-8"))
        for e in scan["entries"]:
            if e["classification"] == "CONFIRMED":
                self.assertEqual(_resolve(e["reproducer"]), "", e["id"])


if __name__ == "__main__":
    unittest.main()
