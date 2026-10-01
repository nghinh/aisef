"""Projection 5 — terminal state: the run's, and each story's (P3-PROJECTION-SEMANTICS.md §5). Nothing follows run/end
or an abandonment; a second interrupt abandons (§20.2); no story begins once shutdown has started (§18)."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T
from aisef2.journal.fold import ProjectionError

#: run-level event (and value of `abandoned` for run/interrupted) -> (states it may follow, state it leads to)
_RUN = {(T.RUN_BEGIN.value, None): (("NOT_STARTED",), "RUNNING"),
        (T.RUN_DISPOSE_BEGIN.value, None): (("RUNNING", "INTERRUPTED"), "DISPOSING"),
        (T.RUN_INTERRUPTED.value, False): (("RUNNING", "DISPOSING"), "INTERRUPTED"),
        (T.RUN_INTERRUPTED.value, True): (("INTERRUPTED", "DISPOSING"), "ABANDONED"),
        (T.RUN_END.value, None): (("RUNNING", "DISPOSING", "INTERRUPTED"), "ENDED")}
_OUTCOME = {T.STORY_COMMIT.value: "COMMIT", T.STORY_ROLLBACK.value: "ROLLBACK", T.STORY_RETRY.value: "RETRY"}


class TerminalState:
    id = ControlProjection.TERMINAL_STATE.value
    version = 1

    def initial(self):
        return {"run": "NOT_STARTED", "interrupts": 0, "stories": {}, "pending": {}}

    def step(self, state, event):
        t, d = event.type, event.data
        if state["run"] in ("ENDED", "ABANDONED"):
            raise ProjectionError(f"terminal_state: {t} after the run is {state['run']}")
        abandoned = d["abandoned"] if t == T.RUN_INTERRUPTED.value else None
        if (t, abandoned) in _RUN:
            after, to = _RUN[(t, abandoned)]
            if state["run"] not in after:
                raise ProjectionError(f"terminal_state: {t} while the run is {state['run']}")
            if abandoned is not None and abandoned is not (state["interrupts"] > 0):
                raise ProjectionError(f"terminal_state: run/interrupted with abandoned {abandoned} after "
                                      f"{state['interrupts']} interrupts: only a second interrupt abandons (§20.2)")
            return {**state, "run": to, "interrupts": state["interrupts"] + (abandoned is not None)}
        sid = d.get("story_id")
        if t == T.STORY_BEGIN.value:
            if state["run"] != "RUNNING" or state["stories"].get(sid, "OPEN") != "OPEN":
                raise ProjectionError(f"terminal_state: story/begin for {sid} ({state['stories'].get(sid)}) while the "
                                      f"run is {state['run']}")
            return {**state, "stories": {**state["stories"], sid: "RUNNING"}}
        if t in _OUTCOME:
            if state["stories"].get(sid) != "RUNNING" or sid in state["pending"]:
                raise ProjectionError(f"terminal_state: {t} for {sid}, which has no open attempt without an outcome")
            return {**state, "pending": {**state["pending"], sid: _OUTCOME[t]}}
        if t == T.STORY_END.value:
            if sid not in state["pending"]:
                raise ProjectionError(f"terminal_state: story/end for {sid} with no transaction outcome")
            outcome = state["pending"][sid]
            return {**state, "stories": {**state["stories"], sid: "OPEN" if outcome == "RETRY" else outcome},
                    "pending": {k: v for k, v in state["pending"].items() if k != sid}}
        return state
