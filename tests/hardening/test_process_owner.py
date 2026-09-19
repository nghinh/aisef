"""F5 — the attempt owns its process tree (INV-L.1, INV-L.2): what a session STARTED (a real adapter's process group /
job object; an in-process client's declared `spawned`) is terminated, reaped and VERIFIED dead before the session is
scored, and the pids are recorded — never a silent side effect, never a sibling story's process."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import tests  # noqa: E402,F401
from aisef.harness import process_owner as P  # noqa: E402
from aisef.phases import implement as I  # noqa: E402

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


class TestASessionsLeftoversDieWithTheSession(unittest.TestCase):
    def test_a_child_left_by_an_in_process_session_is_reaped_and_recorded(self):
        left: list[subprocess.Popen] = []

        class Leaves:
            def run(self, spec):
                left.append(subprocess.Popen(SLEEPER))
                return SimpleNamespace(ok=True, cost_usd=0.0, num_turns=1, raw_result={"spawned": [left[-1].pid]})
        try:
            res = I._owned_run(Leaves(), SimpleNamespace(prompt=""))
            self.assertEqual(res.raw_result.get("reaped"), [left[0].pid])
            self.assertFalse(P.pid_alive(left[0].pid), "the leftover must be dead, not merely signalled")
        finally:
            for p in left:
                try:
                    p.kill(); p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass

    def test_a_session_that_leaves_nothing_records_nothing(self):
        class Clean:
            def run(self, spec):
                return SimpleNamespace(ok=True, cost_usd=0.0, num_turns=1, raw_result={})
        self.assertNotIn("reaped", I._owned_run(Clean(), SimpleNamespace(prompt="")).raw_result)

    @unittest.skipIf(sys.platform == "win32", "POSIX process groups; Windows uses the job object exercised by the adapters")
    def test_a_grandchild_in_the_sessions_group_dies_when_the_leader_is_gone(self):
        # a leader in its own session spawns a grandchild sleeper and exits at once: the grandchild outlives it
        leader = subprocess.Popen([sys.executable, "-c",
                                   "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print('spawned', flush=True)"],
                                  stdout=subprocess.PIPE, text=True, start_new_session=True, encoding="utf-8")
        leader.wait(timeout=20)
        members = P._group_members(leader.pid)
        self.assertTrue(members, "precondition: the grandchild is still in the leader's group")
        reaped = P.reap_group(leader)
        self.assertEqual(sorted(reaped), sorted(members))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(P.pid_alive(p) for p in members):
            time.sleep(0.05)
        self.assertFalse(any(P.pid_alive(p) for p in members), "members of the group must be dead, verified")
        try:
            os.killpg(leader.pid, 0)
            self.fail("the process group still exists")
        except OSError:
            pass


class TestASurvivorOfTheReaperIsTypedAndKeepsTheWorkspace(unittest.TestCase):
    """Terminate, reap, VERIFY, then remove (F5 owner rule). When verification fails — a process the session left
    behind survives SIGTERM and SIGKILL — the attempt says so as data: ENVIRONMENT_FAILURE, fatal, the pids on the
    attempt and in evidence, and the run loop keeps the workspace instead of removing a tree still in use."""

    def _no_reap(self):
        from unittest import mock
        return mock.patch.object(P, "reap", lambda pids, *, grace=P.GRACE_SECONDS: [])   # the reaper cannot end it

    def test_owned_run_records_the_survivor_instead_of_a_reaped_pid(self):
        left: list[subprocess.Popen] = []

        class Leaves:
            def run(self, spec):
                left.append(subprocess.Popen(SLEEPER))
                return SimpleNamespace(ok=True, cost_usd=0.0, num_turns=1, raw_result={"spawned": [left[-1].pid]})
        try:
            with self._no_reap():
                res = I._owned_run(Leaves(), None)
            self.assertEqual(res.raw_result.get("orphans"), [left[0].pid])
            self.assertNotIn("reaped", res.raw_result)
        finally:
            for p in left:
                p.kill(); p.wait()

    def test_the_attempt_is_a_fatal_environment_failure_with_the_pids_in_evidence(self):
        from aisef.control.outcome import StageOutcome
        from aisef.harness.observe import TOOL_RUN, EvidenceStore
        from tests.hardening import differential as D
        case = D._Case("runTest"); case.setUp()
        try:
            sc = D.Scenario(0, ["CHANGED_ORPHAN"], ["PASS"], ["PASS"], max_retries=1, test_tool_missing=False)
            with self._no_reap():
                client, out = case.run_scenario(sc)
            try:
                last = out.attempts[-1]
                self.assertEqual(last.outcome, StageOutcome.ENVIRONMENT_FAILURE.value)
                self.assertTrue(last.fatal and last.infra)
                self.assertEqual(last.orphans, [client.orphans[0].pid])
                self.assertIn("workspace kept", last.error)
                rec = [e for e in EvidenceStore(case.artifacts).read(D.SID).of(TOOL_RUN) if e.name == "process"]
                self.assertEqual(rec[-1].detail.get("orphans"), last.orphans)
                self.assertEqual(len(out.attempts), 1, "fatal: no retry inside a tree a live process holds")
            finally:
                for p in client.orphans:
                    p.kill(); p.wait()
        finally:
            case.tearDown()


@unittest.skipIf(sys.platform == "win32", "POSIX signals")
class TestReapTerminatesGracefullyBeforeItKills(unittest.TestCase):
    """Phase 13 mutants of `reap` (INV-L.1): SIGTERM first and a grace wait — a child that handles SIGTERM exits on its
    own terms and leaves its marker; a child that IGNORES SIGTERM is still dead after the hard kill."""

    def test_a_child_that_handles_sigterm_gets_to_exit_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "clean-exit"
            child = subprocess.Popen([sys.executable, "-c",
                                      "import signal, sys, time, pathlib\n"
                                      f"pathlib.Path({str(marker)!r})\n"
                                      "def bye(*_):\n    time.sleep(0.3); pathlib.Path(%r).write_text('term'); sys.exit(0)\n"
                                      "signal.signal(signal.SIGTERM, bye)\nprint('ready', flush=True)\ntime.sleep(60)" % str(marker)],
                                     stdout=subprocess.PIPE, text=True, encoding="utf-8")
            child.stdout.readline()
            try:
                self.assertEqual(P.reap([child.pid]), [child.pid])
                self.assertEqual(marker.read_text(), "term", "SIGTERM was sent first and the grace wait let the handler finish")
            finally:
                child.kill(); child.wait()

    def test_a_child_that_ignores_sigterm_is_hard_killed(self):
        child = subprocess.Popen([sys.executable, "-c",
                                  "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nprint('ready', flush=True)\ntime.sleep(60)"],
                                 stdout=subprocess.PIPE, text=True, encoding="utf-8")
        child.stdout.readline()
        try:
            t0 = time.monotonic()
            self.assertEqual(P.reap([child.pid], grace=0.5), [child.pid])
            self.assertLess(time.monotonic() - t0, 5.0)
            self.assertFalse(P.pid_alive(child.pid))
        finally:
            child.kill(); child.wait()
