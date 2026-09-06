"""Đọc JSON status headless — kiểm trên phần trả lời THẬT của BMAD.

Fixture `status-architecture-partial.txt` là nguyên văn phần kết của một
lượt `bmad-architecture` chạy headless (33 lượt, $2.78): văn xuôi rồi mới
tới khối JSON. Đây là ca đáng giá nhất — BMAD tự khai `partial` kèm 6 câu
hỏi mở, tức là chính nó nói "đừng tự duyệt tài liệu này".
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.bmad_status import parse_headless_status  # noqa: E402

REAL = ROOT / "tests" / "fixtures" / "bmad" / "status-architecture-partial.txt"


class TestRealArchitectureRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = parse_headless_status(REAL.read_text(encoding="utf-8"))

    def test_parsed(self):
        self.assertTrue(self.s.parsed)
        self.assertEqual(self.s.status, "partial")
        self.assertEqual(self.s.intent, "create")

    def test_artifact_produced_despite_partial(self):
        """`partial` vẫn có artifact — khác hẳn `blocked`."""
        self.assertTrue(self.s.produced_artifact)

    def test_needs_human(self):
        """BMAD tự khai chưa đứng được một mình; tự duyệt là bỏ qua đúng
        chỗ cổng người sinh ra để bảo vệ."""
        self.assertTrue(self.s.needs_human)
        self.assertEqual(len(self.s.open_questions), 6)

    def test_assumptions_captured(self):
        self.assertEqual(len(self.s.assumptions), 7)
        self.assertTrue(any("WebSearch" in a for a in self.s.assumptions))

    def test_artifacts_are_paths_only(self):
        """Khoá artifact mỗi skill đặt một kiểu (`spine`, `memlog`,
        `companions`), nhưng `altitude: "feature"` thì không phải file."""
        self.assertEqual(self.s.artifacts.get("spine"), "_bmad-output/architecture.md")
        self.assertEqual(self.s.artifacts.get("memlog"), "_bmad-output/.memlog.md")
        for key in ("altitude", "purpose", "doc_workspace"):
            self.assertNotIn(key, self.s.artifacts)

    def test_list_of_paths_captured(self):
        """`companions` là danh sách — bỏ qua nó là mất dấu file review."""
        self.assertIn(
            "_bmad-output/reviews/review-architecture.md", self.s.declared_paths()
        )

    def test_summary_readable(self):
        text = self.s.summary()
        self.assertIn("partial", text)
        self.assertIn("6 câu hỏi mở", text)


class TestStatusSemantics(unittest.TestCase):
    def test_complete_may_auto_approve(self):
        s = parse_headless_status('```json\n{"status":"complete","intent":"create"}\n```')
        self.assertTrue(s.produced_artifact)
        self.assertFalse(s.needs_human)

    def test_open_questions_force_human_even_when_complete(self):
        """Mâu thuẫn giữa `complete` và câu hỏi mở: nghiêng về phía an toàn."""
        s = parse_headless_status(
            '{"status":"complete","open_questions":["ai sở hữu dữ liệu?"]}'
        )
        self.assertTrue(s.needs_human)

    def test_blocked_has_no_artifact(self):
        s = parse_headless_status(
            '{"status":"blocked","intent":"create","reason":"thiếu PRD"}'
        )
        self.assertFalse(s.produced_artifact)
        self.assertEqual(s.reason, "thiếu PRD")


class TestParsing(unittest.TestCase):
    def test_last_json_block_wins(self):
        """Phần văn xuôi có thể chứa JSON ví dụ; status thật ở khối cuối."""
        text = (
            'Schema trông như sau:\n```json\n{"status":"complete"}\n```\n'
            'Kết quả thật:\n```json\n{"status":"blocked","reason":"hết giờ"}\n```'
        )
        self.assertEqual(parse_headless_status(text).status, "blocked")

    def test_bare_json_without_fence(self):
        s = parse_headless_status('xong.\n\n{"status": "complete", "intent": "update"}')
        self.assertEqual(s.status, "complete")

    def test_open_questions_as_objects(self):
        s = parse_headless_status(
            '{"status":"partial","open_questions":[{"id":"OQ-1","text":"ai duyệt?"}]}'
        )
        self.assertEqual(s.open_questions, ["OQ-1: ai duyệt?"])

    def test_no_json_at_all(self):
        s = parse_headless_status("Tôi đã viết xong tài liệu.")
        self.assertFalse(s.parsed)
        self.assertIn("không đọc được", s.summary())

    def test_malformed_json_is_not_a_crash(self):
        self.assertFalse(parse_headless_status('```json\n{hỏng\n```').parsed)

    def test_empty_text(self):
        self.assertFalse(parse_headless_status("").parsed)

    def test_json_without_status_key_ignored(self):
        """Khối JSON khác trong câu trả lời không được nhận nhầm là status."""
        s = parse_headless_status('```json\n{"foo":"bar"}\n```')
        self.assertFalse(s.parsed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
