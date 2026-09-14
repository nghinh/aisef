"""Bộ kiểm định — và điều quan trọng nhất: "chưa cấu hình" ≠ "đạt"."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401 — HostProvider vào chỗ docker, không mở container (tests/__init__.py)

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.phases.qa import KINDS, command_for_kind, find_fake_tests, run_suite  # noqa: E402


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
        self.assertIn("never ran means never verified", r.summary())

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
        self.assertIn("no UI", e2e.skipped)


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

    def test_stack_default_used_when_the_tool_is_actually_present(self):
        """Lỗi 164. `_UNIVERSAL` đã đúng luật và tự nêu lý do ngay cạnh:
        *"declaring a non-existent command makes the kind 'ran and red',
        misreporting the root cause — it is unconfigured."* `_DEFAULTS` thì trả
        vô điều kiện, nên nó vi phạm đúng câu ấy.

        Đo trên marks-cli: `npx stryker run` được trả về dù stryker không có,
        và `mutation` báo **FAILED — npm error EAI_AGAIN … registry.npmjs.org**.
        Sandbox **đúng** khi không có mạng; công cụ vắng mặt bị ghi thành một
        phép kiểm của dự án bị trượt, tức đảo ngược nghĩa của một cổng đỏ.

        Kiểm `which(argv[0])` là chưa đủ: argv[0] là `npx`, và npx **có** trên
        máy. Công cụ thật là argv[1], và với npx thì phép thử trung thực là nó
        phân giải được tại chỗ hay không — chứ không phải tải về được hay không.
        """
        self.write("package.json", "{}")
        # Không có `node_modules/.bin/playwright` → chưa cấu hình, không phải đỏ.
        self.assertEqual(command_for_kind("e2e", self.project, self.config()), "")

        binv = self.project / "node_modules" / ".bin"
        binv.mkdir(parents=True, exist_ok=True)
        (binv / "playwright").write_text("#!/bin/sh" + chr(10), encoding="utf-8")
        (binv / "playwright").chmod(0o755)
        self.assertEqual(
            command_for_kind("e2e", self.project, self.config()), "npx playwright test"
        )

    def test_config_still_wins_over_a_missing_tool(self):
        """Người vận hành khai lệnh thì lệnh ấy chạy — kể cả khi công cụ vắng
        mặt: lúc ấy *đỏ* là câu trả lời đúng, vì họ đã khai nó phải chạy được."""
        self.write("package.json", "{}")
        cfg = self.config(**{"verify.e2e": "npx playwright test --headed"})
        self.assertEqual(command_for_kind("e2e", self.project, cfg),
                         "npx playwright test --headed")

    def test_mutation_unconfigured_rather_than_failed_when_stryker_absent(self):
        self.write("package.json", "{}")
        self.assertEqual(command_for_kind("mutation", self.project, self.config()), "")


class TestProviderGia(QaTestCase):
    """`run_suite` trên `FakeProvider` (ADR-005 V5): không Docker, không suy
    biến, kịch bản quyết định xanh/đỏ — và bậc quyền của loại vẫn tới provider."""

    def test_do_theo_kich_ban_khong_suy_bien(self):
        from aisef.harness import sandbox

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
        from aisef.harness import sandbox

        fake = sandbox.FakeProvider([sandbox.SandboxResult(
            125, stderr="docker: Error response from daemon: pull access denied",
            provider_error="pull access denied")])
        cfg = self.config(**{"verify.unit": "npm test", "sandbox.provider": "fake"})
        with sandbox.using(fake):
            r = run_suite(self.project, config=cfg, only=["unit"], has_ui=False)
        self.assertEqual(r.failed, [], "không phải test đỏ")
        self.assertEqual(len(r.unrunnable), 1)
        self.assertIn("sandbox infrastructure error", r.results[0].unrunnable)

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

    def test_skill_cua_khung_khong_phai_test_cua_du_an(self):
        """`.claude/skills` do khung cài và **bắt buộc commit**, nên git liệt
        kê chúng như tệp của dự án. Một test script trong skill không phải
        test của dự án — mà mục `real tests` là mục **chặn** (họ lỗi 113)."""
        self.write(".claude/skills/mot-skill/scripts/tests/test_x.py",
                   "def test_gi_do():\n    x = 1 + 1\n")
        self.write("tests/test_that.py", "def test_y():\n    assert 1 == 1\n")
        self.assertEqual(find_fake_tests(self.project), [])

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
        self.assertIn("fake tests", r.summary())

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
        from aisef.phases.qa import KINDS, KindResult, _unrunnable_reason

        r = KindResult(kind=KINDS["unit"], ran=True, ok=False, detail=detail)
        r.unrunnable = _unrunnable_reason(exit_code, detail)
        return r

    def test_nhan_dung_moi_cach_bao_thieu_cong_cu(self):
        """127 là mã POSIX; phần còn lại là cách các hệ khác nói cùng một
        chuyện. Lỗi 37: `mutation` sập với stack trace Node thô
        (`MODULE_NOT_FOUND`) và bị đếm là test đỏ."""
        from aisef.phases.qa import _unrunnable_reason

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
        from aisef.phases.qa import _unrunnable_reason

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
        self.assertIn("unrunnable", r.line())
        self.assertNotIn("✗", r.line())

    def test_van_chan_nhung_khong_bi_dem_la_test_do(self):
        from aisef.phases.qa import QaReport

        rep = QaReport(results=[self.kq("sh: vitest: command not found")])
        self.assertEqual(rep.failed, [], "không phải test đỏ")
        self.assertEqual(len(rep.unrunnable), 1)
        self.assertFalse(rep.passed, "vẫn không đạt — chưa chạy thì chưa kiểm")
        self.assertIn("environment not set up", rep.summary())

    def test_test_do_that_van_la_test_do(self):
        from aisef.phases.qa import QaReport

        rep = QaReport(results=[self.kq("3 tests failed", exit_code=1)])
        self.assertEqual(len(rep.failed), 1)
        self.assertEqual(rep.unrunnable, [])


class TestCoGiaoDien(unittest.TestCase):
    """Lỗi 34: ứng dụng 5 màn hình bị báo "dự án không có giao diện"."""

    def test_hop_dong_thi_giac_la_bang_chung_co_giao_dien(self):
        import json
        import tempfile

        from aisef.cli import _project_has_ui

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


class TestKeHoachDaChotQuyetDinhCoGiaoDien(unittest.TestCase):
    """Lỗi 163 — kế hoạch **đã chốt** mà không màn hình nào là bằng chứng
    *không* có giao diện, và hôm nay nó bị bỏ qua.

    `_project_has_ui` tự nêu đúng nguyên tắc trong docstring của nó: *"hỏi cái
    đã **quyết**, không phải cái được **gợi ý** … tới lúc chấm cổng pre-deploy
    thì kiến trúc đã chốt và màn hình đã dựng — dùng chúng."* Nhưng mã chỉ áp
    dụng cho vế **khẳng định**: `if any(screens): return True`, rồi rơi xuống
    đoán từ văn xuôi requirements.

    Đo trên marks-cli: cả 7 story đều `screens: []`, requirements viết *"no
    server, no network, **no ui**"* — và `_project_has_ui` trả **True**, vì
    `Stack.has_ui` tính `"frontend" in undetermined`, mà `undetermined:
    frontend` được thêm khi WEB_MARKERS khớp. Khớp hai chỗ: `browser` trong
    *"browser profile"* (nơi dấu trang của người dùng đang nằm), và `ui` ngay
    **trong lời phủ định** *"no ui"*. Ranh giới từ không cứu được một phủ định.

    Hậu quả: cổng pre-deploy đòi E2E trình duyệt (Playwright) và accessibility ở
    một CLI vừa nói thẳng là nó không có giao diện. Không riêng marks-cli: mọi
    CLI, thư viện hay daemon nhắc tới web một cách tình cờ đều dính.
    """

    def _du_an(self, tmp, *, stories, requirements="a single-user command-line "
                                                   "tool. no server, no network, no ui."):
        import json
        p = Path(tmp)
        (p / "_bmad-output").mkdir(parents=True, exist_ok=True)
        (p / "_bmad-output" / "stories.index.json").write_text(
            json.dumps({"stories": stories}, ensure_ascii=False), encoding="utf-8")
        (p / "docs").mkdir(exist_ok=True)
        (p / "docs" / "requirements.md").write_text(requirements, encoding="utf-8")
        return p

    def test_moi_story_khong_man_hinh_thi_khong_co_giao_dien(self):
        import tempfile
        from aisef.cli import _project_has_ui
        with tempfile.TemporaryDirectory() as tmp:
            p = self._du_an(tmp, stories=[{"id": "S-1", "screens": []},
                                          {"id": "S-2", "screens": []}])
            self.assertFalse(
                _project_has_ui(p),
                "kế hoạch đã chốt, không story nào có màn hình — đó là bằng chứng "
                "cơ học, mạnh hơn hẳn việc đánh hơi văn xuôi")

    def test_mot_story_co_man_hinh_thi_van_co_giao_dien(self):
        """Phép kiểm âm, và là ca lỗi 34: không được quay ngược lại."""
        import tempfile
        from aisef.cli import _project_has_ui
        with tempfile.TemporaryDirectory() as tmp:
            p = self._du_an(tmp, stories=[{"id": "S-1", "screens": []},
                                          {"id": "S-2", "screens": ["notes-list"]}])
            self.assertTrue(_project_has_ui(p))

    def test_chi_so_rong_thi_khong_ket_luan_tu_no(self):
        """Chỉ số **rỗng** không phải bằng chứng phủ định: chưa có kế hoạch thì
        chưa quyết được gì, nên vẫn hỏi văn xuôi như cũ."""
        import tempfile
        from aisef.cli import _project_has_ui
        with tempfile.TemporaryDirectory() as tmp:
            p = self._du_an(tmp, stories=[], requirements="a React app in the browser")
            self.assertTrue(_project_has_ui(p))

    def test_hop_dong_thi_giac_van_thang(self):
        import json, tempfile
        from aisef.cli import _project_has_ui
        with tempfile.TemporaryDirectory() as tmp:
            p = self._du_an(tmp, stories=[{"id": "S-1", "screens": []}])
            (p / "_bmad-output" / "design-contract.json").write_text(
                json.dumps({"screens": [{"id": "x"}]}), encoding="utf-8")
            self.assertTrue(_project_has_ui(p), "hợp đồng thị giác vẫn thắng")


class TestMienTuongMinh(unittest.TestCase):
    """Lỗi 36: miễn mà vẫn chạy và vẫn đếm là trượt.

    Báo cáo tự mâu thuẫn — dòng dưới ghi "miễn tường minh: e2e" trong khi
    dòng trên ghi "✗ e2e". Miễn là quyết định của người, đã ghi lại; vẫn
    đếm nó là trượt thì miễn chẳng có nghĩa gì.
    """

    def test_loai_duoc_mien_khong_chay_va_khong_dem(self):
        import tempfile

        from aisef.config import DEFAULTS, Config
        from aisef.phases.qa import run_suite

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config({
                **DEFAULTS,
                "verify.waived": "e2e,accessibility",
                "verify.e2e": "chac-chan-khong-co-lenh-nay",
            })
            rep = run_suite(tmp, config=cfg, only=["e2e"], has_ui=True)

        e2e = rep.results[0]
        self.assertTrue(e2e.skipped)
        self.assertIn("explicit waiver", e2e.skipped)
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

class TestCayKiemSach(QaTestCase):
    """ADR-005 V6: kiểm định cấp dự án chạy ở worktree sạch dựng từ SHA.

    Harbor dừng env agent rồi chạy verifier ở chỗ tách; ta chạy trên cây
    agent vừa sửa, nơi `node_modules/.bin/vitest`, `pytest.ini`, `conftest.py`
    có thể là shim. Fixture: `tests/run.sh` **trong git** gọi
    `node_modules/.bin/vitest` (tệp giả, không theo dõi — "vitest thật" của
    dự án, mượn vào cây sạch); rồi cây làm việc bị ghi đè `tests/run.sh`
    bằng shim in "ok". QA ở cây sạch phải chạy bản trong git → tool trong
    `node_modules`; shim bị bỏ qua vì worktree lấy từ SHA.
    """

    def git(self, *args: str) -> str:
        p = subprocess.run(["git", "-C", str(self.project), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        return p.stdout.strip()

    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write(".gitignore", "node_modules/\n")
        self.write("tests/run.sh", "sh node_modules/.bin/vitest\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "test thật")
        self.sha = self.git("rev-parse", "HEAD")
        self.write("node_modules/.bin/vitest", "echo 'vitest that: 1 failed'\nexit 1\n")
        self.write("tests/run.sh", "echo ok\n")  # agent ghi đè trong cây, không commit

    def cfg(self, **over):
        return self.config(**{"verify.unit": "sh tests/run.sh", "sandbox.use_docker": False, **over})

    def test_shim_trong_cay_bi_bo_qua_tool_trong_node_modules_van_chay(self):
        r = run_suite(self.project, config=self.cfg(), only=["unit"], has_ui=False,
                      story_id="S-01", artifact_root=self.artifacts)
        unit = r.results[0]
        self.assertTrue(unit.ran)
        self.assertFalse(unit.ok, "shim in 'ok' không được tính")
        self.assertIn("vitest that", unit.detail)
        self.assertEqual(r.tree, "clean-worktree")
        self.assertEqual(r.clean_tree, self.sha)
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "qa:unit")
        self.assertEqual(e.detail["clean_tree"], self.sha)
        self.assertEqual(e.detail["tree"], "clean-worktree")
        self.assertIn("verification tree: clean-worktree", r.summary())

    def test_worktree_tam_duoc_go_sau_khi_kiem(self):
        run_suite(self.project, config=self.cfg(), only=["unit"], has_ui=False)
        self.assertEqual(len(self.git("worktree", "list").splitlines()), 1)
        root = self.project / ".aisef" / "worktrees"
        self.assertEqual([p.name for p in root.iterdir() if p.is_dir()], [])

    def test_tat_knob_thi_chay_cay_agent_va_noi_ra(self):
        r = run_suite(self.project, config=self.cfg(**{"verify.clean_tree": False}),
                      only=["unit"], has_ui=False)
        self.assertTrue(r.results[0].ok, "shim chạy — đó là điều tắt knob chấp nhận, có ghi")
        self.assertEqual(r.tree, "agent-tree")
        self.assertEqual(r.clean_tree, "")

    def test_muc_story_giu_cay_worktree(self):
        r = run_suite(self.project, config=self.cfg(), only=["unit"], has_ui=False, clean=False)
        self.assertTrue(r.results[0].ok)
        self.assertEqual(r.tree, "agent-tree")

    def test_khong_co_git_thi_chay_cay_dang_dung_va_noi_ly_do(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "t.sh").write_text("echo ok\n", encoding="utf-8")
            r = run_suite(d, config=self.config(**{"verify.unit": "sh t.sh", "sandbox.use_docker": False}),
                          only=["unit"], has_ui=False)
        self.assertTrue(r.results[0].ok)
        self.assertTrue(r.tree.startswith("agent-tree"), r.tree)
        self.assertIn("git", r.tree)



class TestBoKhongKhopTestNaoKhongPhaiDo(unittest.TestCase):
    """Lỗi 134 (todo-oc 2026-09-13): `verify.accessibility` là
    `playwright test --grep @a11y`; chừng nào chưa story nào viết test gắn
    `@a11y` thì lệnh ấy tìm thấy 0 test. Báo là FAIL nghĩa là "accessibility
    hỏng" ở **mọi** story của dự án — đúng luật "chưa cấu hình ≠ đỏ" mà tool
    `test` đã có từ lỗi 2/8, chỉ là chưa áp cho các loại kiểm định khác."""

    def _ly_do(self, out, exit_code=1):
        from aisef.phases.qa import _unrunnable_reason
        return _unrunnable_reason(exit_code, out)

    def test_khong_tim_thay_test_nao_la_khong_chay_duoc(self):
        for out in ("Error: No tests found", "no tests ran", "collected 0 items"):
            with self.subTest(out=out):
                self.assertIn("matched no tests", self._ly_do(out))

    def test_test_do_that_van_la_do(self):
        self.assertEqual(self._ly_do("1 failed\n  ✘ AC-S-01-1: adds a note"), "")

    def test_cong_cu_thieu_van_uu_tien_chan_doan_cu(self):
        """Chẩn đoán "thiếu công cụ" đã có phải thắng — nó cụ thể hơn."""
        ly_do = self._ly_do("stryker: command not found", exit_code=127)
        self.assertNotIn("matched no tests", ly_do)
        self.assertTrue(ly_do)


class TestGhiTenTestChoLoaiKiemDinh(unittest.TestCase):
    """Lỗi 132, tầng thứ hai: đường ghi của `qa:*` gọi `store.tool_run` trực
    tiếp, không đi qua `record()` của `harness/tools`, nên bản vá ở đó không
    tới — bộ e2e vẫn ghi 0 tên test."""

    def test_duong_ghi_qa_phan_tich_ten_test(self):
        import inspect
        from aisef.phases import qa

        src = inspect.getsource(qa.run_suite)
        i_parse = src.index("parse_testlog(day_du)")
        i_ghi = src.index('f"qa:{kind.id}", ok=sb.ok')
        self.assertLess(i_parse, i_ghi, "phải phân tích trước khi ghi")
        self.assertIn("if doc.format:", src,
                      "đầu ra không phải test log thì không được dựng thành test_ids")


class TestTomTatKhongPhaiAccessLog(unittest.TestCase):
    """Lỗi 137 (todo-oc 2026-09-13): thông báo cổng cho `e2e` và
    `accessibility` là **năm dòng access log** của dev server. `webServer` của
    Playwright ghi một dòng mỗi request vào cùng luồng, nên phần đuôi nuốt sạch
    kết quả test. `ToolResult.tail` đã có `_NOISE` cho đúng chuyện này từ
    2026-09-09 — nhưng chỉ cho tool `test`; đường `qa:*` tự cắt đuôi riêng."""

    LOG = "\n".join([
        "Running 2 tests",
        "  ✘  1 e2e/a.spec.js:3:1 › AC-S-01-1: contrast fails",
        '[WebServer] ::1 - - [13/Sep/2026 20:47:01] "GET / HTTP/1.1" 200 -',
        '[WebServer] ::1 - - [13/Sep/2026 20:47:02] "GET / HTTP/1.1" 200 -',
        '[WebServer] ::1 - - [13/Sep/2026 20:47:03] "GET / HTTP/1.1" 200 -',
        '[WebServer] ::1 - - [13/Sep/2026 20:47:04] "GET / HTTP/1.1" 200 -',
        '[WebServer] ::1 - - [13/Sep/2026 20:47:05] "GET / HTTP/1.1" 200 -',
    ])

    def test_duong_qa_bo_access_log_truoc_khi_cat_duoi(self):
        import inspect
        from aisef.phases import qa

        src = inspect.getsource(qa.run_suite)
        i_loc = src.index("_NOISE.search(x)")
        i_cat = src.index("result.detail = ")
        self.assertLess(i_loc, i_cat, "phải lọc trước khi cắt đuôi")

    def test_loc_giu_lai_dong_co_nghia(self):
        from aisef.harness.tools import _NOISE

        moi = [x for x in self.LOG.splitlines() if not _NOISE.search(x)]
        self.assertIn("AC-S-01-1: contrast fails", "\n".join(moi[-5:]))

    def test_toan_bo_la_access_log_thi_van_in_cai_co(self):
        """Lọc sạch thành rỗng thì phải trả lại nguyên bản — thà nhiễu còn hơn
        không nói gì."""
        from aisef.harness.tools import _NOISE

        chi_log = "\n".join(self.LOG.splitlines()[2:])
        moi = [x for x in chi_log.splitlines() if not _NOISE.search(x)]
        self.assertEqual(moi, [])
        self.assertTrue((moi or chi_log.splitlines())[-5:])


class TestKhongApDungKhacVoiChuaCauHinh(QaTestCase):
    """Lỗi 165 — khung **tự xác định được** một loại không áp dụng, mà vẫn tính
    nó là "chưa cấu hình" nên vẫn chặn.

    `unconfigured` gom hai thứ khác hẳn nhau vào một rổ: *chưa ai cấu hình* (một
    khoảng trống — không biết) và *khung đã xác định loại này không thể áp dụng*
    (một sự việc — biết rồi). Cái đầu phải chặn; cái sau thì không.

    Hậu quả đo được: một dự án **không có giao diện** không bao giờ
    `release_ready` được, vì `e2e` và `accessibility` bị bỏ qua với lý do "project
    has no UI" — do chính khung suy ra từ kế hoạch đã chốt — rồi vẫn bị đếm là
    chưa cấu hình. Người vận hành buộc phải ký một miễn trừ cho một sự việc mà
    khung đã tự chứng minh, và một miễn trừ như thế làm loãng nghĩa của miễn trừ.
    """

    def _bao_cao(self, has_ui: bool):
        from aisef.phases.qa import run_suite
        self.write("package.json", "{}")
        return run_suite(self.project, config=self.config(**{"verify.unit": "true"}),
                         has_ui=has_ui)

    def test_bo_qua_vi_khong_co_giao_dien_khong_phai_chua_cau_hinh(self):
        rep = self._bao_cao(has_ui=False)
        ids = {r.kind.id for r in rep.unconfigured}
        self.assertNotIn("e2e", ids, "khung đã xác định được: đó là sự việc, không phải khoảng trống")
        self.assertNotIn("accessibility", ids)
        self.assertIn("e2e", {r.kind.id for r in rep.not_applicable})

    def test_van_hien_ra_trong_bao_cao_chu_khong_bien_mat(self):
        """Không áp dụng **không** có nghĩa là giấu đi: người ký phải thấy."""
        rep = self._bao_cao(has_ui=False)
        self.assertIn("project has no UI", rep.summary())

    def test_co_giao_dien_thi_e2e_van_chan_nhu_cu(self):
        """Phép kiểm âm: dự án **có** giao diện thì e2e chưa cấu hình vẫn chặn."""
        rep = self._bao_cao(has_ui=True)
        self.assertIn("e2e", {r.kind.id for r in rep.unconfigured})

    def test_chua_cau_hinh_that_thi_van_chan(self):
        """Phép kiểm âm: `sit`/`perf` không có luật áp dụng nào, vẫn chặn."""
        rep = self._bao_cao(has_ui=False)
        ids = {r.kind.id for r in rep.unconfigured}
        self.assertIn("sit", ids)
        self.assertIn("perf", ids)
        self.assertFalse(rep.release_ready)
