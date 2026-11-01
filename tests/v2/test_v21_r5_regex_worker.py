"""V2.1 (owner decision of 2026-10-15, item 4 — ReDoS in the reproducer): the search of a `regex` stream shape of
`probe.cli_invocation` runs in a worker process under the harness watchdog, and a search that does not finish is a stop
of the harness — UNRUNNABLE, UNVERIFIABLE in a review — never a verdict about the product.

The pattern is a model reviewer's (a reproducer) or a spec author's, and the stream is the candidate's: `(a+)+$` over a
line of forty `a`s and a mark does not return. Before this change `_stream_matches` ran `re.search` in the probe's own
process, `timeouts_s.probe` bounded nothing there, and the run (or the review, which verifies every finding that states
a reproducer) did not end. The mechanism is the one `file_artifact` has for `grep_count` since PM-13 (test_v21_fa_grep_worker.py):
a harness script given bytes and a pattern, in a process range, one deadline for the whole operation, one reason for
each way to stop, never retried. Pinned here, by observation and by what happens to the processes:

* what the worker answers is what `re.search` in this process answers, over every kind of text a stream can hold (empty,
  several lines, flags, non-ASCII, bytes that are not UTF-8, a NUL, a truncated capture, a megabyte), and the verdict of
  the whole observable is the one the in-process verdict was;
* a pattern that cannot finish stops at the deadline (about `timeouts_s.probe`, not a minute later), is
  HARNESS_FAILED/UNRUNNABLE (owner ENVIRONMENT) whatever the window and whichever expectation, names the stream, the
  bytes and the head of the pattern, and says that running it again changes nothing;
* the range is emptied: the worker, a grandchild of it, a worker that ignores the polite signals — and a process of the
  host that is not in the range, whatever its command line says, is not touched;
* each way the worker can fail has its own reason; nothing is retried;
* the time of the search is the harness's: it is not part of the subject's window (a slow search changes no verdict, a
  stuck one is not `SUBJECT_DEADLINE`), and a search is made only for a conjunct that is reached;
* through `review_verify.verify`: a stuck search is UNVERIFIABLE, an ordinary one NOT_REPRODUCED or CONFIRMED."""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, MeasurementPoint, ObligationRole, SubjectAbsence  # noqa: E402
from aisef2.control.owner import FailureCode, Owner  # noqa: E402
from aisef2.control.routing import row_for  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, run_probe  # noqa: E402
from aisef2.runtime import process_range as PR  # noqa: E402
from tests.v2 import test_c2_cli_invocation as base  # noqa: E402   (helpers only: its test classes are not imported)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
posix = unittest.skipUnless(os.name == "posix", "the ladder of signals and the process groups are POSIX")
#: classic catastrophic backtracking: nested quantifiers over forty letters and a character the pattern cannot take
EVIL = "(a+)+$"
EVIL_LINE = "a" * 40 + "!"
#: what a stopped search may take beyond its deadline: the range's ladder (0.5 s + 0.5 s), the start and the host
SLACK = 4.0


def search(pattern: str, data: bytes, *, work: str, timeout: float = 30.0, stream: str = "stdout", on_range=None) -> bool:
    return ci.search_in_worker(pattern, data, stream=stream, work=work, name="test regex search", timeout_s=timeout,
                               on_range=on_range)


def in_process(pattern: str, data: bytes) -> bool:
    """The search as it always was: written here, for comparison only."""
    return re.search(pattern, data.decode("utf-8", "replace")) is not None


def oracle(pattern: str, data: bytes, stream: str = "") -> bool:
    """`in_process` as the `search` of a caller that holds no harness (the class table's fixture facts): `verdict_of` and
    `_stream_matches` have no search of their own to fall back to, so what they are compared with is given explicitly."""
    return in_process(pattern, data)


def recording(calls: list, work: str):
    """A `search` for `_stream_matches` that records what it is asked and asks the worker."""
    def bounded(pattern, data, stream):
        calls.append((pattern, data))
        return search(pattern, data, work=work, stream=stream)
    return bounded


def alive(pid: int) -> bool:
    return pid in PR.process_table()


def counting(made: list):
    """ProcessRange, recording the name of every range made."""
    class Counting(PR.ProcessRange):
        def __init__(self, *a, **k):
            made.append(a[0])
            super().__init__(*a, **k)
    return Counting


class Work(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-rl-regex-")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.dir = pathlib.Path(cls._tmp.name)

    def work(self) -> str:
        return tempfile.mkdtemp(dir=self.dir)


# a pattern, the bytes of a stream
ROWS = (
    ("a letter in the text", "a", b"banana"),
    ("an anchor that holds", "^b", b"banana"),
    ("an anchor that does not", "^a", b"banana"),
    ("nothing found", "x", b"banana"),
    ("an empty stream, nothing to find", "x", b""),
    ("an empty stream, the empty match", "^$", b""),
    ("an empty pattern", "", b"anything"),
    ("the second line is not a line start without (?m)", "^b", b"a\nb\n"),
    ("(?m)", "(?m)^b", b"a\nb\n"),
    ("$ before a final newline", "a$", b"a\n"),
    ("\\Z does not", "a\\Z", b"a\n"),
    ("a dot does not take a newline", "a.b", b"a\nb"),
    ("(?s)", "(?s)a.b", b"a\nb"),
    ("(?i)", "(?i)BAN", b"banana"),
    ("a carriage return and a newline", "\\r\\n", b"a\r\nb"),
    ("a non-ASCII letter", "é", "café".encode("utf-8")),
    ("a non-ASCII class", "[^\\x00-\\x7f]+$", "naïve日本".encode("utf-8")),
    ("a character outside the BMP", "\U0001f600", "x\U0001f600y".encode("utf-8")),
    ("a lone surrogate in the pattern", "\ud800", "x\U0001f600y".encode("utf-8")),
    ("bytes that are not UTF-8 are replaced", "�", b"a\xffb"),
    ("... and are found as the replacement", "a�b", b"a\xffb"),
    ("a NUL", "a\\x00b", b"a\x00b"),
    ("a mark that is not the end", "﻿", b"\xef\xbb\xbfx"),
    ("a bounded quantifier", "x{3}", b"xx xxx"),
    ("a lazy quantifier", "a.*?c", b"abcabc"),
    ("a lookahead", "a(?=b)", b"ab"),
    ("a backreference", "(a)\\1", b"aa"),
    ("a megabyte and a needle at the end", "x{1000}needle$", b"x" * (1 << 20) + b"needle"),
    ("a megabyte and none", "needle", b"x" * (1 << 20)),
    ("long lines the pattern passes", "^(?:ab)+$", b"ab" * 200000),
)


class SameAnswerAsInProcess(Work):
    """The worker's answer is the in-process answer, byte for byte, whatever the text."""

    def test_every_row(self):
        for what, pattern, data in ROWS:
            with self.subTest(what):
                self.assertEqual(search(pattern, data, work=self.work()), in_process(pattern, data))

    def test_the_rows_hold_both_answers(self):
        got = {in_process(p, d) for _, p, d in ROWS}
        self.assertEqual(got, {True, False})

    def test_a_shape_is_matched_over_the_bytes_its_facts_name_and_no_more(self):
        """`_stream_matches` with the search given and without it, over a capture the harness cut (`truncated`), over a
        capture file longer than the size the facts state, over a file that is gone and over no facts: the same bytes
        reach the worker as reach `re.search`, and the answer is the same."""
        work = self.work()
        path = os.path.join(work, "out.bin")
        pathlib.Path(path).write_bytes(b"first\nsecond\nTAIL")
        for what, fact in (("a whole capture", {"path": path, "size": 17, "truncated": False}),
                           ("a cut capture", {"path": path, "size": 12, "truncated": True}),
                           ("a capture file that is gone", {"path": os.path.join(work, "none.bin"), "size": 5}),
                           ("no facts", {})):
            for pattern in ("TAIL$", "second$", "^first", "(?m)^second$", "^$", "x"):
                with self.subTest(what, pattern=pattern):
                    calls = []
                    shape = {"regex": pattern}
                    self.assertEqual(ci._stream_matches(shape, fact, recording(calls, work), "stdout"),
                                     ci._stream_matches(shape, fact, oracle, "stdout"))
                    self.assertEqual(calls, [(pattern, ci._stream_bytes(fact))])
        self.assertEqual(ci._stream_bytes({"path": path, "size": 12, "truncated": True}), b"first\nsecond")

    def test_the_verdict_of_a_whole_observable_is_the_in_process_verdict(self):
        work = self.work()
        for name, text in (("out", b"hello\nworld\n"), ("err", b"warning: x\n")):
            pathlib.Path(work, name).write_bytes(text)

        def fact(name: str, size: int, truncated: bool = False) -> dict:
            return {"path": os.path.join(work, name), "size": size, "truncated": truncated}

        def bounded(pattern, data, stream):
            return search(pattern, data, work=work, stream=stream)
        facts = {"exit_code": 0, "stdout": fact("out", 12), "stderr": fact("err", 11)}
        for what, obs in (
                ("stdout found", {"exit_code": 0, "stdout": {"regex": "^world$|world\\n"}}),
                ("stdout not found", {"exit_code": 0, "stdout": {"regex": "^nothing"}}),
                ("both found", {"exit_code": 0, "stdout": {"regex": "hello"}, "stderr": {"regex": "^warning"}}),
                ("stderr not found", {"exit_code": 0, "stdout": {"regex": "hello"}, "stderr": {"regex": "^error"}}),
                ("a regex beside a text", {"exit_code": 0, "stdout": {"regex": "hello"}, "stderr": "warning: x\n"}),
                ("a text that fails beside a regex", {"exit_code": 0, "stdout": {"regex": "hello"}, "stderr": "no"}),
                ("an exit code that differs", {"exit_code": 1, "stdout": {"regex": "hello"}}),
                ("only a regex on stderr", {"exit_code": 0, "stderr": {"regex": "x$"}})):
            with self.subTest(what):
                self.assertEqual(ci.verdict_of("exits_streams", obs, facts, bounded),
                                 ci.verdict_of("exits_streams", obs, facts, oracle))


class AStuckSearchStopsAtItsDeadline(Work):
    def test_the_catastrophic_pattern_stops_at_the_deadline_and_says_what_it_is(self):
        ranges = []
        began = time.monotonic()
        with self.assertRaises(ci.StreamSearchFailed) as caught:
            search(EVIL, EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0, stream="stderr", on_range=ranges.append)
        took = time.monotonic() - began
        self.assertEqual(caught.exception.reason, "DEADLINE")
        self.assertGreaterEqual(took, 1.0)
        self.assertLess(took, 1.0 + SLACK, "the deadline bounds the search; a minute is the bug")
        text = str(caught.exception)
        self.assertTrue(text.startswith("regex search DEADLINE: "), text)
        for said in ("1s: timeouts_s.probe", "the stderr stream", f"{len(EVIL_LINE)} bytes", repr(EVIL), "never a verdict",
                     "changes nothing"):
            self.assertIn(said, text)
        self.assertEqual(len(ranges), 1)

    @posix
    def test_the_catastrophic_pattern_stops_at_the_deadline_and_the_range_is_emptied(self):
        """The process-table half of the test above: `members()` and `alive()` read the ps table, which the range has
        only on POSIX; the deadline, the reason and the refusal's text are pinned everywhere by the sibling."""
        ranges = []
        with self.assertRaises(ci.StreamSearchFailed):
            search(EVIL, EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0, stream="stderr", on_range=ranges.append)
        self.assertEqual(ranges[0].members(), [])
        self.assertFalse(alive(ranges[0].target_pid))

    def test_the_pattern_head_names_a_long_pattern_by_its_head(self):
        long = "(a+)+" + "(?:b|" * 20 + "c" + ")" * 20 + "$"
        with self.assertRaises(ci.StreamSearchFailed) as caught:
            search(long, EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0)
        self.assertIn(repr(long[:40] + "..."), str(caught.exception))
        self.assertIn(f"({len(long)} characters)", str(caught.exception))

    def test_a_pattern_that_finishes_in_time_is_not_stopped(self):
        # the same shape of pattern over a line it can refuse at once: nested quantifiers are not the fault
        self.assertEqual(search(EVIL, b"aaaa", work=self.work(), timeout=5.0), True)
        self.assertEqual(search(EVIL, b"!" * 100, work=self.work(), timeout=5.0), False)

    def test_one_deadline_covers_the_whole_operation_and_nothing_is_retried(self):
        made = []
        with mock.patch.object(ci, "ProcessRange", counting(made)):
            with self.assertRaises(ci.StreamSearchFailed):
                search(EVIL, EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0)
        self.assertEqual(made, ["test regex search"])


def stand_in(text: str):
    """The worker script replaced by a stand-in (protocol: argv[1:3] = request, result)."""
    return mock.patch.object(ci, "REGEX_WORKER", text)


class TheRangeIsEmptied(Work):
    def run_with(self, text: str, timeout: float = 1.5):
        ranges = []
        with stand_in(text):
            with self.assertRaises(ci.StreamSearchFailed) as caught:
                search("x", b"x", work=self.work(), timeout=timeout, on_range=ranges.append)
        return caught.exception, ranges

    def test_the_range_is_given_to_the_harness_hook_once_and_is_empty_after(self):
        e, ranges = self.run_with("import time\ntime.sleep(600)\n")
        self.assertEqual(e.reason, "DEADLINE")
        self.assertEqual((len(ranges), ranges[0].name), (1, "test regex search"))

    @posix
    def test_the_range_given_to_the_harness_hook_is_emptied(self):
        """The ps-table half of the test above (`members()`/`alive()` are POSIX reads); the hook's count and the
        range's name are pinned everywhere by the sibling."""
        _, ranges = self.run_with("import time\ntime.sleep(600)\n")
        self.assertEqual(ranges[0].members(), [])
        self.assertFalse(alive(ranges[0].target_pid))

    @posix
    def test_a_worker_that_ignores_the_polite_signals_is_ended_by_its_range(self):
        pidfile = self.dir / "ignorer.json"
        e, ranges = self.run_with(
            "import json, os, signal, sys, time\n"
            "signal.signal(signal.SIGINT, signal.SIG_IGN)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"open({str(pidfile)!r}, 'w').write(json.dumps({{'worker': os.getpid()}}))\ntime.sleep(600)\n")
        self.assertEqual(e.reason, "DEADLINE")
        self.assertEqual([s["stage"] for s in ranges[0].ledger], ["cooperative", "terminate", "kill"])
        self.assertFalse(alive(json.loads(pidfile.read_text(encoding="utf-8"))["worker"]))

    @posix
    def test_a_grandchild_of_the_worker_is_the_ranges_and_is_ended_with_it(self):
        pidfile = self.dir / "grand.json"
        e, ranges = self.run_with(
            "import json, os, subprocess, sys, time\n"
            "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
            f"open({str(pidfile)!r}, 'w').write(json.dumps({{'worker': os.getpid(), 'grandchild': gc.pid}}))\n"
            "time.sleep(600)\n", timeout=3.0)
        pids = json.loads(pidfile.read_text(encoding="utf-8"))
        self.assertEqual(ranges[0].members(), [])
        self.assertFalse(alive(pids["worker"]))
        self.assertFalse(alive(pids["grandchild"]))

    @posix
    def test_a_process_that_is_not_the_ranges_is_not_touched_whatever_its_command_line_says(self):
        # a sentinel whose command line holds the worker's whole text: what a kill by pattern would take
        sentinel = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c",
                                     "import sys; sys.stdin.read()  # " + ci.REGEX_WORKER.replace("\n", " ")],
                                    stdin=subprocess.PIPE)
        try:
            e, _ = self.run_with("import time\ntime.sleep(600)\n")
            self.assertEqual(e.reason, "DEADLINE")
            self.assertIsNone(sentinel.poll())
            self.assertTrue(alive(sentinel.pid))
        finally:
            sentinel.stdin.close()
            sentinel.wait(timeout=30)

    def test_the_real_worker_leaves_nothing_behind_when_it_is_stopped(self):
        ranges = []
        with self.assertRaises(ci.StreamSearchFailed):
            search(EVIL, EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0, on_range=ranges.append)
        self.assertEqual(len(ranges), 1)

    @posix
    def test_the_stopped_real_workers_range_is_emptied(self):
        """The ps-table half of the test above (`members()`/`alive()` are POSIX reads); that EVIL over the real worker
        is StreamSearchFailed is pinned everywhere by the sibling."""
        ranges = []
        with self.assertRaises(ci.StreamSearchFailed):
            search(EVIL, EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0, on_range=ranges.append)
        self.assertEqual(ranges[0].members(), [])
        self.assertFalse(alive(ranges[0].target_pid))

    def test_a_worker_that_answers_leaves_nothing_behind_either(self):
        ranges = []
        self.assertTrue(search("a", b"banana", work=self.work(), on_range=ranges.append))
        self.assertEqual(len(ranges), 1)

    @posix
    def test_an_answering_workers_range_is_emptied_too(self):
        """The ps-table half of the test above (`members()`/`alive()` are POSIX reads); the answer itself is pinned
        everywhere by the sibling."""
        ranges = []
        self.assertTrue(search("a", b"banana", work=self.work(), on_range=ranges.append))
        self.assertEqual(ranges[0].members(), [])
        self.assertFalse(alive(ranges[0].target_pid))


class TheDeadlineIsTheWholeOperationAndALateAnswerIsNoAnswer(Work):
    """The deadline's edge, as `file_artifact`'s grep worker publishes it (PM-13: "a late answer is no answer"): the
    clock is read three times — before the request is written, to give `wait` what is left, and after it — and the
    answer of a worker that exits 0 is taken when the whole operation took no more than `timeouts_s.probe`, and only
    then. A real, fast worker; the clock replaced in the module, as `file_artifact`'s own test does."""

    TIMEOUT = 5.0

    def took(self, seconds: float):
        with mock.patch.object(ci, "_monotonic", mock.Mock(side_effect=[0.0, 0.0, seconds])):
            return search("a", b"banana", work=self.work(), timeout=self.TIMEOUT)

    def test_an_answer_that_took_exactly_the_deadline_is_taken(self):
        self.assertIs(self.took(self.TIMEOUT), True)

    def test_an_answer_that_took_longer_is_not(self):
        with self.assertRaises(ci.StreamSearchFailed) as caught:
            self.took(self.TIMEOUT + 0.001)
        self.assertEqual(caught.exception.reason, "DEADLINE")
        self.assertIn("5s: timeouts_s.probe", str(caught.exception))

    def test_a_worker_that_took_nothing_is_taken(self):
        self.assertIs(self.took(0.0), True)


class FailureModes(Work):
    """Each way the worker can fail has a reason of its own, and is never retried."""

    CASES = {
        # reason: (stand-in worker, a phrase of the message)
        "CRASHED/exit": ("import sys\nsys.exit(7)\n", "CRASHED", "exited with status 7"),
        "CRASHED/traceback": ("1 / 0\n", "CRASHED", "ZeroDivisionError"),
        "NO_RESULT/none": ("pass\n", "NO_RESULT", "wrote no result"),
        "NO_RESULT/empty": ("import sys\nopen(sys.argv[2], 'w').close()\n", "NO_RESULT", "its result is empty"),
        "BAD_RESULT/two": ("import sys\nopen(sys.argv[2], 'w').write('2')\n", "BAD_RESULT", "not an answer"),
        "BAD_RESULT/words": ("import sys\nopen(sys.argv[2], 'w').write('true')\n", "BAD_RESULT", "not an answer"),
        "BAD_RESULT/two answers": ("import sys\nopen(sys.argv[2], 'w').write('10')\n", "BAD_RESULT", "not an answer"),
        "BAD_RESULT/too much": ("import sys\nopen(sys.argv[2], 'w').write('1' * 5_000_000)\n", "BAD_RESULT", "not an answer"),
    }

    def test_each_failure_has_its_reason_and_says_what_the_worker_printed(self):
        for what, (text, reason, phrase) in self.CASES.items():
            with self.subTest(what), stand_in(text):
                with self.assertRaises(ci.StreamSearchFailed) as caught:
                    search("x", b"x", work=self.work())
                self.assertEqual(caught.exception.reason, reason)
                self.assertTrue(str(caught.exception).startswith(f"regex search {reason}: "), str(caught.exception))
                self.assertIn(phrase, str(caught.exception))

    @posix
    def test_a_worker_ended_by_a_signal_is_CRASHED_naming_the_signal(self):
        with stand_in("import signal\nsignal.raise_signal(signal.SIGTERM)\n"):
            with self.assertRaises(ci.StreamSearchFailed) as caught:
                search("x", b"x", work=self.work())
        self.assertEqual(caught.exception.reason, "CRASHED")
        self.assertIn("ended by signal 15", str(caught.exception))

    def test_a_range_that_will_not_start_is_LAUNCH_and_one_that_ends_unreported_is_CRASHED(self):
        for error in (PR.RangeError("the target did not start"), OSError("no such file")):
            with self.subTest(type(error).__name__):
                with mock.patch.object(ci, "ProcessRange", mock.Mock(return_value=mock.Mock(
                        start=mock.Mock(side_effect=error)))):
                    with self.assertRaises(ci.StreamSearchFailed) as caught:
                        search("x", b"x", work=self.work())
                self.assertEqual(caught.exception.reason, "LAUNCH")
        fake = mock.Mock(wait=mock.Mock(return_value=None), release=mock.Mock(), ledger=[])
        with mock.patch.object(ci, "ProcessRange", mock.Mock(return_value=fake)):
            with self.assertRaises(ci.StreamSearchFailed) as caught:
                search("x", b"x", work=self.work(), timeout=60.0)
        self.assertEqual(caught.exception.reason, "CRASHED")
        self.assertIn("without reporting how the worker ended", str(caught.exception))
        fake.release.assert_called_once()

    def test_a_request_that_cannot_be_written_is_INPUT(self):
        with self.assertRaises(ci.StreamSearchFailed) as caught:
            search("x", b"x", work=str(self.dir / "does" / "not" / "exist"))
        self.assertEqual(caught.exception.reason, "INPUT")
        self.assertIn("the request cannot be written", str(caught.exception))

    def test_the_reasons_are_the_vocabulary_of_the_grep_worker(self):
        self.assertEqual(ci.SEARCH_REASONS, fa.WORKER_REASONS)
        self.assertEqual({r for _, r, _ in self.CASES.values()} | {"DEADLINE", "LAUNCH", "INPUT"},
                         set(ci.SEARCH_REASONS))

    def test_the_worker_is_given_a_pattern_and_bytes_and_nothing_else(self):
        seen = []
        real = PR.ProcessRange

        class Seeing(real):
            def __init__(self, name, argv, **kw):
                seen.append((list(argv), kw["env"], kw["cwd"]))
                super().__init__(name, argv, **kw)
        work = self.work()
        with mock.patch.object(ci, "ProcessRange", Seeing):
            self.assertTrue(search("a", b"banana", work=work))
        argv, env, cwd = seen[0]
        self.assertEqual(argv[:5], [sys.executable, "-I", "-S", "-B", "-c"])
        self.assertEqual(argv[5], ci.REGEX_WORKER)
        # a directory of its own, made for this search inside the evaluation directory: not a name in `work` itself
        home = pathlib.Path(cwd)
        self.assertEqual((home.parent, home.name.startswith("regex-")), (pathlib.Path(work), True))
        self.assertEqual([pathlib.Path(a) for a in argv[6:]], [home / "request", home / "result"])
        self.assertFalse({k for k in env if k not in ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR",
                                                      "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHONIOENCODING")})
        head, _, data = (home / "request").read_bytes().partition(b"\n")
        self.assertEqual((json.loads(head), data), ({"pattern": "a"}, b"banana"))
        modules = {a.name for n in ast.parse(ci.REGEX_WORKER).body if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(modules, {"json", "re", "sys"})


@unittest.skipUnless(os.name == "posix" or sys.platform == "win32", "the probe runs on both")
class ThroughTheProbe(base._Product):
    """`observe` and `run_probe` over a real subject whose stdout the pattern is searched in."""

    def say(self, argv, observable, *, window=base.W, timeout=20, probe=None, ranges=None):
        probe = probe or ci.CliInvocationProbe(on_range=None if ranges is None else ranges.append)
        s = base.spec("app:__main__", {"exit_code": 0, **observable}, {"argv": argv}, window=window)
        return s, probe, probe.observe(s, self.at, base.env(timeout))

    def test_an_ordinary_search_gives_the_verdict_the_in_process_search_gave(self):
        for pattern, verdict in (("^hel", S), ("lo$", S), ("^xyz", R), ("(?i)HELLO", S)):
            with self.subTest(pattern):
                _, _, o = self.say(["echo", "hello"], {"stdout": {"regex": pattern}})
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, verdict), o.detail)

    def test_a_pattern_that_cannot_finish_is_a_stop_of_the_harness_not_a_verdict(self):
        for window in (2.0, 60):     # whichever side of the search's deadline (3 s) the subject's window is
            with self.subTest(window=window):
                began = time.monotonic()
                _, _, o = self.say(["echo", EVIL_LINE], {"stdout": {"regex": EVIL}}, window=window, timeout=3)
                self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None), o.detail)
                self.assertTrue(o.detail.startswith("regex search DEADLINE: "), o.detail)
                self.assertIn("the stdout stream", o.detail)
                self.assertLess(time.monotonic() - began, 3 + SLACK + 5)

    def test_it_is_unrunnable_and_the_environment_s_under_every_expectation_and_absence(self):
        for expectation, absence in ((S, SubjectAbsence.REQUIRES_SUBJECT), (R, SubjectAbsence.ABSENCE_IS_DECIDABLE)):
            s = base.spec("app:__main__", {"exit_code": 0, "stdout": {"regex": EVIL}, "within_s": 5},
                          {"argv": ["echo", EVIL_LINE]}, expectation=expectation, absence=absence)
            rec = run_probe(ci.CliInvocationProbe(), s, self.at, base.env(3))
            self.assertEqual(rec.result.status.value, "UNRUNNABLE", rec.result)
            for point in MeasurementPoint:
                for role in (None, *ObligationRole):
                    with self.subTest(point=point.value, role=role and role.value, expectation=expectation.value):
                        route = row_for(rec.result, s, point, role)
                        self.assertEqual((route.failure.code, route.failure.owner),
                                         (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))

    def test_a_search_is_made_for_a_conjunct_that_is_reached_and_in_a_range_of_its_own(self):
        made = []
        with mock.patch.object(ci, "ProcessRange", counting(made)):
            self.say(["echo", "hello"], {"stdout": {"regex": "hello"}})                       # one stream
            self.assertEqual(len([n for n in made if "regex" in n]), 1)
            made.clear()
            self.say(["echo", "hello"], {"stdout": {"regex": "hello"}, "stderr": {"regex": "^$"}})   # two
            self.assertEqual(sorted(n.rsplit(" ", 1)[1] for n in made if "regex" in n), ["stderr", "stdout"])
            made.clear()
            _, _, o = self.say(["echo", "hello"], {"exit_code": 1, "stdout": {"regex": "hello"}})    # the exit already fails
            self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R))
            self.assertEqual([n for n in made if "regex" in n], [])
            _, _, o = self.say(["echo", "hello"], {"stdout": "hello\n"})                       # no regex shape at all
            self.assertEqual([n for n in made if "regex" in n], [])
            self.say(["echo", "hello"], {"stdout": {"regex": "^x"}, "stderr": {"regex": "^y"}})   # stdout fails first
            self.assertEqual(len([n for n in made if "regex" in n]), 1)

    def test_the_observation_never_searches_in_the_probes_own_process(self):
        real, given = ci.verdict_of, []

        def watching(cls, observable, facts, search=None):
            given.append(search)
            return real(cls, observable, facts, search)
        with mock.patch.object(ci, "verdict_of", watching):
            self.say(["echo", "hello"], {"stdout": {"regex": "hello"}})
        self.assertEqual(len(given), 1)
        self.assertTrue(callable(given[0]))

    def test_the_time_of_a_slow_search_is_not_the_subjects_window(self):
        """A search slower than the window, finishing inside the watchdog, changes no verdict: the window is the
        subject's, and the search begins after its RESULT."""
        slow = "import time\ntime.sleep(3.0)\n" + ci.REGEX_WORKER
        with stand_in(slow):
            began = time.monotonic()
            _, _, o = self.say(["echo", "hello"], {"stdout": {"regex": "hello"}}, window=2.0, timeout=30)
            self.assertGreater(time.monotonic() - began, 3.0)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        with stand_in(slow):
            _, _, o = self.say(["echo", "hello"], {"stdout": {"regex": "^xyz"}}, window=2.0, timeout=30)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)


@unittest.skipUnless(os.name == "posix" or sys.platform == "win32", "the probe runs on both")
class ThroughReviewVerify(base._Product):
    """A reviewer's reproducer with a pattern, verified by the kernel's probe: what the finding is told."""

    def verify(self, pattern: str, line: str, *, timeout_s: float = 3.0) -> V.Verification:
        finding = {"id": "F-RX", "severity": "critical", "summary": "the output must match",
                   "reproducer": {"clause": "R-1/1", "subject": {"kind": "cli_invocation", "locator": "app:__main__"},
                                  "stimulus": {"argv": ["echo", line]},
                                  "observable": {"exit_code": 0, "stdout": {"regex": pattern}, "within_s": 10}}}
        with mock.patch.object(V, "calibration_for", return_value=object()):     # the table is not what is under test
            return V.verify(finding, requirements={"R-1": object()}, product_roots={"app"}, root=self.at.root,
                            revision="0" * 40, timeout_s=timeout_s, interpreter=sys.executable)

    def test_a_pattern_that_cannot_finish_is_unverifiable_and_never_blocks(self):
        began = time.monotonic()
        v = self.verify(EVIL, EVIL_LINE)
        self.assertLess(time.monotonic() - began, 3 + SLACK + 5)
        self.assertEqual((v.status, v.observed), (V.UNVERIFIABLE, None), v)
        self.assertIn("did not execute the reproducer", v.reason)
        self.assertIn("regex search DEADLINE", v.reason)
        self.assertEqual(v.evidence(), "")
        anchored = V.Anchor(V.ANCHORED, "x")
        for policy in V.POLICIES:
            self.assertFalse(V.blocks(v, {"severity": "critical"}, policy, "low", anchored))
        self.assertNotIn(v.status, (V.NOT_REPRODUCED, V.CONFIRMED))

    def test_an_ordinary_pattern_is_answered_as_it_always_was(self):
        v = self.verify("^hel", "hello")           # the output is what the finding says the requirement demands
        self.assertEqual((v.status, v.observed), (V.NOT_REPRODUCED, "SATISFIED"), v)
        v = self.verify("^xyz", "hello")           # it is not: the finding reproduces
        self.assertEqual((v.status, v.observed), (V.CONFIRMED, "REFUTED"), v)


class EveryPatternClassifierTakesNoPatternReCannotCompile(unittest.TestCase):
    """The other place a model's or a spec author's pattern meets the kernel is `re.compile`, in the classifier of the two
    probes that take one (`cli_invocation`'s `regex` shape, `file_artifact`'s `grep`). `re` refuses a pattern in three
    ways — `re.error`, `OverflowError` (`a{4294967296}`), `RecursionError` (2,000 nested groups) — and a classifier
    answers "the class, or None when this probe cannot give it a meaning", never an exception: `file_artifact`'s caught
    `re.error` only, so static admission and `aisef bundle coverage` (which call it on an authored spec, with no guard of
    their own) ended in a traceback. A pattern that compiles is searched in a worker; the compile itself is made here, in the
    classifier, in the kernel's process, with no deadline. Its cost is linear in the pattern's size, but the constant is the
    pattern's: a megabyte of plain letters took 0.6 s, and `(?i)` with a thousand `[\\u0000-\\U0010ffff]` (19 KB) took 3.7 s,
    76 KB of them 15 s (measured, CPython 3.14.7, macOS). What bounds it is the size of the reply the pattern came in,
    not a clock; whether to bound it otherwise is the owner's (decision D4 of the review-limits lane's report)."""

    BAD = ("(", "[", "a{2,1}", "(?P=n)", "\\", "(?z)", "a{4294967296}", "(" * 2000 + "a" + ")" * 2000)
    GOOD = ("hel+o", "^ok$", "(a+)b", "a{2,3}", ".*", "[0-9]+", "(?i)x", EVIL)

    @staticmethod
    def grep_class(pattern):
        return fa.observation_class({"matches": 0, "within_s": 5}, {"grep": pattern})

    @staticmethod
    def regex_class(pattern):
        return ci.observation_class({"exit_code": 0, "stdout": {"regex": pattern}, "within_s": 5}, {"argv": []})

    def test_a_pattern_re_cannot_take_is_no_class_in_either_probe(self):
        for pattern in self.BAD:
            with self.subTest(pattern[:12]):
                self.assertIsNone(self.grep_class(pattern))
                self.assertIsNone(self.regex_class(pattern))

    def test_a_pattern_it_takes_is_a_class_in_both(self):
        for pattern in self.GOOD:
            with self.subTest(pattern):
                self.assertEqual((self.grep_class(pattern), self.regex_class(pattern)), ("grep_count", "exits_streams"))

    def test_the_spec_class_of_the_grep_is_none_too(self):
        from aisef2.product.spec import ProductProofSpec
        for pattern in (*self.BAD, "x"):
            s = ProductProofSpec.create(
                contract_id="BC-G", probe_id=fa.PROBE_ID, probe_digest=fa.DIGEST,
                probe_input={"subject": {"kind": "file_artifact", "locator": "path:app"}, "stimulus": {"grep": pattern},
                             "observable": {"matches": 0, "within_s": 5}, "subject_absence": "REQUIRES_SUBJECT"},
                candidate_expectation=S, compiler_id="test", compiler_digest="c" * 64)
            with self.subTest(pattern[:12]):
                self.assertEqual(fa.spec_class(s), None if pattern in self.BAD else "grep_count")


if __name__ == "__main__":
    unittest.main()
