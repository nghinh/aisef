"""Lỗi 16: lời người rà soát phải được giữ nguyên văn và mục nhiều dòng không bị cụt."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.phases.implement import REVIEWS_DIR, blocking_findings, persist_verdict, plan_defects  # noqa: E402

REPORT = """# Rà soát

- [chặn] src/ui/app-shell.tsx:190-256 — toàn bộ phần nối dây của TCCN 1, 4, 6, 7
  chưa có test nào chạm tới; xoá đoạn này thì bộ test vẫn xanh.
- [bế tắc] Hai loại kiểm định `e2e` và `accessibility` mà story khai — không
  thể thêm test cho chúng từ trong write_scope: story chỉ cho ghi `src/**`,
  còn `tests/e2e` và `tests/a11y` nằm ngoài. Sửa write_scope rồi chạy lại.

- ghi chú thường, không phải mục chặn.
"""


class TestMultilineFindings(unittest.TestCase):
    def test_continuation_lines_belong_to_the_finding(self):
        f = blocking_findings(REPORT)
        self.assertEqual(len(f), 2)
        self.assertIn("xoá đoạn này thì bộ test vẫn xanh", f[0])
        self.assertTrue(f[1].startswith("[bế tắc]"))
        self.assertIn("tests/a11y", f[1])
        self.assertNotIn("ghi chú thường", " ".join(f))
        self.assertEqual(len(plan_defects(f)), 1)

    def test_single_line_findings_unchanged(self):
        self.assertEqual(blocking_findings("- [chặn] a\n- [chặn] b\n"), ["[chặn] a", "[chặn] b"])


class TestPersistVerdict(unittest.TestCase):
    def test_full_text_is_kept_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            r = RunResult(ok=True, text=REPORT, session_id="s1", num_turns=35, cost_usd=4.12)
            p = persist_verdict(d, "STORY-01-05", "review", 1, r)
            self.assertEqual(p, Path(d) / REVIEWS_DIR / "STORY-01-05-review-1.md")
            body = p.read_text(encoding="utf-8")
            self.assertIn("tests/a11y", body)
            self.assertIn("$4.12", body)


if __name__ == "__main__":
    unittest.main()
