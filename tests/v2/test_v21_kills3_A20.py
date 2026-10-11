"""V2.1 (owner B-03, kills3 batch A20, reviewed): kill test for the survivor of aisef2/app/usage.py::no_progress at
campaign 2 (snapshot 5719f1f) whose "equivalent" verdict did not hold when the format's own admission was measured.

`no_progress` is a function of a journal. The journal here is written through the kernel's own Authority (the six
projections' pre-check RunScope installs) and read back with format3.reconstruct, the reader `aisef run --verify`
uses (aisef2/app/verify.py), so the input is one the journal format admits: the format admits several
failure/observed in one attempt (budgets.py refuses a retry that "reaches past a newer failure", so a retry cites the
latest of several). The runner itself writes one per attempt (orchestrate/story_runner.py `_fail`).

Not tested here, on purpose: "L122 element 2 dropped" [13] and "L122 string 'story/commit' emptied" [23]. They differ
from the original only on a journal whose *committing* attempt observed a failure equal to the attempt before it (the
496 journals of up to three attempts, none to two failures of two codes each, were compared: no other difference).
The format admits that journal; no writer emits it (failure/observed has one emitter, story_runner._fail, called
only in the branch of an attempt that does not commit: story_runner.py:329-335); and whether a committed attempt is
ever "no progress" is stated nowhere (the docstring and USAGE-2.1.md speak of failed attempts / retries). A test would pin an
undecided polarity."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import usage  # noqa: E402
from aisef2.arch.enums import ControlProjection as P, EventType as T  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.fold import Authority  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402

SHA = "a" * 40
UNSAT = ("CONTRACT_UNSATISFIED", "proof of C-ADD: CONTRACT_UNSATISFIED")
TESTS = ("TESTS_INADEQUATE", "developer tests: TESTS_INADEQUATE")
MERGE = ("MERGE_CONFLICT", "merge: MERGE_CONFLICT")


def shown(failure: tuple[str, str]) -> str:
    return f"{failure[0]}: {failure[1]}"


def written(*attempts: tuple[list, str], story: str = "S1") -> tuple[list[dict], int]:
    """One story's attempts, each `(failures, decision)` with decision retry|rollback, written through
    Authority(JournalWriter3, PROJECTIONS) — a retry or rollback cites its attempt's latest failure — and read back
    as verify reads a journal. Returns the events as dicts and the attempt number story_state ends the story at."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "journal.jsonl"
        w = format3.JournalWriter3(path, clock=lambda: 0.0)
        try:
            a = Authority(w, PROJECTIONS.values())
            a.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r"})
            a.append(T.PLAN_FROZEN, {"plan_id": "PLAN-1", "plan_hash": "b" * 64, "roles": {"C-ADD": "INTRODUCE"}})
            for failures, decision in attempts:
                a.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
                a.append(T.STORY_ADMITTED, {"story_id": story, "parent": SHA, "admitted": True,
                                            "developer_call_permitted": True, "dispositions": {"C-ADD": "READY"}})
                seq = None
                for code, detail in failures:
                    seq = a.append(T.FAILURE_OBSERVED, {"story_id": story, "code": code, "detail": detail}).seq
                a.append(T(f"story/{decision}"), {"story_id": story}, source_seqs=(seq,))
                a.append(T.STORY_DISPOSE, {"story_id": story})
                a.append(T.STORY_END, {"story_id": story})
            attempt = a.state(P.STORY_STATE.value)[story]["attempt"]
        finally:
            w.close()
        text = path.read_bytes().decode("utf-8")
    return [{"seq": e.seq, "type": e.type, "data": dict(e.data)} for e in format3.reconstruct(text).events], attempt


class FailuresOfAnAttemptAreASet(unittest.TestCase):
    """no_progress — "L123 sorted() -> list()" [24]: an attempt's failures are compared as the set of (code, detail)
    it observed ("cùng tập lỗi", docs/v2.1/TRACEABILITY.md P-5.3c), not in the order they were observed: two attempts
    that observed the same failures in another order made no progress between them, and two that differ in one
    failure did."""

    def test_the_same_failures_observed_in_another_order_are_the_same_failures(self):
        events, attempt = written(([TESTS, UNSAT], "retry"), ([UNSAT, TESTS], "rollback"))
        self.assertEqual(attempt, 2)
        report = usage.no_progress(events)
        self.assertEqual([(r["story"], r["attempts_repeating_the_one_before"]) for r in report], [("S1", [2])])
        self.assertCountEqual(report[0]["failures"], [shown(UNSAT), shown(TESTS)])

    def test_attempts_that_differ_in_one_failure_are_not_the_same_failures(self):
        events, attempt = written(([TESTS, UNSAT], "retry"), ([UNSAT, MERGE], "rollback"))
        self.assertEqual(attempt, 2)
        self.assertEqual(usage.no_progress(events), [])


if __name__ == "__main__":
    unittest.main()
