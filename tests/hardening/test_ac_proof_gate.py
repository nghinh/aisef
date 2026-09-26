"""The story gate under TDD proof policy V2: each criterion judged by its declared obligation, on real evidence.

Companion to test_ac_proof_policy.py (the transition table) — here the same rules are read out of an evidence store
through the one proof engine, which is where policy V1 produced the W1 workload's refusals.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.control.gate import evaluate  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.harness.observe import EvidenceStore  # noqa: E402

SID = "S-01"
CHECK = "tests verify story"
AC1 = "tests/test_a.py::test_AC_S_01_1_x"
AC2 = "tests/test_a.py::test_AC_S_01_2_y"
AC3 = "tests/test_a.py::test_AC_S_01_3_z"


def decl(*modes: str) -> dict:
    """`decl("CHANGE_REQUIRED", "PRESERVE_REQUIRED")` -> planning data for criteria 1..n, in order."""
    return {f"AC-{SID}-{i}": {"ac_id": f"AC-{SID}-{i}", "proof_mode": m, "requirement": "FR-1"}
            for i, m in enumerate(modes, 1)}


class GateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = EvidenceStore(self._tmp.name)

    def baseline(self, ids, failed=()):
        self.store.tool_run(SID, "test:baseline", ok=not failed, detail={
            "baseline": True, "test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed),
            "skipped_ids": []})

    def candidate(self, ids, failed=()):
        st = EvidenceStore(self._tmp.name, candidate="aaa")
        st.file_change(SID, "src/a.py")
        st.tool_run(SID, "test", ok=not failed, detail={
            "test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed)})
        st.tool_run(SID, "lint", ok=True)
        st.tool_run(SID, "qa:fake-tests", ok=True, detail={"files": []})

    def nop(self, ids, failed=(), **detail):
        EvidenceStore(self._tmp.name, candidate="aaa").tool_run(SID, "test:nop", ok=not failed, detail={
            "nop": True, "parent": "cha0000", "files": ["tests/test_a.py"], "test_format": "pytest",
            "test_ids": list(ids), "failed_ids": list(failed), "absent_at_parent": ["src/a.py"], **detail})

    def check(self, acceptance: int, ac_proof: dict, name: str = CHECK):
        g = evaluate(SID, self.store.read(SID), changed=["src/a.py", "tests/test_a.py"], write_scope=["src", "tests"],
                     screens=[], review_blocking=[], candidate="aaa", acceptance=acceptance, ac_proof=ac_proof,
                     added_tests=["tests/test_a.py"])
        return next(c for c in g.checks if c.name == name)

    def rows(self, check) -> dict:
        return {r["ac_id"]: r for r in (check.data or {}).get("rows", [])}


class TestGateJudgesEachCriterionByItsObligation(GateCase):
    """H, at the gate: one story, three obligations, one verdict each — from one nop run and one candidate run."""

    def test_a_mixed_story_gets_one_verdict_per_criterion(self):
        self.baseline([AC2, AC3, "t1"])
        self.candidate([AC1, AC2, AC3, "t1"])
        self.nop([AC2, AC3, "t1"], failed=[])                       # AC1 absent at the parent, AC2/AC3 green there
        self.nop([AC1, AC2, AC3, "t1"], failed=[AC1])               # the newest nop decides: AC1 red
        m = self.check(3, decl("CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"))
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        rows = self.rows(m)
        self.assertEqual([rows[f"AC-{SID}-{i}"]["outcome"] for i in (1, 2, 3)], ["SATISFIED"] * 3)
        self.assertEqual(rows[f"AC-{SID}-1"]["actual_transition"], "RED -> GREEN")
        self.assertEqual(rows[f"AC-{SID}-2"]["actual_transition"], "GREEN -> GREEN")

    def test_k_a_criterion_an_upstream_story_delivers_passes_as_preserve_required(self):
        """K. The behaviour is already there at the story's entry — declared PRESERVE_REQUIRED, it passes; declared
        CHANGE_REQUIRED, the same evidence is a PLAN defect and names the plan as its owner."""
        # the story writes a NEW test for the criterion (so level 1's "tagged an existing test" does not apply);
        # it is green at the parent because an upstream story already delivers the behaviour
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"])
        ok = self.check(1, decl("PRESERVE_REQUIRED"))
        self.assertIs(ok.outcome, Outcome.PASSED, ok.detail)
        bad = self.check(1, decl("CHANGE_REQUIRED"))
        self.assertIs(bad.outcome, Outcome.FAILED)
        self.assertEqual(self.rows(bad)[f"AC-{SID}-1"]["outcome"], "PLAN_OVERLAP")
        self.assertEqual(self.rows(bad)[f"AC-{SID}-1"]["owner"], "PLAN")

    def test_a_preserved_behaviour_broken_by_this_story_is_a_developer_regression(self):
        self.baseline([AC1, "t1"])
        self.candidate([AC1, "t1"], failed=[AC1])
        self.nop([AC1, "t1"])
        m = self.check(1, decl("PRESERVE_REQUIRED"))
        self.assertIs(m.outcome, Outcome.FAILED)
        row = self.rows(m)[f"AC-{SID}-1"]
        self.assertEqual((row["outcome"], row["owner"]), ("DEVELOPER_REGRESSION", "DEVELOPER"))

    def test_a_negative_invariant_green_on_both_sides_passes_without_a_manufactured_red(self):
        self.baseline([AC1, "t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"])
        m = self.check(1, decl("NEGATIVE_INVARIANT"))
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertEqual(self.rows(m)[f"AC-{SID}-1"]["expected_transition"], "GREEN -> GREEN")

    def test_the_tdd_check_asks_nothing_of_a_story_that_changes_nothing(self):
        self.baseline([AC1, "t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"])
        tdd = self.check(1, decl("NEGATIVE_INVARIANT"), name="TDD")
        self.assertIs(tdd.outcome, Outcome.NOT_APPLICABLE, tdd.detail)
        self.assertIn("no criterion of this story is CHANGE_REQUIRED", tdd.detail)

    def test_l_a_plan_with_no_declared_obligation_is_refused_by_the_plan_not_the_developer(self):
        """L / J at the gate: the kernel refuses rather than reading the criterion's wording."""
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"], failed=[AC1])
        m = self.check(1, {})
        self.assertIs(m.outcome, Outcome.FAILED)
        # one sentence for the whole plan defect, not one row per criterion: the story declares nothing at all
        self.assertTrue(m.detail.startswith("no criterion declares what it must show (proof obligation)"), m.detail)
        self.assertEqual(m.data["owners"], ["PLAN"])
        self.assertEqual(self.rows(m)[f"AC-{SID}-1"]["outcome"], "PLAN_METADATA_MISSING")

    def test_evidence_that_did_not_execute_is_the_environments_not_a_pass(self):
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop(["t1"], unrunnable="", skipped_ids=[AC1], test_ids=["t1", AC1])
        m = self.check(1, decl("CHANGE_REQUIRED"))
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertEqual(self.rows(m)[f"AC-{SID}-1"]["outcome"], "NO_EVIDENCE")
        self.assertIn("SKIPPED", self.rows(m)[f"AC-{SID}-1"]["parent_states"])

    def test_policy_v2_with_every_criterion_change_required_answers_exactly_as_policy_v1(self):
        """The migration's own control: V1's universal rule is V2 with every criterion declared CHANGE_REQUIRED."""
        self.baseline(["t1"])
        self.candidate([AC1, AC2, "t1"])
        self.nop([AC1, AC2, "t1"], failed=[AC1, AC2])
        self.assertIs(self.check(2, decl("CHANGE_REQUIRED", "CHANGE_REQUIRED")).outcome, Outcome.PASSED)
        self.setUp()
        self.baseline(["t1"])
        self.candidate([AC1, AC2, "t1"])
        self.nop([AC1, AC2, "t1"], failed=[AC1])                    # AC2 green at the parent — V1 blocked here
        self.assertIs(self.check(2, decl("CHANGE_REQUIRED", "CHANGE_REQUIRED")).outcome, Outcome.FAILED)


class TestStoryThatContributesNothingNeverReachesAModel(unittest.TestCase):
    """G, before the first model call: preflight refuses the story, so no developer attempt is spent on it."""

    def story(self, modes, story_type="NORMAL"):
        from aisef.control.normalize import Story

        st = Story(id="STORY-01-02", epic_id="EPIC-01", title="t", write_scope=["src"], covers=["FR-1"],
                   acceptance_criteria=[f"criterion {i}" for i in range(1, len(modes) + 1)])
        st.story_type = story_type
        st.ac_proof = {f"AC-{st.id}-{i}": {"ac_id": f"AC-{st.id}-{i}", "proof_mode": m, "requirement": "FR-1"}
                       for i, m in enumerate(modes, 1)}
        return st

    def defect(self, story):
        from aisef.control.preflight import ac_proof_defect

        return ac_proof_defect(story)

    def test_a_story_whose_every_criterion_is_already_satisfied_is_refused(self):
        need = self.defect(self.story(["PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"]))
        self.assertIsNotNone(need)
        self.assertEqual(need.kind, "story")
        self.assertTrue(need.blocks_run)
        self.assertIn("CHANGE_REQUIRED", need.evidence)

    def test_a_verification_only_story_is_allowed_to_contribute_no_new_behaviour(self):
        self.assertIsNone(self.defect(self.story(["PRESERVE_REQUIRED"], story_type="VERIFICATION_ONLY")))

    def test_an_ordinary_story_passes(self):
        self.assertIsNone(self.defect(self.story(["CHANGE_REQUIRED", "PRESERVE_REQUIRED"])))

    def test_a_criterion_without_an_obligation_is_refused_before_any_model_call(self):
        st = self.story(["CHANGE_REQUIRED"])
        st.acceptance_criteria.append("a criterion the plan forgot")
        need = self.defect(st)
        self.assertIsNotNone(need)
        self.assertIn("AC-STORY-01-02-2", need.evidence)


class TestPlanOwnedFailureNeverSpendsADeveloperAttempt(GateCase):
    """Section 12: routing reads the row's owner, so a planning fact ends the story instead of retrying it."""

    def gate_with_plan_row(self):
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"])                                        # green at the parent: the plan's own defect
        return evaluate(SID, self.store.read(SID), changed=["src/a.py"], write_scope=["src"], screens=[],
                        review_blocking=[], candidate="aaa", acceptance=1,
                        ac_proof=decl("CHANGE_REQUIRED"))

    def test_a_plan_owned_criterion_is_reported_for_routing(self):
        from aisef.phases.implement import Attempt, plan_owned_criteria

        a = Attempt(number=1)
        a.gate = self.gate_with_plan_row()
        found = plan_owned_criteria(a)
        self.assertTrue(found)
        self.assertIn("AC-S-01-1", found[0])
        self.assertIn("PLAN_OVERLAP", found[0])

    def test_a_developer_owned_failure_is_not_routed_to_the_plan(self):
        from aisef.phases.implement import Attempt, plan_owned_criteria

        self.baseline(["t1"])
        self.candidate([AC1, "t1"], failed=[AC1])
        self.nop([AC1, "t1"], failed=[AC1])
        a = Attempt(number=1)
        a.gate = evaluate(SID, self.store.read(SID), changed=["src/a.py"], write_scope=["src"], screens=[],
                          review_blocking=[], candidate="aaa", acceptance=1, ac_proof=decl("CHANGE_REQUIRED"))
        self.assertEqual(plan_owned_criteria(a), [])

    def test_an_attempt_without_a_gate_routes_nothing(self):
        from aisef.phases.implement import Attempt, plan_owned_criteria

        self.assertEqual(plan_owned_criteria(Attempt(number=1)), [])


class TestRoutingReadsTheRowsNotTheWording(GateCase):
    """Mutation qualification of `plan_owned_criteria`: it reads the check's structured rows, and only the rows
    whose owner is the PLAN."""

    def attempt_with(self, rows, name=CHECK, failed=True):
        from aisef.control.outcome import Check
        from aisef.phases.implement import Attempt

        class _Gate:
            def __init__(self, checks):
                self.checks = checks

            @property
            def failures(self):
                return [c for c in self.checks if c.outcome is Outcome.FAILED]

        a = Attempt(number=1)
        a.gate = _Gate([Check(name, Outcome.FAILED if failed else Outcome.PASSED, "d", data={"rows": rows})])
        return a

    ROW_PLAN = {"ac_id": "AC-S-01-1", "proof_mode": "CHANGE_REQUIRED", "actual_transition": "GREEN -> GREEN",
                "outcome": "PLAN_OVERLAP", "owner": "PLAN", "why": "already there"}
    ROW_DEV = {"ac_id": "AC-S-01-2", "proof_mode": "CHANGE_REQUIRED", "actual_transition": "RED -> RED",
               "outcome": "DEVELOPER_QUALITY_BLOCK", "owner": "DEVELOPER", "why": "still red"}

    def test_only_plan_owned_rows_are_returned(self):
        from aisef.phases.implement import plan_owned_criteria

        got = plan_owned_criteria(self.attempt_with([self.ROW_DEV, self.ROW_PLAN]))
        self.assertEqual(len(got), 1)
        self.assertIn("AC-S-01-1", got[0])

    def test_rows_of_another_check_are_not_read(self):
        from aisef.phases.implement import plan_owned_criteria

        self.assertEqual(plan_owned_criteria(self.attempt_with([self.ROW_PLAN], name="review")), [])

    def test_a_check_that_did_not_fail_is_not_read(self):
        from aisef.phases.implement import plan_owned_criteria

        self.assertEqual(plan_owned_criteria(self.attempt_with([self.ROW_PLAN], failed=False)), [])

    def test_a_failing_check_without_rows_routes_nothing(self):
        from aisef.phases.implement import plan_owned_criteria

        self.assertEqual(plan_owned_criteria(self.attempt_with([])), [])

    def test_a_row_without_an_obligation_still_names_the_criterion(self):
        from aisef.phases.implement import plan_owned_criteria

        row = {"ac_id": "AC-S-01-3", "proof_mode": None, "outcome": "PLAN_METADATA_MISSING", "owner": "PLAN"}
        got = plan_owned_criteria(self.attempt_with([row]))
        self.assertEqual(len(got), 1)
        self.assertIn("no obligation", got[0])


class TestTheGateKeepsItsOtherRefusals(GateCase):
    """The obligation model replaced the verdict, not the guards around it: a nop whose own totals do not match the
    tests it read still proves nothing, whatever the obligations say."""

    def test_an_incomplete_nop_output_is_unrunnable_even_when_every_row_is_satisfied(self):
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"], failed=[AC1], output_complete=False)
        m = self.check(1, decl("CHANGE_REQUIRED"))
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertIn("incomplete", m.detail)

    def test_a_complete_nop_output_passes(self):
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"], failed=[AC1], output_complete=True)
        self.assertIs(self.check(1, decl("CHANGE_REQUIRED")).outcome, Outcome.PASSED)

    def test_a_criterion_left_out_of_the_declaration_is_reported_with_its_gaps_named(self):
        """One criterion declared, one forgotten: the story is not refused wholesale, and the forgotten one's line
        says what is missing rather than printing empty fields."""
        self.baseline(["t1"])
        self.candidate([AC1, AC2, "t1"])
        self.nop([AC1, AC2, "t1"], failed=[AC1, AC2])
        m = self.check(2, decl("CHANGE_REQUIRED"))          # AC-S-01-2 has no obligation at all
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)
        row = self.rows(m)[f"AC-{SID}-2"]
        self.assertEqual((row["outcome"], row["owner"]), ("PLAN_METADATA_MISSING", "PLAN"))
        self.assertIn("no obligation", m.detail)
        self.assertIn("no requirement", m.detail)
        self.assertIn("expected a declared transition", m.detail)

    def test_a_row_with_no_observed_state_on_a_side_says_none(self):
        """The failing line prints what each side actually showed; a side with no test states says `none`."""
        self.baseline(["t1"])
        self.candidate(["t1"])                               # no test carries the criterion's code
        self.nop(["t1"])
        m = self.check(1, decl("CHANGE_REQUIRED"))
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)
        self.assertIn("parent none / candidate none", m.detail)

    def test_the_failing_line_names_the_parent_sha_the_obligation_and_the_owner(self):
        self.baseline(["t1"])
        self.candidate([AC1, "t1"])
        self.nop([AC1, "t1"])
        m = self.check(1, decl("CHANGE_REQUIRED"))
        for part in ("at parent SHA cha0000", "CHANGE_REQUIRED", "FR-1", "expected RED -> GREEN", "PLAN_OVERLAP",
                     "(PLAN)", "parent GREEN_EXECUTED / candidate GREEN_EXECUTED", AC1):
            self.assertIn(part, m.detail)


if __name__ == "__main__":
    unittest.main()
