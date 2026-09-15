"""LedgerLock Run #2 (2026-09-15, public aisef==1.7.3) — Finding A.

STORY-01-06, candidate eed6f87a: nop control red at parent (expected), test
PASS, lint PASS, the reviewer hit `max_turns=40` and produced no verdict,
security PASS. The gate failed on `review` alone — "review could not run:
max_turns: stopped at 40 turns (cap 40)" scored as one blocking item. The
next attempt opened a **developer** session against a candidate that had
nothing left to fix; it wrote nothing; so did the one after it; the no-op
policy (`MAX_NOOP = 2`) then made the story terminal: "2 sessions in a row
ran clean and wrote nothing". A forced resume repeated the pattern.

Reproduced here without OpenCode: the scripted reviewer fails to execute
exactly like the real one did; the scripted developer, having already
delivered the candidate, correctly writes nothing when asked again.

RED (the defect): a reviewer execution failure on a candidate whose
deterministic gates pass must retain the candidate and retry the REVIEW
stage, bounded, ending in PASS, a structured BLOCK, or an explicit
REVIEW_UNRUNNABLE — never in a developer no-op verdict.

Controls (green on 1.7.3): a genuine `[block]` still returns to the
developer; a deterministic lint failure still returns to the developer; the
number of review sessions stays bounded.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import subprocess  # noqa: E402

from aisef.clients.base import RunResult  # noqa: E402
from aisef.harness.observe import AGENT_RUN, NOTE, TOOL_RUN, Event, EvidenceStore  # noqa: E402
from aisef.phases import implement as I  # noqa: E402
from tests.test_implement import ImplementTestCase, ScriptedClient  # noqa: E402

CUT = "max_turns: stopped at 40 turns (cap 40)"
PASS_JSON = '[pass]\n\n```json\n{"verdict": "pass", "findings": []}\n```\n'
BLOCK_JSON = ('[block] src/a.py:1 — loses data on save\n\n```json\n{"verdict": "block", "findings": '
              '[{"tag": "block", "file": "src/a.py", "line": 1, "why": "loses data on save"}]}\n```\n')


class ReviewerCut(ScriptedClient):
    """The Run #2 shape: the developer delivers once and then, asked again with
    nothing left to do, writes nothing; the reviewer's first `fail_reviews`
    executions end the way OpenCode's did — no verdict, `max_turns`."""

    def __init__(self, *, fail_reviews: int, review: str = PASS_JSON, noop_after_first: bool = True):
        super().__init__(review=review)
        self.fail_reviews = fail_reviews
        self.review_calls = 0
        #: Run #2 shape (True): once delivered, the developer writes nothing more.
        #: Controls (False): the developer keeps revising — a block or a red
        #: lint gives it something to do.
        self.noop_after_first = noop_after_first

    def run(self, spec):
        dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        if dau.startswith("# Review") and not dau.startswith("# Security review"):
            self.review_calls += 1
            self.calls.append("review")
            if self.review_calls <= self.fail_reviews:
                return RunResult(ok=False, error=CUT, num_turns=40, cost_usd=0.0)
            return RunResult(ok=True, text=self.review, cost_usd=0.3)
        if dau.startswith("# Security review"):
            return super().run(spec)
        if self.develop_calls == 0 or not self.noop_after_first:
            return super().run(spec)
        self.calls.append("develop")
        self.develop_calls += 1
        return RunResult(ok=True, num_turns=7, output_tokens=200, text="nothing to do", cost_usd=0.0)


class TestReviewExecutionFailureRecovery(ImplementTestCase):
    def test_review_execution_failure_retries_the_reviewer_on_the_same_candidate(self):
        """RED on 1.7.3. One cut review, then a clean one: the story must end
        done with ONE developer session — the candidate never needed another."""
        c = ReviewerCut(fail_reviews=1)
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertEqual(c.develop_calls, 1,
                         f"a reviewer that could not run must not reopen the developer; calls={c.calls}")
        self.assertGreaterEqual(c.review_calls, 2, "the review stage must be retried on the same candidate")
        self.assertTrue(out.done, out.blocked_reason)
        self.assertNotIn("wrote nothing", out.blocked_reason)

    def test_persistent_review_failure_ends_as_review_unrunnable_not_as_a_developer_noop(self):
        """RED on 1.7.3. A reviewer that never executes is a REVIEW execution
        failure; the terminal reason must say so, and no unrelated developer
        session may be spent on it."""
        c = ReviewerCut(fail_reviews=99)
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertFalse(out.done)
        self.assertEqual(c.develop_calls, 1, f"calls={c.calls}")
        low = out.blocked_reason.lower()
        self.assertIn("review", low, out.blocked_reason)
        self.assertTrue("could not run" in low or "unrunnable" in low, out.blocked_reason)
        self.assertNotIn("wrote nothing", low, "a correct no-op is not the story's failure")

    # ------------------------------------------------------------ controls

    def test_a_genuine_review_block_still_returns_to_the_developer(self):
        c = ReviewerCut(fail_reviews=0, review=BLOCK_JSON, noop_after_first=False)
        out = self.implement(c, config=self.config(**{"run.max_retries": 1}))
        self.assertGreaterEqual(c.develop_calls, 2, f"calls={c.calls}")
        self.assertFalse(out.done)
        self.assertEqual(out.quality_attempts, 2)

    def test_a_deterministic_lint_failure_still_returns_to_the_developer(self):
        c = ReviewerCut(fail_reviews=0, noop_after_first=False)
        out = self.implement(c, config=self.config(**{"run.max_retries": 1, "tools.lint": "false",
                                                      "sandbox.use_docker": False}))
        self.assertGreaterEqual(c.develop_calls, 2, f"calls={c.calls}")
        self.assertFalse(out.done)
        self.assertTrue(any(ch.name == "lint" for a in out.attempts if a.gate for ch in a.gate.failures),
                        "lint must be the failing check")

    def test_review_retries_stay_bounded(self):
        c = ReviewerCut(fail_reviews=99)
        out = self.implement(c, config=self.config(**{"run.max_retries": 3}))
        self.assertFalse(out.done)
        self.assertLessEqual(c.review_calls, 2 * (3 + 1),
                             f"review must not be retried without bound: {c.review_calls} sessions")


class TestReviewEvidenceAndReuse(ImplementTestCase):
    """Requirements 5–8: deterministic failures still reach the developer; the
    candidate SHA is preserved across a review retry and every review execution
    is recorded against it; a complete prior review is reused; an incomplete
    one (new shape or the ≤ 1.7.3 finding text) is not; a resumed story picks
    up at the review stage."""

    def setUp(self):
        super().setUp()
        for args in (["config", "user.email", "t@t.t"], ["config", "user.name", "t"],
                     ["commit", "-q", "--allow-empty", "-m", "base"]):
            subprocess.run(["git", *args], cwd=self.project, check=True)
        self.sha = I.head_sha(self.project)
        self.assertTrue(self.sha)

    def _stage_args(self):
        from aisef.control.normalize import effective_write_scope
        from aisef.harness.guardrails import changed_files
        from aisef.harness.prompts import load_catalog
        return dict(project=self.project, workdir=self.project, artifact_root=self.artifacts,
                    config=self.config(), catalog=load_catalog(), architecture=None, contract=None,
                    base_ref="", scope=effective_write_scope(self.story, self.project),
                    changed=changed_files(str(self.project)), preservation=[])

    def test_a_deterministic_test_failure_still_returns_to_the_developer(self):
        c = ReviewerCut(fail_reviews=0, noop_after_first=False)
        out = self.implement(c, config=self.config(**{"run.max_retries": 1, "tools.test": "false",
                                                      "sandbox.use_docker": False}))
        self.assertGreaterEqual(c.develop_calls, 2, f"calls={c.calls}")
        self.assertFalse(out.done)

    def test_candidate_is_preserved_and_every_review_execution_is_recorded_against_it(self):
        c = ReviewerCut(fail_reviews=1)
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertTrue(out.done, out.blocked_reason)
        shas = {a.candidate for a in out.attempts}
        self.assertEqual(shas, {self.sha}, "the review retry must run on the same frozen candidate")
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        reviews = [e for e in ev.of(TOOL_RUN, "review") if e.detail.get("candidate") == self.sha]
        self.assertEqual([e.detail["outcome"] for e in reviews], ["REVIEW_UNRUNNABLE", "PASS"])
        self.assertEqual([e.detail["review_attempt"] for e in reviews], [1, 2])
        self.assertTrue(reviews[0].detail["unrunnable"].startswith("max_turns"))
        self.assertEqual(out.quality_attempts, 1, "developer attempts are counted apart from review executions")
        self.assertEqual(sum(1 for a in out.attempts if a.verify_only), 1)

    def test_successful_prior_review_evidence_is_reused(self):
        c = ReviewerCut(fail_reviews=0)
        out = self.implement(c)
        self.assertTrue(out.done, out.blocked_reason)
        before = c.review_calls
        again = I.Attempt(number=2, verify_only=True); again.candidate = self.sha
        again = I.verify_candidate(self.story, client=c, attempt=again, reuse=True, **self._stage_args())
        self.assertEqual(c.review_calls, before, "a complete prior review at this candidate is reused")
        self.assertTrue(again.ok, again.gate.summary() if again.gate else "")
        self.assertIn("review", again.kept)

    def _seed_incomplete_review(self, *, legacy: bool):
        # The candidate's work is in the tree (as in Run #2's worktree); the
        # non-isolated harness freezes HEAD as the candidate and reviews the diff.
        (self.project / "src").mkdir(exist_ok=True)
        (self.project / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        store = EvidenceStore(self.artifacts, candidate=self.sha)
        store.record(self.story.id, Event(kind=AGENT_RUN, name=f"{self.story.id}-review", ok=False,
                                          detail={"error": CUT, "num_turns": 40}))
        if legacy:   # the exact 1.7.3 shape from LedgerLock Run #2
            store.tool_run(self.story.id, "review", ok=False,
                           detail={"findings": [f"review could not run: {CUT}"], "plan": [], "attempt": 1})
        else:
            store.tool_run(self.story.id, "review", ok=False,
                           detail={"findings": [], "plan": [], "attempt": 1, "outcome": "REVIEW_UNRUNNABLE",
                                   "unrunnable": CUT, "review_attempt": 1})
        return store

    def test_incomplete_prior_review_evidence_is_not_reused_by_verify_only(self):
        for legacy in (True, False):
            with self.subTest(legacy=legacy):
                self._seed_incomplete_review(legacy=legacy)
                c = ReviewerCut(fail_reviews=0)
                again = I.Attempt(number=2, verify_only=True); again.candidate = self.sha
                again = I.verify_candidate(self.story, client=c, attempt=again, reuse=True, **self._stage_args())
                self.assertEqual(c.review_calls, 1, "an unrunnable prior review must be re-run")
                self.assertIn("review", again.reran)
                self.assertEqual(again.review_unrunnable, "")

    def test_verify_only_ends_review_unrunnable_when_the_rerun_is_cut_again(self):
        """`--verify-only` on an incomplete review re-runs the reviewer once; cut
        again, the outcome is named REVIEW_UNRUNNABLE with the actual failure —
        not a generic `did not pass gate: review`."""
        self._seed_incomplete_review(legacy=True)
        c = ReviewerCut(fail_reviews=1)
        out = I.verify_only(self.story, project=self.project, workdir=self.project,
                            artifact_root=self.artifacts, client=c, config=self.config())
        self.assertEqual(c.review_calls, 1, f"calls={c.calls}")
        self.assertFalse(out.done)
        self.assertTrue(out.blocked_reason.startswith("REVIEW_UNRUNNABLE"), out.blocked_reason)
        self.assertIn("max_turns", out.blocked_reason)

    def test_a_resumed_story_picks_up_at_the_review_stage_without_a_developer_session(self):
        """The Run #2 forced-resume state: the worktree HEAD is a candidate whose
        only failing check was a reviewer that did not run (recorded in the
        1.7.3 shape). Resuming must retry the review, not open a developer."""
        store = self._seed_incomplete_review(legacy=True)
        store.record(self.story.id, Event(kind=NOTE, name="gate:verdict", ok=False,
                                          detail={"failures": ["review"], "attempt": 1, "checks": []}))
        c = ReviewerCut(fail_reviews=0)
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertEqual(c.develop_calls, 0, f"calls={c.calls}")
        self.assertEqual(c.review_calls, 1)
        self.assertTrue(out.done, out.blocked_reason)
        self.assertEqual(out.attempts[-1].candidate, self.sha)

    def test_a_resumed_story_with_the_review_budget_spent_ends_review_unrunnable(self):
        store = self._seed_incomplete_review(legacy=True)
        for _ in range(I.MAX_REVIEW_RETRIES):
            store.record(self.story.id, Event(kind=AGENT_RUN, name=f"{self.story.id}-review", ok=False,
                                              detail={"error": CUT}))
        store.record(self.story.id, Event(kind=NOTE, name="gate:verdict", ok=False,
                                          detail={"failures": ["review"], "attempt": 1, "checks": []}))
        c = ReviewerCut(fail_reviews=99)
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertEqual(c.develop_calls, 0, f"calls={c.calls}")
        self.assertFalse(out.done)
        self.assertIn("REVIEW_UNRUNNABLE", out.blocked_reason)
        self.assertNotIn("wrote nothing", out.blocked_reason)


if __name__ == "__main__":
    unittest.main()
