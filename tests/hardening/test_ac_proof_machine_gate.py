"""Every way a plan can declare its proof obligations wrongly, refused by name at the machine gate.

Mutation qualification (Phase 13) of `ac_proof_defects`: each branch below is a distinct plan defect, and the gate
that does not name it is the gate that lets a whole run be spent on it (owner decision 2026-09-20, sections 8-9).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.control.machine_gate import ac_proof_defects, ac_proof_warnings  # noqa: E402
from aisef.control.normalize import PRD, Requirement  # noqa: E402

SID = "STORY-01-01"
PRD_2 = PRD(requirements=[Requirement(id="FR-1", kind="functional", title="one"),
                          Requirement(id="FR-2", kind="functional", title="two")])


def decl(*modes, requirement="FR-1", start=1):
    return {f"AC-{SID}-{i}": {"ac_id": f"AC-{SID}-{i}", "proof_mode": m, "requirement": requirement}
            for i, m in enumerate(modes, start)}


def defects(n, obligations, *, kind="NORMAL", covers=("FR-1",), prd=PRD_2):
    return ac_proof_defects({SID: n}, {SID: obligations}, {SID: kind}, {SID: list(covers)}, prd)


class TestEveryPlanDefectIsNamed(unittest.TestCase):
    def test_the_ordinary_plan_is_accepted(self):
        self.assertEqual(defects(2, decl("CHANGE_REQUIRED", "PRESERVE_REQUIRED")), [])

    def test_an_unknown_story_type(self):
        out = defects(1, decl("CHANGE_REQUIRED"), kind="TEST_ONLY")
        self.assertTrue(any("story_type" in o and "TEST_ONLY" in o for o in out), out)

    def test_a_story_that_declares_nothing_at_all(self):
        out = defects(3, {})
        self.assertEqual(len(out), 1, out)
        self.assertIn("declares no proof obligation for its 3 acceptance criteria", out[0])
        self.assertIn("CHANGE_REQUIRED|PRESERVE_REQUIRED|NEGATIVE_INVARIANT", out[0])

    def test_criteria_left_without_an_obligation_are_listed(self):
        out = defects(3, decl("CHANGE_REQUIRED"))
        self.assertTrue(any(f"no proof obligation for AC-{SID}-2, AC-{SID}-3" in o for o in out), out)

    def test_more_than_five_missing_criteria_are_summarised(self):
        out = defects(8, decl("CHANGE_REQUIRED"))
        row = next(o for o in out if "no proof obligation for" in o)
        self.assertIn("(+2 more)", row)
        self.assertEqual(row.count("AC-"), 5)

    def test_an_unknown_proof_mode(self):
        out = defects(1, decl("MUST_NOT_REGRESS"))
        self.assertTrue(any("declares proof mode 'MUST_NOT_REGRESS'" in o for o in out), out)

    def test_an_entry_the_parser_could_not_read(self):
        out = defects(1, {"?1": {"ac_id": None, "proof_mode": None, "requirement": "", "raw": "nonsense"}})
        self.assertTrue(any("unreadable entry" in o and "nonsense" in o for o in out), out)

    def test_an_obligation_for_a_criterion_that_no_longer_exists(self):
        out = defects(1, decl("CHANGE_REQUIRED", "CHANGE_REQUIRED"))
        self.assertTrue(any(f"AC-{SID}-2 has a proof obligation but no such criterion (the story has 1)" in o
                            for o in out), out)

    def test_an_obligation_that_names_no_requirement(self):
        out = defects(1, decl("CHANGE_REQUIRED", requirement=""))
        self.assertTrue(any("names no requirement" in o for o in out), out)

    def test_a_requirement_the_prd_does_not_carry(self):
        out = defects(1, decl("CHANGE_REQUIRED", requirement="FR-99"))
        self.assertTrue(any("names requirement FR-99, which the PRD does not carry" in o for o in out), out)

    def test_a_requirement_outside_the_storys_own_coverage(self):
        out = defects(1, decl("CHANGE_REQUIRED", requirement="FR-2"), covers=("FR-1",))
        self.assertTrue(any("which this story does not cover (FR-1)" in o for o in out), out)

    def test_a_requirement_is_not_checked_against_coverage_when_the_story_declares_none(self):
        self.assertEqual(defects(1, decl("CHANGE_REQUIRED", requirement="FR-2"), covers=()), [])

    def test_without_a_prd_the_requirement_name_is_taken_as_given(self):
        self.assertEqual(defects(1, decl("CHANGE_REQUIRED", requirement="FR-99"), covers=(), prd=None), [])

    def test_a_normal_story_that_contributes_no_new_behaviour(self):
        out = defects(2, decl("PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"))
        self.assertEqual(len(out), 1, out)
        self.assertIn("no CHANGE_REQUIRED obligation", out[0])
        self.assertIn("VERIFICATION_ONLY", out[0])

    def test_a_verification_only_story_may_contribute_none(self):
        self.assertEqual(defects(2, decl("PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"), kind="VERIFICATION_ONLY"), [])

    def test_a_story_with_no_criteria_is_left_to_the_criteria_gate(self):
        self.assertEqual(defects(0, {}), [])

    def test_the_contribution_error_is_not_repeated_when_nothing_is_declared(self):
        """One defect, one line: a story that declares nothing must not also be accused of contributing nothing."""
        out = defects(2, {})
        self.assertEqual(len(out), 1, out)

    def test_a_lowercase_story_type_is_accepted_as_the_same_type(self):
        self.assertEqual(defects(1, decl("PRESERVE_REQUIRED"), kind="verification_only"), [])


class TestDuplicateChangeOwnershipIsWarned(unittest.TestCase):
    def test_two_stories_changing_one_requirement_are_named(self):
        w = ac_proof_warnings({"S-1": decl("CHANGE_REQUIRED"), "S-2": {"AC-S-2-1": {"proof_mode": "CHANGE_REQUIRED",
                                                                                   "requirement": "FR-1"}}})
        self.assertEqual(len(w), 1)
        self.assertIn("FR-1 is CHANGE_REQUIRED in 2 stories", w[0])

    def test_one_story_changing_it_twice_is_not_a_duplicate(self):
        self.assertEqual(ac_proof_warnings({"S-1": decl("CHANGE_REQUIRED", "CHANGE_REQUIRED")}), [])

    def test_preserving_the_same_requirement_elsewhere_is_not_a_duplicate(self):
        self.assertEqual(ac_proof_warnings({"S-1": decl("CHANGE_REQUIRED"),
                                            "S-2": {"AC-S-2-1": {"proof_mode": "PRESERVE_REQUIRED",
                                                                 "requirement": "FR-1"}}}), [])


if __name__ == "__main__":
    unittest.main()
