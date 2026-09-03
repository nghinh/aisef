"""Kiểm chứng adapter client và bảng khai báo năng lực."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.base import Capability, RunSpec, Support  # noqa: E402
from aisdlc.clients.claude_code import ClaudeCodeAdapter  # noqa: E402
from aisdlc.clients.opencode import OpenCodeAdapter  # noqa: E402

ADAPTERS = [ClaudeCodeAdapter(), OpenCodeAdapter()]


class TestSupportSemantics(unittest.TestCase):
    def test_only_native_and_emulated_block_at_source(self):
        self.assertTrue(Support.NATIVE.blocks_at_source)
        self.assertTrue(Support.EMULATED.blocks_at_source)
        self.assertFalse(Support.POST_HOC.blocks_at_source)
        self.assertFalse(Support.UNSUPPORTED.blocks_at_source)


class TestCapabilityDeclaration(unittest.TestCase):
    def test_every_adapter_declares_every_capability(self):
        """Không được im lặng bỏ trống — thiếu khai là thiếu thông tin."""
        for adapter in ADAPTERS:
            with self.subTest(client=adapter.id):
                declared = adapter.capabilities()
                for cap in Capability:
                    self.assertIn(cap, declared, f"{adapter.id} chưa khai {cap.value}")

    def test_claude_blocks_at_source(self):
        """S2 đã chứng minh hook chặn thật."""
        self.assertTrue(ClaudeCodeAdapter().guards_block_at_source())

    def test_opencode_declared_post_hoc_until_proven(self):
        """S4 chưa chứng minh guard chặn → khai POST_HOC, không khai NATIVE."""
        oc = OpenCodeAdapter()
        self.assertIs(oc.supports(Capability.PRE_TOOL_GUARD), Support.POST_HOC)
        self.assertFalse(oc.guards_block_at_source())

    def test_degradations_are_reported(self):
        degradations = OpenCodeAdapter().degradations()
        self.assertTrue(any("pre_tool_guard" in d for d in degradations))
        self.assertTrue(any("dir_allowlist" in d for d in degradations))

    def test_claude_has_no_degradations(self):
        self.assertEqual(ClaudeCodeAdapter().degradations(), [])


class TestClaudeCommand(unittest.TestCase):
    def setUp(self):
        self.a = ClaudeCodeAdapter()

    def spec(self, **kw) -> RunSpec:
        return RunSpec(prompt="làm gì đó", workdir=Path("."), **kw)

    def test_minimum_flags(self):
        cmd = self.a.build_command(self.spec())
        self.assertIn("-p", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("stream-json", cmd)
        self.assertIn("--verbose", cmd)

    def test_optional_flags_absent_when_unset(self):
        cmd = self.a.build_command(self.spec())
        for flag in ("--model", "--max-turns", "--settings", "--add-dir", "--session-id"):
            self.assertNotIn(flag, cmd)

    def test_settings_and_dirs(self):
        cmd = self.a.build_command(
            self.spec(settings_file=Path("/x/s.json"), extra_dirs=[Path("/a"), Path("/b")])
        )
        self.assertIn("--settings", cmd)
        self.assertEqual(cmd.count("--add-dir"), 2)

    def test_tool_lists(self):
        cmd = self.a.build_command(self.spec(allowed_tools=["Read", "Write"],
                                             disallowed_tools=["Bash"]))
        self.assertIn("--allowed-tools", cmd)
        self.assertIn("Read", cmd)
        self.assertIn("--disallowed-tools", cmd)

    def test_max_turns_is_string(self):
        cmd = self.a.build_command(self.spec(max_turns=40))
        self.assertIn("40", cmd)


class TestOpenCodeCommand(unittest.TestCase):
    def test_run_subcommand(self):
        cmd = OpenCodeAdapter().build_command(RunSpec(prompt="xin chào", workdir=Path(".")))
        self.assertEqual(cmd[1], "run")
        self.assertIn("xin chào", cmd)

    def test_model_flag(self):
        cmd = OpenCodeAdapter().build_command(
            RunSpec(prompt="p", workdir=Path("."), model="anthropic/x")
        )
        self.assertIn("--model", cmd)


class TestGuardRails(unittest.TestCase):
    def test_missing_binary_returns_error_not_crash(self):
        a = ClaudeCodeAdapter(binary="lenh-khong-ton-tai-12345")
        r = a.run(RunSpec(prompt="p", workdir=Path(".")))
        self.assertFalse(r.ok)
        self.assertIn("không tìm thấy", r.error)

    def test_missing_workdir_reported(self):
        a = ClaudeCodeAdapter()
        if not a.available():
            self.skipTest("chưa cài claude")
        r = a.run(RunSpec(prompt="p", workdir=Path("/khong/ton/tai")))
        self.assertFalse(r.ok)
        self.assertIn("workdir", r.error)

    def test_adapters_available_on_this_machine(self):
        """Ghi nhận thực tế máy đang chạy, không bắt buộc."""
        for a in ADAPTERS:
            with self.subTest(client=a.id):
                self.assertIsInstance(a.available(), bool)


class TestTimeoutIsInfrastructureError(unittest.TestCase):
    def test_timeout_message_distinguishes_from_quality_failure(self):
        """Hết giờ ≠ story kém — phân biệt được mới quyết đúng nên thử lại."""
        with tempfile.TemporaryDirectory() as d:
            # Binary giả: nuốt mọi tham số rồi ngủ, để chạm đúng nhánh timeout.
            fake = Path(d) / "cham-chap"
            fake.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
            fake.chmod(0o755)

            r = ClaudeCodeAdapter(binary=str(fake)).run(
                RunSpec(prompt="p", workdir=Path(d), timeout_seconds=1)
            )
        self.assertFalse(r.ok)
        self.assertIn("quá 1s", r.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
