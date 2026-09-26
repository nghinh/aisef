"""Projection 2 — failure owner: the owner of the failure that decided a story's attempt (P3-PROJECTION-SEMANTICS.md
§2). A rollback's recorded owner is its cited failure's owner, never the stage that observed it (§17)."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T
from aisef2.journal.fold import ProjectionError


class FailureOwner:
    id = ControlProjection.FAILURE_OWNER.value
    version = 1

    def initial(self):
        return {}

    def step(self, state, event):
        t, d = event.type, event.data
        if t == T.STORY_BEGIN.value:
            prev = state.get(d["story_id"])
            return {**state, d["story_id"]: {"attempt": (prev["attempt"] if prev is not None else 0) + 1,
                                             "begin_seq": event.seq, "observed": {}, "owner": None, "code": None,
                                             "failure_seq": None, "cited": False}}
        if t not in (T.FAILURE_OBSERVED.value, T.STORY_ROLLBACK.value, T.STORY_RETRY.value):
            return state
        cur = state.get(d["story_id"])
        if cur is None:
            raise ProjectionError(f"failure_owner: {t} for story {d['story_id']}, which has not begun")
        if t == T.FAILURE_OBSERVED.value:
            new = {**cur, "observed": {**cur["observed"], str(event.seq): [d["owner"], d["code"]]}}
            if not cur["cited"]:
                new = {**new, "owner": d["owner"], "code": d["code"], "failure_seq": event.seq}
            return {**state, d["story_id"]: new}
        cited = str(event.source_seqs[0])
        if cited not in cur["observed"]:
            raise ProjectionError(f"failure_owner: {t} for story {d['story_id']} cites seq {cited}, not a failure of "
                                  f"its attempt {cur['attempt']}")
        owner, code = cur["observed"][cited]
        return {**state, d["story_id"]: {**cur, "owner": owner, "code": code, "failure_seq": int(cited),
                                         "cited": True}}
