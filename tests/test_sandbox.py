"""Kiểm chứng cách ly sandbox — chạy Docker thật khi có daemon."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.harness.sandbox import (  # noqa: E402
    DEFAULT_IMAGE,
    PROVIDERS,
    DockerProvider,
    FakeProvider,
    Guarantee,
    Level,
    LocalProvider,
    SandboxResult,
    SandboxSpec,
    _run_docker,
    build_docker_args,
    docker_available,
    missing_guarantees,
    run,
    select_provider,
    using,
)

HAS_DOCKER = docker_available()
needs_docker = unittest.skipUnless(HAS_DOCKER, "docker daemon không chạy")


class TestLevels(unittest.TestCase):
    def test_read_only_is_not_writable(self):
        self.assertFalse(Level.READ_ONLY.writable)

    def test_only_two_levels_have_network(self):
        networked = [l for l in Level if l.networked]
        self.assertEqual(set(networked), {Level.WORKSPACE_NETWORK, Level.PRIVILEGED_TEST})


class TestDockerArgs(unittest.TestCase):
    """Dựng dòng lệnh — kiểm được mà không cần chạy container."""

    def spec(self, level: Level) -> SandboxSpec:
        return SandboxSpec(workspace=Path("/tmp"), cmd=["echo", "hi"], level=level)

    def test_no_network_by_default(self):
        args = build_docker_args(self.spec(Level.WORKSPACE_WRITE))
        self.assertIn("--network=none", args)

    def test_network_allowed_only_when_level_says_so(self):
        self.assertNotIn("--network=none", build_docker_args(self.spec(Level.WORKSPACE_NETWORK)))

    def test_read_only_mount(self):
        args = build_docker_args(self.spec(Level.READ_ONLY))
        self.assertTrue(any(a.endswith(":/workspace:ro") for a in args))

    def test_writable_mount(self):
        args = build_docker_args(self.spec(Level.WORKSPACE_WRITE))
        self.assertTrue(any(a.endswith(":/workspace:rw") for a in args))

    def test_drops_capabilities_and_runs_non_root(self):
        args = build_docker_args(self.spec(Level.WORKSPACE_WRITE))
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("1000:1000", args)

    def test_privileged_level_keeps_capabilities(self):
        args = build_docker_args(self.spec(Level.PRIVILEGED_TEST))
        self.assertNotIn("--cap-drop=ALL", args)

    def test_env_passed(self):
        s = SandboxSpec(workspace=Path("/tmp"), cmd=["env"], env={"CI": "1"})
        self.assertIn("CI=1", build_docker_args(s))


class TestValidation(unittest.TestCase):
    def test_missing_workspace(self):
        with self.assertRaises(FileNotFoundError):
            run(SandboxSpec(workspace=Path("/khong/ton/tai"), cmd=["true"]))

    def test_empty_cmd(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run(SandboxSpec(workspace=Path(d), cmd=[]))


@needs_docker
class TestIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name) / "workspace"
        self.ws.mkdir()
        (self.ws / "input.txt").write_text("xin chào\n", encoding="utf-8")
        self.outside = Path(self._tmp.name) / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("bí mật\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def spec(self, cmd, level=Level.WORKSPACE_WRITE, **kw):
        return SandboxSpec(workspace=self.ws, cmd=cmd, level=level, image=DEFAULT_IMAGE, **kw)

    def test_runs_and_reads_workspace(self):
        r = run(self.spec(["cat", "input.txt"]))
        self.assertTrue(r.ok)
        self.assertIn("xin chào", r.stdout)
        self.assertFalse(r.degraded)
        self.assertEqual(r.isolation, "docker/WORKSPACE_WRITE")

    def test_network_is_blocked(self):
        """--network=none chặn cả phân giải tên miền."""
        r = run(self.spec(["wget", "-q", "-T", "3", "-O-", "http://example.com"]))
        self.assertNotEqual(r.exit_code, 0)

    def test_cannot_see_paths_outside_mount(self):
        r = run(self.spec(["cat", str(self.outside / "secret.txt")]))
        self.assertNotEqual(r.exit_code, 0)
        self.assertNotIn("bí mật", r.stdout)

    def test_write_lands_on_host(self):
        r = run(self.spec(["sh", "-c", "echo tao-ra > out.txt"]))
        self.assertTrue(r.ok)
        self.assertEqual((self.ws / "out.txt").read_text().strip(), "tao-ra")

    def test_read_only_level_blocks_writes(self):
        r = run(self.spec(["sh", "-c", "echo x > blocked.txt"], level=Level.READ_ONLY))
        self.assertNotEqual(r.exit_code, 0)
        self.assertFalse((self.ws / "blocked.txt").exists())

    def test_cannot_write_outside_workspace_in_container(self):
        r = run(self.spec(["sh", "-c", "touch /etc/nope"]))
        self.assertNotEqual(r.exit_code, 0)

    def test_timeout(self):
        r = run(self.spec(["sleep", "10"], timeout_seconds=2))
        self.assertTrue(r.timed_out)
        self.assertFalse(r.ok)
        self.assertEqual(r.exit_code, 124)

    def test_evidence_shape(self):
        ev = run(self.spec(["true"])).to_evidence()
        for k in ("exit_code", "ok", "duration_ms", "isolation", "degraded", "timed_out"):
            self.assertIn(k, ev)


class TestDegradedMode(unittest.TestCase):
    def test_refuses_when_isolation_required(self):
        """Thà hỏng còn hơn chạy mà giả vờ có cách ly."""
        import aisdlc.harness.sandbox as sb

        original = sb.docker_available
        sb.docker_available = lambda: False
        try:
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(RuntimeError):
                    sb.run(sb.SandboxSpec(workspace=Path(d), cmd=["true"], allow_degraded=False))
        finally:
            sb.docker_available = original

    def test_degraded_is_flagged(self):
        import aisdlc.harness.sandbox as sb

        original = sb.docker_available
        sb.docker_available = lambda: False
        try:
            with tempfile.TemporaryDirectory() as d:
                r = sb.run(sb.SandboxSpec(workspace=Path(d), cmd=["echo", "hi"]))
                self.assertTrue(r.degraded)
                self.assertEqual(r.isolation, "local/WORKSPACE_WRITE")
                self.assertEqual(r.missing, ["network_none", "non_root", "secrets_absent"])
                self.assertIn("hi", r.stdout)
        finally:
            sb.docker_available = original


class TestDockerCanBeTurnedOff(unittest.TestCase):
    """Có dự án mà bộ công cụ chỉ chạy đúng trên máy này — phụ thuộc có
    binary biên dịch theo kiến trúc máy chủ, cài trên host rồi chạy trong
    container Linux thì hỏng. Tắt được, nhưng **phải** hiện ra là mức bảo
    đảm thấp hơn."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_runs_degraded_and_says_so(self):
        r = run(SandboxSpec(workspace=self.ws, cmd=["true"], use_docker=False))
        self.assertTrue(r.ok)
        self.assertTrue(r.degraded)
        self.assertNotIn("docker", r.isolation)
        self.assertTrue(r.to_evidence()["degraded"])

    def test_refusing_to_degrade_still_refuses(self):
        with self.assertRaises(RuntimeError) as e:
            run(SandboxSpec(workspace=self.ws, cmd=["true"],
                            use_docker=False, allow_degraded=False))
        self.assertIn("cấu hình tắt Docker", str(e.exception))


class TestBacKhaiYeuCauProviderKhaiNangLuc(unittest.TestCase):
    """ADR-005 V5: bậc quyền khai **cần** gì, provider khai **có** gì — so
    nhau bằng tên, không bằng `if docker`."""

    def test_moi_bac_khong_mang_can_network_none(self):
        for lv in Level:
            with self.subTest(lv=lv):
                self.assertEqual(Guarantee.NETWORK_NONE in lv.requires(), not lv.networked)

    def test_chi_read_only_can_read_only_fs(self):
        for lv in Level:
            with self.subTest(lv=lv):
                self.assertEqual(Guarantee.READ_ONLY_FS in lv.requires(), not lv.writable)

    def test_moi_bac_can_non_root_tru_privileged(self):
        for lv in Level:
            with self.subTest(lv=lv):
                self.assertEqual(Guarantee.NON_ROOT in lv.requires(), lv is not Level.PRIVILEGED_TEST)

    def test_moi_bac_can_secrets_absent_khong_bac_nao_doi_no_host_mount(self):
        for lv in Level:
            self.assertIn(Guarantee.SECRETS_ABSENT, lv.requires())
            self.assertNotIn(Guarantee.NO_HOST_MOUNT, lv.requires(), "mount worktree là thiết kế")

    def test_docker_du_bao_dam_cho_moi_bac(self):
        for lv in Level:
            with self.subTest(lv=lv):
                self.assertEqual(missing_guarantees(DockerProvider(), lv), [])

    def test_docker_khai_that_no_host_mount_unsupported(self):
        from aisdlc.clients.base import Support

        self.assertIs(DockerProvider().guarantees(Level.READ_ONLY)[Guarantee.NO_HOST_MOUNT],
                      Support.UNSUPPORTED)

    def test_local_thieu_moi_bao_dam_bac_can(self):
        for lv in Level:
            with self.subTest(lv=lv):
                self.assertEqual(missing_guarantees(LocalProvider(), lv),
                                 sorted(g.value for g in lv.requires()))

    def test_fake_khai_native_het(self):
        for lv in Level:
            self.assertEqual(missing_guarantees(FakeProvider(), lv), [])

    def test_docker_chi_chuyen_spec_env_khong_thua_huong_may_chu(self):
        """SECRETS_ABSENT của Docker đứng trên đúng một điều: `-e` chỉ mang
        `spec.env`. Không `--env-file`, không `-e KEY` trần (docker sẽ lấy
        từ host)."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-canary"}):
            args = build_docker_args(SandboxSpec(workspace=Path("/tmp"), cmd=["env"], env={"CI": "1"}))
        self.assertNotIn("--env-file", args)
        gia_tri = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
        self.assertEqual(gia_tri, ["CI=1"])


class TestChonProviderTruocKhiChay(unittest.TestCase):
    """Provider và bảo đảm thiếu quyết định **lúc chọn**, không lúc chạy."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tat_docker_ha_xuong_local_va_neu_ten_thieu(self):
        prov, missing = select_provider(SandboxSpec(workspace=self.ws, cmd=["true"], use_docker=False))
        self.assertEqual(prov.id, "local")
        self.assertEqual(missing, ["network_none", "non_root", "secrets_absent"])

    def test_tu_choi_neu_ten_bao_dam_thieu(self):
        with self.assertRaises(RuntimeError) as e:
            select_provider(SandboxSpec(workspace=self.ws, cmd=["true"],
                                        use_docker=False, allow_degraded=False))
        for g in ("network_none", "non_root", "secrets_absent"):
            self.assertIn(g, str(e.exception))

    def test_tu_choi_thi_lenh_chua_chay(self):
        with self.assertRaises(RuntimeError):
            run(SandboxSpec(workspace=self.ws, cmd=["touch", "da-chay"],
                            use_docker=False, allow_degraded=False))
        self.assertFalse((self.ws / "da-chay").exists())

    def test_provider_khong_ton_tai(self):
        with self.assertRaises(ValueError):
            select_provider(SandboxSpec(workspace=self.ws, cmd=["true"], provider="khong-co"))

    def test_import_path_cho_backend_ngoai(self):
        ten = "aisdlc.harness.sandbox:FakeProvider"
        try:
            prov, missing = select_provider(SandboxSpec(workspace=self.ws, cmd=["true"], provider=ten))
            self.assertEqual(prov.id, "fake")
            self.assertEqual(missing, [])
        finally:
            PROVIDERS.pop(ten, None)

    def test_using_dang_ky_roi_go(self):
        fake = FakeProvider()
        with using(fake):
            self.assertIs(PROVIDERS["fake"], fake)
        self.assertNotIn("fake", PROVIDERS)

    def test_ket_qua_mang_provider_bac_va_bao_dam_thieu(self):
        r = run(SandboxSpec(workspace=self.ws, cmd=["true"], use_docker=False))
        self.assertEqual(r.isolation, "local/WORKSPACE_WRITE")
        self.assertTrue(r.degraded)
        ev = r.to_evidence()
        self.assertEqual(ev["missing"], ["network_none", "non_root", "secrets_absent"])
        self.assertEqual(ev["provider_error"], "")

    def test_fake_tra_theo_kich_ban_va_lap_ket_qua_cuoi(self):
        fake = FakeProvider([SandboxResult(1, stderr="đỏ"), SandboxResult(0, stdout="xanh")])
        with using(fake):
            spec = SandboxSpec(workspace=self.ws, cmd=["bat-ky"], provider="fake", level=Level.READ_ONLY)
            a, b, c = run(spec), run(spec), run(spec)
        self.assertEqual(a.exit_code, 1)
        self.assertEqual((b.stdout, c.stdout), ("xanh", "xanh"))
        self.assertFalse(a.degraded)
        self.assertEqual(a.isolation, "fake/READ_ONLY")
        self.assertEqual([s.cmd for s in fake.calls], [["bat-ky"]] * 3)

    def test_fake_khong_kich_ban_thi_xanh(self):
        with using(FakeProvider()):
            self.assertTrue(run(SandboxSpec(workspace=self.ws, cmd=["x"], provider="fake")).ok)


class TestLocalGiuPath(unittest.TestCase):
    """`env={**spec.env} or None` cũ: env khác rỗng làm mất PATH — lệnh ngoài
    /bin:/usr/bin (node, pytest trong venv) thành "không tìm thấy" (ADR-005 §9)."""

    def test_lenh_tren_path_van_tim_thay_khi_co_env(self):
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as d:
            bin_dir = Path(d) / "bin"
            bin_dir.mkdir()
            script = bin_dir / "lenh-rieng"
            script.write_text("#!/bin/sh\necho CI=$CI\n", encoding="utf-8")
            script.chmod(0o755)
            with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}):
                r = run(SandboxSpec(workspace=Path(d), cmd=["lenh-rieng"], env={"CI": "1"}, use_docker=False))
        self.assertTrue(r.ok, r.stderr)
        self.assertIn("CI=1", r.stdout)


class TestLoiHaTangKhacLenhDo(unittest.TestCase):
    """Docker thoát 125 là **docker** hỏng (daemon, kéo image), không phải
    lệnh bên trong đỏ — SWE-ReX tách `DockerPullError` khỏi exit code."""

    def spec(self, **kw):
        return SandboxSpec(workspace=Path("/tmp"), cmd=["true"], **kw)

    def test_125_thanh_provider_error(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        proc = CompletedProcess(args=[], returncode=125, stdout="",
                                stderr="Unable to find image 'x:y' locally\n"
                                       "docker: Error response from daemon: pull access denied\n")
        with patch("aisdlc.harness.sandbox.subprocess.run", return_value=proc):
            r = _run_docker(self.spec(image="x:y"))
        self.assertEqual(r.exit_code, 125)
        self.assertIn("pull access denied", r.provider_error)
        self.assertFalse(r.ok)

    def test_lenh_do_binh_thuong_khong_phai_loi_ha_tang(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        proc = CompletedProcess(args=[], returncode=1, stdout="1 failed", stderr="")
        with patch("aisdlc.harness.sandbox.subprocess.run", return_value=proc):
            r = _run_docker(self.spec())
        self.assertEqual(r.provider_error, "")

    def test_timeout_don_container_theo_ten(self):
        """Giết CLI không giết container: `sleep 9999` chạy tiếp gần ba giờ
        và giữ mount worktree — S5 hợp quy sandbox lộ ra."""
        import subprocess as sp
        from unittest.mock import patch

        calls = []

        def gia(args, **kw):
            calls.append(list(args))
            if args[:2] == ["docker", "run"]:
                raise sp.TimeoutExpired(args, 2)
            return sp.CompletedProcess(args, 0)

        with patch("aisdlc.harness.sandbox.subprocess.run", side_effect=gia):
            r = _run_docker(self.spec(timeout_seconds=2))
        self.assertTrue(r.timed_out)
        self.assertEqual(r.exit_code, 124)
        ten = calls[0][calls[0].index("--name") + 1]
        self.assertIn(["docker", "rm", "-f", ten], calls)

class TestMounts(unittest.TestCase):
    """ADR-005 V6: worktree sạch từ SHA không có `node_modules`/venv — mượn của dự án."""

    def test_docker_bind_mount_cung_mode_voi_workspace(self):
        s = SandboxSpec(workspace=Path("/tmp"), cmd=["true"],
                        mounts={"node_modules": Path("/du-an/node_modules")})
        self.assertIn("/du-an/node_modules:/workspace/node_modules:rw", build_docker_args(s))
        s.level = Level.READ_ONLY
        self.assertIn("/du-an/node_modules:/workspace/node_modules:ro", build_docker_args(s))

    def test_suy_bien_symlink_vao_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            ws, src = Path(d) / "ws", Path(d) / "src"
            ws.mkdir()
            src.mkdir()
            (src / "x").write_text("1", encoding="utf-8")
            r = run(SandboxSpec(workspace=ws, cmd=["cat", "node_modules/x"], use_docker=False,
                                mounts={"node_modules": src}))
            self.assertEqual(r.stdout.strip(), "1")
            self.assertTrue((ws / "node_modules").is_symlink())


if __name__ == "__main__":
    unittest.main(verbosity=2)
