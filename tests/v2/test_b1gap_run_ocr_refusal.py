"""B1 gap kill tests for aisef2/app/run.py::ocr_refusal (mutation campaign survivors).

Function level, hermetic and offline: `ocr_refusal` is a pure function of the ident dict, so each test
constructs one directly (check/operator taken from the real OCR_CHECKS table). Each test names the exact
surviving mutant it kills."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import run as R  # noqa: E402


class OcrRefusal(unittest.TestCase):
    """run.ocr_refusal: the sentence joint between what was observed and what the operator does."""

    # kills: L225 string '. ' emptied
    def test_the_observed_reason_is_a_sentence_closed_before_the_operator_instruction(self):
        # The only observable effect of the mutant is inside the refusal message (which cli prints and
        # RUN.json stores as failure.detail): the '. ' joining the observed reason to the operator text
        # disappears, fusing "...observed <reason><operator>...". The existing identity/preflight tests
        # assert reason and operator as separate substrings, which the fused message still satisfies —
        # so this asserts the smallest stable joint substring the mutant destroys: "<reason>. <operator>".
        check, operator = R.OCR_CHECKS["declared"]
        reason = "declared `version` names v9.9.9 (0000000)"  # no '. ' of its own: the joint is the literal's
        ident = {"check": check, "operator": operator, "reason": reason,
                 "expected": {"sha256": "a" * 64, "version": "v1.12.12", "commit": "182898cdeadbee"}}
        said = R.ocr_refusal(ident)
        self.assertIn(f"observed {reason}. {operator}", said)
        self.assertNotIn(f"{reason}{operator}", said)


if __name__ == "__main__":
    unittest.main()
