"""WP-3.1 — the event envelope and the append-only writer (RFC §20; F1).

Kill set for `event.py::validate` and `writer.py::append`. JOURNAL-1 (a seq gap is refused, never partially
authoritative) and JOURNAL-2 (a duplicate or conflicting event identity fails closed) are here.
"""

import dataclasses
import errno
import inspect
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import event as ev  # noqa: E402
from aisef2.journal import writer as wr  # noqa: E402
from aisef2.journal.compat import reconstruct  # noqa: E402
from aisef2.journal.event import Event, JournalError, validate  # noqa: E402
from tests.v2.p3.journal_world import BEGIN, SHA_A, Journals, admitted, failure, observed  # noqa: E402


def e(seq, type_, data, **kw):
    return Event(seq, type_.value if isinstance(type_, T) else type_, data, 0.0, **kw)


RUN = e(0, T.RUN_BEGIN, BEGIN)


class Envelope(unittest.TestCase):
    def test_the_fields_are_the_rfcs_in_order(self):
        self.assertEqual([(f.name, f.default) for f in dataclasses.fields(Event)],
                         [("seq", dataclasses.MISSING), ("type", dataclasses.MISSING), ("data", dataclasses.MISSING),
                          ("time", dataclasses.MISSING), ("ignorable", False), ("source_seqs", ())])

    def test_an_envelope_that_is_not_one_is_refused(self):
        seqs = "^run/begin: source_seqs cite earlier events, each once, in order$"
        lossless = "^run/begin: data is not JSON-lossless: "
        bad = [(dict(seq=-1), "^seq is a dense index, a non-negative int: -1$"), (dict(seq=True), "int: True$"),
               (dict(seq=1.0), "int: 1.0$"), (dict(type=""), "^an event has a non-empty type$"),
               (dict(type=3), "^an event has a non-empty type$"), (dict(data=[1]), "^run/begin: data is a mapping$"),
               (dict(data={"x": float("nan")}), lossless + "non-finite"), (dict(data={"x": {1, 2}}), lossless + "set"),
               (dict(data={1: "k"}), lossless + "mapping keys"), (dict(data={"x": b"b"}), lossless + "bytes"),
               (dict(data={"x": object()}), lossless + "object"), (dict(time=True), "^run/begin: time is a finite number$"),
               (dict(time=float("inf")), "time is a finite number$"), (dict(time="1"), "time is a finite number$"),
               (dict(ignorable=1), "^run/begin: ignorable is a bool$"), (dict(seq=3, source_seqs=(3,)), seqs),
               (dict(seq=3, source_seqs=(1, 1)), seqs), (dict(seq=3, source_seqs=(2, 1)), seqs),
               (dict(seq=3, source_seqs=(-1,)), seqs), (dict(seq=3, source_seqs=(True,)), seqs),
               (dict(seq=3, source_seqs="1"), seqs), (dict(seq=3, source_seqs={1}), seqs),
               (dict(seq=3, source_seqs=5), seqs)]
        for over, msg in bad:
            with self.subTest(**{k: repr(v) for k, v in over.items()}), self.assertRaisesRegex(JournalError, msg):
                Event(**{"seq": 0, "type": "run/begin", "data": {}, "time": 0.0, **over})

    def test_data_is_frozen_and_identity_is_content(self):
        a = e(1, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A})
        with self.assertRaises(TypeError):
            a.data["story_id"] = "S2"
        self.assertEqual(ev.event_id(a), ev.event_id(e(1, T.STORY_BEGIN, {"parent": SHA_A, "story_id": "S1"})))
        for other in (e(2, T.STORY_BEGIN, dict(a.data)), e(1, T.STORY_BEGIN, {**a.data, "story_id": "S2"}),
                      dataclasses.replace(a, time=1.0)):
            with self.subTest(other=other):
                self.assertNotEqual(ev.event_id(a), ev.event_id(other))
        self.assertIsInstance(e(0, T.RUN_BEGIN, BEGIN, source_seqs=[]).source_seqs, tuple)
        self.assertIsInstance(Event(0, "run/begin", BEGIN, 1).time, float)


class Decode(unittest.TestCase):
    def test_a_stored_line_that_is_not_one_is_refused(self):
        good = ev.encode(RUN, ev.link(ev.GENESIS, RUN)).rstrip("\n")
        shape = r"^line 0 is not a stored event \{chain, event: \['seq', 'type', 'data', 'time', 'ignorable', " \
                r"'source_seqs'\]\}$"
        obj = __import__("json").loads(good)
        cases = [("{", "^line 0 is not JSON$"), ("[1]", shape), ('{"chain": "x"}', shape),
                 (ev.canonical({**obj, "extra": 1}), shape), (ev.canonical({**obj, "event": 5}), shape),
                 (ev.canonical({**obj, "event": {k: v for k, v in obj["event"].items() if k != "time"}}), shape),
                 (ev.canonical({**obj, "event": {**obj["event"], "note": 1}}), shape),
                 (ev.canonical({**obj, "event": {**obj["event"], "source_seqs": 5}}),
                  "^run/begin: source_seqs cite earlier events, each once, in order$"),
                 (ev.canonical({**obj, "chain": "0" * 64}), "^line 0: the chain does not link — an earlier event was "
                                                           "edited or removed, or this one was$"),
                 (__import__("json").dumps(obj), "^line 0 is not the canonical encoding of its event$")]
        for line, msg in cases:
            with self.subTest(line=line[:40]), self.assertRaisesRegex(JournalError, msg):
                ev.decode(line, 0, ev.GENESIS)
        self.assertEqual(ev.decode(good, 0, ev.GENESIS), (RUN, ev.link(ev.GENESIS, RUN)))


class AppendSiteValidation(unittest.TestCase):
    def refused(self, event, prior=(RUN,), msg=""):
        with self.assertRaisesRegex(JournalError, msg):
            validate(event, list(prior))

    def test_position_type_and_ignorability(self):
        self.refused(e(2, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A}), msg="^story/begin at seq 2, but the "
                     "journal holds 1 events: seq == index$")
        self.refused(e(1, "story/bogus", {}), msg="^story/bogus is not in the event vocabulary$")
        self.refused(e(1, T.TOOL_INVOKED, {}), msg="^tool/invoked has no payload schema in journal format 1; writing "
                     r"it is a format version bump \(§35\)$")
        self.refused(e(1, T.RUN_END, {}, ignorable=True), msg="^run/end is a required event in format 1; it is never "
                     "ignorable$")
        self.refused(e(0, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A}), prior=(),
                     msg="a journal begins with run/begin, and only once$")
        self.refused(e(1, T.RUN_BEGIN, BEGIN), msg="^run/begin at seq 1: a journal begins with run/begin, and only once$")
        validate(RUN, [])
        validate(e(1, T.RUN_END, {}), [RUN])

    def test_fields_exactly_the_schemas(self):
        self.refused(e(1, T.STORY_BEGIN, {"story_id": "S1"}), msg=r"^story/begin: fields missing \['parent'\], not in "
                     r"the schema \[\]$")
        self.refused(e(1, T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A, "note": "x"}),
                     msg=r"^story/begin: fields missing \[\], not in the schema \['note'\]$")
        self.refused(e(1, T.STORY_BEGIN, {}), msg=r"^story/begin: fields missing \['story_id', 'parent'\], not in the "
                     r"schema \[\]$")
        self.refused(e(1, T.STORY_BEGIN, {"z": 1, "story_id": "S1", "parent": SHA_A, "a": 2}),
                     msg=r"not in the schema \['a', 'z'\]$")
        self.refused(e(1, T.STORY_BEGIN, {"story_id": "", "parent": "x"}),
                     msg=r"^story/begin: fields of the wrong kind or enum \['parent', 'story_id'\]$")
        kinds = [(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A[:12]}, "parent"),
                 (T.STORY_BEGIN, {"story_id": "", "parent": SHA_A}, "story_id"),
                 (T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A.upper()}, "parent"),
                 (T.RUN_INTERRUPTED, {"abandoned": 0}, "abandoned"),
                 (T.PLAN_FROZEN, {"plan_id": "P", "plan_hash": "f" * 63, "roles": {}}, "plan_hash"),
                 (T.PLAN_FROZEN, {"plan_id": "P", "plan_hash": "f" * 64, "roles": {"C1": "OWNS"}}, "roles"),
                 (T.PLAN_FROZEN, {"plan_id": "P", "plan_hash": "f" * 64, "roles": {"": "INTRODUCE"}}, "roles"),
                 (T.STORY_ADMITTED, {**admitted("S1", {"C1": "READY"}), "dispositions": {"C1": "MAYBE"}},
                  "dispositions"),
                 (T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": []}, "criteria"),
                 (T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1", ""]}, "criteria"),
                 (T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": "C1"}, "criteria"),
                 (T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1", "C1"]}, "criteria"),
                 (T.PROBE_EVALUATED, {"story_id": "S1", "criterion_id": "C1", "record": ["x"]}, "record"),
                 (T.FAILURE_OBSERVED, failure("S1", owner="NOBODY"), "owner"),
                 (T.FAILURE_OBSERVED, failure("S1", code="NOPE"), "code"),
                 (T.FAILURE_OBSERVED, failure("S1", detail=None), "detail"),
                 (T.STORY_PLAN_DRIFT, {"story_id": "S2", "criterion_id": "C", "spec_id": "P", "attributed_to": "S1",
                                       "candidates": [3]}, "candidates"),
                 (T.GATE_CHECK, {"gate": "g", "check": "c", "passed": "yes", "detail": ""}, "passed")]
        for type_, data, name in kinds:
            with self.subTest(type=type_.value, field=name):
                self.refused(e(1, type_, data), msg=rf"^{type_.value}: fields of the wrong kind or enum \['{name}'\]$")
        self.refused(e(0, T.RUN_BEGIN, {"journal_format": True, "run_id": "r"}), prior=(),
                     msg=r"^run/begin: fields of the wrong kind or enum \['journal_format'\]$")

    def test_rules_across_fields(self):
        self.refused(e(0, T.RUN_BEGIN, {"journal_format": 2, "run_id": "r"}), prior=(),
                     msg="journal format 2 is not format 1: refused, never read under another format$")
        self.refused(e(1, T.STORY_ADMITTED, {**admitted("S1", {"C1": "READY"}), "developer_call_permitted": False}),
                     msg=r"^story/admitted: admitted and developer_call_permitted are those the dispositions derive "
                         r"\(§13\)$")
        self.refused(e(1, T.STORY_ADMITTED, {**admitted("S1", {"C1": "PROBE_INVALID"}), "admitted": True}),
                     msg="derive")
        self.refused(e(1, T.STORY_ADMITTED, admitted("S1", {})), msg="at least one disposition$")
        for data in (admitted("S1", {"C1": "READY"}), admitted("S1", {"C1": "PRE_SATISFIED"}),
                     admitted("S1", {"C1": "READY", "C2": "PLAN_CONTRADICTION"})):
            with self.subTest(data=data["dispositions"]):
                validate(e(1, T.STORY_ADMITTED, data), [RUN])
        drift = {"story_id": "S3", "criterion_id": "C", "spec_id": "P"}
        self.refused(e(1, T.STORY_PLAN_DRIFT, {**drift, "attributed_to": "S1", "candidates": ["S1", "S2"]}),
                     msg=r"attributed_to 'S1': with candidates \['S1', 'S2'\] it is 'UNATTRIBUTED' \(§14\)$")
        self.refused(e(1, T.STORY_PLAN_DRIFT, {**drift, "attributed_to": "UNATTRIBUTED", "candidates": ["S1"]}),
                     msg="it is 'S1'")
        validate(e(1, T.STORY_PLAN_DRIFT, {**drift, "attributed_to": "UNATTRIBUTED", "candidates": []}), [RUN])
        self.refused(e(1, T.FAILURE_OBSERVED, failure("S1", owner="DEVELOPER")),
                     msg=r"PROBE_UNRUNNABLE carries owner DEVELOPER, retryable True; the taxonomy fixes ENVIRONMENT, "
                         r"True — a call site never decides them \(§22\)$")
        self.refused(e(1, T.FAILURE_OBSERVED, failure("S1", "PLAN_CONTRADICTION", "PLAN", True)), msg="fixes PLAN, False")
        self.refused(e(1, T.FAILURE_OBSERVED, failure("S1", "UNKNOWN", "INTEGRATION", False)),
                     msg=r"only UNKNOWN carries one \(§22\)$")
        self.refused(e(1, T.FAILURE_OBSERVED, failure("S1", original="E")), msg="only UNKNOWN carries one")
        validate(e(1, T.FAILURE_OBSERVED, failure("S1", "UNKNOWN", "INTEGRATION", False, original="OSError")), [RUN])
        validate(e(1, T.FAILURE_OBSERVED, failure("S1", "MISSING_CREDENTIAL", "ENVIRONMENT", True)), [RUN])

    def test_citations(self):
        f1, f2 = e(1, T.FAILURE_OBSERVED, failure("S1")), e(2, T.FAILURE_OBSERVED, failure("S2"))
        prior = [RUN, f1, f2]
        self.refused(e(3, T.STORY_ROLLBACK, {"story_id": "S1"}), prior, "^story/rollback cites exactly one "
                     "failure/observed$")
        self.refused(e(3, T.STORY_RETRY, {"story_id": "S1"}, source_seqs=(1, 2)), prior, "exactly one")
        self.refused(e(3, T.STORY_ROLLBACK, {"story_id": "S1"}, source_seqs=(2,)), prior,
                     r"^story/rollback cites \[2\]: not a failure/observed with the same story_id$")
        self.refused(e(3, T.STORY_RETRY, {"story_id": "S1"}, source_seqs=(0,)), prior, r"cites \[0\]")
        self.refused(e(3, T.STORY_END, {"story_id": "S1"}, source_seqs=(1,)), prior, "^story/end cites no event in "
                     "format 1$")
        validate(e(3, T.STORY_ROLLBACK, {"story_id": "S1"}, source_seqs=(1,)), prior)
        c1, c2 = (e(n, T.GATE_CHECK, {"gate": g, "check": "c", "passed": True, "detail": ""})
                  for n, g in ((1, "commit"), (2, "merge")))
        decision = {"gate": "commit", "passed": True, "projections": ["story_state", "budgets"]}
        self.refused(e(3, T.GATE_DECISION, decision), [RUN, c1, c2], "cites at least one gate/check$")
        self.refused(e(3, T.GATE_DECISION, decision, source_seqs=(1, 2)), [RUN, c1, c2], r"cites \[2\]")
        validate(e(3, T.GATE_DECISION, decision, source_seqs=(1,)), [RUN, c1, c2])

    def test_a_seventh_projection_cannot_be_cited_by_a_gate(self):
        c = e(1, T.GATE_CHECK, {"gate": "g", "check": "c", "passed": True, "detail": ""})
        for projections in (["story_state", "progress_report"], [], ["STORY_STATE"]):
            with self.subTest(projections=projections):
                self.refused(e(2, T.GATE_DECISION, {"gate": "g", "passed": True, "projections": projections},
                               source_seqs=(1,)), [RUN, c], r"fields of the wrong kind or enum \['projections'\]")


class PairSink:
    """P2's MemorySink shape over a journal: `emit` appends; `events` are (EventType, data) pairs."""

    def __init__(self, writer):
        self.writer = writer

    def emit(self, event_type, data):
        self.writer.emit(event_type, data)

    @property
    def events(self):
        return tuple((T(x.type), dict(x.data)) for x in self.writer.events)


class Writer(Journals, unittest.TestCase):
    def test_no_update_and_no_delete_verb(self):
        public = sorted(n for n in dir(wr.JournalWriter) if not n.startswith("_"))
        self.assertEqual(public, ["append", "close", "emit", "events", "head", "path"])
        module = sorted(n for n, v in vars(wr).items() if callable(v) and not n.startswith("_")
                        and getattr(v, "__module__", "") == wr.__name__)
        self.assertEqual(module, ["JournalWriter"])
        self.assertNotIn("seq", inspect.signature(wr.JournalWriter.append).parameters)  # layer 1: never supplied
        w = self.writer()
        with self.assertRaises(AttributeError):
            w.events.append("x")
        self.assertIsInstance(w.events, tuple)

    def test_seq_equals_index_over_a_long_sequence_and_the_file_reconstructs(self):
        w = self.writer()
        for n in range(1, 400):
            got = w.append(T.GATE_CHECK, {"gate": "g", "check": f"c{n}", "passed": n % 2 == 0, "detail": ""})
            self.assertEqual(got.seq, n)
        self.assertEqual([x.seq for x in w.events], list(range(400)))
        journal = reconstruct(self.text())
        self.assertEqual((journal.events, journal.head()), (w.events, w.head))
        self.assertEqual(self.writer().events, w.events)  # layer 2: seed admission of what it wrote

    def test_layer_3_append_rechecks_the_position(self):
        w = self.writer()
        size = self.size()
        with mock.patch.object(wr.JournalWriter, "_assign", lambda self: len(self._events) + 1), \
                self.assertRaisesRegex(JournalError, "seq == index$"):
            w.append(T.RUN_END, {})
        self.assertEqual((len(w.events), self.size()), (1, size))

    def test_JOURNAL_1_a_seq_gap_is_refused_at_seed_admission_and_decode(self):
        w = self.writer()
        for n in range(3):
            w.append(T.GATE_CHECK, {"gate": "g", "check": f"c{n}", "passed": True, "detail": ""})
        lines = self.text().splitlines(keepends=True)
        for name, edited in (("gap", lines[:2] + lines[3:]), ("reordered", [lines[0], lines[2], lines[1], lines[3]])):
            with self.subTest(case=name):
                self.rewrite(edited)
                with self.assertRaisesRegex(JournalError, "seq == index is broken"):
                    reconstruct(self.text())
                with self.assertRaisesRegex(JournalError, "seq == index is broken"):
                    wr.JournalWriter(self.path)
        with self.assertRaisesRegex(JournalError, r"^line 4 holds seq 3: seq == index is broken"):  # layer 4
            ev.decode(lines[3].rstrip("\n"), 4, "0" * 64)

    def test_JOURNAL_2_a_duplicate_or_conflicting_identity_fails_closed(self):
        w = self.writer()
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A})
        lines = self.text().splitlines(keepends=True)
        conflicting = lines[1].replace('"S1"', '"S9"')
        for name, edited, msg in (("duplicated line", lines + [lines[1]], "seq == index is broken"),
                                  ("same seq, other content", lines[:1] + [conflicting], "chain does not link"),
                                  ("same seq twice", lines + [conflicting], "seq == index is broken")):
            with self.subTest(case=name):
                self.rewrite(edited)
                with self.assertRaisesRegex(JournalError, msg):
                    reconstruct(self.text())

    def test_a_bad_event_fails_before_the_log_grows(self):
        w = self.writer()
        size, before = self.size(), w.events
        for bad in ((T.STORY_BEGIN, {"story_id": "S1", "parent": "abc"}), (T.RUN_BEGIN, BEGIN),
                    (T.TOOL_INVOKED, {}), ("story/begin", {"story_id": "S1", "parent": SHA_A}),
                    (T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A, "x": float("nan")})):
            with self.subTest(bad=bad[0]), self.assertRaises(JournalError):
                w.append(*bad)
        with self.assertRaisesRegex(JournalError, "typed EventType"):
            w.append("story/begin", {"story_id": "S1", "parent": SHA_A})
        check = mock.Mock(side_effect=JournalError("the projections refuse it"))
        with self.assertRaisesRegex(JournalError, "the projections refuse it"):
            w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A}, check=check)
        self.assertEqual(check.call_args.args[0].seq, 1)
        self.assertEqual((w.events, self.size()), (before, size))
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A}, check=lambda event: None)
        self.assertEqual(len(w.events), 2)

    def test_disk_full_and_fsync_failure_leave_the_log_unchanged_and_poison_the_writer(self):
        faults = {"disk full": ("write", OSError(errno.ENOSPC, "No space left on device")),
                  "fsync failure": ("fsync", OSError(errno.EIO, "Input/output error")),
                  "short write": ("write", None)}
        for name, (call, error) in faults.items():
            with self.subTest(fault=name):
                path = pathlib.Path(self._dir.name, f"{call}-{name}.jsonl")
                w = self.writer(path)
                size, before = self.size(path), w.events
                patch = mock.patch.object(wr.os, call, side_effect=error) if error else \
                    mock.patch.object(wr.os, "write", lambda fd, b, real=os.write: real(fd, b[:5]))
                detail = {"disk full": rf"OSError: \[Errno {errno.ENOSPC}\] No space left on device",
                          "fsync failure": rf"OSError: \[Errno {errno.EIO}\] Input/output error",
                          "short write": r"OSError: short write: 5 of \d+ bytes"}[name]
                with patch, self.assertRaisesRegex(JournalError, rf"^append of run/end at seq 1 failed \({detail}\); the "
                                                                 "journal did not grow$"):
                    w.append(T.RUN_END, {})
                self.assertEqual((w.events, self.size(path)), (before, size))
                with self.assertRaisesRegex(JournalError, "failed .* and accepts nothing more$"):
                    w.append(T.RUN_END, {})
                again = wr.JournalWriter(path)  # closed: Windows cannot remove a directory holding an open file
                self.addCleanup(again.close)
                self.assertEqual(again.events, before)

    def test_a_torn_tail_is_reported_and_never_extended(self):
        w = self.writer()
        w.append(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA_A})
        size = self.size()
        with mock.patch.object(wr.os, "fsync", side_effect=OSError(errno.EIO, "gone")), \
                mock.patch.object(wr.os, "ftruncate", side_effect=OSError(errno.EIO, "gone")), \
                self.assertRaises(JournalError):
            w.append(T.RUN_END, {})
        self.assertGreater(self.size(), size)  # the truncation failed: a partial line stays on disk
        whole = self.text()
        self.rewrite([whole[:size + 20]])
        journal = reconstruct(self.text())
        self.assertEqual((len(journal.events), journal.torn_tail), (2, True))
        with self.assertRaisesRegex(JournalError, r"ends in a torn append; repair it \(WP-4.6\) before extending it$"):
            wr.JournalWriter(self.path)

    def test_the_journal_is_opened_binary_where_the_platform_translates_newlines(self):
        # Windows' CRT opens low-level files in text mode and turns LF into CRLF unless O_BINARY is set
        opened = []
        real_open = os.open
        with mock.patch.object(wr.os, "O_BINARY", 0x8000, create=True), \
                mock.patch.object(wr.os, "open", lambda p, flags, mode=0o777: opened.append(flags) or
                                  real_open(p, flags & ~0x8000, mode)):
            self.writer()
        self.assertTrue(opened and opened[0] & 0x8000)
        self.assertTrue(opened[0] & os.O_APPEND)

    def test_a_closed_writer_accepts_nothing(self):
        w = self.writer()
        w.close()
        w.close()
        with self.assertRaisesRegex(JournalError, "^the writer is closed$"):
            w.append(T.RUN_END, {})

    def test_the_journal_is_the_StoryAdmission_sink_unchanged(self):
        from aisef2.plan import story_admission as sa
        from tests.v2.p2 import test_story_admission as p2
        w = self.writer()
        w.append(T.STORY_BEGIN, {"story_id": "S2", "parent": p2.PARENT.sha})
        a, b = p2.spec("a"), p2.spec("b")
        plan = p2.Plan.create(id="PLAN", baseline=p2.PARENT.sha, obligations=(
            p2.ob("C1", a, "S2", p2.Role.INTRODUCE), p2.ob("C2", b, "S2", p2.Role.INTRODUCE)),
            plan_quality_policy=p2.NOT_PREREGISTERED)
        seen = {a.id: p2.Observation(p2.K.OBSERVED, p2.S), b.id: p2.Observation(p2.K.OBSERVED, p2.R)}
        r = sa.admit_story(plan, "S2", p2.PARENT, specs={a.id: a, b.id: b}, probes={"probe.fake": p2.Fake(seen)},
                           env=p2.ENV, committed_stories=frozenset(), sink=w)
        sink = PairSink(w)  # P2's request_developer reads (EventType, data) pairs; the journal holds Events
        sa.request_developer(sink, "S2", {"criteria": ["C2"]})
        self.assertEqual([x.type for x in w.events], ["run/begin", "story/begin", "probe/evaluated", "probe/evaluated",
                                                      "story/admitted", "provider/request"])
        self.assertEqual(dict(w.events[4].data["dispositions"]), {"C1": "PRE_SATISFIED", "C2": "READY"})
        self.assertTrue(r.developer_call_permitted)
        self.assertEqual(reconstruct(self.text()).events, w.events)
        with self.assertRaisesRegex(JournalError, r"provider/request: fields missing \['criteria'\]"):
            sa.request_developer(sink, "S2", {"model": "m"})

    def test_failure_owner_and_retryable_are_carried_from_the_taxonomy(self):
        w = self.writer()
        for code, owner, retryable in (("PROBE_UNRUNNABLE", "ENVIRONMENT", True), ("PLAN_CONTRADICTION", "PLAN", False),
                                       ("MISSING_CREDENTIAL", "ENVIRONMENT", True),
                                       ("INVALID_CREDENTIAL", "ENVIRONMENT", False)):
            with self.subTest(code=code):
                got = w.append(T.FAILURE_OBSERVED, observed("S1", code))
                self.assertEqual((got.data["owner"], got.data["retryable"]), (owner, retryable))
        size = self.size()
        for supplied in ({"owner": "ENVIRONMENT"}, {"retryable": True}, {"owner": "DEVELOPER", "retryable": False}):
            with self.subTest(supplied=supplied), self.assertRaisesRegex(
                    JournalError, r"^failure/observed: owner and retryable come from the taxonomy, never from the call "
                                  r"site \(§22\)$"):
                w.append(T.FAILURE_OBSERVED, {**observed("S1"), **supplied})
        with self.assertRaisesRegex(JournalError, "code 'OSError' is not a taxonomy code; a foreign error flattens to "
                                                  "UNKNOWN"):
            w.append(T.FAILURE_OBSERVED, observed("S1", "OSError"))
        self.assertEqual(self.size(), size)
        got = w.append(T.FAILURE_OBSERVED, observed("S1", "UNKNOWN", original="OSError"))
        self.assertEqual((got.data["owner"], got.data["retryable"], got.data["original"]),
                         ("INTEGRATION", False, "OSError"))
        self.assertEqual(reconstruct(self.text()).events, w.events)

    def test_the_retry_rule_admits_one_carrier_and_only_its_key(self):
        import importlib.util
        s = importlib.util.spec_from_file_location("p3_ks", ROOT / "validation" / "v2" / "kernel_static_checks.py")
        ks = importlib.util.module_from_spec(s)
        s.loader.exec_module(ks)
        rule = ("RETRYABLE_ONLY_IN_TAXONOMY",)
        self.assertEqual(ks.violations("aisef2/journal/event.py", "x = {'retryable': True}\n", rule), [])
        for rel, src in (("aisef2/journal/event.py", "retryable = True\n"),
                         ("aisef2/journal/event.py", "f(retryable=True)\n"),
                         ("aisef2/journal/writer.py", "x = {'retryable': True}\n"),
                         ("aisef2/journal/projections/budgets.py", "x = {'retryability': 1}\n")):
            with self.subTest(rel=rel, src=src):
                self.assertEqual(len(ks.violations(rel, src, rule)), 1)

    def test_a_journal_with_an_event_type_it_does_not_know_is_not_extended(self):
        w = self.writer()
        w.close()
        stranger = Event(1, "report/progress", {"done": 1}, 0.0, ignorable=True)
        self.rewrite([self.text(), ev.encode(stranger, ev.link(w.head, stranger))])
        self.assertEqual(reconstruct(self.text()).skipped, (1,))
        with self.assertRaisesRegex(JournalError, r"holds event types this format-1 writer does not know \(seqs \[1\]\)"):
            wr.JournalWriter(self.path)


class WindowsTextMode(unittest.TestCase):
    def test_the_writer_evidence_holds_where_text_files_are_written_with_crlf(self):
        # Windows' text mode writes CRLF, so a journal the evidence writes as text is not canonical there and is refused
        # for that reason instead of the one the evidence names (CI run 35698648555). Journals are written as bytes.
        import importlib.util
        spec = importlib.util.spec_from_file_location("aisef_v2_p3_evidence_crlf", ROOT / "validation/v2/p3_evidence.py")
        evidence = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evidence)
        real = pathlib.Path.write_text

        def crlf(path, data, encoding=None, errors=None, newline=None):
            return real(path, data.replace("\n", "\r\n"), encoding=encoding, errors=errors, newline="")
        with mock.patch.object(pathlib.Path, "write_text", crlf):
            properties = evidence.journal_writer()["properties"]
        self.assertEqual([k for k, v in properties.items() if not v], [])


if __name__ == "__main__":
    unittest.main()
