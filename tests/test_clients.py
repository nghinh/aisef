"""Kiểm chứng adapter client và bảng khai báo năng lực."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients import base  # noqa: E402
from aisef.clients.base import Capability, RunSpec, Support  # noqa: E402
from aisef.clients.claude_code import ClaudeCodeAdapter  # noqa: E402
from aisef.clients.opencode import OpenCodeAdapter, parse_json_events  # noqa: E402
from aisef.clients.stream import exit_status_of  # noqa: E402

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

    def test_opencode_chan_that_da_co_phep_thu(self):
        """Nâng POST_HOC → NATIVE ngày 2026-09-05.

        Hai phép thử trên agent thật (opencode 1.18.26, `9router/mycombo`),
        agent đứng trong thư mục con của dự án:
        - `rm -rf <thư mục có tệp>`: tool báo failed bằng stderr của guard,
          tệp **vẫn còn** → chặn trước, không phải phát hiện sau;
        - `Write ping.py` chứa `os.system(f"... {host}")`: tool báo failed,
          **không có tệp nào** ra đĩa.

        Phép thử đầu tiên tôi làm (ghi khoá API) là vô giá trị: model tự từ
        chối trước khi gọi tool, nên nó chứng minh model ngoan chứ không
        chứng minh guard chặn.
        """
        oc = OpenCodeAdapter()
        self.assertIs(oc.supports(Capability.PRE_TOOL_GUARD), Support.NATIVE)
        self.assertTrue(oc.guards_block_at_source())

    def test_degradations_are_reported(self):
        """Chặn được rồi thì không kê `pre_tool_guard` vào danh sách kém
        nữa — nhưng những mục kém thật vẫn phải nêu."""
        degradations = OpenCodeAdapter().degradations()
        self.assertFalse(any("pre_tool_guard" in d for d in degradations))
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

    def test_isolated_from_user_config(self):
        """Đo 2026-09-05: `defaultMode: auto` toàn cục làm phiên con mất
        Glob/Grep và né guard bằng Bash; MCP + hook người dùng lọt vào."""
        cmd = self.a.build_command(self.spec())
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "project,local")
        self.assertIn("--strict-mcp-config", cmd)
        tools = cmd[cmd.index("--allowed-tools") + 1:]
        for t in ("Glob", "Grep", "Bash", "Write"):
            self.assertIn(t, tools)

    def test_explicit_allowlist_replaces_default(self):
        cmd = self.a.build_command(self.spec(allowed_tools=["Read"]))
        self.assertEqual(cmd[cmd.index("--allowed-tools") + 1], "Read")
        self.assertNotIn("Bash", cmd)


class TestGiaiTenLenh(unittest.TestCase):
    """Lỗi 33. `CreateProcess` không tra `PATHEXT` và không chạy được shim
    `.cmd` mà npm/bun cài — gọi tên trần trên Windows là `WinError 2` dù CLI
    có cài và `shutil.which` tìm thấy."""

    def test_khong_cai_thi_rong(self):
        from unittest import mock
        from aisef.clients.base import resolve_binary
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(resolve_binary("opencode"), [])

    def test_posix_dung_duong_dan_da_giai(self):
        from unittest import mock
        from aisef.clients.base import resolve_binary
        with mock.patch("shutil.which", return_value="/usr/local/bin/opencode"), \
             mock.patch("aisef.clients.base.sys.platform", "linux"):
            self.assertEqual(resolve_binary("opencode"), ["/usr/local/bin/opencode"])

    def test_windows_shim_cmd_chay_qua_cmd_exe(self):
        from unittest import mock
        from aisef.clients.base import resolve_binary
        with mock.patch("shutil.which", return_value=r"C:\npm\opencode.cmd"), \
             mock.patch("aisef.clients.base.sys.platform", "win32"), \
             mock.patch.dict("os.environ", {"COMSPEC": r"C:\Windows\cmd.exe"}):
            self.assertEqual(resolve_binary("opencode"),
                             [r"C:\Windows\cmd.exe", "/c", r"C:\npm\opencode.cmd"])

    def test_windows_exe_khong_can_boc(self):
        from unittest import mock
        from aisef.clients.base import resolve_binary
        with mock.patch("shutil.which", return_value=r"C:\bin\opencode.exe"), \
             mock.patch("aisef.clients.base.sys.platform", "win32"):
            self.assertEqual(resolve_binary("opencode"), [r"C:\bin\opencode.exe"])


class TestLenhDuAnChayDuocTrenWindows(unittest.TestCase):
    """Lỗi 45. Lệnh của dự án — `npm test`, `npm run lint`, `npm audit` — trên
    Windows là shim `.cmd`: `CreateProcess` không chạy được, `subprocess` cũng
    không tra `PATHEXT`. Mọi lệnh trả `[WinError 2]`, exit 127, và harness báo
    "tool not installed" trên máy có npm cài đủ và chạy tốt (báo 2026-09-09).
    Cùng gốc lỗi 33, một tầng sâu hơn: lần ấy sửa cho CLI của client, lần này
    cho lệnh của dự án."""

    def test_shim_cmd_duoc_boc_qua_cmd_exe(self):
        from unittest import mock
        from aisef.clients.base import runnable
        with mock.patch("shutil.which", return_value=r"C:\npm\npm.cmd"), \
             mock.patch("aisef.clients.base.sys.platform", "win32"), \
             mock.patch.dict("os.environ", {"COMSPEC": r"C:\Windows\cmd.exe"}):
            self.assertEqual(runnable(["npm", "test"]),
                             [r"C:\Windows\cmd.exe", "/c", r"C:\npm\npm.cmd", "test"])

    def test_posix_giu_nguyen_tham_so(self):
        from unittest import mock
        from aisef.clients.base import runnable
        with mock.patch("shutil.which", return_value="/usr/bin/npm"), \
             mock.patch("aisef.clients.base.sys.platform", "linux"):
            self.assertEqual(runnable(["npm", "run", "lint"]), ["/usr/bin/npm", "run", "lint"])

    def test_khong_tim_thay_thi_giu_nguyen_de_bao_loi_that(self):
        from unittest import mock
        from aisef.clients.base import runnable
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(runnable(["khong-co-lenh-nay", "-v"]), ["khong-co-lenh-nay", "-v"])
        self.assertEqual(runnable([]), [])


class TestOpenCodeCommand(unittest.TestCase):
    def test_run_subcommand(self):
        cmd = OpenCodeAdapter().build_command(RunSpec(prompt="xin chào", workdir=Path(".")))
        self.assertEqual(cmd[1], "run")

    def test_prompt_di_qua_stdin_khong_qua_dong_lenh(self):
        """Lỗi 33. Windows chặn dòng lệnh dài quá 32767 ký tự, mà riêng
        prompt lập kế hoạch đã 16–23k (`WinError 206`, người dùng báo
        2026-09-09). Prompt đi qua stdin — đo 2026-09-09: cả hai CLI đọc
        prompt từ stdin khi không có tham số vị trí."""
        for a in (OpenCodeAdapter(), ClaudeCodeAdapter()):
            with self.subTest(client=a.id):
                cmd = a.build_command(RunSpec(prompt="X" * 40_000, workdir=Path(".")))
                self.assertNotIn("X" * 40_000, cmd)
                self.assertLess(sum(len(c) for c in cmd), 32_767,
                                "dòng lệnh vẫn vượt giới hạn của Windows")

    def test_model_flag(self):
        cmd = OpenCodeAdapter().build_command(
            RunSpec(prompt="p", workdir=Path("."), model="anthropic/x")
        )
        self.assertIn("--model", cmd)

    def test_bao_thang_cay_lam_viec_cho_opencode(self):
        """Lỗi 40. `cwd=` của tiến trình con là **không đủ**: OpenCode dò
        gốc dự án riêng, thấy worktree nằm trong `<dự án>/.aisef/`, đi
        ngược lên tới gốc dự án rồi nói với model rằng đó là nơi làm việc.

        Model sau đó đọc/ghi bằng đường dẫn tuyệt đối vào gốc dự án và đặt
        `workdir` cho từng lệnh bash ở đó — công việc rơi thẳng lên thân
        cây trong khi worktree vẫn trống. Đã tái hiện ba lần trên `par`.
        """
        wt = Path("/du/an/.aisef/worktrees/STORY-01-01")
        cmd = OpenCodeAdapter().build_command(RunSpec(prompt="p", workdir=wt))
        self.assertIn("--dir", cmd)
        self.assertEqual(cmd[cmd.index("--dir") + 1], str(wt))


class TestGuardRails(unittest.TestCase):
    def test_missing_binary_returns_error_not_crash(self):
        a = ClaudeCodeAdapter(binary="lenh-khong-ton-tai-12345")
        r = a.run(RunSpec(prompt="p", workdir=Path(".")))
        self.assertFalse(r.ok)
        self.assertIn("command not found", r.error)

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
            from tests._bin import sleeps
            fake = sleeps(Path(d) / "cham-chap", 5)

            r = ClaudeCodeAdapter(binary=str(fake)).run(
                RunSpec(prompt="p", workdir=Path(d), timeout_seconds=1)
            )
        self.assertFalse(r.ok)
        self.assertIn("exceeded 1s", r.error)


class TestTimeoutCapturesPartialStream(unittest.TestCase):
    """When a client is killed on wall-clock deadline, the harness must
    retain whatever stdout it produced **before** the kill — the cost/turn
    signal lives in the last event, and a late timeout used to wipe it.

    The previous ``proc.communicate(timeout=)`` call buffered stdout in the
    pipe until kill; the drain-capturing version keeps a reader thread
    alive from Popen start, so lines are captured up to the millisecond.
    """

    def test_claude_keeps_result_event_before_timeout(self):
        """Result event written before timeout → cost_usd survives."""
        # A Claude Code stream emits `{"type":"result","total_cost_usd":0.42, ...}`
        # on its last line.  Emit one, then block past the deadline.
        if sys.platform == "win32":
            self.skipTest("emits_then_sleeps fixture is POSIX-only")
        from tests._bin import emits_then_sleeps
        result_line = '{"type":"result","total_cost_usd":0.42,"num_turns":3,"text":"x"}'
        with tempfile.TemporaryDirectory() as d:
            fake = emits_then_sleeps(
                Path(d) / "claude-fake",
                prefix_lines=[result_line],
                sleep_seconds=5,
            )
            r = ClaudeCodeAdapter(binary=str(fake)).run(
                RunSpec(prompt="p", workdir=Path(d), timeout_seconds=1)
            )
        # Infrastructure: timeout fired.
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "exceeded 1s")
        # Signal preserved: cost and turn count arrive from the captured line.
        self.assertAlmostEqual(r.cost_usd, 0.42, places=3)
        self.assertEqual(r.num_turns, 3)

    def test_opencode_keeps_step_finish_before_timeout(self):
        """OpenCode's `step_finish` carries tokens + cost; same drain logic."""
        if sys.platform == "win32":
            self.skipTest("emits_then_sleeps fixture is POSIX-only")
        from tests._bin import emits_then_sleeps
        finish = '{"type":"step_finish","part":{"tokens":{"input":10,"output":7,"cache":{"read":0,"write":0}},"cost":0.07}}'
        with tempfile.TemporaryDirectory() as d:
            fake = emits_then_sleeps(
                Path(d) / "opencode-fake",
                prefix_lines=[finish],
                sleep_seconds=5,
            )
            r = OpenCodeAdapter(binary=str(fake)).run(
                RunSpec(prompt="p", workdir=Path(d), timeout_seconds=1)
            )
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "exceeded 1s")
        # `parse_json_events` accumulates cost + tokens from step_finish.
        self.assertAlmostEqual(r.cost_usd, 0.07, places=3)
        self.assertEqual(r.num_turns, 1)
        self.assertEqual(r.input_tokens, 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestKhongThuaHuongPhienCha(unittest.TestCase):
    """Hợp quy C3: phiên con thừa hưởng `CLAUDE*` của phiên cha thì tự chuyển
    sang Bash. Từ ADR-005 V2 môi trường con là **allowlist** (`child_env`):
    không chỉ `CLAUDE*` mà mọi biến ngoài danh sách đều vắng (hợp quy C9)."""

    def test_claude_vars_are_dropped_but_anthropic_kept(self):
        import os
        from unittest import mock
        from aisef.clients.base import child_env
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x", "ANTHROPIC_API_KEY": "k"}):
            env = child_env({})
        self.assertNotIn("CLAUDECODE", env)
        self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "k")

    def test_bien_ngoai_allowlist_vang_bien_trong_thi_co(self):
        import os
        from unittest import mock
        from aisef.clients.base import ENV_KEEP, child_env
        may = {"NGHI_CANARY_TOKEN": "bí mật", "FAKE_SECRET_TOKEN": "x", "NINEROUTER_API_KEY": "k9",
               "PATH": "/bin", "HOME": "/h", "LC_ALL": "C", "ANTHROPIC_BASE_URL": "u", "AISEF_PROJECT": "/p"}
        with mock.patch.dict(os.environ, may, clear=True):
            env = child_env({"AISEF_STORY_ID": "S"})
        for k in ("NGHI_CANARY_TOKEN", "FAKE_SECRET_TOKEN", "NINEROUTER_API_KEY"):
            self.assertNotIn(k, env)
        for k in ("PATH", "HOME", "LC_ALL", "ANTHROPIC_BASE_URL", "AISEF_PROJECT", "AISEF_STORY_ID"):
            self.assertIn(k, env)
        self.assertIn("SSL_CERT_FILE", ENV_KEEP)

    def test_tien_to_cau_hinh_duoc_qua_tien_to_rong_khong_mo_toang(self):
        import os
        from unittest import mock
        from aisef.clients.base import child_env
        may = {"NINEROUTER_API_KEY": "k9", "NGHI_CANARY_TOKEN": "x", "PATH": "/bin"}
        with mock.patch.dict(os.environ, may, clear=True):
            co = child_env({}, allow_prefixes=["NINEROUTER_"])
            rong = child_env({}, allow_prefixes=[""])
        self.assertEqual(co.get("NINEROUTER_API_KEY"), "k9")
        self.assertNotIn("NGHI_CANARY_TOKEN", co)
        self.assertNotIn("NGHI_CANARY_TOKEN", rong, "tiền tố rỗng không được mở mọi biến")

    def test_git_khong_hoi_credential_va_harness_khong_bi_lay(self):
        import os
        from aisef.clients.base import GIT_NO_CREDENTIALS, child_env
        env = child_env({})
        for k, v in GIT_NO_CREDENTIALS.items():
            self.assertEqual(env.get(k), v, k)
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "credential.helper")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], "")
        # Bộ này chỉ vào tiến trình client; git của harness (`worktree._git`,
        # không truyền `env=`) đọc `os.environ` — không được bị đổi.
        self.assertNotIn("GIT_CONFIG_COUNT", os.environ)

    def _fake(self, tmp):
        from pathlib import Path
        fake = Path(tmp) / "client-gia"
        from tests._bin import dump_env
        return dump_env(fake, Path(tmp) / "env.txt")

    def test_child_process_really_gets_the_clean_env(self):
        import os, tempfile
        from pathlib import Path
        from unittest import mock
        from aisef.clients.base import RunSpec
        from aisef.clients.claude_code import ClaudeCodeAdapter
        from aisef.clients.opencode import OpenCodeAdapter
        for adapter in (ClaudeCodeAdapter, OpenCodeAdapter):
            with self.subTest(client=adapter.id), tempfile.TemporaryDirectory() as tmp:
                a = adapter(binary=str(self._fake(tmp)))
                with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "NGHI_CANARY_TOKEN": "bí mật",
                                                  "NINEROUTER_API_KEY": "k9"}):
                    a.run(RunSpec(prompt="x", workdir=Path(tmp), env={"AISEF_STORY_ID": "S"}))
                    a.run(RunSpec(prompt="x", workdir=Path(tmp), env={"AISEF_STORY_ID": "S"},
                                  env_allow=["NINEROUTER_"]))
                    khai = (Path(tmp) / "env.txt").read_text(encoding="utf-8")
                    a.run(RunSpec(prompt="x", workdir=Path(tmp), env={"AISEF_STORY_ID": "S"}))
                    got = (Path(tmp) / "env.txt").read_text(encoding="utf-8")
                self.assertNotIn("CLAUDECODE=", got)
                self.assertNotIn("NGHI_CANARY_TOKEN=", got)
                self.assertNotIn("NINEROUTER_API_KEY=", got)
                self.assertIn("AISEF_STORY_ID=S", got)
                self.assertIn("GIT_TERMINAL_PROMPT=0", got)
                self.assertIn("NINEROUTER_API_KEY=k9", khai, "`env_allow` của spec phải tới tiến trình")

    def test_build_spec_mang_env_allow_tu_cau_hinh(self):
        from pathlib import Path
        from aisef.config import DEFAULTS, Config
        from aisef.harness.prompts import Prompt
        from aisef.harness.routing import ROLES, DEVELOPER, build_spec
        cfg = Config({**DEFAULTS, "clients.env_allow": ["NINEROUTER_"]})
        role = ROLES[DEVELOPER]
        prompt = Prompt(name=role.prompt, version=1, role=DEVELOPER, body="x")
        spec = build_spec(DEVELOPER, prompt, {}, workdir=Path("."), config=cfg)
        self.assertEqual(spec.env_allow, ["NINEROUTER_"])
        self.assertEqual(DEFAULTS["clients.env_allow"], [])


class TestGitKhongCamCredentialCuaMay(unittest.TestCase):
    """ADR-005 V2, phần git. Remote giả trả 401 và ghi lại yêu cầu có mang
    `Authorization` không; helper `store` được gieo sẵn token cho remote ấy.
    Env thường: git gửi token (đối chứng — fixture *có thể* lộ). Env con
    (`GIT_NO_CREDENTIALS`): helper không được hỏi, push thất bại vì auth."""

    def test_env_con_khong_gui_token_env_thuong_thi_gui(self):
        import os, subprocess, tempfile
        from pathlib import Path
        from unittest import mock
        from aisef.clients.base import child_env
        from tests.conformance._runner import seed_fake_credential, start_fake_remote
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "r"
            repo.mkdir()
            # HOME riêng + không đọc config hệ thống: không đụng osxkeychain của máy.
            # Trên Windows, "môi trường tối thiểu" vẫn phải có SystemRoot/PATHEXT
            # — thiếu chúng thì git không mở nổi socket, hỏng **trước** khi kịp
            # hỏi credential helper, và phép đối chứng đo nhầm.
            from aisef.clients.base import ENV_KEEP
            base = {k: v for k, v in os.environ.items()
                    if k.upper() in ENV_KEEP and k.upper() not in ("HOME", "PATH")}
            # `GIT_CONFIG_GLOBAL`, not just `HOME`: on Windows git also reads
            # the global config from `%USERPROFILE%`, and the runner's global
            # config sets `credential.helper=manager` — which never consults
            # the store file this fixture seeds.
            base.update({"PATH": os.environ["PATH"], "HOME": d,
                         "GIT_CONFIG_NOSYSTEM": "1",
                         "GIT_CONFIG_GLOBAL": str(Path(d) / "gitconfig")})
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, env=base, check=True)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                            "--allow-empty", "-m", "x"], cwd=repo, env=base, check=True)
            srv, url = start_fake_remote()
            try:
                seed_fake_credential(repo, url)
                doi_chung = subprocess.run(["git", "push", url, "HEAD"], cwd=repo, env=base,
                                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                self.assertNotEqual(doi_chung.returncode, 0)
                self.assertTrue(
                    any(srv.seen),
                    "đối chứng: helper `store` phải gửi token, không thì fixture vô nghĩa. "
                    f"requests={srv.seen!r} rc={doi_chung.returncode} "
                    f"stderr={doi_chung.stderr.strip()[-600:]!r}")
                srv.seen.clear()

                with mock.patch.dict(os.environ, base, clear=True):
                    env = child_env({})
                con = subprocess.run(["git", "push", url, "HEAD"], cwd=repo, env=env,
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            finally:
                srv.shutdown()
                srv.server_close()
        self.assertNotEqual(con.returncode, 0)
        self.assertTrue(srv.seen, "push phải tới remote (thất bại vì auth, không phải vì mạng)")
        self.assertFalse(any(srv.seen), "env con: không yêu cầu nào được mang Authorization")
        self.assertIn("could not read Username", con.stderr)


class TestOpenCodeLuongJson(unittest.TestCase):
    """`opencode run --format json` (đo 2026-09-05): tool_use, tokens, cost, text."""

    LINES = [
        '{"type":"step_start","timestamp":1,"sessionID":"ses_1","part":{"type":"step-start"}}',
        '{"type":"tool_use","timestamp":2,"sessionID":"ses_1","part":{"type":"tool","tool":"read","callID":"call_1","state":{"status":"completed","input":{"filePath":"/p/package.json"},"output":"..."}}}',
        '{"type":"tool_use","timestamp":3,"sessionID":"ses_1","part":{"type":"tool","tool":"write","callID":"call_2","state":{"status":"error","input":{"filePath":"/p/x.py"},"output":"aisef guard injection: Write bị chặn"}}}',
        '{"type":"step_finish","timestamp":4,"sessionID":"ses_1","part":{"type":"step-finish","tokens":{"total":48888,"input":29851,"output":93,"reasoning":0,"cache":{"write":0,"read":18944}},"cost":0}}',
        'banner không phải json',
        '{"type":"text","timestamp":5,"sessionID":"ses_1","part":{"type":"text","text":"OK"}}',
        '{"type":"step_finish","timestamp":6,"sessionID":"ses_1","part":{"type":"step-finish","tokens":{"total":49066,"input":2469,"output":5,"reasoning":0,"cache":{"write":0,"read":46592}},"cost":0.0012}}',
    ]

    def test_parse(self):
        from aisef.clients.opencode import parse_json_events
        r = parse_json_events(self.LINES)
        self.assertEqual([t.name for t in r.tool_uses], ["Read", "Write"])
        self.assertEqual(r.tool_uses[0].input["filePath"], "/p/package.json")
        self.assertEqual(r.text, "OK")
        self.assertEqual(r.num_turns, 2)
        self.assertEqual((r.input_tokens, r.output_tokens, r.cache_read_tokens), (32320, 98, 65536))
        self.assertAlmostEqual(r.cost_usd, 0.0012)
        self.assertEqual(r.session_id, "ses_1")
        self.assertIn("injection", r.guard_messages[0])

    def test_command_has_json_format(self):
        cmd = OpenCodeAdapter().build_command(RunSpec(prompt="p", workdir=Path(".")))
        self.assertIn("--format", cmd)
        self.assertEqual(cmd[cmd.index("--format") + 1], "json")

    def test_capabilities_now_native(self):
        from aisef.clients.base import Capability, Support
        caps = OpenCodeAdapter().capabilities()
        self.assertIs(caps[Capability.MACHINE_OUTPUT], Support.NATIVE)
        self.assertIs(caps[Capability.COST_REPORTING], Support.NATIVE)


class TestLoiNhaCungCapPhaiNoiRa(unittest.TestCase):
    """Lỗi 48. OpenCode báo lỗi provider bằng một sự kiện JSON rồi thoát khác 0
    với stderr **rỗng**. Parser bỏ qua sự kiện ấy, nên harness ghi đúng một
    chữ `exit != 0`, còn lý do ("Bad Gateway", 502, retryable) nằm trong log
    riêng của OpenCode nơi không người vận hành nào ngó tới.

    Hệ quả nặng hơn cả việc khó đọc: `exit_status_of` không thấy dấu hiệu
    hạ tầng nên xếp là `error`, và giai đoạn kế hoạch **chết hẳn** vì một cú
    502 thoáng qua — trong khi vòng thử lại đã có sẵn cho đúng trường hợp này.
    Đo 2026-09-09 trên todo-e2e: `phase=project-context FAIL err=exit != 0`.
    """

    def _stream(self, **data):
        import json as _json
        from aisef.clients.opencode import parse_json_events
        return parse_json_events([_json.dumps(
            {"type": "error", "sessionID": "ses_1",
             "error": {"name": "APIError", "data": data}})])

    def test_thong_diep_va_ma_trang_thai_vao_ket_qua(self):
        r = self._stream(message="Bad Gateway", statusCode=502, isRetryable=True)
        self.assertIn("Bad Gateway", r.error)
        self.assertIn("502", r.error)

    def test_xep_la_ha_tang_de_duoc_thu_lai(self):
        from aisef.clients.stream import INFRA_STATUSES, exit_status_of
        r = self._stream(message="Bad Gateway", statusCode=502, isRetryable=True)
        r.ok = False
        self.assertIn(exit_status_of(r), INFRA_STATUSES)

    def test_retryable_khong_kem_ma_van_la_ha_tang(self):
        from aisef.clients.stream import INFRA_STATUSES, exit_status_of
        r = self._stream(message="upstream hiccup", isRetryable=True)
        r.ok = False
        self.assertIn(exit_status_of(r), INFRA_STATUSES)

    def test_loi_that_su_cua_ma_khong_bi_coi_la_ha_tang(self):
        from aisef.clients.stream import exit_status_of
        r = self._stream(message="tool refused by policy", statusCode=400)
        r.ok = False
        self.assertEqual(exit_status_of(r), "infra",
                         "400 vẫn là api_error_status — phân biệt sâu hơn là việc của bản sau")


class TestSplitCommand(unittest.TestCase):
    """Windows paths are backslashes; POSIX shlex ate them (bug 54)."""

    def test_posix_unchanged(self):
        with mock.patch.object(base.sys, "platform", "linux"):
            self.assertEqual(base.split_command("npm run lint"), ["npm", "run", "lint"])
            self.assertEqual(base.split_command("py -c 'a b'"), ["py", "-c", "a b"])

    def test_windows_keeps_backslashes(self):
        with mock.patch.object(base.sys, "platform", "win32"):
            self.assertEqual(
                base.split_command(r"C:\hostedtoolcache\Python\python.exe -c x"),
                [r"C:\hostedtoolcache\Python\python.exe", "-c", "x"],
            )

    def test_ghep_roi_tach_lai_ra_dung_argv(self):
        """Tính chất mà hook guard dựa vào: ghép argv thành một chuỗi rồi để
        shell của HĐH tách lại phải ra **đúng** argv ấy — dấu cách, nháy, hay
        ký tự đặc biệt của shell đều không được sinh thêm một tham số."""
        argv = ["aisef", "--project", "/tmp/my project", "guard", "write-scope"]
        for platform in ("linux", "win32"):
            with self.subTest(platform=platform), \
                 mock.patch.object(base.sys, "platform", platform):
                self.assertEqual(base.split_command(base.quote_command(argv)), argv)

    def test_ghep_khong_de_lot_ky_tu_dac_biet_cua_shell(self):
        for platform, argv in (("linux", ["aisef", "/tmp/$(whoami)"]),
                               ("win32", ["aisef", r"C:\tmp\a&b"])):
            with self.subTest(platform=platform), \
                 mock.patch.object(base.sys, "platform", platform):
                raw = base.quote_command(argv)
                self.assertNotIn(f" {argv[1]}", raw)      # không bao giờ để trần
                self.assertEqual(base.split_command(raw), argv)

    def test_windows_groups_with_double_quotes_only(self):
        with mock.patch.object(base.sys, "platform", "win32"):
            self.assertEqual(
                base.split_command(r'"C:\Program Files\node\npm.cmd" run "my test"'),
                [r"C:\Program Files\node\npm.cmd", "run", "my test"],
            )


class TestOpenCodeGhiLaiModelDaYeuCau(unittest.TestCase):
    """OpenCode không nói model nào đã trả lời — ghi cái đã yêu cầu, nói rõ là lời khai.

    Đo 2026-09-12: `opencode run --format json` phát ba loại sự kiện
    (`step_start`/`text`/`step_finish`) và **không** sự kiện nào mang
    `modelID`/`providerID`. Với alias định tuyến như `9router/mycombo` — đổi mô
    hình nền theo từng lần gọi — bỏ trống trường này làm cả đợt đo không so lại
    được với đợt sau.
    """

    def test_doc_khoa_model_tu_cau_hinh_du_an(self):
        from aisef.clients.opencode import configured_model
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "opencode.json").write_text('{"model": "9router/mycombo"}', encoding="utf-8")
            self.assertEqual(configured_model(Path(d)), "9router/mycombo")

    def test_khong_co_cau_hinh_thi_de_rong(self):
        from aisef.clients.opencode import configured_model
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": d}):
            self.assertEqual(configured_model(Path(d)), "")

    def test_chi_doc_khoa_model_chu_khong_mang_theo_bi_mat(self):
        """Tệp cấu hình của OpenCode chứa cả khoá API nhà cung cấp. Hàm này chỉ
        được trả về tên model — không trả, không ghi, không log gì khác."""
        from aisef.clients.opencode import configured_model
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "opencode.json").write_text(
                '{"model": "9router/mycombo", "provider": {"p": {"options": {"apiKey": "sk-BI-MAT"}}}}',
                encoding="utf-8")
            ra = configured_model(Path(d))
            self.assertEqual(ra, "9router/mycombo")
            self.assertNotIn("sk-", ra)

#: Con giả: in `step_finish` đều đặn cho tới khi bị giết. Đủ để đo trần lượt mà
#: không cần model thật.
_CON_STEP = (
    "import json, time\n"
    "for i in range(100):\n"
    "    print(json.dumps({'type': 'step_finish', 'part': {'tokens': {'input': 1}}})"
    ".replace(chr(39), chr(34)), flush=True)\n"
    "    time.sleep(0.1)\n"
)


class _OpenCodeGia(OpenCodeAdapter):
    """Adapter thật, lệnh giả — đo đúng đường đi của `run()`."""

    def __init__(self, ma: str):
        super().__init__()
        self._ma = ma

    def available(self) -> bool:
        return True

    def build_command(self, spec):
        return [sys.executable, "-c", self._ma]


class TestTranLuotDoAdapterThiHanh(unittest.TestCase):
    """OpenCode CLI không có cờ giới hạn lượt, nên `run.max_turns` chỉ có nghĩa
    nếu adapter tự đếm và tự dừng.

    Đo trên cohort C-1 khi chưa có phần này: khai trần 40, một phiên chạy **61**
    lượt và chỉ dừng vì đồng hồ 1800 s (`docs/BENCH-OBSERVATIONS-C1.md` § O-10).
    Trần theo thời gian không phải trần theo chi phí.
    """

    def test_cham_tran_thi_dung_tien_trinh_va_goi_ten_dung(self):
        import time as _t
        t = _t.monotonic()
        res = _OpenCodeGia(_CON_STEP).run(
            RunSpec(prompt="x", workdir=".", max_turns=5, timeout_seconds=60))
        self.assertFalse(res.ok)
        self.assertEqual(exit_status_of(res), "max_turns")
        self.assertEqual(res.num_turns, 5)
        self.assertLess(_t.monotonic() - t, 20, "phải giết sớm, không chờ hết 100 bước")

    def test_khong_khai_tran_thi_chay_het(self):
        ngan = "import json\nprint(json.dumps({'type': 'step_finish'}).replace(chr(39), chr(34)))\n"
        res = _OpenCodeGia(ngan).run(
            RunSpec(prompt="x", workdir=".", max_turns=0, timeout_seconds=30))
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.num_turns, 1)


class TestPhienBiCliCatGiuaChung(unittest.TestCase):
    """Model in cú gọi công cụ ra dưới dạng văn bản, CLI không phân giải được,
    phiên dừng. Đo C-1: 20/20 phiên mang chữ ký ấy chết ngay tại đó, và 7/8 lượt
    trượt của **cả hai** nhánh là kiểu hỏng này — nếu xếp nó là "agent trượt"
    thì mọi kết luận về harness đều đọc sai (§ O-7)."""

    def _luong(self, text: str):
        return parse_json_events([json.dumps({"type": "text", "part": {"text": text}})])

    def test_cu_phap_chua_phan_giai_o_cuoi_thi_la_ha_tang_chay_lai_duoc(self):
        res = self._luong('<think></think><minimax:tool_call><invoke name="read">')
        self.assertEqual(exit_status_of(res), "infra")
        self.assertIn("could not parse", res.error)
        self.assertTrue((res.raw_result or {}).get("retryable"))

    def test_cli_thoat_0_van_phai_ra_infra_khi_phien_bi_cat(self):
        """Chỗ bản vá đầu **hỏng**: OpenCode thoát 0 khi phiên bị cắt (nó tưởng
        phiên xong bình thường), nên `ok=True` và `exit_status_of` trả `"ok"`
        ngay dòng đầu, không bao giờ đọc tới `error`. Hệ quả đo được trên C-1b:
        8/24 lượt kết thúc bằng phiên bị cắt, **0 lần** chạy lại hạ tầng nổ.

        Phép thử đi qua đúng `run()` với một tiến trình thật thoát 0."""
        ma = ("import json\n"
              "print(json.dumps({'type': 'text', 'part': {'text': "
              "'<minimax:tool_call><invoke name=\"read\">'}}).replace(chr(39), chr(34)))\n")
        res = _OpenCodeGia(ma).run(RunSpec(prompt="x", workdir=".", timeout_seconds=30))
        self.assertFalse(res.ok, "CLI thoát 0 nhưng phiên bị cắt thì không phải ok")
        self.assertEqual(exit_status_of(res), "infra")

    def test_ket_thuc_binh_thuong_thi_khong_dong_gi_vao(self):
        res = self._luong("xong: 133 test xanh, lint sạch")
        res.ok = True
        self.assertEqual(exit_status_of(res), "ok")
        self.assertEqual(res.error, "")

    def test_cu_phap_o_giua_phien_khong_tinh(self):
        """Chỉ phần văn bản **cuối** mới là dấu hiệu phiên chết ở đó."""
        res = parse_json_events([
            json.dumps({"type": "text", "part": {"text": '<invoke name="read">'}}),
            json.dumps({"type": "text", "part": {"text": "đã sửa xong, test xanh"}}),
        ])
        res.ok = True
        self.assertEqual(exit_status_of(res), "ok")
