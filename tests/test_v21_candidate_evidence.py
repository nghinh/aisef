"""The candidate evidence tool keeps every control (validation/v21/candidate_evidence.py): it writes a new directory
outside the repository only (a set inside it changed what repository-scanning generators derive — measured), never
over a sealed record; nothing that decides a release or a test reads a candidate set; a sealed record is
byte-identical after a run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("candidate_evidence", ROOT / "validation" / "v21" / "candidate_evidence.py")
CE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CE)
FAST = ["closure-evidence/v2/P2-STATIC-ADMISSION.json", "closure-evidence/v2/release/AUTHORITY-INVENTORY.json"]


class CandidateEvidence(unittest.TestCase):
    def test_a_run_writes_its_copies_and_manifest_and_leaves_every_sealed_record_byte_identical(self):
        before = {r: hashlib.sha256((ROOT / r).read_bytes()).hexdigest() for r in CE.GENERATED}
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "set"
            m = CE.generate(out, FAST)
            self.assertEqual(sorted(m["artifacts"]), sorted(FAST))
            for rel in FAST:
                row = m["artifacts"][rel]
                self.assertTrue(row["generated"], row)
                self.assertEqual(row["sha256"], hashlib.sha256((out / rel).read_bytes()).hexdigest())
            self.assertEqual(json.loads((out / CE.MANIFEST).read_text())["status"][:9], "CANDIDATE")
            self.assertIn("not_generated", m)
        self.assertEqual({r: hashlib.sha256((ROOT / r).read_bytes()).hexdigest() for r in CE.GENERATED}, before)

    def test_it_refuses_an_existing_set_any_place_inside_the_repository_and_an_unknown_record(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                CE.generate(pathlib.Path(t), FAST)                                   # exists
        for place in (ROOT / "closure-evidence" / "v2.1-candidate" / "x", ROOT / "closure-evidence" / "v2" / "x",
                      ROOT / "docs" / "x"):                                          # anywhere inside the repository
            with self.assertRaises(SystemExit):
                CE.generate(place, FAST)
            self.assertFalse(place.exists())
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                CE.generate(pathlib.Path(t) / "set", ["closure-evidence/v2/RELEASE-DECISIONS.json"])

    def test_nothing_that_decides_reads_a_candidate_set(self):
        readers = [p for d in ("aisef", "aisef2", "validation", "tests") for p in (ROOT / d).rglob("*.py")
                   if p.name not in ("candidate_evidence.py", "test_v21_candidate_evidence.py")
                   and re.search(r"v2\.1-candidate", p.read_text(encoding="utf-8", errors="replace"))]
        self.assertEqual(readers, [])

    def test_differing_paths_names_where_two_documents_differ(self):
        self.assertEqual(CE.differing_paths({"a": 1, "b": {"c": [1, 2]}}, {"a": 1, "b": {"c": [1, 3]}, "d": 0}),
                         ["b.c[1]", "d"])
        self.assertEqual(CE.differing_paths({"x": [1]}, {"x": [1, 2]}), ["x[len 1 vs 2]"])


if __name__ == "__main__":
    unittest.main()
