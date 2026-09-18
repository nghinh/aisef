"""Candidate siblings of SS-81 — each driven on the frozen kernel with the suite's own fixtures. A failing assertion
here means the candidate is CONFIRMED (the kernel accepted non-execution / non-behavioural red as proof)."""
import sys, tempfile, unittest
sys.path.insert(0, "tests")
from test_gate import GateTestCase, TestTestCoKiemDuocStory, Outcome
from aisef.harness.observe import EvidenceStore
from aisef.control import ledger as L

UNRUN = "tool not installed or cannot load (command not found) — set up the environment or fix the command and retry"


class S4_TddCountsUnrunnableAsRed(GateTestCase):
    def test_an_environment_failure_is_not_a_red_run(self):
        s = EvidenceStore(self._tmp.name, candidate="aaa")
        s.file_change("S-01", "src/a.py")
        s.tool_run("S-01", "test", ok=False, detail={"unrunnable": UNRUN, "test_format": "", "test_ids": []})
        s.tool_run("S-01", "test", ok=True, detail={"test_format": "pytest", "test_ids": ["tests/test_a.py::test_AC_S_01_1_x"], "failed_ids": []})
        s.tool_run("S-01", "lint", ok=True); s.tool_run("S-01", "qa:fake-tests", ok=True, detail={"files": []})
        g = self.gate(candidate="aaa", acceptance=1, added_tests=["tests/test_a.py"])
        m = next(c for c in g.checks if c.name == "TDD")
        print("\nS4 TDD:", m.outcome, "|", m.detail[:120])
        self.assertIsNot(m.outcome, Outcome.PASSED)

    def test_a_red_run_that_never_executed_the_story_tests_is_not_tdd_red(self):
        s = EvidenceStore(self._tmp.name, candidate="aaa")
        s.file_change("S-01", "src/a.py")
        # red only because an UNRELATED pre-existing test failed; the story's AC test is not in the run
        s.tool_run("S-01", "test", ok=False, detail={"test_format": "pytest", "test_ids": ["tests/test_old.py::test_x"], "failed_ids": ["tests/test_old.py::test_x"]})
        s.tool_run("S-01", "test", ok=True, detail={"test_format": "pytest", "test_ids": ["tests/test_a.py::test_AC_S_01_1_x", "tests/test_old.py::test_x"], "failed_ids": []})
        s.tool_run("S-01", "lint", ok=True); s.tool_run("S-01", "qa:fake-tests", ok=True, detail={"files": []})
        g = self.gate(candidate="aaa", acceptance=1, added_tests=["tests/test_a.py"])
        m = next(c for c in g.checks if c.name == "TDD")
        print("S4b TDD:", m.outcome, "|", m.detail[:120])
        self.assertIsNot(m.outcome, Outcome.PASSED)


class S5_NoCriteriaAnyRedAtParent(TestTestCoKiemDuocStory):
    def test_a_red_parent_run_is_not_proof_without_named_tests(self):
        self.baseline(["t1"])
        self.ung_vien(["t1"])
        self.nop(None, ok=False, unrunnable="")          # red at parent, no names, for any reason
        m = self.muc(self.gate(candidate="aaa", acceptance=0))
        print("S5 nop(acceptance=0):", m.outcome, "|", m.detail[:120])
        self.assertIsNot(m.outcome, Outcome.PASSED)


class S6_BaselineAbortedCollection(TestTestCoKiemDuocStory):
    def test_an_aborted_baseline_cannot_prove_nothing_regressed(self):
        # baseline: pytest printed its format but collection was interrupted — no test ids although tests exist
        self.store.tool_run("S-01", "test:baseline", ok=False, detail={
            "baseline": True, "test_format": "pytest", "test_ids": [], "failed_ids": [], "skipped_ids": [],
            "tail": "ERROR tests/test_broken.py\n!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!"})
        self.ung_vien(["tests/test_new.py::test_AC_S_01_1_x"])      # an existing test was deleted by the story
        m = next(c for c in self.gate(candidate="aaa", acceptance=1).checks if c.name == "no baseline regression")
        print("S6 baseline:", m.outcome, "|", m.detail[:120])
        self.assertIsNot(m.outcome, Outcome.PASSED)


class S7_LedgerSkippedIsNotVerified(unittest.TestCase):
    def test_a_skipped_ac_test_is_not_a_verified_criterion(self):
        led = L.Ledger()
        led.stories["S-01"] = L.StoryLine(id="S-01", acceptance=1, covers=["FR-1"])
        class E:  # one tool_run test event, the shape _observe_tests reads
            name, ok = "test", True
            detail = {"test_format": "pytest", "test_ids": ["tests/test_a.py::test_AC_S_01_1_x"], "failed_ids": [],
                      "skipped_ids": ["tests/test_a.py::test_AC_S_01_1_x"]}
        L._observe_tests(led, E(), "S-01", 1, "aaa", 1.0)
        st = {k: (v.status if hasattr(v, "status") else v) for k, v in led.behaviors.items()} if hasattr(led, "behaviors") else {}
        print("S7 ledger:", st)
        ac = next((v for k, v in led.behaviors.items() if k.endswith("S-01-1")), None)
        self.assertNotEqual(getattr(ac, "status", None), "VERIFIED", "a skipped test verified nothing")


if __name__ == "__main__":
    unittest.main(verbosity=1)
