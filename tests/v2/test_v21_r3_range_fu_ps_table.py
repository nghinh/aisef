"""B-03 round 3, WP range-fu — `process_range._ps_table` reads the rows `ps` prints, at the line feed only
(docs/v2.1/decisions/B03-R3-range.md, section 11).

The requirement, from what a real macOS `ps` does (measured; the evidence is in the decision doc):

1. A ROW IS A LINE. `ps` ends a row with a line feed and escapes the line feed inside a command (`\\012`), but prints
   U+2028 and U+2029 raw (in a UTF-8 locale). A command line holding one of them — or any character `str.splitlines()`
   or a text-mode read treats as a break: U+0085, VT, FF, FS, GS, RS, CR — is ONE row, with the whole command, and
   nothing after the character is a row of its own (it used to raise, or be dropped, or — when it looked like a row —
   become a process that is not there).
2. A LINE THAT IS NOT A ROW IS AN ERROR, TYPED AND NAMED: `ProcessTableError`, naming the first 80 characters of the
   line; never skipped (a skipped row is a process the table cannot see) and never an opaque `ValueError`.
3. As before: a zombie is not listed; a row with only pid, ppid, pgid and stat has an empty command; bytes that are not
   UTF-8 are replaced; a failed `ps` is an error and not an empty table.

Every character is built with `chr()`: no source line of this file, and no command line of a process that runs it,
holds one, so this file cannot itself break the table of a host it runs on.
"""

import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.runtime import process_range as pr  # noqa: E402
from aisef2.runtime.process_range import Proc  # noqa: E402
from aisef2.runtime.story_scope import Residual  # noqa: E402

PS_ARGV = ["ps", "-A", "-o", "pid=,ppid=,pgid=,stat=,command="]
FAKE = 4_000_000  # above any pid a host hands out (macOS: 99999): a row that names it is a row that was made up
#: every character that `str.splitlines()`, a text-mode read (universal newlines) or `str.split()` treats as a break
#: or as a separator, and that a command line can hold
SEPARATORS = {"NEL": 0x85, "LS": 0x2028, "PS": 0x2029, "VT": 0x0B, "FF": 0x0C, "FS": 0x1C, "GS": 0x1D, "RS": 0x1E,
              "CR": 0x0D, "US": 0x1F, "TAB": 0x09, "NBSP": 0xA0, "IDEOGRAPHIC SPACE": 0x3000}
#: what can follow the character in a command line (the whole command is `PREFIX + char + tail`, or the tail alone)
TAILS = {"words": "alpha beta gamma delta", "row-shaped": f"{FAKE} 1 {FAKE} S fabricated", "short": "end",
         "last": "", "first": None}


def row(pid, ppid, pgid, stat, command=""):
    """One line as `ps` pads it: right-aligned numbers, the stat left-aligned, then the command."""
    return f"{pid:5d} {ppid:5d} {pgid:5d} {stat:<4}{' ' if command else ''}{command}"


def answered(output: bytes, code: int = 0, asked=None):
    """`subprocess.run` as `process_range` uses it, answered by a real child process that prints `output` and exits
    `code` — with the caller's own keyword arguments, so capture and `check` are the real ones, and a bytes read is a
    bytes read. A command other than the one the table is read from is not answered (the child exits 2)."""
    real = subprocess.run

    def run(argv, **kw):
        if asked is not None:
            asked.append(list(argv))
        if list(argv) == PS_ARGV:
            src = f"import sys; sys.stdout.buffer.write({output!r}); sys.exit({code})"
        else:
            src = "import sys; sys.exit(2)"
        return real([sys.executable, "-S", "-c", src], **kw)
    return run


def table_of(output: bytes, code: int = 0, asked=None):
    with mock.patch.object(pr.subprocess, "run", answered(output, code, asked)):
        return pr._ps_table()


def lines(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


class RowIsALine(unittest.TestCase):
    def test_a_command_holding_a_separator_is_one_row_with_the_whole_command(self):
        # one output, one row per (character, what follows it); every row must come back whole and alone
        expected, rows, pid = {}, [row(1, 0, 1, "Ss", "/sbin/launchd")], 1000
        for code in SEPARATORS.values():
            for tail in TAILS.values():
                ch = chr(code)
                command = ch + "alpha beta gamma delta" if tail is None else f"/bin/zsh -c x{ch}{tail}"
                pid += 1
                expected[pid] = Proc(pid, 1, pid, None, command)
                rows.append(row(pid, 1, pid, "S", command))
        rows.append(row(2, 1, 2, "Ss", "/usr/sbin/after-the-last-one"))
        table = table_of(lines(*rows))
        self.assertNotIn(FAKE, table, "a row that was made up out of the tail of a command line")
        self.assertEqual(sorted(set(table) - {1, 2}), sorted(expected))
        for pid, want in expected.items():
            with self.subTest(command=want.command):
                self.assertEqual(table[pid], want)
        self.assertEqual(table[1], Proc(1, 0, 1, None, "/sbin/launchd"))
        self.assertEqual(table[2], Proc(2, 1, 2, None, "/usr/sbin/after-the-last-one"))

    def test_a_carriage_return_is_not_turned_into_a_line_feed_by_a_text_mode_read(self):
        # the bytes of the command hold CR, and CR LF is never a row break either: only the line feed ends a row
        cr = chr(0x0D)
        table = table_of(lines(row(10, 1, 10, "S", f"a{cr}b"), row(11, 1, 11, "S", f"c{cr}")))
        self.assertEqual(table, {10: Proc(10, 1, 10, None, f"a{cr}b"), 11: Proc(11, 1, 11, None, f"c{cr}")})

    def test_the_escaped_line_feed_stays_as_ps_printed_it(self):
        command = "/bin/zsh -c printf 'a" + "\\012" + "b'"  # backslash 0 1 2: what macOS prints for a line feed
        self.assertEqual(table_of(lines(row(10, 1, 10, "S", command)))[10].command, command)

    def test_bytes_that_are_not_utf8_are_replaced_beside_a_separator(self):
        out = row(10, 1, 10, "S", "bad").encode() + b"\xff " + chr(0x2028).encode() + b" alpha beta gamma\n"
        self.assertEqual(table_of(out)[10].command, "bad" + chr(0xFFFD) + " " + chr(0x2028) + " alpha beta gamma")

    def test_leading_trailing_and_blank_lines_are_no_rows(self):
        want = {10: Proc(10, 1, 10, None, "/bin/a"), 11: Proc(11, 10, 10, None, "/bin/b")}
        good = [row(10, 1, 10, "S", "/bin/a"), row(11, 10, 10, "S", "/bin/b")]
        for name, out in {"final newline": lines(*good), "no final newline": "\n".join(good).encode(),
                          "blank lines around": ("\n\n" + "\n".join(good) + "\n\n\n").encode(),
                          "a blank line between": (good[0] + "\n\n" + good[1] + "\n").encode(),
                          "a line of spaces": (good[0] + "\n      \n" + good[1] + "\n").encode()}.items():
            with self.subTest(name):
                self.assertEqual(table_of(out), want)
        self.assertEqual(table_of(b""), {})  # no process listed and no error: ps itself answered nothing


class RowShape(unittest.TestCase):
    def test_a_zombie_is_not_listed_and_a_row_without_a_command_has_an_empty_one(self):
        table = table_of(lines(row(10, 1, 10, "Ss", "/bin/zsh -l"), row(11, 10, 10, "Z", "(python)"),
                                row(12, 10, 10, "Z+", "<defunct>"), "   13    10    10 R",
                                "   14    10    14 R+    ", row(15, 10, 15, "S<s", "  indented  ")))
        self.assertEqual(sorted(table), [10, 13, 14, 15])
        self.assertEqual(table[10], Proc(10, 1, 10, None, "/bin/zsh -l"))
        self.assertEqual(table[13], Proc(13, 10, 10, None, ""))
        self.assertEqual(table[14], Proc(14, 10, 14, None, ""))
        self.assertEqual(table[15], Proc(15, 10, 15, None, "indented  "))  # as printed, after the column's padding

    def test_the_command_is_asked_for_once_with_these_columns(self):
        asked = []
        table_of(lines(row(10, 1, 10, "S", "x")), asked=asked)
        self.assertEqual(asked, [PS_ARGV])

    def test_a_failed_ps_is_an_error_and_never_an_empty_or_partial_table(self):
        with self.assertRaises(subprocess.CalledProcessError):
            table_of(lines(row(10, 1, 10, "S", "x")), code=1)


class NotARow(unittest.TestCase):
    MALFORMED = {
        "prose": "this is not a process row at all",
        "a tail of a command line": "alpha beta gamma delta",
        "pid and ppid only": "   12    10",
        "pid, ppid and pgid only": "   12    10    10",
        "a word for the pid": "abc 1 2 S x",
        "a word for the ppid": "1 two 3 S x",
        "a word for the pgid": "1 2 x S cmd",
        "a signed pid": "+5 1 5 S x",
        "a pid in other digits": chr(0x663) + " 1 3 S x",
        "an underscore in the pid": "1_0 1 10 S x",
        "a tab between the columns": "10\t1\t10 S x",
        "a separator before the pid": chr(0x2028) + " 10 1 10 S x",
    }

    def test_a_line_that_is_not_a_row_is_a_typed_error_naming_the_line(self):
        for name, bad in self.MALFORMED.items():
            with self.subTest(name):
                out = lines(row(10, 1, 10, "S", "/bin/a"), bad, row(11, 10, 10, "S", "/bin/b"))
                with self.assertRaises(pr.ProcessTableError) as caught:
                    table_of(out)
                e = caught.exception
                self.assertIs(type(e), pr.ProcessTableError)
                self.assertIn(repr(bad[:80]), str(e))
                # not what a caller reads as "the range was not empty" or "the tool could not start", and not opaque
                self.assertNotIsInstance(e, (ValueError, Residual, pr.RangeError))

    def test_the_message_says_that_ps_printed_a_line_that_is_not_a_process_row(self):
        # an operator reads this in a release record: which program, and what was wrong with what it printed
        with self.assertRaises(pr.ProcessTableError) as caught:
            table_of(lines("   12    10"))  # a line with no letters of its own: the words are the message's
        self.assertRegex(str(caught.exception), r"\bps\b.*not a process row")

    def test_only_the_first_80_characters_of_the_line_are_named(self):
        bad = "not-a-row " + "0123456789" * 30
        with self.assertRaises(pr.ProcessTableError) as caught:
            table_of(lines(bad))
        self.assertIn(repr(bad[:80]), str(caught.exception))
        self.assertNotIn(bad[:81], str(caught.exception))
        self.assertLess(len(str(caught.exception)), 200)

    def test_the_name_shows_a_separator_instead_of_printing_it(self):
        bad = "continuation" + chr(0x2028) + "of a command"
        with self.assertRaises(pr.ProcessTableError) as caught:
            table_of(lines(bad))
        self.assertNotIn(chr(0x2028), str(caught.exception))
        self.assertIn(repr(bad), str(caught.exception))

    def test_no_row_is_returned_when_one_line_is_not_one(self):
        # fail closed: the rows before the bad line are not handed out as if they were the whole table
        with self.assertRaises(pr.ProcessTableError):
            table_of(lines(row(10, 1, 10, "S", "/bin/a"), "garbage", row(11, 1, 11, "S", "/bin/b")))


@unittest.skipUnless(sys.platform == "darwin", "the `ps` of macOS: the table that is read from `ps`")
class RealPs(unittest.TestCase):
    def test_the_row_of_a_real_process_whose_command_line_holds_separators(self):
        """A real `/bin/sh` that holds U+2028, U+2029 and U+0085 in its command line, and `ps` in a UTF-8 locale (where
        macOS prints U+2028 and U+2029 raw). The child reports that it runs and waits for its stdin to close: no sleep,
        no signal, and it ends by itself."""
        text = (f"RANGEFU-A{chr(0x2028)}alpha beta gamma delta{chr(0x2029)}{FAKE} 1 {FAKE} S fabricated"
                f"{chr(0x85)}RANGEFU-B")
        child = subprocess.Popen(["/bin/sh", "-c", f"echo ready; read x; : '{text}'"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline(), b"ready\n")
            with mock.patch.dict(os.environ, {"LC_ALL": "en_US.UTF-8"}):
                printed = subprocess.run(["ps", "-p", str(child.pid), "-o", "command="], capture_output=True,
                                         check=True).stdout.decode("utf-8", "replace").rstrip("\n")
                table = pr.process_table()
        finally:
            child.stdin.close()
            child.wait()
            child.stdout.close()
        self.assertIn(child.pid, table)
        self.assertEqual(table[child.pid].command, printed)  # the whole command, as ps printed it
        self.assertTrue(printed.startswith("/bin/sh -c echo ready"))
        self.assertTrue(printed.endswith("RANGEFU-B'"))  # the closing quote of the shell text
        self.assertNotIn(FAKE, table)


if __name__ == "__main__":
    unittest.main()
