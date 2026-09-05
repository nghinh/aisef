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
