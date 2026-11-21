"""F2 (W1-DESIGN §7, DEPENDENCY-DAG R6): typed test markers generate the release exception set; the meta-test.

Fails on a product-category marker, a marker without a checklist ID, or an unmarked exception, and on every other
way a marker can claim more than it shows (validation/qualification/test_markers.py). release_qualify's v2.2 rule
(no exception below 2.3 except the 2.1.0 history allowlist) is pinned unchanged. Red-before: on the base
release_qualify, a hand-authored V2.3.0 or V2.2.0 allowlist was honoured for its own version (qualification PASS);
it is now a blocker.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_qualify as rq  # noqa: E402
from validation.qualification import test_markers as tm  # noqa: E402

HEAD = ("import unittest\nfrom tests.v2.sealing_gate import sealing\n"
        "from validation.qualification.test_markers import marker\n\n\n"
        "class Pos(unittest.TestCase):\n    def test_positive(self):\n        pass\n\n\n")
GOOD = dict(category="'platform-harness'", id="'F2'", reason="'the harness is POSIX-only'",
            platforms="['windows']", positive="'v9.test_fix.Pos.test_positive'")


def _call(**over) -> str:
    f = {**GOOD, **over}
    return "marker(" + ", ".join(f"{k}={v}" for k, v in f.items() if v is not None) + ")"


def _method(deco: str, extra: str = "") -> str:
    return HEAD + f"class T(unittest.TestCase):\n    {extra}@{deco}\n    def test_x(self):\n        pass\n"


def _collect(source: str, more: dict[str, str] | None = None):
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "docs/v2.3").mkdir(parents=True)
        (root / tm.CHECKLIST).write_text((ROOT / tm.CHECKLIST).read_text(encoding="utf-8"), encoding="utf-8")
        files = {"tests/v9/__init__.py": "", "tests/v9/test_fix.py": source, **(more or {})}
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return tm.collect(root)


class Markers(unittest.TestCase):
    def assertRefused(self, source: str, reason: str, more: dict[str, str] | None = None):
        _, problems = _collect(source, more)
        self.assertTrue(any(reason in p for p in problems), f"{reason!r} not in {problems}")

    def test_a_well_formed_marker_is_read_exactly_and_clean(self):
        markers, problems = _collect(_method(_call()))
        self.assertEqual(problems, [])
        self.assertEqual(markers, [tm.Marker(
            test="v9.test_fix.T.test_x", category="platform-harness", id="F2", reason="the harness is POSIX-only",
            platforms=("windows",), positive="v9.test_fix.Pos.test_positive", where="tests/v9/test_fix.py:12")])

    def test_the_decorator_is_inert(self):
        def f():
            pass
        self.assertIs(tm.marker(category="product", anything=1)(f), f)

    def test_a_product_or_safety_category_is_refused(self):
        for category in ("'product'", "'security'", "'process-safety'", "'record-currency'"):
            with self.subTest(category=category):
                self.assertRefused(_method(_call(category=category)), "is not one of ['platform-harness', 'sealing']")

    def test_a_marker_without_a_checklist_id_is_refused(self):
        self.assertRefused(_method(_call(id="'NOPE-1'")), "is not a checklist ID")
        self.assertRefused(_method(_call(id="'#34'")), "is not a checklist ID")   # a CODE-AUDIT number is no row
        self.assertRefused(_method(_call(id=None)), "the fields must be exactly")

    def test_fields_are_exact_typed_literals(self):
        self.assertRefused(_method(_call(reason="' '")), "the reason is empty")
        self.assertRefused(_method(_call(reason="str(1)")), "every field must be a literal")
        self.assertRefused(_method(_call(evidence="'x'")), "the fields must be exactly")
        self.assertRefused(_method(_call(platforms="'windows'")), "platforms a list of strings")
        self.assertRefused(_method("marker('platform-harness')"), "keyword fields only")
        self.assertRefused(_method("marker"), "keyword fields only")
        self.assertRefused(_method("marker(**FIELDS)"), "keyword fields only")

    def test_platforms_are_a_subset_and_a_platform_limit_is_not_everywhere(self):
        self.assertRefused(_method(_call(platforms="[]")), "non-empty subset")
        self.assertRefused(_method(_call(platforms="['solaris']")), "non-empty subset")
        self.assertRefused(_method(_call(platforms="['linux', 'darwin', 'windows']")), "is not a platform limit")

    def test_sealing_only_on_a_test_in_the_closed_gated_list(self):
        seal = _call(category="'sealing'", platforms="['linux', 'darwin', 'windows']")
        gated = _method(seal, extra="@sealing\n    ")
        self.assertRefused(_method(seal), "the @sealing gate does not carry")
        self.assertRefused(gated, "the @sealing gate does not carry")       # a decorator's name alone is no gate
        for entry in ("tests/v9/test_fix.py::T.test_x", "tests/v9/test_fix.py::T"):
            with self.subTest(entry=entry):
                self.assertEqual(_collect(gated, {tm.GATE: f"GATED = ({entry!r},)\n"})[1], [])
        self.assertRefused(gated, "the @sealing gate does not carry", {tm.GATE: "GATED = ('tests/v9/test_fix.py::T.test_y',)\n"})

    def test_a_homemade_sealing_decorator_gates_nothing(self):
        # red-before (L1F2-R1): on 141f74c5 both were clean markers and excepted a real failure on every platform; the
        # testX.py file escapes test_sealing_gate's test_*.py closure, the call form escapes its Name/Attribute match
        seal = _call(category="'sealing'", platforms="['linux', 'darwin', 'windows']")
        for rel, defn, deco in (("tests/v9/testproduct.py", "def sealing(test):\n    return test\n", "sealing"),
                                ("tests/v9/test_product.py", "def sealing():\n    return lambda test: test\n",
                                 "sealing()")):
            source = ("import unittest\nfrom validation.qualification.test_markers import marker\n\n\n" + defn
                      + f"\n\nclass T(unittest.TestCase):\n    @{deco}\n    @{seal}\n    def test_x(self):\n"
                      "        self.fail('PRODUCT DEFECT')\n")
            with self.subTest(file=rel):
                markers, problems = _collect(HEAD, {rel: source})
                self.assertTrue(any("the @sealing gate does not carry" in p for p in problems), problems)
                failing = {m.test for m in markers}
                self.assertEqual(len(failing), 1)
                for token in ("linux", "darwin", "windows"):
                    d = rq.decide("2.3.0", failing, {}, token, markers, problems, {"v9.test_fix.Pos.test_positive"})
                    self.assertEqual((d["qualification"], d["unexpected"]), ("FAIL", sorted(failing)), token)

    def test_the_gated_list_is_read_from_the_source_exactly(self):
        from tests.v2 import sealing_gate
        self.assertEqual(tm.gated_ids(), frozenset(sealing_gate.GATED))
        with tempfile.TemporaryDirectory() as d:                         # no list: every sealing marker is refused
            self.assertEqual(tm.gated_ids(pathlib.Path(d)), frozenset())

    def test_the_positive_assertion_is_another_discovered_unmarked_test(self):
        self.assertRefused(_method(_call(positive="'v9.test_fix.Pos.test_missing'")), "positive")
        self.assertRefused(_method(_call(positive="'v9.test_fix.T.test_x'")), "positive")
        both = _method(_call()).replace("    def test_positive(self):",
                                        f"    @{_call(positive=repr('v9.test_fix.T.test_x'))}\n"
                                        "    def test_positive(self):")
        self.assertRefused(both, "positive 'v9.test_fix.Pos.test_positive' must name another")
        undiscovered = {"tests/v9/nopkg/test_other.py": HEAD}   # no __init__.py: unittest never runs it
        self.assertRefused(_method(_call(positive="'v9.nopkg.test_other.Pos.test_positive'")), "positive",
                           undiscovered)

    def test_a_marker_off_a_test_method_or_twice_on_one_is_refused(self):
        on_class = HEAD + f"@{_call()}\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n"
        helper = HEAD + f"class T(unittest.TestCase):\n    @{_call()}\n    def helper(self):\n        pass\n"
        function = HEAD + f"@{_call()}\ndef test_x():\n    pass\n"
        nested = HEAD + (f"class T(unittest.TestCase):\n    class Inner(unittest.TestCase):\n        @{_call()}\n"
                         "        def test_x(self):\n            pass\n")
        for source in (on_class, helper, function, nested):
            with self.subTest(source=source.splitlines()[-3]):
                self.assertRefused(source, "a marker must decorate a test method of a top-level class")
        self.assertRefused(_method(_call(), extra=f"@{_call()}\n    "), "more than one marker")

    def test_an_unreadable_test_file_is_a_problem(self):
        self.assertRefused("def (:\n", "cannot be read for markers")

    def test_the_live_tree_has_no_refused_marker(self):
        markers, problems = tm.collect()
        self.assertEqual(problems, [])
        self.assertTrue(all(m.category in tm.CATEGORIES for m in markers))

    def test_the_checklist_ids_are_the_master_checklist_rows(self):
        ids = tm.checklist_ids()
        self.assertEqual(len(ids), 147)                     # MASTER-CHECKLIST.md "147 unique IDs"
        self.assertTrue({"F2", "F5", "V21-36", "EVID-COUPLING-01"} <= ids)


X, P = "v9.t.T.test_x", "v9.t.Pos.test_p"
M = tm.Marker(test=X, category="platform-harness", id="F2", reason="r", platforms=("windows",), positive=P,
              where="tests/v9/t.py:5")
S = tm.Marker(test=X, category="sealing", id="F2", reason="r", platforms=("darwin", "linux", "windows"),
              positive=P, where="tests/v9/t.py:5")


class Decide(unittest.TestCase):
    def q(self, *args, **kw) -> dict:
        return rq.decide(*args, **kw)

    def test_an_unmarked_exception_is_a_blocker_after_2_1_0(self):
        # red-before: the base decide honoured a hand-authored allowlist for its own version (PASS for both)
        for version in ("2.3.0", "2.2.0"):
            hand = {"version": version, "exceptions": [
                {"test": X, "category": "platform-harness", "platforms": ["windows"], "reason": "r"}]}
            with self.subTest(version=version):
                for failing in ({X}, set()):
                    d = self.q(version, failing, hand, "windows", [M], [], {P})
                    self.assertEqual(d["qualification"], "FAIL")
                    self.assertTrue(any(p.startswith("unmarked exception") for p in d["problems"]), d["problems"])

    def test_a_marker_excepts_its_failure_only_where_it_is_declared(self):
        d = self.q("2.3.0", {X, f"{X} (n=1)"}, {}, "windows", [M], [], {P})
        self.assertEqual((d["qualification"], d["exception_source"], d["excepted_and_observed"]),
                         ("PASS", "markers", [X]))
        self.assertEqual(d["exceptions"][0]["id"], "F2")
        self.assertEqual(self.q("2.3.0", {X}, {}, "linux", [M], [], {P})["unexpected"], [X])
        self.assertEqual(self.q("2.3.0", {X, "v9.t.T.test_y"}, {}, "windows", [M], [], {P})["qualification"],
                         "FAIL")
        self.assertEqual(self.q("2.3.0.dev0", {X}, {}, "windows", [M], [], {P})["qualification"], "PASS")

    def test_the_positive_assertion_must_have_passed_in_the_same_run(self):
        d = self.q("2.3.0", {X}, {}, "windows", [M], [], set())
        self.assertEqual(d["qualification"], "FAIL")
        self.assertIn(f"positive assertion {P} of the excepted {X} did not pass in this run", d["problems"])
        self.assertEqual(self.q("2.3.0", set(), {}, "windows", [M], [], set())["qualification"], "PASS")

    def test_a_refused_marker_blocks_even_without_a_failure(self):
        d = self.q("2.3.0", set(), {}, "windows", [], ["tests/v9/t.py:5: v9.t.T.test_x: the reason is empty"], set())
        self.assertEqual(d["qualification"], "FAIL")
        self.assertTrue(d["problems"][0].startswith("test marker refused: "))

    def test_a_sealing_marker_never_excepts_a_failure(self):
        # red-before (L1F2-R1): on 141f74c5 a sealing marker excepted its test on every platform outside a sealing run
        for token in ("linux", "darwin", "windows"):
            with self.subTest(token=token):
                d = self.q("2.3.0", {X}, {}, token, [S], [], {P})
                self.assertEqual((d["qualification"], d["unexpected"], d["exceptions"]), ("FAIL", [X], []))

    def test_the_v2_2_rule_is_unchanged_below_2_3_no_exception_at_all(self):
        for version in ("2.2.0", "2.2.1", "2.1.1", "2.0.0", "dev"):
            with self.subTest(version=version):
                d = self.q(version, {X}, {}, "windows", [M], [], {P})
                self.assertEqual((d["qualification"], d["exception_source"], d["unexpected"]), ("FAIL", "none", [X]))
                self.assertEqual(self.q(version, set(), {}, "windows", [M], ["refused"], {P})["qualification"],
                                 "PASS")

    def test_markers_apply_from_2_3_on(self):
        for v, want in (("2.3.0", True), ("2.3.0.dev0", True), ("2.10.1", True), ("3.0", True),
                        ("2.2.9", False), ("2.1.0", False), ("", False), ("v2.3.0", False)):
            self.assertIs(rq.markers_apply(v), want, v)

    def test_the_2_1_0_history_allowlist_is_decided_as_before_and_ignores_markers(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rq._selftest()
        real = json.loads((ROOT / rq.allowlist_rel("2.1.0")).read_text(encoding="utf-8"))
        for token in ("linux", "darwin", "windows"):
            with self.subTest(token=token):
                listed = {e["test"] for e in real["exceptions"] if token in e["platforms"]}
                d = self.q("2.1.0", listed, real, token, [M], ["refused"], set())
                self.assertEqual((d["exception_source"], d["unexpected"], d["excepted_and_observed"]),
                                 ("allowlist", [], sorted(listed)))
                self.assertEqual(self.q("2.1.0", {X}, real, token, [M], [], {P})["unexpected"], [X])

    def test_no_hand_authored_allowlist_exists_for_any_other_version(self):
        found = sorted(p.name for p in (ROOT / "closure-evidence/v2/release").glob("V*-QUALIFICATION-ALLOWLIST.json"))
        self.assertEqual(found, ["V2.1.0-QUALIFICATION-ALLOWLIST.json"])


class RunResult(unittest.TestCase):
    def test_passed_holds_only_tests_that_ran_to_the_end_and_passed(self):
        class Case(unittest.TestCase):
            def test_ok(self):
                pass

            def test_bad_subtest(self):
                for n in (1, 2):
                    with self.subTest(n=n):
                        self.assertEqual(n, 1)

            @unittest.skip("x")
            def test_skipped(self):
                pass

            def test_error(self):
                raise RuntimeError

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Case)
        res = unittest.TextTestRunner(stream=io.StringIO(), resultclass=rq.Result).run(suite)
        self.assertEqual(res.passed, {f"{Case.__module__}.{Case.__qualname__}.test_ok"})


if __name__ == "__main__":
    unittest.main()
