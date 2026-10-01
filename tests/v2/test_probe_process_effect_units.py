"""WP-2.3.1 — the `process_effect` probe in-process: the closed step vocabulary and its typed shapes, the scenario
rules, the observation classes, the class table on fixture facts (every row, DECISION-1), the file observables, the
placeholder substitution and the request layout, and the parent's decision table over test doubles of the owned range
(the marker-file lines the child would write, how the process ended, what the controller signalled). No subprocess
but the digest check: the mutation runner lists this module first, so a mutant of a parent-side function dies here in
a second and only a survivor pays for tests/v2/test_probe_process_effect.py (the real subjects).
"""

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, ProbeExecutionStatus, SubjectAbsence  # noqa: E402
from aisef2.probe import cli_invocation as ci, process_effect as pe  # noqa: E402
from aisef2.probe.process_effect import ProcessEffectProbe  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, Observation, ObservationKind as K, ProbeInterrupted, RevisionRef, run_probe,
)
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2.test_c2_cli_invocation import FakeRange  # noqa: E402

P = ProcessEffectProbe()
S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
SHA = "89abcdef0123456789abcdef0123456789abcdef"
BOOK = "<ws>/book.jsonl"
CALL = {"step": "call", "args": [], "kwargs": {}}
NEW = {"step": "construct", "args": [BOOK], "kwargs": {}}
#: one minimal valid step per kind of the vocabulary
MINIMAL = {
    "workspace": {"step": "workspace", "files": {"a.txt": {"text": ""}}},
    "construct": NEW,
    "call": CALL,
    "expect_raises": {"step": "expect_raises", "args": [], "kwargs": {}, "exception": "ValueError"},
    "write": {"step": "write", "path": BOOK, "text": ""},
    "edit_jsonl": {"step": "edit_jsonl", "path": BOOK, "line": 0, "field": "k", "value": None},
    "subprocess": {"step": "subprocess", "argv": ["-m", "store"]},
    "fault": {"step": "fault", "fault": "os.replace"},
}


def spec(scenario, observable, *, locator="store.book:Book", window=10, kind="process_effect"):
    observable = dict(observable)
    if window is not None:
        observable.setdefault("within_s", window)
    return ProductProofSpec.create(
        contract_id="BC-EFFECT-UNIT", probe_id=P.id, probe_digest=P.digest,
        probe_input={"subject": {"kind": kind, "locator": locator}, "stimulus": {"scenario": scenario},
                     "observable": observable, "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
        candidate_expectation=S, compiler_id="test", compiler_digest="c" * 64)


def cls_of(scenario, observable, window=10):
    return pe.observation_class({**observable, "within_s": window} if window else observable, {"scenario": scenario})


def env(interpreter=sys.executable, timeout=20):
    return ExecutionEnv(interpreter, timeout, Enforcement.PARTIAL)


def faked(*tags, returncode, ledger=(), write=True):
    return mock.patch.object(pe, "ProcessRange", FakeRange(tags, returncode, ledger, write=write))


def never_runs():
    return mock.patch.object(pe, "ProcessRange", side_effect=AssertionError("ran"))


def facts_of(o):
    return json.loads(o.detail)


class _Checkout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = tempfile.TemporaryDirectory(prefix="aisef2-effect-unit-", ignore_cleanup_errors=True)
        cls.addClassCleanup(d.cleanup)
        cls.root = d.name
        pathlib.Path(d.name, "store").mkdir()
        cls.at = RevisionRef(SHA, d.name)

    def see(self, s, e=None, probe=P):
        return probe.observe(s, self.at, e or env())


# --------------------------------------------------------------------------------------- vocabulary and shapes

class Vocabulary(unittest.TestCase):
    def test_the_step_vocabulary_is_closed_and_each_kind_has_exactly_its_typed_fields(self):
        self.assertEqual(tuple(pe.STEPS), ("workspace", "construct", "call", "expect_raises", "write", "edit_jsonl",
                                           "subprocess", "fault"))
        self.assertEqual(set(pe._SHAPES), set(pe.STEPS))
        self.assertEqual(set(MINIMAL), set(pe.STEPS))
        self.assertEqual(pe.FAULTED, ("call", "expect_raises", "subprocess"))
        for kind, step in MINIMAL.items():
            required, optional = pe.STEPS[kind]
            with self.subTest(kind=kind):
                self.assertIs(True, pe._step_ok(step))
                for field in required:
                    self.assertIs(False, pe._step_ok({k: v for k, v in step.items() if k != field}), field)
                self.assertIs(False, pe._step_ok({**step, "extra": 1}))
                self.assertIs(False, pe._step_ok({**step, "step": kind.upper()}))
        for bad in (None, [], "call", {"step": None}, {"step": ["call"]}, {"step": "shell", "argv": []}, {}):
            with self.subTest(bad=bad):
                self.assertIs(False, pe._step_ok(bad))

    def test_every_field_has_one_typed_shape(self):
        good = {
            "call": [{**CALL, "method": "m", "as": "r1"}, {"step": "call", "args": [1, [2]], "kwargs": {"k": {"x": 1}}}],
            "expect_raises": [{**MINIMAL["expect_raises"], "method": "m", "attrs": {"key": "k", "index": 1}}],
            "write": [{"step": "write", "path": BOOK, "text": "a\n", "newline": "\r\n", "append": True},
                      {"step": "write", "path": BOOK, "bytes_hex": "00ff", "append": False}],
            "subprocess": [{"step": "subprocess", "argv": ["-m", "store.cli", "x", "<ws>/y"], "expect_exit": 3}],
            "fault": [{"step": "fault", "fault": f} for f in pe.FAULTS],
            "workspace": [{"step": "workspace", "files": {"a.txt": {"bytes_hex": "00"}, "b_1.jsonl": {"text": "x",
                                                                                                    "newline": "\n"}}}],
            "edit_jsonl": [{**MINIMAL["edit_jsonl"], "line": 3, "value": {"any": ["json"]}}],
        }
        bad = {
            "construct": [{**NEW, "args": "x"}, {**NEW, "kwargs": []}, {**NEW, "kwargs": {"1x": 1}}, {**NEW, "method": "m"}],
            "call": [{**CALL, "method": "a.b"}, {**CALL, "method": 1}, {**CALL, "as": "r-1"}, {**CALL, "args": {}},
                     {**CALL, "kwargs": {"a b": 1}}],
            "expect_raises": [{**MINIMAL["expect_raises"], "exception": "Value Error"},
                              {**MINIMAL["expect_raises"], "exception": 1},
                              {**MINIMAL["expect_raises"], "attrs": []}, {**MINIMAL["expect_raises"], "attrs": {"a.b": 1}}],
            "write": [{"step": "write", "path": "book.jsonl", "text": ""}, {"step": "write", "path": "<ws>/a/b", "text": ""},
                      {"step": "write", "path": "<ws>xbook.jsonl", "text": ""}, {"step": "write", "path": "<ws>", "text": ""},
                      {"step": "write", "path": "<ws>/.x", "text": ""}, {"step": "write", "path": BOOK},
                      {"step": "write", "path": BOOK, "text": "", "bytes_hex": "00"},
                      {"step": "write", "path": BOOK, "bytes_hex": "0g"}, {"step": "write", "path": BOOK, "newline": "\n"},
                      {"step": "write", "path": BOOK, "text": "", "append": 1}],
            "edit_jsonl": [{**MINIMAL["edit_jsonl"], "line": -1}, {**MINIMAL["edit_jsonl"], "line": True},
                           {**MINIMAL["edit_jsonl"], "line": 1.0}, {**MINIMAL["edit_jsonl"], "field": ""},
                           {**MINIMAL["edit_jsonl"], "field": 1}, {**MINIMAL["edit_jsonl"], "path": "<ws>"}],
            "subprocess": [{"step": "subprocess", "argv": ["-m"]}, {"step": "subprocess", "argv": ["-c", "x"]},
                           {"step": "subprocess", "argv": ["-m", "a/b"]}, {"step": "subprocess", "argv": ["-m", "x", 1]},
                           {"step": "subprocess", "argv": "-m x"}, {"step": "subprocess", "argv": ["-m", "x"],
                                                                     "expect_exit": "0"},
                           {"step": "subprocess", "argv": ["-m", "x"], "expect_exit": False}],
            "fault": [{"step": "fault", "fault": "os.unlink"}, {"step": "fault", "fault": ["os.replace"]},
                      {"step": "fault", "fault": "OS.REPLACE"}],
            "workspace": [{"step": "workspace", "files": {}}, {"step": "workspace", "files": {"a/b": {"text": ""}}},
                          {"step": "workspace", "files": {"..": {"text": ""}}}, {"step": "workspace", "files": []},
                          {"step": "workspace", "files": {"a": "text"}}],
        }
        for kind, steps in good.items():
            for s in steps:
                with self.subTest(good=s):
                    self.assertIs(True, pe._step_ok(s) and s["step"] == kind)
        for kind, steps in bad.items():
            for s in steps:
                with self.subTest(bad=s):
                    self.assertEqual(s["step"], kind)
                    self.assertIs(False, pe._step_ok(s))

    def test_the_scenario_rules(self):
        ok = [MINIMAL["workspace"], NEW, MINIMAL["fault"], {**CALL, "as": "a"}, MINIMAL["fault"],
              MINIMAL["expect_raises"], MINIMAL["fault"], MINIMAL["subprocess"], {**CALL, "as": "b"}]
        self.assertIs(True, pe._scenario_ok(ok))
        for name, scenario in {
            "empty": [], "not a list": {"0": CALL}, "a bad step": [CALL, {"step": "nope"}],
            "workspace second": [NEW, MINIMAL["workspace"]], "two workspaces": [MINIMAL["workspace"], MINIMAL["workspace"]],
            "two constructs": [NEW, CALL, NEW], "a name bound twice": [{**CALL, "as": "a"}, {**CALL, "as": "a"}],
            "a trailing fault": [CALL, MINIMAL["fault"]], "a fault before a write": [MINIMAL["fault"], MINIMAL["write"], CALL],
            "a fault before a construct": [MINIMAL["fault"], NEW, CALL],
            "two faults": [MINIMAL["fault"], MINIMAL["fault"], CALL],
        }.items():
            with self.subTest(case=name):
                self.assertIs(False, pe._scenario_ok(scenario))
        for kind in pe.FAULTED:
            self.assertIs(True, pe._scenario_ok([MINIMAL["fault"], MINIMAL[kind]]))
        self.assertIs(True, pe._scenario_ok([MINIMAL["workspace"]]))

    def test_the_observation_classes(self):
        calls = [NEW, {**CALL, "method": "a", "as": "r1"}, {**CALL, "as": "r2"}]
        cases = [
            (calls, {"returns": {"ok": True}}, "scenario_returns"), (calls, {"returns": None}, "scenario_returns"),
            (calls, {"returns_bytes_hex": "00FF"}, "scenario_returns"), (calls, {"returns_bytes_hex": ""}, "scenario_returns"),
            (calls, {"returns_name": "r1", "equals_name": "r2"}, "scenario_returns"),
            (calls, {"returns_name": "r1", "equals_name": "r1"}, None), (calls, {"returns_name": "r1", "equals_name": "r3"}, None),
            (calls, {"returns_name": ["r1"], "equals_name": "r2"}, None),
            (calls, {"returns_name": "r1"}, None), (calls, {"returns_bytes_hex": "0"}, None),
            (calls, {"returns_bytes_hex": 1}, None), ([NEW], {"returns": 0}, None), ([NEW], {"returns_bytes_hex": ""}, None),
            (calls, {"returns": 0, "raises": True}, None), (calls, {"raises": True}, None),
            ([NEW, MINIMAL["expect_raises"]], {"raises": True}, "scenario_raises"),
            ([NEW, MINIMAL["expect_raises"]], {"raises": 1}, None), ([NEW, MINIMAL["expect_raises"]], {"raises": False}, None),
            ([NEW, MINIMAL["expect_raises"], CALL], {"raises": True}, None),
            ([NEW], {"files": {BOOK: {"absent": True}}}, "scenario_files"),
            ([NEW], {"files": {BOOK: {"absent": True}, "<ws>/b": {"line_count": 0}}}, "scenario_files"),
            ([NEW], {"files": {}}, None), ([NEW], {"files": {"book.jsonl": {"absent": True}}}, None),
            ([NEW], {"files": {"<ws>/a/b": {"absent": True}}}, None), ([NEW], {"files": {BOOK: {"prose": "ok"}}}, None),
            ([NEW], {"files": {"<ws>xbook.jsonl": {"absent": True}}}, None),
            ([NEW], {"files": {BOOK: {"absent": True, "line_count": 1}}}, None), ([NEW], {"files": []}, None),
            ([NEW], {"exit_code": 0}, None), ([NEW], {}, None),
        ]
        for scenario, observable, expected in cases:
            with self.subTest(observable=observable, scenario=[s["step"] for s in scenario]):
                self.assertEqual(cls_of(scenario, observable), expected)
        self.assertIsNone(cls_of(calls, {"returns": 0}, window=None))   # no bounded window: no meaning for expiry
        self.assertIsNone(cls_of(calls, {"returns": 0}, window=0))
        self.assertIsNone(pe.observation_class({"returns": 0, "within_s": 1}, {"scenario": calls, "argv": []}))
        self.assertIsNone(pe.observation_class({"returns": 0, "within_s": 1}, {}))
        self.assertIsNone(pe.observation_class({"returns": 0, "within_s": 1}, {"scenario": [{"step": "teleport"}]}))
        # spec_class: the subject kind and the locator shape first
        self.assertEqual(pe.spec_class(spec(calls, {"returns": 0})), "scenario_returns")
        self.assertIsNone(pe.spec_class(spec(calls, {"returns": 0}, kind="python_callable")))
        for locator in ("store/book.py:Book", "store.book", "store.book:Book.append", "store.book:Book()", ":Book"):
            with self.subTest(locator=locator):
                self.assertIsNone(pe.spec_class(spec(calls, {"returns": 0}, locator=locator)))

    def test_the_file_shapes(self):
        self.assertEqual(tuple(pe._FILE_SHAPE_OK), pe.FILE_SHAPES)
        self.assertEqual(tuple(pe._FILE_HOLDS), pe.FILE_SHAPES)
        good = [{"sha256": "0" * 64}, {"equals_before": True}, {"absent": True}, {"line_count": 0}, {"line_count": 7},
                {"final_byte": "\n"}, {"final_byte": "x"}, {"jsonl": {"line": 0, "field": "f", "equals": None}}]
        bad = [{"sha256": "0" * 63}, {"sha256": "G" * 64}, {"equals_before": False}, {"absent": 1}, {"line_count": -1},
               {"line_count": True}, {"final_byte": ""}, {"final_byte": "ab"}, {"final_byte": "é"}, {"final_byte": 10},
               {"jsonl": {"line": 0, "field": "f"}}, {"jsonl": {"line": -1, "field": "f", "equals": 1}},
               {"jsonl": {"line": 0, "field": "", "equals": 1}}, {"jsonl": {"line": "0", "field": "f", "equals": 1}},
               {"jsonl": [0, "f", 1]}, {}, {"text": "x"}, "absent", {"absent": True, "sha256": "0" * 64}]
        for shape in good:
            with self.subTest(good=shape):
                self.assertIs(True, pe._file_shape_ok(shape))
        for shape in bad:
            with self.subTest(bad=shape):
                self.assertIs(False, pe._file_shape_ok(shape))


# --------------------------------------------------------------------------------------- verdicts

#: fixture facts for every row of the class table: (class, row) -> (observable, facts)
DONE = {"subject": "present", "trace": [{"i": 0, "kind": "construct", "outcome": "ok"},
                                         {"i": 1, "kind": "call", "outcome": "ok"}]}
REFUTED_STEP = {**DONE, "refuted": {"step": 1, "kind": "call", "why": "raised ValueError"}}
HARD = {"subject": "present", "hard_exit": True, "exit_code": 0, "trace": [], "refuted": {"step": 1, "why": "ended"}}
RAISED = {"subject": "present", "trace": [DONE["trace"][0], {"i": 1, "kind": "expect_raises", "outcome": "raised:E"}]}
FILE = {"sha256": "a" * 64, "size": 3, "line_count": 1, "final_byte_hex": "0a", "jsonl": {"0": {"k": 1}}}
ROWS = {
    ("scenario_returns", "a step refuted"): ({"returns": 1}, {**REFUTED_STEP, "last_returned": 1}),
    ("scenario_returns", "the process ended during a step"): ({"returns": 1}, {**HARD, "last_returned": 1}),
    ("scenario_returns", "completed, the last call returned the declared value"): ({"returns": {"a": [1, None]}},
                                                                                    {**DONE, "last_returned": {"a": [1, None]}}),
    ("scenario_returns", "completed, the last call returned another value, bytes or an unserializable value"): (
        {"returns": 1}, {**DONE, "last_returned": 2}),
    ("scenario_returns", "completed, the last call returned the declared bytes"): (
        {"returns_bytes_hex": "0A"}, {**DONE, "last_returned_bytes_hex": "0a"}),
    ("scenario_returns", "completed, the two bound results are equal"): (
        {"returns_name": "a", "equals_name": "b"}, {**DONE, "bound": {"a": {"json": [1]}, "b": {"json": [1]}}}),
    ("scenario_returns", "completed, the two bound results differ or one is unserializable"): (
        {"returns_name": "a", "equals_name": "b"}, {**DONE, "bound": {"a": {"json": [1]}, "b": {"json": [2]}}}),
    ("scenario_raises", "a step refuted"): ({"raises": True}, {**RAISED, "refuted": {"step": 0, "why": "x"}}),
    ("scenario_raises", "the process ended during a step"): ({"raises": True}, HARD),
    ("scenario_raises", "completed, the last step raised the declared type with every declared attribute"): (
        {"raises": True}, RAISED),
    ("scenario_files", "a step refuted"): ({"files": {BOOK: {"line_count": 1}}},
                                           {**REFUTED_STEP, "files": {"book.jsonl": FILE}}),
    ("scenario_files", "the process ended during a step"): ({"files": {BOOK: {"absent": True}}}, HARD),
    ("scenario_files", "completed, every named file matches its shape"): (
        {"files": {BOOK: {"line_count": 1}, "<ws>/x": {"absent": True}}},
        {**DONE, "files": {"book.jsonl": FILE, "x": {"absent": True}}}),
    ("scenario_files", "completed, a named file does not match its shape"): (
        {"files": {BOOK: {"line_count": 1}, "<ws>/x": {"absent": True}}},
        {**DONE, "files": {"book.jsonl": FILE, "x": FILE}}),
}


class Verdicts(unittest.TestCase):
    def test_the_class_table_row_by_row_on_fixture_facts(self):
        self.assertEqual(set(pe.CLASS_TABLE), set(pe.CLASSES))
        self.assertEqual(pe.ON_DEADLINE, {c: R for c in pe.CLASSES})
        seen = set()
        for cls, row in pe.CLASS_TABLE.items():
            self.assertIn(row["quantifier"], ci.QUANTIFIERS)
            self.assertEqual((row["quantifier"], row["domain"], row["enforcement"]),
                             ("exhaustive_finite_domain", pe._ONE, "PARTIAL"))
            self.assertEqual({f for f, _ in row["rows"]} - {k[1] for k in ROWS if k[0] == cls}, {"window expired"})
            for facts_name, verdict in row["rows"]:
                with self.subTest(cls=cls, row=facts_name):
                    if facts_name == "window expired":
                        self.assertEqual(pe.ON_DEADLINE[cls].value, verdict)
                        continue
                    observable, facts = ROWS[(cls, facts_name)]
                    self.assertEqual(pe.verdict_of(cls, {**observable, "within_s": 1}, facts).value, verdict)
                    seen.add((cls, facts_name))
        self.assertEqual(seen, set(ROWS))   # every fixture row is a row of the table, and every row has fixture facts

    def test_returns_is_exact_json_equality(self):
        v = pe.verdict_of
        for returned, declared, verdict in ((1, 1, S), (True, 1, R), (1, 1.0, R), (1, True, R), (None, None, S),
                                            ({"a": 1, "b": 2}, {"b": 2, "a": 1}, S), ({"b": 2, "a": 1}, {"a": 1, "b": 2}, S),
                                            ([1, 2], [2, 1], R), ("1", 1, R)):
            with self.subTest(returned=returned, declared=declared):
                self.assertIs(v("scenario_returns", {"returns": declared}, {**DONE, "last_returned": returned}), verdict)
        self.assertIs(v("scenario_returns", {"returns": None}, DONE), R)   # nothing returned is not null
        self.assertIs(v("scenario_returns", {"returns": None}, {**DONE, "last_unserializable": "object"}), R)
        self.assertIs(v("scenario_returns", {"returns_bytes_hex": "ab"}, {**DONE, "last_returned": "ab"}), R)
        eq = {"returns_name": "a", "equals_name": "b"}
        for a, b, verdict in (({"bytes_hex": "00"}, {"bytes_hex": "00"}, S), ({"json": 1}, {"json": True}, R),
                              ({"unserializable": "object"}, {"unserializable": "object"}, R),
                              ({"json": 1}, {"bytes_hex": "01"}, R), (None, None, R), ({"json": 1}, None, R)):
            with self.subTest(a=a, b=b):
                bound = {k: x for k, x in (("a", a), ("b", b)) if x is not None}
                self.assertIs(v("scenario_returns", eq, {**DONE, "bound": bound}), verdict)

    def test_raises_reads_the_last_step_of_the_trace(self):
        v = pe.verdict_of
        self.assertIs(v("scenario_raises", {"raises": True}, RAISED), S)
        for trace in ([], [{"i": 0, "kind": "call", "outcome": "raised:E"}],
                      [{"i": 0, "kind": "expect_raises", "outcome": "ok"}],
                      [{"i": 0, "kind": "expect_raises", "outcome": "raised:E"}, {"i": 1, "kind": "call", "outcome": "ok"}]):
            with self.subTest(trace=trace):
                self.assertIs(v("scenario_raises", {"raises": True}, {"subject": "present", "trace": trace}), R)

    def test_each_file_shape_on_fixture_facts(self):
        before = {"book.jsonl": {"sha256": "a" * 64}, "gone": {"absent": True}, "changed": {"sha256": "b" * 64},
                  "made": {"absent": True}}
        facts = {**DONE, "before": before, "files": {"book.jsonl": FILE, "gone": {"absent": True}, "changed": FILE,
                                                    "made": FILE,
                                                    "empty": {"sha256": "e" * 64, "size": 0, "line_count": 0,
                                                              "final_byte_hex": None, "jsonl": {"0": None}}}}
        cases = [
            ("book.jsonl", {"sha256": "a" * 64}, S), ("book.jsonl", {"sha256": "b" * 64}, R), ("gone", {"sha256": "a" * 64}, R),
            ("book.jsonl", {"equals_before": True}, S), ("gone", {"equals_before": True}, S), ("empty", {"equals_before": True}, R),
            ("changed", {"equals_before": True}, R), ("made", {"equals_before": True}, R),
            ("book.jsonl", {"absent": True}, R), ("gone", {"absent": True}, S), ("nowhere", {"absent": True}, R),
            ("book.jsonl", {"line_count": 1}, S), ("book.jsonl", {"line_count": 2}, R), ("gone", {"line_count": 0}, R),
            ("empty", {"line_count": 0}, S), ("book.jsonl", {"final_byte": "\n"}, S), ("empty", {"final_byte": "\n"}, R),
            ("book.jsonl", {"final_byte": "x"}, R),
            ("book.jsonl", {"jsonl": {"line": 0, "field": "k", "equals": 1}}, S),
            ("book.jsonl", {"jsonl": {"line": 0, "field": "k", "equals": True}}, R),
            ("book.jsonl", {"jsonl": {"line": 0, "field": "j", "equals": None}}, R),
            ("book.jsonl", {"jsonl": {"line": 1, "field": "k", "equals": 1}}, R),
            ("empty", {"jsonl": {"line": 0, "field": "k", "equals": None}}, R),
            ("gone", {"jsonl": {"line": 0, "field": "k", "equals": None}}, R),
        ]
        for name, shape, verdict in cases:
            with self.subTest(name=name, shape=shape):
                self.assertIs(pe.verdict_of("scenario_files", {"files": {f"<ws>/{name}": shape}}, facts), verdict)
        # before a file was recorded there is nothing to equal
        self.assertIs(pe.verdict_of("scenario_files", {"files": {BOOK: {"equals_before": True}}},
                                    {**DONE, "files": {"book.jsonl": FILE}}), R)
        # every named file must hold, not one of them
        both = {"files": {BOOK: {"line_count": 1}, "<ws>/gone": {"absent": True}}}
        self.assertIs(pe.verdict_of("scenario_files", both, facts), S)
        self.assertIs(pe.verdict_of("scenario_files", {"files": {BOOK: {"line_count": 9}, "<ws>/gone": {"absent": True}}},
                                    facts), R)
        self.assertIs(pe.verdict_of("scenario_files", {"files": {BOOK: {"line_count": 1}, "<ws>/gone": {"line_count": 0}}},
                                    facts), R)

    def test_the_conclusion_from_a_RESULT(self):
        self.assertEqual(pe._concluded("scenario_returns", {"returns": 1}, {"subject": "absent", "note": "n"}),
                         Observation(K.SUBJECT_ABSENT, R, "n"))
        self.assertEqual(pe._concluded("scenario_returns", {"returns": 1}, {"subject": "absent"}),
                         Observation(K.SUBJECT_ABSENT, R, ""))
        self.assertEqual(pe._concluded("scenario_returns", {"returns": 1}, {"harness_failure": "leaked"}),
                         Observation(K.HARNESS_FAILED, detail="the harness failed its own scenario: leaked"))
        facts = {**DONE, "last_returned": 1}
        self.assertEqual(pe._concluded("scenario_returns", {"returns": 1}, facts),
                         Observation(K.OBSERVED, S, json.dumps(facts)))
        self.assertEqual(pe._concluded("scenario_returns", {"returns": 2}, facts).verdict, R)


# --------------------------------------------------------------------------------------- placeholder and request

class Request(_Checkout):
    def test_ws_is_substituted_at_the_head_of_strings_only(self):
        ws = os.path.join("/x", "ws")
        cases = [("<ws>", ws), ("<ws>/a", ws + "/a"), ("<ws>/", ws + "/"), ("x<ws>/a", "x<ws>/a"), ("<wsx>", "<wsx>"), ("<ws>x", "<ws>x"),
                 ("<ws", "<ws"), ("<WS>/a", "<WS>/a"), (1, 1), (None, None), (True, True),
                 (["<ws>/a", ["<ws>"]], [ws + "/a", [ws]]), ({"<ws>": "<ws>/k"}, {"<ws>": ws + "/k"})]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(pe._substitute(value, ws), expected)

    def test_each_step_is_resolved_for_the_harness(self):
        ws = "/w/ws"
        self.assertEqual(pe._resolved(MINIMAL["workspace"], ws), {"step": "workspace", "files": {"a.txt": ""}})
        self.assertEqual(pe._resolved({"step": "workspace", "files": {"a": {"text": "x\n", "newline": "\r\n"},
                                                                     "b": {"bytes_hex": "00FF"}}}, ws)["files"],
                         {"a": b"x\r\n".hex(), "b": "00ff"})
        self.assertEqual(pe._resolved({**CALL, "args": ["<ws>/a", 1], "kwargs": {"p": "<ws>"}, "method": "<ws>", "as": "r"},
                                      ws), {**CALL, "args": [ws + "/a", 1], "kwargs": {"p": ws}, "method": "<ws>", "as": "r"})
        self.assertEqual(pe._resolved({"step": "write", "path": BOOK, "text": "a\n", "newline": "\r\n", "append": True}, ws),
                         {"step": "write", "path": "book.jsonl", "data_hex": b"a\r\n".hex(), "append": True})
        self.assertEqual(pe._resolved({"step": "write", "path": BOOK, "bytes_hex": ""}, ws),
                         {"step": "write", "path": "book.jsonl", "data_hex": ""})
        self.assertEqual(pe._resolved({**MINIMAL["edit_jsonl"], "value": "<ws>/v"}, ws),
                         {"step": "edit_jsonl", "path": "book.jsonl", "line": 0, "field": "k", "value": "<ws>/v"})
        self.assertEqual(pe._resolved({"step": "subprocess", "argv": ["-m", "s", "<ws>/b"], "expect_exit": 2}, ws),
                         {"step": "subprocess", "argv": ["-m", "s", ws + "/b"], "expect_exit": 2})
        for fault, patch in pe.FAULTS.items():
            self.assertEqual(pe._resolved({"step": "fault", "fault": fault}, ws),
                             {"step": "fault", "fault": fault, "patch": list(patch)})
        self.assertEqual(pe._resolved({**MINIMAL["expect_raises"], "attrs": {"filename": "<ws>/x"}}, ws)["attrs"],
                         {"filename": "<ws>/x"})   # declared values are compared in placeholder form, never substituted

    def test_the_fault_table_is_closed_typed_and_names_no_callable(self):
        self.assertEqual(pe.FAULTS, {"os.replace": ("os", "replace", "OSError"), "os.rename": ("os", "rename", "OSError"),
                                     "os.fsync": ("os", "fsync", "OSError"), "os.write": ("os", "write", "OSError")})
        for fault, (module, attr, error) in pe.FAULTS.items():
            self.assertEqual(fault, f"{module}.{attr}")
            self.assertTrue(callable(getattr(__import__(module), attr)))
            self.assertTrue(issubclass(getattr(__import__("builtins"), error), BaseException))

    def test_the_observed_files_and_their_jsonl_probes(self):
        self.assertEqual(pe._observed_files({"returns": 1}), {})
        self.assertEqual(pe._observed_files({"files": {BOOK: {"jsonl": {"line": 2, "field": "f", "equals": 1}},
                                                       "<ws>/b": {"absent": True}}}),
                         {"book.jsonl": [[2, "f"]], "b": []})

    def test_the_request_the_harness_receives(self):
        captured = {}

        class Capture(FakeRange):
            def start(self):
                captured.update(json.loads(pathlib.Path(self.argv[-1]).read_text(encoding="utf-8")))
                captured["argv"], captured["kw"] = self.argv, self.kw
                return super().start()

            def __call__(self, name, argv, **kw):
                self.kw = kw
                return super().__call__(name, argv, **kw)
        scenario = [MINIMAL["workspace"], NEW, {**CALL, "method": "where"}, MINIMAL["fault"], CALL]
        s = spec(scenario, {"files": {BOOK: {"jsonl": {"line": 0, "field": "k", "equals": 1}}}})
        fake = Capture(("READY", "DISPATCHED", 'RESULT {"subject": "absent"}'), 0)
        with mock.patch.object(pe, "ProcessRange", fake):
            self.assertEqual(self.see(s).kind, K.SUBJECT_ABSENT)
        ws = captured["ws"]
        self.assertEqual(os.path.basename(ws), "ws")
        self.assertEqual((captured["root"], captured["locator"], captured["interpreter"], captured["boot"]),
                         (self.root, "store.book:Book", sys.executable, pe.SUBPROCESS))
        self.assertEqual(captured["env"], ci._child_env(ws))
        self.assertEqual(captured["steps"], [pe._resolved(x, ws) for x in scenario])
        self.assertEqual(captured["steps"][1]["args"], [ws + "/book.jsonl"])
        self.assertEqual(captured["files"], {"book.jsonl": [[0, "k"]]})
        self.assertEqual(captured["protocol"], os.path.join(captured["work"], "protocol.log"))
        self.assertEqual(captured["kw"]["cwd"], ws)
        self.assertEqual(captured["kw"]["env"], ci._child_env(ws))
        argv = captured["argv"]
        self.assertEqual(argv[:4] + argv[5:9], [sys.executable, "-I", "-B", "-X", "-X", "utf8=1", "-c", pe.HARNESS])
        self.assertEqual(argv[4], "pycache_prefix=" + os.path.join(captured["work"], "pycache"))
        self.assertEqual(fake.name, f"probe {s.id}")
        self.assertTrue(fake.released)
        self.assertEqual(pe._harness_argv("py", "ask", "pc"), ["py", "-I", "-B", "-X", "pycache_prefix=pc", "-X", "utf8=1",
                                                                "-c", pe.HARNESS, "ask"])


# --------------------------------------------------------------------------------------- the parent's decision table

class Decision(_Checkout):
    S1 = spec([NEW, CALL], {"returns": 1})

    def test_a_RESULT_is_the_observation(self):
        with faked("READY", "DISPATCHED", "STEP 0", "STEP 1", 'RESULT {"subject": "present", "trace": [], "last_returned": 1}',
                   "END", returncode=0):
            o = self.see(self.S1)
        self.assertEqual((o.kind, o.verdict, facts_of(o)["last_returned"]), (K.OBSERVED, S, 1))
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "trace": [], "last_returned": 2}', returncode=0):
            self.assertEqual(self.see(self.S1).verdict, R)
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "absent", "note": "n"}', returncode=0):
            self.assertEqual(self.see(self.S1), Observation(K.SUBJECT_ABSENT, R, "n"))
        with faked("READY", "DISPATCHED", 'RESULT {"harness_failure": "the fault os.replace was not restored"}', returncode=0):
            self.assertEqual(self.see(self.S1), Observation(K.HARNESS_FAILED, detail="the harness failed its own scenario: "
                                                                                     "the fault os.replace was not restored"))
            self.assertIs(run_probe(P, self.S1, self.at, env()).result.status, ProbeExecutionStatus.UNRUNNABLE)
        ladder = [{"stage": "cooperative", "signal": "SIGINT"}]
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "trace": [], "last_returned": 1}', returncode=0,
                   ledger=ladder), self.assertRaises(ProbeInterrupted):
            self.see(self.S1)   # the controller stopped it: whatever the harness reported is not a measurement

    def test_the_process_ending_during_a_step_refutes_with_that_step(self):
        with faked("READY", "DISPATCHED", "STEP 0", "STEP 1", returncode=3):
            o = self.see(self.S1)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        self.assertEqual(facts_of(o), {"subject": "present", "hard_exit": True, "exit_code": 3, "trace": [],
                                       "refuted": {"step": 1, "why": "the process ended with exit status 3 before the "
                                                                     "scenario completed"}})
        with faked("READY", "DISPATCHED", returncode=0):   # before the first step (the subject's import)
            self.assertEqual(facts_of(self.see(self.S1))["refuted"]["step"], None)
        with faked("READY", "DISPATCHED", "STEP 0", returncode=-9):
            o = self.see(self.S1)
            self.assertEqual(run_probe(P, self.S1, self.at, env()).result.status, ProbeExecutionStatus.EXECUTED)
        self.assertEqual(o, Observation(K.NON_CONTROLLER_SIGNAL, detail="the process ended by signal 9 after DISPATCHED, "
                                                                        "and this controller's signal ledger is empty: "
                                                                        "it did not send it"))
        with faked("READY", "DISPATCHED", "STEP 0", returncode=-9, ledger=[{"stage": "kill", "signal": "SIGKILL"}]):
            with self.assertRaises(ProbeInterrupted) as stopped:
                self.see(self.S1)
        self.assertEqual((stopped.exception.signal, stopped.exception.stage), (9, "kill"))

    def test_before_DISPATCHED_the_harness_failed(self):
        with faked(returncode=-9):
            self.assertEqual(self.see(self.S1).detail, "the harness process was killed by signal 9 before READY")
        with faked("READY", returncode=0):
            self.assertEqual(self.see(self.S1).detail, "the harness did not start (exit 0, no DISPATCHED): tool absent or "
                                                       "broken")
        with faked("READY", "DISPATCHED", returncode=0, write=False):
            self.assertEqual(self.see(self.S1).detail, "the harness did not start (exit 0, no READY): tool absent or broken")

    def test_the_window_expired_with_the_process_present_or_gone(self):
        class Running(FakeRange):
            def wait(self, timeout=None):
                return None

            def members(self):
                return [object()]

        class Vanished(FakeRange):
            def wait(self, timeout=None):
                return None
        s = spec([NEW, CALL, CALL], {"returns": 1}, window=0.2)
        with mock.patch.object(pe, "ProcessRange", Running(("READY", "DISPATCHED", "STEP 0", "STEP 2"), None)):
            self.assertEqual(self.see(s), Observation(K.SUBJECT_DEADLINE, R, "the scenario's 0.2s observation window "
                                                                            "expired at step 2 (scenario_returns)"))
        with mock.patch.object(pe, "ProcessRange", Running(("READY", "DISPATCHED"), None)):
            self.assertEqual(self.see(s).detail, "the scenario's 0.2s observation window expired at step none "
                                                 "(scenario_returns)")
        with mock.patch.object(pe, "ProcessRange", Running(("READY", "DISPATCHED"), None,
                                                           [{"stage": "cooperative", "signal": "SIGINT"}])), \
                self.assertRaises(ProbeInterrupted):
            self.see(s)
        with mock.patch.object(pe, "ProcessRange", Vanished(("READY", "DISPATCHED"), None)), \
                mock.patch.object(pe, "_COLLECT_S", 0.05):
            self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the harness process ended and its exit "
                                                                              "status was never reported"))
        # C2-P2-FINDING-002: a controller stop that reports no exit status (Windows' TerminateJobObject) is an
        # interruption, the ledger asked first
        with mock.patch.object(pe, "ProcessRange", Vanished(("READY", "DISPATCHED"), None,
                                                            [{"stage": "terminate_job", "signal": "TerminateJobObject"}])), \
                mock.patch.object(pe, "_COLLECT_S", 0.05), self.assertRaises(ProbeInterrupted) as stopped:
            self.see(s)
        self.assertEqual(stopped.exception.stage, "terminate_job")

        class LateResult(Vanished):   # the status is reported at the end of the window and RESULT is in the file then
            def wait(self, timeout=None):
                return 0 if timeout else None
        with mock.patch.object(pe, "ProcessRange", LateResult(("READY", "DISPATCHED", "STEP 1"), 0)), \
                mock.patch.object(pe, "_COLLECT_S", 0.05):
            o = self.see(s)
        self.assertEqual((o.kind, o.verdict, facts_of(o)["refuted"]["step"]), (K.OBSERVED, R, 1))

    def test_nothing_runs_for_a_refused_spec_or_a_harness_that_cannot_look(self):
        gone = os.path.join(self.root, "no-python")
        with never_runs():
            self.assertEqual(self.see(self.S1, e=env(interpreter=gone)),
                             Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"))
            self.assertEqual(P.observe(self.S1, RevisionRef(SHA, os.path.join(self.root, "gone")), env()),
                             Observation(K.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing"))
            self.assertEqual(self.see(self.S1, probe=ProcessEffectProbe(scratch=gone)),
                             Observation(K.HARNESS_FAILED, detail="the evaluation directory cannot be created: "
                                                                  "FileNotFoundError"))
            inside = os.path.join(self.root, "scratch-in-tree")
            os.makedirs(inside, exist_ok=True)
            self.assertEqual(self.see(self.S1, probe=ProcessEffectProbe(scratch=inside)),
                             Observation(K.HARNESS_FAILED, detail="the evaluation directory lies inside the revision "
                                                                  "checkout: refused"))
            with mock.patch.object(pe, "_prepare", side_effect=PermissionError("denied")):
                self.assertEqual(self.see(self.S1), Observation(K.HARNESS_FAILED, detail="the evaluation directory "
                                                                                        "cannot be prepared: "
                                                                                        "PermissionError"))
            self.assertEqual(self.see(spec([CALL], {"returns": 1}, kind="python_callable")),
                             Observation(K.UNSUPPORTED, detail="subject kind 'python_callable' is not process_effect"))
            self.assertEqual(self.see(spec([CALL], {"returns": 1}, locator="store/book.py")),
                             Observation(K.UNSUPPORTED, detail="locator 'store/book.py' is not module.path:Name — a path "
                                                               "is never accepted"))
            o = self.see(spec([{"step": "teleport"}], {"returns": 1}))
            self.assertEqual(o.kind, K.UNSUPPORTED)
            self.assertEqual(o.detail, f"observable/stimulus is not a supported class {pe.CLASSES} over a scenario of the "
                                       "closed step vocabulary with a bounded window (within_s); refused, not degraded")
            for locator in ("tests.book:Book", "store.test_book:Book"):
                self.assertRegex(run_probe(P, spec([CALL], {"returns": 1}, locator=locator), self.at, env()).result.detail,
                                 "developer test artefact")
        for error in (OSError("cannot launch"), ci.RangeError("no anchor")):
            with self.subTest(error=error), mock.patch.object(
                    pe, "ProcessRange", mock.Mock(return_value=mock.Mock(start=mock.Mock(side_effect=error)))):
                self.assertEqual(self.see(self.S1), Observation(K.HARNESS_FAILED, detail=f"the harness cannot launch: "
                                                                                        f"{type(error).__name__}"))
        hooked = []
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "absent"}', returncode=0):
            ProcessEffectProbe(on_range=hooked.append).observe(self.S1, self.at, env())
        self.assertEqual(len(hooked), 1)


# --------------------------------------------------------------------------------------- identity

class Identity(unittest.TestCase):
    def test_the_digest_covers_exactly_the_sources_it_names_and_is_stable_across_processes(self):
        self.assertEqual(pe.PROBE_SOURCES, ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py",
                                            "probe/process_effect.py"))

        def digest_of(files):
            h = hashlib.sha256()
            for rel, data in files:
                h.update(rel.encode() + b"\0" + data + b"\0")
            return h.hexdigest()
        files = [(rel, (ROOT / "aisef2" / rel).read_bytes().replace(b"\r\n", b"\n")) for rel in pe.PROBE_SOURCES]
        self.assertEqual(digest_of(files), P.digest)
        self.assertEqual(pe._probe_digest(), P.digest)
        for i, (rel, data) in enumerate(files):
            with self.subTest(source=rel):
                changed = list(files)
                changed[i] = (rel, data + b"# changed\n")
                self.assertNotEqual(digest_of(changed), P.digest)
                self.assertNotEqual(digest_of(files[:i] + files[i + 1:]), P.digest)
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import aisef2.probe.process_effect as m; "
                "print(m.ProcessEffectProbe.digest)")
        out = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(out.stdout.strip(), P.digest)
        self.assertNotIn(P.digest, (ci.DIGEST, __import__("aisef2.probe.python_callable", fromlist=["DIGEST"]).DIGEST))

    def test_enforcement_preconditions_and_the_weakest_path_are_declared(self):
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        self.assertEqual(len(P.harness_preconditions()), 5)
        self.assertIn("restored", P.harness_preconditions()[-1])
        self.assertTrue(all(p and ": " in p for p in P.harness_preconditions()))
        self.assertEqual(len(set(P.harness_preconditions())), 5)
        self.assertIn("not a sandbox", pe.WEAKEST_PATH)
        self.assertIn("bounded witness", pe.FAULT_WITNESS)
        self.assertEqual((P.id, pe.METADATA.probe_id, pe.METADATA.probe_digest), (pe.PROBE_ID, pe.PROBE_ID, pe.DIGEST))
        self.assertEqual(pe.CLASSES, ("scenario_returns", "scenario_raises", "scenario_files"))
        self.assertEqual(pe.PLACEHOLDER, "<ws>")
        self.assertEqual(Executed(S), Executed(S))


if __name__ == "__main__":
    unittest.main()
