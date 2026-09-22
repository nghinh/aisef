"""RFC §17 (RETRY), §22 — typed retry budgets as projections (WP-4.5; P4-LIFETIME-SEMANTICS.md §6).

A retry is decided from the journal only: the `retry_target` projection names the budget the story's latest failure
would charge (its owner, when the taxonomy makes it retryable; none otherwise), the `budgets` projection says how many
retries that budget has already been charged, and the resolved retry counts say how many it allows (`None`: no
approved count, so no retry). Nothing here counts: the decision is recomputed from the journal every time, so it can
never disagree with it (SS-64), and a failure is only ever charged to its own owner's budget — a credential
rejection never reaches the developer's (D-006). Static check NO_SIDE_RETRY_COUNTER keeps a counter out of the
kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from aisef2.arch.enums import ControlProjection as P, Owner
from aisef2.journal.event import Event
from aisef2.journal.fold import fold
from aisef2.journal.projections import PROJECTIONS


@dataclass(frozen=True)
class Charge:
    story: str
    retry: bool
    budget: str | None      # the owner whose budget a retry charges; None when the failure is not retryable
    spent: int              # retries already charged to that budget in this story (budgets projection)
    limit: int | None       # the resolved retry count for that budget; None when none is approved
    failure_seq: int | None  # the failure a retry would cite (retry_target)
    reason: str


def charge(events: Sequence[Event], story: str, limits: Mapping[Owner, int | None]) -> Charge:
    """Whether `story` may retry now, and against which budget — from the journal prefix `events` alone."""
    target = fold(PROJECTIONS[P.RETRY_TARGET], events).get(story)
    if target is None or target["failure_seq"] is None:
        return Charge(story, False, None, 0, None, None, f"{story} has no failure to retry")
    budget, seq = target["budget"], target["failure_seq"]
    if budget is None:
        return Charge(story, False, None, 0, None, seq, f"the failure at seq {seq} is not retryable: it charges no "
                                                        "budget (§22)")
    spent = fold(PROJECTIONS[P.BUDGETS], events)["retries"].get(story, {}).get(budget, 0)
    limit = limits.get(Owner(budget))
    if limit is None:
        return Charge(story, False, budget, spent, None, seq, f"no approved retry count for the {budget} budget")
    if spent >= limit:
        return Charge(story, False, budget, spent, limit, seq, f"the {budget} budget is spent ({spent} of {limit}): "
                                                               "the story stops; no other budget is consulted")
    return Charge(story, True, budget, spent, limit, seq, f"retry against the {budget} budget ({spent + 1} of {limit})")


def developer_spend(events: Sequence[Event], story: str) -> Mapping[str, int]:
    """Developer calls charged per criterion in `story` (budgets projection): a PRE_SATISFIED criterion is never one."""
    return fold(PROJECTIONS[P.BUDGETS], events)["developer"].get(story, {"criteria": {}})["criteria"]
