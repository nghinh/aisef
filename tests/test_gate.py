"""Cổng story — năm điều kiện, chấm từ bằng chứng chứ không từ lời kể."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.outcome import Outcome
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


class TestGuardCoChay(unittest.TestCase):
    """G4 mảnh 2. Hook sinh ra ≠ hook chạy: worktree không có `.claude/`
    thì story chạy với zero guard và bằng chứng trông y hệt agent ngoan.
    Nay guard tự ghi, nên "chưa từng đánh giá thao tác ghi nào" đo được."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)
        self.store.tool_run("S-01", "test", ok=True)
        self.store.tool_run("S-01", "lint", ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def gate(self, expected):
        return evaluate("S-01", self.store.read("S-01"), changed=["src/a.py"],
                        write_scope=["src"], screens=[], guard_expected=expected)

    def muc(self, g):
        return next(c for c in g.checks if c.name == "guard có chạy")

    def test_khong_ky_vong_thi_bo_qua_co_ly_do(self):
        m = self.muc(self.gate(False))
        self.assertTrue(m.skipped)
        self.assertIn("chưa biên dịch", m.detail)

    def test_ky_vong_ma_khong_dau_vet_thi_truot(self):
        m = self.muc(self.gate(True))
        self.assertFalse(m.passed)
        self.assertIn("hook không tới được worktree", m.detail)

    def test_mot_file_change_la_du(self):
        self.store.file_change("S-01", "src/a.py")
        self.assertTrue(self.muc(self.gate(True)).passed)

    def test_mot_lan_chan_cung_la_du(self):
        from aisdlc.harness.observe import GUARD_BLOCK, Event
        self.store.record("S-01", Event(kind=GUARD_BLOCK, name="secret", ok=False))
        self.assertTrue(self.muc(self.gate(True)).passed)

    def test_nhip_tim_la_du_du_khong_ghi_gi(self):
        """Phiên chỉ dùng Bash và không bị chặn: hook vẫn tới, và đó là
        điều mục này hỏi."""
        from aisdlc.harness.observe import GUARD_SEEN, Event
        self.store.record("S-01", Event(kind=GUARD_SEEN, name="git-stage"))
        self.assertTrue(self.muc(self.gate(True)).passed)


class TestTieuChiCoTest(GateTestCase):
    """G5: mã `AC-<story>-<i>` phải nằm trong tên một test của lần xanh cuối."""

    def green_with_ids(self, ids, fmt="node-spec", **extra):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True,
                            detail={"test_format": fmt, "test_ids": ids, **extra})
        self.store.tool_run("S-01", "lint", ok=True)

    def muc(self, g):
        return next(c for c in g.checks if c.name == "tiêu chí có test")

    def test_missing_criterion_is_named_and_blocks(self):
        self.green_with_ids(["AC-S-01-1: chuỗi rỗng"])
        g = self.gate(acceptance=2)
        self.assertFalse(g.passed)
        m = self.muc(g)
        self.assertIn("AC-S-01-2", m.detail)
        self.assertNotIn("AC-S-01-1 ", m.detail + " ")

    def test_all_criteria_covered_passes(self):
        self.green_with_ids(["AC-S-01-1: a", "nhóm > AC-S-01-2: b 3ms"])
        self.assertTrue(self.gate(acceptance=2).passed)

    def test_unreadable_reporter_is_unconfigured_not_pass_not_fail(self):
        self.green_with_ids([], fmt="", test_note="vitest reporter mặc định không in tên test — thêm `--reporter=verbose`")
        g = self.gate(acceptance=2)
        m = self.muc(g)
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertIn("--reporter=verbose", m.detail)
        self.assertTrue(g.passed)                 # không chặn story, nhưng phải hiện ra
        self.assertFalse(m.outcome.counts_as_done)

    def test_story_without_criteria_is_not_applicable(self):
        self.green_story()
        self.assertIs(self.muc(self.gate(acceptance=0)).outcome, Outcome.NOT_APPLICABLE)


class TestCoverageMin(GateTestCase):
    """G10b: số coverage đọc từ output runner; không có số là chưa cấu hình."""

    def cov(self, value):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True, detail={"test_format": "pytest", "test_ids": ["t"], "coverage": value})
        self.store.tool_run("S-01", "lint", ok=True)
        return next(c for c in self.gate(coverage_min=0.85).checks if c.name == "coverage")

    def test_no_number_is_unconfigured_with_the_fix(self):
        m = self.cov(None)
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertIn("--cov", m.detail)

    def test_below_threshold_fails_with_numbers(self):
        m = self.cov(60.0)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("60% < 85%", m.detail)

    def test_at_or_above_passes(self):
        self.assertIs(self.cov(90.0).outcome, Outcome.PASSED)

    def test_not_asked_means_no_check(self):
        self.green_story()
        self.assertNotIn("coverage", [c.name for c in self.gate().checks])


class TestTDD(GateTestCase):
    """G8: story thêm test thì phải có lần đỏ trước lần xanh cuối."""

    def test_green_first_time_fails(self):
        self.green_story()
        g = self.gate(added_tests=["tests/x.test.js"])
        self.assertIn("TDD", [c.name for c in g.failures])
        self.assertIn("xanh ngay lần đầu", g.feedback())

    def test_red_then_green_passes(self):
        self.store.tool_run("S-01", "test", ok=False)
        self.green_story()
        self.assertTrue(self.gate(added_tests=["tests/x.test.js"]).passed)

    def test_no_new_tests_is_not_applicable(self):
        self.green_story()
        m = next(c for c in self.gate(added_tests=[]).checks if c.name == "TDD")
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)

    def test_caller_that_cannot_know_adds_no_check(self):
        self.green_story()
        self.assertNotIn("TDD", [c.name for c in self.gate().checks])
