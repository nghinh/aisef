"""Kiểm mốc ghim kho tham chiếu — phân tích và so sánh, **không gọi mạng**."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.pins.__main__ import (  # noqa: E402
    NGUON_SKILL, PINS, bao_cao, doc_pins, main, so_sanh)


class TestDocBangGhim(unittest.TestCase):
    def test_doc_duoc_bang_that_trong_kho(self):
        muc = doc_pins(PINS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(muc), 10)
        for m in muc:
            with self.subTest(kho=m["ten"]):
                self.assertRegex(m["sha"], r"^[0-9a-f]{7,40}$")
                self.assertEqual(m["kho"].count("/"), 1)
                self.assertIn(m["nhanh"], ("main", "master"))

    def test_ten_bo_phan_chu_thich_trong_ngoac(self):
        """`playwright-monorepo (sparse: …)` phải ra tên gọn, để so khớp được."""
        muc = doc_pins(PINS.read_text(encoding="utf-8"))
        self.assertIn("playwright-monorepo", [m["ten"] for m in muc])

    def test_dong_khong_phai_bang_ghim_thi_bo_qua(self):
        self.assertEqual(doc_pins("| a | b | c |\n# tiêu đề\nvăn xuôi"), [])

    def test_moi_nguon_skill_deu_co_trong_bang(self):
        """Danh sách nguồn skill mà lệch khỏi bảng ghim thì cổng đỏ vô nghĩa."""
        ten = {m["ten"] for m in doc_pins(PINS.read_text(encoding="utf-8"))}
        self.assertEqual(set(NGUON_SKILL) - ten, set())


class TestSoSanh(unittest.TestCase):
    def setUp(self):
        self.ghim = [{"ten": "karpathy-skills", "url": "u", "sha": "abc1234", "nhanh": "main",
                      "kho": "o/karpathy-skills"},
                     {"ten": "serena", "url": "u", "sha": "def5678", "nhanh": "main",
                      "kho": "o/serena"}]

    def test_sha_ngan_khop_sha_dai_van_la_dung_yen(self):
        ra = so_sanh(self.ghim, {"karpathy-skills": "abc1234def", "serena": "def5678"})
        self.assertEqual([m["trang_thai"] for m in ra], ["đứng yên", "đứng yên"])

    def test_khong_hoi_duoc_khong_duoc_bao_la_dung_yen(self):
        """Mạng hỏng mà in "đứng yên" là kiểu im lặng nguy hiểm nhất ở đây."""
        ra = so_sanh(self.ghim, {})
        self.assertEqual({m["trang_thai"] for m in ra}, {"không hỏi được"})

    def test_da_chay_tiep_thi_noi_ro_va_nhac_quet_lai(self):
        ra = so_sanh(self.ghim, {"karpathy-skills": "9999999", "serena": "def5678"})
        bc = bao_cao(ra)
        self.assertIn("1 đã chạy tiếp", bc)
        self.assertIn("Nguồn skill đã chạy tiếp: karpathy-skills", bc)

    def test_kho_cong_cu_chay_tiep_thi_khong_nhac_quet_skill(self):
        """Công cụ chạy tiếp là tin tức; chỉ nguồn skill mới là việc bảo mật."""
        bc = bao_cao(so_sanh(self.ghim, {"karpathy-skills": "abc1234", "serena": "9999999"}))
        self.assertIn("1 đã chạy tiếp", bc)
        self.assertNotIn("Nguồn skill đã chạy tiếp", bc)


class TestMaThoat(unittest.TestCase):
    def test_offline_khong_goi_mang_va_thoat_0(self):
        import contextlib
        import io
        ra = io.StringIO()
        with contextlib.redirect_stdout(ra):
            ma = main(["--offline"])
        self.assertEqual(ma, 0)
        self.assertIn("không hỏi được", ra.getvalue())

    def test_khong_doc_duoc_bang_thi_thoat_2(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "PINS.md"
            p.write_text("không có bảng nào", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--offline", "--pins", str(p)]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
