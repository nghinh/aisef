"""The release acceptance (validation/qualification/release_acceptance.py, charter §13/§17) on the offline calc
project: a delivered run passes; a run that delivered nothing does not; a delivered main changed after the run is a
false acceptance the independent suite catches, whatever the journal says."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2 import test_app_run as e2e  # noqa: E402
from validation.qualification import release_acceptance as A  # noqa: E402


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ReleaseAcceptance(e2e.ProductBase):
    def accepted(self) -> dict:
        return A.frozen(self.project)

    def test_a_delivered_run_passes_every_check(self):
        self.execute()
        out = A.evaluate(self.project, self.tmp / "out", self.accepted())
        self.assertEqual((out["RELEASE_SMOKE_PASS"], out["problems"]), ("YES", []))
        self.assertTrue(all(out["checks"].values()), out["checks"])
        self.assertEqual((out["acceptance"]["total"], out["acceptance"]["satisfied"]), (1, 1))
        self.assertEqual(out["productproof"], {"total": 1, "delivered": 1})

    def test_a_run_that_delivered_nothing_does_not_pass(self):
        self.mode("nothing")
        self.execute()
        out = A.evaluate(self.project, self.tmp / "out", self.accepted())
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")
        self.assertEqual({k for k, ok in out["checks"].items() if not ok},
                         {"delivery_verdict", "stories_committed", "productproof_delivered", "acceptance_suite_satisfied"})
        self.assertEqual(out["false_acceptance"], [])

    def test_a_delivered_main_changed_after_the_run_is_a_false_acceptance(self):
        self.execute()
        repo = self.tmp / "out" / "repo"
        (repo / "app" / "calc.py").write_text(e2e.CALC, encoding="utf-8")       # `add` is gone again
        e2e.git(repo, "commit", "-qam", "after the run")
        out = A.evaluate(self.project, self.tmp / "out", self.accepted())
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")
        self.assertEqual(out["false_acceptance"], [next(iter(self.project.specs))])
        self.assertFalse(out["checks"]["acceptance_suite_satisfied"])
        self.assertFalse(out["checks"]["run_verified"])      # the record's final main is not the repository's main

    def test_an_acceptance_frozen_for_another_bundle_is_refused(self):
        self.execute()
        out = A.evaluate(self.project, self.tmp / "out", {**self.accepted(), "bundle_digest": "0" * 64})
        self.assertIn("the frozen acceptance is not this bundle's", out["problems"])
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")

    def test_framework_owned_blocks_are_counted_developer_failures_are_not(self):
        events = [{"seq": 1, "type": "failure/observed", "data": {"story_id": "S1", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT"}},
                  {"seq": 2, "type": "failure/observed", "data": {"story_id": "S2", "code": "PRODUCT_REFUTED", "owner": "DEVELOPER"}},
                  {"seq": 3, "type": "failure/observed", "data": {"story_id": "S3", "code": "X", "owner": "PLAN"}}]
        self.assertEqual(A.framework_blocks(events, {"S3"}), [{"story": "S1", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT"}])


if __name__ == "__main__":
    unittest.main()
