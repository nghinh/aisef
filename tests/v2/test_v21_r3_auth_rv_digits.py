"""V2.1 (B-03, round 3, WP auth, independent review): a number in a row is a number a host can print.

Every reader of `cleanup_authority` turns the digit runs of a row into an `int`. A run of more than 4300 digits makes
`int()` raise ValueError (CPython 3.11+), which is not the typed `TableUnreadable` the runner stops on
(HOST_TABLE_UNREADABLE): it would be a RUNNER_EXCEPTION out of the reader, the defect batch T23a found. No host prints a
pid of more than ten digits (pid_t is 32 bits; Windows' is a DWORD, 4294967295), so a longer run is a line that is no
row — refused with the same typed error as any other. The widest pid of any host is still a row.

Hermetic: the readers are fed the bytes a tool printed through the module's own seams (nothing is started)."""

from __future__ import annotations

import base64
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))

import cleanup_authority as ca  # noqa: E402

WIDEST = 4294967295                       # a Windows DWORD: ten digits
STARTED = "Tue Oct 13 09:30:00 2026"
TOO_MANY = ("9" * 11, "9" * 4301, "0" * 4301 + "1")


def ps(pid=7, ppid=1, pgid=7):
    return f"{pid} {ppid} {pgid} {STARTED}     /bin/x\n".encode()


def lsof(pid):
    return f"p{pid}\0\nfcwd\0n/work\0\n".encode()


def win(pid=7, ppid=1, born=5):
    return f"{pid}|{ppid}|{born}|{base64.b64encode(b'a').decode()}\r\n".encode()


class DigitsAreBounded(unittest.TestCase):
    def test_a_number_longer_than_any_pid_is_a_line_that_is_no_row_not_a_value_error(self):
        for tool, read, make in (("ps", ca._ps_rows, ps), ("ps -E", ca._env_rows, lambda p: f"{p} /bin/x\n".encode()),
                                 ("lsof", ca._lsof_cwds, lsof), ("powershell", ca._win_rows, win)):
            for digits in TOO_MANY:
                with self.subTest(tool=tool, digits=len(digits)):
                    with self.assertRaises(ca.TableUnreadable) as cm:
                        read(make(digits))
                    self.assertIsInstance(cm.exception, OSError)
                    self.assertNotIsInstance(cm.exception, ValueError)

    def test_every_number_of_a_row_is_bounded_not_only_the_pid(self):
        for digits in TOO_MANY:
            for what, raw in (("ppid", ps(ppid=digits)), ("pgid", ps(pgid=digits))):
                with self.subTest(column=what, digits=len(digits)):
                    self.assertRaises(ca.TableUnreadable, ca._ps_rows, raw)
            with self.subTest(column="windows ppid", digits=len(digits)):
                self.assertRaises(ca.TableUnreadable, ca._win_rows, win(ppid=digits))
        for digits in ("9" * 13, "9" * 4301):        # seconds since 1970: ten digits until the year 2286
            with self.subTest(column="windows born", digits=len(digits)):
                self.assertRaises(ca.TableUnreadable, ca._win_rows, win(born=digits))

    def test_the_widest_pid_of_any_host_is_a_row_in_every_reader(self):
        self.assertEqual(sorted(ca._ps_rows(ps(WIDEST, WIDEST, WIDEST))), [WIDEST])
        self.assertEqual(ca._ps_rows(ps(WIDEST, WIDEST, WIDEST))[WIDEST].ppid, WIDEST)
        self.assertEqual(sorted(ca._env_rows(f"{WIDEST} /bin/x\n".encode())), [WIDEST])
        self.assertEqual(ca._lsof_cwds(lsof(WIDEST)), {WIDEST: "/work"})
        rows = ca._win_rows(win(WIDEST, WIDEST, 4102444799))
        self.assertEqual((rows[WIDEST].ppid, rows[WIDEST].born), (WIDEST, 4102444799.0))

    def test_the_bound_is_on_the_row_not_on_the_table(self):
        raw = ps(100, 1, 100) + ps(2147483647, 100, 100) + ps(WIDEST, 100, 100)
        self.assertEqual(sorted(ca._ps_rows(raw)), [100, 2147483647, WIDEST])


if __name__ == "__main__":
    unittest.main()
