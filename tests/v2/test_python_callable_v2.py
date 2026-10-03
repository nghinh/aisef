"""WP-2.4.1 (C2-P4) — `probe.python_callable_v2`, the second python_callable identity (owner DECISION-6).

PCV2_1 calibration of every declared class at the NEW digest (the four Cycle-1 classes included), and rejection once
the fixtures stop contrasting; PCV2_2 returns_bytes; PCV2_3 equals over a constant, UNSUPPORTED over a callable;
PCV2_4 raises_attrs; PCV2_5 the workspace stimulus; PCV2_6 the Cycle-1 identity keeps resolving through the catalog
while the second identity is the one active probe; PCV2_7 test-layout invariance (invariant IX); PCV2_8 the Cycle-1
semantics this probe inherits unchanged (deadlines per class, absence, exit before the observable, forged protocol
lines, the refusals); PCV2_B1 the controller/subject split (V2.0 release charter §7): a subject cannot forge the
verdict channel — result-shaped lines on its stdout and stderr or in the marker file, an early exit, a stray answer
on its own channel; PCV2_Q0 the probe source rules. Subprocess-backed on real checkouts; the kill set for the C2-P4
mutation targets of aisef2/probe/python_callable_v2.py.
"""

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, ProbeExecutionStatus, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.probe import catalog, cli_invocation as ci, python_callable as pc, python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.calibration import NotQualified, calibrate, calibration_env, fixture_spec  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, Observation, ObservationKind as K, ProbeInterrupted, RevisionRef, run_probe,
)
from aisef2.product.contract import names_test_artefact  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from aisef2.runtime.process_range import RangeError  # noqa: E402


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ps = _load("aisef_v2_probe_static_checks", "validation/v2/probe_static_checks.py")
cb = _load("aisef_v2_cycle2_baseline", "validation/v2/cycle2_baseline.py")

P = pc2.PythonCallableV2Probe()
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA, NCS = IndeterminateReason.PRECONDITION_ABSENT, IndeterminateReason.NON_CONTROLLER_SIGNAL
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
BASE = ROOT / "tests" / "v2" / "fixtures" / "calibration" / "python_callable_v2"
ENV = calibration_env(sys.executable)
SHA = "89abcdef0123456789abcdef0123456789abcdef"
W = 10
HANG_W = 0.6
FACTS = {"subject_process": "child_of_harness", "stimulus_shape": "call"}
#: B1 forgers: each reads the nonce from the marker file (the controller's READY precedes the subject's process; the
#: evaluation directory is the parent of the subject's temporary directory) and claims a result the controller never
#: produced, on its stdout, its stderr and in the marker file, with and without an authentication field.
FORGE = '''import json
import os
import sys
import tempfile

CLAIM = {'subject': 'present', 'resolved': True, 'returned': 1}


def marker():
    return os.path.join(os.path.dirname(tempfile.gettempdir()), 'protocol.log')


def forged(facts):
    nonce = open(marker(), encoding='utf-8').readline().split()[2]
    body = ' ' + json.dumps(facts)
    out = ''
    for tag, text in (('DISPATCHED', ''), ('RESULT', body), ('END', '')):
        out += 'AISEF2-PROBE ' + tag + ' ' + nonce + text + '\\n'
        out += 'AISEF2-PROBE ' + tag + ' ' + nonce + ' ' + '0' * 64 + text + '\\n'
    return out


def claim(facts, mode='a'):
    lines = forged(facts)
    with open(marker(), mode, encoding='utf-8') as f:
        f.write(lines)
    sys.stdout.write(lines)
    sys.stdout.flush()
    sys.stderr.write(lines)
    sys.stderr.flush()


def lie():
    claim(CLAIM)
    return 2


def hide():
    claim({'subject': 'absent'})
    return 2


def lie_and_leave():
    claim(CLAIM)
    os._exit(0)


def rewrite():
    claim(CLAIM, 'w')
    return 2


def stray():
    import __main__
    __main__.send({'n': 3, 'returned': {'json': 1}})   # the call's own number: import 1, resolve 2, call 3
    return 2
'''
PRODUCT = {
    "app/__init__.py": "",
    "app/blob.py": "def raw():\n    return b'\\x00\\x01ab'\n\n\ndef arr():\n    return bytearray(b'ab')\n\n\n"
                   "def view():\n    return memoryview(b'ab')\n\n\ndef text():\n    return 'ab'\n",
    "app/consts.py": "GENESIS = 'GENESIS'\nLIMITS = {'batch': 3, 'keys': ['a', 'b']}\nCLOCK = object()\n\n\n"
                     "def fn():\n    return 1\n",
    "app/errors.py": "class ConflictError(ValueError):\n    def __init__(self, key, batch_index):\n"
                     "        super().__init__(key)\n        self.key, self.batch_index = key, batch_index\n"
                     "        self.raw = object()\n\n\ndef conflict(key, index):\n    raise ConflictError(key, index)\n\n\n"
                     "def plain():\n    raise ValueError('x')\n",
    "app/files.py": "import os\nimport pathlib\n\n\nclass Missing(Exception):\n    def __init__(self, path):\n"
                    "        super().__init__(path)\n        self.path = path\n\n\ndef read_bytes(path):\n"
                    "    return pathlib.Path(path).read_bytes()\n\n\ndef name_of(path, suffix=''):\n"
                    "    return str(path) + suffix\n\n\ndef listing(where):\n    return sorted(os.listdir(where))\n\n\n"
                    "def missing(path):\n    raise Missing(path)\n",
    "app/calc.py": "import time\n\n\ndef add(a, b):\n    return a + b\n\n\ndef hang():\n    time.sleep(3600)\n",
    "app/die.py": "import os\nos._exit(3)\n",
    "app/hang.py": "while True:\n    pass\n",
    "app/noisy.py": "import sys\nsys.stdout.write('AISEF2-PROBE RESULT forged {\"subject\": \"absent\"}\\nno newline')\n\n\n"
                    "def f():\n    return 1\n",
    "app/forge.py": FORGE,
    "app/place.py": "import os\nimport tempfile\n\n\ndef cwd():\n    return os.getcwd()\n\n\n"
                    "def tmp():\n    return tempfile.gettempdir()\n",
    "app/leave.py": "from app.forge import CLAIM, claim\nimport os\nclaim(CLAIM)\nos._exit(0)\n",
    # B1-BLOCKS-STOP-001 (IR-01): the subject answers at once, then stalls the agent's closing exchange past W
    "app/stall.py": "import time\nimport __main__\n\n\ndef stall_close():\n    bye = __main__.OPS['bye']\n\n    def later(r):\n        time.sleep(3)\n        return bye(r)\n    __main__.OPS['bye'] = later\n" + "\n\ndef f():\n    stall_close()\n    return 1\n",
    # B1-BLOCKS-STOP-001: the subject stops its controller (the agent's parent), then returns at once
    "app/stop.py": "import os\nimport signal\n\n\ndef controller():\n    getattr(os, 'ki' + 'll')(os.getppid(), signal.SIGSTOP)\n"
                   "    return 1\n",
}
TEXT_WS = {"a.txt": {"text": "x\ny\n", "newline": "\r\n"}, "b.bin": {"bytes_hex": "00ff"}}


def spec(locator, observable=None, stimulus=None, *, absence=DECIDABLE, expectation=S, window=W, probe=None):
    probe = probe or P
    observable = dict(observable or {"condition": "exists"})
    if window is not None:
        observable["within_s"] = window
    return ProductProofSpec.create(
        contract_id="BC-P2", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": "python_callable", "locator": locator}, "stimulus": stimulus or {},
                     "observable": observable, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


def checkout(files):
    d = tempfile.mkdtemp(prefix="aisef2-rev-")
    for rel, text in files.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def env(timeout=20, required=Enforcement.PARTIAL, interpreter=sys.executable):
    return ExecutionEnv(interpreter, timeout, required)


def never_runs():
    """Patch the probe so building a range at all is a test failure: nothing may run."""
    return mock.patch.object(pc2, "ProcessRange", side_effect=AssertionError("ran"))


def refuses(error):
    """Patch the probe so starting a range fails: the harness cannot launch."""
    return mock.patch.object(pc2, "ProcessRange", mock.Mock(return_value=mock.Mock(start=mock.Mock(side_effect=error))))


class FakeRange:
    """A range whose target writes `tags` (each "TAG" or "TAG body") into the marker file named in the request, tagged
    with the request's nonce and authenticated with its key (B1), then ends with `returncode` (None: never reported);
    nothing of it is left once it ended. `ledger` is what the controller signalled (§9.3)."""

    def __init__(self, tags, returncode, ledger=()):
        self.tags, self.returncode, self.ledger, self.calls = tags, returncode, list(ledger), []

    def __call__(self, name, argv, **kw):
        self.calls.append((name, list(argv)))
        return self

    def start(self):
        req = json.loads(pathlib.Path(self.calls[-1][1][-1]).read_text(encoding="utf-8"))
        key, text = bytes.fromhex(req["key"]), ""
        for tag in self.tags:
            name, _, body = tag.partition(" ")
            text += f"AISEF2-PROBE {name} {req['nonce']} {ci._mac(key, name, body)}" + (f" {body}" if body else "") + "\n"
        pathlib.Path(req["protocol"]).write_text(text, encoding="utf-8")
        return self

    def wait(self, timeout=None):
        return self.returncode

    def members(self):
        return []

    def release(self):
        pass


def faked(*tags, returncode, ledger=()):
    return mock.patch.object(pc2, "ProcessRange", FakeRange(tags, returncode, ledger))


class Requests:
    """Captures the request file of every harness the probe launched (the real ProcessRange runs them)."""

    def __init__(self):
        self.requests = []
        self.real = pc2.ProcessRange

    def __enter__(self):
        def make(name, argv, **kw):
            self.requests.append(json.loads(pathlib.Path(argv[-1]).read_text(encoding="utf-8")))
            return self.real(name, argv, **kw)
        self._p = mock.patch.object(pc2, "ProcessRange", make)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False


class _Revisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = RevisionRef(SHA, checkout(PRODUCT))
        cls.empty = RevisionRef(SHA, checkout({"README.md": "no product yet\n"}))

    def run_(self, s, at=None, e=None, probe=None):
        return run_probe(probe or P, s, at or self.product, e or env()).result

    def see(self, s, at=None, e=None):
        return P.observe(s, at or self.product, e or env())


class Calibration(unittest.TestCase):
    def test_PCV2_1_every_declared_class_has_both_fixtures_asking_for_it(self):
        self.assertEqual(sorted(p.name for p in BASE.iterdir()), sorted(pc2.CLASSES))
        self.assertEqual(sorted(pc2.CLASSES), sorted((*pc.CLASSES, "returns_bytes", "equals", "raises_attrs")))
        for cls in pc2.CLASSES:
            for side in ("positive", "negative"):
                d = BASE / cls / side
                with self.subTest(cls=cls, side=side):
                    self.assertTrue((d / "checkout").is_dir())
                    self.assertEqual(pc2.spec_class(fixture_spec(P, d)), cls)
                    self.assertEqual(names_test_artefact(json.loads((d / "request.json").read_text(encoding="utf-8"))), [])
                    self.assertFalse([p for p in (d / "checkout").rglob("*") if p.name.startswith("test")])

    def test_PCV2_1_a_positive_fixture_uses_the_workspace_stimulus(self):
        request = json.loads((BASE / "returns_bytes" / "positive" / "request.json").read_text(encoding="utf-8"))
        self.assertIn("workspace", request["stimulus"])
        self.assertIn("<ws>/", request["stimulus"]["args"][0])

    def test_PCV2_1_the_probe_is_qualified_for_every_class_at_the_new_digest(self):
        registry = catalog.registry()
        for cls in pc2.CLASSES:
            with self.subTest(cls=cls):
                rec = calibrate(P, cls, BASE / cls / "positive", BASE / cls / "negative", ENV, time.time, registry=registry)
                self.assertEqual((rec.probe_id, rec.probe_digest, rec.observation_class), (P.id, P.digest, cls))
                self.assertNotEqual(rec.probe_digest, pc.DIGEST)   # the Cycle-1 classes too, at the NEW digest

    def test_PCV2_1_the_same_fixtures_reject_it_once_they_stop_contrasting(self):
        registry = catalog.registry()
        for cls in pc2.CLASSES:
            with self.subTest(cls=cls):
                with self.assertRaises(NotQualified):
                    calibrate(P, cls, BASE / cls / "negative", BASE / cls / "negative", ENV, time.time, registry=registry)
                with self.assertRaises(NotQualified):
                    calibrate(P, cls, BASE / cls / "positive", BASE / cls / "positive", ENV, time.time, registry=registry)


class ReturnsBytes(_Revisions):
    def test_PCV2_2_bytes_bytearray_and_memoryview_results_are_observed_as_hex(self):
        for locator, hexed in (("app.blob:raw", "00016162"), ("app.blob:arr", "6162"), ("app.blob:view", "6162")):
            with self.subTest(locator=locator):
                self.assertEqual(self.run_(spec(locator, {"returns_bytes_hex": hexed})), Executed(S))
                self.assertEqual(self.run_(spec(locator, {"returns_bytes_hex": "ff"})), Executed(R))
        seen = self.see(spec("app.blob:raw", {"returns_bytes_hex": "00016162"}))
        self.assertEqual(seen, Observation(K.OBSERVED, S, json.dumps({"subject": "present", "resolved": True,
                                                                     "returned_bytes_hex": "00016162"})))

    def test_PCV2_2_a_str_result_is_REFUTED_and_bytes_never_equal_a_json_value(self):
        self.assertEqual(self.run_(spec("app.blob:text", {"returns_bytes_hex": "6162"})), Executed(R))
        self.assertEqual(self.run_(spec("app.blob:raw", {"returns": "\u0000\u0001ab"})), Executed(R))
        self.assertEqual(self.run_(spec("app.blob:text", {"returns": "ab"})), Executed(S))

    def test_PCV2_2_only_lower_case_even_length_hex_is_a_supported_observable(self):
        with never_runs():
            for bad in ("ABCD", "abc", 12, None, "0x61"):
                with self.subTest(hex=bad):
                    result = self.run_(spec("app.blob:raw", {"returns_bytes_hex": bad}))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
        self.assertEqual(pc2.observation_class({"returns_bytes_hex": "", "within_s": 1}, {}), "returns_bytes")


class Equals(_Revisions):
    def test_PCV2_3_equality_over_a_constant_is_SATISFIED_or_REFUTED_by_its_json_form(self):
        self.assertEqual(self.run_(spec("app.consts:GENESIS", {"equals": "GENESIS"})), Executed(S))
        self.assertEqual(self.run_(spec("app.consts:GENESIS", {"equals": "genesis"})), Executed(R))
        self.assertEqual(self.run_(spec("app.consts:LIMITS", {"equals": {"batch": 3, "keys": ["a", "b"]}})), Executed(S))
        self.assertEqual(self.run_(spec("app.consts:LIMITS", {"equals": {"batch": 3, "keys": ["a"]}})), Executed(R))
        self.assertEqual(self.run_(spec("app.consts:LIMITS.nope", {"equals": 1}, absence=REQUIRES)), Executed(I, PA))
        # a bound method is a callable subject: equality is not offered over it either
        self.assertIs(self.run_(spec("app.consts:LIMITS.keys", {"equals": ["a", "b"]})).status,
                      ProbeExecutionStatus.INVALID_SPEC)

    def test_PCV2_3_an_unserialisable_constant_is_REFUTED_and_says_so(self):
        seen = self.see(spec("app.consts:CLOCK", {"equals": None}))
        self.assertEqual(seen.kind, K.OBSERVED)
        self.assertIs(seen.verdict, R)
        self.assertEqual(json.loads(seen.detail)["returned_unserializable"], "object")

    def test_PCV2_3_equality_over_a_callable_is_UNSUPPORTED_hence_INVALID_SPEC(self):
        s = spec("app.consts:fn", {"equals": 1})
        self.assertEqual(self.see(s), Observation(K.UNSUPPORTED, detail="equality over a callable subject is not offered"))
        result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
        self.assertEqual(result.detail, "equality over a callable subject is not offered")

    def test_PCV2_3_equals_takes_an_empty_stimulus_only(self):
        with never_runs():
            for stim in ({"args": []}, {"kwargs": {}}, {"workspace": {}}):
                with self.subTest(stimulus=stim):
                    self.assertIsNone(pc2.observation_class({"equals": 1, "within_s": 1}, stim))
                    self.assertIs(self.run_(spec("app.consts:GENESIS", {"equals": "GENESIS"}, stim)).status,
                                  ProbeExecutionStatus.INVALID_SPEC)
        self.assertEqual(self.run_(spec("app.consts:NOPE", {"equals": 1}, absence=REQUIRES)), Executed(I, PA))


class RaisesAttrs(_Revisions):
    OBS = {"raises": "ConflictError", "attrs": {"key": "k", "batch_index": 1}}

    def test_PCV2_4_matching_type_and_attributes_are_SATISFIED(self):
        self.assertEqual(self.run_(spec("app.errors:conflict", self.OBS, {"args": ["k", 1]})), Executed(S))
        self.assertEqual(self.run_(spec("app.errors:conflict", {"raises": "ConflictError"}, {"args": ["k", 1]})), Executed(S))
        seen = self.see(spec("app.errors:conflict", self.OBS, {"args": ["k", 1]}))
        self.assertEqual(json.loads(seen.detail), {"subject": "present", "resolved": True, "raised": "ConflictError",
                                                   "raised_attrs": {"batch_index": 1, "key": "k"},
                                                   "raised_attrs_unserializable": []})

    def test_PCV2_4_a_wrong_value_a_missing_attribute_or_a_wrong_type_is_REFUTED(self):
        cases = {
            "wrong value": spec("app.errors:conflict", self.OBS, {"args": ["k", 2]}),
            "missing attribute": spec("app.errors:conflict", {"raises": "ConflictError", "attrs": {"key": "k", "nope": 1}},
                                      {"args": ["k", 1]}),
            "wrong type": spec("app.errors:conflict", {"raises": "KeyError", "attrs": {"key": "k"}}, {"args": ["k", 1]}),
            "unserialisable attribute": spec("app.errors:conflict", {"raises": "ConflictError", "attrs": {"raw": None}},
                                             {"args": ["k", 1]}),
            "nothing raised": spec("app.calc:add", self.OBS, {"args": [1, 2]}),
        }
        for name, s in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.run_(s), Executed(R))
        seen = self.see(cases["unserialisable attribute"])
        self.assertEqual(json.loads(seen.detail)["raised_attrs_unserializable"], ["raw"])

    def test_PCV2_4_attrs_are_a_non_empty_mapping_of_identifiers(self):
        with never_runs():
            for obs in ({"raises": "ConflictError", "attrs": {}}, {"raises": "ConflictError", "attrs": {"a b": 1}},
                        {"raises": "ConflictError", "attrs": [1]}, {"raises": "not an identifier", "attrs": {"a": 1}},
                        {"raises": 5, "attrs": {"a": 1}}, {"attrs": {"a": 1}}):
                with self.subTest(observable=obs):
                    self.assertIsNone(pc2.observation_class({**obs, "within_s": 1}, {}))
                    self.assertIs(self.run_(spec("app.errors:conflict", obs, {"args": ["k", 1]})).status,
                                  ProbeExecutionStatus.INVALID_SPEC)


class Workspace(_Revisions):
    def test_PCV2_5_files_are_written_byte_exactly_with_the_declared_newline(self):
        cases = (("<ws>/a.txt", b"x\r\ny\r\n"), ("<ws>/b.bin", b"\x00\xff"))
        for path, data in cases:
            with self.subTest(file=path):
                s = spec("app.files:read_bytes", {"returns_bytes_hex": data.hex()}, {"workspace": TEXT_WS, "args": [path]})
                self.assertEqual(self.run_(s), Executed(S))
        lf = {"a.txt": {"text": "x\ny\n", "newline": "\n"}}
        self.assertEqual(self.run_(spec("app.files:read_bytes", {"returns_bytes_hex": b"x\ny\n".hex()},
                                        {"workspace": lf, "args": ["<ws>/a.txt"]})), Executed(S))
        self.assertEqual(self.run_(spec("app.files:read_bytes", {"returns_bytes_hex": b"x\r\ny\r\n".hex()},
                                        {"workspace": lf, "args": ["<ws>/a.txt"]})), Executed(R))
        self.assertEqual(self.run_(spec("app.files:listing", {"returns": ["a.txt", "b.bin"]},
                                        {"workspace": TEXT_WS, "args": ["<ws>"]})), Executed(S))

    def test_PCV2_5_the_placeholder_is_substituted_in_args_and_kwargs_and_the_path_replaced_back(self):
        s = spec("app.files:name_of", {"returns": "<ws>/a.txt|<ws>"},
                 {"workspace": TEXT_WS, "args": ["<ws>/a.txt"], "kwargs": {"suffix": "|<ws>"}})
        with Requests() as launched:
            seen = self.see(s)
        self.assertEqual(seen, Observation(K.OBSERVED, S, json.dumps({"subject": "present", "resolved": True,
                                                                     "returned": "<ws>/a.txt|<ws>"})))
        [request] = launched.requests
        ws = request["args"][0].removesuffix("/a.txt")
        self.assertTrue(os.path.isabs(ws) and "<ws>" not in ws, ws)
        self.assertEqual(request["kwargs"], {"suffix": "|" + ws})
        self.assertNotIn(ws, seen.detail)   # the evaluation's own path never reaches the verdict or its detail
        # a raised value is replaced back too
        self.assertEqual(self.run_(spec("app.files:missing", {"raises": "Missing", "attrs": {"path": "<ws>/nope"}},
                                        {"args": ["<ws>/nope"]})), Executed(S))
        self.assertEqual(self.run_(spec("app.files:missing", {"raises": "Missing", "attrs": {"path": "<ws>/other"}},
                                        {"args": ["<ws>/nope"]})), Executed(R))

    def test_PCV2_5_every_evaluation_gets_a_fresh_workspace(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-scratch-") as scratch:
            probe = pc2.PythonCallableV2Probe(scratch=scratch)
            s = spec("app.files:listing", {"returns": ["a.txt", "b.bin"]}, {"workspace": TEXT_WS, "args": ["<ws>"]},
                     probe=probe)
            with Requests() as launched:
                for _ in range(2):
                    self.assertEqual(self.run_(s, probe=probe), Executed(S))
            first, second = (r["args"][0] for r in launched.requests)
            self.assertNotEqual(first, second)
            for ws in (first, second):
                self.assertEqual(pathlib.Path(ws).parent.parent, pathlib.Path(scratch).resolve())
                self.assertEqual(sorted(os.listdir(ws)), ["a.txt", "b.bin"])
                self.assertEqual(pathlib.Path(ws, "a.txt").read_bytes(), b"x\r\ny\r\n")
        # without a workspace the placeholder still resolves, to an empty directory of the evaluation's own
        self.assertEqual(self.run_(spec("app.files:listing", {"returns": []}, {"args": ["<ws>"]})), Executed(S))

    def test_PCV2_5_a_malformed_workspace_is_refused_before_anything_runs(self):
        good = {"a.txt": {"text": "x", "newline": "\n"}}
        with never_runs():
            for ws in ([], {"a/b": {"text": "x", "newline": "\n"}}, {"..": {"bytes_hex": "00"}}, {"a": "x"},
                       {"a": {"text": "x", "newline": "\r"}}, {"a": {"text": 1, "newline": "\n"}},
                       {"a": {"bytes_hex": "0"}}, {"a": {"bytes_hex": "0G"}}, {"a": {"text": "x"}},
                       {"a": {"text": "x", "newline": "\n", "bytes_hex": "00"}}):
                with self.subTest(workspace=ws):
                    self.assertIsNone(pc2.observation_class({"returns": 1, "within_s": 1}, {"workspace": ws}))
                    result = self.run_(spec("app.calc:add", {"returns": 3}, {"workspace": ws, "args": [1, 2]}))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
            for obs in ({"condition": "exists"}, {"equals": 1}):
                self.assertIsNone(pc2.observation_class({**obs, "within_s": 1}, {"workspace": good}))
        for obs in ({"returns": 1}, {"returns_bytes_hex": "00"}, {"raises": "E"}, {"raises": "E", "attrs": {"a": 1}},
                    {"blocks": True}):
            with self.subTest(observable=obs):
                self.assertIsNotNone(pc2.observation_class({**obs, "within_s": 1}, {"workspace": good}))
                self.assertIsNotNone(pc2.observation_class({**obs, "within_s": 1}, {"workspace": {}}))


class Identity(_Revisions):
    def test_PCV2_6_the_cycle1_identity_is_unchanged_and_the_second_is_its_own(self):
        self.assertEqual(pc.DIGEST, cb.CYCLE1_PROBE["digest"])
        # B1: the subject's process and the protocol reader are cli_invocation's, so its source is one of this digest's
        self.assertEqual(tuple(pc2.PROBE_SOURCES), ("probe/protocol.py", "probe/python_callable.py",
                                                    "probe/cli_invocation.py", "probe/python_callable_v2.py"))
        self.assertEqual((pc2.PROBE_ID, P.id), ("probe.python_callable_v2", "probe.python_callable_v2"))
        self.assertNotEqual(P.digest, pc.DIGEST)
        self.assertEqual((pc2.METADATA.probe_id, pc2.METADATA.probe_digest), (P.id, P.digest))
        self.assertIs(pc2.METADATA.observation_class, pc2.spec_class)
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        # the subject no longer runs in the harness's process: cli_invocation's weakest path, not Cycle 1's
        self.assertEqual(pc2.WEAKEST_PATH, ci.WEAKEST_PATH)
        self.assertNotEqual(pc2.WEAKEST_PATH, pc.WEAKEST_PATH)

        def digest_of(files):  # the composition, stated here rather than taken from the module
            h = hashlib.sha256()
            for rel, data in files:
                h.update(rel.encode() + b"\0" + data + b"\0")
            return h.hexdigest()
        files = [(rel, (ROOT / "aisef2" / rel).read_bytes().replace(b"\r\n", b"\n")) for rel in pc2.PROBE_SOURCES]
        self.assertEqual(digest_of(files), P.digest)
        for i, (rel, data) in enumerate(files):
            with self.subTest(source=rel):
                self.assertNotEqual(digest_of(files[:i] + [(rel, data + b"# changed\n")] + files[i + 1:]), P.digest)
                self.assertNotEqual(digest_of(files[:i] + files[i + 1:]), P.digest)
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import aisef2.probe.python_callable_v2 as m; "
                "print(m.PythonCallableV2Probe.digest)")
        out = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(out.stdout.strip(), P.digest)

    def test_PCV2_6_a_cycle1_spec_still_resolves_and_runs_while_the_second_identity_is_the_active_one(self):
        registry = catalog.registry()
        c1 = spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}, probe=pc.PythonCallableProbe())
        self.assertEqual((c1.probe_id, c1.probe_digest), (pc.PROBE_ID, cb.CYCLE1_PROBE["digest"]))
        self.assertEqual(registry.observation_class(pc.PROBE_ID, pc.DIGEST, c1), "returns")
        self.assertEqual(run_probe(pc.PythonCallableProbe(), c1, self.product, env()).result, Executed(S))
        c2 = spec("app.calc:add", {"returns": 3}, {"args": [1, 2]})
        self.assertEqual(registry.observation_class(pc2.PROBE_ID, pc2.DIGEST, c2), "returns")
        self.assertIsNone(registry.observation_class(pc.PROBE_ID, pc.DIGEST, spec("app.blob:raw", {"returns_bytes_hex": "00"},
                                                                                  probe=pc.PythonCallableProbe())))
        # each probe refuses the other's binding
        self.assertRegex(self.run_(c1).detail, "^the spec is bound to probe.python_callable@")
        self.assertRegex(self.run_(c2, probe=pc.PythonCallableProbe()).detail, "^the spec is bound to probe.python_callable_v2@")
        self.assertEqual(catalog.problems_of(catalog.CATALOG), [])
        # the python_callable kind's entries: other kinds may be registered and active beside it (the integrated
        # Cycle-2 catalog holds file_artifact, cli_invocation and process_effect too)
        active = catalog.active()
        self.assertIn(SubjectKind.PYTHON_CALLABLE, active)
        self.assertEqual((active[SubjectKind.PYTHON_CALLABLE].probe_id, active[SubjectKind.PYTHON_CALLABLE].cycle),
                         (pc2.PROBE_ID, 2))
        self.assertIsInstance(catalog.catalogue()[SubjectKind.PYTHON_CALLABLE], pc2.PythonCallableV2Probe)
        mine = [e for e in catalog.CATALOG if e.subject_kind is SubjectKind.PYTHON_CALLABLE]
        self.assertEqual([(e.probe_id, e.probe_digest, e.active, e.cycle) for e in mine],
                         [(pc.PROBE_ID, cb.CYCLE1_PROBE["digest"], False, 1), (pc2.PROBE_ID, pc2.DIGEST, True, 2)])
        self.assertEqual([i for i in catalog.probes_by_id() if i in (pc.PROBE_ID, pc2.PROBE_ID)], [pc.PROBE_ID, pc2.PROBE_ID])
        self.assertEqual(len([e for e in mine if e.active]), 1)


class LayoutInvariance(unittest.TestCase):
    """Invariant IX: product verdicts are identical whatever the developer's test layout."""

    LAYOUTS = {
        "no tests": {},
        "tests/ at the root": {"tests/__init__.py": "", "tests/test_blob.py": "from app.blob import raw\n"},
        "a test beside the subject": {"app/test_blob.py": "import no_such_module\n"},
        "broken tests": {"tests/test_blob.py": "def (:\n", "conftest.py": "raise SystemExit(4)\n"},
    }
    SPECS = {"exists": spec("app.calc:add"), "absent": spec("app.telemetry:send"),
             "requires absent": spec("app.telemetry:send", absence=REQUIRES),
             "returns": spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}),
             "returns_bytes": spec("app.blob:raw", {"returns_bytes_hex": "00016162"}),
             "equals": spec("app.consts:GENESIS", {"equals": "GENESIS"}),
             "raises_attrs": spec("app.errors:conflict", RaisesAttrs.OBS, {"args": ["k", 1]}),
             "workspace": spec("app.files:read_bytes", {"returns_bytes_hex": "00ff"},
                               {"workspace": TEXT_WS, "args": ["<ws>/b.bin"]})}

    def test_PCV2_7_product_verdicts_are_identical_across_test_layouts(self):
        seen = {}
        for name, extra in self.LAYOUTS.items():
            at = RevisionRef(SHA, checkout({**PRODUCT, **extra}))
            seen[name] = {k: run_probe(P, s, at, env()).result for k, s in self.SPECS.items()}
        first = next(iter(seen.values()))
        self.assertEqual(first, {"exists": Executed(S), "absent": Executed(R), "requires absent": Executed(I, PA),
                                 "returns": Executed(S), "returns_bytes": Executed(S), "equals": Executed(S),
                                 "raises_attrs": Executed(S), "workspace": Executed(S)})
        for name, results in seen.items():
            with self.subTest(layout=name):
                self.assertEqual(results, first)


class Cycle1Semantics(_Revisions):
    """What this probe inherits unchanged: the per-class meaning of an expired window (§9.2), absence, a subject that
    ends the process, a forged protocol line, the refusals — and the exit-at-the-deadline edge of the stream/exit
    split (§9.4)."""

    def test_PCV2_8_the_deadline_verdict_of_every_class(self):
        cases = {"returns": ({"returns": 3}, R), "raises": ({"raises": "ValueError"}, R), "blocks": ({"blocks": True}, S),
                 "returns_bytes": ({"returns_bytes_hex": "00"}, R),
                 "raises_attrs": ({"raises": "ValueError", "attrs": {"a": 1}}, R)}
        for cls, (obs, want) in cases.items():
            with self.subTest(cls=cls):
                self.assertEqual(self.see(spec("app.calc:hang", obs, window=HANG_W)),
                                 Observation(K.SUBJECT_DEADLINE, want, f"the subject's 0.6s observation window expired ({cls})"))
        for cls, obs in (("exists", {"condition": "exists"}), ("equals", {"equals": 1})):   # the import never finishes
            with self.subTest(cls=cls):
                self.assertEqual(self.see(spec("app.hang:f", obs, window=HANG_W)),
                                 Observation(K.SUBJECT_DEADLINE, R, f"the subject's 0.6s observation window expired ({cls})"))
        self.assertEqual(pc2.ON_DEADLINE, {c: (S if c == "blocks" else R) for c in pc2.CLASSES})
        self.assertEqual(self.run_(spec("app.calc:add", {"blocks": True}, {"args": [1, 2]})), Executed(R))
        self.assertEqual(self.see(spec("app.calc:hang", {"blocks": True}, window=1)),   # an integral window is written 1s, not 1.0s
                         Observation(K.SUBJECT_DEADLINE, S, "the subject's 1s observation window expired (blocks)"))

    def test_PCV2_8_absence_exit_and_forgery_are_what_they_were(self):
        self.assertEqual(self.see(spec("json:dumps", absence=REQUIRES)),
                         Observation(K.SUBJECT_ABSENT, R, "resolves only outside the revision"))
        self.assertEqual(self.run_(spec("json:dumps", absence=REQUIRES)), Executed(I, PA))
        self.assertEqual(self.run_(spec("app.gone:f", absence=REQUIRES)), Executed(I, PA))
        self.assertEqual(self.run_(spec("app.telemetry:send")), Executed(R))
        self.assertEqual(self.see(spec("app.die:f")),
                         Observation(K.OBSERVED, R, "the subject ended the process before the observable (exit 3)"))
        self.assertEqual(self.run_(spec("app.noisy:f", {"returns": 1})), Executed(S))
        self.assertEqual(self.see(spec("app.calc:add", {"returns": 3}, {"args": [1], "kwargs": {"b": 2}})),
                         Observation(K.OBSERVED, S, json.dumps({"subject": "present", "resolved": True, "returned": 3})))
        self.assertEqual(self.run_(spec("app.calc:add", {"returns": 4}, {"args": [1, 2]})), Executed(R))
        self.assertEqual(self.run_(spec("app.errors:plain", {"raises": "KeyError"})), Executed(R))

    def test_PCV2_8_refusals_name_what_is_refused(self):
        other = ProductProofSpec.create(**{**{f: getattr(spec("app.calc:add"), f) for f in (
            "contract_id", "probe_id", "probe_digest", "candidate_expectation", "compiler_id", "compiler_digest")},
            "probe_input": {**spec("app.calc:add").probe_input, "subject": {"kind": "file_artifact", "locator": "a"}}})
        cases = [
            (other, "subject kind 'file_artifact' is not python_callable"),
            (spec("app/calc.py:add"), "locator 'app/calc.py:add' is not module.path:attr — a path is never accepted"),
            (spec("app.calc:add", {"stdout": "x"}), f"observable/stimulus is not a supported class {pc2.CLASSES} with a "
                                                    "bounded window (within_s); refused, not degraded"),
        ]
        with never_runs():
            for s, detail in cases:
                with self.subTest(detail=detail):
                    self.assertEqual(self.see(s), Observation(K.UNSUPPORTED, detail=detail))
                    self.assertIs(self.run_(s).status, ProbeExecutionStatus.INVALID_SPEC)
            for obs, stim in (({"returns": 1}, {"argv": ["x"]}), ({"condition": "exists"}, {"args": [1]}),
                              ({"blocks": 1}, {}), ({"returns": 1, "returns_bytes_hex": "00"}, {})):
                with self.subTest(observable=obs, stimulus=stim):
                    self.assertIs(self.run_(spec("app.calc:add", obs, stim)).status, ProbeExecutionStatus.INVALID_SPEC)
            self.assertIs(self.run_(spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}, window=None)).status,
                          ProbeExecutionStatus.INVALID_SPEC)
            self.assertIsNone(pc2.spec_class(other))
        gone = os.path.join(self.empty.root, "no-python")
        self.assertEqual(self.see(spec("app.calc:add"), e=env(interpreter=gone)),
                         Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"))
        self.assertEqual(self.see(spec("app.calc:add"), at=RevisionRef(SHA, os.path.join(self.empty.root, "gone"))),
                         Observation(K.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing"))
        with mock.patch.object(pc2, "HARNESS", "import time\ntime.sleep(3600)\n"):
            watchdog = self.run_(spec("app.calc:add"), e=env(timeout=1.0))
        self.assertIs(watchdog.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertEqual(watchdog.detail, "harness timeout: no READY within 1s — the observation mechanism did not operate")
        self.assertIs(self.run_(spec("app.calc:add"), e=env(required=Enforcement.FULL)).status, ProbeExecutionStatus.UNRUNNABLE)
        with tempfile.TemporaryDirectory(prefix="aisef2-scratch-") as scratch:
            inside = pc2.PythonCallableV2Probe(scratch=os.path.join(scratch, "in-tree"))
            os.mkdir(os.path.join(scratch, "in-tree"))
            at = RevisionRef(SHA, scratch)
            result = self.run_(spec("app.calc:add"), at=at, probe=inside)
            self.assertEqual((result.status, result.detail), (ProbeExecutionStatus.UNRUNNABLE,
                                                              "the evaluation directory lies inside the revision checkout: refused"))
            missing = pc2.PythonCallableV2Probe(scratch=os.path.join(scratch, "no-such"))
            result = self.run_(spec("app.calc:add"), probe=missing)
            self.assertEqual((result.status, result.detail), (ProbeExecutionStatus.UNRUNNABLE,
                                                              "the evaluation directory cannot be created: FileNotFoundError"))
        for error in (RangeError("no anchor"), OSError("cannot launch")):   # the range refuses to start, or the OS does
            with refuses(error):
                result = self.run_(spec("app.calc:add"))
            self.assertEqual((result.status, result.detail),
                             (ProbeExecutionStatus.UNRUNNABLE, f"the harness cannot launch: {type(error).__name__}"))
        with mock.patch.object(pc2, "_write_workspace", side_effect=OSError("disk full")), never_runs():
            result = self.run_(spec("app.files:listing", {"returns": []}, {"workspace": TEXT_WS, "args": ["<ws>"]}))
        self.assertEqual((result.status, result.detail),
                         (ProbeExecutionStatus.UNRUNNABLE, "the workspace cannot be written: OSError"))

    def test_PCV2_8_the_protocol_reader_never_holds_the_interpreter_open(self):
        """B1: the parent reads the protocol by polling the marker file and starts no thread of its own (§9.4); the
        controller's one reader of the subject's channel is a daemon thread (§17.1), so a subject's process that holds
        the channel open never keeps the controller alive."""
        started = []
        real = threading.Thread

        class Spy(real):
            def __init__(self, *a, **kw):
                started.append(kw.get("daemon"))
                super().__init__(*a, **kw)
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "resolved": true}', returncode=0), \
                mock.patch.object(threading, "Thread", Spy):
            self.assertEqual(self.run_(spec("app.calc:add")), Executed(S))
        self.assertEqual(started, [])
        self.assertEqual(pc2.HARNESS.count("threading.Thread("), 1)
        self.assertIn("threading.Thread(target=pump, daemon=True)", pc2.HARNESS)

    def test_PCV2_8_the_stream_and_the_exit_stay_two_facts(self):
        """B1: how the subject's process ended is the controller's RESULT, which outlives it; the controller's own
        process ending with no RESULT is the observation mechanism failing; the exit stays lifecycle evidence (§9.4)."""
        s = spec("app.calc:add", {"blocks": True}, {"args": [1, 2]}, window=0.4)
        with faked("READY", "DISPATCHED", returncode=None), mock.patch.object(pc2, "_COLLECT_S", 0.05):
            self.assertEqual(self.run_(s).detail, "the harness process ended and its exit status was never reported")
        for code in (0, 3):   # the controller ended with no RESULT, whatever its status
            with faked("READY", "DISPATCHED", returncode=code):
                self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the probe's controller ended without "
                                                                                   f"a result (exit {code})"))
                self.assertIs(self.run_(s).status, ProbeExecutionStatus.UNRUNNABLE)
        hard = {"subject": "present", "hard_exit": True, "exit_code": 3}   # the subject's process ended by a status
        with faked("READY", "DISPATCHED", "RESULT " + json.dumps(hard), returncode=0):
            self.assertEqual(self.see(s), Observation(K.OBSERVED, R, "the subject ended the process before the observable (exit 3)"))
        ladder = [{"stage": "terminate", "signal": "SIGTERM"}]
        with faked("READY", "DISPATCHED", 'RESULT {"subject_signal": 9}', returncode=0):   # by a signal (§9.3)
            self.assertEqual(self.see(s), Observation(K.NON_CONTROLLER_SIGNAL, detail="the subject's process ended by "
                                                      "signal 9 after DISPATCHED, and this controller's signal ledger is "
                                                      "empty: it did not send it"))
            self.assertEqual(self.run_(s), Executed(I, NCS))
        with faked("READY", "DISPATCHED", 'RESULT {"subject_signal": 9}', returncode=0, ledger=ladder), \
                self.assertRaises(ProbeInterrupted):
            self.see(s)   # the controller stopped it: an interruption, never a measurement
        for facts in ({"subject": "present", "tampered": "x"}, {"subject": "present", "resolved": True, "returned": 3}):
            with faked("READY", "DISPATCHED", "RESULT " + json.dumps(facts), returncode=0):
                self.assertEqual(self.see(s), Observation(K.OBSERVED, R, json.dumps(facts)))
        with faked("READY", "DISPATCHED", 'RESULT {"harness_failure": "the harness raised KeyError"}', returncode=0):
            self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the harness raised KeyError"))
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "resolved": true, "unsupported": "u"}',
                   returncode=0):
            self.assertEqual(self.see(s), Observation(K.UNSUPPORTED, detail="u"))
        with faked("READY", "DISPATCHED", returncode=-9):
            self.assertEqual(self.run_(s), Executed(I, NCS))
        with faked("READY", "DISPATCHED", returncode=-9, ledger=ladder), self.assertRaises(ProbeInterrupted):
            self.see(s)
        with faked("READY", "DISPATCHED", returncode=0):
            self.run_(s)
            name, argv = pc2.ProcessRange.calls[-1]
        self.assertEqual(name, f"probe {s.id}")
        self.assertEqual(pathlib.Path(argv[-1]).name, "request.json")
        with faked("READY", returncode=0):
            self.assertEqual(self.run_(s).detail, "the harness did not start (exit 0, no DISPATCHED): tool absent or broken")

    def test_PCV2_8_the_request_names_the_subject_process_and_leaves_no_secret_behind(self):
        """B1 + B6: the request carries the key and the subject process's settings — the shared agent, the
        controller's fresh bytecode prefix, the checkout as its working directory (Cycle 1's), the scrubbed
        environment with the evaluation's own temporary directory; the controller empties it before the subject's
        process exists."""
        seen = {}
        real_start = pc2.ProcessRange.start

        def start(run):
            seen["at_start"] = json.loads(pathlib.Path(run._argv[-1]).read_text(encoding="utf-8"))
            seen["argv"] = run._argv
            return real_start(run)
        with tempfile.TemporaryDirectory(prefix="aisef2-scratch-") as scratch:
            probe = pc2.PythonCallableV2Probe(scratch=scratch)
            with mock.patch.object(pc2.ProcessRange, "start", start):
                self.assertEqual(run_probe(probe, spec("app.files:listing", {"returns": []}, {"args": ["<ws>"]},
                                                       probe=probe), self.product, env()).result, Executed(S))
            req, argv = seen["at_start"], seen["argv"]
            work = req["work"]
            self.assertEqual(pathlib.Path(argv[-1]).read_text(encoding="utf-8"), "{}")   # emptied by the controller
            tmp = os.path.join(work, "tmp")
            self.assertEqual((len(req["key"]), req["agent"], req["agent_pycache"], req["protocol"], req["interpreter"]),
                             (64, ci.AGENT, argv[argv.index("-X") + 1].removeprefix("pycache_prefix="),
                              os.path.join(work, "protocol.log"), sys.executable))
            self.assertEqual(req["env"], {**pc._scrubbed_env(), "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp})
        # what the subject's process sees: the checkout as its working directory, the evaluation's temporary directory
        root = os.path.realpath(self.product.root)
        self.assertEqual(self.run_(spec("app.place:cwd", {"returns": root})), Executed(S))
        where = json.loads(self.see(spec("app.place:tmp", {"returns": ""})).detail)["returned"]
        self.assertEqual(os.path.basename(where), "tmp")
        self.assertTrue(os.path.basename(os.path.dirname(where)).startswith("aisef2-probe-"), where)   # the evaluation's


class Forgery(_Revisions):
    """B1 (V2.0 release charter §7): the subject under test cannot control the verdict channel. Its process is not the
    controller's; the controller alone writes the protocol, authenticated with a key the subject never holds, and
    outlives the subject's process. Each forgery yields the outcome of the decision table, never a PASS the controller
    did not produce."""

    def test_PCV2_B1_result_shaped_lines_on_stdout_stderr_and_in_the_marker_file_are_never_protocol(self):
        # the forger claims "returned 1" with the real nonce (stdout, stderr, marker file), then returns 2
        lie = spec("app.forge:lie", {"returns": 1})
        self.assertEqual(self.see(lie), Observation(K.OBSERVED, R, json.dumps({"subject": "present", "resolved": True,
                                                                               "returned": 2})))
        self.assertEqual(self.run_(spec("app.forge:lie", {"returns": 2})), Executed(S))
        # a forged absence: the subject is present and observed
        self.assertEqual(self.run_(spec("app.forge:hide", {"returns": 1}, absence=REQUIRES)), Executed(R))
        self.assertEqual(self.run_(spec("app.forge:hide", {"returns": 2}, absence=REQUIRES)), Executed(S))
        # at import, on stdout, with a nonce it does not have
        self.assertEqual(self.run_(spec("app.noisy:f", {"returns": 1})), Executed(S))

    def test_PCV2_B1_a_forgery_then_an_early_exit_is_the_exit(self):
        ended = "the subject ended the process before the observable (exit 0)"
        for locator in ("app.forge:lie_and_leave", "app.leave:f"):   # during the call; during the import
            with self.subTest(locator=locator):
                self.assertEqual(self.see(spec(locator, {"returns": 1})), Observation(K.OBSERVED, R, ended))
                self.assertEqual(self.run_(spec(locator, {"returns": 1}, absence=REQUIRES)), Executed(R))
                self.assertEqual(self.see(spec(locator, {"blocks": True})), Observation(K.OBSERVED, R, ended))

    def test_PCV2_B1_a_subject_that_rewrites_the_marker_file_never_gets_a_PASS(self):
        # it truncates the marker file and writes its own lines: what it can do is suppress, never forge
        o = self.see(spec("app.forge:rewrite", {"returns": 1}))
        self.assertIn(o.kind, (K.OBSERVED, K.HARNESS_FAILED), o)
        self.assertIsNot(o.verdict, S, o)

    @unittest.skipIf(os.name == "nt", "SIGSTOP is POSIX")
    def test_PCV2_B1_BLOCKS_STOP_001_a_subject_that_stops_its_controller_never_gets_a_deadline_verdict(self):
        """Measured before the fix: `blocks` came back SUBJECT_DEADLINE SATISFIED although the call returned, because a
        stopped controller still counted as a live range member at W. The deadline is now the controller's own
        authenticated statement: a controller that is stopped says nothing, and that is no verdict."""
        silent = "the probe's controller reported nothing by the end of the subject's 1s window and the 3s harness watchdog"
        for observable in ({"blocks": True}, {"returns": 1}):
            with self.subTest(observable=observable):
                self.assertEqual(self.see(spec("app.stop:controller", observable, window=1), e=env(timeout=3)),
                                 Observation(K.HARNESS_FAILED, None, silent))
        # IR-01: a call that answered at once and then stalls the closing exchange past W is the answer, not a deadline
        o = self.see(spec("app.stall:f", {"blocks": True}, window=1), e=env(timeout=10))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o)
        self.assertEqual(json.loads(o.detail)["returned"], 1)
        # a subject that really blocks is still the controller's deadline
        self.assertEqual(self.see(spec("app.hang:f", {"blocks": True}, window=HANG_W)),
                         Observation(K.SUBJECT_DEADLINE, S, f"the subject's {HANG_W:g}s observation window expired (blocks)"))

    def test_PCV2_B1_an_answer_on_the_subjects_channel_the_agent_did_not_write_is_REFUTED(self):
        # the subject writes an answer to the call's own request number on its process's channel, then returns 2
        o = self.see(spec("app.forge:stray", {"returns": 1}))
        self.assertEqual(o, Observation(K.OBSERVED, R, json.dumps({"subject": "present", "tampered": "an answer on the "
                                                                   "subject's channel is not the agent's"})))


class Q0(unittest.TestCase):
    REL = "aisef2/probe/python_callable_v2.py"

    def test_PCV2_Q0_the_probe_source_rules_pass_on_this_module(self):
        src = (ROOT / self.REL).read_text(encoding="utf-8")
        self.assertEqual(ps.violations(self.REL, src, ps.SOURCE_RULES, FACTS), [])
        self.assertEqual(ps.check(ROOT), [])
        [(name, _, inner)] = ps.child_scripts(__import__("ast").parse(src))
        self.assertEqual(name, "HARNESS")   # the controller; the subject's process is cli_invocation.AGENT
        imported = {a.name for n in __import__("ast").walk(inner) if isinstance(n, __import__("ast").Import) for a in n.names}
        self.assertEqual(imported & {"time", "datetime"}, set())
        e = catalog.entry_for(self.REL)
        self.assertEqual((e.subject_process, e.protocol_channel, e.stimulus_shape, e.cycle),
                         ("child_of_harness", "marker_file", "call", 2))
        # the channel rule is what rejects a controller that puts its protocol on the subject's stdout
        self.assertEqual(src.count('    proto.write((req["mark"]'), 1)
        forged = src.replace('    proto.write((req["mark"]', '    sys.stdout.write((req["mark"]')
        self.assertTrue(any("PROTOCOL_CHANNEL_DISCIPLINE" in v for v in ps.violations(self.REL, forged, ps.SOURCE_RULES, FACTS)))


if __name__ == "__main__":
    unittest.main()
