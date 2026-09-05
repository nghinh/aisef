"""Lỗi 18: ô Map mockup của báo cáo phải là kết quả mới nhất, không phải "mọi lần đều đạt"."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.phases.report import mockup_cell  # noqa: E402


class TestMockupCell(unittest.TestCase):
    def test_latest_pass_wins_over_earlier_failures(self):
        self.assertEqual(mockup_cell([NS(name="note-editor", ok=False), NS(name="note-editor", ok=False),
                                      NS(name="note-editor", ok=True)]), "✅")

    def test_latest_failure_is_a_failure(self):
        self.assertEqual(mockup_cell([NS(name="s", ok=True), NS(name="s", ok=False)]), "✗")

    def test_every_screen_must_pass_latest(self):
        self.assertEqual(mockup_cell([NS(name="a", ok=True), NS(name="b", ok=False), NS(name="a", ok=True)]), "✗")

    def test_no_events_is_not_a_pass(self):
        self.assertEqual(mockup_cell([]), "✗")


if __name__ == "__main__":
    unittest.main()
