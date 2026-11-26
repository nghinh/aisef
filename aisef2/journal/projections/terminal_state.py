"""Projection 5 — terminal state (version 2): the run's, and each story's (P3-PROJECTION-SEMANTICS.md §5), keyed off
THE transition table (`aisef2/journal/transitions.py`, C-1 §3.2 consumer 4): the run-level part reads `RUN` (the
table lifted verbatim from this module's v1 `_RUN`), the story outcome words are read off the table's `DECIDED_*`
states. The fold output is VERSION 1's exactly over every format ≤ 3 journal (the J7 bound, pinned by the
equivalence test). Nothing follows run/end or an abandonment; a second interrupt abandons (§20.2 — the counter rule
stays this projection's, as the table module declares); no story begins once shutdown has started (§18)."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T
from aisef2.journal.fold import ProjectionError
from aisef2.journal.transitions import RUN, STORY, symbol_of

#: outcome words read off the table states: story/commit -> DECIDED_COMMIT -> "COMMIT", … (C-1 §3.2 consumer 4)
_OUTCOME = {s: STORY[("ACTIVE", s)].removeprefix("DECIDED_")
            for s in (T.STORY_COMMIT.value, T.STORY_ROLLBACK.value, T.STORY_RETRY.value)}


class TerminalState:
    id = ControlProjection.TERMINAL_STATE.value
    version = 2

    def initial(self):
        return {"run": "NOT_STARTED", "interrupts": 0, "stories": {}, "pending": {}}

    def step(self, state, event):
        t, d = event.type, event.data
        if state["run"] in ("ENDED", "ABANDONED"):
            raise ProjectionError(f"terminal_state: {t} after the run is {state['run']}")
        symbol = symbol_of(t, d)
        if symbol in RUN:
            after, to = RUN[symbol]
            if state["run"] not in after:
                raise ProjectionError(f"terminal_state: {t} while the run is {state['run']}")
            abandoned = None if t != T.RUN_INTERRUPTED.value else symbol.endswith(":abandoning")
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
