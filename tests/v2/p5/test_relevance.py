"""WP-5.2 — RFC §15.2: relevance is measured, never inferred.

REL-1..8 on typed inputs and for real through the harness-owned runner's `--measure` capability: RELEVANT only from an
executed story-owned test intersecting a changed executable line (or accessing a changed non-line-addressable
artefact); IRRELEVANT only when everything was measurable; capability absent or PARTIAL is UNMEASURABLE, never
IRRELEVANT; branch evidence recorded, never required; test layout never changes the answer."""

import difflib
import inspect
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import MappingProxyType
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Enforcement as E, Owner, Relevance as R, TestExecutionStatus as X, TestOutcome as TO  # noqa: E402
from aisef2.arch.enums import TestSelection as TS  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.quality import relevance as rv, test_execution as te  # noqa: E402
from aisef2.quality.relevance import ChangedArtefact, Intersection, RelevanceResult, StoryDiff, measure, story_diff  # noqa: E402
from aisef2.quality.test_execution import Case, Dependencies, DeveloperTests, ResultSet, TestExecution  # noqa: E402

CALC_OLD = "def add(a, b):\n    return a + b\n"
CALC_NEW = CALC_OLD + "\n\ndef mul(a, b):\n    return a * b\n\n\ndef sign(x):\n    if x < 0:\n        return -1\n    return 1\n"
# CALC_NEW line numbers: 1 def add, 2 return, 5 def mul, 6 return, 9 def sign, 10 if, 11 return -1, 12 return 1
HEAD = "import unittest\nfrom app.calc import add, mul, sign\n\n\nclass T(unittest.TestCase):\n"
TEST_MUL = HEAD + "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"
TEST_ADD = HEAD + "    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n"
TEST_SIGN = HEAD + "    def test_sign(self):\n        self.assertEqual(sign(-4), -1)\n"
TEST_DATA = ("import json, pathlib, unittest\n\n\nclass T(unittest.TestCase):\n    def test_data(self):\n"
             "        self.assertEqual(json.loads(pathlib.Path('app/data.json').read_text())['k'], 2)\n")
DATA_OLD, DATA_NEW = '{"k": 1}\n', '{"k": 2}\n'
STORY = DeveloperTests("S1", ("tests/test_calc.py",))
X_RAN = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "ran")
X_NONE = TestExecution(X.EXECUTED, TO.PASSED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER, "none matched")
T1 = Case("tests.test_calc.T.test_mul", "tests/test_calc.py", "passed")


def patch(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/" + path, "b/" + path))


CALC_DIFF = story_diff(patch(CALC_OLD, CALC_NEW, "app/calc.py"))       # lines 3..12 at the candidate
DATA_DIFF = story_diff(patch(DATA_OLD, DATA_NEW, "app/data.json"))     # line 1


def project(files: dict) -> str:
    d = tempfile.mkdtemp(prefix="aisef2-p5rel-")
    base = {"app/__init__.py": "", "app/calc.py": CALC_NEW, "app/data.json": DATA_NEW, "tests/__init__.py": ""}
    for rel, text in {**base, **files}.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def rs(cases=(T1,), caps=("FULL", "FULL", "FULL"), lines=None, accessed=None, arcs=None) -> ResultSet:
    names = (te.LINE_COVERAGE, te.ARTEFACT_ACCESS, te.BRANCH_COVERAGE)
    return ResultSet(tuple(cases), (), MappingProxyType({n: E(v) for n, v in zip(names, caps, strict=True) if v}),
                     MappingProxyType({c: MappingProxyType({p: frozenset(v) for p, v in m.items()}) for c, m in (lines or {}).items()}),
                     MappingProxyType({c: frozenset(v) for c, v in (accessed or {}).items()}),
                     MappingProxyType({c: MappingProxyType({p: frozenset(v) for p, v in m.items()}) for c, m in (arcs or {}).items()}))


class Typed(unittest.TestCase):
    """REL-1..8 on typed inputs: the only thing `measure` reads."""

    def setUp(self):
        self.d = project({})
        self.addCleanup(shutil.rmtree, self.d, True)

    def m(self, result_set, execution=X_RAN, diff=CALC_DIFF, story=STORY):
        return measure(execution, result_set, story, diff, self.d)

    def test_REL_1_an_executed_story_test_intersecting_a_changed_executable_line_is_RELEVANT(self):
        r = self.m(rs(lines={T1.id: {"app/calc.py": {1, 2, 5, 6}}}))
        self.assertIs(r.relevance, R.RELEVANT)
        self.assertEqual(r.intersections, (Intersection(T1.id, "app/calc.py", frozenset({5, 6})),))  # 1, 2 are unchanged
        self.assertEqual((r.unmeasured, r.branch_intersections), ((), ()))

    def test_REL_2_measured_story_tests_with_zero_intersection_are_IRRELEVANT(self):
        r = self.m(rs(lines={T1.id: {"app/calc.py": {1, 2}}}))
        self.assertEqual((r.relevance, r.intersections, r.unmeasured), (R.IRRELEVANT, (), ()))
        r = self.m(rs(lines={T1.id: {"app/calc.py": {3, 4, 7, 8}}}))  # changed but not executable (blank lines)
        self.assertIs(r.relevance, R.IRRELEVANT)

    def test_REL_3_coverage_capability_unavailable_is_UNMEASURABLE_never_IRRELEVANT(self):
        for caps in (("UNAVAILABLE", "FULL", "FULL"), (None, None, None)):
            with self.subTest(caps=caps):
                r = self.m(rs(caps=caps, lines={T1.id: {"app/calc.py": {5, 6}}}))
                self.assertIs(r.relevance, R.UNMEASURABLE)
                self.assertIsNot(r.relevance, R.IRRELEVANT)
                self.assertEqual(r.unmeasured, (("app/calc.py", "line-coverage is UNAVAILABLE"),))
                self.assertEqual(r.intersections, ())  # the lines a missing capability reports are not read

    def test_REL_4_coverage_capability_PARTIAL_is_UNMEASURABLE(self):
        r = self.m(rs(caps=("PARTIAL", "FULL", "FULL"), lines={T1.id: {"app/calc.py": {5, 6}}}))
        self.assertEqual((r.relevance, r.unmeasured), (R.UNMEASURABLE, (("app/calc.py", "line-coverage is PARTIAL"),)))

    def test_REL_5_branch_evidence_is_recorded_when_present_and_never_required(self):
        lines = {T1.id: {"app/calc.py": {5, 6}}}
        without = self.m(rs(caps=("FULL", "FULL", "UNAVAILABLE"), lines=lines))          # no branch capability at all
        straight = self.m(rs(lines=lines, arcs={T1.id: {"app/calc.py": {(2, 5)}}}))       # arcs, none from the change
        self.assertEqual((without.relevance, straight.relevance), (R.RELEVANT, R.RELEVANT))
        self.assertEqual((without.branch_intersections, straight.branch_intersections, without.unmeasured), ((), (), ()))
        branchy = self.m(rs(lines={T1.id: {"app/calc.py": {9, 10, 11}}}, arcs={T1.id: {"app/calc.py": {(10, 11)}}}))
        self.assertIs(branchy.relevance, R.RELEVANT)
        self.assertEqual(branchy.branch_intersections, (Intersection(T1.id, "app/calc.py", frozenset({10})),))
        same_without_arcs = self.m(rs(caps=("FULL", "FULL", "PARTIAL"), lines={T1.id: {"app/calc.py": {9, 10, 11}}}))
        self.assertEqual((same_without_arcs.relevance, same_without_arcs.intersections), (branchy.relevance, branchy.intersections))
        irrelevant = self.m(rs(caps=("FULL", "FULL", "UNAVAILABLE"), lines={T1.id: {"app/calc.py": {1, 2}}}))
        self.assertIs(irrelevant.relevance, R.IRRELEVANT)  # absent branch capability never makes anything UNMEASURABLE

    def test_REL_6_a_non_line_addressable_artefact_uses_its_own_measurement(self):
        r = self.m(rs(accessed={T1.id: {"app/data.json"}}), diff=DATA_DIFF)
        self.assertEqual((r.relevance, r.intersections), (R.RELEVANT, (Intersection(T1.id, "app/data.json", frozenset()),)))
        r = self.m(rs(accessed={T1.id: {"app/other.json"}}), diff=DATA_DIFF)
        self.assertEqual((r.relevance, r.unmeasured), (R.IRRELEVANT, ()))

    def test_REL_7_a_non_line_addressable_artefact_without_a_capability_is_UNMEASURABLE(self):
        for caps in (("FULL", "UNAVAILABLE", "FULL"), ("FULL", "PARTIAL", "FULL"), ("FULL", None, "FULL")):
            with self.subTest(caps=caps):
                r = self.m(rs(caps=caps, lines={T1.id: {"app/data.json": {1}}}, accessed={T1.id: {"app/data.json"}}), diff=DATA_DIFF)
                self.assertIs(r.relevance, R.UNMEASURABLE)  # no line approximation is forced on it
                self.assertEqual(r.unmeasured[0][0], "app/data.json")

    def test_REL_8_the_same_coverage_under_another_test_layout_is_the_same_result(self):
        moved = Case("tests.unit.test_calculator.Calc.test_product", "tests/unit/test_calculator.py", "passed")
        a = self.m(rs(lines={T1.id: {"app/calc.py": {5, 6}}}))
        b = self.m(rs(cases=(moved,), lines={moved.id: {"app/calc.py": {5, 6}}}),
                   story=DeveloperTests("S1", ("tests/unit/test_calculator.py",)))
        self.assertEqual((a.relevance, {(i.path, i.lines) for i in a.intersections}),
                         (b.relevance, {(i.path, i.lines) for i in b.intersections}))

    def test_a_test_that_did_not_execute_establishes_nothing(self):
        with self.assertRaisesRegex(InvariantError, "defined only when the execution is EXECUTED"):
            self.m(rs(lines={T1.id: {"app/calc.py": {5, 6}}}), execution=te.unrunnable("no runner"))
        skipped = Case(T1.id, T1.path, "skipped")
        r = self.m(rs(cases=(skipped,), lines={T1.id: {"app/calc.py": {5, 6}}}))
        self.assertIs(r.relevance, R.IRRELEVANT)
        other = Case("tests.test_other.T.t", "tests/test_other.py", "passed")   # not the story's
        r = self.m(rs(cases=(other,), lines={other.id: {"app/calc.py": {5, 6}}}), execution=X_NONE)
        self.assertIs(r.relevance, R.IRRELEVANT)  # NO_STORY_TESTS_MATCHED is never converted into relevance
        r = self.m(rs(cases=(other,), caps=(None, None, None)), execution=X_NONE)
        self.assertIs(r.relevance, R.UNMEASURABLE)

    def test_the_developers_own_test_file_is_not_the_product_change(self):
        both = StoryDiff((ChangedArtefact("app/calc.py", frozenset({5, 6})), ChangedArtefact("tests/test_calc.py", frozenset({6, 7}))))
        r = self.m(rs(lines={T1.id: {"tests/test_calc.py": {6, 7}, "app/calc.py": {1, 2}}}), diff=both)
        self.assertEqual((r.relevance, r.intersections), (R.IRRELEVANT, ()))
        tests_only = StoryDiff((ChangedArtefact("tests/test_calc.py", frozenset({6, 7})),))
        self.assertIs(self.m(rs(lines={T1.id: {"tests/test_calc.py": {6, 7}}}), diff=tests_only).relevance, R.IRRELEVANT)

    def test_REL_DEL_1_a_pure_executable_deletion_is_UNMEASURABLE_not_IRRELEVANT(self):
        deletion = StoryDiff((ChangedArtefact("app/calc.py", frozenset(), 4),))      # mul and sign removed, nothing added
        r = self.m(rs(lines={T1.id: {"app/calc.py": {1, 2}}}), diff=deletion)          # the test ran and executed what is left
        self.assertIs(r.relevance, R.UNMEASURABLE)
        self.assertIsNot(r.relevance, R.IRRELEVANT)
        self.assertEqual(r.unmeasured, (("app/calc.py", "4 executable line(s) removed with nothing added: no candidate line "
                                         "carries the deletion, so the candidate-side line measurement cannot observe it "
                                         "(\u00a715.2 defines no deletion capability)"),))
        gone = StoryDiff((ChangedArtefact("app/gone.py", frozenset(), 3),))            # a deleted file
        r = self.m(rs(lines={T1.id: {"app/calc.py": {1, 2}}}), diff=gone)
        self.assertEqual((r.relevance, r.unmeasured[0][0]), (R.UNMEASURABLE, "app/gone.py"))
        self.assertIn("deleted at the candidate", r.unmeasured[0][1])
        gone_data = StoryDiff((ChangedArtefact("app/gone.json", frozenset(), 1),))     # a deleted non-line-addressable file
        r = self.m(rs(accessed={T1.id: {"app/data.json"}}), diff=gone_data)
        self.assertEqual((r.relevance, r.unmeasured[0][0]), (R.UNMEASURABLE, "app/gone.json"))
        mixed = StoryDiff((ChangedArtefact("app/calc.py", frozenset({5, 6}), 2),))     # a removal hunk and an addition hunk
        self.assertIs(self.m(rs(lines={T1.id: {"app/calc.py": {5, 6}}}), diff=mixed).relevance, R.RELEVANT)   # the addition intersects
        self.assertIs(self.m(rs(lines={T1.id: {"app/calc.py": {1, 2}}}), diff=mixed).relevance, R.UNMEASURABLE)  # the removal is unobservable

    def test_REL_DEL_2_and_3_ordinary_modifications_are_measured(self):
        modification = StoryDiff((ChangedArtefact("app/calc.py", frozenset({6}), 0),))
        self.assertIs(self.m(rs(lines={T1.id: {"app/calc.py": {1, 2}}}), diff=modification).relevance, R.IRRELEVANT)  # REL-DEL-2
        self.assertIs(self.m(rs(lines={T1.id: {"app/calc.py": {5, 6}}}), diff=modification).relevance, R.RELEVANT)    # REL-DEL-3

    def test_REL_DEL_4_a_tests_only_diff_is_measured_empty_and_is_not_a_deletion(self):
        tests_only = StoryDiff((ChangedArtefact("tests/test_calc.py", frozenset({6, 7})),))
        r = self.m(rs(lines={T1.id: {"tests/test_calc.py": {6, 7}, "app/calc.py": {1, 2}}}), diff=tests_only)
        self.assertEqual((r.relevance, r.unmeasured, r.intersections), (R.IRRELEVANT, (), ()))  # measurable, empty product change
        self.assertEqual(r.reason, "1 executed story-owned test(s) measured; none intersects the change")
        deletion = StoryDiff((ChangedArtefact("app/calc.py", frozenset(), 4),))
        self.assertIs(self.m(rs(lines={T1.id: {"app/calc.py": {1, 2}}}), diff=deletion).relevance, R.UNMEASURABLE)
        self.assertIs(self.m(rs(caps=(None, None, None)), diff=tests_only).relevance, R.IRRELEVANT)  # no product artefact needs a capability

    def test_one_unmeasurable_artefact_never_hides_behind_the_others(self):
        two = StoryDiff((ChangedArtefact("app/calc.py", frozenset({5, 6})), ChangedArtefact("app/data.json", frozenset({1}))))
        r = self.m(rs(caps=("FULL", "UNAVAILABLE", "FULL"), lines={T1.id: {"app/calc.py": {1, 2}}}), diff=two)
        self.assertEqual((r.relevance, r.unmeasured), (R.UNMEASURABLE, (("app/data.json", "artefact-access is UNAVAILABLE"),)))
        r = self.m(rs(caps=("FULL", "UNAVAILABLE", "FULL"), lines={T1.id: {"app/calc.py": {5, 6}}}), diff=two)
        self.assertEqual((r.relevance, r.unmeasured), (R.RELEVANT, (("app/data.json", "artefact-access is UNAVAILABLE"),)))
        broken = StoryDiff((ChangedArtefact("app/broken.py", frozenset({1})),))
        pathlib.Path(self.d, "app/broken.py").write_text("def (:\n", encoding="utf-8")
        r = self.m(rs(lines={T1.id: {"app/broken.py": {1}}}), diff=broken)
        self.assertEqual((r.relevance, r.unmeasured),
                         (R.UNMEASURABLE, (("app/broken.py", "line-coverage cannot read it: not compilable at the candidate"),)))
        self.assertTrue(rv.line_addressable("app/broken.py") and not rv.line_addressable("app/data.json"))

    def test_the_result_shape_refuses_every_contradiction(self):
        with self.assertRaisesRegex(InvariantError, "RELEVANT is exactly a measured intersection"):
            RelevanceResult(R.RELEVANT, (), (), (), "r")
        with self.assertRaisesRegex(InvariantError, "capability absence is UNMEASURABLE, never IRRELEVANT"):
            RelevanceResult(R.IRRELEVANT, (), (), (("a.py", "line-coverage is UNAVAILABLE"),), "r")
        with self.assertRaisesRegex(InvariantError, "UNMEASURABLE names the artefact"):
            RelevanceResult(R.UNMEASURABLE, (), (), (), "r")
        with self.assertRaisesRegex(InvariantError, "one of RELEVANT, IRRELEVANT, UNMEASURABLE"):
            RelevanceResult("RELEVANT", (), (), (), "r")
        with self.assertRaisesRegex(InvariantError, "relative path"):
            ChangedArtefact("/abs/a.py", frozenset({1}))
        with self.assertRaisesRegex(InvariantError, "positive candidate line numbers"):
            ChangedArtefact("a.py", frozenset({0}))
        with self.assertRaisesRegex(InvariantError, "removed lines are counted"):
            ChangedArtefact("a.py", frozenset({1}), -1)
        with self.assertRaisesRegex(InvariantError, "changes something"):
            ChangedArtefact("a.py", frozenset())

    def test_reasons_are_the_measured_facts(self):
        self.assertEqual(self.m(rs(lines={T1.id: {"app/calc.py": {5, 6}}})).reason,
                         "1 intersection(s) of executed story-owned tests with the change")
        self.assertEqual(self.m(rs(lines={T1.id: {"app/calc.py": {1}}})).reason,
                         "1 executed story-owned test(s) measured; none intersects the change")
        self.assertEqual(self.m(rs(caps=("PARTIAL", "FULL", "FULL"))).reason,
                         "1 changed artefact(s) no capability could measure: line-coverage is PARTIAL")

    def test_nothing_here_reaches_the_product_verdict(self):
        src = inspect.getsource(rv)
        for forbidden in ("aisef2.product", "aisef2.probe", "aisef2.control", "BehaviorVerdict", "ContractSatisfaction",
                          "ProductProof", "os.listdir", "glob", "fnmatch"):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertEqual(set(rv.__all__) & {"ProductProofSpec", "Verdict"}, set())


class Parsing(unittest.TestCase):
    def test_a_unified_diff_becomes_candidate_line_numbers(self):
        self.assertEqual([(a.path, sorted(a.lines)) for a in CALC_DIFF.artefacts], [("app/calc.py", list(range(3, 13)))])
        git = ("diff --git a/app/calc.py b/app/calc.py\nindex 1..2 100644\n--- a/app/calc.py\n+++ b/app/calc.py\n"
               "@@ -1,2 +1,4 @@\n def add(a, b):\n-    return a + b\n+    return a + b  # changed\n+++ x = 1\n+y = 2\n"
               "\\ No newline at end of file\n"
               "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n"
               "diff --git a/new.txt b/new.txt\n--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+a\n+b\n")
        d = story_diff(git)
        self.assertEqual([(a.path, sorted(a.lines), a.removed) for a in d.artefacts],
                         [("app/calc.py", [2, 3, 4], 0), ("gone.py", [], 1), ("new.txt", [1, 2], 0)])  # a deleted file is an artefact
        self.assertEqual(story_diff(""), StoryDiff(()))
        unordered = patch("x\n", "y\n", "z/last.py") + patch("x\n", "y\n", "a/first.py") + "--- b.txt\n+++ b.txt\n@@ -1 +1 @@\n-x\n+y\n"
        self.assertEqual([a.path for a in story_diff(unordered).artefacts], ["a/first.py", "b.txt", "z/last.py"])  # canonical order
        self.assertEqual(story_diff(patch("a\nb\n", "b\n", "x.py")), StoryDiff((ChangedArtefact("x.py", frozenset(), 1),)))  # a deletion
        self.assertEqual(story_diff(patch("a\nb\nc\n", "a\nB\nc\n", "m.py")), StoryDiff((ChangedArtefact("m.py", frozenset({2}), 0),)))
        mixed = patch("a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk\n", "a\nc\nd\ne\nf\ng\nh\ni\nj\nK\nk\n", "m.py")  # a removal hunk and an addition hunk
        (a,) = story_diff(mixed).artefacts
        self.assertEqual((sorted(a.lines), a.removed), ([10], 1))

    def test_executable_lines_are_the_code_objects_own(self):
        d = project({"m.py": '"""doc"""\nimport os\n\n\ndef f(x):\n    # comment\n    if x:\n        return 1\n    return 2\n'})
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(sorted(rv.executable_lines(d, "m.py")), [1, 2, 5, 7, 8, 9])
        self.assertIsNone(rv.executable_lines(d, "app/data.json"))
        self.assertIsNone(rv.executable_lines(d, "absent.py"))
        pathlib.Path(d, "bad.py").write_text("def (:\n", encoding="utf-8")
        self.assertIsNone(rv.executable_lines(d, "bad.py"))
        pathlib.Path(d, "dir.py").mkdir()                                   # unreadable as a file (OSError)
        self.assertIsNone(rv.executable_lines(d, "dir.py"))
        with mock.patch("builtins.compile", side_effect=ValueError("null bytes")):  # what Python <= 3.11 raises for them
            self.assertIsNone(rv.executable_lines(d, "m.py"))


class ForReal(unittest.TestCase):
    """The harness-owned runner measures for real: `--measure` turns the capability on and declares its level."""

    def run_(self, files, story=STORY, diff=CALC_DIFF, measured=True, runner=te.UNITTEST):
        d = project(files)
        self.addCleanup(shutil.rmtree, d, True)
        targets = (*story.paths, te.MEASURE) if measured else story.paths
        rep, x = te.execute(runner, d, story, Dependencies(frozenset(), te.project_top_level(d)), targets=targets, timeout_s=120)
        self.assertEqual((x.status, x.selection), (X.EXECUTED, TS.STORY_TESTS_RAN), x)
        return rep, measure(x, rep.result_set, story, diff, d)

    def test_REL_1_for_real(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_MUL})
        self.assertEqual(rep.result_set.capabilities[te.LINE_COVERAGE], E.FULL)
        self.assertIs(r.relevance, R.RELEVANT)
        (hit,) = r.intersections
        self.assertEqual((hit.case_id, hit.path, hit.lines), ("tests.test_calc.T.test_mul", "app/calc.py", frozenset({6})))

    def test_REL_2_for_real(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_ADD})
        self.assertEqual((r.relevance, r.intersections, r.unmeasured), (R.IRRELEVANT, (), ()))

    def test_REL_3_for_real_the_runner_without_the_capability_declares_it(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_MUL}, measured=False)
        self.assertEqual(rep.result_set.capabilities[te.LINE_COVERAGE], E.UNAVAILABLE)
        self.assertEqual((r.relevance, r.unmeasured), (R.UNMEASURABLE, (("app/calc.py", "line-coverage is UNAVAILABLE"),)))

    def test_REL_4_for_real_a_test_that_replaces_the_tracer_makes_the_measurement_PARTIAL(self):
        hostile = HEAD + "    def test_mul(self):\n        import sys\n        sys.settrace(None)\n        self.assertEqual(mul(2, 3), 6)\n"
        rep, r = self.run_({"tests/test_calc.py": hostile})
        self.assertEqual(rep.result_set.capabilities[te.LINE_COVERAGE], E.PARTIAL)
        self.assertEqual((r.relevance, r.unmeasured), (R.UNMEASURABLE, (("app/calc.py", "line-coverage is PARTIAL"),)))

    def test_REL_5_for_real_branch_evidence_is_recorded_and_the_value_is_the_lines(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_SIGN})
        self.assertIs(r.relevance, R.RELEVANT)
        self.assertEqual({i.lines for i in r.intersections}, {frozenset({10, 11})})
        self.assertEqual({i.lines for i in r.branch_intersections}, {frozenset({10})})   # the arc 10 -> 11 was taken
        rep, r = self.run_({"tests/test_calc.py": TEST_MUL})                               # straight-line code: no arcs from the change
        self.assertEqual((r.relevance, r.branch_intersections), (R.RELEVANT, ()))

    def test_REL_6_for_real_an_accessed_data_file(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_DATA}, diff=DATA_DIFF)
        self.assertEqual((r.relevance, r.intersections), (R.RELEVANT, (Intersection("tests.test_calc.T.test_data", "app/data.json", frozenset()),)))
        rep, r = self.run_({"tests/test_calc.py": TEST_MUL}, diff=DATA_DIFF)
        self.assertEqual((r.relevance, r.unmeasured), (R.IRRELEVANT, ()))

    def test_REL_7_for_real_no_capability_for_the_data_file(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_DATA}, diff=DATA_DIFF, measured=False)
        self.assertEqual((r.relevance, r.unmeasured), (R.UNMEASURABLE, (("app/data.json", "artefact-access is UNAVAILABLE"),)))

    def test_REL_8_for_real_the_same_tests_in_another_layout(self):
        rep, a = self.run_({"tests/test_calc.py": TEST_MUL})
        moved = DeveloperTests("S1", ("tests/unit/test_calculator.py",))
        rep, b = self.run_({"tests/unit/__init__.py": "", "tests/unit/test_calculator.py": TEST_MUL.replace("class T", "class Calc")}, story=moved)
        self.assertEqual((a.relevance, {(i.path, i.lines) for i in a.intersections}), (b.relevance, {(i.path, i.lines) for i in b.intersections}))
        self.assertNotEqual([i.case_id for i in a.intersections], [i.case_id for i in b.intersections])

    def test_REL_DEL_1_for_real_the_story_deletes_executable_code_and_its_test_verifies_the_deletion(self):
        deleted = story_diff(patch(CALC_NEW, CALC_OLD, "app/calc.py"))            # parent had mul and sign; the candidate has not
        (artefact,) = deleted.artefacts
        self.assertEqual((artefact.lines, artefact.removed), (frozenset(), 10))
        verifies = ("import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_gone(self):\n"
                    "        self.assertFalse(hasattr(calc, 'mul'))\n        self.assertEqual(calc.add(1, 2), 3)\n")
        rep, r = self.run_({"app/calc.py": CALC_OLD, "tests/test_calc.py": verifies}, diff=deleted)
        self.assertEqual(rep.result_set.capabilities[te.LINE_COVERAGE], E.FULL)     # the capability is there and FULL
        self.assertTrue(rep.result_set.lines["tests.test_calc.T.test_gone"]["app/calc.py"])  # the test executed candidate lines
        self.assertIs(r.relevance, R.UNMEASURABLE)                                    # yet the deletion has no line to intersect
        self.assertIsNot(r.relevance, R.IRRELEVANT)
        self.assertEqual(r.unmeasured[0][0], "app/calc.py")

    def test_product_code_run_in_a_thread_is_measured(self):
        threaded = HEAD.replace("import unittest", "import threading, unittest") + (
            "    def test_mul(self):\n        out = []\n        t = threading.Thread(target=lambda: out.append(mul(2, 3)))\n"
            "        t.start(); t.join()\n        self.assertEqual(out, [6])\n")
        rep, r = self.run_({"tests/test_calc.py": threaded})
        self.assertIs(r.relevance, R.RELEVANT)

    @unittest.skipUnless(subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0,
                         "pytest is not installed here (CI runs the stdlib runner)")
    def test_the_pytest_adapter_declares_no_measurement(self):
        rep, r = self.run_({"tests/test_calc.py": TEST_MUL}, measured=False, runner=te.PYTEST)
        self.assertEqual(rep.result_set.capabilities, {})
        self.assertIs(r.relevance, R.UNMEASURABLE)


if __name__ == "__main__":
    unittest.main()
