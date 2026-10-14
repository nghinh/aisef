"""B-03 round 3 — `_Posix.abort` (aisef2/runtime/process_range.py), the abort of a range whose start() failed.

The requirement (the method's shape and its call path: `start()` calls `_abort()` when the range cannot be
established, and `_abort` goes on to `anchor.wait()` — an anchor that is still running there would hang the caller):

* a LIVE anchor is SIGKILLed through its own process group, once; an anchor that has ENDED is never signalled — its pid
  may already belong to another process and the group id it pinned is gone;
* the group being already gone (the anchor ended between `poll()` and the signal: ESRCH, or EPERM where macOS answers
  it for a group of zombies) is not an error — nothing is left to kill, and the failure that led here must not be
  replaced by this one (`signal()` of the same class says the same); any other failure of the signal is not hidden.

campaign 5 left two TIMEOUT mutants at this method (`anchor.poll() is None` negated: a live anchor is left running, so
the P4 test that waits for it never returned). The tests below fail at once instead: no process is started, the anchor
is a stand-in and `os.killpg` and `os.kill` are recorders, so a mutant is KILLED by an assertion in microseconds and
nothing real can be signalled (INV-MUTATION-AUTHORITY: this file signals nothing).
"""

import errno
import os
import pathlib
import signal
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.runtime import process_range as pr  # noqa: E402

PID = 4242      # no real process is signalled: both signal calls of `os` are replaced below


class Anchor:
    """A stand-in for subprocess.Popen: a pid and what poll() answers."""

    def __init__(self, pid: int, returncode: int | None) -> None:
        self.pid, self._rc = pid, returncode

    def poll(self):
        return self._rc


@unittest.skipUnless(os.name == "posix", "the POSIX backend")
class Abort(unittest.TestCase):
    def abort(self, anchor, killpg_raises: BaseException | None = None):
        """(calls of os.killpg, calls of os.kill) of `_Posix.abort(anchor)` on a backend that adopted the anchor."""
        backend = pr._Posix()
        backend.adopt(anchor.pid)
        with mock.patch.object(pr.os, "killpg", side_effect=killpg_raises) as killpg, \
                mock.patch.object(pr.os, "kill") as kill:
            backend.abort(anchor)
        return killpg.call_args_list, kill.call_args_list

    def test_a_live_anchor_has_its_own_group_killed_once_and_nothing_else_is_signalled(self):
        killpg, kill = self.abort(Anchor(PID, None))
        self.assertEqual(killpg, [mock.call(PID, signal.SIGKILL)])
        self.assertEqual(kill, [])

    def test_the_group_is_the_anchors_pid_not_a_pid_the_code_could_hold_otherwise(self):
        for pid in (31337, 7):
            with self.subTest(pid=pid):
                killpg, _ = self.abort(Anchor(pid, None))
                self.assertEqual([c.args[0] for c in killpg], [pid])

    def test_an_anchor_that_has_ended_is_never_signalled(self):
        for rc in (0, 1, 2, -9, -15):
            with self.subTest(returncode=rc):
                self.assertEqual(self.abort(Anchor(PID, rc)), ([], []))

    def test_a_group_that_is_already_gone_is_not_an_error(self):
        for exc in (ProcessLookupError(errno.ESRCH, "no such process"), PermissionError(errno.EPERM, "not permitted")):
            with self.subTest(exc=type(exc).__name__):
                killpg, kill = self.abort(Anchor(PID, None), killpg_raises=exc)
                self.assertEqual(killpg, [mock.call(PID, signal.SIGKILL)])      # it was tried, once
                self.assertEqual(kill, [])

    def test_a_failure_that_is_not_an_absent_group_is_not_hidden(self):
        with self.assertRaises(OSError) as raised:
            self.abort(Anchor(PID, None), killpg_raises=OSError(errno.EINVAL, "invalid argument"))
        self.assertEqual(raised.exception.errno, errno.EINVAL)


if __name__ == "__main__":
    unittest.main()
