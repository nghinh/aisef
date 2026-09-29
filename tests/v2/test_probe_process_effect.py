"""WP-2.3.1 — the `process_effect` scenario probe on real checkouts (RFC §9, §9.2, §9.3, §10.2; F5; DECISION-2).

PE-1..8, PE-ADV-1/2, PE-Q0, the Q3 fault family FM2-EFFECT-1..10 and FM2-PYC-2 (P7-FINDING-001 case 2 re-run against
this probe). Subprocess backed: the kill set for the harness script's functions (`HARNESS/<function>` mutation
targets: the step dispatcher, the placeholder round trip, the expect_raises attribute comparison, edit_jsonl, the file
facts, the fault scope) and for the parent's harness targets; the pure functions and the parent's decision table over
test doubles are in tests/v2/test_probe_process_effect_units.py, the bytecode family in
tests/v2/test_probe_process_effect_bytecode.py. At the tests/v2 root like the other Cycle-2 modules (the test tiers
are a closed enum of the frozen invariant registry).
"""

import ast
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, MeasurementPoint, ObligationRole, Owner, Polarity,
    ProbeExecutionStatus, SubjectAbsence, SubjectKind,
)
from aisef2.control.owner import FailureCode  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.plan import static_admission as sa  # noqa: E402
from aisef2.probe import catalog, process_effect as pe  # noqa: E402
from aisef2.probe.process_effect import ProcessEffectProbe  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, ObservationKind as K, RevisionRef, classify_failure, run_probe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = ProcessEffectProbe()
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
POSIX = os.name == "posix"
SHA = "89abcdef0123456789abcdef0123456789abcdef"
W = 20          # a window generous enough for any runner; the hanging cases use their own
BOOK = "<ws>/book.jsonl"

#: A product-like checkout: an append-only JSONL book with a digest chain (names never start with "test"; every
#: behaviour is the subject's own, written by the harness's test author, never read for control).
BOOK_PY = '''
import hashlib
import json
import os
import sys
import time


class ConflictError(Exception):
    def __init__(self, key, rid, index):
        super().__init__("key " + key + " belongs to another rid")
        self.key, self.rid, self.index = key, rid, index


class Rich(Exception):
    def __init__(self):
        super().__init__("rich")
        self.payload = {"b": 1, "a": [2, {"d": None, "c": True}]}


class Odd(Exception):
    @property
    def detail(self):
        raise RuntimeError("no detail")


def _digest(prev, body):
    return hashlib.sha256((prev + "|" + json.dumps(body, sort_keys=True)).encode("utf-8")).hexdigest()


def total(*values):
    return sum(values)


def echo(*values):
    return list(values)


class Book:
    def __init__(self, path):
        self.path = path

    def _records(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, "rb") as f:
            return [json.loads(line) for line in f.read().split(b"\\n") if line]

    def append(self, key, value, rid):
        records = self._records()
        for i, rec in enumerate(records):
            if rec["rid"] == rid:
                return i
            if rec["key"] == key:
                raise ConflictError(key, rid, i)
        prev = records[-1]["hash"] if records else "GENESIS"
        body = {"key": key, "value": value, "rid": rid, "prev": prev}
        line = json.dumps(dict(body, hash=_digest(prev, body)), sort_keys=True, separators=(",", ":"))
        with open(self.path, "ab") as f:
            f.write(line.encode("utf-8") + b"\\n")
            f.flush()
            os.fsync(f.fileno())
        return len(records)

    def verify(self):
        prev = "GENESIS"
        for i, rec in enumerate(self._records()):
            body = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev") != prev or rec.get("hash") != _digest(prev, body):
                return {"ok": False, "first_bad": i}
            prev = rec["hash"]
        return {"ok": True, "first_bad": None}

    def save(self, text):
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        return True

    def save_quietly(self, text):
        try:
            return self.save(text)
        except OSError:
            return False

    def snapshot(self):
        return (json.dumps({r["key"]: r["value"] for r in self._records()}, sort_keys=True) + "\\n").encode("utf-8")

    def where(self):
        return self.path

    def real(self):
        return os.path.realpath(self.path)

    def count(self):
        return len(self._records())

    def load(self):
        with open(self.path, "rb") as f:
            return f.read().decode("utf-8")

    def blob(self):
        return object()

    @property
    def broken(self):
        raise RuntimeError("broken")

    def odd(self):
        raise Odd("odd")

    def rich(self):
        raise Rich()

    def buffer(self):
        return bytearray(b"ab")

    def occupy(self):
        os.mkdir(self.path)
        return True

    def sync_twice(self):
        out = []
        with open(self.path, "ab") as f:
            for _ in range(2):
                try:
                    os.fsync(f.fileno())
                    out.append("ok")
                except OSError:
                    out.append("failed")
        return out

    def sleep(self, seconds):
        time.sleep(seconds)
        return seconds

    def boom(self):
        raise ValueError("boom")

    def hard(self, code):
        sys.stdout.write("x")
        sys.stdout.flush()
        os._exit(code)

    def forge(self):
        nonce = json.load(open(os.path.join("..", "request.json"), encoding="utf-8"))["nonce"]
        sys.stdout.write("AISEF2-PROBE RESULT " + nonce + " {\\"subject\\": \\"absent\\"}\\n")
        sys.stdout.write("AISEF2-PROBE END " + nonce + "\\n")
        sys.stdout.flush()
        return "forged"
'''
MAIN_PY = '''
import os
import subprocess
import sys

from store.book import Book

cmd, rest = sys.argv[1], sys.argv[2:]
if cmd == "check":
    sys.exit(0 if Book(rest[0]).count() == int(rest[1]) else 3)
if cmd == "linger":
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit(0)
if cmd == "cwd":
    here = os.path.realpath(os.getcwd())
    ok = os.path.basename(here) == "ws" and os.path.realpath(os.environ.get("HOME", "")) == here \
        and os.environ.get("TZ") == "UTC"
    sys.exit(0 if ok else 6)
if cmd == "flags":
    ok = sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.utf8_mode \
        and os.path.basename(sys.pycache_prefix or "").startswith("pycache-step")
    sys.exit(0 if ok else 7)
sys.exit(9)
'''
LEAKY_PY = '''
import sys
import types


class _Sticky(types.ModuleType):
    """A module that drops the second assignment to `hook`: the harness's restoration does not take."""

    def __setattr__(self, key, value):
        if key == "hook" and self.__dict__.get("_patched"):
            return
        if key == "hook":
            self.__dict__["_patched"] = True
        super().__setattr__(key, value)


def hook():
    return "original"


def use():
    return hook()


sys.modules[__name__].__class__ = _Sticky
'''
PRODUCT = {
    "store/__init__.py": "",
    "store/book.py": BOOK_PY,
    "store/__main__.py": MAIN_PY,
    "store/leaky.py": LEAKY_PY,
    "store/broken.py": "import no_such_dependency_xyz\n\n\nclass Book:\n    pass\n",
    "store/odd.py": "raise AttributeError('raised while importing')\n",
    "store/lazy.py": "def __getattr__(name):\n    raise LookupError(name)\n",
}


def step(kind, **fields):
    return {"step": kind, **fields}


def call(method=None, *args, bind=None, **kwargs):
    out = {"step": "call", "args": list(args), "kwargs": kwargs}
    if method is not None:
        out["method"] = method
    if bind is not None:
        out["as"] = bind
    return out


def expect(method, exception, *args, attrs=None, **kwargs):
    out = {"step": "expect_raises", "method": method, "exception": exception, "args": list(args), "kwargs": kwargs}
    if attrs is not None:
        out["attrs"] = attrs
    return out


def construct(*args, **kwargs):
    return {"step": "construct", "args": list(args), "kwargs": kwargs}


def spec(locator, scenario, observable, *, expectation=S, absence=REQUIRES, probe=P, window=W):
    """A spec over `locator`; its observable declares the bounded window `window` (None: declares none)."""
    observable = dict(observable)
    if window is not None:
        observable.setdefault("within_s", window)
    return ProductProofSpec.create(
        contract_id="BC-EFFECT", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": "process_effect", "locator": locator}, "stimulus": {"scenario": scenario},
                     "observable": observable, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


def book(*scenario):
    """A scenario over a Book at <ws>/book.jsonl."""
    return [construct(BOOK), *scenario]


def env(timeout=20, required=Enforcement.PARTIAL, interpreter=sys.executable):
    return ExecutionEnv(interpreter, timeout, required)


def facts_of(observation):
    return json.loads(observation.detail)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Product(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dirs = [tempfile.TemporaryDirectory(prefix="aisef2-effect-rev-", ignore_cleanup_errors=True)
                     for _ in range(2)]
        for d in cls._dirs:
            cls.addClassCleanup(d.cleanup)
        cls.at = RevisionRef(SHA, checkout(cls._dirs[0].name, PRODUCT))
        cls.empty = RevisionRef(SHA, checkout(cls._dirs[1].name, {"README.md": "no product yet\n"}))

    def see(self, s, at=None, e=None, probe=P):
        return probe.observe(s, at or self.at, e or env())

    def run_(self, s, at=None, e=None, probe=P):
        return run_probe(probe, s, at or self.at, e or env()).result


def checkout(root, files):
    for rel, text in files.items():
        p = pathlib.Path(root, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return root


def never_runs():
    return mock.patch.object(pe, "ProcessRange", side_effect=AssertionError("ran"))


# --------------------------------------------------------------------------------------- PE-1..8

class Scenario(_Product):
    def test_PE_1_a_full_scenario_workspace_construct_call_call_returns(self):
        scenario = [step("workspace", files={"book.jsonl": {"text": ""}}), construct(BOOK),
                    call("append", "a", 1, "r1"), call("append", "b", 2, "r2")]
        o = self.see(spec("store.book:Book", scenario, {"returns": 1}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts_of(o)
        self.assertEqual(f["trace"], [{"i": 0, "kind": "workspace", "outcome": "ok"},
                                      {"i": 1, "kind": "construct", "outcome": "ok"},
                                      {"i": 2, "kind": "call", "outcome": "ok"}, {"i": 3, "kind": "call", "outcome": "ok"}])
        self.assertEqual((f["subject"], f["last_returned"], f.get("refuted")), ("present", 1, None))
        self.assertEqual(self.run_(spec("store.book:Book", scenario, {"returns": 1})), Executed(S))
        self.assertEqual(self.see(spec("store.book:Book", scenario, {"returns": 5})).verdict, R)
        # the state is the instance's across calls: a replayed rid returns its first index
        o = self.see(spec("store.book:Book", book(call("append", "a", 1, "r1"), call("append", "b", 2, "r2"),
                                                  call("append", "a", 1, "r1")), {"returns": 0}))
        self.assertEqual(o.verdict, S, o.detail)
        # a callable subject: no construct, each call on the callable itself
        o = self.see(spec("store.book:total", [call(None, 1, 2, 3)], {"returns": 6}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        # equality between two bound results, bytes reported as hex
        eq = book(call("append", "a", 1, "r1"), call("snapshot", bind="s1"), call("snapshot", bind="s2"))
        o = self.see(spec("store.book:Book", eq, {"returns_name": "s1", "equals_name": "s2"}))
        self.assertEqual(o.verdict, S, o.detail)
        self.assertEqual(facts_of(o)["bound"]["s1"], {"bytes_hex": b'{"a": 1}\n'.hex()})
        self.assertEqual(self.see(spec("store.book:Book", eq, {"returns_bytes_hex": b'{"a": 1}\n'.hex()})).verdict, S)
        self.assertEqual(self.see(spec("store.book:Book", eq, {"returns": '{"a": 1}\n'})).verdict, R)   # bytes, not text
        self.assertEqual(self.see(spec("store.book:Book", book(call("buffer")), {"returns_bytes_hex": "6162"})).verdict, S)
        differ = book(call("snapshot", bind="s1"), call("append", "a", 1, "r1"), call("snapshot", bind="s2"))
        self.assertEqual(self.see(spec("store.book:Book", differ, {"returns_name": "s1", "equals_name": "s2"})).verdict, R)
        blobs = book(call("blob", bind="b1"), call("blob", bind="b2"))
        o = self.see(spec("store.book:Book", blobs, {"returns_name": "b1", "equals_name": "b2"}))
        self.assertEqual((o.verdict, facts_of(o)["last_unserializable"]), (R, "object"))
        self.assertEqual(self.see(spec("store.book:Book", blobs, {"returns": None})).verdict, R)

    def test_PE_2_expect_raises_with_attributes(self):
        base = [call("append", "a", 1, "r1")]
        declared = {"key": "a", "rid": "r2", "index": 0}
        o = self.see(spec("store.book:Book", book(*base, expect("append", "ConflictError", "a", 2, "r2", attrs=declared)),
                          {"raises": True}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts_of(o)
        self.assertEqual(f["raised"], {"type": "ConflictError", "attrs": {k: {"json": v} for k, v in declared.items()}})
        self.assertEqual(f["trace"][-1]["outcome"], "raised:ConflictError")
        cases = {
            "wrong value": (expect("append", "ConflictError", "a", 2, "r2", attrs={**declared, "index": 1}),
                            "ConflictError.index is not the declared value"),
            "missing attribute": (expect("append", "ConflictError", "a", 2, "r2", attrs={"owner": "x"}),
                                  "ConflictError has no attribute owner"),
            "other type": (expect("append", "ValueError", "a", 2, "r2"), "raised ConflictError, not ValueError"),
            "no raise": (expect("append", "ConflictError", "a", 1, "r1"), "returned; ConflictError was not raised"),
            "method missing": (expect("nope", "ConflictError"), "method nope missing"),
        }
        for name, (last, why) in cases.items():
            with self.subTest(case=name):
                o = self.see(spec("store.book:Book", book(*base, last), {"raises": True}))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                self.assertEqual(facts_of(o)["refuted"], {"step": 2, "kind": "expect_raises", "why": why})
        # an expect_raises that matched need not be last: the scenario goes on after it
        o = self.see(spec("store.book:Book", book(*base, expect("append", "ConflictError", "a", 2, "r2"),
                                                  call("count")), {"returns": 1}))
        self.assertEqual(o.verdict, S, o.detail)
        # exactly the type name: a subclass does not match its base's name
        o = self.see(spec("store.book:Book", book(*base, expect("append", "Exception", "a", 2, "r2")), {"raises": True}))
        self.assertEqual(o.verdict, R)
        # a mapping attribute is compared as JSON: its key order is not significant, its values are exact
        rich = {"payload": {"a": [2, {"c": True, "d": None}], "b": 1}}
        self.assertEqual(self.see(spec("store.book:Book", book(expect("rich", "Rich", attrs=rich)), {"raises": True})).verdict, S)
        rich_1 = {"payload": {"a": [2, {"c": 1, "d": None}], "b": 1}}
        self.assertEqual(self.see(spec("store.book:Book", book(expect("rich", "Rich", attrs=rich_1)), {"raises": True})).verdict, R)
        # the exception's args are an attribute like any other, compared after JSON serialisation
        o = self.see(spec("store.book:Book", book(expect("boom", "ValueError", attrs={"args": ["boom"]})), {"raises": True}))
        self.assertEqual(o.verdict, S, o.detail)

    def test_PE_3_write_and_edit_jsonl_out_of_band_then_the_subject_and_the_file_observables(self):
        two = [call("append", "a", 1, "r1"), call("append", "b", 2, "r2")]
        clean = self.see(spec("store.book:Book", book(*two, call("verify")), {"returns": {"ok": True, "first_bad": None}}))
        self.assertEqual(clean.verdict, S, clean.detail)
        tamper = book(*two, step("edit_jsonl", path=BOOK, line=1, field="value", value=99), call("verify"))
        o = self.see(spec("store.book:Book", tamper, {"returns": {"ok": False, "first_bad": 1}}))
        self.assertEqual(o.verdict, S, o.detail)
        # a write out of band: the book's bytes replaced by the harness itself, detected by the subject
        rewrite = book(*two, step("write", path=BOOK, text='{"key":"z"}\n', newline="\n"), call("verify"))
        self.assertEqual(self.see(spec("store.book:Book", rewrite, {"returns": {"ok": False, "first_bad": 0}})).verdict, S)
        # the file observables, all at once over one scenario
        seed = step("workspace", files={"book.jsonl": {"text": ""}, "keep.txt": {"bytes_hex": "00ff0a"}})
        tail = step("write", path=BOOK, bytes_hex=b'{"trunc'.hex(), append=True)
        scenario = [seed, construct(BOOK), *two, tail]
        files = {BOOK: {"line_count": 3}, "<ws>/keep.txt": {"equals_before": True}, "<ws>/none.txt": {"absent": True}}
        o = self.see(spec("store.book:Book", scenario, {"files": files}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts_of(o)
        self.assertEqual(f["before"], {"book.jsonl": {"sha256": sha(b"")}, "keep.txt": {"sha256": sha(b"\x00\xff\n")},
                                       "none.txt": {"absent": True}})
        self.assertEqual((f["files"]["book.jsonl"]["line_count"], f["files"]["book.jsonl"]["final_byte_hex"]), (3, "63"))
        self.assertEqual((f["files"]["keep.txt"]["size"], f["files"]["keep.txt"]["final_byte_hex"]), (3, "0a"))
        # a scenario of its workspace alone: the files are recorded before and after it, and are equal
        only = [step("workspace", files={"keep.txt": {"text": "k"}})]
        o = self.see(spec("store.book:Book", only, {"files": {"<ws>/keep.txt": {"equals_before": True},
                                                              "<ws>/none.txt": {"absent": True}}}))
        self.assertEqual((o.verdict, facts_of(o)["before"]), (S, {"keep.txt": {"sha256": sha(b"k")}, "none.txt": {"absent": True}}))
        # the shapes that read the recorded facts are verdicts over this observation's facts; each jsonl shape asks
        # the harness for its own (line, field), so it is observed on its own
        for shape, verdict in (({"final_byte": "\n"}, R), ({"final_byte": "c"}, S), ({"equals_before": True}, R),
                               ({"absent": True}, R), ({"line_count": 2}, R),
                               ({"sha256": f["files"]["book.jsonl"]["sha256"]}, S), ({"sha256": sha(b"")}, R)):
            with self.subTest(shape=shape):
                self.assertIs(pe.verdict_of("scenario_files", {"files": {BOOK: shape}}, f), verdict)
        for shape, verdict in (({"jsonl": {"line": 0, "field": "prev", "equals": "GENESIS"}}, S),
                               ({"jsonl": {"line": 1, "field": "value", "equals": 2}}, S),
                               ({"jsonl": {"line": 1, "field": "value", "equals": "2"}}, R),
                               ({"jsonl": {"line": 1, "field": "owner", "equals": None}}, R),
                               ({"jsonl": {"line": 2, "field": "key", "equals": None}}, R),
                               ({"jsonl": {"line": 7, "field": "key", "equals": "a"}}, R)):
            with self.subTest(shape=shape):
                self.assertEqual(self.see(spec("store.book:Book", scenario, {"files": {BOOK: shape}})).verdict, verdict)
        # edit_jsonl names the step it could not perform: a line that is not JSON, a missing field, no such line
        for edit, why in ((step("edit_jsonl", path=BOOK, line=2, field="key", value="x"), "edit_jsonl: line 2 is not JSON"),
                          (step("edit_jsonl", path=BOOK, line=0, field="owner", value="x"),
                           "edit_jsonl: line 0 has no field owner"),
                          (step("edit_jsonl", path=BOOK, line=3, field="key", value="x"),
                           "edit_jsonl: book.jsonl has no line 3"),
                          (step("edit_jsonl", path="<ws>/gone.jsonl", line=0, field="key", value="x"),
                           "edit_jsonl: no file gone.jsonl")):
            with self.subTest(edit=edit):
                o = self.see(spec("store.book:Book", [*scenario, edit, call("count")], {"returns": 2}))
                self.assertEqual((o.verdict, facts_of(o)["refuted"]), (R, {"step": 5, "kind": "edit_jsonl", "why": why}))
        # a JSON line that is not an object has no field: edit_jsonl refuses, the jsonl shape does not hold
        arr = [*scenario, step("write", path="<ws>/arr.jsonl", text="[1]\n")]
        o = self.see(spec("store.book:Book", [*arr, step("edit_jsonl", path="<ws>/arr.jsonl", line=0, field="key", value=1)],
                          {"files": {"<ws>/arr.jsonl": {"line_count": 1}}}))
        self.assertEqual(facts_of(o)["refuted"]["why"], "edit_jsonl: line 0 has no field key")
        o = self.see(spec("store.book:Book", arr, {"files": {"<ws>/arr.jsonl": {"jsonl": {"line": 0, "field": "key",
                                                                                          "equals": None}}}}))
        self.assertEqual((o.verdict, facts_of(o)["files"]["arr.jsonl"]["jsonl"]), (R, {"0": None}))
        o = self.see(spec("store.book:Book", book(call("occupy"), step("write", path=BOOK, text="x"), call("count")),
                          {"returns": 0}))
        self.assertEqual((o.verdict, facts_of(o)["refuted"]["step"], facts_of(o)["refuted"]["kind"]), (R, 2, "write"))
        self.assertRegex(facts_of(o)["refuted"]["why"], r"^write book\.jsonl raised (IsADirectoryError|PermissionError)$")
        # edit_jsonl rewrites one field and keeps every other byte
        o = self.see(spec("store.book:Book", book(*two, step("edit_jsonl", path=BOOK, line=0, field="value", value=[1, "é"]),
                                                  call("load")), {"returns": "x"}))
        lines = facts_of(o)["last_returned"].split("\n")
        self.assertEqual(json.loads(lines[0])["value"], [1, "é"])
        self.assertIn('"value":[1,"é"]', lines[0])
        self.assertEqual((len(lines), lines[2]), (3, ""))

    def test_PE_4_a_subprocess_step_is_a_separate_process_opening_the_path(self):
        two = [call("append", "a", 1, "r1"), call("append", "b", 2, "r2")]
        ok = book(*two, step("subprocess", argv=["-m", "store", "check", BOOK, "2"]), call("count"))
        o = self.see(spec("store.book:Book", ok, {"returns": 2}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["trace"][3], {"i": 3, "kind": "subprocess", "outcome": "ok", "exit": 0})
        declared = book(*two, step("subprocess", argv=["-m", "store", "check", BOOK, "5"], expect_exit=3), call("count"))
        self.assertEqual(self.see(spec("store.book:Book", declared, {"returns": 2})).verdict, S)
        undeclared = book(*two, step("subprocess", argv=["-m", "store", "check", BOOK, "5"]), call("count"))
        o = self.see(spec("store.book:Book", undeclared, {"returns": 2}))
        self.assertEqual((o.verdict, facts_of(o)["refuted"]),
                         (R, {"step": 3, "kind": "subprocess", "why": "the subprocess exited 3, not 0"}))
        self.assertEqual(facts_of(o)["trace"][3]["exit"], 3)
        # its working directory and HOME are the workspace, TZ is pinned, it runs -I -B with a fresh bytecode prefix of
        # its own and UTF-8 mode; a module outside the revision is never found
        o = self.see(spec("store.book:Book", book(step("subprocess", argv=["-m", "store", "cwd"]),
                                                  step("subprocess", argv=["-m", "store", "flags"]),
                                                  step("subprocess", argv=["-m", "no_such_module_xyz"], expect_exit=1)),
                          {"files": {"<ws>/book.jsonl": {"absent": True}}}))
        self.assertEqual(o.verdict, S, o.detail)
        self.assertEqual([e.get("exit") for e in facts_of(o)["trace"]], [None, 0, 0, 1])

    def test_PE_5_a_fault_step_applies_to_the_next_call_only_and_is_restored(self):
        scenario = book(step("fault", fault="os.replace"), expect("save", "OSError", "x",
                                                                 attrs={"args": ["controlled fault os.replace"]}),
                        call("save", "y"))
        o = self.see(spec("store.book:Book", scenario, {"returns": True}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        trace = facts_of(o)["trace"]
        self.assertEqual(trace[1], {"i": 1, "kind": "fault", "outcome": "ok"})
        self.assertEqual(trace[2]["fault"], "os.replace")
        self.assertIs(trace[2]["fired"], True)
        self.assertNotIn("fault", trace[3])   # the one after does not see it: os.replace was restored
        # the fault is the subject's to meet: an unguarded fsync fault ends the call that met it
        o = self.see(spec("store.book:Book", book(step("fault", fault="os.fsync"), call("save", "z"), call("load")),
                          {"returns": "z"}))
        self.assertEqual(o.verdict, R, o.detail)   # save raised: the fault reached the subject's own call
        self.assertEqual(facts_of(o)["refuted"], {"step": 2, "kind": "call", "why": "raised OSError"})
        o = self.see(spec("store.book:Book", book(call("append", "a", 1, "r1"), step("fault", fault="os.fsync"),
                                                  expect("append", "OSError", "b", 2, "r2"), call("count")),
                          {"returns": 2}))
        self.assertEqual(o.verdict, S, o.detail)   # the line was written before the failed fsync; the fsync raised
        # two faults in one scenario: each is its own step's, and each fires there
        twice = book(step("fault", fault="os.replace"), expect("save", "OSError", "x"), call("save", "y"),
                     step("fault", fault="os.replace"), expect("save", "OSError", "z"), call("load"))
        o = self.see(spec("store.book:Book", twice, {"returns": "y"}))
        self.assertEqual(o.verdict, S, o.detail)
        self.assertEqual([e.get("fired") for e in facts_of(o)["trace"]], [None, None, True, None, None, True, None])
        # the stand-in raises once: a second invocation inside the same call reaches the original
        o = self.see(spec("store.book:Book", book(step("fault", fault="os.fsync"), call("sync_twice")),
                          {"returns": ["failed", "ok"]}))
        self.assertEqual(o.verdict, S, o.detail)
        # a fault that fires on nothing is recorded as not fired
        o = self.see(spec("store.book:Book", book(step("fault", fault="os.rename"), call("count")), {"returns": 0}))
        self.assertEqual((o.verdict, facts_of(o)["trace"][2]["fired"]), (S, False))
        # a fault not followed by the step it applies to is refused at admission; nothing runs
        with never_runs():
            for bad in (book(step("fault", fault="os.replace")),
                        book(step("fault", fault="os.replace"), step("write", path=BOOK, text="")),
                        book(step("fault", fault="os.replace"), step("fault", fault="os.fsync"), call("count")),
                        book(step("fault", fault="os.unlink"), call("count")),
                        book(step("fault", fault="os.replace", raises="OSError"), call("count"))):
                with self.subTest(scenario=[s["step"] for s in bad]):
                    self.assertIsNone(pe.spec_class(spec("store.book:Book", bad, {"returns": 0})))
                    self.assertIs(self.run_(spec("store.book:Book", bad, {"returns": 0})).status,
                                  ProbeExecutionStatus.INVALID_SPEC)

    def test_PE_6_an_absent_subject_before_any_step_a_missing_method_at_call_time(self):
        marker = step("workspace", files={"seen.txt": {"text": "x"}})
        cases = {"module missing": "nope:Book", "attribute missing": "store.book:Nope",
                 "a submodule of a plain module": "store.book.deeper:Book", "a package missing": "nope.inner:Book",
                 "resolves only outside the revision": "json:dumps"}
        for name, locator in cases.items():
            with self.subTest(case=name):
                o = self.see(spec(locator, [marker, call(None)], {"returns": None}))
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))
                self.assertEqual(classify_failure(spec(locator, [marker, call(None)], {"returns": None}), o), Executed(I, PA))
                forbidden = spec(locator, [marker, call(None)], {"returns": None}, absence=DECIDABLE, expectation=R)
                self.assertIs(contract_satisfaction(classify_failure(forbidden, o), forbidden), ContractSatisfaction.SATISFIED)
        self.assertEqual(self.see(spec("store.book:Book", [marker, call(None)], {"returns": None}), at=self.empty).kind,
                         K.SUBJECT_ABSENT)
        self.assertEqual(self.see(spec("json:dumps", [call(None)], {"returns": None})).detail,
                         "resolves only outside the revision")
        self.assertEqual(self.see(spec("store.book:Nope", [call(None)], {"returns": None})).detail,
                         "the module does not define Nope")
        self.assertEqual(self.see(spec("nope:Book", [call(None)], {"returns": None})).detail, "")
        # a construct that raises refutes at step 0; so does a method whose lookup raises, and an attribute read
        for scenario, why in (([construct(), call("count")], (0, "construct", "construct raised TypeError")),
                              (book(call("broken")), (1, "call", "resolving the method raised RuntimeError")),
                              (book(expect("broken", "RuntimeError")),
                               (1, "expect_raises", "resolving the method raised RuntimeError")),
                              (book(expect("odd", "Odd", attrs={"detail": 1})),
                               (1, "expect_raises", "reading Odd.detail raised RuntimeError"))):
            with self.subTest(why=why):
                o = self.see(spec("store.book:Book", scenario, {"returns": 0}
                                  if scenario[-1]["step"] == "call" else {"raises": True}))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                self.assertEqual(facts_of(o)["refuted"], dict(zip(("step", "kind", "why"), why, strict=True)))
        # the subject is there and does not offer the behaviour: observed, refuted, the step named
        o = self.see(spec("store.book:Book", book(call("append", "a", 1, "r1"), call("nope")), {"returns": None}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        self.assertEqual(facts_of(o)["refuted"], {"step": 2, "kind": "call", "why": "method nope missing"})
        # a module that resolves and raises on import is a present subject that does not work
        o = self.see(spec("store.broken:Book", book(call("count")), {"returns": 0}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        self.assertEqual(facts_of(o), {"subject": "present", "trace": [], "refuted": {
            "step": None, "kind": "import", "why": "importing the subject raised ModuleNotFoundError"}})
        # an AttributeError raised by the import is the import's failure, never an absent name
        o = self.see(spec("store.odd:Book", book(call("count")), {"returns": 0}))
        self.assertEqual((o.kind, o.verdict, facts_of(o)), (K.OBSERVED, R, {"subject": "present", "trace": [], "refuted": {
            "step": None, "kind": "import", "why": "importing the subject raised AttributeError"}}))
        o = self.see(spec("store.lazy:Book", book(call("count")), {"returns": 0}))
        self.assertEqual((o.kind, o.verdict, facts_of(o)), (K.OBSERVED, R, {"subject": "present", "trace": [], "refuted": {
            "step": None, "kind": "import", "why": "resolving the subject raised LookupError"}}))

    def test_PE_7_ws_is_the_only_placeholder_and_the_workspace_path_is_replaced_back(self):
        o = self.see(spec("store.book:Book", book(call("where")), {"returns": BOOK}))
        self.assertEqual(o.verdict, S, o.detail)
        # the resolved form too (realpath writes the platform's separator: that is the subject's own behaviour)
        o = self.see(spec("store.book:Book", book(call("real")), {"returns": "<ws>" + os.sep + "book.jsonl"}))
        self.assertEqual(o.verdict, S, o.detail)
        values = ["<ws>", "<ws>/a", "x<ws>/a", "<wsx>", "<ws>x", "<ws", "<tmp>/a", "<ws>/"]
        o = self.see(spec("store.book:echo", [call(None, *values, bind="e")], {"returns": values}))
        self.assertEqual(o.verdict, S, o.detail)   # substituted then replaced back: only the head forms moved
        o = self.see(spec("store.book:echo", [call(None, [{"p": "<ws>/n"}])], {"returns": [[{"p": "<ws>/n"}]]}))
        self.assertEqual(o.verdict, S, o.detail)
        # an exception attribute carrying the path is compared in its placeholder form
        o = self.see(spec("store.book:Book", [construct("<ws>/nope/x.jsonl"),
                                              expect("load", "FileNotFoundError", attrs={"filename": "<ws>/nope/x.jsonl"})],
                          {"raises": True}))
        self.assertEqual(o.verdict, S, o.detail)
        # a keyword argument's value is substituted like a positional one
        o = self.see(spec("store.book:Book", [construct(path=BOOK), call("where")], {"returns": BOOK}))
        self.assertEqual(o.verdict, S, o.detail)
        # the workspace itself: the harness's working directory and HOME, and never the checkout
        o = self.see(spec("store.book:Book", book(step("subprocess", argv=["-m", "store", "cwd"]), call("where")),
                          {"returns": BOOK}))
        self.assertEqual(o.verdict, S, o.detail)

    def test_PE_8_one_window_for_the_whole_scenario(self):
        o = self.see(spec("store.book:Book", book(call("sleep", 0), call("sleep", 30)), {"returns": 0}, window=1.0))
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))
        self.assertEqual(o.detail, "the scenario's 1s observation window expired at step 2 (scenario_returns)")
        self.assertEqual(classify_failure(spec("store.book:Book", book(call("sleep", 30)), {"returns": 0}), o), Executed(R))
        # each step fits the window alone; together they do not: the window is the scenario's, not a step's
        o = self.see(spec("store.book:Book", book(call("sleep", 0.6), call("sleep", 0.6)), {"returns": 0.6}, window=1.0))
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R), o.detail)
        for observable, cls in (({"raises": True}, "scenario_raises"), ({"files": {BOOK: {"absent": True}}}, "scenario_files")):
            with self.subTest(cls=cls):
                last = expect("sleep", "ValueError", 30) if cls == "scenario_raises" else call("sleep", 30)
                o = self.see(spec("store.book:Book", book(last), observable, window=0.3))
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))


# --------------------------------------------------------------------------------------- PE-ADV

class Adversarial(_Product):
    def test_PE_ADV_1_an_unknown_or_malformed_step_is_INVALID_SPEC_through_run_probe_and_refused_at_admission(self):
        bad = {"unknown kind": [step("teleport", to="x")], "no kind": [{"args": [], "kwargs": {}}],
               "extra field": [call("count") | {"shell": "rm -r x"}], "missing field": [{"step": "call", "args": []}],
               "args not a list": [{"step": "call", "args": "x", "kwargs": {}}],
               "reconstruct": [construct(BOOK), construct(BOOK), call("count")],
               "workspace not first": [construct(BOOK), step("workspace", files={"a": {"text": ""}}), call("count")],
               "a path that leaves the workspace": [construct(BOOK), step("write", path="<ws>/../x", text=""), call("count")],
               "a nested workspace name": [step("workspace", files={"a/b": {"text": ""}}), call(None)],
               "a subprocess that is not a module": [step("subprocess", argv=["-c", "print(1)"]), call(None)],
               "a binding name used twice": [construct(BOOK), call("count", bind="n"), call("count", bind="n")]}
        with never_runs():
            for name, scenario in bad.items():
                with self.subTest(case=name):
                    s = spec("store.book:Book", scenario, {"returns": 0})
                    self.assertIsNone(pe.spec_class(s))
                    self.assertIsNone(catalog.registry().observation_class(pe.PROBE_ID, pe.DIGEST, s))
                    result = self.run_(s)
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "refused, not degraded$")
        # through the frozen compiler: an approved contract compiles (the compiler is pure), and admission's check 9
        # refuses it because the registry gives the spec no observation class
        req = Requirement.create(id="R-EFFECT", text="the book detects tampering", source="fixture")
        contract = BehaviorContract.create(
            id="BC-EFFECT-1", requirement_ids=("R-EFFECT",), subject=Subject(SubjectKind.PROCESS_EFFECT, "store.book:Book"),
            stimulus={"scenario": [step("teleport", to="x")]}, observable={"returns": 0, "within_s": 5},
            polarity=Polarity.MUST_HOLD, subject_absence=REQUIRES, rationale="an unknown step kind")
        approval = ContractApproval("R-EFFECT", req.requirement_hash, contract.id, contract.contract_hash, "human:pe-adv-1",
                                    0.0, ())
        compiled = compile_spec(contract, requirements={"R-EFFECT": req}, approvals=[approval],
                                probes={SubjectKind.PROCESS_EFFECT: ProbeRef(pe.PROBE_ID, pe.DIGEST)})
        self.assertEqual((compiled.probe_id, compiled.probe_digest), (pe.PROBE_ID, pe.DIGEST))
        self.assertIsNone(catalog.registry().observation_class(pe.PROBE_ID, pe.DIGEST, compiled))
        inputs = sa.AdmissionInputs(requirements={"R-EFFECT": req}, contracts={contract.id: contract},
                                    approvals=(approval,), specs={compiled.id: compiled},
                                    catalogue=catalog.catalogue(), calibrations=(), registry=catalog.registry())
        plan = types.SimpleNamespace(obligations=[types.SimpleNamespace(product_proof_spec_id=compiled.id)])
        self.assertEqual(sa.check_probe_calibration(plan, inputs),
                         [f"spec {compiled.id}: {pe.PROBE_ID} does not support the observation it asks for"])
        good = BehaviorContract.create(**{**{f: getattr(contract, f) for f in ("id", "requirement_ids", "subject",
                                                                               "observable", "polarity", "subject_absence",
                                                                               "rationale")},
                                          "stimulus": {"scenario": book(call("count"))}})
        ok = compile_spec(good, requirements={"R-EFFECT": req},
                          approvals=[ContractApproval("R-EFFECT", req.requirement_hash, good.id, good.contract_hash,
                                                      "human:pe-adv-1", 0.0, ())],
                          probes={SubjectKind.PROCESS_EFFECT: ProbeRef(pe.PROBE_ID, pe.DIGEST)})
        self.assertEqual(catalog.registry().observation_class(pe.PROBE_ID, pe.DIGEST, ok), "scenario_returns")

    def test_PE_ADV_2_a_leaked_fault_is_a_harness_failure_never_a_verdict(self):
        """A controlled double of the request: the fault table in this process names an attribute of a module whose
        `__setattr__` drops the restoration (store/leaky.py). The probe's source is untouched."""
        s_ = [step("fault", fault="leaky.hook"), call("use")]
        with mock.patch.dict(pe.FAULTS, {"leaky.hook": ("store.leaky", "hook", "OSError")}):
            s = spec("store.leaky:use", [step("fault", fault="leaky.hook"), call(None)], {"returns": "original"})
            self.assertEqual(pe.spec_class(s), "scenario_returns")
            o = self.see(s)
            result = self.run_(s)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertEqual(o.detail, "the harness failed its own scenario: the fault leaky.hook was not restored after step 1")
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
        for point in MeasurementPoint:
            r = route(result, s, point, ObligationRole.INTRODUCE)
            self.assertEqual((r.failure.code, r.failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))
        self.assertIsNone(pe.spec_class(spec("store.leaky:use", s_, {"returns": 0})))   # the real table: refused


# --------------------------------------------------------------------------------------- FM2-EFFECT

class FaultEffect(_Product):
    def test_FM2_EFFECT_1_an_unknown_step_kind_is_INVALID_SPEC_at_admission_before_anything_runs(self):
        s = spec("store.book:Book", book(step("sleep_forever")), {"returns": 0})
        with never_runs():
            result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
        self.assertIsNone(catalog.registry().observation_class(pe.PROBE_ID, pe.DIGEST, s))

    def test_FM2_EFFECT_2_a_fault_restoration_failure_is_HARNESS_FAILED(self):
        with mock.patch.dict(pe.FAULTS, {"leaky.hook": ("store.leaky", "hook", "OSError")}):
            o = self.see(spec("store.leaky:use", [step("fault", fault="leaky.hook"), call(None)], {"returns": "x"}))
        self.assertEqual(o.kind, K.HARNESS_FAILED)
        self.assertIn("was not restored", o.detail)

    def test_FM2_EFFECT_3_an_exception_in_a_non_final_step_refutes_with_the_step_named(self):
        for cls, observable in (("scenario_returns", {"returns": 0}), ("scenario_raises", {"raises": True}),
                                ("scenario_files", {"files": {BOOK: {"absent": True}}})):
            with self.subTest(cls=cls):
                last = expect("boom", "ValueError") if cls == "scenario_raises" else call("count")
                o = self.see(spec("store.book:Book", book(call("boom"), last), observable))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                self.assertEqual(facts_of(o)["refuted"], {"step": 1, "kind": "call", "why": "raised ValueError"})
                self.assertEqual(len(facts_of(o)["trace"]), 2)   # the scenario stopped there

    @unittest.skipUnless(POSIX, "a lingering grandchild in the range's process group (POSIX; the Windows job is the same)")
    def test_FM2_EFFECT_4_a_subprocess_step_that_leaves_a_process_is_the_range_residual_never_the_probe_s(self):
        ranges = []
        probe = ProcessEffectProbe(on_range=ranges.append)
        o = self.see(spec("store.book:Book", book(step("subprocess", argv=["-m", "store", "linger"]), call("count")),
                          {"returns": 0}), probe=probe)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)   # the observation stands
        run = ranges[0]
        self.assertTrue(run.ledger, "the range's release stopped what the step left")   # §17.1: recorded
        self.assertEqual(run.ledger[0]["stage"], "cooperative")
        self.assertEqual(run.members(), [])

    def test_FM2_EFFECT_5_a_second_construct_without_declaration_is_refused(self):
        s = spec("store.book:Book", [construct(BOOK), call("count"), construct(BOOK), call("count")], {"returns": 0})
        with never_runs():
            self.assertIs(self.run_(s).status, ProbeExecutionStatus.INVALID_SPEC)

    def test_FM2_EFFECT_6_a_fault_the_subject_swallows_is_observed_by_the_file_observable(self):
        seeded = [step("workspace", files={"book.jsonl": {"text": "old"}}), construct(BOOK)]
        faulted = [*seeded, step("fault", fault="os.replace"), call("save_quietly", "new")]
        unchanged = {"files": {BOOK: {"equals_before": True}}}
        o = self.see(spec("store.book:Book", faulted, unchanged))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts_of(o)
        self.assertEqual((f["last_returned"], f["trace"][-1]["fired"]), (False, True))   # swallowed, but it fired
        self.assertEqual(self.see(spec("store.book:Book", [*seeded, call("save_quietly", "new")], unchanged)).verdict, R)

    def test_FM2_EFFECT_7_a_harness_that_crashes_before_opening_the_marker_file_is_HARNESS_FAILED(self):
        s = spec("store.book:Book", book(call("count")), {"returns": 0})
        with mock.patch.object(pe, "HARNESS", "import sys\nsys.exit(1)\n"):
            o = self.see(s)
            result = self.run_(s)
        self.assertEqual((o.kind, o.detail), (K.HARNESS_FAILED, "the harness did not start (exit 1, no READY): tool "
                                                                "absent or broken"))
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)

    def test_FM2_EFFECT_8_a_protocol_line_forged_on_stdout_is_captured_bytes_never_protocol(self):
        o = self.see(spec("store.book:Book", book(call("forge")), {"returns": "forged"}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["subject"], "present")

    def test_FM2_EFFECT_9_the_process_ending_during_a_step_refutes_with_that_step(self):
        o = self.see(spec("store.book:Book", book(call("count"), call("hard", 0), call("count")), {"returns": 0}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        self.assertEqual(facts_of(o), {"subject": "present", "hard_exit": True, "exit_code": 0, "trace": [],
                                       "refuted": {"step": 2, "why": "the process ended with exit status 0 before the "
                                                                     "scenario completed"}})

    def test_FM2_EFFECT_10_a_controller_stop_after_DISPATCHED_is_an_interruption_with_no_result(self):
        from aisef2.probe.protocol import ProbeInterrupted
        stops = []
        scratch = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)   # C2-P2-FINDING-003 on Windows
        self.addCleanup(scratch.cleanup)

        def after_dispatch(run):
            # the stop lands after the first step started, read from this evaluation's own protocol file
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and not any(
                    b" STEP " in p.read_bytes() for p in pathlib.Path(scratch.name).glob("*/protocol.log")):
                time.sleep(0.02)
            run.release()

        def stop_it(run):
            stops.append(run)
            threading.Thread(target=after_dispatch, args=(run,), daemon=True).start()
        probe = ProcessEffectProbe(on_range=stop_it, scratch=scratch.name)
        with self.assertRaises(ProbeInterrupted) as interrupted:
            run_probe(probe, spec("store.book:Book", book(call("sleep", 60)), {"returns": 0}, window=15), self.at, env())
        self.assertTrue(stops and stops[0].ledger)
        self.assertEqual(interrupted.exception.stage, stops[0].ledger[-1]["stage"])


# --------------------------------------------------------------------------------------- FM2-PYC-2

class Bytecode(unittest.TestCase):
    def test_FM2_PYC_2_two_checkouts_of_the_same_content_with_different_dates_observe_one_verdict(self):
        """P7-FINDING-001 case 2 against this probe: the collision checkout (stale bytecode whose header matches the
        source's size and whole second) and a second checkout dated away from it observe the source, both."""
        from tests.v2.test_probe_process_effect_bytecode import RETURNS_2, stale_checkout, value_spec
        d = tempfile.TemporaryDirectory(prefix="aisef2-pyc-effect-", ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        tmp = pathlib.Path(d.name)
        self.assertTrue(stale_checkout(tmp / "implementer")["collision"])
        self.assertFalse(stale_checkout(tmp / "verifier", offset_s=100)["collision"])
        a = run_probe(ProcessEffectProbe(), value_spec(RETURNS_2), RevisionRef("a" * 40, str(tmp / "implementer")), env(60))
        b = run_probe(ProcessEffectProbe(), value_spec(RETURNS_2), RevisionRef("a" * 40, str(tmp / "verifier")), env(60))
        self.assertEqual((a.result, b.result), (Executed(S), Executed(S)))


# --------------------------------------------------------------------------------------- identity, Q0

class Identity(_Product):
    def test_PE_Q0_the_module_passes_the_six_probe_rules_with_its_catalog_facts(self):
        sys.path.insert(0, str(ROOT / "validation" / "v2"))
        import probe_static_checks as ps
        src = (ROOT / "aisef2/probe/process_effect.py").read_text(encoding="utf-8")
        facts = {"subject_process": "child_of_harness", "stimulus_shape": "scenario"}
        self.assertEqual(ps.violations("aisef2/probe/process_effect.py", src, ps.SOURCE_RULES, facts), [])
        self.assertEqual(ps.check(ROOT), [])   # catalog closure: registered, digest live, fixtures for every class
        self.assertEqual([name for name, _, _ in ps.child_scripts(ast.parse(src))], ["HARNESS", "SUBPROCESS"])
        e = catalog.entry_for("aisef2/probe/process_effect.py")
        self.assertEqual((e.subject_process, e.stimulus_shape), (facts["subject_process"], facts["stimulus_shape"]))
        # each rule rejects the corresponding defect in this module's own source
        defects = {
            "PROTOCOL_CHANNEL_DISCIPLINE": ('proto.write(line.encode("utf-8"))', 'sys.stdout.write(line)'),
            "SINGLE_PLACEHOLDER_TOKEN": ('value = value.replace(form, "<ws>")', 'value = value.replace(form, "<root>")'),
            "NO_CLOCK_IN_PROBE_FACTS": ("import builtins, hashlib,", "import time, builtins, hashlib,"),
            "CLOSED_DISPATCH_IN_SCENARIO_PROBES": ('    if kind != step["exception"]:\n',
                                                  '    if kind == "x":\n        pass\n    elif kind != step["exception"]:\n'),
        }
        for rule, (before, after) in defects.items():
            with self.subTest(rule=rule):
                self.assertEqual(src.count(before), 1, before)
                broken = src.replace(before, after)
                if rule == "CLOSED_DISPATCH_IN_SCENARIO_PROBES":
                    broken = broken.replace('return {"outcome": "refuted:raised " + kind + ", not " + step["exception"]}',
                                            'return {"outcome": "refuted:raised " + kind + ", not " + step["exception"]}\n'
                                            '    else:\n        pass', 1)
                self.assertTrue(any(v.startswith(rule) for v in ps.violations("aisef2/probe/process_effect.py", broken,
                                                                                ps.SOURCE_RULES, facts)), rule)

    def test_the_catalog_entry_binds_this_probe_as_the_active_process_effect_probe(self):
        e = catalog.active()[SubjectKind.PROCESS_EFFECT]
        self.assertEqual((e.probe_id, e.probe_digest, e.classes, e.cycle), (pe.PROBE_ID, pe.DIGEST, pe.CLASSES, 2))
        self.assertEqual((e.subject_process, e.protocol_channel, e.stimulus_shape, e.fixture_root),
                         ("child_of_harness", "marker_file", "scenario", "process_effect"))
        self.assertIs(e.metadata, pe.METADATA)
        self.assertIs(pe.METADATA.observation_class, pe.spec_class)
        self.assertIsInstance(catalog.catalogue()[SubjectKind.PROCESS_EFFECT], ProcessEffectProbe)
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        with never_runs():
            refused = run_probe(P, spec("store.book:Book", book(call("count")), {"returns": 0}), self.at,
                                env(required=Enforcement.FULL))
        self.assertIs(refused.result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(refused.enforcement, Enforcement.PARTIAL)

    def test_product_verdicts_are_identical_across_developer_test_layouts(self):
        layouts = {"no tests": {}, "tests/ at the root": {"tests/__init__.py": "", "tests/test_book.py": "import store\n"},
                   "broken tests": {"conftest.py": "raise SystemExit(4)\n", "store/test_book.py": "import no_such_module\n"}}
        s = spec("store.book:Book", book(call("append", "a", 1, "r1"), call("verify")),
                 {"returns": {"ok": True, "first_bad": None}})
        seen = {}
        for name, extra in layouts.items():
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
                seen[name] = run_probe(P, s, RevisionRef(SHA, checkout(d, {**PRODUCT, **extra})), env()).result
        self.assertEqual(set(seen.values()), {Executed(S)})


if __name__ == "__main__":
    unittest.main()
