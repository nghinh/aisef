"""Tests for ``aisef.clients.simulated`` — the bench A-3 simulator.

These tests assert the **deterministic strategy** by reading the
worktree after each ``run()``.  They are not unit tests of the patch
parser alone (that has its own coverage in the bench task mining
loop).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from aisef.clients.base import RunSpec
from aisef.clients.simulated import (
    BINARY,
    SimulatedWeakAdapter,
    _read_gold,
)

#: Path to a real bench task whose gold.patch we parse in tests.
SAMPLE_TASK = Path("tests/bench/tasks/bug-a2-state-1")


def _make_worktree(base_sha: str, dest: Path) -> None:
    """Create a fresh worktree at ``base_sha`` so the simulator has a
    realistic git repo to operate on.  Same recipe as bench ``materialize``.
    """
    repo = Path.cwd()
    arch = subprocess.run(
        ["git", "archive", "--format=tar", base_sha], cwd=str(repo),
        capture_output=True, check=True,
    )
    import io

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tf:
        tf.extractall(dest, filter="data")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(dest), check=True)
    subprocess.run(["git", "config", "user.email", "x"], cwd=str(dest), check=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=str(dest), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(dest), check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=str(dest), check=True)


def _show_base(workdir: Path, base_sha: str, rel: str) -> str:
    """Read ``<base_sha>:<rel>`` from the AISEF repo.

    The worktree is a fresh git init with only the new HEAD commit in
    its object DB; the base SHA is not reachable from there.  Read it
    from the AISEF repo (cwd ``.``).
    """
    out = subprocess.run(
        ["git", "show", f"{base_sha}:{rel}"],
        cwd=str(Path.cwd()), capture_output=True, check=True,
    )
    return out.stdout.decode("utf-8", errors="replace")


class TestReadGold(unittest.TestCase):
    """``_read_gold`` produces a list of ``(rel_path, content)`` pairs."""

    @classmethod
    def setUpClass(cls):
        assert SAMPLE_TASK.is_dir(), f"sample bench task missing: {SAMPLE_TASK}"
        # Clean any previous scratch that may linger from the bench CLI.
        shutil.rmtree(SAMPLE_TASK / ".sim_scratch", ignore_errors=True)
        shutil.rmtree(SAMPLE_TASK / ".sim_clean", ignore_errors=True)

    def test_returns_non_test_files(self):
        out = _read_gold(SAMPLE_TASK)
        self.assertTrue(out, "expected at least one file from gold.patch")
        for p, body in out:
            self.assertNotIn("tests/", p.parts)
            self.assertTrue(body, f"{p} has empty body")
            self.assertIsInstance(body, str)

    def test_missing_patch_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            empty = Path(d) / "no_such_task"
            empty.mkdir()
            self.assertEqual(_read_gold(empty), [])

    def test_clean_up_scratch_dirs(self):
        # scratch/clean are written under task_dir; ensure test cleanup.
        for suffix in (".sim_scratch", ".sim_clean"):
            self.assertFalse((SAMPLE_TASK / suffix).exists(),
                             f"scratch dir left behind: {suffix}")


class TestSimulatedStrategies(unittest.TestCase):
    """Strategy choice is keyed on ``attempt % 4`` and reproducible."""

    def setUp(self):
        self._saved = {}
        for k in ("AISEF_BENCH_TASK_DIR", "AISEF_BENCH_ATTEMPT", "AISEF_BENCH_BASE_SHA",
                  "AISEF_BENCH_AISEF_ROOT"):
            self._saved[k] = os.environ.get(k)
        # Sandbox: copy the bench task dir so we can mutate it freely.
        self.tmp = Path(tempfile.mkdtemp(prefix="sim_"))
        self.task_dir = self.tmp / "bug-a2-state-1"
        shutil.copytree(SAMPLE_TASK, self.task_dir)
        # Pick a base SHA out of task.json.
        data = json.loads((self.task_dir / "task.json").read_text())
        self.base = data["base"]
        # Set up a fresh worktree.
        self.workdir = self.tmp / "workdir"
        shutil.rmtree(self.workdir, ignore_errors=True)
        _make_worktree(self.base, self.workdir)
        # Real AISEF repo is needed for ``_read_gold``'s ``git archive``.
        os.environ["AISEF_BENCH_TASK_DIR"] = str(self.task_dir)
        os.environ["AISEF_BENCH_AISEF_ROOT"] = str(Path.cwd())
        os.environ["AISEF_BENCH_BASE_SHA"] = self.base

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)
        for suffix in (".sim_scratch", ".sim_clean"):
            shutil.rmtree(self.task_dir / suffix, ignore_errors=True)

    def _run_strategy(self, attempt: int):
        os.environ["AISEF_BENCH_ATTEMPT"] = str(attempt)
        adapter = SimulatedWeakAdapter()
        result = adapter.run(RunSpec(prompt="x", workdir=self.workdir, timeout_seconds=10))
        return result, adapter

    def test_gold_strategy_writes_post_fix_content(self):
        result, _ = self._run_strategy(1)  # attempt 1 -> "gold"
        self.assertTrue(result.ok)
        self.assertEqual("gold", result.raw_result["strategy"])
        # The patched file should now differ from the pre-fix commit.
        rel = Path("aisef/phases/implement.py")
        post = (self.workdir / rel).read_text()
        pre = _show_base(self.workdir, self.base, str(rel))
        self.assertNotEqual(pre, post)

    def test_noop_strategy_writes_nothing(self):
        result, _ = self._run_strategy(2)  # attempt 2 -> "noop"
        self.assertTrue(result.ok)
        self.assertEqual("noop", result.raw_result["strategy"])
        # Working tree should be clean; no candidate commit.
        proc = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(self.workdir),
            capture_output=True, text=True, check=True,
        )
        self.assertEqual("", proc.stdout)

    def test_partial_strategy_writes_subset(self):
        result, _ = self._run_strategy(3)  # attempt 3 -> "partial"
        self.assertTrue(result.ok)
        self.assertEqual("partial", result.raw_result["strategy"])
        # The summary text in result.text announces the subset count.
        self.assertIn("wrote", result.text)
        self.assertIn("/", result.text)  # "wrote 1/N files"

    def test_revert_strategy_restores_pre_fix(self):
        # First apply gold so the working tree has post-fix content,
        # then revert to verify the strategy restores pre-fix.
        result_gold, _ = self._run_strategy(1)
        self.assertEqual("gold", result_gold.raw_result["strategy"])
        # Now attempt 4 -> "revert": simulates agent re-rolling to old code.
        result, _ = self._run_strategy(4)
        self.assertTrue(result.ok)
        self.assertEqual("revert", result.raw_result["strategy"])
        # File should match the pre-fix version.
        rel = Path("aisef/phases/implement.py")
        post = (self.workdir / rel).read_text()
        pre = _show_base(self.workdir, self.base, str(rel))
        self.assertEqual(pre, post)


class TestAdapterContract(unittest.TestCase):
    """The simulator reports clean capabilities so the bench compile
    step does not break and gates do not lie about their assurance.
    """

    def test_id_is_simulated_weak(self):
        self.assertEqual(BINARY, "simulated-weak")
        self.assertEqual(SimulatedWeakAdapter.id, "simulated-weak")

    def test_capabilities_honest(self):
        caps = SimulatedWeakAdapter().capabilities()
        from aisef.clients.base import Capability, Support
        # HEADLESS is native: writes directly.
        self.assertEqual(caps[Capability.HEADLESS], Support.NATIVE)
        # PRE_TOOL_GUARD is unsupported: there are no real hooks.
        self.assertEqual(caps[Capability.PRE_TOOL_GUARD], Support.UNSUPPORTED)
        # COST_REPORTING is native: cost is 0, real cost is 0.
        self.assertEqual(caps[Capability.COST_REPORTING], Support.NATIVE)
        # TURN_LIMIT is native: deterministic, always 1.
        self.assertEqual(caps[Capability.TURN_LIMIT], Support.NATIVE)

    def test_always_available(self):
        self.assertTrue(SimulatedWeakAdapter().available())

    def test_run_with_no_env_falls_back_to_noop(self):
        # No env vars => "task_dir_present": false => all strategies fall back
        # to writing nothing, which is the documented safe default.
        for k in ("AISEF_BENCH_TASK_DIR", "AISEF_BENCH_ATTEMPT"):
            os.environ.pop(k, None)
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            res = SimulatedWeakAdapter().run(
                RunSpec(prompt="x", workdir=wd, timeout_seconds=10)
            )
        self.assertTrue(res.ok)
        self.assertFalse(res.raw_result["task_dir_present"])


if __name__ == "__main__":
    unittest.main()
