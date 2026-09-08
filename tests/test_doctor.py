"""Doctor — kiểm hàm nội bộ không cần gọi model hay cài tool."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

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
