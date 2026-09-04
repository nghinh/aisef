"""Bộ kiểm định — và điều quan trọng nhất: "chưa cấu hình" ≠ "đạt"."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisdlc.phases.qa import KINDS, command_for_kind, find_fake_tests, run_suite  # noqa: E402


class QaTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        return Config({**DEFAULTS, **over})

    def write(self, rel: str, text: str) -> Path:
        p = self.project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


class TestUnconfiguredIsNotPassing(QaTestCase):
    def test_nothing_configured_is_not_release_ready(self):
        """Bộ kiểm định báo xanh vì tám trên tám loại chưa từng chạy còn
        nguy hiểm hơn không có bộ kiểm định nào."""
        r = run_suite(self.project, config=self.config(), has_ui=False)
        self.assertFalse(r.release_ready)
        self.assertTrue(r.unconfigured)
        self.assertIn("chưa chạy thì không được gọi là đã kiểm", r.summary())

    def test_story_level_tolerates_unconfigured(self):
        """Ở mức story thì cảnh báo là đủ — chặn từng story vì thiếu k6 sẽ
        khiến người ta tắt cả bộ kiểm định."""
        r = run_suite(self.project, config=self.config(), has_ui=False)
        self.assertTrue(r.passed)

    def test_waiver_must_be_explicit(self):
        cfg = self.config(**{"verify.waived": "perf,mutation"})
        r = run_suite(self.project, config=cfg, has_ui=False)
        ids = [x.kind.id for x in r.unconfigured]
        self.assertNotIn("perf", ids)
        self.assertIn("uat", ids)

    def test_ui_checks_skipped_without_ui(self):
        r = run_suite(self.project, config=self.config(), has_ui=False)
        e2e = next(x for x in r.results if x.kind.id == "e2e")
        self.assertIn("không có giao diện", e2e.skipped)


class TestRunningChecks(QaTestCase):
    def test_green_check_passes(self):
        cfg = self.config(**{"verify.unit": "true"})
        r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        unit = r.results[0]
        self.assertTrue(unit.ran)
        self.assertTrue(unit.ok)

    def test_red_check_fails_the_suite(self):
        cfg = self.config(**{"verify.unit": "false"})
        r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        self.assertFalse(r.passed)
        self.assertEqual(len(r.failed), 1)

    def test_output_tail_kept_for_diagnosis(self):
        cfg = self.config(**{"verify.unit": "sh -c 'echo dòng lỗi cuối; exit 1'"})
        r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        self.assertIn("dòng lỗi cuối", r.results[0].detail)

    def test_evidence_recorded(self):
        cfg = self.config(**{"verify.unit": "true"})
        run_suite(self.project, config=cfg, only=["unit"], has_ui=False,
                  story_id="S-01", artifact_root=self.artifacts)
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "qa:unit")
        self.assertIsNotNone(e)
        self.assertTrue(e.ok)

    def test_unit_falls_back_to_the_project_test_command(self):
        cfg = self.config(**{"tools.test": "pytest -q"})
        self.assertEqual(command_for_kind("unit", self.project, cfg), "pytest -q")

    def test_config_beats_stack_default(self):
        self.write("pyproject.toml", "")
        cfg = self.config(**{"verify.security": "semgrep --error"})
        self.assertEqual(command_for_kind("security", self.project, cfg), "semgrep --error")

    def test_stack_default_used_when_nothing_configured(self):
        self.write("package.json", "{}")
        self.assertEqual(
            command_for_kind("e2e", self.project, self.config()), "npx playwright test"
        )


class TestFakeTests(QaTestCase):
    """Test luôn xanh dù code hỏng tệ hơn không có test — nó tạo cảm giác
    an toàn giả."""

    def test_python_test_without_assertions_is_flagged(self):
        self.write("tests/test_a.py", "def test_gi_do():\n    x = 1 + 1\n")
        self.assertEqual(find_fake_tests(self.project), ["tests/test_a.py"])

    def test_python_test_with_assertion_is_fine(self):
        self.write("tests/test_a.py", "def test_gi_do():\n    assert 1 + 1 == 2\n")
        self.assertEqual(find_fake_tests(self.project), [])

    def test_unittest_style_assertion_counts(self):
        self.write("tests/test_b.py",
                   "class T:\n    def test_x(self):\n        self.assertEqual(1, 1)\n")
        self.assertEqual(find_fake_tests(self.project), [])

    def test_js_expect_counts(self):
        self.write("src/a.test.ts", "it('chạy', () => { expect(1).toBe(1) })\n")
        self.assertEqual(find_fake_tests(self.project), [])

    def test_js_test_without_expectation_is_flagged(self):
        self.write("src/a.test.ts", "it('chạy', () => { render(<App/>) })\n")
        self.assertEqual(find_fake_tests(self.project), ["src/a.test.ts"])

    def test_non_test_files_ignored(self):
        self.write("src/app.py", "def helper():\n    return 1\n")
        self.assertEqual(find_fake_tests(self.project), [])

    def test_suite_fails_on_fake_tests(self):
        self.write("tests/test_a.py", "def test_gi_do():\n    pass\n")
        r = run_suite(self.project, config=self.config(), has_ui=False)
        self.assertFalse(r.passed)
        self.assertIn("test giả", r.summary())

    def test_only_changed_files_when_given(self):
        self.write("tests/test_cu.py", "def test_x():\n    pass\n")
        self.write("tests/test_moi.py", "def test_y():\n    pass\n")
        self.assertEqual(
            find_fake_tests(self.project, ["tests/test_moi.py"]), ["tests/test_moi.py"]
        )

    def test_vendor_directories_are_not_the_project(self):
        """Kho tham chiếu và node_modules không phải mã của dự án."""
        self.write("node_modules/x/a.test.js", "it('x', () => {})\n")
        self.write("references/y/tests/test_z.py", "def test_z():\n    pass\n")
        self.assertEqual(find_fake_tests(self.project), [])

    def test_git_decides_what_belongs_to_the_project(self):
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        self.write(".gitignore", "bo-qua/\n")
        self.write("tests/test_a.py", "def test_x():\n    pass\n")
        subprocess.run(["git", "add", "tests"], cwd=self.project, check=True)
        self.write("bo-qua/test_b.py", "def test_y():\n    pass\n")
        self.assertEqual(find_fake_tests(self.project), ["tests/test_a.py"])

    def test_uncommitted_test_is_still_checked(self):
        """Test giả vừa viết xong thì chưa nằm trong chỉ mục git — mà đó
        đúng là lúc cần bắt nó nhất."""
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        self.write("tests/test_moi.py", "def test_x():\n    pass\n")
        self.assertEqual(find_fake_tests(self.project), ["tests/test_moi.py"])


class TestKinds(unittest.TestCase):
    def test_every_kind_says_why_it_exists(self):
        for kind in KINDS.values():
            self.assertTrue(len(kind.why) > 20, kind.id)

    def test_read_only_checks_do_not_get_write_access(self):
        self.assertFalse(KINDS["security"].level.writable)


if __name__ == "__main__":
    unittest.main(verbosity=2)
