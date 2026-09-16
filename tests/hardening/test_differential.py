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
