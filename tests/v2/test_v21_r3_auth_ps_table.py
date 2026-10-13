"""V2.1 (B-03, round 3, WP auth): the mutation runner's host table is not forgeable by a command line.

`cleanup_authority._read()` is the root of every ownership proof of the runner (`owned`, `prove_member`,
`signal_owned`, `establish`, ...). It read `ps` with `str.splitlines()` and skipped every line that was no row, so a
command line holding U+2028 followed by row-shaped text put a row into the table that no process had: a process born
BEFORE the boundary became the runner's and was signalled. A command line is implementation output
(INV-MUTATION-AUTHORITY: it may never expand destructive authority).

The requirements pinned here, through the module's own entry points (`host_table`, `establish`, `owned`,
`prove_member`, `signal_owned`) with `subprocess.Popen` returning the bytes `ps` printed:

* a row ends at LF and nowhere else; the command is whatever `ps` printed, separators and Unicode spaces included;
* a line that is no row, a pid listed twice, a failed `ps`, a table without its reader: `TableUnreadable` (an
  OSError, which the runner already stops on) — never a partial table, never a skipped line;
* `ps` runs with LC_TIME=C (its `lstart` is printed in the locale's own words otherwise);
* whatever the command lines hold, a process born before the boundary is never owned, proved or signalled.

The last class runs the real `ps` of the host (a posix host; hermetic: two children that end when their stdin is
closed)."""

from __future__ import annotations

import contextlib
import os
import pathlib
import subprocess
import sys
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))

import cleanup_authority as ca  # noqa: E402

READER = 31337
RUNNER = os.getpid()
EARLY, LATE = "Sun Oct 11 09:30:00 2026", "Sun Oct 11 09:30:10 2026"
FORGED_DATE = "Tue Oct 13 23:59:59 2099"


def mktime(y, mo, d, h, mi, s):
    return time.mktime((y, mo, d, h, mi, s, 0, 0, -1))


def row(pid, ppid, pgid, started=EARLY, command="/usr/bin/x", pad=5):
    """One row as macOS prints it (the `lstart` column is padded with five spaces, procps with one)."""
    return f"{pid:>5} {ppid:>5} {pgid:>5} {started}{' ' * pad}{command}\n"


def reader_row(command="ps -A -o pid=,ppid=,pgid=,lstart=,command="):
    return row(READER, RUNNER, READER, LATE, command)


class FakePopen:
    """What a reader of `ps` gets back from a binary-mode `Popen`: the bytes the tool printed, a return code, a pid."""
    calls: list = []

    def __init__(self, argv, *args, raw=b"", returncode=0, pid=READER, **kwargs):
        self.argv, self.kwargs, self.raw, self.returncode, self.pid = argv, kwargs, raw, returncode, pid
        type(self).calls.append((argv, kwargs))

    def communicate(self, *_a, **_k):
        return self.raw, None


@contextlib.contextmanager
def reading(raw, returncode=0, pid=READER, posix=True):
    """A context in which the module's `ps` (or PowerShell) prints `raw`, as a binary-mode Popen returns it."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    FakePopen.calls = []

    def popen(argv, *a, **k):
        return FakePopen(argv, *a, raw=raw, returncode=returncode, pid=pid, **k)
    with mock.patch.object(ca, "POSIX", posix), mock.patch.object(ca.subprocess, "Popen", popen):
        yield


def table_of(raw, **kw):
    with reading(raw, **kw):
        return ca._read()


SEPARATORS = {"U+2028": " ", "U+2029": " ", "U+0085": "\u0085", "VT": "\x0b", "FF": "\x0c", "FS": "\x1c",
              "GS": "\x1d", "RS": "\x1e", "CR": "\r", "NBSP": " ", "U+3000": "　", "TAB": "\t", "DEL": "\x7f"}


class RowIsALine(unittest.TestCase):
    def test_the_rows_are_read_with_their_pid_parent_group_start_and_command(self):
        out, reader = table_of(row(100, 1, 100, EARLY, "/usr/bin/sleep 60") + reader_row())
        self.assertEqual((sorted(out), reader), ([100, READER], READER))
        self.assertEqual(out[100], ca.Host(100, 1, 100, mktime(2026, 10, 11, 9, 30, 0), "/usr/bin/sleep 60"))
        self.assertEqual((out[READER].ppid, out[READER].pgid, out[READER].born),
                         (RUNNER, READER, mktime(2026, 10, 11, 9, 30, 10)))

    def test_the_day_below_ten_is_padded_with_spaces_and_means_that_day(self):
        out, _ = table_of(row(100, 1, 100, "Tue Oct  6 05:58:42 2026", "/x") + reader_row())
        self.assertEqual(out[100].born, mktime(2026, 10, 6, 5, 58, 42))
        out, _ = table_of(row(100, 1, 100, "Thu Oct 29 23:59:59 2026", "/x") + reader_row())
        self.assertEqual(out[100].born, mktime(2026, 10, 29, 23, 59, 59))

    def test_the_column_padding_of_macos_and_of_procps_are_both_rows_and_neither_is_the_command(self):
        for pad in (1, 5, 7):
            with self.subTest(pad=pad):
                out, _ = table_of(row(100, 1, 100, EARLY, "/bin/y -c z", pad=pad) + reader_row())
                self.assertEqual(out[100].command, "/bin/y -c z")

    def test_a_row_without_a_command_has_an_empty_one(self):
        for tail in ("", " ", "     "):
            with self.subTest(tail=tail):
                out, _ = table_of(f"  100     1   100 {EARLY}{tail}\n" + reader_row())
                self.assertEqual(out[100].command, "")

    def test_a_command_holding_a_separator_is_one_row_with_the_whole_command(self):
        for name, sep in SEPARATORS.items():
            with self.subTest(sep=name):
                command = f"carrier{sep}{300} {RUNNER} 300 {FORGED_DATE} fabricated"
                out, _ = table_of(row(100, RUNNER, 100) + row(200, RUNNER, 200, LATE, command) + reader_row())
                self.assertEqual(sorted(out), [100, 200, READER])
                self.assertEqual(out[200].command, command)
                self.assertEqual(out[100], ca.Host(100, RUNNER, 100, mktime(2026, 10, 11, 9, 30, 0), "/usr/bin/x"))

    def test_the_separator_ends_nothing_even_at_the_end_or_the_start_of_the_command(self):
        for name, sep in SEPARATORS.items():
            for command in (sep + "tail", "head" + sep, sep, sep * 3):
                with self.subTest(sep=name, command=command):
                    out, _ = table_of(row(100, 1, 100, EARLY, command) + reader_row())
                    self.assertEqual(out[100].command, command)

    def test_a_command_that_starts_with_a_unicode_space_keeps_it(self):
        for space in (" ", " ", "　", " ", "\u0085", "﻿"):
            with self.subTest(space=hex(ord(space))):
                out, _ = table_of(row(100, 1, 100, EARLY, space + "/bin/z a") + reader_row())
                self.assertEqual(out[100].command, space + "/bin/z a")

    def test_bytes_that_are_not_utf8_are_replaced_and_end_nothing(self):
        raw = row(100, 1, 100).encode() + b"  200     1   200 " + EARLY.encode() + b"     a\xff\xfe\xc3\n" + \
            row(300, 1, 300).encode() + reader_row().encode()
        out, _ = table_of(raw)
        self.assertEqual(sorted(out), [100, 200, 300, READER])
        self.assertEqual(out[200].command, "a���")

    def test_a_carriage_return_is_data_never_a_line_end(self):
        raw = row(100, 1, 100, EARLY, "a\rb").encode() + reader_row().encode()
        out, _ = table_of(raw)
        self.assertEqual(out[100].command, "a\rb")
        out, _ = table_of(raw.replace(b"\n", b"\r\n"))   # a CR LF ended the line: the CR is the last byte of the command
        self.assertEqual(out[100].command, "a\rb\r")

    def test_blank_lines_and_the_end_of_the_output_are_no_rows(self):
        out, _ = table_of("\n" + row(100, 1, 100) + "   \n\n" + reader_row() + "\n")
        self.assertEqual(sorted(out), [100, READER])


class NotARow(unittest.TestCase):
    """A line that is not a row is a refusal of the whole reading: a skipped line is a process the table cannot see,
    a made-up row is one that is not there."""

    BAD = {
        "a continuation fragment": 'y.py"])\\012',
        "a continuation that reads as a date": "foo bar baz Sun Oct 11 09:30:00 2026 trailing text",
        "a pid that is not digits": f"12x     7    12 {EARLY}     c",
        "a parent that is not digits": f"   12     x    12 {EARLY}     c",
        "a group that is not digits": f"   12     7     y {EARLY}     c",
        "Arabic-Indic digits": f"١٢     7    12 {EARLY}     c",
        "a superscript digit": f"   ²     7    12 {EARLY}     c",
        "a negative pid": f"   -5     7    12 {EARLY}     c",
        "a header": "  PID  PPID  PGID STARTED                  COMMAND",
        "a date with a missing field": "   12     7    12 Sun Oct 11 2026     c",
        "a month that is no month": "   12     7    12 Sun Foo 11 09:30:00 2026     c",
        "a day that does not exist": "   12     7    12 Sun Feb 31 09:30:00 2026     c",
        "a clock that is no time": "   12     7    12 Sun Oct 11 25:61:00 2026     c",
        "a year of five digits": "   12     7    12 Sun Oct 11 09:30:00 20266     c",
        "a year the clock cannot hold": "   12     7    12 Mon Jan  1 00:00:00 0001     c",
        "text glued to the year": f"   12     7    12 {EARLY}x c",
        "a localised date": "   12     7    12 Di. 13 Okt. 08:03:59 2026     c",
        "only a separator": " ",
        "a lone carriage return": "\r",
        "text of an error": "ps: Unknown user",
    }

    def test_every_line_that_is_no_row_is_refused_with_a_typed_error(self):
        for name, bad in self.BAD.items():
            for where in ("first", "middle", "last"):
                with self.subTest(line=name, where=where):
                    rows = [row(100, 1, 100), bad + "\n", reader_row()]
                    order = {"first": [1, 0, 2], "middle": [0, 1, 2], "last": [0, 2, 1]}[where]
                    with self.assertRaises(ca.TableUnreadable) as cm:
                        table_of("".join(rows[i] for i in order))
                    self.assertIsInstance(cm.exception, OSError)
                    self.assertNotIsInstance(cm.exception, ValueError)
                    self.assertTrue(str(cm.exception).startswith("ps printed a line that is not a process row: "),
                                    str(cm.exception))   # what the operator reads under HOST_TABLE_UNREADABLE

    def test_the_error_names_the_line_cut_to_eighty_characters(self):
        bad = "x" * 200
        with self.assertRaises(ca.TableUnreadable) as cm:
            table_of(row(100, 1, 100) + bad + "\n" + reader_row())
        self.assertIn(repr("x" * 80), str(cm.exception))
        self.assertNotIn("x" * 81, str(cm.exception))

    def test_a_pid_listed_twice_is_refused_whichever_row_is_the_made_up_one(self):
        both = row(100, 1, 100) + row(100, RUNNER, 100, LATE, "fabricated") + reader_row()
        with self.assertRaises(ca.TableUnreadable) as cm:
            table_of(both)
        self.assertTrue(str(cm.exception).startswith("ps listed pid 100 twice: "), str(cm.exception))
        with self.assertRaises(ca.TableUnreadable):
            table_of(row(100, RUNNER, 100, LATE, "fabricated") + row(100, 1, 100) + reader_row())

    def test_the_error_is_an_oserror_so_the_runner_stops_instead_of_going_on(self):
        self.assertTrue(issubclass(ca.TableUnreadable, OSError))
        self.assertFalse(issubclass(ca.TableUnreadable, ValueError))

    def test_a_failed_ps_is_never_an_empty_or_a_partial_table(self):
        good = row(100, 1, 100) + reader_row()
        for name, raw, rc in (("exit 1, no output", "", 1), ("exit 1, a table", good, 1), ("exit 0, no output", "", 0),
                              ("exit 0, without itself", row(100, 1, 100), 0), ("exit 1, an error text", "ps: boom\n", 1)):
            with self.subTest(name):
                with self.assertRaises(ca.TableUnreadable) as cm:
                    table_of(raw, returncode=rc)
                self.assertIn("cannot be read", str(cm.exception))

    def test_the_failure_says_which_of_the_two_it_was(self):
        with self.assertRaises(ca.TableUnreadable) as cm:
            table_of(row(100, 1, 100), returncode=0)
        self.assertEqual(str(cm.exception), "ps -A did not list itself: the host table cannot be read")
        with self.assertRaises(ca.TableUnreadable) as cm:
            table_of(row(100, 1, 100) + reader_row(), returncode=3)
        self.assertEqual(str(cm.exception), "ps -A exited 3: the host table cannot be read")

    def test_establish_and_host_table_refuse_alike(self):
        for call in (ca.host_table, lambda: ca.establish("root")):
            with self.subTest(call=getattr(call, "__name__", "establish")), reading(row(100, 1, 100) + "junk\n" + reader_row()):
                self.assertRaises(ca.TableUnreadable, call)


class PsRunsInTheCLocaleForItsDates(unittest.TestCase):
    """macOS prints `lstart` in the locale's words (`Di. 13 Okt. 08:03:59 2026` under de_DE.UTF-8, measured): the
    table's date pattern is not, and every row was dropped. LC_TIME is pinned; LC_ALL, which would override it, is
    handed to LC_CTYPE (how the bytes of a command are printed)."""

    LOCALE = ("LANG", "LC_ALL", "LC_CTYPE", "LC_TIME")

    def env_of_the_call(self, environ):
        """The environment `ps` is started with when this process's locale variables are exactly `environ`."""
        with mock.patch.dict(os.environ, environ):
            for name in self.LOCALE:
                if name not in environ:
                    os.environ.pop(name, None)
            with reading(row(100, 1, 100) + reader_row()):
                ca._read()
        (argv, kwargs), = FakePopen.calls
        self.assertEqual(argv[0], "ps")
        return kwargs["env"]

    def test_the_time_words_are_pinned(self):
        env = self.env_of_the_call({"LANG": "de_DE.UTF-8", "PATH": "/p"})
        self.assertEqual(env["LC_TIME"], "C")
        self.assertEqual((env["LANG"], env["PATH"]), ("de_DE.UTF-8", "/p"))
        self.assertNotIn("LC_ALL", env)
        self.assertNotIn("LC_CTYPE", env)

    def test_a_time_locale_of_the_user_is_overridden(self):
        self.assertEqual(self.env_of_the_call({"LC_TIME": "fr_FR.UTF-8"})["LC_TIME"], "C")

    def test_lc_all_would_override_it_so_it_moves_to_the_category_that_prints_the_command(self):
        env = self.env_of_the_call({"LC_ALL": "de_DE.UTF-8", "LC_CTYPE": "C"})
        self.assertNotIn("LC_ALL", env)
        self.assertEqual((env["LC_CTYPE"], env["LC_TIME"]), ("de_DE.UTF-8", "C"))

    def test_the_environment_of_this_process_is_not_changed(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "de_DE.UTF-8"}):
            before = dict(os.environ)
            with reading(row(100, 1, 100) + reader_row()):
                ca._read()
            self.assertEqual(dict(os.environ), before)


def forged(victim, runner=RUNNER, date=FORGED_DATE):
    """Text shaped like a row: the victim's pid, the runner as its parent, a start after every boundary."""
    return f"{victim} {runner} {victim} {date} fabricated-by-a-command-line"


class ACommandLineIsNeverAuthority(unittest.TestCase):
    """INV-MUTATION-AUTHORITY at the root: whatever the command lines hold, a process born before the boundary is
    never in `owned`, never provable by `prove_member`, never in the signalled list."""

    VICTIM, CARRIER, SIBLING = 400, 500, 600

    def host(self, carrier_command, victim_born=EARLY):
        return (row(1, 0, 1, EARLY, "/sbin/launchd") + row(self.VICTIM, RUNNER, self.VICTIM, victim_born, "/bin/earlier") +
                row(self.CARRIER, RUNNER, self.CARRIER, LATE, carrier_command) +
                row(self.SIBLING, self.CARRIER, self.CARRIER, LATE, "/bin/later") + reader_row())

    def prove_nothing_about_the_victim(self, raw):
        with reading(raw):
            boundary = ca.establish("root")
            table = ca.host_table()
        self.assertEqual(boundary.runner, RUNNER)
        self.assertEqual(boundary.since, mktime(2026, 10, 11, 9, 30, 10))
        self.assertEqual(sorted(table), [1, self.VICTIM, self.CARRIER, self.SIBLING, READER])
        self.assertEqual((table[self.VICTIM].ppid, table[self.VICTIM].command), (RUNNER, "/bin/earlier"))
        mine = ca.owned(boundary, table)
        self.assertNotIn(self.VICTIM, mine)
        self.assertEqual(sorted(mine), [self.CARRIER, self.SIBLING, READER])
        self.assertIsNone(ca.prove_member(boundary, self.VICTIM, self.VICTIM, table))
        self.assertIsNone(ca.prove_member(boundary, self.VICTIM, self.CARRIER, table))
        report = ca.signal_owned(boundary, pids=[self.VICTIM], groups=[self.VICTIM], dry_run=True, table=table)
        self.assertEqual(report.signalled, [])
        self.assertEqual(sorted((u["kind"], u["id"]) for u in report.unproven),
                         [("group", self.VICTIM), ("pid", self.VICTIM)])
        again = ca.signal_member(boundary, self.VICTIM, self.CARRIER, dry_run=True, table=table)
        self.assertEqual(again.signalled, [])
        return table

    def test_a_row_inside_a_command_line_adds_and_replaces_nothing_whatever_separates_it(self):
        for name, sep in SEPARATORS.items():
            with self.subTest(sep=name):
                carrier = f"carrier{sep}{forged(self.VICTIM)}"
                table = self.prove_nothing_about_the_victim(self.host(carrier))
                self.assertEqual(table[self.CARRIER].command, carrier)

    def test_the_forgery_may_follow_a_separator_on_either_side_or_stand_alone_in_the_command(self):
        for command in (forged(self.VICTIM), f" {forged(self.VICTIM)} ", f"a  {forged(self.VICTIM)}",
                        f"{forged(self.VICTIM)} {forged(self.SIBLING)}",
                        f"x {self.CARRIER} 1 1 {LATE} ps {forged(self.VICTIM, date=LATE)}"):
            with self.subTest(command=command):
                self.prove_nothing_about_the_victim(self.host(command))

    def test_a_fabricated_row_for_a_pid_that_is_not_there_is_not_in_the_table(self):
        raw = self.host(f"x {forged(777)}")
        with reading(raw):
            table = ca.host_table()
        self.assertNotIn(777, table)

    def test_a_row_that_is_a_line_of_its_own_for_a_listed_pid_is_a_pid_listed_twice(self):
        """No `ps` measured prints a raw LF inside a command. Were one to, a row-shaped text for a pid that is listed
        could not be told from a real row by its shape; a process is listed once, and that is refused."""
        raw = self.host("carrier") + forged(self.VICTIM) + "\n"
        with reading(raw):
            self.assertRaises(ca.TableUnreadable, ca.host_table)

    def test_the_reader_s_own_row_cannot_be_forged_into_a_boundary(self):
        """`establish` dates the boundary by the reader's row: a command line naming the reader's pid with an early
        start must not move the line back."""
        carrier = f"x {forged(READER, date=EARLY)}"
        with reading(self.host(carrier)):
            boundary = ca.establish("root")
        self.assertEqual(boundary.since, mktime(2026, 10, 11, 9, 30, 10))


@unittest.skipUnless(ca.POSIX, "the POSIX `ps` reading")
class TheRealPs(unittest.TestCase):
    """The real `ps` of this host, two real children that end when their stdin is closed. On macOS, in a UTF-8
    locale, `ps` prints U+2028 raw: before the fix the victim became the runner's (on procps the separator is printed
    as `?`: this passes there for the better reason that there was nothing to forge)."""

    def start(self, *argv):
        code = "import sys; print('ready', flush=True); sys.stdin.read()"
        p = subprocess.Popen([sys.executable, "-c", code, *argv], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.addCleanup(self.end, p)
        self.assertEqual(p.stdout.readline(), b"ready\n")   # it has exec'd: `ps` shows its own argv, not its parent's
        return p

    @staticmethod
    def end(p):
        p.stdin.close()
        p.wait()
        p.stdout.close()

    def test_this_process_its_parent_and_the_reader_are_in_the_table(self):
        table, reader = ca._read()
        self.assertIn(os.getpid(), table)
        self.assertIn(reader, table)
        self.assertEqual(table[os.getpid()].ppid, os.getppid())
        self.assertGreaterEqual(len(table), 2)
        self.assertEqual(table[os.getpid()].pgid, os.getpgrp())
        self.assertLess(abs(table[reader].born - time.time()), 120)

    def test_a_locale_that_words_its_dates_is_still_a_table(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "de_DE.UTF-8"}):
            table = ca.host_table()
        self.assertIn(os.getpid(), table)

    def test_a_real_command_line_with_separators_and_a_row_forges_nothing(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "en_US.UTF-8"}):
            victim = self.start("a process of the host that is not the runner's")
            fake = forged(victim.pid, os.getpid(), "Tue Oct 13 23:59:59 2099")
            carrier = self.start(*(f"carrier{sep}{fake}" for sep in ("\u2028", "\u2029", "\u0085", "\x0b", "\x0c", "\r")))
            table = ca.host_table()
        real = table[victim.pid]
        self.assertEqual(real.ppid, os.getpid())
        self.assertLess(real.born, 2_000_000_000)   # the real start, not the one a command line wrote
        self.assertNotIn("fabricated", real.command)
        self.assertIn(carrier.pid, table)
        boundary = ca.Boundary(os.getpid(), real.born + 5.0, "root")   # established after the victim was born
        self.assertNotIn(victim.pid, ca.owned(boundary, table))
        report = ca.signal_owned(boundary, pids=[victim.pid], dry_run=True, table=table)
        self.assertEqual((report.signalled, [u["id"] for u in report.unproven]), ([], [victim.pid]))


if __name__ == "__main__":
    unittest.main()
