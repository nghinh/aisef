"""SS-96 — evidence that did not execute is never a failure against the developer (INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE).

`tests verify story` correctly reported UNRUNNABLE when the parent's evidence could not run, while `TDD`, reading
the SAME evidence, reported FAILED ("tests green on first run"). `_absent_stages` stops at any FAILED check, so the
environment was routed to the developer: a story whose candidate was correct spent its whole quality budget and
ended as QUALITY_BLOCK. lint, review and security were already routed correctly — which is what made the single
converting check visible.

The cases below are the owner's regression list (decision 2026-09-20, section 7, A-I), each driven through the REAL
kernel on a real git project with a real test runner.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.control.outcome import StageOutcome  # noqa: E402
from tests.hardening import policy_v2 as P  # noqa: E402

ENV = StageOutcome.ENVIRONMENT_FAILURE.value
UNRUNNABLE = StageOutcome.UNRUNNABLE.value
QUALITY = StageOutcome.QUALITY_BLOCK.value
PLAN = StageOutcome.PLAN_CONFLICT.value


def run(**kw) -> dict:
    """One real story. `crits` defaults to the single CHANGE_REQUIRED criterion the story owes."""
    crits = kw.pop("crits", None) or [P._crit("new", "CHANGE_REQUIRED")]
    return P.real_run(P.Case(kw.pop("id", "R"), kw.pop("title", ""), crits, **kw))


class TestAbsenceIsNeverADeveloperFailure(unittest.TestCase):
    """A, B, C, D: whatever stage could not produce evidence, the developer's quality budget is untouched."""

    def assert_environment(self, r: dict, *, terminal: str = ENV) -> None:
        self.assertEqual(r["checks_failed"], [], f"an absence was reported as FAILED: {r['checks_failed']}")
        self.assertEqual(r["quality_attempts"], 1, "the session that revealed the absence is the only one charged")
        self.assertEqual(r["developer_sessions"], 1, "no second developer session may be opened for an absence")
        self.assertEqual(r["terminal"], terminal)

    def test_A_the_parent_evidence_cannot_run(self):
        self.assert_environment(run(crits=[P._crit("parent_unrunnable", "CHANGE_REQUIRED")]))

    def test_B_repeated_absence_ends_on_the_environment_and_never_as_a_quality_block(self):
        r = run(crits=[P._crit("parent_unrunnable", "CHANGE_REQUIRED")], retries=3)
        self.assert_environment(r)
        self.assertNotEqual(r["terminal"], QUALITY, "more retries must not convert an absence into a quality block")

    def test_C_the_test_tool_itself_cannot_run(self):
        self.assert_environment(run(test_tool=P.MISSING_TOOL))

    def test_D_lint_cannot_run(self):
        self.assert_environment(run(lint_tool=P.MISSING_TOOL))

    def test_D_sast_cannot_run(self):
        r = run(sast_tool=P.MISSING_TOOL, contract=("security",))
        self.assertEqual(r["checks_failed"], [], f"an absence was reported as FAILED: {r['checks_failed']}")
        self.assertEqual(r["developer_sessions"], 1, "no second developer session may be opened for an absence")


class TestTheStageThatCouldNotRunIsTheStageRetried(unittest.TestCase):
    """E, F: a verifier that did not answer is re-executed; the developer is not."""

    def test_E_review_unrunnable_retries_the_review_stage_only(self):
        r = run(review_step="UNRUNNABLE")
        self.assertEqual(r["developer_sessions"], 1)
        self.assertGreater(r["review_executions"], 1, "the reviewer must be re-executed")
        self.assertEqual(r["terminal"], UNRUNNABLE)

    def test_F_security_unrunnable_retries_the_security_stage_only(self):
        r = run(security_step="UNRUNNABLE")
        self.assertEqual(r["developer_sessions"], 1)
        self.assertGreater(r["security_executions"], 1, "the security reviewer must be re-executed")
        self.assertEqual(r["terminal"], UNRUNNABLE)

    def test_an_absence_buys_a_re_verify_attempt_not_a_developer_session(self):
        r = run(crits=[P._crit("parent_unrunnable", "CHANGE_REQUIRED")])
        self.assertGreater(r["verify_only_attempts"], 0, "the responsible stage was never re-run")
        self.assertEqual(r["verify_only_attempts"] + 1, r["attempts"], "every extra attempt was a stage re-verify")


class TestAGenuineFailureStillChargesTheDeveloper(unittest.TestCase):
    """G, H, I: the fix must not make the gate toothless."""

    def test_G_a_candidate_that_does_not_implement_the_criterion_is_charged(self):
        r = run(crits=[P._crit("unimplemented", "CHANGE_REQUIRED")], unimplemented=True, retries=1)
        self.assertEqual(r["terminal"], QUALITY)
        self.assertEqual(r["quality_attempts"], 2, "one attempt plus one retry, both charged")
        self.assertEqual(r["developer_sessions"], 2)

    def test_H_a_plan_overlap_charges_no_developer_quality_attempt(self):
        r = run(crits=[P._crit("already", "CHANGE_REQUIRED")])
        self.assertEqual(r["terminal"], PLAN)
        self.assertEqual(r["quality_attempts"], 1)
        self.assertEqual(r["developer_sessions"], 1)

    def test_I_only_the_genuine_quality_failure_increments_the_quality_budget(self):
        """The tool is absent for a whole first attempt, recovers, and only then is the candidate seen to be wrong.

        The first attempt blocks on absence alone and buys a stage re-verify, not a developer session. When the
        tool comes back it shows a candidate that never implemented the criterion, and from there the developer is
        the right owner: the story ends as a quality block, charged for the two attempts that were graded.
        """
        r = run(crits=[P._crit("unimplemented", "CHANGE_REQUIRED")], unimplemented=True, retries=1,
                test_tool=P.FLAKY_TOOL)
        self.assertEqual(r["verify_only_attempts"], 1, "the environment failure must buy a stage re-verify")
        self.assertEqual(r["terminal"], QUALITY, "once the tool runs, the wrong candidate is the developer's")
        self.assertEqual(r["developer_sessions"], 2, "the absence alone opened no developer session")
        self.assertEqual(r["quality_attempts"], 2, "only the graded attempts are charged")


if __name__ == "__main__":
    unittest.main()
