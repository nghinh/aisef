"""Dogfood `calc` EPIC-01 — 3 story tuần tự, OpenCode + mycombo, Python."""

from __future__ import annotations

import shutil
import unittest

from . import _runner as R

STORIES = ["STORY-01-01", "STORY-01-02", "STORY-01-03"]


@unittest.skipUnless(R.ENABLED and shutil.which("opencode"), "AISEF_DOGFOOD=1 và có `opencode`")
class TestCalcEpic01(unittest.TestCase):
    def test_moc(self):
        project = R.make_project("calc", clients=("opencode",))
        R.run_epic(project, "EPIC-01", client="opencode")
        m = R.milestones(project, STORIES)
        for sid, s in m["stories"].items():
            with self.subTest(story=sid):
                self.assertEqual(s["status"], "done", s)
                self.assertLessEqual(s["attempts"], 2)
                self.assertEqual(s["ac_missing"], [])
                self.assertGreaterEqual(s["handoffs"], 3)
        print(f"\n  calc: chi phí ${m['cost_usd']:.2f}")
        self.assertEqual(m["stray_commits"], [])
