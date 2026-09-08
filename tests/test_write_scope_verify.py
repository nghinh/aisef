"""Lỗi 21: story khai e2e/accessibility thì harness phải cấp phạm vi ghi cho thư mục test tương ứng."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.normalize import Story, effective_write_scope, verification_paths  # noqa: E402
from aisef.phases.story_split import render_story  # noqa: E402


class TestVerificationPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "tests" / "e2e").mkdir(parents=True)
        (self.project / "tests" / "a11y").mkdir(parents=True)
        (self.project / "src" / "store").mkdir(parents=True)
        (self.project / "src" / "store" / "db.test.ts").write_text("", encoding="utf-8")
        self.cfg = Config({**DEFAULTS, "verify.e2e": "npx playwright test tests/e2e",
                           "verify.accessibility": "npx playwright test tests/a11y",
                           "verify.migration": "npx vitest run src/store/db.test.ts --reporter=verbose",
                           "verify.perf": "npm run bench"})

    def tearDown(self):
        self._tmp.cleanup()

    def story(self, contract):
        return Story(id="STORY-01-06", epic_id="EPIC-01", title="x", write_scope=["src/ui/a.tsx"],
                     verification_contract=contract)

    def test_declared_kinds_grant_existing_paths_only(self):
        got = verification_paths(self.story(["unit", "e2e", "accessibility", "perf", "mockup-map"]), self.project, self.cfg)
        self.assertEqual(got, ["tests/e2e", "tests/a11y"])  # perf: không có đường dẫn có thật

    def test_file_path_in_command_counts(self):
        got = verification_paths(self.story(["migration"]), self.project, self.cfg)
        self.assertEqual(got, ["src/store/db.test.ts"])

    def test_no_contract_adds_nothing(self):
        self.assertEqual(verification_paths(self.story([]), self.project, self.cfg), [])

    def test_effective_scope_includes_granted_paths(self):
        (self.project / ".ai").mkdir()
        (self.project / ".ai" / "config.json").write_text(
            '{"verify.e2e": "npx playwright test tests/e2e"}', encoding="utf-8")
        scope = effective_write_scope(self.story(["e2e"]), self.project)
        self.assertIn("tests/e2e", scope)
        self.assertIn("src/ui/a.tsx", scope)

    def test_story_file_shows_granted_paths(self):
        (self.project / ".ai").mkdir()
        (self.project / ".ai" / "config.json").write_text(
            '{"verify.e2e": "npx playwright test tests/e2e"}', encoding="utf-8")
        root = self.project / "_bmad-output"; root.mkdir()
        text = render_story(self.story(["e2e"]), None, root)
        self.assertIn("Harness added", text)
        self.assertIn("`tests/e2e`", text)


if __name__ == "__main__":
    unittest.main()
