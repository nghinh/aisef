"""WP-2.2.1 — the `cli_invocation` probe on real checkouts (RFC §9, §9.2, §9.3, §9.4, §10.2; F5; DESIGN-CHECK-1).

CLI-1..9 and CLI-Q0 (the harness), the Q3 fault families FM2-CLI-HARNESS-1..4, FM2-CLI-SUBJECT-1..6,
FM2-CLI-STREAM-1..5 and the bytecode family FM2-PYC-CLI-1..4 (P7-FINDING-001 re-run against this probe). Subprocess
backed: the kill set for the harness targets of `aisef2/probe/cli_invocation.py` (observe, the watch loop, the
marker-file protocol, the hard-exit rule, the harness-failure rule); the pure functions are killed by
tests/v2/test_c2_cli_verdicts.py. Lives at the tests/v2 root like the other Cycle-2 modules: the test tiers are a
closed enum of the frozen invariant registry, and a new package under tests/v2 would fail registration.
"""

import contextlib
import hashlib
import importlib.util
import json
import os
import pathlib
import py_compile
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, MeasurementPoint, ObligationRole, Owner, ProbeExecutionStatus,
    SubjectAbsence, SubjectKind,
)
from aisef2.control.owner import FailureCode  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.probe import catalog, cli_invocation as ci  # noqa: E402
from aisef2.probe.cli_invocation import CliInvocationProbe  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, Observation, ObservationKind as K, ProbeInterrupted, RevisionRef, classify_failure, run_probe,
)
from aisef2.product.outcome import Executed, IndeterminateReason, contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = CliInvocationProbe()
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA, NCS = IndeterminateReason.PRECONDITION_ABSENT, IndeterminateReason.NON_CONTROLLER_SIGNAL
SAT, UNSAT, INDET = ContractSatisfaction.SATISFIED, ContractSatisfaction.UNSATISFIED, ContractSatisfaction.INDETERMINATE
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
POSIX = os.name == "posix"
SHA = "89abcdef0123456789abcdef0123456789abcdef"
W = 10          # a window generous enough for any runner; the hanging cases use HANG_W
HANG_W = 0.4
NL = os.linesep  # what the subject's text-mode stdout writes for "\n" on this platform
EXIT0 = {"exit_code": 0}

#: A product-like checkout: one package with a __main__, an entry function and a command table (names never start
#: with "test"; every command is the subject's own behaviour, written by the harness, never read for control).
CORE = '''
import os
import signal
import sys
import threading
import time


def dispatch(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ("echo", [])
    if cmd == "echo":
        sys.stdout.write(" ".join(rest) + "\\n")
        return 0
    if cmd == "err":
        sys.stderr.write(" ".join(rest) + "\\n")
        return 0
    if cmd == "show":
        sys.stdout.buffer.write(open(rest[0], "rb").read())
        return 0
    if cmd == "code":
        return int(rest[0])
    if cmd == "exit":
        sys.exit(int(rest[0]))
    if cmd == "exitmsg":
        raise SystemExit("bad thing")
    if cmd == "exitnone":
        sys.exit()
    if cmd == "boom":
        raise ValueError("no")
    if cmd == "hard":
        sys.stdout.write("x")
        os._exit(int(rest[0]))
    if cmd == "sleep":
        time.sleep(float(rest[0]))
        return 0
    if cmd == "closefd1":
        sys.stdout.write("a")
        sys.stdout.flush()
        os.close(1)
        return 0
    if cmd == "redirect":
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, 1)
        os.dup2(null, 2)
        return 0
    if cmd in ("forge", "forgehard"):
        nonce = __import__("json").load(open(os.path.join("..", "request.json"), encoding="utf-8"))["nonce"]
        sys.stdout.write("AISEF2-PROBE RESULT " + nonce + " {\\"subject\\": \\"absent\\"}\\n")
        sys.stdout.flush()
        sys.stderr.write("forged\\n")
        sys.stderr.flush()
        if cmd == "forgehard":
            os._exit(0)
        return 0
    if cmd == "flood":
        chunk = b"x" * (1 << 20)
        for _ in range(int(rest[0])):
            sys.stdout.buffer.write(chunk)
        return 0
    if cmd == "late":
        sys.stdout.write("early")
        sys.stdout.flush()
        def later():
            time.sleep(0.3)
            os.write(1, b"late")
        threading.Thread(target=later).start()
        return 0
    if cmd == "linger":
        sys.stdout.write("x")
        threading.Thread(target=lambda: time.sleep(3600)).start()   # not a daemon: the process cannot exit
        return 0
    if cmd == "cat":
        sys.stdout.buffer.write(sys.stdin.buffer.read())
        return 0
    if cmd == "put":
        open(rest[0], "wb").write(rest[1].encode("utf-8"))
        return 0
    if cmd == "copy":
        open(rest[1], "wb").write(open(rest[0], "rb").read())
        return 0
    if cmd == "drop":
        os.remove(rest[0])
        return 0
    if cmd == "selfterm":
        os.kill(os.getpid(), signal.SIGTERM)
        return 0
    if cmd == "where":
        sys.stdout.write(os.getcwd() + "|" + os.environ.get("HOME", "") + "|" + os.environ.get("TZ", "") + "\\n")
        return 0
    return 9
'''
PRODUCT = {
    "app/__init__.py": "",
    "app/core.py": CORE,
    "app/__main__.py": "import sys\n\nfrom app.core import dispatch\n\nif __name__ == \"__main__\":\n"
                       "    sys.exit(dispatch(sys.argv[1:]))\n",
    "app/cli.py": "from app.core import dispatch\n\n\ndef main(argv):\n    return dispatch(argv)\n\n\nNOT_CALLABLE = 3\n",
    "app/broken.py": "import no_such_dependency_xyz\n\n\ndef main(argv):\n    return 0\n",
    "plain.py": "import sys\n\nif __name__ == \"__main__\":\n    sys.stdout.write(\"plain\")\n    sys.exit(0)\n",
}


def spec(locator, observable=None, stimulus=None, *, expectation=S, absence=REQUIRES, probe=P, window=W):
    """A spec over `locator`; its observable declares the bounded window `window` (None: declares none)."""
    observable = dict(observable or EXIT0)
    if window is not None:
        observable.setdefault("within_s", window)
    return ProductProofSpec.create(
        contract_id="BC-CLI", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": "cli_invocation", "locator": locator}, "stimulus": stimulus or {"argv": []},
                     "observable": observable, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


def checkout(files):
    d = tempfile.mkdtemp(prefix="aisef2-rev-")
    for rel, text in files.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return d


def env(timeout=20, required=Enforcement.PARTIAL, interpreter=sys.executable):
    return ExecutionEnv(interpreter, timeout, required)


def facts_of(observation):
    return json.loads(observation.detail)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeRange:
    """A process range whose target writes `tags` (each "TAG" or "TAG body") into the marker file named in the
    request, tagged with the request's own nonce, then ends with `returncode`; `ledger` is what the controller
    signalled — the one authority on provenance (§9.3). `unterminated` leaves the last line without its newline;
    `write=False` never opens the file (the harness crashed before it)."""

    def __init__(self, tags, returncode, ledger=(), *, unterminated=False, write=True):
        self.tags, self.returncode, self.ledger = tags, returncode, list(ledger)
        self.unterminated, self.write, self.released, self.argv = unterminated, write, False, None

    def __call__(self, name, argv, **kw):
        self.name, self.argv = name, list(argv)
        return self

    def start(self):
        req = json.loads(pathlib.Path(self.argv[-1]).read_text(encoding="utf-8"))
        lines = []
        for tag in self.tags:
            name, _, body = tag.partition(" ")
            lines.append(f"AISEF2-PROBE {name} {req['nonce']}" + (f" {body}" if body else "") + "\n")
        text = "".join(lines)
        if self.unterminated and text:
            text = text[:-1]
        if self.write:
            pathlib.Path(req["protocol"]).write_text(text, encoding="utf-8")
        return self

    def wait(self, timeout=None):
        return self.returncode

    def members(self):
        return []

    def release(self):
        self.released = True


def faked(*tags, returncode, ledger=(), unterminated=False, write=True):
    return mock.patch.object(ci, "ProcessRange", FakeRange(tags, returncode, ledger, unterminated=unterminated,
                                                           write=write))


def refuses(error):
    return mock.patch.object(ci, "ProcessRange", mock.Mock(return_value=mock.Mock(start=mock.Mock(side_effect=error))))


def never_runs():
    return mock.patch.object(ci, "ProcessRange", side_effect=AssertionError("ran"))


class _Product(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.at = RevisionRef(SHA, checkout(PRODUCT))
        cls.empty = RevisionRef(SHA, checkout({"README.md": "no product yet\n"}))

    def see(self, s, at=None, e=None, probe=P):
        return probe.observe(s, at or self.at, e or env())

    def run_(self, s, at=None, e=None, probe=P):
        return run_probe(probe, s, at or self.at, e or env()).result


# --------------------------------------------------------------------------------------- DESIGN-CHECK-1

def design_check_1(at: RevisionRef, reps: int = 3) -> dict:
    """The same semantic result under every scheduling of the subject's exit against the marker file's close: five
    variants, each observed `reps` times; per variant the (kind, verdict, hard_exit) triple of every repetition.
    Read by the evidence harness (validation/qualification/c2_cli_harness.py) as well as by test CLI-4."""
    variants = {
        "a_exit_normally": (spec("app:__main__", EXIT0, {"argv": ["echo", "hi"]}), None),
        "b_hard_exit_after_stdout": (spec("app:__main__", {"exit_code": 3}, {"argv": ["hard", "3"]}), None),
        "c_lingers_past_the_window": (spec("app:__main__", EXIT0, {"argv": ["sleep", "30"]}, window=HANG_W), None),
        "d_closes_fd_1_before_exit": (spec("app:__main__", EXIT0, {"argv": ["closefd1"]}), None),
        "e_last_protocol_line_unterminated": (spec("app:__main__", EXIT0, {"argv": ["echo"]}),
                                              lambda: faked("READY", "DISPATCHED", 'MAIN {"before": {}}',
                                                            'RESULT {"subject": "present", "exit_code": 0}',
                                                            returncode=0, unterminated=True)),
    }
    out = {}
    for name, (s, patch) in variants.items():
        seen = []
        for _ in range(reps):
            with (patch() if patch else contextlib.nullcontext()):
                o = P.observe(s, at, env())
            hard = facts_of(o).get("hard_exit", False) if o.kind is K.OBSERVED else None
            seen.append((o.kind.value, o.verdict.value if o.verdict else None, hard))
        out[name] = seen
    return out


EXPECTED_DESIGN_CHECK_1 = {
    "a_exit_normally": ("OBSERVED", "SATISFIED", False),
    "b_hard_exit_after_stdout": ("OBSERVED", "SATISFIED", True),
    "c_lingers_past_the_window": ("SUBJECT_DEADLINE", "REFUTED", None),
    "d_closes_fd_1_before_exit": ("OBSERVED", "SATISFIED", False),
    "e_last_protocol_line_unterminated": ("OBSERVED", "SATISFIED", True),
}


# --------------------------------------------------------------------------------------- CLI-1..9, Q0

class Harness(_Product):
    def test_CLI_1_runpy_dispatch_with_argv_and_a_workspace_file_exit_0_and_captured_streams(self):
        s = spec("app:__main__", {"exit_code": 0, "stdout": "hello\n", "stderr": ""},
                 {"argv": ["show", "<ws>/note.txt"], "workspace": {"note.txt": {"text": "hello\n", "newline": "\n"}}})
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        f = facts_of(o)
        self.assertEqual((f["subject"], f["exit_code"], f["exit_status_raw"], f["raised"]), ("present", 0, 0, None))
        self.assertEqual((f["stdout"]["size"], f["stdout"]["sha256"], f["stdout"]["truncated"]),
                         (6, sha(b"hello\n"), False))
        self.assertEqual((f["stderr"]["size"], f["pre"], f["files"]), (0, [], {}))
        self.assertNotIn("path", f["stdout"])   # the capture path is not evidence: the directory is disposed
        self.assertEqual(self.run_(s), Executed(S))
        # a single-file module runs as __main__ too, and the entry-function form calls it with argv
        self.assertEqual(self.see(spec("plain:__main__", {"exit_code": 0, "stdout": "plain"})).verdict, S)
        self.assertEqual(self.see(spec("app.cli:main", {"exit_code": 0, "stdout": {"first_word": "hi"}},
                                       {"argv": ["echo", "hi", "there"]})).verdict, S)

    def test_CLI_2_a_forged_protocol_line_on_stdout_is_captured_bytes_never_protocol(self):
        # the subject reads the real nonce and prints a RESULT line claiming absence: the real RESULT comes from the file
        o = self.see(spec("app:__main__", EXIT0, {"argv": ["forge"]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        f = facts_of(o)
        self.assertEqual(f["subject"], "present")
        self.assertGreater(f["stdout"]["size"], 40)
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": {"contains": ["AISEF2-PROBE RESULT"]}},
                          {"argv": ["forge"]}))
        self.assertEqual(o.verdict, S)   # the forged line is the subject's own stdout, compared like any bytes

    def test_CLI_3_a_stdout_flood_is_capped_and_exits_still_observes_the_code(self):
        self.assertEqual(ci.STREAM_CAP, 8 * 1024 * 1024)
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": "x"}, {"argv": ["flood", "20"]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        f = facts_of(o)
        self.assertEqual((f["stdout"]["size"], f["stdout"]["truncated"]), (ci.STREAM_CAP, True))
        self.assertEqual(f["stdout"]["sha256"], sha(b"x" * ci.STREAM_CAP))
        o = self.see(spec("app:__main__", EXIT0, {"argv": ["flood", "20"]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))

    def test_CLI_4_DESIGN_CHECK_1_the_same_result_under_every_scheduling_of_exit_and_file_close(self):
        matrix = design_check_1(self.at, reps=3)
        self.assertEqual(set(matrix), set(EXPECTED_DESIGN_CHECK_1))
        for name, seen in matrix.items():
            with self.subTest(variant=name):
                self.assertEqual(seen, [EXPECTED_DESIGN_CHECK_1[name]] * 3)

    def test_CLI_5_a_failing_pre_step_names_its_index_and_refutes(self):
        s = spec("app:__main__", EXIT0, {"argv": ["echo"], "pre": [{"argv": ["echo", "one"]}, {"argv": ["exit", "2"]},
                                                                  {"argv": ["echo", "never"]}]})
        o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        f = facts_of(o)
        self.assertEqual((f["pre_failed"], len(f["pre"]), f["pre"][1]["exit_code"]), (1, 2, 2))
        self.assertNotIn("exit_code", f)   # the main invocation never ran
        for observable in ({"exit_code": 0}, {"blocks": True}):
            with self.subTest(observable=observable):
                self.assertEqual(self.see(spec("app:__main__", observable, dict(s.probe_input["stimulus"]))).verdict, R)
        ok = self.see(spec("app:__main__", EXIT0, {"argv": ["echo"], "pre": [{"argv": ["echo", "one"]}]}))
        self.assertEqual(ok.verdict, S)
        self.assertEqual([p["exit_code"] for p in facts_of(ok)["pre"]], [0])
        self.assertEqual(facts_of(ok)["pre"][0]["stdout"]["size"], 3 + len(NL))   # each pre-step captured on its own
        hard = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["hard", "3"], "pre": [{"argv": ["echo", "one"]}]}))
        self.assertEqual((hard.verdict, facts_of(hard)["hard_exit"], facts_of(hard).get("pre_failed")), (S, True, None))

    def test_CLI_6_an_absent_subject_is_SUBJECT_ABSENT_and_the_contract_decides(self):
        cases = {"module missing": ("nope:__main__", self.at), "submodule missing": ("app.gone:main", self.at),
                 "entry function missing": ("app.cli:gone", self.at),
                 "resolves only outside the revision": ("json.tool:__main__", self.at),
                 "empty checkout": ("app:__main__", self.empty)}
        for name, (locator, at) in cases.items():
            with self.subTest(case=name):
                o = self.see(spec(locator), at=at)
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R))
                # the contract's declaration decides what the same observation counts for (§10.2)
                self.assertEqual(classify_failure(spec(locator, absence=REQUIRES), o), Executed(I, PA))
                forbidden = spec(locator, absence=DECIDABLE, expectation=R)
                self.assertIs(contract_satisfaction(classify_failure(forbidden, o), forbidden), SAT)
                required = spec(locator, absence=DECIDABLE, expectation=S)
                self.assertIs(contract_satisfaction(classify_failure(required, o), required), UNSAT)
        self.assertEqual(self.run_(spec("nope:__main__", absence=REQUIRES)), Executed(I, PA))
        o = self.see(spec("json.tool:__main__"))
        self.assertEqual(o.detail, "resolves only outside the revision")
        # a package with no __main__ submodule has no __main__ semantics at this revision
        pkg = RevisionRef(SHA, checkout({"pkg/__init__.py": "", "pkg/mod.py": "X = 1\n"}))
        self.assertEqual(self.see(spec("pkg:__main__"), at=pkg).kind, K.SUBJECT_ABSENT)

    def test_CLI_7_ws_substitution_and_workspace_bytes_are_exact(self):
        ws = {"crlf.txt": {"text": "a\nb\n", "newline": "\r\n"}, "lf.txt": {"text": "a\nb\n", "newline": "\n"},
              "raw.bin": {"bytes_hex": "00ff10"}, "sub/deep.txt": {"text": "d"}}
        files = {"<ws>/out.txt": {"sha256": sha(b"a\r\nb\r\n")}, "<ws>/lf.txt": {"equals_before": True},
                 "<ws>/crlf.txt": {"text": "a\nb\n", "newline": "\r\n"}, "<ws>/raw.bin": {"sha256": sha(b"\x00\xff\x10")},
                 "<ws>/sub/deep.txt": {"text": "d"}, "<ws>/none.txt": {"absent": True}}
        o = self.see(spec("app:__main__", {"exit_code": 0, "files": files},
                          {"argv": ["copy", "<ws>/crlf.txt", "<ws>/out.txt"], "workspace": ws}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        f = facts_of(o)
        self.assertEqual(f["before"]["out.txt"], {"absent": True})
        self.assertEqual(f["files"]["out.txt"], {"sha256": sha(b"a\r\nb\r\n")})
        self.assertEqual(f["files"]["lf.txt"], f["before"]["lf.txt"])
        self.assertEqual(f["before"]["crlf.txt"], {"sha256": sha(b"a\r\nb\r\n")})
        gone = {"argv": ["drop", "<ws>/lf.txt"], "workspace": ws}
        self.assertEqual(self.see(spec("app:__main__", {"exit_code": 0, "files": {"<ws>/lf.txt": {"equals_before": True}}},
                                       gone)).verdict, R)
        self.assertEqual(self.see(spec("app:__main__", {"exit_code": 0, "files": {"<ws>/lf.txt": {"absent": True}}},
                                       gone)).verdict, S)
        # the placeholder becomes the workspace's absolute path; nothing else is substituted
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": {"regex": r"^(?:[A-Za-z]:)?[\\/].*[\\/]x <ws\r?\n$"}},
                          {"argv": ["echo", "<ws>/x", "<ws"]}))
        self.assertEqual(o.verdict, S, o.detail)
        # the working directory, HOME and TZ are the harness's, never the checkout's or the host's
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": {"regex": r"^(?:[^|]*[\\/])?ws\|(?:[^|]*[\\/])?ws\|UTC\r?\n$"}},
                          {"argv": ["where"]}))
        self.assertEqual(o.verdict, S, o.detail)

    def test_CLI_8_stdin_comes_from_the_stimulus_or_the_null_device(self):
        cases = [({"text": "a\nb", "newline": "\r\n"}, "a\r\nb"), ({"bytes_hex": "6869"}, "hi"), (None, "")]
        for stdin, expected in cases:
            with self.subTest(stdin=stdin):
                o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": expected}, {"argv": ["cat"], "stdin": stdin}))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_CLI_9_the_exit_status_is_recorded_verbatim_beside_the_code(self):
        cases = {
            "SystemExit(None)": (("app:__main__", ["exitnone"]), (None, 0, None), None),
            "SystemExit('msg')": (("app:__main__", ["exitmsg"]), ("bad thing", 1, None), "bad thing"),
            "SystemExit(7)": (("app:__main__", ["exit", "7"]), (7, 7, None), None),
            "uncaught exception": (("app:__main__", ["boom"]), (None, 1, "ValueError"), "ValueError: no"),
            "entry function returns 5": (("app.cli:main", ["code", "5"]), (5, 5, None), None),
            "entry function returns None": (("app.cli:main", ["echo"]), (0, 0, None), None),
            "import of the entry module fails": (("app.broken:main", []), (None, 1, "ModuleNotFoundError"),
                                                 "no_such_dependency_xyz"),
        }
        for name, ((locator, argv), (raw, code, raised), on_stderr) in cases.items():
            with self.subTest(case=name):
                observable = {"exit_code": code, "stderr": {"contains": [on_stderr]}} if on_stderr else {"exit_code": code}
                o = self.see(spec(locator, observable, {"argv": argv}))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
                f = facts_of(o)
                self.assertEqual((f["exit_status_raw"], f["exit_code"], f["raised"]), (raw, code, raised))
        self.assertEqual(self.see(spec("app:__main__", {"exit_code": 0}, {"argv": ["exit", "7"]})).verdict, R)

    def test_CLI_Q0_the_module_passes_the_probe_rules_with_its_catalog_facts(self):
        sys.path.insert(0, str(ROOT / "validation" / "v2"))
        import probe_static_checks as ps
        src = (ROOT / "aisef2/probe/cli_invocation.py").read_text(encoding="utf-8")
        facts = {"subject_process": "child_of_harness", "stimulus_shape": "invocation"}
        self.assertEqual(ps.violations("aisef2/probe/cli_invocation.py", src, ps.SOURCE_RULES, facts), [])
        self.assertEqual(ps.check(ROOT), [])   # catalog closure: registered, digest live, fixtures for every class
        scripts = ps.child_scripts(__import__("ast").parse(src))
        self.assertEqual([name for name, _, _ in scripts], ["HARNESS"])
        # the channel rule is what rejects a harness that puts its protocol on the subject's stdout
        forged = src.replace('proto.write(line.encode("utf-8"))', 'sys.stdout.write(line)')
        self.assertTrue(any("PROTOCOL_CHANNEL_DISCIPLINE" in v
                            for v in ps.violations("aisef2/probe/cli_invocation.py", forged, ps.SOURCE_RULES, facts)))


# --------------------------------------------------------------------------------------- FM2-CLI-HARNESS

class FaultHarness(_Product):
    def assert_unrunnable(self, s, result, detail=None):
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertFalse(hasattr(result, "behavior_verdict"))
        if detail is not None:
            self.assertEqual(result.detail, detail)
        for point in MeasurementPoint:
            r = route(result, s, point, ObligationRole.INTRODUCE)
            self.assertEqual((r.failure.code, r.failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))

    def test_FM2_CLI_HARNESS_1_interpreter_absent(self):
        gone = os.path.join(self.empty.root, "no-python")
        s = spec("app:__main__")
        with never_runs():
            self.assertEqual(self.see(s, e=env(interpreter=gone)),
                             Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"))
            self.assert_unrunnable(s, self.run_(s, e=env(interpreter=gone)))
            self.assert_unrunnable(s, self.run_(s, at=RevisionRef(SHA, os.path.join(self.empty.root, "gone"))),
                                   "cannot inspect: the revision checkout is missing")
        with refuses(OSError("cannot launch")):
            self.assert_unrunnable(s, self.run_(s), "the harness cannot launch: OSError")

    def test_FM2_CLI_HARNESS_2_evaluation_directory_uncreatable(self):
        s = spec("app:__main__")
        with never_runs():
            result = self.run_(s, probe=CliInvocationProbe(scratch=os.path.join(self.empty.root, "no-such-scratch")))
        self.assert_unrunnable(s, result, "the evaluation directory cannot be created: FileNotFoundError")
        self.assertFalse(os.path.exists(os.path.join(self.empty.root, "no-such-scratch")))

    def test_FM2_CLI_HARNESS_3_evaluation_directory_inside_the_checkout_refused(self):
        inside = os.path.join(self.at.root, "scratch-in-tree")
        os.makedirs(inside, exist_ok=True)
        s = spec("app:__main__")
        with never_runs():
            result = self.run_(s, probe=CliInvocationProbe(scratch=inside))
        self.assert_unrunnable(s, result, "the evaluation directory lies inside the revision checkout: refused")

    def test_FM2_CLI_HARNESS_4_protocol_file_unwritable(self):
        prepared = tempfile.mkdtemp(prefix="aisef2-cli-ro-")
        os.mkdir(os.path.join(prepared, "protocol.log"))   # the harness cannot open its channel for writing
        s = spec("app:__main__")
        with mock.patch.object(ci, "_evaluation_dir", lambda scratch: contextlib.nullcontext(prepared)):
            result = self.run_(s)
        self.assert_unrunnable(s, result, "the harness did not start (exit 1, no READY): tool absent or broken")
        # and a workspace that cannot be laid out is a harness failure before any launch
        with never_runs(), mock.patch.object(ci, "_prepare", side_effect=PermissionError("denied")):
            self.assert_unrunnable(s, self.run_(s), "the evaluation directory cannot be prepared: PermissionError")


# --------------------------------------------------------------------------------------- FM2-CLI-SUBJECT

class FaultSubject(_Product):
    def test_FM2_CLI_SUBJECT_1_a_subject_that_never_exits_gets_the_deadline_verdict_of_its_class(self):
        hang = {"argv": ["sleep", "30"]}
        cases = [({"exit_code": 0}, "exits", R), ({"exit_code": 0, "stdout": ""}, "exits_streams", R),
                 ({"exit_code": 0, "files": {"<ws>/x": {"absent": True}}}, "exits_files", R), ({"blocks": True}, "blocks", S)]
        for observable, cls, verdict in cases:
            with self.subTest(cls=cls):
                s = spec("app:__main__", observable, hang, window=HANG_W)
                self.assertEqual(ci.spec_class(s), cls)
                o = self.see(s)
                self.assertEqual(o, Observation(K.SUBJECT_DEADLINE, verdict,
                                                f"the subject's {HANG_W:g}s observation window expired ({cls})"))
                result = classify_failure(s, o)   # what run_probe folds the same observation into
                self.assertEqual(result, Executed(verdict))
                for point in MeasurementPoint:
                    failure = route(result, s, point, ObligationRole.INTRODUCE).failure
                    self.assertNotEqual(failure and failure.owner, Owner.ENVIRONMENT)   # TIME-5: never ENVIRONMENT
                if cls == "exits":
                    self.assertIs(route(result, s, MeasurementPoint.CANDIDATE).failure.owner, Owner.DEVELOPER)
        self.assertEqual(self.run_(spec("app:__main__", {"exit_code": 0}, hang, window=HANG_W)), Executed(R))
        o = self.see(spec("app:__main__", {"exit_code": 0}, hang, window=1))   # an integral window is written 1s, not 1.0s
        self.assertEqual(o, Observation(K.SUBJECT_DEADLINE, R, "the subject's 1s observation window expired (exits)"))

    @unittest.skipUnless(POSIX, "a process that ends itself by a signal (POSIX; Windows has no signal exit)")
    def test_FM2_CLI_SUBJECT_2_a_non_controller_signal_is_executed_and_indeterminate(self):
        import signal
        o = self.see(spec("app:__main__", EXIT0, {"argv": ["selfterm"]}))
        self.assertEqual((o.kind, o.verdict), (K.NON_CONTROLLER_SIGNAL, None))
        self.assertIn(f"signal {int(signal.SIGTERM)} after DISPATCHED", o.detail)
        result = self.run_(spec("app:__main__", EXIT0, {"argv": ["selfterm"]}))
        self.assertEqual(result, Executed(I, NCS))
        self.assertIsNot(route(result, spec("app:__main__"), MeasurementPoint.CANDIDATE).failure.owner, Owner.ENVIRONMENT)

    def test_FM2_CLI_SUBJECT_3_a_controller_stop_is_an_interruption_with_no_result(self):
        stops = []

        def stop_it(run):
            stops.append(run)
            threading.Timer(0.5, run.release).start()   # the controller's own ladder: it goes into the ledger
        probe = CliInvocationProbe(on_range=stop_it)
        with self.assertRaises(ProbeInterrupted) as interrupted:
            run_probe(probe, spec("app:__main__", EXIT0, {"argv": ["sleep", "60"]}, window=60), self.at, env())
        self.assertTrue(stops and stops[0].ledger)
        self.assertEqual(interrupted.exception.stage, stops[0].ledger[-1]["stage"])
        self.assertIn("what the subject did is not known", interrupted.exception.detail)
        self.assertFalse(stops[0].members())

    def test_FM2_CLI_SUBJECT_4_a_stdout_flood_is_bounded(self):
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": {"lines": 1}}, {"argv": ["flood", "12"]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))   # 12 MiB of one line: the captured 8 MiB is one line
        f = facts_of(o)
        self.assertEqual((f["stdout"]["size"], f["stdout"]["truncated"], f["exit_code"]), (ci.STREAM_CAP, True, 0))

    def test_FM2_CLI_SUBJECT_5_a_forged_protocol_line_then_a_hard_exit_is_the_hard_exit(self):
        o = self.see(spec("app:__main__", EXIT0, {"argv": ["forgehard"]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        f = facts_of(o)
        self.assertEqual((f["hard_exit"], f["exit_code"], f["subject"]), (True, 0, "present"))
        self.assertGreater(f["stdout"]["size"], 40)   # the forged line is in the subject's captured stdout
        self.assertEqual((f["stderr"]["size"], f["stderr"]["sha256"]), (7, sha(b"forged\n")))   # what it flushed to stderr
        o = self.see(spec("app:__main__", {"exit_code": 0, "stderr": "forged\n", "stdout": {"first_word": "AISEF2-PROBE"}},
                          {"argv": ["forgehard"]}))
        self.assertEqual(o.verdict, S, o.detail)

    def test_FM2_CLI_SUBJECT_6_nonzero_exit_shapes(self):
        for argv, code in ((["exit", "7"], 7), (["hard", "3"], 3), (["code", "250"], 250), (["boom"], 1),
                           (["exitmsg"], 1), (["unknown"], 9)):
            with self.subTest(argv=argv):
                o = self.see(spec("app:__main__", {"exit_code": code}, {"argv": argv}))
                self.assertEqual((o.kind, o.verdict, facts_of(o)["exit_code"]), (K.OBSERVED, S, code))
                self.assertIs(ci.verdict_of("exits", {"exit_code": code + 1}, facts_of(o)), R)
        self.assertEqual(self.see(spec("app:__main__", {"exit_code": 8}, {"argv": ["code", "250"]})).verdict, R)


# --------------------------------------------------------------------------------------- FM2-CLI-STREAM

class FaultStream(_Product):
    def test_FM2_CLI_STREAM_1_exit_before_READY(self):
        s = spec("app:__main__")
        with mock.patch.object(ci, "HARNESS", "import sys\nsys.exit(127)\n"):
            self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the harness did not start (exit 127, "
                                                                                "no READY): tool absent or broken"))
        with faked(returncode=-9):
            self.assertEqual(self.see(s).detail, "the harness process was killed by signal 9 before READY")
        with faked("READY", returncode=0):
            self.assertEqual(self.see(s).detail, "the harness did not start (exit 0, no DISPATCHED): tool absent or broken")
        with faked("READY", returncode=-9):
            self.assertEqual(self.see(s).detail, "the harness process was killed by signal 9 before DISPATCHED")
        with mock.patch.object(ci, "HARNESS", "import time\ntime.sleep(3600)\n"):
            o = self.see(s, e=env(timeout=1.0))   # written 1s, not 1.0s
        self.assertEqual(o, Observation(K.HARNESS_FAILED, detail="harness timeout: no READY within 1s — the "
                                                                 "observation mechanism did not operate"))
        with faked("READY", returncode=0):   # READY read, then the exit: no DISPATCHED is concluded after the file
            self.assertIs(self.run_(s).status, ProbeExecutionStatus.UNRUNNABLE)

    def test_FM2_CLI_STREAM_2_exit_after_DISPATCHED_without_RESULT(self):
        s = spec("app:__main__", EXIT0, {"argv": ["echo"]})
        empty = {"size": 0, "truncated": False, "sha256": sha(b"")}
        fake = FakeRange(("READY", "DISPATCHED", 'MAIN {"before": {}}'), 0)
        with mock.patch.object(ci, "ProcessRange", fake):
            o = self.see(s)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        self.assertEqual(facts_of(o), {"subject": "present", "exit_code": 0, "hard_exit": True, "stdout": empty,
                                       "stderr": empty, "before": {}, "files": {}})
        self.assertEqual((fake.name, fake.released), (f"probe {s.id}", True))   # the range is named for the spec
        with faked("READY", "DISPATCHED", 'MAIN {"before": {}}', returncode=4):
            self.assertEqual(self.see(s).verdict, R)
            self.assertEqual(self.see(spec("app:__main__", {"exit_code": 4}, {"argv": ["echo"]})).verdict, S)
            self.assertEqual(self.see(spec("app:__main__", {"blocks": True}, {"argv": ["echo"]})).verdict, R)
        # the files named by the observable are digested by the parent, against what MAIN recorded before
        files = {"<ws>/a": {"equals_before": True}, "<ws>/b": {"absent": True}}
        with faked("READY", "DISPATCHED", 'MAIN {"before": {"a": {"absent": true}, "b": {"absent": true}}}', returncode=0):
            o = self.see(spec("app:__main__", {"exit_code": 0, "files": files}, {"argv": ["echo"]}))
        self.assertEqual((o.verdict, facts_of(o)["before"], facts_of(o)["files"]),
                         (S, {"a": {"absent": True}, "b": {"absent": True}}, {"a": {"absent": True}, "b": {"absent": True}}))
        with faked("READY", "DISPATCHED", 'MAIN {"before": {"a": {"sha256": "00"}, "b": {"absent": true}}}', returncode=0):
            self.assertEqual(self.see(spec("app:__main__", {"exit_code": 0, "files": files}, {"argv": ["echo"]})).verdict, R)
        with faked("READY", "DISPATCHED", "PRE 0", returncode=3):   # it died in a pre-step: the state was never built
            o = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["echo"], "pre": [{"argv": ["echo"]}]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        self.assertEqual(facts_of(o), {"subject": "present", "pre_failed": 0, "exit_code": 3, "hard_exit": True})
        with faked("READY", "DISPATCHED", "PRE 0", "PRE 1", returncode=3):
            o = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["echo"], "pre": [{"argv": ["a"]}, {"argv": ["b"]}]}))
        self.assertEqual((o.verdict, facts_of(o)["pre_failed"]), (R, 1))
        with faked("READY", "DISPATCHED", "PRE 0", returncode=3):   # the file names a pre-step: that is what was running
            o = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["echo"]}))
        self.assertEqual((o.verdict, facts_of(o)["pre_failed"]), (R, 0))
        with faked("READY", "DISPATCHED", returncode=3):   # before its first pre-step
            o = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["echo"], "pre": [{"argv": ["echo"]}]}))
        self.assertEqual((o.verdict, facts_of(o)["pre_failed"]), (R, 0))
        with faked("READY", "DISPATCHED", "PRE 0", 'MAIN {"before": {}}', returncode=3):   # after a passing pre-step
            o = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["echo"], "pre": [{"argv": ["echo"]}]}))
        self.assertEqual((o.verdict, facts_of(o).get("pre_failed"), facts_of(o)["hard_exit"]), (S, None, True))
        with faked("READY", "DISPATCHED", returncode=-9):   # a signal the controller did not send (§9.3)
            o = self.see(s)
            self.assertEqual(self.run_(s), Executed(I, NCS))
        self.assertEqual(o, Observation(K.NON_CONTROLLER_SIGNAL, detail="the process ended by signal 9 after DISPATCHED, "
                                                                        "and this controller's signal ledger is empty: it "
                                                                        "did not send it"))
        with refuses(ci.RangeError("no anchor")):   # a range that refuses to start is a launch failure, like OSError
            self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the harness cannot launch: RangeError"))
        ladder = [{"stage": "terminate", "signal": "SIGTERM"}, {"stage": "kill", "signal": "SIGKILL"}]
        with faked("READY", "DISPATCHED", returncode=-9, ledger=ladder):
            with self.assertRaises(ProbeInterrupted) as stopped:   # the same exit, the controller's own signal
                self.see(s)
        self.assertEqual((stopped.exception.signal, stopped.exception.stage), (9, "kill"))
        # a real hard exit: the captured streams are what the process left, the exit code is the process's
        o = self.see(spec("app:__main__", {"exit_code": 3, "stdout": ""}, {"argv": ["hard", "3"]}))
        self.assertEqual((o.kind, o.verdict, facts_of(o)["hard_exit"]), (K.OBSERVED, S, True))

    def test_FM2_CLI_STREAM_3_RESULT_then_late_bytes_on_stdout(self):
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": "early"}, {"argv": ["late"]}))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(facts_of(o)["stdout"]["size"], 5)   # the bytes captured when the invocation returned
        # a RESULT is read as soon as it is written: a process that lingers after it (a thread that never ends) is
        # observed inside the window, and the caller's release stops what lingers
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": "x"}, {"argv": ["linger"]}, window=HANG_W))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_FM2_CLI_STREAM_4_the_subject_closing_or_redirecting_its_descriptors(self):
        for argv in (["closefd1"], ["redirect"]):
            with self.subTest(argv=argv):
                o = self.see(spec("app:__main__", EXIT0, {"argv": argv}))
                self.assertEqual((o.kind, o.verdict, facts_of(o).get("hard_exit", False)), (K.OBSERVED, S, False))
        o = self.see(spec("app:__main__", {"exit_code": 0, "stdout": "a"}, {"argv": ["closefd1"]}))
        self.assertEqual(o.verdict, S)

    def test_FM2_CLI_STREAM_5_marker_file_absent_at_exit(self):
        s = spec("app:__main__")
        with mock.patch.object(ci, "HARNESS", "import sys\nsys.exit(0)\n"):   # never opened its channel
            self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the harness did not start (exit 0, "
                                                                                "no READY): tool absent or broken"))
        with faked("READY", "DISPATCHED", returncode=0, write=False):
            self.assertEqual(self.see(s).detail, "the harness did not start (exit 0, no READY): tool absent or broken")

    def test_the_marker_file_poll_reports_a_line_an_exit_or_a_timeout_and_re_reads_after_the_exit(self):
        """`_await`: ("LINE", seen) when the tag is in the file — before the exit, or only in the re-read the exit
        triggers (§9.4: the exit never ends the protocol); ("EXITED", seen) when the process exited without it;
        ("TIMEOUT", seen) when the deadline passes with the process still running."""
        import time
        work = tempfile.mkdtemp(prefix="aisef2-cli-poll-")
        proto = os.path.join(work, "protocol.log")
        lines = "AISEF2-PROBE READY n0nce\nAISEF2-PROBE DISPATCHED n0nce\n"

        class Exited:
            returncode = 0

            def wait(self, timeout=None):
                return 0

        class Running:
            def wait(self, timeout=None):
                return None

        class LateWriter(Exited):   # the exit is reported first; the file holds the lines when read once more
            def wait(self, timeout=None):
                pathlib.Path(proto).write_text(lines + "AISEF2-PROBE RESULT n0nce {}\n", encoding="utf-8")
                return 0
        pathlib.Path(proto).write_text(lines, encoding="utf-8")
        self.assertEqual(ci._await(Running(), proto, "n0nce", "DISPATCHED", time.monotonic() + 5),
                         ("LINE", {"READY": [""], "DISPATCHED": [""]}))
        self.assertEqual(ci._await(Exited(), proto, "n0nce", "RESULT", time.monotonic() + 5),
                         ("EXITED", {"READY": [""], "DISPATCHED": [""]}))
        self.assertEqual(ci._await(Running(), proto, "n0nce", "RESULT", time.monotonic() + 0.1)[0], "TIMEOUT")
        pathlib.Path(proto).write_text("", encoding="utf-8")
        self.assertEqual(ci._await(LateWriter(), proto, "n0nce", "RESULT", time.monotonic() + 5),
                         ("LINE", {"READY": [""], "DISPATCHED": [""], "RESULT": ["{}"]}))
        # and through the harness: the exit reported before any line was read still yields the complete result
        s = spec("app:__main__", EXIT0, {"argv": ["echo"]})

        class LateRange(FakeRange):
            def start(self):
                self.req = json.loads(pathlib.Path(self.argv[-1]).read_text(encoding="utf-8"))
                return self

            def wait(self, timeout=None):
                pathlib.Path(self.req["protocol"]).write_text(
                    f"AISEF2-PROBE READY {self.req['nonce']}\nAISEF2-PROBE DISPATCHED {self.req['nonce']}\n"
                    f"AISEF2-PROBE RESULT {self.req['nonce']} {{\"subject\": \"present\", \"exit_code\": 0}}\n", encoding="utf-8")
                return 0
        with mock.patch.object(ci, "ProcessRange", LateRange((), 0)):
            o = self.see(s)
        self.assertEqual((o.kind, o.verdict, facts_of(o)), (K.OBSERVED, S, {"subject": "present", "exit_code": 0}))

    def test_a_status_never_reported_with_nothing_left_of_the_process_is_a_harness_failure(self):
        class Vanished(FakeRange):
            def wait(self, timeout=None):
                return None
        with mock.patch.object(ci, "ProcessRange", Vanished(("READY", "DISPATCHED"), None)), \
                mock.patch.object(ci, "_COLLECT_S", 0.05):
            o = self.see(spec("app:__main__", EXIT0, {"argv": ["echo"]}, window=0.3))
        self.assertEqual(o, Observation(K.HARNESS_FAILED, detail="the harness process ended and its exit status was "
                                                                 "never reported"))


# --------------------------------------------------------------------------------------- FM2-PYC-CLI

SOURCE_A = "import sys\nsys.exit(1)\n"   # the source the stale bytecode was compiled from
SOURCE_B = "import sys\nsys.exit(2)\n"   # the source of the revision under proof: same size, one character apart
assert len(SOURCE_A) == len(SOURCE_B)
EXITS_2, EXITS_1 = {"exit_code": 2, "within_s": 10}, {"exit_code": 1, "within_s": 10}


def stale_checkout(root: pathlib.Path, *, offset_s: int = 0, bytecode: bool = True) -> dict:
    """app/mod.py holding SOURCE_B beside app/__pycache__/mod.<tag>.pyc compiled from SOURCE_A, the bytecode's header
    matching the source's size and (offset 0) its whole-second mtime (tests/v2/test_p7_finding_001.py's construction)."""
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    src = app / "mod.py"
    src.write_text(SOURCE_A, encoding="utf-8", newline="\n")
    cfile = importlib.util.cache_from_source(str(src))
    if bytecode:
        py_compile.compile(str(src), cfile=cfile, doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    header = pathlib.Path(cfile).read_bytes()[:16] if bytecode else b"\0" * 16
    src.write_text(SOURCE_B, encoding="utf-8", newline="\n")
    second = int.from_bytes(header[8:12], "little")
    os.utime(src, (second + offset_s, second + offset_s))
    st = src.stat()
    return {"bytecode": cfile if bytecode else None,
            "collision": bytecode and second == int(st.st_mtime) & 0xFFFFFFFF
            and st.st_size == int.from_bytes(header[12:16], "little")}


def snapshot(root: pathlib.Path) -> dict:
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def verdict(record):
    return record.result.behavior_verdict if isinstance(record.result, Executed) else record.result


class Bytecode(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-pyc-cli-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.root = self.tmp / "checkout"
        self.built = stale_checkout(self.root)
        self.assertTrue(self.built["collision"], self.built)
        self.at = RevisionRef("a" * 40, str(self.root))

    def observe(self, observable, *, probe=None, expectation=S):
        return run_probe(probe or CliInvocationProbe(), spec("app.mod:__main__", observable, expectation=expectation,
                                                              window=None), self.at, env(60))

    def test_FM2_PYC_CLI_1_in_tree_stale_bytecode_with_a_matching_header_is_never_the_subject(self):
        self.assertEqual(verdict(self.observe(EXITS_2)), S)   # exit 2 is SOURCE_B's behaviour; the stale bytecode exits 1
        self.assertEqual(verdict(self.observe(EXITS_1, expectation=R)), R)
        other = self.tmp / "verifier"
        self.assertFalse(stale_checkout(other, offset_s=100)["collision"])
        b = run_probe(CliInvocationProbe(), spec("app.mod:__main__", EXITS_2, window=None), RevisionRef("a" * 40, str(other)), env(60))
        self.assertEqual(verdict(b), S)

    def test_FM2_PYC_CLI_2_the_probe_writes_no_bytecode_into_the_checkout(self):
        before = snapshot(self.root)
        self.assertEqual(verdict(self.observe(EXITS_2)), S)
        self.assertEqual(snapshot(self.root), before)
        plain = self.tmp / "plain"
        stale_checkout(plain, bytecode=False)
        self.assertEqual(verdict(run_probe(CliInvocationProbe(), spec("app.mod:__main__", EXITS_2, window=None),
                                           RevisionRef("a" * 40, str(plain)), env(60))), S)
        self.assertEqual(sorted(str(p.relative_to(plain)) for p in plain.rglob("*.pyc")), [])

    def test_FM2_PYC_CLI_3_the_cache_is_fresh_empty_outside_the_checkout_and_distinct_per_evaluation(self):
        seen = []
        real_start = ci.ProcessRange.start

        def start(run):
            argv = run._argv
            prefix = argv[argv.index("-X") + 1].removeprefix("pycache_prefix=")
            seen.append((prefix, os.listdir(prefix) == [], ci._inside(prefix, str(self.root)), argv[1:4]))
            return real_start(run)
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        with mock.patch.object(ci.ProcessRange, "start", start):
            self.assertEqual(verdict(self.observe(EXITS_2)), S)
            for _ in ("implementer", "verifier"):
                self.assertEqual(verdict(self.observe(EXITS_2, probe=CliInvocationProbe(scratch=str(scratch)))), S)
        self.assertEqual(len({p for p, *_ in seen}), 3)
        self.assertEqual([(empty, inside, flags) for _, empty, inside, flags in seen], [(True, False, ["-I", "-B", "-X"])] * 3)
        self.assertFalse(pathlib.Path(seen[0][0]).exists())   # the probe's own temporary directory: gone
        self.assertEqual({pathlib.Path(p).parent.parent for p, *_ in seen[1:]}, {scratch})
        self.assertEqual(sorted(scratch.rglob("*.pyc")), [])   # -B: nothing written anywhere

    def test_FM2_PYC_CLI_4_without_the_external_cache_the_stale_bytecode_decides_the_reproducer_detects_the_defect(self):
        for keep_b in (True, False):
            def argv(interpreter, ask, pycache, keep_b=keep_b):
                return [interpreter, "-I", *(["-B"] if keep_b else []), "-X", "utf8=1", "-c", ci.HARNESS, ask]
            with self.subTest(keep_b=keep_b), mock.patch.object(ci, "_harness_argv", argv):
                self.assertEqual(verdict(self.observe(EXITS_2)), R)   # the stale code's exit 1, not the source's 2
                self.assertEqual(verdict(self.observe(EXITS_1, expectation=R)), S)
        # without -B the bytecode lands under the prefix, never in the checkout
        scratch = self.tmp / "scratch"
        scratch.mkdir()
        before = snapshot(self.root)
        with mock.patch.object(ci, "_harness_argv", lambda i, a, p: [i, "-I", "-X", f"pycache_prefix={p}", "-c", ci.HARNESS, a]):
            self.assertEqual(verdict(self.observe(EXITS_2, probe=CliInvocationProbe(scratch=str(scratch)))), S)
        self.assertEqual(snapshot(self.root), before)
        self.assertTrue(any(p.name.startswith("mod.") for p in scratch.rglob("*.pyc")))


# --------------------------------------------------------------------------------------- identity and refusals

class Identity(_Product):
    def test_the_digest_covers_exactly_the_sources_it_names_and_is_stable_across_processes(self):
        self.assertEqual(tuple(ci.PROBE_SOURCES), ("probe/protocol.py", "probe/python_callable.py", "probe/cli_invocation.py"))

        def digest_of(files):
            h = hashlib.sha256()
            for rel, data in files:
                h.update(rel.encode() + b"\0" + data + b"\0")
            return h.hexdigest()
        files = [(rel, (ROOT / "aisef2" / rel).read_bytes().replace(b"\r\n", b"\n")) for rel in ci.PROBE_SOURCES]
        self.assertEqual(digest_of(files), P.digest)
        for i, (rel, data) in enumerate(files):
            with self.subTest(source=rel):
                changed = list(files)
                changed[i] = (rel, data + b"# changed\n")
                self.assertNotEqual(digest_of(changed), P.digest)
                self.assertNotEqual(digest_of(files[:i] + files[i + 1:]), P.digest)
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import aisef2.probe.cli_invocation as m; "
                "print(m.CliInvocationProbe.digest)")
        out = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(out.stdout.strip(), P.digest)
        self.assertNotEqual(P.digest, __import__("aisef2.probe.python_callable", fromlist=["DIGEST"]).DIGEST)

    def test_the_catalog_entry_binds_this_probe_as_the_active_cli_invocation_probe(self):
        e = catalog.active()[SubjectKind.CLI_INVOCATION]
        self.assertEqual((e.probe_id, e.probe_digest, e.classes, e.cycle), (ci.PROBE_ID, ci.DIGEST, ci.CLASSES, 2))
        self.assertEqual((e.subject_process, e.protocol_channel, e.stimulus_shape), ("child_of_harness", "marker_file", "invocation"))
        self.assertIs(e.metadata, ci.METADATA)
        self.assertIs(ci.METADATA.observation_class, ci.spec_class)
        self.assertIsInstance(catalog.catalogue()[SubjectKind.CLI_INVOCATION], CliInvocationProbe)
        self.assertEqual(catalog.registry().observation_class(ci.PROBE_ID, ci.DIGEST, spec("app:__main__")), "exits")

    def test_enforcement_is_declared_bound_and_never_degraded(self):
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        self.assertIn("not a sandbox", ci.WEAKEST_PATH)
        rec = run_probe(P, spec("app:__main__", EXIT0, {"argv": ["echo"]}), self.at, env())
        self.assertIs(rec.enforcement, Enforcement.PARTIAL)
        with never_runs():
            refused = run_probe(P, spec("app:__main__"), self.at, env(required=Enforcement.FULL))
        self.assertIs(refused.result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertEqual(ci.ON_DEADLINE, {"exits": R, "exits_streams": R, "exits_files": R, "blocks": S})
        self.assertEqual(len(P.harness_preconditions()), 4)

    def test_unsupported_specs_are_refused_before_anything_runs(self):
        with never_runs():
            for locator in ("app/__main__.py:__main__", "app-cli", "app.cli", "app.cli:main()", "app.cli:a.b"):
                with self.subTest(locator=locator):
                    result = self.run_(spec(locator))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "never accepted$")
            # the refusals name what is refused
            self.assertEqual(self.see(spec("app-cli")).detail, "locator 'app-cli' is not module.path:__main__ or "
                                                                "module.path:callable — a path or a console script is "
                                                                "never accepted")
            self.assertEqual(self.see(spec("app:__main__", {"returns": 1})).detail,
                             f"observable/stimulus is not a supported class {ci.CLASSES} with a bounded window "
                             "(within_s); refused, not degraded")
            for obs, stim in (({"returns": 1}, {"argv": []}), ({"exit_code": "0"}, {"argv": []}), ({"exit_code": True}, {"argv": []}),
                              ({"exit_code": 0, "stdout": {"prose": "ok"}}, {"argv": []}), ({"exit_code": 0, "files": {"out": {"absent": True}}}, {"argv": []}),
                              ({"exit_code": 0, "files": {"<ws>/../x": {"absent": True}}}, {"argv": []}), ({"exit_code": 0}, {"argv": [1]}),
                              ({"exit_code": 0}, {"args": []}), ({"exit_code": 0}, {"argv": [], "stdin": "text"}),
                              ({"exit_code": 0}, {"argv": [], "workspace": {"../x": {"text": ""}}}), ({"blocks": 1}, {"argv": []}),
                              ({"exit_code": 0}, {"argv": [], "pre": [["a"]]})):
                with self.subTest(observable=obs, stimulus=stim):
                    result = self.run_(spec("app:__main__", obs, stim))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "refused, not degraded$")
            other = spec("app:__main__")
            other = ProductProofSpec.create(**{**{f: getattr(other, f) for f in (
                "contract_id", "probe_id", "probe_digest", "candidate_expectation", "compiler_id", "compiler_digest")},
                "probe_input": {**other.probe_input, "subject": {"kind": "python_callable", "locator": "app:__main__"}}})
            self.assertEqual(self.see(other), Observation(K.UNSUPPORTED, detail="subject kind 'python_callable' is not cli_invocation"))
            self.assertIsNone(ci.spec_class(other))
            for locator in ("tests.cli:main", "app.test_cli:main"):
                self.assertRegex(self.run_(spec(locator)).detail, "developer test artefact")
            result = self.run_(spec("app:__main__", {"exit_code": 0}, window=None))
            self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
            self.assertIn("bounded window (within_s)", result.detail)

    def test_the_internal_observation_carries_its_facts_on_every_path(self):
        """`_observe` answers (Observation, facts): the facts the harness reported (or the hard-exit facts) with an
        OBSERVED observation, None with every other kind — the channel a two-invocation class reads."""
        s = spec("app:__main__", EXIT0, {"argv": ["echo"]})
        args = (s.id, "exits", "app:__main__", {"argv": ["echo"]}, {"exit_code": 0, "within_s": W})
        gone = os.path.join(self.empty.root, "no-python")
        inside = os.path.join(self.at.root, "scratch-in-tree")
        os.makedirs(inside, exist_ok=True)
        with never_runs():
            self.assertEqual(P._observe(*args, self.at, env(interpreter=gone)),
                             (Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"), None))
            self.assertEqual(P._observe(*args, RevisionRef(SHA, gone), env()),
                             (Observation(K.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing"), None))
            self.assertEqual(CliInvocationProbe(scratch=gone)._observe(*args, self.at, env()),
                             (Observation(K.HARNESS_FAILED, detail="the evaluation directory cannot be created: "
                                                                   "FileNotFoundError"), None))
            self.assertEqual(CliInvocationProbe(scratch=inside)._observe(*args, self.at, env()),
                             (Observation(K.HARNESS_FAILED, detail="the evaluation directory lies inside the revision "
                                                                   "checkout: refused"), None))
            with mock.patch.object(ci, "_prepare", side_effect=PermissionError("denied")):
                self.assertEqual(P._observe(*args, self.at, env()),
                                 (Observation(K.HARNESS_FAILED, detail="the evaluation directory cannot be prepared: "
                                                                       "PermissionError"), None))
        with refuses(OSError("cannot launch")):
            self.assertEqual(P._observe(*args, self.at, env()),
                             (Observation(K.HARNESS_FAILED, detail="the harness cannot launch: OSError"), None))
        with faked("READY", returncode=0):
            self.assertEqual(P._observe(*args, self.at, env()),
                             (Observation(K.HARNESS_FAILED, detail="the harness did not start (exit 0, no DISPATCHED): "
                                                                   "tool absent or broken"), None))
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "absent", "note": "n"}', returncode=0):
            self.assertEqual(P._observe(*args, self.at, env()), (Observation(K.SUBJECT_ABSENT, R, "n"), None))
        with faked("READY", "DISPATCHED", returncode=-9):
            o, facts = P._observe(*args, self.at, env())
            self.assertEqual((o.kind, facts), (K.NON_CONTROLLER_SIGNAL, None))
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "exit_code": 0, "pre": []}', returncode=0):
            self.assertEqual(P._observe(*args, self.at, env()),
                             (Observation(K.OBSERVED, S, '{"subject": "present", "exit_code": 0, "pre": []}'),
                              {"subject": "present", "exit_code": 0, "pre": []}))
        with faked("READY", "DISPATCHED", 'MAIN {"before": {}}', returncode=2):
            o, facts = P._observe(*args, self.at, env())
            self.assertEqual((o.kind, o.verdict, facts["exit_code"], facts["hard_exit"], "path" in facts["stdout"]),
                             (K.OBSERVED, R, 2, True, True))
        with faked("READY", "DISPATCHED", "PRE 0", returncode=2):
            o, facts = P._observe(s.id, "exits", "app:__main__", {"argv": ["echo"], "pre": [{"argv": ["a"]}]},
                                  {"exit_code": 2, "within_s": W}, self.at, env())
            self.assertEqual((o.verdict, facts), (R, {"subject": "present", "pre_failed": 0, "exit_code": 2, "hard_exit": True}))
        o, facts = P._observe(s.id, "exits", "app:__main__", {"argv": ["sleep", "30"]}, {"exit_code": 0, "within_s": HANG_W},
                              self.at, env())
        self.assertEqual((o.kind, o.verdict, facts), (K.SUBJECT_DEADLINE, R, None))

        class Vanished(FakeRange):
            def wait(self, timeout=None):
                return None
        with mock.patch.object(ci, "ProcessRange", Vanished(("READY", "DISPATCHED"), None)), \
                mock.patch.object(ci, "_COLLECT_S", 0.05):
            o, facts = P._observe(s.id, "exits", "app:__main__", {"argv": ["echo"]}, {"exit_code": 0, "within_s": 0.3},
                                  self.at, env())
        self.assertEqual((o.kind, facts), (K.HARNESS_FAILED, None))

    def test_product_verdicts_are_identical_across_developer_test_layouts(self):
        layouts = {"no tests": {}, "tests/ at the root": {"tests/__init__.py": "", "tests/test_cli.py": "import app\n"},
                   "broken tests": {"conftest.py": "raise SystemExit(4)\n", "app/test_cli.py": "import no_such_module\n"}}
        specs = {"exits": spec("app:__main__", {"exit_code": 7}, {"argv": ["exit", "7"]}),
                 "absent": spec("app.telemetry:__main__", absence=DECIDABLE)}
        seen = {name: {k: run_probe(P, s, RevisionRef(SHA, checkout({**PRODUCT, **extra})), env()).result
                       for k, s in specs.items()} for name, extra in layouts.items()}
        first = next(iter(seen.values()))
        self.assertEqual(first, {"exits": Executed(S), "absent": Executed(R)})
        for name, results in seen.items():
            with self.subTest(layout=name):
                self.assertEqual(results, first)


if __name__ == "__main__":
    unittest.main()
