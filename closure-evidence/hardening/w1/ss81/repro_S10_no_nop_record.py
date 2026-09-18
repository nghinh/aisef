"""Candidate sibling S10: no nop record at this candidate while the story has AC tests — the control never ran, and
the gate returns NOT_APPLICABLE, which does not block (Outcome.blocks is FAILED/UNRUNNABLE only)."""
import sys, unittest
sys.path.insert(0, "tests")
from test_gate import TestTestCoKiemDuocStory, Outcome


class S10_NoNopRecord(TestTestCoKiemDuocStory):
    def test_a_missing_control_does_not_let_the_gate_pass(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])                  # AC test green at the candidate, no test:nop recorded
        g = self.gate(candidate="aaa", acceptance=1, added_tests=["tests/test_a.py"])
        m = self.muc(g)
        print("\nS10 nop:", m.outcome, "| blocks:", m.outcome.blocks, "|", m.detail[:100])
        self.assertTrue(m.outcome.blocks, "the control did not run, so it cannot be allowed to not block")


if __name__ == "__main__":
    unittest.main(defaultTest=["S10_NoNopRecord"], verbosity=1)
