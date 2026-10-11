"""Timeout batch TO2 (V2.1 mutation campaign 2): the survivor poll of the confinement measurement, bounded.

Pins aisef2/app/confine.py::_survivors [1].

`_survivors(command)` is what the measurement reports as `setsid_survivors`, and `_judge` refuses a run on a
non-empty list ("a process the session left outlived it"). Its contract: look at the process table; a sleeper that is
gone is no survivor and the poll ends AT ONCE; one still there is looked at again until SURVIVOR_GRACE has passed, and
is reported only then. The mutant that negates the loop's exit condition never returns when nothing is left (it
polls `time.sleep(0.05)` until the runner's 900 s limit), and returns a sleeper the teardown is still killing at the
first look, before its grace.

These tests run on a clock of their own, so the poll costs no wall-clock time at all and a poll that does not end is
a failure in the test's own words ("did not terminate"), after a bound the real code never comes near: it ends within
SURVIVOR_GRACE plus one 0.05 s step of fake time and looks about twenty times (the bounds are three graces and a
second of fake time, and MAX_LOOKS looks, which also stops a poll that never sleeps and so never moves the fake
clock). No real process, no real sleep, no timer: portable (Windows CI too).
"""

from __future__ import annotations

import pathlib
import sys
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from aisef2.runtime import process_range  # noqa: E402

#: the real poll looks SURVIVOR_GRACE / 0.05 + 1 = 21 times at most; a poll that never sleeps never moves the fake clock,
#: so the clock's bound alone would let it spin for ever
MAX_LOOKS = 1000
COMMAND = "sleep 30.000001"
MINE = process_range.Proc(9, 1, None, None, COMMAND)
OTHER = process_range.Proc(8, 1, None, None, "sleep 30.000002")


class Clock:
    """The time `confine._survivors` sees: `sleep` advances it and nothing else does. A poll that is still sleeping
    after `bound` seconds of it has not ended: it raises, so the test fails at once instead of waiting a limit out."""

    def __init__(self) -> None:
        self.now = 0.0
        self.bound = 3 * confine.SURVIVOR_GRACE + 1.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        if self.now > self.bound:
            raise AssertionError(f"_survivors did not terminate: still polling {self.now:.2f} s of fake time in "
                                 f"(SURVIVOR_GRACE is {confine.SURVIVOR_GRACE} s)")


class Poll(unittest.TestCase):
    """What the poll does when the table says `still_there(clock_now)`: its result, the fake time it took and how many
    times it looked."""

    def poll(self, still_there) -> tuple[list[int], float, int]:
        clock, looks = Clock(), []

        def table() -> dict:
            looks.append(clock.now)
            if len(looks) > MAX_LOOKS:
                raise AssertionError(f"_survivors did not terminate: {len(looks)} looks at the process table in "
                                     f"{clock.now:.2f} s of fake time (it pauses between looks)")
            return {9: MINE, 8: OTHER} if still_there(clock.now) else {8: OTHER}
        fake_time = types.SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
        with mock.patch.object(process_range, "process_table", table), mock.patch.object(confine, "time", fake_time):
            found = confine._survivors(COMMAND)
        return found, clock.now, len(looks)


class ThePollEndsWhenNothingIsLeft(Poll):
    """Requirement: a session that left nothing behind is judged at the first look, and one whose sleeper was still
    being torn down is judged when it is gone. Neither waits out the grace (a measurement that waited a whole grace on
    every clean run would also hold its range that much longer) and neither reports a sleeper that is gone.
    Pins aisef2/app/confine.py::_survivors [1]: negated, it polls forever once the table holds no match."""

    def test_no_match_at_the_first_look_returns_empty_without_waiting(self):
        found, took, looks = self.poll(lambda now: False)
        self.assertEqual(found, [])
        self.assertEqual(took, 0.0, "it waited although no process matched the sleeper's command line")
        self.assertEqual(looks, 1)

    def test_a_sleeper_that_is_gone_within_the_grace_ends_the_poll_when_it_is_gone(self):
        gone_at = confine.SURVIVOR_GRACE / 5
        found, took, looks = self.poll(lambda now: now < gone_at)
        self.assertEqual(found, [], "a sleeper gone within the grace was reported as a survivor")
        self.assertGreaterEqual(took, gone_at)                 # it looked again until the sleeper was gone ...
        self.assertLess(took, confine.SURVIVOR_GRACE)          # ... and stopped there, not at the end of the grace
        self.assertGreater(looks, 1)


class ASurvivorIsReportedOnlyOnceTheGraceHasPassed(Poll):
    """Requirement: a sleeper alive at every look through SURVIVOR_GRACE is a survivor, and is reported after the
    grace, not at the first look — the first look cannot tell it from one the PID namespace's teardown is still
    killing; and it is reported once that grace has passed, not a longer one later (the sleeper's own life, SLEEPER,
    is set against ONE grace: a longer look lets a real survivor reach its end unseen). Pins
    aisef2/app/confine.py::_survivors [1]: negated, the first look that sees it returns it at once."""

    def test_a_sleeper_alive_throughout_is_returned_after_the_grace_not_before(self):
        found, took, looks = self.poll(lambda now: True)
        self.assertEqual(found, [9])
        self.assertGreaterEqual(took, confine.SURVIVOR_GRACE, "it returned the sleeper before its grace had passed")
        self.assertLess(took, 2 * confine.SURVIVOR_GRACE, "it kept looking for longer than one grace")
        self.assertGreater(looks, 1)


if __name__ == "__main__":
    unittest.main()
