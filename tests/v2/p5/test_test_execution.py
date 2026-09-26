"""WP-5.1 — RFC §15.0: test execution is typed, not boolean.

TEST-1 (the runner is missing -> UNRUNNABLE / ENVIRONMENT, no outcome, no selection), TEST-2 (tests execute and
fail -> EXECUTED / FAILED / STORY_TESTS_RAN, DEVELOPER), the four collection-cause cases of rule 4, an empty
selection, and the shape that refuses the SS-96 edge. Real runs use the harness-owned unittest runner (stdlib alone,
so every CI job runs them); the pytest adapter is read from its own result set."""

import inspect
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Owner, TestExecutionStatus as X, TestOutcome as TO, TestSelection as TS  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.quality import test_execution as te  # noqa: E402
from aisef2.quality.test_execution import (  # noqa: E402
    Case, CollectionError, Dependencies, DeveloperTests, ResultSet, RunnerReport, TestExecution, classify,
)

POSIX = os.name == "posix"
PASSING = ("import unittest\nfrom app.calc import add\n\n\nclass T(unittest.TestCase):\n"
           "    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n")
FAILING = PASSING.replace("self.assertEqual(add(1, 2), 3)", "self.assertEqual(add(1, 2), 4)")


def project(files: dict) -> str:
    d = tempfile.mkdtemp(prefix="aisef2-p5-")
    base = {"app/__init__.py": "", "app/calc.py": "def add(a, b):\n    return a + b\n", "tests/__init__.py": ""}
    for rel, text in {**base, **files}.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def report(cases=(), errors=(), exit_code=0, launched=True, signalled=False, timed_out=False, result=True, stderr=""):
    rs = ResultSet(tuple(cases), tuple(errors)) if result else None
    return RunnerReport(launched, exit_code, signalled, timed_out, rs, stderr)


STORY = DeveloperTests("S1", ("tests/test_calc.py",))
DEPS = Dependencies(frozenset({"numpy", "requests"}), frozenset({"app"}))
RAN_OK = Case("tests.test_calc.T.test_add", "tests/test_calc.py", "passed")
RAN_BAD = Case("tests.test_calc.T.test_add", "tests/test_calc.py", "failed")


class Shape(unittest.TestCase):
    """The dataclass refuses every 'did not run => developer' shape (rule 6)."""

    def test_the_fields_are_the_rfcs(self):
        import dataclasses
        self.assertEqual([f.name for f in dataclasses.fields(TestExecution)],
                         ["status", "outcome", "selection", "owner_on_failure", "reason"])

    def test_UNRUNNABLE_carries_no_outcome_no_selection_and_only_the_environment_owner(self):
        te.unrunnable("x")  # the legal shape
        for kw in ({"outcome": TO.FAILED}, {"selection": TS.NO_STORY_TESTS_MATCHED},
                   {"owner_on_failure": Owner.DEVELOPER}, {"owner_on_failure": Owner.INTEGRATION},
                   {"owner_on_failure": None}, {"reason": None}):
            fields = {"status": X.UNRUNNABLE, "outcome": None, "selection": None, "owner_on_failure": Owner.ENVIRONMENT,
                      "reason": "the runner is missing", **kw}
            with self.subTest(kw=kw), self.assertRaises(InvariantError):
                TestExecution(**fields)

    def test_EXECUTED_owner_follows_outcome_and_selection(self):
        ok = [(TO.PASSED, TS.STORY_TESTS_RAN, None), (TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER),
              (TO.PASSED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER), (TO.FAILED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER),
              (TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER),
              (TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION)]
        for outcome, selection, owner in ok:
            TestExecution(X.EXECUTED, outcome, selection, owner, "r")
        bad = [(TO.PASSED, TS.STORY_TESTS_RAN, Owner.DEVELOPER), (TO.FAILED, TS.STORY_TESTS_RAN, None),
               (TO.FAILED, TS.STORY_TESTS_RAN, Owner.ENVIRONMENT), (TO.PASSED, TS.NO_STORY_TESTS_MATCHED, None),
               (TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.ENVIRONMENT),
               (TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, None), (None, TS.STORY_TESTS_RAN, None),
               (TO.PASSED, None, None)]
        for outcome, selection, owner in bad:
            with self.subTest(outcome=outcome, selection=selection, owner=owner), self.assertRaises(InvariantError):
                TestExecution(X.EXECUTED, outcome, selection, owner, "r")

    def test_typed_inputs_refuse_untyped_causes_and_absolute_paths(self):
        with self.assertRaises(InvariantError):
            CollectionError("t.py", "IMPORT")  # an import cause names its module
        with self.assertRaises(InvariantError):
            CollectionError("t.py", "OTHER", "x")
        with self.assertRaises(InvariantError):
            CollectionError("t.py", "prose")
        with self.assertRaises(InvariantError):
            Case("t", "t.py", "flaky")
        with self.assertRaises(InvariantError):
            DeveloperTests("S1", ("/abs/tests",))
        with self.assertRaises(InvariantError):
            DeveloperTests("S1", ())

    def test_the_refusals_say_why(self):
        R = lambda msg: self.assertRaisesRegex(InvariantError, "^" + re.escape(msg) + "$")  # noqa: E731
        with R("a test execution has a typed status"):
            TestExecution("EXECUTED", TO.PASSED, TS.STORY_TESTS_RAN, None, "r")
        with R("UNRUNNABLE: outcome and selection are defined only when EXECUTED (\u00a715.0)"):
            TestExecution(X.UNRUNNABLE, TO.PASSED, None, Owner.ENVIRONMENT, "r")
        with R("UNRUNNABLE is owner ENVIRONMENT and nothing else \u2014 never DEVELOPER (\u00a715.0 rule 1, "
               "INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE)"):
            TestExecution(X.UNRUNNABLE, None, None, Owner.DEVELOPER, "r")
        with R("UNRUNNABLE says why"):
            TestExecution(X.UNRUNNABLE, None, None, Owner.ENVIRONMENT, "")
        with R("EXECUTED carries a typed outcome and a typed selection (\u00a715.0)"):
            TestExecution(X.EXECUTED, "PASSED", TS.STORY_TESTS_RAN, None, "r")
        with R("STORY_TESTS_NOT_COLLECTABLE is owned by DEVELOPER (project source) or INTEGRATION (undeterminable); "
               "the environment-dependency shape is UNRUNNABLE (\u00a715.0 rule 4)"):
            TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.ENVIRONMENT, "r")
        with R("PASSED + STORY_TESTS_RAN is owned by nobody, not Owner.DEVELOPER (\u00a715.0)"):
            TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, Owner.DEVELOPER, "r")
        with R("FAILED + STORY_TESTS_RAN is owned by DEVELOPER, not None (\u00a715.0)"):
            TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, None, "r")
        for story in ("", None, 5):
            with self.subTest(story=story), R("developer tests belong to a story"):
                DeveloperTests(story, ("tests",))
        for paths in ((), ("",), ("/abs/tests",), (5,), "tests"):
            with self.subTest(paths=paths), R("developer tests are named by relative paths under the candidate root"):
                DeveloperTests("S1", paths)
        with R("a collection cause is IMPORT, SYNTAX or OTHER, not 'prose'"):
            CollectionError("t.py", "prose")
        with R("an IMPORT cause names the module; no other cause does"):
            CollectionError("t.py", "SYNTAX", "x")
        with R("a case outcome is one of ('passed', 'failed', 'error', 'skipped'), not 'flaky'"):
            Case("t", "t.py", "flaky")

    def test_paths_are_normalised_and_ownership_is_by_whole_path_components(self):
        self.assertEqual([te._norm(p) for p in ("./tests/a.py", "tests\\a.py", "/tests/a.py", "tests/a.py/", "tests//")],
                         ["tests/a.py", "tests/a.py", "tests/a.py", "tests/a.py", "tests"])
        story = DeveloperTests("S1", ("tests/unit", "./tests/test_one.py"))
        self.assertTrue(all(story.owns(p) for p in ("tests/unit", "tests/unit/test_a.py", "tests\\unit\\deep\\test_b.py",
                                                    "./tests/test_one.py", "tests/test_one.py")))
        self.assertFalse(any(story.owns(p) for p in ("tests/unit_extra.py", "tests/units/test_a.py", "tests/test_one.pyc",
                                                     "tests", "tests/test_two.py")))

    def test_project_top_level_names_packages_and_modules_at_the_root_and_under_src(self):
        d = project({"src/lib/__init__.py": "", "src/single.py": "", "top.py": "", "README.md": "", "docs/index.md": "",
                     "src/README.md": "", "stray.txt": ""})
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(te.project_top_level(d), frozenset({"app", "tests", "top", "lib", "single"}))
        self.assertIsInstance(te.project_top_level(d), frozenset)
        self.assertEqual(te.project_top_level(pathlib.Path(d) / "absent"), frozenset())


class Classify(unittest.TestCase):
    """§15.0 rules 1-5 on typed reports: the only mapping."""

    def test_TEST_1_a_missing_runner_is_UNRUNNABLE_ENVIRONMENT_with_no_outcome_and_no_selection(self):
        for rep in (report(launched=False, stderr="OSError: no interpreter"),
                    report(exit_code=1, result=False, stderr="python: No module named pytest"),
                    report(exit_code=3, result=False), report(signalled=True, exit_code=-9, result=False),
                    report(timed_out=True, exit_code=None, result=False)):
            with self.subTest(rep=rep):
                x = classify(rep, STORY, DEPS)
                self.assertEqual((x.status, x.outcome, x.selection, x.owner_on_failure),
                                 (X.UNRUNNABLE, None, None, Owner.ENVIRONMENT))
                self.assertIsNot(x.owner_on_failure, Owner.DEVELOPER)
                self.assertTrue(x.reason)

    def test_TEST_2_failing_assertions_are_EXECUTED_FAILED_STORY_TESTS_RAN_DEVELOPER(self):
        x = classify(report([RAN_BAD], exit_code=1), STORY, DEPS)
        self.assertEqual((x.status, x.outcome, x.selection, x.owner_on_failure),
                         (X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER))

    def test_a_passing_suite_is_EXECUTED_PASSED_STORY_TESTS_RAN_with_no_owner(self):
        x = classify(report([RAN_OK]), STORY, DEPS)
        self.assertEqual((x.status, x.outcome, x.selection, x.owner_on_failure),
                         (X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None))

    def test_rule_4_collection_cause_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT(self):
        err = CollectionError("tests/test_calc.py", "IMPORT", "numpy.linalg")
        x = classify(report(errors=[err], exit_code=1), STORY, DEPS)
        self.assertEqual((x.status, x.outcome, x.selection, x.owner_on_failure),
                         (X.UNRUNNABLE, None, None, Owner.ENVIRONMENT))
        self.assertIn("declared environment dependency", x.reason)

    def test_rule_4_collection_cause_in_the_projects_own_tree_is_DEVELOPER(self):
        err = CollectionError("tests/test_calc.py", "IMPORT", "app.missing")
        x = classify(report(errors=[err], exit_code=1), STORY, DEPS)
        self.assertEqual((x.status, x.selection, x.owner_on_failure),
                         (X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER))
        syntax = CollectionError("tests/test_calc.py", "SYNTAX")
        x = classify(report(errors=[syntax], exit_code=1), STORY, DEPS)
        self.assertEqual((x.selection, x.owner_on_failure), (TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER))

    def test_rule_4_undeterminable_collection_cause_is_INTEGRATION_never_DEVELOPER(self):
        for err in (CollectionError("tests/test_calc.py", "IMPORT", "neither_here_nor_there"),
                    CollectionError("tests/test_calc.py", "IMPORT", "app"),  # declared AND the project's: ambiguous
                    CollectionError("tests/test_calc.py", "OTHER")):
            with self.subTest(err=err):
                x = classify(report(errors=[err], exit_code=1), STORY,
                             Dependencies(frozenset({"numpy", "app"}), frozenset({"app"})))
                self.assertEqual((x.status, x.selection, x.owner_on_failure),
                                 (X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION))

    def test_rule_3_no_story_test_matched_is_DEVELOPER_by_the_typed_value_and_distinct_from_UNRUNNABLE(self):
        other = Case("tests.test_other.T.test_x", "tests/test_other.py", "passed")
        for rep in (report([], exit_code=5), report([other]), report([Case("s", "tests/test_calc.py", "skipped")])):
            with self.subTest(rep=rep):
                x = classify(rep, STORY, DEPS)
                self.assertEqual((x.status, x.selection, x.owner_on_failure),
                                 (X.EXECUTED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER))
        self.assertIs(classify(report(exit_code=5, result=False), STORY, DEPS).status, X.UNRUNNABLE)

    def test_rule_5_regressions_use_the_identical_rules(self):
        regression = DeveloperTests("S1", ("tests",))
        self.assertIs(classify(report(exit_code=1, result=False), regression, DEPS).owner_on_failure, Owner.ENVIRONMENT)
        self.assertEqual(classify(report([RAN_BAD], exit_code=1), regression, DEPS).owner_on_failure, Owner.DEVELOPER)
        self.assertIsNone(classify(report([RAN_OK]), regression, DEPS).owner_on_failure)

    def test_no_did_not_run_to_developer_edge_exists(self):
        """Every report without a result set, whatever else it says, is ENVIRONMENT; the shape refuses the rest."""
        for exit_code in (None, 0, 1, 2, 3, 4, 5, 127, -9):
            for signalled in (False, True):
                for timed_out in (False, True):
                    rep = report(exit_code=exit_code, signalled=signalled, timed_out=timed_out, result=False)
                    x = classify(rep, STORY, DEPS)
                    self.assertEqual((x.status, x.owner_on_failure), (X.UNRUNNABLE, Owner.ENVIRONMENT), rep)
        self.assertNotIn("DEVELOPER", inspect.getsource(te.unrunnable))


    def test_an_error_outcome_fails_the_story_like_a_failure(self):
        err = Case("tests.test_calc.T.test_boom", "tests/test_calc.py", "error")
        x = classify(report([RAN_OK, err], exit_code=1), STORY, DEPS)
        self.assertEqual((x.outcome, x.selection, x.owner_on_failure), (TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER))
        self.assertEqual(x.reason, "2 story-owned test(s) ran; 1 failed")
        x = classify(report([RAN_OK, RAN_BAD, err], exit_code=1), STORY, DEPS)
        self.assertEqual(x.reason, "3 story-owned test(s) ran; 2 failed")
        x = classify(report([RAN_OK, Case("s", "tests/test_calc.py", "skipped")]), STORY, DEPS)
        self.assertEqual((x.outcome, x.reason), (TO.PASSED, "1 story-owned test(s) ran; 0 failed"))

    def test_the_outcome_is_the_storys_tests_never_another_files(self):
        other_bad = Case("tests.test_other.T.test_x", "tests/test_other.py", "failed")
        x = classify(report([RAN_OK, other_bad], exit_code=1), STORY, DEPS)
        self.assertEqual((x.outcome, x.selection, x.owner_on_failure), (TO.PASSED, TS.STORY_TESTS_RAN, None))
        x = classify(report([other_bad], exit_code=1), STORY, DEPS)
        self.assertEqual((x.outcome, x.selection), (TO.PASSED, TS.NO_STORY_TESTS_MATCHED))

    def test_a_story_file_the_runner_could_not_collect_is_never_hidden_by_the_story_files_that_ran(self):
        story = DeveloperTests("S1", ("tests/test_calc.py", "tests/test_more.py"))
        for err, status, selection, owner in (
                (CollectionError("tests/test_more.py", "IMPORT", "app.gone"), X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER),
                (CollectionError("tests/test_more.py", "OTHER"), X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION),
                (CollectionError("tests/test_more.py", "IMPORT", "numpy"), X.UNRUNNABLE, None, Owner.ENVIRONMENT)):
            with self.subTest(err=err):
                x = classify(report([RAN_OK], errors=[err], exit_code=1), story, DEPS)
                self.assertEqual((x.status, x.selection, x.owner_on_failure), (status, selection, owner))
        foreign = CollectionError("tests/test_other.py", "OTHER")  # not the story's: it decides nothing
        x = classify(report([RAN_OK], errors=[foreign], exit_code=1), story, DEPS)
        self.assertEqual((x.status, x.selection, x.owner_on_failure), (X.EXECUTED, TS.STORY_TESTS_RAN, None))

    def test_reasons_are_the_typed_facts_spelled_out(self):
        def reason(rep, story=STORY, deps=DEPS):
            return classify(rep, story, deps).reason
        self.assertEqual(reason(report(launched=False, stderr="  OSError: no interpreter\n")),
                         "the configured test runner could not be launched: OSError: no interpreter")
        self.assertEqual(reason(report(launched=False)), "the configured test runner could not be launched: no process")
        self.assertEqual(reason(report(timed_out=True, exit_code=None, result=False)),
                         "the test runner did not finish within the harness deadline")
        self.assertEqual(reason(report(signalled=True, exit_code=-9, result=False)),
                         "the test runner ended by a signal before reporting a result set")
        self.assertEqual(reason(report(exit_code=3, result=False, stderr="Traceback\nModuleNotFoundError: x\n")),
                         "the test runner reported no result set (exit 3): ModuleNotFoundError: x")
        self.assertEqual(reason(report(exit_code=3, result=False)), "the test runner reported no result set (exit 3): no output")
        self.assertEqual(reason(report([], exit_code=5)),
                         "none of the story's declared tests ['tests/test_calc.py'] ran (0 test(s) in the result set)")
        both = Dependencies(frozenset({"numpy", "app"}), frozenset({"app"}))
        for err, deps, why in (
                (CollectionError("tests/test_calc.py", "SYNTAX"), DEPS, "a syntax error in the developer's own test file"),
                (CollectionError("tests/test_calc.py", "IMPORT", "numpy.linalg"), DEPS,
                 "import of 'numpy.linalg' failed: a declared environment dependency"),
                (CollectionError("tests/test_calc.py", "IMPORT", "app.missing"), DEPS,
                 "import of 'app.missing' failed: the project's own source tree"),
                (CollectionError("tests/test_calc.py", "IMPORT", "app"), both,
                 "import of 'app' failed: both a declared environment dependency and the project's own tree \u2014 cause undeterminable"),
                (CollectionError("tests/test_calc.py", "IMPORT", "nowhere"), DEPS,
                 "import of 'nowhere' failed: neither a declared environment dependency and the project's own tree \u2014 cause undeterminable"),
                (CollectionError("tests/test_calc.py", "OTHER"), DEPS, "the cause of the collection failure could not be determined")):
            with self.subTest(err=err):
                self.assertEqual(reason(report(errors=[err], exit_code=1), deps=deps), "tests/test_calc.py could not be collected: " + why)


class RealRunner(unittest.TestCase):
    """The harness-owned unittest runner, for real, at a candidate tree — fault injection: runner absent, an import
    error from a declared dependency, one from the project's own tree, an undeterminable one, an empty selection."""

    def run_(self, files, story=STORY, deps=None, runner=te.UNITTEST, **kw):
        d = project(files)
        self.addCleanup(shutil.rmtree, d, True)
        deps = deps or Dependencies(frozenset({"numpy_absent_dep"}), te.project_top_level(d))
        kw.setdefault("timeout_s", 60)
        return te.execute(runner, d, story, deps, **kw)

    def test_a_passing_suite_yields_EXECUTED_PASSED_STORY_TESTS_RAN(self):
        rep, x = self.run_({"tests/test_calc.py": PASSING})
        self.assertEqual((rep.exit_code, x.status, x.outcome, x.selection, x.owner_on_failure),
                         (0, X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None))
        self.assertEqual([c.path for c in rep.result_set.cases], ["tests/test_calc.py"])

    def test_TEST_2_for_real(self):
        rep, x = self.run_({"tests/test_calc.py": FAILING})
        self.assertEqual((rep.exit_code, x.status, x.outcome, x.selection, x.owner_on_failure),
                         (1, X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER))

    def test_TEST_1_for_real_the_configured_runner_is_absent(self):
        absent = te.Runner("absent", ("-m", "aisef2_no_such_runner", "{out}"), te._read_unittest)
        rep, x = self.run_({"tests/test_calc.py": PASSING}, runner=absent)
        self.assertEqual((rep.launched, rep.result_set, x.status, x.owner_on_failure, x.outcome, x.selection),
                         (True, None, X.UNRUNNABLE, Owner.ENVIRONMENT, None, None))
        gone = te.Runner("gone", (), te._read_unittest)
        empty = project({})
        self.addCleanup(shutil.rmtree, empty, True)
        rep, x = self.run_({"tests/test_calc.py": PASSING}, runner=gone, interpreter=str(pathlib.Path(empty) / "no-python"))
        self.assertEqual((rep.launched, x.status, x.owner_on_failure), (False, X.UNRUNNABLE, Owner.ENVIRONMENT))

    def test_a_runner_that_crashes_before_reporting_is_UNRUNNABLE(self):
        crash = te.Runner("crash", ("-c", "import sys; sys.exit(3)", "{out}"), te._read_unittest)
        rep, x = self.run_({"tests/test_calc.py": PASSING}, runner=crash)
        self.assertEqual((rep.exit_code, rep.result_set, x.status), (3, None, X.UNRUNNABLE))

    def test_collection_failure_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT(self):
        rep, x = self.run_({"tests/test_calc.py": "import numpy_absent_dep\n" + PASSING})
        self.assertEqual(rep.result_set.collection_errors[0].module, "numpy_absent_dep")
        self.assertEqual((x.status, x.owner_on_failure, x.outcome, x.selection), (X.UNRUNNABLE, Owner.ENVIRONMENT, None, None))

    def test_collection_failure_on_the_projects_own_tree_is_DEVELOPER(self):
        rep, x = self.run_({"tests/test_calc.py": "from app.missing import nothing\n" + PASSING})
        self.assertEqual(rep.result_set.collection_errors[0].module, "app.missing")
        self.assertEqual((x.status, x.selection, x.owner_on_failure), (X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER))
        rep, x = self.run_({"tests/test_calc.py": "def broken(:\n"})
        self.assertEqual(rep.result_set.collection_errors[0].kind, "SYNTAX")
        self.assertEqual((x.selection, x.owner_on_failure), (TS.STORY_TESTS_NOT_COLLECTABLE, Owner.DEVELOPER))

    def test_undeterminable_collection_cause_is_INTEGRATION(self):
        rep, x = self.run_({"tests/test_calc.py": "import neither_declared_nor_project\n" + PASSING})
        self.assertEqual((x.status, x.selection, x.owner_on_failure), (X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE, Owner.INTEGRATION))

    def test_an_empty_selection_is_NO_STORY_TESTS_MATCHED_DEVELOPER(self):
        rep, x = self.run_({"tests/test_calc.py": "import unittest\n"})  # a file with no tests
        self.assertEqual((rep.exit_code, x.status, x.selection, x.owner_on_failure),
                         (0, X.EXECUTED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER))
        rep, x = self.run_({"tests/test_calc.py": PASSING}, story=DeveloperTests("S1", ("tests/test_missing.py",)),
                           targets=("tests/test_calc.py",))
        self.assertEqual((x.status, x.selection), (X.EXECUTED, TS.NO_STORY_TESTS_MATCHED))

    def test_a_directory_target_is_discovered_and_a_node_id_selects_one_test(self):
        rep, x = self.run_({"tests/test_calc.py": PASSING}, story=DeveloperTests("S1", ("tests",)))
        self.assertEqual((x.status, x.selection), (X.EXECUTED, TS.STORY_TESTS_RAN))
        rep, x = self.run_({"tests/test_calc.py": PASSING}, targets=("tests/test_calc.py::T.test_add",))
        self.assertEqual([c.id for c in rep.result_set.cases], ["tests.test_calc.T.test_add"])

    @unittest.skipUnless(POSIX, "a runner that ends by a signal (POSIX)")
    def test_a_runner_ended_by_a_signal_is_UNRUNNABLE(self):
        dying = te.Runner("dying", ("-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)", "{out}"), te._read_unittest)
        rep, x = self.run_({"tests/test_calc.py": PASSING}, runner=dying)
        self.assertEqual((rep.signalled, rep.exit_code, x.status, x.owner_on_failure),
                         (True, -int(signal.SIGTERM), X.UNRUNNABLE, Owner.ENVIRONMENT))

    def test_the_harness_deadline_is_UNRUNNABLE_and_the_range_is_released(self):
        hang = te.Runner("hang", ("-c", "import time; time.sleep(60)", "{out}"), te._read_unittest)
        seen = []
        rep, x = self.run_({"tests/test_calc.py": PASSING}, runner=hang, timeout_s=1.0, on_range=seen.append)
        self.assertEqual((rep.timed_out, x.status, x.owner_on_failure), (True, X.UNRUNNABLE, Owner.ENVIRONMENT))
        self.assertTrue(seen[0].ledger)  # the controller's own ladder, in the ledger
        self.assertEqual(seen[0].members(), [])

    def test_the_candidate_is_the_only_tree_execute_knows(self):
        params = inspect.signature(te.execute).parameters
        self.assertNotIn("parent", params)
        self.assertFalse(any("parent" in p or "revision" in p for p in params), list(params))

    def test_the_result_set_is_typed_and_carries_the_collection_detail(self):
        rep, x = self.run_({"tests/test_calc.py": "import numpy_absent_dep\n" + PASSING, "tests/test_ok.py": PASSING},
                           story=DeveloperTests("S1", ("tests",)))
        self.assertIsInstance(rep.result_set.cases, tuple)
        self.assertIsInstance(rep.result_set.collection_errors, tuple)
        self.assertEqual([c.id for c in rep.result_set.cases], ["tests.test_ok.T.test_add"])
        (err,) = rep.result_set.collection_errors
        self.assertEqual((err.path, err.kind, err.module), ("tests/test_calc.py", "IMPORT", "numpy_absent_dep"))
        self.assertIn("No module named 'numpy_absent_dep'", err.detail)
        self.assertEqual((x.status, x.owner_on_failure), (X.UNRUNNABLE, Owner.ENVIRONMENT))  # rule 4 before rule 2


class PytestAdapter(unittest.TestCase):
    """pytest's junit result set (xunit1), typed the same way."""

    JUNIT = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="3" errors="1" failures="1">'
             '<testcase classname="tests.test_calc" file="tests/test_calc.py" line="4" name="test_add" time="0.001"/>'
             '<testcase classname="tests.test_calc" file="tests/test_calc.py" line="7" name="test_sub" time="0.001">'
             '<failure message="assert 1 == 2">assert 1 == 2</failure></testcase>'
             '<testcase classname="tests.test_dep" file="tests/test_dep.py" name="tests.test_dep" time="0.0">'
             "<error message=\"collection failure\">ImportError while importing test module\nModuleNotFoundError: No module named "
             "'numpy_absent_dep'</error></testcase>"
             '<testcase classname="tests.test_syn" file="tests/test_syn.py" name="tests.test_syn" time="0.0">'
             '<error message="collection failure">  File "tests/test_syn.py", line 1\nSyntaxError: invalid syntax</error></testcase>'
             '<testcase classname="tests.test_odd" file="tests/test_odd.py" name="tests.test_odd" time="0.0">'
             '<error message="collection failure">something the adapter cannot type</error></testcase>'
             '<testcase classname="tests.test_calc" file="tests/test_calc.py" line="9" name="test_boom" time="0.001">'
             '<error message="RuntimeError: boom">Traceback (most recent call last):\nRuntimeError: boom</error></testcase>'
             '<testcase classname="tests.test_calc" file="tests/test_calc.py" line="12" name="test_later" time="0.0">'
             '<skipped type="pytest.skip" message="not yet">tests/test_calc.py:12: not yet</skipped></testcase>'
             "</testsuite></testsuites>")

    def test_the_junit_result_set_is_read_typed(self):
        d = tempfile.mkdtemp(prefix="aisef2-junit-")
        self.addCleanup(shutil.rmtree, d, True)
        p = pathlib.Path(d) / "r.xml"
        p.write_text(self.JUNIT, encoding="utf-8")
        rs = te._read_junit(p)
        self.assertIsInstance(rs.cases, tuple)
        self.assertIsInstance(rs.collection_errors, tuple)
        self.assertEqual([(c.id, c.path, c.outcome) for c in rs.cases],
                         [("tests/test_calc.py::tests.test_calc::test_add", "tests/test_calc.py", "passed"),
                          ("tests/test_calc.py::tests.test_calc::test_sub", "tests/test_calc.py", "failed"),
                          ("tests/test_calc.py::tests.test_calc::test_boom", "tests/test_calc.py", "error"),
                          ("tests/test_calc.py::tests.test_calc::test_later", "tests/test_calc.py", "skipped")])
        self.assertEqual([e.detail for e in rs.collection_errors],  # the traceback text alone, never the XML around it
                         ["ImportError while importing test module\nModuleNotFoundError: No module named 'numpy_absent_dep'",
                          '  File "tests/test_syn.py", line 1\nSyntaxError: invalid syntax', "something the adapter cannot type"])
        self.assertEqual([(e.path, e.kind, e.module) for e in rs.collection_errors],
                         [("tests/test_dep.py", "IMPORT", "numpy_absent_dep"), ("tests/test_syn.py", "SYNTAX", None),
                          ("tests/test_odd.py", "OTHER", None)])
        x = classify(RunnerReport(True, 1, False, False, rs), STORY, DEPS)
        self.assertEqual((x.status, x.outcome, x.selection, x.owner_on_failure), (X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER))

    @unittest.skipUnless(subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0,
                         "pytest is not installed here (CI runs the stdlib runner)")
    def test_pytest_for_real(self):
        d = project({"tests/test_calc.py": FAILING})
        self.addCleanup(shutil.rmtree, d, True)
        rep, x = te.execute(te.PYTEST, d, STORY, Dependencies(frozenset(), te.project_top_level(d)), timeout_s=120)
        self.assertEqual((rep.exit_code, x.status, x.outcome, x.selection, x.owner_on_failure),
                         (1, X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER))


if __name__ == "__main__":
    unittest.main()
