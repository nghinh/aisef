"""PL-7, the `aisef run` session teardown: a process that LEFT a session's range (setsid) can be caught mid-exit at
release(), so a single snapshot may report it alive though it is gone a moment later (measured: the E2 X1 guest, a
session timeout, pid 1681 reported by the kernel yet absent on every re-look). client._release_session re-checks the
named escapees over a grace: one gone within it keeps the session's outcome (named, never silent); one that STAYS alive
refuses the session (a developer process that could still write). This is the mutation runner's PL-7 settle, applied to
the run — not a wider timeout and not a suppressed leak. Both cases are pinned here; nothing is signalled."""

import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from aisef2.app import client
from aisef2.runtime.process_range import (
    Proc,
    ProcessTableError,
    RangeEscaped,
    _win_liveness,
    pid_alive,
    process_table,
)


class _FakeRange:
    """release() raises RangeEscaped (or not); left_the_range() returns what the flight recorded leaving."""
    def __init__(self, name, left, raise_escaped=True):
        self.name = name
        self._left = list(left)
        self._raise = raise_escaped

    def release(self):
        if self._raise:
            raise RangeEscaped(f"{self.name}: processes left the range and are alive: "
                               f"{[(p.pid, p.command) for p in self._left]}")

    def left_the_range(self):
        return list(self._left)


class PL7SessionTeardown(unittest.TestCase):
    def test_a_clean_release_returns_no_escapees(self):
        self.assertEqual(client._release_session(_FakeRange("developer S1", [], raise_escaped=False)), [])

    @unittest.skipUnless(os.name == "posix", "reads the live POSIX process table")
    def test_an_escapee_gone_within_the_grace_keeps_the_outcome_and_is_named(self):
        # a process that exited before (or during) the post-release snapshot: reaped, so absent from the table — gone.
        p = subprocess.Popen([sys.executable, "-c", ""])
        p.wait()
        dead = p.pid
        self.assertNotIn(dead, process_table(), "precondition: the pid is reaped and not in the table")
        r = _FakeRange("developer S1", [Proc(pid=dead, ppid=1, group=None, created=None, command="gone")])
        self.assertEqual(client._release_session(r), [dead])   # named on the result, NO RangeEscaped: the session is not refused

    @unittest.skipUnless(os.name == "posix", "reads the live POSIX process table")
    def test_a_process_that_stays_alive_refuses_the_session(self):
        # a real escapee that outlives release(): detection is kept — RangeEscaped is re-raised and the session refused.
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        proc = process_table().get(p.pid)
        self.assertIsNotNone(proc, "precondition: the live process is in the table")
        r = _FakeRange("developer S1", [proc])
        grace, poll = client.ESCAPEE_GRACE_S, client.POLL_S
        client.ESCAPEE_GRACE_S, client.POLL_S = 1.0, 0.2   # do not wait the full production grace in a test
        try:
            with self.assertRaises(RangeEscaped):
                client._release_session(r)
        finally:
            client.ESCAPEE_GRACE_S, client.POLL_S = grace, poll

    def test_escapees_proved_gone_by_the_mocked_table_keep_the_outcome_and_are_named(self):
        # the gone-within-grace path with the table FAULT-INJECTED (empty, ESRCH from the per-pid probe), as
        # IsGoneConfirmation does: every platform runs it; the real reaped-process case above is POSIX (the live table).
        r = _FakeRange("developer S1", [Proc(pid=4242, ppid=1, group=None, created=100.0, command="gone"),
                                        Proc(pid=4243, ppid=1, group=None, created=100.0, command="gone too")])
        with mock.patch.object(client, "process_table", return_value={}), \
                mock.patch.object(client.os, "kill", side_effect=ProcessLookupError(3, "ESRCH")):
            self.assertEqual(client._release_session(r), [4242, 4243])   # named on the result, NO RangeEscaped

    def test_a_process_the_mocked_table_keeps_alive_refuses_the_session(self):
        # the refuse side with the table FAULT-INJECTED: the escapee stays in the table under its own start time, so it
        # is never proved gone, and RangeEscaped is re-raised when the grace runs out — on every platform.
        proc = Proc(pid=4242, ppid=1, group=None, created=100.0, command="alive")
        r = _FakeRange("developer S1", [proc])
        grace, poll = client.ESCAPEE_GRACE_S, client.POLL_S
        client.ESCAPEE_GRACE_S, client.POLL_S = 0.3, 0.05   # do not wait the full production grace in a test
        try:
            with mock.patch.object(client, "process_table", return_value={4242: proc}):
                with self.assertRaises(RangeEscaped):
                    client._release_session(r)
        finally:
            client.ESCAPEE_GRACE_S, client.POLL_S = grace, poll

    def test_a_range_not_empty_residual_always_propagates(self):
        from aisef2.runtime.process_range import RangeNotEmpty

        class NotEmpty(_FakeRange):
            def release(self):
                raise RangeNotEmpty(f"{self.name}: not empty after []: [(1, 'x')]")
        with self.assertRaises(RangeNotEmpty):
            client._release_session(NotEmpty("developer S1", []))


class IsGoneConfirmation(unittest.TestCase):
    """client._is_gone: a process that left the range is "gone" only when positively confirmed, in the parent's PID
    namespace at the moment of the look. These cases are FAULT-INJECTED (process_table / os.kill monkeypatched): a real
    /proc read error or a real within-grace pid reuse is not reproducible on demand. The real-process cases are in
    PL7RealProcessTeardown (Linux)."""

    def test_a_table_read_error_never_reads_a_live_escapee_as_gone(self):
        # FAULT-INJECTED: process_table() raises (an unreadable/torn table). A real, live escapee must NOT read as gone
        # — os.kill(pid, 0) still finds it alive, so _is_gone is False and the session would be refused.
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        proc = Proc(pid=p.pid, ppid=1, group=None, created=None, command="alive")
        with mock.patch.object(client, "process_table", side_effect=ProcessTableError("ps printed a torn row")):
            self.assertFalse(client._is_gone(p.pid, proc))

    def test_an_eperm_from_kill_is_not_taken_for_gone(self):
        # A permission-denied observation is not proof of exit -> NOT gone (the refuse side). Checked against the
        # REAL post-H2 probe on BOTH platforms (gate-3 owner #1): the old form fault-injected os.kill, which the
        # Windows path no longer calls, so it could not see a Windows regression. Now:
        #  - Windows seam: OpenProcess failing with ERROR_ACCESS_DENIED (5) must read ALIVE -> not gone. The real
        #    _win_liveness decision is exercised on EVERY OS, so a Windows regression is caught on Linux/macOS too.
        self.assertTrue(_win_liveness(False, 5, False, 0),
                        "Windows ERROR_ACCESS_DENIED means the process exists (not ours) -> ALIVE, never gone")
        #  - the ALIVE decision must propagate through _is_gone to 'not gone', whatever the platform reason:
        with mock.patch.object(client, "process_table", return_value={}), \
             mock.patch.object(client, "pid_alive", return_value=True):
            self.assertFalse(client._is_gone(4242, Proc(4242, 1, None, None, "x")))
        #  - POSIX seam: os.kill raising EPERM (where os.kill IS the probe) must read not gone:
        if os.name == "posix":
            with mock.patch.object(client, "process_table", return_value={}), \
                 mock.patch.object(client.os, "kill", side_effect=PermissionError(1, "EPERM")):
                self.assertFalse(client._is_gone(4242, Proc(4242, 1, None, None, "x")))

    def test_an_esrch_from_kill_on_an_absent_pid_is_gone(self):
        with mock.patch.object(client, "process_table", return_value={}), \
             mock.patch.object(client.os, "kill", side_effect=ProcessLookupError(3, "ESRCH")):
            self.assertTrue(client._is_gone(4242, Proc(4242, 1, None, None, "x")))

    def test_a_reused_pid_is_not_the_escapee(self):
        # FAULT-INJECTED: the escapee exited and its pid is back under a different start time. Identity (created) proves
        # the escapee is gone though the pid is alive — the live process is someone else.
        escapee = Proc(pid=4242, ppid=1, group=None, created=100.0, command="escapee")
        reuser = Proc(pid=4242, ppid=1, group=None, created=200.0, command="someone-else")
        with mock.patch.object(client, "process_table", return_value={4242: reuser}):
            self.assertTrue(client._is_gone(4242, escapee))

    def test_the_same_pid_with_the_same_start_time_is_the_escapee_still_alive(self):
        same = Proc(pid=4242, ppid=1, group=None, created=100.0, command="escapee")
        with mock.patch.object(client, "process_table", return_value={4242: same}):
            self.assertFalse(client._is_gone(4242, same))


class WinLivenessDecision(unittest.TestCase):
    """The Windows liveness decision `_win_liveness` — the post-H2 probe (OpenProcess + GetExitCodeProcess), fed the
    real ctypes results in production — proven on EVERY OS so a Windows regression is caught on Linux/macOS CI too
    (gate-3 owner #1/#2). GONE is concluded ONLY from reliable non-existence evidence; every ambiguous failure reads
    ALIVE (fail closed). The five owner-mandated branches follow, plus an exact-boundary case that detects divergence."""

    def test_process_alive_reports_alive(self):
        # OpenProcess opened the handle, GetExitCodeProcess read STILL_ACTIVE (259): running.
        self.assertTrue(_win_liveness(True, 0, True, 259))

    def test_process_genuinely_gone_reports_gone(self):
        # the only two reliable 'gone' signals: OpenProcess "no such pid" (ERROR_INVALID_PARAMETER 87), and a handle
        # that opened and reported a real (non-STILL_ACTIVE) exit code -> the process terminated.
        self.assertFalse(_win_liveness(False, 87, False, 0))   # no such process id
        self.assertFalse(_win_liveness(True, 0, True, 0))      # opened, exited with code 0

    def test_access_denied_reports_alive(self):
        # ERROR_ACCESS_DENIED (5): the process exists, we just may not query it -> ALIVE, never gone.
        self.assertTrue(_win_liveness(False, 5, False, 0))

    def test_resource_exhaustion_reports_alive_not_gone(self):
        # a transient kernel resource failure for a process that may well exist -> conservatively ALIVE.
        self.assertTrue(_win_liveness(False, 8, False, 0))      # ERROR_NOT_ENOUGH_MEMORY
        self.assertTrue(_win_liveness(False, 1450, False, 0))   # ERROR_NO_SYSTEM_RESOURCES

    def test_unknown_open_failure_reports_alive_not_gone(self):
        # any error that is neither "no such pid" (87) nor success is ambiguous -> ALIVE (fail closed, no inference).
        self.assertTrue(_win_liveness(False, 0, False, 0))      # GetLastError set nothing
        self.assertTrue(_win_liveness(False, 1, False, 0))      # ERROR_INVALID_FUNCTION, arbitrary
        self.assertTrue(_win_liveness(False, 1300, False, 0))   # ERROR_NOT_ALL_ASSIGNED, arbitrary

    def test_handle_opened_but_exit_code_unreadable_reports_alive(self):
        # GetExitCodeProcess failed: cannot prove gone -> ALIVE.
        self.assertTrue(_win_liveness(True, 0, False, 0))

    def test_a_process_that_exited_with_code_259_reads_alive_the_safe_direction(self):
        # the documented STILL_ACTIVE ambiguity: a process that exited with 259 reads ALIVE — false-alive is safe.
        self.assertTrue(_win_liveness(True, 0, True, 259))

    def test_only_no_such_pid_among_open_failures_is_gone(self):
        # exact boundary: for EVERY OpenProcess-failure error, ALIVE unless it is exactly 87. Kills a mutant that
        # flips the test back to `== 5` (old false-gone), to `== 87`, or to a constant.
        for err in (0, 1, 5, 6, 8, 14, 87, 122, 299, 1300, 1450):
            self.assertEqual(_win_liveness(False, err, False, 0), err != 87, f"open-failure error {err}")


@unittest.skipUnless(os.name == "posix", "os.kill(pid, 0) is the POSIX branch of pid_alive")
class PidAlivePosixSeam(unittest.TestCase):
    """pid_alive's POSIX branch (os.kill(pid, 0)) — unchanged by the gate-3 fix, pinned against a future weakening:
    only ESRCH is gone; EPERM and every other OSError read ALIVE. The owner-mandated branches for POSIX."""

    def _kill(self, **kw):
        return mock.patch("aisef2.runtime.process_range.os.kill", **kw)

    def test_process_alive_reports_alive(self):
        with self._kill(return_value=None):
            self.assertTrue(pid_alive(4242))

    def test_process_genuinely_gone_reports_gone(self):
        with self._kill(side_effect=ProcessLookupError(3, "ESRCH")):
            self.assertFalse(pid_alive(4242))

    def test_access_denied_reports_alive(self):
        with self._kill(side_effect=PermissionError(1, "EPERM")):
            self.assertTrue(pid_alive(4242))

    def test_unknown_or_resource_oserror_reports_alive_not_gone(self):
        with self._kill(side_effect=OSError(12, "ENOMEM")):   # resource exhaustion / any non-ESRCH OSError
            self.assertTrue(pid_alive(4242))

    def test_a_non_positive_pid_is_never_alive(self):
        self.assertFalse(pid_alive(0))
        self.assertFalse(pid_alive(-1))


class PL7DeveloperEscapeeHoldsWorkspace(unittest.TestCase):
    """story_runner._EscapedRange (PL-7, §17.1, owner 2026-10-20 point 1): a developer session whose range left a live
    process holds the writable resources the escapee could still write to RESIDUAL at scope disposal, instead of
    force-removing them — the same guarantee a probe range that did not empty gets."""

    def test_an_escaped_developer_range_holds_the_checkout_and_scratch_residual(self):
        from types import SimpleNamespace

        from aisef2.journal.format2 import ReleaseStatus as S, ResourceKind as K
        from aisef2.orchestrate.story_runner import _EscapedRange
        from aisef2.runtime.story_scope import StoryScope

        seq = [0]

        def emit(t, d, **k):
            seq[0] += 1
            return SimpleNamespace(seq=seq[0])

        released: list[str] = []

        class _Dir:
            def __init__(self, name, kind):
                self.name, self.kind = name, kind

            def release(self):
                released.append(self.name)

        scope = StoryScope("S1", emit, release_timeout_s=None)
        scope.acquire(_Dir("scratch-S1", K.SCRATCH))     # acquired first (disposed last)
        scope.acquire(_Dir("wt-S1", K.WORKTREE))         # the implementer's checkout
        scope.acquire(_EscapedRange("developer S1 range", "left a live process"))  # PROCESS_RANGE, on top
        report = scope.dispose()
        byname = {r.resource: r.status for r in report.records}
        self.assertEqual(byname["developer S1 range"], S.RESIDUAL.value)   # the leak is named RESIDUAL
        self.assertEqual(byname["wt-S1"], S.RESIDUAL.value)                # the checkout is HELD, not released
        self.assertEqual(byname["scratch-S1"], S.RESIDUAL.value)          # the scratch too
        self.assertEqual(released, [])                                     # neither directory's release() ran
        self.assertFalse(report.ok)


@unittest.skipUnless(sys.platform == "linux", "real setsid escapees and /proc identity need Linux (the e2 guest)")
class PL7RealProcessTeardown(unittest.TestCase):
    """PL-7 with REAL orchestrated processes (owner 2026-10-20 point 3): a real ProcessRange whose anchor forks a
    setsid child that leaves the range's process group. These are measured on Linux; the pid-reuse and /proc-read-error
    cases stay in IsGoneConfirmation (fault-injected, not reproducible on demand). The grace and poll are shortened so
    the test does not wait the production minute."""

    # The anchor forks a setsid child (which leaves the range's process group -> escapes), prints nothing, and exits at
    # once; the child sleeps `lifetime` seconds then exits. argv[1] = lifetime.
    ESCAPE = ("import os, sys, time\n"
              "pid = os.fork()\n"
              "if pid == 0:\n"
              "    os.setsid()\n"
              "    time.sleep(float(sys.argv[1]))\n"
              "    os._exit(0)\n"
              "os._exit(0)\n")

    def _range(self, lifetime: float):
        from aisef2.runtime.process_range import ProcessRange
        devnull = open(os.devnull, "w")
        self.addCleanup(devnull.close)
        r = ProcessRange("pl7-real", [sys.executable, "-c", self.ESCAPE, str(lifetime)],
                         cwd=os.getcwd(), env=dict(os.environ), output=devnull)
        r.start()
        return r

    def _short_grace(self, grace: float):
        g, p = client.ESCAPEE_GRACE_S, client.POLL_S
        client.ESCAPEE_GRACE_S, client.POLL_S = grace, 0.1
        self.addCleanup(lambda: setattr(client, "ESCAPEE_GRACE_S", g))
        self.addCleanup(lambda: setattr(client, "POLL_S", p))

    def test_a_range_with_no_escapee_releases_clean(self):
        # REAL: the anchor forks no surviving child (lifetime 0: the child exits at once, within release()'s own wait).
        self._short_grace(5.0)
        r = self._range(0.0)
        time.sleep(0.3)
        self.assertEqual(client._release_session(r), [])

    def test_an_escapee_alive_past_the_grace_refuses_the_session(self):
        # REAL: a setsid child that outlives the grace -> RangeEscaped is re-raised, the session is refused.
        self._short_grace(1.0)
        r = self._range(30.0)
        time.sleep(0.3)
        with self.assertRaises(RangeEscaped):
            client._release_session(r)

    def test_an_escapee_that_self_exits_within_the_grace_is_named_gone(self):
        # REAL: a setsid child that leaves the group then exits within the grace -> named on the result, not a refusal.
        self._short_grace(5.0)
        r = self._range(1.0)
        time.sleep(0.3)
        gone = client._release_session(r)
        self.assertTrue(gone, "the self-exited escapee is named on the result")


if __name__ == "__main__":
    unittest.main()
