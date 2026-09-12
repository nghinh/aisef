"""Doctor — kiểm hàm nội bộ không cần gọi model hay cài tool."""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.cli.doctor import _hook_paths_elsewhere  # noqa: E402


class TestHookPathsElsewhere(unittest.TestCase):
    def test_no_hooks_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_hook_paths_elsewhere(Path(d)))

    def test_settings_same_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            claude = p / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(
                f'{{"hooks": "aisef --project {p} guard"}}',
            )
            result = _hook_paths_elsewhere(p)
            self.assertEqual(result, [])

    def test_settings_different_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            claude = p / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(
                '{"hooks": "aisef --project /other/proj guard"}',
            )
            result = _hook_paths_elsewhere(p)
            self.assertIn("/other/proj", result)

    def test_opencode_plugin_same_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            plugin_dir = p / ".opencode" / "plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "aisef-guard.ts").write_text(
                f'const PROJECT = "{p}";',
            )
            result = _hook_paths_elsewhere(p)
            self.assertEqual(result, [])

    def test_opencode_plugin_different_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            plugin_dir = p / ".opencode" / "plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "aisef-guard.ts").write_text(
                'const PROJECT = "/somewhere/else";',
            )
            result = _hook_paths_elsewhere(p)
            self.assertIn("/somewhere/else", result)

    def test_both_hooks_mixed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            claude = p / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(
                f'{{"hooks": "aisef --project {p} guard"}}',
            )
            plugin_dir = p / ".opencode" / "plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "aisef-guard.ts").write_text(
                'const PROJECT = "/other/place";',
            )
            result = _hook_paths_elsewhere(p)
            self.assertEqual(result, ["/other/place"])


if __name__ == "__main__":
    unittest.main()


class TestDoctorNoiRoPhienAgentDangNhapBangGi(unittest.TestCase):
    """Biến môi trường nào quyết định danh tính của phiên agent — nêu tên, không nêu giá trị.

    Ngày 2026-09-12 một `ANTHROPIC_API_KEY` hết hạn trong shell ghi đè login
    `claude.ai` đang chạy được; triệu chứng duy nhất là mọi phiên trả 401 sau
    khi đốt hết thời gian chờ. `doctor` là nơi người vận hành nhìn *trước* khi
    trả tiền, nên nó phải nói ra điều này.
    """

    def _chay(self, env: dict) -> str:
        import io
        from contextlib import redirect_stdout
        from aisef.cli.doctor import cmd_doctor

        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", env, clear=False), \
             redirect_stdout(io.StringIO()) as ra:
            cmd_doctor(argparse.Namespace(project=d))
        return ra.getvalue()

    def test_neu_ten_bien_khi_co_khoa_trong_moi_truong(self):
        ra = self._chay({"ANTHROPIC_API_KEY": "sk-BI-MAT-KHONG-DUOC-IN"})
        self.assertIn("ANTHROPIC_API_KEY", ra)
        self.assertNotIn("sk-BI-MAT", ra, "giá trị khoá không bao giờ được in")

    def test_khong_co_khoa_thi_noi_client_tu_dang_nhap(self):
        import os as _os
        sach = {n: "" for n in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                                "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL")}
        with mock.patch.dict(_os.environ, sach, clear=False):
            ra = self._chay({})
        self.assertIn("agent credential", ra)
        self.assertIn("its own login", ra)
