"""CORE-2 — the J7 equality bound (C-1 §3.2 consumers 3-4, §7 item 6): StoryState v3 and TerminalState v2 are the
2.2.0 projections re-keyed off the transition table, and their FOLD IS THE OLD FOLD over every format ≤ 3 journal.

The old implementations are embedded here VERBATIM as the reference oracles (copied from git blob at commit
175ba3a8, the V2-005 landing — the last pre-CORE-2 edit of each file), so the bound is checked against the real
2.2.0 semantics, not against the new code's own idea of them:

* per-cell: v3's verdict AND successor dict equal v2's on every (story state cell, 2.2.0 symbol) — full dict
  equality, so admitted/outcome/attempt drift is caught, not just the phase word;
* per-journal: folds of both live projections equal the reference folds over the committed fixture corpus and
  generated format-2/3 journals exercising retry, refusal, unwind, interrupt and failure paths.
"""

from __future__ import annotations

import pathlib
import unittest
from types import SimpleNamespace

from aisef2.arch.enums import EventType as T
from aisef2.journal import format3 as f3
from aisef2.journal.fold import ProjectionError, fold
from aisef2.journal.projections.story_state import StoryState
from aisef2.journal.projections.terminal_state import TerminalState

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "journal"

# ------------------------------------------------------------------ the 2.2.0 reference implementations, verbatim

_OUTCOMES = {T.STORY_COMMIT.value: ("COMMIT", ("ACTIVE",)), T.STORY_ROLLBACK.value: ("ROLLBACK", ("BEGIN", "ACTIVE")),
             T.STORY_RETRY.value: ("RETRY", ("BEGIN", "ACTIVE"))}
_WITHIN = {T.PROBE_EVALUATED.value: ("BEGIN", "ACTIVE"), T.PROVIDER_REQUEST.value: ("ACTIVE",),
           T.PROOF_VERIFIED.value: ("ACTIVE",), T.TESTS_ADEQUACY.value: ("ACTIVE",), T.FAILURE_OBSERVED.value: None}
_NAMED = {T.STORY_BEGIN.value, T.STORY_ADMITTED.value, T.STORY_DISPOSE.value, T.STORY_END.value,
          T.STORY_PLAN_DRIFT.value, *_OUTCOMES, *_WITHIN}


class StoryStateV2Reference:
    """aisef2/journal/projections/story_state.py at 175ba3a8 — step() verbatim (class fields dropped)."""

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


_RUN = {(T.RUN_BEGIN.value, None): (("NOT_STARTED",), "RUNNING"),
        (T.RUN_DISPOSE_BEGIN.value, None): (("RUNNING", "INTERRUPTED"), "DISPOSING"),
        (T.RUN_INTERRUPTED.value, False): (("RUNNING", "DISPOSING"), "INTERRUPTED"),
        (T.RUN_INTERRUPTED.value, True): (("INTERRUPTED", "DISPOSING"), "ABANDONED"),
        (T.RUN_END.value, None): (("RUNNING", "DISPOSING", "INTERRUPTED"), "ENDED")}
_OUTCOME = {T.STORY_COMMIT.value: "COMMIT", T.STORY_ROLLBACK.value: "ROLLBACK", T.STORY_RETRY.value: "RETRY"}


class TerminalStateV1Reference:
    """aisef2/journal/projections/terminal_state.py at 175ba3a8 — step() verbatim (class fields dropped)."""

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


# ----------------------------------------------------------------------------------------------- per-cell oracle

#: the 2.2.0 symbols: every v2-named type, with story/admitted split (run kinds are TerminalState's)
SYMBOLS_220 = sorted((_NAMED - {T.STORY_ADMITTED.value}) | {"story/admitted:accepted", "story/admitted:refused"})
#: a v2 dict representative of each of the 13 table states (ABSENT = no entry)
V2_CELLS = {
    "ABSENT": None,
    "BEGIN": {"state": "BEGIN", "attempt": 1, "admitted": None, "outcome": None},
    "BEGIN_REFUSED": {"state": "BEGIN", "attempt": 1, "admitted": False, "outcome": None},
    "ACTIVE": {"state": "ACTIVE", "attempt": 1, "admitted": True, "outcome": None},
    **{f"DECIDED_{o}": {"state": o, "attempt": 1, "admitted": True, "outcome": o}
       for o in ("COMMIT", "ROLLBACK", "RETRY")},
    **{f"DISPOSED_{o}": {"state": "DISPOSE", "attempt": 1, "admitted": True, "outcome": o}
       for o in ("COMMIT", "ROLLBACK", "RETRY")},
    **{f"ENDED_{o}": {"state": "ENDED", "attempt": 1, "admitted": True, "outcome": o}
       for o in ("COMMIT", "ROLLBACK", "RETRY")},
}


class PerCellJ7(unittest.TestCase):
    """v3.step == v2.step on every (cell, symbol): same refusal set, same successor DICT (full equality)."""

    def outcome(self, projection, prior, kind, data):
        try:
            return projection.step(prior, SimpleNamespace(type=kind, data=data))
        except ProjectionError as e:
            return ("REFUSED", str(e))

    def test_every_cell_and_symbol_agree_with_the_220_reference(self):
        for cell, cur in V2_CELLS.items():
            for symbol in SYMBOLS_220:
                kind, _, variant = symbol.partition(":")
                data = {"story_id": "S"}
                if variant:
                    data["admitted"] = variant == "accepted"
                prior = {} if cur is None else {"S": dict(cur)}
                with self.subTest(cell=cell, symbol=symbol):
                    self.assertEqual(self.outcome(StoryState(), prior, kind, data),
                                     self.outcome(StoryStateV2Reference(), prior, kind, data))

    def test_begin_refused_variant_cells_agree_too(self):
        # the BEGIN_REFUSED-reachable decided cells carry admitted False — parity must hold there as well
        for o in ("ROLLBACK", "RETRY"):
            for phase in ("DECIDED", "DISPOSED", "ENDED"):
                cur = {"state": {"DECIDED": o, "DISPOSED": "DISPOSE", "ENDED": "ENDED"}[phase],
                       "attempt": 2, "admitted": False, "outcome": o}
                for symbol in SYMBOLS_220:
                    kind, _, variant = symbol.partition(":")
                    data = {"story_id": "S"}
                    if variant:
                        data["admitted"] = variant == "accepted"
                    with self.subTest(cell=f"{phase}_{o}+refused", symbol=symbol):
                        self.assertEqual(self.outcome(StoryState(), {"S": dict(cur)}, kind, data),
                                         self.outcome(StoryStateV2Reference(), {"S": dict(cur)}, kind, data))


# --------------------------------------------------------------------------------------------- per-journal J7

def specs_to_events(specs):
    return [SimpleNamespace(seq=i, type=t, data=d) for i, (t, d) in enumerate(specs)]


S = "story_id"
#: generated format-≤3 shaped event streams: retry/re-begin, refusal, unwind, interrupts, failure, plan-drift
STREAMS = {
    "commit_path": [("run/begin", {}), ("story/begin", {S: "A"}), ("story/admitted", {S: "A", "admitted": True}),
                    ("probe/evaluated", {S: "A"}), ("provider/request", {S: "A"}), ("proof/verified", {S: "A"}),
                    ("tests/adequacy", {S: "A"}), ("story/commit", {S: "A"}), ("story/dispose", {S: "A"}),
                    ("story/end", {S: "A"}), ("run/end", {})],
    "retry_then_commit": [("run/begin", {}), ("story/begin", {S: "A"}),
                          ("story/admitted", {S: "A", "admitted": True}), ("failure/observed", {S: "A"}),
                          ("story/retry", {S: "A"}), ("story/dispose", {S: "A"}), ("story/end", {S: "A"}),
                          ("story/begin", {S: "A"}), ("story/admitted", {S: "A", "admitted": True}),
                          ("story/commit", {S: "A"}), ("story/dispose", {S: "A"}), ("story/end", {S: "A"})],
    "admission_refused_drift_rollback": [("run/begin", {}), ("story/begin", {S: "B"}),
                                         ("story/admitted", {S: "B", "admitted": False}),
                                         ("story/plan-drift", {S: "B"}), ("probe/evaluated", {S: "B"}),
                                         ("story/rollback", {S: "B"}), ("story/dispose", {S: "B"}),
                                         ("story/end", {S: "B"})],
    "interrupt_dispose": [("run/begin", {}), ("story/begin", {S: "C"}),
                          ("run/interrupted", {"abandoned": False}), ("run/dispose-begin", {}),
                          ("story/rollback", {S: "C"}), ("story/dispose", {S: "C"}), ("story/end", {S: "C"}),
                          ("run/end", {})],
    "abandoned": [("run/begin", {}), ("run/interrupted", {"abandoned": False}),
                  ("run/interrupted", {"abandoned": True})],
    "two_stories": [("run/begin", {}), ("story/begin", {S: "A"}), ("story/begin", {S: "B"}),
                    ("story/admitted", {S: "A", "admitted": True}), ("story/admitted", {S: "B", "admitted": False}),
                    ("story/retry", {S: "B"}), ("story/commit", {S: "A"}), ("story/dispose", {S: "A"}),
                    ("story/dispose", {S: "B"}), ("story/end", {S: "A"}), ("story/end", {S: "B"})],
}


class PerJournalJ7(unittest.TestCase):
    def outcome(self, projection, events):
        try:
            return fold(projection, events)
        except ProjectionError as e:
            return ("REFUSED", str(e))

    def test_generated_streams_fold_identically(self):
        for name, specs in STREAMS.items():
            events = specs_to_events(specs)
            with self.subTest(stream=name, projection="story_state"):
                self.assertEqual(self.outcome(StoryState(), events), self.outcome(StoryStateV2Reference(), events))
            with self.subTest(stream=name, projection="terminal_state"):
                self.assertEqual(self.outcome(TerminalState(), events),
                                 self.outcome(TerminalStateV1Reference(), events))

    def test_committed_fixture_journals_fold_identically(self):
        folded = 0
        for path in sorted(FIXTURES.glob("*.jsonl")):
            try:
                journal = f3.reconstruct(path.read_text(encoding="utf-8"))
            except Exception:
                continue  # unreadable fixtures are the readers' tests, not a fold input
            folded += 1
            for live, ref in ((StoryState(), StoryStateV2Reference()),
                              (TerminalState(), TerminalStateV1Reference())):
                with self.subTest(fixture=path.name, projection=type(live).__name__):
                    self.assertEqual(self.outcome(live, journal.events), self.outcome(ref, journal.events))
        self.assertGreater(folded, 0, "the fixture corpus went missing — J7 checked nothing")


if __name__ == "__main__":
    unittest.main()
