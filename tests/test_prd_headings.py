"""Lỗi 19: khối tiêu chí của PRD có thể mang tiêu đề tiếng Việt hoặc tiếng Anh."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.normalize import parse_prd  # noqa: E402

VI = """## Yêu cầu chức năng

#### FR-1: Tạo ghi chú

Mô tả.

**Hệ quả kiểm chứng được:**
- Một thao tác là con trỏ vào ô soạn thảo.
- Tạo được khi offline.

#### FR-2: Sửa

Mô tả.

**Tiêu chí chấp nhận:**
- Lưu tự động sau 500ms.
"""

EN = VI.replace("**Hệ quả kiểm chứng được:**", "**Consequences (testable):**").replace("**Tiêu chí chấp nhận:**", "**Testable consequences:**")


class TestHeadings(unittest.TestCase):
    def test_vietnamese_headings_yield_criteria(self):
        prd = parse_prd(VI)
        self.assertEqual([len(r.acceptance_criteria) for r in prd.functional()], [2, 1])
        self.assertEqual(prd.untestable(), [])

    def test_english_headings_still_work(self):
        prd = parse_prd(EN)
        self.assertEqual([len(r.acceptance_criteria) for r in prd.functional()], [2, 1])


if __name__ == "__main__":
    unittest.main()
