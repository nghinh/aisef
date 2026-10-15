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
classifier answers None for any `streams` that is not a list of distinct names and `verify` answers UNVERIFIABLE.

Four more of the same family, found by the two independent reviews of this lane (the lane's own sweep had replaced the
probe by a sentinel, so it never reached the verdict-time reads), each reproduced before it was fixed:

3. `json_equal` over a stream. `cli_invocation._equal` parses both streams of the CANDIDATE with `json.loads` and
compares the documents; it caught `ValueError` only. A document nested past the parser's depth (`RecursionError`:
~1,000 levels on 3.11, ~10,000 on 3.12 and 3.13) or parsed but too deep to compare (3.14 read 12,000 levels and gave
"Stack overflow in comparison" at 50,000) was an exception out of the probe — the story REFUSED. What is not a document this
comparator can read is not equal, the rule the same line already states for text that is not JSON; and a candidate
that nests its output does not make the comparison undecidable (UNVERIFIABLE would be exactly that lever).

4. A returned value in the controller. `python_callable_v2._watch` reads the controller's RESULT with `json.loads` in
the PARENT, whose recursion budget is the caller's stack away from the limit: a value the subject's own process and the
controller could write (they run shallow) is unreadable here on 3.11 for a window of ~20 levels below the limit, a
window that moves with the caller's depth (measured on 3.11.15: 960-985 levels from 40 frames deeper, none from 0).
The same value is REFUTED from a shallower caller (it is not what any expectation states, and a value its own process
could not serialise is `unserializable`, REFUTED), so it is REFUTED here: a verdict never depends on the caller's depth.

5. A `regex` shape that is not a pattern. `_stream_shape_ok` accepted any string; `re.search` then raised `re.error` at
verdict time (`"("`, `"["`), an `OverflowError` (a repetition past the engine's) or a `RecursionError` (groups nested
past the compiler's) out of the probe. A pattern `re.compile` does not take gives the observation no meaning at
classification: UNVERIFIABLE, "gives the reproducer's observation no meaning".

6. A `within_s` that is an integer no float holds (400 digits). `window_of` of the Cycle-1 probe, which every probe
shares or copies, asks `math.isfinite` of it: `OverflowError` out of the classifier. The Cycle-1 file is immutable, so
the caller that hands a model's reproducer to a probe's classifier answers it: no meaning, UNVERIFIABLE. The same
guard answers `file_artifact`'s grep pattern, whose own check catches `re.error` only (`a{4294967296}`:
`OverflowError`; 2,000 nested groups: `RecursionError`) and whose file is another lane's."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, ControlProjection  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K  # noqa: E402
from aisef2.probe.protocol import RevisionRef  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2 import test_c2_cli_invocation as CI  # noqa: E402
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


class AJsonDocumentTheParserCannotTake(unittest.TestCase):
    """`json_equal` over the candidate's streams: a document nested past what can be parsed or compared is not equal."""

    @staticmethod
    def deep(levels: int) -> bytes:
        return ("[" * levels + "]" * levels + "\n").encode()

    def test_a_document_the_parser_gives_up_on_is_not_equal_and_never_an_exception(self):
        gives_up = mock.Mock(side_effect=RecursionError("maximum recursion depth exceeded while decoding a JSON array"))
        with mock.patch.object(ci.json, "loads", gives_up):
            self.assertIs(ci._equal(b"[]", b"[]", "json_equal"), False)
            self.assertEqual(gives_up.call_count, 1)    # the first document was the one it gave up on
            self.assertIs(ci._equal(b"[]", b"[]", "bytes_equal"), True)     # the other comparator never parses
            self.assertEqual(gives_up.call_count, 1)

    def test_two_documents_parsed_but_too_deep_to_compare_are_not_equal_and_never_an_exception(self):
        class TooDeepToCompare:      # CPython 3.14: "RecursionError: Stack overflow in comparison"
            def __eq__(self, other):
                raise RecursionError("Stack overflow in comparison")

        with mock.patch.object(ci.json, "loads", lambda text: TooDeepToCompare()):
            self.assertIs(ci._equal(b"[]", b"[]", "json_equal"), False)

    def test_a_real_document_nested_12000_levels_is_equal_or_not_never_an_exception(self):
        """The parser reads it (3.14) or gives up (3.11-3.13); the answer is a bool either way."""
        deep = self.deep(12_000)
        self.assertIn(ci._equal(deep, deep, "json_equal"), (True, False))

    def test_the_documents_the_parser_can_read_are_compared_as_before(self):
        for a, b, same in ((b'{"a": [1]}', b'{ "a" : [ 1 ] }', True), (b'{"a": 1}', b'{"a": 2}', False),
                           (b"x", b"x", False), (b"\xff", b"\xff", False), (self.deep(500), self.deep(500), True),
                           (self.deep(500), self.deep(501), False)):
            with self.subTest(a=a[:20], b=b[:20]):
                self.assertIs(ci._equal(a, b, "json_equal"), same)

    def test_a_candidate_that_prints_one_is_decided_by_the_probe(self):
        """On the product path: the facts of both invocations, then the comparison — 50,000 levels is past every
        supported parser (3.11-3.13) or comparison (3.14)."""
        product = CI.checkout({"eq/__init__.py": "",
                               "eq/__main__.py": "import sys\nsys.stdout.write('[' * 50000 + ']' * 50000 + '\\n')\n"})
        side = {"argv": []}
        s = ProductProofSpec.create(
            contract_id="BC-EQ", probe_id=CI.P.id, probe_digest=CI.P.digest,
            probe_input={"subject": {"kind": "cli_invocation", "locator": "eq:__main__"}, "stimulus": {},
                         "observable": {"equality": {"stimulus_a": side, "stimulus_b": side, "normalization": {},
                                                     "comparator": "json_equal"},
                                        "streams": ["stdout"], "within_s": 20},
                         "subject_absence": "REQUIRES_SUBJECT"},
            candidate_expectation=S, compiler_id="test", compiler_digest="c" * 64)
        o = CI.P.observe(s, RevisionRef(CI.SHA, product), CI.env())
        self.assertEqual(o.kind, K.OBSERVED, o.detail)
        self.assertIn(o.verdict, (S, R))


class AnAnswerThisProcessCannotRead(unittest.TestCase):
    """`python_callable_v2._watch`: the controller's RESULT, read in the parent, nested past what the parent reads."""

    @classmethod
    def setUpClass(cls):
        cls.product = RevisionRef(T.SHA, T.checkout({"app/__init__.py": "",
                                                     "app/deep.py": "def deep():\n    v = []\n    for _ in range(300):\n"
                                                                    "        v = [v]\n    return v\n\n\n"
                                                                    "def echo(x):\n    return x\n"}))

    def unreadable(self, marker: str):
        """A `json.loads` that raises exactly what an interpreter's does for the one document holding `marker`."""
        real = json.loads

        def loads(text, *a, **k):
            if marker in text:
                raise RecursionError("maximum recursion depth exceeded while decoding a JSON array from a unicode string")
            return real(text, *a, **k)
        return mock.patch.object(pc2.json, "loads", loads)

    def test_a_value_the_controller_wrote_and_this_process_cannot_read_is_REFUTED(self):
        s = T.spec("app.deep:deep", {"returns": []})
        with self.unreadable("[[[[["):
            o = T.P.observe(s, self.product, T.env())
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        self.assertIn("nests deeper", o.detail)
        with self.unreadable("[[[[["):
            self.assertEqual(T.run_probe(T.P, s, self.product, T.env()).result, Executed(R))

    def test_the_same_value_is_REFUTED_when_it_is_read(self):
        """The verdict does not depend on the caller's depth: the readable case says the same."""
        s = T.spec("app.deep:deep", {"returns": []})
        self.assertEqual(T.run_probe(T.P, s, self.product, T.env()).result, Executed(R))

    def test_an_answer_the_parent_reads_is_decided_as_before(self):
        s = T.spec("app.deep:echo", {"returns": [1, [2]]}, {"args": [[1, [2]]]})
        with self.unreadable("[[[[["):      # nothing here is nested: the patched reader reads it
            self.assertEqual(T.run_probe(T.P, s, self.product, T.env()).result, Executed(S))


class ARegexThatIsNotAPattern(unittest.TestCase):

    #: what `re.compile` refuses, by the exception it uses: re.error (PatternError from 3.13), OverflowError (a
    #: repetition count past the engine's), RecursionError (groups nested past the compiler's)
    BAD = ("(", "[", "a{2,1}", "(?P=n)", "\\", "(?z)", "a{4294967296}", "(" * 2000 + "a" + ")" * 2000)

    @staticmethod
    def obs(**streams):
        return {"exit_code": 0, **streams, "within_s": 5}

    def test_a_pattern_re_takes_gives_the_class(self):
        for rx in ("hel+o", "^ok$", "(a+)b", "a{2,3}", ".*", "[0-9]+"):
            with self.subTest(rx=rx):
                self.assertEqual(ci.observation_class(self.obs(stdout={"regex": rx}), {"argv": []}), "exits_streams")

    def test_a_pattern_re_does_not_take_gives_no_class_on_either_stream(self):
        for rx in self.BAD:
            for stream in ("stdout", "stderr"):
                with self.subTest(rx=rx[:12], stream=stream):
                    self.assertIsNone(ci.observation_class(self.obs(**{stream: {"regex": rx}}), {"argv": []}))

    def test_a_non_string_pattern_is_still_no_class(self):
        for rx in (None, 3, ["a"], {"a": 1}, True):
            with self.subTest(rx=rx):
                self.assertIsNone(ci.observation_class(self.obs(stdout={"regex": rx}), {"argv": []}))

    def test_verify_answers_a_reason_not_an_exception(self):
        for rx in self.BAD:
            f = {"id": "F-RX", "severity": "high", "summary": "s", "reproducer": {
                "clause": "R-9/3", "subject": {"kind": "cli_invocation", "locator": "ledgerlock:__main__"},
                "stimulus": {"argv": []}, "observable": self.obs(stdout={"regex": rx})}}
            with self.subTest(rx=rx[:12]):
                v = V.verify(f, requirements={"R-9": object()}, product_roots=("ledgerlock",),
                             root="/nonexistent-rv1", revision="0" * 40, timeout_s=5, interpreter=sys.executable)
                self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, "probe.cli_invocation", None))
                self.assertIn("no meaning", v.reason)


class AGrepPatternOfTheFileArtifactProbe(unittest.TestCase):
    """The probe's own `_compiles` catches `re.error` only (its file belongs to another lane of this window): a pattern
    `re.compile` fails on with `OverflowError` or `RecursionError` ends its classifier in an exception. The caller of
    every probe's classifier answers it, so the review is safe whichever way that file is fixed."""

    def verify(self, grep):
        f = {"id": "F-G", "severity": "high", "summary": "s", "reproducer": {
            "clause": "R-9/3", "subject": {"kind": "file_artifact", "locator": "path:ledgerlock"},
            "stimulus": {"grep": grep, "suffixes": [".py"]}, "observable": {"matches": 0, "within_s": 5}}}
        return V.verify(f, requirements={"R-9": object()}, product_roots=("ledgerlock",), root="/nonexistent-rv1",
                        revision="0" * 40, timeout_s=5, interpreter=sys.executable)

    def test_a_pattern_re_cannot_take_is_no_meaning(self):
        for grep in ("(", "[", "a{4294967296}", "(" * 2000 + "a" + ")" * 2000):
            with self.subTest(grep=grep[:12]):
                v = self.verify(grep)
                self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, "probe.file_artifact", None))
                self.assertIn("no meaning", v.reason)

    def test_a_pattern_re_takes_is_given_a_meaning(self):
        v = self.verify("^import telemetry\\b")
        self.assertEqual(v.status, V.UNVERIFIABLE)
        self.assertNotIn("no meaning", v.reason)      # it stops at the calibration or the checkout that does not exist


class AWindowNoFloatHolds(unittest.TestCase):
    """`within_s` as an integer of 400 digits: `math.isfinite` of it raises in the Cycle-1 `window_of`."""

    REPRODUCERS = {
        "probe.cli_invocation": ({"kind": "cli_invocation", "locator": "ledgerlock:__main__"}, {"argv": []},
                                 {"exit_code": 0}),
        "probe.python_callable_v2": ({"kind": "python_callable", "locator": "ledgerlock.core:total"}, {},
                                     {"returns": 5}),
        "probe.process_effect": ({"kind": "process_effect", "locator": "ledgerlock.core:Tally"},
                                 {"scenario": [{"step": "construct", "args": ["<ws>/t.jsonl"], "kwargs": {}},
                                               {"step": "call", "method": "add", "args": ["a", 2], "kwargs": {}}]},
                                 {"returns": 5}),
        "probe.file_artifact": ({"kind": "file_artifact", "locator": "path:ledgerlock/data.txt"}, {},
                                {"condition": "exists"}),
    }

    def verify(self, subject, stimulus, observable, within_s):
        f = {"id": "F-W", "severity": "high", "summary": "s", "reproducer": {
            "clause": "R-9/3", "subject": subject, "stimulus": stimulus, "observable": {**observable, "within_s": within_s}}}
        return V.verify(f, requirements={"R-9": object()}, product_roots=("ledgerlock",), root="/nonexistent-rv1",
                        revision="0" * 40, timeout_s=5, interpreter=sys.executable)

    def test_every_probe_kind_answers_no_meaning(self):
        for probe_id, (subject, stimulus, observable) in self.REPRODUCERS.items():
            for within_s in (10 ** 400, -(10 ** 400)):
                with self.subTest(probe=probe_id, negative=within_s < 0):
                    v = self.verify(subject, stimulus, observable, within_s)
                    self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, probe_id, None))
                    self.assertIn("no meaning", v.reason)

    def test_a_window_that_is_a_number_is_still_given_a_meaning(self):
        """The control: the same reproducers with an ordinary window are not refused for it (they stop later — the
        calibration, or the checkout that does not exist)."""
        for probe_id, (subject, stimulus, observable) in self.REPRODUCERS.items():
            with self.subTest(probe=probe_id):
                v = self.verify(subject, stimulus, observable, 10)
                self.assertEqual(v.status, V.UNVERIFIABLE)
                self.assertNotIn("no meaning", v.reason)


class ReviewsOverReproducersTheProbesCannotTake(unittest.TestCase):
    """Through `Reviewer.review`: such a reproducer is a typed, non-blocking row and the review completes."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        e2e.make_repo(self.tmp / "repo")
        project = bundle.load(e2e.project_bundle("a" * 40))
        run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 1}}
                                    if proj is ControlProjection.STORY_STATE else None)
        self.rev = ad.Reviewer(run, project, self.tmp / "logs", {}, 5,
                               review={"policy": "fix-loop", "min_severity": "low", "finder": "model", "ocr": None,
                                       "given": True})
        self.scope = types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))

    def review(self, found: list):
        with mock.patch.object(self.rev, "_model", return_value=(found, {"parsed": True}, None)):
            return self.rev.review(self.scope, ("C-ADD",))

    def test_each_is_a_row_and_the_others_are_still_reviewed(self):
        calc = {"kind": "python_callable", "locator": "app.calc:add"}
        main = {"kind": "cli_invocation", "locator": "app:__main__"}
        found = [
            {"id": "F-RX", "severity": "critical", "summary": "a regex that is not one", "reproducer": {
                "clause": "R-ADD/1.1", "subject": main, "stimulus": {"argv": []},
                "observable": {"exit_code": 0, "stdout": {"regex": "("}, "within_s": 10}}},
            {"id": "F-W", "severity": "critical", "summary": "a window of 400 digits", "reproducer": {
                "clause": "R-ADD/1.1", "subject": calc, "stimulus": {"args": [2, 3]},
                "observable": {"returns": 5, "within_s": 10 ** 400}}},
            {"id": "F-OK", "severity": "low", "summary": "no reproducer"},
        ]
        r = self.review(found)
        self.assertEqual(r.outcome.value, "COMPLETED")
        self.assertEqual([(f.id, f.blocks) for f in r.findings], [("F-RX", False), ("F-W", False), ("F-OK", False)])
        for row in r.findings[:2]:
            stated = json.loads(row.detail)
            self.assertEqual(stated["verification"], V.UNVERIFIABLE)
            self.assertIn("no meaning", stated["why"])


if __name__ == "__main__":
    unittest.main()
