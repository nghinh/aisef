"""Tool của harness — lệnh cố định, chạy trong sandbox, ghi bằng chứng."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests import needs_docker  # noqa: E402 — HostProvider vào chỗ docker (tests/__init__.py)
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.harness.observe import TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.harness.tools import (  # noqa: E402
    TOOLS,
    aisef_argv,
    aisef_command,
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
        self.assertIn("has not declared a command", e.detail["skipped"])

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
        from aisef.harness import sandbox

        fake = sandbox.FakeProvider([sandbox.SandboxResult(
            125, stderr="docker: Error response from daemon: pull access denied",
            provider_error="pull access denied")])
        cfg = Config({**DEFAULTS, "tools.test": "pytest -q", "sandbox.provider": "fake"})
        with sandbox.using(fake):
            res = run_tool("test", self.project, story_id="S-01",
                           artifact_root=self.artifacts, config=cfg)
        self.assertFalse(res.ok)
        self.assertIn("sandbox infrastructure", res.unrunnable)
        self.assertFalse(res.degraded)
        self.assertEqual(fake.calls[0].cmd, ["pytest", "-q"])
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertEqual(e.detail["provider_error"], "pull access denied")
        self.assertIn("infrastructure", e.detail["unrunnable"])

    def test_suy_bien_neu_ten_bao_dam_thieu(self):
        cfg = Config({**DEFAULTS, "tools.test": "true", "sandbox.use_docker": False})
        res = run_tool("test", self.project, config=cfg)
        self.assertTrue(res.degraded)
        self.assertEqual(res.detail["missing"], ["network_none", "non_root", "secrets_absent"])
        self.assertIn("network_none", res.summary())


class TestLenhGoiFramework(unittest.TestCase):
    """`aisef_command()` là thứ đi vào hook và vào prompt — trỏ sai thì guard
    không chạy mà **không ai báo gì**."""

    def test_uu_tien_ten_tren_path(self):
        with mock.patch("shutil.which", return_value="/usr/local/bin/aisef"):
            self.assertEqual(aisef_command(), "aisef")

    @unittest.skipIf(sys.platform == "win32",
                     "bin/aisef là script POSIX; Windows đi thẳng xuống python -m")
    def test_khong_co_tren_path_thi_dung_bin_cua_kho(self):
        with mock.patch("shutil.which", return_value=None):
            got = aisef_command()
        self.assertTrue(got.endswith("bin/aisef"), got)
        self.assertTrue(Path(got).is_file(), "đường dẫn trả về phải tồn tại")

    def test_windows_khong_dung_script_posix(self):
        """Lỗi 49. `bin/aisef` là script shell: có mặt trong bản kho trên **mọi**
        HĐH, nhưng Windows không chạy được — `is_file()` nói có, `CreateProcess`
        nói không, và hook được ghi trỏ vào thứ không chạy nổi (đúng hình dạng
        lỗi 31, ở nền tảng bên kia)."""
        with mock.patch("shutil.which", return_value=None), \
             mock.patch("aisef.harness.tools.sys.platform", "win32"):
            self.assertEqual(aisef_argv(), [sys.executable, "-m", "aisef.cli"])

    def test_ban_cai_tu_wheel_lui_ve_python_m(self):
        """Wheel không mang `bin/`. Trước 0.2.0 chỗ này trả `<site-packages>/bin/aisef`
        — không tồn tại — nên hook im lặng không chạy guard nào."""
        with mock.patch("shutil.which", return_value=None), \
             mock.patch.object(Path, "is_file", return_value=False):
            got = aisef_command()
        self.assertEqual(got, f"{sys.executable} -m aisef.cli")

    def test_dang_argv_khong_gop_ba_tu_thanh_mot(self):
        """Lỗi 32. Người gọi thật cần **argv**: gộp `<python> -m aisef.cli`
        vào một chuỗi thì phía nhận đọc lại thành một tên tệp có dấu cách —
        `command not found` ở mọi lần gọi guard, và cả lượt chạy không còn
        guard nào (đo 2026-09-09 trên `todo`: 46 phiên, 0 sự kiện guard)."""
        with mock.patch("shutil.which", return_value=None), \
             mock.patch.object(Path, "is_file", return_value=False):
            self.assertEqual(aisef_argv(), [sys.executable, "-m", "aisef.cli"])
        with mock.patch("shutil.which", return_value="/usr/local/bin/aisef"):
            self.assertEqual(aisef_argv(), ["aisef"])


class TestSuiteKhongMoContainer(ToolTestCase):
    """A2 kế hoạch phát hành: `run_tool` với cấu hình mặc định của dự án
    (`sandbox.provider = docker`) chạy trên `HostProvider` trong suite đơn vị —
    không container, không suy biến, bằng chứng ghi thật `host/…`. Đỏ khi hoàn
    nguyên `tests/__init__.py`."""

    @unittest.skipIf(os.environ.get("AISEF_TEST_DOCKER") == "1", "đang chạy Docker thật")
    def test_cau_hinh_mac_dinh_chay_tren_host(self):
        res = run_tool("test", self.project, story_id="S-01", artifact_root=self.artifacts,
                       config=Config({**DEFAULTS, "tools.test": "true"}))
        self.assertTrue(res.ok)
        self.assertFalse(res.degraded)
        self.assertEqual(res.detail["isolation"], "host/WORKSPACE_WRITE")
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertEqual(e.detail["isolation"], "host/WORKSPACE_WRITE")


@needs_docker
class TestRunToolQuaDockerThat(ToolTestCase):
    """Docker thật, bật bằng `AISEF_TEST_DOCKER=1`: `run_tool` end-to-end qua
    container — bằng chứng ghi `docker/…`, và lệnh đỏ trong container vẫn là
    test đỏ, không phải "không chạy được"."""

    def test_xanh_trong_container_khong_suy_bien(self):
        res = run_tool("test", self.project, story_id="S-01", artifact_root=self.artifacts,
                       config=Config({**DEFAULTS, "tools.test": "true"}))
        self.assertTrue(res.ok, res.stderr)
        self.assertFalse(res.degraded)
        self.assertEqual(res.detail["isolation"], "docker/WORKSPACE_WRITE")
        self.assertEqual(res.detail["provider_error"], "")

    def test_do_trong_container_van_la_test_do(self):
        res = run_tool("test", self.project, config=Config(
            {**DEFAULTS, "tools.test": "sh -c 'echo 1 failed; exit 1'"}))
        self.assertFalse(res.ok)
        self.assertEqual(res.exit_code, 1)
        self.assertEqual(res.unrunnable, "")
        self.assertEqual(res.detail["isolation"], "docker/WORKSPACE_WRITE")


class TestDescription(ToolTestCase):
    def test_every_tool_says_when_to_call_it(self):
        """Tool không có mô tả dùng đúng lúc thì agent sẽ gọi sai lúc."""
        for tool in TOOLS.values():
            self.assertTrue(len(tool.when) > 30, tool.name)

    def test_prompt_names_a_command_the_agent_can_actually_run(self):
        """`aisef tool test` là vô dụng nếu `aisef` không nằm trên PATH
        của phiên agent: nó nhận "command not found", tự chạy pytest bằng
        tay, và lần chạy đó không vào bằng chứng."""
        import os
        import shutil

        from aisef.clients.base import split_command

        binary = aisef_command()
        program, *rest = split_command(binary)
        if program == "aisef":
            self.assertTrue(shutil.which("aisef"))
        elif rest[:1] == ["-m"]:
            self.assertEqual(program, sys.executable)  # last resort: this interpreter
        else:
            self.assertTrue(os.path.isfile(program), program)
            self.assertTrue(os.access(program, os.X_OK), program)
        self.assertIn(binary, describe_tools(self.project, self.cfg))

    def test_prompt_table_shows_the_real_command(self):
        self.write("pyproject.toml", "")
        text = describe_tools(self.project, self.cfg)
        self.assertIn("pytest -q", text)
        self.assertIn("When:", text)


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
        self.assertIn("cannot load", res.unrunnable)
        e = EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")
        self.assertTrue(e.detail["unrunnable"])

    def test_red_test_mentioning_not_found_is_still_red(self):
        from pathlib import Path
        (Path(self.project) / "out.txt").write_text(
            "✔ AC-S-1: có (1ms)\n✖ AC-S-2: element not found (2ms)\nℹ tests 2\nℹ pass 1\nℹ fail 1\n", encoding="utf-8")
        res = self.run_test_tool("sh -c 'cat out.txt; exit 1'")
        self.assertFalse(res.ok)
        self.assertEqual(res.unrunnable, "")


class TestCheBiMatVaLogToanVan(ToolTestCase):
    """ADR-005 V1 + V11 (A). `tail` đi vào `_bmad-output`, thư mục được commit
    theo dự án — bí mật phải bị che **trước** khi ghi; output dài thì toàn văn
    nằm ở tệp `.log` cạnh sổ, còn `tail` vẫn 20 dòng (ngân sách prompt B5)."""

    AWS = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    GH = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    BEARER = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop"

    def run_test_tool(self, command: str):
        # Không Docker: điều cần kiểm là che/cắt, không phải sandbox.
        cfg = Config({**DEFAULTS, "tools.test": command, "sandbox.use_docker": False})
        return run_tool("test", self.project, story_id="S-01",
                        artifact_root=self.artifacts, config=cfg)

    def last(self):
        return EvidenceStore(self.artifacts).read("S-01").last(TOOL_RUN, "test")

    def test_bi_mat_trong_stdout_bi_che_va_dem(self):
        res = self.run_test_tool(
            f"sh -c 'echo {self.AWS}; echo {self.GH}; echo \"{self.BEARER}\"; exit 1'")
        e = self.last()
        self.assertEqual(e.detail["redacted"], 3)
        self.assertEqual(e.detail["tail"].count("[REDACTED]"), 3)
        for lo in ("wJalrXUtnFEMI", "ghp_", "eyJhbGci"):
            self.assertNotIn(lo, e.detail["tail"])
            self.assertNotIn(lo, res.tail())   # thứ agent thấy cũng đã che

    def test_stdout_sach_thi_khong_doi(self):
        self.run_test_tool("sh -c 'echo xanh sạch'")
        e = self.last()
        self.assertNotIn("redacted", e.detail)
        self.assertEqual(e.detail["tail"], "xanh sạch")

    def test_output_dai_co_log_toan_van_da_che_tail_van_20_dong(self):
        res = self.run_test_tool(f"sh -c 'seq 1 500; echo {self.GH}; exit 1'")
        e = self.last()
        self.assertEqual(len(e.detail["tail"].splitlines()), 20)
        self.assertTrue(res.log.endswith(f"S-01-test-{e.seq}.log"), res.log)
        log = Path(res.log).read_text(encoding="utf-8")
        self.assertEqual(len(log.splitlines()), 501)
        self.assertIn("[REDACTED]", log)
        self.assertNotIn("ghp_", log)

    def test_output_ngan_thi_khong_co_log(self):
        res = self.run_test_tool("seq 1 20")
        self.assertEqual(res.log, "")
        self.assertEqual(list(self.artifacts.glob("evidence/*.log")), [])

    def test_ten_log_baseline_khong_co_dau_hai_cham(self):
        """`test:baseline` → `-test-baseline-`: tên tệp phải mở được ở mọi hệ."""
        from aisef.harness.tools import BASELINE_RUN, ToolResult, record
        res = ToolResult(name="test", ok=True, stdout="\n".join(map(str, range(30))))
        path = record(res, "S-01", self.artifacts, name=BASELINE_RUN)
        self.assertEqual(Path(path).name, "S-01-test-baseline-1.log")


class TestThieuDuAnKhacThieuCongCu(unittest.TestCase):
    """Lỗi 55: npm báo ENOENT vì **thiếu package.json**, không phải thiếu npm.
    Chuỗi "no such file or directory" khớp MISSING_TOOL nên harness kết luận
    "tool not installed" trên đúng cái máy vừa chạy bộ test đó."""

    NPM_ENOENT = (
        "npm error code ENOENT\nnpm error syscall open\n"
        "npm error path /w/package.json\n"
        "npm error enoent Could not read package.json: Error: ENOENT: "
        "no such file or directory, open '/w/package.json'"
    )

    def test_thieu_manifest_la_khong_co_du_an(self):
        from aisef.harness.tools import NO_PROJECT, unrunnable_reason
        self.assertTrue(unrunnable_reason("test", 254, self.NPM_ENOENT).startswith(NO_PROJECT))

    def test_thieu_cong_cu_van_la_thieu_cong_cu(self):
        from aisef.harness.tools import unrunnable_reason
        for out, code in (("npm: command not found", 127),
                          ("sh: vitest: not found\nsee package.json for scripts", 127)):
            with self.subTest(out=out):
                self.assertIn("tool not installed", unrunnable_reason("test", code, out))

    def test_test_that_ra_ket_qua_van_khong_phai_unrunnable(self):
        from aisef.harness.tools import unrunnable_reason
        out = "tests/a.py::test_x PASSED\nno such file or directory: package.json"
        self.assertEqual(unrunnable_reason("test", 1, out), "")
