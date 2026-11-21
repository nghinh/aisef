"""C4 (W1-DESIGN §7, MASTER-CHECKLIST C4): the qualifying test for the roadmap's no-op short circuit.

A developer attempt that changes nothing leaves the candidate at its base. The existing stage flow already spends
nothing more on it: the proof at the candidate fails first, and quality, review and scan run only while no failure is
set (aisef2/orchestrate/story_runner.py `_attempt`). So a candidate==base attempt makes 0 reviewer, 0 scanner and 0
quality calls, and C4 closes WONT_DO on the owner's directive (the closure text is the integrator's). Each count is
read where the stage leaves it: the adapter call, the journal row the stage writes, the session log. The control (a
developer that writes the story) shows every counter live, so a 0 is a measurement, not a dead counter.

Disclosed beside it, not C4's case: a story with no developer work (every obligation PRE_SATISFIED at the parent,
K-NOWORK-001) also has candidate == parent, and its review and scan do run. Pinned as measured; whether that call is
wanted is a question for the C4 closure, not decided here. No existing test file is edited (§2.8).
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad, bundle  # noqa: E402
from aisef2.arch.enums import EventType as T, Owner  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang (as in test_app_run)")
class CandidateEqualsBase(e2e.ProductBase):
    def counted(self) -> tuple[dict, dict]:
        reviews, scans, real = [], [], ad.Reviewer.review

        def review(self_, scope, criteria):
            reviews.append(scope.story_id)
            return real(self_, scope, criteria)

        class Scanner(ad.NoScanner):
            def argv(self_, scope, report):
                scans.append(scope.story_id)
                return super().argv(scope, report)

        with mock.patch.object(ad.Reviewer, "review", review), mock.patch.object(ad, "scanner", Scanner):
            rec = self.execute()
        events = self.journal().events
        sessions = [p.name for p in (self.tmp / "out" / "sessions").glob("*.jsonl")]
        owners = [e.data["budget_owner"] for e in events if e.type == T.PROVIDER_REQUEST.value]
        self.candidates = {e.data["candidate"] for e in events if e.type == T.PROOF_VERIFIED.value}
        return rec, {
            "developer requests": owners.count(Owner.DEVELOPER.value),
            "reviewer calls": len(reviews),
            "reviewer requests": owners.count(Owner.REVIEW.value),
            "reviewer sessions": sum(".reviewer." in s for s in sessions),
            "scanner calls": len(scans),
            "scanner invocations": sum(e.type == T.TOOL_INVOKED.value and e.data["tool"] == Scanner.name for e in events),
            "quality assessments": sum(e.type == T.TESTS_ADEQUACY.value for e in events),
        }

    def test_a_candidate_equal_to_its_base_makes_no_reviewer_scanner_or_quality_call(self):
        self.mode("nothing")
        rec, n = self.counted()
        self.assertEqual(rec["delivery_verdict"], "FAIL")
        self.assertEqual(self.candidates, {self.baseline})      # every proof ran at candidate == base
        self.assertGreaterEqual(n.pop("developer requests"), 1)  # the developer ran: an attempt, not a refusal before it
        self.assertEqual(n, dict.fromkeys(n, 0))

    def test_the_control_a_developer_that_writes_the_story_is_assessed_reviewed_and_scanned(self):
        rec, n = self.counted()
        self.assertEqual(rec["delivery_verdict"], "PASS")
        self.assertNotIn(self.baseline, self.candidates)
        self.assertEqual(n, dict.fromkeys(n, 1))

    def test_disclosed_a_story_with_no_developer_work_is_reviewed_and_scanned_at_its_parent(self):
        src = self.tmp / "source"
        (src / "app" / "calc.py").write_text(e2e.ADD)
        (src / "tests").mkdir()
        (src / "tests" / "__init__.py").write_text("")
        (src / "tests" / "test_add.py").write_text(e2e.TEST)
        e2e.git(src, "add", "-A")
        e2e.git(src, "commit", "-qm", "the story's behaviour is already there")
        self.baseline = e2e.git(src, "rev-parse", "HEAD")
        self.project = bundle.load(e2e.project_bundle(self.baseline))
        self.mode("nothing")
        rec, n = self.counted()
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        self.assertEqual(self.candidates, {self.baseline})
        self.assertEqual(n, {"developer requests": 0, "reviewer calls": 1, "reviewer requests": 1, "reviewer sessions": 1,
                             "scanner calls": 1, "scanner invocations": 1, "quality assessments": 0})


if __name__ == "__main__":
    unittest.main()
