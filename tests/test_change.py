"""`aisdlc change` — vòng đời thay đổi sau phát hành (S4)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from aisdlc.control.approvals import ApprovalStore, Gate, Status
from aisdlc.control.change import apply


class TestChange(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.p = Path(self._tmp.name)
        (self.p / "docs").mkdir(); (self.p / "docs" / "requirements.md").write_text("# YC\n\n## FR-1 — a\nx\n", encoding="utf-8")
        root = self.p / "_bmad-output"; root.mkdir()
        (root / "prd.md").write_text("# PRD\n", encoding="utf-8")
        (root / "stories.index.json").write_text(json.dumps({"version": 1, "epics": [{"id": "EPIC-01", "title": "e"}],
            "stories": [{"id": "STORY-01-01", "epic_id": "EPIC-01", "title": "cũ", "acceptance_criteria": ["a"], "covers": ["FR-1"],
                         "write_scope": ["src"], "depends_on": [], "screens": [], "verification_contract": ["unit"], "file": "stories/EPIC-01/STORY-01-01.md"}],
            "waves": {"EPIC-01": [["STORY-01-01"]]}}), encoding="utf-8")
        self.store = ApprovalStore(root); self.store.approve(Gate.PRD, by="t")

    def tearDown(self):
        self._tmp.cleanup()

    def test_prd_becomes_stale_and_delta_story_is_created(self):
        self.assertIs(self.store.status(Gate.PRD), Status.APPROVED)
        r = apply(self.p, "FR-1", "Slug phải giữ dấu gạch dưới", today=date(2026, 9, 5))
        self.assertEqual(r.story_id, "STORY-CH-01")
        self.assertIs(self.store.status(Gate.PRD), Status.STALE)
        self.assertIn("thay đổi 2026-09-05", (self.p / "docs" / "requirements.md").read_text(encoding="utf-8"))
        idx = json.loads((self.p / "_bmad-output" / "stories.index.json").read_text(encoding="utf-8"))
        s = next(x for x in idx["stories"] if x["id"] == "STORY-CH-01")
        self.assertEqual(s["covers"], ["FR-1"]); self.assertEqual(s["write_scope"], [])
        self.assertEqual(idx["waves"]["EPIC-CH"], [["STORY-CH-01"]])
        self.assertTrue(r.story_file.is_file())
        self.assertIn("[AC-STORY-CH-01-1]", r.story_file.read_text(encoding="utf-8"))
        # story cũ giữ nguyên
        self.assertTrue(any(x["id"] == "STORY-01-01" for x in idx["stories"]))
        st = json.loads((self.p / "_bmad-output" / "sprint-status.json").read_text(encoding="utf-8"))["stories"]
        self.assertEqual(st["STORY-CH-01"]["status"], "pending")

    def test_second_change_gets_next_number(self):
        apply(self.p, "FR-1", "một"); r = apply(self.p, "NFR-2", "hai")
        self.assertEqual(r.story_id, "STORY-CH-02")

    def test_bad_requirement_id_rejected(self):
        with self.assertRaises(ValueError):
            apply(self.p, "yeu-cau-3", "x")
