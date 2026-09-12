"""Kiểm chứng CLI — chạy qua `main()` như người dùng thật gọi."""

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401 — HostProvider vào chỗ docker, không mở container (tests/__init__.py)

from aisef.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main  # noqa: E402
from aisef.control.state import StateStore, StoryStatus  # noqa: E402


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "requirements.md").write_text("# yêu cầu\n", encoding="utf-8")
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        import subprocess
        subprocess.run(["git", "init"], cwd=self.project, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.project, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=self.project, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=self.project, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.project, capture_output=True)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(self.project), *args])
        return code, out.getvalue(), err.getvalue()

    def write_artifact(self, name: str, text: str = "# nội dung\n") -> Path:
        p = self.artifacts / name
        p.write_text(text, encoding="utf-8")
        return p

    def stub_client(self, name: str = "claude"):
        """Adapter luôn `available()` cho lệnh cần client — phép kiểm nào đo
        *lệnh* thì không được phụ thuộc máy chạy có cài `claude` hay không."""
        import contextlib
        import unittest.mock as mock

        from aisef.clients.compile import ADAPTERS

        that = ADAPTERS[name]

        class Stub(that):                     # giữ nguyên id/năng lực đã khai
            def available(self) -> bool:
                return True

        @contextlib.contextmanager
        def _ctx():
            with mock.patch.dict(ADAPTERS, {name: Stub}):
                yield

        return _ctx()


class TestEveryCommandIsUsable(unittest.TestCase):
    """Lỗi khai đối số chỉ lộ ra lúc người dùng gõ lệnh — trừ khi có test."""

    def commands(self) -> list[str]:
        from aisef.cli import build_parser

        parser = build_parser()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        return sorted(actions[0].choices) if actions else []

    def test_at_least_the_six_steps_exist(self):
        for name in ("setup", "plan", "mockup", "run", "qa", "devsecops",
                     "pre-deploy", "report", "gates", "guard", "verify", "tool"):
            self.assertIn(name, self.commands())

    def test_help_works_for_every_command(self):
        from aisef.cli import build_parser

        for name in self.commands():
            with self.subTest(command=name):
                with self.assertRaises(SystemExit) as e:
                    with redirect_stdout(io.StringIO()):
                        build_parser().parse_args([name, "--help"])
                self.assertEqual(e.exception.code, 0)


class TestDoctor(CliTestCase):
    def test_passes_on_valid_project(self):
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("ready", out)

    def test_fails_without_requirements(self):
        (self.project / "docs" / "requirements.md").unlink()
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("requirements.md", out)

    def test_reports_optional_tools_without_failing(self):
        """Thiếu docker không làm doctor trượt — chỉ hạ mức bảo đảm."""
        code, out, _ = self.run_cli("doctor")
        self.assertIn("docker", out)
        self.assertEqual(code, EXIT_OK)


class TestDoctorTenTest(CliTestCase):
    """ADR-005 V9: `doctor` nói cổng có đọc được tên test không — tin bằng
    chứng khi có, đoán từ cờ lệnh khi chưa — và gợi reporter/CTRF."""

    def cau_hinh(self, lenh: str) -> None:
        import json as _json
        (self.project / ".ai").mkdir(exist_ok=True)
        (self.project / ".ai" / "config.json").write_text(_json.dumps({"tools.test": lenh}), encoding="utf-8")

    def test_lenh_khong_in_ten_thi_goi_ctrf(self):
        self.cau_hinh("pytest")
        _, out, _ = self.run_cli("doctor")
        self.assertIn("test command prints test names", out)
        self.assertIn("pytest-json-ctrf", out)
        self.assertIn("guessing from command flags", out)

    def test_bang_chung_thang_co_lenh(self):
        """Lệnh trông "câm" nhưng bằng chứng ghi `test_format` → tin bằng chứng."""
        from aisef.harness.observe import EvidenceStore
        self.cau_hinh("pytest")
        EvidenceStore(self.artifacts).tool_run("S-01", "test", ok=True, detail={"test_format": "ctrf"})
        _, out, _ = self.run_cli("doctor")
        self.assertIn("gate can read test names", out)
        self.assertIn("'ctrf'", out)

    def test_bang_chung_rong_thi_goi_du_lenh_in_ten(self):
        from aisef.harness.observe import EvidenceStore
        self.cau_hinh("pytest -v")
        EvidenceStore(self.artifacts).tool_run("S-01", "test", ok=True, detail={"test_format": ""})
        _, out, _ = self.run_cli("doctor")
        self.assertIn("not configured", out)
        self.assertIn("CTRF", out)


class TestDoctorSkillFreshness(CliTestCase):
    def test_stale_framework_skill_is_flagged(self):
        """Skill của framework nằm trong kho framework; dự án giữ một bản
        sao. Sửa skill mà không cài lại thì agent vẫn chạy bản cũ, và cách
        duy nhất phát hiện là ngồi so từng file."""
        from aisef.kit.install import OWN_SKILLS

        own = next(OWN_SKILLS.glob("*/SKILL.md"))
        copied = self.project / ".claude" / "skills" / own.parent.name / "SKILL.md"
        copied.parent.mkdir(parents=True)
        copied.write_text("bản cũ\n", encoding="utf-8")

        _, out, _ = self.run_cli("doctor")
        self.assertIn("outdated", out)
        self.assertIn(own.parent.name, out)

    def test_matching_copy_passes(self):
        from aisef.kit.install import OWN_SKILLS

        own = next(OWN_SKILLS.glob("*/SKILL.md"))
        copied = self.project / ".claude" / "skills" / own.parent.name / "SKILL.md"
        copied.parent.mkdir(parents=True)
        copied.write_bytes(own.read_bytes())
        _, out, _ = self.run_cli("doctor")
        self.assertIn("matches source", out)


class TestGates(CliTestCase):
    def test_lists_all_eight_gates(self):
        code, out, _ = self.run_cli("gates")
        for gate in ("prd", "architecture", "ux-spec", "epics", "stories",
                     "mockups", "readiness", "pre-deploy"):
            self.assertIn(gate, out)
        self.assertEqual(code, EXIT_NOT_READY)  # chưa cổng nào duyệt

    def test_points_at_next_gate(self):
        _, out, _ = self.run_cli("gates")
        self.assertIn("Next gate to handle: prd", out)

    def test_flags_missing_artifact_by_name(self):
        """Nói thiếu file nào, không chỉ nói thiếu — cổng ux-spec có hai
        file nên "chưa có artifact" không đủ để biết phải làm gì."""
        _, out, _ = self.run_cli("gates")
        self.assertIn("missing: prd.md", out)
        self.assertIn("missing: DESIGN.md, EXPERIENCE.md", out)


class TestApproveReject(CliTestCase):
    def test_cannot_approve_without_artifact(self):
        code, _, err = self.run_cli("approve", "prd")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("no artifact", err)

    def test_approve_with_artifact(self):
        self.write_artifact("prd.md")
        code, out, _ = self.run_cli("approve", "prd")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("approved", out)

    def test_cannot_approve_out_of_order(self):
        """Duyệt architecture khi prd chưa duyệt là bỏ qua thứ tự."""
        self.write_artifact("architecture.md")
        code, _, err = self.run_cli("approve", "architecture")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("preceding gates not yet approved", err)

    def test_force_bypasses_order(self):
        self.write_artifact("architecture.md")
        code, _, _ = self.run_cli("approve", "architecture", "--force")
        self.assertEqual(code, EXIT_OK)

    def test_reject_requires_note(self):
        self.write_artifact("prd.md")
        code, _, _ = self.run_cli("reject", "prd", "--note", "   ")
        self.assertEqual(code, EXIT_USAGE)

    def test_reject_records_note(self):
        self.write_artifact("prd.md")
        code, out, _ = self.run_cli("reject", "prd", "--note", "thiếu chỉ tiêu")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("thiếu chỉ tiêu", out)

    def test_invalid_gate_name(self):
        with self.assertRaises(SystemExit):
            self.run_cli("approve", "khong-ton-tai")

    def test_editing_artifact_after_approval_shows_stale(self):
        self.write_artifact("prd.md", "bản 1\n")
        self.run_cli("approve", "prd")
        self.write_artifact("prd.md", "bản 2\n")
        _, out, _ = self.run_cli("gates")
        self.assertIn("stale", out)


class TestAutoApprove(CliTestCase):
    def test_auto_approve_all(self):
        self.write_artifact("prd.md")
        self.write_artifact("architecture.md")
        code, out, _ = self.run_cli("auto-approve", "all")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("prd", out)

    def test_auto_approve_subset(self):
        self.write_artifact("prd.md")
        self.write_artifact("architecture.md")
        self.run_cli("auto-approve", "prd")
        _, out, _ = self.run_cli("gates")
        self.assertIn("(auto)", out)

    def test_invalid_gate_in_list(self):
        code, _, err = self.run_cli("auto-approve", "prd,bay-gio")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("bay-gio", err)

    def test_skips_gates_without_artifact(self):
        code, out, _ = self.run_cli("auto-approve", "all")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("no gate has artifacts", out)


class TestReview(CliTestCase):
    def test_missing_artifact(self):
        code, out, _ = self.run_cli("review", "prd")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("artifact not found", out)

    def test_shows_content_and_next_steps(self):
        self.write_artifact("prd.md", "# PRD\n\ndòng một\ndòng hai\n")
        code, out, _ = self.run_cli("review", "prd")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("dòng một", out)
        self.assertIn("aisef approve prd", out)

    def test_truncates_long_artifact(self):
        self.write_artifact("prd.md", "\n".join(f"dòng {i}" for i in range(200)))
        _, out, _ = self.run_cli("review", "prd", "--lines", "10")
        self.assertIn("190 more lines", out)

    def test_shows_previous_note(self):
        self.write_artifact("prd.md")
        self.run_cli("reject", "prd", "--note", "cần bổ sung NFR")
        _, out, _ = self.run_cli("review", "prd")
        self.assertIn("cần bổ sung NFR", out)


class TestReviewStories(CliTestCase):
    def test_stories_gate_shows_a_readable_breakdown_not_json(self):
        """Cổng story để người xem cách chia việc; 350 dòng JSON thì cổng
        chỉ còn là thủ tục."""
        import shutil

        from aisef.phases.story_split import split

        fix = Path(__file__).resolve().parent / "fixtures" / "bmad"
        for name in ("epics.md", "prd.md"):
            shutil.copy(fix / name, self.artifacts / name)
        split(self.artifacts)

        code, out, _ = self.run_cli("review", "stories")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("EPIC-01", out)
        self.assertIn("wave 2 (parallel)", out)
        self.assertIn("covers: FR-1", out)
        self.assertIn("machine gate: PASS", out)


class TestReviewReadinessTinhLaiThieuGi(CliTestCase):
    """Lỗi 97: cổng `readiness` in lại cảnh báo thiếu cấu hình **ghi lúc chia
    story** — tức trước khi có mockup và trước khi ai kịp cấu hình công cụ —
    ngay bên trên dòng "✅ 7 stories are all executable" nó vừa tính xong."""

    def _chia_story(self):
        import shutil

        from aisef.phases.story_split import split

        fix = Path(__file__).resolve().parent / "fixtures" / "bmad"
        for name in ("epics.md", "prd.md"):
            shutil.copy(fix / name, self.artifacts / name)
        split(self.artifacts)

    def test_canh_bao_thieu_cong_cu_duoc_tinh_lai_khi_da_cau_hinh(self):
        self._chia_story()
        # Ghi nhận lúc chia: chưa có `tools.test` nào.
        ghi = (self.artifacts / "stories.gate.json").read_text(encoding="utf-8")
        self.assertIn("configure `tools.test`", ghi)

        (self.project / ".ai").mkdir(exist_ok=True)
        (self.project / ".ai" / "config.json").write_text(
            '{"tools.test": "true", "tools.lint": "true"}', encoding="utf-8")
        (self.artifacts / "design-contract.json").write_text(
            '{"version": 1, "screens": []}', encoding="utf-8")

        code, out, _ = self.run_cli("review", "readiness")
        self.assertEqual(code, EXIT_OK)
        self.assertNotIn("configure `tools.test`", out)
        # Cảnh báo không thuộc loại "thiếu cấu hình" vẫn còn nguyên.
        self.assertIn("machine gate:", out)

    def test_cong_story_van_in_dung_ban_da_ghi(self):
        """Ở cổng `stories` thì bản ghi là bản đúng: nó tính ngay lúc ấy."""
        self._chia_story()
        (self.project / ".ai").mkdir(exist_ok=True)
        (self.project / ".ai" / "config.json").write_text(
            '{"tools.test": "true", "tools.lint": "true"}', encoding="utf-8")
        _, out, _ = self.run_cli("review", "stories")
        self.assertIn("configure `tools.test`", out)


class TestMockupCommand(CliTestCase):
    def test_rejects_unknown_client(self):
        code, _, err = self.run_cli("mockup", "--client", "khong-co")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("khong-co", err)

    def test_without_experience_file(self):
        """Thiếu artifact đầu vào là lỗi gọi lệnh (1), không phải "chưa sẵn sàng".

        Lệnh dựng mockup mở phiên agent nên nó tra client **trước**; máy không
        cài `claude` thì dừng ở đó với mã 2 và phép kiểm này đo môi trường chứ
        không đo lệnh (CI Linux 2026-09-06: 2 != 1). Cắm adapter giả để chỉ còn
        một biến: có EXPERIENCE.md hay không.
        """
        with self.stub_client():
            code, out, _ = self.run_cli("mockup")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("EXPERIENCE.md", out)

    def test_review_mockups_shows_screens_and_index_link(self):
        import shutil

        from aisef.control.design_contract import CONTRACT_FILE
        from aisef.control.experience import parse_experience_file
        from aisef.harness import browser
        from aisef.phases.mockup import extract

        if browser.availability(self.project):
            self.skipTest("chưa dựng được mockup trên máy này")

        fix = Path(__file__).resolve().parent / "fixtures"
        shutil.copy(fix / "bmad" / "EXPERIENCE.md", self.artifacts / "EXPERIENCE.md")
        (self.artifacts / "mockups").mkdir()
        for p in (fix / "mockups").glob("*.html"):
            shutil.copy(p, self.artifacts / "mockups" / p.name)
        extract(self.artifacts, parse_experience_file(self.artifacts / "EXPERIENCE.md"))
        self.assertTrue((self.artifacts / CONTRACT_FILE).is_file())

        code, out, _ = self.run_cli("review", "mockups")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("index.html", out)
        self.assertIn("contract:", out)
        self.assertIn("unresolved", out)      # tim-kiem cố ý còn OQ-4


class TestStatusExitCode(CliTestCase):
    def test_failed_story_makes_status_not_ready(self):
        """Một story trượt cổng mà lệnh trả 0 thì CI báo xanh trên một
        sprint đang hỏng."""
        store = StateStore(self.artifacts)
        store.register("S-01", "E-01")
        store.transition("S-01", StoryStatus.RUNNING)
        store.transition("S-01", StoryStatus.FAILED, reason="cổng không đạt")
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("cổng không đạt", out)


class TestPlan(CliTestCase):
    """Chỉ kiểm phần kiểm đầu vào — chạy pipeline thật tốn tiền, đã kiểm
    riêng bằng client giả trong `test_plan.py`."""

    def test_rejects_unknown_client(self):
        code, _, err = self.run_cli("plan", "--client", "khong-co")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("khong-co", err)

    def test_rejects_unknown_gate_in_auto_approve(self):
        code, _, err = self.run_cli("plan", "--auto-approve", "prd,bay-gio")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("bay-gio", err)


class TestToolCommand(CliTestCase):
    def test_unknown_tool_is_a_clear_error(self):
        code, _, err = self.run_cli("tool", "khong-co")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("khong-co", err)

    def test_project_without_a_command_says_so(self):
        code, out, _ = self.run_cli("tool", "test")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("has not declared a command", out)

    def test_runs_and_records_evidence(self):
        (self.project / ".ai").mkdir()
        (self.project / ".ai" / "config.json").write_text(
            '{"tools.test": "true"}', encoding="utf-8")
        code, out, _ = self.run_cli("tool", "test", "--story", "STORY-01-01")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("✅ test", out)

        from aisef.harness.observe import EvidenceStore

        self.assertTrue(EvidenceStore(self.artifacts).read("STORY-01-01").tests_green())


class TestVerifyCommand(CliTestCase):
    def test_clean_tree_passes(self):
        code, out, _ = self.run_cli("verify")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("post-check passed", out)

    def test_story_without_tests_fails_post_hoc(self):
        """Lớp bảo đảm cho client không gắn được hook tiền kiểm."""
        code, out, _ = self.run_cli("verify", "--story", "STORY-01-01")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("no test run recorded", out)


class TestRunCommand(CliTestCase):
    def test_refuses_before_the_readiness_gate(self):
        """Cổng `readiness` gắn vào **cả** chỉ mục story lẫn hợp đồng thị
        giác. Chỉ đòi `stories` thì một story khai `screens` vẫn chạy được
        khi chưa có mockup nào — rồi trượt vì "chưa đối chiếu", sau khi đã
        tiêu tiền viết xong code."""
        code, _, err = self.run_cli("run")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("readiness", err)

    def test_rejects_unknown_client(self):
        code, _, err = self.run_cli("run", "--client", "khong-co", "--force")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("khong-co", err)

    def test_verify_only_can_story(self):
        """R13: kiểm lại là kiểm lại **một** ứng viên — không có story thì
        không có gì để chỉ vào."""
        code, _, err = self.run_cli("run", "--verify-only", "--force")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--story", err)

    def test_verify_only_khong_di_voi_no_isolate(self):
        code, _, err = self.run_cli("run", "--verify-only", "--story", "STORY-01-01",
                                    "--no-isolate", "--force")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--no-isolate", err)

    def test_repeat_chi_di_voi_verify_only(self):
        """R13 `--repeat k` lặp **phép kiểm** trên một ứng viên đã đóng băng —
        không có nghĩa với lượt developer."""
        code, _, err = self.run_cli("run", "--repeat", "3", "--force")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--repeat", err)

    def test_repeat_phai_duong(self):
        code, _, err = self.run_cli("run", "--verify-only", "--story", "STORY-01-01",
                                    "--repeat", "0", "--force")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--repeat", err)


class TestCtxCommand(CliTestCase):
    """`aisef ctx` (ADR-005 V7): bản đồ đầy đủ, và ghi `ctx_lookup` khi gọi
    trong phiên có `AISEF_STORY_ID`."""

    def setUp(self):
        super().setUp()
        (self.project / "src").mkdir()
        (self.project / "src" / "a.ts").write_text("export function taoGhiChu() {}\n", encoding="utf-8")
        (self.project / "src" / "b.ts").write_text("taoGhiChu()\n", encoding="utf-8")

    def test_file_ve_quanh_mot_tep(self):
        code, out, _ = self.run_cli("ctx", "--file", "src/a.ts")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("export function taoGhiChu() …", out)
        self.assertIn("`src/b.ts` · taoGhiChu", out)
        self.assertNotIn("truncated", out)

    def test_budget_cat_va_chi_cho_tra(self):
        code, out, _ = self.run_cli("ctx", "--file", "src", "--budget", "120")
        self.assertEqual(code, EXIT_OK)
        self.assertLessEqual(len(out.rstrip("\n")), 120)
        self.assertIn("truncated", out)

    def test_khong_story_khong_file_la_loi_dung_cach(self):
        code, _, err = self.run_cli("ctx")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--story", err)

    def test_story_chua_co_chi_muc_thi_noi_ra(self):
        code, _, err = self.run_cli("ctx", "--story", "STORY-01-01")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("STORY-01-01", err)

    def test_trong_phien_thi_ghi_ctx_lookup(self):
        import json
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"AISEF_STORY_ID": "STORY-01-09"}):
            code, out, _ = self.run_cli("ctx", "--file", "src/a.ts")
        self.assertEqual(code, EXIT_OK)
        ev = (self.artifacts / "evidence" / "STORY-01-09.jsonl").read_text(encoding="utf-8")
        rec = [json.loads(l) for l in ev.splitlines() if "ctx_lookup" in l]
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["detail"]["file"], "src/a.ts")
        self.assertGreater(rec[0]["detail"]["chars"], 0)


class TestQaCommand(CliTestCase):
    def test_unconfigured_blocks_release_level(self):
        """Mặc định là mức trước triển khai: chưa chạy thì không phải đạt."""
        code, out, _ = self.run_cli("qa")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("unconfigured", out)

    def test_story_level_only_warns(self):
        code, _, _ = self.run_cli("qa", "--story-level")
        self.assertEqual(code, EXIT_OK)

    def test_red_check_fails_even_at_story_level(self):
        (self.project / ".ai").mkdir()
        (self.project / ".ai" / "config.json").write_text(
            '{"verify.unit": "false"}', encoding="utf-8")
        code, out, _ = self.run_cli("qa", "--only", "unit", "--story-level")
        self.assertEqual(code, EXIT_NOT_READY)


class TestStatus(CliTestCase):
    def test_empty(self):
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("No stories registered", out)

    def test_shows_progress_and_cost(self):
        store = StateStore(self.artifacts)
        store.register("S-01", "E-01")
        store.transition("S-01", StoryStatus.RUNNING, cost_usd=1.5)
        store.transition("S-01", StoryStatus.VERIFYING)
        store.transition("S-01", StoryStatus.DONE)
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("1/1 stories done", out)
        self.assertIn("$1.50", out)

    def test_tien_do_dem_theo_ke_hoach_khong_theo_so_da_dang_ky(self):
        """Một lượt `--epic` chỉ đăng ký từng story một: "0/1 stories done"
        đọc thành một dự án một story trong khi kế hoạch có mười bốn (đo trên
        `todo-e2e` 2026-09-09)."""
        import json

        (self.artifacts / "stories.index.json").write_text(
            json.dumps({"stories": [{"id": f"S-{i:02d}"} for i in range(1, 15)]}),
            encoding="utf-8")
        store = StateStore(self.artifacts)
        store.register("S-01", "E-01")
        store.transition("S-01", StoryStatus.RUNNING)
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("0/14 stories done", out)
        self.assertIn("13 not started", out)

    def test_blocked_story_makes_status_not_ready(self):
        store = StateStore(self.artifacts)
        store.register("S-02", "E-01")
        store.transition("S-02", StoryStatus.BLOCKED, reason="thiếu write_scope")
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("thiếu write_scope", out)


class TestInit(CliTestCase):
    def test_writes_config_template(self):
        code, out, _ = self.run_cli("init")
        self.assertEqual(code, EXIT_OK)
        self.assertTrue((self.project / ".ai" / "config.json").is_file())
        self.assertIn("config.json", out)


    def test_init_with_stack_sets_tools(self):
        code, out, _ = self.run_cli("init", "--stack", "python")
        self.assertEqual(code, EXIT_OK)
        import json
        cfg = json.loads((self.project / ".ai" / "config.json").read_text(encoding="utf-8"))
        from aisef.cli.harness import _PY
        self.assertEqual(cfg["tools.test"], f"{_PY} -m pytest -v")
        self.assertEqual(cfg["sandbox.image"], "python:3.12-slim")
        self.assertIn("pypi.org", cfg["sandbox.allow_hosts"])

    def test_lenh_test_cua_preset_chay_duoc_tren_may_nay(self):
        """`init --stack python` ghi `python -m pytest -v` trên máy không có
        `python` (macOS, phần lớn Linux) — `aisef tool test` ra `exit 127` ngay
        trên máy vừa sinh ra lệnh ấy. Đo 13/09/2026 trên dự án mới."""
        import shutil

        from aisef.cli.harness import STACK_PRESETS, _PY
        self.assertIsNotNone(shutil.which(_PY), f"{_PY} không có trên máy này")
        lenh = str(STACK_PRESETS["python"]["tools.test"])
        self.assertTrue(lenh.startswith(_PY + " "), lenh)

    def test_moi_stack_preset_deu_in_duoc_ten_test(self):
        """`doctor` coi lệnh không in tên test là "gate chưa cấu hình". Một
        preset mặc định mà rơi ngay vào đó thì người mới không có cách nào biết
        trước khi chạy hết một story (đo 2026-09-12 trên dự án mới)."""
        from aisef.cli.harness import STACK_PRESETS
        doc_duoc = ("-v", "--verbose", "--reporter=verbose", "--test-reporter", "node --test", "ctrf")
        for ten, preset in STACK_PRESETS.items():
            lenh = str(preset["tools.test"])
            with self.subTest(stack=ten):
                if ten == "node":
                    continue   # `npm test` chạy script của dự án — không đoán hộ được
                self.assertTrue(any(k in lenh for k in doc_duoc), f"{ten}: {lenh}")

    def test_init_with_stack_react(self):
        code, out, _ = self.run_cli("init", "--stack", "react")
        self.assertEqual(code, EXIT_OK)
        import json
        cfg = json.loads((self.project / ".ai" / "config.json").read_text(encoding="utf-8"))
        self.assertIn("vitest", cfg["tools.test"])
        self.assertTrue(cfg["sandbox.tools_network"])


class TestDuongDanDuAn(unittest.TestCase):
    """`--project .` phải thành đường dẫn tuyệt đối ngay ở cửa vào.

    `Path(".").name` là chuỗi rỗng, và mỗi pha dùng nó một kiểu: báo cáo
    nghiệm thu ra tiêu đề cụt (lỗi 22), prompt `devsecops` trượt vì biến
    rỗng (lỗi 30). Chín chỗ trong mã làm `Path(project)` mà không
    resolve — vá từng chỗ dùng là vá triệu chứng, chỗ thứ mười sẽ lại
    hỏng.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "du-an-cua-toi"
        (self.project / "_bmad-output").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_chay_tu_trong_thu_muc_du_an_van_ra_dung_ten(self):
        import os

        cwd = os.getcwd()
        os.chdir(self.project)
        try:
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                main(["report"])
        finally:
            os.chdir(cwd)

        text = (self.project / "docs" / "ACCEPTANCE-REPORT.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("# Acceptance Report — du-an-cua-toi", text)



if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestStatusNoiRoChuaMerge(CliTestCase):
    def test_xong_nhung_chua_merge_duoc_goi_ten(self):
        from aisef.control.journal import Entry, JournalStore
        store = StateStore(self.artifacts)
        store.register("S-01", "E-01")
        for b in (StoryStatus.RUNNING, StoryStatus.VERIFYING, StoryStatus.DONE):
            store.transition("S-01", b)
        j = JournalStore(self.artifacts)
        for s in ("attempt.started", "worktree.created", "commit.created", "attempt.committed"):
            j.record("S-01", Entry(step=s, attempt=1))
        code, out, _ = self.run_cli("status")
        self.assertIn("done but not merged", out)
        self.assertIn("S-01", out)


class TestDoctorHookTrongWorktree(CliTestCase):
    def _hook(self):
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

    def test_chua_commit_thi_canh_bao_noi_ro_lop_dang_dua_vao(self):
        self._hook()
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        code, out, _ = self.run_cli("doctor")
        self.assertIn("hook in worktree", out)
        self.assertIn("not committed", out)
        self.assertIn("--settings", out)

    def test_da_commit_thi_xanh(self):
        self._hook()
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)
        subprocess.run(["git", "add", ".claude/settings.json"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "hook"], cwd=self.project, check=True)
        code, out, _ = self.run_cli("doctor")
        self.assertIn("committed", out)


class TestStatusCanhBaoNguCanhPhinh(CliTestCase):
    """G10a. Thay knob `story.max_context_tokens` (chưa từng có mã đọc) bằng
    đo thật: `prompt_chars` trong evidence, cảnh báo story vượt 3× trung vị."""

    def test_story_nap_gap_ba_bi_goi_ten(self):
        from aisef.clients.stream import RunResult
        from aisef.harness.observe import EvidenceStore
        store = StateStore(self.artifacts)
        ev = EvidenceStore(self.artifacts)
        for sid, chars in (("S-01", 10_000), ("S-02", 11_000), ("S-03", 12_000), ("S-04", 90_000)):
            store.register(sid, "E-01")
            ev.agent_run(sid, RunResult(ok=True, text="x"), name=f"{sid}#1", prompt_chars=chars)
        code, out, _ = self.run_cli("status")
        self.assertIn("loaded context exceeding", out)
        self.assertIn("S-04", out)
        self.assertNotIn("S-02", out.split("loaded context exceeding")[1].split("\n\n")[0] if "loaded context exceeding" in out else "")

    def test_it_hon_ba_story_thi_khong_ket_luan(self):
        from aisef.clients.stream import RunResult
        from aisef.harness.observe import EvidenceStore
        store = StateStore(self.artifacts); ev = EvidenceStore(self.artifacts)
        for sid, chars in (("S-01", 1_000), ("S-02", 90_000)):
            store.register(sid, "E-01")
            ev.agent_run(sid, RunResult(ok=True, text="x"), name=f"{sid}#1", prompt_chars=chars)
        code, out, _ = self.run_cli("status")
        self.assertNotIn("loaded context exceeding", out)


class TestDoctorHookTroDungDuAn(CliTestCase):
    """P0-1: hook trỏ sang dự án khác phải là ✗ — guard sẽ ghi bằng chứng sai chủ."""

    def _hook(self, project_path: str):
        import json
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": [
            {"matcher": "", "hooks": [{"type": "command", "command": f"aisef --project {project_path} guard completion"}]}]}}),
            encoding="utf-8")

    def test_lech_thi_do(self):
        self._hook("/tmp/du-an-khac")
        code, out, _ = self.run_cli("doctor")
        self.assertIn("hook points to this project", out)
        self.assertIn("/tmp/du-an-khac", out)
        self.assertIn("compile", out)

    def test_khop_thi_xanh(self):
        self._hook(str(self.project))
        code, out, _ = self.run_cli("doctor")
        self.assertIn("✅ hook points to this project", out)


class TestDoctorCoverageHint(CliTestCase):
    def test_test_command_without_coverage_is_named(self):
        import json
        (self.project / ".ai").mkdir(exist_ok=True)
        (self.project / ".ai" / "config.json").write_text(json.dumps({"tools.test": "node --test src/*.test.js"}), encoding="utf-8")
        code, out, _ = self.run_cli("doctor")
        self.assertIn("test command prints coverage", out)
        self.assertIn("not configured", out)

    def test_with_coverage_flag_is_green(self):
        import json
        (self.project / ".ai").mkdir(exist_ok=True)
        (self.project / ".ai" / "config.json").write_text(json.dumps({"tools.test": "node --test --experimental-test-coverage src/*.test.js"}), encoding="utf-8")
        code, out, _ = self.run_cli("doctor")
        self.assertIn("✅ test command prints coverage", out)


class TestLenhDoc(CliTestCase):
    """S2: `aisef doc` in tài liệu và ghi `doc_lookup` khi có --story."""

    def test_records_evidence_for_story(self):
        import json, os
        from unittest import mock
        from aisef.kit import docs as D
        from aisef.harness.observe import NOTE, EvidenceStore
        with tempfile.TemporaryDirectory() as cache, mock.patch.dict(os.environ, {D.ENV_DOCS: cache}), \
             mock.patch.object(D, "_get", lambda url, fetch=None: json.dumps({"results": [{"id": "/x/y", "title": "Y"}]}) if "/search?" in url else "tài liệu Y"):
            code, out, _ = self.run_cli("doc", "y", "--topic", "hooks", "--story", "S-1")
        self.assertEqual(code, 0, out)
        self.assertIn("tài liệu Y", out)
        e = EvidenceStore(self.project / "_bmad-output").read("S-1").last(NOTE, "doc_lookup")
        self.assertEqual(e.detail["library"], "/x/y")

    def test_prompt_tools_mention_the_command(self):
        from aisef.harness.tools import describe_tools
        self.assertIn("doc <gói>", describe_tools(self.project))


class TestLenhChange(CliTestCase):
    def test_change_command_prints_next_steps(self):
        (self.project / "docs").mkdir(exist_ok=True)
        (self.project / "docs" / "requirements.md").write_text("# YC\n", encoding="utf-8")
        code, out, _ = self.run_cli("change", "FR-2", "Thêm nút hoàn tác")
        self.assertEqual(code, 0, out)
        self.assertIn("STORY-CH-01", out)
        self.assertIn("write_scope", out)


class TestDoctorHookThieuGuard(CliTestCase):
    def test_old_compile_report_names_missing_guards(self):
        import json
        out_dir = self.project / "_bmad-output"; out_dir.mkdir(exist_ok=True)
        (out_dir / "compile-report.json").write_text(json.dumps({"clients": [{"client": "claude", "written": [],
            "guards_wired": ["completion", "destructive", "diff-scope", "git-stage", "injection", "secret", "write-scope"],
            "guards_post_hoc": [], "blocks_at_source": True, "degradations": []}]}), encoding="utf-8")
        code, out, _ = self.run_cli("doctor")
        self.assertIn("hook claude has all guards", out)
        self.assertIn("process-ref", out)
        self.assertIn("aisef compile", out)


class TestToolCoCauTruc(CliTestCase):
    """ADR-005 V11 (A): kết luận máy đọc **trước** tail, khai cắt và trỏ toàn văn —
    agent không phải tự chạy lại runner để biết test nào đỏ (lượt bị đốt vào
    `Bash: pytest` sau một `aisef tool test` trên stream dogfood)."""

    def config(self, command: str) -> None:
        (self.project / ".ai").mkdir(exist_ok=True)
        (self.project / ".ai" / "config.json").write_text(
            '{"tools.test": "%s", "sandbox.use_docker": false}' % command, encoding="utf-8")

    def test_ten_test_do_nam_trong_nam_dong_dau(self):
        self.config("sh -c 'seq 1 60; echo tests/test_a.py::test_x FAILED; "
                    "echo tests/test_a.py::test_y PASSED; exit 1'")
        code, out, _ = self.run_cli("tool", "test", "--story", "STORY-01-01")
        self.assertEqual(code, EXIT_NOT_READY)
        dau = out.splitlines()[:5]
        self.assertIn("1 passed · 1 failed · 0 skipped (pytest)", dau)
        self.assertTrue(any("✗ tests/test_a.py::test_x" in line for line in dau), dau)

    def test_output_dai_khai_cat_va_tro_toan_van(self):
        self.config("seq 1 500")
        code, out, _ = self.run_cli("tool", "test", "--story", "STORY-01-01", "--lines", "40")
        self.assertIn("(truncated 460/500 lines — full output: ", out)
        path = out.split("full output: ")[1].split(")")[0]
        self.assertTrue((self.project / path).is_file(), path)
        self.assertEqual(len((self.project / path).read_text(encoding="utf-8").splitlines()), 500)

    def test_output_ngan_khong_co_dong_luoc(self):
        self.config("seq 1 10")
        _, out, _ = self.run_cli("tool", "test", "--story", "STORY-01-01")
        self.assertNotIn("truncated", out)


class TestStatusDemKetCuc(CliTestCase):
    """ADR-005 V11 (B): `status` đếm lượt theo `exit_status` harness chuẩn hoá
    lúc ghi; bản ghi cũ không có khoá là "chưa ghi", không suy đoán thay."""

    def test_dem_theo_exit_status(self):
        from aisef.clients.stream import RunResult
        from aisef.harness.observe import AGENT_RUN, Event, EvidenceStore
        StateStore(self.artifacts).register("S-01", "E-01")
        ev = EvidenceStore(self.artifacts)
        ev.agent_run("S-01", RunResult(ok=False, error="max_turns"), name="S-01#1")
        ev.agent_run("S-01", RunResult(ok=True, text="x"), name="S-01#2")
        ev.record("S-01", Event(kind=AGENT_RUN, name="S-01-cu"))
        _, out, _ = self.run_cli("status")
        line = next(l for l in out.splitlines() if l.startswith("Agent runs: "))
        for phan in ("max_turns 1", "ok 1", "unrecorded 1"):
            self.assertIn(phan, line)


class TestStatusAttemptsDoLuotDiDauMat(CliTestCase):
    """`aisef status --attempts` trả lời câu hỏi của ADR-009 O4.

    Sổ nói được một lần chạy tốn bao nhiêu, chưa nói được tiền ấy mua gì. Bước
    đầu: lượt nào chết vì cái gì. Trượt vì test đỏ và trượt vì người rà soát
    chặn là hai bài toán khác nhau với hai chi phí sửa khác nhau.
    """

    def _du_lieu(self) -> None:
        from aisef.harness.observe import AGENT_RUN, NOTE, Event, EvidenceStore

        store = EvidenceStore(self.artifacts)
        store.record("STORY-01-01", Event(kind=NOTE, name="gate:input", detail={"attempt": 1}))
        store.record("STORY-01-01", Event(kind=NOTE, name="gate:verdict", ok=False,
                                          detail={"attempt": 1, "failures": ["review"]}))
        store.record("STORY-01-01", Event(kind=NOTE, name="gate:verdict", ok=True,
                                          detail={"attempt": 2, "failures": []}))
        # Pha kế hoạch: có phiên agent nhưng **không** qua cổng story.
        store.record("plan-architecture", Event(kind=AGENT_RUN, name="plan",
                                                detail={"role": "", "exit_status": "ok"}))

    def test_dem_dung_va_khong_tinh_pha_ke_hoach(self):
        self._du_lieu()
        code, out, _ = self.run_cli("status", "--attempts")
        self.assertEqual(code, 0)
        self.assertIn("Attempts: 2 across 1 stories", out)
        self.assertIn("review", out)
        self.assertNotIn("plan-architecture", out)

    def test_khong_co_lan_cham_nao_thi_noi_thang(self):
        code, out, _ = self.run_cli("status", "--attempts")
        self.assertEqual(code, 0)
        self.assertTrue("no gate verdict recorded yet" in out or "No stories registered" in out, out)

class TestCliLuonNoiUtf8(unittest.TestCase):
    """`main()` phải đặt stdout/stderr về UTF-8 **trước** khi chạy lệnh.

    Không có bước này thì trên console Windows (cp1252 trên runner CI) mọi lệnh
    in `✅`, `·` hay tiếng Việt sẽ chết bằng UnicodeEncodeError trên chính đầu
    ra của nó — và tiến trình cha đọc được mojibake. Lỗi ấy đã xảy ra thật
    2026-09-13 ở `aisef dashboard`; phép thử này là cái chuông cho lần sau.
    """

    def test_main_goi_speak_utf8_truoc_khi_chay_lenh(self):
        from unittest.mock import patch

        from aisef.cli import parser as P

        goi: list[str] = []
        with patch.object(P, "_speak_utf8", lambda: goi.append("x")):
            P.main(["doctor"])        # lệnh rẻ nhất; mã thoát không quan trọng ở đây
        self.assertEqual(goi, ["x"])

    def test_speak_utf8_dat_dung_bang_ma(self):
        from unittest.mock import MagicMock, patch

        from aisef.cli.parser import _speak_utf8

        gia = MagicMock()
        with patch("sys.stdout", gia), patch("sys.stderr", gia):
            _speak_utf8()
        gia.reconfigure.assert_called_with(encoding="utf-8", errors="replace")

    def test_stream_khong_reconfigure_duoc_thi_bo_qua_chu_khong_no(self):
        """`StringIO` trong test không có `reconfigure` — lệnh vẫn phải chạy."""
        import io
        from unittest.mock import patch

        from aisef.cli.parser import _speak_utf8

        with patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()):
            _speak_utf8()      # không ném là đạt

class TestQuyUocMaThoat(unittest.TestCase):
    """`0` xong · `1` gõ sai · `2` chưa sẵn sàng — README hứa thế để CI phân
    biệt "hỏng" với "chưa tới lúc".

    Mặc định của argparse là thoát **2** khi gõ sai, tức một lỗi gõ lệnh đọc
    thành "chưa tới lúc" và script CI đi tiếp như thể bình thường. Đo 13/09/2026
    trên bản 1.4.0: `aisef evidence` thiếu tham số thoát 2.
    """

    def _chay(self, *args) -> int:
        import subprocess
        return subprocess.run([sys.executable, "-m", "aisef", *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT)).returncode

    def test_thieu_tham_so_la_go_sai_thoat_1(self):
        self.assertEqual(self._chay("evidence"), 1)

    def test_lenh_khong_ton_tai_thoat_1(self):
        self.assertEqual(self._chay("khong-co-lenh-nay"), 1)

    def test_co_khong_ton_tai_thoat_1(self):
        self.assertEqual(self._chay("status", "--co-nay-khong-co"), 1)

    def test_project_dat_sau_ten_lenh_cung_chay(self):
        """`aisef gates --project X` là dạng người thật gõ (và `git`/`docker`
        nhận). Trước 13/09/2026 nó ra lỗi gõ sai; sau bản vá, hai thứ tự cho
        cùng mã thoát và cùng đầu ra."""
        import subprocess
        import tempfile
        # `encoding="utf-8"` là thứ phải có: `text=True` trần giải mã bằng bảng
        # mã của máy (cp1252 trên runner Windows), mà tiến trình con nói UTF-8,
        # nên luồng đọc chết trong thread và `stdout` về `None` — đúng cái
        # `out=None` đã làm CI Windows đỏ ba vòng (lỗi 99). Thông báo lỗi vẫn
        # mang nguyên văn cả ba trường để lần sau đọc được sự thật thay vì đoán.
        with tempfile.TemporaryDirectory() as d:
            sau = subprocess.run([sys.executable, "-m", "aisef", "gates", "--project", d],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
            truoc = subprocess.run([sys.executable, "-m", "aisef", "--project", d, "gates"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
        chi_tiet = (f"sau: rc={sau.returncode} out={sau.stdout!r} err={sau.stderr!r}\n"
                    f"truoc: rc={truoc.returncode} out={truoc.stdout!r} err={truoc.stderr!r}")
        self.assertEqual(sau.returncode, truoc.returncode, chi_tiet)
        self.assertEqual(sau.stdout, truoc.stdout, chi_tiet)
        self.assertIn("prd", sau.stdout or "", chi_tiet)

    def test_project_truoc_lenh_khong_bi_subparser_ghi_de(self):
        """Cái bẫy của argparse: nếu subparser khai `--project` với mặc định
        `"."` thì `aisef --project X gates` bị ghi đè về `"."` — hỏng im lặng,
        tệ hơn lỗi gõ sai. `default=SUPPRESS` là thứ chặn điều đó."""
        from aisef.cli.parser import _cho_moi_lenh_nhan_project, build_parser
        p = build_parser()
        _cho_moi_lenh_nhan_project(p)
        self.assertEqual(p.parse_args(["--project", "/tmp/x", "gates"]).project, "/tmp/x")
        self.assertEqual(p.parse_args(["gates", "--project", "/tmp/y"]).project, "/tmp/y")

    def test_reject_doi_tao_tac_co_that_nhu_approve(self):
        """`approve` đòi tạo tác có thật; nếu `reject` không đòi thì ghi được một
        lời từ chối cho thứ **chưa tồn tại**, và khi pha kế hoạch sinh ra tạo
        tác thật thì cổng đã mang sẵn trạng thái "bị từ chối" kèm nhận xét viết
        trước khi có gì để nhận xét. Đo 13/09/2026: `approve prd` thoát 2 trong
        khi `reject prd` thoát 0 trên cùng dự án rỗng."""
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ap = subprocess.run([sys.executable, "-m", "aisef", "approve", "prd", "--project", d],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
            rj = subprocess.run([sys.executable, "-m", "aisef", "reject", "prd",
                                 "--note", "x", "--project", d],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
        self.assertEqual(ap.returncode, 2, ap.stderr[-200:])
        self.assertEqual(rj.returncode, 2, rj.stdout + rj.stderr)
        self.assertIn("nothing to reject yet", rj.stderr)

    def test_guard_go_sai_thi_chan_chu_khong_cho_qua(self):
        """Hook đọc mã thoát: **2 = chặn**, mọi mã khác = không chặn. Nên quy
        ước "1 = gõ sai" đúng ở mọi lệnh **trừ** `guard`.

        Bản vá lỗi 81 đã mở đúng lỗ hổng này (gõ sai tên guard → thoát 1 → hook
        cho qua) và nó được bắt bằng cách chạy lệnh guard bằng tay. Lỗi 32 đã
        dạy một lần: guard không chạy được thì phải chặn."""
        import subprocess
        for args in (["guard", "khong-co-guard-nay"], ["guard"]):
            with self.subTest(args=args):
                r = subprocess.run([sys.executable, "-m", "aisef", *args],
                                   input="{}", capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
                self.assertEqual(r.returncode, 2, r.stderr[-200:])
                self.assertIn("blocking, not allowing", r.stderr)

    def test_chua_san_sang_van_thoat_2(self):
        """Đừng sửa lỗi này bằng cách biến mọi thứ thành 1: cổng chưa duyệt
        **phải** còn là 2, nếu không CI hết phân biệt được hai ca."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            import subprocess
            rc = subprocess.run([sys.executable, "-m", "aisef", "gates", "--project", d],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT)).returncode
        self.assertEqual(rc, 2)
