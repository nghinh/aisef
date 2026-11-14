"""B1 gap kill tests for aisef2/app/run.py::OCR_CHECKS (v2.2 release-gate mutation campaign).

Each test pins one surviving mutant of the module-level OCR_CHECKS operator texts. The only observable effect
of each mutant is the operator message itself (the structured 'operator' field at run.py:216, ocr_refusal,
RUN.json), so each test asserts the smallest stable span the mutant destroys — composed from the module's own
unmutated constants (SHA256_OF, OCR_INSTEAD, review_ocr.OCR), never copied prose, and never compared against
OCR_CHECKS itself (a self-referential check mutates in lockstep and cannot fail)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_ocr  # noqa: E402
from aisef2.app import run as R  # noqa: E402


class OcrChecksText(unittest.TestCase):
    """The f-string joints of the OCR_CHECKS operator texts that no other test pins."""

    # Kills: L158 string '). ' emptied
    def test_pinned_operator_closes_the_sha_recipe_then_offers_the_model_reviewer(self):
        # The pinned operator text ends with the sha256 recipe in parentheses, a sentence boundary, then
        # OCR_INSTEAD; the mutant deletes the ') . ' joint, fusing '<exe>`' straight into 'Or have the model'.
        tail = f"({R.SHA256_OF}). {R.OCR_INSTEAD}"
        self.assertIn(tail, R.OCR_CHECKS["pinned"][1])
        self.assertTrue(R.OCR_CHECKS["pinned"][1].endswith(tail),
                        "the pinned operator text must end with the recipe, a sentence boundary, and the alternative")

    # Kills: L161 string ' (' emptied
    def test_declared_operator_names_version_then_commit_in_parentheses(self):
        # The declared operator text names the pinned version, then the 7-char commit in parentheses, before
        # 'what it did'; the mutant deletes the ' (' so version and commit fuse ('v1.12.12182898c)'). The
        # needle keeps '; what it did' so it can only match the L160-161 sentence, never the second
        # version/commit occurrence at L164-166.
        needle = (f"line of Open Code Review {review_ocr.OCR['version']} "
                  f"({review_ocr.OCR['commit'][:7]}); what it did")
        self.assertIn(needle, R.OCR_CHECKS["declared"][1])


if __name__ == "__main__":
    unittest.main()
