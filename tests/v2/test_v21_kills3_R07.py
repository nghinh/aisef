"""V2.1 (owner B-03, kill round 3 / round 2, batch R07): the two survivors left of aisef2/app/adapters.py::Reviewer._ocr
after the product fixes — the refusal for a `git diff --name-status` listing whose rows are not `<status> <path>`.

`_ocr` reads the story's change with `git diff -z --name-status --no-renames <parent>..<candidate>`. A listing that has
a row of two paths (a rename or copy) or a dangling status is refused as CapabilityUnrunnable before any session starts
(test_v21_defects_ocrz pins that it is refused, and that the message names `git diff`). What the operator reads of it is
the journal's `provider/result` detail, "reviewer cannot run: <the refusal>" (orchestrate/review.review): the same
command refused for two different causes, told apart by its text — the exit status (pinned in test_v21_kills3_T10d,
OcrGitDiffRefusal) or the shape of what it printed (here) — so the refusal names the range git was asked to list, the
cause class and the leading fields that were not rows.

git is the stand-in: `--no-renames` makes real git print only one-path rows, so the listing is scripted through
`adapters.git`; the Reviewer and its pinned-binary check are real, and `_ocr` is called as the other kill files do."""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.orchestrate.adapters import CapabilityUnrunnable  # noqa: E402
from tests.v2.test_v21_defects_ocr import _Finder  # noqa: E402  (the OCR stand-in: it answers `version`, the gate before the diff)

#: the story's parent and the candidate: well-formed revisions with different, recognisable first characters
PARENT = "a1b2c3d4e5f6" + "0" * 28
HEAD = "f6e5d4c3b2a1" + "9" * 28


class ARowOfAnotherShapeIsRefusedWithItsRangeItsCauseAndItsFields(unittest.TestCase):
    """The listing is refused (CapabilityUnrunnable); the refusal is the operator's only lead, so it names the range
    that was listed (the two revisions joined as git writes a range), states a cause that is not the exit-status one
    of the sibling refusal, and then shows the leading fields it could not read as rows, in that order. Asserted by
    structure — range, then a clause of words, then the fields — not by the words of the clause or by how the fields
    are written out (a list, a comma-separated line).

    Pins aisef2/app/adapters.py::Reviewer._ocr [198] [199]."""

    #: what git printed (NUL-separated fields), the status field that opens it, the paths the refusal must show of it
    LISTINGS = (
        ("a row of two paths", "R100\0app/old.py\0app/new.py\0", ("R100",), ("app/old.py", "app/new.py")),
        ("a status without its path", "A\0app/new.py\0M\0", ("A",), ("app/new.py",)),
    )

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        tmp = pathlib.Path(t.name).resolve()
        exe = tmp / "ocr"
        exe.write_bytes(b"the pinned binary\n")
        review = {"policy": "advisory", "min_severity": "high", "finder": "ocr", "given": True,
                  "ocr": {"exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        events = [types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": PARENT})]
        self.reviewer = ad.Reviewer(types.SimpleNamespace(events=events), types.SimpleNamespace(product_roots=("app",)),
                                    tmp / "sessions", {}, 5.0, review=review,
                                    route={"url": "http://127.0.0.1:9/v1", "token": "sk-test-not-a-key", "model": "m"})
        self.root = str(tmp / "repo")

    def refusal(self, listing: str) -> str:
        done = subprocess.CompletedProcess([], 0, listing, "")
        with mock.patch.object(ad, "git", return_value=done), mock.patch.object(ad, "ProcessRange", _Finder(())), \
                self.assertRaises(CapabilityUnrunnable) as cm:
            self.reviewer._ocr(types.SimpleNamespace(story_id="S1", root=self.root), 1, HEAD)
        return str(cm.exception)

    def test_the_refusal_names_the_range_then_the_cause_then_the_fields(self):
        for label, listing, statuses, paths in self.LISTINGS:
            with self.subTest(listing=label):
                said = self.refusal(listing)
                # <parent>..<candidate>, each an abbreviated revision that ends where it ends (the number of characters
                # shown is not the contract) — the range, not two revisions run together
                span = re.search(rf"{PARENT[:7]}[0-9a-f]*\.\.{HEAD[:7]}[0-9a-f]*\b", said)
                self.assertIsNotNone(span, said)
                after = said[span.end():]
                for path in paths:                              # the fields it could not read, after the range
                    self.assertIn(path, after, said)
                # between the range and the first field the refusal says what was wrong — not the exit status of the
                # sibling refusal, and not nothing (the status field that opens the fields is not a cause)
                gap = after[:min(after.find(p) for p in paths)]
                for status in statuses:
                    gap = gap.replace(status, "")
                self.assertTrue(re.search(r"[a-z]{3,}", gap), said)
                self.assertNotIn("exit", gap, said)


if __name__ == "__main__":
    unittest.main()
