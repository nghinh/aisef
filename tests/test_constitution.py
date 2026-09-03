"""Kiểm chứng sinh hiến pháp kỹ thuật cho dự án đích."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.kit.constitution import (  # noqa: E402
    CLIENT_FILES,
    Constitution,
    write_for_project,
)
from aisdlc.kit.detect_stack import detect


class TestRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = Constitution.load()

    def render(self, text: str, name: str = "DuAn") -> str:
        return self.c.render(name, detect(text))

    def test_includes_principles_and_prohibitions(self):
        out = self.render("Backend Python.")
        self.assertIn("Hiểu trước khi viết", out)
        self.assertIn("Tuyệt đối không", out)

    def test_evidence_principle_present(self):
        """Nguyên tắc nền của mọi cổng phải có mặt."""
        self.assertIn("Bằng chứng, không tự khai", self.render("Python."))

    def test_python_quality_commands(self):
        out = self.render("Backend Python FastAPI.")
        for cmd in ("ruff check .", "mypy .", "pytest --cov"):
            self.assertIn(cmd, out)

    def test_react_quality_commands(self):
        self.assertIn("npx tsc --noEmit", self.render("Frontend React."))

    def test_no_commands_for_undetected_stack(self):
        """Không nhắc lệnh của công nghệ dự án không dùng."""
        out = self.render("Backend Python.")
        self.assertNotIn("cargo", out)
        self.assertNotIn("gradlew", out)

    def test_ui_section_only_when_ui(self):
        self.assertIn("Story có giao diện", self.render("Frontend React."))
        self.assertNotIn("Story có giao diện", self.render("Công cụ dòng lệnh Python."))

    def test_undetermined_is_surfaced_not_guessed(self):
        out = self.render("Ứng dụng quản lý công việc.")
        self.assertIn("Chưa chốt", out)
        self.assertIn("không tự chọn", out)

    def test_warns_against_hand_editing(self):
        self.assertIn("Không sửa tay", self.render("Python."))

    def test_project_name_in_title(self):
        self.assertIn("BookStore", self.render("Python.", "BookStore"))

    def test_attribution_to_source(self):
        """Nguồn Karpathy phải được ghi công, vì kho gốc không có license."""
        self.assertIn("Karpathy", self.render("Python."))


class TestWrite(unittest.TestCase):
    def test_writes_file_per_client(self):
        with tempfile.TemporaryDirectory() as d:
            written = write_for_project(d, "DuAn", detect("Python, Docker."))
            self.assertEqual(len(written), len(CLIENT_FILES))
            for p in written:
                self.assertTrue(p.is_file())

    def test_claude_and_opencode_get_same_content(self):
        """Một nguồn, nhiều đích — không duy trì hai bản dễ lệch."""
        with tempfile.TemporaryDirectory() as d:
            write_for_project(d, "DuAn", detect("Python."))
            a = (Path(d) / "CLAUDE.md").read_text(encoding="utf-8")
            b = (Path(d) / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(a, b)

    def test_rewrite_is_stable(self):
        with tempfile.TemporaryDirectory() as d:
            write_for_project(d, "DuAn", detect("Python."))
            first = (Path(d) / "CLAUDE.md").read_text(encoding="utf-8")
            write_for_project(d, "DuAn", detect("Python."))
            self.assertEqual(first, (Path(d) / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_single_client(self):
        with tempfile.TemporaryDirectory() as d:
            written = write_for_project(d, "DuAn", detect("Python."), clients=["claude"])
            self.assertEqual([p.name for p in written], ["CLAUDE.md"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
