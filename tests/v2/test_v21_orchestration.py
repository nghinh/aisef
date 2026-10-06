"""V2.1 (A): a git failure while the story runner reads the candidate's diff is the environment's —
RESOURCE_ACQUISITION_FAILED, ENVIRONMENT, retryable through the taxonomy — never an InvariantError that ends the run as
a kernel defect (2.0.0: `GitWorkspace.diff` raised InvariantError; 360° reliability). The story's checkouts are
released and nothing is merged."""

from __future__ import annotations

import unittest

import tests.v2.test_p6_orchestration as orch
from aisef2.control.owner import Owner
from aisef2.orchestrate.adapters import ResourceUnavailable
from aisef2.orchestrate.workspace import GitWorkspace


class DiffFailure(orch.Orchestration):
    def test_a_diff_git_cannot_produce_is_RESOURCE_ACQUISITION_FAILED(self):
        class NoDiff(GitWorkspace):
            def diff(self, base, candidate):
                raise ResourceUnavailable(f"git diff {base[:12]}..{candidate[:12]} exited 128")
        dev = self.s1_dev()
        r = self.story(self.s1_plan(), "S1", dev, workspace=NoDiff(self.repo, self.tmp / "ws"),
                       limits={**orch.LIMITS, Owner.ENVIRONMENT: 0})
        self.assertEqual(self.failures("S1"), [("RESOURCE_ACQUISITION_FAILED", "ENVIRONMENT", True)])
        detail = f"candidate diff: git diff {self.base[:12]}..{dev.candidates[0][:12]} exited 128"
        self.assertEqual(self.details("S1"), [detail])
        self.assertEqual(self.rows("S1")[-1], ("S1:candidate", False, detail))
        self.assertEqual([a.outcome for a in r.attempts], ["ROLLBACK"])
        self.assertEqual(self.merger.base(), self.base)
        self.assert_disposed("S1")

    def test_a_retry_budget_takes_the_story_to_its_next_attempt(self):
        calls = []

        class OnceNoDiff(GitWorkspace):
            def diff(self, base, candidate):
                calls.append(candidate)
                if len(calls) == 1:
                    raise ResourceUnavailable("git diff exited 128")
                return super().diff(base, candidate)
        r = self.story(self.s1_plan(), "S1", self.s1_dev(), workspace=OnceNoDiff(self.repo, self.tmp / "ws"))
        self.assertEqual([a.outcome for a in r.attempts][:1], ["RETRY"])
        self.assertEqual(len(calls), 2)


def load_tests(loader, tests, pattern):     # only this module's cases, not the inherited Orchestration suite
    return unittest.TestSuite(loader.loadTestsFromNames(
        [f"{__name__}.DiffFailure.{n}" for n in ("test_a_diff_git_cannot_produce_is_RESOURCE_ACQUISITION_FAILED",
                                                  "test_a_retry_budget_takes_the_story_to_its_next_attempt")]))


if __name__ == "__main__":
    unittest.main()
