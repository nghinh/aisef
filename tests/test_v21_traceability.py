"""The 2.1 traceability table holds at its head, and its checker names each kind of wrong cell
(validation/v21/traceability_check.py)."""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("traceability_check", ROOT / "validation" / "v21" / "traceability_check.py")
TC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TC)


class Traceability(unittest.TestCase):
    def setUp(self):
        self.table = json.loads((ROOT / TC.TABLE).read_text(encoding="utf-8"))
        self.doc = (ROOT / TC.DOC).read_text(encoding="utf-8")

    def test_the_committed_table_and_its_document_hold_at_the_head(self):
        self.assertEqual(TC.check(self.table, ROOT, None, None, self.doc), [])

    def test_each_kind_of_wrong_cell_is_named(self):
        t = copy.deepcopy(self.table)
        rows = {r["id"]: r for r in t["rows"]}
        rows["P-V2-01"]["commits"][0]["paths"].append("aisef2/no/such/file.py")
        rows["P-V2-02"]["commits"].append({"sha": "0" * 40, "paths": []})
        rows["P-V2-04"]["reproducers"].append("tests/v2/test_v21_inputs.py::Endpoint::test_that_was_never_written")
        rows["P-V2-06"]["report_items"]["B1"] = "M5"
        rows["P-V2-09"]["upstream"][0]["label"] = "README"
        rows["P-V2-11"]["refs"].append({"path": "aisef2/app/usage.py", "contains": "unknown cost is 0"})
        rows["R-P0-1"]["item"] += " (edited)"
        rows["P-5.3a"]["decision"] = "adopted"
        rows["P-V2-03"]["commits"].append({"sha": "f006d3d", "paths": []})       # 2.0.1, not under the 2.1 head
        rows["P-V2-07"]["refs"].append({"path": "pyproject.toml", "same_as": "610a593"})
        rows["P-V2-10"]["refs"].append({"path": "aisef2/app/usage.py", "lacks": "NO_SIDE_RETRY_COUNTER"})
        rows["P-V2-13"]["refs"].append({"path": "aisef2/app/usage.py", "exists": False})
        expected = {"P-V2-01": "does not touch aisef2/no/such/file.py", "P-V2-02": "is not in this clone",
                    "P-V2-04": "no method test_that_was_never_written", "P-V2-06": "REPORT §2 gives B1 M3",
                    "P-V2-09": "the row says README", "P-V2-11": "does not contain",
                    "R-P0-1": "not verbatim", "open item": "P-5.3a is adopted",
                    "P-V2-03": "is not an ancestor", "P-V2-07": "is not the same as at 610a593",
                    "P-V2-10": "contains 'NO_SIDE_RETRY_COUNTER'", "P-V2-13": "usage.py at c9c736f"}
        problems = TC.check(t, ROOT, None, None, self.doc.replace("adopted 25", "adopted 26"))
        for rid, text in expected.items():
            self.assertTrue(any(p.startswith(rid) and text in p for p in problems), (rid, text, problems))
        self.assertTrue(any("generated block" in p for p in problems))

    def test_report_levels_expand_ranges_and_per_item_levels(self):
        text = ("# R\n\n## 2. Levels\n\n| # | x | Mức |\n|---|---|---|\n| A3–A5 | x | M4 (A5), M3 (A3, A4) |\n"
                "| A9–A10 | x | M4 (build + `packaging_check` local) |\n| F | x | **M6** |\n\n## 3. Next\n| B1 | x | M1 |\n")
        self.assertEqual(TC.report_levels(text), {"A3": "M3", "A4": "M3", "A5": "M4", "A9": "M4", "A10": "M4", "F": "M6"})


if __name__ == "__main__":
    unittest.main()
