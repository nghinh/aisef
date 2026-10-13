"""V2.1 (B-03, round 3, WP auth): the readers beside `_read` — the Windows table, `carriers` (`ps -E`), `cwd_under`
(`lsof -F`) — read their tool's bytes, end a line at LF (or NUL) only, and refuse a line that is no row.

They produce *candidates* that `signal_owned` re-proves against `_read`'s table, so a forged line is no authority; but a
line cut silently is a candidate lost (a leftover the runner never cleans, while it reports "no stray left"), and a
line made up is a process that is not there.

* Windows: the PowerShell script prints the command line as base64 of its UTF-8 bytes, so no character of a command
  can end a row or begin another; a row is `pid|ppid|seconds|base64` or the reading is refused. The Windows path is NOT
  run by this file (no PowerShell here): the script's text is asserted, and its OUTPUT is simulated from the format.
* `carriers`: the environment follows the command in `ps -E`, so any text is in it; a token after a U+2028 is found.
* `cwd_under`: `lsof -F0pn` ends a field at NUL, which no path holds; a path with U+2028 is one field.

The last class runs the real tools of the host (`ps -E` / `lsof` on macOS, /proc on Linux) with real children."""

from __future__ import annotations

import base64
import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))

import cleanup_authority as ca  # noqa: E402

READER = 31337
RUNNER = os.getpid()
SEPARATORS = ("\u2028", "\u2029", "\u0085", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\r", "\n", "\r\n", "\u00a0")
PREFIX = "AISEF_MUTATION_RUN=worker:"


class Fake:
    """The Popen a reader of a tool's output gets: the bytes, a return code, a pid, and the arguments it was given."""
    calls: list = []

    def __init__(self, argv, *a, raw=b"", returncode=0, pid=READER, **kw):
        self.raw, self.returncode, self.pid = raw, returncode, pid
        type(self).calls.append((argv, kw))

    def communicate(self, *_a, **_k):
        return self.raw, None


@contextlib.contextmanager
def printing(raw, returncode=0, pid=READER, posix=True, platform=None):
    """The module's `ps` / PowerShell prints `raw` (a binary-mode Popen); with `platform`, `sys.platform` of the
    module is that — "darwin" selects the `ps -E` branch of `carriers` on any host."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    Fake.calls = []

    def popen(argv, *a, **k):
        return Fake(argv, *a, raw=raw, returncode=returncode, pid=pid, **k)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(ca, "POSIX", posix))
        stack.enter_context(mock.patch.object(ca.subprocess, "Popen", popen))
        if platform is not None:
            stack.enter_context(mock.patch.object(ca, "sys", types.SimpleNamespace(platform=platform)))
        yield


def host(pid, born=1_000.0, command="x"):
    return ca.Host(pid, 1, pid, born, command)


# ------------------------------------------------------------------------------------------------ Windows

def win_row(pid, ppid, born, command, end="\r\n"):
    return f"{pid}|{ppid}|{born}|{base64.b64encode(command.encode('utf-8')).decode('ascii')}{end}"


def windows(raw, **kw):
    with printing(raw, posix=False, **kw):
        return ca._read()


class WindowsTable(unittest.TestCase):
    """The PowerShell output is simulated from the format the script prints (it is not run here)."""

    def test_the_rows_are_read_with_the_command_decoded_and_the_reader_is_the_shell(self):
        out, reader = windows(win_row(4, 0, 1_700_000_000, "") + win_row(100, 4, 1_700_000_005, r"C:\x\y.exe -a b"))
        self.assertEqual(reader, READER)
        self.assertEqual(out[4], ca.Host(4, 0, -1, 1_700_000_000.0, ""))
        self.assertEqual(out[100], ca.Host(100, 4, -1, 1_700_000_005.0, r"C:\x\y.exe -a b"))

    def test_a_command_holding_any_character_is_one_row_with_the_whole_command(self):
        victim = 700
        for sep in SEPARATORS:
            with self.subTest(sep=repr(sep)):
                command = f"carrier{sep}{victim}|{RUNNER}|4102444799|QUJD{sep}200|1|5|QUJD"
                out, _ = windows(win_row(victim, 1, 1_000, "/earlier") + win_row(200, RUNNER, 2_000, command))
                self.assertEqual(sorted(out), sorted([victim, 200]))
                self.assertEqual(out[200].command, command)
                self.assertEqual((out[victim].ppid, out[victim].born, out[victim].command), (1, 1000.0, "/earlier"))

    def test_the_command_is_utf8_and_a_byte_that_is_not_is_replaced(self):
        raw = "100|4|5|" + base64.b64encode("na\u00efve \u2028 \U0001f600".encode()).decode() + "\r\n" + \
              "101|4|5|" + base64.b64encode(b"a\xffb").decode() + "\r\n"
        out, _ = windows(raw)
        self.assertEqual(out[100].command, "na\u00efve \u2028 \U0001f600")
        self.assertEqual(out[101].command, "a\ufffdb")

    def test_lines_end_at_crlf_or_lf_and_blank_lines_are_no_rows(self):
        out, _ = windows("\r\n" + win_row(1, 0, 5, "a", end="\n") + "  \r\n" + win_row(2, 1, 6, "b") + "\r\n")
        self.assertEqual(sorted(out), [1, 2])

    def test_every_line_that_is_no_row_refuses_the_reading(self):
        good = win_row(1, 0, 5, "a")
        for name, bad in {
            "a raw command line, not encoded": "100|4|5|C:\\x y.exe\r\n",
            "a command that was cut at a raw LF": "100|4|5|QUJD\r\ngarbage line\r\n",
            "a pid that is not digits": "1x|4|5|QUJD\r\n",
            "a parent that is not digits": "100|x|5|QUJD\r\n",
            "a start that is not a number": "100|4|soon|QUJD\r\n",
            "base64 with a space": "100|4|5|QU JD\r\n",
            "base64 with a bad pad": "100|4|5|QUJD=\r\n",
            "base64 that is not whole": "100|4|5|QUJ\r\n",
            "a missing field": "100|4|5\r\n",
            "an extra field": "100|4|5|QUJD|QUJD\r\n",
            "an error text": "Get-CimInstance : Access denied\r\n",
            "only a separator": "\u2028\r\n",
            "a lone CR": "\r",
        }.items():
            with self.subTest(bad=name):
                with self.assertRaises(ca.TableUnreadable) as cm:
                    windows(good + bad)
                self.assertIsInstance(cm.exception, OSError)
                self.assertTrue(str(cm.exception).startswith("powershell printed a line that is not a process row: "),
                                str(cm.exception))

    def test_a_pid_listed_twice_is_refused(self):
        with self.assertRaises(ca.TableUnreadable) as cm:
            windows(win_row(100, 4, 5, "a") + win_row(100, RUNNER, 99, "fabricated"))
        self.assertTrue(str(cm.exception).startswith("powershell listed pid 100 twice: "), str(cm.exception))

    def test_a_shell_that_cannot_run_or_times_out_proves_nothing_and_is_not_an_error(self):
        for exc in (OSError("no powershell"), subprocess.TimeoutExpired("powershell", 60)):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(ca, "POSIX", False), mock.patch.object(ca.subprocess, "Popen", side_effect=exc):
                    self.assertEqual(ca._read(), ({}, -1))
                    self.assertEqual(ca.host_table(), {})

    def test_the_script_asks_for_the_command_encoded_and_for_nothing_raw(self):
        """The script text is asserted, not run: the one place a raw command line could leave PowerShell is
        `$_.CommandLine`, and it must go through ToBase64String of its UTF-8 bytes."""
        windows(win_row(1, 0, 5, "a"))
        (argv, kwargs), = Fake.calls
        self.assertEqual(argv[:4], ["powershell", "-NoProfile", "-NonInteractive", "-Command"])
        script = argv[4]
        self.assertEqual(script.count("$_.CommandLine"), 1)
        self.assertIn("[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$_.CommandLine))", script)
        for needed in ("Get-CimInstance Win32_Process", "'{0}|{1}|{2}|{3}' -f", "$_.ProcessId", "$_.ParentProcessId",
                       "$_.CreationDate", ".TotalSeconds"):
            self.assertIn(needed, script)

    def test_a_command_line_cannot_make_a_process_the_runner_s(self):
        """The proofs over a Windows table: a victim older than the boundary stays unproven whatever text a command
        holds (the text is encoded, so it is only ever a command)."""
        victim, carrier = 700, 800
        command = f"x\u2028{victim}|{RUNNER}|4102444799|QUJD\n{victim}|{RUNNER}|4102444799|QUJD"
        raw = win_row(READER, RUNNER, 2_000, "powershell") + win_row(victim, RUNNER, 1_000, "/earlier") + \
            win_row(carrier, RUNNER, 2_000, command)
        with printing(raw, posix=False):
            boundary = ca.establish("root")
            table = ca.host_table()
        self.assertEqual((boundary.runner, boundary.since), (RUNNER, 2000.0))
        self.assertEqual(sorted(ca.owned(boundary, table)), [carrier, READER])
        report = ca.signal_owned(boundary, pids=[victim], dry_run=True, table=table)
        self.assertEqual((report.signalled, [u["id"] for u in report.unproven]), ([], [victim]))


# ------------------------------------------------------------------------------------------- carriers (ps -E)

def env_row(pid, text):
    return f"{pid:>5} {text}\n"


def carriers_of(raw, table, **kw):
    with printing(raw, platform="darwin", **kw):
        return ca.carriers(PREFIX, table)


class Carriers(unittest.TestCase):
    """macOS: `ps -E -ww -A -o pid=,command=`: the command and its environment as printed, on one line."""

    def table(self, *pids):
        return {p: host(p) for p in (*pids, READER)}

    def test_a_process_whose_environment_holds_the_token_is_a_candidate(self):
        raw = env_row(100, "/bin/a X=1") + env_row(200, f"/bin/b Y=2 {PREFIX}1 Z=3") + env_row(READER, "ps -E")
        found = carriers_of(raw, self.table(100, 200))
        self.assertEqual([h.pid for h in found], [200])

    def test_a_token_after_a_separator_is_found_not_cut_off(self):
        for sep in [s for s in SEPARATORS if "\n" not in s]:   # an LF is where a row ends: `ps` escapes it
            with self.subTest(sep=repr(sep)):
                raw = env_row(100, "/bin/a X=1") + env_row(200, f"/bin/b A_FIRST=x{sep}y {PREFIX}1") + \
                    env_row(READER, "ps -E")
                self.assertEqual([h.pid for h in carriers_of(raw, self.table(100, 200))], [200])

    def test_text_that_looks_like_a_row_inside_an_environment_makes_no_candidate(self):
        raw = env_row(100, "/bin/a X=1") + env_row(200, f"/bin/b E=x\u2028100 {PREFIX}1") + env_row(READER, "ps -E")
        self.assertEqual([h.pid for h in carriers_of(raw, self.table(100, 200))], [200])

    def test_only_listed_processes_other_than_this_one_are_candidates_in_pid_order(self):
        raw = env_row(300, f"c {PREFIX}1") + env_row(999, f"d {PREFIX}1") + env_row(200, f"b {PREFIX}1") + \
            env_row(os.getpid(), f"me {PREFIX}1") + env_row(READER, "ps -E")
        table = {**self.table(200, 300), os.getpid(): host(os.getpid())}   # 999 is not in the authority's table
        self.assertEqual([h.pid for h in carriers_of(raw, table)], [200, 300])

    def test_a_row_without_a_command_is_a_row(self):
        raw = env_row(100, "") + "  200\n" + env_row(READER, "ps -E")
        self.assertEqual(carriers_of(raw, self.table(100, 200)), [])

    def test_a_line_that_is_no_row_or_a_pid_twice_or_a_failed_ps_refuses_the_reading(self):
        listed = env_row(READER, "ps -E")
        for name, raw, rc, message in (
                ("no row", env_row(100, "a") + "junk without a pid\n" + listed, 0,
                 "ps -E printed a line that is not a process row: 'junk without a pid'"),
                ("a header", "  PID COMMAND\n" + listed, 0,
                 "ps -E printed a line that is not a process row: '  PID COMMAND'"),
                ("a pid twice", env_row(100, "a") + env_row(100, f"b {PREFIX}1") + listed, 0,
                 f"ps -E listed pid 100 twice: '  100 b {PREFIX}1'"),
                ("exit 1", env_row(100, "a") + listed, 1, "ps -E exited 1: the environments cannot be read"),
                ("exit 0, without itself", env_row(100, "a"), 0,
                 "ps -E did not list itself: the environments cannot be read"),
                ("empty", "", 0, "ps -E did not list itself: the environments cannot be read")):
            with self.subTest(name):
                with self.assertRaises(ca.TableUnreadable) as cm:
                    carriers_of(raw, self.table(100), returncode=rc)
                self.assertIsInstance(cm.exception, OSError)
                self.assertEqual(str(cm.exception), message)

    def test_the_command_is_ps_E_for_every_process_untruncated(self):
        carriers_of(env_row(READER, "ps -E"), self.table())
        (argv, _), = Fake.calls
        self.assertEqual(argv, ["ps", "-E", "-ww", "-A", "-o", "pid=,command="])

    def test_windows_has_no_environment_to_read(self):
        with printing("", posix=False):
            self.assertEqual(ca.carriers(PREFIX, {}), [])


class CarriersOnLinux(unittest.TestCase):
    """Linux: /proc/<pid>/environ, NUL separated — a hermetic fake of the files (the branch was not changed; its
    mutants are pinned here, and the real /proc is read by TheRealHost on a Linux host)."""

    def carriers(self, environ, table, prefix=PREFIX):
        reads = []

        class FakePath:
            def __init__(self, path):
                self.path = str(path)

            def read_bytes(self):
                reads.append(self.path)
                if self.path not in environ:
                    raise OSError("gone")
                return environ[self.path]
        with mock.patch.object(ca, "POSIX", True), mock.patch.object(ca, "sys", types.SimpleNamespace(platform="linux")), \
                mock.patch.object(ca, "pathlib", types.SimpleNamespace(Path=FakePath)):
            return ca.carriers(prefix, table), reads

    def test_the_token_is_a_whole_variable_at_the_start_of_one_of_the_nul_separated_strings(self):
        environ = {
            "/proc/100/environ": b"A=1\0AISEF_MUTATION_RUN=worker:1\0B=2\0",
            "/proc/200/environ": b"A=1\0X_AISEF_MUTATION_RUN=worker:1\0",     # not at the start of a variable
            "/proc/300/environ": b"AISEF_MUTATION_RUN=other:1\0",                # another worker's
            "/proc/400/environ": b"A=\xe2\x80\xa8\0AISEF_MUTATION_RUN=worker:2\0",  # U+2028 before it
        }
        table = {p: host(p) for p in (100, 200, 300, 400, 500, os.getpid())}
        found, reads = self.carriers(environ, table)
        self.assertEqual([h.pid for h in found], [100, 400])
        self.assertEqual(sorted(reads), sorted(f"/proc/{p}/environ" for p in table))   # each pid of the table, once

    def test_an_environment_that_cannot_be_read_is_skipped_and_this_process_is_not_a_candidate(self):
        environ = {f"/proc/{os.getpid()}/environ": PREFIX.encode() + b"1\0", "/proc/100/environ": b"A=1\0"}
        found, _ = self.carriers(environ, {p: host(p) for p in (100, 200, os.getpid())})
        self.assertEqual(found, [])


# ------------------------------------------------------------------------------------------- cwd_under (lsof)

def lsof_out(entries):
    """`lsof -F0pn` as measured: each field ends at NUL, each set (the process, then its file) at LF."""
    return "".join(f"p{pid}\0\nfcwd\0n{path}\0\n" for pid, path in entries).encode("utf-8")


@contextlib.contextmanager
def lsof_prints(raw, returncode=1):
    """`lsof` prints `raw` (bytes); it exits 1 when one of the asked pids is gone, as it did where measured."""
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return types.SimpleNamespace(stdout=raw, returncode=returncode, stderr=b"")
    with mock.patch.object(ca, "POSIX", True), mock.patch.object(ca, "sys", types.SimpleNamespace(platform="darwin")), \
            mock.patch.object(ca.subprocess, "run", run):
        yield calls


class CwdUnder(unittest.TestCase):
    ME = os.getpid()

    def table(self, *pids, born=2_000.0):
        return {p: host(p, born) for p in pids}

    def test_a_process_working_under_the_prefix_is_a_candidate(self):
        raw = lsof_out([(self.ME, "/home/me"), (100, "/work/tree/sub"), (200, "/elsewhere"), (300, "/work/tree")])
        with lsof_prints(raw):
            found = ca.cwd_under("/work/tree/", self.table(100, 200, 300))
        self.assertEqual([h.pid for h in found], [100, 300])

    def test_a_path_holding_a_separator_is_one_field_not_cut(self):
        for sep in ("\u2028", "\u2029", "\u0085", "\x0b", "\x0c", "\r", "\n", "\u00a0", " "):
            with self.subTest(sep=repr(sep)):
                d = f"/work/tree/a{sep}b"
                raw = lsof_out([(self.ME, "/home/me"), (100, d), (200, "/work/tree/a")])
                with lsof_prints(raw):
                    found = ca.cwd_under(d + "/", self.table(100, 200))
                self.assertEqual([h.pid for h in found], [100])

    def test_text_that_looks_like_a_field_inside_a_path_makes_no_process(self):
        d = "/work/tree/x\np999\nn/work/tree"      # a path holding what would be the next set, were it split at LF
        raw = lsof_out([(self.ME, "/home/me"), (100, d)])
        with lsof_prints(raw):
            found = ca.cwd_under("/work/tree/", self.table(100, 999))
        self.assertEqual([h.pid for h in found], [100])

    def test_the_prefix_is_a_directory_or_a_name_prefix_as_given(self):
        raw = lsof_out([(self.ME, "/home/me"), (100, "/work/tree2"), (200, "/work/tree")])
        with lsof_prints(raw):
            self.assertEqual([h.pid for h in ca.cwd_under("/work/tree/", self.table(100, 200))], [200])
        with lsof_prints(raw):
            self.assertEqual([h.pid for h in ca.cwd_under("/work/tree", self.table(100, 200))], [100, 200])

    def test_only_processes_born_after_since_are_asked_and_this_one_always(self):
        table = {300: host(300, 2_000.0), 100: host(100, 1_000.0), 200: host(200, 2_000.0)}
        with lsof_prints(lsof_out([(self.ME, "/home/me"), (200, "/w"), (300, "/w")])) as calls:
            found = ca.cwd_under("/w/", table, since=2_000.0)
        self.assertEqual([h.pid for h in found], [200, 300])
        (argv, _), = calls
        self.assertEqual(argv[-1], f"{self.ME},200,300")   # in pid order, whatever the table's order

    def test_lsof_is_asked_for_cwd_with_nul_terminated_fields(self):
        """`-a` ANDs `-d cwd` with `-p`: without it lsof lists every open file of those pids and the cwd of every
        process, and a later `n` field would replace the working directory; `-0` ends fields at NUL."""
        with lsof_prints(lsof_out([(self.ME, "/home/me")])) as calls:
            ca.cwd_under("/w/", {})
        (argv, kw), = calls
        self.assertEqual(argv, ["lsof", "-nP", "-w", "-a", "-d", "cwd", "-F0pn", "-p", str(self.ME)])
        self.assertTrue(kw["capture_output"])
        self.assertNotIn("text", kw)
        self.assertNotIn("encoding", kw)   # bytes: a text-mode read would turn a CR into an LF

    def test_a_name_that_is_not_utf8_is_replaced_and_ends_nothing(self):
        raw = lsof_out([(self.ME, "/home/me"), (100, "/w/a")]) + b"p200\0\nfcwd\0n/w/b\xffc\0\n"
        with lsof_prints(raw):
            found = ca.cwd_under("/w/b\ufffdc/", self.table(100, 200))
        self.assertEqual([h.pid for h in found], [200])

    def test_output_that_is_not_p_f_n_fields_refuses_the_reading(self):
        me = lsof_out([(self.ME, "/home/me")])
        for name, raw in {
            "output that stops inside a field": me + b"p100\0\nfcwd\0n/work/tr",
            "an unknown field": me + b"p100\0\nfcwd\0nx\0\nXjunk\0\n",
            "a process id that is not digits": me + b"p10x\0\nfcwd\0n/w\0\n",
            "a name before any process": b"n/w\0\n" + me,
            "plain lines (a tool that ignores -0)": b"p100\nfcwd\nn/w\n",
        }.items():
            with self.subTest(name):
                with lsof_prints(raw):
                    with self.assertRaises(ca.TableUnreadable) as cm:
                        ca.cwd_under("/w/", self.table(100))
                self.assertIsInstance(cm.exception, OSError)
                self.assertEqual(str(cm.exception), self.WHAT[name])

    WHAT = {
        "output that stops inside a field": "lsof output ends inside a field: b'n/work/tr'",
        "an unknown field": "lsof printed a field that is not p, f or n of a process: b'Xjunk'",
        "a process id that is not digits": "lsof printed a field that is not p, f or n of a process: b'p10x'",
        "a name before any process": "lsof printed a field that is not p, f or n of a process: b'n/w'",
        "plain lines (a tool that ignores -0)": "lsof output ends inside a field: b'p100\\nfcwd\\nn/w\\n'",
    }

    def test_a_reading_that_does_not_list_this_process_is_refused_not_an_empty_answer(self):
        for raw in (b"", b"\n", lsof_out([(100, "/w/x")])):
            with self.subTest(raw=raw[:20]):
                with lsof_prints(raw):
                    with self.assertRaises(ca.TableUnreadable) as cm:
                        ca.cwd_under("/w/", self.table(100))
                self.assertEqual(str(cm.exception),
                                 "lsof did not list this process's cwd: the working directories cannot be read")

    def test_a_fd_field_of_another_kind_and_a_name_for_a_pid_not_in_the_table_are_ignored(self):
        raw = lsof_out([(self.ME, "/home/me"), (999, "/w/x")]).replace(b"fcwd", b"ftxt", 1)
        with lsof_prints(raw):
            self.assertEqual(ca.cwd_under("/w/", self.table(100)), [])

    def test_windows_has_no_working_directory_to_read(self):
        with mock.patch.object(ca, "POSIX", False):
            self.assertEqual(ca.cwd_under("/w/", {}), [])


class CwdUnderOnLinux(unittest.TestCase):
    """Linux: /proc/<pid>/cwd by readlink — a hermetic fake (the branch was not changed; its mutants are pinned here,
    and the real /proc is read by TheRealHost on a Linux host)."""

    def cwd_under(self, links, table, prefix, since=None):
        asked = []

        def readlink(path):
            asked.append(str(path))
            if str(path) not in links:
                raise OSError("gone")
            return links[str(path)]
        with mock.patch.object(ca, "POSIX", True), mock.patch.object(ca, "sys", types.SimpleNamespace(platform="linux")), \
                mock.patch.object(ca.os, "readlink", readlink):
            return ca.cwd_under(prefix, table, since), asked

    def test_a_process_whose_cwd_link_is_under_the_prefix_is_a_candidate(self):
        links = {"/proc/100/cwd": "/w/tree/a", "/proc/200/cwd": "/w/other", "/proc/300/cwd": "/w/tree",
                 f"/proc/{os.getpid()}/cwd": "/w/tree/me"}
        table = {p: host(p) for p in (300, 100, 200, 400, os.getpid())}   # 400: its link cannot be read
        found, asked = self.cwd_under(links, table, "/w/tree/")
        self.assertEqual([h.pid for h in found], [100, 300])
        self.assertEqual(asked, [f"/proc/{p}/cwd" for p in (100, 200, 300, 400)])   # in pid order, not this process

    def test_a_path_with_a_separator_is_whole_and_since_limits_the_asked(self):
        links = {"/proc/200/cwd": "/w/tree/a\u2028b", "/proc/100/cwd": "/w/tree/a\u2028b"}
        table = {100: host(100, 1_000.0), 200: host(200, 2_000.0)}
        found, asked = self.cwd_under(links, table, "/w/tree/a\u2028b/", since=2_000.0)
        self.assertEqual(([h.pid for h in found], asked), ([200], ["/proc/200/cwd"]))


# ------------------------------------------------------------------------------- the real tools of the host

@unittest.skipUnless(ca.POSIX, "ps -E, lsof and /proc are the POSIX readers")
class TheRealHost(unittest.TestCase):
    """Real children (they end when their stdin is closed) and the real tool of this host: `lsof -F0pn` and `ps -E`
    on macOS, /proc on Linux."""

    def start(self, argv=(), env=None, cwd=None):
        code = "import sys; print('ready', flush=True); sys.stdin.read()"
        p = subprocess.Popen([sys.executable, "-c", code, *argv], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             env=env, cwd=cwd)
        self.addCleanup(self.end, p)
        self.assertEqual(p.stdout.readline(), b"ready\n")
        return p

    @staticmethod
    def end(p):
        p.stdin.close()
        p.wait()
        p.stdout.close()

    def test_a_process_working_in_a_directory_with_a_separator_in_its_name_is_found(self):
        names = ("plain", "a\u2028b", "c\u2029d", "e\u00a0f", "g h")
        with tempfile.TemporaryDirectory() as t:
            kids = {}
            for name in names:
                pathlib.Path(t, name).mkdir()
                kids[name] = self.start(cwd=str(pathlib.Path(t, name)))
            table = ca.host_table()
            try:
                for name, kid in kids.items():
                    with self.subTest(name=name):
                        found = ca.cwd_under(os.path.join(os.path.realpath(t), name) + os.sep, table)
                        self.assertEqual([h.pid for h in found], [kid.pid])
            finally:
                for kid in kids.values():
                    self.end(kid)   # before the directory goes: nothing of this test is running when it is removed

    def test_a_token_after_a_variable_holding_a_separator_is_found(self):
        name = f"AISEF_AUTH_TEST_{os.getpid()}"   # no other process of the host carries it, or names it
        base = {"PATH": os.environ.get("PATH", "")}
        control = self.start(env={**base, name: "run:1"})
        if control.pid not in [h.pid for h in ca.carriers(f"{name}=run:", ca.host_table())]:
            self.skipTest("this host hides the environment of its interpreter from ps -E")
        kid = self.start(env={**base, "A_FIRST": "x\u2028y", "B": "1\u20292", name: "run:2"})
        found = ca.carriers(f"{name}=run:", ca.host_table())
        self.assertEqual(sorted(h.pid for h in found), sorted([control.pid, kid.pid]))


if __name__ == "__main__":
    unittest.main()
