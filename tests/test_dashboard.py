"""Dashboard và guard telemetry — v0.4.0."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.observe import (  # noqa: E402
    AGENT_RUN,
    GUARD_BLOCK,
    GUARD_CHECK,
    GUARD_SEEN,
    NOTE,
    TOOL_RUN,
    Event,
    EvidenceStore,
)


class TestGuardTelemetry(unittest.TestCase):
    """P0-2: mỗi lần guard chạy phải ghi GUARD_CHECK."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = EvidenceStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_outcome_writes_guard_check(self):
        from aisef.harness.guardrails import ALLOW, record_outcome
        env = {"AISEF_STORY_ID": "S-01", "AISEF_WRITE_SCOPE": "src"}
        record_outcome("git-stage", {"tool_name": "Bash", "tool_input": {"command": "ls"}},
                       ALLOW, env=env, artifact_root=str(self.root), duration_ms=42)
        ev = self.store.read("S-01")
        checks = ev.of(GUARD_CHECK)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].name, "git-stage")
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].duration_ms, 42)
        self.assertEqual(checks[0].detail["verdict"], "allow")
        self.assertEqual(checks[0].detail["tool"], "Bash")

    def test_record_outcome_writes_guard_check_on_block(self):
        from aisef.harness.guardrails import Verdict, record_outcome
        env = {"AISEF_STORY_ID": "S-01", "AISEF_WRITE_SCOPE": "src"}
        record_outcome("destructive", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
                       Verdict(False, "destructive"), env=env, artifact_root=str(self.root),
                       duration_ms=5)
        ev = self.store.read("S-01")
        checks = ev.of(GUARD_CHECK)
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].ok)
        self.assertEqual(checks[0].detail["verdict"], "block")

    def test_guard_check_constant_exists(self):
        self.assertEqual(GUARD_CHECK, "guard_check")


class TestDashboardGeneration(unittest.TestCase):
    """P0-1: dashboard generates valid HTML."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = EvidenceStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_evidence(self):
        self.store.record("S-01", Event(kind=GUARD_SEEN, name="write-scope"))
        self.store.record("S-01", Event(kind=GUARD_CHECK, name="write-scope",
                                        ok=True, duration_ms=10,
                                        detail={"tool": "Write", "verdict": "allow"}))
        self.store.record("S-01", Event(kind=GUARD_CHECK, name="write-scope",
                                        ok=True, duration_ms=20,
                                        detail={"tool": "Edit", "verdict": "allow"}))
        self.store.record("S-01", Event(kind=GUARD_CHECK, name="destructive",
                                        ok=False, duration_ms=3,
                                        detail={"tool": "Bash", "verdict": "block"}))
        self.store.record("S-01", Event(kind=GUARD_BLOCK, name="destructive",
                                        ok=False, detail={"tool": "Bash", "reason": "rm -rf"}))
        self.store.record("S-01", Event(kind=TOOL_RUN, name="test", ok=True, duration_ms=5000))
        self.store.record("S-01", Event(kind=NOTE, name="gate:verdict",
                                        detail={"attempt": 1, "failures": [],
                                                "candidate": "abc1234"}))

    def test_generates_valid_html(self):
        from aisef.cli.dashboard import generate_html
        self._seed_evidence()
        evidences = [self.store.read("S-01")]
        html = generate_html(evidences, project="test-project")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("AISEF Conformance Dashboard", html)
        self.assertIn("test-project", html)

    def test_guard_stats_in_html(self):
        from aisef.cli.dashboard import generate_html
        self._seed_evidence()
        html = generate_html([self.store.read("S-01")], project="p")
        self.assertIn("write-scope", html)
        self.assertIn("destructive", html)

    def test_gate_verdicts_in_html(self):
        from aisef.cli.dashboard import generate_html
        self._seed_evidence()
        html = generate_html([self.store.read("S-01")], project="p")
        self.assertIn("abc1234", html)
        self.assertIn("DAT", html)

    def test_empty_evidence_produces_html(self):
        from aisef.cli.dashboard import generate_html
        html = generate_html([], project="empty")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("No guard telemetry data", html)

    def test_cmd_dashboard_writes_file(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from aisef.cli.dashboard import cmd_dashboard
        self._seed_evidence()
        out = self.root / "out.html"
        args = SimpleNamespace(project=str(self.root), out=str(out))
        with patch("aisef.cli.dashboard._artifact_root", return_value=self.root):
            rc = cmd_dashboard(args)
        self.assertEqual(rc, 0)
        self.assertTrue(out.exists())
        self.assertIn("<!DOCTYPE html>", out.read_text())

    def test_cmd_dashboard_no_evidence_returns_not_ready(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from aisef.cli.dashboard import cmd_dashboard
        args = SimpleNamespace(project=str(self.root), out="")
        with patch("aisef.cli.dashboard._artifact_root", return_value=self.root):
            rc = cmd_dashboard(args)
        self.assertEqual(rc, 2)


class TestMultiProjectDashboard(unittest.TestCase):
    """Multi-project aggregation — v0.4.1."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.proj_a = self.root / "proj-a" / "_bmad-output"
        self.proj_b = self.root / "proj-b" / "_bmad-output"
        for d in (self.proj_a, self.proj_b):
            d.mkdir(parents=True)
        self.store_a = EvidenceStore(self.proj_a)
        self.store_b = EvidenceStore(self.proj_b)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, store, story_id):
        store.record(story_id, Event(kind=GUARD_CHECK, name="write-scope",
                                     ok=True, duration_ms=5,
                                     detail={"tool": "Write", "verdict": "allow"}))
        store.record(story_id, Event(kind=TOOL_RUN, name="test", ok=True, duration_ms=1000))

    def test_collect_projects_includes_extra_dirs(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from aisef.cli.dashboard import _collect_projects

        self._seed(self.store_a, "SA-01")
        self._seed(self.store_b, "SB-01")
        args = SimpleNamespace(
            project=str(self.root / "proj-a"),
            projects=[str(self.root / "proj-b")],
        )
        with patch("aisef.cli.dashboard._artifact_root", return_value=self.proj_a):
            groups = _collect_projects(args)
        self.assertEqual(len(groups), 2)
        names = [n for n, _ in groups]
        self.assertIn("proj-a", names)
        self.assertIn("proj-b", names)

    def test_project_summary_table_only_for_multi(self):
        from aisef.cli.dashboard import _project_summary
        self._seed(self.store_a, "SA-01")
        evs = [self.store_a.read("SA-01")]
        self.assertEqual(_project_summary([("a", evs)]), "")
        self.assertIn("Tổng hợp dự án", _project_summary([("a", evs), ("b", evs)]))

    def test_generate_html_with_extra_sections(self):
        from aisef.cli.dashboard import generate_html
        self._seed(self.store_a, "SA-01")
        evs = [self.store_a.read("SA-01")]
        html = generate_html(evs, project="multi", extra_sections="<h2>EXTRA</h2>")
        self.assertIn("EXTRA", html)

    def test_cmd_dashboard_multi_project(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from aisef.cli.dashboard import cmd_dashboard

        self._seed(self.store_a, "SA-01")
        self._seed(self.store_b, "SB-01")
        out = self.root / "out.html"
        args = SimpleNamespace(
            project=str(self.root / "proj-a"),
            projects=[str(self.root / "proj-b")],
            out=str(out),
        )
        with patch("aisef.cli.dashboard._artifact_root", return_value=self.proj_a):
            rc = cmd_dashboard(args)
        self.assertEqual(rc, 0)
        content = out.read_text()
        self.assertIn("proj-a", content)
        self.assertIn("proj-b", content)
        self.assertIn("Tổng hợp dự án", content)

    def test_nonexistent_project_dir_skipped(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from aisef.cli.dashboard import _collect_projects

        self._seed(self.store_a, "SA-01")
        args = SimpleNamespace(
            project=str(self.root / "proj-a"),
            projects=[str(self.root / "nonexistent")],
        )
        with patch("aisef.cli.dashboard._artifact_root", return_value=self.proj_a):
            groups = _collect_projects(args)
        self.assertEqual(len(groups), 1)


class TestStructuredGuardError(unittest.TestCase):
    """P1-4: guard block emits JSON on stdout."""

    def test_cmd_guard_outputs_json_on_block(self):
        import io
        import json
        from contextlib import redirect_stderr, redirect_stdout
        from types import SimpleNamespace
        from unittest.mock import patch

        from aisef.cli.harness import cmd_guard
        from aisef.harness.guardrails import Verdict

        event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
        args = SimpleNamespace(project="/tmp", kind="destructive")

        with patch("sys.stdin", io.StringIO(event)), \
             patch("aisef.control.worktree.main_repo", return_value=Path("/tmp")), \
             patch("aisef.harness.guardrails.run_guard", return_value=Verdict(False, "blocked")), \
             patch("aisef.harness.guardrails.record_outcome"):
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = cmd_guard(args)

        self.assertEqual(rc, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["allowed"])
        self.assertEqual(payload["reason"], "blocked")
        self.assertEqual(payload["guard"], "destructive")
        self.assertIn("blocked", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestRoleCost(unittest.TestCase):
    """Role cost breakdown — v0.5.0."""

    def test_role_cost_from_agent_run(self):
        from aisef.cli.dashboard import _role_cost
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        store = EvidenceStore(root)
        store.record("S-01", Event(kind=AGENT_RUN, name="dev", ok=True,
                                   cost_usd=0.50, duration_ms=5000,
                                   detail={"role": "developer", "model": "claude-sonnet"}))
        store.record("S-01", Event(kind=AGENT_RUN, name="rev", ok=True,
                                   cost_usd=0.30, duration_ms=3000,
                                   detail={"role": "reviewer", "model": "claude-haiku"}))
        evs = [store.read("S-01")]
        roles = _role_cost(evs)
        self.assertIn("developer", roles)
        self.assertIn("reviewer", roles)
        self.assertAlmostEqual(roles["developer"]["cost"], 0.50)
        self.assertEqual(roles["developer"]["runs"], 1)
        self.assertIn("claude-sonnet", roles["developer"]["models"])
        tmp.cleanup()

    def test_role_cost_in_html(self):
        from aisef.cli.dashboard import generate_html
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        store = EvidenceStore(root)
        store.record("S-01", Event(kind=AGENT_RUN, name="dev", ok=True,
                                   cost_usd=1.0, duration_ms=5000,
                                   detail={"role": "developer", "model": "opus"}))
        evs = [store.read("S-01")]
        html = generate_html(evs, project="test")
        self.assertIn("Cost by role", html)
        self.assertIn("developer", html)
        tmp.cleanup()
