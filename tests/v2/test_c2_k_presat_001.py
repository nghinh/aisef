"""K-PRESAT-001 (owner ruling 'AISEF V2 — BOUNDED CORRECTIVE PATCH' §3; RFC §14): a story whose every obligation is
PRE_SATISFIED makes no developer call, so engineering-test adequacy is not run and can neither fail the story nor
charge the developer — whatever the tests policy. The measured defect (QP-2.9 attempt 2, STORY-02-01 and STORY-02-02):
such a story under a blocking policy was TESTS_INADEQUATE, owner DEVELOPER, one DEVELOPER retry charged, rolled back.

The cases through the one real path (the Cycle-1 fixture of test_p6_orchestration, nothing mocked):

  A  all PRE_SATISFIED + blocking policy + the story's test file missing      -> already satisfied
  B  all PRE_SATISFIED + blocking policy + an ordinary passing test file      -> the same result as A
  C  some PRE_SATISFIED + some READY                                          -> the developer path and adequacy as before
  D  the developer was called + EXECUTED failing / vacuous tests + blocking   -> the policy still blocks

'Already satisfied' is not a journal value (the journal schema is unchanged): it is a COMMIT whose revision is the
parent, of a story admitted with every obligation PRE_SATISFIED and no developer call permitted.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole, Owner  # noqa: E402
from tests.v2 import test_p6_orchestration as e2e  # noqa: E402

P = e2e.P

VACUOUS = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_nothing(self):\n        self.assertTrue(True)\n"


class Fixture(unittest.TestCase):
    """The Cycle-1 orchestration fixture, borrowed without its test cases."""
    setUp = e2e.Orchestration.setUp
    story, inputs, adapters = e2e.Orchestration.story, e2e.Orchestration.inputs, e2e.Orchestration.adapters
    events, types, rows = e2e.Orchestration.events, e2e.Orchestration.types, e2e.Orchestration.rows
    failures, details, proofs = e2e.Orchestration.failures, e2e.Orchestration.details, e2e.Orchestration.proofs
    assertAttempts, assertCommitted = e2e.Orchestration.assertAttempts, e2e.Orchestration.assertCommitted

    def introduce(self, *pairs):
        """A plan at main's tip: each (criterion, spec) an INTRODUCE obligation of S1."""
        return e2e.plan_of(self.merger.base(), *(e2e.obligation(c, s.id, "S1", ObligationRole.INTRODUCE) for c, s in pairs))

    def requests(self, owner: Owner) -> list:
        return [e for e in self.events("provider/request", "S1") if e.data["budget_owner"] == owner.value]

    def assertAlreadySatisfied(self, r, parent: str, criteria: tuple[str, ...]) -> None:
        """Everything §14 names for a story that ends already satisfied."""
        self.assertCommitted(r)
        self.assertAttempts(r, ["COMMIT"])                                        # no retry, no rollback
        self.assertEqual((r.revision, self.merger.base()), (parent, parent))      # candidate == parent: nothing landed
        admitted = self.events("story/admitted", "S1")
        self.assertEqual(len(admitted), 1)
        self.assertEqual((admitted[0].data["dispositions"], admitted[0].data["developer_call_permitted"]),
                         ({c: "PRE_SATISFIED" for c in criteria}, False))
        self.assertEqual(self.requests(Owner.DEVELOPER), [])                      # the developer call is skipped
        b = self.run.state(P.BUDGETS)
        self.assertEqual((b["developer"], b["retries"]), ({}, {}))               # no developer budget, no retry charged
        self.assertEqual(self.failures("S1"), [])                                 # no failure at all: none DEVELOPER-owned
        self.assertEqual(self.events("story/retry", "S1"), [])
        self.assertEqual(self.events("story/rollback", "S1"), [])
        self.assertEqual(self.events("tests/adequacy", "S1"), [])                 # engineering adequacy NOT RUN
        self.assertEqual([x for x in self.rows("S1") if x[0] == "S1:quality"], [])
        drift = self.events("story/plan-drift", "S1")
        self.assertEqual([(e.data["criterion_id"], e.data["attributed_to"]) for e in drift], [(c, "UNATTRIBUTED") for c in criteria])
        # independent verification: each obligation proved at the candidate by two records (implementer, verifier), and
        # again after the merge step — on top of the one parent measurement admission made
        proofs = self.events("proof/verified", "S1")
        self.assertEqual([(e.data["criterion_id"], e.data["agreement"], e.data["verdict"], e.data["candidate"]) for e in proofs],
                         [(c, True, "SATISFIED", parent) for c in criteria] * 2)
        records = self.events("probe/evaluated", "S1")
        self.assertEqual(len(records), 5 * len(criteria))                         # parent; candidate x2; post-merge x2
        for e in proofs:
            cited = [self.run.events[s] for s in e.source_seqs]
            self.assertEqual([c.type for c in cited], ["probe/evaluated"] * 2)
            self.assertEqual({c.data["record"]["revision"] for c in cited}, {parent})

    def summary(self) -> dict:
        """What the two fully pre-satisfied cases must have in common."""
        return {"types": self.types("S1"), "rows": [(c, ok) for c, ok, _ in self.rows("S1")],
                "budgets": {k: self.run.state(P.BUDGETS)[k] for k in ("developer", "review", "retries")},
                "state": dict(self.run.state(P.STORY_STATE)["S1"])}


class FullyPreSatisfied(Fixture):
    def already_satisfied(self, files: dict) -> dict:
        parent = e2e.land(self.repo, files, "add landed earlier")
        dev = e2e.Dev(outage=True)                                                 # a developer call would raise
        r = self.story(self.introduce(("C1", self.s1)), "S1", dev, tests_block=True)
        self.assertAlreadySatisfied(r, parent, ("C1",))
        self.assertEqual(dev.calls, [])
        return self.summary()

    def test_A_blocking_policy_and_a_missing_story_test_file_is_already_satisfied(self):
        s = self.already_satisfied({"app/calc.py": e2e.CALC + e2e.ADD})           # no tests/test_s1.py anywhere
        self.assertFalse((pathlib.Path(self.repo) / "tests" / "test_s1.py").exists())
        self.assertEqual(s["state"]["outcome"], "COMMIT")

    def test_A_the_only_provider_request_is_the_review_of_the_unchanged_candidate(self):
        """Stated, not hidden: the reviewer and the scanner still see the candidate, as Cycle-1's ORCH-4 has it — one
        REVIEW request, no DEVELOPER one. Skipping review as well would be a second semantic change (owner's to rule)."""
        self.already_satisfied({"app/calc.py": e2e.CALC + e2e.ADD})
        self.assertEqual([e.data["budget_owner"] for e in self.events("provider/request", "S1")], ["REVIEW"])
        self.assertEqual(self.run.state(P.BUDGETS)["review"], {"S1": {"requests": 1, "criteria": {"C1": 1}}})

    def test_B_blocking_policy_and_an_ordinary_passing_test_file_gives_the_same_result_as_A(self):
        a = self.already_satisfied({"app/calc.py": e2e.CALC + e2e.ADD})
        other = FullyPreSatisfied("already_satisfied")
        other.setUp()
        try:
            b = other.already_satisfied({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD})
        finally:
            other.doCleanups()
        self.assertEqual(a, b)

    def test_the_stance_does_not_matter_non_blocking_gives_the_same_journal_shape(self):
        a = self.already_satisfied({"app/calc.py": e2e.CALC + e2e.ADD})
        other = FullyPreSatisfied("already_satisfied")
        other.setUp()
        try:
            parent = e2e.land(other.repo, {"app/calc.py": e2e.CALC + e2e.ADD}, "add landed earlier")
            r = other.story(other.introduce(("C1", other.s1)), "S1", e2e.Dev(outage=True), tests_block=False)
            other.assertAlreadySatisfied(r, parent, ("C1",))
            b = other.summary()
        finally:
            other.doCleanups()
        self.assertEqual(a, b)


class PartlyPreSatisfied(Fixture):
    def partly(self, files: dict, **kw):
        e2e.land(self.repo, {"app/calc.py": e2e.CALC + e2e.ADD}, "add landed earlier")
        dev = e2e.Dev(files)
        r = self.story(self.introduce(("C1", self.s1), ("C2", self.s2)), "S1", dev, tests_block=True, **kw)
        admitted = self.events("story/admitted", "S1")[0].data
        self.assertEqual((admitted["dispositions"], admitted["developer_call_permitted"]),
                         ({"C1": "PRE_SATISFIED", "C2": "READY"}, True))
        return r, dev

    def test_C_the_developer_gets_the_READY_work_and_adequacy_is_assessed_as_before(self):
        r, dev = self.partly({"app/mul.py": e2e.MUL, "tests/test_s1.py": e2e.TEST_MUL})
        self.assertCommitted(r)
        self.assertEqual([c[1] for c in dev.calls], [("C2",)])                    # never the PRE_SATISFIED criterion
        self.assertEqual([list(e.data["criteria"]) for e in self.requests(Owner.DEVELOPER)], [["C2"]])
        self.assertEqual(self.run.state(P.BUDGETS)["developer"], {"S1": {"requests": 1, "criteria": {"C2": 1}}})
        adequacy = self.events("tests/adequacy", "S1")
        self.assertEqual(len(adequacy), 1)                                        # engineering adequacy RAN
        self.assertEqual((adequacy[0].data["execution"]["status"], adequacy[0].data["execution"]["selection"]),
                         ("EXECUTED", "STORY_TESTS_RAN"))
        self.assertIn(("S1:quality", True), [(c, ok) for c, ok, _ in self.rows("S1")])
        self.assertEqual([e.data["criterion_id"] for e in self.events("story/plan-drift", "S1")], ["C1"])
        self.assertEqual({e.data["criterion_id"] for e in self.events("proof/verified", "S1")}, {"C1", "C2"})

    def test_C_a_blocking_policy_still_blocks_the_partly_pre_satisfied_story_on_failing_tests(self):
        failing = e2e.TEST_MUL.replace(", 6)", ", 7)")
        r, _ = self.partly({"app/mul.py": e2e.MUL, "tests/test_s1.py": failing}, limits={**e2e.LIMITS, Owner.DEVELOPER: 0})
        self.assertAttempts(r, ["ROLLBACK"])
        self.assertEqual(self.failures("S1"), [("TESTS_INADEQUATE", "DEVELOPER", True)])
        self.assertEqual(self.events("tests/adequacy", "S1")[0].data["outcome"], "INADEQUATE")


class DeveloperWasCalled(Fixture):
    def blocked(self, tests: str, *, vacuity: str):
        dev = e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": tests})
        r = self.story(self.introduce(("C1", self.s1)), "S1", dev, tests_block=True)
        self.assertEqual(len(dev.calls), 2)                                       # called, then called again on the retry
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])
        self.assertEqual(self.failures("S1"), [("TESTS_INADEQUATE", "DEVELOPER", True)] * 2)
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {"S1": {"DEVELOPER": 1}})
        adequacy = [e.data for e in self.events("tests/adequacy", "S1")]
        self.assertEqual([(a["execution"]["status"], a["outcome"], a["owner"], a["vacuity"]) for a in adequacy],
                         [("EXECUTED", "INADEQUATE", "DEVELOPER", vacuity)] * 2)
        self.assertEqual(self.merger.base(), self.base)                           # nothing landed

    def test_D_executed_failing_tests_are_still_blocked_under_a_blocking_policy(self):
        dev = e2e.Dev({"app/calc.py": e2e.CALC + e2e.ADD, "tests/test_s1.py": e2e.TEST_ADD_WRONG})
        r = self.story(self.introduce(("C1", self.s1)), "S1", dev, tests_block=True)
        self.assertAttempts(r, ["RETRY", "ROLLBACK"])
        self.assertEqual(self.failures("S1"), [("TESTS_INADEQUATE", "DEVELOPER", True)] * 2)
        self.assertEqual([e.data["execution"]["outcome"] for e in self.events("tests/adequacy", "S1")], ["FAILED"] * 2)
        self.assertEqual(self.run.state(P.BUDGETS)["retries"], {"S1": {"DEVELOPER": 1}})

    def test_D_executed_vacuous_tests_are_still_blocked_under_a_blocking_policy(self):
        self.blocked(VACUOUS, vacuity="VACUOUS")


if __name__ == "__main__":
    unittest.main()
