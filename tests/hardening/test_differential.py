"""Phase 12 — differential model-based testing, in-suite slice.

`AISEF_DIFF_TRACES` seeded scenarios (default 40) drive the reference model and the real kernel from the same
script; every mismatch must be attributed to a registered open defect (`differential.KNOWN`). An unexplained
mismatch is a NEW kernel defect and a hard failure. The large run (100 000 traces) is the CLI:
`python3 -m tests.hardening.differential --traces 100000 --workers 8`.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from tests.hardening import differential as D  # noqa: E402

TRACES = int(os.environ.get("AISEF_DIFF_TRACES", "40"))


class TestDifferential(unittest.TestCase):
    def test_no_unexplained_mismatch_between_model_and_kernel(self):
        res = D.run_many(TRACES, workers=1, start=100_000)      # a seed range the CLI's big run does not reuse
        self.assertEqual(res["unexplained_count"], 0,
                         "\n".join(f"seed {r['seed']} {r['scenario']}: {r['diff']}" for r in res["unexplained"][:10]))
        self.assertGreater(res["matched"], 0)

    def test_every_vocabulary_kind_has_a_model_event_and_a_realisation(self):
        for kind, _ in D.DEV:
            self.assertIn(kind, D.DEV_EVENT)
        for kind, _ in D.REV:
            self.assertIn(kind, D.REV_EVENT)
        for kind, _ in D.SEC:
            self.assertIn(kind, D.SEC_EVENT)
        sc = D.Scenario(0, [k for k, _ in D.DEV], [k for k, _ in D.REV], [k for k, _ in D.SEC])
        script = D.to_script(sc)
        self.assertEqual((len(script.developer), len(script.review), len(script.security)),
                         (len(D.DEV), len(D.REV), len(D.SEC)))


class TestSeed232ReviewerCommitOnTheSchemaRetry(unittest.TestCase):
    """SS-62 — found by differential seed 232 during F2 (2026-09-16), a sibling of SS-A10: a reviewer that answers
    without a verdict and then COMMITS during the schema-retry session moved HEAD off the frozen candidate; F1
    restored a commit made in the first review session only. The candidate must be back on HEAD, the review
    re-run, and the story done with one developer session — never a second developer over a candidate that no
    longer exists (INV-A.1, INV-K.2)."""

    def test_a_reviewer_commit_on_the_schema_retry_is_restored_and_the_review_re_run(self):
        sc = D.Scenario(232, ["CHANGED", "ZERO_OUTPUT", "CHANGED"], ["MALFORMED", "COMMIT", "PASS"], ["PASS"],
                        max_retries=2)
        real = D.real_run(sc)
        self.assertEqual(real.terminal, "done", real.events)
        self.assertEqual(real.developer_sessions, 1, real.events)


class TestSeed2624PlanConflictSurvivesAVerifierRerun(unittest.TestCase):
    """SS-63 — found by differential seed 2624 during F2 (2026-09-16): `deadlock_reason` compared ADJACENT attempt
    records; when the reviewer's session on the second candidate had to be re-run (a tree mutation, D-032 retry), the
    developer attempt in between carried no verdict and the two identical out-of-scope blocks were never paired. The
    plan conflict was reported as `did not pass gate` and the developer budget burned (INV-Q.1)."""

    def test_two_identical_out_of_scope_blocks_around_a_review_rerun_are_a_plan_conflict(self):
        sc = D.Scenario(2624, ["CHANGED"], ["BLOCK_OUTSIDE", "MUTATE", "BLOCK_OUTSIDE", "PASS"], ["PASS", "PASS"],
                        max_retries=1)
        real = D.real_run(sc)
        self.assertEqual(real.terminal, "human:plan conflict", real.events)
        self.assertEqual(real.developer_sessions, 2, real.events)
