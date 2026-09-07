"""Dashboard và guard telemetry — v0.4.0."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.observe import (  # noqa: E402
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
