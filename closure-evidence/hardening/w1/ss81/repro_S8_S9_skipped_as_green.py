"""Candidate siblings: a test that did not execute (SKIPPED) read as still green."""
import sys, unittest
sys.path.insert(0, "tests")
from test_gate import TestTestCoKiemDuocStory, Outcome
from aisef.harness.observe import EvidenceStore

OLD = "tests/test_old.py::test_AC_S_00_1_old_behaviour"


class S8_BaselineSkippedAtCandidate(TestTestCoKiemDuocStory):
    def test_a_baseline_green_test_skipped_at_the_candidate_is_a_regression_signal(self):
        self.baseline([OLD])                                   # green at baseline
        self.ung_vien([OLD, self.AC], skipped_ids=[OLD])        # the story made it skip; run is green
        m = next(c for c in self.gate(candidate="aaa", acceptance=1).checks if c.name == "no baseline regression")
        print("\nS8 R9:", m.outcome, "|", m.detail[:140])
        self.assertIsNot(m.outcome, Outcome.PASSED)


class S9_PreservationSkipped(TestTestCoKiemDuocStory):
    def test_a_verified_behaviour_whose_test_is_skipped_is_not_preserved(self):
        self.baseline([OLD])
        self.ung_vien([OLD, self.AC], skipped_ids=[OLD])
        pres = [{"id": "AC-S-00-1", "kind": "ac", "story": "S-00"}]
        m = next(c for c in self.gate(candidate="aaa", acceptance=1, preservation=pres).checks if c.name == "preservation")
        print("S9 preservation:", m.outcome, "|", m.detail[:140])
        self.assertIsNot(m.outcome, Outcome.PASSED)


if __name__ == "__main__":
    unittest.main(defaultTest=["S8_BaselineSkippedAtCandidate", "S9_PreservationSkipped"], verbosity=1)
