"""Phase 14 — compound faults: real failures are not isolated. Each scenario injects two faults (or a fault
plus a resume) into the real kernel through the synthetic client / the run-level fake agent and asserts every
invariant that applies. Red scenarios are marked with the defect id or fix family that closes them; they turn
green with the family and lose the marker in the same commit. No OpenCode, no network, no Docker.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.clients.base import RunSpec  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import gate as G  # noqa: E402
from aisef.control.approvals import ApprovalStore, Gate, Status  # noqa: E402
from aisef.control.journal import JournalStore  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.state import StoryStatus  # noqa: E402
from aisef.control.worktree import WorktreeManager  # noqa: E402
from aisef.harness.observe import NOTE, TOOL_RUN, Event, Evidence, EvidenceStore  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from aisef.phases import run as R  # noqa: E402
from tests.test_retry_hygiene import SCOPE, SID, HygieneCase, _git  # noqa: E402
from tests.test_run import Agent, RunTestCase  # noqa: E402

IN, OUT = SCOPE[0], "ledgerlock/ledger.py"


def _green(n): return {IN: f"def main(argv=None):\n    return {n}\n"}
def _block_in(): return [{"tag": "block", "file": IN, "line": 1, "why": "exit code wrong", "behavior_id": "FR-4"}]


class _Case(HygieneCase):
    def runTest(self):
        pass

    def implement(self, client, *, retries=1, **cfg):
        return I.implement_story(self.story, project=self.project, workdir=self.work, artifact_root=self.artifacts,
                                 client=client, config=Config({**DEFAULTS, "tools.test": "true", "tools.lint": "true",
                                                              "run.max_retries": retries, **cfg}))

    def ev(self):
        return EvidenceStore(self.artifacts).read(SID)


# --------------------------------------------------------------- CF-01 reviewer timeout after recovery
class TestCF01ReviewerTimeoutAfterRecovery(_Case):
    def test_recovery_then_reviewer_absence_keeps_the_candidate_and_never_reopens_the_developer(self):
        c = SyntheticClientAdapter(Script(
            developer=[Step("SCOPE_VIOLATION", files={**_green(1), OUT: "# reformatted\n"}), Step("CHANGED", files=_green(2))],
            review=[Step.passes(), Step.unrunnable()], security=[Step.passes()]))
        out = self.implement(c, retries=2)
        self.assertFalse(out.done)
        self.assertIn("REVIEW_UNRUNNABLE", out.blocked_reason, out.blocked_reason)
        self.assertEqual(c.develop_calls, 2, "the reviewer's absence is not developer work")
        rec = [e for e in self.ev().of(NOTE, "retry:recovery")]
        self.assertEqual([r.detail["tracked"] for r in rec], [[OUT]], "hygiene restored exactly the violating path")
        self.assertEqual(len([k for k in c.calls if k.role == "review"]), 1 + 3, "one review on candidate 1, three on candidate 2")
        self.assertEqual(_git(self.work, "rev-parse", "HEAD"), out.attempts[-1].candidate, "the candidate is kept for --verify-only")


# --------------------------------------------------------------- CF-02 security timeout after reviewer BLOCK remediation
class TestCF02SecurityTimeoutAfterBlockRemediation(_Case):
    @unittest.expectedFailure   # SS-13 (F2) — a security SESSION failure is a FAILED check and reopens the developer
    def test_security_absence_after_a_fixed_block_retries_security_not_the_developer(self):
        c = SyntheticClientAdapter(Script(developer=[Step("CHANGED", files=_green(1)), Step("CHANGED", files=_green(2))],
                                          review=[Step.block(_block_in()), Step.passes()],
                                          security=[Step.passes(), Step.unrunnable()]))
        out = self.implement(c, retries=2)
        self.assertFalse(out.done)
        self.assertEqual(c.develop_calls, 2, "security could not run: that is not the developer's work")
        self.assertIn("SECURITY_UNRUNNABLE", out.blocked_reason, out.blocked_reason)


# --------------------------------------------------------------- CF-03 dirty tree + process crash (resume)
class TestCF03DirtyTreeThenCrashThenResume(_Case):
    def _crash_after_violation(self):
        c1 = SyntheticClientAdapter(Script(developer=[Step("SCOPE_VIOLATION", files={**_green(1), OUT: "# dirt\n"})]))
        out1 = self.implement(c1, retries=0)          # the run stops here: dirt on record, tree dirty — a crash-equivalent state
        self.assertFalse(out1.done)
        self.assertEqual((self.work / OUT).read_text(encoding="utf-8"), "# dirt\n")

    def test_attributable_dirt_is_restored_on_resume_and_the_story_completes(self):
        self._crash_after_violation()
        c2 = SyntheticClientAdapter(Script(developer=[Step("CHANGED", files=_green(2))]))
        out2 = self.implement(c2, retries=1)
        self.assertTrue(out2.done, out2.summary())
        rec = self.ev().of(NOTE, "retry:recovery")
        self.assertEqual([r.detail["tracked"] for r in rec], [[OUT]])
        self.assertEqual((self.work / OUT).read_text(encoding="utf-8"), (self.project / OUT).read_text(encoding="utf-8"))

    def test_unattributed_dirt_is_never_deleted_and_no_session_opens(self):
        self._crash_after_violation()
        mine = self.work / "ledgerlock" / "operator_notes.py"
        mine.write_text("mine\n", encoding="utf-8")
        c2 = SyntheticClientAdapter(Script(developer=[Step("CHANGED", files=_green(2))]))
        out2 = self.implement(c2, retries=1)
        self.assertFalse(out2.done)
        self.assertEqual(c2.develop_calls, 0)
        self.assertTrue(mine.exists() and mine.read_text(encoding="utf-8") == "mine\n")
        self.assertIn("operator_notes.py", out2.blocked_reason)


# --------------------------------------------------------------- CF-04 candidate freeze + crash before the evidence write
class TestCF04FreezeThenCrashBeforeEvidence(_Case):
    def test_a_committed_but_unrecorded_candidate_is_graded_on_resume_not_treated_as_a_noop(self):
        real = JournalStore.record

        def boom(self_, story_id, entry):
            if entry.step == "candidate.frozen":
                raise RuntimeError("process died between the commit and the journal write")
            return real(self_, story_id, entry)
        c1 = SyntheticClientAdapter(Script(developer=[Step("CHANGED", files=_green(1))]))
        with mock.patch.object(JournalStore, "record", boom):
            with self.assertRaises(RuntimeError):
                self.implement(c1)
        head = _git(self.work, "rev-parse", "HEAD")
        self.assertNotEqual(head, self.entry, "precondition: the candidate commit exists")
        self.assertEqual(self.ev().of(NOTE, "gate:verdict"), [], "precondition: nothing was graded")
        c2 = SyntheticClientAdapter(Script(developer=[Step.noop()]))
        out = self.implement(c2)
        self.assertTrue(out.done, out.summary())
        self.assertEqual(c2.develop_calls, 1)
        verdicts = self.ev().of(NOTE, "gate:verdict")
        self.assertEqual([v.detail.get("candidate") for v in verdicts], [head], "the verdict names the committed candidate")


# --------------------------------------------------------------- CF-06 duplicate (replayed) event after resume
class TestCF06DuplicateEventAfterResume(unittest.TestCase):
    # GREEN since F1 (CF-06 identity-bound staleness), 2026-09-16
    def test_a_replayed_old_record_never_outranks_the_candidates_own_result(self):
        C1, C2 = "1" * 40, "2" * 40
        events = [Event(kind=TOOL_RUN, name="test", ok=True, detail={"candidate": C1}),
                  Event(kind=TOOL_RUN, name="lint", ok=True, detail={"candidate": C1}),
                  Event(kind=TOOL_RUN, name="test", ok=False, detail={"candidate": C2, "tail": "1 failed"}),
                  Event(kind=TOOL_RUN, name="lint", ok=True, detail={"candidate": C2}),
                  Event(kind=TOOL_RUN, name="test", ok=True, detail={"candidate": C1})]      # the duplicate, appended on resume
        ev = Evidence(story_id="S", events=[Event(seq=i + 1, at=float(i + 1), **e.__dict__ | {"seq": i + 1, "at": float(i + 1)}) if False else e for i, e in enumerate(events)])
        for i, e in enumerate(ev.events):
            e.seq, e.at = i + 1, float(i + 1)
        g = G.evaluate("S", ev, changed=["src/a.py"], write_scope=["src"], screens=[], contract=["unit"], candidate=C2)
        test = next(c for c in g.checks if c.name == "test")
        ident = next(c for c in g.checks if c.name == "evidence matches candidate")
        self.assertIs(test.outcome, Outcome.FAILED, f"the candidate's own red run must be the verdict: {test.detail}")
        self.assertIs(ident.outcome, Outcome.PASSED, f"a replayed record of another build is not staleness of this one: {ident.detail}")


# --------------------------------------------------------------- CF-08 baseline change attempt during resume
class TestCF08BaselineDuringResume(_Case):
    def test_the_baseline_stays_the_epochs_root_after_main_advanced(self):
        c1 = SyntheticClientAdapter(Script(developer=[Step("CHANGED", files=_green(1))], review=[Step.block(_block_in())]))
        out1 = self.implement(c1, retries=0)
        self.assertFalse(out1.done)
        (self.project / "README.md").write_text("main moved\n", encoding="utf-8")
        _git(self.project, "add", "-A"); _git(self.project, "commit", "-qm", "main advanced")
        _git(self.work, "merge", "-q", "--no-edit", _git(self.project, "rev-parse", "--abbrev-ref", "HEAD"))   # the run loop's refresh
        c2 = SyntheticClientAdapter(Script(developer=[Step("CHANGED", files=_green(2))]))
        out2 = self.implement(c2, retries=1)
        self.assertTrue(out2.done, out2.summary())
        base = [e for e in self.ev().of(TOOL_RUN, "test:baseline")]
        roots = {str(e.detail.get("root") or e.detail.get("parent") or "") for e in base}
        # D-033: one capture per (story, epoch) at the story-entry parent; the resume REUSES it (no second capture)
        self.assertEqual(roots, {self.entry}, f"the baseline root must stay the epoch's parent after main advanced: {roots}")
        self.assertEqual(len(base), 1, "the resume reused the epoch's baseline instead of re-capturing at the new fork point")


# --------------------------------------------------------------- CF-09 client drift during replay
class TestCF09ClientDriftDuringReplay(unittest.TestCase):
    @unittest.expectedFailure   # INV-S.1 MISSING (Phase 17) — no replay manifest / preflight exists yet
    def test_a_replay_declared_for_opencode_but_run_with_claude_stops_before_the_first_agent_call(self):
        from aisef.control import replay  # noqa: F401  — ImportError IS the red result today
        source = replay.ReplayManifest(framework_version="1.7.6", client="opencode", client_version="1.18.29", model="mycombo",
                                       route="9router", config_digest="c", requirements_digest="r", story_contract_digests={},
                                       environment_digest="e", sandbox_digests={}, baseline_identities={}, source_run="run-1")
        requested = replay.ReplayManifest(**{**source.__dict__, "client": "claude", "client_version": "2.0"})
        drift = replay.preflight(requested, source)
        self.assertTrue(drift.material)
        self.assertIn("client", drift.fields)


# --------------------------------------------------------------- run-level compound scenarios
class _RunCase(RunTestCase):
    def runTest(self):
        pass


class TestCF05EvidenceWrittenThenCrashBeforeStateUpdate(_RunCase):
    """The gate PASSED and its verdict was written; the process died before `verification.completed`. The
    candidate is frozen on the branch with a fresh passing verdict — the rerun must converge to DONE."""

    def _crash_after_the_verdict(self):
        real = R.StoryRunTransaction.record

        def boom(self_, step, **data):
            if step == "verification.completed":
                raise RuntimeError("process died after the evidence was written, before the state update")
            return real(self_, step, **data)
        with mock.patch.object(R.StoryRunTransaction, "record", boom):
            with self.assertRaises(RuntimeError):
                self.run_sprint(Agent(), only_epic="EPIC-01")
        self.assertEqual(str(self.state().stories["STORY-01-01"].status), str(StoryStatus.RUNNING.value),
                         "precondition: the crash left an orphaned RUNNING claim")

    def test_the_rerun_reconciles_the_orphaned_claim(self):
        self._crash_after_the_verdict()
        report = self.run_sprint(Agent(), only_epic="EPIC-01")
        self.assertTrue(report.reconciled, "the orphaned transaction is reconciled before any new session")
        self.assertNotEqual(str(self.state().stories["STORY-01-01"].status), str(StoryStatus.RUNNING.value))

    # GREEN since F1 (SS-61), 2026-09-16
    def test_the_rerun_converges_to_done_with_exactly_one_integration(self):
        self._crash_after_the_verdict()
        report = self.run_sprint(Agent(), only_epic="EPIC-01")
        self.assertFalse(report.error, report.error)
        st = self.state()
        self.assertEqual(str(st.stories["STORY-01-01"].status), str(StoryStatus.DONE.value),
                         f"a verified candidate with a fresh PASS must reach DONE on rerun: {st.stories['STORY-01-01']}")
        log = subprocess.run(["git", "log", "--oneline", "--", "src/core/STORY-01-01.py"], cwd=self.project, capture_output=True,
                             text=True, encoding="utf-8").stdout.strip().splitlines()
        self.assertEqual(len(log), 1, f"exactly one integration of the story's work: {log}")


class TestCF10MergeConflictAfterVerification(_RunCase):
    def test_a_trunk_conflict_after_the_gate_passed_is_typed_never_done_and_keeps_the_branch(self):
        real = WorktreeManager.merge_wave

        def conflict_then_merge(self_, story_ids, **kw):
            p = self.project / "src" / "core" / "STORY-01-01.py"      # the story's scope is src/core
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# trunk wrote here first\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
            subprocess.run(["git", "commit", "-qm", "trunk"], cwd=self.project, check=True)
            return real(self_, story_ids, **kw)
        with mock.patch.object(WorktreeManager, "merge_wave", conflict_then_merge):
            report = self.run_sprint(Agent(), only_epic="EPIC-01", sequential=True)
        st = self.state()
        self.assertIsNot(st.stories["STORY-01-01"].status, StoryStatus.DONE, "a conflicted merge is never DONE")
        self.assertTrue(report.stopped_at or report.error, "the run stops at the conflict and says so")
        branches = subprocess.run(["git", "branch", "--list", "story/STORY-01-01"], cwd=self.project, capture_output=True,
                                  text=True, encoding="utf-8").stdout
        self.assertIn("story/STORY-01-01", branches, "the verified work is preserved on its branch")
        trunk = (self.project / "src" / "core" / "STORY-01-01.py").read_text(encoding="utf-8")
        self.assertEqual(trunk, "# trunk wrote here first\n", "the trunk is never overwritten by a conflicted merge")


class _LeavesAServer(Agent):
    """A developer session that starts a dev server and forgets it — the grandchild the story must not orphan."""

    def __init__(self):
        super().__init__()
        self.children: list[subprocess.Popen] = []

    def run(self, spec: RunSpec) -> RunResult:
        if spec.prompt.lstrip().startswith("# ") and not spec.prompt.lstrip().startswith("# Review") and not spec.prompt.lstrip().startswith("# Security review"):
            self.children.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], cwd=spec.workdir,
                                                  start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        return super().run(spec)


@unittest.skipIf(os.name == "nt", "process groups: POSIX semantics; the Windows tree kill is covered by tests/test_clients.py")
class TestCF11OrphanProcessDuringCleanup(_RunCase):
    @unittest.expectedFailure   # F5 — the kernel owns no per-story process tree; a grandchild left by the session survives workspace removal
    def test_a_process_left_by_the_session_is_dead_before_the_workspace_is_removed(self):
        agent = _LeavesAServer()
        try:
            self.run_sprint(agent, only_epic="EPIC-01", sequential=True)
            self.assertTrue(agent.children, "precondition: a developer session ran and left a process")
            alive = []
            for p in agent.children:
                try:
                    os.kill(p.pid, 0)
                    alive.append(p.pid)
                except ProcessLookupError:
                    pass
            self.assertEqual(alive, [], f"survivors after the story's workspace was removed: {alive}")
        finally:
            for p in agent.children:
                try:
                    p.kill(); p.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass


class TestCF12ApprovalInvalidationDuringResume(unittest.TestCase):
    def _store(self, root: Path) -> ApprovalStore:
        (root / "prd.md").write_text("# PRD v1\n", encoding="utf-8")
        (root / "architecture.md").write_text("# Arch v1\n", encoding="utf-8")
        (root / "stories.index.json").write_text('{"epics": []}\n', encoding="utf-8")
        store = ApprovalStore(root)
        for g in (Gate.PRD, Gate.ARCHITECTURE, Gate.STORIES, Gate.READINESS):
            try:
                store.approve(g, by="owner")
            except Exception:  # noqa: BLE001 — a gate whose artifact this fixture lacks
                pass
        return store

    def test_the_cli_precheck_blocks_a_resume_after_an_upstream_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = self._store(root)
            (root / "prd.md").write_text("# PRD v2 — scope changed while the run was stopped\n", encoding="utf-8")
            self.assertIs(store.status(Gate.PRD), Status.STALE)
            self.assertIn(Gate.PRD, store.blocking(Gate.READINESS), "the resume entry point (aisef run) sees the cascade")

    @unittest.expectedFailure   # SS-56 (F6) — programmatic status cascades only on a new upstream DECISION, not on an upstream edit
    def test_the_programmatic_readiness_status_is_stale_after_an_upstream_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = self._store(root)
            (root / "prd.md").write_text("# PRD v2\n", encoding="utf-8")
            self.assertIs(store.status(Gate.READINESS), Status.STALE)


if __name__ == "__main__":
    unittest.main()
