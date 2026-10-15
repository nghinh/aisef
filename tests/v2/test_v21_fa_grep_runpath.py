"""V2.1 (owner decision 2026-10-15, PM-13) — a pattern that cannot finish, on the real run path.

The unit cases are in test_v21_fa_grep_worker.py. Here the real `run_story` runs (a real git repository and worktrees,
the real probes, journal format 3; typed doubles only for the developer, reviewer and scanner, as
test_p6_orchestration.py and test_v21_fa_parser_limits.py): a `grep_count` whose pattern cannot finish over a file
of the candidate's tree, or of the parent's, ends the story at its own gate instead of hanging the run, releases
everything the story held — the worker's process ranges included, which the probe hands to the story's scope — is
never charged to the developer, retries only as often as the ENVIRONMENT budget the run's settings give, and leaves the
next story and the run's closing as they were.
"""

from __future__ import annotations

import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    ControlProjection as P, Enforcement, ObligationRole, Owner, Polarity, SubjectAbsence, SubjectKind,
)
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv  # noqa: E402

#: every line of a file made of the letter a alone, and no ordinary line is: a prohibition over the package
PATTERN = r"^(a+)+$"
#: sixty letters and a mark: the pattern cannot finish on it in any time anyone waits
EVIL = "a" * 60 + "!\n"
DEADLINE_S = 2.0


def run_path_cases():
    from aisef2.app import run as app_run
    from aisef2.control.owner import FailureCode
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.workspace import commit_all
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    from tests.v2 import test_p6_orchestration as O

    probes = {**O.PROBE, fa.PROBE_ID: lambda on_range, scratch: fa.FileArtifactProbe(on_range=on_range, scratch=scratch)}
    env = ExecutionEnv(sys.executable, DEADLINE_S, Enforcement.PARTIAL)

    def contract():
        req = Requirement.create(id="R-GREP", text="no line of the package is made of the letter a alone", source="t")
        c = BehaviorContract.create(id="BC-GREP", requirement_ids=(req.id,),
                                    subject=Subject(SubjectKind.FILE_ARTIFACT, "path:app"), stimulus={"grep": PATTERN},
                                    observable={"matches": 0, "within_s": 30}, polarity=Polarity.MUST_HOLD,
                                    subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="no such line")
        approval = ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
        return compile_spec(c, requirements={req.id: req}, approvals=[approval],
                            probes={SubjectKind.FILE_ARTIFACT: ProbeRef(fa.PROBE_ID, fa.DIGEST)})

    class RunPath(O.Orchestration):
        def setUp(self):
            super().setUp()
            self.s_grep = contract()
            self.specs[self.s_grep.id] = self.s_grep

        def inputs(self, story, **kw):
            i = super().inputs(story, **kw)
            return sr.StoryInputs(i.specs, probes, env, i.story_tests, i.regression_tests, i.deps, i.runner)

        def plan(self, *more):
            return O.plan_of(self.base, O.obligation("C1", self.s1.id, "S1", ObligationRole.INTRODUCE),
                             O.obligation("GREP", self.s_grep.id, "S1", ObligationRole.VERIFY), *more)

        def dev_with_evil(self, **kw):
            return O.Dev({"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD, "app/evil.txt": EVIL}, **kw)

        # ---------------------------------------------------------------------------- the candidate holds the file
        def test_a_candidate_with_a_line_the_pattern_cannot_finish_ends_the_story_and_releases_what_it_held(self):
            began = time.monotonic()
            r = self.story(self.plan(), "S1", self.dev_with_evil())          # must return: the run is not hung
            self.assertLess(time.monotonic() - began, 120)
            self.assertFalse(r.committed)
            self.assertEqual(self.events("story/commit"), [])
            self.assertTrue(self.events("gate/decision"))
            self.assert_disposed("S1")      # acquired == released: the worker's ranges were the story's and are gone
            self.assertEqual({c for c, _, _ in self.failures("S1")}, {FailureCode.PROBE_UNRUNNABLE.value})
            self.assertEqual({o for _, o, _ in self.failures("S1")}, {Owner.ENVIRONMENT.value})
            for e in self.events("failure/observed", "S1"):
                self.assertNotEqual(e.data["code"], FailureCode.CONTRACT_UNSATISFIED.value)
            # the records the journal holds say what each observation of the prohibition was, in the probe's own words:
            # the parent, which has no such line, was counted (a verdict); the candidate was not looked at
            results = [e.data["record"]["result"] for e in self.events("probe/evaluated", "S1")
                       if e.data["criterion_id"] == "GREP"]
            counted = [r for r in results if "behavior_verdict" in r]
            stopped = [r for r in results if "behavior_verdict" not in r]
            self.assertEqual([r["behavior_verdict"] for r in counted], ["SATISFIED"] * len(counted))
            self.assertTrue(stopped)
            for result in stopped:
                self.assertIn("grep_count worker DEADLINE", result["detail"])
                self.assertIn("matching line 1 of 'app/evil.txt'", result["detail"])
            self.assertNotIn(Owner.DEVELOPER.value, [d for d in self.run.state(P.BUDGETS)["retries"].get("S1", {})])

        def test_the_retry_is_the_environment_budget_the_run_gives_and_no_more(self):
            for n, (environment, attempts) in enumerate(((0, 1), (1, 2))):
                with self.subTest(environment_retries=environment):
                    if n:
                        self.setUp()
                    limits = {**O.LIMITS, Owner.ENVIRONMENT: environment}
                    r = self.story(self.plan(), "S1", self.dev_with_evil(), limits=limits)
                    self.assertEqual(len(r.attempts), attempts)
                    self.assertEqual([a.outcome for a in r.attempts][-1], "ROLLBACK")
                    self.assertEqual({a.failure for a in r.attempts}, {FailureCode.PROBE_UNRUNNABLE})
                    self.assertEqual(self.run.state(P.BUDGETS)["retries"].get("S1", {}).get("ENVIRONMENT", 0), environment)

        # ----------------------------------------------------------------------------- the parent holds the file
        def test_a_parent_with_such_a_line_blocks_admission_before_any_developer_call(self):
            pathlib.Path(self.repo, "app", "evil.txt").write_text(EVIL, encoding="utf-8")
            self.base = commit_all(self.repo, "a generated file")
            dev = O.Dev({"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD})
            r = self.story(self.plan(), "S1", dev)
            self.assertFalse(r.committed)
            self.assertEqual(dev.calls, [])                            # no developer call before admission (§13)
            self.assertEqual(self.events("provider/request"), [])
            self.assertEqual({c for c, _, _ in self.failures("S1")}, {FailureCode.PROBE_UNRUNNABLE.value})
            self.assert_disposed("S1")

        # ----------------------------------------------------------------------------------------- the rest of the run
        def test_the_next_story_of_the_run_is_not_affected_and_the_run_closes_as_a_shutdown(self):
            plan = self.plan(O.obligation("C2", self.s2.id, "S2", ObligationRole.INTRODUCE))
            self.story(plan, "S1", self.dev_with_evil())
            r2 = self.story(plan, "S2", O.Dev({"app/mul.py": O.MUL, "tests/test_s2.py": O.TEST_MUL}),
                            inputs=self.inputs("S2", tests=("tests/test_s2.py",)))
            self.assertTrue(r2.committed)
            self.assertEqual(app_run._close_run(self.run), "SHUTDOWN")

        # ------------------------------------------------------------------------------- the ordinary line is a verdict
        def test_a_candidate_without_such_a_line_is_counted_and_commits(self):
            r = self.story(self.plan(), "S1", O.Dev({"app/calc.py": O.CALC + O.ADD, "tests/test_s1.py": O.TEST_ADD}))
            self.assertCommitted(r)
            self.assert_disposed("S1")

    return RunPath


NAMES = ("test_a_candidate_with_a_line_the_pattern_cannot_finish_ends_the_story_and_releases_what_it_held",
         "test_the_retry_is_the_environment_budget_the_run_gives_and_no_more",
         "test_a_parent_with_such_a_line_blocks_admission_before_any_developer_call",
         "test_the_next_story_of_the_run_is_not_affected_and_the_run_closes_as_a_shutdown",
         "test_a_candidate_without_such_a_line_is_counted_and_commits")


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    run_path = run_path_cases()      # its base class holds the whole orchestration suite: only the named cases run
    for name in NAMES:
        suite.addTest(run_path(name))
    return suite


if __name__ == "__main__":
    unittest.main()
