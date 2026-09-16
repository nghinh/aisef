"""The Phase 12 watchdog is qualification infrastructure (owner item 7): its decision must be right deterministically —
progressing → no alarm; stalled → alarm; dead → terminal; a signal that cannot be measured → TOOL_UNAVAILABLE, never a
false stall."""
from __future__ import annotations

import unittest

from validation.p12_watchdog import Signals, Tracker, alive, classify, limit_s, running_chunk


class TestClassify(unittest.TestCase):
    def test_progressing_process_raises_no_alarm(self):
        t = Tracker(now=0.0)
        for tick in range(1, 200):                                  # the marker moves every tick, far beyond the limit in wall time
            self.assertEqual(t.observe(now=tick * 100.0, sig=Signals(True, ("log", tick), False), limit=1000.0), "PROGRESSING")

    def test_stalled_process_alarms_only_after_the_limit(self):
        t = Tracker(now=0.0)
        self.assertEqual(t.observe(10.0, Signals(True, ("log", 1), False), limit=1000.0), "PROGRESSING")
        self.assertEqual(t.observe(900.0, Signals(True, ("log", 1), False), limit=1000.0), "PROGRESSING")   # within the limit
        self.assertEqual(t.observe(1011.0, Signals(True, ("log", 1), False), limit=1000.0), "STALL")        # 1001 s without change

    def test_dead_process_is_terminal_even_when_recent(self):
        t = Tracker(now=0.0)
        self.assertEqual(t.observe(1.0, Signals(False, ("log", 1), False), limit=1000.0), "DEAD")

    def test_completed_chunk_wins(self):
        self.assertEqual(classify(10_000.0, 0.0, Signals(False, None, True), 1.0), "COMPLETE")

    def test_unmeasurable_signal_is_tool_unavailable_never_a_stall(self):
        t = Tracker(now=0.0)
        self.assertEqual(t.observe(10_000.0, Signals(None, ("log", 1), False), limit=1.0), "TOOL_UNAVAILABLE")   # liveness unknown
        self.assertEqual(t.observe(20_000.0, Signals(True, None, False), limit=1.0), "TOOL_UNAVAILABLE")         # progress unknown
        self.assertEqual(t.observe(20_001.0, Signals(True, ("log", 2), False), limit=1.0), "PROGRESSING")        # measurable again → the clock restarts

    def test_limit_is_three_times_the_median_with_a_two_hour_floor(self):
        self.assertEqual(limit_s([]), 7200.0)
        self.assertEqual(limit_s([1000.0, 2000.0, 3000.0]), 7200.0)      # 3 × 2000 < floor
        self.assertEqual(limit_s([2400.0, 3000.0, 3100.0]), 9000.0)      # 3 × 3000


class TestSignalProviders(unittest.TestCase):
    def test_running_chunk_is_parsed_from_ps_or_reported_unmeasurable(self):
        ps = "  123 /usr/bin/python3 -m tests.hardening.differential --traces 10000 --start 40000 --workers 8 --out x.json\n  9 other\n"
        self.assertEqual(running_chunk(ps), (123, 40000))
        self.assertIs(running_chunk("  9 other\n"), False)              # none running (a chunk boundary or a dead chain)
        self.assertIsNone(running_chunk(None))                          # ps unreadable → TOOL_UNAVAILABLE upstream

    def test_alive_uses_signal_zero_not_a_platform_field(self):
        import os
        self.assertTrue(alive(os.getpid()))
        self.assertFalse(alive(2_000_000_000))                          # no such pid → dead, not unmeasurable


if __name__ == "__main__":
    unittest.main()
