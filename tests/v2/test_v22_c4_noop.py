"""ROADMAP-2.2 C4 — a no-op attempt is routed as a DEVELOPER failure at the candidate without re-proving, judging
quality, or spending the (paid) reviewer and the scanner on a tree byte-identical to the one admission measured. When
the developer runs but the candidate is the parent unchanged, story_runner sets CONTRACT_UNSATISFIED (§10.3,
CANDIDATE/UNSATISFIED -> DEVELOPER) before the candidate stages — the outcome a retry, exactly as an identical-candidate
proof would reach, with no reviewer session created. The legitimate no-work path (nothing to introduce) is unaffected:
C4 is gated on `not no_work`, proved by the existing K-NOWORK suite staying green."""
from __future__ import annotations

import os
import unittest

from tests.v2 import test_app_run as e2e


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class NoOpAttempt(e2e.ProductBase):
    def _checks(self, out: str = "out"):
        return [e.data for e in e2e.format3.reconstruct(
            (self.tmp / out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events
                if e.type == "gate/check"]

    def test_a_developer_that_changes_nothing_fails_at_the_candidate_without_quality_review_or_scan(self):
        self.mode("nochange")        # the fake developer writes nothing, so the candidate is the parent unchanged
        rec = self.execute()
        self.assertIn(rec["delivery_verdict"], ("FAIL", "NOT_REACHED"), rec.get("budget_stop"))
        # a no-op is a retryable DEVELOPER failure; with the retries exhausted the story rolls back, never commits
        self.assertEqual(rec["story_outcomes"]["S1"][-1], "ROLLBACK")
        self.assertTrue(set(rec["story_outcomes"]["S1"]) <= {"RETRY", "ROLLBACK"}, rec["story_outcomes"])
        checks = self._checks()
        # C4 routed the DEVELOPER failure at the candidate...
        candidate = [c for c in checks if c["check"] == "S1:candidate" and not c["passed"]]
        self.assertTrue(candidate, checks)
        self.assertIn("changed nothing", candidate[0]["detail"])
        # ...and the candidate stages that measure a tree were skipped: no quality, no review, no scan, no proof
        for stage in ("S1:quality", "S1:security"):
            self.assertEqual([c for c in checks if c["check"] == stage], [], stage)
        self.assertEqual([c for c in checks if c["check"].startswith("S1:review")], [])
        self.assertEqual([c for c in checks if c["check"].startswith("S1:proof:")], [])
        # the efficiency the owner asked for: no reviewer session was ever created (a paid call avoided)
        self.assertEqual([s for s in rec["sessions"] if s.get("role") == "reviewer"], [])
        self.assertTrue(all(s.get("role") == "developer" for s in rec["sessions"]), rec["sessions"])

    def test_the_run_still_verifies_from_its_journal(self):
        self.mode("nochange")
        self.execute()
        self.assertEqual(e2e.verify(self.project, self.tmp / "out")["verdict"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
