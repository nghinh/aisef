"""Negative controls for the W1 oracle ownership model (owner decision "COMPLETE W1 RUNS 2-3", section 1).

The W1 qualification driver decides whether a red hidden-oracle check is a framework FALSE PASS or an expected red of an
incomplete delivery. A classifier that cannot say FALSE PASS is not a gate (that was SS-77), so every branch here is
driven to its answer from constructed inputs — no run, no model, no network.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "closure-evidence/hardening/w1/w1_driver.py"

_spec = importlib.util.spec_from_file_location("w1_driver_for_tests", DRIVER)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
classify_oracle, classify_run = _mod.classify_oracle, _mod.classify_run

# One story per FR keeps the controls readable: FR-1 -> STORY-A, FR-2 -> STORY-B.
COVERS = {"STORY-A": ["FR-1"], "STORY-B": ["FR-2"]}
MAP = {"ownership": {"t_story": "STORY_OWNED", "t_global": "PROJECT_GLOBAL"}, "t_story": ["FR-1"], "t_global": []}
ALL_DONE = {"STORY-A": {"status": "done"}, "STORY-B": {"status": "done"}}
ONE_OPEN = {"STORY-A": {"status": "done"}, "STORY-B": {"status": "failed"}}


def cls(results, fr_map=MAP, covers=COVERS, state=ALL_DONE):
    out = classify_oracle(results, fr_map, covers, state)
    return out, {r["test"]: r["classification"] for r in out["reds"]}


class TestStoryOwnedReds(unittest.TestCase):
    def test_a_red_whose_owner_stories_are_all_done_is_a_false_pass(self):
        out, by = cls({"T::t_story": "FAILED"})
        self.assertEqual(by["T::t_story"], "POTENTIAL_FALSE_PASS")
        self.assertEqual(out["false_pass_count"], 1)

    def test_a_red_with_one_owner_story_not_done_is_an_expected_red(self):
        # STORY-A owns FR-1 and is done; give the test both FRs so STORY-B (failed) is also an owner.
        fr_map = {**MAP, "t_story": ["FR-1", "FR-2"]}
        out, by = cls({"T::t_story": "FAILED"}, fr_map=fr_map, state=ONE_OPEN)
        self.assertEqual(by["T::t_story"], "INCOMPLETE_DELIVERY_EXPECTED_RED")
        self.assertEqual(out["false_pass_count"], 0)
        self.assertEqual(out["story_owned_reds_expected"], ["T::t_story"])


class TestProjectGlobalReds(unittest.TestCase):
    def test_a_project_global_red_on_a_complete_delivery_is_a_false_pass(self):
        out, by = cls({"T::t_global": "FAILED"}, state=ALL_DONE)
        self.assertTrue(out["delivery_complete"])
        self.assertEqual(by["T::t_global"], "FALSE_PASS")
        self.assertEqual(out["false_pass_count"], 1)

    def test_a_project_global_red_on_an_incomplete_delivery_is_an_expected_red(self):
        out, by = cls({"T::t_global": "FAILED"}, state=ONE_OPEN)
        self.assertEqual(by["T::t_global"], "INCOMPLETE_DELIVERY_EXPECTED_RED")
        self.assertEqual(out["false_pass_count"], 0)
        self.assertEqual(out["project_global_reds_expected"], ["T::t_global"])

    def test_an_unstarted_story_cannot_make_a_delivery_look_complete(self):
        # STORY-B never started, so it is absent from the state store. That is not a complete delivery.
        out, _ = cls({"T::t_global": "FAILED"}, state={"STORY-A": {"status": "done"}})
        self.assertFalse(out["delivery_complete"])
        self.assertEqual(out["false_pass_count"], 0)


class TestMappingErrors(unittest.TestCase):
    def test_an_undeclared_check_is_a_mapping_error_and_blocks_qualification(self):
        out, by = cls({"T::t_unknown": "FAILED"})
        self.assertEqual(by["T::t_unknown"], "ORACLE_MAPPING_ERROR")
        self.assertEqual(out["oracle_mapping_error_count"], 1)
        self.assertFalse(out["classifiable"])

    def test_story_owned_with_no_owning_story_is_a_mapping_error_not_a_silent_pass(self):
        fr_map = {"ownership": {"t_story": "STORY_OWNED"}, "t_story": ["FR-99"]}
        out, by = cls({"T::t_story": "FAILED"}, fr_map=fr_map)
        self.assertEqual(by["T::t_story"], "ORACLE_MAPPING_ERROR")
        self.assertFalse(out["classifiable"])

    def test_no_red_is_ever_dropped(self):
        results = {"T::t_story": "FAILED", "T::t_global": "FAILED", "T::t_unknown": "ERROR", "T::t_ok": "PASSED"}
        out, by = cls(results)
        self.assertEqual(set(by), {"T::t_story", "T::t_global", "T::t_unknown"})
        self.assertEqual(sum(out["counts"].values()), 3)


class TestNoStructuredState(unittest.TestCase):
    def test_a_missing_state_store_makes_every_red_a_false_pass(self):
        out, by = cls({"T::t_story": "FAILED", "T::t_global": "FAILED"}, state={})
        self.assertEqual(set(by.values()), {"FALSE_PASS"})
        self.assertEqual(out["false_pass_count"], 2)
        self.assertFalse(out["classifiable"])


class TestRunClassification(unittest.TestCase):
    def test_every_story_done_is_delivery_complete(self):
        self.assertEqual(classify_run(ALL_DONE, 2, [], []), "DELIVERY_COMPLETE")

    def test_a_story_that_never_started_is_not_a_complete_delivery(self):
        self.assertEqual(classify_run({"STORY-A": {"status": "done"}}, 2, [], []), "LEGITIMATE_MODEL_PROJECT_STOP")

    def test_an_exhausted_story_is_a_legitimate_stop_not_a_framework_failure(self):
        self.assertEqual(classify_run(ONE_OPEN, 2, [], []), "LEGITIMATE_MODEL_PROJECT_STOP")

    def test_a_safety_violation_outranks_a_complete_delivery(self):
        self.assertEqual(classify_run(ALL_DONE, 2, ["false_pass=1"], []), "FRAMEWORK_FAILURE")

    def test_a_story_waiting_on_a_person_is_human_required(self):
        self.assertEqual(classify_run({"STORY-A": {"status": "human"}}, 1, [], []), "HUMAN_REQUIRED")

    def test_no_state_is_a_framework_failure_never_a_pass(self):
        self.assertEqual(classify_run({}, 2, [], []), "FRAMEWORK_FAILURE")



class TestOracleResultParsing(unittest.TestCase):
    """SS-79: nine skipped checks once collapsed into one entry called "[1]" and eight outcomes were lost."""

    VERBOSE_SKIPS = "\n".join(
        f"oracle/test_oracle.py::TestAcceptance::test_{i} SKIPPED (AISEF_W1_PROJECT must point at a delivered LedgerLock) [ 11%]"
        for i in range(1, 10)) + "\n" + "\n".join(
        f"SKIPPED [1] oracle/test_oracle.py:{70 + i}: AISEF_W1_PROJECT must point at a delivered LedgerLock" for i in range(9)) + \
        "\n9 skipped in 0.01s\n"

    def test_every_skipped_check_is_recovered_with_its_own_name(self):
        out = _mod.parse_oracle(self.VERBOSE_SKIPS)
        self.assertEqual(out["parsed"], 9)
        self.assertTrue(out["complete"])
        self.assertEqual(set(out["results"].values()), {"SKIPPED"})

    def test_a_parse_that_loses_outcomes_is_rejected(self):
        # pytest counted 9, only one per-test line present: the parse must not be believed.
        out = _mod.parse_oracle("oracle/test_oracle.py::T::test_1 SKIPPED (why) [100%]\n9 skipped in 0.01s\n")
        self.assertFalse(out["complete"])
        self.assertIn("recovered 1", out["why"])

    def test_mixed_outcomes_reconcile(self):
        stdout = ("oracle/test_oracle.py::T::test_a PASSED [ 50%]\n"
                  "oracle/test_oracle.py::T::test_b FAILED [100%]\n"
                  "1 failed, 1 passed in 0.10s\n")
        out = _mod.parse_oracle(stdout)
        self.assertTrue(out["complete"])
        self.assertEqual(out["results"], {"T::test_a": "PASSED", "T::test_b": "FAILED"})


class TestSkippedIsNeverAPass(unittest.TestCase):
    def test_a_skipped_check_on_a_complete_delivery_blocks_qualification(self):
        out = classify_oracle({"T::t_story": "SKIPPED"}, MAP, COVERS, ALL_DONE)
        self.assertEqual(out["skipped"][0]["classification"], "ORACLE_NOT_EXECUTED")
        self.assertFalse(out["classifiable"])
        self.assertFalse(out["oracle_passed_completely"])

    def test_a_skipped_check_on_an_incomplete_delivery_is_expected(self):
        out = classify_oracle({"T::t_story": "SKIPPED"}, MAP, COVERS, ONE_OPEN)
        self.assertEqual(out["skipped"][0]["classification"], "INCOMPLETE_DELIVERY_EXPECTED_SKIP")
        self.assertTrue(out["classifiable"])

    def test_oracle_passed_completely_needs_every_check_green_on_a_complete_delivery(self):
        self.assertTrue(classify_oracle({"T::t_story": "PASSED", "T::t_global": "PASSED"}, MAP, COVERS, ALL_DONE)["oracle_passed_completely"])
        self.assertFalse(classify_oracle({"T::t_story": "PASSED", "T::t_global": "FAILED"}, MAP, COVERS, ALL_DONE)["oracle_passed_completely"])
        self.assertFalse(classify_oracle({}, MAP, COVERS, ALL_DONE)["oracle_passed_completely"])

if __name__ == "__main__":
    unittest.main()
