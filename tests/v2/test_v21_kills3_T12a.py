"""V2.1 mutation survivors, batch T12a: the verdict vocabularies and the pin of aisef2/app/review_ocr.py.

Three constants decide what a review may skip or must not trust, and one names the upstream commit:

* `NOT_FULL`: a `complete` manifest that carries one of OCR's warnings is not a full review (a round, and the findings
  of its group, were lost) — coverage is INDETERMINATE and says which warning;
* `NOT_REVIEWABLE`: a required path the preview excludes as `unsupported_ext` or `binary` is one this finder cannot
  read (named, not counted against COMPLETE); every other exclusion of a required path — including a reason that is
  empty or absent — is a gap;
* `OCR["commit"]`: the full upstream commit the real-binary check compares a 7-character prefix of.

The names of OCR's warning codes and exclusion reasons are written out below, not read from the module's tuples: a
test that read them back would pass whatever the tuples held."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_ocr as O  # noqa: E402

FIX = ROOT / "tests/v2/fixtures/ocr"
A = json.loads((FIX / "complete.json").read_text(encoding="utf-8"))
PREVIEW = json.loads((FIX / "preview.json").read_text(encoding="utf-8"))
BASE, HEAD = "1" * 40, "2" * 40
REQUIRED = ["src/app/api.py", "src/app/limits.py"]


def cov(out=A, required=REQUIRED, preview=None):
    return O.coverage(out, 0, required=required, base=BASE, head=HEAD, preview=preview)


def preview_with(*entries):
    p = copy.deepcopy(PREVIEW)
    p["files"] = [*p["files"], *entries]
    return p


class WarningsAfterWhichACompleteManifestIsNotAFullReview(unittest.TestCase):
    """OCR leaves the manifest `complete` after a failed round, a threshold or a budget stop; the warning is the only
    signal that part of the review did not run. A fix-loop commits on COMPLETE, so each of the three must degrade it.
    Pins aisef2/app/review_ocr.py::NOT_FULL [0, 1]."""

    def test_the_unwarned_manifest_is_complete(self):
        self.assertEqual((cov().status, cov().reasons), (O.COMPLETE, ()))

    def test_each_warning_makes_coverage_indeterminate_and_is_named(self):
        for warning in ("review_round_failed", "token_threshold_exceeded", "token_budget_reached"):
            with self.subTest(warning):
                out = copy.deepcopy(A)
                out.setdefault("warnings", []).append({"type": warning, "message": "m"})
                c = cov(out)
                self.assertEqual(c.status, O.INDETERMINATE, c)
                self.assertTrue(any(f"warning {warning}" in r for r in c.reasons), c.reasons)


class WhatTheFinderCannotReadIsNamedAndEverythingElseIsAGap(unittest.TestCase):
    """A required path excluded as `unsupported_ext` or `binary` is one OCR cannot read: coverage stays COMPLETE and
    names it (Coverage.not_reviewable, which `aisef run` records). Any other exclusion of a required path is a gap.
    Pins aisef2/app/review_ocr.py::NOT_REVIEWABLE [0, 1]."""

    def test_unsupported_ext_is_named_and_not_counted_against_complete(self):
        c = cov(required=[*REQUIRED, "docs/limits.md"], preview=PREVIEW)    # docs/limits.md: unsupported_ext
        self.assertEqual((c.status, c.reasons, c.not_reviewable), (O.COMPLETE, (), ("docs/limits.md",)))

    def test_binary_is_named_and_not_counted_against_complete(self):
        preview = preview_with({"path": "assets/logo.png", "status": "added", "will_review": False,
                                "exclude_reason": "binary"})
        c = cov(required=[*REQUIRED, "assets/logo.png"], preview=preview)
        self.assertEqual((c.status, c.reasons, c.not_reviewable), (O.COMPLETE, (), ("assets/logo.png",)))

    def test_any_other_exclusion_of_a_required_path_is_a_gap_that_names_the_path(self):
        reasons = {
            "secret": "secret_exclude", "provider directory": "provider_directory", "default path": "default_path",
            "too large": "too_large", "empty reason": "",
        }
        entries = {name: {"path": f"gap/{n}.dat", "status": "modified", "will_review": False, "exclude_reason": why}
                   for n, (name, why) in enumerate(reasons.items())}
        entries["no reason at all"] = {"path": "gap/none.dat", "status": "modified", "will_review": False}
        for name, entry in entries.items():
            with self.subTest(name):
                c = cov(required=[*REQUIRED, entry["path"]], preview=preview_with(entry))
                self.assertEqual(c.status, O.INDETERMINATE, c)
                self.assertTrue(any(entry["path"] in r for r in c.reasons), c.reasons)
                self.assertEqual(c.not_reviewable, ())


class ThePinNamesOneUpstreamCommitInFull(unittest.TestCase):
    """`OCR["commit"]` is a 40-character lowercase hex SHA. The only reader is the real-binary check
    (tests/v2/test_v21_review_chain.py RealBinary.setUp: `assertIn(OCR["commit"][:7], version)`), which a missing key
    breaks and an empty or short value makes vacuous (`assertIn("", version)` is always true). Whether it is the right
    commit only that check, against the real binary, can say.
    Pins aisef2/app/review_ocr.py::OCR [2, 6]."""

    def test_the_commit_is_a_full_sha(self):
        self.assertRegex(O.OCR["commit"], r"\A[0-9a-f]{40}\Z")


if __name__ == "__main__":
    unittest.main()
