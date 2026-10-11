"""V2.1 mutation survivors, batch T11b: aisef2/app/review_ocr.py::findings.

findings() turns OCR's comments into the triage records the review stage writes to RUN.json (sessions[].findings).
Two requirements, neither pinned before:

* the record locates and classifies the claim: OCR's category, the comment's path and start line are carried through,
  and in_scope says whether that path is one of the files AISEF required to be reviewed (the id is a one-way hash of
  path|category|code, so without these fields the record cannot say where or what);
* findings() is a function of the *set* of comments: OCR's emission order (a concurrent collector's: docs/v2.1/research/
  UPSTREAM-RESEARCH.json, adapter_contract_corrections 11) reaches neither the ids, nor the order of the records (the
  order of the review rows in the journal), nor which line a repeated comment reports; and the occurrences of one
  place are numbered by where they are (the line), not by how the model worded them.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_ocr as O  # noqa: E402

COMPLETE = json.loads((ROOT / "tests/v2/fixtures/ocr/complete.json").read_text(encoding="utf-8"))


def comment(path="a.py", content="x", category="bug", start_line=5, existing_code="same code", end_line=None):
    """One OCR comment; the same existing_code makes comments of one path and category one place (one fingerprint).
    end_line is not start_line (unless given), so a record that read the wrong one of the two cannot pass."""
    if end_line is None:
        end_line = (start_line or 0) + 2
    return {"path": path, "content": content, "existing_code": existing_code, "start_line": start_line,
            "end_line": end_line, "category": category, "severity": "medium"}


def run(*comments, required=()):
    return O.findings({"comments": list(comments)}, required)


def occurrence(finding) -> str:
    """The occurrence index of an id (`ocr-<12 hex of the place>-<n>`; the format is pinned in test_v21_review_ocr)."""
    return finding["id"].rsplit("-", 1)[1]


class FindingRecord(unittest.TestCase):
    """Pins aisef2/app/review_ocr.py::findings [21, 23, 24, 36, 38, 39, 44, 45, 53, 60, 61, 62]: the record says what
    OCR claimed and where, and whether that file is in the scope AISEF required."""

    def test_the_finding_of_ocr_s_own_output_carries_its_category_path_and_line(self):
        c = COMPLETE["comments"][0]
        [f] = O.findings(COMPLETE, [c["path"]])
        self.assertEqual((f["category"], f["path"], f["start_line"]), ("bug", "src/app/limits.py", 41))
        self.assertEqual((c["category"], c["path"], c["start_line"]), ("bug", "src/app/limits.py", 41))  # what it read

    def test_each_comment_keeps_its_own_category_path_and_start_line(self):
        found = run(comment("src/app/api.py", "p", "security", 7), comment("docs/notes.md", "q", "style", 120))
        self.assertEqual({f["summary"]: (f["category"], f["path"], f["start_line"]) for f in found},
                         {"p": ("security", "src/app/api.py", 7), "q": ("style", "docs/notes.md", 120)})

    def test_in_scope_is_the_comment_s_path_read_against_the_required_files(self):
        found = run(comment("src/app/limits.py", "in"), comment("src/app/other.py", "out"),
                    comment("lib/limits.py", "same name elsewhere"), comment("src/app/limits.pyi", "longer name"),
                    required=["src/app/limits.py"])
        self.assertEqual({f["summary"]: f["in_scope"] for f in found},
                         {"in": True, "out": False, "same name elsewhere": False, "longer name": False})


class Order(unittest.TestCase):
    """Pins aisef2/app/review_ocr.py::findings [28, 29, 30, 58, 64, 65, 68]: the records come in one order whatever
    order OCR emitted the comments in, and the repeats of one place are numbered and de-duplicated by line."""

    def same_either_way(self, a, b):
        """a and b differ in one field only: the two records, in the order they come, do not depend on who came first."""
        found = run(a, b)
        self.assertEqual(len(found), 2)          # two claims, none merged (else there is no order to speak of)
        self.assertEqual(run(b, a), found)

    def test_path_orders_comments_that_tie_on_everything_else(self):
        self.same_either_way(comment("a.py"), comment("b.py"))

    def test_category_orders_comments_that_tie_on_everything_else(self):
        self.same_either_way(comment(category="bug"), comment(category="style"))

    def test_the_line_and_not_the_wording_numbers_the_occurrences_of_one_place(self):
        # 9 < 10 only as numbers; early's end line is the later one, and its wording sorts after late's
        early = comment(content="zzz", start_line=9, end_line=90)
        late = comment(content="aaa", start_line=10, end_line=11)
        self.assertEqual(O.finding_id(late), O.finding_id(early))      # one place: the index is what tells them apart
        for given in ([late, early], [early, late]):
            self.assertEqual([(f["start_line"], f["summary"], occurrence(f)) for f in run(*given)],
                             [(9, "zzz", "0"), (10, "aaa", "1")])

    def test_a_comment_said_again_reports_the_earliest_line(self):
        early = comment(content="same", start_line=9, end_line=90)
        late = comment(content="same", start_line=10, end_line=11)
        for given in ([late, early], [early, late]):
            found = run(*given)
            self.assertEqual([(f["start_line"], occurrence(f)) for f in found], [(9, "0")])

    def test_a_comment_with_no_line_is_line_0_and_not_an_error(self):
        absent, none = comment(content="a"), comment(content="b", start_line=None)
        del absent["start_line"]
        found = run(comment(content="c", start_line=5), absent, none)
        self.assertEqual({f["summary"]: f["start_line"] for f in found}, {"a": 0, "b": 0, "c": 5})
        self.assertEqual([f["summary"] for f in found][-1], "c")      # line 0 sorts before line 5 within one place

    def test_every_input_order_gives_the_same_findings(self):
        absent = comment(content="z")
        del absent["start_line"]
        comments = [comment("a.py", "y", "bug", 5), comment("a.py", "x", "bug", 9), comment("a.py", "y", "style", 5),
                    comment("b.py", "y", "bug", 5), absent]
        want = run(*comments)
        self.assertEqual(len(want), 5)
        for given in itertools.permutations(comments):
            self.assertEqual(run(*given), want)


if __name__ == "__main__":
    unittest.main()
