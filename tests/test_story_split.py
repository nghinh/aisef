"""Tách `epics.md` thành mỗi story một file.

Chạy trên `tests/fixtures/bmad/epics.md` — đúng khuôn template của BMAD
(`## Epic N`, `### Story N.M`, Given/When/Then) và ánh xạ sang PRD thật
trong cùng thư mục fixture, nên phần phủ FR kiểm trên dữ liệu thật.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.normalize import parse_epics, parse_epics_file  # noqa: E402
from aisdlc.phases.story_split import split, story_file  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "bmad"


class TestParseEpics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = parse_epics_file(FIX / "epics.md")

    def test_epics_and_stories(self):
        self.assertEqual([e.id for e in self.plan.epics],
                         ["EPIC-01", "EPIC-02", "EPIC-03", "EPIC-04"])
        self.assertEqual(len(self.plan.stories()), 12)

    def test_story_ids_are_zero_padded(self):
        """Id có số 0 đứng đầu để sắp xếp bằng chuỗi ra đúng thứ tự."""
        self.assertEqual(self.plan.epics[0].stories[0].id, "STORY-01-01")

    def test_role_lines(self):
        s = self.plan.by_id("STORY-01-01")
        self.assertEqual(s.as_a, "người dùng")
        self.assertIn("một thao tác", s.i_want)
        self.assertTrue(s.so_that)

    def test_given_when_then_becomes_one_criterion(self):
        """Given/When/Then/And là **một** tiêu chí trải trên nhiều dòng —
        cắt theo dòng sẽ ra bốn mảnh vô nghĩa."""
        s = self.plan.by_id("STORY-01-01")
        self.assertEqual(len(s.acceptance_criteria), 2)
        first = s.acceptance_criteria[0]
        for word in ("Given", "When", "Then", "And"):
            self.assertIn(word, first)

    def test_metadata_block(self):
        s = self.plan.by_id("STORY-02-01")
        self.assertEqual(s.covers, ["FR-5", "FR-6"])
        self.assertEqual(s.write_scope, ["src/search/"])
        self.assertEqual(s.depends_on, ["STORY-01-04"])

    def test_metadata_is_not_mistaken_for_acceptance_criteria(self):
        for s in self.plan.stories():
            for ac in s.acceptance_criteria:
                self.assertNotIn("write_scope", ac)
                self.assertNotIn("covers:", ac)

    def test_depends_on_none_is_empty(self):
        self.assertEqual(self.plan.by_id("STORY-01-01").depends_on, [])

    def test_coverage_map_read(self):
        self.assertEqual(self.plan.coverage_map["FR-7"], ["STORY-02-02"])

    def test_coverage_map_fills_missing_covers(self):
        """Story quên khai `covers` vẫn truy được FR nhờ bản đồ phủ."""
        text = (FIX / "epics.md").read_text(encoding="utf-8")
        stripped = text.replace("- covers: FR-7\n", "")
        plan = parse_epics(stripped)
        self.assertEqual(plan.by_id("STORY-02-02").covers, ["FR-7"])

    def test_story_does_not_depend_on_itself(self):
        for s in self.plan.stories():
            self.assertNotIn(s.id, s.depends_on)


class SplitTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for name in ("epics.md", "prd.md"):
            shutil.copy(FIX / name, self.root / name)

    def tearDown(self):
        self._tmp.cleanup()

    def index(self) -> dict:
        return json.loads((self.root / "stories.index.json").read_text(encoding="utf-8"))


class TestSplit(SplitTestCase):
    def test_one_file_per_story_under_its_epic(self):
        r = split(self.root)
        self.assertTrue(r.ok, r.summary())
        self.assertEqual(len(r.files), 12)
        self.assertTrue((self.root / "stories" / "EPIC-02" / "STORY-02-01.md").is_file())

    def test_story_file_carries_the_full_requirement_text(self):
        """Story phải đứng được một mình: agent mở một file là đủ, không
        phải lọc lại PRD 33KB mỗi lượt."""
        split(self.root)
        text = (self.root / "stories" / "EPIC-01" / "STORY-01-01.md").read_text(encoding="utf-8")
        self.assertIn("FR-1", text)
        self.assertIn("Kho cục bộ", text)          # nguyên văn từ PRD thật
        self.assertIn("src/notes/", text)          # phạm vi được ghi
        self.assertIn("Tiêu chí chấp nhận", text)

    def test_index_feeds_the_scheduler(self):
        split(self.root)
        data = self.index()
        ids = [s["id"] for s in data["stories"]]
        self.assertIn("STORY-04-03", ids)
        self.assertEqual(len(data["epics"]), 4)
        self.assertTrue(data["gate"]["passed"])

    def test_waves_are_computed_once_and_stored(self):
        """Hai story cùng epic, không phụ thuộc nhau, phạm vi ghi rời nhau
        thì chạy cùng đợt."""
        split(self.root)
        waves = self.index()["waves"]
        self.assertEqual(waves["EPIC-01"][0], ["STORY-01-01"])
        self.assertIn("STORY-01-02", waves["EPIC-01"][1])
        self.assertIn("STORY-01-04", waves["EPIC-01"][1])

    def test_overlapping_write_scope_serialises(self):
        """01-03 và 01-02 cùng ghi src/notes/ nên không được cùng đợt."""
        split(self.root)
        for wave in self.index()["waves"]["EPIC-01"]:
            self.assertFalse({"STORY-01-02", "STORY-01-03"} <= set(wave))

    def test_rerun_is_idempotent(self):
        first = split(self.root)
        before = {p: p.read_text(encoding="utf-8") for p in first.files}
        second = split(self.root)
        self.assertEqual(len(second.files), len(first.files))
        self.assertEqual(second.removed, [])
        for p, text in before.items():
            self.assertEqual(p.read_text(encoding="utf-8"), text)

    def test_removed_story_leaves_no_orphan_file(self):
        """Story bị gỡ khỏi epics.md mà file còn lại sẽ bị nhặt lên như
        việc thật ở vòng sau."""
        split(self.root)
        orphan = self.root / "stories" / "EPIC-01" / "STORY-01-09.md"
        orphan.write_text("# story đã bị gỡ\n", encoding="utf-8")
        r = split(self.root)
        self.assertIn(orphan, r.removed)
        self.assertFalse(orphan.exists())

    def test_editing_epics_regenerates_story_files(self):
        split(self.root)
        path = story_file(self.root, parse_epics_file(self.root / "epics.md").by_id("STORY-01-01"))
        path.write_text("người dùng sửa tay\n", encoding="utf-8")
        split(self.root)
        self.assertIn("FR-1", path.read_text(encoding="utf-8"))


class TestSplitFailures(SplitTestCase):
    def test_no_epics_file(self):
        (self.root / "epics.md").unlink()
        r = split(self.root)
        self.assertFalse(r.ok)
        self.assertIn("chưa có epics.md", r.error)

    def test_epics_without_stories(self):
        (self.root / "epics.md").write_text("# Epic Breakdown\n\nchưa viết gì.\n", encoding="utf-8")
        r = split(self.root)
        self.assertFalse(r.ok)
        self.assertIn("không có story", r.error)

    def test_missing_write_scope_fails_the_gate(self):
        text = (self.root / "epics.md").read_text(encoding="utf-8")
        text = text.replace("- write_scope: src/search/\n", "")
        (self.root / "epics.md").write_text(text, encoding="utf-8")
        r = split(self.root)
        self.assertFalse(r.ok)
        self.assertTrue(any("write_scope" in e for e in r.gate.errors))

    def test_uncovered_requirement_fails_the_gate(self):
        text = (self.root / "epics.md").read_text(encoding="utf-8")
        text = text.replace("| FR-9 | 3.2 |\n", "").replace("- covers: FR-9\n", "")
        (self.root / "epics.md").write_text(text, encoding="utf-8")
        r = split(self.root)
        self.assertFalse(r.ok)
        self.assertTrue(any("FR-9" in e for e in r.gate.errors))

    def test_files_are_still_written_when_the_gate_fails(self):
        """Cổng trượt vẫn phải ghi file: người duyệt cần đọc để biết sai gì."""
        text = (self.root / "epics.md").read_text(encoding="utf-8")
        (self.root / "epics.md").write_text(text.replace("- write_scope: src/tags/\n", ""), encoding="utf-8")
        r = split(self.root)
        self.assertFalse(r.ok)
        self.assertTrue(r.files)
        self.assertFalse(self.index()["gate"]["passed"])

    def test_dependency_cycle_is_reported_not_hidden(self):
        text = (self.root / "epics.md").read_text(encoding="utf-8")
        text = text.replace("- covers: FR-1\n- write_scope: src/notes/, src/db/\n- depends_on: none",
                            "- covers: FR-1\n- write_scope: src/notes/, src/db/\n- depends_on: 1.2")
        (self.root / "epics.md").write_text(text, encoding="utf-8")
        r = split(self.root)
        self.assertFalse(r.ok)
        self.assertEqual(self.index()["waves"], {})
        self.assertTrue(self.index()["gate"]["errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
