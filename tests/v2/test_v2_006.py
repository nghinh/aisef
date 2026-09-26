"""ARCHITECTURE-EXCEPTION-V2-006 — protocol stream vs process lifecycle in the probe harness (RFC §9.4, F5).

P6-FINDING-001: the anchor's exit notice could reach the reader before the pump delivered a READY the target had
already written, and before DISPATCHED that read as "the harness did not start" — a false UNRUNNABLE on one party, a
false VERIFIER_DISAGREEMENT between two. The fix is structural: the anchor holds no copy of the target's output writer
(the stream's end of file is the target's own), and one pump reads every line and then publishes STREAM_CLOSED; the
exit is asked of the range only after that. These cases inject the orderings the operating system may choose — a
late pump, the exit reported before the pump runs — and demand the result of normal scheduling.

RACE-1..9 here; RACE-10 (every injected ordering, repeated) is tests/v2/test_v2_006_repeat.py.
"""

import os
import pathlib
import queue
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ProbeExecutionStatus  # noqa: E402
from aisef2.probe import python_callable as pc  # noqa: E402
from aisef2.probe.protocol import RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from aisef2.runtime.process_range import ProcessRange  # noqa: E402
from tests.v2.p2.test_python_callable import PRODUCT, SHA, R, S, P, checkout, env, spec  # noqa: E402

REAL_PUMP = pc._pump
REAL_RANGE = pc.ProcessRange
REAL_FAILURE = pc._harness_failure


class Ordering:
    """Force an ordering the scheduler may choose: `delay` holds the pump back before it reads anything; `exit_first`
    holds it until the range has reported the target's exit (the exit notice delivered before the pump is scheduled).
    Records what happened: whether the exit was known before the first line was read, whether the pump had published
    STREAM_CLOSED before a harness failure was concluded, and how many were concluded."""

    def __init__(self, delay=0.0, exit_first=False):
        self.delay, self.exit_first = delay, exit_first
        self.ranges, self.exit_known_first, self.closed = [], [], threading.Event()
        self.failures_after_close = []

    def __enter__(self):
        def make(*a, **kw):
            r = REAL_RANGE(*a, **kw)
            self.ranges.append(r)
            return r

        closed = self.closed

        class Published:  # marks STREAM_CLOSED at the moment the pump publishes it, before any reader can see it
            def __init__(self, lines):
                self.lines = lines

            def put(self, item):
                if item is None or item[0] == "STREAM_CLOSED":   # None: the end marker before V2-006 (red-before runs)
                    closed.set()
                self.lines.put(item)

        def pump(stream, lines):
            if self.exit_first:
                self.exit_known_first.append(self.ranges[-1].wait(10) is not None)
            if self.delay:
                time.sleep(self.delay)  # fault injection: the scheduler's choice, forced
            REAL_PUMP(stream, Published(lines))

        def failure(*a, **kw):
            self.failures_after_close.append(self.closed.is_set())
            return REAL_FAILURE(*a, **kw)
        self._patch = mock.patch.multiple(pc, ProcessRange=make, _pump=pump, _harness_failure=failure)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


def harness(source):
    """Replace the harness script: a real process in a real range, emitting only what `source` writes."""
    return mock.patch.object(pc, "HARNESS", source)


#: writes READY with this run's nonce, but never its newline, then exits 0 — a partial protocol line
PARTIAL_READY = ("import json, sys\nreq = json.load(open(sys.argv[1], encoding='utf-8'))\n"
                 "sys.stdout.write('\\n%s READY %s ' % (req['mark'], req['nonce']))\nsys.stdout.flush()\n")
#: writes every protocol line after 400 lines of noise, then exits at once
NOISY_HARNESS = "import sys\nsys.stdout.write('noise line\\n' * 400)\nsys.stdout.flush()\n" + pc.HARNESS


class _Probe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = RevisionRef(SHA, checkout(PRODUCT))

    def record(self, s=None):
        return run_probe(P, s or spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}), self.product, env())


class Race(_Probe):
    def setUp(self):
        self.normal = self.record()
        self.assertEqual(self.normal.result, Executed(S))

    def test_RACE_1_a_READY_written_before_exit_is_observed_however_late_the_pump(self):
        with Ordering(delay=0.5) as o:
            got = self.record()
        self.assertEqual(got, self.normal)                  # READY observed: no harness failure, the same record
        self.assertEqual(o.failures_after_close, [])

    def test_RACE_2_READY_DISPATCHED_RESULT_then_immediate_exit_is_the_complete_result(self):
        refuted = spec("app.calc:add", {"returns": 4}, {"args": [1, 2]})
        with Ordering(exit_first=True, delay=0.2) as o:
            got, got_r = self.record(), self.record(refuted)
        self.assertEqual(o.exit_known_first, [True, True])  # the exit was reported before a single line was read
        self.assertEqual((got, got_r), (self.normal, self.record(refuted)))
        self.assertEqual(got_r.result, Executed(R))         # the RESULT's content decides, not a default

    def test_RACE_3_the_exit_notice_before_the_pump_is_scheduled_gives_the_normal_result(self):
        with Ordering(exit_first=True) as o:
            got = self.record()
        self.assertEqual(o.exit_known_first, [True])
        self.assertEqual(got, self.normal)
        self.assertEqual(o.failures_after_close, [])

    def test_RACE_4_one_party_late_the_other_normal_gives_identical_records(self):
        with Ordering(delay=0.3, exit_first=True):
            late = self.record()
        self.assertEqual(late.record_digest, self.normal.record_digest)   # nothing for a verifier to disagree on
        self.assertEqual(late.result, self.normal.result)


class StoryRace(unittest.TestCase):
    def test_RACE_4_a_story_with_one_party_late_on_every_proof_commits_with_agreement(self):
        from tests.v2 import test_p6_orchestration as e2e
        calls = []

        def every_second_late(stream, lines):
            calls.append(1)
            if len(calls) % 2 == 0:
                time.sleep(0.3)
            REAL_PUMP(stream, lines)
        case = e2e.Orchestration("test_ORCH_1_an_end_to_end_story_completes_through_the_real_path")
        case.setUp()
        try:
            with mock.patch.object(pc, "_pump", every_second_late):
                r = case.story(case.s1_plan(), "S1", case.s1_dev())
            case.assertCommitted(r)
            verified = case.events("proof/verified", "S1")
            self.assertTrue(verified and all(e.data["agreement"] for e in verified))
            for e in verified:
                a, b = (case.run.events[s].data["record"] for s in e.source_seqs)
                self.assertEqual(a["result"], b["result"])
            self.assertEqual(case.failures("S1"), [])
            self.assertGreaterEqual(len(calls), 4)
        finally:
            case.doCleanups()


class TrueEnd(_Probe):
    def test_RACE_5_a_harness_that_emits_nothing_and_exits_0_did_not_start_after_the_stream_closed(self):
        for ordering in (Ordering(), Ordering(delay=0.3), Ordering(exit_first=True)):
            with self.subTest(delay=ordering.delay, exit_first=ordering.exit_first), harness("pass\n"), ordering as o:
                got = self.record()
            self.assertIs(got.result.status, ProbeExecutionStatus.UNRUNNABLE)
            self.assertEqual(got.result.detail, "the harness did not start (exit 0, no READY): tool absent or broken")
            self.assertEqual(o.failures_after_close, [True])   # concluded only once the stream had closed

    def test_RACE_6_a_target_that_dies_before_READY_keeps_its_typed_outcome(self):
        with harness("import sys\nsys.exit(3)\n"), Ordering(delay=0.2) as o:
            got = self.record()
        self.assertEqual(got.result.detail, "the harness did not start (exit 3, no READY): tool absent or broken")
        self.assertEqual(o.failures_after_close, [True])
        if os.name == "posix":
            with harness("import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"), Ordering(exit_first=True) as o:
                got = self.record()
            self.assertEqual(got.result.detail, "the harness process was killed by signal 9 before READY")
            self.assertEqual((o.exit_known_first, o.failures_after_close), ([True], [True]))

    def test_RACE_7_a_partial_READY_then_exit_is_no_READY_never_a_guess(self):
        for ordering in (Ordering(), Ordering(delay=0.3), Ordering(exit_first=True)):
            with self.subTest(delay=ordering.delay, exit_first=ordering.exit_first), harness(PARTIAL_READY), ordering:
                got = self.record()
            self.assertIs(got.result.status, ProbeExecutionStatus.UNRUNNABLE)
            self.assertEqual(got.result.detail, "the harness did not start (exit 0, no READY): tool absent or broken")

    def test_RACE_9_every_line_before_the_end_is_read_before_STREAM_CLOSED(self):
        with harness(NOISY_HARNESS), Ordering(exit_first=True, delay=0.2) as o:
            got = self.record()
        self.assertEqual(got.result, Executed(S))           # the protocol lines behind 400 lines of noise
        self.assertEqual(o.failures_after_close, [])


class AnchorHoldsNoWriter(unittest.TestCase):
    def test_RACE_8_the_output_stream_ends_when_the_target_ends_while_the_anchor_lives(self):
        r = ProcessRange("race-8", [sys.executable, "-c", "print('last line')"], output=subprocess.PIPE).start()
        try:
            got, done = [], threading.Event()

            def read():
                for line in r.output:
                    got.append(line)
                done.set()
            threading.Thread(target=read, daemon=True).start()
            self.assertTrue(done.wait(30), "no end of file while the anchor lives: it holds a copy of the writer")
            self.assertIsNone(r._anchor.poll())             # the anchor is alive and unreaped: the EOF is not its exit
            self.assertEqual(got, ["last line\n"])
            self.assertEqual(r.wait(10), 0)
            if pathlib.Path(f"/proc/{r._anchor.pid}/fd/2").exists():   # Linux: the anchor's fd 2 is the null device
                self.assertEqual(os.readlink(f"/proc/{r._anchor.pid}/fd/2"), os.devnull)
        finally:
            r.release()

    def test_a_descendant_holding_the_writer_keeps_the_stream_open_until_it_ends(self):
        """The end of file is the writers' truth, not the target's exit: a child that inherited the stream keeps it
        open after the target is gone, and the stream ends when that child does."""
        child = "import time; time.sleep(1.0); print('child done', flush=True)"
        r = ProcessRange("race-8b", [sys.executable, "-c",
                                     f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', {child!r}]); "
                                     "print('target done', flush=True)"], output=subprocess.PIPE).start()
        try:
            got, done = [], threading.Event()

            def read():
                for line in r.output:
                    got.append(line)
                done.set()
            threading.Thread(target=read, daemon=True).start()
            self.assertEqual(r.wait(20), 0)                  # the target has exited ...
            self.assertTrue(done.wait(20))
            self.assertEqual(got, ["target done\n", "child done\n"])   # ... and the stream ended with its last writer
        finally:
            r.release()


class NextAndPump(unittest.TestCase):
    """The reader's two parts, pinned: the pump publishes every line then STREAM_CLOSED; `_next` returns protocol
    lines only — complete, marked, this run's nonce — then STREAM_CLOSED for good."""

    def pumped(self, items):
        q = queue.Queue()
        pc._pump(iter(items), q)
        out = []
        while not q.empty():
            out.append(q.get())
        return out

    def test_the_pump_publishes_every_line_in_order_then_STREAM_CLOSED_once(self):
        lines = [f"line {i}\n" for i in range(1000)] + ["partial"]
        self.assertEqual(self.pumped(lines), [("LINE", x) for x in lines] + [("STREAM_CLOSED", "")])
        self.assertEqual(self.pumped([]), [("STREAM_CLOSED", "")])

        class Stream:
            closed = False

            def __iter__(self):
                yield "a\n"
                raise OSError("read failed")

            def close(self):
                self.closed = True
        s, q = Stream(), queue.Queue()
        with self.assertRaises(OSError):
            pc._pump(s, q)
        self.assertEqual([q.get(), q.get()], [("LINE", "a\n"), ("STREAM_CLOSED", "")])
        self.assertTrue(s.closed)

    def test_next_returns_only_complete_marked_lines_of_this_nonce(self):
        q = queue.Queue()
        for kind, line in (("LINE", "noise\n"), ("LINE", "AISEF2-PROBE READY other \n"), ("LINE", "OTHER READY n0nce \n"),
                           ("LINE", "AISEF2-PROBE\n"), ("LINE", "AISEF2-PROBE READY n0nce \r\n"),
                           ("LINE", 'AISEF2-PROBE RESULT n0nce {"a": 1} x\n'), ("LINE", "AISEF2-PROBE DISPATCHED n0nce"),
                           ("STREAM_CLOSED", "")):
            q.put((kind, line))
        far = time.monotonic() + 30
        self.assertEqual(pc._next(q, "n0nce", far), ("READY", ""))
        self.assertEqual(pc._next(q, "n0nce", far), ("RESULT", '{"a": 1} x'))
        self.assertEqual(pc._next(q, "n0nce", far), ("STREAM_CLOSED", ""))   # the unterminated DISPATCHED is no line
        self.assertEqual(pc._next(q, "n0nce", far), ("STREAM_CLOSED", ""))   # and a closed stream stays closed
        three = queue.Queue()
        three.put(("LINE", "AISEF2-PROBE READY n0nce\n"))
        self.assertEqual(pc._next(three, "n0nce", far), ("READY", ""))

    def test_next_times_out_at_its_deadline_and_never_waits_past_it(self):
        q = queue.Queue()
        t0 = time.monotonic()
        self.assertEqual(pc._next(q, "n0nce", t0 + 0.2), ("TIMEOUT", ""))
        self.assertLess(time.monotonic() - t0, 5)
        q.put(("LINE", "AISEF2-PROBE READY n0nce \n"))
        self.assertEqual(pc._next(q, "n0nce", time.monotonic() - 1), ("TIMEOUT", ""))   # a passed deadline reads nothing

    def test_a_protocol_tag_out_of_order_is_the_harness_breaking_its_protocol(self):
        class Still:
            def wait(self, timeout=None):
                raise AssertionError("an out-of-order tag needs no exit status")
        got = pc._harness_failure(Still(), "RESULT", "READY", 20, time.monotonic() + 20)
        self.assertEqual(got.detail, "the harness broke its protocol: RESULT before READY")

    def test_a_stream_closed_while_the_process_runs_is_a_harness_timeout_at_the_watchdog(self):
        class Running:
            def wait(self, timeout=None):
                time.sleep(min(timeout or 0, 0.3))
                return None
        until = time.monotonic() + 0.2
        got = pc._harness_failure(Running(), "STREAM_CLOSED", "READY", 7, until)
        self.assertEqual(got.detail, "harness timeout: no READY within 7s — the observation mechanism did not operate")

        class Gone:  # the report channel closed before the watchdog: the status was never reported
            def wait(self, timeout=None):
                return None
        got = pc._harness_failure(Gone(), "STREAM_CLOSED", "DISPATCHED", 7, time.monotonic() + 30)
        self.assertEqual(got.detail, "the harness did not start (exit None, no DISPATCHED): tool absent or broken")

    def test_after_DISPATCHED_a_closed_stream_with_the_process_running_is_the_window_expiring(self):
        dispatched = ["AISEF2-PROBE READY n0nce \n", "AISEF2-PROBE DISPATCHED n0nce \n"]

        class Closed:
            ledger = []

            def __init__(self, code):
                self.output, self.code = iter(dispatched), code

            def start(self):
                return self

            def wait(self, timeout=None):
                if self.code is None:
                    time.sleep(min(timeout or 0, 1.0))
                return self.code

            def release(self):
                pass
        blocks = spec("app.calc:hang", {"blocks": True}, window=0.3)
        for code, want in ((None, (ProbeExecutionStatus.EXECUTED, "SATISFIED")), (0, (ProbeExecutionStatus.EXECUTED, "REFUTED"))):
            with self.subTest(code=code), mock.patch.multiple(pc, ProcessRange=mock.Mock(return_value=Closed(code)),
                                                              secrets=mock.Mock(token_hex=mock.Mock(return_value="n0nce"))):
                got = run_probe(P, blocks, RevisionRef(SHA, checkout(PRODUCT)), env()).result
            self.assertEqual((got.status, got.behavior_verdict.value), want)


if __name__ == "__main__":
    unittest.main()
