"""WP-4.2 — WIN-PID-1 and WIN-PID-2 (V1-PF-001): ownership is never inferred from PID ancestry. Kill set for
`process_range.py::descendants` and `::targets`. Pure: synthetic process tables, plus the local POSIX table.
"""

import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.runtime import process_range as pr  # noqa: E402
from aisef2.runtime.process_range import Proc  # noqa: E402

POSIX = os.name == "posix"


class NoPidAncestry(unittest.TestCase):
    """WIN-PID-1 and WIN-PID-2 on the synthetic snapshots of P0-OBS-001: the unmodified V1 function fails; V2
    selects nothing by ancestry, and its reporting walk terminates and drops stale edges."""

    # RUNNER=10 (live), SHELL=20 (its recorded ppid 500 belongs to a long-dead launcher), T=30, R=500 (reused pid),
    # F=600 (fake CLI), U=700 (an unrelated live process whose long-dead parent also had pid 500)
    REUSED = {10: Proc(10, 1, None, 1.0), 20: Proc(20, 500, None, 2.0), 30: Proc(30, 20, None, 3.0),
              500: Proc(500, 30, None, 9.0), 600: Proc(600, 500, None, 10.0)}
    STALE = {10: Proc(10, 1, None, 1.0), 20: Proc(20, 10, None, 2.0), 30: Proc(30, 20, None, 3.0),
             500: Proc(500, 30, None, 9.0), 600: Proc(600, 500, None, 10.0), 700: Proc(700, 500, None, 4.0)}

    def v1_kill_tree(self, snapshot):
        """The unmodified V1 aisef.clients.base._kill_tree_win32 on a snapshot (Win32 mocked; walk bounded)."""
        import aisef.clients.base as base
        import aisef.harness.process_owner as po
        children = {}
        for p in snapshot.values():
            children.setdefault(p.ppid, []).append(p.pid)

        class Bounded(dict):
            calls = 0

            def get(self, k, d=None):
                Bounded.calls += 1
                if Bounded.calls > 10_000:
                    raise RuntimeError("walk did not terminate (10 000 lookups)")
                return super().get(k, d)
        killed = []

        class K32:
            def __init__(self, *a, **k):
                self.OpenProcess = mock.Mock(side_effect=lambda acc, inh, pid: pid)
                self.TerminateProcess = mock.Mock(side_effect=lambda h, c: killed.append(h))
                self.CloseHandle = mock.Mock()
        with mock.patch.object(sys, "platform", "win32"), mock.patch("ctypes.WinDLL", K32, create=True), \
                mock.patch.object(po, "_snapshot_win32", lambda: Bounded(children)):
            try:
                base._kill_tree_win32(500)
            except RuntimeError as e:
                return str(e)
        return sorted(killed)

    def test_WIN_PID_1_a_stale_parent_cycle_terminates_bounded_and_targets_nothing_unowned(self):
        self.assertEqual(self.v1_kill_tree(self.REUSED), "walk did not terminate (10 000 lookups)")  # red: V1
        self.assertEqual(pr.descendants(self.REUSED, 500), [600])  # SHELL->500 is stale: 500 is younger than SHELL
        self.assertEqual(pr.targets(self.REUSED, members=[500, 600]), [500, 600])
        big = {n: Proc(n, (n + 1) % 5000, None, None) for n in range(5000)}  # one long cycle, no times known
        self.assertEqual(len(pr.descendants(big, 0)), 4999)

    def test_WIN_PID_2_a_stale_parent_without_a_cycle_never_selects_the_unrelated_process(self):
        self.assertIn(700, self.v1_kill_tree(self.STALE))  # red: V1 would TerminateProcess the unrelated 700
        self.assertEqual(pr.descendants(self.STALE, 500), [600])
        self.assertNotIn(700, pr.targets(self.STALE, members=[500, 600]))
        self.assertEqual(pr.targets(self.STALE, members=[600, 999]), [600])  # a member that is gone is not signalled

    def test_the_walk_keeps_true_edges_and_self_parents_and_unknown_times(self):
        table = {1: Proc(1, 1, None, None), 2: Proc(2, 1, None, None), 3: Proc(3, 2, None, 5.0),
                 4: Proc(4, 3, None, 4.0), 5: Proc(5, 42, None, None)}
        self.assertEqual(pr.descendants(table, 1), [2, 3])  # 4 is older than its "parent" 3: stale, dropped
        self.assertEqual(pr.descendants(table, 3), [])
        self.assertEqual(pr.descendants(table, 99), [])

    def test_the_walk_and_the_targets_are_in_pid_order(self):
        table = {1: Proc(1, 0, None, None), 5: Proc(5, 1, None, None), 2: Proc(2, 1, None, None),
                 9: Proc(9, 2, None, None), 3: Proc(3, 5, None, None)}
        self.assertEqual(pr.descendants(table, 1), [2, 3, 5, 9])
        self.assertEqual(pr.targets(table, members=[9, 5, 3]), [3, 5, 9])

    def test_the_ps_reader_skips_zombies_and_short_lines_and_a_failed_ps_is_not_an_empty_table(self):
        out = b"   10     1    10 Ss   /bin/zsh -l\n   11    10    10 Z    (python)\n   12    10\n" \
              b"   13    10    10 R\n   14    10    14 S    bad\xff name\n"
        real = subprocess.run

        def answered(output=None, code=0):  # the same call, answered by a process that prints `output`
            src = f"import sys; sys.stdout.buffer.write({output!r}); sys.exit({code})"
            return lambda argv, **kw: real([sys.executable, "-c", src], **kw)
        with mock.patch.object(pr.subprocess, "run", answered(out)):
            table = pr._ps_table()
        self.assertEqual(sorted(table), [10, 13, 14])
        self.assertEqual(table[10], Proc(10, 1, 10, None, "/bin/zsh -l"))
        self.assertEqual(table[13].command, "")
        self.assertEqual(table[14], Proc(14, 10, 14, None, "bad\ufffd name"))  # not UTF-8: still measured
        with mock.patch.object(pr.subprocess, "run", answered(b"", 1)), self.assertRaises(subprocess.CalledProcessError):
            pr._ps_table()  # a failed measurement is an error, never an empty range

    def test_the_process_table_reads_this_process(self):
        if not POSIX:
            self.skipTest("POSIX process table")
        me = pr.process_table()[os.getpid()]
        self.assertEqual((me.pid, me.ppid, me.group), (os.getpid(), os.getppid(), os.getpgrp()))
        self.assertIn("python", me.command.lower())



if __name__ == "__main__":
    unittest.main()
