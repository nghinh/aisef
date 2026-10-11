"""V2.1 (owner B-03, kills3 batch TO3): the survivor of aisef2/app/adapters.py::_bounded that campaign 2 could not
classify because the mutant never ended ("L281 And swapped": `while code is None or time.monotonic() < deadline`).

`_bounded` gives the finder's process (Open Code Review's preview, then its review) `timeout_s`: it returns the exit
status as soon as the process has ended, or None when the budget ran out, and releases the process range either way.
What the callers rely on (`Reviewer._ocr`: `timed_out = code is None`, the session's seconds, the next stage starting
at all) is that the poll STOPS at one of those two points. The mutant stops at neither: after the process ended it
polls out the whole budget, and a process that outlives the budget is polled for ever.

The tests bound a loop that must terminate without a real timer: the process range is a scripted stand-in that follows
the real one's `wait` contract (an exit status once the process has ended, None when the asked wait runs out) on a
hand-driven clock, and raises AssertionError("did not terminate") when polled past the point a correct loop stops.
One test runs a real child through the real ProcessRange: it ends by itself, so there is nothing to time."""

from __future__ import annotations

import math
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import client  # noqa: E402

START = 1000.0     # where the test's clock starts
TICK = 1e-6        # a real clock moves on even for a wait of zero seconds
SLACK = 0.001      # "at the deadline": a float's width, not a poll's


class Clock:
    """`time.monotonic` of a test: only a wait of the scripted range moves it."""

    def __init__(self) -> None:
        self.now = START

    def monotonic(self) -> float:
        return self.now


class ScriptedRange:
    """ProcessRange as `_bounded` drives it (construct, `start`, `wait`, `release`) on the test's clock.

    `ends_after` seconds after the start the process has ended with status `status`; None: it never ends. Like the real
    `wait`: an ended process answers at once with its status (a wait of an ended process spends no time), a running
    one answers None after the asked time, and an answer comes no later than the process's end. `limit`: the waits a
    loop that terminates can have made (one per poll slice of the budget, plus slack); a loop past it has not stopped."""

    def __init__(self, clock: Clock, ends_after: float | None, status: int | None, limit: int) -> None:
        self.clock, self.status, self.limit = clock, status, limit
        self.ends_at = None if ends_after is None else clock.now + ends_after
        self.waits: list[float] = []
        self.started = self.released = 0
        self.status_given = False

    def __call__(self, name, argv, **_how):     # the class `_bounded` constructs
        return self

    def start(self):
        self.started += 1
        return self

    def release(self) -> None:
        self.released += 1

    @property
    def elapsed(self) -> float:
        return self.clock.now - START

    def wait(self, timeout: float | None = None):
        self.waits.append(timeout)
        if len(self.waits) > self.limit:
            raise AssertionError(f"did not terminate: {len(self.waits)} waits, clock {self.elapsed:.1f} s in")
        if self.status_given:
            raise AssertionError("polled again after the process had ended and its exit status was known: "
                                 "the loop waits out the whole budget instead of returning it")
        if self.ends_at is not None and self.clock.now + timeout >= self.ends_at:
            self.clock.now = max(self.clock.now, self.ends_at)
            self.status_given = True
            return self.status
        self.clock.now += max(timeout, TICK)
        return None


class Bounded(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()

    def run_bounded(self, ends_after, status, timeout_s: float, tag: str):
        """`_bounded` on a fresh clock and range: (what it returned, the range)."""
        rng = ScriptedRange(Clock(), ends_after, status, limit=2 * math.ceil(timeout_s / client.POLL_S) + 10)
        with mock.patch.object(ad, "ProcessRange", rng), \
                mock.patch.object(ad, "time", types.SimpleNamespace(monotonic=rng.clock.monotonic)):
            got = ad._bounded(["finder", "--review"], str(self.tmp), {}, self.tmp / f"{tag}.log", timeout_s, f"ocr {tag}")
        return got, rng


class ExitStatusIsReturnedWhenTheProcessEnds(Bounded):
    """Pins aisef2/app/adapters.py::_bounded [6] (And swapped, TIMEOUT at campaign 2).

    A finder that ends inside its budget is reported with its exit status at the moment it ended: no further wait, and
    the budget is not spent (the mutant keeps polling an ended process until the deadline — an hour here — and the
    range's stand-in refuses the first such poll). The status 0 is a status like any other, not "still running"."""

    def test_the_status_is_returned_at_the_end_of_the_process_not_at_the_end_of_the_budget(self):
        for status in (0, 3):
            with self.subTest(status=status):
                got, rng = self.run_bounded(7.0, status, 3600.0, f"exit-{status}")
                self.assertEqual(got, status)
                self.assertAlmostEqual(rng.elapsed, 7.0, delta=SLACK, msg="the clock stopped when the process ended")
                self.assertTrue(rng.status_given)
                self.assertEqual((rng.started, rng.released), (1, 1), "the range is released once the status is known")


class BudgetIsEnforcedWhenTheProcessDoesNotEnd(Bounded):
    """Pins aisef2/app/adapters.py::_bounded [6] (And swapped, TIMEOUT at campaign 2).

    A finder that outlives `timeout_s` is reported as timed out (None — `Reviewer._ocr` records `timed_out` from it and
    the story's review is then INDETERMINATE) at the budget, not a poll slice after it, and its range is released. The
    mutant never leaves the loop once the deadline is past (`code` stays None), so the stand-in's bound raises."""

    def test_a_process_that_outlives_the_budget_is_reported_as_none_after_exactly_the_budget(self):
        for budget in (12.0, client.POLL_S / 2):    # longer, and shorter, than one poll slice
            with self.subTest(budget=budget):
                got, rng = self.run_bounded(None, None, budget, f"never-{budget:g}")
                self.assertIsNone(got)
                self.assertAlmostEqual(rng.elapsed, budget, delta=SLACK, msg="gave up at the deadline: not before, not after")
                self.assertAlmostEqual(sum(rng.waits), budget, delta=SLACK)
                self.assertEqual((rng.started, rng.released), (1, 1), "the range is released when the budget ran out")

    def test_a_process_that_ends_after_the_budget_is_reported_as_timed_out(self):
        """It ended 5 s after the deadline: the loop had already given up on it, as the caller's clock did."""
        got, rng = self.run_bounded(17.0, 0, 12.0, "late")
        self.assertIsNone(got)
        self.assertFalse(rng.status_given)
        self.assertEqual(rng.released, 1)


class RealProcessEndsOnItsOwn(unittest.TestCase):
    """Pins aisef2/app/adapters.py::_bounded [6] against the real ProcessRange: a real child that exits with status 7
    is reported with it, and the loop does not poll the ended process again (the spy raises on a poll from the loop;
    `release`'s own final look at the child is not the loop's). The budget is far above the child's life: nothing here
    waits on a timer."""

    def test_a_real_child_exit_status_is_returned_and_not_polled_again(self):
        t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)     # a Windows handle may outlive the child briefly
        self.addCleanup(t.cleanup)
        tmp = pathlib.Path(t.name).resolve()

        class Spy(ad.ProcessRange):
            status_seen = releasing = False

            def wait(self, timeout=None):
                if self.status_seen and not self.releasing:
                    raise AssertionError("polled again after the process had ended: the loop waits out its budget")
                code = super().wait(timeout)
                self.status_seen = self.status_seen or code is not None
                return code

            def release(self):
                self.releasing = True
                super().release()

        with mock.patch.object(ad, "ProcessRange", Spy):
            got = ad._bounded([sys.executable, "-I", "-c", "raise SystemExit(7)"], str(tmp), dict(os.environ),
                              tmp / "child.log", 120.0, "real exit 7")
        self.assertEqual(got, 7)


if __name__ == "__main__":
    unittest.main()
