"""C-1 (FORMAT-4 freeze, blob 41506829d2) §3 — the transition table: value pins, TABLE_DIGEST determinism,
`symbol_of`, the T10 cell oracle against the 2.2.0 StoryState projection, and the freeze package §4b lifecycle
controls T1–T8b at the A (append) and R (reconstruct) sites.

DEFERRED to the measured CORE-2 batch (the F site and the format-3 adapter do not exist yet by the landing
boundary — projections/ and format3.py are not this merge's to edit):
* the F (fold) leg of every three-site refusal — StoryState v3 / TerminalState v2 keyed off the table;
* T10's golden-corpus half: f3-with-table == f3-at-2.2.0 event-for-event over the E5 fault-matrix journals,
  the p6 scenarios and the 10 committed fixtures (needs the format3 adapter);
* T17: the fold oracle (`oracle_problems`) for StoryState v3 + TerminalState v2 over the golden corpus.
The cell oracle below (every (state, symbol) against StoryState VERSION 2 through the state adapter) is the
now-testable half of T10: the table claims to be exactly the 2.2.0 semantics re-keyed (C-1 §3.1)."""

import unittest
from types import SimpleNamespace

from aisef2.arch.enums import EventType as T
from aisef2.journal import format4 as f4
from aisef2.journal import transitions as tr
from aisef2.journal.event import JournalError, carried
from aisef2.journal.fold import ProjectionError
from aisef2.journal.projections.story_state import StoryState
from aisef2.journal.projections.terminal_state import _RUN as TERMINAL_RUN
from aisef2.product.contract import digest
from tests.v2.test_v23_format4 import (
    SHA, World, adequacy_payload, admission, proof_payload, request_payload, sealed_record,
)

#: the table symbols derivable from 2.2.0 kinds — the cell oracle's alphabet (the two new kinds are format 4's)
SYMBOLS_220 = (
    "story/begin", "story/admitted:accepted", "story/admitted:refused", "story/commit", "story/rollback",
    "story/retry", "story/dispose", "story/end", "story/plan-drift", "probe/evaluated", "provider/request",
    "proof/verified", "tests/adequacy", "failure/observed",
)


class TableValues(unittest.TestCase):
    maxDiff = None

    def test_the_13_states(self):
        self.assertEqual(len(tr.STORY_STATES), 13)
        self.assertEqual(len(set(tr.STORY_STATES)), 13)
        self.assertEqual(tr.STORY_STATES[0], "ABSENT")

    def test_story_rows_and_within_are_over_the_declared_states_and_vocabulary(self):
        self.assertEqual(len(tr.STORY), 17)
        for (state, symbol), to in tr.STORY.items():
            self.assertIn(state, tr.STORY_STATES)
            self.assertIn(to, tr.STORY_STATES)
            self.assertIn(symbol.split(":")[0], f4.VOCABULARY4)
        for symbol, states in tr.WITHIN.items():
            self.assertIn(symbol, f4.VOCABULARY4)
            self.assertTrue(states <= set(tr.STORY_STATES))
        self.assertEqual(set(tr.WITHIN), {"probe/evaluated", "provider/request", "proof/verified", "tests/adequacy",
                                          "failure/observed", "story/plan-drift", "provider/result",
                                          "story/completed"})
        self.assertEqual(tr.WITHIN["story/completed"], frozenset({"ENDED_COMMIT"}))
        self.assertEqual(tr.WITHIN["failure/observed"], frozenset(tr.STORY_STATES) - {"ABSENT"})
        self.assertEqual(tr.WITHIN["provider/result"], frozenset(tr.STORY_STATES) - {"ABSENT"})

    def test_run_is_terminal_state_run_lifted_verbatim(self):
        expected = {}
        for (event_type, abandoned), value in TERMINAL_RUN.items():
            if abandoned is None:
                expected[event_type] = value
            else:
                expected["run/interrupted:abandoning" if abandoned else "run/interrupted:first"] = value
        self.assertEqual(dict(tr.RUN), expected)

    def test_table_digest_is_the_asserted_literal_and_deterministic(self):
        self.assertRegex(tr.TABLE_DIGEST, r"^[0-9a-f]{64}$")
        self.assertEqual(digest(tr._digest_form()), tr.TABLE_DIGEST,
                         "the table's values changed: TABLE_DIGEST is the consumers' pin (C-1 §3.1) — any edit "
                         "must be a visible, reviewed one-line diff of the literal")
        self.assertEqual(digest(tr._digest_form()), digest(tr._digest_form()))


class SymbolOf(unittest.TestCase):
    def test_payload_dependent_splits(self):
        self.assertEqual(tr.symbol_of("story/admitted", {"admitted": True}), "story/admitted:accepted")
        self.assertEqual(tr.symbol_of("story/admitted", {"admitted": False}), "story/admitted:refused")
        self.assertEqual(tr.symbol_of("run/interrupted", {"abandoned": False}), "run/interrupted:first")
        self.assertEqual(tr.symbol_of("run/interrupted", {"abandoned": True}), "run/interrupted:abandoning")

    def test_everything_else_maps_to_itself_and_nothing_raises(self):
        self.assertEqual(tr.symbol_of("story/begin", {"story_id": "S"}), "story/begin")
        self.assertEqual(tr.symbol_of("no/such-kind", None), "no/such-kind")
        self.assertEqual(tr.symbol_of("story/admitted", None), "story/admitted:refused")
        self.assertEqual(tr.symbol_of("run/interrupted", "junk"), "run/interrupted:first")


# --------------------------------------------------------------------------------------- T10 (cell half)

def v2_cur(state):
    """A StoryState-v2 per-story record in the given table state (the f3 two-state view adapter, C-1 §3.2.2)."""
    if state == "ABSENT":
        return None
    base = {"attempt": 1, "admitted": True, "outcome": None}
    if state == "BEGIN":
        return {**base, "state": "BEGIN", "admitted": None}
    if state == "BEGIN_REFUSED":
        return {**base, "state": "BEGIN", "admitted": False}
    if state == "ACTIVE":
        return {**base, "state": "ACTIVE"}
    phase, _, outcome = state.partition("_")
    v2_state = {"DECIDED": outcome, "DISPOSED": "DISPOSE", "ENDED": "ENDED"}[phase]
    return {**base, "state": v2_state, "outcome": outcome}


def table_state_of(cur):
    """The table state a StoryState-v2 record denotes."""
    if cur is None:
        return "ABSENT"
    state = cur["state"]
    if state == "BEGIN":
        return "BEGIN_REFUSED" if cur["admitted"] is False else "BEGIN"
    if state == "ACTIVE":
        return "ACTIVE"
    if state in ("COMMIT", "ROLLBACK", "RETRY"):
        return f"DECIDED_{state}"
    if state == "DISPOSE":
        return f"DISPOSED_{cur['outcome']}"
    return f"ENDED_{cur['outcome']}"


class CellOracle(unittest.TestCase):
    """T10's now-testable half: for every (state, 2.2.0 symbol) cell, the table's verdict AND successor equal
    StoryState VERSION 2's — the table is exactly the 2.2.0 semantics re-keyed, zero divergences."""

    def v2_step(self, state, symbol):
        kind, _, variant = symbol.partition(":")
        data = {"story_id": "S"}
        if variant:
            data["admitted"] = variant == "accepted"
        projection = StoryState()
        prior = {} if state == "ABSENT" else {"S": v2_cur(state)}
        try:
            after = projection.step(prior, SimpleNamespace(type=kind, data=data))
        except ProjectionError:
            return None
        return table_state_of(after.get("S"))

    def table_step(self, state, symbol):
        to = tr.STORY.get((state, symbol))
        if to is not None:
            return to
        allowed = tr.WITHIN.get(symbol)
        if allowed is not None and state in allowed:
            return state
        return None

    def test_every_cell_agrees_with_story_state_v2(self):
        self.assertEqual(StoryState.version, 2, "StoryState bumped: move this oracle to the J7 equality bound "
                                                "(v3 fold == v2 fold over every format <= 3 journal)")
        for state in tr.STORY_STATES:
            for symbol in SYMBOLS_220:
                with self.subTest(state=state, symbol=symbol):
                    self.assertEqual(self.table_step(state, symbol), self.v2_step(state, symbol))

    def test_the_only_new_cells_are_the_format_4_kinds(self):
        table_only = {sym for sym in tr.WITHIN if sym not in SYMBOLS_220}
        self.assertEqual(table_only, {"provider/result", "story/completed"},
                         "provider/result legality is new table surface (M7: closers land during unwinding); "
                         "story/completed is format 4's marker — everything else is 2.2.0 re-keyed")


# --------------------------------------------------------------------------------------- T1–T8b, two sites

class Lifecycle(unittest.TestCase):
    """Freeze package §4b: every row refused at the A site (JournalWriter4.append) and the R site
    (format4.reconstruct) with the shape rule+kind+seq+state. The F site (StoryState v3) is the measured batch's."""

    maxDiff = None

    def world(self):
        return World(self)

    def refused(self, w, kind, data, source_seqs=(), state=""):
        kind_str = kind.value if isinstance(kind, T) else kind
        seq = len(w.w.events)
        pattern = rf"transitions: {kind_str} at seq {seq} for \S+ in state {state}"
        with self.assertRaisesRegex(JournalError, pattern):
            w.append(kind, data, source_seqs=source_seqs)
        with self.assertRaisesRegex(JournalError, pattern):
            f4.reconstruct(w.plus(kind_str, carried(kind_str, data), source_seqs))

    def begun(self):
        """BEGIN: a story begun, not yet admitted."""
        w = self.world()
        w.begin()
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        return w

    def test_t1_proof_verified_in_begin_refused_at_both_sites(self):
        w = self.begun()
        record = sealed_record()
        a = w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": record})
        b = w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": record})
        self.refused(w, T.PROOF_VERIFIED, proof_payload(), source_seqs=(a.seq, b.seq), state="BEGIN")

    def test_t2_tests_adequacy_in_begin_refused(self):
        self.refused(self.begun(), T.TESTS_ADEQUACY, adequacy_payload(), state="BEGIN")

    def test_t3_provider_request_in_begin_refused(self):
        self.refused(self.begun(), T.PROVIDER_REQUEST, request_payload(), state="BEGIN")

    def test_t1_t2_t3_are_legal_in_active(self):
        w = self.world()
        w.active()
        w.proof()
        w.append(T.TESTS_ADEQUACY, adequacy_payload())
        w.append(T.PROVIDER_REQUEST, request_payload())

    def test_t4_second_admission_refused_one_admission_per_attempt(self):
        w = self.world()
        w.begin()
        w.story("S1", admitted=False)
        self.refused(w, T.STORY_ADMITTED, admission("S1"), state="BEGIN_REFUSED")
        w2 = self.world()
        w2.active()  # accepted admission
        self.refused(w2, T.STORY_ADMITTED, admission("S1"), state="ACTIVE")

    def test_t5_second_begin_of_an_open_attempt_refused(self):
        w = self.world()
        w.active()
        self.refused(w, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA}, state="ACTIVE")

    def test_t6_begin_after_ended_commit_refused_only_ended_retry_begins_again(self):
        w = self.world()
        w.active()
        w.commit_path()
        self.refused(w, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA}, state="ENDED_COMMIT")
        w2 = self.world()
        w2.active()
        w2.unwind_path(outcome=T.STORY_RETRY)
        w2.story("S1")  # ENDED_RETRY -> BEGIN -> ACTIVE: the legal re-begin

    def test_t7_end_before_dispose_refused(self):
        w = self.world()
        w.active()
        w.proof()
        w.append(T.STORY_COMMIT, {"story_id": "S1", "revision": SHA})
        self.refused(w, T.STORY_END, {"story_id": "S1"}, state="DECIDED_COMMIT")

    def test_t8_completed_marker_on_ended_rollback_refused(self):
        w = self.world()
        w.active()
        w.unwind_path()  # ENDED_ROLLBACK
        self.refused(w, f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA, "fingerprint": "cd" * 32},
                     state="ENDED_ROLLBACK")

    def test_within_positives_the_rows_that_do_not_move(self):
        w = self.world()
        w.begin()
        w.story("S1", admitted=False)  # BEGIN_REFUSED
        w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": sealed_record()})
        w.append(T.STORY_PLAN_DRIFT, {"story_id": "S1", "criterion_id": "C1", "spec_id": "SPEC-1",
                                      "attributed_to": "X", "candidates": ("X",)})
        failure = w.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "CONTRACT_UNSATISFIED", "detail": "x"})
        w.append(T.STORY_ROLLBACK, {"story_id": "S1"}, source_seqs=(failure.seq,))
        w.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "UNKNOWN", "detail": "late", "original": "Boom"})
        w.append(T.STORY_DISPOSE, {"story_id": "S1"})

    def test_plan_drift_in_unadmitted_begin_refused(self):
        self.refused(self.begun(), T.STORY_PLAN_DRIFT,
                     {"story_id": "S1", "criterion_id": "C1", "spec_id": "SPEC-1", "attributed_to": "X",
                      "candidates": ("X",)}, state="BEGIN")

    def test_provider_result_closer_during_unwinding_is_legal_m7(self):
        w = self.world()
        w.active()
        request = w.append(T.PROVIDER_REQUEST, request_payload())
        failure = w.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "PROVIDER_UNAVAILABLE", "detail": "x"})
        w.append(T.STORY_ROLLBACK, {"story_id": "S1"}, source_seqs=(failure.seq,))
        w.append(T.PROVIDER_RESULT,  # the closer lands in DECIDED_ROLLBACK: WITHIN every state but ABSENT
                 {"story_id": "S1", "outcome": "OUTCOME_UNKNOWN", "synthetic": True, "detail": "", "segment": None},
                 source_seqs=(request.seq,))
        w.append(T.STORY_DISPOSE, {"story_id": "S1"})
        w.append(T.STORY_END, {"story_id": "S1"})
        w.append(T.RUN_END, {})  # R-CLOSED satisfied: the request is accounted

    def test_lifecycle_of_a_never_begun_story_refused(self):
        w = self.world()
        w.begin()
        self.refused(w, T.FAILURE_OBSERVED, {"story_id": "S9", "code": "UNKNOWN", "detail": "", "original": "Boom"},
                     state="ABSENT")


if __name__ == "__main__":
    unittest.main()
