"""PL-7, the `aisef run` session teardown: a process that LEFT a session's range (setsid) can be caught mid-exit at
release(), so a single snapshot may report it alive though it is gone a moment later (measured: the E2 X1 guest, a
session timeout, pid 1681 reported by the kernel yet absent on every re-look). client._release_session re-checks the
named escapees over a grace: one gone within it keeps the session's outcome (named, never silent); one that STAYS alive
refuses the session (a developer process that could still write). This is the mutation runner's PL-7 settle, applied to
the run — not a wider timeout and not a suppressed leak. Both cases are pinned here; nothing is signalled."""

import subprocess
import sys
import unittest

from aisef2.app import client
from aisef2.runtime.process_range import Proc, RangeEscaped, process_table


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

    def test_an_escapee_gone_within_the_grace_keeps_the_outcome_and_is_named(self):
        # a process that exited before (or during) the post-release snapshot: reaped, so absent from the table — gone.
        p = subprocess.Popen([sys.executable, "-c", ""])
        p.wait()
        dead = p.pid
        self.assertNotIn(dead, process_table(), "precondition: the pid is reaped and not in the table")
        r = _FakeRange("developer S1", [Proc(pid=dead, ppid=1, group=None, created=None, command="gone")])
        self.assertEqual(client._release_session(r), [dead])   # named on the result, NO RangeEscaped: the session is not refused

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

    def test_a_range_not_empty_residual_always_propagates(self):
        from aisef2.runtime.process_range import RangeNotEmpty

        class NotEmpty(_FakeRange):
            def release(self):
                raise RangeNotEmpty(f"{self.name}: not empty after []: [(1, 'x')]")
        with self.assertRaises(RangeNotEmpty):
            client._release_session(NotEmpty("developer S1", []))


if __name__ == "__main__":
    unittest.main()
