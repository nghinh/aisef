"""Kiểm mốc ghim kho tham chiếu — phân tích và so sánh, **không gọi mạng**."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.pins.__main__ import (  # noqa: E402
    CATALOG, PINS, bao_cao, doc_catalog, doc_pins, main, nguon, so_sanh)


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

    def test_nguon_skill_lay_tu_danh_muc_phat_hanh_chu_khong_go_tay(self):
        """Danh sách gõ tay sẽ trôi khỏi `catalog.json`, và một nguồn skill rơi
        khỏi danh sách là một nguồn không ai canh."""
        cat = doc_catalog(CATALOG.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cat), 3)
        self.assertTrue(all(m["skill"] and m["sha"] and m["kho"].count("/") == 1 for m in cat))

    def test_hop_nhat_khong_dem_mot_kho_hai_lan(self):
        """`bmad` trong danh mục và `bmad-method` trong PINS là **một** kho."""
        muc = nguon(PINS.read_text(encoding="utf-8"), CATALOG.read_text(encoding="utf-8"))
        kho = [m["kho"] for m in muc]
        self.assertEqual(len(kho), len(set(kho)))
        bmad = [m for m in muc if m["kho"].endswith("/bmad-method")]
        self.assertEqual(len(bmad), 1)
        self.assertTrue(bmad[0]["skill"], "kho có trong danh mục phát hành phải mang cờ nguồn skill")


class TestSoSanh(unittest.TestCase):
    def setUp(self):
        self.ghim = [{"ten": "karpathy", "url": "u", "sha": "abc1234", "nhanh": "main",
                      "kho": "o/karpathy-skills", "skill": True},
                     {"ten": "serena", "url": "u", "sha": "def5678", "nhanh": "main",
                      "kho": "o/serena", "skill": False}]

    def test_sha_ngan_khop_sha_dai_van_la_dung_yen(self):
        ra = so_sanh(self.ghim, {"o/karpathy-skills": "abc1234def", "o/serena": "def5678"})
        self.assertEqual([m["trang_thai"] for m in ra], ["đứng yên", "đứng yên"])

    def test_khong_hoi_duoc_khong_duoc_bao_la_dung_yen(self):
        """Mạng hỏng mà in "đứng yên" là kiểu im lặng nguy hiểm nhất ở đây."""
        ra = so_sanh(self.ghim, {})
        self.assertEqual({m["trang_thai"] for m in ra}, {"không hỏi được"})

    def test_da_chay_tiep_thi_noi_ro_va_nhac_quet_lai(self):
        ra = so_sanh(self.ghim, {"o/karpathy-skills": "9999999", "o/serena": "def5678"})
        bc = bao_cao(ra)
        self.assertIn("1 đã chạy tiếp", bc)
        self.assertIn("Nguồn skill đã chạy tiếp: karpathy", bc)

    def test_kho_cong_cu_chay_tiep_thi_khong_nhac_quet_skill(self):
        """Công cụ chạy tiếp là tin tức; chỉ nguồn skill mới là việc bảo mật."""
        bc = bao_cao(so_sanh(self.ghim, {"o/karpathy-skills": "abc1234", "o/serena": "9999999"}))
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

    def test_khong_doc_duoc_ghim_nao_thi_thoat_2(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pins = Path(d) / "PINS.md"
            pins.write_text("không có bảng nào", encoding="utf-8")
            cat = Path(d) / "catalog.json"
            cat.write_text('{"sources": []}', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--offline", "--pins", str(pins), "--catalog", str(cat)]), 2)

    def test_mat_PINS_van_canh_duoc_nguon_skill(self):
        """`PINS.md` là bản ghi nghiên cứu, có thể vắng trên máy khác; danh mục
        phát hành thì luôn đi cùng gói, và nó mới là thứ phải canh."""
        import contextlib
        import io
        ra = io.StringIO()
        with contextlib.redirect_stdout(ra):
            ma = main(["--offline", "--pins", "/khong/co/PINS.md"])
        self.assertEqual(ma, 0)
        self.assertIn("nguồn skill", ra.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
