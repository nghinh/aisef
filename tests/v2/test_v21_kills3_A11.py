"""V2.1 (owner B-03, kills3 batch A11): the audit of the survivors of aisef2/app/review_ocr.py's `coverage` and
`findings`. Each survivor was re-examined from its consumers; the ones that stay survivors are audited in the batch
report, the ones below are real gaps.

`coverage` has no machine-readable reason codes: its reasons are strings, and a reason's words are the only statement
of *which check failed*. Under `review.policy: advisory` (the default, USAGE-2.1) an INDETERMINATE review blocks
nothing, so `sessions[].coverage.reasons` in RUN.json is the only signal an operator gets; under `fix-loop` the same
strings are the journaled refusal (`reviewer cannot run: ...`). Nothing parses them, so what is asserted below is not a
sentence but what a reader needs from each entry: the values and which check they belong to."""

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
A = json.loads((FIX / "complete.json").read_text(encoding="utf-8"))       # reviewed 1*40..2*40, v1.12.12, both complete
PREVIEW = json.loads((FIX / "preview.json").read_text(encoding="utf-8"))
BASE, HEAD = "1" * 40, "2" * 40
REQUIRED = ["src/app/api.py", "src/app/limits.py"]


class ReasonsNameTheCheckThatFailed(unittest.TestCase):
    """A refusal reason says which check failed together with the values it failed on, so an operator reading one entry
    on its own (RUN.json holds the reasons as a list, unframed) can act on it."""

    def cov(self, out=A, code=0, required=REQUIRED, base=BASE, head=HEAD, preview=None) -> O.Coverage:
        return O.coverage(out, code, required=required, base=base, head=head, preview=preview)

    def entry(self, c: O.Coverage, *needles: str) -> str:
        """The one reason holding every needle: the values and the words that say what they are."""
        found = [r for r in c.reasons if all(n in r for n in needles)]
        self.assertEqual(len(found), 1, (needles, c.reasons))
        return found[0]

    def test_a_non_zero_exit_is_named_as_the_exit_status_with_its_number(self):
        """Pins aisef2/app/review_ocr.py::coverage [76]. A complete manifest with a failing exit is INDETERMINATE and
        the only reason: a bare number would not say it is the process's exit status; exit 0 gives no such reason."""
        c = self.cov(A, 7)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.entry(c, "exit", "7")
        self.assertEqual(self.cov(A, 0).reasons, ())

    def test_a_run_failure_is_named_as_one_with_its_class_and_ocr_s_own_words(self):
        """Pins aisef2/app/review_ocr.py::coverage [83]. OCR's `run_failure.classification` is one of input,
        configuration, timeout, cancelled, budget, internal, unknown (docs/v2.1/research/UPSTREAM-RESEARCH.json,
        adapter contract §3): taken alone `input (bad revision)` or `unknown (None)` does not say what it is the class
        of — the entry says it is the run's failure, with the class and OCR's reason in the same entry."""
        out = copy.deepcopy(A)
        out["manifest"]["terminal_state"] = "failed"
        out["manifest"]["run_failure"] = {"classification": "input", "reason": "bad revision"}
        c = self.cov(out, 1)
        self.assertEqual((c.status, c.failure), (O.INDETERMINATE, "input"))
        self.entry(c, "failure", "input", "bad revision")

    def test_a_mismatched_base_is_named_as_the_base_with_both_ids_apart_from_the_head(self):
        """Pins aisef2/app/review_ocr.py::coverage [79]. Both ends of the frozen range wrong: the two ids of each end
        are in the entry of that end, and the entry that holds the base's ids says it is the base — two bare id pairs
        would not say which end of the range OCR got wrong."""
        c = self.cov(A, 0, REQUIRED, "8" * 40, "9" * 40)
        base = self.entry(c, "base", "1" * 12, "8" * 12)        # what OCR reviewed (the manifest's), what was frozen
        head = self.entry(c, "2" * 12, "9" * 12)
        self.assertNotEqual(base, head)
        self.assertNotIn("1" * 12, head)
        self.assertNotIn("9" * 12, base)

    def test_each_list_of_required_paths_says_why_its_paths_are_listed(self):
        """Pins aisef2/app/review_ocr.py::coverage [89, 111, 112]. A required path can be missing from three different
        causes — OCR never completed it, the preview excludes it, the preview does not list it at all (gitignored, or
        a provider directory) — and each reason lists only its own paths under its own cause: with the headings gone
        the three are bare lists that cannot be told apart, and the third has no recovery hint."""
        required = [*REQUIRED, "tests/test_limits.py", "build/gen.py"]
        c = self.cov(A, 0, required, preview=PREVIEW)
        self.assertEqual(c.status, O.INDETERMINATE)
        undone = self.entry(c, "completed", "tests/test_limits.py", "build/gen.py")   # neither is in OCR's completed
        excluded = self.entry(c, "exclude", "tests/test_limits.py", "default_path")   # the preview lists it, not reviewed
        absent = self.entry(c, "absent", "build/gen.py")                              # the preview does not list it
        self.assertNotIn("build/gen.py", excluded)
        self.assertNotIn("tests/test_limits.py", absent)
        self.assertEqual(len({undone, excluded, absent}), 3)
        self.assertFalse([r for r in c.reasons for p in REQUIRED if p in r], c.reasons)   # a reviewed path is never listed

    def test_an_excluded_path_is_named_as_excluded_whether_or_not_the_preview_gave_a_code(self):
        """Pins aisef2/app/review_ocr.py::coverage [111]. The preview's `exclude_reason` is optional in OCR's
        contract (docs/v2.1/research/UPSTREAM-RESEARCH.json, adapter contract): the reason must not depend on it to
        say that the preview excluded the path — with no code, the words are all that say so."""
        preview = {"files": [{"path": "src/app/api.py", "will_review": True},
                             {"path": "src/app/limits.py", "will_review": False}]}
        c = self.cov(A, 0, REQUIRED, preview=preview)
        self.assertEqual(c.status, O.INDETERMINATE)
        self.entry(c, "exclude", "src/app/limits.py")
        self.assertFalse(any("src/app/api.py" in r for r in c.reasons), c.reasons)    # the reviewable one is not named


if __name__ == "__main__":
    unittest.main()
