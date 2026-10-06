"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/adapters.py's V2.1 mutation targets, each class named
by the target and the mutants it kills. In the kill set of exactly the targets it kills (validation/v2/mutation.py)."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402


class _Reviewer(unittest.TestCase):
    """A Reviewer over the two-story calc bundle and its repository (no test of its own)."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 2}}
                                         if proj is ControlProjection.STORY_STATE else None)


class ReviewerModel(_Reviewer):
    """Reviewer._model — "L137 string 'reviewer ' emptied", "L138 string '.reviewer.' emptied", "L139 string 'reviewer'
    emptied": the model review's session is the reviewer's by the title the client is run with (`--title`), by the name
    of its evidence log (the run's sessions/ directory) and by the role its session record carries into RUN.json."""

    def test_the_review_session_is_titled_logged_and_recorded_as_the_reviewer_s(self):
        calls = []

        def fake(name, prompt, cwd, log, timeout_s, **kw):
            calls.append((name, log.name))
            return {"exit": 0, "timed_out": False, "stopped": None, "started": True, "error": None,
                    "text": '{"findings": []}', "turns": 1, "tokens": {"input": 1, "output": 1}, "seconds": 0.0, "log": log.name}
        rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)
        with mock.patch.object(client, "session", fake):
            found, s, _ = rev._model(types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo")), 3)
        self.assertEqual(found, [])
        self.assertEqual(calls, [("reviewer S1", "S1.reviewer.3.jsonl")])
        self.assertEqual((s["role"], s["story_id"], s["attempt"], s["log"]), ("reviewer", "S1", 3, "S1.reviewer.3.jsonl"))
        self.assertEqual(rev.sessions, [s])


class ReviewerVerify(_Reviewer):
    """Reviewer._verify — "L233 string 'no reproducer: the finding states no observable behaviour' emptied": a finding
    with no reproducer is UNVERIFIABLE, and the reason the run records for the operator (finding.verification.why) says
    why; no probe is run for it."""

    def test_a_finding_without_a_reproducer_is_unverifiable_for_a_stated_reason_and_runs_nothing(self):
        rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)
        with mock.patch.object(ad.review_verify, "verify", side_effect=AssertionError("no probe for a finding without one")):
            for finding in ({"id": "F1"}, {"id": "F2", "reproducer": "run it"}, {"id": "F3", "reproducer": None}):
                with self.subTest(finding=finding):
                    v = rev._verify(finding, str(self.tmp / "repo"), "a" * 40)
                    self.assertEqual((v.status, v.reason), (ad.review_verify.UNVERIFIABLE,
                                                            "no reproducer: the finding states no observable behaviour"))


class ReviewerInit(_Reviewer):
    """Reviewer.__init__ — "L104 Or swapped" (`sys.executable or interpreter`): the interpreter the run gives the review is
    the one its probes run under (app/run: the run's probe interpreter, V2.1 A1); without one, this Python."""

    def test_the_verification_runs_the_probe_under_the_interpreter_the_run_gave(self):
        seen = []

        def verify(finding, **kw):
            seen.append(kw["interpreter"])
            return ad.review_verify.Verification(ad.review_verify.UNVERIFIABLE, "stub")
        finding = {"id": "F1", "reproducer": {"kind": "python_callable"}}
        with mock.patch.object(ad.review_verify, "verify", verify):
            ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5, interpreter="/opt/run/bin/python3")._verify(
                finding, str(self.tmp / "repo"), "a" * 40)
            ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)._verify(finding, str(self.tmp / "repo"), "a" * 40)
        self.assertEqual(seen, ["/opt/run/bin/python3", sys.executable])


if __name__ == "__main__":
    unittest.main()
