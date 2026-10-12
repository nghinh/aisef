"""B-03 round 3, WP range — `ProcessRange.release` called by more than one thread (docs/v2.1/decisions/B03-R3-range.md).

The contract this file tests, from the real call paths (the decision doc's table):

1. MUTUAL EXCLUSION — at most one thread runs the ladder, the EXIT write, the reap and the pipe close of one range.
2. IDEMPOTENCE — a call after a release has ended does nothing observable (no signal, no ledger growth, no second
   write or close) and returns as it always did: None once the anchor is reaped, a new ladder after RangeNotEmpty. A
   caller that WAITED for a release is given its outcome (RangeNotEmpty / RangeEscaped): a leak is never silent.
3. OWNERSHIP — no signal is sent after the anchor is reaped, and a caller that waited never signals a range another
   thread has emptied.
4. NO DEADLOCK — a call from the thread that is already releasing (a signal handler) neither hangs nor corrupts the
   frame below; a waiter waits exactly as long as the release it waits for; a failed start() leaves nothing to wait on.

Every test below is a controlled thread choreography over a fake anchor, backend and pipes (no process, no sleep of
the test's own): a thread is PARKED inside the operation the race needs, the second caller is brought to the point
where it is either waiting for the first (a waiter polls: it is seen in the `time.sleep` the module calls) or — in an
implementation that does not make it wait — already running, and only then is the first one let go. Two exceptions: `RealRange` runs a real target under a real anchor (an integration check, not the
proof), and `AbandonedWorker` lets StoryScope's own 0.05 s bound run out on a release that is parked, so it cannot
end any other way. The bound on every wait (`BOUND_S`) only ends a test that would otherwise hang.
"""

import io
import os
import pathlib
import sys
import threading
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.runtime import process_range as pr  # noqa: E402
from aisef2.runtime.process_range import Proc, ProcessRange, RangeError, RangeEscaped, RangeNotEmpty  # noqa: E402
from aisef2.runtime.story_scope import StoryScope  # noqa: E402
from tests.v2.p4.world import Journal2, emitter, released  # noqa: E402

BOUND_S = 10.0           # a gate's upper bound: reached only by a test that would otherwise hang
HELD_FALLBACK_S = 5.0    # how long an implementation that blocks the second caller some other way is given to do so
PY = sys.executable
POSIX = os.name == "posix"


# --------------------------------------------------------------------------------------- the choreography

class Park:
    """Parks the first thread that reaches it until the test lets it go."""

    def __init__(self, rig: "Rig") -> None:
        self.rig, self.taken = rig, False
        self.arrived, self.go = threading.Event(), threading.Event()

    def __call__(self) -> None:
        with self.rig._mx:
            first, self.taken = not self.taken, True
        if not first:
            return
        self.arrived.set()
        if not self.go.wait(BOUND_S):
            raise AssertionError("a parked thread was never let go")


class _Time:
    """`time` as `process_range` sees it. A caller that waits for a release in flight polls with `time.sleep`; that
    call says "a caller is held behind the release", and may run a hook (a signal handler arriving while it waits)."""

    monotonic = staticmethod(time.monotonic)

    def __init__(self, rig: "Rig") -> None:
        self._rig = rig

    def sleep(self, seconds: float) -> None:
        rig = self._rig
        rig.waits += 1
        rig.waiting.set()
        rig.second.set()
        hook, rig.during_wait = rig.during_wait, None
        if hook is not None:
            hook()
        time.sleep(seconds)


class Caller(threading.Thread):
    """`release()` on a thread of its own; what it returned or raised is kept."""

    def __init__(self, rng: ProcessRange, name: str, before=None) -> None:
        super().__init__(name=name, daemon=True)
        self.rng, self.error, self.before = rng, None, before

    def run(self) -> None:
        try:
            if self.before is not None:
                self.before()
            self.rng.release()
        except BaseException as e:  # noqa: BLE001 - what escapes release() is the thing under test
            self.error = e

    def finish(self, test: unittest.TestCase) -> None:
        self.join(BOUND_S)
        test.assertFalse(self.is_alive(), f"{self.name} never returned from release()")


class _Pipe:
    def __init__(self, rig: "Rig", name: str) -> None:
        self.rig, self.name, self.closed = rig, name, False

    def write(self, text: str) -> None:
        with self.rig.op(f"{self.name}.write"):
            self.rig.writes.append(text)
            self.rig.anchor.exiting = True      # EXIT is what makes the anchor end

    def flush(self) -> None:
        with self.rig.op(f"{self.name}.flush"):
            pass

    def close(self) -> None:
        with self.rig.op(f"{self.name}.close"):
            self.closed = True


class _Anchor:
    pid = 4242

    def __init__(self, rig: "Rig") -> None:
        self.rig, self.returncode, self.exiting, self.reaped = rig, None, False, False
        self.stdin, self.stdout = _Pipe(rig, "stdin"), _Pipe(rig, "stdout")

    def poll(self):
        with self.rig.op("anchor.poll"):
            if self.exiting and not self.reaped:
                self.returncode, self.reaped = 0, True      # poll() reaps what has exited
            return self.returncode

    def wait(self):
        with self.rig.op("anchor.wait"):
            self.returncode, self.reaped = 0, True
            return 0


class _Backend:
    stages = (("cooperative", "SIGINT", 0), ("terminate", "SIGTERM", 1), ("kill", "SIGKILL", None))

    def __init__(self, rig: "Rig") -> None:
        self.rig = rig

    def members(self, anchor: int) -> list:
        with self.rig.op("members"):
            return list(self.rig.alive)

    def escaped(self, anchor: int) -> list:
        with self.rig.op("escaped"):
            return list(self.rig.escapees)

    def signal(self, sig) -> None:
        if self.rig.empties_before_signal:
            self.rig.alive = []                             # the members left by themselves, meanwhile
        with self.rig.op("signal"):
            self.rig.sent.append((sig, self.rig.anchor.reaped))   # read when it is SENT: after any parking
            if sig == self.rig.dies_on:
                self.rig.alive = []
            if sig == "SIGKILL":
                self.rig.anchor.exiting = True

    def close(self) -> None:
        with self.rig.op("backend.close"):
            pass


class Rig:
    """A ProcessRange with no process: the anchor, the backend and the pipes are fakes that journal every operation with
    the thread that did it, so a test can say what ran, how often, and whether two threads were inside at once."""

    def __init__(self, test: unittest.TestCase, members: int = 1, dies_on: str | None = "SIGINT",
                 escapees: tuple = (), empties_before_signal: bool = False) -> None:
        self._mx = threading.Lock()
        self.ops: list[tuple[str, str]] = []        # (thread name, operation), in the order they started
        self.depth: dict[int, int] = {}             # thread ident -> operations it is inside now
        self.max_threads = 0                        # the most threads inside operations at once
        self.hooks: dict[str, object] = {}
        self.second, self.waiting, self.overlap = threading.Event(), threading.Event(), threading.Event()
        self.waits, self.during_wait = 0, None
        self.alive = [Proc(100 + i, 1, None, None, f"member-{i}") for i in range(members)]
        self.dies_on, self.empties_before_signal = dies_on, empties_before_signal
        self.escapees = [Proc(pid, 1, None, None, command) for pid, command in escapees]
        self.sent: list[tuple[str, bool]] = []      # (signal, was the anchor already reaped when it was sent)
        self.writes: list[str] = []
        self.range = ProcessRange("r", ["unused"], grace_s=(0.0, 0.0), wait_s=0.0)
        self.anchor = _Anchor(self)
        self.range._anchor, self.range._os = self.anchor, _Backend(self)
        self.range._pumper = types.SimpleNamespace(join=lambda timeout=None: None)
        self.range.returncode = 0                   # the target's exit status was reported
        patch = mock.patch.object(pr, "time", _Time(self))
        patch.start()
        test.addCleanup(patch.stop)

    def op(self, name: str):
        return _Op(self, name)

    def park_at(self, operation: str) -> Park:
        park = self.hooks[operation] = Park(self)
        return park

    def count(self, operation: str) -> int:
        return sum(1 for _, o in self.ops if o == operation)

    def second_is_held(self) -> str:
        """Returns once the second caller is out of the way of the parked first one: polling for the release's end
        ("waiting"), or — an implementation that does not make it wait — already running inside ("inside"); an
        implementation that blocks it some other way is given `HELD_FALLBACK_S` ("elsewhere")."""
        if not self.second.wait(HELD_FALLBACK_S):
            return "elsewhere"
        return "waiting" if self.waiting.is_set() else "inside"


class _Op:
    def __init__(self, rig: Rig, name: str) -> None:
        self.rig, self.name = rig, name

    def __enter__(self):
        rig, me = self.rig, threading.get_ident()
        with rig._mx:
            rig.ops.append((threading.current_thread().name, self.name))
            rig.depth[me] = rig.depth.get(me, 0) + 1
            threads = sum(1 for d in rig.depth.values() if d)
            rig.max_threads = max(rig.max_threads, threads)
            if threads > 1:
                rig.overlap.set()
                rig.second.set()
        hook = rig.hooks.get(self.name)
        if hook is not None:
            hook()
        return self

    def __exit__(self, *exc):
        with self.rig._mx:
            self.rig.depth[threading.get_ident()] -= 1
        return False


def two_callers(test: unittest.TestCase, rig: Rig, park: Park) -> tuple[Caller, Caller]:
    """A releases and parks at `park`; B calls release() while A is parked there; both are brought to the point the
    race needs and nothing else. Returns (A, B) with A still parked."""
    a = Caller(rig.range, "A")
    a.start()
    test.assertTrue(park.arrived.wait(BOUND_S), "the first releaser never reached the parking point")
    b = Caller(rig.range, "B")
    b.start()
    rig.second_is_held()
    return a, b


# --------------------------------------------------------------------------------------- 1. mutual exclusion

class MutualExclusion(unittest.TestCase):
    def test_two_threads_releasing_one_range_run_one_ladder_one_exit_write_and_one_close(self):
        rig = Rig(self, dies_on="SIGINT")
        park = rig.park_at("signal")        # A is inside its first signal, past the reaped guard
        a, b = two_callers(self, rig, park)
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual((a.error, b.error), (None, None))
        self.assertEqual(rig.max_threads, 1)                             # never two threads inside at once
        self.assertEqual([s for s, _ in rig.sent], ["SIGINT"])           # one ladder: one signal ...
        self.assertEqual([s["stage"] for s in rig.range.ledger], ["cooperative"])   # ... one ledger row
        self.assertEqual(rig.writes, ["EXIT\n"])                          # one EXIT write
        self.assertEqual((rig.count("stdin.close"), rig.count("stdout.close")), (1, 1))   # one close of each pipe
        self.assertEqual(rig.count("anchor.wait"), 1)                     # one reap
        self.assertEqual(rig.count("backend.close"), 1)
        self.assertTrue(rig.range._reaped)

    def test_the_second_caller_is_not_released_before_the_first_has_finished(self):
        """B waits behind A while A is stuck (the last stage of a ladder with no bound waits as long as it must): B is
        still waiting when A has not finished, and both return once A does — a wait on A, not a lock held across A."""
        rig = Rig(self, dies_on="SIGINT")
        park = rig.park_at("members")
        a, b = two_callers(self, rig, park)
        self.assertTrue(a.is_alive() and b.is_alive())     # B did not run a release of its own meanwhile
        self.assertEqual(rig.max_threads, 1)
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual((a.error, b.error, rig.max_threads), (None, None, 1))
        self.assertEqual([s for s, _ in rig.sent], ["SIGINT"])

    def test_the_real_pipe_close_of_a_second_releaser_never_meets_the_first(self):
        """The 2026-10-12 failure itself: both threads close the anchor's stdin, bytes pending after an EPIPE flush, and
        the loser flushes from a freed buffer — ValueError('PyMemoryView_FromBuffer(): info->buf must not be NULL').
        Real io objects (TextIOWrapper over BufferedWriter, as Popen builds them) over a raw that is EPIPE on write and
        holds the second closer inside `close()` until the first has read its way past the closed checks."""
        raw = _StdinRaw()
        stdin = io.TextIOWrapper(io.BufferedWriter(raw), encoding="utf-8", write_through=True)
        stdin.write("EXIT\n")                   # pending in the buffer: the reader was gone
        try:
            stdin.flush()
        except OSError:
            pass                                # EPIPE: the range ignores it too; the bytes stay
        rig = Rig(self, members=0)
        rig.anchor.stdin, rig.anchor.reaped, rig.anchor.returncode = stdin, True, 0   # the anchor has exited
        park = rig.park_at("escaped")           # A is past the reaped guard, before any close
        a = Caller(rig.range, "A", before=lambda: setattr(raw, "x_ident", threading.get_ident()))
        a.start()
        self.assertTrue(park.arrived.wait(BOUND_S))
        b = Caller(rig.range, "B")
        b.start()
        if rig.second_is_held() == "inside":
            # nothing holds B: it runs on to the pipe close and is held inside it, as the original race needs
            self.assertTrue(raw.in_close.wait(BOUND_S))
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual((repr(a.error), repr(b.error)), ("None", "None"))
        self.assertTrue(stdin.closed and rig.range._reaped)


class WaitingCaller(unittest.TestCase):
    def test_a_call_that_arrives_on_a_waiting_thread_waits_too_and_hangs_nothing(self):
        """A handler runs on the thread that is waiting for A's release and calls release() itself: it is a waiter like
        any other (A is the releasing thread, not this one), and both waits end with A's release."""
        rig = Rig(self, dies_on="SIGINT")
        park = rig.park_at("signal")
        nested = []

        def handler():
            try:
                nested.append(rig.range.release())
            except BaseException as e:  # noqa: BLE001
                nested.append(e)
        rig.during_wait = handler
        a, b = two_callers(self, rig, park)
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual((a.error, b.error, nested, rig.max_threads), (None, None, [None], 1))
        self.assertEqual(([s for s, _ in rig.sent], rig.writes, rig.count("stdin.close")), (["SIGINT"], ["EXIT\n"], 1))


class _StdinRaw(io.RawIOBase):
    """The anchor's stdin pipe with its reader gone. close() of the second closer is held until X (the thread named in
    `x_ident`) has read `closed` three times (TextIOWrapper.close, TextIOWrapper.flush, BufferedWriter.flush)."""

    def __init__(self) -> None:
        super().__init__()
        self.in_close, self.x_checked = threading.Event(), threading.Event()
        self.x_ident, self.x_reads, self._seen = None, 3, 0

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    @property
    def closed(self) -> bool:
        value = io.RawIOBase.closed.__get__(self)
        if threading.get_ident() == self.x_ident:
            self._seen += 1
            if self._seen == self.x_reads:
                self.x_checked.set()
        return value

    def close(self) -> None:
        if not io.RawIOBase.closed.__get__(self):
            self.in_close.set()
            if threading.get_ident() != self.x_ident:    # the other closer waits for X; X never waits for itself
                self.x_checked.wait(BOUND_S)
        super().close()


# --------------------------------------------------------------------------------------- 2. idempotence

class Idempotence(unittest.TestCase):
    def test_a_call_after_the_release_ended_does_nothing_observable_and_returns(self):
        rig = Rig(self, dies_on="SIGINT")
        rig.range.release()
        ops, ledger, sent = list(rig.ops), list(rig.range.ledger), list(rig.sent)
        for _ in range(2):
            self.assertIsNone(rig.range.release())
        self.assertEqual((rig.ops, rig.range.ledger, rig.sent), (ops, ledger, sent))   # nothing at all was touched
        self.assertEqual((rig.writes, rig.count("stdin.close"), rig.count("anchor.wait")), (["EXIT\n"], 1, 1))

    def test_a_range_never_started_releases_to_nothing(self):
        self.assertIsNone(ProcessRange("never", [PY]).release())

    def test_a_range_that_exited_by_itself_is_released_without_a_signal(self):
        rig = Rig(self, members=0)
        rig.range.release()
        self.assertEqual((rig.sent, rig.range.ledger, rig.writes), ([], [], ["EXIT\n"]))

    def test_an_empty_range_whose_target_never_reported_its_exit_is_still_stopped(self):
        """Nothing is alive in the range, but the target's exit was never reported: the controller does not know how it
        ended, so it runs the ladder (`and`, not `or`: emptiness AND a reported exit)."""
        rig = Rig(self, members=0, dies_on="SIGINT")
        rig.range.returncode = None
        real = rig.range._os.signal

        def signal(sig):
            real(sig)
            rig.range._lines.put(("EXITED", "0"))      # the target reports how it ended once it is told to stop
        rig.range._os.signal = signal
        rig.range.release()
        self.assertEqual([s for s, _ in rig.sent], ["SIGINT"])
        self.assertEqual(rig.range.returncode, 0)

    def test_the_message_of_a_range_that_will_not_empty_names_the_stages_and_the_members(self):
        rig = Rig(self, dies_on=None)
        with self.assertRaises(RangeNotEmpty) as e:
            rig.range.release()
        self.assertEqual(str(e.exception), "r: not empty after ['cooperative', 'terminate', 'kill']: "
                                           "[(100, 'member-0')]")
        self.assertEqual(rig.writes, [])        # a range that is not empty is never told to exit
        self.assertEqual(rig.count("stdin.close"), 0)
        self.assertFalse(rig.range._reaped)

    def test_RangeNotEmpty_then_a_later_call_runs_the_ladder_again_as_it_always_did(self):
        rig = Rig(self, dies_on=None)
        for _ in range(2):
            with self.assertRaises(RangeNotEmpty):
                rig.range.release()
        self.assertEqual([s["stage"] for s in rig.range.ledger], ["cooperative", "terminate", "kill"] * 2)
        rig.alive = []                               # it empties at last
        rig.range.release()
        self.assertEqual(len(rig.range.ledger), 6)   # nothing sent: it was measured empty first
        self.assertTrue(rig.range._reaped)
        # SIGKILL took the anchor with its group: no EXIT to write; the pipes are closed once, the anchor reaped once
        self.assertEqual((rig.writes, rig.count("stdin.close"), rig.count("anchor.wait")), ([], 1, 1))

    def test_RangeEscaped_is_raised_to_the_caller_and_a_later_call_returns_as_it_always_did(self):
        rig = Rig(self, members=0, escapees=((9002, "later"), (9001, "leaver")))
        alive = {9001: Proc(9001, 1, None, None, "leaver"), 9002: Proc(9002, 1, None, None, "later")}
        with mock.patch.object(pr, "process_table", return_value=alive):
            with self.assertRaises(RangeEscaped) as e:
                rig.range.release()
            self.assertEqual(str(e.exception), "r: processes left the range and are alive: "
                                               "[(9001, 'leaver'), (9002, 'later')]")   # in pid order
            ops = list(rig.ops)
            self.assertIsNone(rig.range.release())    # the anchor is reaped: a no-op, exactly as before
            self.assertEqual(rig.ops, ops)
        self.assertTrue(rig.range._reaped)

    def test_a_range_with_no_escapee_does_not_read_the_process_table(self):
        rig = Rig(self, members=0)
        with mock.patch.object(pr, "process_table", side_effect=AssertionError("read the table")):
            rig.range.release()


# --------------------------------------------------------------------------------------- the outcome of a waited-for release

class SharedOutcome(unittest.TestCase):
    def test_a_caller_that_waited_is_given_RangeEscaped_a_leak_is_never_silent_for_it(self):
        rig = Rig(self, dies_on="SIGINT", escapees=((9001, "leaver"),))
        alive = {9001: Proc(9001, 1, None, None, "leaver")}
        park = rig.park_at("signal")
        with mock.patch.object(pr, "process_table", return_value=alive):
            a, b = two_callers(self, rig, park)
            park.go.set()
            a.finish(self)
            b.finish(self)
        expected = "r: processes left the range and are alive: [(9001, 'leaver')]"
        self.assertEqual((type(a.error), str(a.error)), (RangeEscaped, expected))
        self.assertEqual((type(b.error), str(b.error)), (RangeEscaped, expected))
        self.assertIsNot(b.error, a.error)                 # its own exception ...
        self.assertIs(b.error.__cause__, a.error)          # ... caused by the release it waited for
        self.assertEqual(([s for s, _ in rig.sent], rig.writes, rig.count("stdin.close")), (["SIGINT"], ["EXIT\n"], 1))
        with mock.patch.object(pr, "process_table", return_value=alive):
            self.assertIsNone(rig.range.release())          # a call after it ended: as it always was

    def test_a_caller_that_waited_is_given_RangeNotEmpty_and_no_second_ladder_runs(self):
        rig = Rig(self, dies_on=None)
        park = rig.park_at("signal")
        a, b = two_callers(self, rig, park)
        park.go.set()
        a.finish(self)
        b.finish(self)
        expected = "r: not empty after ['cooperative', 'terminate', 'kill']: [(100, 'member-0')]"
        self.assertEqual((type(a.error), str(a.error)), (RangeNotEmpty, expected))
        self.assertEqual((type(b.error), str(b.error)), (RangeNotEmpty, expected))
        self.assertIs(b.error.__cause__, a.error)
        self.assertEqual([s for s, _ in rig.sent], ["SIGINT", "SIGTERM", "SIGKILL"])    # one ladder, not two
        self.assertFalse(rig.range._reaped)
        rig.alive = []
        self.assertIsNone(rig.range.release())              # a later, separate call is a new attempt: it empties
        self.assertTrue(rig.range._reaped)

    def test_a_failure_that_is_not_an_outcome_is_not_handed_to_the_waiter_who_leads_instead(self):
        """A release that dies of something else (here a signal that fails) is no outcome of the range: the caller that
        waited for it runs the release itself, as a later call would."""
        rig = Rig(self, dies_on="SIGINT")
        park = rig.park_at("signal")
        real = rig.range._os.signal
        calls = []

        def signal(sig):
            calls.append(sig)
            if len(calls) == 1:
                real(sig)
                raise RangeError("TerminateJobObject failed")
            real(sig)
        rig.range._os.signal = signal
        a, b = two_callers(self, rig, park)
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual((type(a.error), b.error), (RangeError, None))
        self.assertTrue(rig.range._reaped)
        self.assertEqual(rig.writes, ["EXIT\n"])


# --------------------------------------------------------------------------------------- 3. ownership

class Ownership(unittest.TestCase):
    def test_no_signal_is_sent_after_the_anchor_was_reaped(self):
        """A is past the reaped guard, inside the signal; the members have left by themselves; B measures the range empty
        and reaps the anchor. A's signal is then sent to a group the anchor no longer pins — unless B waits for A."""
        rig = Rig(self, empties_before_signal=True)
        park = rig.park_at("signal")
        a, b = two_callers(self, rig, park)
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual((a.error, b.error), (None, None))
        self.assertEqual([(s, reaped) for s, reaped in rig.sent], [("SIGINT", False)])    # sent while unreaped
        self.assertEqual(rig.count("anchor.wait"), 1)

    def test_a_caller_that_waited_never_signals_a_range_the_other_thread_emptied(self):
        rig = Rig(self, dies_on="SIGINT")
        park = rig.park_at("signal")
        a, b = two_callers(self, rig, park)
        park.go.set()
        a.finish(self)
        b.finish(self)
        self.assertEqual(rig.sent, [("SIGINT", False)])     # B added none: the range was measured empty by A
        self.assertEqual(len(rig.range.ledger), 1)
        self.assertEqual([t for t, o in rig.ops if o == "signal"], ["A"])

    def test_the_signal_guard_refuses_after_the_reap(self):
        rig = Rig(self, members=0)
        rig.range.release()
        with self.assertRaisesRegex(RangeError, "the anchor is reaped; the range is never signalled again"):
            rig.range._signal("kill", "SIGKILL")
        self.assertEqual(rig.sent, [])


# --------------------------------------------------------------------------------------- 4. no deadlock

class Reentry(unittest.TestCase):
    """A signal handler runs on the thread that is inside release(), between two of its bytecodes; the tests call
    release() from inside an operation of the frame below, which is the same thing from the range's side."""

    def run_below(self, rig: Rig) -> Caller:
        below = Caller(rig.range, "below")
        below.start()
        below.finish(self)      # a re-entry that waits for itself fails here, not by hanging the suite
        return below

    def test_a_call_inside_the_ladder_stops_the_range_and_the_frame_below_disposes(self):
        rig = Rig(self, dies_on="SIGINT")
        seen = {}

        def handler():
            rig.hooks.pop("members")                # the handler arrives once
            try:
                rig.range.release()
            except BaseException as e:  # noqa: BLE001
                seen["error"] = e
            seen["members"] = list(rig.alive)       # on return the range is empty: that was the handler's wish
        rig.hooks["members"] = handler
        below = self.run_below(rig)
        self.assertEqual((below.error, seen.get("error"), seen["members"]), (None, None, []))
        self.assertEqual([s for s, _ in rig.sent], ["SIGINT"])
        self.assertEqual(rig.writes, ["EXIT\n"])
        self.assertEqual((rig.count("stdin.close"), rig.count("anchor.wait"), rig.count("backend.close")), (1, 1, 1))
        self.assertTrue(rig.range._reaped)

    def test_a_call_past_the_ladder_returns_at_once_and_leaves_the_disposal_to_the_frame_below(self):
        rig = Rig(self, members=0)
        seen = {}

        def handler():
            rig.hooks.pop("anchor.poll")
            start = len(rig.ops)
            try:
                seen["result"] = rig.range.release()
            except BaseException as e:  # noqa: BLE001
                seen["error"] = e
            seen["ops"] = rig.ops[start:]           # what the re-entry did to the anchor, the pipes, the backend
        rig.hooks["anchor.poll"] = handler
        below = self.run_below(rig)
        self.assertEqual((below.error, seen.get("error"), seen["result"], seen["ops"]), (None, None, None, []))
        self.assertEqual((rig.writes, rig.count("stdin.close"), rig.count("anchor.wait"), rig.sent), (["EXIT\n"], 1, 1, []))
        self.assertTrue(rig.range._reaped)

    def test_a_call_inside_the_ladder_that_cannot_empty_the_range_raises_to_its_caller_only(self):
        rig = Rig(self, dies_on=None)
        seen = {}

        def handler():
            rig.hooks.pop("members")
            try:
                rig.range.release()
            except RangeNotEmpty as e:
                seen["error"] = e
        rig.hooks["members"] = handler
        below = self.run_below(rig)
        self.assertIsInstance(seen["error"], RangeNotEmpty)         # the handler is told ...
        self.assertIsInstance(below.error, RangeNotEmpty)           # ... and the frame below ends as it would have
        self.assertIsNot(seen["error"], below.error)
        self.assertEqual(len(rig.sent), 6)                          # both ladders are in the ledger: it is the truth
        self.assertFalse(rig.range._reaped)
        rig.alive = []
        self.assertIsNone(rig.range.release())                      # nothing is left half done: the next call completes
        self.assertTrue(rig.range._reaped)

    def test_a_call_that_arrives_while_a_release_is_being_claimed_hangs_nothing(self):
        """The handler lands inside the few bytecodes in which the first call holds the range's own lock to claim the
        release: the lock is the range's, so the re-entering call must be able to take it again (an `RLock`)."""
        rig = Rig(self, dies_on="SIGINT")
        inner, nested = getattr(rig.range, "_mx", None), []
        if inner is None:
            self.skipTest("this range has no lock of its own to claim a release under: nothing for a handler to re-enter")

        class Hooked:
            def __init__(self):
                self.hook = lambda: nested.append(rig.range.release())

            def __enter__(self):
                inner.acquire()                     # the range's own lock, held ...
                hook, self.hook = self.hook, None
                if hook is not None:
                    hook()                          # ... when the handler arrives
                return self

            def __exit__(self, *exc):
                inner.release()
                return False
        rig.range._mx = Hooked()
        below = self.run_below(rig)
        self.assertEqual((below.error, nested), (None, [None]))
        self.assertEqual(([s for s, _ in rig.sent], rig.writes, rig.count("stdin.close"), rig.count("anchor.wait")),
                         (["SIGINT"], ["EXIT\n"], 1, 1))
        self.assertTrue(rig.range._reaped)

    @unittest.skipUnless(POSIX, "a failed adopt on Windows is not exercised here: _Job.abort does not signal an anchor "
                                "that was never in the job (docs/v2.1/decisions/B03-R3-range.md, not established)")
    def test_a_failed_start_leaves_a_range_whose_release_returns_at_once(self):
        class FailsToAdopt(pr._Posix):
            def adopt(self, pid):
                raise RangeError("adopt failed")
        r = ProcessRange("r", [PY, "-c", "pass"])
        with mock.patch.object(pr, "BACKEND", FailsToAdopt):
            with self.assertRaisesRegex(RangeError, "adopt failed"):
                r.start()
        self.assertTrue(r._reaped)
        caller = Caller(r, "after-failed-start")
        caller.start()
        caller.finish(self)
        self.assertIsNone(caller.error)
        self.assertIsNotNone(r.anchor_returncode)


class AbandonedWorker(Journal2, unittest.TestCase):
    def test_a_release_the_scope_abandoned_at_its_bound_is_not_the_end_of_a_later_caller(self):
        """StoryScope runs a release on a worker thread and, at its bound, names the resource RESIDUAL and goes on; the
        worker is abandoned, not joined, and is still inside release(). A later caller waits for it and returns when
        it ends — it neither hangs for good nor runs a second ladder under the abandoned one."""
        w = self.writer()
        self.story(w)
        scope = StoryScope("S1", emitter(w), release_timeout_s=0.05)
        rig = Rig(self, dies_on="SIGINT")
        park = rig.park_at("members")
        self.addCleanup(park.go.set)
        scope.acquire(rig.range)
        report = scope.dispose()
        self.assertTrue(park.arrived.wait(BOUND_S))
        self.assertEqual(released(w), [("r", "RESIDUAL")])
        self.assertEqual(report.records[0].detail, "not released: the release was still running after 0.05s")
        late = Caller(rig.range, "late")
        late.start()
        rig.second_is_held()
        self.assertTrue(late.is_alive())                   # it waits for the abandoned worker ...
        park.go.set()
        late.finish(self)                                  # ... and is free when that ends
        self.assertIsNone(late.error)
        self.assertEqual((rig.max_threads, [s for s, _ in rig.sent], rig.writes), (1, ["SIGINT"], ["EXIT\n"]))
        for t in threading.enumerate():
            if t.name == "release r":
                t.join(BOUND_S)
                self.assertFalse(t.is_alive())


# --------------------------------------------------------------------------------------- a real range

class RealRange(unittest.TestCase):
    """The by-design concurrent caller of the suite in miniature, on a real target, anchor and pipes: a controller's
    stop thread and the owner's own release arrive together. An integration check — the proof is above."""

    def test_a_stop_thread_and_the_owner_release_one_real_range_once(self):
        r = ProcessRange("real", [PY, "-c", "import time\nend = time.time() + 120\nwhile time.time() < end: time.sleep(0.05)"],
                         grace_s=(1.0, 1.0), wait_s=10.0).start()
        self.addCleanup(lambda: r.release() if not r._reaped else None)
        gate = threading.Barrier(2)

        def aligned():
            gate.wait(BOUND_S)
        stop, owner = Caller(r, "stop", before=aligned), Caller(r, "owner", before=aligned)
        stop.start()
        owner.start()
        stop.finish(self)
        owner.finish(self)
        self.assertEqual((stop.error, owner.error), (None, None))
        self.assertEqual(r.members(), [])
        self.assertTrue(r._reaped and r._anchor.stdin.closed and r._anchor.stdout.closed)
        ladder = ["cooperative", "terminate", "kill"] if POSIX else ["terminate_job"]
        stages = [s["stage"] for s in r.ledger]
        self.assertTrue(stages and stages == ladder[:len(stages)], stages)   # one ladder, not two climbing together


if __name__ == "__main__":
    unittest.main()
