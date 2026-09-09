"""Kiểm chứng biên dịch cấu hình client."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.compile import (  # noqa: E402
    ADAPTERS,
    build_claude_settings,
    build_opencode_plugin,
    compile_for,
    write_compile_report,
)
from aisef.harness.guardrails import GUARD_MATCHERS  # noqa: E402


class CompileTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestClaudeSettings(CompileTestCase):
    def settings(self) -> dict:
        return build_claude_settings(self.project, "/usr/local/bin/aisef")

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
        self.assertIn("do not edit", self.settings()["_generated"])


class TestOpenCodePlugin(CompileTestCase):
    def test_calls_every_tool_guard_at_its_own_moment(self):
        """Guard theo mốc, không đổ hết vào `tool.execute.before`.

        `completion` hỏi "test đã xanh cho đoạn code hiện tại chưa" — hỏi
        trước **mỗi** thao tác thì nó chặn cả lần chạy test đầu tiên, và
        một guard chặn mọi thứ sẽ bị gỡ ngay trong ngày.
        """
        src = build_opencode_plugin(self.project, "/bin/aisef")
        before = src.split("const AFTER")[0]
        after = src.split("const AFTER")[1].split("const BIN")[0]
        for kind, (event, _) in GUARD_MATCHERS.items():
            if event == "PreToolUse":
                self.assertIn(f'"{kind}"', before, kind)
            elif event == "PostToolUse":
                self.assertIn(f'"{kind}"', after, kind)
            else:
                self.assertNotIn(f'"{kind}"', src, kind)

    def test_post_tool_guard_wired(self):
        self.assertIn("tool.execute.after", build_opencode_plugin(self.project, "/bin/aisef"))

    def test_treats_exit_two_as_block(self):
        """Cùng quy ước mã thoát với Claude Code."""
        self.assertIn("exitCode === 2", build_opencode_plugin(self.project, "/bin/aisef"))

    def test_lenh_aisef_la_mang_khong_phai_chuoi(self):
        """Lỗi 32. `aisef_command()` lùi về `"<python> -m aisef.cli"` khi
        `aisef` không nằm trên PATH (cài trong venv). Bun shell trích dẫn
        một chuỗi nội suy thành **một** argv[0], nên tên chương trình thành
        một đường dẫn có dấu cách: `bun: command not found`, `.nothrow()`
        nuốt lỗi, và **mọi guard im lặng không chạy**.

        Đo 2026-09-09 trên `todo`, cùng một phiên OpenCode, cùng một hook:
        dạng chuỗi exit=1, dạng mảng exit=0. Cả run 46 phiên không có lấy
        một sự kiện guard nào, story trượt cổng `guard ran` tới cạn lượt.
        """
        src = build_opencode_plugin(
            self.project, ["/Users/x/.venvs/aisef/bin/python3.14", "-m", "aisef.cli"])
        dong = next(d for d in src.splitlines() if d.startswith("const BIN"))
        self.assertEqual(
            dong,
            'const BIN = ["/Users/x/.venvs/aisef/bin/python3.14", "-m", "aisef.cli"]',
            "lệnh nhiều từ phải thành mảng, không thì Bun coi cả câu là tên tệp")
        self.assertIn("${BIN} --project", src)

    def test_hook_claude_khong_boc_ca_cau_lenh_thanh_mot_tu(self):
        """Cùng gốc lỗi 32, phía Claude Code: `shlex.quote` bọc cả
        `"<python> -m aisef.cli"` thành một token, shell đi tìm một tệp có
        dấu cách trong tên. Hook trả mã khác 2 ⇒ Claude cho qua."""
        from aisef.clients.compile import build_claude_settings
        import json as _json
        s = _json.dumps(build_claude_settings(
            self.project, ["/Users/x/.venvs/aisef/bin/python", "-m", "aisef.cli"]))
        self.assertIn("/Users/x/.venvs/aisef/bin/python -m aisef.cli --project", s)
        self.assertNotIn("'/Users/x/.venvs/aisef/bin/python -m aisef.cli'", s)

    def test_guard_khong_chay_duoc_thi_chan(self):
        """Mã thoát khác 0 và 2 nghĩa là guard **chưa** chấm thao tác này.
        Coi đó là cho qua chính là cách một lượt chạy kết thúc với zero
        guard mà bằng chứng trông y hệt một agent ngoan."""
        src = build_opencode_plugin(self.project, "/bin/aisef")
        self.assertIn("res.exitCode !== 0", src)
        than = src.split("res.exitCode !== 0")[1].split("}")[0]
        self.assertIn("throw", than, "guard hỏng mà không chặn thì bảo vệ chỉ là hình thức")

    def test_hooks_the_right_event(self):
        self.assertIn("tool.execute.before", build_opencode_plugin(self.project, "/bin/aisef"))

    def test_loc_tool_theo_dung_matcher_nhu_claude(self):
        """Lỗi 41. `settings.json` của Claude Code mang matcher, nên Claude
        chỉ gọi guard cho tool khớp. OpenCode không có cơ chế ấy — plugin
        phải tự lọc, nếu không thì **mọi guard chạy trên mọi tool**.

        Đo trên agent thật: `write-scope` chấm luôn `glob` (tham số
        `path: "."`), chặn một thao tác chỉ đọc, và agent kẹt cả lượt.
        """
        src = build_opencode_plugin(self.project, "/bin/aisef")
        for kind, (_, matcher) in GUARD_MATCHERS.items():
            if matcher:
                self.assertIn(f'"{kind}": /^({matcher})$/i', src, kind)
        self.assertIn("if (!MATCH[kind]?.test(tool ?? \"\")) continue", src)

    def test_matcher_co_neo_hai_dau_va_khong_phan_biet_hoa_thuong(self):
        """Tên tool của OpenCode viết thường (`write`, `bash`) nên phải bỏ
        phân biệt hoa thường; và phải neo hai đầu, nếu không `todowrite`
        cũng dính vào `Write`."""
        src = build_opencode_plugin(self.project, "/bin/aisef")
        dong = next(d for d in src.splitlines() if d.startswith("const MATCH"))
        import re as _re
        mau = _re.findall(r"/\^\(([^)]+)\)\$/i", dong)
        self.assertEqual(len(mau), sum(1 for _, m in GUARD_MATCHERS.values() if m))
        for m in mau:
            with self.subTest(matcher=m):
                r = _re.compile(f"^({m})$", _re.I)
                self.assertIsNone(r.match("todowrite"))
                self.assertIsNone(r.match("glob"))
                self.assertIsNone(r.match("read"))

    def test_guard_chi_doc_khong_bi_chan(self):
        """Tool chỉ đọc không dính guard ghi — egress kiểm host nên khớp WebFetch là đúng."""
        src = build_opencode_plugin(self.project, "/bin/aisef")
        dong = next(d for d in src.splitlines() if d.startswith("const MATCH"))
        import re as _re
        matchers = _re.findall(r"/\^\(([^)]+)\)\$/i", dong)
        egress_matcher = "WebFetch|Bash"
        non_egress = [m for m in matchers if m != egress_matcher]
        for tool in ("glob", "grep", "read", "webfetch", "todowrite"):
            for m in non_egress:
                with self.subTest(tool=tool, matcher=m):
                    self.assertIsNone(_re.compile(f"^({m})$", _re.I).match(tool))

    def test_khong_goi_stdin_nhu_mot_ham(self):
        """Lỗi 39. `$` của OpenCode là Bun shell: `BunShellPromise.stdin` là
        một `WritableStream` **chỉ đọc**, không phải hàm.

        Bản sinh cũ gọi `.stdin(event)` → mọi lần gọi tool đều ném
        TypeError. Nhìn từ ngoài giống guard đang chặn; thật ra guard chưa
        chạy lần nào, và OpenCode không hiện thực nổi một story.
        """
        src = build_opencode_plugin(self.project, "/bin/aisef")
        ma = "\n".join(d for d in src.splitlines() if not d.lstrip().startswith("//"))
        self.assertNotIn(".stdin(", ma)
        self.assertIn("< ${input}", ma)

    def test_gui_cwd_cua_phien_khong_phai_goc_du_an(self):
        """Lỗi 15, phiên bản OpenCode. Agent chạy story đứng trong
        `.aisef/worktrees/<story>`; guard soi gốc dự án sẽ thấy toàn bộ
        file kế hoạch là "ghi ngoài phạm vi" và chặn sạch mọi thao tác."""
        src = build_opencode_plugin(self.project, "/bin/aisef")
        self.assertIn("cwd: CWD", src)
        self.assertIn("directory || worktree || PROJECT", src)
        # cả hai mốc đều phải gửi, không chỉ mốc trước.
        self.assertEqual(src.count("cwd: CWD"), 2)


class TestCompileFor(CompileTestCase):
    def test_claude_writes_settings(self):
        r = compile_for("claude", self.project)
        self.assertTrue((self.project / ".claude" / "settings.json").is_file())
        self.assertEqual(r.client, "claude")

    def test_opencode_writes_plugin(self):
        compile_for("opencode", self.project)
        self.assertTrue((self.project / ".opencode" / "plugin" / "aisef-guard.ts").is_file())

    def test_claude_blocks_at_source(self):
        self.assertTrue(compile_for("claude", self.project).blocks_at_source)

    def test_opencode_chan_tai_nguon_sau_khi_da_chung_minh(self):
        """Khai `NATIVE` ngày 2026-09-05, có hai phép thử trên agent thật:
        `rm -rf` không xoá được tệp, và `Write` chứa `os.system` ghép chuỗi
        không để lại tệp nào. Xem docstring `clients/opencode.py`."""
        r = compile_for("opencode", self.project)
        self.assertTrue(r.blocks_at_source)
        self.assertEqual(r.guards_post_hoc, [])
        self.assertEqual(sorted(r.guards_wired), sorted(GUARD_MATCHERS))

    def test_opencode_van_bao_cac_muc_thuc_su_kem(self):
        """Chặn được không có nghĩa là ngang Claude Code: OpenCode vẫn
        không giới hạn được số lượt và không phát luồng sự kiện."""
        r = compile_for("opencode", self.project)
        self.assertFalse(any("pre_tool_guard" in d for d in r.degradations))
        self.assertTrue(any("turn_limit" in d for d in r.degradations))
        # 2026-09-05: `--format json` đo được → machine_output NATIVE; chỗ kém còn
        # lại là tool_allowlist (giả lập bằng guard), và đó vẫn phải được khai.
        self.assertFalse(any("machine_output" in d for d in r.degradations), r.degradations)
        self.assertTrue(any("tool_allowlist" in d for d in r.degradations), r.degradations)

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
        """Không còn guard hậu kiểm thì đừng doạ người bằng chữ "hậu kiểm";
        nhưng các mục kém thật vẫn phải nêu tên."""
        r = compile_for("opencode", self.project)
        self.assertNotIn("hậu kiểm", r.summary())
        self.assertIn("turn_limit", r.summary())


class TestCompileReport(CompileTestCase):
    def test_report_records_assurance_level(self):
        reports = [compile_for(c, self.project) for c in sorted(ADAPTERS)]
        path = write_compile_report(self.project, reports)
        data = json.loads(path.read_text(encoding="utf-8"))

        by_client = {c["client"]: c for c in data["clients"]}
        self.assertTrue(by_client["claude"]["blocks_at_source"])
        self.assertTrue(by_client["opencode"]["blocks_at_source"])

    def test_report_lists_written_files(self):
        path = write_compile_report(self.project, [compile_for("claude", self.project)])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(".claude/settings.json", data["clients"][0]["written"])


class TestGuardCommandInjection(CompileTestCase):
    """The hook command is a **string** a shell will split. Whatever the path
    contains, that shell must hand the guard back exactly the argv we meant —
    not a second argument, and not a second command."""

    def _argv(self, aisef_bin, project: str) -> list[str]:
        from aisef.clients.base import split_command
        from aisef.clients.compile import _guard_command
        return split_command(_guard_command(aisef_bin, Path(project), "write-scope"))

    def _expect(self, aisef_bin, project: str) -> list[str]:
        binary = [aisef_bin] if isinstance(aisef_bin, str) else list(aisef_bin)
        return [*binary, "--project", str(Path(project)), "guard", "write-scope"]

    def test_space_in_project_path(self):
        self.assertEqual(self._argv("aisef", "/tmp/my project"),
                         self._expect("aisef", "/tmp/my project"))

    def test_quote_in_project_path(self):
        self.assertEqual(self._argv("aisef", "/tmp/it's here"),
                         self._expect("aisef", "/tmp/it's here"))

    def test_shell_metachar_in_project_path(self):
        from aisef.clients.compile import _guard_command
        raw = _guard_command("aisef", Path("/tmp/$(whoami)"), "write-scope")
        # Quoted, not merely present: bare, the shell would run `whoami`.
        self.assertNotIn(f" {Path('/tmp/$(whoami)')} ", raw)
        self.assertEqual(self._argv("aisef", "/tmp/$(whoami)"),
                         self._expect("aisef", "/tmp/$(whoami)"))

    def test_space_in_aisef_bin(self):
        self.assertEqual(self._argv("/opt/my tools/aisef", "/tmp/p"),
                         self._expect("/opt/my tools/aisef", "/tmp/p"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
