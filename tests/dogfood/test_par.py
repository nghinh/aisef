"""Dogfood `par` EPIC-01 — 3 story độc lập, chạy song song, Claude."""

from __future__ import annotations

import shutil
import unittest

from . import _runner as R

STORIES = ["STORY-01-01", "STORY-01-02", "STORY-01-03"]


@unittest.skipUnless(R.ENABLED and shutil.which("claude"), "AISDLC_DOGFOOD=1 và có `claude`")
class TestParEpic01(unittest.TestCase):
    def test_moc(self):
        project = R.make_project("par")
        R.run_epic(project, "EPIC-01")
        m = R.milestones(project, STORIES)
        for sid, s in m["stories"].items():
            with self.subTest(story=sid):
                self.assertEqual(s["status"], "done", s)
                self.assertEqual(s["attempts"], 1, "mốc: qua ở lượt đầu")
                self.assertEqual(s["ac_missing"], [], "mọi tiêu chí có test mang mã")
                self.assertGreaterEqual(s["handoffs"], 3, "dev → reviewer → security")
        self.assertLessEqual(m["cost_usd"], 2 * R.PAR_BASELINE_USD, m)
        self.assertEqual(m["non_merge_after_base"], [], "main chỉ đổi qua merge")
