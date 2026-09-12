from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aisef.clients.base import RunSpec
from aisef.clients.simulated import SimulatedWeakAdapter, _read_gold, _revert_files


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


class TestSimulatedStrategies(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "source"
        self.workdir = self.root / "work"
        self.task_dir = self.root / "task"
        for repo in (self.repo, self.workdir):
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "test")
            for name in ("z.py", "a.py", "tests/test_a.py"):
                target = repo / name
                target.parent.mkdir(exist_ok=True)
                target.write_text("old\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", repo.name)
        self.base = git(self.workdir, "rev-parse", "HEAD")
        self.task_dir.mkdir()
        (self.task_dir / "task.json").write_text(json.dumps({"base": git(self.repo, "rev-parse", "HEAD")}), encoding="utf-8")
        for name in ("z.py", "a.py", "tests/test_a.py"):
            (self.repo / name).write_text("new\n", encoding="utf-8")
        (self.task_dir / "gold.patch").write_text(git(self.repo, "diff") + "\n", encoding="utf-8")
        self.env = {"AISEF_BENCH_TASK_DIR": str(self.task_dir),
                    "AISEF_BENCH_AISEF_ROOT": str(self.repo),
                    "AISEF_BENCH_BASE_SHA": self.base}
        clean = patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith("AISEF_BENCH_")}, clear=True)
        clean.start()
        self.addCleanup(clean.stop)

    def run_strategy(self, attempt):
        return SimulatedWeakAdapter().run(RunSpec(prompt="x", workdir=self.workdir, timeout_seconds=10,
                                                  env={**self.env, "AISEF_BENCH_ATTEMPT": str(attempt)}))

    def test_spec_env_root_overrides_process_env(self):
        with patch.dict(os.environ, {"AISEF_BENCH_AISEF_ROOT": str(self.workdir)}):
            result = self.run_strategy(1)
        self.assertTrue(result.ok, result.error)
        self.assertEqual((self.workdir / "a.py").read_text(), "new\n")
        self.assertEqual((self.workdir / "tests/test_a.py").read_text(), "old\n")

    def test_gold_sorted_and_excludes_tests(self):
        original = Path.rglob
        def reversed_glob(path, pattern):
            return iter(sorted(original(path, pattern), reverse=True))
        with patch.dict(os.environ, {"AISEF_BENCH_AISEF_ROOT": str(self.repo)}), patch.object(Path, "rglob", reversed_glob):
            files = _read_gold(self.task_dir)
        self.assertEqual([str(p) for p, _ in files], ["a.py", "z.py"])
        self.assertFalse((self.task_dir / ".sim_scratch").exists())
        self.assertFalse((self.task_dir / ".sim_clean").exists())

    def test_gold_preserves_task_directory_metadata(self):
        before = self.task_dir.stat().st_mtime_ns
        self.assertTrue(self.run_strategy(1).ok)
        self.assertEqual(self.task_dir.stat().st_mtime_ns, before)

    def test_malformed_task_returns_error(self):
        (self.task_dir / "task.json").write_text("{", encoding="utf-8")
        result = self.run_strategy(1)
        self.assertFalse(result.ok)
        self.assertTrue(result.error)

    def test_invalid_attempt_returns_error(self):
        result = self.run_strategy("invalid")
        self.assertFalse(result.ok)
        self.assertTrue(result.error)

    def test_partial_writes_first_file_only(self):
        result = self.run_strategy(3)
        self.assertTrue(result.ok, result.error)
        self.assertEqual((self.workdir / "a.py").read_text(), "new\n")
        self.assertEqual((self.workdir / "z.py").read_text(), "old\n")

    def test_noop_writes_nothing(self):
        self.assertTrue(self.run_strategy(2).ok)
        self.assertEqual(git(self.workdir, "status", "--porcelain"), "")

    def test_revert_uses_materialized_base(self):
        (self.workdir / "a.py").write_text("new\n", encoding="utf-8")
        with patch.dict(os.environ, {"AISEF_BENCH_AISEF_ROOT": str(self.repo)}):
            _revert_files(self.workdir, [(Path("a.py"), "new\n")], self.base)
        self.assertEqual((self.workdir / "a.py").read_text(), "old\n")

    def test_revert_deletes_only_new_files(self):
        (self.workdir / "new.py").write_text("new\n", encoding="utf-8")
        _revert_files(self.workdir, [(Path("new.py"), "new\n")], self.base)
        self.assertFalse((self.workdir / "new.py").exists())

    def test_invalid_base_does_not_delete_files(self):
        with self.assertRaises((OSError, subprocess.CalledProcessError)):
            _revert_files(self.workdir, [(Path("a.py"), "new\n")], "0" * 40)
        self.assertEqual((self.workdir / "a.py").read_text(), "old\n")

    def test_gold_then_revert(self):
        self.assertTrue(self.run_strategy(1).ok)
        self.assertTrue(self.run_strategy(4).ok)
        self.assertEqual(git(self.workdir, "status", "--porcelain"), "")

    def test_adapter_contract(self):
        from aisef.clients.base import Capability, Support

        adapter = SimulatedWeakAdapter()
        self.assertEqual(adapter.id, "simulated-weak")
        self.assertTrue(adapter.available())
        caps = adapter.capabilities()
        self.assertEqual(caps[Capability.HEADLESS], Support.NATIVE)
        self.assertEqual(caps[Capability.MACHINE_OUTPUT], Support.EMULATED)
        self.assertEqual(caps[Capability.PRE_TOOL_GUARD], Support.UNSUPPORTED)
        self.assertEqual(caps[Capability.COST_REPORTING], Support.NATIVE)
        self.assertEqual(caps[Capability.TURN_LIMIT], Support.NATIVE)

    def test_no_env_writes_nothing(self):
        result = SimulatedWeakAdapter().run(RunSpec(prompt="x", workdir=self.workdir, timeout_seconds=10))
        self.assertTrue(result.ok)
        self.assertFalse(result.raw_result["task_dir_present"])
        self.assertEqual(git(self.workdir, "status", "--porcelain"), "")

    def test_missing_patch_returns_empty(self):
        self.assertEqual(_read_gold(self.root), [])
