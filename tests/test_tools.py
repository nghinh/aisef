"""Tool của harness — lệnh cố định, chạy trong sandbox, ghi bằng chứng."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisdlc.harness.tools import (  # noqa: E402
    TOOLS,
    aisdlc_command,
    command_for,
    image_for,
    describe_tools,
    detect_commands,
    run_tool,
)


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        self.cfg = Config(dict(DEFAULTS))

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str = "") -> None:
        (self.project / name).write_text(text, encoding="utf-8")


class TestDetectCommands(ToolTestCase):
    def test_python_project(self):
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.assertEqual(detect_commands(self.project)["test"], "pytest -q")

    def test_go_project(self):
        self.write("go.mod", "module x\n")
        self.assertEqual(detect_commands(self.project)["test"], "go test ./...")

    def test_node_uses_scripts_that_exist(self):
        self.write("package.json", json.dumps({"scripts": {"test": "vitest run"}}))
        cmds = detect_commands(self.project)
        self.assertEqual(cmds["test"], "npm test --silent")
        self.assertEqual(cmds["lint"], "")

    def test_node_without_a_test_script_declares_nothing(self):
        """`npm test` khi không có script `test` thoát khác 0 vì lý do sai —
        cổng sẽ báo "test đỏ" trong khi dự án chưa hề có test."""
        self.write("package.json", json.dumps({"scripts": {"build": "tsc"}}))
        self.assertEqual(detect_commands(self.project)["test"], "")

    def test_node_falls_back_to_typecheck_for_lint(self):
        self.write("package.json", json.dumps({"scripts": {"typecheck": "tsc --noEmit"}}))
        self.assertEqual(detect_commands(self.project)["lint"], "npm run typecheck --silent")

    def test_broken_package_json_does_not_crash(self):
        self.write("package.json", "{ hỏng")
        self.assertEqual(detect_commands(self.project)["test"], "")

    def test_unknown_stack(self):
        self.assertEqual(detect_commands(self.project), {"test": "", "lint": "", "sast": ""})

    def test_config_beats_detection(self):
        self.write("pyproject.toml", "")
        cfg = Config({**DEFAULTS, "tools.test": "make test"})
        self.assertEqual(command_for("test", self.project, cfg), "make test")

    def test_empty_config_value_falls_back_to_detection(self):
        self.write("pyproject.toml", "")
        self.assertEqual(command_for("test", self.project, self.cfg), "pytest -q")


class TestSandboxImage(ToolTestCase):
    """`alpine` không có node hay python: chạy `npm test` trong đó sẽ đỏ vì
    **thiếu công cụ**, không phải vì code sai — và một cổng báo đỏ vì lý do
    sai sẽ bị bỏ qua trong hai ngày."""

    def test_image_follows_the_stack(self):
        self.write("package.json", "{}")
        self.assertEqual(image_for(self.project, self.cfg), "node:22-alpine")

    def test_python_stack(self):
        self.write("pyproject.toml", "")
        self.assertEqual(image_for(self.project, self.cfg), "python:3.12-alpine")

    def test_config_wins(self):
        self.write("package.json", "{}")
        cfg = Config({**DEFAULTS, "sandbox.image": "cong-ty/ci:2024"})
        self.assertEqual(image_for(self.project, cfg), "cong-ty/ci:2024")

    def test_unknown_stack_falls_back(self):
        self.assertEqual(image_for(self.project, self.cfg), "alpine:latest")


class TestRunTool(ToolTestCase):
    def run_test_tool(self, command: str, **kw):
        cfg = Config({**DEFAULTS, "tools.test": command, "sandbox.allow_degraded": True})
        return run_tool(
            "test", self.project, story_id="S-01",
            artifact_root=self.artifacts, config=cfg, **kw,
        )

    def test_green_command(self):
        res = self.run_test_tool("true")
        self.assertTrue(res.ok)
        self.assertEqual(res.exit_code, 0)

    def test_red_command(self):
        res = self.run_test_tool("false")
        self.assertFalse(res.ok)

    def test_output_captured_for_the_agent_to_read(self):
        res = self.run_test_tool("sh -c 'echo hai dòng; echo lỗi ở đây; exit 1'")
        self.assertIn("lỗi ở đây", res.tail())

    def test_evidence_recorded(self):
        """Cổng và guard đọc bằng chứng, không đọc lời agent kể."""
        self.run_test_tool("true")
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertIsNotNone(e)
        self.assertTrue(e.ok)
        self.assertEqual(e.detail["command"], "true")

    def test_test_ids_and_coverage_land_in_evidence(self):
        """Output runner → tên test + coverage trong bằng chứng, không chỉ `tail`."""
        from pathlib import Path
        # Lệnh chạy trong sandbox (có thể là Docker): chỉ thấy workspace,
        # nên đặt output mẫu vào dự án chứ không trỏ đường dẫn máy chủ.
        fx = Path(__file__).parent / "fixtures" / "testlog" / "node-test-fail.txt"
        (Path(self.project) / "out.txt").write_text(fx.read_text(encoding="utf-8"), encoding="utf-8")
        self.run_test_tool("sh -c 'cat out.txt; echo \"TOTAL 10 1 90%\"; exit 1'")
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertEqual(e.detail["test_format"], "node-spec")
        self.assertIn("AC-STORY-01-01-1: chuỗi rỗng trả về rỗng", e.detail["test_ids"])
        self.assertEqual(e.detail["failed_ids"], ["AC-STORY-01-01-3: thất bại"])
        self.assertEqual(e.detail["coverage"], 90.0)

    def test_failure_is_recorded_too(self):
        self.run_test_tool("false")
        self.assertFalse(EvidenceStore(self.artifacts).read("S-01").tests_green())

    def test_missing_command_is_skipped_not_failed_silently(self):
        """Chưa khai lệnh ≠ test đỏ. Nhưng vẫn phải ghi lại, nếu không
        story sẽ 'xong' mà chưa từng chạy test."""
        res = run_tool("test", self.project, story_id="S-01",
                       artifact_root=self.artifacts, config=self.cfg)
        self.assertFalse(res.ok)
        self.assertTrue(res.skipped)
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertFalse(e.ok)
        self.assertIn("chưa khai lệnh", e.detail["skipped"])

    def test_no_story_means_no_evidence(self):
        """Người gõ tay không nên làm bẩn hồ sơ story."""
        cfg = Config({**DEFAULTS, "tools.test": "true"})
        run_tool("test", self.project, config=cfg)
        self.assertEqual(EvidenceStore(self.artifacts).stories(), [])

    def test_unknown_tool_raises(self):
        with self.assertRaises(ValueError):
            run_tool("khong-co", self.project)


class TestProviderGia(ToolTestCase):
    """`run_tool` trên `FakeProvider` (ADR-005 V5) — không Docker; lỗi hạ tầng
    sandbox thành `unrunnable`, không thành test đỏ."""

    def test_loi_ha_tang_la_khong_chay_duoc_khong_phai_test_do(self):
        from aisdlc.harness import sandbox

        fake = sandbox.FakeProvider([sandbox.SandboxResult(
            125, stderr="docker: Error response from daemon: pull access denied",
            provider_error="pull access denied")])
        cfg = Config({**DEFAULTS, "tools.test": "pytest -q", "sandbox.provider": "fake"})
        with sandbox.using(fake):
            res = run_tool("test", self.project, story_id="S-01",
                           artifact_root=self.artifacts, config=cfg)
        self.assertFalse(res.ok)
        self.assertIn("hạ tầng sandbox", res.unrunnable)
        self.assertFalse(res.degraded)
        self.assertEqual(fake.calls[0].cmd, ["pytest", "-q"])
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertEqual(e.detail["provider_error"], "pull access denied")
        self.assertIn("hạ tầng", e.detail["unrunnable"])

    def test_suy_bien_neu_ten_bao_dam_thieu(self):
        cfg = Config({**DEFAULTS, "tools.test": "true", "sandbox.use_docker": False})
        res = run_tool("test", self.project, config=cfg)
        self.assertTrue(res.degraded)
        self.assertEqual(res.detail["missing"], ["network_none", "non_root", "secrets_absent"])
        self.assertIn("network_none", res.summary())


class TestDescription(ToolTestCase):
    def test_every_tool_says_when_to_call_it(self):
        """Tool không có mô tả dùng đúng lúc thì agent sẽ gọi sai lúc."""
        for tool in TOOLS.values():
            self.assertTrue(len(tool.when) > 30, tool.name)

    def test_prompt_names_a_command_the_agent_can_actually_run(self):
        """`aisdlc tool test` là vô dụng nếu `aisdlc` không nằm trên PATH
        của phiên agent: nó nhận "command not found", tự chạy pytest bằng
        tay, và lần chạy đó không vào bằng chứng."""
        import os
        import shutil

        binary = aisdlc_command()
        if binary != "aisdlc":
            self.assertTrue(os.path.isfile(binary), binary)
            self.assertTrue(os.access(binary, os.X_OK), binary)
        else:
            self.assertTrue(shutil.which("aisdlc"))
        self.assertIn(binary, describe_tools(self.project, self.cfg))

    def test_prompt_table_shows_the_real_command(self):
        self.write("pyproject.toml", "")
        text = describe_tools(self.project, self.cfg)
        self.assertIn("pytest -q", text)
        self.assertIn("Khi nào:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestKhongChayDuocKhacDo(ToolTestCase):
    """Dogfood par: `node --test src/` → MODULE_NOT_FOUND bị coi là test đỏ,
    guard completion chặn Stop ~10 lần/lượt, 3 story đốt $17."""

    def run_test_tool(self, command: str):
        cfg = Config({**DEFAULTS, "tools.test": command, "sandbox.allow_degraded": True})
        return run_tool("test", self.project, story_id="S-01", artifact_root=self.artifacts, config=cfg)

    def test_module_not_found_is_unrunnable(self):
        res = self.run_test_tool("sh -c 'echo \"Error: Cannot find module x\"; echo \"code: MODULE_NOT_FOUND\" >&2; exit 1'")
        self.assertFalse(res.ok)
        self.assertIn("không nạp được", res.unrunnable)
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertTrue(e.detail["unrunnable"])

    def test_red_test_mentioning_not_found_is_still_red(self):
        from pathlib import Path
        (Path(self.project) / "out.txt").write_text(
            "✔ AC-S-1: có (1ms)\n✖ AC-S-2: element not found (2ms)\nℹ tests 2\nℹ pass 1\nℹ fail 1\n", encoding="utf-8")
        res = self.run_test_tool("sh -c 'cat out.txt; exit 1'")
        self.assertFalse(res.ok)
        self.assertEqual(res.unrunnable, "")
