"""Cổng phát hành của **chính kho framework** — đọc bảng hợp quy bằng code.

Chạy với ``AISDLC_RELEASE=1``. Không có biến đó thì bỏ qua, để bộ test
thường không đỏ chỉ vì bảng chưa được chạy tuần này.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control import conformance as C  # noqa: E402


@unittest.skipUnless(os.environ.get("AISDLC_RELEASE") == "1", "chỉ khi phát hành (AISDLC_RELEASE=1)")
class TestCongPhatHanh(unittest.TestCase):
    def test_bang_hop_quy_du_va_moi(self):
        p = ROOT / C.REPORT_PATH
        self.assertTrue(p.is_file(), "chưa có docs/CONFORMANCE.md — chạy hợp quy trước")
        ok, why = C.release_ready(C.parse(p.read_text(encoding="utf-8")))
        self.assertTrue(ok, why)

    def test_nghiem_thu_dogfood_theo_pham_vi(self):
        """Corpus nghiệm thu (e9 EPIC-01, QĐ C-a 2026-09-06) phải có cổng
        `pre-deploy` **đạt theo phạm vi khai** và **được duyệt** trên đúng bản
        báo cáo ấy — đọc từ đĩa, không từ STATUS. Đường dẫn dự án qua
        ``AISDLC_ACCEPTANCE``; thiếu thì bỏ qua có nêu tên, không tính đạt."""
        import json

        from aisdlc.control.approvals import PRE_DEPLOY_REPORT, ApprovalStore, Gate, Status

        root = os.environ.get("AISDLC_ACCEPTANCE", "")
        if not root:
            self.skipTest("AISDLC_ACCEPTANCE=<dự án nghiệm thu> chưa đặt — chưa kiểm nghiệm thu dogfood")
        art = Path(root) / "_bmad-output"
        rep_path = art / PRE_DEPLOY_REPORT
        self.assertTrue(rep_path.is_file(), f"chưa có {rep_path} — chạy `aisdlc pre-deploy --epic E`")
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        self.assertTrue(rep.get("passed"), "pre-deploy của corpus nghiệm thu KHÔNG ĐẠT")
        scope = rep.get("scope") or {}
        self.assertTrue(scope.get("epic"), "báo cáo không khai phạm vi (`--epic`) — nghiệm thu gì?")
        self.assertIs(ApprovalStore(art).status(Gate.PRE_DEPLOY), Status.APPROVED,
                      "cổng pre-deploy chưa duyệt, hoặc duyệt trên bản báo cáo khác (stale)")
        # Loại miễn phải có lý do ghi trong báo cáo — miễn không lý do không phải bằng chứng.
        for kind, why in (rep.get("waivers") or {}).items():
            self.assertTrue(str(why).strip(), f"{kind} miễn không lý do")
