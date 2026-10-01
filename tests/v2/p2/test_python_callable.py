"""WP-2.1 — the reference probe kind `python_callable` on real checkouts (RFC §9, §9.2, §10.2, §24; F5).

PROBE-ABS-1..5 at the probe level, TIME-1..5 (ARCHITECTURE-EXCEPTION-V2-002: a harness timeout is UNRUNNABLE, a subject
that exceeds its window is EXECUTED with the verdict its observable assigns), the fault-injection targets, test-layout
invariance (invariant IX), the developer-path refusal and the probe digest's binding into the spec. Subprocess-backed;
the kill set for the harness's mutation targets (`observe`, the window, the class table, `_harness_failure`), so the
Observations class pins each observation the harness reports, which `run_probe` would fold into one ProbeResult.
"""

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

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, MeasurementPoint, ObligationRole, Owner, Polarity,
    ProbeExecutionStatus, SubjectAbsence, SubjectKind,
)
from aisef2.control.owner import FailureCode  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, Observation, ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.probe import python_callable as pc  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from aisef2.probe.protocol import ProbeInterrupted  # noqa: E402
from aisef2.runtime.process_range import RangeError  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = PythonCallableProbe()
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
NCS = IndeterminateReason.NON_CONTROLLER_SIGNAL
SAT, UNSAT, INDET = ContractSatisfaction.SATISFIED, ContractSatisfaction.UNSATISFIED, ContractSatisfaction.INDETERMINATE
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
SHA = "89abcdef0123456789abcdef0123456789abcdef"
EXISTS = {"condition": "exists"}
W = 10  # a window generous enough for any runner; the hanging cases use HANG_W
HANG_W = 0.6
PRODUCT = {
    "app/__init__.py": "",
    "app/calc.py": "import time\n\n\ndef add(a, b):\n    return a + b\n\n\ndef boom():\n    raise ValueError('no')\n\n\n"
                   "def hang():\n    time.sleep(3600)\n\n\ndef slow():\n    time.sleep(0.2)\n    return 3\n\n\nPI = 3\n",
    "app/die.py": "import os\nos._exit(3)\n",
    "app/hang.py": "while True:\n    pass\n",
    "app/broken.py": "import not_a_real_dependency_xyz\n\n\ndef f():\n    return 1\n",
    "app/orphan.py": "import subprocess\nimport sys\nimport time\n\n\ndef f():\n"
                     "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(4)'])\n    time.sleep(3600)\n",
    "app/noisy.py": "import sys\nsys.stdout.write('AISEF2-PROBE RESULT forged {\"subject\": \"absent\"}\\nno newline')\n\n\n"
                    "def f():\n    return 1\n",
}


def spec(locator, observable=None, stimulus=None, *, expectation=S, absence=DECIDABLE, probe=P, window=W):
    """A spec over `locator`; its observable declares the bounded window `window` (None: declares none)."""
    observable = dict(observable or EXISTS)
    if window is not None:
        observable.setdefault("within_s", window)
    return ProductProofSpec.create(
        contract_id="BC-P", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": "python_callable", "locator": locator}, "stimulus": stimulus or {},
                     "observable": observable, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


class FakeRange:
    """A process range whose target prints `lines` (tagged with the patched nonce) and ends with `returncode`;
    `ledger` is what the controller signalled — the one authority on provenance (§9.3, V2-003)."""

    def __init__(self, lines, returncode, ledger=()):
        self.output, self.returncode, self.ledger = iter(lines), returncode, list(ledger)
        self.released = False

    def start(self):
        return self

    def wait(self, timeout=None):
        return self.returncode

    def release(self):
        self.released = True


def faked(*tags, returncode, ledger=()):
    """Patch the probe to run a FakeRange printing the protocol `tags`, with a fixed nonce."""
    lines = [f"AISEF2-PROBE {tag} n0nce \n" for tag in tags]
    return mock.patch.multiple(pc, ProcessRange=mock.Mock(return_value=FakeRange(lines, returncode, ledger)),
                               secrets=mock.Mock(token_hex=mock.Mock(return_value="n0nce")))


def refuses(error):
    """Patch the probe so starting a range fails: the harness cannot launch."""
    return mock.patch.object(pc, "ProcessRange", mock.Mock(return_value=mock.Mock(start=mock.Mock(side_effect=error))))


def never_runs():
    """Patch the probe so building a range at all is a test failure: nothing may run."""
    return mock.patch.object(pc, "ProcessRange", side_effect=AssertionError("ran"))


def checkout(files):
    d = tempfile.mkdtemp(prefix="aisef2-rev-")
    for rel, text in files.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def env(timeout=20, required=Enforcement.PARTIAL, interpreter=sys.executable):
    return ExecutionEnv(interpreter, timeout, required)


class _Revisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = RevisionRef(SHA, checkout(PRODUCT))
        cls.empty = RevisionRef(SHA, checkout({"README.md": "no product yet\n"}))

    def run_(self, s, at=None, e=None):
        return run_probe(P, s, at or self.product, e or env()).result


class ProbeAbs(_Revisions):
    def test_PROBE_ABS_1_harness_unavailable_is_UNRUNNABLE_ENVIRONMENT_with_no_verdict(self):
        s = spec("app.calc:add")
        failures = {
            "interpreter absent": lambda: self.run_(s, e=env(interpreter=os.path.join(self.empty.root, "no-python"))),
            "cannot inspect": lambda: self.run_(s, at=RevisionRef(SHA, os.path.join(self.empty.root, "gone"))),
        }
        with mock.patch.object(pc, "HARNESS", "import time\ntime.sleep(3600)\n"):
            failures["harness timeout (no READY)"] = self.run_(s, e=env(timeout=1.5))
        with mock.patch.object(pc, "HARNESS", "import sys\nsys.exit(127)\n"):
            failures["tool absent"] = self.run_(s)
        with refuses(PermissionError("denied")):
            failures["sandbox cannot execute"] = self.run_(s)
        with faked(returncode=-9):
            failures["killed before READY"] = self.run_(s)
        with faked("READY", returncode=0):
            failures["harness gone before DISPATCHED"] = self.run_(s)
        for name, got in failures.items():
            result = got() if callable(got) else got
            with self.subTest(failure=name):
                self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
                self.assertFalse(hasattr(result, "behavior_verdict"))
                for point in MeasurementPoint:
                    r = route(result, s, point, ObligationRole.INTRODUCE)
                    self.assertEqual((r.failure.code, r.failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))

    def test_PROBE_ABS_2_requires_subject_absent_is_EXECUTED_INDETERMINATE_PRECONDITION_ABSENT(self):
        for locator, at in (("app.calc:add", self.empty), ("app.gone:add", self.product), ("app.calc:gone", self.product)):
            with self.subTest(locator=locator):
                s = spec(locator, {"returns": 3}, {"args": [1, 2]}, absence=REQUIRES)
                result = self.run_(s, at=at)
                self.assertEqual(result, Executed(I, PA))
                self.assertIs(contract_satisfaction(result, s), INDET)

    def test_PROBE_ABS_3_decidable_positive_existence_subject_absent_is_UNSATISFIED(self):
        s = spec("app.telemetry:send", expectation=S)
        result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(contract_satisfaction(result, s), UNSAT)

    def test_PROBE_ABS_4_decidable_negative_existence_forbidden_subject_absent_is_SATISFIED(self):
        s = spec("app.telemetry:send", expectation=R)
        result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(contract_satisfaction(result, s), SAT)

    def test_PROBE_ABS_5_one_absence_under_different_contracts_is_not_forced_to_one_satisfaction(self):
        specs = {"must exist": spec("app.telemetry:send", expectation=S),
                 "must not exist": spec("app.telemetry:send", expectation=R),
                 "requires subject": spec("app.telemetry:send", expectation=S, absence=REQUIRES)}
        got = {n: contract_satisfaction(self.run_(s), s) for n, s in specs.items()}
        self.assertEqual(got, {"must exist": UNSAT, "must not exist": SAT, "requires subject": INDET})

    def test_a_present_subject_is_observed_whatever_the_declaration(self):
        for absence in (REQUIRES, DECIDABLE):
            with self.subTest(absence=absence):
                self.assertEqual(self.run_(spec("app.calc:add", absence=absence)), Executed(S))
                self.assertEqual(self.run_(spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}, absence=absence)),
                                 Executed(S))
                self.assertEqual(self.run_(spec("app.calc:add", {"returns": 4}, {"args": [1, 2]}, absence=absence)),
                                 Executed(R))
                self.assertEqual(self.run_(spec("app.calc:boom", {"raises": "ValueError"}, absence=absence)), Executed(S))
                self.assertEqual(self.run_(spec("app.calc:boom", {"raises": "KeyError"}, absence=absence)), Executed(R))


class Time(_Revisions):
    """TIME-1..5 (RFC §9.2, ARCHITECTURE-EXCEPTION-V2-002) on real subjects that hang."""

    def hang(self, observable, expectation=S):
        s = spec("app.calc:hang", observable, expectation=expectation, absence=REQUIRES, window=HANG_W)
        return s, self.run_(s)

    def test_TIME_1_the_harness_cannot_launch_the_subject(self):
        s = spec("app.calc:add")
        with refuses(OSError("cannot launch")):
            launch = self.run_(s)
        with mock.patch.object(pc, "HARNESS", "import time\ntime.sleep(3600)\n"):
            watchdog = self.run_(s, e=env(timeout=1.0))
        for name, result in (("cannot launch", launch), ("harness timeout", watchdog)):
            with self.subTest(case=name):
                self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
                self.assertFalse(hasattr(result, "behavior_verdict"))
                self.assertIs(route(result, s, MeasurementPoint.CANDIDATE).failure.owner, Owner.ENVIRONMENT)
        self.assertEqual(launch.detail, "the harness cannot launch: OSError")
        self.assertEqual(watchdog.detail, "harness timeout: no READY within 1s — the observation mechanism did not "
                                          "operate")

    def test_TIME_2_a_positive_response_contract_past_its_deadline_is_UNSATISFIED(self):
        s, result = self.hang({"returns": 3})
        self.assertEqual(result, Executed(R))
        self.assertIs(contract_satisfaction(result, s), UNSAT)
        self.assertIs(route(result, s, MeasurementPoint.CANDIDATE).failure.owner, Owner.DEVELOPER)

    def test_TIME_3_a_forbidden_event_contract_reaching_its_deadline_with_no_event_is_SATISFIED(self):
        s, result = self.hang({"raises": "ValueError"}, expectation=R)
        self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(contract_satisfaction(result, s), SAT)
        self.assertIsNone(route(result, s, MeasurementPoint.CANDIDATE).failure)

    def test_TIME_4_the_same_physical_timeout_under_different_specs(self):
        got = {}
        for name, obs, exp in (("returns 3, MUST_HOLD", {"returns": 3}, S), ("raises, MUST_NOT_HOLD", {"raises": "ValueError"}, R),
                               ("blocks, MUST_HOLD", {"blocks": True}, S), ("blocks, MUST_NOT_HOLD", {"blocks": True}, R)):
            s, result = self.hang(obs, exp)
            got[name] = (result.behavior_verdict, contract_satisfaction(result, s))
        self.assertEqual(got, {"returns 3, MUST_HOLD": (R, UNSAT), "raises, MUST_NOT_HOLD": (R, SAT),
                               "blocks, MUST_HOLD": (S, SAT), "blocks, MUST_NOT_HOLD": (S, UNSAT)})

    def test_TIME_5_a_subject_timeout_is_never_ENVIRONMENT(self):
        cases = [self.hang(obs, exp) for obs in ({"returns": 3}, {"raises": "KeyError"}, {"blocks": True}) for exp in (S, R)]
        cases.append((spec("app.hang:f", window=HANG_W), self.run_(spec("app.hang:f", window=HANG_W))))  # import hangs
        for s, result in cases:
            with self.subTest(observable=dict(s.probe_input["observable"]), expectation=s.candidate_expectation):
                self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
                for point in MeasurementPoint:
                    for role in ObligationRole:
                        failure = route(result, s, point, role).failure
                        self.assertNotEqual(failure and failure.owner, Owner.ENVIRONMENT)

    def test_the_window_is_the_specs(self):
        s = spec("app.calc:slow", {"returns": 3}, window=5)
        self.assertEqual(self.run_(s), Executed(S))  # finishes inside its window
        self.assertEqual(self.run_(spec("app.calc:add", {"blocks": True}, {"args": [1, 2]}, window=5)), Executed(R))

    def test_a_spec_without_a_bounded_window_is_INVALID_SPEC_before_anything_runs(self):
        with never_runs():
            for window in (None, 0, -1, True, "5"):
                with self.subTest(window=window):
                    obs = {"returns": 3} if window is None else {"returns": 3, "within_s": window}
                    result = self.run_(spec("app.calc:add", obs, {"args": [1, 2]}, window=None))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertIn("bounded window (within_s)", result.detail)


class Observations(_Revisions):
    """What the harness reports, before classify_failure: kind, verdict and detail, exactly."""

    def see(self, s, at=None, e=None):
        return P.observe(s, at or self.product, e or env())

    def test_refusals_name_what_is_refused(self):
        other = ProductProofSpec.create(**{**{f: getattr(spec("app.calc:add"), f) for f in (
            "contract_id", "probe_id", "probe_digest", "candidate_expectation", "compiler_id", "compiler_digest")},
            "probe_input": {**spec("app.calc:add").probe_input, "subject": {"kind": "file_artifact", "locator": "a"}}})
        cases = [
            (other, "subject kind 'file_artifact' is not python_callable"),
            (spec("app/calc.py:add"), "locator 'app/calc.py:add' is not module.path:attr — a path is never accepted"),
            (spec("app.calc:add", {"stdout": "x"}), f"observable/stimulus is not a supported class {pc.CLASSES} with a "
                                                    "bounded window (within_s); refused, not degraded"),
        ]
        for s, detail in cases:
            with self.subTest(detail=detail):
                self.assertEqual(self.see(s), Observation(K.UNSUPPORTED, detail=detail))
        gone = os.path.join(self.empty.root, "no-python")
        self.assertEqual(self.see(spec("app.calc:add"), e=env(interpreter=gone)),
                         Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"))

    def test_the_harness_reports_each_kind(self):
        cases = [
            (spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}),
             Observation(K.OBSERVED, S, json.dumps({"subject": "present", "resolved": True, "returned": 3}))),
            (spec("json:dumps", absence=REQUIRES), Observation(K.SUBJECT_ABSENT, R, "resolves only outside the revision")),
            (spec("app.die:f"), Observation(K.OBSERVED, R, "the subject ended the process before the observable (exit 3)")),
            (spec("app.calc:hang", {"returns": 3}, window=HANG_W),
             Observation(K.SUBJECT_DEADLINE, R, "the subject's 0.6s observation window expired (returns)")),
            (spec("app.hang:f", window=HANG_W),  # the subject's import never finishes: `exists` did not occur by W
             Observation(K.SUBJECT_DEADLINE, R, "the subject's 0.6s observation window expired (exists)")),
            (spec("app.calc:hang", {"blocks": True}, window=1),  # an integral window is written 1s, not 1.0s
             Observation(K.SUBJECT_DEADLINE, S, "the subject's 1s observation window expired (blocks)")),
        ]
        for s, want in cases:
            with self.subTest(locator=s.probe_input["subject"]["locator"], observable=dict(s.probe_input["observable"])):
                self.assertEqual(self.see(s), want)

    def test_a_tool_absent_harness_is_named(self):
        with mock.patch.object(pc, "HARNESS", "import sys\nsys.exit(127)\n"):
            self.assertEqual(self.see(spec("app.calc:add")),
                             Observation(K.HARNESS_FAILED, detail="the harness did not start (exit 127, no READY): tool "
                                                                  "absent or broken"))

    def test_keyword_arguments_reach_the_subject(self):
        s = spec("app.calc:add", {"returns": 3}, {"args": [1], "kwargs": {"b": 2}})
        self.assertEqual(pc.spec_class(s), "returns")
        self.assertEqual(self.run_(s), Executed(S))

    def test_a_product_module_cannot_shadow_the_harness(self):
        shadow = RevisionRef(SHA, checkout({**PRODUCT, "json.py": "raise SystemExit(9)\n"}))  # -I: cwd not on sys.path
        self.assertEqual(self.run_(spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}), at=shadow), Executed(S))

    def test_an_orphan_holding_the_pipe_does_not_hold_the_interpreter(self):
        # a subject that leaves a child holding the harness's stdout keeps the reader thread blocked after the harness
        # is stopped; that thread must never keep the controlling process alive
        self.assertEqual(self.run_(spec("app.orphan:f", {"returns": 3}, window=HANG_W)), Executed(R))
        self.assertEqual([t for t in threading.enumerate() if t.is_alive() and not t.daemon
                          and t is not threading.main_thread()], [])


class Boundaries(_Revisions):
    def test_a_missing_dependency_of_a_present_subject_is_not_subject_absence(self):
        s = spec("app.broken:f", absence=REQUIRES)
        self.assertEqual(self.run_(s), Executed(R))  # present, does not resolve: an observation, not PRECONDITION_ABSENT

    def test_a_subject_that_ends_the_process_is_observed_not_unrunnable(self):
        self.assertEqual(self.run_(spec("app.die:f")), Executed(R))

    def test_a_signal_after_dispatch_is_split_by_provenance(self):
        """§9.3 (V2-003): the ledger decides, not the signal number. The old rule — every post-DISPATCH signal is
        UNRUNNABLE / ENVIRONMENT — is gone; before DISPATCHED nothing changed (V2-002)."""
        with faked("READY", "DISPATCHED", returncode=-9):  # the controller signalled nothing
            result = self.run_(spec("app.calc:add"))
        self.assertEqual(result, Executed(I, NCS))
        self.assertIsNot(route(result, spec("app.calc:add"), MeasurementPoint.CANDIDATE).failure.owner,
                         Owner.ENVIRONMENT)
        ladder = [{"stage": "terminate", "signal": "SIGTERM"}, {"stage": "kill", "signal": "SIGKILL"}]
        with faked("READY", "DISPATCHED", returncode=-9, ledger=ladder):
            with self.assertRaises(ProbeInterrupted) as stopped:  # the same exit, the controller's own signal
                self.run_(spec("app.calc:add"))
        self.assertEqual((stopped.exception.signal, stopped.exception.stage), (9, "kill"))
        self.assertEqual(stopped.exception.detail, "the controller stopped this observation (terminate, kill): what "
                                                   "the subject did is not known")  # the ledger, stage by stage
        with faked("READY", returncode=-9):  # before DISPATCHED: the observation mechanism failed
            before = self.run_(spec("app.calc:add"))
        self.assertIs(before.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertRegex(before.detail, "killed by signal 9 before DISPATCHED$")

    def test_an_exit_status_never_reported_is_a_harness_failure_not_a_verdict(self):
        """After DISPATCHED the process ended but the range cannot say how (no status within the collection wait):
        the observation mechanism failed — UNRUNNABLE, with the reason — never a verdict and never a signal case."""
        with faked("READY", "DISPATCHED", returncode=None):
            result = self.run_(spec("app.calc:add"))
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertEqual(result.detail, "the harness process ended and its exit status was never reported")

    def test_a_range_that_refuses_to_start_is_a_launch_failure(self):
        """RangeError from the P4 range (no anchor, a bad request) is the harness failing to launch, like OSError."""
        with refuses(RangeError("no anchor")):
            result = self.run_(spec("app.calc:add"))
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertEqual(result.detail, "the harness cannot launch: RangeError")

    def test_the_range_and_its_request_are_named_for_the_probe(self):
        """The range is named for the spec it observes (its residual messages say which probe leaked) and the
        request file lives in a directory named for the probe (what a leak on disk belongs to)."""
        s = spec("app.calc:add")
        with faked("READY", "DISPATCHED", returncode=0):
            self.run_(s)
            name, argv = pc.ProcessRange.call_args.args[:2]
        self.assertEqual(name, f"probe {s.id}")
        self.assertTrue(pathlib.Path(argv[-1]).parent.name.startswith("aisef2-probe-"), argv[-1])

    def test_a_result_written_just_before_exit_is_drained_not_lost(self):
        """The anchor reports the exit while the harness's last line is still in the pipe: the protocol ends at the
        stream's own end of file, never at the exit (§9.4, V2-006), so the RESULT still on its way is read — the same
        exit must not read as 'ended before the observable'. No drain window decides it."""
        dispatched = threading.Event()

        class LateResult(FakeRange):
            def __init__(self):
                super().__init__([], 0)

                def lines():
                    for tag in ("READY", "DISPATCHED"):
                        yield f"AISEF2-PROBE {tag} n0nce \n"
                    dispatched.set()
                    time.sleep(0.3)  # the exit is reported first; the RESULT is still on its way
                    yield 'AISEF2-PROBE RESULT n0nce {"resolved": true}\n'  # the subject exists: SATISFIED
                self.output = lines()

            def wait(self, timeout=None):
                dispatched.wait(5)
                return 0
        with mock.patch.multiple(pc, ProcessRange=mock.Mock(return_value=LateResult()),
                                 secrets=mock.Mock(token_hex=mock.Mock(return_value="n0nce"))):
            result = self.run_(spec("app.calc:add"))
        self.assertEqual(result, Executed(S))  # without the drain: REFUTED, 'ended the process before the observable'

    def test_the_protocol_readers_never_hold_the_interpreter_open(self):
        """The protocol's one reader is a daemon thread: a controller that dies with a pipe still open is not kept alive
        by its own probe's reader (§17.1: a leak is never silent, and never the reader's). There is no second,
        exit-driven reader: the exit never ends the protocol (§9.4, ARCHITECTURE-EXCEPTION-V2-006)."""
        started = []
        real = threading.Thread

        class Spy(real):
            def __init__(self, *a, **kw):
                started.append(kw.get("daemon"))
                super().__init__(*a, **kw)
        with faked("READY", "DISPATCHED", returncode=0), mock.patch.object(pc.threading, "Thread", Spy):
            self.run_(spec("app.calc:add"))
        self.assertEqual(started, [True])

    def test_subject_output_cannot_forge_the_protocol(self):
        self.assertEqual(self.run_(spec("app.noisy:f", {"returns": 1})), Executed(S))

    def test_a_module_that_resolves_only_outside_the_revision_is_absent_there(self):
        self.assertEqual(self.run_(spec("json:dumps", absence=REQUIRES)), Executed(I, PA))
        self.assertIs(contract_satisfaction(self.run_(spec("json:dumps")), spec("json:dumps")), UNSAT)

    def test_an_unsupported_observation_class_is_refused_before_anything_runs(self):
        with never_runs():
            for obs, stim in (({"stdout": "x"}, {}), ({"returns": 1}, {"argv": ["x"]}), (EXISTS, {"args": [1]}),
                              ({"raises": "not an identifier"}, {}), ({"blocks": 1}, {})):
                with self.subTest(observable=obs, stimulus=stim):
                    result = self.run_(spec("app.calc:add", obs, stim))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "refused, not degraded$")

    def test_a_developer_authored_path_is_never_accepted(self):
        with never_runs():
            for locator in ("app/calc.py:add", "/abs/app/calc.py:add", "../calc:add", "app.calc", "app.calc:add()"):
                with self.subTest(locator=locator):
                    result = self.run_(spec(locator))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "a path is never accepted$")
            for locator in ("tests.test_calc:test_add", "app.test_calc:helper"):
                with self.subTest(locator=locator):
                    self.assertRegex(self.run_(spec(locator)).detail, "developer test artefact")

    def test_the_observation_class_is_read_from_the_spec(self):
        self.assertEqual([pc.spec_class(s) for s in (spec("a.b:c"), spec("a.b:c", {"returns": 1}),
                                                     spec("a.b:c", {"raises": "KeyError"}),
                                                     spec("a.b:c", {"blocks": True}),
                                                     spec("a.b:c", {"stdout": "x"}), spec("a/b.py:c"))],
                         ["exists", "returns", "raises", "blocks", None, None])
        self.assertEqual((pc.METADATA.probe_id, pc.METADATA.probe_digest), (P.id, P.digest))
        self.assertIs(pc.METADATA.observation_class, pc.spec_class)
        other_kind = ProductProofSpec.create(**{**{f: getattr(spec("a.b:c"), f) for f in (
            "contract_id", "probe_id", "probe_digest", "candidate_expectation", "compiler_id", "compiler_digest")},
            "probe_input": {**spec("a.b:c").probe_input, "subject": {"kind": "cli_invocation", "locator": "a.b:c"}}})
        self.assertIsNone(pc.spec_class(other_kind))

    def test_enforcement_is_declared_bound_and_never_degraded(self):
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        rec = run_probe(P, spec("app.calc:add"), self.product, env())
        self.assertIs(rec.enforcement, Enforcement.PARTIAL)
        refused = run_probe(P, spec("app.calc:add"), self.product, env(required=Enforcement.FULL))
        self.assertIs(refused.result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(refused.enforcement, Enforcement.PARTIAL)


class LayoutInvariance(unittest.TestCase):
    """Invariant IX / P2 exit: product verdicts are identical whatever the developer's test layout."""

    LAYOUTS = {
        "no tests": {},
        "tests/ at the root": {"tests/__init__.py": "", "tests/test_calc.py": "from app.calc import add\n"},
        "tests inside the package": {"app/tests/__init__.py": "", "app/tests/test_calc.py": "import app.calc\n"},
        "broken tests": {"tests/test_calc.py": "def (:\n", "conftest.py": "raise SystemExit(4)\n",
                         "app/test_calc.py": "import no_such_module\n"},
    }
    SPECS = {"exists": spec("app.calc:add"), "absent": spec("app.telemetry:send"),
             "requires absent": spec("app.telemetry:send", absence=REQUIRES),
             "returns": spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}),
             "raises": spec("app.calc:boom", {"raises": "ValueError"})}

    def test_product_verdicts_are_identical_across_test_layouts(self):
        seen = {}
        for name, extra in self.LAYOUTS.items():
            at = RevisionRef(SHA, checkout({**PRODUCT, **extra}))
            seen[name] = {k: run_probe(P, s, at, env()).result for k, s in self.SPECS.items()}
        first = next(iter(seen.values()))
        self.assertEqual(first, {"exists": Executed(S), "absent": Executed(R), "requires absent": Executed(I, PA),
                                 "returns": Executed(S), "raises": Executed(S)})
        for name, results in seen.items():
            with self.subTest(layout=name):
                self.assertEqual(results, first)


class Identity(unittest.TestCase):
    def test_the_digest_is_stable_across_processes(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import aisef2.probe.python_callable as m; "
                "print(m.PythonCallableProbe.digest)")
        out = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(out.stdout.strip(), P.digest)
        self.assertRegex(P.digest, "^[0-9a-f]{64}$")

    def test_the_digest_covers_exactly_the_sources_it_names(self):
        """A source dropped from the identity would let the probe change while its digest did not (§35, V2-003)."""
        import hashlib
        self.assertEqual(tuple(pc.PROBE_SOURCES), ("probe/protocol.py", "probe/python_callable.py"))

        def digest_of(files):  # the composition, stated here rather than taken from the module
            h = hashlib.sha256()
            for rel, data in files:
                h.update(rel.encode() + b"\0" + data + b"\0")
            return h.hexdigest()
        files = [(rel, (ROOT / "aisef2" / rel).read_bytes().replace(b"\r\n", b"\n")) for rel in pc.PROBE_SOURCES]
        self.assertEqual(digest_of(files), P.digest)
        for i, (rel, data) in enumerate(files):
            with self.subTest(source=rel):
                changed = list(files)
                changed[i] = (rel, data + b"# changed\n")
                self.assertNotEqual(digest_of(changed), P.digest)
                self.assertNotEqual(digest_of(files[:i] + files[i + 1:]), P.digest)

    def test_the_digest_is_bound_into_the_spec_and_a_stale_binding_is_refused(self):
        req = Requirement.create(id="REQ-P", text="adds", source="docs/req.md")
        c = BehaviorContract.create(id="BC-ADD", requirement_ids=("REQ-P",),
                                    subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"),
                                    stimulus={"args": [1, 2]}, observable={"returns": 3, "within_s": W},
                                    polarity=Polarity.MUST_HOLD,
                                    subject_absence=REQUIRES, rationale="adds")
        approvals = [ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())]
        compiled = compile_spec(c, requirements={req.id: req}, approvals=approvals,
                                probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, P.digest)})
        self.assertEqual((compiled.probe_id, compiled.probe_digest), (P.id, P.digest))
        stale = compile_spec(c, requirements={req.id: req}, approvals=approvals,
                             probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, "0" * 64)})
        self.assertNotEqual(stale.semantic_hash, compiled.semantic_hash)
        at = RevisionRef(SHA, checkout(PRODUCT))
        self.assertEqual(run_probe(P, compiled, at, env()).result, Executed(S))
        self.assertIs(run_probe(P, stale, at, env()).result.status, ProbeExecutionStatus.INVALID_SPEC)


if __name__ == "__main__":
    unittest.main()
