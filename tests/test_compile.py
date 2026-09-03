"""Kiểm chứng biên dịch cấu hình client."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.compile import (  # noqa: E402
    ADAPTERS,
    build_claude_settings,
    build_opencode_plugin,
    compile_for,
    write_compile_report,
)
from aisdlc.harness.guardrails import GUARD_MATCHERS  # noqa: E402


class CompileTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestClaudeSettings(CompileTestCase):
    def settings(self) -> dict:
        return build_claude_settings(self.project, "/usr/local/bin/aisdlc")

    def test_shape_matches_verified_format(self):
        """Định dạng này đã kiểm chứng chặn thật ở spike S2."""
        s = self.settings()
        self.assertIn("hooks", s)
        self.assertIn("PreToolUse", s["hooks"])
        entry = s["hooks"]["PreToolUse"][0]
        self.assertIn("matcher", entry)
        self.assertEqual(entry["hooks"][0]["type"], "command")

    def test_every_guard_is_wired(self):
        s = self.settings()
        commands = [
            h["command"]
            for entries in s["hooks"].values()
            for e in entries
            for h in e["hooks"]
        ]
        for kind in GUARD_MATCHERS:
            with self.subTest(guard=kind):
                self.assertTrue(any(f"guard {kind}" in c for c in commands))

    def test_matchers_come_from_single_source(self):
        """Guard mô tả một lần; compile chỉ dịch lại."""
        s = self.settings()
        matchers = {e["matcher"] for entries in s["hooks"].values() for e in entries}
        for _, matcher in GUARD_MATCHERS.values():
            self.assertIn(matcher, matchers)

    def test_marked_as_generated(self):
        self.assertIn("không sửa tay", self.settings()["_generated"])


class TestOpenCodePlugin(CompileTestCase):
    def test_calls_same_guards(self):
        src = build_opencode_plugin(self.project, "/bin/aisdlc")
        for kind in GUARD_MATCHERS:
            self.assertIn(f'"{kind}"', src)

    def test_treats_exit_two_as_block(self):
        """Cùng quy ước mã thoát với Claude Code."""
        self.assertIn("exitCode === 2", build_opencode_plugin(self.project, "/bin/aisdlc"))

    def test_hooks_the_right_event(self):
        self.assertIn("tool.execute.before", build_opencode_plugin(self.project, "/bin/aisdlc"))


class TestCompileFor(CompileTestCase):
    def test_claude_writes_settings(self):
        r = compile_for("claude", self.project)
        self.assertTrue((self.project / ".claude" / "settings.json").is_file())
        self.assertEqual(r.client, "claude")

    def test_opencode_writes_plugin(self):
        compile_for("opencode", self.project)
        self.assertTrue((self.project / ".opencode" / "plugin" / "aisdlc-guard.ts").is_file())

    def test_claude_blocks_at_source(self):
        self.assertTrue(compile_for("claude", self.project).blocks_at_source)

    def test_opencode_declared_post_hoc(self):
        """S4 chưa chứng minh guard chặn → phải báo là hậu kiểm."""
        r = compile_for("opencode", self.project)
        self.assertFalse(r.blocks_at_source)
        self.assertEqual(sorted(r.guards_post_hoc), sorted(GUARD_MATCHERS))
        self.assertEqual(r.guards_wired, [])

    def test_opencode_reports_degradations(self):
        r = compile_for("opencode", self.project)
        self.assertTrue(any("pre_tool_guard" in d for d in r.degradations))

    def test_claude_has_no_degradations(self):
        self.assertEqual(compile_for("claude", self.project).degradations, [])

    def test_unknown_client_rejected(self):
        with self.assertRaises(ValueError):
            compile_for("khong-co", self.project)

    def test_settings_json_is_valid(self):
        compile_for("claude", self.project)
        raw = (self.project / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertIn("hooks", json.loads(raw))

    def test_recompile_is_stable(self):
        compile_for("claude", self.project)
        first = (self.project / ".claude" / "settings.json").read_text(encoding="utf-8")
        compile_for("claude", self.project)
        self.assertEqual(first, (self.project / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_warning_message_is_actionable(self):
        r = compile_for("opencode", self.project)
        self.assertIn("hậu kiểm", r.summary())
        self.assertIn("verify", r.summary())


class TestCompileReport(CompileTestCase):
    def test_report_records_assurance_level(self):
        reports = [compile_for(c, self.project) for c in sorted(ADAPTERS)]
        path = write_compile_report(self.project, reports)
        data = json.loads(path.read_text(encoding="utf-8"))

        by_client = {c["client"]: c for c in data["clients"]}
        self.assertTrue(by_client["claude"]["blocks_at_source"])
        self.assertFalse(by_client["opencode"]["blocks_at_source"])

    def test_report_lists_written_files(self):
        path = write_compile_report(self.project, [compile_for("claude", self.project)])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(".claude/settings.json", data["clients"][0]["written"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
