"""Bằng chứng story — cơ sở cho cổng và cho guard `completion`."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.stream import parse_file  # noqa: E402
from aisef.harness.observe import (  # noqa: E402
    AGENT_RUN,
    TOOL_RUN,
    EvidenceStore,
    Event,
)

FIX = ROOT / "tests" / "fixtures"


class EvidenceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestRecording(EvidenceTestCase):
    def test_sequence_is_assigned_by_the_file_not_the_caller(self):
        """Hai tiến trình cùng ghi một story là chuyện bình thường khi chạy
        song song; thứ tự phải do file quyết định."""
        self.store.file_change("S-01", "a.py")
        other = EvidenceStore(self.store.root.parent)  # tiến trình khác
        other.tool_run("S-01", "test", ok=True)
        seqs = [e.seq for e in self.store.read("S-01").events]
        self.assertEqual(seqs, [1, 2])

    def test_events_survive_a_reread(self):
        self.store.tool_run("S-01", "lint", ok=False, duration_ms=120,
                            detail={"tail": "3 lỗi"})
        e = self.store.read("S-01").last(TOOL_RUN, "lint")
        self.assertFalse(e.ok)
        self.assertEqual(e.duration_ms, 120)
        self.assertEqual(e.detail["tail"], "3 lỗi")

    def test_broken_line_does_not_lose_the_file(self):
        self.store.tool_run("S-01", "test", ok=True)
        with self.store.path("S-01").open("a", encoding="utf-8") as fh:
            fh.write("{ hỏng\n")
        self.store.tool_run("S-01", "lint", ok=True)
        self.assertEqual(len(self.store.read("S-01").events), 2)

    def test_unknown_story_reads_empty(self):
        self.assertEqual(self.store.read("khong-co").events, [])

    def test_lists_stories(self):
        self.store.tool_run("S-01", "test", ok=True)
        self.store.tool_run("S-02", "test", ok=True)
        self.assertEqual(self.store.stories(), ["S-01", "S-02"])


class TestCompletionQuestions(EvidenceTestCase):
    """Ba câu hỏi guard `completion` cần trả lời."""

    def test_no_test_run_at_all(self):
        ev = self.store.read("S-01")
        self.assertFalse(ev.tests_green())

    def test_last_run_red(self):
        self.store.tool_run("S-01", "test", ok=True)
        self.store.tool_run("S-01", "test", ok=False)
        self.assertFalse(self.store.read("S-01").tests_green())

    def test_file_changed_after_the_green_run(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True)
        self.store.file_change("S-01", "src/b.py")
        ev = self.store.read("S-01")
        self.assertTrue(ev.tests_green())
        self.assertEqual(ev.stale_since_last_test(), ["src/b.py"])

    def test_nothing_stale_after_a_fresh_run(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True)
        self.assertEqual(self.store.read("S-01").stale_since_last_test(), [])

    def test_every_change_counts_when_tests_never_ran(self):
        self.store.file_change("S-01", "src/a.py")
        self.assertEqual(self.store.read("S-01").stale_since_last_test(), ["src/a.py"])


class TestCostAndLatency(EvidenceTestCase):
    def test_agent_run_takes_numbers_from_the_real_stream(self):
        """Chi phí và độ trễ lấy từ luồng client, không tự đoán."""
        result = parse_file(FIX / "stream-minimal.jsonl")
        self.store.agent_run("S-01", result)
        e = self.store.read("S-01").last(AGENT_RUN)
        self.assertEqual(e.cost_usd, result.cost_usd)
        self.assertEqual(e.duration_ms, result.duration_ms)
        self.assertGreater(e.tokens["cache_creation"], 0)

    def test_failed_run_still_records_cost(self):
        result = parse_file(FIX / "stream-api-error.jsonl")
        self.store.agent_run("S-01", result)
        e = self.store.read("S-01").last(AGENT_RUN)
        self.assertFalse(e.ok)
        self.assertGreater(e.cost_usd, 0)
        self.assertEqual(e.detail["error"], "api_error")

    def test_ket_cuc_chuan_hoa_duoc_ghi(self):
        """ADR-005 V11 (B): `status` đếm theo `exit_status`, không dò lại chuỗi `error`."""
        self.store.agent_run("S-01", parse_file(FIX / "stream-api-error.jsonl"))
        self.assertEqual(self.store.read("S-01").last(AGENT_RUN).detail["exit_status"], "infra")
        self.store.agent_run("S-02", parse_file(FIX / "stream-minimal.jsonl"))
        self.assertEqual(self.store.read("S-02").last(AGENT_RUN).detail["exit_status"], "ok")

    def test_totals_accumulate(self):
        self.store.record("S-01", Event(kind=AGENT_RUN, cost_usd=1.5, duration_ms=100))
        self.store.record("S-01", Event(kind=AGENT_RUN, cost_usd=0.5, duration_ms=200))
        ev = self.store.read("S-01")
        self.assertAlmostEqual(ev.total_cost_usd, 2.0)
        self.assertEqual(ev.total_duration_ms, 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestGuardBlocks(unittest.TestCase):
    def test_doc_lai_duoc_nhung_lan_guard_chan(self):
        import tempfile
        from aisef.harness.observe import GUARD_BLOCK, Event, EvidenceStore
        with tempfile.TemporaryDirectory() as tmp:
            st = EvidenceStore(tmp)
            st.record("S-01", Event(kind=GUARD_BLOCK, name="write-scope", ok=False,
                                    detail={"tool": "Write", "reason": "ngoài phạm vi"}))
            st.tool_run("S-01", "test", ok=True)
            ev = st.read("S-01")
            self.assertEqual([e.name for e in ev.guard_blocks], ["write-scope"])
            self.assertIn("guard_block=1", ev.summary())


class TestSoThuTuKhongDuocDatLai(unittest.TestCase):
    """Lỗi 42. `_next_seq` chỉ đọc 4096 byte cuối. Một sự kiện dài hơn thế —
    phán quyết rà soát kèm findings, đuôi output của tool — làm cửa sổ ấy chỉ
    chứa một dòng cụt: không parse được gì, hàm trả `1`, và **số thứ tự đặt
    lại giữa tệp**.

    `read()` sắp theo `seq`, nên sự kiện của lượt cũ (seq lớn) xếp *sau* sự
    kiện của lượt này (seq nhỏ), và mọi phép kiểm đọc "kết quả mới nhất" đọc
    nhầm bản cũ. Đo trên todo/STORY-01-02 2026-09-09: 3 lần đặt lại trong một
    tệp, mỗi lần ngay sau một dòng > 4 KB; cổng báo "bằng chứng ghi ở ứng viên
    e7a81a6" trong khi mọi phép kiểm vừa chạy ở dd88027, và story trượt.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_su_kien_dai_khong_lam_dat_lai_so(self):
        st = EvidenceStore(self.root)
        st.record("S", Event(kind="tool_run", name="test", detail={"tail": "x" * 8000}))
        e = st.record("S", Event(kind="tool_run", name="lint"))
        self.assertEqual(e.seq, 2, "sự kiện dài làm số thứ tự quay về 1")

    def test_tien_trinh_moi_van_doc_duoc_so_cuoi(self):
        EvidenceStore(self.root).record(
            "S", Event(kind="tool_run", name="test", detail={"tail": "y" * 20000}))
        e = EvidenceStore(self.root).record("S", Event(kind="tool_run", name="lint"))
        self.assertEqual(e.seq, 2)

    def test_doc_theo_thoi_gian_chua_lanh_tep_da_hong(self):
        """Tệp ghi bằng bản cũ đã mang số đặt lại — đọc theo `at` chữa được."""
        path = EvidenceStore(self.root).path("S")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"kind": "tool_run", "name": "test", "seq": 300, "at": 100.0,
                        "detail": {"candidate": "cu"}}) + "\n"
            + json.dumps({"kind": "tool_run", "name": "test", "seq": 2, "at": 200.0,
                          "detail": {"candidate": "moi"}}) + "\n",
            encoding="utf-8")
        ev = EvidenceStore(self.root).read("S")
        self.assertEqual(ev.events[-1].detail["candidate"], "moi",
                         "sự kiện mới nhất phải là sự kiện xảy ra sau cùng")
