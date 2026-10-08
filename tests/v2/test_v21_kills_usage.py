"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/usage.py's V2.1 mutation target `no_progress`, the
class named by the target and the mutants it kills. In the kill set of exactly the target it kills
(validation/v2/mutation.py).

The earlier kill set reports one story whose attempts all failed the same one way: no attempt that failed differently
from the one before (so reporting it anyway survived), and no attempt with more than one failure (so comparing an
attempt's failures in the order they were journaled, not as a set, survived)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import usage  # noqa: E402


def failed(sid: str, *failures: tuple[str, str], then: str = "story/retry") -> list[dict]:
    """One failed attempt of story `sid` as the journal holds it: each failure observed, then the decision."""
    return [*({"type": "failure/observed", "data": {"story_id": sid, "code": c, "detail": d}} for c, d in failures),
            {"type": then, "data": {"story_id": sid}}]


class NoProgress(unittest.TestCase):
    """no_progress — "L126 And swapped" (an attempt reported although its failures differ from the one before), "L123
    sorted() -> list()" (an attempt's failures compared in journal order): a retry is reported as changing nothing
    exactly when its attempt failed with the same set of failures (codes and details) as the attempt before it
    (docs/v2.1/TRACEABILITY.md P-5.3c: "cùng tập lỗi"). The journal admits several failures in one attempt — the
    failure_owner and budgets projections fold each, and a retry cites the latest — so the order they were observed in
    is no difference; the report lists them sorted."""

    def test_only_an_attempt_failing_with_the_same_set_of_failures_as_the_one_before_is_reported(self):
        unsat = ("CONTRACT_UNSATISFIED", "proof of C-ADD: CONTRACT_UNSATISFIED")
        tests = ("TESTS_INADEQUATE", "developer tests: TESTS_INADEQUATE")
        merge = ("MERGE_CONFLICT", "merge: MERGE_CONFLICT")
        events = [*failed("S1", tests, unsat), *failed("S1", unsat, tests), *failed("S1", unsat, then="story/rollback"),
                  *failed("S2", merge), *failed("S2", unsat, then="story/rollback")]
        self.assertEqual(usage.no_progress(events), [
            {"story": "S1", "attempts_repeating_the_one_before": [2],
             "failures": ["CONTRACT_UNSATISFIED: proof of C-ADD: CONTRACT_UNSATISFIED",
                          "TESTS_INADEQUATE: developer tests: TESTS_INADEQUATE"]}])


if __name__ == "__main__":
    unittest.main()
