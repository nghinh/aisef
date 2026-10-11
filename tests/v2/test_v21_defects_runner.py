"""V2.1 (B-03, survivor audit of campaign 2): the cleanup authority's reading of the host table.

`ps -A -o pid=,ppid=,pgid=,lstart=,command=` prints a command that holds a newline over several lines. A continuation
line whose fields 3..7 happen to read as a date (`foo bar baz Sun Oct 11 09:30:00 2026 ...`) reached `int(f[0])` and
raised ValueError out of the reader — the runner stopped on a RUNNER_EXCEPTION/INFRA for any process of the host that
had a multi-line command (two kill_check runs of batch T23a). A line that is no row is no row; the table is what the
real rows say, and a table that does not list the reader itself is still refused."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))

import cleanup_authority as ca  # noqa: E402


class FakePs:
    pid = 31337
    returncode = 0

    def __init__(self, text: str, *_a, **_k) -> None:
        self.text = text

    def communicate(self, *_a, **_k):
        return self.text, None


def table_of(text: str, returncode: int = 0):
    class P(FakePs):
        pass
    P.returncode = returncode
    with mock.patch.object(ca, "POSIX", True), \
            mock.patch.object(ca.subprocess, "Popen", lambda *a, **k: P(text, *a, **k)):
        return ca._read()


ROWS = (" 100     1   100 Sun Oct 11 09:30:00 2026 /usr/bin/sleep 60\n"
        "31337   100 31337 Sun Oct 11 09:30:01 2026 ps -A -o pid=,ppid=,pgid=,lstart=,command=\n")


@unittest.skipUnless(ca.POSIX, "the POSIX `ps` reading")
class ContinuationLines(unittest.TestCase):
    def test_the_rows_are_read_and_the_reader_is_listed(self):
        out, reader = table_of(ROWS)
        self.assertEqual(sorted(out), [100, 31337])
        self.assertEqual(reader, 31337)
        self.assertEqual((out[100].ppid, out[100].pgid), (1, 100))

    def test_a_continuation_line_that_reads_as_a_date_is_no_row(self):
        lines = ROWS.splitlines(keepends=True)
        text = lines[0] + 'y.py"])\\012\n' + "foo bar baz Sun Oct 11 09:30:00 2026 trailing text\n" + \
            "12 x 7 Sun Oct 11 09:30:00 2026 a pid that is not one\n" + lines[1]
        out, _ = table_of(text)
        self.assertEqual(sorted(out), [100, 31337])
        self.assertEqual(out[100].command, "/usr/bin/sleep 60")

    def test_a_table_that_does_not_list_the_reader_is_still_refused(self):
        with self.assertRaises(OSError):
            table_of(ROWS.splitlines(keepends=True)[0] + "foo bar baz Sun Oct 11 09:30:00 2026 x\n")


if __name__ == "__main__":
    unittest.main()
