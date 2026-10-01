"""WP-5.3 — RFC §15.1: the candidate-side vacuity control, for real.

VAC-1..12 through the harness-owned runner: a scratch copy of the candidate with the story's product hunks reversed
exactly, the story's tests untouched, and a per-case attribution of typed runner facts. NON_VACUOUS only when all four
frozen conditions hold; VACUOUS when the story's tests still pass without the change; INDETERMINATE for everything
non-vacuity cannot be proven from. Invariant IX: the parent revision is never executed, structurally and at runtime."""

import difflib
import hashlib
import inspect
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Owner, TestExecutionStatus as X, TestOutcome as TO, TestSelection as TS, Vacuity as V  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.quality import test_execution as te, vacuity as vc  # noqa: E402
from aisef2.quality.test_execution import Case, Dependencies, DeveloperTests, ResultSet, RunnerReport, TestExecution  # noqa: E402
from aisef2.quality.vacuity import Hunk, VacuityResult, evaluate, file_patches, neutralise  # noqa: E402

OLD = "def add(a, b):\n    return a - b\n"                       # the parent's defect
NEW = "def add(a, b):\n    return a + b\n"                       # the story's fix
NEW_MUL = NEW + "\n\ndef mul(a, b):\n    return a * b\n"          # the story adds mul
HEAD = "import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n"
TEST_ADD = HEAD + "    def test_add(self):\n        self.assertEqual(calc.add(1, 2), 3)\n"
TEST_ZERO = HEAD + "    def test_zero(self):\n        self.assertEqual(calc.add(0, 0), 0)\n"       # true either way
TEST_IMPORT_MUL = "import unittest\nfrom app.calc import mul\n\n\nclass T(unittest.TestCase):\n    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"
TEST_ATTR_MUL = HEAD + "    def test_mul(self):\n        self.assertEqual(calc.mul(2, 3), 6)\n"
TEST_SKIP_MUL = HEAD + "    @unittest.skipUnless(hasattr(calc, 'mul'), 'no mul')\n    def test_mul(self):\n        self.assertEqual(calc.mul(2, 3), 6)\n"
STORY = DeveloperTests("S1", ("tests/test_calc.py",))
IX_CWD: dict = {}


def patch(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/" + path, "b/" + path))


def project(files: dict) -> str:
    d = tempfile.mkdtemp(prefix="aisef2-p5vac-")
    base = {"app/__init__.py": "", "app/calc.py": NEW, "tests/__init__.py": ""}
    for rel, text in {**base, **files}.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def digests(root) -> dict[str, str]:
    root = pathlib.Path(root)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


class ForReal(unittest.TestCase):
    """The experiment, end to end, with the harness-owned unittest runner."""

    def story(self, files: dict, story=STORY, runner=te.UNITTEST, neutralised_runner=None, **kw):
        """Run the story's tests at the candidate (WP-5.1), then the vacuity control; return (candidate, baseline, result)."""
        d = project(files)
        self.addCleanup(shutil.rmtree, d, True)
        deps = Dependencies(frozenset(), te.project_top_level(d))
        baseline = te.execute(runner, d, story, deps, timeout_s=120)
        r = evaluate(neutralised_runner or runner, d, kw.pop("diff"), story, deps, baseline, timeout_s=120, **kw)
        return d, baseline, r

    def test_VAC_1_a_story_test_that_fails_by_assertion_once_the_product_change_is_neutralised_is_NON_VACUOUS(self):
        d, (rep0, x0), r = self.story({"tests/test_calc.py": TEST_ADD}, diff=patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((x0.status, x0.selection, x0.outcome), (X.EXECUTED, TS.STORY_TESTS_RAN, TO.PASSED))
        self.assertEqual((r.vacuity, r.neutralised, r.attributed), (V.NON_VACUOUS, ("app/calc.py",), ("tests.test_calc.T.test_add",)))
        self.assertEqual((r.execution.status, r.execution.selection, r.execution.outcome), (X.EXECUTED, TS.STORY_TESTS_RAN, TO.FAILED))
        self.assertEqual(r.reason, "1 intended story-owned test(s) fail by assertion once the story's product change is neutralised (app/calc.py)")
        self.assertEqual(pathlib.Path(d, "app/calc.py").read_text(encoding="utf-8"), NEW)  # the candidate itself is untouched
        two = "import unittest\nfrom app import calc\n\n\nclass Z(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(calc.add(1, 2), 3)\n\n\n" \
              "class A(unittest.TestCase):\n    def test_b(self):\n        self.assertEqual(calc.add(2, 2), 4)\n"
        d, _, r = self.story({"tests/test_calc.py": two}, diff=patch(OLD, NEW, "app/calc.py"))
        self.assertEqual(r.attributed, ("tests.test_calc.A.test_b", "tests.test_calc.Z.test_a"))  # attributed cases, in one order
        deps = Dependencies(frozenset(), te.project_top_level(d))
        listed_backwards = (RunnerReport(True, 0, False, False, ResultSet((Case("tests.test_calc.Z.test_a", "tests/test_calc.py", "passed"),
                                                                            Case("tests.test_calc.A.test_b", "tests/test_calc.py", "passed")), ())),
                            TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "r"))
        r = evaluate(te.UNITTEST, d, patch(OLD, NEW, "app/calc.py"), STORY, deps, listed_backwards, timeout_s=120)
        self.assertEqual(r.attributed, ("tests.test_calc.A.test_b", "tests.test_calc.Z.test_a"))  # not the baseline's order
        other_old, other_new = "K = 1\n", "K = 2\n"
        both = patch(OLD, NEW, "app/calc.py") + patch(other_old, other_new, "app/other.py")
        d, _, r = self.story({"app/other.py": other_new, "tests/test_calc.py": TEST_ADD}, diff=both)
        self.assertEqual((r.vacuity, r.neutralised), (V.NON_VACUOUS, ("app/calc.py", "app/other.py")))
        self.assertEqual(r.reason, "1 intended story-owned test(s) fail by assertion once the story's product change is neutralised (app/calc.py, app/other.py)")

    def test_VAC_2_a_story_test_that_still_passes_is_VACUOUS(self):
        d, _, r = self.story({"tests/test_calc.py": TEST_ZERO}, diff=patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((r.vacuity, r.neutralised, r.attributed), (V.VACUOUS, ("app/calc.py",), ()))
        self.assertEqual((r.execution.status, r.execution.selection, r.execution.outcome), (X.EXECUTED, TS.STORY_TESTS_RAN, TO.PASSED))
        self.assertEqual(r.reason, "1 intended story-owned test(s) still pass without the story's product change")

    def test_VAC_3_a_tree_that_cannot_be_reconstructed_is_INDETERMINATE(self):
        stale = patch(OLD, "def add(a, b):\n    return a + b + 0\n", "app/calc.py")  # not what the candidate holds
        d, _, r = self.story({"tests/test_calc.py": TEST_ADD}, diff=stale)
        self.assertEqual((r.vacuity, r.attributed, r.execution), (V.INDETERMINATE, (), None))
        self.assertIn("could not be reconstructed deterministically: app/calc.py: a hunk does not match the candidate", r.reason)

    def test_VAC_4_a_runner_unavailable_in_the_neutralised_run_is_INDETERMINATE(self):
        absent = te.Runner("absent", ("-m", "aisef2_no_such_runner", "{out}"), te._read_unittest)
        d, _, r = self.story({"tests/test_calc.py": TEST_ADD}, diff=patch(OLD, NEW, "app/calc.py"), neutralised_runner=absent)
        self.assertEqual((r.vacuity, r.attributed, r.execution.status, r.execution.owner_on_failure),
                         (V.INDETERMINATE, (), X.UNRUNNABLE, Owner.ENVIRONMENT))
        self.assertEqual(r.reason, "the runner could not execute in the neutralised tree: " + r.execution.reason)

    def test_VAC_5_a_story_test_that_no_longer_imports_is_INDETERMINATE(self):
        d, _, r = self.story({"app/calc.py": NEW_MUL, "tests/test_calc.py": TEST_IMPORT_MUL}, diff=patch(NEW, NEW_MUL, "app/calc.py"))
        self.assertEqual((r.vacuity, r.attributed, r.execution.status, r.execution.selection),
                         (V.INDETERMINATE, (), X.EXECUTED, TS.STORY_TESTS_NOT_COLLECTABLE))
        self.assertEqual(r.reason, "the story's tests did not actually execute in the neutralised tree: " + r.execution.reason)

    def test_VAC_6_intended_story_tests_that_do_not_actually_run_are_INDETERMINATE(self):
        d, _, r = self.story({"app/calc.py": NEW_MUL, "tests/test_calc.py": TEST_SKIP_MUL}, diff=patch(NEW, NEW_MUL, "app/calc.py"))
        self.assertEqual((r.vacuity, r.attributed, r.execution.selection), (V.INDETERMINATE, (), TS.NO_STORY_TESTS_MATCHED))
        one_of_two = TEST_SKIP_MUL + "\n    def test_zero(self):\n        self.assertEqual(calc.add(0, 0), 0)\n"
        d, _, r = self.story({"app/calc.py": NEW_MUL, "tests/test_calc.py": one_of_two}, diff=patch(NEW, NEW_MUL, "app/calc.py"))
        self.assertEqual((r.vacuity, r.attributed, r.execution.selection, r.execution.outcome),
                         (V.INDETERMINATE, (), TS.STORY_TESTS_RAN, TO.PASSED))       # test_zero ran and passed, test_mul was skipped
        self.assertEqual(r.reason, "1 intended story-owned test(s) did not execute in the neutralised tree")
        conditional = (HEAD + "    def test_zero(self):\n        self.assertEqual(calc.add(0, 0), 0)\n\n    if hasattr(calc, 'mul'):\n"
                       "        def test_mul(self):\n            self.assertEqual(calc.mul(2, 3), 6)\n")   # the method exists only with mul
        d, _, r = self.story({"app/calc.py": NEW_MUL, "tests/test_calc.py": conditional}, diff=patch(NEW, NEW_MUL, "app/calc.py"))
        self.assertEqual((r.vacuity, r.attributed, r.execution.selection, r.reason),
                         (V.INDETERMINATE, (), TS.STORY_TESTS_RAN, "1 intended story-owned test(s) did not execute in the neutralised tree"))

    def test_VAC_7_a_failure_not_attributable_to_the_neutralisation_is_INDETERMINATE(self):
        failing_at_candidate = HEAD + "    def test_add(self):\n        self.assertEqual(calc.add(1, 2), 4)\n"
        d, (rep0, x0), r = self.story({"tests/test_calc.py": failing_at_candidate}, diff=patch(OLD, NEW, "app/calc.py"))
        self.assertIs(x0.outcome, TO.FAILED)
        self.assertEqual((r.vacuity, r.attributed, r.execution), (V.INDETERMINATE, (), None))
        self.assertIn("no counterfactual to attribute", r.reason)
        d, _, r = self.story({"app/calc.py": NEW_MUL, "tests/test_calc.py": TEST_ATTR_MUL}, diff=patch(NEW, NEW_MUL, "app/calc.py"))
        self.assertEqual((r.vacuity, r.attributed), (V.INDETERMINATE, ()))  # AttributeError: an exception, not an assertion
        self.assertEqual(r.reason, "1 intended story-owned test(s) ended in an exception, not an assertion: the cause is not established")
        not_intended = (TEST_ZERO + "\n    @unittest.skipIf(hasattr(calc, 'mul'), 'has mul')\n    def test_only_without_mul(self):\n"
                        "        self.fail('appears only once the change is gone')\n")       # skipped at the candidate: not intended
        d, _, r = self.story({"app/calc.py": NEW_MUL, "tests/test_calc.py": not_intended}, diff=patch(NEW, NEW_MUL, "app/calc.py"))
        self.assertEqual((r.vacuity, r.attributed, r.execution.outcome), (V.INDETERMINATE, (), TO.FAILED))
        self.assertEqual(r.reason, "the neutralised run failed only in story-owned tests that were not intended: not attributable")

    def test_VAC_8_a_tests_only_diff_leaves_the_product_unchanged_and_is_VACUOUS(self):
        tests_only = patch("", TEST_ZERO, "tests/test_calc.py")
        d, _, r = self.story({"tests/test_calc.py": TEST_ZERO}, diff=tests_only)
        self.assertEqual((r.vacuity, r.neutralised, r.attributed), (V.VACUOUS, (), ()))
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="aisef2-p5vac-")) / "tree"
        self.addCleanup(shutil.rmtree, scratch.parent, True)
        n = neutralise(d, tests_only, STORY, scratch)
        self.assertEqual((n.neutralised, n.kept, n.problems), ((), ("tests/test_calc.py",), ()))
        self.assertEqual(digests(n.root), digests(d))  # the neutralised product is the candidate, byte for byte

    def test_VAC_9_a_pure_deletion_the_patch_carries_is_reconstructed_and_classified_from_execution(self):
        deleting = patch(NEW_MUL, NEW, "app/calc.py")                     # the story removes mul
        gone = HEAD + "    def test_gone(self):\n        self.assertFalse(hasattr(calc, 'mul'))\n"
        d, _, r = self.story({"app/calc.py": NEW, "tests/test_calc.py": gone}, diff=deleting)
        self.assertEqual((r.vacuity, r.neutralised, r.attributed), (V.NON_VACUOUS, ("app/calc.py",), ("tests.test_calc.T.test_gone",)))
        whole_file = "--- a/app/extra.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def extra():\n-    return 1\n"
        d, _, r = self.story({"tests/test_calc.py": HEAD + "    def test_no_extra(self):\n        import importlib.util\n"
                              "        self.assertIsNone(importlib.util.find_spec('app.extra'))\n"}, diff=whole_file)
        self.assertEqual((r.vacuity, r.neutralised, r.attributed), (V.NON_VACUOUS, ("app/extra.py",), ("tests.test_calc.T.test_no_extra",)))

    def test_VAC_10_a_deletion_the_patch_does_not_carry_is_INDETERMINATE(self):
        gone = HEAD + "    def test_gone(self):\n        self.assertFalse(hasattr(calc, 'mul'))\n"
        for shape, diff in (("binary", "Binary files a/app/blob.bin and /dev/null differ\n"),
                            ("no content", "--- a/app/extra.py\n+++ /dev/null\n"),
                            ("truncated hunk", "--- a/app/calc.py\n+++ b/app/calc.py\n@@ -5,3 +4,0 @@\n-def mul(a, b):\n")):
            with self.subTest(shape=shape):
                d, _, r = self.story({"tests/test_calc.py": gone}, diff=diff)
                self.assertEqual((r.vacuity, r.attributed, r.execution), (V.INDETERMINATE, (), None))
                self.assertIn("could not be reconstructed deterministically", r.reason)
        both = "Binary files a/app/blob.bin and /dev/null differ\n--- a/app/extra.py\n+++ /dev/null\n"
        d, _, r = self.story({"tests/test_calc.py": gone}, diff=both)
        self.assertEqual(r.reason, "the neutralised tree could not be reconstructed deterministically: app/blob.bin: the patch "
                                   "carries no reconstructible content for it; app/extra.py: the patch carries no reconstructible content for it")

    def test_VAC_11_moving_the_developer_tests_does_not_change_the_result(self):
        _, _, a = self.story({"tests/test_calc.py": TEST_ADD}, diff=patch(OLD, NEW, "app/calc.py"))
        moved = DeveloperTests("S1", ("tests/unit/test_arith.py",))
        _, _, b = self.story({"tests/unit/__init__.py": "", "tests/unit/test_arith.py": TEST_ADD.replace("class T", "class Arith")},
                             story=moved, diff=patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.vacuity, a.neutralised, len(a.attributed)), (b.vacuity, b.neutralised, len(b.attributed)))
        self.assertNotEqual(a.attributed, b.attributed)
        _, _, a = self.story({"tests/test_calc.py": TEST_ZERO}, diff=patch(OLD, NEW, "app/calc.py"))
        _, _, b = self.story({"tests/unit/__init__.py": "", "tests/unit/test_arith.py": TEST_ZERO}, story=moved, diff=patch(OLD, NEW, "app/calc.py"))
        self.assertEqual((a.vacuity, b.vacuity), (V.VACUOUS, V.VACUOUS))

    def test_VAC_12_an_unrunnable_parent_changes_nothing_because_the_parent_is_never_executed(self):
        seen = []
        d, _, r = self.story({"tests/test_calc.py": TEST_ADD}, diff=patch(OLD, NEW, "app/calc.py"), on_range=seen.append)
        parent = pathlib.Path(d).parent / (pathlib.Path(d).name + "-parent")   # a broken "parent" beside the candidate
        parent.mkdir()
        self.addCleanup(shutil.rmtree, parent, True)
        (parent / "app").mkdir()
        (parent / "app" / "calc.py").write_text("def (:\n", encoding="utf-8")          # unrunnable, no tests at all
        d2 = project({"tests/test_calc.py": TEST_ADD})
        self.addCleanup(shutil.rmtree, d2, True)
        deps = Dependencies(frozenset(), te.project_top_level(d2))
        r2 = evaluate(te.UNITTEST, d2, patch(OLD, NEW, "app/calc.py"), STORY, deps, te.execute(te.UNITTEST, d2, STORY, deps, timeout_s=120),
                      timeout_s=120, on_range=seen.append)
        self.assertEqual((r.vacuity, r.attributed), (r2.vacuity, r2.attributed))
        cwds = [pathlib.Path(rng._cwd).resolve() for rng in seen]  # the range records the cwd it was started with
        IX_CWD.update({"ranges": len(cwds), "under_controller_scratch": all("aisef2-vacuity-" in str(c) for c in cwds)})
        self.assertEqual(len(cwds), 2)
        for c in cwds:
            self.assertIn("aisef2-vacuity-", str(c))                        # the controller's scratch copy
            self.assertNotIn(str(pathlib.Path(d).resolve()), str(c))        # not the candidate itself
            self.assertNotIn("-parent", str(c))                              # never the parent


class Typed(unittest.TestCase):
    def test_the_patch_is_typed_per_file(self):
        text = (patch(OLD, NEW, "app/calc.py") + "--- /dev/null\n+++ b/app/new.py\n@@ -0,0 +1 @@\n+x = 1\n"
                "--- a/app/gone.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-g = 1\n-h = 2\n\\ No newline at end of file\n"
                "Binary files a/app/blob.bin and b/app/blob.bin differ\n"
                "diff --git a/app/odd.py b/app/odd.py\n--- a/app/odd.py\n+++ b/app/odd.py\n")
        fp = file_patches(text)
        self.assertEqual([(p.path, p.added, p.deleted, p.opaque, [(h.new_start, h.new_count, h.lines) for h in p.hunks]) for p in fp], [
            ("app/calc.py", False, False, False, [(1, 2, ((" ", "def add(a, b):"), ("-", "    return a - b"), ("+", "    return a + b")))]),
            ("app/new.py", True, False, False, [(1, 1, (("+", "x = 1"),))]),
            ("app/gone.py", False, True, False, [(0, 0, (("-", "g = 1"), ("-", "h = 2")))]),
            ("app/blob.bin", False, False, True, []),
            ("app/odd.py", False, False, True, [])])
        self.assertTrue(all(isinstance(p.hunks, tuple) for p in fp))
        (gone_binary,) = file_patches("Binary files a/app/blob.bin and /dev/null differ\n")
        self.assertEqual((gone_binary.path, gone_binary.added, gone_binary.deleted, gone_binary.opaque), ("app/blob.bin", False, True, True))
        self.assertEqual(fp[0].hunks[0].side("+"), ["def add(a, b):", "    return a + b"])
        self.assertEqual(fp[0].hunks[0].side("-"), ["def add(a, b):", "    return a - b"])
        self.assertEqual(file_patches(""), ())
        self.assertEqual(file_patches("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n?b\n+c\n")[0].opaque, True)  # a line of neither side
        self.assertEqual(file_patches("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+c\nstray\n")[0].opaque, True)   # a line after the hunk
        git_headers = ("diff --git a/x.py b/x.py\nold mode 100644\nnew mode 100755\nindex 1..2\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+c\n")
        self.assertEqual(file_patches(git_headers)[0].opaque, False)                                            # git's own headers are fine
        preamble = "From: someone\nSubject: a story\n\n" + git_headers                                          # lines before any file
        self.assertEqual([(p.path, p.opaque) for p in file_patches(preamble)], [("x.py", False)])
        empty_context = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n a\n\n-b\n+c\n"                              # a blank context line, unpadded
        (ec,) = file_patches(empty_context)
        self.assertEqual((ec.opaque, ec.hunks[0].lines), (False, ((" ", "a"), (" ", ""), ("-", "b"), ("+", "c"))))
        mid_header = "--- a/x.py\n--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-a\n+b\n"                              # x.py never got its +++
        self.assertEqual([(p.path, p.deleted, p.opaque) for p in file_patches(mid_header)], [("x.py", True, True), ("y.py", False, False)])
        mid_binary = "--- a/x.py\nBinary files a/y.bin and b/y.bin differ\n"
        self.assertEqual([(p.path, p.opaque) for p in file_patches(mid_binary)], [("x.py", True), ("y.bin", True)])
        new_side_only = "+++ b/x.py\nBinary files a/y.bin and b/y.bin differ\n"                                  # a +++ with no --- before it
        self.assertEqual([(p.path, p.added, p.opaque) for p in file_patches(new_side_only)], [("x.py", True, True), ("y.bin", False, True)])

    def test_reverse_application_is_exact_or_refused(self):
        h = file_patches(patch(OLD, NEW, "app/calc.py"))[0].hunks
        self.assertEqual(vc._reverse(NEW, h), OLD)
        self.assertIsNone(vc._reverse("def add(a, b):\n    return a * b\n", h))     # not the candidate's lines
        self.assertIsNone(vc._reverse("# moved\n" + NEW, h))                      # not at the candidate position
        two = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk\n"
        edited = "A\nb\nc\nd\ne\nf\ng\nh\ni\nj\nK\nk\n"                             # two hunks: a change and an addition
        self.assertEqual(vc._reverse(edited, file_patches(patch(two, edited, "m.txt"))[0].hunks), two)
        shifted = "a\nX\nb\nc\nd\ne\nf\ng\nh\ni\nj\nK\nk\n"                        # the first hunk changes the line count
        self.assertEqual(vc._reverse(shifted, file_patches(patch(two, shifted, "m.txt"))[0].hunks), two)  # later hunks first
        removal = "a\nc\nd\ne\nf\ng\nh\ni\nj\nk\n"
        self.assertEqual(vc._reverse(removal, file_patches(patch(two, removal, "m.txt"))[0].hunks), two)
        self.assertEqual(vc._reverse("b\n", [Hunk(0, 0, (("-", "a"),))]), "a\nb\n")            # a hunk adding nothing sits after new_start
        no_newline = "--- a/n.txt\n+++ b/n.txt\n@@ -1 +1 @@\n-y\n\\ No newline at end of file\n+x\n\\ No newline at end of file\n"
        self.assertEqual(vc._reverse("x", file_patches(no_newline)[0].hunks), "y")  # no trailing newline, kept that way
        self.assertEqual(vc._reverse("", file_patches(patch("z\n", "", "e.txt"))[0].hunks), "z\n")

    def test_neutralisation_touches_exactly_the_story_product_artefacts(self):
        d = project({"app/new.py": "x = 1\n", "newtop.py": "t = 1\n", "app/other.py": "o = 1\n", "tests/test_calc.py": TEST_ADD,
                     "docs/README.md": "r\n"})
        self.addCleanup(shutil.rmtree, d, True)
        pathlib.Path(d, ".git").mkdir()
        pathlib.Path(d, ".git", "HEAD").write_text("ref\n", encoding="utf-8")
        text = (patch(OLD, NEW, "app/calc.py") + "--- /dev/null\n+++ b/app/new.py\n@@ -0,0 +1 @@\n+x = 1\n"
                + "--- /dev/null\n+++ b/newtop.py\n@@ -0,0 +1 @@\n+t = 1\n"
                + patch("", TEST_ADD, "tests/test_calc.py") + "--- a/app/gone.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-g = 1\n-h = 2\n"
                + "--- a/app/old/deep/legacy.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-legacy = True\n")   # its directory is gone too
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="aisef2-p5vac-")) / "tree"
        self.addCleanup(shutil.rmtree, scratch.parent, True)
        n = neutralise(d, text, STORY, scratch)
        self.assertEqual((n.neutralised, n.kept, n.problems),
                         (("app/calc.py", "app/new.py", "newtop.py", "app/gone.py", "app/old/deep/legacy.py"), ("tests/test_calc.py",), ()))
        before, after = digests(d), digests(n.root)
        self.assertEqual({k for k in before if before.get(k) != after.get(k)} | {k for k in after if k not in before},
                         {"app/calc.py", "app/new.py", "newtop.py", "app/gone.py", "app/old/deep/legacy.py", ".git/HEAD"})  # .git is not copied
        self.assertEqual(after["tests/test_calc.py"], before["tests/test_calc.py"])  # the story's test file, untouched
        self.assertEqual(after["app/other.py"], before["app/other.py"])              # a product file outside the story
        self.assertEqual((after.get("app/new.py"), after.get("newtop.py")), (None, None))
        self.assertEqual(pathlib.Path(n.root, "app/gone.py").read_text(encoding="utf-8"), "g = 1\nh = 2\n")
        self.assertEqual(pathlib.Path(n.root, "app/old/deep/legacy.py").read_text(encoding="utf-8"), "legacy = True\n")
        self.assertEqual(pathlib.Path(n.root, "app/calc.py").read_text(encoding="utf-8"), OLD)
        n = neutralise(d, "Binary files a/app/blob.bin and b/app/blob.bin differ\n", STORY, scratch.parent / "tree0")
        self.assertEqual(n.problems, ("app/blob.bin: the patch carries no reconstructible content for it",))
        n = neutralise(d, "--- a/app/gone.py\n+++ /dev/null\n@@ -1 +1 @@\n-g = 1\n+h = 2\n", STORY, scratch.parent / "tree4")
        self.assertEqual(n.problems, ("app/gone.py: a deleted file whose patch is not a plain removal",))  # a '+' line in a deletion
        n = neutralise(d, "--- a/app/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-g = 1\nstray content\n", STORY, scratch.parent / "tree5")
        self.assertEqual(n.problems, ("app/gone.py: the patch carries no reconstructible content for it",))  # a line no header explains
        self.assertEqual(pathlib.Path(d, "app/calc.py").read_text(encoding="utf-8"), NEW)   # the candidate is never written
        n = neutralise(d, "--- a/app/absent.py\n+++ b/app/absent.py\n@@ -1 +1 @@\n-a\n+b\n", STORY, scratch.parent / "tree2")
        self.assertEqual(n.problems, ("app/absent.py: not a file at the candidate",))
        n = neutralise(d, "--- a/app/calc.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def add(a, b):\n-    return a + b\n", STORY, scratch.parent / "tree3")
        self.assertEqual(n.problems, ("app/calc.py: a deleted file whose patch is not a plain removal",))  # it still exists

    @unittest.skipUnless(os.name == "posix", "symbolic links (POSIX)")
    def test_a_symbolic_link_in_the_candidate_stays_a_link_in_the_scratch_copy(self):
        d = project({"tests/test_calc.py": TEST_ADD})
        self.addCleanup(shutil.rmtree, d, True)
        os.symlink("app/calc.py", pathlib.Path(d, "calc_link.py"))
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="aisef2-p5vac-")) / "tree"
        self.addCleanup(shutil.rmtree, scratch.parent, True)
        neutralise(d, patch(OLD, NEW, "app/calc.py"), STORY, scratch)
        self.assertTrue(pathlib.Path(scratch, "calc_link.py").is_symlink())        # never dereferenced into a copy

    def test_the_result_shape_refuses_every_contradiction(self):
        ran_failed = TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER, "r")
        ran_passed = TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "r")
        VacuityResult(V.NON_VACUOUS, ("a.py",), ("t",), ran_failed, "r")
        VacuityResult(V.VACUOUS, ("a.py",), (), ran_passed, "r")
        VacuityResult(V.INDETERMINATE, (), (), None, "r")
        for args, why in (((V.NON_VACUOUS, ("a.py",), (), ran_failed, "r"), "exactly an attributed assertion failure"),
                          ((V.NON_VACUOUS, ("a.py",), ("t",), ran_passed, "r"), "exactly an attributed assertion failure"),
                          ((V.NON_VACUOUS, ("a.py",), ("t",), te.unrunnable("x"), "r"), "exactly an attributed assertion failure"),
                          ((V.NON_VACUOUS, ("a.py",), ("t",), None, "r"), "exactly an attributed assertion failure"),
                          ((V.VACUOUS, ("a.py",), (), ran_failed, "r"), "executing and passing"),
                          ((V.VACUOUS, ("a.py",), (), None, "r"), "executing and passing"),
                          ((V.VACUOUS, ("a.py",), ("t",), ran_passed, "r"), "executing and passing"),
                          ((V.INDETERMINATE, (), ("t",), ran_failed, "r"), "attributes nothing"),
                          (("VACUOUS", (), (), None, "r"), "one of NON_VACUOUS, VACUOUS, INDETERMINATE")):
            with self.subTest(args=args), self.assertRaisesRegex(InvariantError, why):
                VacuityResult(*args)

    def test_a_baseline_that_does_not_pass_has_no_counterfactual(self):
        d = project({"tests/test_calc.py": TEST_ZERO})
        self.addCleanup(shutil.rmtree, d, True)
        deps = Dependencies(frozenset(), te.project_top_level(d))
        ran = Case("tests.test_calc.T.test_zero", "tests/test_calc.py", "passed")
        foreign = Case("tests.test_other.T.test_x", "tests/test_other.py", "passed")   # passed, but not the story's: not intended
        ok = (RunnerReport(True, 0, False, False, ResultSet((ran, foreign), ())), TestExecution(X.EXECUTED, TO.PASSED, TS.STORY_TESTS_RAN, None, "r"))
        r = evaluate(te.UNITTEST, d, patch(OLD, NEW, "app/calc.py"), STORY, deps, ok, timeout_s=60)
        self.assertEqual((r.vacuity, r.reason), (V.VACUOUS, "1 intended story-owned test(s) still pass without the story's product change"))
        for report, execution in ((RunnerReport(False, None, False, False, None), te.unrunnable("no runner")),
                                  (RunnerReport(True, 1, False, False, ResultSet((Case(ran.id, ran.path, "failed"),), ())),
                                   TestExecution(X.EXECUTED, TO.FAILED, TS.STORY_TESTS_RAN, Owner.DEVELOPER, "r")),
                                  (RunnerReport(True, 0, False, False, ResultSet((), ())),
                                   TestExecution(X.EXECUTED, TO.PASSED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER, "r")),
                                  (RunnerReport(True, 0, False, False, ResultSet((Case(ran.id, ran.path, "skipped"),), ())),
                                   TestExecution(X.EXECUTED, TO.PASSED, TS.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER, "r"))):
            with self.subTest(execution=execution):
                r = evaluate(te.UNITTEST, d, patch(OLD, NEW, "app/calc.py"), STORY, deps, (report, execution), timeout_s=60)
                self.assertEqual((r.vacuity, r.attributed, r.execution, r.neutralised), (V.INDETERMINATE, (), None, ()))
                self.assertEqual(r.reason, "the story's tests do not execute and pass at the candidate: there is no counterfactual to attribute")

    def test_invariant_IX_is_structural(self):
        params = inspect.signature(evaluate).parameters
        import re
        self.assertFalse(any(re.search(r"(^|_)(parent|revision|worktree|base_rev|upstream)(_|$)", p) for p in params), list(params))
        src = inspect.getsource(vc)
        for forbidden in ("parent_revision", "subprocess", "aisef2.product", "aisef2.probe", "aisef2.control", "ProductProof"):
            self.assertNotIn(forbidden, src, forbidden)   # no revision, no process of its own, no product verdict
        self.assertIn("CANDIDATE_ONLY_EXECUTION", pathlib.Path(ROOT, "validation/v2/kernel_static_checks.py").read_text(encoding="utf-8"))
        sys.path.insert(0, str(ROOT / "validation" / "v2"))
        import kernel_static_checks as ks
        self.assertEqual(ks.violations("aisef2/quality/vacuity.py", src, ("CANDIDATE_ONLY_EXECUTION",)), [])
        bad = "def evaluate(runner, candidate, parent):\n    return execute(runner, parent)\n"
        self.assertEqual(len(ks.violations("aisef2/quality/vacuity.py", bad, ("CANDIDATE_ONLY_EXECUTION",))), 2)


if __name__ == "__main__":
    unittest.main()
