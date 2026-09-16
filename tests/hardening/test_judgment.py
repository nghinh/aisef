"""F3 — STRUCTURED JUDGMENT AUTHORITY: a blocker binds to what it blocks (INV-F.2; D-002's structural property).
A `block`/`stuck` finding counts only when it names a file, a `behavior_id` or a criterion code; an unbound one is
recorded as `review:unbound` and never scored; a verdict whose blockers all bind to nothing is asked once more and
is then REVIEW_UNRUNNABLE — never a PASS, never a developer session."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import tests  # noqa: E402,F401
from aisef.harness.observe import NOTE, EvidenceStore  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from tests.hardening import differential as D  # noqa: E402

SID = "STORY-04-01"


class TestABlockerBindsToWhatItBlocks(unittest.TestCase):
    def test_a_bound_block_blocks_and_an_unbound_one_is_recorded_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp), candidate="c1")
            v = I.Verdict(verdict="block", findings=[
                {"tag": "block", "file": "src/a.py", "line": "3", "why": "null is not handled", "behavior_id": ""},
                {"tag": "block", "file": "", "line": "", "why": "the overall approach is wrong", "behavior_id": ""},
            ])
            got = I._reconcile(SID, store, "", v, role="review")
            self.assertEqual(got, ["[block] src/a.py:3 — null is not handled"])
            unbound = store.read(SID).of(NOTE, "review:unbound")
            self.assertEqual([f["why"] for f in unbound[-1].detail["findings"]], ["the overall approach is wrong"])

    def test_a_behaviour_id_or_a_criterion_code_binds_without_a_file(self):
        self.assertTrue(I.finding_bound({"tag": "block", "file": "", "behavior_id": "FR-3", "why": "x"}))
        self.assertTrue(I.finding_bound({"tag": "block", "file": "", "behavior_id": "", "why": "AC-STORY-04-01-2 is not met"}))
        self.assertFalse(I.finding_bound({"tag": "block", "file": "", "behavior_id": "", "why": "looks wrong"}))

    def test_a_stuck_item_on_nothing_named_is_not_a_plan_conflict(self):
        v = I.Verdict(verdict="stuck", findings=[{"tag": "stuck", "file": "", "line": "", "why": "the plan is wrong", "behavior_id": ""}])
        self.assertEqual(I.structured_plan_defects(v), [])
        v2 = I.Verdict(verdict="stuck", findings=[{"tag": "stuck", "file": "src/store/db.ts", "line": "", "why": "index needed", "behavior_id": ""}])
        self.assertEqual(I.structured_plan_defects(v2), ["[stuck] src/store/db.ts — index needed"])

    def test_a_verdict_whose_blockers_bind_to_nothing_is_review_unrunnable_never_pass_never_developer(self):
        sc = D.Scenario(4001, ["CHANGED"], ["BLOCK_UNBOUND"], ["PASS"], max_retries=1)
        real = D.real_run(sc)
        self.assertEqual(real.terminal, "blocked:REVIEW_UNRUNNABLE", real.events)
        self.assertEqual(real.developer_sessions, 1, real.events)
        self.assertEqual(real.quality_attempts, 1, real.events)

    def test_the_model_agrees_on_the_unbound_block(self):
        sc = D.Scenario(4001, ["CHANGED"], ["BLOCK_UNBOUND"], ["PASS"], max_retries=1)
        self.assertEqual(D.real_run(sc).diff(D.model_run(sc)), [])
