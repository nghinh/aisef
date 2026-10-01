"""P1 retry/CI policy — a rerun never erases a failure, and no attempt disappears from the history."""

import importlib.util
import json
import pathlib
import shutil
import tempfile
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
        self.assertFalse(rh.gate_green(diag, C, "ci", "unit (windows-latest, 3.11)", POLICY))

    def test_no_approved_retry_count_means_a_retry_never_satisfies_a_gate(self):
        """Owner correction (P1 review): no global cap; with no approved count a retry is diagnostic only."""
        self.assertNotIn("max_gate_retries_per_attempt_chain", POLICY)
        self.assertIsNone(rh.approved_retry_count(POLICY, "ci"))
        self.assertIsNone(rh.approved_retry_count(POLICY, "local"))
        env = attempt(1, "FAIL", classification="ENVIRONMENT", retry_permitted=True)
        counting = [env, attempt(2, "PASS", retry_of=1)]
        self.assertTrue(any("no approved retry count" in p for p in rh.entry_problems(counting, POLICY)))
        diagnostic = [env, attempt(2, "PASS", retry_of=1, gate_effect="DIAGNOSTIC_ONLY")]
        self.assertEqual(rh.entry_problems(diagnostic, POLICY), [])
        self.assertFalse(rh.gate_green(diagnostic, C, "ci", "unit (windows-latest, 3.11)", POLICY))

    def test_an_approved_count_comes_from_the_resolved_policy_and_bounds_retries(self):
        resolved = json.loads(json.dumps(POLICY))
        resolved["retry_count"]["approved_counts_by_execution_path"]["phase-gate:ci"] = 1
        env = attempt(1, "FAIL", classification="ENVIRONMENT", retry_permitted=True)
        runs = [env, attempt(2, "PASS", retry_of=1)]
        self.assertEqual(rh.entry_problems(runs, resolved), [])
        self.assertTrue(rh.gate_green(runs, C, "ci", "unit (windows-latest, 3.11)", resolved))
        env2 = attempt(2, "FAIL", classification="ENVIRONMENT", retry_permitted=True, retry_of=1)
        third = [env, env2, attempt(3, "PASS", retry_of=2)]
        self.assertTrue(any("more gate-counting retries than the approved 1" in p
                            for p in rh.entry_problems(third, resolved)))
        self.assertFalse(rh.gate_green(third, C, "ci", "unit (windows-latest, 3.11)", resolved))

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

    def test_a_sealed_history_takes_no_attempt_and_loses_none(self):
        seal = {"attempt_history": {"total_attempts": 2}}
        runs = [attempt(1, "PASS"), attempt(2, "PASS")]
        self.assertEqual(rh.seal_problems("P1", runs, seal), [])
        self.assertEqual(rh.seal_problems("P1", runs + [attempt(3, "PASS")], None), [])
        for changed in (runs + [attempt(3, "PASS")], runs[:1]):
            with self.subTest(n=len(changed)):
                self.assertRegex(rh.seal_problems("P1", changed, seal)[0], "^P1 history is sealed at 2 attempts")

    def test_sealed_histories_are_closed_and_new_attempts_go_to_the_open_phase(self):
        sealed = {ph: json.loads((ROOT / rh.HISTORIES[ph]).read_text(encoding="utf-8"))["entries"] for ph in rh.SEALS}
        for phase, entries in sealed.items():
            seal = json.loads((ROOT / rh.SEALS[phase]).read_text(encoding="utf-8"))
            self.assertEqual(len(entries), seal["attempt_history"]["total_attempts"], phase)
        opened = next(ph for ph in rh.HISTORIES if ph not in rh.SEALS)
        self.assertEqual(rh.open_phase(ROOT), opened)
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            for rel in (rh.POLICY_REL, *(rh.HISTORIES[ph] for ph in rh.SEALS), *rh.SEALS.values()):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, root / rel)
            for phase in rh.SEALS:
                with self.subTest(phase=phase), self.assertRaisesRegex(SystemExit, f"the {phase} history is sealed"):
                    rh.record({**attempt(1, "PASS"), "seq": None}, root=root, phase=phase)
            entry = rh.record({k: v for k, v in attempt(1, "PASS").items() if k != "seq"}, root=root)
            self.assertEqual(entry["seq"], 1)
            self.assertTrue((root / rh.HISTORIES[opened]).exists())
            for phase, entries in sealed.items():
                self.assertEqual(json.loads((root / rh.HISTORIES[phase]).read_text(encoding="utf-8"))["entries"],
                                 entries)

    def test_a_pass_that_changed_v1_evidence_is_not_a_pass(self):
        self.assertTrue(rh.entry_problems([attempt(1, "PASS", v1_evidence_changed=True)], POLICY))


if __name__ == "__main__":
    unittest.main()
