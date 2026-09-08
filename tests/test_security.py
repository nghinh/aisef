"""Rà soát bảo mật theo ngữ nghĩa — phân loại, lọc nhiễu, và chặn cổng.

Phán đoán "dữ liệu người dùng đi tới đâu" giao cho model; việc chấm
đạt/không đạt thì không — ngưỡng là code, đọc từ cấu hình.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import gate as story_gate  # noqa: E402
from aisef.control.security import (  # noqa: E402
    DEFAULT_BLOCKING,
    SEVERITIES,
    Finding,
    SecurityReport,
    is_noise,
    parse,
)
from aisef.harness.observe import Evidence  # noqa: E402
from aisef.harness.routing import ROLES, SECURITY  # noqa: E402

BAO_CAO = """
[critical] src/api/users.ts:12 — id lấy thẳng từ query rồi nối vào câu SQL
[high] src/auth.ts:40 — so sánh token bằng ==, rò rỉ theo thời gian
[medium] src/log.ts:9 — ghi email người dùng vào log
[low] src/app.ts:3 — thiếu header X-Frame-Options
"""


class TestParse(unittest.TestCase):
    def test_doc_du_bon_muc_va_sap_nghiem_truoc(self):
        r = parse(BAO_CAO)
        self.assertEqual([f.severity for f in r.findings],
                         ["critical", "high", "medium", "low"])

    def test_khong_co_phat_hien_la_ket_qua_hop_le(self):
        r = parse("không có phát hiện bảo mật")
        self.assertEqual(r.findings, [])
        self.assertFalse(r.error)
        self.assertIn("pass", r.summary())

    def test_rong_la_khong_cham_duoc_khong_phai_sach(self):
        """Rỗng đọc ra là "không có lỗ hổng" — kết luận ngược hẳn."""
        for x in ("", "   ", None):
            with self.subTest(x=x):
                r = parse(x)
                self.assertTrue(r.error)
                self.assertIn("CANNOT SCORE", r.summary())

    def test_sai_dinh_dang_cung_la_khong_cham_duoc(self):
        r = parse("tôi nghĩ code này ổn thôi")
        self.assertTrue(r.error)
        self.assertIn("format", r.error)

    def test_dong_thua_bi_bo_qua_khong_lam_hong_ca_bao_cao(self):
        r = parse("Mở đầu vài dòng.\n\n" + BAO_CAO + "\nKết luận: nên sửa.")
        self.assertEqual(len(r.findings), 4)

    def test_muc_nghiem_trong_khong_phan_biet_hoa_thuong(self):
        self.assertEqual(parse("[CRITICAL] a.ts:1 — x").findings[0].severity, "critical")


class TestLocNhieu(unittest.TestCase):
    def test_ba_nhom_gay_nhieu_bi_loai(self):
        for cum in ("thiếu giới hạn tần suất trên endpoint đăng nhập",
                    "có thể gây từ chối dịch vụ nếu gửi payload lớn",
                    "chuyển hướng mở trong tham số next"):
            with self.subTest(cum=cum):
                self.assertTrue(is_noise(cum))

    def test_loi_that_khong_bi_loai(self):
        for cum in ("id nối thẳng vào câu SQL",
                    "so sánh token không hằng thời gian",
                    "bí mật viết cứng trong mã"):
            with self.subTest(cum=cum):
                self.assertFalse(is_noise(cum))

    def test_muc_bi_loc_van_dem_duoc(self):
        """Lọc mà không nói đã lọc gì thì không ai kiểm lại được bộ lọc."""
        r = parse(BAO_CAO + "\n[high] api.ts:1 — thiếu giới hạn tần suất\n")
        self.assertEqual(len(r.filtered), 1)
        self.assertIn("1 items filtered", r.summary())
        self.assertNotIn("tần suất", " ".join(f.text for f in r.findings))


class TestNguong(unittest.TestCase):
    def test_mac_dinh_chan_critical_va_high(self):
        r = parse(BAO_CAO)
        self.assertEqual(DEFAULT_BLOCKING, ("critical", "high"))
        self.assertEqual([f.severity for f in r.blocking()], ["critical", "high"])

    def test_nguong_doc_tu_cau_hinh_khong_cung_trong_code(self):
        r = parse(BAO_CAO)
        self.assertEqual(len(r.blocking(("critical",))), 1)
        self.assertEqual(len(r.blocking(SEVERITIES)), 4)

    def test_chi_con_medium_low_thi_dat(self):
        r = parse("[medium] a.ts:1 — x\n[low] b.ts:2 — y")
        self.assertEqual(r.blocking(), [])
        self.assertIn("pass", r.summary())


class TestCong(unittest.TestCase):
    """Regression bắt buộc: phát hiện `high` làm story gate trượt."""

    def gate(self, security=None, **kw):
        ev = Evidence(story_id="STORY-01-01")
        return story_gate.evaluate(
            "STORY-01-01", ev, changed=[], write_scope=["src"], screens=[],
            review_blocking=[], security=security, **kw,
        )

    def muc(self, g, ten):
        return next(c for c in g.checks if c.name == ten)

    def test_phat_hien_high_lam_cong_truot(self):
        g = self.gate(parse("[high] src/auth.ts:1 — chiếm phiên được"))
        self.assertFalse(self.muc(g, "security").passed)
        self.assertFalse(g.passed)

    def test_phat_hien_critical_lam_cong_truot(self):
        g = self.gate(parse("[critical] src/api.ts:1 — thực thi mã từ xa"))
        self.assertFalse(self.muc(g, "security").passed)

    def test_chi_medium_thi_khong_chan(self):
        g = self.gate(parse("[medium] src/log.ts:1 — ghi email vào log"))
        self.assertTrue(self.muc(g, "security").passed)

    def test_chua_cau_hinh_la_bo_qua_co_ghi_lai_khong_phai_dat_am_tham(self):
        g = self.gate(None)
        muc = self.muc(g, "security")
        self.assertTrue(muc.skipped)
        self.assertIn("not configured", muc.detail)

    def test_khong_cham_duoc_thi_chan(self):
        """"Không chấm được" khác "sạch" — và phải chặn, không phải bỏ qua."""
        g = self.gate(SecurityReport(error="không chạy được: hết lượt"))
        self.assertFalse(self.muc(g, "security").passed)

    def test_nguong_truyen_vao_duoc_ton_trong(self):
        g = self.gate(parse("[high] a.ts:1 — x"), block_severities=["critical"])
        self.assertTrue(self.muc(g, "security").passed)


class TestVaiTro(unittest.TestCase):
    def test_nguoi_ra_soat_bao_mat_khong_sua_duoc_gi(self):
        """Nó đọc mã do agent khác viết — dữ liệu không tin được. Cho quyền
        ghi là mở đúng đường nó đang đi tìm."""
        vai = ROLES[SECURITY]
        for tool in ("Write", "Edit", "NotebookEdit"):
            self.assertIn(tool, vai.disallowed_tools)
        self.assertFalse(vai.may_resume)

    def test_prompt_noi_ro_diff_la_du_lieu_khong_tin_duoc(self):
        from aisef.harness.prompts import load_catalog

        body = load_catalog().get("story-security-review").body
        self.assertIn("không tin được", body)
        self.assertIn("không có phát hiện bảo mật", body)


class TestFinding(unittest.TestCase):
    def test_dong_in_ra_doc_duoc(self):
        self.assertEqual(Finding("high", "a.ts:1 — x").line(), "[high] a.ts:1 — x")


if __name__ == "__main__":
    unittest.main()
