"""V2.1 (owner decision 2026-10-15, PM-13) — the regex loop of `grep_count` runs in a worker process under the harness
watchdog, and a worker that does not give valid facts inside it is UNRUNNABLE, never a verdict.

Before this change `grep_facts` ran `pattern.search(line)` in the probe's own process: a pattern with nested
quantifiers over one long line took minutes to days, `timeouts_s.probe` bounded only git, and `within_s` was compared
after the loop had finished. Pinned here, by observation and by what happens to the processes:

* what a worker returns is what the in-process loop returned: the same facts, the same verdict — against a reference
  loop written in this file, over every kind of text the loop has a rule for (line breaks, marks, binary, not UTF-8,
  the location cap, many files);
* a pattern that cannot finish is UNRUNNABLE (ENVIRONMENT), whatever M and whichever `subject_absence`, the file, the
  line and the head of the pattern named and the way out said; it returns in about the deadline;
* the process range is emptied: the worker, a grandchild of it, a worker that ignores the polite signals — and a
  process of the host that is not in the range, whatever its command line says, is not touched;
* the deadline covers the whole operation, the start of the worker included; nothing is retried;
* a worker that crashes, ends by a signal, writes nothing, writes what is not JSON, writes the wrong shape or too much,
  or cannot be started is UNRUNNABLE with a reason of its own;
* the worker is given bytes and a pattern and nothing else: its environment, its directory, its request, its source.
"""

from __future__ import annotations

import ast
import codecs
import contextlib
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement, MeasurementPoint, ObligationRole, SubjectAbsence  # noqa: E402
from aisef2.control.owner import FailureCode, Owner  # noqa: E402
from aisef2.control.routing import row_for  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, Unrunnable  # noqa: E402
from aisef2.runtime import process_range as PR  # noqa: E402
from tests.v2 import test_c2_file_artifact as base  # noqa: E402   (helpers only: its test classes are not imported)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
DECIDABLE, REQUIRES = SubjectAbsence.ABSENCE_IS_DECIDABLE, SubjectAbsence.REQUIRES_SUBJECT
P = fa.FileArtifactProbe()
FULL = ExecutionEnv(sys.executable, 60.0, Enforcement.PARTIAL)
SHORT = ExecutionEnv(sys.executable, 1.5, Enforcement.PARTIAL)
BOM = codecs.BOM_UTF8
#: a pattern that does not finish on a line of a few dozen letters and a mark: catastrophic backtracking
EVIL = r"^(\w+\s?)*$"
EVIL_LINE = b"a" * 40 + b"!\n"
posix = unittest.skipUnless(os.name == "posix", "the ladder of signals and the process groups are POSIX")


def spec(locator: str, matches: int, pattern: str, absence=DECIDABLE, suffixes=None):
    stim = {"grep": pattern, **({"suffixes": suffixes} if suffixes is not None else {})}
    return base.spec(locator, {"matches": matches}, stim, absence=absence)


def reference(pattern: str, files: list) -> dict:
    """The loop as it always was, in process: written here, for comparison only."""
    rx = re.compile(pattern)
    matches, skipped, where = 0, [], []
    for rel, data in files:
        if b"\0" in data:
            skipped.append(rel)
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return {"present": True, "undecodable": rel, "skipped_binary": skipped}
        for n, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches += 1
                if len(where) < 50:
                    where.append([rel, n])
    return {"present": True, "files": len(files), "matches": matches, "skipped_binary": skipped, "locations": where}


class Tmp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm13-")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.dir = pathlib.Path(cls._tmp.name)

    def tree(self, name: str, files: dict) -> RevisionRef:
        root = self.dir / name
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        return RevisionRef("0" * 40, str(root))

    def work(self) -> str:
        return tempfile.mkdtemp(dir=self.dir)


@contextlib.contextmanager
def worker(text: str):
    """The worker script replaced by a stand-in (protocol: argv[1:4] = request, result, progress)."""
    with mock.patch.object(fa, "GREP_WORKER", text):
        yield


def alive(pid: int) -> bool:
    return pid in PR.process_table()


def counting(made: list):
    """ProcessRange, recording the name of every range the probe makes."""
    class Counting(PR.ProcessRange):
        def __init__(self, *a, **k):
            made.append(a[0])
            super().__init__(*a, **k)
    return Counting


class SameFacts(Tmp):
    """The facts of the worker are the facts of the in-process loop, byte for byte, whatever the text."""

    FILES = [
        ("plain.txt", b"alpha\nbeta telemetry\ngamma\n"),
        ("crlf.txt", b"one\r\ntelemetry two\r\nthree\r\n"),
        ("cr.txt", b"a\rtelemetry\rb\r"),
        ("breaks.txt", "x\x0bytelemetry\x0cz\x1c\x1d\x1e\x85telemetry telemetry end".encode("utf-8")),
        ("marked.txt", BOM + b"telemetry first\nsecond\n"),
        ("midmark.txt", b"ok\n" + BOM + b"telemetry\n"),
        ("empty.txt", b""),
        ("only-mark.txt", BOM),
        ("binary.bin", b"\x00\x01telemetry"),
        ("binary2.bin", b"telemetry\x00"),
        ("unicode.txt", "naïve télémétrie\nTELEMETRY\n日本語 telemetry\n".encode("utf-8")),
        ("noeol.txt", b"telemetry"),
        ("many.txt", b"".join(b"telemetry %d\n" % i for i in range(60))),
        ("blank.txt", b"\n\n\n"),
    ]
    LATIN = ("latin1.txt", b"caf\xe9 telemetry\n")
    PATTERNS = ("telemetry", r"^telemetry", r"telemetry$", r"(?i)telemetry", r"\bte\w+y\b", r"^$", r"[^\x00-\x7f]",
                "﻿", r"x", r"(?m)^")

    def test_every_pattern_over_the_set_and_a_few_over_every_file(self):
        d = self.work()
        for pattern in self.PATTERNS:
            for name, data in (self.FILES if pattern in ("telemetry", r"^$", r"[^\x00-\x7f]") else ()):
                with self.subTest(pattern=pattern, file=name):
                    self.assertEqual(fa.grep_facts(pattern, [(name, data)], timeout_s=60.0, work=d),
                                     reference(pattern, [(name, data)]))
            with self.subTest(pattern=pattern, files="all"):
                self.assertEqual(fa.grep_facts(pattern, self.FILES, timeout_s=60.0, work=d), reference(pattern, self.FILES))

    def test_the_first_file_that_is_not_utf8_ends_the_count_and_the_binaries_before_it_are_named(self):
        d = self.work()
        for position in (0, 1, 3, len(self.FILES)):
            files = [*self.FILES[:position], self.LATIN, *self.FILES[position:]]
            with self.subTest(position=position):
                got = fa.grep_facts("telemetry", files, timeout_s=60.0, work=d)
                self.assertEqual(got, reference("telemetry", files))
                self.assertEqual(got["undecodable"], "latin1.txt")
                self.assertNotIn("matches", got)
        # no file at all: the loop is vacuous and says so (the probe never asks it: a selection of none is absent)
        self.assertEqual(fa.grep_facts("x", [], timeout_s=60.0, work=d), reference("x", []))

    def test_the_locations_are_the_first_fifty_matching_lines_and_the_count_is_not_capped(self):
        d = self.work()
        files = [("a.txt", b"".join(b"hit\n" for _ in range(40))), ("b.txt", b"".join(b"hit\n" for _ in range(40)))]
        got = fa.grep_facts("hit", files, timeout_s=60.0, work=d)
        self.assertEqual((got["matches"], len(got["locations"])), (80, 50))
        self.assertEqual(got["locations"][0], ["a.txt", 1])
        self.assertEqual(got["locations"][-1], ["b.txt", 10])
        self.assertEqual(got, reference("hit", files))

    def test_names_travel_as_they_are_never_through_the_worker(self):
        d = self.work()
        name = "caf\udce9/日本 \"q\" \\ \n.txt"          # not UTF-8, quotes, a backslash, a newline
        got = fa.grep_facts("x", [(name, b"x\n")], timeout_s=60.0, work=d)
        self.assertEqual(got["locations"], [[name, 1]])

    def test_a_large_input_is_carried_whole(self):
        d = self.work()
        body = b"".join(b"line %06d telemetry\n" % i for i in range(120_000))        # ~2.5 MiB, 120k lines
        got = fa.grep_facts(r"^line \d{5}0 ", [("big.txt", body)], timeout_s=120.0, work=d)
        self.assertEqual((got["files"], got["matches"], got["locations"][-1]), (1, 12_000, ["big.txt", 491]))
        self.assertEqual(got, reference(r"^line \d{5}0 ", [("big.txt", body)]))

    def test_through_the_probe_the_verdict_is_the_one_the_loop_gave(self):
        ref = self.tree("verdicts", {"app/a.py": b"import telemetry\n", "app/b.py": b"ok\n", "app/c.md": b"telemetry\n"})
        for matches, suffixes, want in ((1, [".py"], S), (0, [".py"], R), (2, None, S), (2, [".md"], R)):
            for absence in (REQUIRES, DECIDABLE):
                with self.subTest(matches=matches, suffixes=suffixes, absence=absence.value):
                    s = spec("path:app", matches, "telemetry", absence, suffixes)
                    o = P.observe(s, ref, base.ENV)
                    self.assertEqual((o.kind, o.verdict), (K.OBSERVED, want))
                    self.assertEqual(run_probe(P, s, ref, base.ENV).result, Executed(want))


class CannotFinish(Tmp):
    """A pattern that cannot finish inside the watchdog is the harness's stop: UNRUNNABLE, ENVIRONMENT — never REFUTED
    (it would read as a defect of the developer's product), never a verdict of any kind."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ref = cls.tree_of("long", {"app/ok.txt": b"fine\n", "app/long.txt": b"a\nb\n" + EVIL_LINE + b"after\n"})

    @classmethod
    def tree_of(cls, name: str, files: dict) -> RevisionRef:
        root = cls.dir / name
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        return RevisionRef("0" * 40, str(root))

    def test_it_is_unrunnable_whatever_the_count_and_the_declaration_and_returns_in_about_the_deadline(self):
        for matches, absence in ((0, REQUIRES), (0, DECIDABLE), (1, REQUIRES), (3, DECIDABLE)):
            s = spec("path:app", matches, EVIL, absence, [".txt"])
            with self.subTest(matches=matches, absence=absence.value):
                began = time.monotonic()
                o = P.observe(s, self.ref, SHORT)
                self.assertLess(time.monotonic() - began, SHORT.timeout_s + 20)      # not a minute, not never
                self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                rec = run_probe(P, s, self.ref, SHORT)
                self.assertIsInstance(rec.result, Unrunnable)
                self.assertTrue(rec.result.detail.startswith("grep_count worker DEADLINE: "), rec.result.detail)

    def test_the_detail_names_the_file_the_line_the_pattern_and_the_way_out(self):
        s = spec("path:app", 0, EVIL, DECIDABLE, [".txt"])
        o = P.observe(s, self.ref, SHORT)
        text = o.detail
        self.assertIn("matching line 3 of 'app/long.txt'", text)           # long.txt sorts before ok.txt: read first
        self.assertIn(repr(EVIL), text)
        self.assertIn(f"({len(EVIL)} characters)", text)
        self.assertIn("1.5s: timeouts_s.probe", text)
        self.assertIn("never a verdict", text)
        self.assertIn("running it again changes nothing", text)
        self.assertIn("Simplify the pattern", text)
        self.assertIn("raise timeouts_s.probe on purpose", text)
        # a long pattern is cut at its head and its length said
        long = r"^(\w+\s?|" + "x" * 80 + r")*$"
        text = P.observe(spec("path:app", 0, long, DECIDABLE, [".txt"]), self.ref, SHORT).detail
        self.assertIn(repr(long[:fa._PATTERN_HEAD] + "..."), text)
        self.assertIn(f"({len(long)} characters)", text)

    def test_the_file_is_the_one_the_worker_was_on_not_the_first(self):
        ref = self.tree("second", {"d/a.txt": b"fine\nfine\n", "d/b.txt": EVIL_LINE})
        o = P.observe(spec("path:d", 0, EVIL, DECIDABLE, [".txt"]), ref, SHORT)
        self.assertEqual(o.kind, K.HARNESS_FAILED)
        self.assertIn("matching line 1 of 'd/b.txt'", o.detail)

    def test_a_stop_is_ENVIRONMENT_not_the_developers_and_never_a_retry_here(self):
        s = spec("path:app", 0, EVIL, REQUIRES, [".txt"])
        made = []
        with mock.patch.object(fa, "ProcessRange", counting(made)):
            rec = run_probe(P, s, self.ref, SHORT)
        self.assertEqual(made, ["grep_count worker"])                      # one worker for one observation
        for point in MeasurementPoint:
            for role in (None, *ObligationRole):
                with self.subTest(point=point.value, role=role and role.value):
                    route = row_for(rec.result, s, point, role)
                    self.assertEqual((route.failure.code, route.failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))

    def test_a_finished_loop_is_judged_by_its_own_window_as_before(self):
        # PM-12 is not moved: a read that completed is decided by within_s after it (the clock replaced in the module)
        s = spec("path:app", 0, "fine", DECIDABLE, [".txt"])
        with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=[0.0, base.W + 1.0]))):
            o = P.observe(s, self.ref, base.ENV)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))
        with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=[0.0, base.W - 1.0]))):
            o = P.observe(s, self.ref, base.ENV)
        self.assertEqual(o.kind, K.OBSERVED)


class RangeIsEmptied(Tmp):
    """What the worker started is the range's and the range is empty when the observation returns; what is not the
    range's is not touched."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.dir / "t"
        (root / "f.txt").parent.mkdir(parents=True)
        (root / "f.txt").write_bytes(b"x\n")
        cls.ref = RevisionRef("0" * 40, str(root))

    def run_with(self, text: str, deadline: float = 2.0):
        ranges = []
        probe = fa.FileArtifactProbe(on_range=ranges.append)
        with worker(text):
            o = probe.observe(spec("path:f.txt", 0, "x"), self.ref, ExecutionEnv(sys.executable, deadline, Enforcement.PARTIAL))
        return o, ranges

    def pids(self, name: str) -> dict:
        return json.loads(pathlib.Path(self.dir, name).read_text(encoding="utf-8"))

    def test_the_range_is_given_to_the_harness_hook_once_and_is_empty_after(self):
        o, ranges = self.run_with("import time\ntime.sleep(600)\n")
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertEqual(len(ranges), 1)
        r = ranges[0]
        self.assertEqual((r.members(), r.name), ([], "grep_count worker"))
        self.assertIsNotNone(r.target_pid)
        self.assertFalse(alive(r.target_pid))

    @posix
    def test_a_worker_that_ignores_the_polite_signals_is_ended_by_its_range(self):
        pidfile = self.dir / "ignorer.json"
        o, ranges = self.run_with(
            "import json, os, signal, sys, time\n"
            "signal.signal(signal.SIGINT, signal.SIG_IGN)\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"open({str(pidfile)!r}, 'w').write(json.dumps({{'worker': os.getpid()}}))\ntime.sleep(600)\n")
        self.assertEqual(o.kind, K.HARNESS_FAILED)
        self.assertIn("grep_count worker DEADLINE", o.detail)
        self.assertEqual([s["stage"] for s in ranges[0].ledger], ["cooperative", "terminate", "kill"])
        self.assertFalse(alive(self.pids("ignorer.json")["worker"]))

    @posix
    def test_a_grandchild_of_the_worker_is_the_ranges_and_is_ended_with_it(self):
        pidfile = self.dir / "grand.json"
        o, ranges = self.run_with(
            "import json, os, subprocess, sys, time\n"
            "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
            f"open({str(pidfile)!r}, 'w').write(json.dumps({{'worker': os.getpid(), 'grandchild': gc.pid}}))\n"
            "time.sleep(600)\n", deadline=3.0)
        self.assertEqual(o.kind, K.HARNESS_FAILED)
        pids = self.pids("grand.json")
        self.assertEqual(ranges[0].members(), [])
        self.assertFalse(alive(pids["worker"]))
        self.assertFalse(alive(pids["grandchild"]))

    @posix
    def test_a_process_that_is_not_the_ranges_is_not_touched_whatever_its_command_line_says(self):
        # a sentinel whose command line holds the worker's whole text: what a kill by pattern would take
        sentinel = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c",
                                     "import sys; sys.stdin.read()  # " + fa.GREP_WORKER.replace("\n", " ")],
                                    stdin=subprocess.PIPE)
        try:
            o, _ = self.run_with("import time\ntime.sleep(600)\n")
            self.assertEqual(o.kind, K.HARNESS_FAILED)
            self.assertIsNone(sentinel.poll())
            self.assertTrue(alive(sentinel.pid))
        finally:
            sentinel.stdin.close()
            sentinel.wait(timeout=30)

    def test_the_real_worker_leaves_nothing_behind_when_it_is_stopped(self):
        ref = self.tree("evil", {"f.txt": EVIL_LINE})
        ranges = []
        probe = fa.FileArtifactProbe(on_range=ranges.append)
        o = probe.observe(spec("path:f.txt", 0, EVIL), ref, SHORT)
        self.assertEqual(o.kind, K.HARNESS_FAILED)
        self.assertEqual((len(ranges), ranges[0].members()), (1, []))
        self.assertFalse(alive(ranges[0].target_pid))

    def test_no_range_is_made_for_what_has_no_regex_loop(self):
        ref = self.tree("noloop", {"a.py": b"import os\n", "docs/n.md": b"x\n"})
        ranges = []
        probe = fa.FileArtifactProbe(on_range=ranges.append)
        for s in (base.spec("path:a.py"), base.spec("path:a.py", {"sha256": "0" * 64}),
                  base.spec("path:a.py", {"matches": 0}, {"imports_outside": {"stdlib": True, "allowed": []}}),
                  spec("path:docs", 0, "x", suffixes=[".py"]),          # a selection of none: nothing to count over
                  spec("path:none", 0, "x")):
            probe.observe(s, ref, base.ENV)
        self.assertEqual(ranges, [])
        probe.observe(spec("path:a.py", 0, "x"), ref, base.ENV)
        self.assertEqual(len(ranges), 1)


class TheDeadlineCoversTheOperation(Tmp):
    def test_a_start_that_takes_the_whole_deadline_is_a_stop_even_when_the_worker_then_finishes(self):
        ref = self.tree("slowstart", {"f.txt": b"x\n"})

        class SlowStart(PR.ProcessRange):
            def start(self):
                super().start()
                time.sleep(2.2)          # the worker is long done by the time the harness looks
                return self
        with mock.patch.object(fa, "ProcessRange", SlowStart):
            o = P.observe(spec("path:f.txt", 0, "x"), ref, ExecutionEnv(sys.executable, 1.0, Enforcement.PARTIAL))
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertTrue(o.detail.startswith("grep_count worker DEADLINE: "), o.detail)
        self.assertIn("answered only after the watchdog had passed", o.detail)
        self.assertIn("nothing is taken from a late answer", o.detail)

    def test_the_same_observation_inside_the_deadline_is_a_verdict(self):
        ref = self.tree("fast", {"f.txt": b"x\n"})
        o = P.observe(spec("path:f.txt", 1, "x"), ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))


def lagging(start: float = 0.0, release: float = 0.0):
    """ProcessRange whose start and whose release each take `start` / `release` seconds more than they do: the cost of
    the mechanism that owns the worker, which the worker's own life does not include."""
    class Lagging(PR.ProcessRange):
        def start(self):
            time.sleep(start)
            return super().start()

        def release(self):
            time.sleep(release)
            super().release()
    return Lagging


class TheWindowIsTheReadsOwn(Tmp):
    """V2.1 review (r2-1). `within_s` is the window of the read (PM-12), decided after it: a worker process must not make
    a read that returned in a window return outside it. What it costs to own the worker — the range's start and its
    release, about a tenth of a second on a laptop and the greater part of what a worker costs — is not the read's; the
    worker's own life (its interpreter, the request, the loop, the result) is, as the in-process loop was."""

    WINDOW = 1.0
    LAG = 1.5       # more than the window, and many times what the same read takes without it

    def setUp(self):
        self.ref = self.tree("window", {"f.txt": b"x\n"})
        self.s = base.spec("path:f.txt", {"matches": 1}, {"grep": "x"}, window=self.WINDOW)

    def test_a_slow_start_of_the_range_does_not_expire_the_window_of_a_read_that_is_quick(self):
        with mock.patch.object(fa, "ProcessRange", lagging(start=self.LAG)):
            o = P.observe(self.s, self.ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_a_slow_release_of_the_range_does_not_expire_it_either(self):
        with mock.patch.object(fa, "ProcessRange", lagging(release=self.LAG)):
            o = P.observe(self.s, self.ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_the_life_of_the_worker_is_the_reads_own_time(self):
        # a worker that takes longer than the window before it does its work is a read that did not complete in it
        with worker(f"import time\ntime.sleep({self.LAG})\n" + fa.GREP_WORKER):
            o = P.observe(self.s, self.ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R), o.detail)
        self.assertTrue(o.detail.startswith(f"the {self.WINDOW:g}s observation window expired (grep_count); "), o.detail)

    def test_grep_facts_says_what_the_mechanism_cost_and_only_when_it_returns_facts(self):
        cost: list = []
        with mock.patch.object(fa, "ProcessRange", lagging(start=0.6, release=0.6)):
            facts = fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=30.0, work=self.work(), hosting=cost)
        self.assertEqual(facts["matches"], 1)
        self.assertEqual(len(cost), 1)
        self.assertTrue(1.2 <= cost[0] < 1.2 + 8, cost)      # both lags, and no more than the lags and the machine's own
        # the worker's own life is not what the mechanism cost
        cost = []
        with worker("import time\ntime.sleep(1.5)\n" + fa.GREP_WORKER):
            fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=30.0, work=self.work(), hosting=cost)
        self.assertEqual(len(cost), 1)
        self.assertTrue(0.0 <= cost[0] < 1.0, cost)
        # a failure gives no facts and so no cost; nothing is asked for by default
        cost = []
        with worker("import sys\nsys.exit(3)\n"):
            with self.assertRaises(fa.WorkerFailed):
                fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=30.0, work=self.work(), hosting=cost)
        self.assertEqual(cost, [])
        self.assertEqual(fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=30.0, work=self.work())["matches"], 1)

    def test_a_read_that_took_longer_than_its_window_is_still_refuted_by_it(self):
        # the clock of the read replaced in the module, as PM-12's own test does: what the range cost is taken out of
        # the read's time and the rest is judged by the window, here one the read's time (2 s) is past
        with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=[0.0, self.WINDOW + 1.0]))):
            o = P.observe(self.s, self.ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))


class FailureModes(Tmp):
    """Each way the worker can fail is UNRUNNABLE with a reason of its own, and is never retried."""

    CASES = {
        # reason: (stand-in worker, a phrase of the detail)
        "CRASHED/exit": ("import sys\nsys.exit(7)\n", "exited with status 7"),
        "CRASHED/traceback": ("1 / 0\n", "ZeroDivisionError"),
        "NO_RESULT/none": ("pass\n", "wrote no result"),
        "NO_RESULT/empty": ("import sys\nopen(sys.argv[2], 'w').close()\n", "its result is empty"),
        "BAD_RESULT/not json": ("import sys\nopen(sys.argv[2], 'w').write('{nope')\n", "is not JSON"),
        "BAD_RESULT/array": ("import sys\nopen(sys.argv[2], 'w').write('[1, 2]')\n", "a list, not an object"),
        "BAD_RESULT/missing": ("import sys\nopen(sys.argv[2], 'w').write('{\"files\": 1}')\n", "fields ['files']"),
        "BAD_RESULT/no skipped": ("import sys\nopen(sys.argv[2], 'w').write("
                                  "'{\"files\":1,\"matches\":0,\"locations\":[]}')\n",
                                  "fields ['files', 'locations', 'matches']"),
        "BAD_RESULT/matches type": ("import sys\nopen(sys.argv[2], 'w').write("
                                    "'{\"files\":1,\"matches\":\"0\",\"skipped_binary\":[],\"locations\":[]}')\n",
                                    "matches is not a count"),
        "BAD_RESULT/matches bool": ("import sys\nopen(sys.argv[2], 'w').write("
                                    "'{\"files\":1,\"matches\":true,\"skipped_binary\":[],\"locations\":[]}')\n",
                                    "matches is not a count"),
        "BAD_RESULT/matches negative": ("import sys\nopen(sys.argv[2], 'w').write("
                                        "'{\"files\":1,\"matches\":-1,\"skipped_binary\":[],\"locations\":[]}')\n",
                                        "matches is not a count"),
        "BAD_RESULT/files": ("import sys\nopen(sys.argv[2], 'w').write("
                             "'{\"files\":2,\"matches\":0,\"skipped_binary\":[],\"locations\":[]}')\n",
                             "files is not the number of files sent"),
        "BAD_RESULT/locations short": ("import sys\nopen(sys.argv[2], 'w').write("
                                       "'{\"files\":1,\"matches\":1,\"skipped_binary\":[],\"locations\":[]}')\n",
                                       "locations are not the first matching lines"),
        "BAD_RESULT/location index": ("import sys\nopen(sys.argv[2], 'w').write("
                                      "'{\"files\":1,\"matches\":1,\"skipped_binary\":[],\"locations\":[[5,1]]}')\n",
                                      "locations are not the first matching lines"),
        "BAD_RESULT/location line": ("import sys\nopen(sys.argv[2], 'w').write("
                                     "'{\"files\":1,\"matches\":1,\"skipped_binary\":[],\"locations\":[[0,0]]}')\n",
                                     "locations are not the first matching lines"),
        "BAD_RESULT/skipped index": ("import sys\nopen(sys.argv[2], 'w').write("
                                     "'{\"files\":1,\"matches\":0,\"skipped_binary\":[3],\"locations\":[]}')\n",
                                     "skipped_binary is not an ascending list of file indexes"),
        "BAD_RESULT/undecodable index": ("import sys\nopen(sys.argv[2], 'w').write("
                                         "'{\"undecodable\":9,\"skipped_binary\":[]}')\n", "undecodable is not a file index"),
        "BAD_RESULT/too large": ("import sys\nopen(sys.argv[2], 'w').write('[' + '0,' * 400000 + '0]')\n",
                                 "more than a request of 1 file(s) can produce"),
        "BAD_RESULT/extra field": ("import sys\nopen(sys.argv[2], 'w').write("
                                   "'{\"files\":1,\"matches\":0,\"skipped_binary\":[],\"locations\":[],\"x\":1}')\n",
                                   "fields ['files', 'locations', 'matches', 'skipped_binary', 'x']"),
        "BAD_RESULT/skipped type": ("import sys\nopen(sys.argv[2], 'w').write("
                                    "'{\"files\":1,\"matches\":0,\"skipped_binary\":5,\"locations\":[]}')\n",
                                    "skipped_binary is not an ascending list of file indexes"),
        "BAD_RESULT/skipped twice": ("import sys\nopen(sys.argv[2], 'w').write("
                                     "'{\"files\":1,\"matches\":0,\"skipped_binary\":[0,0],\"locations\":[]}')\n",
                                     "skipped_binary is not an ascending list of file indexes"),
        "BAD_RESULT/files bool": ("import sys\nopen(sys.argv[2], 'w').write("
                                  "'{\"files\":true,\"matches\":0,\"skipped_binary\":[],\"locations\":[]}')\n",
                                  "files is not the number of files sent"),
        "BAD_RESULT/locations type": ("import sys\nopen(sys.argv[2], 'w').write("
                                      "'{\"files\":1,\"matches\":1,\"skipped_binary\":[],\"locations\":7}')\n",
                                      "locations are not the first matching lines"),
        "BAD_RESULT/location shape": ("import sys\nopen(sys.argv[2], 'w').write("
                                      "'{\"files\":1,\"matches\":1,\"skipped_binary\":[],\"locations\":[[0]]}')\n",
                                      "locations are not the first matching lines"),
        "BAD_RESULT/location of a skipped file": (
            "import sys\nopen(sys.argv[2], 'w').write("
            "'{\"files\":1,\"matches\":1,\"skipped_binary\":[0],\"locations\":[[0,1]]}')\n",
            "locations are not the first matching lines"),
        "BAD_RESULT/undecodable bool": ("import sys\nopen(sys.argv[2], 'w').write("
                                        "'{\"undecodable\":true,\"skipped_binary\":[]}')\n", "undecodable is not a file index"),
    }

    if os.name == "posix":      # an exit by a signal: SIGTERM raised by the worker itself, default disposition
        CASES["CRASHED/signal"] = ("import signal\nsignal.raise_signal(signal.SIGTERM)\n", "ended by signal 15")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.dir / "t"
        root.mkdir()
        (root / "f.txt").write_bytes(b"x\n")
        cls.ref = RevisionRef("0" * 40, str(root))

    def test_each_failure_is_unrunnable_with_its_own_reason_and_is_run_once(self):
        for name, (text, phrase) in self.CASES.items():
            reason = name.split("/")[0]
            for absence in (REQUIRES, DECIDABLE):
                s = spec("path:f.txt", 0, "x", absence)
                made = []
                with self.subTest(case=name, absence=absence.value), worker(text), \
                        mock.patch.object(fa, "ProcessRange", counting(made)):
                    o = P.observe(s, self.ref, FULL)
                    self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
                    self.assertTrue(o.detail.startswith(f"grep_count worker {reason}: "), o.detail)
                    self.assertIn(phrase, o.detail)
                    self.assertEqual(len(made), 1)
                    self.assertIsInstance(run_probe(P, s, self.ref, FULL).result, Unrunnable)

    def test_a_worker_that_cannot_be_started_is_LAUNCH(self):
        s = spec("path:f.txt", 0, "x")
        with mock.patch.object(sys, "executable", str(self.dir / "no-such-python")):
            o = P.observe(s, self.ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertTrue(o.detail.startswith("grep_count worker LAUNCH: the worker did not start ("), o.detail)

        class Refusing(PR.ProcessRange):
            def start(self):
                raise PR.RangeError("the target did not start")
        with mock.patch.object(fa, "ProcessRange", Refusing):
            o = P.observe(s, self.ref, FULL)
        self.assertTrue(o.detail.startswith("grep_count worker LAUNCH: "), o.detail)
        self.assertIn("RangeError", o.detail)

    def test_a_range_whose_anchor_never_says_it_started_is_LAUNCH_and_leaves_nothing(self):
        # V2.1 review (r2-2): the watchdog does not shorten the range's own handshake (`ProcessRange.start` waits up to
        # 30 s for its target to say it started, whatever timeouts_s.probe is: said in the module's docstring). What it
        # ends as is pinned: the answer is given at once here, as the range gives it when its wait is over
        class Unanswered(PR.ProcessRange):
            def _line(self, timeout):
                return ("TIMEOUT", "") if timeout == 30.0 else super()._line(timeout)
        mine = os.getpid()

        def children() -> set:     # the anchors this process started (the table lists its own `ps` as a child too)
            return {pid for pid, row in PR.process_table().items() if row.ppid == mine and str(PR.ANCHOR) in row.command}
        before = children()
        with mock.patch.object(fa, "ProcessRange", Unanswered):
            o = P.observe(spec("path:f.txt", 0, "x"), self.ref, ExecutionEnv(sys.executable, 1.5, Enforcement.PARTIAL))
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertTrue(o.detail.startswith("grep_count worker LAUNCH: the worker did not start (RangeError)"), o.detail)
        self.assertEqual(children() - before, set())       # the anchor was ended and reaped: nothing of this one is left

    def test_a_range_that_ends_without_saying_how_is_CRASHED_not_a_deadline(self):
        class Silent(PR.ProcessRange):
            def wait(self, timeout=None):
                return None              # the report of the range closed before the watchdog: no exit status
        with mock.patch.object(fa, "ProcessRange", Silent):
            o = P.observe(spec("path:f.txt", 0, "x"), self.ref, FULL)
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertTrue(o.detail.startswith("grep_count worker CRASHED: the process range ended without reporting "),
                        o.detail)

    def test_a_request_that_cannot_be_written_is_INPUT(self):
        blocker = self.dir / "a-file"
        blocker.write_bytes(b"")
        with self.assertRaises(fa.WorkerFailed) as caught:
            fa.grep_facts("x", [("f", b"x")], timeout_s=5.0, work=str(blocker / "under"))
        self.assertEqual(caught.exception.reason, "INPUT")
        self.assertTrue(str(caught.exception).startswith("grep_count worker INPUT: the request cannot be written ("))

    def test_the_reasons_are_a_closed_set_and_a_failure_is_a_refusal_of_the_harness(self):
        self.assertEqual(fa.WORKER_REASONS, ("DEADLINE", "LAUNCH", "CRASHED", "NO_RESULT", "BAD_RESULT", "INPUT"))
        self.assertTrue(issubclass(fa.WorkerFailed, fa.Refused))
        for name in self.CASES:
            self.assertIn(name.split("/")[0], fa.WORKER_REASONS)


class TheResultIsDataFromAnotherProcess(unittest.TestCase):
    """`_worker_facts`, `_said`, `_stopped` and the size cap, pure: the shapes a result may have and every way it may
    not (no process is started: the cases that need one are FailureModes)."""

    RELS = ["a.py", "sub/b.py", "c.txt"]

    def test_the_two_shapes_a_worker_writes_are_the_facts_with_the_files_named(self):
        self.assertEqual(fa._worker_facts({"files": 3, "matches": 2, "skipped_binary": [1], "locations": [[0, 4], [2, 1]]},
                                          self.RELS),
                         {"present": True, "files": 3, "matches": 2, "skipped_binary": ["sub/b.py"],
                          "locations": [["a.py", 4], ["c.txt", 1]]})
        self.assertEqual(fa._worker_facts({"undecodable": 2, "skipped_binary": [0, 1]}, self.RELS),
                         {"present": True, "undecodable": "c.txt", "skipped_binary": ["a.py", "sub/b.py"]})
        self.assertEqual(fa._worker_facts({"files": 0, "matches": 0, "skipped_binary": [], "locations": []}, []),
                         {"present": True, "files": 0, "matches": 0, "skipped_binary": [], "locations": []})
        # more matches than locations are kept: the count is not capped, the locations are the first fifty
        fifty = [[0, n] for n in range(1, fa._LOCATIONS + 1)]
        self.assertEqual(fa._worker_facts({"files": 3, "matches": 70, "skipped_binary": [], "locations": fifty},
                                          self.RELS)["matches"], 70)

    def test_every_other_shape_is_a_bad_result_with_its_reason(self):
        good = {"files": 3, "matches": 1, "skipped_binary": [], "locations": [[0, 1]]}
        bad = {
            "not an object": [1],
            "a field short": {k: v for k, v in good.items() if k != "locations"},
            "a field over": {**good, "extra": 0},
            "both shapes at once": {**good, "undecodable": 0},
            "matches a string": {**good, "matches": "1"},
            "matches a float": {**good, "matches": 1.0},
            "matches a bool": {**good, "matches": True},
            "matches below zero": {**good, "matches": -1, "locations": []},
            "files not the request's": {**good, "files": 2},
            "files a bool": {**good, "files": True},
            "skipped a number": {**good, "skipped_binary": 1},
            "skipped past the files": {**good, "skipped_binary": [3]},
            "skipped below zero": {**good, "skipped_binary": [-1]},
            "skipped a float": {**good, "skipped_binary": [1.0]},
            "skipped a bool": {**good, "skipped_binary": [True]},
            "skipped out of order": {**good, "skipped_binary": [2, 1]},
            "skipped twice": {**good, "skipped_binary": [1, 1]},
            "locations not a list": {**good, "locations": {}},
            "locations fewer than the matches": {**good, "matches": 2},
            "locations more than the matches": {**good, "matches": 0},
            "a location of one": {**good, "locations": [[0]]},
            "a location of three": {**good, "locations": [[0, 1, 2]]},
            "a location not a list": {**good, "locations": ["0,1"]},
            "a location past the files": {**good, "locations": [[3, 1]]},
            "a location line zero": {**good, "locations": [[0, 0]]},
            "a location line a bool": {**good, "locations": [[0, True]]},
            "a location line a string": {**good, "locations": [[0, "1"]]},
            "a location of a skipped file": {**good, "skipped_binary": [0]},
            "locations out of order": {**good, "matches": 2, "locations": [[1, 1], [0, 1]]},
            "undecodable past the files": {"undecodable": 3, "skipped_binary": []},
            "undecodable a string": {"undecodable": "a.py", "skipped_binary": []},
            "undecodable with matches": {"undecodable": 0, "skipped_binary": [], "matches": 0},
        }
        for name, obj in bad.items():
            with self.subTest(name):
                with self.assertRaises(fa.WorkerFailed) as caught:
                    fa._worker_facts(obj, self.RELS)
                self.assertEqual(caught.exception.reason, "BAD_RESULT")
                self.assertTrue(str(caught.exception).startswith(
                    "grep_count worker BAD_RESULT: the result is not the facts of this request ("))
        # and the same shapes with their order kept are good: the checks above are not a blanket refusal
        self.assertEqual(fa._worker_facts({**good, "matches": 2, "locations": [[0, 1], [1, 1]]}, self.RELS)["matches"], 2)
        self.assertEqual(fa._worker_facts({**good, "matches": 2, "locations": [[0, 1], [0, 3]]}, self.RELS)["matches"], 2)

    def test_the_size_a_result_may_have_is_what_the_request_can_produce(self):
        cap = 65536 + 8 * (len("f.txt") + 8)
        facts = '{"files": 1, "matches": 0, "skipped_binary": [], "locations": []}'
        with tempfile.TemporaryDirectory(prefix="aisef2-pm13-cap-") as d:
            def run(size):
                text = ("import sys\nopen(sys.argv[2], 'w').write(" + repr(facts + " " * (size - len(facts))) + ")\n")
                with worker(text):
                    return fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=60.0, work=d)
            self.assertEqual(run(cap)["files"], 1)               # exactly what it can produce: taken
            with self.assertRaises(fa.WorkerFailed) as caught:
                run(cap + 1)
            self.assertEqual(caught.exception.reason, "BAD_RESULT")
            self.assertIn(f"the result is {cap + 1} bytes", str(caught.exception))
            self.assertIn(f"({cap})", str(caught.exception))

    def test_what_the_worker_said_is_the_tail_of_its_output_cut_and_never_a_crash(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-pm13-log-") as d:
            log = pathlib.Path(d, "worker.log")
            self.assertEqual(fa._said(str(log)), "")                      # no file
            log.write_bytes(b"")
            self.assertEqual(fa._said(str(log)), "")                      # nothing printed
            log.write_bytes(b"  \n")
            self.assertEqual(fa._said(str(log)), "")
            log.write_bytes(b"Traceback\nZeroDivisionError: x\n")
            self.assertEqual(fa._said(str(log)), ": " + repr("Traceback\nZeroDivisionError: x"))
            log.write_bytes(b"A" * 1000 + b"END")
            said = fa._said(str(log))
            self.assertEqual(said, ": " + repr("A" * 297 + "END"))          # the last 300 bytes
            log.write_bytes(b"ok \xff\xfe tail")
            self.assertEqual(fa._said(str(log)), ": " + repr("ok \ufffd\ufffd tail"))

    def test_where_the_worker_was_is_read_from_its_mark_and_the_pattern_is_cut_at_its_head(self):
        files = [("a.py", b""), ("sub/b.py", b""), ("c.txt", b"")]
        with tempfile.TemporaryDirectory(prefix="aisef2-pm13-mark-") as d:
            mark = pathlib.Path(d, "progress")

            def said(at, line, pattern="x", finished=None, write=True):
                if write:
                    mark.write_bytes(struct.pack("<II", at, line))
                return fa._stopped(pattern, files, str(mark), 2.5, finished)
            self.assertIn("before it began on the first file", said(0, 0))
            self.assertIn("reading 'a.py'", said(1, 0))
            self.assertIn("reading 'sub/b.py'", said(2, 0))
            self.assertIn("matching line 7 of 'sub/b.py'", said(2, 7))
            self.assertIn("matching line 1 of 'c.txt'", said(3, 1))
            self.assertIn("before it began on the first file", said(4, 1))       # past the files: no name is made up
            mark.write_bytes(b"\x01")                                             # a mark that is not eight bytes
            self.assertIn("before it began on the first file", said(0, 0, write=False))
            gone = fa._stopped("x", files, str(pathlib.Path(d, "no-such-mark")), 2.5, None)    # no mark at all
            self.assertIn("before it began on the first file", gone)
            text = said(2, 7, "x" * 40)
            self.assertIn(f"pattern {'x' * 40!r} (40 characters)", text)       # exactly the head: not cut, no dots
            text = said(2, 7, "x" * 41)
            self.assertIn(f"pattern {'x' * 40 + '...'!r} (41 characters)", text)
            self.assertTrue(text.startswith("the regex loop did not finish within the harness watchdog (2.5s: "))
            late = said(2, 7, finished=3.26)
            self.assertTrue(late.startswith("the worker answered only after the watchdog had passed (3.3s, start "
                                            "included; nothing is taken from a late answer): the harness watchdog (2.5s"),
                            late)

    def test_the_environment_given_is_exactly_the_allowlist_present_in_the_host(self):
        host = {"SYSTEMROOT": "C:/W", "SystemRoot": "C:/W", "WINDIR": "C:/W", "TEMP": "/te", "TMP": "/tm", "TMPDIR": "/t",
                "PATH": "/p", "HOME": "/h", "PYTHONPATH": "/x", "GIT_DIR": "/g"}
        with mock.patch.dict(os.environ, host, clear=True):
            self.assertEqual(fa._worker_env(), {k: host[k] for k in ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR")})
        with mock.patch.dict(os.environ, {"PATH": "/p", "TMPDIR": "/t"}, clear=True):
            self.assertEqual(fa._worker_env(), {"TMPDIR": "/t"})
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(fa._worker_env(), {})


class WhatTheWorkerIsGiven(Tmp):
    """The worker is a harness script on bytes: its environment, its directory, its request, its source."""

    PROBE = (
        "import json, os, sys\n"
        "out = {'env': sorted(os.environ), 'cwd': os.getcwd(), 'argv': sys.argv[1:], 'prefix': sys.flags.isolated,\n"
        "       'no_site': sys.flags.no_site, 'no_bytecode': sys.flags.dont_write_bytecode,\n"
        "       'request': open(sys.argv[1], 'rb').read().decode('latin-1')}\n"
        "open(%r, 'w').write(json.dumps(out))\n"
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out = cls.dir / "seen.json"
        root = cls.dir / "checkout"
        root.mkdir()
        (root / "f.txt").write_bytes(b"x\n")
        cls.root = str(root)
        text = cls.PROBE % str(cls.out) + fa.GREP_WORKER      # then the real work: the observation is normal
        with worker(text):
            cls.o = P.observe(spec("path:f.txt", 1, "x"), RevisionRef("0" * 40, cls.root), FULL)
        cls.seen = json.loads(cls.out.read_text(encoding="utf-8"))

    def test_the_observation_is_the_normal_one(self):
        self.assertEqual((self.o.kind, self.o.verdict), (K.OBSERVED, S))

    def test_the_environment_is_the_allowlist_and_nothing_of_the_hosts_secrets(self):
        # LC_CTYPE: set by CPython itself (locale coercion); __CF_USER_TEXT_ENCODING: put there by macOS for any process
        allowed = {"SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
        self.assertLessEqual(set(self.seen["env"]), allowed)
        with mock.patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "s3cret", "GIT_DIR": "/x", "PYTHONPATH": "/evil",
                                          "HOME": "/home/x", "PATH": "/bin"}):
            self.assertLessEqual(set(fa._worker_env()), {"SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR"})

    def test_it_runs_isolated_without_site_and_writes_no_bytecode(self):
        self.assertEqual((self.seen["prefix"], self.seen["no_site"], self.seen["no_bytecode"]), (1, 1, 1))

    def test_its_directory_is_the_evaluations_never_the_checkout(self):
        self.assertIn("aisef2-file-artifact-", self.seen["cwd"])
        self.assertFalse(os.path.realpath(self.seen["cwd"]).startswith(os.path.realpath(self.root)))

    def test_its_request_holds_the_pattern_the_sizes_and_the_bytes_and_no_path(self):
        head, _, blob = self.seen["request"].encode("latin-1").partition(b"\n")
        self.assertEqual(json.loads(head), {"pattern": "x", "sizes": [2], "locations": 50})
        self.assertEqual(blob, b"x\n")
        self.assertNotIn(self.root, self.seen["request"])
        self.assertEqual(len(self.seen["argv"]), 3)         # request, result, progress: paths of the evaluation directory
        self.assertTrue(all("aisef2-file-artifact-" in a for a in self.seen["argv"]))

    def test_its_source_is_stdlib_only_with_no_clock_no_stdout_and_nothing_of_aisef(self):
        tree = ast.parse(fa.GREP_WORKER)
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"json", "mmap", "os", "re", "struct", "sys"})
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn("print", calls)
        self.assertNotIn("exec", calls)
        self.assertNotIn("eval", calls)
        self.assertNotIn("__import__", calls)
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn("stdout", attrs)
        # it is a module-level string of this file, so the bytes that run are the bytes EXECUTION_DIGEST hashes
        module = ast.parse((ROOT / "aisef2" / "probe" / "file_artifact.py").read_text(encoding="utf-8"))
        bound = [n for n in module.body if isinstance(n, ast.Assign) and [t.id for t in n.targets] == ["GREP_WORKER"]]
        self.assertEqual(len(bound), 1)
        self.assertEqual(bound[0].value.value, fa.GREP_WORKER)
        self.assertIn("probe/file_artifact.py", fa.PROBE_SOURCES)


if __name__ == "__main__":
    unittest.main()
