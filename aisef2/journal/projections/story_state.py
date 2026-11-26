"""Projection 1 — story state (version 3): §17's lifecycle per story and attempt (P3-PROJECTION-SEMANTICS.md §1),
keyed off THE transition table (`aisef2/journal/transitions.py`, C-1 §3.2 consumer 3). Version 2's if-chain is
re-derived as `STORY`/`WITHIN` lookups; the projection keeps only the attempt counter and the admitted flag beside
the table state. The FOLD OUTPUT IS VERSION 2's EXACTLY — same dict words, same refusal set, same messages — over
every format ≤ 3 journal (the J7 bound, pinned by the equivalence test in tests/v2/test_v23_projections.py).
Version 2 (V2-005) admitted `proof/verified` and `tests/adequacy` inside an ACTIVE attempt; the table says the same."""

from __future__ import annotations

from aisef2.arch.enums import ControlProjection, EventType as T
from aisef2.journal.fold import ProjectionError
from aisef2.journal.transitions import STORY, WITHIN, symbol_of

#: table state -> the v2 fold words (state, admitted, outcome); None keeps the story's current field (J7: the fold
#: output is v2's exactly). BEGIN keeps admitted None; BEGIN_REFUSED/ACTIVE carry the admission verdict.
_WORDS = {
    "BEGIN": ("BEGIN", None, None),
    "BEGIN_REFUSED": ("BEGIN", False, None),
    "ACTIVE": ("ACTIVE", True, None),
    "DECIDED_COMMIT": ("COMMIT", None, "COMMIT"),
    "DECIDED_ROLLBACK": ("ROLLBACK", None, "ROLLBACK"),
    "DECIDED_RETRY": ("RETRY", None, "RETRY"),
    "DISPOSED_COMMIT": ("DISPOSE", None, None),
    "DISPOSED_ROLLBACK": ("DISPOSE", None, None),
    "DISPOSED_RETRY": ("DISPOSE", None, None),
    "ENDED_COMMIT": ("ENDED", None, None),
    "ENDED_ROLLBACK": ("ENDED", None, None),
    "ENDED_RETRY": ("ENDED", None, None),
}
#: the types this projection folds — exactly v2's named set (J7: `provider/result`, `story/completed` and the gate
#: kinds stay pass-through; their rules are the validators', see FoldHasNoGateLeg).
_MOVES = {T.STORY_BEGIN.value, T.STORY_ADMITTED.value, T.STORY_COMMIT.value, T.STORY_ROLLBACK.value,
          T.STORY_RETRY.value, T.STORY_DISPOSE.value, T.STORY_END.value}
_STAYS = {T.PROBE_EVALUATED.value, T.PROVIDER_REQUEST.value, T.PROOF_VERIFIED.value, T.TESTS_ADEQUACY.value,
          T.FAILURE_OBSERVED.value, T.STORY_PLAN_DRIFT.value}
_NAMED = _MOVES | _STAYS


class StoryState:
    id = ControlProjection.STORY_STATE.value
    version = 3

    def initial(self):
        return {}

    def step(self, state, event):
        t = event.type
        if t not in _NAMED:
            return state
        sid = event.data["story_id"]
        cur = state.get(sid)
        # the v2 words back to the table state — total over every dict the fold can hold (admitted True in BEGIN
        # is unreachable: an accepted admission is the move to ACTIVE; decided words keep admitted untouched)
        if cur is None:
            at = "ABSENT"
        elif cur["state"] == "BEGIN":
            at = "BEGIN" if cur["admitted"] is None else "BEGIN_REFUSED"
        elif cur["state"] in ("COMMIT", "ROLLBACK", "RETRY"):
            at = f"DECIDED_{cur['state']}"
        elif cur["state"] == "DISPOSE":
            at = f"DISPOSED_{cur['outcome']}"
        elif cur["state"] == "ENDED":
            at = f"ENDED_{cur['outcome']}"
        else:
            at = cur["state"]  # "ACTIVE"
        symbol = symbol_of(t, event.data)
        to = STORY.get((at, symbol))
        if to is not None:
            word, admitted, outcome = _WORDS[to]
            prev_attempt = cur["attempt"] if cur is not None else 0
            if t == T.STORY_BEGIN.value:
                new = {"state": word, "attempt": prev_attempt + 1, "admitted": admitted, "outcome": outcome}
            else:
                new = {**cur, "state": word,
                       **({"admitted": admitted} if admitted is not None or to.startswith("BEGIN") else {}),
                       **({"outcome": outcome} if outcome is not None else {})}
            return {**state, sid: new}
        if t in _STAYS and at in WITHIN.get(symbol, ()):
            return state
        raise ProjectionError(f"story_state: {t} for story {sid} in state "
                              f"{cur['state'] if cur is not None else None}: not a §17 transition")
