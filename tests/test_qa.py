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


class TestProviderGia(QaTestCase):
    """`run_suite` trên `FakeProvider` (ADR-005 V5): không Docker, không suy
    biến, kịch bản quyết định xanh/đỏ — và bậc quyền của loại vẫn tới provider."""

    def test_do_theo_kich_ban_khong_suy_bien(self):
        from aisdlc.harness import sandbox

        fake = sandbox.FakeProvider([sandbox.SandboxResult(1, stdout="1 failed")])
        cfg = self.config(**{"verify.unit": "npm test", "sandbox.provider": "fake"})
        with sandbox.using(fake):
            r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        unit = r.results[0]
        self.assertTrue(unit.ran)
        self.assertFalse(unit.ok)
        self.assertFalse(unit.degraded)
        self.assertEqual(unit.missing, [])
        self.assertEqual(len(r.failed), 1)
        self.assertEqual(fake.calls[0].cmd, ["npm", "test"])
        self.assertIs(fake.calls[0].level, sandbox.Level.WORKSPACE_WRITE)

    def test_loi_ha_tang_la_khong_chay_duoc(self):
        from aisdlc.harness import sandbox

        fake = sandbox.FakeProvider([sandbox.SandboxResult(
            125, stderr="docker: Error response from daemon: pull access denied",
            provider_error="pull access denied")])
        cfg = self.config(**{"verify.unit": "npm test", "sandbox.provider": "fake"})
        with sandbox.using(fake):
            r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        self.assertEqual(r.failed, [], "không phải test đỏ")
        self.assertEqual(len(r.unrunnable), 1)
        self.assertIn("hạ tầng sandbox", r.results[0].unrunnable)

    def test_suy_bien_mang_ten_bao_dam_thieu(self):
        cfg = self.config(**{"verify.unit": "true", "sandbox.use_docker": False})
        r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        self.assertTrue(r.results[0].degraded)
        self.assertEqual(r.results[0].missing, ["network_none", "non_root", "secrets_absent"])


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


class TestKhongChayDuoc(unittest.TestCase):
    """"Không chạy được" khác "test đỏ".

    Lỗi 33, đo trên e9: gốc dự án chưa từng `npm ci` — mọi story chạy
    trong worktree riêng, mỗi worktree tự cài. `pre-deploy` báo
    "✗ unit — vitest: command not found" thành **test trượt**. Test không
    trượt; nó chưa từng chạy, và chỗ cần sửa là môi trường chứ không phải
    bộ test.
    """

    def kq(self, detail, exit_code=127):
        from aisdlc.phases.qa import KINDS, KindResult, _unrunnable_reason

        r = KindResult(kind=KINDS["unit"], ran=True, ok=False, detail=detail)
        r.unrunnable = _unrunnable_reason(exit_code, detail)
        return r

    def test_nhan_dung_moi_cach_bao_thieu_cong_cu(self):
        """127 là mã POSIX; phần còn lại là cách các hệ khác nói cùng một
        chuyện. Lỗi 37: `mutation` sập với stack trace Node thô
        (`MODULE_NOT_FOUND`) và bị đếm là test đỏ."""
        from aisdlc.phases.qa import _unrunnable_reason

        for ma, chi_tiet in (
            (127, "sh: vitest: command not found"),
            (1, "Error: Cannot find module 'stryker'"),
            (1, "MODULE_NOT_FOUND"),
            (1, "'stryker' is not recognized as an internal or external command"),
        ):
            with self.subTest(chi_tiet=chi_tiet):
                self.assertTrue(_unrunnable_reason(ma, chi_tiet), chi_tiet)

        self.assertFalse(_unrunnable_reason(1, "3 tests failed: expected 2 got 3"))

    def test_do_tren_dau_ra_day_du_khong_phai_phan_da_cat(self):
        """`Cannot find module` nằm ở **đầu** stack trace; `detail` chỉ giữ
        5 dòng cuối. Dò trên phần đã cắt thì mất hẳn dấu hiệu — đúng lý do
        `mutation` vẫn bị đếm là test đỏ sau bản vá đầu tiên."""
        from aisdlc.phases.qa import _unrunnable_reason

        day_du = (
            "Error: Cannot find module 'stryker'\n"
            "    at Module._resolveFilename\n"
            "    at Module._load\n"
            "  paths: [\n"
            "    '/Users/x/.npm/_npx/abc/node_modules/stryker/bin/stryker'\n"
            "  ]\n"
            "}\n"
            "\n"
            "Node.js v26.0.0"
        )
        duoi = "\n".join(day_du.splitlines()[-5:])
        self.assertFalse(_unrunnable_reason(1, duoi), "5 dòng cuối mất dấu hiệu")
        self.assertTrue(_unrunnable_reason(1, day_du))

    def test_khong_bi_in_thanh_dau_thap(self):
        r = self.kq("sh: vitest: command not found")
        self.assertIn("không chạy được", r.line())
        self.assertNotIn("✗", r.line())

    def test_van_chan_nhung_khong_bi_dem_la_test_do(self):
        from aisdlc.phases.qa import QaReport

        rep = QaReport(results=[self.kq("sh: vitest: command not found")])
        self.assertEqual(rep.failed, [], "không phải test đỏ")
        self.assertEqual(len(rep.unrunnable), 1)
        self.assertFalse(rep.passed, "vẫn không đạt — chưa chạy thì chưa kiểm")
        self.assertIn("môi trường chưa dựng", rep.summary())

    def test_test_do_that_van_la_test_do(self):
        from aisdlc.phases.qa import QaReport

        rep = QaReport(results=[self.kq("3 tests failed", exit_code=1)])
        self.assertEqual(len(rep.failed), 1)
        self.assertEqual(rep.unrunnable, [])


class TestCoGiaoDien(unittest.TestCase):
    """Lỗi 34: ứng dụng 5 màn hình bị báo "dự án không có giao diện"."""

    def test_hop_dong_thi_giac_la_bang_chung_co_giao_dien(self):
        import json
        import tempfile

        from aisdlc.cli import _project_has_ui

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "_bmad-output").mkdir()
            self.assertTrue(_project_has_ui(p), "không có gì để bác bỏ → mặc định có")

            (p / "docs").mkdir()
            (p / "docs" / "requirements.md").write_text("một CLI thuần", encoding="utf-8")
            self.assertFalse(_project_has_ui(p))

            (p / "_bmad-output" / "design-contract.json").write_text(
                json.dumps({"screens": [{"id": "notes-list"}]}), encoding="utf-8"
            )
            self.assertTrue(_project_has_ui(p), "hợp đồng thị giác thắng gợi ý ban đầu")


class TestMienTuongMinh(unittest.TestCase):
    """Lỗi 36: miễn mà vẫn chạy và vẫn đếm là trượt.

    Báo cáo tự mâu thuẫn — dòng dưới ghi "miễn tường minh: e2e" trong khi
    dòng trên ghi "✗ e2e". Miễn là quyết định của người, đã ghi lại; vẫn
    đếm nó là trượt thì miễn chẳng có nghĩa gì.
    """

    def test_loai_duoc_mien_khong_chay_va_khong_dem(self):
        import tempfile

        from aisdlc.config import DEFAULTS, Config
        from aisdlc.phases.qa import run_suite

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config({
                **DEFAULTS,
                "verify.waived": "e2e,accessibility",
                "verify.e2e": "chac-chan-khong-co-lenh-nay",
            })
            rep = run_suite(tmp, config=cfg, only=["e2e"], has_ui=True)

        e2e = rep.results[0]
        self.assertTrue(e2e.skipped)
        self.assertIn("miễn tường minh", e2e.skipped)
        self.assertFalse(e2e.ran, "miễn thì không chạy")
        self.assertEqual(rep.failed, [])
        self.assertEqual(rep.unconfigured, [], "miễn không phải là chưa cấu hình")


class TestCheBiMat(QaTestCase):
    def test_bi_mat_trong_output_kiem_dinh_bi_che(self):
        """ADR-005 V1: `tail` của `qa:*` cũng đi vào `_bmad-output` được commit."""
        cfg = self.config(**{
            "verify.unit": "sh -c 'echo token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789; exit 1'",
            "sandbox.use_docker": False,
        })
        r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False,
                      story_id="S-01", artifact_root=self.artifacts)
        self.assertNotIn("ghp_", r.results[0].detail)
        self.assertIn("[REDACTED]", r.results[0].detail)
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "qa:unit")
        self.assertEqual(e.detail["redacted"], 1)
        self.assertNotIn("ghp_", e.detail["tail"])

