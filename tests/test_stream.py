"""Kiểm chứng bộ đọc stream-json trên luồng THẬT do `claude -p` sinh ra.

Hai fixture lấy từ spike S1/S2, không phải dữ liệu bịa: một lượt bình
thường và một lượt bị guard chặn.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.stream import (  # noqa: E402
    EXIT_STATUSES,
    RunResult,
    exit_status_of,
    parse_file,
    parse_stream,
)

FIX = ROOT / "tests" / "fixtures"
MINIMAL = FIX / "stream-minimal.jsonl"
BLOCKED = FIX / "stream-blocked.jsonl"
API_ERROR = FIX / "stream-api-error.jsonl"


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
        self.assertFalse(self.r.guard_blocked)
        self.assertFalse(self.r.permission_limited)
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

    def test_recognised_as_guard_block_not_permission_limit(self):
        """Guard chặn là lỗi chất lượng; hạn chế quyền thì không."""
        self.assertTrue(self.r.guard_blocked)
        self.assertFalse(self.r.permission_limited)

    def test_guard_message_captured_from_tool_result(self):
        """Claude Code không phát hook_response khi hook chặn — lý do nằm
        trong tool_result."""
        self.assertTrue(self.r.guard_messages)
        self.assertIn("hook", self.r.guard_messages[0].lower())

    def test_chu_hook_trong_loi_thuong_khong_phai_guard_chan(self):
        """Cờ `guard_blocked` phải nhận **thông báo của hook**, không phải
        mọi lỗi tool có chữ "hook".

        Dự án React nói về hook suốt ngày. Nhận diện bằng chuỗi con thì
        một `grep` hỏng trên `useEffect` cũng làm cờ bật, và cờ đó đi
        thẳng vào báo cáo nghiệm thu — người đọc đuổi theo lỗi không có
        thật. Đã mất một vòng chẩn đoán vì đúng chuyện này.
        """
        import json as _json

        def chay(body):
            return parse_stream([
                _json.dumps({"type": "user", "message": {"content": [
                    {"type": "tool_result", "is_error": True, "content": body},
                ]}}),
                _json.dumps({"type": "result", "subtype": "success"}),
            ])

        that = chay("PreToolUse:Bash hook error: [aisdlc guard destructive]: chặn")
        self.assertTrue(that.guard_blocked)
        self.assertEqual(len(that.guard_messages), 1)

        for gia in (
            "React hook useEffect gọi sai thứ tự",
            "Invalid hook call. Hooks can only be called inside a component.",
        ):
            with self.subTest(body=gia):
                self.assertFalse(chay(gia).guard_blocked)

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



@unittest.skipUnless(API_ERROR.is_file(), "chưa có fixture lỗi hạ tầng")
class TestInfrastructureFailure(unittest.TestCase):
    """Luồng thật của một lượt chạy đứt giữa chừng vì lỗi kết nối."""

    @classmethod
    def setUpClass(cls):
        cls.r = parse_file(API_ERROR)

    def test_marked_as_failed(self):
        self.assertFalse(self.r.ok)

    def test_error_message_is_meaningful(self):
        """`subtype` vẫn là "success" dù is_error=True — lấy nó ra sẽ cho
        thông báo lỗi "success", vô nghĩa với cả người lẫn logic thử lại."""
        self.assertEqual(self.r.error, "api_error")
        self.assertNotEqual(self.r.error, "success")

    def test_not_a_guard_block(self):
        """Đứt kết nối không phải agent làm sai — không được tính là lỗi
        chất lượng, vì hai loại này cần quyết định khác nhau."""
        self.assertFalse(self.r.guard_blocked)

    def test_permission_denials_are_environment_limits(self):
        """WebSearch bị từ chối vì môi trường, không phải vì guard."""
        self.assertTrue(self.r.permission_limited)
        self.assertTrue(any(d.tool_name == "WebSearch" for d in self.r.denials))

    def test_cost_still_recorded_on_failure(self):
        """Lượt chạy hỏng vẫn tốn tiền — evidence phải ghi lại."""
        self.assertGreater(self.r.cost_usd, 0)

    def test_evidence_separates_the_two_kinds(self):
        ev = self.r.evidence()
        self.assertFalse(ev["guard_blocked"])
        self.assertTrue(ev["permission_limited"])


class TestExitStatus(unittest.TestCase):
    """ADR-005 V11 (B): một bảng kết cục cho mọi client — `aisdlc status`
    đếm theo nó, vòng thử lại đọc nó thay vì dò chuỗi `error`."""

    def ket_cuc(self, result_event: dict) -> str:
        return exit_status_of(parse_stream([json.dumps({"type": "result", **result_event})]))

    def test_ok_tu_luong_that(self):
        self.assertEqual(exit_status_of(parse_file(MINIMAL)), "ok")

    def test_infra_tu_luong_that(self):
        self.assertEqual(exit_status_of(parse_file(API_ERROR)), "infra")

    def test_max_turns_theo_hinh_dang_e9(self):
        """e9 01-01 lượt 1 (61/60): `subtype` lỗi, `terminal_reason` max_turns."""
        self.assertEqual(self.ket_cuc({"subtype": "error_max_turns", "is_error": True,
                                       "terminal_reason": "max_turns", "num_turns": 61}), "max_turns")

    def test_max_turns_thang_ha_tang(self):
        """Lượt chạm trần thường kèm thông báo lỗi — xếp vào hạ tầng là thử lại miễn phí."""
        self.assertEqual(self.ket_cuc({"subtype": "error_max_turns", "is_error": True,
                                       "terminal_reason": "max_turns",
                                       "result": "API Error: connection reset"}), "max_turns")

    def test_timeout_do_client_cat(self):
        self.assertEqual(exit_status_of(RunResult(ok=False, error="quá 1800s")), "timeout")

    def test_cost(self):
        self.assertEqual(self.ket_cuc({"subtype": "error_max_budget_usd", "is_error": True}), "cost")

    def test_context(self):
        self.assertEqual(self.ket_cuc({
            "subtype": "success", "is_error": True, "api_error_status": 400,
            "result": "API Error: 400 prompt is too long: 210000 tokens > 200000 maximum",
        }), "context")

    def test_tien_trinh_chet_giua_chung_la_ha_tang(self):
        self.assertEqual(exit_status_of(parse_stream([])), "infra")

    def test_permission(self):
        self.assertEqual(self.ket_cuc({
            "subtype": "error_during_execution", "is_error": True,
            "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {}}],
        }), "permission")

    def test_error_khi_khong_biet_gi_hon(self):
        self.assertEqual(self.ket_cuc({"subtype": "error_during_execution", "is_error": True}), "error")
        self.assertEqual(exit_status_of(RunResult(ok=False, error="test đỏ")), "error")

    def test_bang_dong_va_moi_gia_tri_deu_sinh_duoc(self):
        sinh = {
            exit_status_of(parse_file(MINIMAL)), exit_status_of(parse_file(API_ERROR)),
            exit_status_of(parse_stream([])),
            exit_status_of(RunResult(ok=False, error="quá 1s")),
            exit_status_of(RunResult(ok=False, error="lạ")),
            self.ket_cuc({"subtype": "error_max_turns", "is_error": True}),
            self.ket_cuc({"subtype": "error_max_budget_usd", "is_error": True}),
            self.ket_cuc({"subtype": "success", "is_error": True, "result": "prompt is too long"}),
            self.ket_cuc({"subtype": "error_during_execution", "is_error": True,
                          "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t", "tool_input": {}}]}),
        }
        self.assertEqual(sinh, set(EXIT_STATUSES))

if __name__ == "__main__":
    unittest.main(verbosity=2)
