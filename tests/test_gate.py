"""Cổng story — năm điều kiện, chấm từ bằng chứng chứ không từ lời kể."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.outcome import Outcome
from aisef.control.gate import evaluate  # noqa: E402
from aisef.harness.observe import MOCKUP_MAP, NOTE, EvidenceStore, Event  # noqa: E402


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


class TestKhongOnDinh(GateTestCase):
    """R13 `--repeat k`: test đổi kết cục giữa k lần trên **cùng SHA** →
    mục "test" UNRUNNABLE "không ổn định" nêu tên — không phải trượt, không
    phải đạt (lỗi 22). Đỏ ở mọi lần → FAILED như thường."""

    def lan(self, failed, ids=("t1", "t2")):
        EvidenceStore(self._tmp.name, candidate="aaa").tool_run("S-01", "test", ok=not failed, detail={
            "test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed)})

    def ghi(self, **d):
        store = EvidenceStore(self._tmp.name, candidate="aaa")
        store.tool_run("S-01", "lint", ok=True)
        store.record("S-01", Event(kind=NOTE, name="verify-only.repeat", ok=False, detail={
            "k": 3, "checks": ["test"], "flaky_ids": [], "stable_red": [], "flaky_checks": [], **d}))

    def muc(self, ten):
        return next(c for c in self.gate(candidate="aaa").checks if c.name == ten)

    def test_doi_ket_cuc_la_khong_on_dinh_neu_ten(self):
        for f in ([], [], ["t2"]):
            self.lan(f)
        self.ghi(flaky_ids=["t2"], flaky_checks=["test"])
        m = self.muc("test")
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertIn("t2", m.detail)
        self.assertNotIn("t1", m.detail)
        self.assertFalse(self.gate(candidate="aaa").passed, "không ổn định vẫn chặn")

    def test_do_moi_lan_la_truot_that(self):
        for _ in range(3):
            self.lan(["t2"])
        self.ghi(stable_red=["t2"])
        self.assertIs(self.muc("test").outcome, Outcome.FAILED)

    def test_khong_co_ban_ghi_repeat_thi_lan_cuoi_quyet(self):
        self.lan([]); self.lan(["t2"]); self.lan([])
        EvidenceStore(self._tmp.name, candidate="aaa").tool_run("S-01", "lint", ok=True)
        self.assertIs(self.muc("test").outcome, Outcome.PASSED)

    def test_lint_doi_ket_cuc_cung_khong_on_dinh(self):
        self.lan([])
        EvidenceStore(self._tmp.name, candidate="aaa").tool_run("S-01", "lint", ok=False)
        self.ghi(checks=["test", "lint"], flaky_checks=["lint"])
        self.assertIs(self.muc("lint").outcome, Outcome.UNRUNNABLE)


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
        self.assertIn("write scope", [c.name for c in g.failures])


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
        self.assertIn("not compared", g.feedback())

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
        self.assertIn("write scope", g.feedback())
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
        return next(c for c in g.checks if c.name == "guard ran")

    def test_khong_ky_vong_thi_bo_qua_co_ly_do(self):
        m = self.muc(self.gate(False))
        self.assertTrue(m.skipped)
        self.assertIn("not compiled", m.detail)

    def test_ky_vong_ma_khong_dau_vet_thi_truot(self):
        m = self.muc(self.gate(True))
        self.assertFalse(m.passed)
        self.assertIn("hook cannot reach worktree", m.detail)

    def test_mot_file_change_la_du(self):
        self.store.file_change("S-01", "src/a.py")
        self.assertTrue(self.muc(self.gate(True)).passed)

    def test_mot_lan_chan_cung_la_du(self):
        from aisef.harness.observe import GUARD_BLOCK, Event
        self.store.record("S-01", Event(kind=GUARD_BLOCK, name="secret", ok=False))
        self.assertTrue(self.muc(self.gate(True)).passed)

    def test_nhip_tim_la_du_du_khong_ghi_gi(self):
        """Phiên chỉ dùng Bash và không bị chặn: hook vẫn tới, và đó là
        điều mục này hỏi."""
        from aisef.harness.observe import GUARD_SEEN, Event
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
        return next(c for c in g.checks if c.name == "criteria have tests")

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
        self.assertIn("green on first run", g.feedback())

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


class TestTestKhongChayDuoc(GateTestCase):
    def test_gate_names_the_environment_not_the_story(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=False, detail={"unrunnable": "công cụ chưa cài hoặc không nạp được (module_not_found)"})
        self.store.tool_run("S-01", "lint", ok=True)
        g = self.gate()
        m = next(c for c in g.checks if c.name == "test")
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertFalse(g.passed)
        self.assertIn("không nạp được", g.feedback())


class TestHopDongDocTenQa(GateTestCase):
    """e9 R2: `qa:accessibility` xanh trong evidence mà cổng ghi "chưa cấu hình"."""

    def test_qa_prefixed_runs_count(self):
        self.green_story()
        self.store.tool_run("S-01", "qa:e2e", ok=True)
        self.store.tool_run("S-01", "qa:accessibility", ok=False, detail={"tail": "1 failed"})
        g = self.gate(contract=["unit", "e2e", "accessibility"])
        muc = {c.name: c for c in g.checks}
        self.assertIs(muc["e2e"].outcome, Outcome.PASSED)
        self.assertIs(muc["accessibility"].outcome, Outcome.FAILED)
        self.assertFalse(g.passed)


class TestKhongLamDoTestCoSan(GateTestCase):
    """ADR-004 R9: test xanh ở baseline mà đỏ hoặc mất ở ứng viên là hồi quy,
    và cổng phải nêu **đúng tên** — không phải "test đỏ" chung chung, vì đỏ
    do test mới của story (TDD) và đỏ do làm hỏng test có sẵn sửa khác nhau."""

    TEN = "no baseline regression"

    def baseline(self, ids, failed=(), skipped=(), **detail):
        self.store.tool_run("S-01", "test:baseline", ok=not failed, detail={
            "baseline": True, "test_format": "pytest", "test_ids": list(ids),
            "failed_ids": list(failed), "skipped_ids": list(skipped),
            "red_before": list(failed), **detail,
        })

    def ung_vien(self, ids, failed=(), sha="aaa", **detail):
        store = EvidenceStore(self._tmp.name, candidate=sha)
        store.file_change("S-01", "src/a.py")
        store.tool_run("S-01", "test", ok=not failed, detail={
            "test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed), **detail,
        })
        store.tool_run("S-01", "lint", ok=True)

    def muc(self, g):
        return next(c for c in g.checks if c.name == self.TEN)

    def test_doi_ten_test_giu_tieu_de_la_khong_phai_mat(self):
        """e9 01-07 lượt 2: bốn test có sẵn được thêm mã `AC_STORY_01_01_6:` — không phải xoá."""
        goc = ["src/ui/app-shell.tsx > Lớp token (TCCN 4, 6) > mọi màu có biến CSS",
               "src/ui/app-shell.tsx > Lớp token (TCCN 4, 6) > mọi bậc spacing có biến CSS",
               "tests/test_a.py::test_1"]
        moi = ["src/ui/app-shell.tsx > Lớp token (TCCN 4, 6) > AC_STORY_01_01_6: mọi màu có biến CSS",
               "src/ui/app-shell.tsx > Lớp token (TCCN 4, 6) > AC_STORY_01_01_6: mọi bậc spacing có biến CSS",
               "tests/test_a.py::test_1"]
        self.baseline(goc)
        self.ung_vien(moi)
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertIn("renamed", m.detail)
        # Xoá thật (tiêu đề lá biến mất) vẫn là hồi quy.
        self.ung_vien(moi[:1] + ["tests/test_a.py::test_1"])
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("mọi bậc spacing", m.detail)

    def test_muoi_xanh_roi_chin_xanh_mot_do_thi_neu_dung_ten(self):
        ids = [f"tests/test_a.py::test_{i}" for i in range(1, 11)]
        self.baseline(ids)
        self.ung_vien(ids, failed=[ids[9]])
        g = self.gate(candidate="aaa")
        m = self.muc(g)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("tests/test_a.py::test_10", m.detail)
        self.assertNotIn("test_9", m.detail)
        self.assertIn("test_10", g.feedback(), "tên test hồi quy phải vào feedback lượt sau")

    def test_test_moi_do_cua_story_khong_phai_hoi_quy(self):
        """TDD: test mới đang đỏ là đúng nghĩa; mục "test" đỏ, mục này không."""
        ids = [f"t{i}" for i in range(10)]
        self.baseline(ids)
        self.ung_vien(ids + ["t_moi"], failed=["t_moi"])
        g = self.gate(candidate="aaa")
        self.assertIs(self.muc(g).outcome, Outcome.PASSED)
        self.assertIn("test", [c.name for c in g.failures])

    def test_do_san_o_baseline_va_van_do_thi_khong_tinh(self):
        self.baseline(["t1", "t2"], failed=["t2"])
        self.ung_vien(["t1", "t2"], failed=["t2"])
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertIn("already red", m.detail)
        self.assertIn("t2", m.detail)

    def test_bo_qua_o_baseline_khong_phai_xanh(self):
        """Test skip ở baseline mà đỏ hay mất ở ứng viên chưa chứng minh được
        story làm hỏng gì — nó chưa từng xanh."""
        self.baseline(["t1", "t2"], skipped=["t2"])
        self.ung_vien(["t1"])
        self.assertIs(self.muc(self.gate(candidate="aaa")).outcome, Outcome.PASSED)

    def test_mat_test_co_san_la_hoi_quy_va_noi_vi_sao(self):
        self.baseline(["t1", "t2", "t3"])
        self.ung_vien(["t1", "t3"])
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("lost 1 test", m.detail)
        self.assertIn("t2", m.detail)
        self.assertIn("declared in the story", m.detail)

    def test_khong_co_baseline_thi_khong_ap_dung_co_ly_do(self):
        self.green_story()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("recorded no baseline", m.detail)

    def test_tat_boi_cau_hinh_la_khong_ap_dung_khong_phai_dat(self):
        self.store.tool_run("S-01", "test:baseline", ok=False,
                            detail={"baseline": True, "disabled": True,
                                    "skipped": "tắt bởi cấu hình `verify.baseline`"})
        self.green_story()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("verify.baseline", m.detail)
        self.assertIsNot(m.outcome, Outcome.PASSED)

    def test_chua_khai_lenh_test_la_chua_cau_hinh_khong_phai_baseline_xanh(self):
        self.store.tool_run("S-01", "test:baseline", ok=False,
                            detail={"baseline": True, "skipped": "dự án chưa khai lệnh cho tool này"})
        self.green_story()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        self.assertFalse(m.outcome.counts_as_done)

    def test_baseline_khong_chay_duoc_la_moi_truong_khong_phai_story(self):
        self.store.tool_run("S-01", "test:baseline", ok=False,
                            detail={"baseline": True, "unrunnable": "công cụ chưa cài (module_not_found)"})
        self.green_story()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertIn("module_not_found", m.detail)

    def test_reporter_khong_in_ten_thi_chua_cau_hinh_kem_cho_sua(self):
        self.baseline([], test_format="", test_note="vitest reporter mặc định không in tên test — thêm `--reporter=verbose`")
        self.green_story()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertIn("--reporter=verbose", m.detail)

    def test_chi_so_voi_lan_test_dung_ung_vien(self):
        """Lần test ở bản khác không được dùng để chấm bản này."""
        self.baseline(["t1"])
        self.ung_vien(["t1"], sha="bbb")
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("no test run at candidate", m.detail)

    def test_lan_test_truoc_baseline_khong_duoc_tinh(self):
        """Lịch sử của lần chạy trước không phải "ứng viên": chỉ so lần sau mốc."""
        self.store.tool_run("S-01", "test", ok=False,
                            detail={"test_format": "pytest", "test_ids": ["t1"], "failed_ids": ["t1"]})
        self.baseline(["t1"])
        self.ung_vien(["t1"])
        self.assertIs(self.muc(self.gate(candidate="aaa")).outcome, Outcome.PASSED)


class TestTestCoKiemDuocStory(GateTestCase):
    """ADR-005 V3 nop control: test mang mã tiêu chí phải **đỏ khi không có mã
    của story**. Cấp 1 ($0) so với `test:baseline`; cấp 2 đọc `test:nop` —
    bộ test chạy ở SHA cha với tệp test của story chép vào."""

    TEN = "tests verify story"
    AC = "tests/test_a.py::test_AC_S_01_1_x"       # mang mã AC-S-01-1 của story S-01

    def baseline(self, ids, failed=(), skipped=(), **detail):
        self.store.tool_run("S-01", "test:baseline", ok=not failed, detail={
            "baseline": True, "test_format": "pytest", "test_ids": list(ids),
            "failed_ids": list(failed), "skipped_ids": list(skipped), **detail,
        })

    def ung_vien(self, ids, failed=(), sha="aaa", **detail):
        store = EvidenceStore(self._tmp.name, candidate=sha)
        store.file_change("S-01", "src/a.py")
        store.tool_run("S-01", "test", ok=not failed, detail={
            "test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed), **detail,
        })
        store.tool_run("S-01", "lint", ok=True)

    def nop(self, ids=None, failed=(), sha="aaa", ok=None, files=("tests/test_a.py",), **detail):
        d = {"nop": True, "parent": "cha0000", "files": list(files), **detail}
        if ids is not None:
            d.update({"test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed)})
        EvidenceStore(self._tmp.name, candidate=sha).tool_run(
            "S-01", "test:nop", ok=(not failed) if ok is None else ok, detail=d)

    def muc(self, g):
        return next(c for c in g.checks if c.name == self.TEN)

    def cham(self, **kw):
        return self.muc(self.gate(candidate="aaa", acceptance=1, **kw))

    # ---- cấp 1
    def test_gan_ma_vao_test_co_san_la_that_bai_neu_ten(self):
        """Test mang mã đã xanh ở baseline với đúng tên — xanh trước khi story
        viết dòng nào. Cấp 2 đỏ cũng không cứu: cấp 1 đã đủ kết luận."""
        self.baseline([self.AC, "t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop([self.AC, "t1"], failed=[self.AC])
        m = self.cham()
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("tagged existing tests", m.detail)
        self.assertIn(self.AC, m.detail)
        self.assertNotIn("t1", m.detail.replace(self.AC, ""))

    def test_doi_ten_test_co_san_de_gan_ma_van_that_bai_va_noi_vi_sao(self):
        """R9 coi đổi tên giữ tiêu đề lá là không mất; ở đây nó là "mã tiêu chí
        thành một cái tên" — test xanh ở baseline dưới tên cũ."""
        cu, moi = "src/a.ts > s > làm việc", "src/a.ts > s > AC_S_01_1: làm việc"
        self.baseline([cu, "t1"])
        self.ung_vien([moi, "t1"])
        m = self.cham()
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("renamed existing tests", m.detail)
        self.assertIn(moi, m.detail)
        self.assertIn("new tests", m.detail)

    def test_test_moi_trung_tieu_de_la_voi_test_con_nguyen_ten_khong_bi_bat_oan(self):
        """Test có sẵn còn nguyên tên ở ứng viên → test mang mã là test **khác**;
        cấp 1 để yên, cấp 2 quyết."""
        cu, moi = "src/a.ts > s > làm việc", "src/a.ts > s > AC_S_01_1: làm việc"
        self.baseline([cu])
        self.ung_vien([cu, moi])
        self.nop([cu, moi], failed=[moi])
        self.assertIs(self.cham().outcome, Outcome.PASSED)

    def test_baseline_o_ban_cua_chinh_story_thi_cap_1_khong_so_cap_2_quyet(self):
        """Lượt chạy lại: baseline đứng ở ứng viên cũ (e9 01-07 lần chạy 3), mọi
        test của story đã xanh sẵn — không phải "gắn mã vào test có sẵn"."""
        self.baseline([self.AC, "t1"], parent="bbb", base_ref="aaa0")
        self.ung_vien([self.AC, "t1"])
        self.nop(["t1"])
        m = self.cham()
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertIn("level 1 cannot compare", m.detail)
        self.assertIn("rerun", m.detail)
        # cùng dữ liệu, baseline ở điểm rẽ → cấp 1 bắt
        self.baseline([self.AC, "t1"], parent="aaa0", base_ref="aaa0")
        self.assertIs(self.cham().outcome, Outcome.FAILED)

    # ---- cấp 2
    def test_xanh_o_sha_cha_la_test_khong_kiem_duoc_gi(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop([self.AC, "t1"])
        g = self.gate(candidate="aaa", acceptance=1)
        m = self.muc(g)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("still green without story code", m.detail)
        self.assertIn(self.AC, m.detail)
        self.assertIn("cha0000"[:7], m.detail)
        self.assertIn(self.AC, g.feedback(), "tên test phải vào feedback lượt sau")

    def test_do_hoac_khong_ton_tai_o_sha_cha_la_dat(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop(["t1"])                            # lỗi import ở SHA cha: test không tồn tại
        m = self.cham()
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertIn("red or absent", m.detail)
        self.nop([self.AC, "t1"], failed=[self.AC])   # có mặt nhưng đỏ
        self.assertIs(self.cham().outcome, Outcome.PASSED)

    def test_nop_lay_lan_moi_nhat_o_dung_ung_vien(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop([self.AC, "t1"], sha="bbb")          # bản khác: không dùng để chấm bản này
        m = self.cham()
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("ran no nop", m.detail)

    def test_chua_co_test_mang_ma_xanh_o_ung_vien_thi_khong_co_gi_de_kiem(self):
        self.baseline(["t1"])
        self.ung_vien(["t1", "t2"])
        self.nop(["t1", "t2"])
        m = self.cham()
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("criteria have tests", m.detail)

    def test_khong_chay_duoc_la_moi_truong_khong_phai_story(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC])
        self.nop(ok=False, unrunnable="công cụ chưa cài (module_not_found)")
        m = self.cham()
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertIn("module_not_found", m.detail)

    def test_loi_import_o_sha_cha_khong_phai_khong_chay_duoc(self):
        """Runner báo "cannot find module" vì thiếu module **của story** nhưng
        vẫn in được tên test khác → là đỏ hợp lệ, không phải môi trường."""
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop(["t1"], ok=False, unrunnable="công cụ chưa cài (cannot find module)")
        self.assertIs(self.cham().outcome, Outcome.PASSED)

    def test_khong_them_sua_test_thi_khong_ap_dung(self):
        self.baseline(["t1"])
        self.ung_vien([self.AC, "t1"])
        self.nop(ok=False, files=[], skipped="story không thêm/sửa tệp test")
        m = self.cham()
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("did not add/modify", m.detail)

    def test_chua_khai_lenh_test_la_chua_cau_hinh(self):
        self.ung_vien([self.AC])
        self.nop(ok=False, skipped="dự án chưa khai lệnh cho tool này")
        self.assertIs(self.cham().outcome, Outcome.UNCONFIGURED)

    def test_tat_boi_cau_hinh_la_khong_ap_dung_khong_phai_dat(self):
        self.ung_vien([self.AC])
        self.nop(ok=False, disabled=True, skipped="tắt bởi cấu hình `verify.nop`")
        m = self.cham()
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("verify.nop", m.detail)

    def test_khong_co_nop_thi_khong_ap_dung_co_ly_do(self):
        self.green_story()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("ran no nop", m.detail)

    def test_reporter_khong_in_ten_thi_chi_ket_luan_khi_ca_bo_xanh(self):
        store = EvidenceStore(self._tmp.name, candidate="aaa")
        store.tool_run("S-01", "test", ok=True)
        store.tool_run("S-01", "lint", ok=True)
        self.nop(ok=True)
        m = self.cham()
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("test suite green at parent SHA", m.detail)
        self.nop(ok=False)
        m = self.cham()
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertIn("reporter", m.detail)

    def test_dung_ngay_sau_muc_tdd(self):
        self.green_story()
        names = [c.name for c in self.gate(added_tests=["tests/x.py"]).checks]
        self.assertEqual(names[names.index("TDD") + 1], self.TEN)

