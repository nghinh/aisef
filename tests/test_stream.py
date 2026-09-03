"""Kiểm chứng bộ đọc stream-json trên luồng THẬT do `claude -p` sinh ra.

Hai fixture lấy từ spike S1/S2, không phải dữ liệu bịa: một lượt bình
thường và một lượt bị guard chặn.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.stream import parse_file, parse_stream  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
MINIMAL = FIX / "stream-minimal.jsonl"
BLOCKED = FIX / "stream-blocked.jsonl"


class TestMinimalRun(unittest.TestCase):
    """Lượt chạy bình thường: `claude -p "Reply with exactly the word: OK"`."""

    @classmethod
    def setUpClass(cls):
        cls.r = parse_file(MINIMAL)

    def test_success(self):
        self.assertTrue(self.r.ok)
        self.assertEqual(self.r.error, "")

    def test_text(self):
        self.assertEqual(self.r.text.strip(), "OK")

    def test_cost_and_latency_present(self):
        self.assertGreater(self.r.cost_usd, 0)
        self.assertGreater(self.r.duration_ms, 0)
        self.assertGreater(self.r.ttft_ms, 0)

    def test_tokens_counted(self):
        self.assertGreater(self.r.total_tokens, 0)
        # Ngữ cảnh nền được nạp vào cache — đây là phần chi phí cố định
        # mỗi phiên story phải trả (xem mục chi phí trong SOLUTION).
        self.assertGreater(self.r.cache_creation_tokens, 0)

    def test_session_id_for_resume(self):
        self.assertTrue(self.r.session_id)

    def test_nothing_blocked(self):
        self.assertFalse(self.r.was_blocked)
        self.assertEqual(self.r.denials, [])

    def test_evidence_shape(self):
        ev = self.r.evidence()
        for key in ("ok", "cost_usd", "duration_ms", "tokens", "session_id", "denials"):
            self.assertIn(key, ev)
        self.assertEqual(ev["denials"], [])


class TestBlockedRun(unittest.TestCase):
    """Lượt bị guard chặn: agent cố ghi ra ngoài write_scope."""

    @classmethod
    def setUpClass(cls):
        cls.r = parse_file(BLOCKED)

    def test_run_itself_succeeded(self):
        """Guard chặn tool, nhưng lượt chạy vẫn kết thúc bình thường.

        Phân biệt quan trọng: bị chặn ≠ chạy hỏng. Agent nhận thông báo
        rồi dừng đúng cách.
        """
        self.assertTrue(self.r.ok)

    def test_denial_recorded(self):
        self.assertTrue(self.r.was_blocked)
        self.assertEqual(len(self.r.denials), 1)

    def test_denial_carries_tool_and_path(self):
        d = self.r.denials[0]
        self.assertEqual(d.tool_name, "Write")
        self.assertIn("secret_area/leak.txt", d.target_path)
        self.assertTrue(d.tool_use_id)

    def test_denial_carries_intended_content(self):
        """Bằng chứng ghi cả thứ agent định ghi — không chỉ việc nó bị chặn."""
        self.assertIn("HELLO", self.r.denials[0].tool_input.get("content", ""))

    def test_tool_use_captured(self):
        names = [t.name for t in self.r.tool_uses]
        self.assertIn("Write", names)

    def test_hooks_observed(self):
        self.assertTrue(self.r.hooks)
        self.assertTrue(all(h.event for h in self.r.hooks))

    def test_evidence_lists_denial(self):
        ev = self.r.evidence()
        self.assertEqual(len(ev["denials"]), 1)
        self.assertEqual(ev["denials"][0]["tool"], "Write")


class TestRobustness(unittest.TestCase):
    def test_malformed_lines_are_skipped(self):
        r = parse_stream(["{ hỏng", "", "không phải json", '{"type":"result","subtype":"success","result":"ok"}'])
        self.assertTrue(r.ok)
        self.assertEqual(r.text, "ok")

    def test_missing_result_event_is_an_error(self):
        """Tiến trình chết giữa chừng ≠ chạy xong nhưng thất bại."""
        r = parse_stream(['{"type":"assistant","message":{"content":[{"type":"text","text":"đang làm"}]}}'])
        self.assertFalse(r.ok)
        self.assertIn("result", r.error)

    def test_empty_stream(self):
        r = parse_stream([])
        self.assertFalse(r.ok)
        self.assertTrue(r.error)

    def test_non_dict_json_ignored(self):
        r = parse_stream(["[1,2,3]", '"chuỗi"', '{"type":"result","subtype":"success"}'])
        self.assertTrue(r.ok)

    def test_api_error_surfaces(self):
        r = parse_stream(['{"type":"result","subtype":"error","is_error":true,"api_error_status":"overloaded"}'])
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "overloaded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
