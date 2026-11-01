"""ROADMAP-2.2 G1 — the stimulus serve-surface tripwire. The needles are the contracts' own stimulus/observable
content; a clean tree scans CLEAN, the project's own bundle (or a copied stimulus) in the served tree is a LEAK,
a poisoned prompt refuses the session, a public-facts collision is dropped BY NAME, and a contract too small to
scan is named UNSCANNED — never silently passed, never a refusal by itself. The report and every refusal name the
contract and the length, NEVER the sealed value."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from aisef2.app import tripwire

STIMULUS = {"scenario": [["add", 223344, 556677], ["expect", "the-grand-total-of-the-ledger"]]}
OBSERVABLE = {"returns": "a-ledger-total-beyond-any-doubt", "within_s": 10}


def project(facts_text: str = "R-1 adds numbers", stimulus=None, observable=None):
    spec = SimpleNamespace(contract_id="BC-ADD",
                           probe_input={"stimulus": stimulus or STIMULUS, "observable": observable or OBSERVABLE,
                                        "subject": "app.calc:add", "subject_absence": "REQUIRES_SUBJECT"})
    return SimpleNamespace(name="calc", description="a calculator", requirements_path="docs/requirements.md",
                           product_roots=("app",), facts={"C-1": {"requirement": "R-1", "section": "", "clause": "1",
                                                                  "clause_text": facts_text, "subject": "app.calc:add"}},
                           specs={"PPS-1": spec}, contracts={"BC-ADD": object()},
                           plan=SimpleNamespace(plan_hash="a" * 64))


class Needles(unittest.TestCase):
    def test_needles_cover_stimulus_and_observable_and_hold_no_short_value(self):
        wire = tripwire.needles_of(project())
        self.assertTrue(wire["needles"])
        self.assertTrue(all(len(n) >= tripwire.MIN_NEEDLE for n in wire["needles"]))
        self.assertTrue(all(c == "BC-ADD" for c in wire["needles"].values()))
        self.assertTrue(any("the-grand-total-of-the-ledger" in n for n in wire["needles"]))
        self.assertTrue(any("a-ledger-total-beyond-any-doubt" in n for n in wire["needles"]))
        self.assertEqual((wire["dropped"], wire["unscanned"]), ([], []))

    def test_a_public_facts_collision_is_dropped_by_name(self):
        leaky = project(facts_text="the clause even quotes the-grand-total-of-the-ledger in public")
        wire = tripwire.needles_of(leaky)
        self.assertNotIn("the-grand-total-of-the-ledger", wire["needles"])
        self.assertTrue(any(d.startswith("BC-ADD:") for d in wire["dropped"]), wire["dropped"])

    def test_a_contract_too_small_to_scan_is_named_unscanned(self):
        small = project(stimulus={"a": 2}, observable={"r": 5})
        wire = tripwire.needles_of(small)
        self.assertEqual(wire["needles"], {})
        self.assertEqual(wire["unscanned"], ["BC-ADD"])


class ScanRepo(unittest.TestCase):
    def setUp(self):
        self.project = project()
        self.wire = tripwire.needles_of(self.project)
        self.repo = pathlib.Path(tempfile.mkdtemp(prefix="aisef-tw-"))
        (self.repo / "app").mkdir()
        (self.repo / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    def test_a_clean_tree_scans_clean_and_the_report_names_its_bounds(self):
        report = tripwire.scan_repo(self.repo, self.project, self.wire)
        self.assertEqual((report["verdict"], report["hits"]), ("CLEAN", []))
        self.assertGreaterEqual(report["files_scanned"], 1)
        self.assertIn("not confinement", report["statement"])
        for key in ("needles", "dropped", "unscanned"):
            self.assertIn(key, report)

    def test_the_projects_own_bundle_in_the_tree_is_a_hit_and_a_foreign_one_is_not(self):
        mine = {"format": "aisef-v2-project/1", "contracts": [{"id": "BC-ADD"}], "plan": {"plan_hash": "b" * 64}}
        (self.repo / "bundle.json").write_text(json.dumps(mine), encoding="utf-8")
        report = tripwire.scan_repo(self.repo, self.project, self.wire)
        self.assertEqual(report["verdict"], "LEAK")
        self.assertTrue(any(h["file"] == "bundle.json" for h in report["hits"]))
        foreign = {"format": "aisef-v2-project/1", "contracts": [{"id": "BC-OTHER"}],
                   "plan": {"plan_hash": "c" * 64}}
        (self.repo / "bundle.json").write_text(json.dumps(foreign), encoding="utf-8")
        report = tripwire.scan_repo(self.repo, self.project, self.wire)
        self.assertNotIn("bundle.json", {h["file"] for h in report["hits"]})

    def test_a_copied_fragment_is_a_hit_naming_the_contract_never_the_value(self):
        needle = max(self.wire["needles"], key=len)
        (self.repo / "app" / "notes.txt").write_text(f"seen in a run: {needle}\n", encoding="utf-8")
        report = tripwire.scan_repo(self.repo, self.project, self.wire)
        self.assertEqual(report["verdict"], "LEAK")
        hit = next(h for h in report["hits"] if h["file"] == "app/notes.txt")
        self.assertEqual(hit["contract"], "BC-ADD")
        self.assertNotIn(needle, json.dumps(report["hits"]))        # hits carry id + length, never the value
        self.assertNotIn(needle, tripwire.refusal(report["hits"], "x"))

    def test_the_json_escaped_spelling_is_a_hit_too(self):
        needle = 'scenario "x": the first step'
        escaped = json.dumps(needle, ensure_ascii=False)[1:-1]
        self.assertNotEqual(escaped, needle)
        self.assertEqual(tripwire.scan_text(f"log: {escaped}", {needle: "BC-X"})[0]["contract"], "BC-X")


class ServeBoundary(unittest.TestCase):
    def test_a_poisoned_prompt_refuses_the_session_before_anything_starts(self):
        from aisef2.app import client
        needles = {"THE-SEALED-STIMULUS-CONTENT": "BC-1"}
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="aisef-tw-"))
        exe = tmp / "opencode"
        exe.write_bytes(b"x")
        budget = client.Budget({k: 9 for k in client.Budget.KEYS}, {k: 0 for k in client.Budget.KEYS}, tmp / "logs")
        with self.assertRaises(client.SessionRefused) as c:
            client.session("s", "fix it: THE-SEALED-STIMULUS-CONTENT", str(tmp), tmp / "logs" / "s.jsonl", 5.0,
                           model="p/m", env={"PATH": "/nowhere"}, budget=budget, turn_cap=3, exe=str(exe),
                           needles=needles)
        self.assertIn("BC-1", str(c.exception))
        self.assertNotIn("THE-SEALED-STIMULUS-CONTENT", str(c.exception).replace(
            "fix it: THE-SEALED-STIMULUS-CONTENT", ""))     # the refusal itself never echoes the value
        self.assertFalse((tmp / "logs" / "s.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
