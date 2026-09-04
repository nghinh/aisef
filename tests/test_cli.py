"""Kiểm chứng CLI — chạy qua `main()` như người dùng thật gọi."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main  # noqa: E402
from aisdlc.control.state import StateStore, StoryStatus  # noqa: E402


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "requirements.md").write_text("# yêu cầu\n", encoding="utf-8")
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()

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


class TestEveryCommandIsUsable(unittest.TestCase):
    """Lỗi khai đối số chỉ lộ ra lúc người dùng gõ lệnh — trừ khi có test."""

    def commands(self) -> list[str]:
        from aisdlc.cli import build_parser

        parser = build_parser()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        return sorted(actions[0].choices) if actions else []

    def test_at_least_the_six_steps_exist(self):
        for name in ("setup", "plan", "mockup", "run", "qa", "devsecops",
                     "pre-deploy", "report", "gates", "guard", "verify", "tool"):
            self.assertIn(name, self.commands())

    def test_help_works_for_every_command(self):
        from aisdlc.cli import build_parser

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
        self.assertIn("sẵn sàng", out)

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


class TestDoctorSkillFreshness(CliTestCase):
    def test_stale_framework_skill_is_flagged(self):
        """Skill của framework nằm trong kho framework; dự án giữ một bản
        sao. Sửa skill mà không cài lại thì agent vẫn chạy bản cũ, và cách
        duy nhất phát hiện là ngồi so từng file."""
        from aisdlc.kit.install import OWN_SKILLS

        own = next(OWN_SKILLS.glob("*/SKILL.md"))
        copied = self.project / ".claude" / "skills" / own.parent.name / "SKILL.md"
        copied.parent.mkdir(parents=True)
        copied.write_text("bản cũ\n", encoding="utf-8")

        _, out, _ = self.run_cli("doctor")
        self.assertIn("cũ hơn kho", out)
        self.assertIn(own.parent.name, out)

    def test_matching_copy_passes(self):
        from aisdlc.kit.install import OWN_SKILLS

        own = next(OWN_SKILLS.glob("*/SKILL.md"))
        copied = self.project / ".claude" / "skills" / own.parent.name / "SKILL.md"
        copied.parent.mkdir(parents=True)
        copied.write_bytes(own.read_bytes())
        _, out, _ = self.run_cli("doctor")
        self.assertIn("khớp bản gốc", out)


class TestGates(CliTestCase):
    def test_lists_all_eight_gates(self):
        code, out, _ = self.run_cli("gates")
        for gate in ("prd", "architecture", "ux-spec", "epics", "stories",
                     "mockups", "readiness", "pre-deploy"):
            self.assertIn(gate, out)
        self.assertEqual(code, EXIT_NOT_READY)  # chưa cổng nào duyệt

    def test_points_at_next_gate(self):
        _, out, _ = self.run_cli("gates")
        self.assertIn("Cổng kế tiếp cần xử lý: prd", out)

    def test_flags_missing_artifact_by_name(self):
        """Nói thiếu file nào, không chỉ nói thiếu — cổng ux-spec có hai
        file nên "chưa có artifact" không đủ để biết phải làm gì."""
        _, out, _ = self.run_cli("gates")
        self.assertIn("thiếu: prd.md", out)
        self.assertIn("thiếu: DESIGN.md, EXPERIENCE.md", out)


class TestApproveReject(CliTestCase):
    def test_cannot_approve_without_artifact(self):
        code, _, err = self.run_cli("approve", "prd")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("chưa có artifact", err)

    def test_approve_with_artifact(self):
        self.write_artifact("prd.md")
        code, out, _ = self.run_cli("approve", "prd")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("đã duyệt", out)

    def test_cannot_approve_out_of_order(self):
        """Duyệt architecture khi prd chưa duyệt là bỏ qua thứ tự."""
        self.write_artifact("architecture.md")
        code, _, err = self.run_cli("approve", "architecture")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("cổng phía trước chưa duyệt", err)

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
        self.assertIn("không cổng nào có artifact", out)


class TestReview(CliTestCase):
    def test_missing_artifact(self):
        code, out, _ = self.run_cli("review", "prd")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("chưa có artifact", out)

    def test_shows_content_and_next_steps(self):
        self.write_artifact("prd.md", "# PRD\n\ndòng một\ndòng hai\n")
        code, out, _ = self.run_cli("review", "prd")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("dòng một", out)
        self.assertIn("aisdlc approve prd", out)

    def test_truncates_long_artifact(self):
        self.write_artifact("prd.md", "\n".join(f"dòng {i}" for i in range(200)))
        _, out, _ = self.run_cli("review", "prd", "--lines", "10")
        self.assertIn("còn 190 dòng", out)

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

        from aisdlc.phases.story_split import split

        fix = Path(__file__).resolve().parent / "fixtures" / "bmad"
        for name in ("epics.md", "prd.md"):
            shutil.copy(fix / name, self.artifacts / name)
        split(self.artifacts)

        code, out, _ = self.run_cli("review", "stories")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("EPIC-01", out)
        self.assertIn("đợt 2 (song song)", out)
        self.assertIn("phủ: FR-1", out)
        self.assertIn("cổng máy: ĐẠT", out)


class TestMockupCommand(CliTestCase):
    def test_rejects_unknown_client(self):
        code, _, err = self.run_cli("mockup", "--client", "khong-co")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("khong-co", err)

    def test_without_experience_file(self):
        code, out, _ = self.run_cli("mockup")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("EXPERIENCE.md", out)

    def test_review_mockups_shows_screens_and_index_link(self):
        import shutil

        from aisdlc.control.design_contract import CONTRACT_FILE
        from aisdlc.control.experience import parse_experience_file
        from aisdlc.harness import browser
        from aisdlc.phases.mockup import extract

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
        self.assertIn("cam kết:", out)
        self.assertIn("chưa chốt", out)      # tim-kiem cố ý còn OQ-4


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
        self.assertIn("chưa khai lệnh", out)

    def test_runs_and_records_evidence(self):
        (self.project / ".ai").mkdir()
        (self.project / ".ai" / "config.json").write_text(
            '{"tools.test": "true"}', encoding="utf-8")
        code, out, _ = self.run_cli("tool", "test", "--story", "STORY-01-01")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("✅ test", out)

        from aisdlc.harness.observe import EvidenceStore

        self.assertTrue(EvidenceStore(self.artifacts).read("STORY-01-01").tests_green())


class TestVerifyCommand(CliTestCase):
    def test_clean_tree_passes(self):
        code, out, _ = self.run_cli("verify")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("hậu kiểm đạt", out)

    def test_story_without_tests_fails_post_hoc(self):
        """Lớp bảo đảm cho client không gắn được hook tiền kiểm."""
        code, out, _ = self.run_cli("verify", "--story", "STORY-01-01")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("chưa có lần chạy test", out)


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


class TestQaCommand(CliTestCase):
    def test_unconfigured_blocks_release_level(self):
        """Mặc định là mức trước triển khai: chưa chạy thì không phải đạt."""
        code, out, _ = self.run_cli("qa")
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("chưa cấu hình", out)

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
        self.assertIn("Chưa có story", out)

    def test_shows_progress_and_cost(self):
        store = StateStore(self.artifacts)
        store.register("S-01", "E-01")
        store.transition("S-01", StoryStatus.RUNNING, cost_usd=1.5)
        store.transition("S-01", StoryStatus.VERIFYING)
        store.transition("S-01", StoryStatus.DONE)
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("1/1 story xong", out)
        self.assertIn("$1.50", out)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
