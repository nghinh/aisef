"""V2.1 (owner decision of 2026-10-15, item 4 — `within_s`): the edge of the observation window, where the published
definition and the code agree.

What is published, and where:

* RFC §9.2 (docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md): the subject did not complete or emit the expected observation
  "within the bounded observation window the `ProductProofSpec` declares"; the verdict of an expired window is the one the
  spec's observable assigns to it.
* `file_artifact`'s module docstring and PM-12 (docs/v2.1/decisions/B03-R3-PROBE-MODULE-FINDINGS.md): a read is judged by
  its own window *after* it, and is REFUTED when it **took longer than** `within_s` — so a read that took exactly the
  window is within it; what it costs to own the grep worker (its range's start and release: `hosting`) is not the
  read's time.
* The code: `file_artifact.py`, `expired = time.monotonic() - started - sum(hosting) > window` — strictly greater.

The three agree, and this file pins the edge they define: exactly the window is not expired, the least more is, the
start is the probe's own (not the clock's zero), and the hosting seconds are taken out before the comparison.

What is NOT pinned here, because nothing published defines it (the lane's report lists it for the owner): the edge of the
window of the probes that decide it by a timer (`cli_invocation`, `python_callable_v2`, `process_effect`): the controller
arms `threading.Timer(window)` and the answer and the timer race for one lock, so a subject that answers at exactly the
window is a race, not a rule; and the window's relation to the stream cap, to a finite window the timer cannot hold
(`threading.TIMEOUT_MAX`) and to the reviewer's choice of it."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe import file_artifact as fa  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K  # noqa: E402
from tests.v2 import test_c2_file_artifact as FA  # noqa: E402   (helpers only: its test classes are not imported)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
W = FA.W
LEAST_MORE = 1e-6      # more than the window by less than anything a clock could be asked about, and exactly more


def hosted(seconds: float):
    """`grep_facts` as it answers when owning the worker cost `seconds`: the facts of a count of one matching line."""
    def grep_facts(pattern, files, *, timeout_s, work, on_range=None, hosting=None):
        hosting.append(seconds)
        return {"present": True, "files": len(files), "matches": 1, "skipped_binary": [],
                "locations": [[files[0][0], 1]]}
    return grep_facts


class TheEdgeOfTheReadsWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="aisef2-rl-window-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.repo = FA.Repo(pathlib.Path(cls.tmp.name) / "repo")
        cls.sha = cls.repo.commit({"app/VERSION": FA.V1, "app/a.txt": b"telemetry\n"})

    SPECS = {"exists": lambda: FA.spec("path:app/VERSION"),
             "content": lambda: FA.spec("path:app/VERSION", FA.content(FA.sha(FA.V1))),
             "grep_count": lambda: FA.spec("path:app", *FA.grep("telemetry", 1))}

    def observe(self, s, clock):
        """The probe's own clock replaced, as PM-12's tests do: the module reads it twice in `observe`, before the read
        and after it."""
        with mock.patch.object(fa, "time", mock.Mock(monotonic=mock.Mock(side_effect=clock))):
            return FA.P.observe(s, FA.at(self.repo.path, self.sha), FA.ENV)

    def test_a_read_that_took_exactly_the_window_is_within_it_and_the_least_more_is_not(self):
        """The worker of `grep_count` costs nothing here (`hosted(0.0)`): its real cost is taken out of the time (next test)."""
        with mock.patch.object(fa, "grep_facts", hosted(0.0)):
            for cls, make in self.SPECS.items():
                s = make()
                for took, kind, verdict in ((0.0, K.OBSERVED, S), (W - LEAST_MORE, K.OBSERVED, S), (W, K.OBSERVED, S),
                                            (W + LEAST_MORE, K.SUBJECT_DEADLINE, R)):
                    with self.subTest(cls=cls, took=took):
                        o = self.observe(s, [0.0, took])
                        self.assertEqual((o.kind, o.verdict), (kind, verdict), o.detail)

    def test_the_read_is_timed_from_its_own_start_not_from_the_clocks_zero(self):
        s = self.SPECS["exists"]()
        o = self.observe(s, [1234.5, 1234.5 + W])
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S))
        o = self.observe(s, [1234.5, 1234.5 + W + LEAST_MORE])
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R))

    def test_what_owning_the_worker_cost_is_taken_out_before_the_comparison(self):
        """PM-13 (the worker) with PM-12 (the window): `hosting` seconds of the read's time are the harness's. With them
        out, exactly the window is within it and the least more is not."""
        s = self.SPECS["grep_count"]()
        with mock.patch.object(fa, "grep_facts", hosted(3.0)):
            o = self.observe(s, [0.0, W + 3.0])
            self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
            o = self.observe(s, [0.0, W + 3.0 + LEAST_MORE])
            self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, R), o.detail)
            o = self.observe(s, [0.0, W + 2.0])     # less than the hosting alone: nothing of it is the read's
            self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_an_expired_window_is_a_subject_deadline_of_the_class_and_never_a_harness_failure(self):
        for cls, make in self.SPECS.items():
            with self.subTest(cls):
                o = self.observe(make(), [0.0, W + 1.0])
                self.assertEqual((o.kind, o.verdict), (K.SUBJECT_DEADLINE, fa.ON_DEADLINE[cls]), o.detail)
                self.assertTrue(o.detail.startswith(f"the {W}s observation window expired ({cls}); "), o.detail)


if __name__ == "__main__":
    unittest.main()
