"""The 2.1 traceability table holds at its head, and its checker names each kind of wrong cell
(validation/v21/traceability_check.py)."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("traceability_check", ROOT / "validation" / "v21" / "traceability_check.py")
TC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TC)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


class Traceability(unittest.TestCase):
    def setUp(self):
        self.table = json.loads((ROOT / TC.TABLE).read_text(encoding="utf-8"))
        self.doc = (ROOT / TC.DOC).read_text(encoding="utf-8")

    def test_the_committed_table_and_its_document_hold_at_the_head(self):
        """In any clone of the branch: only objects reachable from the head are read by default, and the cells on the
        local 2.0.1 branch are named as not checked, never passed silently."""
        self.assertEqual(TC.check(self.table, ROOT, None, None, self.doc), [])
        off = TC.off_head(self.table)
        self.assertEqual(({rid for rid, _, _ in off}, len(off), {name for *_, name in off}),
                         ({"P-V2-01", "P-GATE-2.0.1", "R-P0-1"}, 7, {"release/v2.0.1-prep"}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(TC.main([]), 0)
        self.assertIn("(7 cells on release/v2.0.1-prep not checked: pass --with-ref release/v2.0.1-prep)", out.getvalue())
        n = sum(r["decision"] == "adopted" for r in self.table["rows"])
        drifted = self.doc.replace(f"adopted {n},", f"adopted {n + 1},", 1)      # the .md edited by hand
        self.assertNotEqual(drifted, self.doc)
        self.assertEqual(TC.check(self.table, ROOT, None, None, drifted),
                         [f"{TC.DOC}: the generated block is not what --render prints from {TC.TABLE}"])

    def test_each_kind_of_wrong_cell_is_named(self):
        head = git("rev-parse", "HEAD").stdout.strip()      # holds the table, so it is a descendant, never an ancestor
        self.assertNotEqual(git("merge-base", "--is-ancestor", head, self.table["head"]).returncode, 0)
        t = copy.deepcopy(self.table)
        rows = {r["id"]: r for r in t["rows"]}
        rows["P-V2-01"]["commits"][0]["paths"].append("aisef2/no/such/file.py")
        rows["P-V2-02"]["commits"].append({"sha": "0" * 40, "paths": ["aisef2/app/usage.py"]})
        rows["P-V2-04"]["reproducers"].append("tests/v2/test_v21_inputs.py::Endpoint::test_that_was_never_written")
        rows["P-V2-06"]["report_items"]["B1"] = "M5"
        rows["P-V2-09"]["upstream"][0]["label"] = "README"
        rows["P-V2-11"]["refs"].append({"path": "aisef2/app/usage.py", "contains": "unknown cost is 0"})
        rows["R-P0-1"]["item"] += " (edited)"
        rows["P-5.3a"]["decision"] = "adopted"
        rows["P-V2-03"]["commits"].append({"sha": head, "paths": [TC.TABLE]})
        rows["P-V2-07"]["refs"].append({"path": "pyproject.toml", "same_as": "610a593"})
        rows["P-V2-10"]["refs"].append({"path": "aisef2/app/usage.py", "lacks": "NO_SIDE_RETRY_COUNTER"})
        rows["P-V2-13"]["refs"].append({"path": "aisef2/app/usage.py", "exists": False})
        rows["P-V2-08"]["refs"].append({"path": "aisef2/app/usage.py", "exists": True, "contians": "NOT THERE"})
        rows["P-V2-14"]["refs"].append({"path": "aisef2/app/usage.py", "exists": True, "contains": "CLASSES"})
        rows["P-4.2b"]["commits"].append({"sha": "919a271", "paths": ["x"], "patsh": []})
        rows["P-V2-12"]["commits"].append({"sha": "919a271", "paths": ["x"], "ref": self.table["head"]})
        rows["P-ADJ-3"]["reproducers"].append(f"{head}:tests/test_v21_traceability.py::Traceability")
        rows["P-9.3"]["gap"] = ""
        rows["P-4.3c"]["decision"] = "blocked"
        rows["P-5.2a"]["upstream"][0]["were"] = "x"
        n18 = next(u for u in rows["P-5.2b"]["upstream"] if u["claim"] == "N-18")
        n18["label"] = n18.pop("research_label")
        rows["P-7c"]["upstream"][0]["where"] += ", 9999-10000"
        rows["P-V2-05"]["upstream"][0]["where"] = "đề xuất §10 V2-05"
        # the right line numbers under a wrong file, and a number that only occurs elsewhere in the evidence ("9-backend")
        p03 = rows["P-5.3a"]["upstream"][0]
        p03["where"] = p03["where"].replace("checkpoint-templates.ts", "no-such-file.ts")
        rows["P-6.2c"]["upstream"][0]["where"] = "README.md:9"
        rows["P-6.2a"]["upstream"][0]["commit"] = "d"                     # one hex digit is a prefix of anything
        rows["P-11.3"]["refs"].append({"path": "aisef2/app/usage.py", "contains": ""})       # holds in every file
        rows["P-12-4"]["refs"].append({"path": "aisef2/app/usage.py", "exists": "yes"})
        rows["P-5.2c"]["commits"][0]["paths"] = []                        # touches nothing it names
        rows["P-4.2a"]["gap"] = ""                                        # adopted: nothing missing must be said
        rows["R-M1"]["gap"] = "—"                                         # a dash is not a gap
        rows["R-P1-6"]["acceptance"] = "lỗi DEVELOPER, có phản hồi"         # words of the item, not a criterion of 360
        rows["R-P1-7"]["acceptance"] = rows["R-P1-7"]["acceptance"].replace("(360 §6)", "(360 §7)")
        rows["R-P2-17"]["acceptance"] = "—"                               # a dash only on a declined row
        rows["P-9.1"]["refs"].append({"path": "../outside.txt", "at": TC.WITH_TABLE, "exists": False})
        rows["P-ADJ-6"]["refs"].append({"path": "docs/v2.1/evidence/cli-integration-c9c736f.out", "at": TC.WITH_TABLE,
                                        "contains": "commit: b72e51e"})          # evidence committed with the table, read
        expected = {"P-V2-01": "does not touch aisef2/no/such/file.py", "P-V2-02": "is not in this clone",
                    "P-V2-04": "no method test_that_was_never_written", "P-V2-06": "REPORT §2 gives B1 M3",
                    "P-V2-09": "the row says README", "P-V2-11": "does not contain",
                    "R-P0-1": "not verbatim", "open item": "P-5.3a is adopted",
                    "P-V2-03": "is not an ancestor", "P-V2-07": "is not the same as at 610a593",
                    "P-V2-10": "contains 'NO_SIDE_RETRY_COUNTER'", "P-V2-13": "usage.py at c9c736f",
                    "P-V2-08": "unknown key contians", "P-V2-14": "exactly one of",
                    "P-4.2b": "unknown key patsh", "P-V2-12": "is not the commit of a branch in other_refs",
                    "P-ADJ-3": "is not reachable from", "P-9.3": "names its gap",
                    "P-4.3c": "no open item lists it", "P-5.2a": "unknown key were",
                    "P-5.2b": "the verifier reclassified it as INFERENCE, the row says CODE",
                    "P-7c": "where line 9999-10000 of", "P-V2-05": "where names no file:line",
                    "P-5.3a": "of no-such-file is not one the", "P-6.2c": "where line 9 of README is not one",
                    "P-6.2a": "commit d is not one the research read", "P-11.3": "is not a string of 4 characters",
                    "P-12-4": "is not true or false", "P-5.2c": "paths names no path",
                    "P-4.2a": "decision is adopted names its gap", "R-M1": "decision is blocked names its gap",
                    "R-P1-6": "not a criterion the 360 document states (", "R-P1-7": "states in §7",
                    "R-P2-17": "not a criterion the 360 document states (", "P-9.1": "a path outside the checkout",
                    "P-ADJ-6": "cli-integration-c9c736f.out at with-table does not contain 'commit: b72e51e'"}
        problems = TC.check(t, ROOT, None, None, self.doc)
        for rid, text in expected.items():
            self.assertTrue(any(p.startswith(rid) and text in p for p in problems), (rid, text, problems))
        self.assertTrue(any("generated block" in p for p in problems))

    def test_a_key_the_format_does_not_know_is_named_anywhere_in_the_table(self):
        cases = [({**self.table, "opne_items": []}, "the table: unknown key opne_items"),
                 ({**self.table, "format": "aisef.v21-traceability/0"}, "the table: format"),
                 ({k: v for k, v in self.table.items() if k != "sources"}, "the table: missing key sources"),
                 ({**self.table, "sources": {**self.table["sources"], "reprot": "x"}}, "sources: unknown key reprot"),
                 ({**self.table, "sources": {**self.table["sources"], "proposal": {}}}, "sources.proposal: missing key sha256"),
                 ({**self.table, "open_items": [{**self.table["open_items"][0], "nmae": "x"}]}, "unknown key nmae"),
                 ({**self.table, "open_items": [{"name": "x", "rows": []}]}, "lists no row")]
        for table, text in cases:
            problems = TC.check(table, ROOT)
            self.assertTrue(any(text in p for p in problems), (text, problems))

    def test_criteria_are_read_from_the_sections_that_state_them(self):
        proposal = ("## 4. X\n\n### 4.3. Y\n\nmột câu.\n\n**Nghiệm thu bước đầu:** a; b.\n\n## 10. Backlog\n\n"
                    "| ID | Ưu tiên | Thay đổi | Nghiệm thu cụ thể | Phụ thuộc | Cỡ |\n|---|---|---|---|---|---|\n"
                    "| V2-01 | P0 | đổi | tiêu chí một | — | M |\n\n## 12. Gate\n\n### Phần phải làm ngay\n\n**x:** không phải cổng\n\n"
                    "### Gate đề xuất\n\n**2.0.1:** cổng một.\n\n## 13. Hoãn\n\n**2.2:** không phải cổng\n")
        self.assertEqual(TC.criteria(proposal, "proposal"), {"§4.3": ["a; b."], "§10": ["tiêu chí một"], "§12": ["cổng một."]})
        assessment = ("## 6. Lộ trình\n\n- **2.1**: #6. Thước đo xong: một người\n  ngoài dựng bundle.\n\n## 7. Bảng\n\n"
                      "| Chỉ số | 2.0.0 | Mục tiêu 2.1 |\n|---|---|---|\n| USD | chưa đo | có |\n\n## 8. Rủi ro\n| a | b | c |\n")
        self.assertEqual(TC.criteria(assessment, "360"), {"§6": ["một người ngoài dựng bundle."], "§7": ["Mục tiêu 2.1: có"]})
        rows = {r["id"]: r for r in self.table["rows"]}
        ctx = {"criteria": {"proposal": TC.criteria(proposal, "proposal"), "360": {}}}
        for acc, ok in (("tiêu chí một", True), ("cổng một (§12)", True), ("tiêu chí một (§12)", False), ("một câu.", False),
                        (TC.NO_CRITERION["proposal"] + "; theo chính mục", True), ("—", False), ("(§10)", False)):
            row = {**rows["P-V2-01"], "acceptance": acc}
            self.assertEqual(TC.acceptance_problem(row, ctx) is None, ok, acc)
        self.assertIsNone(TC.acceptance_problem({**rows["P-13-1"], "acceptance": "—"}, ctx))      # declined
        self.assertIsNone(TC.acceptance_problem({**rows["P-V2-01"], "acceptance": "x"}, {"criteria": {"proposal": None}}))

    def test_a_revision_from_the_table_or_the_command_line_is_never_read_as_an_option(self):
        with tempfile.TemporaryDirectory() as d:
            target = pathlib.Path(d) / "written-by-checker"
            t = copy.deepcopy(self.table)
            t["rows"][0]["refs"].append({"path": "aisef2/app/usage.py", "at": f"--output={target}", "exists": True})
            t["other_refs"]["bad"] = f"--output={target}"
            problems = TC.check(t, ROOT)
            self.assertEqual(list(pathlib.Path(d).iterdir()), [])
        self.assertTrue(any("is not a hex commit id" in p for p in problems), problems)
        self.assertTrue(any(p.startswith("other_refs bad:") for p in problems), problems)
        self.assertEqual(TC.check(self.table, ROOT, f"--output={target}"),
                         [f"--at --output={target}: not a commit in this clone"])

    def test_with_ref_names_a_branch_of_the_table_at_the_commit_it_records(self):
        t = copy.deepcopy(self.table)
        t["other_refs"]["HEAD"] = "0" * 40
        problems = TC.check(t, ROOT, None, None, None, ("HEAD", "no/such/branch"))
        self.assertTrue(any(p.startswith("--with-ref HEAD: is at ") and p.endswith("0" * 40) for p in problems), problems)
        self.assertTrue(any(p.startswith("--with-ref no/such/branch: not one of") for p in problems), problems)

    def test_report_levels_expand_ranges_and_per_item_levels(self):
        text = ("# R\n\n## 2. Levels\n\n| # | x | Mức |\n|---|---|---|\n| A3–A5 | x | M4 (A5), M3 (A3, A4) |\n"
                "| A9–A10 | x | M4 (build + `packaging_check` local) |\n| F | x | **M6** |\n\n## 3. Next\n| B1 | x | M1 |\n")
        self.assertEqual(TC.report_levels(text), {"A3": "M3", "A4": "M3", "A5": "M4", "A9": "M4", "A10": "M4", "F": "M6"})


if __name__ == "__main__":
    unittest.main()
