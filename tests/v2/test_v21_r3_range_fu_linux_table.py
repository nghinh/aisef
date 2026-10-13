"""B-03 round 3, WP range-fu — `process_range._linux_table` is not broken by one process's name
(docs/v2.1/decisions/B03-R3-range.md, section 11).

The same hazard as the `ps` reader's, on the Linux path: one process anywhere on the host whose name is not valid
UTF-8 (`prctl(PR_SET_NAME)`, or an executable file with such a name) made `/proc/<pid>/stat` fail to decode, and that
`UnicodeDecodeError` — not an `OSError`, so not what the reader skips — ended every `ProcessRange` operation on the
host. Measured for real in the Linux guest (Python 3.14.8): see the decision doc.

The requirement: the table lists every live process, with its name decoded with replacement (the row's own fields
are ASCII); a process that exits while the table is read, a zombie and a dead task are not listed; the table is read
from `/proc`.

The `/proc` of these tests is a directory the test writes (`os.scandir` is the one thing patched, and only for the
call). `RealLinux` is the same requirement on the host's own `/proc`, on Linux only.
"""

import ctypes
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

from aisef2.runtime import process_range as pr  # noqa: E402
from aisef2.runtime.process_range import Proc  # noqa: E402


def stat_file(pid: int, comm: bytes = b"proc", state: str = "S", ppid: int = 1, pgrp: int | None = None,
              start: int = 500) -> bytes:
    """/proc/<pid>/stat: `pid (comm) state ppid pgrp ...`, 52 fields in all, start time the 22nd (proc(5))."""
    rest = [state, ppid, pid if pgrp is None else pgrp, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 20, 0, 1, 0, start,
            4096, 100, 18446744073709551615]
    return f"{pid} (".encode() + comm + b") " + " ".join(map(str, rest)).encode() + b"\n"


class ProcDir:
    """A directory laid out as /proc is: one directory per pid with `stat` and `cmdline`, and names that are no pid."""

    def __init__(self, test: unittest.TestCase) -> None:
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.names: list[str] = []

    def add(self, name: str, stat: bytes | None = None, cmdline: bytes | None = None) -> None:
        """An entry; `stat` None: the entry is listed but its files are gone (the process exited under the reader)."""
        self.names.append(name)
        if stat is not None:
            d = self.root / name
            d.mkdir()
            (d / "stat").write_bytes(stat)
            (d / "cmdline").write_bytes(b"" if cmdline is None else cmdline)

    def table(self) -> dict[int, Proc]:
        asked = []

        def scandir(path):
            asked.append(path)
            return iter([types.SimpleNamespace(name=n, path=str(self.root / n)) for n in self.names])
        with mock.patch.object(pr.os, "scandir", scandir):
            got = pr._linux_table()
        assert asked == ["/proc"], asked  # the table is read from /proc and from nowhere else
        return got


class LinuxTable(unittest.TestCase):
    def setUp(self) -> None:
        self.proc = ProcDir(self)

    def test_a_row_has_its_pid_parent_group_start_and_command(self):
        self.proc.add("10", stat_file(10, b"python3", ppid=1, pgrp=10, start=500), b"python3\0-m\0unittest\0")
        self.assertEqual(self.proc.table(), {10: Proc(10, 1, 10, 500.0, "python3 -m unittest")})

    def test_a_process_name_that_is_not_utf8_does_not_end_the_table(self):
        # the name is a command's own; a closing parenthesis and spaces in it do not move the fields after it
        self.proc.add("20", stat_file(20, b"\xff\xfe) (a b", state="R", ppid=10, pgrp=10, start=700), b"x\0")
        self.proc.add("10", stat_file(10, b"init", ppid=0, pgrp=10, start=100), b"/sbin/init\0")
        table = self.proc.table()
        self.assertEqual(sorted(table), [10, 20])
        self.assertEqual(table[20], Proc(20, 10, 10, 700.0, "x"))
        self.assertEqual(table[10], Proc(10, 0, 10, 100.0, "/sbin/init"))

    def test_a_command_line_that_is_not_utf8_is_replaced_not_fatal(self):
        self.proc.add("30", stat_file(30), b"tool\0bad\xff\0")
        self.assertEqual(self.proc.table()[30].command, "tool bad" + chr(0xFFFD))

    def test_a_zombie_and_a_dead_task_are_not_listed(self):
        self.proc.add("10", stat_file(10, state="S"), b"live\0")
        self.proc.add("11", stat_file(11, state="Z"), b"")
        self.proc.add("12", stat_file(12, state="X"), b"")
        self.proc.add("13", stat_file(13, state="D"), b"uninterruptible\0")
        self.assertEqual(sorted(self.proc.table()), [10, 13])

    def test_a_process_that_exited_under_the_reader_and_names_that_are_no_pid_are_skipped(self):
        self.proc.add("10", stat_file(10), b"live\0")
        self.proc.add("40", None)           # listed, files gone: ENOENT while read
        self.proc.add("self", stat_file(1))  # not a pid
        self.proc.add("sys", stat_file(2))
        self.assertEqual(sorted(self.proc.table()), [10])

    def test_a_kernel_thread_has_an_empty_command(self):
        self.proc.add("2", stat_file(2, b"kthreadd", ppid=0, pgrp=0), b"")
        self.assertEqual(self.proc.table(), {2: Proc(2, 0, 0, 500.0, "")})


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux /proc, prctl(PR_SET_NAME)")
class RealLinux(unittest.TestCase):
    def test_this_process_with_a_name_that_is_not_utf8_is_in_the_table(self):
        """The real /proc, the real kernel: this process names itself with bytes that are not UTF-8 (restored at the
        end) and reads the table. The call is on the main thread, whose name is the process's name."""
        libc = ctypes.CDLL(None, use_errno=True)
        before = pathlib.Path("/proc/self/comm").read_bytes().rstrip(b"\n")
        if libc.prctl(15, b"\xff\xfeab", 0, 0, 0) != 0:   # PR_SET_NAME
            self.skipTest("prctl(PR_SET_NAME) is refused here")
        try:
            self.assertEqual(pathlib.Path("/proc/self/comm").read_bytes(), b"\xff\xfeab\n")
            me = pr.process_table()[os.getpid()]
        finally:
            libc.prctl(15, before, 0, 0, 0)
        self.assertEqual((me.pid, me.ppid, me.group), (os.getpid(), os.getppid(), os.getpgrp()))
        self.assertIn("python", me.command.lower())


if __name__ == "__main__":
    unittest.main()
