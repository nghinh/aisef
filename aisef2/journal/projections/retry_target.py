"""Projection 4 — retry target: the budget a retry of a story's attempt would charge — the failure's owner when it is
retryable, else none. Reads only `owner` and `retryable` (§22; P3-PROJECTION-SEMANTICS.md §4)."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T
from aisef2.journal.fold import ProjectionError


class RetryTarget:
    id = ControlProjection.RETRY_TARGET.value
    version = 1

    def initial(self):
        return {}

    def step(self, state, event):
        t, d = event.type, event.data
        if t == T.STORY_BEGIN.value:
            return {**state, d["story_id"]: {"budget": None, "failure_seq": None}}
        if t != T.FAILURE_OBSERVED.value:
            return state
        if d["story_id"] not in state:
            raise ProjectionError(f"retry_target: failure/observed for story {d['story_id']}, which has not begun")
        return {**state, d["story_id"]: {"budget": d["owner"] if d["retryable"] else None, "failure_seq": event.seq}}
