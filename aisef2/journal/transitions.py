"""E6 (v2.3, contract C-1 §3) — THE story/run lifecycle transition table, as one pure value.

The 2.2.0 kernel defines the story lifecycle twice and the two definitions diverge (C-1 §1 M1/M2): the format-3
writer-validator and the StoryState projection each hold their own if-chain. This module is the single table both
derive from, frozen by the C-1 design (docs/v2.3/drafts/FORMAT-4-DESIGN-DRAFT.md §3, blob 41506829d2):

* `STORY_STATES` — the 13 states, the full product of phase x outcome the two 2.2.0 validators jointly distinguish.
* `symbol_of(event_type, data)` — the pure discriminant. Most types map to themselves; the payload-dependent ones
  split (`story/admitted` on `admitted`, `run/interrupted` on `abandoned`). It never raises: an unknown type is
  returned as given.
* `STORY` — `Mapping[(state, symbol), state]`: the moves. Absence of a key = REFUSE.
* `WITHIN` — `Mapping[symbol, frozenset[state]]`: events legal in a state without moving it. Resource/tool kinds are
  NOT in the table: their lifecycle rules stay format 2's, as written (sealed).
* `RUN` — the run-level table, lifted verbatim from `projections/terminal_state.py` `_RUN`, re-keyed by symbol.
* `TABLE_DIGEST` — `product.contract.digest` of the canonical JSON form of the four values above (`_digest_form`),
  asserted as a literal by `tests/v2/test_v23_transitions.py`: consumers pin the table by this digest, and any edit
  to the values is a visible one-line diff.

The module holds only pure values plus the one pure function — no wall-clock, no prose-as-control, no kernel import
(C-1 §3.1). Consumers (C-1 §3.2): the format-4 validator, the format-3 adapter, StoryState v3, TerminalState v2,
the E1 verdict fold and the C3b no_progress projection.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

#: The 13 story states (C-1 §3.1). ABSENT is the state of a story the journal has never begun.
STORY_STATES: tuple[str, ...] = (
    "ABSENT", "BEGIN", "BEGIN_REFUSED", "ACTIVE",
    "DECIDED_COMMIT", "DECIDED_ROLLBACK", "DECIDED_RETRY",
    "DISPOSED_COMMIT", "DISPOSED_ROLLBACK", "DISPOSED_RETRY",
    "ENDED_COMMIT", "ENDED_ROLLBACK", "ENDED_RETRY",
)


def symbol_of(event_type: Any, data: Any) -> Any:
    """The table symbol of an event: its type string, except the payload-dependent splits. Total — never raises."""
    if event_type == "story/admitted":
        admitted = data.get("admitted") if isinstance(data, Mapping) else None
        return "story/admitted:accepted" if admitted is True else "story/admitted:refused"
    if event_type == "run/interrupted":
        abandoned = data.get("abandoned") if isinstance(data, Mapping) else None
        return "run/interrupted:abandoning" if abandoned is True else "run/interrupted:first"
    return event_type


#: The moves: exactly the 2.2.0 semantics of StoryState v2 (`story_state.py`) + `_OUTCOMES`/`_WITHIN`, re-keyed.
STORY: Mapping[tuple[str, str], str] = MappingProxyType({
    ("ABSENT", "story/begin"): "BEGIN",
    ("ENDED_RETRY", "story/begin"): "BEGIN",
    ("BEGIN", "story/admitted:accepted"): "ACTIVE",
    ("BEGIN", "story/admitted:refused"): "BEGIN_REFUSED",
    ("ACTIVE", "story/commit"): "DECIDED_COMMIT",
    ("BEGIN", "story/rollback"): "DECIDED_ROLLBACK",
    ("BEGIN_REFUSED", "story/rollback"): "DECIDED_ROLLBACK",
    ("ACTIVE", "story/rollback"): "DECIDED_ROLLBACK",
    ("BEGIN", "story/retry"): "DECIDED_RETRY",
    ("BEGIN_REFUSED", "story/retry"): "DECIDED_RETRY",
    ("ACTIVE", "story/retry"): "DECIDED_RETRY",
    ("DECIDED_COMMIT", "story/dispose"): "DISPOSED_COMMIT",
    ("DECIDED_ROLLBACK", "story/dispose"): "DISPOSED_ROLLBACK",
    ("DECIDED_RETRY", "story/dispose"): "DISPOSED_RETRY",
    ("DISPOSED_COMMIT", "story/end"): "ENDED_COMMIT",
    ("DISPOSED_ROLLBACK", "story/end"): "ENDED_ROLLBACK",
    ("DISPOSED_RETRY", "story/end"): "ENDED_RETRY",
})

_EVERY_STATE_BUT_ABSENT = frozenset(STORY_STATES) - {"ABSENT"}

#: Events legal in a state without moving it (C-1 §3.1). `story/plan-drift` in BEGIN_REFUSED:
#: P3-PROJECTION-SEMANTICS.md §14 "MUST emit" — a blocked story still records drift.
WITHIN: Mapping[str, frozenset[str]] = MappingProxyType({
    "probe/evaluated": frozenset({"BEGIN", "BEGIN_REFUSED", "ACTIVE"}),
    "provider/request": frozenset({"ACTIVE"}),
    "proof/verified": frozenset({"ACTIVE"}),
    "tests/adequacy": frozenset({"ACTIVE"}),
    "failure/observed": _EVERY_STATE_BUT_ABSENT,
    "story/plan-drift": frozenset({"ACTIVE", "BEGIN_REFUSED"}),
    "provider/result": _EVERY_STATE_BUT_ABSENT,  # closers may land during unwinding (C-1 §1 M7)
    "story/completed": frozenset({"ENDED_COMMIT"}),  # the G6 marker (C-1 §4.5)
})

#: The run-level table — `terminal_state._RUN` verbatim, re-keyed by symbol: symbol -> (states it may follow,
#: state it leads to). The §20.2 counter rule (only a second interrupt abandons) stays the projection's.
RUN: Mapping[str, tuple[tuple[str, ...], str]] = MappingProxyType({
    "run/begin": (("NOT_STARTED",), "RUNNING"),
    "run/dispose-begin": (("RUNNING", "INTERRUPTED"), "DISPOSING"),
    "run/interrupted:first": (("RUNNING", "DISPOSING"), "INTERRUPTED"),
    "run/interrupted:abandoning": (("INTERRUPTED", "DISPOSING"), "ABANDONED"),
    "run/end": (("RUNNING", "DISPOSING", "INTERRUPTED"), "ENDED"),
})


def _digest_form() -> dict:
    """The JSON-foldable form TABLE_DIGEST binds (internal; the digest itself is computed by the test with
    `product.contract.digest` and asserted against the literal below — this module imports nothing of the kernel)."""
    return {
        "STORY_STATES": list(STORY_STATES),
        "STORY": sorted([state, symbol, to] for (state, symbol), to in STORY.items()),
        "WITHIN": {symbol: sorted(states) for symbol, states in WITHIN.items()},
        "RUN": {symbol: [list(after), to] for symbol, (after, to) in RUN.items()},
    }


#: sha256 (product.contract.digest) of canonical(_digest_form()) — the one-line pin consumers rely on (C-1 §3.1).
TABLE_DIGEST = "1107b6898b0ad240cde695de0f1d6952a1cbd610c1e3a5539b3b461e446824ff"
