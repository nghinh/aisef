"""Phase 8a — discovery-debt group B: deterministic reproducers for the NEEDS_TEST sites SS-08, SS-09,
SS-16, SS-19, SS-20, SS-21, SS-22, SS-A10, SS-A15, SS-C2, SS-T1, SS-X1 of
closure-evidence/hardening/sibling-scan.json. Every test asserts the INVARIANT (docs/INVARIANTS.md);
a red one is marked ``expectedFailure`` under its SS id with the observed wrong behaviour, a green one is
kept as a negative control stating which guard makes the code safe by construction. No model, no network,
no Docker (tests/__init__.py swaps the host provider in).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.cli import EXIT_OK, main as cli_main  # noqa: E402
from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter  # noqa: E402
from aisef.control import gate  # noqa: E402
from aisef.control.budget import BudgetConfig, BudgetGuard, BudgetLedger  # noqa: E402
from aisef.control.journal import JournalStore  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.state import StoryStatus  # noqa: E402
from aisef.control.tdd import red_before_green  # noqa: E402
from aisef.control.worktree import WorktreeManager  # noqa: E402
from aisef.harness.guardrails import head_sha  # noqa: E402
from aisef.harness.observe import NOTE, TOOL_RUN, Event, Evidence, EvidenceStore  # noqa: E402
from aisef.harness.tools import NOP_RUN  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from tests.test_implement import ImplementTestCase  # noqa: E402
from tests.test_retry_hygiene import CLI, LEDGER, SCOPE, SID as HSID, Developer, HygieneCase  # noqa: E402
from tests.test_run import RunTestCase  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SID = "STORY-01-01"
C1 = "1111111111111111111111111111111111111111"
C2 = "2222222222222222222222222222222222222222"
CLI_WORK = {"ledgerlock/cli.py": CLI + "\n\ndef repair(argv):\n    return 0\n"}
CLI_WORK2 = {"ledgerlock/cli.py": CLI + "\n\ndef repair(argv):\n    return 2\n"}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout.strip()


def _ev(*events) -> Evidence:
    return Evidence(story_id=SID, events=[Event(seq=i + 1, at=float(i + 1), **e) for i, e in enumerate(events)])


def _check(g, name):
    return next(c for c in g.checks if c.name == name)


def _mentions(ev: Evidence, *shas: str) -> list[Event]:
    """Events whose detail names every given SHA (a typed record about that state change)."""
    return [e for e in ev.events if all(s in json.dumps(e.detail) for s in shas)]


class _Case(ImplementTestCase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)

    def run_script(self, script, **cfg):
        c = SyntheticClientAdapter(script)
        return c, self.implement(c, config=self.config(**cfg))


# ---------------------------------------------------------------- FAM-IDENTITY / INV-D.3

class TestSS08MergeAuthorizationBindsTheVerifiedSha(RunTestCase):
    """SS-08 — `verification.completed` carries no SHA; the wave-end authorization derives the SHA from the
    last `candidate.frozen` by journal order. HEAD moved after verification → the merge must not take B."""

    def test_a_branch_tip_that_moved_after_verification_is_not_merged(self):
        real = I.implement_story

        def moved_after_verify(*a, **kw):
            out = real(*a, **kw)
            wt = Path(kw["workdir"])
            (wt / "src" / "core" / "late.py").write_text("late = 1\n", encoding="utf-8")
            _git(wt, "add", "src"); _git(wt, "commit", "-qm", "after verification")
            return out

        c = SyntheticClientAdapter(Script(developer=[Step.changed({"src/core/a.py": "x = 1\n"})]))
        with patch("aisef.phases.run.implement_story", side_effect=moved_after_verify):
            report = self.run_sprint(c, only_epic="EPIC-01")
        frozen = JournalStore(self.artifacts).read(SID).last("candidate.frozen").data["sha"]
        tip = _git(self.project, "rev-parse", f"story/{SID}")
        self.assertNotEqual(tip, frozen, "precondition: HEAD moved after verification")
        landed = subprocess.run(["git", "merge-base", "--is-ancestor", tip, "main"], cwd=self.project).returncode == 0
        self.assertFalse(landed, "an unverified SHA reached main")
        self.assertIsNot(self.state().stories[SID].state, StoryStatus.DONE, report.stopped_at)
        # NOT_A_DEFECT by construction: the authorized SHA is `candidate.frozen.sha` (the last freeze of the
        # transaction that wrote `verification.completed`), and `WorktreeManager._merge_story_inner`
        # (worktree.py:489-495) refuses when the branch tip != that SHA and merges the SHA, never the branch.
        self.assertIn("candidate changed", report.stopped_at)


# ---------------------------------------------------------------- FAM-RECOVERY / INV-E.1, INV-A.1

class TestSS09ResumeRefreshDoesNotSilentlyInvalidateTheCandidate(HygieneCase):
    """SS-09 — `run.py:616` merges main into the story branch before `_pending_review` looks for the
    REVIEW_UNRUNNABLE candidate at HEAD; HEAD is now a merge commit, nothing is found, a developer opens."""

    # GREEN since F1 (SS-09: typed invalidation when HEAD moved off the candidate of record), 2026-09-16
    def test_resume_after_main_advanced_retries_the_review_or_records_the_invalidation(self):
        c1 = SyntheticClientAdapter(Script(developer=[Step.changed(CLI_WORK)], review=[Step.unrunnable()]))
        out1 = self.implement(c1)
        self.assertIn("REVIEW_UNRUNNABLE", out1.blocked_reason)
        cand = out1.attempts[-1].candidate
        (self.project / "README.md").write_text("main moved\n", encoding="utf-8")
        _git(self.project, "add", "README.md"); _git(self.project, "commit", "-qm", "trunk advanced")
        WorktreeManager(self.project).create(HSID)            # run.py:616 — refresh=True on resume
        merged = head_sha(self.work)
        self.assertNotEqual(merged, cand, "precondition: the refresh moved HEAD off the frozen candidate")
        c2 = SyntheticClientAdapter(Script(developer=[Step.changed(CLI_WORK2)], review=[Step.passes()]))
        self.implement(c2)
        ev = EvidenceStore(self.artifacts).read(HSID)
        self.assertTrue(c2.develop_calls == 0 or _mentions(ev, cand, merged),
                        f"develop_calls={c2.develop_calls}: the frozen candidate {cand[:8]} was abandoned "
                        f"for {merged[:8]} with no invalidation record")


# ---------------------------------------------------------------- FAM-RECOVERY / INV-A.3, INV-E.1

class _WritesThenTimesOut(SyntheticClientAdapter):
    def _developer(self, step, spec):
        if step.kind == "TIMEOUT":
            self._write(Path(spec.workdir), {"src/core/late.py": "late = 1\n"})   # in scope, never frozen
        return super()._developer(step, spec)


class TestSS16WaveEndCommitOfAFailedStoryIsRecorded(RunTestCase):
    """SS-16 — `run.py:371-381` commits a failed story's leftover in-scope work on top of the frozen
    candidate and removes the worktree; nothing in evidence or the journal names the new branch tip."""

    # GREEN since F1 (SS-16: wave-end commit of leftover work is recorded as a moved tip), 2026-09-16
    def test_leftover_work_committed_at_wave_end_is_named_by_a_record(self):
        c = _WritesThenTimesOut(Script(developer=[Step.changed({"src/core/a.py": "x = 1\n"}), Step.timeout()],
                                       review=[Step.block(), Step.passes()]))
        self.run_sprint(c, only_epic="EPIC-01",
                        config=self.config(**{"run.max_retries": 1, "run.infra_retries": 1}))
        journal = JournalStore(self.artifacts).read(SID)
        frozen = journal.last("candidate.frozen").data["sha"]
        tip = _git(self.project, "rev-parse", f"story/{SID}")
        self.assertNotEqual(tip, frozen, "precondition: the wave end committed the leftover work")
        ev = EvidenceStore(self.artifacts).read(SID)
        named = _mentions(ev, tip) + [e for e in journal.entries if tip in json.dumps(e.data)]
        self.assertTrue(named, f"branch tip {tip[:8]} != frozen candidate {frozen[:8]} and no record names it")


# ---------------------------------------------------------------- FAM-RETRY / INV-G.1

ITEM = {"id": "AC-STORY-00-01-1", "kind": "ac", "story": "STORY-00-01", "source": {}, "via": "STORY-00-01"}


class TestSS19CoBlockingUnrunnableKeepsTheReviewerAbsenceAtTheReviewStage(_Case):
    """SS-19 — `_only_review_unrunnable` demands `failures == ["review"]`; a second UNRUNNABLE check
    (here: a preservation item unverifiable at the candidate) routes the reviewer's absence back to a
    developer session. (A missing test runner is not usable as the co-blocker: it also makes
    `criteria have tests` FAILED, and a FAILED check legitimately reopens the developer.)"""

    @unittest.expectedFailure   # SS-19: gate failures were review+preservation, both UNRUNNABLE, yet develop_calls=2 and the review stage was never retried
    def test_two_unrunnable_checks_never_open_a_developer(self):
        with patch.object(I, "preservation_items", return_value=[dict(ITEM)]):
            c, out = self.run_script(Script(review=[Step.unrunnable()]))
        g = out.attempts[0].gate
        self.assertIs(_check(g, "review").outcome, Outcome.UNRUNNABLE)
        others = [x for x in g.failures if x.name != "review"]
        self.assertTrue(others and all(x.outcome is Outcome.UNRUNNABLE for x in others),
                        [(x.name, x.outcome.value) for x in g.failures])
        self.assertEqual(c.develop_calls, 1,
                         f"nothing deterministic failed, yet a developer was reopened: {[x.step for x in c.calls]}")


# ---------------------------------------------------------------- FAM-RECOVERY / INV-D.1

class _LedgerMovesDuringReview(SyntheticClientAdapter):
    """Another story's behaviour becomes VERIFIED while this reviewer is (not) running."""
    moved = False

    def _review(self, step, spec):
        if step.kind == "UNRUNNABLE":
            self.moved = True
        return super()._review(step, spec)


class TestSS20ReviewRetryScoresThePinnedPreservationList(_Case):
    """SS-20 — R4 pins the preservation list once per attempt (`run_attempt`); `_review_stage` recomputes
    it from the ledger, so the re-review of the same candidate is scored against a different list."""

    # GREEN since F1 (SS-20: the review-stage retry scores the list pinned in the attempt's gate:input), 2026-09-16
    def test_the_review_stage_retry_uses_the_list_the_attempt_was_pinned_to(self):
        c = _LedgerMovesDuringReview(Script(review=[Step.unrunnable(), Step.passes()]))
        with patch.object(I, "preservation_items", side_effect=lambda *a, **k: [dict(ITEM)] if c.moved else []) as pi:
            self.implement(c, config=self.config(**{"run.max_retries": 0}))
        self.assertGreaterEqual(pi.call_count, 1)   # F1: the retry reads the pinned list, it no longer recomputes
        inputs = EvidenceStore(self.artifacts).read(self.story.id).of(NOTE, "gate:input")
        self.assertEqual(len(inputs), 2, [e.detail.get("attempt") for e in inputs])
        self.assertEqual(inputs[0].detail["attempt"], inputs[1].detail["attempt"], "same attempt, review retried")
        self.assertEqual(inputs[1].detail["preservation"], inputs[0].detail["preservation"],
                         "the re-review scored a preservation list the candidate was not written against")


# ---------------------------------------------------------------- FAM-RETRY / INV-G.5

_HOLD_LOCK = ("import sys, time\nfrom aisef._compat import flock_ex_nb, open_lock_fd\n"
              "flock_ex_nb(open_lock_fd(sys.argv[1])); print('locked', flush=True); time.sleep(60)\n")


class TestSS21BudgetLockContentionIsInfraNotACap(_Case):
    """SS-21 — `BudgetGuard.reserve` raises BudgetExceeded when the ledger lock is merely held by another
    writer; `run_attempt` charges every BudgetExceeded to quality and words it as a cap."""

    @unittest.expectedFailure   # SS-21: attempt.infra=False, quality_attempts=2, error="budget exceeded: budget ledger locked by another writer (...)"
    def test_a_held_ledger_lock_is_an_environment_outcome(self):
        guard = BudgetGuard(BudgetLedger(self.project))
        guard.configure(BudgetConfig(cap_usd=100.0))
        c = SyntheticClientAdapter(Script())
        c.attach_budget_guard(guard)
        holder = subprocess.Popen([sys.executable, "-c", _HOLD_LOCK, str(guard.ledger.lock_path)], cwd=ROOT,
                                  stdout=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            out = self.implement(c)
        finally:
            holder.kill(); holder.wait()
        a = out.attempts[0]
        self.assertEqual(c.develop_calls, 0, "precondition: the reservation failed before dispatch")
        self.assertTrue(a.infra, f"lock contention charged to quality: infra={a.infra} error={a.error!r}")
        self.assertEqual(out.quality_attempts, 0)
        self.assertFalse(a.error.startswith("budget exceeded"), a.error)


# ---------------------------------------------------------------- FAM-RECOVERY / INV-C.1, INV-D.1

class TestSS22NopParentMatchesTheBaselineRoot(HygieneCase):
    """SS-22 — `implement_story` recomputes `base_ref` (fork point) on every call; after a refresh the
    baseline is reused at its recorded root while `run_nop` builds the parent at the new fork point."""

    # GREEN since F1 (SS-22), 2026-09-16
    def test_the_nop_control_runs_at_the_baseline_root_or_records_the_mismatch(self):
        test_file = "def test_AC_STORY_04_01_1_repair():\n    pass\n"
        c1 = SyntheticClientAdapter(Script(developer=[Step.changed({**CLI_WORK, SCOPE[1]: test_file})]))
        self.implement(c1, retries=0)
        (self.project / "README.md").write_text("main moved\n", encoding="utf-8")
        _git(self.project, "add", "README.md"); _git(self.project, "commit", "-qm", "trunk advanced")
        WorktreeManager(self.project).create(HSID)            # resume: refresh merges main
        c2 = SyntheticClientAdapter(Script(developer=[Step.changed({**CLI_WORK2, SCOPE[1]: test_file + "\n"})]))
        self.implement(c2, retries=0)
        ev = EvidenceStore(self.artifacts).read(HSID)
        root = gate.authoritative_baseline(ev).detail.get("root")
        nop = ev.last(TOOL_RUN, NOP_RUN)
        self.assertEqual(root, self.entry, "precondition: the baseline is reused at the story-entry root")
        self.assertTrue(nop.detail.get("parent") == root or _mentions(ev, root, nop.detail.get("parent", "")),
                        f"nop ran at parent {nop.detail.get('parent', '')[:8]} while the baseline root is {root[:8]}")


# ---------------------------------------------------------------- FAM-RECOVERY / INV-K.3

def _dirty_then_stage_nothing(work: Path) -> None:
    (work / "ledgerlock" / "cli.py").write_text(CLI_WORK["ledgerlock/cli.py"], encoding="utf-8")
    (work / "ledgerlock" / "ledger.py").write_text(LEDGER + "# reformatted\n", encoding="utf-8")   # outside scope


def _reviewer_commits(work: Path) -> None:
    (work / "ledgerlock" / "reviewer_note.py").write_text("x\n", encoding="utf-8")
    _git(work, "add", "--", "ledgerlock/reviewer_note.py"); _git(work, "commit", "-qm", "reviewer")


class TestSS10ResetAfterAMovedCandidateIsRecorded(HygieneCase):
    """SS-A10 — `review_story_v2` puts the tree back with `git reset --hard <candidate>` after a reviewer
    commit: the reset destroys out-of-scope dirt a `write-scope:violation` note still describes, and its
    result is neither checked nor recorded."""

    # GREEN since F1 (SS-A10: soft reset + selective restore, recorded ok or not), 2026-09-16
    def test_dirt_destroyed_by_the_reset_is_preserved_or_named(self):
        c = Developer(first=_dirty_then_stage_nothing, then=None, reviewer_writes=_reviewer_commits)
        out = self.implement(c, retries=0)
        ev = EvidenceStore(self.artifacts).read(HSID)
        moved = ev.last(TOOL_RUN, "review:candidate")
        self.assertIsNotNone(moved, "precondition: the reviewer moved HEAD")
        self.assertEqual(head_sha(self.work), out.attempts[0].candidate, "precondition: the reset ran")
        kept = (self.work / "ledgerlock" / "ledger.py").read_text(encoding="utf-8") != LEDGER
        # A record of the reset's effect names the path under a recovery key (the shape retry:recovery uses);
        # the gate's own `changed` input list and the write-scope check detail describe the tree before it.
        keys = ("tracked", "untracked", "actions", "destroyed", "restored", "reset", "discarded")
        named = [e for e in ev.after_event(moved)
                 if any("ledgerlock/ledger.py" in json.dumps(e.detail.get(k, "")) for k in keys)]
        self.assertTrue(kept or named, "out-of-scope dirt destroyed by the reset with no record naming it")

    # GREEN since F1 (SS-A10: soft reset + selective restore, recorded ok or not), 2026-09-16
    def test_a_failing_reset_is_recorded(self):
        real = subprocess.run

        def refuse_reset(cmd, *a, **kw):
            if cmd[:2] == ["git", "reset"]:
                return subprocess.CompletedProcess(cmd, 128, b"", b"fatal: Unable to create index.lock")
            return real(cmd, *a, **kw)

        c = Developer(first=_dirty_then_stage_nothing, then=None, reviewer_writes=_reviewer_commits)
        with patch.object(I.subprocess, "run", side_effect=refuse_reset):
            out = self.implement(c, retries=0)
        ev = EvidenceStore(self.artifacts).read(HSID)
        self.assertIsNotNone(ev.last(TOOL_RUN, "review:candidate"))
        self.assertNotEqual(head_sha(self.work), out.attempts[0].candidate, "precondition: the reset failed")
        self.assertTrue([e for e in ev.events if "reset" in json.dumps(e.detail).lower()],
                        "the tree is not on the frozen candidate and no record says the reset failed")


# ---------------------------------------------------------------- FAM-IDENTITY / INV-A.2

def _stage_out_of_scope(work: Path) -> None:
    _dirty_then_stage_nothing(work)
    _git(work, "add", "ledgerlock/ledger.py")              # commit_paths refuses: freeze fails, HEAD = parent


class TestSS15RefusedFreezeIsNotGradedUnderTheParent(HygieneCase):
    """SS-A15 — `freeze_candidate` swallows GitError and returns HEAD: the gate then grades a worktree that
    holds the story's work while every record is stamped with the parent SHA."""

    # GREEN since F1 (SS-A15: typed freeze outcome / session-bound proofs), 2026-09-16
    def test_a_refused_freeze_does_not_grade_the_tree_under_the_parent_sha(self):
        c = Developer(first=_stage_out_of_scope, then=None)
        out = self.implement(c, retries=0)
        ev = EvidenceStore(self.artifacts).read(HSID)
        self.assertIsNotNone(ev.last(TOOL_RUN, "candidate:frozen"), "precondition: the freeze was refused")
        gi = ev.last(NOTE, "gate:input")
        graded = str(gi.detail.get("candidate") or "") if gi else ""
        self.assertNotEqual(graded, self.entry, "the gate graded the worktree's work under the parent SHA")
        self.assertFalse(out.done)
        self.assertTrue(out.attempts and out.attempts[0].infra and not out.attempts[0].candidate,
                        "a refused freeze is a typed environment outcome with no candidate, never a grading")


# ---------------------------------------------------------------- FAM-IDENTITY / INV-D.1

class TestSSC2CandidateOfRecordIsTheGradedCandidate(unittest.TestCase):
    """SS-C2 — `Evidence.candidate` returns the newest `detail['candidate']` of any event; a
    `retry:recovery` note naming another SHA after the last `gate:input` becomes the candidate of record."""

    # GREEN since F1 (candidate of record / identity-bound proofs), 2026-09-16
    def test_a_recovery_note_after_the_gate_does_not_change_the_candidate_of_record(self):
        ev = _ev(
            {"kind": TOOL_RUN, "name": "test", "ok": True, "detail": {"candidate": C2}},
            {"kind": NOTE, "name": "gate:input", "detail": {"candidate": C2, "attempt": 2}},
            {"kind": NOTE, "name": "retry:recovery", "detail": {"candidate": C1, "attempt": 2, "tracked": ["x.py"]}},
        )
        self.assertEqual(ev.candidate, C2)


# ---------------------------------------------------------------- FAM-IDENTITY / INV-D.2

class TestSST1TddVerdictFollowsPositionAndCandidateNotSeq(unittest.TestCase):
    """SS-T1 — `tdd.red_before_green` compares `e.seq < last_green.seq`; `read()` orders by (at, seq), so a
    seq that disagrees with position (reset counter, clock skew across machines) decides the verdict."""

    # GREEN since F1 (SS-T1: TDD verdict by position within the candidate's evidence), 2026-09-16
    def test_a_red_run_positioned_after_the_green_does_not_prove_tdd(self):
        ev = Evidence(story_id=SID, events=[
            Event(kind=TOOL_RUN, name="test", ok=True, seq=5, at=1.0, detail={"candidate": C2}),
            Event(kind=TOOL_RUN, name="test", ok=False, seq=1, at=2.0, detail={"candidate": C2}),
        ])
        self.assertFalse(red_before_green(ev), "green then red is not red-before-green")

    def test_control_a_red_run_at_another_candidate_is_filtered_before_the_seq_comparison(self):
        ev = _ev(
            {"kind": TOOL_RUN, "name": "test", "ok": False, "detail": {"candidate": C1}},
            {"kind": TOOL_RUN, "name": "test", "ok": True, "detail": {"candidate": C2}},
            {"kind": TOOL_RUN, "name": "lint", "ok": True, "detail": {"candidate": C2}},
        )
        self.assertTrue(red_before_green(ev), "unfiltered, the foreign red would count")
        g = gate.evaluate(SID, ev, changed=["tests/test_a.py"], write_scope=["tests"], screens=[], candidate=C2,
                          review_blocking=[], added_tests=["tests/test_a.py"])
        # Safe by construction: `gate.evaluate` applies `evidence.for_candidate(candidate)` (gate.py:659-662)
        # before any check, so `red_before_green` only ever compares seq within one candidate.
        self.assertIsNot(_check(g, "TDD").outcome, Outcome.PASSED, _check(g, "TDD").detail)


# ---------------------------------------------------------------- FAM-IDENTITY / INV-P.2

class TestSSX1WaiverBindsToTheStorysCandidate(unittest.TestCase):
    """SS-X1 — `_waive_review` binds the operator's waiver to the newest `gate:input`'s candidate; a later
    scoring at another SHA (a `--no-isolate` verify at the trunk) silently takes the signature."""

    # GREEN since F1 (SS-X1: waiver bound to the story branch tip), 2026-09-16
    def test_a_waiver_is_refused_or_bound_to_the_story_branch_tip_not_the_latest_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q", "-b", "main"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "a.txt").write_text("a\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "trunk")
            trunk = _git(repo, "rev-parse", "HEAD")
            _git(repo, "checkout", "-q", "-b", f"story/{SID}")
            (repo / "a.txt").write_text("b\n", encoding="utf-8"); _git(repo, "commit", "-qam", "candidate")
            tip = _git(repo, "rev-parse", "HEAD"); _git(repo, "checkout", "-q", "main")
            root = repo / "_bmad-output"
            store = EvidenceStore(root)
            block = ["[block] a.txt:1 — wrong"]
            store.record(SID, Event(kind=NOTE, name="gate:input", detail={"candidate": tip, "review_blocking": block, "attempt": 1}))
            store.record(SID, Event(kind=NOTE, name="gate:input", detail={"candidate": trunk, "review_blocking": block, "attempt": 2, "verify_only": True}))
            code = cli_main(["--project", str(repo), "gate", SID, "--waive-review", "--reason", "reviewer misread"])
            waiver = store.read(SID).last(NOTE, gate.REVIEW_WAIVER)
            self.assertTrue(code != EXIT_OK or (waiver is not None and waiver.detail.get("candidate") == tip),
                            f"exit={code} waiver bound to {str(waiver.detail.get('candidate') if waiver else '')[:8]}, "
                            f"story branch tip is {tip[:8]}")


if __name__ == "__main__":
    unittest.main()
