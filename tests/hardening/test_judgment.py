"""F3 — STRUCTURED JUDGMENT AUTHORITY: a blocker binds to what it blocks (INV-F.2; D-002's structural property).
A `block`/`stuck` finding counts only when it names a file, a `behavior_id` or a criterion code; an unbound one is
recorded as `review:unbound` and never scored; a verdict whose blockers all bind to nothing is asked once more and
is then REVIEW_UNRUNNABLE — never a PASS, never a developer session."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import tests  # noqa: E402,F401
from aisef.harness.observe import NOTE, EvidenceStore  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from tests.hardening import differential as D  # noqa: E402

SID = "STORY-04-01"


class TestABlockerBindsToWhatItBlocks(unittest.TestCase):
    def test_a_bound_block_blocks_and_an_unbound_one_is_recorded_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp), candidate="c1")
            v = I.Verdict(verdict="block", findings=[
                {"tag": "block", "file": "src/a.py", "line": "3", "why": "null is not handled", "behavior_id": ""},
                {"tag": "block", "file": "", "line": "", "why": "the overall approach is wrong", "behavior_id": ""},
            ])
            got = I._reconcile(SID, store, "", v, role="review")
            self.assertEqual(got, ["[block] src/a.py:3 — null is not handled"])
            unbound = store.read(SID).of(NOTE, "review:unbound")
            self.assertEqual([f["why"] for f in unbound[-1].detail["findings"]], ["the overall approach is wrong"])

    def test_a_behaviour_id_or_a_criterion_code_binds_without_a_file(self):
        self.assertTrue(I.finding_bound({"tag": "block", "file": "", "behavior_id": "FR-3", "why": "x"}))
        self.assertTrue(I.finding_bound({"tag": "block", "file": "", "behavior_id": "", "why": "AC-STORY-04-01-2 is not met"}))
        self.assertFalse(I.finding_bound({"tag": "block", "file": "", "behavior_id": "", "why": "looks wrong"}))

    def test_a_stuck_item_on_nothing_named_is_not_a_plan_conflict(self):
        v = I.Verdict(verdict="stuck", findings=[{"tag": "stuck", "file": "", "line": "", "why": "the plan is wrong", "behavior_id": ""}])
        self.assertEqual(I.structured_plan_defects(v), [])
        v2 = I.Verdict(verdict="stuck", findings=[{"tag": "stuck", "file": "src/store/db.ts", "line": "", "why": "index needed", "behavior_id": ""}])
        self.assertEqual(I.structured_plan_defects(v2), ["[stuck] src/store/db.ts — index needed"])

    def test_a_verdict_whose_blockers_bind_to_nothing_is_review_unrunnable_never_pass_never_developer(self):
        sc = D.Scenario(4001, ["CHANGED"], ["BLOCK_UNBOUND"], ["PASS"], max_retries=1)
        real = D.real_run(sc)
        self.assertEqual(real.terminal, "blocked:REVIEW_UNRUNNABLE", real.events)
        self.assertEqual(real.developer_sessions, 1, real.events)
        self.assertEqual(real.quality_attempts, 1, real.events)

    def test_the_model_agrees_on_the_unbound_block(self):
        sc = D.Scenario(4001, ["CHANGED"], ["BLOCK_UNBOUND"], ["PASS"], max_retries=1)
        self.assertEqual(D.real_run(sc).diff(D.model_run(sc)), [])


class TestVerifierBudgetCapReadsBothVerifiers(unittest.TestCase):
    """Phase 13 mutants of `_verifier_budget_cap` (INV-G.5 / SS-12, SS-21): a budget cap in EITHER verifier is a
    run-level stop; lock contention is not a cap; a review absent for another reason never hides the security cap."""

    def _attempt(self, review="", security=""):
        from types import SimpleNamespace
        from aisef.phases.implement import Attempt
        a = Attempt(number=1); a.review_unrunnable = review
        a.security = SimpleNamespace(unrunnable=security) if security else None
        return a

    def test_a_cap_in_the_review_is_the_reason(self):
        from aisef.phases.implement import _verifier_budget_cap
        self.assertEqual(_verifier_budget_cap(self._attempt(review="budget exceeded: $12.00 of $10.00")), "budget exceeded: $12.00 of $10.00")

    def test_lock_contention_is_not_a_cap(self):
        from aisef.phases.implement import _verifier_budget_cap
        self.assertEqual(_verifier_budget_cap(self._attempt(review="budget exceeded — ledger locked by another run")), "")

    def test_a_review_absent_for_another_reason_does_not_hide_the_security_cap(self):
        from aisef.phases.implement import _verifier_budget_cap
        self.assertEqual(_verifier_budget_cap(self._attempt(review="exceeded 1800s", security="budget exceeded: cap")), "budget exceeded: cap")
        self.assertEqual(_verifier_budget_cap(self._attempt(review="exceeded 1800s", security="exceeded 1800s")), "")


class TestDeadlockPairSurvivesAnInfraAttempt(unittest.TestCase):
    """Phase 13 mutant of `deadlock_reason` (SS-63's rule): an infra attempt between two graded positions is not a
    position and must not break the pair; two consecutive identical out-of-scope blocks are a plan conflict."""

    def _graded(self, findings):
        from aisef.phases.implement import Attempt
        a = Attempt(number=1); a.review_findings = list(findings); a.infra = False; a.review_unrunnable = ""
        return a

    def _infra(self):
        from aisef.phases.implement import Attempt
        a = Attempt(number=2); a.infra = True; a.review_findings = []; a.review_unrunnable = ""
        return a

    def test_two_identical_outside_blocks_around_an_infra_cut_are_stuck(self):
        from aisef.phases.implement import deadlock_reason
        block = ["[block] ledgerlock/ledger.py:1 — the ledger must reject a short row"]
        stuck = deadlock_reason([self._graded(block), self._infra(), self._graded(block)], ["ledgerlock/cli.py"])
        self.assertIn("stuck", stuck); self.assertIn("ledgerlock/ledger.py", stuck)
        self.assertEqual(deadlock_reason([self._graded(block), self._infra()], ["ledgerlock/cli.py"]), "",
                         "one position and an infra cut: no pair")


class TestLegacyTokenOverlapRule(unittest.TestCase):
    """Phase 13 mutants of `_same_complaint`'s legacy token path (lines without a structured finding id): a verbatim
    repeat is the same complaint; two shared proper nouns with ≥ 40 % overlap are; one shared noun is not; two nouns
    with low overlap are not."""

    def test_verbatim_and_overlap_thresholds(self):
        from aisef.phases.implement import _same_complaint
        a = ["missing fake-indexeddb in package.json devDependencies"]
        self.assertTrue(_same_complaint(a, list(a)), "verbatim repeat")
        self.assertTrue(_same_complaint(a, ["fake-indexeddb not declared in package.json"]), "two shared nouns, high overlap")
        self.assertFalse(_same_complaint(a, ["package.json has a wrong license field"]), "one shared noun is progress, not deadlock")
        long_a = ["missing fake-indexeddb in package.json devDependencies section for the vitest environment setup script and the coverage reporter"]
        self.assertFalse(_same_complaint(long_a, ["fake-indexeddb package.json alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu"]),
                         "two shared nouns but overlap below the ratio (the ratio divides by the SHORTER token set)")
        self.assertFalse(_same_complaint(a, []), "nothing to compare with")


class TestPathsOutsideEdges(unittest.TestCase):
    """Phase 13 mutants of `_paths_outside` (SS-25 / INV-F.2): a manifest at the root is a path (dot, no slash); a
    bare technology word is not; an in-scope path is not reported; a duplicate is reported once; a structured
    finding's `file` counts like a canonical line's leading token."""

    def test_edges(self):
        from aisef.phases.implement import _paths_outside
        scope = ["src/"]
        self.assertEqual(_paths_outside(["[block] package.json:1 — devDependency missing"], scope), ["package.json"])
        self.assertEqual(_paths_outside(["[block] docker — the image is wrong"], scope), [], "a technology name is not a path")
        self.assertEqual(_paths_outside(["[block] src/app.py:3 — wrong"], scope), [], "inside the scope: not yet fixed, not cannot fix")
        self.assertEqual(_paths_outside(["[block] lib/x.py:1 — a", "[block] lib/x.py:9 — b"], scope), ["lib/x.py"], "once")
        self.assertEqual(_paths_outside([{"file": "lib/y.py", "why": "w"}], scope), ["lib/y.py"])
        self.assertEqual(_paths_outside(["[block] lib/x.py:1 — a"], []), ["lib/x.py"], "an empty scope allows nothing")


class TestNopDeadlockPositions(unittest.TestCase):
    """Phase 13 mutants of `nop_deadlock`: one graded verdict naming still-green criteria plus two consecutive no-op
    sessions is the plan diagnosis; one graded verdict alone is not (and must not crash)."""

    def _graded(self, codes):
        from aisef.control.outcome import Check, Outcome
        from aisef.phases.implement import Attempt
        a = Attempt(number=1); a.infra = False
        chk = Check("tests verify story", Outcome.FAILED, "still green at the parent", data={"still_green": list(codes)})
        a.gate = type("G", (), {"failures": [chk], "checks": [chk]})()
        return a

    def _noop(self, n):
        from aisef.phases.implement import Attempt
        a = Attempt(number=n); a.infra = True; a.noop = True
        return a

    def test_one_verdict_then_two_noops_is_the_plan_diagnosis_and_one_verdict_alone_is_not(self):
        from aisef.phases.implement import nop_deadlock
        codes = ["AC-STORY-03-02-1", "AC-STORY-03-02-2"]
        self.assertEqual(nop_deadlock([self._graded(codes)]), "")
        self.assertIn("deadlock due to plan", nop_deadlock([self._graded(codes), self._noop(2), self._noop(3)]))
        self.assertIn("AC-STORY-03-02-1", nop_deadlock([self._graded(codes), self._graded(codes)]))


class TestInScopeRepeatIsNotStuck(unittest.TestCase):
    """Phase 13 mutant of `deadlock_reason` (`write_scope or []` → `and`): two identical blocks on a file INSIDE a
    non-empty write scope are "not yet fixed", never "cannot fix" — the retry limit decides."""

    def test_two_identical_in_scope_blocks_are_not_a_plan_conflict(self):
        from aisef.phases.implement import Attempt, deadlock_reason

        def graded(findings):
            a = Attempt(number=1); a.review_findings = list(findings); a.infra = False; a.review_unrunnable = ""
            return a
        block = ["[block] src/app/list-notes.ts:12 — AR-7 violation"]
        self.assertEqual(deadlock_reason([graded(block), graded(block)], ["src/app/"]), "")
        self.assertIn("stuck", deadlock_reason([graded(block), graded(block)], ["docs/"]), "the same block outside the scope IS stuck")
