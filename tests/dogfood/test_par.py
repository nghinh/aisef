"""Dogfood `par` EPIC-01 — 3 story độc lập, chạy song song, Claude."""

from __future__ import annotations

import shutil
import unittest

from . import _runner as R

STORIES = ["STORY-01-01", "STORY-01-02", "STORY-01-03"]


@unittest.skipUnless(R.ENABLED and shutil.which("claude"), "AISEF_DOGFOOD=1 và có `claude`")
class TestParEpic01(unittest.TestCase):
    def test_moc(self):
        project = R.make_project("par")
        R.run_epic(project, "EPIC-01")
        m = R.milestones(project, STORIES)
        for sid, s in m["stories"].items():
            with self.subTest(story=sid):
                self.assertEqual(s["status"], "done", s)
                self.assertLessEqual(s["attempts"], 2, "quá 2 lượt là story hoặc kế hoạch có vấn đề")
                self.assertEqual(s["ac_missing"], [], "mọi tiêu chí có test mang mã")
                self.assertGreaterEqual(s["handoffs"], 3, "dev → reviewer → security")
        # Tỉ lệ qua ở lượt đầu là telemetry, không phải cổng: người rà soát bắt
        # được lỗi thật (dogfood lần 2: `slice` vỡ cặp thay thế) là hệ thống
        # làm đúng việc, không phải mốc trượt.
        luot_dau = sum(1 for s in m["stories"].values() if s["attempts"] == 1)
        print(f"\n  qua ở lượt đầu: {luot_dau}/{len(m['stories'])} · chi phí ${m['cost_usd']:.2f} (mốc ${R.PAR_BASELINE_USD})")
        self.assertLessEqual(m["cost_usd"], 2 * R.PAR_BASELINE_USD, m)
        self.assertEqual(m["stray_commits"], [], "commit trên main mà không qua worktree")
