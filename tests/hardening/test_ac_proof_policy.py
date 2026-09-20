"""TDD proof policy V2 — every criterion is judged by its OWN declared obligation (owner decision 2026-09-20).

The family cases the owner named (section 16) at the level where the rule lives: the transition table (here), the
planning data that carries it (machine gate), and the story gate that consumes it (test_ac_proof_gate.py).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.control import obligation as ob  # noqa: E402
from aisef.control import proof  # noqa: E402
from aisef.control.normalize import ac_proof, parse_epics  # noqa: E402

RED = {"t": (proof.Proof.RED_EXECUTED, "ran and failed")}
BOUND = {"t": (proof.Proof.RED_COLLECTION_BOUND_TO_STORY, "needs a module this story adds")}
GREEN = {"t": (proof.Proof.GREEN_EXECUTED, "ran and passed")}
SKIPPED = {"t": (proof.Proof.SKIPPED, "collected, not executed")}
UNRUNNABLE = {"t": (proof.Proof.ENVIRONMENT_UNRUNNABLE, "docker is not available")}
DEPENDENCY = {"t": (proof.Proof.DEPENDENCY_UNRUNNABLE, "needs pytest, not part of this story")}
ABSENT = {"t": (proof.Proof.ABSENT, "the run completed without it")}
MIXED = {"a": (proof.Proof.GREEN_EXECUTED, ""), "b": (proof.Proof.RED_EXECUTED, "")}


def verdict(mode, parent, candidate):
    return ob.evaluate(mode, ob.side(parent), ob.side(candidate))[0]


class TestSideReading(unittest.TestCase):
    def test_a_side_is_read_from_the_one_proof_engine(self):
        self.assertEqual(ob.side(RED), ob.Side.RED)
        self.assertEqual(ob.side(BOUND), ob.Side.RED, "a collection failure bound to the story proves red")
        self.assertEqual(ob.side(GREEN), ob.Side.GREEN)
        self.assertEqual(ob.side(MIXED), ob.Side.MIXED)
        for state in (SKIPPED, UNRUNNABLE, DEPENDENCY, ABSENT):
            self.assertEqual(ob.side(state), ob.Side.NO_EVIDENCE, state)
        for empty in ({}, None):
            self.assertEqual(ob.side(empty), ob.Side.NO_TESTS, "no test carrying the code is its own answer")


class TestChangeRequired(unittest.TestCase):
    """A. RED -> GREEN passes.  B. already green at the parent is a PLAN fact, not a developer failure."""

    def test_a_red_parent_and_green_candidate_is_satisfied(self):
        self.assertEqual(verdict(ob.Mode.CHANGE_REQUIRED, RED, GREEN), ob.Outcome.SATISFIED)
        self.assertEqual(verdict(ob.Mode.CHANGE_REQUIRED, BOUND, GREEN), ob.Outcome.SATISFIED)

    def test_b_green_at_the_parent_is_plan_overlap_owned_by_the_plan(self):
        out, why = ob.evaluate(ob.Mode.CHANGE_REQUIRED, ob.side(GREEN), ob.side(GREEN))
        self.assertEqual(out, ob.Outcome.PLAN_OVERLAP)
        self.assertEqual(ob.OWNER_OF[out], ob.Owner.PLAN)
        self.assertIn("parent", why)

    def test_b_partly_green_at_the_parent_is_also_plan_overlap(self):
        self.assertEqual(verdict(ob.Mode.CHANGE_REQUIRED, MIXED, GREEN), ob.Outcome.PLAN_OVERLAP)

    def test_a_red_candidate_is_the_developers(self):
        out = verdict(ob.Mode.CHANGE_REQUIRED, RED, RED)
        self.assertEqual(out, ob.Outcome.DEVELOPER_QUALITY_BLOCK)
        self.assertEqual(ob.OWNER_OF[out], ob.Owner.DEVELOPER)


class TestPreserveRequired(unittest.TestCase):
    """C. GREEN -> GREEN passes.  D. GREEN -> RED is a regression the developer owns."""

    def test_c_green_to_green_is_satisfied(self):
        self.assertEqual(verdict(ob.Mode.PRESERVE_REQUIRED, GREEN, GREEN), ob.Outcome.SATISFIED)

    def test_d_green_to_red_is_a_developer_regression(self):
        out = verdict(ob.Mode.PRESERVE_REQUIRED, GREEN, RED)
        self.assertEqual(out, ob.Outcome.DEVELOPER_REGRESSION)
        self.assertEqual(ob.OWNER_OF[out], ob.Owner.DEVELOPER)

    def test_nothing_to_preserve_at_the_parent_is_a_plan_defect(self):
        out = verdict(ob.Mode.PRESERVE_REQUIRED, RED, GREEN)
        self.assertEqual(out, ob.Outcome.PLAN_PRECONDITION_MISSING)
        self.assertEqual(ob.OWNER_OF[out], ob.Owner.PLAN)

    def test_preserving_gives_no_contribution_credit(self):
        ok, why = ob.story_contribution({"AC-S-1": {"proof_mode": "PRESERVE_REQUIRED"}}, ["AC-S-1"])
        self.assertFalse(ok, why)


class TestNegativeInvariant(unittest.TestCase):
    """E. GREEN -> GREEN passes.  F. GREEN -> RED blocks."""

    def test_e_green_to_green_is_satisfied(self):
        self.assertEqual(verdict(ob.Mode.NEGATIVE_INVARIANT, GREEN, GREEN), ob.Outcome.SATISFIED)

    def test_f_green_to_red_blocks_as_a_developer_regression(self):
        out, why = ob.evaluate(ob.Mode.NEGATIVE_INVARIANT, ob.side(GREEN), ob.side(RED))
        self.assertEqual(out, ob.Outcome.DEVELOPER_REGRESSION)
        self.assertIn("prohibition", why)

    def test_no_red_state_is_manufactured_at_the_parent(self):
        """An absence criterion holds on an empty tree; that is not a TDD failure (owner section 7)."""
        self.assertEqual(verdict(ob.Mode.NEGATIVE_INVARIANT, GREEN, GREEN), ob.Outcome.SATISFIED)
        self.assertEqual(verdict(ob.Mode.NEGATIVE_INVARIANT, RED, GREEN), ob.Outcome.PLAN_PRECONDITION_MISSING)


class TestNoEvidenceNeverSatisfies(unittest.TestCase):
    """I. evidence that did not execute satisfies no obligation, on either side."""

    def test_i_unrunnable_or_absent_evidence_satisfies_nothing(self):
        for mode in ob.Mode:
            for state in (UNRUNNABLE, DEPENDENCY, SKIPPED, ABSENT):
                self.assertEqual(verdict(mode, state, GREEN), ob.Outcome.NO_EVIDENCE, (mode, state))
                self.assertEqual(verdict(mode, GREEN if mode is not ob.Mode.CHANGE_REQUIRED else RED, state),
                                 ob.Outcome.NO_EVIDENCE, (mode, state))

    def test_a_criterion_with_no_test_at_the_candidate_is_the_developers(self):
        for mode in ob.Mode:
            out = verdict(mode, GREEN if mode is not ob.Mode.CHANGE_REQUIRED else RED, {})
            self.assertEqual(out, ob.Outcome.DEVELOPER_QUALITY_BLOCK, mode)

    def test_no_evidence_is_owned_by_the_environment_not_the_developer(self):
        self.assertEqual(ob.OWNER_OF[ob.Outcome.NO_EVIDENCE], ob.Owner.ENVIRONMENT)


class TestMissingMetadata(unittest.TestCase):
    """J. a criterion with no declared obligation is a planning failure — the kernel never guesses from prose."""

    def test_j_absent_or_unknown_mode_is_plan_metadata_missing(self):
        for mode in (None, "", "MUST_NOT", "change_required "):
            out, why = ob.evaluate(mode, ob.Side.RED, ob.Side.GREEN)
            self.assertEqual(out, ob.Outcome.PLAN_METADATA_MISSING, mode)
            self.assertEqual(ob.OWNER_OF[out], ob.Owner.PLAN)
        self.assertIn("never guesses", why)

    def test_j_wording_never_decides_the_obligation(self):
        """"must not", "absence", "no matches" in the text change nothing: only declared data does."""
        rows = ob.judge({}, {"AC-S-1": GREEN}, {"AC-S-1": GREEN}, ["AC-S-1"])
        self.assertEqual(rows[0]["outcome"], ob.Outcome.PLAN_METADATA_MISSING.value)


class TestStoryContribution(unittest.TestCase):
    """G. a story with no CHANGE_REQUIRED obligation is a plan defect unless it says it is verification-only."""

    OBS = {"AC-S-1": {"proof_mode": "PRESERVE_REQUIRED"}, "AC-S-2": {"proof_mode": "NEGATIVE_INVARIANT"}}

    def test_g_zero_change_required_is_refused_for_a_normal_story(self):
        ok, why = ob.story_contribution(self.OBS, list(self.OBS))
        self.assertFalse(ok)
        self.assertIn("VERIFICATION_ONLY", why)

    def test_g_a_verification_only_story_may_have_none(self):
        ok, _ = ob.story_contribution(self.OBS, list(self.OBS), story_type=ob.VERIFICATION_ONLY)
        self.assertTrue(ok)

    def test_one_change_required_is_enough(self):
        obs = {**self.OBS, "AC-S-3": {"proof_mode": "CHANGE_REQUIRED"}}
        ok, why = ob.story_contribution(obs, list(obs))
        self.assertTrue(ok, why)

    def test_a_criterion_without_an_obligation_refuses_before_any_model_call(self):
        ok, why = ob.story_contribution({"AC-S-1": {"proof_mode": "CHANGE_REQUIRED"}}, ["AC-S-1", "AC-S-2"])
        self.assertFalse(ok)
        self.assertIn("AC-S-2", why)


class TestMixedStory(unittest.TestCase):
    """H. six criteria, three obligations — each judged by its own, in one pass."""

    def test_h_every_criterion_is_judged_by_its_own_obligation(self):
        obligations = {
            "AC-S-1": {"proof_mode": "CHANGE_REQUIRED", "requirement": "FR-1"},
            "AC-S-2": {"proof_mode": "CHANGE_REQUIRED", "requirement": "FR-1"},
            "AC-S-3": {"proof_mode": "CHANGE_REQUIRED", "requirement": "FR-2"},
            "AC-S-4": {"proof_mode": "PRESERVE_REQUIRED", "requirement": "FR-3"},
            "AC-S-5": {"proof_mode": "PRESERVE_REQUIRED", "requirement": "FR-4"},
            "AC-S-6": {"proof_mode": "NEGATIVE_INVARIANT", "requirement": "NFR-1"},
        }
        parent = {"AC-S-1": RED, "AC-S-2": RED, "AC-S-3": GREEN, "AC-S-4": GREEN, "AC-S-5": GREEN, "AC-S-6": GREEN}
        candidate = {"AC-S-1": GREEN, "AC-S-2": RED, "AC-S-3": GREEN, "AC-S-4": GREEN, "AC-S-5": RED, "AC-S-6": GREEN}
        rows = ob.judge(obligations, parent, candidate, list(obligations))
        self.assertEqual([r["outcome"] for r in rows],
                         [ob.Outcome.SATISFIED.value, ob.Outcome.DEVELOPER_QUALITY_BLOCK.value,
                          ob.Outcome.PLAN_OVERLAP.value, ob.Outcome.SATISFIED.value,
                          ob.Outcome.DEVELOPER_REGRESSION.value, ob.Outcome.SATISFIED.value])
        self.assertEqual(ob.owners(ob.blocking(rows)), {"DEVELOPER", "PLAN"})

    def test_every_row_carries_the_structure_the_owner_asked_for(self):
        rows = ob.judge({"AC-S-1": {"proof_mode": "CHANGE_REQUIRED", "requirement": "FR-12"}},
                        {"AC-S-1": GREEN}, {"AC-S-1": GREEN}, ["AC-S-1"])
        self.assertEqual(rows[0] | {"why": ""},
                         {"ac_id": "AC-S-1", "requirement": "FR-12", "proof_mode": "CHANGE_REQUIRED",
                          "parent": "GREEN", "candidate": "GREEN", "expected_transition": "RED -> GREEN",
                          "actual_transition": "GREEN -> GREEN", "outcome": "PLAN_OVERLAP", "owner": "PLAN",
                          "parent_states": ["GREEN_EXECUTED"], "candidate_states": ["GREEN_EXECUTED"],
                          "tests": ["t"], "why": ""})


class TestPlanningDataParsing(unittest.TestCase):
    """The obligation is planning data read once, at plan time — the shape the machine gate then validates."""

    EPICS = """## Epic 1: Ledger
### Story 1.1: Skeleton
#### Acceptance Criteria
- **Given** a, **When** b, **Then** c
- **Given** d, **When** e, **Then** f

- covers: FR-1
- ac_proof: 1=CHANGE_REQUIRED/FR-1, 2=NEGATIVE_INVARIANT/NFR-2
- write_scope: src/a.py
"""

    def test_each_criterion_carries_its_obligation_and_requirement(self):
        story = parse_epics(self.EPICS).stories()[0]
        self.assertEqual(story.ac_proof["AC-STORY-01-01-1"]["proof_mode"], "CHANGE_REQUIRED")
        self.assertEqual(story.ac_proof["AC-STORY-01-01-2"]["requirement"], "NFR-2")
        self.assertEqual(story.story_type, "NORMAL")
        self.assertEqual([r["ac_id"] for r in story.as_dict()["ac_proof"]],
                         ["AC-STORY-01-01-1", "AC-STORY-01-01-2"])

    def test_an_unparsable_entry_is_kept_verbatim_so_the_gate_can_name_it(self):
        out = ac_proof(["1=CHANGE_REQUIRED/FR-1", "nonsense"], "STORY-01-01", 2)
        self.assertEqual(len(out), 2)
        self.assertIn("nonsense", [v["raw"] for v in out.values()])
        self.assertIn(None, [v["proof_mode"] for v in out.values()])

    def test_a_story_without_the_declaration_carries_no_obligation_at_all(self):
        story = parse_epics(self.EPICS.replace("- ac_proof: 1=CHANGE_REQUIRED/FR-1, 2=NEGATIVE_INVARIANT/NFR-2\n", "")).stories()[0]
        self.assertEqual(story.ac_proof, {}, "absence must be visible to the gate, never defaulted to a mode")


if __name__ == "__main__":
    unittest.main()
