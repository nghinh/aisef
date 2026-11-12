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
from unittest import mock

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


class B1SurvivorKills(unittest.TestCase):
    """Pinned kills for the v2.2 B1 mutation-campaign survivors in aisef2/app/tripwire.py — each test names the
    mutant descriptor(s) it fails under; all assertions hold on the unmutated tree."""

    def _repo(self):
        proj = project()
        wire = tripwire.needles_of(proj)
        repo = pathlib.Path(tempfile.mkdtemp(prefix="aisef-tw-"))
        (repo / "app").mkdir()
        (repo / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return proj, wire, repo

    def test_bundle_hit_fails_closed_on_marker_bearing_non_bundles(self):
        p = project()
        # L102 returns None / L102 True->False: a marker-bearing unparseable doc refuses rather than guesses
        self.assertIs(tripwire._bundle_hit("aisef-v2-project/1 {not valid json", p), True)
        # L103 Or swapped: the isinstance guard must run before .get() (a JSON list has no .get)
        self.assertIs(tripwire._bundle_hit('["aisef-v2-project/1"]', p), True)
        # L104 returns None / L104 True->False: a marker-bearing dict without a conformant format is still a hit
        self.assertIs(tripwire._bundle_hit('{"note": "aisef-v2-project/1"}', p), True)

    def test_bundle_hit_matches_on_plan_hash_alone(self):
        # L106 conditional negated / L106 string 'plan' emptied / L107 string 'plan_hash' emptied: a bundle
        # identified only by the project's plan_hash (no shared contract id) is a hit
        doc = json.dumps({"format": "aisef-v2-project/1", "contracts": [], "plan": {"plan_hash": "a" * 64}})
        self.assertIs(tripwire._bundle_hit(doc, project()), True)

    def test_canonical_is_sorted_compact_raw_utf8(self):
        # L37 True->False (sort_keys), L37 string ',' emptied, L37 string ':' emptied
        self.assertEqual(tripwire._canonical({"b": 1, "a": 2}), '{"a":2,"b":1}')
        # L37 False->True (ensure_ascii)
        self.assertEqual(tripwire._canonical("é"), '"é"')

    def test_fragments_surface_string_leaves_inside_tuples(self):
        # L46 element 1 dropped: frozen (tuple-shaped) stimuli must still yield their string leaves as needles
        self.assertIn("the-grand-total-of-the-ledger", tripwire._fragments(("the-grand-total-of-the-ledger",)))

    def test_public_text_serves_name_description_and_paths_in_order(self):
        # L56 elements 0-3 dropped, L59 string '\n' emptied
        text = tripwire._public_text(project())
        self.assertTrue(text.startswith("calc\na calculator\ndocs/requirements.md\napp\nR-1\n"), text)

    def test_needle_iteration_order_is_sorted(self):
        # L75 sorted() -> list(): needle insertion order feeds persisted, digested hit lists
        wire = tripwire.needles_of(project())
        self.assertGreaterEqual(len(wire["needles"]), 5)
        self.assertEqual(list(wire["needles"]), sorted(wire["needles"]))

    def test_dropped_entries_are_fully_named_and_sorted(self):
        # L77 string suffix emptied: the full explanation, by name, is the documented contract
        leaky = project(facts_text="the clause even quotes the-grand-total-of-the-ledger in public")
        self.assertEqual(tripwire.needles_of(leaky)["dropped"],
                         ["BC-ADD: a 29-char needle occurs in the bundle's public text"])
        # L83 first sorted() -> list(): many distinct dropped entries come out sorted, not in hash order
        wide = tripwire.needles_of(project(facts_text="public copy: " + tripwire._canonical(STIMULUS)))
        self.assertGreaterEqual(len(wide["dropped"]), 4)
        self.assertEqual(wide["dropped"], sorted(wide["dropped"]))

    def test_unscanned_contracts_come_out_sorted_by_id(self):
        # L83 second sorted() -> list(): tripwire-blind contracts are named in a stable order
        def tiny(cid):
            return SimpleNamespace(contract_id=cid,
                                   probe_input={"stimulus": {"a": 1}, "observable": {"r": 2},
                                                "subject": "app.calc:add", "subject_absence": "REQUIRES_SUBJECT"})
        p = project()
        p.specs = {f"PPS-{i}": tiny(cid) for i, cid in enumerate(("BC-E", "BC-A", "BC-D", "BC-B", "BC-C"))}
        self.assertEqual(tripwire.needles_of(p)["unscanned"], ["BC-A", "BC-B", "BC-C", "BC-D", "BC-E"])

    def test_scan_text_hit_shape_names_contract_and_length(self):
        # L91 dict entry 1 dropped / L91 string 'needle_chars' emptied
        needle = "the-grand-total-of-the-ledger"
        self.assertEqual(tripwire.scan_text(f"log: {needle}", {needle: "BC-X"}),
                         [{"contract": "BC-X", "needle_chars": len(needle)}])

    def test_scan_text_matches_the_raw_utf8_escaped_spelling(self):
        # L90 False->True: the escaped spelling of a non-ASCII needle must stay in ensure_ascii=False form
        needle = 'scenario "café": the first step'
        escaped = json.dumps(needle, ensure_ascii=False)[1:-1]
        self.assertNotEqual(escaped, needle)
        self.assertEqual(tripwire.scan_text(f"log: {escaped}", {needle: "BC-X"}),
                         [{"contract": "BC-X", "needle_chars": len(needle)}])

    def test_git_trees_are_excluded_from_the_scan(self):
        # L116 string '.git' emptied: a needle inside .git is neither scanned nor counted
        proj, wire, repo = self._repo()
        (repo / ".git").mkdir()
        (repo / ".git" / "leak.txt").write_text(max(wire["needles"], key=len), encoding="utf-8")
        report = tripwire.scan_repo(repo, proj, wire)
        self.assertEqual((report["verdict"], report["files_scanned"]), ("CLEAN", 1))

    def test_undecodable_bytes_scan_clean_instead_of_crashing(self):
        # L122 string 'replace' emptied: the error handler is looked up lazily, only a non-UTF-8 file exposes it
        proj, wire, repo = self._repo()
        (repo / "blob.bin").write_bytes(b"\xff\xfe\x00rawbytes")
        self.assertEqual(tripwire.scan_repo(repo, proj, wire)["verdict"], "CLEAN")

    def test_hits_come_out_in_sorted_file_order_whatever_the_walk_yields(self):
        # L115 sorted() -> list(): the persisted, digested hits list must not depend on scandir order
        proj, wire, repo = self._repo()
        needle = max(wire["needles"], key=len)
        for name in ("zz.txt", "mm.txt", "aa.txt"):
            (repo / name).write_text(needle, encoding="utf-8")
        real_rglob = pathlib.Path.rglob
        def reversed_rglob(self, pattern):
            return iter(sorted(real_rglob(self, pattern), reverse=True))
        with mock.patch.object(pathlib.Path, "rglob", reversed_rglob):
            report = tripwire.scan_repo(repo, proj, wire)
        files = [h["file"] for h in report["hits"]]
        self.assertGreaterEqual(len(set(files)), 3)
        self.assertEqual(files, sorted(files))

    def test_the_bundle_hit_record_shape_is_pinned(self):
        # L127 dict entries 1/2 dropped, strings 'contract' / 'needle_chars' / '(the project bundle itself)' emptied
        proj, wire, repo = self._repo()
        mine = {"format": "aisef-v2-project/1", "contracts": [{"id": "BC-ADD"}], "plan": {"plan_hash": "b" * 64}}
        (repo / "bundle.json").write_text(json.dumps(mine), encoding="utf-8")
        report = tripwire.scan_repo(repo, proj, wire)
        hit = next(h for h in report["hits"] if h["file"] == "bundle.json")
        self.assertEqual(hit, {"file": "bundle.json", "contract": "(the project bundle itself)", "needle_chars": 0})

    def test_refusal_names_file_contract_and_length_for_each_hit(self):
        # L135 'file' / ': contract ' emptied, L136 conditional negated + 'needle_chars'/' ('/' chars)' emptied,
        # L138 lead statement emptied, L139 conditional negated / Gt->LtE (3 hits must not claim an overflow)
        hits = [{"file": "app/notes.txt", "contract": "BC-ADD", "needle_chars": 80},
                {"contract": "BC-1", "needle_chars": 27},
                {"file": "bundle.json", "contract": "(the project bundle itself)", "needle_chars": 0}]
        self.assertEqual(
            tripwire.refusal(hits, "the prompt"),
            "sealed stimulus/observable content would reach the developer via the prompt: "
            "app/notes.txt: contract BC-ADD (80 chars); the prompt: contract BC-1 (27 chars); "
            "bundle.json: contract (the project bundle itself). " + tripwire.FOUND)

    def test_refusal_overflow_marker_appears_only_beyond_five_hits(self):
        # L139 strings ' (+' / ' more)' emptied, and the L139 guard mutants on the 5-hit boundary
        five = [{"file": f"f{i}", "contract": "BC-ADD", "needle_chars": 20} for i in range(5)]
        self.assertNotIn("more)", tripwire.refusal(five, "x"))
        seven = five + [{"file": "f5", "contract": "BC-ADD", "needle_chars": 20},
                        {"file": "f6", "contract": "BC-ADD", "needle_chars": 20}]
        self.assertIn(" (+2 more)", tripwire.refusal(seven, "x"))


if __name__ == "__main__":
    unittest.main()
