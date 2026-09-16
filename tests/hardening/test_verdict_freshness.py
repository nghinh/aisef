"""D-035 (OBS-OC-4) — a failed verdict has no freshness identity: after retry hygiene restores the
out-of-scope dirt that was the verdict's only cause, the no-op policy ends the story citing that verdict
and the clean candidate is never re-graded.

Measured on the LedgerLock OpenCode replay, phase 7, public aisef 1.7.6 (STORY-04-01, candidate
de2d3244): the phase 6 verdict on de2d3244 failed `write scope` (stale formatter dirt on ledger.py and
store.py) and `review`, whose structured verdict had exactly one finding — the same dirt. Phase 7 opened
a clean worktree at de2d3244; three developer sessions correctly wrote nothing ("attempt 1 already
satisfies all ACs": 101/101 tests, 4 criteria tests, lint clean, in-scope only); the harness ended the
story as "2 sessions in a row ran clean and wrote nothing … re-running would return the verdict it
already returned". That sentence was false: the verdict depended on tree state the harness had since
changed, not on the candidate SHA.

Invariants (docs/INVARIANTS.md): E EVIDENCE FRESHNESS (a state change relevant to the evidence
invalidates it), H NO-OP SEMANTICS (no-op is terminal only after the candidate is re-evaluated against
current valid evidence), K RETRY HYGIENE (recovery itself changes evidence freshness).

Reproduced here without OpenCode on the LedgerLock-shaped fixture of tests/test_retry_hygiene.py:
attempt 1 = in-scope change + formatter dirt outside scope; the retry developer changes nothing.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aisef.harness.observe import NOTE, EvidenceStore  # noqa: E402
from tests.test_retry_hygiene import LEDGER, SID, STORE, Developer, HygieneCase  # noqa: E402

DEFECT = "D-035"


def _detail(e):
    d = e.detail
    return json.loads(d) if isinstance(d, str) else d


def reproduce(case: HygieneCase) -> dict:
    """Run the scenario once and return the measured facts (also written to the Phase 0 evidence)."""
    c = Developer(then=None)                       # attempt 2+: the work is already done, write nothing
    out = case.implement(c, retries=2)
    ev = EvidenceStore(case.artifacts).read(SID)
    verdicts = [_detail(e) for e in ev.of(NOTE, "gate:verdict")]
    recovery = [_detail(e) for e in ev.of(NOTE, "retry:recovery")]
    first = out.attempts[0]
    seen = c.seen[0] if c.seen else {}
    return {
        "candidate_C": first.candidate,
        "attempt1_failures": [x.name for x in first.gate.failures] if first.gate else None,
        "recovery": [{"tracked": r["tracked"], "untracked": r["untracked"], "ok": r["ok"], "candidate": r["candidate"]} for r in recovery],
        "head_at_attempt2": seen.get("head"),
        "developer_sessions": c.develop_calls,
        "developer_wrote_on_retry": bool(c.then),
        "tree_at_attempt2": {"status": seen.get("status"), "guard_allowed": seen.get("guard_allowed"),
                             "ledger_restored": seen.get("ledger") == LEDGER, "store_restored": seen.get("store") == STORE},
        "gate_verdicts": [{"attempt": v.get("attempt"), "candidate": v.get("candidate"), "failures": v.get("failures")} for v in verdicts],
        "regraded_after_recovery": any(v.get("attempt", 0) >= 2 for v in verdicts),
        "done": out.done,
        "blocked_reason": out.blocked_reason,
    }


class TestOBSOC4Reproduction(HygieneCase):
    """Facts 1–5 and 7 of the owner's expected reproducer. These hold before and after the fix
    except the last, which is the defect itself and lives in the expected-failure test below."""

    def test_the_reproducer_shows_the_stale_verdict_and_the_unchanged_candidate(self):
        f = reproduce(self)
        # 1. candidate C previously failed ONLY because of write-scope dirt
        self.assertEqual(f["attempt1_failures"], ["write scope"], f)
        # 2. retry hygiene removed/restored the offending dirt
        self.assertEqual(len(f["recovery"]), 1, f["recovery"])
        self.assertTrue(f["recovery"][0]["ok"])
        self.assertEqual(f["recovery"][0]["tracked"], ["ledgerlock/ledger.py", "ledgerlock/store.py"])
        # 3. candidate SHA remains C
        self.assertEqual(f["head_at_attempt2"], f["candidate_C"])
        self.assertEqual(f["recovery"][0]["candidate"], f["candidate_C"])
        # 4. the developer correctly writes nothing
        self.assertFalse(f["developer_wrote_on_retry"])
        self.assertGreaterEqual(f["developer_sessions"], 2)
        # 5. the previous verdict is stale because the evaluated state changed
        self.assertEqual(f["tree_at_attempt2"]["status"], "", "clean tree now")
        self.assertTrue(f["tree_at_attempt2"]["guard_allowed"], "write scope would pass now")
        self.assertTrue(f["tree_at_attempt2"]["ledger_restored"] and f["tree_at_attempt2"]["store_restored"])


class TestInvariantEH(HygieneCase):
    """Invariant E/H: a no-op cannot terminate the story on stale failed evidence; the clean frozen
    candidate must be re-graded with current evidence. RED on the 1.7.6 baseline (D-035)."""

    @unittest.expectedFailure   # D-035 — remove this marker in the commit that fixes it
    def test_D_035_the_clean_candidate_is_regraded_and_the_story_completes(self):
        f = reproduce(self)
        self.assertTrue(f["regraded_after_recovery"],
                        "a verdict exists for the candidate on the clean tree (facts 6): " + json.dumps(f["gate_verdicts"]))
        self.assertTrue(f["done"], "deterministic gates pass on the clean tree and scripted review/security pass: " + str(f["blocked_reason"])[:200])
        self.assertNotIn("would return the verdict it already returned", f["blocked_reason"] or "")


if __name__ == "__main__":
    unittest.main()
