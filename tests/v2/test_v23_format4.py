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


# --------------------------------------------------------------------------------------- pending enum state

class PendingEnum(Base):
    """LOUD pending-state pin: the two EventType members land with the measured CORE-2 batch, never silently."""

    def test_the_two_members_are_not_yet_in_the_enum(self):
        values = {t.value for t in T}
        for kind in (f4.PROVIDER_ATTESTATION, f4.STORY_COMPLETED):
            self.assertNotIn(
                kind, values,
                f"{kind!r} is now an EventType member: the measured CORE-2 batch has landed the enums hunk. "
                "This state change must not pass silently — land V3_VOCABULARY in event.py and FORMAT_3_CODES in "
                "format3.py (C-1 §4.10) in the SAME batch, flip format-4 call sites to the typed members, and "
                "retire this test.")

    def test_vocabulary4_is_the_31_names_and_covers_the_enum(self):
        self.assertEqual(len(f4.VOCABULARY4), 31)
        self.assertEqual(f4.VOCABULARY4,
                         {t.value for t in T} | {f4.PROVIDER_ATTESTATION, f4.STORY_COMPLETED},
                         "VOCABULARY4 must be the 29 v2.2.0 names plus the two format-4 kinds (§4.10); once the "
                         "enum lands the two members, this same equality pins VOCABULARY4 == the live enum")
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
        w.begin()
        check = w.append(T.GATE_CHECK, {"gate": "G1", "check": "c1", "passed": passed_check, "detail": ""})
        return w, check

    def test_t9_passing_decision_over_a_failed_check_refused(self):
        w, check = self.gated(False)
        error = self.refused(w, T.GATE_DECISION, {"gate": "G1", "passed": True, "projections": ("story_state",)},
                             source_seqs=(check.seq,), pattern="R-GATE")
        self.assertIn("gate/decision", str(error))
        self.assertIn(f"[{check.seq}]", str(error))

    def test_failing_decision_over_a_failed_check_is_legal(self):
        w, check = self.gated(False)
        w.append(T.GATE_DECISION, {"gate": "G1", "passed": False, "projections": ("story_state",)},
                 source_seqs=(check.seq,))

    def test_passing_decision_over_passed_checks_is_legal(self):
        w, check = self.gated(True)
        w.append(T.GATE_DECISION, {"gate": "G1", "passed": True, "projections": ("story_state",)},
                 source_seqs=(check.seq,))


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
