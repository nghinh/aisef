"""The story gate's rows (RFC §20.1): one `gate/check` per check, all under the one gate the story's decision cites.
A summary-only record is prohibited; the decision cites its inputs by seq."""

from __future__ import annotations

from typing import Sequence

from aisef2.arch.enums import EventType as T

GATE = "story"
#: the projections a story decision reads (F11: nothing else may be cited by a gate)
PROJECTIONS = ("story_state", "budgets", "failure_owner", "retry_target")


def check(run, story_id: str, stage: str, passed: bool, detail: str) -> int:
    return run.append(T.GATE_CHECK, {"gate": GATE, "check": f"{story_id}:{stage}", "passed": bool(passed),
                                     "detail": detail}).seq


def decision(run, checks: Sequence[int], passed: bool) -> int:
    return run.append(T.GATE_DECISION, {"gate": GATE, "passed": bool(passed), "projections": list(PROJECTIONS)},
                      source_seqs=checks).seq
