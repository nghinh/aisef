"""WP-2.2.1 — the `cli_invocation` probe's marker-file protocol, in-process: the parent's decision table over test
doubles of the owned range (FakeRange: the lines the child would write, how the process ended, what the controller
signalled), the refusals that run nothing, the identity and the Q0 rules. No subprocess but the digest check, so the
mutation runner lists this module first: a mutant of the watch loop, the hard-exit rule or the harness-failure rule
dies here in a second, and only a survivor pays for tests/v2/test_c2_cli_invocation.py (the real subjects).

FM2 rows split between the two modules keep their row prefix (the evidence harness reads the union)."""

import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Enforcement, MeasurementPoint, ObligationRole, Owner, ProbeExecutionStatus, SubjectKind  # noqa: E402
from aisef2.control.owner import FailureCode  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.probe import catalog, cli_invocation as ci  # noqa: E402
from aisef2.probe.cli_invocation import CliInvocationProbe  # noqa: E402
from aisef2.probe.protocol import Observation, ObservationKind as K, ProbeInterrupted, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2.test_c2_cli_invocation import (  # noqa: E402
    EXIT0, I, NCS, P, R, S, SHA, W, FakeRange, _Product, facts_of, faked, never_runs, refuses, sha, spec,
)


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
            self.assertEqual(self.see(s, e=env_with(gone)),
                             Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"))
            self.assert_unrunnable(s, self.run_(s, e=env_with(gone)))
            self.assert_unrunnable(s, self.run_(s, at=RevisionRef(SHA, os.path.join(self.empty.root, "gone"))),
                                   "cannot inspect: the revision checkout is missing")
        with refuses(OSError("cannot launch")):
            self.assert_unrunnable(s, self.run_(s), "the harness cannot launch: OSError")
        with refuses(ci.RangeError("no anchor")):   # a range that refuses to start is a launch failure, like OSError
            self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the harness cannot launch: RangeError"))

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

    def test_FM2_CLI_HARNESS_4b_workspace_that_cannot_be_laid_out(self):
        s = spec("app:__main__")
        with never_runs(), mock.patch.object(ci, "_prepare", side_effect=PermissionError("denied")):
            self.assert_unrunnable(s, self.run_(s), "the evaluation directory cannot be prepared: PermissionError")


def env_with(interpreter):
    from tests.v2.test_c2_cli_invocation import env
    return env(interpreter=interpreter)


class Concluded(unittest.TestCase):
    """ci._concluded as a unit: each conclusion a controller's RESULT can carry, decided with a `decide` that would say
    SATISFIED — a conclusion that fell through to the decision would show — and its (observation, facts) pair whole."""
    RUN = types.SimpleNamespace(ledger=[])   # _after_dispatch reads the controller's signal ledger only: empty here

    def concluded(self, facts):
        return ci._concluded(self.RUN, facts, lambda f: S)

    def test_each_conclusion_and_the_facts_only_a_decided_one_returns(self):
        signal = Observation(K.NON_CONTROLLER_SIGNAL, detail="the subject's process ended by signal 9 after DISPATCHED, "
                                                             "and this controller's signal ledger is empty: it did not send it")
        tampered = {"subject": "present", "tampered": "x"}
        cases = {"a signal the controller did not send": ({"subject_signal": 9}, (signal, None)),
                 # defensive: today's controller script reports no failure of its own this way (it ends without a RESULT)
                 "the controller's own failure": ({"harness_failure": "boom"}, (Observation(K.HARNESS_FAILED, detail="boom"), None)),
                 "an absent subject": ({"subject": "absent", "note": "n"}, (Observation(K.SUBJECT_ABSENT, R, detail="n"), None)),
                 "an answer that is not the agent's": (tampered, (Observation(K.OBSERVED, R, detail=json.dumps(tampered)), None))}
        for name, (facts, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.concluded(facts), want)
        facts = {"subject": "present", "exit_code": 0}
        self.assertEqual(self.concluded(facts), (Observation(K.OBSERVED, S, detail=json.dumps(ci._public(facts))), facts))


class FaultStream(_Product):
    def test_FM2_CLI_STREAM_1b_exit_before_READY_or_DISPATCHED_on_the_range(self):
        s = spec("app:__main__")
        with faked(returncode=-9):
            self.assertEqual(self.see(s).detail, "the harness process was killed by signal 9 before READY")
        with faked("READY", returncode=0):
            self.assertEqual(self.see(s).detail, "the harness did not start (exit 0, no DISPATCHED): tool absent or broken")
            self.assertIs(self.run_(s).status, ProbeExecutionStatus.UNRUNNABLE)
        with faked("READY", returncode=-9):
            self.assertEqual(self.see(s).detail, "the harness process was killed by signal 9 before DISPATCHED")

    def test_FM2_CLI_STREAM_2_after_DISPATCHED_the_controller_reports_how_the_subject_ended(self):
        """B1: the subject runs in a process of its own, a child of the controller; the controller, which outlives it,
        reports in RESULT a hard exit (its exit code, the captured streams, the files) or a signal. The controller's
        own process ending with no RESULT is the observation mechanism failing; ended by a signal this controller did
        not send, it is NON_CONTROLLER_SIGNAL (§9.3), as before."""
        s = spec("app:__main__", EXIT0, {"argv": ["echo"]})
        empty = {"size": 0, "truncated": False, "sha256": sha(b"")}
        hard = {"subject": "present", "exit_code": 0, "hard_exit": True, "stdout": empty, "stderr": empty, "before": {},
                "files": {}}
        fake = FakeRange(("READY", "DISPATCHED", 'MAIN {"before": {}}', "RESULT " + json.dumps(hard)), 0)
        with mock.patch.object(ci, "ProcessRange", fake):
            o = self.see(s)
        self.assertEqual((o.kind, o.verdict, facts_of(o)), (K.OBSERVED, S, hard))
        self.assertEqual((fake.name, fake.released), (f"probe {s.id}", True))   # the range is named for the spec
        with faked("READY", "DISPATCHED", "RESULT " + json.dumps({**hard, "exit_code": 4}), returncode=0):
            self.assertEqual(self.see(s).verdict, R)
            self.assertEqual(self.see(spec("app:__main__", {"exit_code": 4}, {"argv": ["echo"]})).verdict, S)
            self.assertEqual(self.see(spec("app:__main__", {"blocks": True}, {"argv": ["echo"]})).verdict, R)
        # the files named by the observable, against what the controller recorded before the main invocation
        files = {"<ws>/a": {"equals_before": True}, "<ws>/b": {"absent": True}}
        absent = {"a": {"absent": True}, "b": {"absent": True}}
        with faked("READY", "DISPATCHED", "RESULT " + json.dumps({**hard, "before": absent, "files": absent}), returncode=0):
            o = self.see(spec("app:__main__", {"exit_code": 0, "files": files}, {"argv": ["echo"]}))
        self.assertEqual((o.verdict, facts_of(o)["before"], facts_of(o)["files"]), (S, absent, absent))
        moved = {**hard, "before": {"a": {"sha256": "00"}, "b": {"absent": True}}, "files": absent}
        with faked("READY", "DISPATCHED", "RESULT " + json.dumps(moved), returncode=0):
            self.assertEqual(self.see(spec("app:__main__", {"exit_code": 0, "files": files}, {"argv": ["echo"]})).verdict, R)
        pre = {"subject": "present", "pre_failed": 0, "exit_code": 3, "hard_exit": True}   # it ended in a pre-step
        with faked("READY", "DISPATCHED", "PRE 0", "RESULT " + json.dumps(pre), returncode=0):
            o = self.see(spec("app:__main__", {"exit_code": 3}, {"argv": ["echo"], "pre": [{"argv": ["echo"]}]}))
        self.assertEqual((o.kind, o.verdict, facts_of(o)), (K.OBSERVED, R, pre))
        # the subject's process ended by a signal the controller did not send: the controller says so (§9.3)
        ladder = [{"stage": "terminate", "signal": "SIGTERM"}, {"stage": "kill", "signal": "SIGKILL"}]
        with faked("READY", "DISPATCHED", 'RESULT {"subject_signal": 9}', returncode=0):
            o = self.see(s)
            self.assertEqual(self.run_(s), Executed(I, NCS))
        self.assertEqual(o, Observation(K.NON_CONTROLLER_SIGNAL, detail="the subject's process ended by signal 9 after "
                                                                        "DISPATCHED, and this controller's signal ledger "
                                                                        "is empty: it did not send it"))
        with faked("READY", "DISPATCHED", 'RESULT {"subject_signal": 9}', returncode=0, ledger=ladder):
            with self.assertRaises(ProbeInterrupted):   # the controller stopped it: an interruption, never a measurement
                self.see(s)
        # an answer on the subject's channel that is not the agent's: REFUTED whatever the class (B1)
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "tampered": "x"}', returncode=0):
            for observable in (EXIT0, {"blocks": True}):
                o = self.see(spec("app:__main__", observable, {"argv": ["echo"]}))
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
        # the same two conclusions in a half of an equality (which unpacks each half's observation AND facts): that
        # half's observation is the answer
        halves = {"stimulus_a": {"argv": ["echo"]}, "stimulus_b": {"argv": ["echo"]}, "normalization": {}, "comparator": "bytes_equal"}
        eq = ProductProofSpec.create(   # an equality's own stimulus is empty: its halves carry theirs
            contract_id="BC-CLI", probe_id=P.id, probe_digest=P.digest, compiler_id="test", compiler_digest="c" * 64,
            probe_input={"subject": {"kind": "cli_invocation", "locator": "app:__main__"}, "stimulus": {},
                         "observable": {"equality": halves, "streams": ["stdout"], "within_s": W}, "subject_absence": "REQUIRES_SUBJECT"},
            candidate_expectation=S)
        self.assertEqual(ci.spec_class(eq), "equality")
        with faked("READY", "DISPATCHED", 'RESULT {"subject_signal": 9}', returncode=0):
            self.assertEqual(self.see(eq).kind, K.NON_CONTROLLER_SIGNAL)
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "tampered": "x"}', returncode=0):
            self.assertEqual((self.see(eq).kind, self.see(eq).verdict), (K.OBSERVED, R))
        # the controller's own process ended with no RESULT: the mechanism failed, whatever line it wrote last
        for tags in (("READY", "DISPATCHED"), ("READY", "DISPATCHED", 'MAIN {"before": {}}'), ("READY", "DISPATCHED", "PRE 0")):
            with self.subTest(tags=tags), faked(*tags, returncode=3):
                self.assertEqual(self.see(s), Observation(K.HARNESS_FAILED, detail="the probe's controller ended without "
                                                                                   "a result (exit 3)"))
                self.assertIs(self.run_(s).status, ProbeExecutionStatus.UNRUNNABLE)
        with faked("READY", "DISPATCHED", returncode=-9):   # a signal the controller did not send (§9.3)
            o = self.see(s)
            self.assertEqual(self.run_(s), Executed(I, NCS))
        self.assertEqual(o, Observation(K.NON_CONTROLLER_SIGNAL, detail="the process ended by signal 9 after DISPATCHED, "
                                                                        "and this controller's signal ledger is empty: it "
                                                                        "did not send it"))
        with faked("READY", "DISPATCHED", returncode=-9, ledger=ladder):
            with self.assertRaises(ProbeInterrupted) as stopped:   # the same exit, the controller's own signal
                self.see(s)
        self.assertEqual((stopped.exception.signal, stopped.exception.stage), (9, "kill"))

    def test_FM2_CLI_STREAM_5b_marker_file_never_opened(self):
        with faked("READY", "DISPATCHED", returncode=0, write=False):
            self.assertEqual(self.see(spec("app:__main__")).detail,
                             "the harness did not start (exit 0, no READY): tool absent or broken")

    def test_the_marker_file_poll_reports_a_line_an_exit_or_a_timeout_and_re_reads_after_the_exit(self):
        """`_await`: ("LINE", seen) when the tag is in the file — before the exit, or only in the re-read the exit
        triggers (§9.4: the exit never ends the protocol); ("EXITED", seen) when the process exited without it;
        ("TIMEOUT", seen) when the deadline passes with the process still running."""
        work = tempfile.mkdtemp(prefix="aisef2-cli-poll-")
        proto = os.path.join(work, "protocol.log")
        key = "ab" * 32

        def line(tag, body=""):
            return f"AISEF2-PROBE {tag} n0nce {ci._mac(bytes.fromhex(key), tag, body)}" + (f" {body}" if body else "") + "\n"
        lines = line("READY") + line("DISPATCHED")

        class Exited:
            returncode = 0

            def wait(self, timeout=None):
                return 0

        class Running:
            def wait(self, timeout=None):
                return None

        class LateWriter(Exited):   # the exit is reported first; the file holds the lines when read once more
            def wait(self, timeout=None):
                pathlib.Path(proto).write_text(lines + line("RESULT", "{}"), encoding="utf-8")
                return 0
        pathlib.Path(proto).write_text(lines, encoding="utf-8")
        self.assertEqual(ci._await(Running(), proto, "n0nce", key, "DISPATCHED", time.monotonic() + 5),
                         ("LINE", {"READY": [""], "DISPATCHED": [""]}))
        self.assertEqual(ci._await(Exited(), proto, "n0nce", key, "RESULT", time.monotonic() + 5),
                         ("EXITED", {"READY": [""], "DISPATCHED": [""]}))
        self.assertEqual(ci._await(Running(), proto, "n0nce", key, "RESULT", time.monotonic() + 0.1)[0], "TIMEOUT")
        # B1: a RESULT line without the key's authentication (a subject that read the nonce in the file) is never seen
        pathlib.Path(proto).write_text(lines + "AISEF2-PROBE RESULT n0nce " + "0" * 64 + " {}\n", encoding="utf-8")
        self.assertEqual(ci._await(Exited(), proto, "n0nce", key, "RESULT", time.monotonic() + 5),
                         ("EXITED", {"READY": [""], "DISPATCHED": [""]}))
        pathlib.Path(proto).write_text("", encoding="utf-8")
        self.assertEqual(ci._await(LateWriter(), proto, "n0nce", key, "RESULT", time.monotonic() + 5),
                         ("LINE", {"READY": [""], "DISPATCHED": [""], "RESULT": ["{}"]}))
        # and through the harness: the exit reported before any line was read still yields the complete result
        s = spec("app:__main__", EXIT0, {"argv": ["echo"]})

        class LateRange(FakeRange):
            def start(self):
                import json
                self.req = json.loads(pathlib.Path(self.argv[-1]).read_text(encoding="utf-8"))
                return self

            def wait(self, timeout=None):
                k, n, body = bytes.fromhex(self.req["key"]), self.req["nonce"], '{"subject": "present", "exit_code": 0}'
                pathlib.Path(self.req["protocol"]).write_text(
                    f"AISEF2-PROBE READY {n} {ci._mac(k, 'READY', '')}\nAISEF2-PROBE DISPATCHED {n} {ci._mac(k, 'DISPATCHED', '')}\n"
                    f"AISEF2-PROBE RESULT {n} {ci._mac(k, 'RESULT', body)} {body}\n", encoding="utf-8")
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

    def test_C2_P2_FINDING_002_a_controller_stop_with_no_status_reported_is_an_interruption(self):
        """On Windows the controller's TerminateJobObject takes the range's anchor down with the job, so the stop
        reports no exit status: after DISPATCHED the ledger is asked first (§9.3), as on every other path."""
        class Vanished(FakeRange):
            def wait(self, timeout=None):
                return None
        ledger = [{"stage": "terminate_job", "signal": "TerminateJobObject", "at": 0.0}]
        with mock.patch.object(ci, "ProcessRange", Vanished(("READY", "DISPATCHED"), None, ledger)), \
                mock.patch.object(ci, "_COLLECT_S", 0.05), self.assertRaises(ProbeInterrupted) as stopped:
            self.see(spec("app:__main__", EXIT0, {"argv": ["echo"]}, window=0.3))
        self.assertEqual(stopped.exception.stage, "terminate_job")
        self.assertIn("what the subject did is not known", stopped.exception.detail)

    def test_C2_P2_FINDING_003_the_evaluation_directory_is_disposed_through_a_passing_sharing_violation(self):
        """Windows: a member TerminateJobObject just ended can still hold handles inside the evaluation directory for a
        moment after the range is measured empty; the probe-owned directory's disposal waits that out, bounded."""
        class Holder:
            def __init__(self, fails, error=PermissionError):
                self.fails, self.error, self.exits = fails, error, 0

            def __enter__(self):
                return "work"

            def __exit__(self, *exc):
                self.exits += 1
                if self.exits <= self.fails:
                    raise self.error("[WinError 32] in use by another process")
        with mock.patch.object(ci, "POLL_S", 0.001):
            passing = Holder(2)
            with ci._disposed(passing) as work:
                self.assertEqual(work, "work")
            self.assertEqual(passing.exits, 3)                     # two sharing violations, then disposed
            other = Holder(1, OSError)
            with self.assertRaises(OSError), ci._disposed(other):  # any other failure is raised at once
                pass
            self.assertEqual(other.exits, 1)
            body = Holder(0)
            with self.assertRaises(ProbeInterrupted), ci._disposed(body):   # the body's own outcome passes through
                raise ProbeInterrupted("stopped", signal=None, stage="terminate_job")
            self.assertEqual(body.exits, 1)
            with mock.patch.object(ci, "DISPOSE_S", 0.05):
                stuck = Holder(10 ** 6)
                started = time.monotonic()
                with self.assertRaises(PermissionError), ci._disposed(stuck):   # still in use: a leak, raised
                    pass
                self.assertLess(time.monotonic() - started, 5)
                self.assertGreater(stuck.exits, 1)
        self.assertEqual(ci.DISPOSE_S, 10.0)

    def test_the_internal_observation_carries_its_facts_on_every_path(self):
        """`_observe` answers (Observation, facts): the facts the harness reported (or the hard-exit facts) with an
        OBSERVED observation, None with every other kind — the channel the equality class reads."""
        s = spec("app:__main__", EXIT0, {"argv": ["echo"]})
        args = (s.id, "exits", "app:__main__", {"argv": ["echo"]}, {"exit_code": 0, "within_s": W})
        gone = os.path.join(self.empty.root, "no-python")
        inside = os.path.join(self.at.root, "scratch-in-tree")
        os.makedirs(inside, exist_ok=True)
        e = env_with(sys.executable)
        with never_runs():
            self.assertEqual(P._observe(*args, self.at, env_with(gone)),
                             (Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"), None))
            self.assertEqual(P._observe(*args, RevisionRef(SHA, gone), e),
                             (Observation(K.HARNESS_FAILED, detail="cannot inspect: the revision checkout is missing"), None))
            self.assertEqual(CliInvocationProbe(scratch=gone)._observe(*args, self.at, e),
                             (Observation(K.HARNESS_FAILED, detail="the evaluation directory cannot be created: "
                                                                   "FileNotFoundError"), None))
            self.assertEqual(CliInvocationProbe(scratch=inside)._observe(*args, self.at, e),
                             (Observation(K.HARNESS_FAILED, detail="the evaluation directory lies inside the revision "
                                                                   "checkout: refused"), None))
            with mock.patch.object(ci, "_prepare", side_effect=PermissionError("denied")):
                self.assertEqual(P._observe(*args, self.at, e),
                                 (Observation(K.HARNESS_FAILED, detail="the evaluation directory cannot be prepared: "
                                                                       "PermissionError"), None))
        with refuses(OSError("cannot launch")):
            self.assertEqual(P._observe(*args, self.at, e),
                             (Observation(K.HARNESS_FAILED, detail="the harness cannot launch: OSError"), None))
        with faked("READY", returncode=0):
            self.assertEqual(P._observe(*args, self.at, e),
                             (Observation(K.HARNESS_FAILED, detail="the harness did not start (exit 0, no DISPATCHED): "
                                                                   "tool absent or broken"), None))
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "absent", "note": "n"}', returncode=0):
            self.assertEqual(P._observe(*args, self.at, e), (Observation(K.SUBJECT_ABSENT, R, "n"), None))
        with faked("READY", "DISPATCHED", returncode=-9):
            o, facts = P._observe(*args, self.at, e)
            self.assertEqual((o.kind, facts), (K.NON_CONTROLLER_SIGNAL, None))
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "present", "exit_code": 0, "pre": []}', returncode=0):
            self.assertEqual(P._observe(*args, self.at, e),
                             (Observation(K.OBSERVED, S, '{"subject": "present", "exit_code": 0, "pre": []}'),
                              {"subject": "present", "exit_code": 0, "pre": []}))
        hard = {"subject": "present", "exit_code": 2, "hard_exit": True, "before": {}, "files": {},
                "stdout": {"path": "/w/stdout.bin", "size": 0, "truncated": False, "sha256": sha(b"")},
                "stderr": {"path": "/w/stderr.bin", "size": 0, "truncated": False, "sha256": sha(b"")}}
        with faked("READY", "DISPATCHED", 'MAIN {"before": {}}', "RESULT " + json.dumps(hard), returncode=0):
            o, facts = P._observe(*args, self.at, e)
            self.assertEqual((o.kind, o.verdict, facts["exit_code"], facts["hard_exit"], "path" in facts["stdout"]),
                             (K.OBSERVED, R, 2, True, True))
        pre = {"subject": "present", "pre_failed": 0, "exit_code": 2, "hard_exit": True}
        with faked("READY", "DISPATCHED", "PRE 0", "RESULT " + json.dumps(pre), returncode=0):
            o, facts = P._observe(s.id, "exits", "app:__main__", {"argv": ["echo"], "pre": [{"argv": ["a"]}]},
                                  {"exit_code": 2, "within_s": W}, self.at, e)
            self.assertEqual((o.verdict, facts), (R, pre))
        with faked("READY", "DISPATCHED", 'MAIN {"before": {}}', returncode=2):   # the controller ended with no RESULT
            self.assertEqual(P._observe(*args, self.at, e),
                             (Observation(K.HARNESS_FAILED, detail="the probe's controller ended without a result (exit 2)"),
                              None))

        class Vanished(FakeRange):
            def wait(self, timeout=None):
                return None
        with mock.patch.object(ci, "ProcessRange", Vanished(("READY", "DISPATCHED"), None)), \
                mock.patch.object(ci, "_COLLECT_S", 0.05):
            o, facts = P._observe(s.id, "exits", "app:__main__", {"argv": ["echo"]}, {"exit_code": 0, "within_s": 0.3},
                                  self.at, e)
        self.assertEqual((o.kind, facts), (K.HARNESS_FAILED, None))
        # the equality path's halves take the same channel; a half that is not a returned invocation is the observation
        eq = ProductProofSpec.create(
            contract_id="BC-EQ", probe_id=P.id, probe_digest=P.digest,
            probe_input={"subject": {"kind": "cli_invocation", "locator": "app:__main__"}, "stimulus": {},
                         "observable": {"equality": {"stimulus_a": {"argv": ["echo"]}, "stimulus_b": {"argv": ["echo"]},
                                                     "normalization": {}, "comparator": "bytes_equal"},
                                        "streams": ["stdout"], "within_s": W}, "subject_absence": "REQUIRES_SUBJECT"},
            candidate_expectation=S, compiler_id="test", compiler_digest="c" * 64)
        with faked("READY", "DISPATCHED", 'RESULT {"subject": "absent"}', returncode=0):
            self.assertEqual(self.see(eq).kind, K.SUBJECT_ABSENT)
        with faked("READY", "DISPATCHED", returncode=-9):
            self.assertEqual(self.see(eq).kind, K.NON_CONTROLLER_SIGNAL)
        fake = FakeRange(("READY", "DISPATCHED", 'RESULT {"subject": "present", "exit_code": 0, "stdout": {"size": 0}}'), 0)
        with mock.patch.object(ci, "ProcessRange", fake):
            o = self.see(eq)
        self.assertEqual((o.kind, o.verdict, facts_of(o)["subject"], facts_of(o)["distinct_evaluation_directories"]),
                         (K.OBSERVED, S, "present", True))
        self.assertEqual(fake.name, f"probe {eq.id}/b")   # each half's range is named for the spec and its side
        both_hard = {"subject": "present", "exit_code": 0, "hard_exit": True, "stdout": {"size": 0}}
        with faked("READY", "DISPATCHED", "RESULT " + json.dumps(both_hard), returncode=0):   # two hard exits, equal captures
            self.assertEqual(self.see(eq).verdict, S)
        with faked("READY", "DISPATCHED", "PRE 0", 'RESULT {"subject": "present", "pre_failed": 0, "exit_code": 3, '
                   '"hard_exit": true}', returncode=0):   # a half whose pre-step failed is the observation
            o = self.see(eq)
        self.assertEqual((o.kind, o.verdict, facts_of(o)["pre_failed"]), (K.OBSERVED, R, 0))
        with never_runs():
            self.assertEqual(self.see(eq, e=env_with(gone)), Observation(K.HARNESS_FAILED, detail=f"interpreter absent: {gone}"))
            self.assertEqual(CliInvocationProbe(scratch=gone).observe(eq, self.at, e),
                             Observation(K.HARNESS_FAILED, detail="the evaluation directory cannot be created: "
                                                                  "FileNotFoundError"))
            self.assertEqual(CliInvocationProbe(scratch=inside).observe(eq, self.at, e),
                             Observation(K.HARNESS_FAILED, detail="the evaluation directory lies inside the revision "
                                                                  "checkout: refused"))
            # DECISION-4: the policy and the comparator are bound, never defaulted — one left out is refused
            for gone_key in ("normalization", "comparator"):
                eq_in = {k: v for k, v in eq.probe_input["observable"]["equality"].items() if k != gone_key}
                partial = ProductProofSpec.create(**{**{f: getattr(eq, f) for f in (
                    "contract_id", "probe_id", "probe_digest", "candidate_expectation", "compiler_id", "compiler_digest")},
                    "probe_input": {**eq.probe_input, "observable": {**eq.probe_input["observable"], "equality": eq_in}}})
                with self.subTest(left_out=gone_key):
                    result = self.run_(partial)
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "refused, not degraded$")


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
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        self.assertIn("not a sandbox", ci.WEAKEST_PATH)
        self.assertEqual(len(P.harness_preconditions()), 4)
        with never_runs():
            refused = run_probe(P, spec("app:__main__"), self.at, env_with(sys.executable).__class__(
                sys.executable, 20, Enforcement.FULL))
        self.assertIs(refused.result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(refused.enforcement, Enforcement.PARTIAL)

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

    def test_CLI_Q0_the_module_passes_the_probe_rules_with_its_catalog_facts(self):
        sys.path.insert(0, str(ROOT / "validation" / "v2"))
        import probe_static_checks as ps
        src = (ROOT / "aisef2/probe/cli_invocation.py").read_text(encoding="utf-8")
        facts = {"subject_process": "child_of_harness", "stimulus_shape": "invocation"}
        self.assertEqual(ps.violations("aisef2/probe/cli_invocation.py", src, ps.SOURCE_RULES, facts), [])
        self.assertEqual(ps.check(ROOT), [])   # catalog closure: registered, digest live, fixtures for every class
        scripts = ps.child_scripts(ast.parse(src))
        self.assertEqual([name for name, _, _ in scripts], ["AGENT", "HARNESS"])   # B1: the subject's process, the controller
        # the channel rule is what rejects a harness that puts its protocol on the subject's stdout
        self.assertEqual(src.count('    proto.write((req["mark"]'), 1)
        forged = src.replace('    proto.write((req["mark"]', '    sys.stdout.write((req["mark"]')
        self.assertTrue(any("PROTOCOL_CHANNEL_DISCIPLINE" in v
                            for v in ps.violations("aisef2/probe/cli_invocation.py", forged, ps.SOURCE_RULES, facts)))


if __name__ == "__main__":
    unittest.main()
