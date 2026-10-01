"""Reproducer B (harness + gate, real pytest, no model): at the parent SHA one story test file fails to import (the
story's own package is absent — the legitimate red), pytest interrupts the whole session, and a second story test file
holding a tautological AC test never runs. The kernel's own parser reports it absent; the gate reads absent as red."""
import sys, unittest
sys.path.insert(0, "tests")
from aisef.harness.testlog import parse
from test_gate import TestTestCoKiemDuocStory, Outcome
SP = __import__('pathlib').Path(__file__).parent.as_posix()
A1 = "tests/test_a.py::test_AC_S_01_1_normalizes"
A2 = "tests/test_b.py::test_AC_S_01_2_tautology"


class ReproB(TestTestCoKiemDuocStory):
    def test_B_a_tautological_ac_test_is_masked_by_another_files_import_error(self):
        parent = parse(open(f"{SP}/reproB-pytest-at-parent.txt").read()).to_evidence()   # the real pytest output at the parent
        print("\nparsed at parent:", {k: parent.get(k) for k in ("test_format", "test_ids", "failed_ids")})
        self.baseline(["t1"])
        self.ung_vien([A1, A2, "t1"])                                           # both AC tests green at the candidate
        self.nop(parent.get("test_ids") or [], failed=parent.get("failed_ids") or [])
        m = self.muc(self.gate(candidate="aaa", acceptance=2))
        print("B outcome:", m.outcome, "|", m.detail)
        self.assertNotIn(A2, parent.get("test_ids") or [], "precondition: the tautology never ran at the parent")
        self.assertIsNot(m.outcome, Outcome.PASSED, "test_b's AC test is green without the story's code")


if __name__ == "__main__":
    unittest.main(defaultTest=["ReproB.test_B_a_tautological_ac_test_is_masked_by_another_files_import_error"], verbosity=1)
