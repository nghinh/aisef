"""Bảng R1–R14 phải trỏ tới thứ có thật.

Một bảng "bằng chứng" trỏ tới lớp test đã bị đổi tên còn tệ hơn không có
bảng: nó trông như đã kiểm. Test này đọc chính `docs/REQUIREMENTS-EVIDENCE.md`
và bắt lỗi khi có dòng trỏ tới chỗ không còn tồn tại.
"""

from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOC = ROOT / "docs" / "REQUIREMENTS-EVIDENCE.md"
_REF = re.compile(r"`(tests/test_[a-z_]+\.py)(?:::([A-Za-z0-9_]+))?`")
_ROW = re.compile(r"^\|\s*(R\d+)\s*\|", re.MULTILINE)


class TestEvidenceTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def test_every_requirement_has_a_row(self):
        found = set(_ROW.findall(self.text))
        self.assertEqual(found, {f"R{i}" for i in range(1, 15)})

    def test_referenced_files_exist(self):
        for path, _ in _REF.findall(self.text):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_referenced_test_classes_exist(self):
        """Đổi tên một lớp test mà quên sửa bảng thì bảng thành lời nói dối."""
        for path, cls_name in _REF.findall(self.text):
            if not cls_name:
                continue
            module = importlib.import_module(path[:-3].replace("/", "."))
            self.assertTrue(
                hasattr(module, cls_name), f"{path}::{cls_name} không còn tồn tại"
            )

    def test_referenced_docs_exist(self):
        for name in re.findall(r"`(docs/[A-Z-]+\.md)`", self.text):
            self.assertTrue((ROOT / name).is_file(), name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
