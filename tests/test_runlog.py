"""Nhật ký chạy (`_bmad-output/run.log`) — mỗi dòng FAIL phải kèm lý do.

Nhật ký tồn tại để debug. Một dòng `gate FAILED: guard ran,test,TDD,review`
không nói được điều gì, và dòng `gate=` cắt cứng ở 120 ký tự in đúng một lý
do, cắt giữa từ, giấu bảy lý do còn lại — đo trên todo/STORY-01-02 lượt 1:
8 phép kiểm trượt, người đọc biết lý do của 1.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401 — HostProvider thay chỗ docker (tests/__init__.py)

from aisef.harness.runlog import one_line, run_log  # noqa: E402


class TestMotDong(unittest.TestCase):
    def test_gap_xuong_dong_thanh_mot_dong(self):
        self.assertEqual(one_line("a\nb\n\nc"), "a · b · c")

    def test_cat_thi_noi_ro_da_cat(self):
        got = one_line("x" * 100, limit=20)
        self.assertTrue(got.startswith("x" * 20))
        self.assertIn("+80 chars", got, "cắt im lặng khiến lý do cụt trông như lý do đủ")

    def test_khong_cat_thi_khong_them_gi(self):
        self.assertEqual(one_line("ngắn"), "ngắn")

    def test_nhan_moi_kieu(self):
        self.assertEqual(one_line(None), "None")


class TestGhiVaXoay(unittest.TestCase):
    def test_ghi_them_dong_co_dau_thoi_gian(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_log(tmp, "story=S FAIL")
            noi_dung = (Path(tmp) / "run.log").read_text(encoding="utf-8")
            self.assertIn("story=S FAIL", noi_dung)
            self.assertRegex(noi_dung, r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ")


class TestLyDoTrongNhatKy(unittest.TestCase):
    """Chạy thật một story trượt cổng rồi đọc `run.log`."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from test_implement import ImplementTestCase, ScriptedClient

        self.case = ImplementTestCase("setUp")
        self.case.setUp()
        self.ScriptedClient = ScriptedClient

    def tearDown(self):
        self.case.tearDown()

    def chay(self, **kw):
        from aisef.phases.implement import implement_story

        implement_story(
            self.case.story, project=self.case.project, artifact_root=self.case.artifacts,
            client=self.ScriptedClient(**kw), config=self.case.config(),
        )
        return (self.case.artifacts / "run.log").read_text(encoding="utf-8")

    def test_moi_phep_kiem_truot_co_mot_dong_ly_do(self):
        log = self.chay(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        ten = [d.split("gate FAILED: ", 1)[1].strip()
               for d in log.splitlines() if "gate FAILED: " in d]
        self.assertTrue(ten, log)
        for name in ten[0].split(","):
            self.assertIn(f"gate ✗ {name} · ", log,
                          f"phép kiểm `{name}` trượt mà không có dòng lý do")

    def test_muc_chan_cua_reviewer_nam_trong_nhat_ky(self):
        log = self.chay(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        self.assertIn("review ✗ [chặn] src/a.py:1 — mất dữ liệu khi lưu", log)

    def test_nop_noi_ro_do_la_ket_qua_mong_doi(self):
        """`nop DONE ok=False` từng bị đọc là lỗi; đỏ ở parent mới là điều cần."""
        log = self.chay()
        if "nop DONE" in log:
            self.assertNotIn("nop DONE ok=", log)
            self.assertIn("at parent", log)


if __name__ == "__main__":
    unittest.main()
