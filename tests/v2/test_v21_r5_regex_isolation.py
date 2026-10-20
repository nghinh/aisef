"""V2.1 (owner decision of 2026-10-15, item 4; review of the review-limits lane: F1, F2, F6 and the controller stop): the
search of a `regex` shape is out of the subject's reach.

The first version of the worker (test_v21_r5_regex_worker.py) wrote its request and read its result in the evaluation
directory — the subject's parent directory, at names anybody could guess (`regex-stdout.request`) — while the subject's
range was still alive. A product that prints something, lingers and polls `..` could rewrite the pattern or the answer
(a finding that reproduces came back NOT_REPRODUCED, a spec REFUTED came back SATISFIED), and plant a link at one of
those names that the kernel then opened for writing and truncated (a file of the host overwritten). B1 exists to stop
exactly that class: what the subject controls is its own behaviour, never the facts or the verdict built from them.

Pinned here, on a real lingering product and on the order of events:

* the pattern's search is made after the subject's range is released: when the worker's range starts, nothing of the
  subject is alive (a subject that lingers on purpose included) — and it is a directory made then, with a name nobody
  chose, that holds the worker's request, result and output;
* a lingering subject that rewrites every file named like the worker's (`request`, `result`, the old names too) or
  plants links at them (to a file of the host) changes neither the verdict nor the victim file;
* a controller stop of the worker's range is an interruption (`ProbeInterrupted`, §9.3) — as it is for the subject's
  range — never a harness failure and never a verdict;
* the two copies of the worker contract (this probe's search, `file_artifact`'s grep, PM-13) cannot drift apart
  unnoticed: the same stand-in workers and the same clock give the same reason in both, at the deadline's edge too.

What this does not pin, said so: the capture files the facts name are still files of the evaluation directory that a
lingering subject can rewrite before its range is released (measured, an older limit of the probe, not of the search);
see the lane's report."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, ProbeInterrupted  # noqa: E402
from aisef2.runtime import process_range as PR  # noqa: E402
from tests.v2 import test_c2_cli_invocation as base  # noqa: E402   (helpers only: its test classes are not imported)
from tests.v2 import test_v21_r5_regex_worker as rw  # noqa: E402   (helpers only, likewise)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
posix = unittest.skipUnless(os.name == "posix", "the ladder of signals and the links are POSIX")
RUNS = unittest.skipUnless(os.name == "posix" or sys.platform == "win32", "the probe runs on both")

#: a product that prints what the pattern below does not take, then lingers (a non-daemon thread) and reaches for every
#: file of the evaluation directory the harness could have made for the search — wherever it is and whatever it is
#: named, the first version's names and this version's alike
TAMPER = '''
import os
import sys
import threading
import time

NAMES = ("request", "result", "worker.log", "regex-stdout.request", "regex-stdout.result", "regex-stdout.log",
         "regex-stderr.request", "regex-stderr.result", "regex-stderr.log")


def main(argv):
    mode, victim = argv[0], (argv[1] if len(argv) > 1 else None)
    sys.stdout.write("nothing special\\n")
    sys.stdout.flush()
    if mode == "symlink":
        for name in NAMES:       # a link at every name it could guess; the kernel opens the name for writing
            try:
                os.symlink(victim, os.path.join("..", name))
            except OSError:
                pass
        return 0

    def poll():
        end = time.monotonic() + 20
        while time.monotonic() < end:
            for here, _, names in os.walk(".."):
                for name in names:
                    if name not in NAMES:
                        continue
                    try:
                        with open(os.path.join(here, name), "r+b") as f:
                            if mode.startswith("request") and name.endswith("request"):
                                # the empty pattern is found anywhere, `(?!)` nowhere
                                f.write((b'{"pattern": "(?!)"}\\n' if mode.endswith("-no") else b'{"pattern": ""}\\n') + b" " * 64)
                            elif mode.startswith("result") and name.endswith("result"):
                                f.write(b"0" if mode.endswith("-no") else b"1")
                    except OSError:
                        pass
            time.sleep(0.001)
    threading.Thread(target=poll).start()
    return 0
'''
LINGERS = {**base.PRODUCT, "app/tamper.py": TAMPER}
SECRET = {"exit_code": 0, "stdout": {"regex": "^SECRET$"}}      # the product never prints it: the true verdict is REFUTED


class Lingering(base._Product):
    """`_Product` with the product that tampers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.at = base.RevisionRef(base.SHA, base.checkout(LINGERS))
        cls.probe = ci.CliInvocationProbe()

    def see(self, argv, observable=SECRET, *, window=10):
        s = base.spec("app.tamper:main", observable, {"argv": argv}, window=window)
        return self.probe.observe(s, self.at, base.env(20))


@RUNS
class ALingeringSubjectCannotChangeTheSearch(Lingering):
    def test_it_does_not_change_the_verdict_it_has_when_it_does_not_try(self):
        o = self.see(["quiet"])
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)

    def test_rewriting_the_workers_request_or_result_changes_nothing(self):
        for mode in ("request", "result"):
            for attempt in range(3):      # a race it would win sometimes is a race it wins
                with self.subTest(mode=mode, attempt=attempt):
                    o = self.see([mode])
                    self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)

    def test_a_pattern_that_is_in_the_output_is_still_found_while_it_tries_to_hide_it(self):
        # the other direction: the answer is the search's, not the subject's wish
        for mode in ("request-no", "result-no"):
            for attempt in range(3):
                with self.subTest(mode=mode, attempt=attempt):
                    o = self.see([mode], {"exit_code": 0, "stdout": {"regex": "^nothing special$"}})
                    self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    @posix
    def test_a_link_planted_where_the_harness_would_write_is_not_followed(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-rl-victim-") as d:
            victim = pathlib.Path(d, "victim.txt")
            victim.write_bytes(b"IMPORTANT-FILE-CONTENT\n")
            o = self.see(["symlink", str(victim)])
            self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
            self.assertEqual(victim.read_bytes(), b"IMPORTANT-FILE-CONTENT\n")

    def test_the_search_reads_no_file_the_subject_could_have_named(self):
        """Not one name of the first version is where the harness works now: the evaluation directory holds a directory
        made for the search, `regex-<random>`, and nothing named after the stream."""
        seen = []
        real = ci.search_in_worker

        def spying(pattern, data, *, work, **kw):
            try:
                return real(pattern, data, work=work, **kw)
            finally:
                seen.append(sorted(os.listdir(work)))
        with mock.patch.object(ci, "search_in_worker", spying):
            self.see(["quiet"])
        (names,) = seen
        self.assertEqual(len([n for n in names if n.startswith("regex-")]), 1, names)
        self.assertFalse([n for n in names if n.startswith(("regex-stdout", "regex-stderr"))
                          or n.endswith((".request", ".result"))], names)


@RUNS
class TheSearchStartsOnlyWhenNothingOfTheSubjectIsAlive(base._Product):
    """The order of events, on a subject that lingers on purpose (`linger`: a non-daemon thread that sleeps an hour)."""

    def test_the_subjects_range_is_empty_when_the_workers_starts(self):
        order = []
        real = PR.ProcessRange

        class Ordered(real):
            def start(self):
                if "regex" in self.name:
                    order.append(("worker starts; the subject's range holds", [(r.name, len(r.members())) for r in ranges
                                                                                if "regex" not in r.name]))
                return super().start()
        ranges = []

        def hook(name, argv, **kw):
            made = Ordered(name, argv, **kw)
            ranges.append(made)
            return made
        s = base.spec("app:__main__", {"exit_code": 0, "stdout": {"regex": "^x$"}}, {"argv": ["linger"]}, window=base.W)
        with mock.patch.object(ci, "ProcessRange", hook):
            o = ci.CliInvocationProbe().observe(s, self.at, base.env(20))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        (event,) = order
        self.assertEqual(event[1], [(f"probe {s.id}", 0)], "the subject still lived when the search began")
        self.assertTrue(ranges[0].ledger, "it lingered: the release had something to end")

    def test_the_verdict_is_decided_after_the_release_and_not_before(self):
        """`decide` hands back a function; `_observe_in` runs it after `release` (a subject that lingers is ended by it),
        and a verdict that is not a function is taken at once (the equality halves')."""
        events = []
        real = ci.CliInvocationProbe._observe_in

        def watching(self, work, spec_id, cls, locator, stim, observable, at, env, decide):
            def decide_(facts):
                chosen = decide(facts)
                events.append("decide")
                return (lambda: (events.append("verdict") or chosen())) if callable(chosen) else chosen
            return real(self, work, spec_id, cls, locator, stim, observable, at, env, decide_)
        released = []
        orig = PR.ProcessRange.release

        def release(self_):
            released.append("release" if "regex" not in self_.name else "worker release")
            events.append(released[-1])
            return orig(self_)
        s = base.spec("app:__main__", {"exit_code": 0, "stdout": {"regex": "^x$"}}, {"argv": ["linger"]}, window=base.W)
        with mock.patch.object(ci.CliInvocationProbe, "_observe_in", watching), \
                mock.patch.object(PR.ProcessRange, "release", release):
            o = ci.CliInvocationProbe().observe(s, self.at, base.env(20))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        self.assertEqual(events[:3], ["decide", "release", "verdict"], events)

    def test_the_workers_range_carries_the_probe_and_spec_name(self):
        """L1164: the regex worker's process range is named `probe <spec> regex <stream>` — the name the story scope
        journals as the acquired/released resource (proof.Ranged) and the name a leaked-range diagnostic prints. It
        names the probe and the spec it ran for, as the subject's own range does; a bare id is not that name."""
        ranges = []

        def hook(name, argv, **kw):
            made = PR.ProcessRange(name, argv, **kw)
            ranges.append(made)
            return made
        s = base.spec("app:__main__", {"exit_code": 0, "stdout": {"regex": "^x$"}}, {"argv": ["linger"]}, window=base.W)
        with mock.patch.object(ci, "ProcessRange", hook):
            o = ci.CliInvocationProbe().observe(s, self.at, base.env(20))
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
        worker_names = [r.name for r in ranges if "regex" in r.name]
        self.assertEqual(worker_names, [f"probe {s.id} regex stdout"], worker_names)


class ALater(unittest.TestCase):
    """`_Later`, the verdict `decide` leaves to after the release: what it makes of a search that gave no answer."""

    def test_a_verdict_is_an_observation_and_the_failure_of_a_search_is_a_stop_of_the_harness(self):
        o = ci._Later(lambda: S, "{}").settle()
        self.assertEqual((o.kind, o.verdict, o.detail), (K.OBSERVED, S, "{}"))

        def fails():
            raise ci.StreamSearchFailed("DEADLINE", "it did not finish")
        o = ci._Later(fails, "{}").settle()
        self.assertEqual((o.kind, o.verdict), (K.HARNESS_FAILED, None))
        self.assertEqual(o.detail, "regex search DEADLINE: it did not finish")

    def test_a_decision_that_is_a_verdict_is_taken_at_once_and_a_function_waits(self):
        run = type("Run", (), {"ledger": []})()
        facts = {"subject": "present", "exit_code": 0}
        got, kept = ci._concluded(run, facts, lambda f: S)
        self.assertEqual((got.kind, got.verdict, kept), (K.OBSERVED, S, facts))
        got, kept = ci._concluded(run, facts, lambda f: (lambda: R))
        self.assertIsInstance(got, ci._Later)
        self.assertEqual((got.settle().verdict, kept), (R, facts))

    def test_a_controller_stop_before_the_release_is_still_an_interruption(self):
        run = type("Run", (), {"ledger": [{"stage": "terminate", "signal": "SIGTERM"}], "returncode": -15})()
        with self.assertRaises(ProbeInterrupted):
            ci._concluded(run, {"subject": "present", "exit_code": 0}, lambda f: (lambda: S))


@posix
class AControllerStopOfTheSearchIsAnInterruption(rw.Work):
    """§9.3: the controller's own signal ledger is the one authority on who stopped a range. A worker whose range the
    controller signalled says nothing about the product, and nothing about the harness either: the observation was
    interrupted, as it is when the subject's range is."""

    def test_a_signal_in_the_workers_ledger_raises_the_interruption_and_the_range_is_released(self):
        class Stopped(PR.ProcessRange):
            released = 0

            def wait(self, timeout=None):
                self.ledger.append({"stage": "terminate", "signal": "SIGTERM", "at": 0.0})    # the scope's handler
                return super().wait(timeout)

            def release(self):
                Stopped.released += 1
                return super().release()
        with mock.patch.object(ci, "ProcessRange", Stopped):
            with self.assertRaises(ProbeInterrupted) as caught:
                rw.search("a", b"banana", work=self.work(), timeout=30.0)
        self.assertEqual(caught.exception.stage, "terminate")
        self.assertEqual(Stopped.released, 1)

    def test_a_worker_nobody_signalled_is_not_one(self):
        self.assertTrue(rw.search("a", b"banana", work=self.work()))
        with self.assertRaises(ci.StreamSearchFailed):         # its own release at the deadline is not a controller stop
            rw.search(rw.EVIL, rw.EVIL_LINE.encode("utf-8"), work=self.work(), timeout=1.0)

    @RUNS
    def test_through_the_probe_the_interruption_reaches_the_caller_not_a_verdict(self):
        class Stopped(PR.ProcessRange):
            def wait(self, timeout=None):
                if "regex" in self.name:
                    self.ledger.append({"stage": "terminate", "signal": "SIGTERM", "at": 0.0})
                return super().wait(timeout)
        at = base.RevisionRef(base.SHA, base.checkout(base.PRODUCT))
        s = base.spec("app:__main__", {"exit_code": 0, "stdout": {"regex": "^hello$"}}, {"argv": ["echo", "hello"]},
                      window=base.W)
        with mock.patch.object(ci, "ProcessRange", Stopped):
            with self.assertRaises(ProbeInterrupted):
                ci.CliInvocationProbe().observe(s, at, base.env(20))


class TheTwoWorkerContractsAgree(rw.Work):
    """F6: the search of a `regex` shape is a second, hand-kept copy of `file_artifact.grep_facts`' launch, wait, deadline
    and failure mapping (judged and kept: report of the lane). What keeps the copies from drifting is this: the same
    stand-in workers and the same clock give the same reason, and the same edge of the deadline, in both."""

    SCENARIOS = {
        "an exit status": ("import sys\nsys.exit(7)\n", "CRASHED"),
        "a traceback": ("1 / 0\n", "CRASHED"),
        "no result": ("pass\n", "NO_RESULT"),
        "an empty result": ("import sys\nopen(sys.argv[2], 'w').close()\n", "NO_RESULT"),
        "a hang": ("import time\ntime.sleep(600)\n", "DEADLINE"),
    }

    def both(self, text: str, *, timeout: float = 2.0) -> tuple[str, str]:
        reasons = []
        with mock.patch.object(ci, "REGEX_WORKER", text), mock.patch.object(fa, "GREP_WORKER", text):
            for run in (lambda: rw.search("x", b"x\n", work=self.work(), timeout=timeout),
                        lambda: fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=timeout, work=self.work())):
                try:
                    run()
                    reasons.append("ANSWERED")
                except (ci.StreamSearchFailed, fa.WorkerFailed) as e:
                    reasons.append(e.reason)
        return tuple(reasons)

    def test_the_same_worker_stops_for_the_same_reason(self):
        for what, (text, reason) in self.SCENARIOS.items():
            with self.subTest(what):
                self.assertEqual(self.both(text), (reason, reason))

    @posix
    def test_a_signal_is_crashed_in_both(self):
        self.assertEqual(self.both("import signal\nsignal.raise_signal(signal.SIGTERM)\n"), ("CRASHED", "CRASHED"))

    def test_a_range_that_will_not_start_is_launch_in_both(self):
        broken = mock.Mock(return_value=mock.Mock(start=mock.Mock(side_effect=PR.RangeError("did not start"))))
        reasons = []
        with mock.patch.object(ci, "ProcessRange", broken), mock.patch.object(fa, "ProcessRange", broken):
            for run in (lambda: rw.search("x", b"x\n", work=self.work()),
                        lambda: fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=30.0, work=self.work())):
                with self.assertRaises((ci.StreamSearchFailed, fa.WorkerFailed)) as caught:
                    run()
                reasons.append(caught.exception.reason)
        self.assertEqual(reasons, ["LAUNCH", "LAUNCH"])

    def test_a_request_that_cannot_be_written_is_input_in_both(self):
        a_file = self.dir / "a-file"
        a_file.write_bytes(b"")
        reasons = []
        for run in (lambda: rw.search("x", b"x\n", work=str(a_file)),
                    lambda: fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=30.0, work=str(a_file))):
            with self.assertRaises((ci.StreamSearchFailed, fa.WorkerFailed)) as caught:
                run()
            reasons.append(caught.exception.reason)
        self.assertEqual(reasons, ["INPUT", "INPUT"])

    def test_the_edge_of_the_deadline_is_the_same(self):
        """An answer that took exactly the deadline is taken; one that took longer is no answer. Each module's clock
        replaced in the module, as their own tests do (this one reads it three times, the grep's four)."""
        timeout = 5.0
        for took, answered in ((0.0, True), (timeout, True), (timeout + 0.001, False)):
            with self.subTest(took=took):
                got = []
                with mock.patch.object(ci, "_monotonic", mock.Mock(side_effect=[0.0, 0.0, took])):
                    try:
                        rw.search("x", b"x\n", work=self.work(), timeout=timeout)
                        got.append("ANSWERED")
                    except ci.StreamSearchFailed as e:
                        got.append(e.reason)
                with mock.patch.object(fa, "_monotonic", mock.Mock(side_effect=[0.0, 0.0, 0.0, took])):
                    try:
                        fa.grep_facts("x", [("f.txt", b"x\n")], timeout_s=timeout, work=self.work())
                        got.append("ANSWERED")
                    except fa.WorkerFailed as e:
                        got.append(e.reason)
                self.assertEqual(got, ["ANSWERED"] * 2 if answered else ["DEADLINE"] * 2)

    def test_the_vocabulary_is_one(self):
        self.assertEqual(set(ci.SEARCH_REASONS), set(fa.WORKER_REASONS))


if __name__ == "__main__":
    unittest.main()
