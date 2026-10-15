"""V2.1 (owner's fix window of 2026-10-15, the family of RV-1): data a model wrote — the candidate's values, a
reviewer's reproducer — that a probe's reading of it cannot take is a verdict or a reason, never an exception out of the
probe (an exception reaches app/run.py and the story is REFUSED).

Two cases, both measured on the parent of this window (CPython 3.12.14 and 3.14.7) by running every request of the
calibration fixtures with each of its values replaced in turn by 15 odd JSON values (5,046 reproducers through
`review_verify.verify`; the probe's run replaced by a sentinel): exactly two exception shapes, one case.

1. A value the candidate returns or raises, nested deeper than the interpreter's recursion limit.
`probe.python_callable_v2` reads the subject's answer in its controller process and gives every occurrence of the
workspace path in it back as `<ws>` before comparing (`_unsubstituted`). That walk was recursive: a candidate whose
function returned a list nested ~1,100 levels (a cons list, a parse tree — the subject's own value, never the
reviewer's or the spec's) ended `run_probe` in a `RecursionError`, which no layer between the probe and `app/run.py`
catches: the story REFUSED, no verdict, the developer's retry never offered (measured from 1,100 levels; 500 was fine).
Nothing about the verdict is in question: the module's own rules decide a returned value that is not the expected one
(REFUTED), and a value whose serialisation raises anything is already `unserializable` (REFUTED) — the walk only has to
reach the facts. The recursion limit is never raised; the walk keeps its own stack.

2. A reproducer whose `streams` holds an entry that is not a name (`[["stdout"]]`, `[{"a": 1}]`): `cli_invocation`'s
classifier built a set of the entries, and a list or a dict is unhashable — a `TypeError` out of `observation_class`,
whose contract is "the class, or None when this probe cannot give it a meaning". A set of a model's JSON is the only
place where code hashes data the model shaped: JSON lists and dicts are unhashable (never a deep hash) and the nested
tuples the contract's `freeze` makes are bounded by its own recursion (~494 levels), so `hash()` of a nested structure
the code built has no path from a model.

Pinned: the verdict of a deeply nested returned value and of a deeply nested attribute of a raised exception; the
control — the same walk still giving `<ws>` back at depth and keeping the facts' key order; and, for 2, that the
classifier answers None for any `streams` that is not a list of distinct names and `verify` answers UNVERIFIABLE."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.protocol import RevisionRef  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from tests.v2 import test_python_callable_v2 as T  # noqa: E402 — the module: its tests are not collected again

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
#: deeper than the recursion limit of every supported interpreter (1,000), and than what a spec's own walks admit
DEEP = 1500
PRODUCT = {
    "app/__init__.py": "",
    "app/deep.py": (
        f"N = {DEEP}\n\n\ndef nest(n, leaf):\n    v = leaf\n    for _ in range(n):\n        v = [v]\n    return v\n\n\n"
        "def deep():\n    return nest(N, 'x')\n\n\n"
        "def shallow():\n    return nest(50, 'x')\n\n\n"
        "class Deep(Exception):\n    def __init__(self):\n        super().__init__('deep')\n        self.payload = nest(N, 'x')\n\n\n"
        "def boom():\n    raise Deep()\n\n\n"
        "def echo(path):\n    return nest(300, {'path': path, 'again': [path]})\n"),
}


def nested(n: int, leaf):
    v = leaf
    for _ in range(n):
        v = [v]
    return v


class DeepValuesAreVerdicts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.product = RevisionRef(T.SHA, T.checkout(PRODUCT))

    def run_(self, s):
        return T.run_probe(T.P, s, self.product, T.env()).result

    def test_a_returned_value_nested_past_the_recursion_limit_is_REFUTED_not_an_exception(self):
        self.assertEqual(self.run_(T.spec("app.deep:deep", {"returns": []})), Executed(R))
        self.assertEqual(self.run_(T.spec("app.deep:deep", {"returns": nested(40, "x")})), Executed(R))

    def test_a_raised_exceptions_attribute_nested_past_the_limit_is_REFUTED_not_an_exception(self):
        s = T.spec("app.deep:boom", {"raises": "Deep", "attrs": {"payload": []}})
        self.assertEqual(self.run_(s), Executed(R))
        self.assertEqual(self.run_(T.spec("app.deep:boom", {"raises": "Deep"})), Executed(S))     # the exception itself

    def test_a_value_the_walk_could_always_reach_is_unchanged(self):
        self.assertEqual(self.run_(T.spec("app.deep:shallow", {"returns": nested(50, "x")})), Executed(S))
        self.assertEqual(self.run_(T.spec("app.deep:shallow", {"returns": nested(49, "x")})), Executed(R))

    def test_the_workspace_path_is_still_given_back_as_the_placeholder_at_depth_and_the_keys_keep_their_order(self):
        seen = T.P.observe(T.spec("app.deep:echo", {"returns": 0}, {"args": ["<ws>/x"]}), self.product, T.env())
        facts = pc2.json.loads(seen.detail)
        v = facts["returned"]
        for _ in range(300):
            v = v[0]
        self.assertEqual(list(v), ["path", "again"])
        self.assertEqual((v["path"], v["again"]), ("<ws>/x", ["<ws>/x"]))

    def test_the_walk_itself_has_no_recursion_to_meet(self):
        deep = nested(20_000, {"a": "/w/x", "b": ["/w/x"]})
        out = pc2._unsubstituted(deep, "/w")
        for _ in range(20_000):
            out = out[0]
        self.assertEqual(out, {"a": "<ws>/x", "b": ["<ws>/x"]})

    def test_what_is_not_a_string_a_list_or_a_mapping_is_returned_as_it_is(self):
        facts = {"z": 1, "a": [None, True, 2.5, "q"]}
        self.assertEqual(pc2._unsubstituted(facts, "/w"), facts)
        self.assertEqual(list(pc2._unsubstituted(facts, "/w")), ["z", "a"])


class StreamsThatAreNotNames(unittest.TestCase):

    FIXTURE = ROOT / "tests" / "v2" / "fixtures" / "calibration" / "cli_invocation" / "equality" / "positive" / "request.json"

    def request(self, streams) -> dict:
        r = json.loads(self.FIXTURE.read_text(encoding="utf-8"))
        r["observable"]["streams"] = streams
        return r

    def test_the_fixtures_own_streams_are_the_equality_class(self):
        for streams in (["stdout"], ["stdout", "stderr"]):
            r = self.request(streams)
            self.assertEqual(ci.observation_class(r["observable"], r["stimulus"]), "equality")

    def test_an_entry_that_is_not_a_name_gives_no_class_and_never_an_exception(self):
        for streams in ([["stdout"]], [{"a": 1}], ["stdout", ["stderr"]], [[]], [{}], "stdout", [], ["stdout", "stdout"],
                        [None], [1], ["stdin"]):
            with self.subTest(streams=streams):
                r = self.request(streams)
                self.assertIsNone(ci.observation_class(r["observable"], r["stimulus"]))

    def test_verify_answers_a_reason_for_such_a_reproducer(self):
        for streams in ([["stdout"]], [{"a": 1}]):
            r = self.request(streams)
            f = {"id": "F-1", "severity": "high", "summary": "s", "reproducer": {
                "clause": "R-9/3", "subject": {"kind": "cli_invocation", "locator": "ledgerlock:__main__"},
                "stimulus": r["stimulus"], "observable": r["observable"]}}
            with self.subTest(streams=streams):
                v = V.verify(f, requirements={"R-9": object()}, product_roots=("ledgerlock",), root="/nonexistent-rv1",
                             revision="0" * 40, timeout_s=5, interpreter=sys.executable)
                self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, "probe.cli_invocation", None))
                self.assertIn("no meaning", v.reason)


if __name__ == "__main__":
    unittest.main()
