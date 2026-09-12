from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import Capability, RunSpec
from aisef.clients.claude_code import ClaudeCodeAdapter, DEFAULT_TOOLS, PERMISSION_MODE
from aisef.clients.opencode import OpenCodeAdapter, parse_json_events, _TOOL_NAMES


def _spec(**kw):
    kw.setdefault("prompt", "test")
    kw.setdefault("workdir", Path("/tmp/test"))
    return RunSpec(**kw)


class TestClaudeCodeId(unittest.TestCase):
    def test_id(self):
        self.assertEqual(ClaudeCodeAdapter().id, "claude")

    def test_default_binary(self):
        self.assertEqual(ClaudeCodeAdapter().binary, "claude")

    def test_capabilities_complete(self):
        caps = ClaudeCodeAdapter().capabilities()
        for c in Capability:
            self.assertIn(c, caps)


class TestClaudeCodeBuildCommand(unittest.TestCase):
    def test_minimal(self):
        cmd = ClaudeCodeAdapter().build_command(_spec())
        self.assertTrue(cmd[0].endswith("claude"), cmd[0])   # resolved path on Windows
        self.assertIn("-p", cmd)
        self.assertNotIn("test", cmd, "prompt đi qua stdin, không qua dòng lệnh")
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", cmd)
        self.assertIn("--permission-mode", cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], PERMISSION_MODE)
        self.assertIn("--setting-sources", cmd)
        self.assertIn("--strict-mcp-config", cmd)

    def test_default_tools(self):
        cmd = ClaudeCodeAdapter().build_command(_spec())
        idx = cmd.index("--allowed-tools")
        tools = cmd[idx + 1 : idx + 1 + len(DEFAULT_TOOLS)]
        self.assertEqual(tuple(tools), DEFAULT_TOOLS)

    def test_with_model(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(model="opus"))
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")

    def test_with_system_prompt(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(system_prompt="be nice"))
        self.assertIn("--append-system-prompt", cmd)
        self.assertEqual(cmd[cmd.index("--append-system-prompt") + 1], "be nice")

    def test_no_system_prompt(self):
        cmd = ClaudeCodeAdapter().build_command(_spec())
        self.assertNotIn("--append-system-prompt", cmd)

    def test_with_max_turns(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(max_turns=5))
        self.assertIn("--max-turns", cmd)
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "5")

    def test_with_settings_file(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(settings_file=Path("/s.json")))
        self.assertIn("--settings", cmd)
        self.assertEqual(cmd[cmd.index("--settings") + 1], str(Path("/s.json")))

    def test_allowed_tools_override(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(allowed_tools=["Read", "Bash"]))
        idx = cmd.index("--allowed-tools")
        self.assertEqual(cmd[idx + 1 : idx + 3], ["Read", "Bash"])

    def test_with_disallowed_tools(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(disallowed_tools=["Bash"]))
        self.assertIn("--disallowed-tools", cmd)
        self.assertEqual(cmd[cmd.index("--disallowed-tools") + 1], "Bash")

    def test_with_extra_dirs(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(extra_dirs=[Path("/a"), Path("/b")]))
        indices = [i for i, x in enumerate(cmd) if x == "--add-dir"]
        self.assertEqual(len(indices), 2)
        self.assertEqual(cmd[indices[0] + 1], str(Path("/a")))
        self.assertEqual(cmd[indices[1] + 1], str(Path("/b")))

    def test_with_session_id(self):
        cmd = ClaudeCodeAdapter().build_command(_spec(session_id="abc123"))
        self.assertIn("--session-id", cmd)
        self.assertEqual(cmd[cmd.index("--session-id") + 1], "abc123")


class TestOpenCodeId(unittest.TestCase):
    def test_id(self):
        self.assertEqual(OpenCodeAdapter().id, "opencode")

    def test_default_binary(self):
        self.assertEqual(OpenCodeAdapter().binary, "opencode")

    def test_capabilities_complete(self):
        caps = OpenCodeAdapter().capabilities()
        for c in Capability:
            self.assertIn(c, caps)


class TestOpenCodeBuildCommand(unittest.TestCase):
    def test_minimal(self):
        cmd = OpenCodeAdapter().build_command(_spec())
        self.assertTrue(cmd[0].endswith("opencode"), cmd[0])   # resolved path on Windows
        self.assertIn("run", cmd)
        self.assertIn("--format", cmd)
        self.assertEqual(cmd[cmd.index("--format") + 1], "json")
        self.assertIn("--dir", cmd)
        self.assertEqual(cmd[cmd.index("--dir") + 1], str(Path("/tmp/test")))
        self.assertNotIn("test", cmd[cmd.index("--dir") + 2:], "prompt đi qua stdin")

    def test_shim_nhieu_tu_khong_lam_lech_co(self):
        """Lỗi 59. Trên Windows `opencode` là shim `.cmd`, `resolve_binary`
        trả **ba** token (`cmd.exe /c <shim>`), nên `insert(2, "--format")`
        nhét cờ vào giữa tham số của chính `cmd.exe`: client được gọi là
        `cmd /c --format json opencode.cmd run …`. Hình dạng lỗi 32 lần nữa —
        một **lệnh** không phải một **từ**."""
        from unittest import mock

        from aisef.clients import opencode as oc

        with mock.patch.object(oc, "resolve_binary",
                               return_value=["cmd.exe", "/c", r"C:\x\opencode.cmd"]):
            cmd = OpenCodeAdapter().build_command(_spec())
        self.assertEqual(cmd[:3], ["cmd.exe", "/c", r"C:\x\opencode.cmd"])
        self.assertEqual(cmd[3], "run")
        self.assertEqual(cmd[cmd.index("--format") + 1], "json")
        self.assertGreater(cmd.index("--format"), 3, cmd)

    def test_with_model(self):
        cmd = OpenCodeAdapter().build_command(_spec(model="gpt-4"))
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-4")

    def test_no_model(self):
        cmd = OpenCodeAdapter().build_command(_spec())
        self.assertNotIn("--model", cmd)


class TestParseJsonEvents(unittest.TestCase):
    def test_text_events(self):
        lines = [
            '{"type":"text","part":{"text":"hello "}}',
            '{"type":"text","part":{"text":"world"}}',
        ]
        res = parse_json_events(lines)
        self.assertEqual(res.text, "hello world")

    def test_tool_use_name_mapping(self):
        for raw, expected in _TOOL_NAMES.items():
            line = f'{{"type":"tool_use","part":{{"tool":"{raw}","callID":"c1","state":{{"input":{{}}}}}}}}'
            res = parse_json_events([line])
            self.assertEqual(res.tool_uses[0].name, expected, f"mapping {raw}")

    def test_tool_use_unknown_name_passthrough(self):
        line = '{"type":"tool_use","part":{"tool":"CustomTool","callID":"c2","state":{"input":{"x":1}}}}'
        res = parse_json_events([line])
        self.assertEqual(res.tool_uses[0].name, "CustomTool")
        self.assertEqual(res.tool_uses[0].input, {"x": 1})

    def test_step_finish_accumulation(self):
        step = '{"type":"step_finish","part":{"tokens":{"input":100,"output":50,"cache":{"read":10,"write":5}},"cost":0.01}}'
        res = parse_json_events([step, step])
        self.assertEqual(res.num_turns, 2)
        self.assertEqual(res.input_tokens, 200)
        self.assertEqual(res.output_tokens, 100)
        self.assertEqual(res.cache_read_tokens, 20)
        self.assertEqual(res.cache_creation_tokens, 10)
        self.assertAlmostEqual(res.cost_usd, 0.02)

    def test_non_json_skipped(self):
        lines = ["banner text", "WARNING: something", '{"type":"text","part":{"text":"ok"}}']
        res = parse_json_events(lines)
        self.assertEqual(res.text, "ok")

    def test_empty_input(self):
        res = parse_json_events([])
        self.assertEqual(res.text, "")
        self.assertEqual(res.num_turns, 0)
        self.assertEqual(res.tool_uses, [])

    def test_session_id_picked_up(self):
        line = '{"type":"text","part":{"text":"hi"},"sessionID":"sess-42"}'
        res = parse_json_events([line])
        self.assertEqual(res.session_id, "sess-42")

    def test_guard_message_on_error(self):
        line = ('{"type":"tool_use","part":{"tool":"bash","callID":"c1","state":'
                '{"input":{},"status":"error","output":'
                '"aisef guard write-scope: src/x.py is outside the story scope"}}}')
        res = parse_json_events([line])
        self.assertIn("outside the story scope", res.guard_messages[0])
        self.assertTrue(res.guard_blocked)

    def test_a_plain_tool_error_is_not_a_guard_block(self):
        """Lỗi 100: mọi lỗi công cụ đều rơi vào `guard_messages`, mà
        `guard_blocked` có nghĩa "agent định làm việc bị cấm". Một tệp không
        tồn tại đủ để báo cáo nghiệm thu ghi một lần guard chặn không hề xảy
        ra — đúng thứ mà docstring của `GUARD_MESSAGE` dặn phải tránh."""
        line = ('{"type":"tool_use","part":{"tool":"read","callID":"c1","state":'
                '{"input":{},"status":"error","output":"File not found: /p/index.html"}}}')
        res = parse_json_events([line])
        self.assertEqual(res.guard_messages, [])
        self.assertFalse(res.guard_blocked)

    def test_stale_plugin_message_still_reads_as_a_guard(self):
        """Plugin cũ (chưa `aisef compile` lại) ném câu của chính nó."""
        line = ('{"type":"tool_use","part":{"tool":"write","callID":"c1","state":'
                '{"input":{},"status":"error","output":'
                '"guard write-scope could not run (exit 127): no output"}}}')
        self.assertTrue(parse_json_events([line]).guard_blocked)


if __name__ == "__main__":
    unittest.main()
