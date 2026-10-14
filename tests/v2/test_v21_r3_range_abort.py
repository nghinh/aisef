"""B-03 round 3 — `_Posix.abort` (aisef2/runtime/process_range.py), the abort of a range whose start() failed.

The requirement (the method's own shape and its call path: start() calls abort(anchor) when the range cannot be
established): a LIVE anchor is killed through its process group, an anchor that has ENDED is never signalled — its pid
may already belong to another process and the group id it pinned is gone.

campaign 5 left two TIMEOUT mutants at this method (`anchor.poll() is None` negated: a live anchor is left running, so
the test that waits for it never returned). The test below fails at once instead: it never starts a process, the
anchor is a stand-in and `os.killpg` is a recording stub, so the mutant is KILLED by an assertion in microseconds
and no signal can reach a real group (INV-MUTATION-AUTHORITY: this file signals nothing).
"""

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


class Anchor:
    """A stand-in for subprocess.Popen: a pid and what poll() answers."""

    def __init__(self, pid: int, returncode: int | None) -> None:
        self.pid, self._rc = pid, returncode

    def poll(self):
        return self._rc


@unittest.skipUnless(os.name == "posix", "the POSIX backend")
class AbortKillsOnlyALiveAnchorsGroup(unittest.TestCase):
    def abort(self, anchor):
        with mock.patch.object(pr.os, "killpg") as killpg:
            pr._Posix().abort(anchor)
        return killpg.call_args_list

    def test_a_live_anchor_has_its_whole_group_killed_once(self):
        self.assertEqual(self.abort(Anchor(4242, None)), [mock.call(4242, signal.SIGKILL)])

    def test_the_group_is_the_anchors_own_not_the_callers(self):
        # the anchor leads its own session (start_new_session): its pid IS the group id
        calls = self.abort(Anchor(31337, None))
        self.assertEqual([c.args[0] for c in calls], [31337])
        self.assertNotIn(os.getpgrp(), [c.args[0] for c in calls])

    def test_an_anchor_that_has_ended_is_never_signalled(self):
        for rc in (0, 1, 2, -9, -15):
            with self.subTest(returncode=rc):
                self.assertEqual(self.abort(Anchor(4242, rc)), [])


if __name__ == "__main__":
    unittest.main()
