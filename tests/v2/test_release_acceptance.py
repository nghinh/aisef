"""The release acceptance (validation/qualification/release_acceptance.py, charter §13/§17) on the offline calc
project. Owner ruling §7 keeps five deterministic cases, each a real `aisef run` directory evaluated end to end:
A a delivered run passes; B a run that delivered nothing does not; C a story blocked because its upstream story failed
is not a framework false block; D a story blocked by a failure the framework owns, with no upstream failure, is one;
E a delivered main changed after the run is a false acceptance the independent suite catches, whatever the journal
says. The `framework_blocks` rule behind C and D is also tested on its own."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle  # noqa: E402
from aisef2.arch.enums import ObligationRole  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from validation.qualification import release_acceptance as A  # noqa: E402

#: what every run below that does not deliver S1 fails, besides the check its case is about
UNDELIVERED = {"delivery_verdict", "stories_committed", "productproof_delivered", "acceptance_suite_satisfied"}


def two_stories(baseline: str) -> dict:
    """The calc bundle with a second story, S2, that depends on S1 and PRESERVEs the addition S1 introduces."""
    b = e2e.project_bundle(baseline)
    add = bundle.load(b).plan.obligations[0]
    keep = PlanObligation("C-KEEP", add.product_proof_spec_id, "S2", ObligationRole.PRESERVE,
                          EXPECTED_AT_PARENT[ObligationRole.PRESERVE], (add.criterion_id,), "S2 keeps addition")
    plan = Plan.create(id="PLAN-CALC-2", baseline=baseline, plan_quality_policy=NOT_PREREGISTERED, obligations=(add, keep))
    return {**b, "plan": plain(plan), "facts": {**b["facts"], "C-KEEP": b["facts"]["C-ADD"]},
            "stories": {**b["stories"], "S2": {"depends_on": ["S1"], "tests": ["tests/test_add.py"]}}}


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ReleaseAcceptance(e2e.ProductBase):
    def accepted(self) -> dict:
        return A.frozen(self.project)

    def evaluate(self) -> dict:
        return A.evaluate(self.project, self.tmp / "out", self.accepted())

    def test_A_a_delivered_run_passes_every_check(self):
        """owner ruling §7 A: the reference scenario passes."""
        self.execute()
        out = self.evaluate()
        self.assertEqual((out["RELEASE_SMOKE_PASS"], out["problems"]), ("YES", []))
        self.assertTrue(all(out["checks"].values()), out["checks"])
        self.assertEqual((out["acceptance"]["total"], out["acceptance"]["satisfied"]), (1, 1))
        self.assertEqual(out["productproof"], {"total": 1, "delivered": 1})

    def test_B_a_run_that_delivered_nothing_does_not_pass(self):
        """owner ruling §7 B: the do-nothing scenario fails — on the developer, never on the framework."""
        self.mode("nothing")
        self.execute()
        out = self.evaluate()
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")
        self.assertEqual({k for k, ok in out["checks"].items() if not ok}, UNDELIVERED)
        self.assertEqual(out["false_acceptance"], [])

    def test_C_a_story_blocked_because_its_upstream_story_failed_is_not_a_framework_false_block(self):
        """owner ruling §7 C: S1's developer changes nothing (SUBJECT_ABSENT_AT_CANDIDATE, DEVELOPER); S2 PRESERVEs what
        S1 was to introduce, so at S2's parent the subject is absent: PRECONDITION_BROKEN, PLAN — a consequence of S1."""
        self.project = bundle.load(two_stories(self.baseline))
        self.mode("nothing")
        rec = self.execute()
        self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "ROLLBACK"], "S2": ["ROLLBACK"]})
        out = self.evaluate()
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")
        self.assertTrue(out["checks"]["framework_false_rollback_or_block"])
        self.assertEqual(out["framework_false_rollback_or_block"],
                         [{"story": "S2", "code": "PRECONDITION_BROKEN", "owner": "PLAN", "upstream_not_committed": True}])
        self.assertEqual({k for k, ok in out["checks"].items() if not ok}, UNDELIVERED)

    def test_D_a_framework_owned_block_with_no_upstream_failure_is_a_framework_false_block(self):
        """owner ruling §7 D: the developer's code is proved at the candidate, but the scanner the product finds on PATH
        (a `ruff` that exits without a report) cannot run: CAPABILITY_UNRUNNABLE, ENVIRONMENT — retried, then rolled
        back. The story has no upstream to blame: the framework blocked a correct delivery."""
        tools = self.tmp / "broken-tools"
        tools.mkdir()
        (tools / "ruff").write_text("#!/bin/sh\nexit 2\n")
        (tools / "ruff").chmod(0o755)
        self.scanner.stop()         # no NoScanner: the product's own discovery (shutil.which) finds the broken ruff
        with mock.patch.dict(os.environ, {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"}):
            rec = self.execute()
        self.assertEqual((rec["scanner"], rec["story_outcomes"]), ("ruff", {"S1": ["RETRY", "ROLLBACK"]}))
        self.assertEqual(rec["productproof"]["satisfied_at_last_proof"], 1)      # the developer's work was right
        out = self.evaluate()
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")
        self.assertFalse(out["checks"]["framework_false_rollback_or_block"])
        self.assertEqual(out["framework_false_rollback_or_block"],
                         [{"story": "S1", "code": "CAPABILITY_UNRUNNABLE", "owner": "ENVIRONMENT"}])
        self.assertEqual({k for k, ok in out["checks"].items() if not ok}, UNDELIVERED | {"framework_false_rollback_or_block"})

    def test_E_a_delivered_main_changed_after_the_run_is_a_false_acceptance(self):
        """owner ruling §7 E: the journal delivered a spec the delivered main does not satisfy."""
        self.execute()
        repo = self.tmp / "out" / "repo"
        (repo / "app" / "calc.py").write_text(e2e.CALC, encoding="utf-8")       # `add` is gone again
        e2e.git(repo, "commit", "-qam", "after the run")
        out = self.evaluate()
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")
        self.assertEqual(out["false_acceptance"], [next(iter(self.project.specs))])
        self.assertFalse(out["checks"]["acceptance_suite_satisfied"])
        self.assertFalse(out["checks"]["run_verified"])      # the record's final main is not the repository's main

    def test_an_evaluator_that_is_not_the_frozen_one_is_refused(self):
        self.execute()
        accepted = self.accepted()
        out = A.evaluate(self.project, self.tmp / "out", {**accepted, "evaluator": {**accepted["evaluator"], "sha256": "0" * 64}})
        self.assertIn("this evaluator is not the frozen one", out["problems"])
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")

    def test_an_acceptance_frozen_for_another_bundle_is_refused(self):
        self.execute()
        out = A.evaluate(self.project, self.tmp / "out", {**self.accepted(), "bundle_digest": "0" * 64})
        self.assertIn("the frozen acceptance is not this bundle's", out["problems"])
        self.assertEqual(out["RELEASE_SMOKE_PASS"], "NO")

    def test_D_rule_framework_owned_blocks_are_counted_developer_failures_are_not(self):
        """owner ruling §7 D, the rule alone."""
        events = [{"seq": 1, "type": "failure/observed", "data": {"story_id": "S1", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT"}},
                  {"seq": 2, "type": "failure/observed", "data": {"story_id": "S2", "code": "PRODUCT_REFUTED", "owner": "DEVELOPER"}},
                  {"seq": 3, "type": "failure/observed", "data": {"story_id": "S3", "code": "X", "owner": "PLAN"}}]
        self.assertEqual(A.framework_blocks(events, {"S3"}), [{"story": "S1", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT"}])

    def test_C_rule_a_block_that_follows_an_upstream_story_s_failure_is_not_a_false_one(self):
        """owner ruling §7 C, the rule alone (transitive dependencies)."""
        events = [{"seq": 1, "type": "failure/observed", "data": {"story_id": "S1", "code": "PRODUCT_REFUTED", "owner": "DEVELOPER"}},
                  {"seq": 2, "type": "failure/observed", "data": {"story_id": "S3", "code": "PRECONDITION_BROKEN", "owner": "PLAN"}},
                  {"seq": 3, "type": "failure/observed", "data": {"story_id": "S4", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT"}}]
        depends = {"S2": ["S1"], "S3": ["S2"], "S4": []}         # S3 -> S2 (committed) -> S1 (not committed)
        self.assertEqual(A.framework_blocks(events, {"S2"}, depends),
                         [{"story": "S3", "code": "PRECONDITION_BROKEN", "owner": "PLAN", "upstream_not_committed": True},
                          {"story": "S4", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT"}])


if __name__ == "__main__":
    unittest.main()
