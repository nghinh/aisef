"""C-1 (FORMAT-4 freeze, blob 41506829d2) — format 4 reader/writer/schemas: the freeze package §4 control tables.

Realized here (testable WITHOUT the deferred edits): the five named rules R-SEALED/R-GATE/R-COMMIT/R-SEGMENT/R-CLOSED
red cases with the refusal SHAPE (rule+kind+seq, never a silent skip); every §4 schema delta's negatives; the §4.10
vocabulary PIN (T15) and §4.9 code PIN; delegation T16 (= FMT4-3/CT-2); writer discipline. Lifecycle rows T1–T8b are
in tests/v2/test_v23_transitions.py (which imports this module's helpers).

DEFERRED to the measured CORE-2 batch (frozen obligations needing files this merge may not touch):
* the F site (fold) leg of every three-site refusal — StoryState v3 / TerminalState v2 (projections/ edits);
* T10's golden-corpus half (f3-with-table == f3-at-2.2.0) and T17's fold oracle — format3.py + projections edits;
* the §4.10 pins THEMSELVES (`V3_VOCABULARY` in event.py, `FORMAT_3_CODES` in format3.py) — this file plants the
  tripwires (test_t15_*, test_format_4_codes_*, PendingEnum) that go RED when the enum grows without them;
* f3 back-application of R-SEALED/R-GATE/R-COMMIT as CR-4 classified stricter findings (Q7) — the red-before
  pins here (`test_red_before_*`) document 2.2.0 behavior and FLIP when that lands, visibly.
"""

import itertools
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from aisef2.arch.enums import EventType as T
from aisef2.control.owner import FailureCode
from aisef2.journal import format2 as f2
from aisef2.journal import format3 as f3
from aisef2.journal import format4 as f4
from aisef2.journal.compat import UnknownRequiredEvent
from aisef2.journal import event as ev
from aisef2.journal.event import GENESIS, Event, JournalError, carried, encode, link
from aisef2.product.contract import digest

SHA = "ab" * 20
HEX = "cd" * 32
FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "journal"


# --------------------------------------------------------------------------------------- payload builders

def run_begin(**over):
    d = {"journal_format": 4, "run_id": "run-f4", "kernel_digest": "11" * 32, "signer": "22" * 32}
    d.update(over)
    return d


def admission(sid="S1", admitted=True):
    if admitted:
        return {"story_id": sid, "parent": SHA, "admitted": True, "developer_call_permitted": True,
                "dispositions": {"O1": "READY"}}
    return {"story_id": sid, "parent": SHA, "admitted": False, "developer_call_permitted": False,
            "dispositions": {"O1": "PRECONDITION_BROKEN"}}


def sealed_record(*, tamper=False, unsealed=False):
    r = {"spec_id": "SPEC-1", "revision": SHA, "result": {"behavior_verdict": "SATISFIED"},
         "probe_id": "P1", "probe_digest": HEX, "enforcement": "FULL", "semantic_hash": HEX}
    if not unsealed:
        r["record_digest"] = "0" * 64 if tamper else digest(r)
    return r


def proof_payload(sid="S1"):
    return {"story_id": sid, "criterion_id": "C1", "spec_id": "SPEC-1", "semantic_hash": HEX,
            "candidate": SHA, "agreement": True, "verdict": "SATISFIED"}


def request_payload(sid="S1", **over):
    d = {"story_id": sid, "criteria": ("CR-1",), "budget_owner": "DEVELOPER",
         "reservation": {"turns": 1, "max_usd": 2.5}}
    d.update(over)
    return d


def segment_payload(**over):
    d = {"session": "sessions/s1.jsonl", "sha256": HEX, "offset": 0, "bytes": 42}
    d.update(over)
    return d


def result_payload(sid="S1", outcome="COMPLETED", synthetic=False, segment="auto", detail=""):
    if segment == "auto":
        segment = segment_payload() if outcome == "COMPLETED" else None
    return {"story_id": sid, "outcome": outcome, "synthetic": synthetic, "detail": detail, "segment": segment}


def adequacy_payload(sid="S1", **over):
    executed = {"status": "EXECUTED", "outcome": "PASSED", "selection": "STORY_TESTS_RAN",
                "owner_on_failure": None, "reason": None}
    d = {"story_id": sid, "execution": executed, "vacuity": "NON_VACUOUS", "relevance": "RELEVANT",
         "regressions": dict(executed), "outcome": "ADEQUATE", "owner": None, "may_block": False,
         "developer_chargeable": False}
    d.update(over)
    return d


def audit_payload(**over):
    d = {"reason": "Assembly: measured", "vacuity": {"neutralised": False, "attributed": "dev", "reason": "r"},
         "relevance": {"intersections": 2, "unmeasured": ("pkg/mod.py",)}}
    d.update(over)
    return d


def attestation_payload(**over):
    d = {"session": "sessions/s1.jsonl", "expected": "model-x", "observed": "model-x", "passed": True, "detail": ""}
    d.update(over)
    return d


def gate_check(sid="S1", gate="story", check="admission", passed=True, detail="", **over):
    """A format-4 gate/check (A2′: story_id required; gate.py's one real gate id is the default)."""
    d = {"gate": gate, "check": f"{sid}:{check}", "passed": passed, "detail": detail, "story_id": sid}
    d.update(over)
    return d


def gate_decision(sid="S1", gate="story", passed=True, **over):
    d = {"gate": gate, "passed": passed, "projections": ("story_state",), "story_id": sid}
    d.update(over)
    return d


def lines(*events):
    """Hand-encoded journal text for `events` (payloads given final — `carried` is NOT applied)."""
    text, prev = "", GENESIS
    for e in events:
        prev = link(prev, e)
        text += encode(e, prev)
    return text


class World:
    """A format-4 journal under a temp dir, driven through JournalWriter4 — the A (append) site; `plus` hand-encodes
    one more line onto the same chain for the R (reconstruct) site. The F (fold) site is the measured batch's."""

    def __init__(self, tc):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-f4-")
        tc.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        self.path = self.dir / "j.jsonl"
        clock = itertools.count(1)
        self.w = f4.JournalWriter4(self.path, clock=lambda: float(next(clock)))
        tc.addCleanup(self.w.close)

    def append(self, kind, data, source_seqs=()):
        return self.w.append(kind, data, source_seqs=source_seqs)

    def begin(self):
        return self.append(T.RUN_BEGIN, run_begin())

    def story(self, sid="S1", admitted=True):
        self.append(T.STORY_BEGIN, {"story_id": sid, "parent": SHA})
        self.append(T.STORY_ADMITTED, admission(sid, admitted))

    def active(self, sid="S1"):
        self.begin()
        self.story(sid)

    def proof(self, sid="S1", record=None):
        r = record if record is not None else sealed_record()
        a = self.append(T.PROBE_EVALUATED, {"story_id": sid, "criterion_id": "C1", "record": r})
        b = self.append(T.PROBE_EVALUATED, {"story_id": sid, "criterion_id": "C1", "record": r})
        return self.append(T.PROOF_VERIFIED, proof_payload(sid), source_seqs=(a.seq, b.seq))

    def commit_path(self, sid="S1"):
        """ACTIVE -> ENDED_COMMIT, with the proof R-COMMIT requires; returns the story/commit event."""
        self.proof(sid)
        commit = self.append(T.STORY_COMMIT, {"story_id": sid, "revision": SHA})
        self.append(T.STORY_DISPOSE, {"story_id": sid})
        self.append(T.STORY_END, {"story_id": sid})
        return commit

    def unwind_path(self, sid="S1", outcome=T.STORY_ROLLBACK):
        """current state -> ENDED_ROLLBACK (or ENDED_RETRY): failure, rollback/retry citing it, dispose, end."""
        failure = self.append(T.FAILURE_OBSERVED, {"story_id": sid, "code": "CONTRACT_UNSATISFIED", "detail": "x"})
        self.append(outcome, {"story_id": sid}, source_seqs=(failure.seq,))
        self.append(T.STORY_DISPOSE, {"story_id": sid})
        self.append(T.STORY_END, {"story_id": sid})

    def text(self):
        return self.path.read_text(encoding="utf-8")

    def plus(self, kind, data, source_seqs=(), ignorable=False):
        """The journal's text plus one hand-encoded event the writer refused (payload given final)."""
        e = Event(len(self.w.events), kind, data, 10.0 ** 6, ignorable, source_seqs)
        return self.text() + encode(e, link(self.w.head, e))


class Base(unittest.TestCase):
    maxDiff = None

    def world(self):
        return World(self)

    def refused(self, w, kind, data, source_seqs=(), pattern=""):
        """A-site and R-site refusal with the same shape (never a silent skip); returns the A-site error."""
        kind_str = kind.value if isinstance(kind, T) else kind
        with self.assertRaisesRegex(JournalError, pattern) as ctx:
            w.append(kind, data, source_seqs=source_seqs)
        payload = carried(kind_str, data)
        with self.assertRaisesRegex(JournalError, pattern):
            f4.reconstruct(w.plus(kind_str, payload, source_seqs))
        return ctx.exception


# --------------------------------------------------------------------- CORE-2 landed enum + §4.10 pin state

class LandedEnum(Base):
    """The CORE-2 batch landed the enums hunk WITH the §4.10 pins (the PendingEnum tripwire's own instruction):
    the two members exist, V3_VOCABULARY stays the 29 v2.2.0 literals, FORMAT_3_CODES the 22 code literals."""

    def test_the_two_members_are_in_the_enum_and_the_constants_are_their_values(self):
        self.assertEqual(T.PROVIDER_ATTESTATION.value, f4.PROVIDER_ATTESTATION)
        self.assertEqual(T.STORY_COMPLETED.value, f4.STORY_COMPLETED)

    def test_v3_vocabulary_is_the_29_v220_literals_exactly(self):
        self.assertEqual(len(ev.V3_VOCABULARY), 29)
        self.assertIs(ev.VOCABULARY, ev.V3_VOCABULARY, "the format 1-3 readers read the pinned set (§4.10)")
        self.assertEqual({t.value for t in T} - {f4.PROVIDER_ATTESTATION, f4.STORY_COMPLETED}, ev.V3_VOCABULARY,
                         "V3_VOCABULARY is exactly the live enum minus the two format-4 kinds: a third member "
                         "landed without a vocabulary ruling, or a v2.2.0 name was dropped")
        for kind in (f4.PROVIDER_ATTESTATION, f4.STORY_COMPLETED):
            self.assertNotIn(kind, ev.V3_VOCABULARY,
                             "a format-4 kind leaked into the sealed readers' vocabulary (§4.10, M4 class)")

    def test_format_3_codes_are_the_22_v220_literals(self):
        self.assertEqual(len(f3.FORMAT_3_CODES), 22)
        self.assertEqual({c.value for c in FailureCode}, f3.FORMAT_3_CODES,
                         "FailureCode and FORMAT_3_CODES diverged: a 23rd code (V21-57 reversal) lands with an "
                         "owner decision and touches format 4 only — the format-3 pin never widens (§4.10)")
        self.assertEqual(f3.FORMAT_3_CODES, f4.FORMAT_4_CODES, "at V21-57 KEEP the two pins hold the same 22")

    def test_vocabulary4_is_the_31_names_and_covers_the_enum(self):
        self.assertEqual(len(f4.VOCABULARY4), 31)
        self.assertEqual(f4.VOCABULARY4,
                         {t.value for t in T} | {f4.PROVIDER_ATTESTATION, f4.STORY_COMPLETED},
                         "VOCABULARY4 must be the 29 v2.2.0 names plus the two format-4 kinds (§4.10); the enum "
                         "landed the two members, so this same equality pins VOCABULARY4 == the live enum")
        self.assertEqual(f4.VOCABULARY4, {t.value for t in T}, "the enum landed: VOCABULARY4 == the live enum")
        self.assertEqual(frozenset(f4.SCHEMAS), f4.VOCABULARY4, "every format-4 kind has a schema (FMT3-1 pattern)")
        self.assertEqual(f4.KNOWN_FORMATS, (1, 2, 3, 4))
        self.assertEqual(f4.FORMAT, 4)


# --------------------------------------------------------------------------------------- §4.9 / §4.10 pins

class CodeAndVocabularyPins(Base):
    def test_format_4_codes_are_the_22_v220_literals(self):
        self.assertEqual(len(f4.FORMAT_4_CODES), 22)
        self.assertEqual(
            {c.value for c in FailureCode}, f4.FORMAT_4_CODES,
            "FailureCode grew beyond the 22 v2.2.0 literals: V21-57 KEEP reversed or violated — the owner "
            "decision and the FORMAT_3_CODES pin (C-1 §4.9/§4.10) must land together with any 23rd code")

    def test_f4_failure_code_outside_the_22_is_refused(self):
        w = self.world()
        w.active()
        data = {"story_id": "S1", "code": "PROBE_LIMIT", "owner": "ENVIRONMENT", "retryable": False, "detail": ""}
        with self.assertRaisesRegex(JournalError, "code"):
            f4.reconstruct(w.plus(T.FAILURE_OBSERVED.value, data))

    def test_code_pin_f3_refuses_an_unknown_code_as_220_did(self):
        begin3 = Event(0, "run/begin", {"journal_format": 3, "run_id": "r3"}, 1.0)
        story3 = Event(1, "story/begin", {"story_id": "S1", "parent": SHA}, 2.0)
        bad = Event(2, "failure/observed", {"story_id": "S1", "code": "PROBE_LIMIT", "owner": "ENVIRONMENT",
                                            "retryable": False, "detail": ""}, 3.0)
        text = lines(begin3, story3, bad)
        for reader in (f3.reconstruct, f4.reconstruct):
            with self.assertRaisesRegex(JournalError, r"wrong kind or enum \['code'\]"):
                reader(text)

    def test_t15_vocabulary_pin_ignorable_new_kinds_in_f3_still_skipped(self):
        """§4.10 PIN: a format-3 journal carrying an IGNORABLE event named like the new kinds is SKIPPED exactly
        as 2.2.0 skipped it. This test goes RED the moment the enum grows without the V3_VOCABULARY pin in
        event.py — that is why it exists (red-before WITHOUT the pin)."""
        begin3 = Event(0, "run/begin", {"journal_format": 3, "run_id": "r3"}, 1.0)
        for kind in (f4.PROVIDER_ATTESTATION, f4.STORY_COMPLETED):
            with self.subTest(kind=kind):
                stray = Event(1, kind, {"anything": "at all"}, 2.0, True)
                text = lines(begin3, stray)
                for reader in (f3.reconstruct, f4.reconstruct):
                    journal = reader(text)
                    self.assertEqual(journal.skipped, (1,),
                                     "2.2.0 reader behavior must stay byte-stable against enum growth (§4.10): "
                                     "land V3_VOCABULARY in event.py with the enums hunk")
                    self.assertEqual(len(journal.events), 1)


# --------------------------------------------------------------------------------------- §4.1 run/begin

class RunBeginSchema(Base):
    def test_f4_run_begin_positive_with_and_without_bundle_digest(self):
        self.world().begin()
        w2 = self.world()
        w2.append(T.RUN_BEGIN, run_begin(bundle_digest="33" * 32))

    def test_missing_required_fields_refused(self):
        for missing in ("signer", "kernel_digest", "run_id"):
            with self.subTest(missing=missing):
                w = self.world()
                data = run_begin()
                del data[missing]
                self.refused(w, T.RUN_BEGIN, data, pattern=rf"missing \['{missing}'\]")

    def test_malformed_values_refused(self):
        for key, value in (("signer", "zz" * 32), ("signer", "22" * 31), ("kernel_digest", 7)):
            with self.subTest(key=key):
                self.refused(self.world(), T.RUN_BEGIN, run_begin(**{key: value}),
                             pattern="wrong kind or enum")

    def test_unknown_key_refused(self):
        self.refused(self.world(), T.RUN_BEGIN, run_begin(extra="x"), pattern=r"not in the schema \['extra'\]")

    def test_declared_4_but_another_format_number_in_payload_refused(self):
        w = self.world()
        with self.assertRaisesRegex(JournalError, "journal format 3 is not format 4"):
            w.append(T.RUN_BEGIN, run_begin(journal_format=3))
        # at the R site the declaration routes to the format-3 reader, which refuses the f4-only fields
        with self.assertRaisesRegex(JournalError, r"not in the schema"):
            f4.reconstruct(w.plus(T.RUN_BEGIN.value, run_begin(journal_format=3)))


# --------------------------------------------------------------------------------------- §4.2 reservation

class ReservationSchema(Base):
    def active(self):
        w = self.world()
        w.active()
        return w

    def test_positive_and_null_means_explicitly_unbounded(self):
        w = self.active()
        w.append(T.PROVIDER_REQUEST, request_payload())
        w.append(T.PROVIDER_REQUEST, request_payload(reservation={"turns": None, "max_usd": None}))

    def test_absent_reservation_refused_null_is_not_absent(self):
        data = request_payload()
        del data["reservation"]
        self.refused(self.active(), T.PROVIDER_REQUEST, data, pattern=r"missing \['reservation'\]")

    def test_malformed_reservations_refused(self):
        shapes = ({"turns": 1}, {"turns": 1, "max_usd": 1.0, "note": "x"}, {"turns": -1, "max_usd": 1.0},
                  {"turns": 1.5, "max_usd": 1.0}, {"turns": 1, "max_usd": -0.01}, {"turns": 1, "max_usd": "1"},
                  {"turns": True, "max_usd": 1.0}, ())
        for bad in shapes:
            with self.subTest(reservation=bad):
                self.refused(self.active(), T.PROVIDER_REQUEST, request_payload(reservation=bad),
                             pattern=r"wrong kind or enum \['reservation'\]")


# --------------------------------------------------------------------------------------- §4.3 segment, R-SEGMENT

class SegmentRule(Base):
    def requested(self):
        w = self.world()
        w.active()
        request = w.append(T.PROVIDER_REQUEST, request_payload())
        return w, request

    def test_positive_completed_seals_a_segment_and_closer_seals_none(self):
        w, request = self.requested()
        w.append(T.PROVIDER_RESULT, result_payload(), source_seqs=(request.seq,))
        second = w.append(T.PROVIDER_REQUEST, request_payload())
        w.append(T.PROVIDER_RESULT, result_payload(outcome="OUTCOME_UNKNOWN", synthetic=True),
                 source_seqs=(second.seq,))

    def test_t14_completed_with_null_segment_refused(self):
        w, request = self.requested()
        error = self.refused(w, T.PROVIDER_RESULT, result_payload(segment=None),
                             source_seqs=(request.seq,), pattern="R-SEGMENT.*COMPLETED")
        self.assertIn("provider/result", str(error))

    def test_t14_synthetic_closer_with_segment_refused(self):
        w, request = self.requested()
        self.refused(w, T.PROVIDER_RESULT,
                     result_payload(outcome="OUTCOME_UNKNOWN", synthetic=True, segment=segment_payload()),
                     source_seqs=(request.seq,), pattern="R-SEGMENT.*synthetic closer")

    def test_failed_carries_either_and_detail_says_which(self):
        w, request = self.requested()
        w.append(T.PROVIDER_RESULT, result_payload(outcome="FAILED", segment=None, detail="no stream"),
                 source_seqs=(request.seq,))
        second = w.append(T.PROVIDER_REQUEST, request_payload())
        w.append(T.PROVIDER_RESULT,
                 result_payload(outcome="FAILED", segment=segment_payload(), detail="stream sealed"),
                 source_seqs=(second.seq,))

    def test_malformed_segment_refused(self):
        for bad in (segment_payload(sha256="zz" * 32), segment_payload(offset=-1), segment_payload(session=""),
                    {"session": "s", "sha256": HEX, "offset": 0}, segment_payload(extra=1)):
            with self.subTest(segment=bad):
                w, request = self.requested()
                self.refused(w, T.PROVIDER_RESULT, result_payload(segment=bad), source_seqs=(request.seq,),
                             pattern=r"wrong kind or enum \['segment'\]")


# --------------------------------------------------------------------------------------- §4.4 provider/attestation

class AttestationEnvelope(Base):
    def test_positive_anywhere_between_begin_and_end_story_id_optional(self):
        w = self.world()
        w.begin()
        w.append(f4.PROVIDER_ATTESTATION, attestation_payload())
        w.append(f4.PROVIDER_ATTESTATION, attestation_payload(story_id="S1", passed=False, detail="drift"))

    def test_missing_or_empty_required_fields_refused(self):
        for data, pattern in ((attestation_payload(session=""), r"wrong kind or enum \['session'\]"),
                              (attestation_payload(expected=""), r"wrong kind or enum \['expected'\]"),
                              ({k: v for k, v in attestation_payload().items() if k != "expected"},
                               r"missing \['expected'\]"),
                              (attestation_payload(extra="x"), r"not in the schema \['extra'\]")):
            with self.subTest(pattern=pattern):
                w = self.world()
                w.begin()
                self.refused(w, f4.PROVIDER_ATTESTATION, data, pattern=pattern)

    def test_after_run_end_refused(self):
        w = self.world()
        w.begin()
        w.append(T.RUN_END, {})
        self.refused(w, f4.PROVIDER_ATTESTATION, attestation_payload(), pattern="before run/end")


# --------------------------------------------------------------------------------------- §4.5 story/completed

class StoryCompletedEnvelope(Base):
    def ended_commit(self):
        w = self.world()
        w.active()
        return w, w.commit_path()

    def test_positive_marker_cites_this_runs_commit(self):
        w, commit = self.ended_commit()
        w.append(f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA, "fingerprint": HEX},
                 source_seqs=(commit.seq,))

    def test_t8b_duplicate_marker_refused(self):
        w, commit = self.ended_commit()
        w.append(f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA, "fingerprint": HEX},
                 source_seqs=(commit.seq,))
        self.refused(w, f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA, "fingerprint": HEX},
                     source_seqs=(commit.seq,), pattern="at most once per story per run")

    def test_a1_marker_after_run_end_refused_at_all_three_sites(self):
        """C-1 amendment A1 (owner ruling 2026-11-26) — the adversarial finding C1's reproducer. Red-before: the
        pre-A1 code ACCEPTED this exact sequence at append and reconstruct (probe preserved in
        aisef-private-evidence/2026-11-26-advrev-f4/); green-after: refused at BOTH sites naming event, seq and
        rule — and the fold refuses the same forbidden sequence, so all three sites agree."""
        w, commit = self.ended_commit()
        w.append(T.RUN_END, {})
        data = {"story_id": "S1", "revision": SHA, "fingerprint": HEX}
        self.refused(w, f4.STORY_COMPLETED, data, source_seqs=(commit.seq,),
                     pattern=r"story/completed at seq \d+: .*before run/end.*C-1 amendment A1")
        from aisef2.journal.projections.terminal_state import TerminalState
        from aisef2.journal.projections import ProjectionError
        ts, state = TerminalState(), TerminalState().initial()
        for e in self.only_terminal_kinds(w.w.events):
            state = ts.step(state, e)
        forged = Event(len(w.w.events), f4.STORY_COMPLETED, carried(f4.STORY_COMPLETED, data), 10.0 ** 6,
                       False, (commit.seq,))
        with self.assertRaisesRegex(ProjectionError, "after the run is ENDED"):
            ts.step(state, forged)

    @staticmethod
    def only_terminal_kinds(events):
        """TerminalState folds whole journals in production; here the minimal stream that reaches ENDED."""
        return [e for e in events if e.type.startswith(("run/", "story/")) and e.type != "story/plan-drift"]

    def test_a1_marker_after_an_abandoning_interrupt_refused_too(self):
        """A1's second sentence ("never be appended after the run has closed") under the terminal-state reading:
        ABANDONED is a closed run (adversarial review F1, 2026-11-26) — the same forge aimed at an abandoned run
        is refused at both sites; a FIRST (non-abandoning) interrupt does NOT close the run and stays legal."""
        w, commit = self.ended_commit()
        w.append(T.RUN_INTERRUPTED, {"abandoned": False})
        data = {"story_id": "S1", "revision": SHA, "fingerprint": HEX}
        probe = Event(len(w.w.events), f4.STORY_COMPLETED, carried(f4.STORY_COMPLETED, data), 10.0 ** 6,
                      False, (commit.seq,))
        f4.reconstruct(w.plus(f4.STORY_COMPLETED, probe.data, (commit.seq,)))   # INTERRUPTED is not closed: legal
        w.append(T.RUN_INTERRUPTED, {"abandoned": True})
        self.refused(w, f4.STORY_COMPLETED, data, source_seqs=(commit.seq,),
                     pattern=r"story/completed at seq \d+: .*an abandoning interrupt closes the run")

    def test_missing_or_malformed_fields_refused(self):
        w, commit = self.ended_commit()
        self.refused(w, f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA},
                     source_seqs=(commit.seq,), pattern=r"missing \['fingerprint'\]")
        self.refused(w, f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA, "fingerprint": "zz" * 32},
                     source_seqs=(commit.seq,), pattern=r"wrong kind or enum \['fingerprint'\]")

    def test_citing_another_story_or_a_non_commit_refused(self):
        w = self.world()
        w.begin()
        w.story("S1")
        begin_s2 = w.append(T.STORY_BEGIN, {"story_id": "S2", "parent": SHA})
        w.append(T.STORY_ADMITTED, admission("S2"))
        commit1 = w.commit_path("S1")
        w.commit_path("S2")
        self.refused(w, f4.STORY_COMPLETED, {"story_id": "S2", "revision": SHA, "fingerprint": HEX},
                     source_seqs=(commit1.seq,), pattern="not a story/commit with the same story_id")
        self.refused(w, f4.STORY_COMPLETED, {"story_id": "S2", "revision": SHA, "fingerprint": HEX},
                     source_seqs=(begin_s2.seq,), pattern="not a story/commit with the same story_id")


# --------------------------------------------------------------------------------------- §4.6 base, R-CLOSED

class WorktreeBase(Base):
    def test_base_on_worktree_positive(self):
        w = self.world()
        w.active()
        w.append(T.STORY_RESOURCE_ACQUIRED, {"story_id": "S1", "resource": "wt-1", "kind": "WORKTREE", "base": SHA})

    def test_base_on_non_worktree_refused(self):
        w = self.world()
        w.active()
        self.refused(w, T.STORY_RESOURCE_ACQUIRED,
                     {"story_id": "S1", "resource": "sess-1", "kind": "SESSION", "base": SHA},
                     pattern="base is the revision a WORKTREE was created at")

    def test_non_sha_base_refused(self):
        w = self.world()
        w.active()
        self.refused(w, T.STORY_RESOURCE_ACQUIRED,
                     {"story_id": "S1", "resource": "wt-1", "kind": "WORKTREE", "base": "not-a-sha"},
                     pattern=r"wrong kind or enum \['base'\]")


class ClosedRule(Base):
    def test_t13_run_end_with_unanswered_request_refused(self):
        w = self.world()
        w.active()
        request = w.append(T.PROVIDER_REQUEST, request_payload())
        error = self.refused(w, T.RUN_END, {}, pattern="R-CLOSED")
        self.assertIn(f"seq {request.seq}", str(error))
        self.assertIn("run/end", str(error))

    def test_t13_companion_closers_first_still_ends_cleanly(self):
        """The E5 interrupt path's shape (M7): the synthetic closer answers the request before the run closes."""
        w = self.world()
        w.active()
        request = w.append(T.PROVIDER_REQUEST, request_payload())
        w.append(T.PROVIDER_RESULT, result_payload(outcome="OUTCOME_UNKNOWN", synthetic=True),
                 source_seqs=(request.seq,))
        w.unwind_path()
        w.append(T.RUN_END, {})

    def test_run_end_with_no_requests_is_legal(self):
        w = self.world()
        w.begin()
        w.append(T.RUN_END, {})


# --------------------------------------------------------------------------------------- §4.7 audit

class AdequacyAudit(Base):
    def active(self):
        w = self.world()
        w.active()
        return w

    def test_audit_optional_absence_stays_writable_presence_legal(self):
        w = self.active()
        w.append(T.TESTS_ADEQUACY, adequacy_payload())
        w.append(T.TESTS_ADEQUACY, adequacy_payload(audit=audit_payload()))
        w.append(T.TESTS_ADEQUACY, adequacy_payload(audit=audit_payload(vacuity=None, relevance=None)))

    def test_malformed_audit_refused(self):
        shapes = (audit_payload(vacuity={"neutralised": False}),
                  audit_payload(relevance={"intersections": 1, "unmeasured": ("x",), "extra": 1}),
                  audit_payload(vacuity={"neutralised": "no", "attributed": "", "reason": ""}),
                  {"reason": "r"}, audit_payload(reason=None))
        for bad in shapes:
            with self.subTest(audit=bad):
                self.refused(self.active(), T.TESTS_ADEQUACY, adequacy_payload(audit=bad),
                             pattern=r"wrong kind or enum \['audit'\]")


# --------------------------------------------------------------------------------------- §4.8 R-SEALED/R-GATE/R-COMMIT

class SealedRule(Base):
    def test_t11_tampered_record_digest_refused(self):
        w = self.world()
        w.active()
        record = sealed_record(tamper=True)
        a = w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": record})
        b = w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": record})
        error = self.refused(w, T.PROOF_VERIFIED, proof_payload(), source_seqs=(a.seq, b.seq),
                             pattern="R-SEALED.*does not re-derive")
        self.assertIn("proof/verified", str(error))
        self.assertIn(f"cites {a.seq}", str(error))

    def test_record_without_a_seal_refused_fail_closed(self):
        w = self.world()
        w.active()
        record = sealed_record(unsealed=True)
        a = w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": record})
        b = w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": record})
        self.refused(w, T.PROOF_VERIFIED, proof_payload(), source_seqs=(a.seq, b.seq),
                     pattern="not a sealed ProbeRecord")

    def test_red_before_f3_still_accepts_the_tampered_record(self):
        """2.2.0 behavior, documented (M9): format 3 checks key-presence only. FLIPS when the Q7-ratified
        back-application of R-SEALED to format-3 reads lands (measured batch) — update it then, visibly."""
        record = sealed_record(tamper=True)
        events = [Event(0, "run/begin", {"journal_format": 3, "run_id": "r3"}, 1.0),
                  Event(1, "story/begin", {"story_id": "S1", "parent": SHA}, 2.0),
                  Event(2, "story/admitted", admission(), 3.0),
                  Event(3, "probe/evaluated", {"story_id": "S1", "criterion_id": "C1", "record": record}, 4.0),
                  Event(4, "probe/evaluated", {"story_id": "S1", "criterion_id": "C1", "record": record}, 5.0),
                  Event(5, "proof/verified", proof_payload(), 6.0, False, (3, 4))]
        journal = f3.reconstruct(lines(*events))
        self.assertEqual(len(journal.events), 6)


class GateRule(Base):
    def gated(self, passed_check):
        w = self.world()
        w.active()
        check = w.append(T.GATE_CHECK, gate_check(passed=passed_check))
        return w, check

    def test_t9_passing_decision_over_a_failed_check_refused(self):
        w, check = self.gated(False)
        error = self.refused(w, T.GATE_DECISION, gate_decision(passed=True),
                             source_seqs=(check.seq,), pattern="R-GATE")
        self.assertIn("gate/decision", str(error))
        self.assertIn(f"[{check.seq}]", str(error))

    def test_failing_decision_over_a_failed_check_is_legal(self):
        w, check = self.gated(False)
        w.append(T.GATE_DECISION, gate_decision(passed=False), source_seqs=(check.seq,))

    def test_passing_decision_over_passed_checks_is_legal(self):
        w, check = self.gated(True)
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(check.seq,))


# --------------------------------------------------------------------- A2′ (C-1 amendment, owner ruling 2026-11-26 §1)

class A2GateSchema(Base):
    """A2′ (schema): f4 gate/check and gate/decision require non-empty story_id — at the f4 layer ONLY."""

    def test_gate_check_without_story_id_refused(self):
        """Red-before/green-after of the schema: the pre-A2′ format-4 validator ACCEPTED this exact payload (no
        story_id — the 2.2.0 gate/check schema, event.py:217). No production format-4 journal exists yet (the
        production writer flip is gated behind the owner ruling's install/signing gates), so no migration is owed:
        the intended break refuses only hand-built pre-A2′ journals."""
        w = self.world()
        w.active()
        self.refused(w, T.GATE_CHECK, {"gate": "story", "check": "S1:admission", "passed": True, "detail": ""},
                     pattern=r"missing \['story_id'\]")

    def test_gate_decision_without_story_id_refused(self):
        w = self.world()
        w.active()
        check = w.append(T.GATE_CHECK, gate_check())
        self.refused(w, T.GATE_DECISION, {"gate": "story", "passed": True, "projections": ("story_state",)},
                     source_seqs=(check.seq,), pattern=r"missing \['story_id'\]")

    def test_empty_story_id_refused_on_both_kinds(self):
        w = self.world()
        w.active()
        self.refused(w, T.GATE_CHECK, gate_check(story_id=""), pattern=r"wrong kind or enum \['story_id'\]")
        check = w.append(T.GATE_CHECK, gate_check())
        self.refused(w, T.GATE_DECISION, gate_decision(story_id=""), source_seqs=(check.seq,),
                     pattern=r"wrong kind or enum \['story_id'\]")

    def test_formats_1_to_3_are_untouched_historical_writers_emit_nothing_new(self):
        """CR-3 both ways on the SAME f3 gate stream: without story_id it reconstructs identically through f3 and
        f4 (delegation — byte and behavior compatible); with the f4-only field it is refused by BOTH readers."""
        begin3 = Event(0, "run/begin", {"journal_format": 3, "run_id": "r3"}, 1.0)
        check3 = Event(1, "gate/check", {"gate": "story", "check": "S1:admission", "passed": True, "detail": ""}, 2.0)
        decision3 = Event(2, "gate/decision", {"gate": "story", "passed": True, "projections": ["story_state"]},
                          3.0, False, (1,))
        text = lines(begin3, check3, decision3)
        self.assertEqual(f4.reconstruct(text), f3.reconstruct(text))
        self.assertEqual(len(f3.reconstruct(text).events), 3)
        leaked = Event(1, "gate/check", {**check3.data, "story_id": "S1"}, 2.0)
        for reader in (f3.reconstruct, f4.reconstruct):
            with self.assertRaisesRegex(JournalError, r"not in the schema \['story_id'\]"):
                reader(lines(begin3, leaked))


class A2GateBinding(Base):
    """A2′ (rule, part 1): a gate event binds to a story the table holds in an OPEN attempt (BEGIN, BEGIN_REFUSED
    or ACTIVE) at that point of the stream — an arbitrary story_id is refused, naming event, seq and rule."""

    def test_unknown_story_refused(self):
        w = self.world()
        w.active()
        self.refused(w, T.GATE_CHECK, gate_check(sid="GHOST"), pattern="R-GATE-BIND.*GHOST in state ABSENT")

    def test_story_of_a_closed_attempt_refused(self):
        w = self.world()
        w.active()
        w.commit_path()  # S1 -> ENDED_COMMIT
        self.refused(w, T.GATE_CHECK, gate_check(), pattern="R-GATE-BIND.*S1 in state ENDED_COMMIT")

    def test_decision_for_a_story_after_unwind_refused(self):
        w = self.world()
        w.active()
        check = w.append(T.GATE_CHECK, gate_check(passed=False))
        w.unwind_path()  # S1 -> ENDED_ROLLBACK
        self.refused(w, T.GATE_DECISION, gate_decision(passed=False), source_seqs=(check.seq,),
                     pattern="R-GATE-BIND.*S1 in state ENDED_ROLLBACK")

    def test_gate_events_legal_in_all_three_open_states(self):
        """The kernel's real emission surface (gate.py:10, story_runner.py:244/:263/:429-443/:449): the resources
        check lands in BEGIN, the admission check in ACTIVE or BEGIN_REFUSED, the decision in any of the three."""
        w = self.world()
        w.begin()
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})  # BEGIN
        begin_check = w.append(T.GATE_CHECK, gate_check(check="resources", passed=False))
        w.append(T.GATE_DECISION, gate_decision(passed=False), source_seqs=(begin_check.seq,))
        w.story("S2", admitted=False)  # BEGIN_REFUSED
        refused_check = w.append(T.GATE_CHECK, gate_check(sid="S2", passed=False))
        w.append(T.GATE_DECISION, gate_decision(sid="S2", passed=False), source_seqs=(refused_check.seq,))
        w.story("S3")  # ACTIVE
        active_check = w.append(T.GATE_CHECK, gate_check(sid="S3"))
        w.append(T.GATE_DECISION, gate_decision(sid="S3", passed=True), source_seqs=(active_check.seq,))
        f4.reconstruct(w.text())


class A2GateCompleteness(Base):
    """A2′ (rule, part 2) — R-GATE-COMPLETE and R-GATE-CITE: a passing decision cites every in-scope gate/check of
    its (gate, story_id); citations are distinct, own-story and in-scope; passed:false is exempt from completeness
    ONLY. Every red case asserts both sites through `refused` (A = append, R = reconstruct); the F site has no gate
    leg (see FoldHasNoGateLeg)."""

    def two_checks(self, w, sid="S1", first=True, second=True, gate="story"):
        a = w.append(T.GATE_CHECK, gate_check(sid=sid, gate=gate, check="admission", passed=first))
        b = w.append(T.GATE_CHECK, gate_check(sid=sid, gate=gate, check="developer", passed=second))
        return a, b

    def test_c3_attack_passing_decision_hiding_a_failed_check_refused(self):
        """The original C3 adversarial finding, exact probe shape (aisef-private-evidence/2026-11-26-advrev-f4/
        probe.py input C3): a passed:true decision citing only the passing check while a FAILED check of the same
        (gate, story_id) sits in scope. Red-before: the pre-A2′ R-GATE checked only CITED checks and ACCEPTED this.
        Green-after: refused naming the uncited seq."""
        w = self.world()
        w.active()
        passing, failing = self.two_checks(w, first=True, second=False)
        error = self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(passing.seq,),
                             pattern="R-GATE-COMPLETE")
        self.assertIn(f"[{failing.seq}]", str(error))
        self.assertIn("gate/decision", str(error))

    def test_omitted_passing_check_refused(self):
        w = self.world()
        w.active()
        cited, omitted = self.two_checks(w, first=True, second=True)
        error = self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(cited.seq,),
                             pattern="R-GATE-COMPLETE")
        self.assertIn(f"[{omitted.seq}]", str(error))

    def test_omitted_failed_check_refused_even_when_every_cited_check_passes(self):
        w = self.world()
        w.active()
        a, b = self.two_checks(w, first=True, second=True)
        failing = w.append(T.GATE_CHECK, gate_check(check="merge", passed=False))
        error = self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(a.seq, b.seq),
                             pattern="R-GATE-COMPLETE")
        self.assertIn(f"[{failing.seq}]", str(error))

    def test_duplicate_citation_refused_for_both_verdicts(self):
        """Duplicates are refused by the FROZEN Event invariant (event.py:78-80: source_seqs "each once, in order"),
        which fires at construction on both sites — structurally stronger than A2′ asks, so A2′ adds no second
        duplicate gate; this test pins the frozen rule as the matrix row's refusal, stated as-is."""
        for passed in (True, False):
            with self.subTest(passed=passed):
                w = self.world()
                w.active()
                check = w.append(T.GATE_CHECK, gate_check(passed=passed))
                self.refused(w, T.GATE_DECISION, gate_decision(passed=passed),
                             source_seqs=(check.seq, check.seq), pattern="each once, in order")

    def test_duplicate_citation_refused_at_reconstruct_on_raw_bytes(self):
        """F2 (adversarial review 2026-11-26): the PRODUCTION R-site leg — the `refused` helper cannot reach it for
        duplicates (Event construction raises inside the harness first), so the forged line goes in as raw JSON
        bytes with source_seqs duplicated after encoding; reconstruct must refuse it itself."""
        w = self.world()
        w.active()
        check = w.append(T.GATE_CHECK, gate_check())
        good = Event(len(w.w.events), T.GATE_DECISION.value,
                     carried(T.GATE_DECISION.value, gate_decision(passed=True)), 10.0 ** 6, False, (check.seq,))
        obj = json.loads(encode(good, link(w.w.head, good)))
        obj["event"]["source_seqs"] = [check.seq, check.seq]
        with self.assertRaisesRegex(JournalError, "each once, in order"):
            f4.reconstruct(w.text() + json.dumps(obj) + "\n")

    def test_vacuous_pass_citing_zero_checks_refused(self):
        """A passed:true decision over no evidence. The refusal is the FROZEN citation-count rule (event.py
        `_cites`: every gate/decision cites at least one gate/check — it refuses the vacuous FAIL too), which fires
        before the A2′ rules; A2′ adds no second vacuity gate because none is reachable past this one. The message
        names the kind; rule+seq shape is the frozen rule's, documented here as-is — no false claim."""
        w = self.world()
        w.active()
        w.append(T.GATE_CHECK, gate_check())
        self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(),
                     pattern="gate/decision cites at least one gate/check")

    def test_completeness_is_per_gate_a_second_gate_id_scopes_apart(self):
        """The rule is per (gate, story_id) even though the kernel has ONE gate id (gate.py:10 GATE = "story")."""
        w = self.world()
        w.active()
        own_a = w.append(T.GATE_CHECK, gate_check(check="admission"))
        other = w.append(T.GATE_CHECK, gate_check(gate="G2", check="x"))
        own_b = w.append(T.GATE_CHECK, gate_check(check="developer"))
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(own_a.seq, own_b.seq))  # G2 not owed
        w.append(T.GATE_DECISION, gate_decision(gate="G2", passed=True), source_seqs=(other.seq,))
        w2 = self.world()
        w2.active()
        a2, _ = self.two_checks(w2)
        w2.append(T.GATE_CHECK, gate_check(gate="G2", check="x"))
        error = self.refused(w2, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(a2.seq,),
                             pattern="R-GATE-COMPLETE")
        self.assertIn(f"[{a2.seq + 1}]", str(error))  # the omitted own-gate check, never the G2 one

    def test_c5_interleaved_stories_completeness_is_own_story_exactly(self):
        """C5-PARALLEL's shape (C-1 adversarial evidence 3): two stories' checks interleaved through one journal
        under the one gate id — each decision owes exactly its own-story in-scope set, never the other story's."""
        w = self.world()
        w.begin()
        w.story("A")
        w.story("B")
        a1 = w.append(T.GATE_CHECK, gate_check(sid="A", check="admission"))
        b1 = w.append(T.GATE_CHECK, gate_check(sid="B", check="admission"))
        a2 = w.append(T.GATE_CHECK, gate_check(sid="A", check="developer"))
        error = self.refused(w, T.GATE_DECISION, gate_decision(sid="A", passed=True), source_seqs=(a1.seq,),
                             pattern="R-GATE-COMPLETE")
        self.assertIn(f"gate/check [{a2.seq}] of", str(error))  # owes exactly its own second check, never B's
        self.refused(w, T.GATE_DECISION, gate_decision(sid="A", passed=True),
                     source_seqs=(a1.seq, b1.seq, a2.seq), pattern="R-GATE-CITE.*another story")
        w.append(T.GATE_DECISION, gate_decision(sid="A", passed=True), source_seqs=(a1.seq, a2.seq))
        w.append(T.GATE_DECISION, gate_decision(sid="B", passed=True), source_seqs=(b1.seq,))
        f4.reconstruct(w.text())

    def test_cross_story_citation_refused(self):
        w = self.world()
        w.begin()
        w.story("A")
        w.story("B")
        other = w.append(T.GATE_CHECK, gate_check(sid="B"))
        mine = w.append(T.GATE_CHECK, gate_check(sid="A"))
        error = self.refused(w, T.GATE_DECISION, gate_decision(sid="A", passed=True),
                             source_seqs=(other.seq, mine.seq), pattern="R-GATE-CITE.*another story")
        self.assertIn(f"[{other.seq}]", str(error))

    def test_retry_the_new_attempts_decision_scopes_from_the_previous_decision(self):
        """(e) retry/repeated decisions: a second decision citing only the new attempt's checks is ACCEPTED (its
        scope opens at the previous (gate, story_id) decision); reaching back across the boundary is refused STALE."""
        w = self.world()
        w.active()
        old = w.append(T.GATE_CHECK, gate_check(passed=False))
        w.append(T.GATE_DECISION, gate_decision(passed=False), source_seqs=(old.seq,))
        w.unwind_path(outcome=T.STORY_RETRY)  # -> ENDED_RETRY
        w.story()                             # the new attempt: BEGIN -> ACTIVE
        new = w.append(T.GATE_CHECK, gate_check())
        error = self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(old.seq, new.seq),
                             pattern="R-GATE-CITE.*stale")
        self.assertIn(f"[{old.seq}]", str(error))
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(new.seq,))  # ACCEPTED
        f4.reconstruct(w.text())

    def test_e5_fault_tail_false_decision_with_stranded_checks_is_accepted(self):
        """The NON-NEGOTIABLE kernel-reality control (C-1 adversarial evidence 2, M7): a helper may append
        gate/checks and then raise BEFORE the runner captures their seqs (merge.py:44-60 reprove, review.py:43-46,
        security.py:51-52); the E5 handler (story_runner.py:409-443) appends ONE more failed check and the decision
        (:449) cites only the captured list — passed:false, with in-scope same-(gate, story_id) checks UNCITED.
        A2′ accepts this at both sites: passed:false is exempt from completeness."""
        w = self.world()
        w.active()
        captured = w.append(T.GATE_CHECK, gate_check(check="admission", passed=True))
        w.append(T.GATE_CHECK, gate_check(check="proof:C1", passed=True))   # stranded by the raise
        w.append(T.GATE_CHECK, gate_check(check="proof:C2", passed=True))   # stranded by the raise
        handler = w.append(T.GATE_CHECK, gate_check(check="developer", passed=False))  # the E5 handler's one row
        w.append(T.GATE_DECISION, gate_decision(passed=False), source_seqs=(captured.seq, handler.seq))
        w.unwind_path()
        w.append(T.RUN_END, {})
        journal = f4.reconstruct(w.text())
        self.assertEqual(journal.events, w.w.events)

    def test_second_decision_of_the_same_attempt_scopes_from_the_first(self):
        """A decision does not move the table state: a later decision of the same (gate, story_id) owes only the
        checks appended after the previous one."""
        w = self.world()
        w.active()
        first = w.append(T.GATE_CHECK, gate_check(check="admission"))
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(first.seq,))
        second = w.append(T.GATE_CHECK, gate_check(check="developer"))
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(second.seq,))  # first no longer owed
        self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(first.seq,),
                     pattern="R-GATE-CITE.*stale")

    def test_failing_decision_still_subject_to_binding_and_citation_rules(self):
        """passed:false is exempt from COMPLETENESS only — schema, binding, R-GATE and the citation rules hold."""
        w = self.world()
        w.active()
        old = w.append(T.GATE_CHECK, gate_check(passed=False))
        w.append(T.GATE_DECISION, gate_decision(passed=False), source_seqs=(old.seq,))
        w.unwind_path(outcome=T.STORY_RETRY)
        w.story()
        self.refused(w, T.GATE_DECISION, gate_decision(passed=False), source_seqs=(old.seq,),
                     pattern="R-GATE-CITE.*stale")


class A2OrphanAttempt(Base):
    """Owner ruling 2026-11-26 (A2′ scope decision §1): a hand-built journal with an UNRESOLVED earlier attempt —
    demonstrate that orphaned checks can never be silently converted into a successful authoritative outcome.
    Four legs: there IS no silent path to a second attempt; the orphan is uncitable from the new attempt; the
    passing outcome rests only on the new attempt's complete evidence; and the orphan stays visible forever."""

    def orphaned(self):
        """Attempt 1 leaves a FAILED check cited by NO decision; the only legal road to attempt 2 is the journaled
        failure/observed + story/retry + dispose + end chain."""
        w = self.world()
        w.active()
        orphan = w.append(T.GATE_CHECK, gate_check(check="developer", passed=False))
        w.unwind_path(outcome=T.STORY_RETRY)
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        w.append(T.STORY_ADMITTED, admission("S1"))
        return w, orphan

    def test_leg1_no_silent_second_attempt_exists(self):
        """story/begin straight out of ACTIVE (skipping the journaled failure+retry) is refused by the frozen
        table at BOTH sites — an attempt cannot be abandoned invisibly, so every orphan sits behind an explicit
        failed-attempt record."""
        w = self.world()
        w.active()
        w.append(T.GATE_CHECK, gate_check(check="developer", passed=False))
        self.refused(w, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA}, pattern="story/begin")

    def test_leg2_the_orphan_is_uncitable_from_the_new_attempt(self):
        w, orphan = self.orphaned()
        fresh = w.append(T.GATE_CHECK, gate_check())
        self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(orphan.seq, fresh.seq),
                     pattern="R-GATE-CITE.*stale")

    def test_leg3_the_passing_outcome_rests_on_the_new_attempts_complete_evidence_only(self):
        """The approved latest-begin reading's acceptance, pinned WITH its guarantees: the new attempt's passing
        decision must cite the new attempt's whole in-scope set (completeness still fires inside the new scope),
        and the decision carries no orphan authority (leg 2 refused it)."""
        w, orphan = self.orphaned()
        fresh1 = w.append(T.GATE_CHECK, gate_check())
        fresh2 = w.append(T.GATE_CHECK, gate_check(check="developer", passed=True))
        self.refused(w, T.GATE_DECISION, gate_decision(passed=True), source_seqs=(fresh1.seq,),
                     pattern="R-GATE-COMPLETE")                     # even here, partial new-scope evidence refuses
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(fresh1.seq, fresh2.seq))

    def test_leg4_the_orphan_and_the_failed_attempt_stay_visible_forever(self):
        w, orphan = self.orphaned()
        fresh = w.append(T.GATE_CHECK, gate_check())
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(fresh.seq,))
        events = f4.reconstruct(w.text()).events
        kinds = [e.type for e in events]
        row = next(e for e in events if e.seq == orphan.seq)
        self.assertEqual((row.type, row.data["passed"]), (T.GATE_CHECK.value, False))   # the orphan, intact
        self.assertIn(T.FAILURE_OBSERVED.value, kinds)                                  # the failure, journaled
        self.assertIn(T.STORY_RETRY.value, kinds)                                       # the retry, journaled
        self.assertIn(encode_line_of(w, orphan.seq), w.text())                          # bytes still in the file


def encode_line_of(w, seq):
    """The journal's own stored line for seq — append-only means it is still there verbatim."""
    return w.text().splitlines()[seq]


class FoldHasNoGateLeg(Base):
    """(h) fold consistency, stated honestly: NO control projection folds gate kinds — gate/check and gate/decision
    pass through every one of the six unchanged, so the A/R verdicts in this file are the whole A2′ surface and
    there is no F-site leg to assert. This test pins that fact instead of claiming a fold refusal that nowhere
    exists; if a projection ever grows a gate leg, it goes red and the A2′ fold obligations must be rewritten."""

    def test_every_projection_ignores_gate_events(self):
        from aisef2.journal.fold import fold
        from aisef2.journal.projections.budgets import Budgets
        from aisef2.journal.projections.failure_owner import FailureOwner
        from aisef2.journal.projections.qualification_counters import QualificationCounters
        from aisef2.journal.projections.retry_target import RetryTarget
        from aisef2.journal.projections.story_state import StoryState
        from aisef2.journal.projections.terminal_state import TerminalState
        w = self.world()
        w.begin()
        w.append(T.PLAN_FROZEN, {"plan_id": "PLAN-1", "plan_hash": HEX, "roles": {"O1": "VERIFY"}})
        w.story()
        a0 = w.append(T.GATE_CHECK, gate_check(passed=True))
        w.append(T.GATE_DECISION, gate_decision(passed=True), source_seqs=(a0.seq,))   # F3: a PASSING decision too,
        a = w.append(T.GATE_CHECK, gate_check(passed=True))                            # so a future projection leg
        b = w.append(T.GATE_CHECK, gate_check(check="developer", passed=False))        # keyed on passed:true trips
        w.append(T.GATE_DECISION, gate_decision(passed=False), source_seqs=(a.seq, b.seq))
        w.unwind_path()
        w.append(T.RUN_END, {})
        events = f4.reconstruct(w.text()).events
        stripped = [e for e in events if e.type not in (T.GATE_CHECK.value, T.GATE_DECISION.value)]
        self.assertLess(len(stripped), len(events))
        for projection in (Budgets(), FailureOwner(), QualificationCounters(), RetryTarget(), StoryState(),
                           TerminalState()):
            with self.subTest(projection=projection.id):
                self.assertEqual(fold(projection, events), fold(projection, stripped))


class CommitRule(Base):
    def test_t12_commit_with_no_proof_in_the_attempt_refused(self):
        w = self.world()
        w.active()
        w.append(T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": sealed_record()})
        error = self.refused(w, T.STORY_COMMIT, {"story_id": "S1", "revision": SHA},
                             pattern="R-COMMIT.*no proof/verified")
        self.assertIn("story/commit", str(error))
        self.assertIn("seq", str(error))

    def test_proof_in_a_previous_attempt_does_not_count(self):
        w = self.world()
        w.active()
        w.proof()
        w.unwind_path(outcome=T.STORY_RETRY)
        w.story()  # ENDED_RETRY -> BEGIN -> ACTIVE again; the new attempt holds no proof
        self.refused(w, T.STORY_COMMIT, {"story_id": "S1", "revision": SHA}, pattern="R-COMMIT")


# --------------------------------------------------------------------------------------- §5 reader

class Reader(Base):
    def test_unknown_format_refused_by_number_never_guessed(self):
        text = lines(Event(0, "run/begin", run_begin(journal_format=7), 1.0))
        with self.assertRaisesRegex(JournalError, "journal format 7 is none of the formats this reader knows"):
            f4.reconstruct(text)
        with self.assertRaisesRegex(JournalError, "a journal is read as text"):
            f4.reconstruct(b"bytes")

    def test_torn_tail_reported_never_decoded(self):
        w = self.world()
        w.begin()
        journal = f4.reconstruct(w.text() + '{"chain": "torn')
        self.assertTrue(journal.torn_tail)
        self.assertEqual(len(journal.events), 1)

    def test_unknown_required_event_refuses_unknown_ignorable_skipped(self):
        w = self.world()
        w.begin()
        with self.assertRaises(UnknownRequiredEvent):
            f4.reconstruct(w.plus("story/checkpoint", {"x": 1}))
        journal = f4.reconstruct(w.plus("story/checkpoint", {"x": 1}, ignorable=True))
        self.assertEqual(journal.skipped, (1,))

    def test_known_f4_kind_marked_ignorable_refused(self):
        w = self.world()
        w.begin()
        with self.assertRaisesRegex(JournalError, "never ignorable"):
            f4.reconstruct(w.plus(f4.PROVIDER_ATTESTATION, attestation_payload(), ignorable=True))

    def test_round_trip_a_full_f4_journal(self):
        w = self.world()
        w.active()
        request = w.append(T.PROVIDER_REQUEST, request_payload())
        w.append(T.PROVIDER_RESULT, result_payload(), source_seqs=(request.seq,))
        commit = w.commit_path()
        w.append(f4.STORY_COMPLETED, {"story_id": "S1", "revision": SHA, "fingerprint": HEX},
                 source_seqs=(commit.seq,))
        w.append(f4.PROVIDER_ATTESTATION, attestation_payload())
        w.append(T.RUN_END, {})
        journal = f4.reconstruct(w.text())
        self.assertEqual(journal.events, w.w.events)
        self.assertEqual(journal.head(), w.w.head)
        self.assertEqual([e.seq for e in journal.events], list(range(len(journal.events))))

    def test_t16_fmt4_3_ct2_delegation_identical_on_every_committed_fixture(self):
        for path in sorted(FIXTURES.glob("*.jsonl")):
            with self.subTest(fixture=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(self.outcome(f3.reconstruct, text), self.outcome(f4.reconstruct, text))

    def outcome(self, reader, text):
        try:
            return reader(text)
        except JournalError as e:
            return (type(e), str(e))

    def test_t16_delegation_identical_on_generated_f2_and_f3_journals(self):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-f4-gen-")
        self.addCleanup(tmp.cleanup)
        p2 = pathlib.Path(tmp.name) / "f2.jsonl"
        w2 = f2.JournalWriter2(p2, clock=lambda: 1.0)
        self.addCleanup(w2.close)
        w2.append(T.RUN_BEGIN, {"journal_format": 2, "run_id": "r2"})
        w2.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        w2.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "sh"})
        p3 = pathlib.Path(tmp.name) / "f3.jsonl"
        w3 = f3.JournalWriter3(p3, clock=lambda: 1.0)
        self.addCleanup(w3.close)
        w3.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r3"})
        w3.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        w3.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "MERGE_CONFLICT", "detail": "x"})
        for path in (p2, p3):
            text = path.read_text(encoding="utf-8")
            self.assertEqual(f4.reconstruct(text), f3.reconstruct(text))

    def test_an_f4_journal_is_refused_loudly_by_the_220_readers(self):
        """CR-3 NEW-ONLY: a 2.2.0 reader refuses the WHOLE format-4 journal explicitly and never misreads it."""
        w = self.world()
        w.begin()
        for reader in (f2.reconstruct, f3.reconstruct):
            with self.assertRaisesRegex(JournalError, "journal format 4 is"):
                reader(w.text())


# --------------------------------------------------------------------------------------- §5 writer discipline

class WriterDiscipline(Base):
    def test_refusal_leaves_the_file_byte_identical_and_the_writer_alive(self):
        w = self.world()
        w.begin()
        before = w.path.read_bytes()
        with self.assertRaises(JournalError):
            w.append(T.STORY_ADMITTED, admission())  # no open attempt: the table refuses
        self.assertEqual(w.path.read_bytes(), before)
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})  # not poisoned by a validation refusal

    def test_never_extends_a_journal_of_another_format(self):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-f4-ext-")
        self.addCleanup(tmp.cleanup)
        path = pathlib.Path(tmp.name) / "f3.jsonl"
        w3 = f3.JournalWriter3(path, clock=lambda: 1.0)
        w3.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r3"})
        w3.close()
        with self.assertRaisesRegex(JournalError, "read, never extended under another format"):
            f4.JournalWriter4(path)

    def test_reopen_continues_the_same_chain(self):
        w = self.world()
        w.begin()
        head = w.w.head
        w.w.close()
        again = f4.JournalWriter4(w.path, clock=lambda: 9.0)
        self.addCleanup(again.close)
        self.assertEqual(again.head, head)
        again.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})

    def test_torn_journal_is_not_extended(self):
        w = self.world()
        w.begin()
        w.w.close()
        with open(w.path, "a", encoding="utf-8") as f:
            f.write('{"chain": "torn')
        with self.assertRaisesRegex(JournalError, "torn append"):
            f4.JournalWriter4(w.path)

    def test_failed_fsync_truncates_back_and_poisons_the_writer(self):
        w = self.world()
        w.begin()
        size = w.path.stat().st_size
        with mock.patch("aisef2.journal.format4.os.fsync", side_effect=OSError("injected: disk full")):
            with self.assertRaisesRegex(JournalError, "did not grow"):
                w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
        self.assertEqual(w.path.stat().st_size, size)
        with self.assertRaisesRegex(JournalError, "accepts nothing more"):
            w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})

    def test_kinds_are_typed_or_vocabulary4_literals_nothing_else(self):
        w = self.world()
        w.begin()
        with self.assertRaisesRegex(JournalError, "typed EventType"):
            w.append("story/checkpoint", {"x": 1})
        with self.assertRaisesRegex(JournalError, "typed EventType"):
            w.append(None, {})


if __name__ == "__main__":
    unittest.main()
