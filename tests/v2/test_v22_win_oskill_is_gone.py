"""FINDING-WIN-OSKILL-001 (owner round-3, H1+H2): `_is_gone`'s escapee-liveness probe must be read-only on every
platform and must never let a failed process-table read distort the verdict.

H1 — a `ps` that exits non-zero raises `subprocess.CalledProcessError` (NOT an `OSError`); on the old kernel it
propagated uncaught out of `_is_gone` (the Windows reproduction erred there before ever reaching the probe). The guard
now treats any `process_table()` failure, including a `subprocess.SubprocessError`, as an unreadable table and falls
through to the per-pid probe — an observation failure is never evidence of exit.

H2 — the fallback probe was a bare `os.kill(pid, 0)`, which on Windows is destructive (signal 0 == CTRL_C_EVENT,
routed to TerminateProcess on CPython <= 3.12), so the "probe" terminated a live escapee. It is now
`process_range.pid_alive`: `os.kill(pid, 0)` on POSIX (unchanged, non-destructive there) and a read-only
`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetExitCodeProcess` handle on Windows (no PROCESS_TERMINATE).

Decision table preserved exactly: provably-absent -> gone; reused pid (different start time) -> gone; running,
not-ours (EPERM), or any ambiguous/unreadable observation -> NOT gone (the refuse side). The reused-pid / torn-table /
EPERM / ESRCH cases are pinned in test_v21_pl7_session_teardown.py; this file adds the H1 and H2 regression and the
Windows non-destructive case.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from aisef2.app import client
from aisef2.runtime import process_range
from aisef2.runtime.process_range import pid_alive


class _Proc:
    """A (pid, proc) call-shape stand-in with no start time to compare on."""
    created = None


class H1TableReadFailureIsNeverTakenForExit(unittest.TestCase):
    def test_a_ps_that_exits_non_zero_is_caught_not_raised(self):
        # RED on the old kernel: CalledProcessError is not an OSError, so it propagated out of _is_gone (the Windows
        # repro erred here). GREEN now: caught, fall through to the probe, which finds the live child alive -> not gone.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        err = subprocess.CalledProcessError(1, ["ps", "-A"])
        with mock.patch.object(client, "process_table", side_effect=err):
            self.assertIs(client._is_gone(child.pid, _Proc()), False,
                          "a failed `ps` must not raise, and a live escapee must not read as gone")

    def test_any_subprocess_error_is_caught(self):
        err = subprocess.TimeoutExpired(["ps"], 1.0)
        with mock.patch.object(client, "process_table", side_effect=err):
            # absent pid + probe: no raise; the verdict is the probe's, not an exception
            self.assertIsInstance(client._is_gone(2_000_000_000, _Proc()), bool)


class H2ProbeIsReadOnly(unittest.TestCase):
    def test_pid_alive_reports_a_live_child_and_a_reaped_child(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertTrue(pid_alive(child.pid), "a running child must read as alive")
        child.kill()
        child.wait()
        time.sleep(0.05)
        self.assertFalse(pid_alive(child.pid), "a reaped child must read as gone")

    def test_pid_alive_rejects_non_positive_pids(self):
        self.assertFalse(pid_alive(0))
        self.assertFalse(pid_alive(-1))

    def test_is_gone_uses_the_probe_a_reaped_pid_is_gone_a_live_one_is_not(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (child.poll() is None and (child.kill(), child.wait())))
        with mock.patch.object(client, "process_table", return_value={}):
            self.assertIs(client._is_gone(child.pid, _Proc()), False, "a live escapee is not provably gone")
            child.kill()
            child.wait()
            time.sleep(0.05)
            self.assertIs(client._is_gone(child.pid, _Proc()), True, "a reaped escapee is provably gone")

    @unittest.skipUnless(os.name == "posix", "POSIX probe routing")
    def test_the_probe_does_not_signal_on_posix(self):
        # pid_alive must only ever ask (signal 0), never deliver a real signal.
        seen = []
        real = os.kill

        def spy(pid, sig):
            seen.append(sig)
            return real(pid, sig)

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        with mock.patch.object(process_range.os, "kill", spy):
            pid_alive(child.pid)
        self.assertEqual(seen, [0], "the probe sent something other than signal 0")


class WinOsKillIsDestructive(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "os.kill(pid, 0) is a safe POSIX probe off Windows")
    def test_is_gone_must_not_terminate_a_live_escapee_on_windows(self):
        # RED on the old kernel (os.kill(pid, 0) terminated the child); GREEN with the OpenProcess query probe.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertIsNone(child.poll(), "precondition: the child must be alive before the probe")
            gone = client._is_gone(child.pid, _Proc())
            time.sleep(0.2)  # give any delivered Ctrl+C / TerminateProcess time to land
            self.assertIsNone(child.poll(),
                              "FINDING-WIN-OSKILL-001: _is_gone terminated a live process on Windows")
            self.assertFalse(gone, "a live process must not be reported as provably gone")
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)


class _P:
    """A proc/table-row stand-in with a chosen start time."""
    def __init__(self, created):
        self.created = created


class _CountingCreated:
    """`created` as a property, so a test can see (or forbid) its evaluation: the or-chain at client.py L47
    is truth-value order-invariant for every real input, so its short-circuit ORDER is the only observable a
    reordered `or` changes."""
    def __init__(self, value, readable=True):
        self._value, self._readable, self.reads = value, readable, 0

    @property
    def created(self):
        self.reads += 1
        if not self._readable:
            raise AssertionError("short-circuit broken: this operand must not be evaluated")
        return self._value


class B1IsGoneSurvivorKills(unittest.TestCase):
    """B1 release-gate mutation-survivor kills for the table-hit branch of `_is_gone` (client.py L43-L48):
    the pid-reuse start-time comparison and the table-read exception tuple. Platform-independent — the table
    and the probe are mocked, nothing real is probed or signalled."""

    def _is_gone_with(self, proc, present):
        with mock.patch.object(client, "process_table", return_value={321: present}):
            return client._is_gone(321, proc)

    def test_table_hit_same_start_time_is_still_the_escapee(self):
        self.assertIs(self._is_gone_with(_P(7.5), _P(7.5)), False, "same start time: still the escapee")

    def test_table_hit_different_start_time_is_a_reused_pid(self):
        self.assertIs(self._is_gone_with(_P(7.5), _P(8.5)), True, "different start time: the pid was reused, gone")

    def test_table_hit_with_no_start_time_on_either_side_is_not_gone(self):
        self.assertIs(self._is_gone_with(_P(None), _P(7.5)), False, "no escapee start time to compare on")
        self.assertIs(self._is_gone_with(_P(7.5), _P(None)), False, "no table start time to compare on")

    def test_the_none_guards_short_circuit_before_the_comparison(self):
        # An escapee with no start time must be decided WITHOUT reading the table row's (left guard first):
        self.assertIs(self._is_gone_with(_CountingCreated(None), _CountingCreated(5.0, readable=False)),
                      False)
        # and with both start times present, each side is read exactly once (guards, then one comparison
        # operand each, stopping at the table-row None guard):
        proc, present = _CountingCreated(5.0), _CountingCreated(None)
        self.assertIs(self._is_gone_with(proc, present), False)
        self.assertEqual((proc.reads, present.reads), (1, 1),
                         "L47 must evaluate guards in order and short-circuit")

    def test_each_table_read_failure_falls_through_to_the_probe(self):
        # One per element of the except tuple (client.py L43): drop any one and the raise propagates out of
        # _is_gone instead of falling through to the per-pid probe.
        failures = [
            process_range.ProcessTableError("not a process row"),
            OSError("table read failed"),
            UnicodeDecodeError("utf-8", b"\x80", 0, 1, "torn row"),
            subprocess.CalledProcessError(1, ["ps", "-A"]),
        ]
        for err in failures:
            with self.subTest(err=type(err).__name__):
                with mock.patch.object(client, "process_table", side_effect=err), \
                        mock.patch.object(client, "pid_alive", return_value=False):
                    self.assertIs(client._is_gone(321, _P(7.5)), True,
                                  "an unreadable table must fall through to the probe, not raise")


if __name__ == "__main__":
    unittest.main()
