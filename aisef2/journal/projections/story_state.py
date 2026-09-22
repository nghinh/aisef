"""Projection 1 — story state: §17's lifecycle per story and attempt (P3-PROJECTION-SEMANTICS.md §1)."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T
from aisef2.journal.fold import ProjectionError

_OUTCOMES = {T.STORY_COMMIT.value: ("COMMIT", ("ACTIVE",)), T.STORY_ROLLBACK.value: ("ROLLBACK", ("BEGIN", "ACTIVE")),
             T.STORY_RETRY.value: ("RETRY", ("BEGIN", "ACTIVE"))}
#: types that leave the state unchanged, and the states they may occur in (None: any, once the story began)
_WITHIN = {T.PROBE_EVALUATED.value: ("BEGIN", "ACTIVE"), T.PROVIDER_REQUEST.value: ("ACTIVE",),
           T.FAILURE_OBSERVED.value: None}
_NAMED = {T.STORY_BEGIN.value, T.STORY_ADMITTED.value, T.STORY_DISPOSE.value, T.STORY_END.value,
          T.STORY_PLAN_DRIFT.value, *_OUTCOMES, *_WITHIN}


class StoryState:
    id = ControlProjection.STORY_STATE.value
    version = 1

    def initial(self):
        return {}

    def step(self, state, event):
        t = event.type
        if t not in _NAMED:
            return state
        sid = event.data["story_id"]
        cur = state.get(sid)
        at = cur["state"] if cur is not None else None

        def refuse():
            raise ProjectionError(f"story_state: {t} for story {sid} in state {at}: not a §17 transition")

        if t == T.STORY_BEGIN.value:
            if cur is not None and not (at == "ENDED" and cur["outcome"] == "RETRY"):
                refuse()
            new = {"state": "BEGIN", "attempt": (cur["attempt"] if cur is not None else 0) + 1, "admitted": None,
                   "outcome": None}
        elif cur is None:
            refuse()
        elif t == T.STORY_ADMITTED.value:
            if at != "BEGIN" or cur["admitted"] is not None:
                refuse()
            admitted = event.data["admitted"]
            new = {**cur, "admitted": admitted, "state": "ACTIVE" if admitted else "BEGIN"}
        elif t in _OUTCOMES:
            outcome, allowed = _OUTCOMES[t]
            if at not in allowed:
                refuse()
            new = {**cur, "state": outcome, "outcome": outcome}
        elif t == T.STORY_DISPOSE.value:
            if at not in ("COMMIT", "ROLLBACK", "RETRY"):
                refuse()
            new = {**cur, "state": "DISPOSE"}
        elif t == T.STORY_END.value:
            if at != "DISPOSE":
                refuse()
            new = {**cur, "state": "ENDED"}
        elif t == T.STORY_PLAN_DRIFT.value:  # after the attempt's admission; a blocked story still records drift (§14)
            if not (at == "ACTIVE" or at == "BEGIN" and cur["admitted"] is False):
                refuse()
            return state
        else:
            allowed = _WITHIN[t]
            if allowed is not None and at not in allowed:
                refuse()
            return state
        return {**state, sid: new}
