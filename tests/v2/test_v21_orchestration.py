"""V2.1 orchestration cases.

* (A) A git failure while the story runner reads the candidate's diff is the environment's —
  RESOURCE_ACQUISITION_FAILED, ENVIRONMENT, retryable through the taxonomy — never an InvariantError that ends the run as
  a kernel defect (2.0.0: `GitWorkspace.diff` raised InvariantError; 360° reliability). Nothing is merged.
* (B, V21-38) A committed story's PRESERVE obligation that the developer's candidate breaks is found AT THE CANDIDATE:
  CONTRACT_UNSATISFIED, owner DEVELOPER, retryable, the criterion in the journal's failure (what the developer's retry
  prompt is built from, app/feedback.retry_feedback) — never merged. On 2.0.0 it was found only after the merge,
  POST_MERGE_REGRESSION / INTEGRATION, not retryable, nothing fed back (release smoke #2, journal seq 387-393)."""

from __future__ import annotations

import unittest

import tests.v2.test_p6_orchestration as orch
from aisef2.arch.enums import ObligationRole
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


class PreserveAtCandidate(orch.Orchestration):
    BROKEN_SUB = "def sub(a, b):\n    return a + b\n"

    def plan(self):
        return orch.plan_of(self.base, orch.obligation("C1", self.s1.id, "S0", ObligationRole.INTRODUCE),
                            orch.obligation("C0", self.s0.id, "S0", ObligationRole.PRESERVE),
                            orch.obligation("C2", self.s2.id, "S2", ObligationRole.INTRODUCE))

    def s2_inputs(self):
        return self.inputs("S2", tests=("tests/test_s2.py",), regressions=("tests/test_other.py",))

    def test_a_regression_the_developer_made_is_the_developer_s_and_never_merged(self):
        plan = self.plan()
        self.assertTrue(self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0")).committed)
        tip = self.merger.base()
        breaking = orch.Dev({"app/mul.py": orch.MUL, "tests/test_s2.py": orch.TEST_MUL, "app/calc.py": self.BROKEN_SUB})
        r = self.story(plan, "S2", breaking, inputs=self.s2_inputs(), tests_block=False)
        self.assertEqual(self.failures("S2"), [("CONTRACT_UNSATISFIED", "DEVELOPER", True)] * 2)
        self.assertEqual(self.details("S2"), ["proof of C0: CONTRACT_UNSATISFIED"] * 2)   # the criterion, for the retry prompt
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "ROLLBACK"])
        self.assertEqual(self.merger.base(), tip)                                     # nothing was merged
        self.assertEqual([e.data["check"] for e in self.events("gate/check") if ":post-merge:" in e.data["check"]
                          and e.data["check"].startswith("S2")], [])
        at = [e.data["candidate"] for e in self.events("proof/verified", "S2") if e.data["criterion_id"] == "C0"]
        self.assertEqual(at, breaking.candidates)                                   # proved on each candidate itself
        self.assert_disposed("S2")

    def test_a_retry_that_repairs_it_commits(self):
        plan = self.plan()
        self.assertTrue(self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0")).committed)
        good = {"app/mul.py": orch.MUL, "tests/test_s2.py": orch.TEST_MUL}

        class LearnsOnce(orch.Dev):
            def implement(self, story_id, criteria, checkout):
                self.files = dict(good, **({"app/calc.py": PreserveAtCandidate.BROKEN_SUB} if not self.calls else {}))
                return super().implement(story_id, criteria, checkout)
        r = self.story(plan, "S2", LearnsOnce(), inputs=self.s2_inputs(), tests_block=False)
        self.assertEqual([a.outcome for a in r.attempts], ["RETRY", "COMMIT"])
        self.assertTrue(r.committed)
        self.assertEqual([(e.data["check"], e.data["passed"]) for e in self.events("gate/check")
                          if e.data["check"] in ("S2:proof:C0", "S2:post-merge:C0")],
                         [("S2:proof:C0", False), ("S2:proof:C0", True), ("S2:post-merge:C0", True)])

    def test_a_story_with_no_committed_predecessor_proves_only_its_own(self):
        plan = self.plan()
        self.story(plan, "S0", self.s1_dev(), inputs=self.inputs("S0"))
        self.assertEqual(sorted(e.data["check"] for e in self.events("gate/check") if e.data["check"].startswith("S0:proof:")),
                         ["S0:proof:C0", "S0:proof:C1"])


def load_tests(loader, tests, pattern):     # only this module's cases, not the inherited Orchestration suite
    names = [f"{__name__}.DiffFailure.{n}" for n in ("test_a_diff_git_cannot_produce_is_RESOURCE_ACQUISITION_FAILED",
                                                      "test_a_retry_budget_takes_the_story_to_its_next_attempt")]
    names += [f"{__name__}.PreserveAtCandidate.{n}" for n in ("test_a_regression_the_developer_made_is_the_developer_s_and_never_merged",
                                                              "test_a_retry_that_repairs_it_commits",
                                                              "test_a_story_with_no_committed_predecessor_proves_only_its_own")]
    return unittest.TestSuite(loader.loadTestsFromNames(names))


if __name__ == "__main__":
    unittest.main()
