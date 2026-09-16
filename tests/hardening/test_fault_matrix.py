"""Phase 7 — fault-injection matrix: the cells that are not already covered by an existing suite
(closure-evidence/hardening/fault-matrix.json names the test for every cell). Faults are injected through
the synthetic client (aisef/clients/synthetic.py) or the harness's own fixtures; no model calls.
RED cells are expected failures naming the registered defect."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.clients.stream import RunResult  # noqa: E402
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter  # noqa: E402
from aisef.control.worktree import WorktreeManager, commit_paths  # noqa: E402
from aisef.harness.observe import EvidenceStore, Event, NOTE, TOOL_RUN  # noqa: E402
from tests.test_implement import ImplementTestCase  # noqa: E402
from tests.test_retry_hygiene import HygieneCase  # noqa: E402


class _Case(ImplementTestCase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)

    def run_script(self, script, **cfg):
        c = SyntheticClientAdapter(script)
        out = self.implement(c, config=self.config(**cfg)) if cfg else self.implement(c)
        return c, out


class _ZeroOutput(SyntheticClientAdapter):
    def _developer(self, step, spec):
        return RunResult(ok=True, text="I would implement this by …", num_turns=2, output_tokens=300)


class TestDeveloperFaults(_Case):
    def test_quality_block_retries_the_developer_once(self):
        c, out = self.run_script(Script(review=[Step.block(), Step.passes()]))
        self.assertTrue(out.done, out.summary())
        # quality_attempts counts every graded attempt (the blocked one and the passing one), never infra
        self.assertEqual((c.develop_calls, out.quality_attempts), (2, 2))

    def test_provider_crash_is_infra_and_the_story_still_completes(self):
        c, out = self.run_script(Script(developer=[Step.crash(), Step.changed()]))
        self.assertTrue(out.done, out.summary())
        self.assertTrue(out.attempts[0].infra, "a 5xx is not the developer's work")
        self.assertEqual(out.quality_attempts, 1, "only the graded attempt counts")

    def test_timeout_with_untouched_tree_is_infra(self):
        c, out = self.run_script(Script(developer=[Step.timeout(), Step.changed()]))
        self.assertTrue(out.done, out.summary())
        self.assertTrue(out.attempts[0].infra)
        self.assertEqual(out.quality_attempts, 1)

    def test_zero_output_session_is_fatal_not_quality(self):
        c = _ZeroOutput(Script())
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertTrue(out.attempts[0].fatal and out.attempts[0].infra)
        self.assertIn("0 tool calls", out.blocked_reason)
        self.assertEqual(c.develop_calls, 1)

    # GREEN since F2 (SS-59: zero output on a retry is fatal), 2026-09-16
    def test_zero_output_on_a_retry_is_still_fatal_not_a_noop_decision(self):
        c, out = self.run_script(Script(developer=[Step.changed(), Step("ZERO_OUTPUT"), Step("ZERO_OUTPUT")],
                                        review=[Step.block(), Step.passes()]))
        self.assertFalse(out.done)
        self.assertIn("0 tool calls", out.blocked_reason, out.blocked_reason)
        self.assertEqual(c.develop_calls, 2, "a fatal environment failure is not retried")

    def test_two_noops_with_nothing_frozen_end_the_story_without_quality_cost(self):
        c, out = self.run_script(Script(developer=[Step.noop()]))
        self.assertFalse(out.done)
        self.assertEqual(c.develop_calls, 2)
        self.assertEqual(out.quality_attempts, 0)
        self.assertIn("wrote nothing", out.blocked_reason)

    def test_auth_rejection_is_fatal_and_free(self):
        c, out = self.run_script(Script(developer=[Step.auth(), Step.changed()]))
        self.assertFalse(out.done)
        self.assertEqual(c.develop_calls, 1)
        self.assertEqual(out.quality_attempts, 0)
        self.assertTrue(out.attempts[0].fatal)

    def test_trunk_commit_is_an_isolation_breach(self):
        case = HygieneCase("runTest"); case.setUp()
        try:
            c = SyntheticClientAdapter(Script(developer=[Step.trunk_commit({"len-thang.py": "x\n"})]))
            out = case.implement(c)
            self.assertFalse(out.done)
            self.assertTrue(out.attempts[0].fatal, out.summary())
            self.assertIn("main branch moved", out.blocked_reason)
        finally:
            case.tearDown()


class TestToolFaults(_Case):
    def test_red_suite_is_a_quality_failure(self):
        c, out = self.run_script(Script(), **{"tools.test": "false"})
        self.assertFalse(out.done)
        self.assertIn("did not pass gate", out.blocked_reason)
        self.assertTrue(any(x.name == "test" and not x.passed for x in out.attempts[0].gate.failures))

    def test_missing_runner_is_unrunnable_not_red(self):
        from aisef.control.outcome import Outcome
        c, out = self.run_script(Script(), **{"tools.test": "aisef-no-such-runner-xyz"})
        check = next(x for x in out.attempts[0].gate.checks if x.name == "test")
        self.assertIs(check.outcome, Outcome.UNRUNNABLE, check.detail)

    def test_red_lint_is_a_quality_failure(self):
        c, out = self.run_script(Script(), **{"tools.lint": "false"})
        self.assertFalse(out.done)
        self.assertTrue(any(x.name == "lint" for x in out.attempts[0].gate.failures))

    # GREEN since F2 (SS-58: absence is never a verdict; a missing linter is unrunnable), 2026-09-16
    def test_missing_linter_is_unrunnable(self):
        from aisef.control.outcome import Outcome
        c, out = self.run_script(Script(), **{"tools.lint": "aisef-no-such-linter-xyz"})
        check = next(x for x in out.attempts[0].gate.checks if x.name == "lint")
        self.assertIs(check.outcome, Outcome.UNRUNNABLE, check.detail)


class TestSandboxIdentityFaults(unittest.TestCase):
    """FM-N-03 (INV-N.2): the environment identity — image name and digest — is recorded with EVERY sandboxed tool
    result, the failed ones included: a timed-out run and a docker that cannot be invoked still name the image they
    were meant to run in. Phase 11 (2026-09-17): `_run_docker` returned both without `image`/`image_id`."""

    def _docker(self, boom):
        from unittest import mock
        from aisef.harness import sandbox as SB
        from aisef.harness import verify_image as VI
        spec = SB.SandboxSpec(workspace=Path("."), cmd=["true"], image="ghcr.io/x/ci:1", timeout_seconds=1)
        with mock.patch.object(VI, "ensure", return_value=""), \
             mock.patch.object(VI, "image_id", return_value="sha256:feedface"), \
             mock.patch.object(SB.subprocess, "run", side_effect=[boom, mock.Mock(returncode=0)]):   # 2nd: `docker rm`
            return SB._run_docker(spec)

    def test_a_timed_out_run_still_records_image_and_digest(self):
        import subprocess as sp
        res = self._docker(sp.TimeoutExpired(cmd="docker", timeout=1))
        self.assertTrue(res.timed_out)
        self.assertEqual((res.image, res.image_id), ("ghcr.io/x/ci:1", "sha256:feedface"), res.to_evidence())

    def test_a_docker_that_cannot_be_invoked_still_records_image_and_digest(self):
        res = self._docker(OSError("docker: not found"))
        self.assertTrue(res.provider_error)
        self.assertEqual((res.image, res.image_id), ("ghcr.io/x/ci:1", "sha256:feedface"), res.to_evidence())


class TestReviewFaults(_Case):
    def test_structured_block_is_developer_feedback(self):
        c, out = self.run_script(Script(review=[Step.block([{"tag": "block", "file": "src/a.py", "line": 1, "why": "off by one"}]), Step.passes()]))
        self.assertTrue(out.done, out.summary())
        self.assertTrue(any("off by one" in f for f in out.attempts[0].review_findings), out.attempts[0].review_findings)

    # GREEN since F2 (SS-57: absence is never a verdict; a missing linter is unrunnable), 2026-09-16
    def test_a_malformed_verdict_never_passes_the_review(self):
        c, out = self.run_script(Script(review=[Step.malformed()]))
        self.assertFalse(out.done, "no structured verdict exists — nothing may PASS the review")
        self.assertIn("REVIEW_UNRUNNABLE", out.blocked_reason or "")

    def test_reviewer_mutation_is_reverted_and_the_review_retried(self):
        c, out = self.run_script(Script(review=[Step.mutate({"src/reviewer.py": "x = 2\n"}), Step.passes()]))
        self.assertTrue(out.done, out.summary())
        self.assertFalse((self.project / "src" / "reviewer.py").exists())
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        self.assertTrue(any(e.name == "review:immutable" for e in ev.events))
        self.assertEqual(c.develop_calls, 1)

    def test_structured_stuck_is_a_plan_conflict_not_developer_work(self):
        c, out = self.run_script(Script(review=[Step.stuck()]))
        self.assertFalse(out.done)
        self.assertIn("deadlock due to plan", out.blocked_reason)
        self.assertEqual(c.develop_calls, 1)


class TestSecurityFaults(_Case):
    def test_security_block_is_developer_feedback(self):
        c, out = self.run_script(Script(security=[Step.block(), Step.passes()]))
        self.assertTrue(out.done, out.summary())
        self.assertEqual(c.develop_calls, 2)
        self.assertTrue(any(x.name == "security" for x in out.attempts[0].gate.failures))

    # GREEN since F2 (SS-13: absence is never a verdict; a missing linter is unrunnable), 2026-09-16
    def test_malformed_security_report_is_unrunnable_not_a_verdict(self):
        from aisef.control.outcome import Outcome
        c, out = self.run_script(Script(security=[Step.malformed()]))
        check = next(x for x in out.attempts[0].gate.checks if x.name == "security")
        self.assertIs(check.outcome, Outcome.UNRUNNABLE, check.detail)
        self.assertEqual(c.develop_calls, 1)


class TestMergeFaults(unittest.TestCase):
    def test_conflict_hands_to_the_human_and_never_marks_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
                subprocess.run(cmd, cwd=repo, check=True)
            (repo / "src").mkdir(); (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True); subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
            wm = WorktreeManager(repo)
            wt = wm.create("STORY-01-01").path
            (wt / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
            commit_paths(wt, "candidate", paths=["src"])
            cand = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True, encoding="utf-8").stdout.strip()
            (repo / "src" / "a.py").write_text("x = 3\n", encoding="utf-8")   # the trunk moved on the same line
            subprocess.run(["git", "commit", "-qam", "trunk"], cwd=repo, check=True)
            res = wm.merge_story("STORY-01-01", expected_candidate=cand)
            self.assertFalse(res.merged)
            self.assertTrue(res.conflicts or "conflict" in res.message.lower() or "re-verification" in res.message, res.message)


class TestEvidenceFaults(unittest.TestCase):
    def test_a_corrupt_evidence_line_is_skipped_not_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp))
            store.record("S", Event(kind=TOOL_RUN, name="test", ok=True, detail={"candidate": "abc"}))
            path = next(Path(tmp).rglob("S.jsonl"))
            with path.open("a", encoding="utf-8") as f:
                f.write('{"kind": "tool_run", "name": "lint", "ok": true, "detail": {"cand\n')   # truncated by a crash
            store.record("S", Event(kind=NOTE, name="after", ok=True))
            ev = store.read("S")
            self.assertEqual([e.name for e in ev.events], ["test", "after"])
            self.assertIsNone(ev.last(TOOL_RUN, "lint"), "a half-written record is no record")


class TestEvidenceValidityFaults(unittest.TestCase):
    """FM-E-07 (INV-E.2): three records that each LOOK valid by a reading the kernel once used — the LATEST record
    (written last, at another candidate), a record that EXISTS (legacy, candidate-only, schema 1) and a record whose
    candidate SHA MATCHES but whose tree digest differs (the D-035 shape) — and the freshness readers score none of
    them: no record is fresh for the identity being decided on, and the stale one is named with its reason."""

    def test_latest_exists_and_sha_match_each_score_nothing(self):
        from aisef.control.gate import _stale_for
        from aisef.control.identity import EvidenceIdentity
        sha = "c" * 40
        now = EvidenceIdentity(story_id="S", story_epoch="e1", candidate_sha=sha, tree_state_digest="tree-now",
                               verifier_config_digest="cfg", environment_digest="env", baseline_root="r" * 40, stage="gate")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # SHA MATCHES, tree differs: the verdict was computed over another tree of the same commit
            EvidenceStore(root, identity=EvidenceIdentity(**{**now.__dict__, "tree_state_digest": "tree-before"})
                          ).tool_run("S", "test", ok=True)
            # EXISTS: a legacy record — candidate only, no identity (schema 1)
            EvidenceStore(root, candidate=sha).tool_run("S", "lint", ok=True)
            # LATEST: the newest record of all, at another candidate
            EvidenceStore(root, identity=EvidenceIdentity(**{**now.__dict__, "candidate_sha": "d" * 40})
                          ).tool_run("S", "test", ok=True)
            ev = EvidenceStore(root).read("S")
            self.assertEqual(len(ev.of(TOOL_RUN)), 3, "three records exist, all green")
            for name in ("test", "lint"):
                self.assertIsNone(ev.last_fresh(TOOL_RUN, name, now), f"{name}: a record that is not fresh scores nothing")
            self.assertEqual(ev.for_identity(now).of(TOOL_RUN), [], "nothing speaks for the identity being decided on")
            stale = _stale_for(ev, now)
            self.assertIn("test", stale, stale)
            self.assertTrue(stale["test"], "the stale record is named with its reason, never silently dropped")
            # control: the same readers DO accept a record written under exactly this identity
            EvidenceStore(root, identity=now).tool_run("S", "test", ok=True)
            self.assertIsNotNone(EvidenceStore(root).read("S").last_fresh(TOOL_RUN, "test", now))


class TestStaleFaults(unittest.TestCase):
    """Stale evidence replayed against a changed tree (FM-D-07 / FM-E-03) — the D-035 scenario."""

    # GREEN since F1 (D-035), 2026-09-16
    def test_a_stale_verdict_is_not_reused_after_hygiene_changed_the_tree(self):
        from tests.hardening.test_verdict_freshness import reproduce
        case = HygieneCase("runTest"); case.setUp()
        try:
            f = reproduce(case)
            self.assertTrue(f["regraded_after_recovery"], f["gate_verdicts"])
            self.assertTrue(f["done"], f["blocked_reason"])
        finally:
            case.tearDown()


class TestWorkspaceFaults(unittest.TestCase):
    """Dirty workspace, pre-existing dirt, generated harness dirt, scope violation — through the synthetic client."""

    def _case(self):
        case = HygieneCase("runTest"); case.setUp()
        return case

    def test_pre_existing_dirt_blocks_before_any_session_and_is_never_deleted(self):
        case = self._case()
        try:
            mine = case.work / "ledgerlock" / "operator_notes.py"
            mine.write_text("mine\n", encoding="utf-8")
            c = SyntheticClientAdapter(Script())
            out = case.implement(c)
            self.assertEqual(c.develop_calls, 0)
            self.assertEqual(mine.read_text(encoding="utf-8"), "mine\n")
            self.assertIn("operator_notes.py", out.blocked_reason)
        finally:
            case.tearDown()

    def test_generated_harness_dirt_is_preserved_and_never_a_violation(self):
        case = self._case()
        try:
            (case.work / ".opencode" / "plugin").mkdir(parents=True)
            (case.work / ".opencode" / "plugin" / "g.ts").write_text("// guard\n", encoding="utf-8")
            files = {"ledgerlock/cli.py": "def main(argv=None):\n    return 1\n", ".coverage": "\x00"}
            c = SyntheticClientAdapter(Script(developer=[Step.changed(files)]))
            out = case.implement(c)
            self.assertTrue(out.done, out.summary())
            self.assertTrue((case.work / ".opencode" / "plugin" / "g.ts").exists())
            ev = EvidenceStore(case.artifacts).read(case.story.id)
            self.assertEqual([e for e in ev.of(NOTE, "write-scope:violation")], [])
        finally:
            case.tearDown()

    def test_a_scope_violation_is_restored_before_the_retry_and_the_story_completes(self):
        case = self._case()
        try:
            bad = {"ledgerlock/cli.py": "def main(argv=None):\n    return 1\n", "ledgerlock/ledger.py": "# reformatted\n"}
            good = {"ledgerlock/cli.py": "def main(argv=None):\n    return 2\n"}
            c = SyntheticClientAdapter(Script(developer=[Step.scope_violation(bad), Step.changed(good)]))
            out = case.implement(c, retries=1)
            self.assertTrue(out.done, out.summary())
            self.assertEqual(c.develop_calls, 2)
            ev = EvidenceStore(case.artifacts).read(case.story.id)
            self.assertEqual([e.detail["tracked"] for e in ev.of(NOTE, "retry:recovery")], [["ledgerlock/ledger.py"]])
        finally:
            case.tearDown()


class TestProcessFaults(unittest.TestCase):
    """Liveness: a claim of a dead process is orphaned, a live one is not (kill-tree cells cite the existing suites)."""

    def test_a_dead_claim_is_orphaned_and_a_live_one_is_not(self):
        import os
        import socket
        from aisef.control.state import claim_is_orphaned
        self.assertFalse(claim_is_orphaned(f"{socket.gethostname()}:{os.getpid()}"))
        self.assertTrue(claim_is_orphaned(f"{socket.gethostname()}:{2**22 + 12345}"))


class TestReplayFaults(unittest.TestCase):
    """FM-X-01: a replay with a different client / model than the source is stopped BEFORE execution."""

    # GREEN since Phase 17 (INV-S.1: replay manifest + preflight), 2026-09-17
    def test_client_drift_is_detected_before_execution(self):
        from tests.hardening.test_replay_contract import TestCliStopsBeforeTheFirstAgentCall as T
        T("test_client_drift_stops_the_run_with_a_typed_record_and_no_agent_call").test_client_drift_stops_the_run_with_a_typed_record_and_no_agent_call()


if __name__ == "__main__":
    unittest.main()
