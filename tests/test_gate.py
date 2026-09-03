"""Cổng story — năm điều kiện, chấm từ bằng chứng chứ không từ lời kể."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.gate import evaluate  # noqa: E402
from aisdlc.harness.observe import MOCKUP_MAP, EvidenceStore, Event  # noqa: E402


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def green_story(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True)
        self.store.tool_run("S-01", "lint", ok=True)

    def gate(self, **kw):
        params = {
            "changed": ["src/a.py"],
            "write_scope": ["src"],
            "screens": [],
            "review_blocking": [],
        }
        params.update(kw)
        return evaluate("S-01", self.store.read("S-01"), **params)


class TestHappyPath(GateTestCase):
    def test_all_conditions_met(self):
        self.green_story()
        g = self.gate()
        self.assertTrue(g.passed, g.summary())
        self.assertEqual(g.failures, [])


class TestTests(GateTestCase):
    def test_no_test_run_fails(self):
        self.store.tool_run("S-01", "lint", ok=True)
        self.assertFalse(self.gate().passed)

    def test_red_test_fails(self):
        self.store.tool_run("S-01", "test", ok=False)
        self.store.tool_run("S-01", "lint", ok=True)
        self.assertFalse(self.gate().passed)

    def test_edit_after_green_fails(self):
        """Xanh rồi sửa tiếp là kiểu "xanh" hay gặp nhất khi agent vội."""
        self.green_story()
        self.store.file_change("S-01", "src/b.py")
        g = self.gate()
        self.assertFalse(g.passed)
        self.assertIn("test", [c.name for c in g.failures])


class TestLint(GateTestCase):
    def test_lint_never_run_fails(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True)
        self.assertFalse(self.gate().passed)

    def test_project_without_lint_command_is_skipped_not_failed(self):
        """Dự án chưa khai lệnh lint ≠ lint bẩn."""
        self.green_story()
        self.store.tool_run("S-01", "lint", ok=False,
                            detail={"skipped": "dự án chưa khai lệnh cho tool này"})
        g = self.gate()
        self.assertTrue(g.passed, g.summary())


class TestScope(GateTestCase):
    def test_file_outside_scope_fails(self):
        self.green_story()
        g = self.gate(changed=["src/a.py", "infra/deploy.yaml"])
        self.assertFalse(g.passed)
        self.assertIn("phạm vi ghi", [c.name for c in g.failures])


class TestMockupMap(GateTestCase):
    def record_map(self, screen: str, ok: bool, **detail):
        self.store.record("S-01", Event(kind=MOCKUP_MAP, name=screen, ok=ok,
                                        detail={"missing": [], "missing_data_roles": [], **detail}))

    def test_story_without_screens_skips_the_check(self):
        self.green_story()
        g = self.gate(screens=[])
        self.assertTrue(g.passed)
        self.assertTrue(any(c.skipped for c in g.checks))

    def test_screen_never_compared_fails(self):
        """Không đối chiếu **không** phải là đạt."""
        self.green_story()
        g = self.gate(screens=["danh-sach"])
        self.assertFalse(g.passed)
        self.assertIn("chưa đối chiếu", g.feedback())

    def test_missing_component_fails(self):
        self.green_story()
        self.record_map("danh-sach", False, missing=['button "Ghi chú mới"'])
        g = self.gate(screens=["danh-sach"])
        self.assertFalse(g.passed)
        self.assertIn("Ghi chú mới", g.feedback())

    def test_matching_screen_passes(self):
        self.green_story()
        self.record_map("danh-sach", True)
        self.assertTrue(self.gate(screens=["danh-sach"]).passed)


class TestFakeTests(GateTestCase):
    def test_assertionless_test_fails_the_gate(self):
        """Test luôn xanh làm điều kiện "test xanh" mất hết ý nghĩa."""
        self.green_story()
        self.store.tool_run("S-01", "qa:fake-tests", ok=False,
                            detail={"files": ["tests/test_a.py"]})
        g = self.gate()
        self.assertFalse(g.passed)
        self.assertIn("tests/test_a.py", g.feedback())

    def test_clean_tests_pass(self):
        self.green_story()
        self.store.tool_run("S-01", "qa:fake-tests", ok=True, detail={"files": []})
        self.assertTrue(self.gate().passed)


class TestReview(GateTestCase):
    def test_blocking_finding_fails(self):
        self.green_story()
        g = self.gate(review_blocking=["[chặn] src/a.py:10 — mất dữ liệu khi lưu"])
        self.assertFalse(g.passed)
        self.assertIn("mất dữ liệu", g.feedback())

    def test_review_that_did_not_run_is_not_clean(self):
        self.green_story()
        self.assertFalse(self.gate(review_ran=False).passed)


class TestFeedback(GateTestCase):
    def test_feedback_only_lists_failures(self):
        self.green_story()
        g = self.gate(changed=["ngoai/pham-vi.py"])
        self.assertIn("phạm vi ghi", g.feedback())
        self.assertNotIn("lint", g.feedback())


if __name__ == "__main__":
    unittest.main(verbosity=2)
