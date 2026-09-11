"""Regression: ``_same_complaint`` recognises identical blocking
findings via stable Finding ids.  Same text raised twice on the same
defect must compare equal; rewriting the same defect with different
wording must not (legacy token-overlap rule still catches that case)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.phases.implement import (
    _same_complaint,
    _same_complaint_by_finding,
)


class TestSameComplaintViaFinding(unittest.TestCase):
    def test_identical_canonical_lines_match_by_id(self):
        line = "[high] src/pay.py:42  Race in checkout pipeline"
        self.assertTrue(_same_complaint([line], [line]))
        # The id path alone is enough.
        self.assertTrue(_same_complaint_by_finding([line], [line]))

    def test_different_line_is_not_same_complaint(self):
        a = "[high] src/pay.py:42  Race in checkout pipeline"
        b = "[high] src/pay.py:42  Lost-order event dispatched twice"
        self.assertFalse(_same_complaint([a], [b]))

    def test_mixed_legacy_and_structured(self):
        # One side canonical, one side legacy text: by-id path returns
        # False, token-overlap path may or may not — but verifying the
        # path doesn't crash is the wiring regression.
        legacy = "src/pay.py:42 checkout race condition"
        canonical = "[high] src/pay.py:42  Race in checkout pipeline"
        # Should not raise.  Whether the legacy overlap catches it
        # is the legacy detector's job; by-id returns False here.
        out = _same_complaint_by_finding([canonical], [legacy])
        self.assertFalse(out)

    def test_empty_inputs_safe(self):
        self.assertFalse(_same_complaint([], []))
        self.assertFalse(_same_complaint_by_finding([], []))


if __name__ == "__main__":
    unittest.main()
