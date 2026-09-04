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
    Level,
    SandboxSpec,
    build_docker_args,
    docker_available,
    run,
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
                self.assertEqual(r.isolation, "subprocess/degraded")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
