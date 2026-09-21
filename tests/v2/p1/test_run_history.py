"""P1 retry/CI policy — a rerun never erases a failure, and no attempt disappears from the history."""

import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("run_history", ROOT / "validation" / "v2" / "run_history.py")
rh = importlib.util.module_from_spec(_s)
_s.loader.exec_module(rh)
POLICY = json.loads((ROOT / rh.POLICY_REL).read_text(encoding="utf-8"))
C = "c" * 40


def attempt(seq, result, **kw):
    e = {"seq": seq, "commit": C, "where": "ci", "job": "unit (windows-latest, 3.11)", "result": result,
         "failing_tests": [], "classification": None, "retry_permitted": False, "gate_effect": "COUNTS",
         "v1_evidence_changed": False, "retry_of": None}
    if result == "FAIL":
        e.update(failing_tests=["t"], classification="PRODUCT", classification_evidence="log signature")
    return {**e, **kw}


class RunHistory(unittest.TestCase):
    def test_committed_history_and_policy_are_consistent(self):
        self.assertEqual(rh.check(ROOT), [])
        self.assertEqual(POLICY["retryable_classes"], ["ENVIRONMENT", "PROVIDER"])

    def test_a_rerun_of_a_non_retryable_failure_is_diagnostic_only_and_the_gate_stays_red(self):
        runs = [attempt(1, "FAIL"), attempt(2, "PASS", retry_of=1)]
        self.assertTrue(any("diagnostic only" in p for p in rh.entry_problems(runs, POLICY)))
        diag = [runs[0], {**runs[1], "gate_effect": "DIAGNOSTIC_ONLY"}]
        self.assertEqual(rh.entry_problems(diag, POLICY), [])
        self.assertFalse(rh.gate_green(diag, C, "ci", "unit (windows-latest, 3.11)"))

    def test_a_preregistered_retryable_failure_may_be_retried_once(self):
        env = attempt(1, "FAIL", classification="ENVIRONMENT", retry_permitted=True)
        runs = [env, attempt(2, "PASS", retry_of=1)]
        self.assertEqual(rh.entry_problems(runs, POLICY), [])
        self.assertTrue(rh.gate_green(runs, C, "ci", "unit (windows-latest, 3.11)"))
        env2 = attempt(2, "FAIL", classification="ENVIRONMENT", retry_permitted=True, retry_of=1)
        third = [env, env2, attempt(3, "PASS", retry_of=2)]
        self.assertTrue(any("preregistered" in p for p in rh.entry_problems(third, POLICY)))

    def test_retry_permission_is_read_from_the_class_never_asserted(self):
        self.assertTrue(rh.entry_problems([attempt(1, "FAIL", retry_permitted=True)], POLICY))

    def test_V1_PF_001_recurrence_must_stop_the_gate(self):
        hit = attempt(1, "FAIL", known_defect="V1-PF-001")
        self.assertTrue(any("STOP" in p for p in rh.entry_problems([hit], POLICY)))
        self.assertEqual(rh.entry_problems([{**hit, "gate_effect": "STOP"}], POLICY), [])

    def test_a_removed_or_rewritten_attempt_is_detected(self):
        a, b = attempt(1, "FAIL"), attempt(2, "PASS", gate_effect="DIAGNOSTIC_ONLY", retry_of=1)
        self.assertEqual(rh.append_only_problems([[a], [a, b]]), [])
        self.assertTrue(rh.append_only_problems([[a, b], [b]]))
        self.assertTrue(rh.append_only_problems([[a], [{**a, "result": "PASS"}]]))

    def test_a_pass_that_changed_v1_evidence_is_not_a_pass(self):
        self.assertTrue(rh.entry_problems([attempt(1, "PASS", v1_evidence_changed=True)], POLICY))


if __name__ == "__main__":
    unittest.main()
