"""Reproducer A (gate level): a nop run that could not run because a THIRD-PARTY dependency is missing at the parent
SHA — recorded exactly as the harness records a pytest collection ImportError (unrunnable + test_format) — must not
prove the story's tests verify it. Documented rule: 'a dependency the project never installed is a real environment
failure and must stay unrunnable' (aisef/phases/implement.py::_vang_ma_cua_story, SS-26 / INV-F.3)."""
import sys, unittest
sys.path.insert(0, "tests")
from test_gate import TestTestCoKiemDuocStory, Outcome

KHONG_PHU_THUOC = "no runnable setup in this tree — the project's dependencies are not installed here"


class Repro(TestTestCoKiemDuocStory):
    def test_A_third_party_missing_with_pytest_format(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])                  # the AC test is green at the candidate
        # parent: collection interrupted by `ModuleNotFoundError: No module named 'hypothesis'` — nothing ran
        self.nop([], unrunnable=KHONG_PHU_THUOC)
        m = self.cham()
        print("\nA outcome:", m.outcome, "|", m.detail)
        self.assertIsNot(m.outcome, Outcome.PASSED, "an environment failure at the parent proved nothing")

    def test_A_control_same_record_without_test_format(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop(None, unrunnable=KHONG_PHU_THUOC)       # the existing control: no test_format
        m = self.cham()
        print("\nA-control outcome:", m.outcome, "|", m.detail)
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)


if __name__ == "__main__":
    unittest.main(defaultTest=["Repro.test_A_third_party_missing_with_pytest_format", "Repro.test_A_control_same_record_without_test_format"], verbosity=1)
