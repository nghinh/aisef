"""Pure qualification policy — one rule for run/repair/pre-deploy.

Three callers, six answer shapes, one shared question: given what is on
disk, what should the harness do next? These tests pin every branch and
every input shape.  Backward compatibility: the module exposes additive
types only; old persistence is unchanged.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.qualification import (  # noqa: E402
    ApprovalSnapshot,
    BehaviorGap,
    Decision,
    Inputs,
    MergeAttempt,
    PHASE_PRE_DEPLOY,
    PHASE_REPAIR,
    PHASE_RUN,
    Profile,
    QaSnapshot,
    StorySnapshot,
    Verdict,
    qualify,
)


class TestPure(unittest.TestCase):
    """The whole module is a pure function. Same inputs → same Verdict."""

    def test_run_phase_default_profile_with_clean_inputs_stops(self):
        v = qualify(Profile(phase=PHASE_RUN), Inputs())
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("all stories done", v.reason)

    def test_repair_phase_default_profile_stops_with_no_gaps(self):
        v = qualify(Profile(phase=PHASE_REPAIR), Inputs())
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("no GAP/REOPENED", v.reason)

    def test_pre_deploy_default_profile_stops(self):
        v = qualify(Profile(phase=PHASE_PRE_DEPLOY), Inputs())
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("deploy gate met", v.reason)


class TestRunPhase(unittest.TestCase):
    def _profile(self, **kw) -> Profile:
        return Profile(phase=PHASE_RUN, attempt=1, max_retries=2, **kw)

    def test_infra_failure_becomes_retry_when_run_phase(self):
        v = qualify(self._profile(), Inputs(infra_failure="connection refused"))
        self.assertEqual(v.decision, Decision.RETRY_INFRA)
        self.assertIn("connection refused", v.reason)
        self.assertIn("infra_failure", v.used_inputs)

    def test_infra_failure_in_repair_phase_becomes_stop(self):
        """Repair loops have no ``retry`` path — the QA suite already ran."""
        v = qualify(Profile(phase=PHASE_REPAIR), Inputs(infra_failure="x"))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("infra:", v.reason)

    def test_plan_error_stops_immediately(self):
        v = qualify(self._profile(), Inputs(plan_error="missing index"))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("missing index", v.reason)
        self.assertIn("plan_error", v.used_inputs)

    def test_missing_artifact_root_stops(self):
        v = qualify(self._profile(), Inputs(artifact_root_exists=False))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("artifact_root", v.reason)

    def test_run_ownership_handed_to_human(self):
        v = qualify(self._profile(), Inputs(run_ownership_ok=False))
        self.assertEqual(v.decision, Decision.HUMAN)
        self.assertIn("another run", v.reason)

    def test_epic_not_in_plan_stops(self):
        v = qualify(self._profile(), Inputs(epic_not_in_plan=True))
        self.assertEqual(v.decision, Decision.STOP)

    def test_blocked_story_stops(self):
        v = qualify(self._profile(),
                    Inputs(stories=(StorySnapshot("S1", "blocked"),)))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("blocked", v.reason)

    def test_failed_beyond_max_retries_stops(self):
        v = qualify(Profile(phase=PHASE_RUN, attempt=2, max_retries=1),
                    Inputs(stories=(StorySnapshot("S1", "failed"),)))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("max_retries", v.reason)

    def test_running_story_returns_verify(self):
        v = qualify(self._profile(),
                    Inputs(stories=(StorySnapshot("S1", "running"),)))
        self.assertEqual(v.decision, Decision.VERIFY)

    def test_verified_no_blockers_returns_merge(self):
        v = qualify(self._profile(), Inputs(stories=(
            StorySnapshot("S1", "verified", has_candidate=True,
                          verification_ok=True),)))
        self.assertEqual(v.decision, Decision.MERGE)
        self.assertIn("S1", v.reason)

    def test_verified_with_review_blocking_returns_verify(self):
        """A story that passed the gate but the reviewer flagged a blocker
        must run another attempt — ``verify`` (the harness reopens the
        attempt), not merge."""
        v = qualify(self._profile(), Inputs(stories=(
            StorySnapshot("S1", "verified", has_candidate=True,
                          verification_ok=True, review_blocking=2),)))
        self.assertEqual(v.decision, Decision.VERIFY)
        self.assertIn("blocking findings", v.reason)

    def test_merge_conflict_hands_to_human(self):
        v = qualify(self._profile(), Inputs(merges=(
            MergeAttempt("S1", merged=False, conflicts=("src/x.py",)),)))
        self.assertEqual(v.decision, Decision.HUMAN)
        self.assertIn("merge conflict", v.reason)
        self.assertIn("src/x.py", v.reason)
        self.assertIn("write_scope misdeclared", v.reason)


class TestRepairPhase(unittest.TestCase):
    def _profile(self, **kw) -> Profile:
        return Profile(phase=PHASE_REPAIR, **kw)

    def test_qa_candidate_mismatch_stops(self):
        v = qualify(self._profile(),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="bbb")))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("stale", v.reason)

    def test_qa_clean_tree_mismatch_stops(self):
        v = qualify(self._profile(),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa", clean_tree="bbb")))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("clean-tree", v.reason)

    def test_required_kind_unconfigured_stops(self):
        v = qualify(self._profile(required_kinds=("e2e",)),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa",
                                         unconfigured_kinds=("e2e",))))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("e2e", v.reason)

    def test_required_kind_waived_passes_through(self):
        v = qualify(self._profile(required_kinds=("e2e",)),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa",
                                         waived_kinds=("e2e",))))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertNotIn("e2e", v.reason)

    def test_required_kind_unrunnable_stops(self):
        v = qualify(self._profile(required_kinds=("mutation",)),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa",
                                         unrunnable_kinds=("mutation",))))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("mutation", v.reason)

    def test_plan_stuck_hands_to_human(self):
        v = qualify(self._profile(),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa"),
                           plan_stuck="scope mismatch"))
        self.assertEqual(v.decision, Decision.HUMAN)
        self.assertIn("plan stuck", v.reason)

    def test_max_loops_stops(self):
        v = qualify(self._profile(max_loops=3, loops_completed=3),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa")))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("max_loops", v.reason)

    def test_cost_cap_stops(self):
        v = qualify(self._profile(cost_cap_usd=5.0, cost_spent_usd=6.0),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa")))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("cost_cap", v.reason)

    def test_eligible_gap_returns_repair(self):
        v = qualify(self._profile(), Inputs(candidate="aaa",
                                            qa=QaSnapshot(candidate="aaa"),
                                            behaviors=(
                                                BehaviorGap("AC-1", "gap",
                                                            has_verifier=True),)))
        self.assertEqual(v.decision, Decision.REPAIR)
        self.assertIn("AC-1", v.reason)

    def test_outside_queue_hands_to_human(self):
        v = qualify(self._profile(), Inputs(candidate="aaa",
                                            qa=QaSnapshot(candidate="aaa"),
                                            behaviors=(
                                                BehaviorGap("qa:e2e", "gap",
                                                            has_verifier=False),)))
        self.assertEqual(v.decision, Decision.HUMAN)
        self.assertIn("project-level", v.reason)

    def test_no_gaps_returns_stop(self):
        v = qualify(self._profile(), Inputs(candidate="aaa",
                                            qa=QaSnapshot(candidate="aaa")))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("no GAP/REOPENED", v.reason)

    def test_round_two_needs_approval_unless_auto(self):
        v = qualify(self._profile(loops_completed=1, auto=False),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa"),
                           approvals=(
                               ApprovalSnapshot("improve", "pending"),)))
        self.assertEqual(v.decision, Decision.HUMAN)
        self.assertIn("improve", v.reason)

    def test_round_two_with_auto_skips_approval(self):
        v = qualify(self._profile(loops_completed=1, auto=True),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa"),
                           approvals=(
                               ApprovalSnapshot("improve", "pending"),)))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertNotIn("improve", v.reason)


class TestPreDeployPhase(unittest.TestCase):
    def _profile(self, **kw) -> Profile:
        return Profile(phase=PHASE_PRE_DEPLOY, **kw)

    def test_not_done_story_stops(self):
        v = qualify(self._profile(),
                    Inputs(stories=(StorySnapshot("S1", "failed"),)))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("not done", v.reason)
        self.assertIn("S1", v.reason)

    def test_pending_approval_hands_to_human(self):
        v = qualify(self._profile(),
                    Inputs(stories=(StorySnapshot("S1", "done"),),
                           approvals=(ApprovalSnapshot("prd", "pending"),)))
        self.assertEqual(v.decision, Decision.HUMAN)
        self.assertIn("prd", v.reason)

    def test_approved_release_ready_stops_clean(self):
        v = qualify(self._profile(),
                    Inputs(stories=(StorySnapshot("S1", "done"),),
                           approvals=(ApprovalSnapshot("prd", "approved"),),
                           qa=QaSnapshot(release_ready=True)))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("deploy gate met", v.reason)

    def test_not_release_ready_stops(self):
        v = qualify(self._profile(),
                    Inputs(stories=(StorySnapshot("S1", "done"),),
                           approvals=(ApprovalSnapshot("prd", "approved"),),
                           qa=QaSnapshot(release_ready=False)))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("release-ready", v.reason)

    def test_required_kind_failed_stops(self):
        v = qualify(self._profile(required_kinds=("e2e",)),
                    Inputs(stories=(StorySnapshot("S1", "done"),),
                           approvals=(ApprovalSnapshot("prd", "approved"),),
                           qa=QaSnapshot(release_ready=True,
                                         failed_kinds=("e2e",))))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("e2e", v.reason)


class TestBranches(unittest.TestCase):
    """Branches that do not depend on phase."""

    def test_infra_failure_in_pre_deploy_stops(self):
        v = qualify(Profile(phase=PHASE_PRE_DEPLOY),
                    Inputs(infra_failure="daemon down"))
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("infra:", v.reason)

    def test_is_terminal_only_for_stop_and_human(self):
        self.assertTrue(Verdict(Decision.STOP).is_terminal)
        self.assertTrue(Verdict(Decision.HUMAN).is_terminal)
        self.assertFalse(Verdict(Decision.RETRY_INFRA).is_terminal)
        self.assertFalse(Verdict(Decision.REPAIR).is_terminal)
        self.assertFalse(Verdict(Decision.VERIFY).is_terminal)
        self.assertFalse(Verdict(Decision.MERGE).is_terminal)

    def test_used_inputs_records_every_branch_consulted(self):
        v = qualify(Profile(phase=PHASE_REPAIR, max_loops=3, loops_completed=5),
                    Inputs(candidate="aaa",
                           qa=QaSnapshot(candidate="aaa")))
        self.assertIn("max_loops", v.used_inputs)

    def test_reasoning_lists_branch_traces(self):
        v = qualify(Profile(phase=PHASE_RUN),
                    Inputs(stories=(StorySnapshot("S1", "running"),)))
        self.assertTrue(any("S1" in t for t in v.reasoning))


class TestDecisionShape(unittest.TestCase):
    def test_decision_enum_is_closed(self):
        self.assertEqual(
            {d.value for d in Decision},
            {"retry_infra", "repair", "verify", "merge", "stop", "human"},
        )


if __name__ == "__main__":
    unittest.main()