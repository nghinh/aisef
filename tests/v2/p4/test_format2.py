"""WP-4.1 — journal format 2 (RFC §35; P4-LIFETIME-SEMANTICS.md §1). Kill set for `format2.py`.

Format 1 stays immutable: every format-1 journal reads the same through the format-2 reader, a format-1 event means
the same in a format-2 journal, and neither writer extends the other format's journal.
"""

import errno
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import compat, event as ev, format2 as f2  # noqa: E402
from aisef2.journal.event import Event, JournalError  # noqa: E402
from aisef2.journal.writer import JournalWriter  # noqa: E402
from tests.v2.p4.world import SHA, Journal2  # noqa: E402

FIXTURES = ROOT / "tests/v2/fixtures/journal"


def outcome(fn, text):
    try:
        j = fn(text)
        return ("OK", j.events, j.chain, j.skipped, j.torn_tail)
    except JournalError as e:
        return (type(e).__name__, str(e))


def cap(name, grade="VERIFIED", enforcement="FULL"):
    return {"name": name, "grade": grade, "enforcement": enforcement, "binding": {"digest": "d" * 64},
            "identity": "e" * 64}


def result(story, call, outcome="COMPLETED", signal=0, provenance="NONE", synthetic=False):
    return {"story_id": story, "call_id": call, "outcome": outcome, "signal": signal, "provenance": provenance,
            "synthetic": synthetic, "detail": ""}


class FormatOneIsUnchanged(unittest.TestCase):
    def test_every_p3_fixture_reads_the_same_through_the_format_2_reader_but_one_that_declares_format_2(self):
        declares_2 = []
        for path in sorted(FIXTURES.glob("*.jsonl")):
            text = path.read_bytes().decode("utf-8")
            with self.subTest(fixture=path.name):
                if f2.declared_format(text) == 2:
                    declares_2.append(path.name)
                    self.assertEqual(outcome(compat.reconstruct, text),
                                     ("JournalError", "run/begin: journal format 2 is not format 1: refused, never "
                                                      "read under another format"))
                    self.assertEqual(outcome(f2.reconstruct, text)[0], "OK")  # a valid format-2 journal
                else:
                    self.assertEqual(outcome(f2.reconstruct, text), outcome(compat.reconstruct, text))
        self.assertEqual(declares_2, ["version_mismatch.jsonl"])  # P3's "future format" fixture: format 1 refuses it

    def test_format_1_schemas_are_the_same_objects_and_only_three_types_are_re_declared(self):
        self.assertEqual(sorted(set(f2.SCHEMAS) & set(ev.SCHEMAS)),
                         sorted(t.value for t in (T.RUN_BEGIN, T.RUN_INTERRUPTED, T.RUN_END)))
        self.assertEqual(f2.WRITABLE, frozenset(ev.SCHEMAS) | frozenset(f2.SCHEMAS))
        self.assertEqual(ev.FORMAT, 1)
        new = sorted(set(f2.SCHEMAS) - set(ev.SCHEMAS))
        self.assertEqual(new, sorted(t.value for t in (
            T.STORY_RESOURCE_ACQUIRED, T.STORY_RESOURCE_RELEASED, T.CAPABILITY_RESOLVED, T.RUN_SPEC_RESOLVED,
            T.TOOL_INVOKED, T.TOOL_RESULT, T.PROVIDER_RESULT)))
        self.assertEqual(sorted(ev.VOCABULARY - f2.WRITABLE),
                         sorted(t.value for t in (T.PLAN_STATIC_ADMITTED, T.PROOF_VERIFIED, T.TESTS_ADEQUACY,
                                                  T.INVARIANT_VIOLATED)))

    def test_a_format_1_type_in_a_format_2_journal_is_judged_by_the_format_1_validator(self):
        bad = Event(1, T.STORY_ADMITTED.value, {"story_id": "S", "parent": SHA, "admitted": True,
                                                "developer_call_permitted": True, "dispositions": {"C": "MAYBE"}}, 0.0)
        begin2 = Event(0, T.RUN_BEGIN.value, {"journal_format": 2, "run_id": "r"}, 0.0)
        with mock.patch.object(ev, "validate", wraps=ev.validate) as spy:
            with self.assertRaises(JournalError) as two:
                f2.validate(bad, [begin2])
        spy.assert_called_once_with(bad, [begin2])
        begin1 = Event(0, T.RUN_BEGIN.value, {"journal_format": 1, "run_id": "r"}, 0.0)
        with self.assertRaises(JournalError) as one:
            ev.validate(bad, [begin1])
        self.assertEqual(str(two.exception), str(one.exception))

    def test_a_format_neither_1_nor_2_is_refused(self):
        e = Event(0, T.RUN_BEGIN.value, {"journal_format": 3, "run_id": "r"}, 0.0)
        text = ev.encode(e, ev.link(ev.GENESIS, e))
        with self.assertRaisesRegex(JournalError, r"^journal format 3 is neither format 1 nor format 2: refused$"):
            f2.reconstruct(text)
        self.assertEqual(f2.declared_format(text), 3)
        self.assertIsNone(f2.declared_format(text.rstrip("\n")))
        self.assertIsNone(f2.declared_format(""))
        other = Event(0, T.RUN_END.value, {}, 0.0)
        self.assertIsNone(f2.declared_format(ev.encode(other, ev.link(ev.GENESIS, other))))
        uncounted = Event(0, T.RUN_BEGIN.value, {"journal_format": "2", "run_id": "r"}, 0.0)
        self.assertIsNone(f2.declared_format(ev.encode(uncounted, ev.link(ev.GENESIS, uncounted))))
        with self.assertRaisesRegex(JournalError, "a journal is read as text"):
            f2.reconstruct(b"")


class FormatTwo(Journal2, unittest.TestCase):
    def test_a_format_2_journal_round_trips_and_keeps_the_format_1_reader_rules(self):
        w = self.writer()
        self.story(w)
        w.append(T.STORY_RESOURCE_ACQUIRED, {"story_id": "S1", "resource": "wt", "kind": "WORKTREE"})
        w.close()
        j = f2.reconstruct(self.text())
        self.assertEqual((j.events, j.chain, j.skipped, j.torn_tail), (w.events, tuple(w._chain), (), False))
        stranger = Event(3, "report/progress", {"n": 1}, 0.0, ignorable=True)
        text = self.text() + ev.encode(stranger, ev.link(j.head(), stranger))
        self.assertEqual(f2.reconstruct(text).skipped, (3,))
        required = Event(3, "story/checkpoint", {}, 0.0)
        with self.assertRaisesRegex(compat.UnknownRequiredEvent, r"^seq 3: unknown event type 'story/checkpoint' is "
                                                                 r"not marked ignorable"):
            f2.reconstruct(self.text() + ev.encode(required, ev.link(j.head(), required)))
        torn = f2.reconstruct(self.text() + '{"chain"')
        self.assertEqual((len(torn.events), torn.torn_tail), (3, True))
        with self.assertRaisesRegex(JournalError, r"line 2 holds seq 3"):
            lines = self.text().splitlines(keepends=True)
            f2.reconstruct("".join(lines[:2] + [lines[2].replace('"seq":2', '"seq":3')]))
        with self.assertRaisesRegex(JournalError, "run/begin at seq 1: a journal begins with run/begin, and only once"):
            f2.validate(Event(1, T.RUN_BEGIN.value, BEGIN_2, 0.0), list(j.events[:1]))

    def test_the_format_1_writer_does_not_extend_a_format_2_journal_nor_the_format_2_writer_a_format_1_one(self):
        two = self.writer()
        two.close()
        with self.assertRaisesRegex(JournalError, r"journal format 2 is not format 1: refused"):
            JournalWriter(self.path)
        one_path = self.dir / "one.jsonl"
        one = JournalWriter(one_path, clock=lambda: 0.0)
        one.append(T.RUN_BEGIN, {"journal_format": 1, "run_id": "r"})
        one.close()
        with self.assertRaisesRegex(JournalError, r"is a format-1 journal: it is read, never extended under another "
                                                  r"format$"):
            f2.JournalWriter2(one_path)
        self.assertEqual(outcome(f2.reconstruct, one_path.read_text(encoding="utf-8"))[0], "OK")

    def test_synthetic_is_written_only_as_true_and_only_in_format_2(self):
        w = self.writer()
        for data, ok in (({"abandoned": False, "synthetic": True}, True), ({"abandoned": False, "synthetic": False},
                                                                            False)):
            e = Event(1, T.RUN_INTERRUPTED.value, data, 0.0)
            with self.subTest(data=data):
                if ok:
                    f2.validate(e, list(w.events))
                else:
                    with self.assertRaisesRegex(JournalError, "synthetic is written only as true"):
                        f2.validate(e, list(w.events))
        with self.assertRaisesRegex(JournalError, r"not in the schema \['synthetic'\]"):
            ev.validate(Event(1, T.RUN_END.value, {"synthetic": True}, 0.0),
                        [Event(0, T.RUN_BEGIN.value, {"journal_format": 1, "run_id": "r"}, 0.0)])
        w.append(T.RUN_END, {"synthetic": True})

    def test_the_schema_checks_run_in_order_and_refuse(self):
        w = self.writer()
        cases = [
            (T.STORY_RESOURCE_ACQUIRED, {"story_id": "S1", "resource": "r"},
             r"^story/resource-acquired: fields missing \['kind'\], not in the schema \[\]$"),
            (T.STORY_RESOURCE_ACQUIRED, {"story_id": "S1", "resource": "r", "kind": "DISK"}, r"wrong kind or enum "
                                                                                             r"\['kind'\]"),
            (T.PLAN_STATIC_ADMITTED, {}, "has no payload schema in journal format 2; writing it is a format version "
                                         r"bump \(§35\)"),
            (T.RUN_BEGIN, {"journal_format": 1, "run_id": "r"}, "run/begin at seq 1"),
        ]
        for t, data, message in cases:
            with self.subTest(type=t.value, data=data), self.assertRaisesRegex(JournalError, message):
                w.append(t, data)
        with self.assertRaisesRegex(JournalError, "^story/bogus is not in the event vocabulary$"):
            f2.validate(Event(1, "story/bogus", {}, 0.0), list(w.events))
        with self.assertRaisesRegex(JournalError, "is a required event in format 2; it is never ignorable"):
            f2.validate(Event(1, T.TOOL_INVOKED.value, {"story_id": "S", "call_id": "c", "tool": "t"}, 0.0,
                              ignorable=True), list(w.events))
        with self.assertRaisesRegex(JournalError, r"at seq 5, but the journal holds 1 events: seq == index"):
            f2.validate(Event(5, T.TOOL_INVOKED.value, {"story_id": "S", "call_id": "c", "tool": "t"}, 0.0),
                        list(w.events))
        with self.assertRaisesRegex(JournalError, "^run/begin: journal format 1 is not format 2: refused, never read "
                                                  "under another format$"):
            f2.validate(Event(0, T.RUN_BEGIN.value, {"journal_format": 1, "run_id": "r"}, 0.0), [])
        with self.assertRaisesRegex(JournalError, "^tool/invoked cites no event in format 2$"):
            w.append(T.TOOL_INVOKED, {"story_id": "S", "call_id": "c", "tool": "t"}, source_seqs=(0,))
        self.assertEqual(len(w.events), 1)


class Resources(Journal2, unittest.TestCase):
    def acquire(self, w, resource, kind, story="S1"):
        return w.append(T.STORY_RESOURCE_ACQUIRED, {"story_id": story, "resource": resource, "kind": kind})

    def release(self, w, acquired, status="RELEASED", resource=None, kind=None, story="S1"):
        return w.append(T.STORY_RESOURCE_RELEASED, {
            "story_id": story, "resource": resource or acquired.data["resource"], "kind": kind or acquired.data["kind"],
            "status": status, "detail": "", "synthetic": False}, source_seqs=(acquired.seq,))

    def test_acquisition_needs_a_begun_attempt_is_once_per_resource_and_is_in_non_increasing_rank(self):
        w = self.writer()
        with self.assertRaisesRegex(JournalError, "S1 has not begun"):
            self.acquire(w, "wt", "WORKTREE")
        self.story(w)
        self.acquire(w, "scratch", "SCRATCH")
        self.acquire(w, "wt", "WORKTREE")
        with self.assertRaisesRegex(JournalError, r"resource 'wt' is already acquired in this attempt of S1"):
            self.acquire(w, "wt", "SANDBOX")
        with self.assertRaisesRegex(JournalError, r"SCRATCH after WORKTREE: reverse disposal would release it later"):
            self.acquire(w, "scratch-2", "SCRATCH")
        self.acquire(w, "wt-2", "WORKTREE")  # equal rank
        self.acquire(w, "range", "PROCESS_RANGE")
        self.acquire(w, "session", "SESSION")
        self.assertEqual([e.data["resource"] for e in w.events if e.type == T.STORY_RESOURCE_ACQUIRED.value],
                         ["scratch", "wt", "wt-2", "range", "session"])

    def test_every_kind_has_its_disposal_rank(self):
        """§17.1: sessions and grants first, then the process range, the sandbox, the worktree, scratch last."""
        K = f2.ResourceKind
        self.assertEqual(dict(f2.DISPOSAL_RANK), {K.SESSION: 0, K.TOOL_GRANT: 0, K.REVIEW_SCOPE: 0,
                                                  K.PROCESS_RANGE: 1, K.SANDBOX: 2, K.WORKTREE: 3, K.SCRATCH: 4})

    def test_an_ended_attempt_takes_no_acquisition(self):
        w = self.writer()
        self.story(w)
        w.append(T.STORY_END, {"story_id": "S1"})
        with self.assertRaisesRegex(JournalError, r"^story/resource-acquired: S1 is disposing: an acquisition is "
                                                  r"refused \(INACTIVE_ACQUIRE, §17.1\)$"):
            self.acquire(w, "late", "SESSION")

    def test_release_is_in_reverse_order_of_the_right_resource_once(self):
        w = self.writer()
        self.story(w)
        a, b = self.acquire(w, "wt", "WORKTREE"), self.acquire(w, "range", "PROCESS_RANGE")
        with self.assertRaisesRegex(JournalError, r"'wt' released before 'range', acquired after it: disposal is in "
                                                  r"reverse acquisition order"):
            self.release(w, a)
        with self.assertRaisesRegex(JournalError, r"cites the acquisition of 'range' \(PROCESS_RANGE\), not this "
                                                  r"resource"):
            self.release(w, b, resource="wt", kind="WORKTREE")
        with self.assertRaisesRegex(JournalError, r"cites exactly one story/resource-acquired"):
            w.append(T.STORY_RESOURCE_RELEASED, {"story_id": "S1", "resource": "range", "kind": "PROCESS_RANGE",
                                                 "status": "RELEASED", "detail": "", "synthetic": False},
                     source_seqs=(a.seq, b.seq))
        with self.assertRaisesRegex(JournalError, r"cites 1: not a story/resource-acquired with the same story_id"):
            w.append(T.STORY_RESOURCE_RELEASED, {"story_id": "S1", "resource": "range", "kind": "PROCESS_RANGE",
                                                 "status": "RELEASED", "detail": "", "synthetic": False},
                     source_seqs=(1,))
        self.release(w, b, status="RESIDUAL")
        with self.assertRaisesRegex(JournalError, r"'range' is not an unreleased acquisition of the current attempt"):
            self.release(w, b)
        self.release(w, a)
        self.assertEqual([(e.data["resource"], e.data["status"]) for e in w.events[-2:]],
                         [("range", "RESIDUAL"), ("wt", "RELEASED")])

    def test_an_acquisition_while_the_story_disposes_is_refused_and_a_new_attempt_starts_fresh(self):
        w = self.writer()
        self.story(w)
        a = self.acquire(w, "wt", "WORKTREE")
        w.append(T.FAILURE_OBSERVED, {"story_id": "S1", "code": "PROVIDER_UNAVAILABLE", "detail": ""})
        w.append(T.STORY_RETRY, {"story_id": "S1"}, source_seqs=(w.events[-1].seq,))
        w.append(T.STORY_DISPOSE, {"story_id": "S1"})
        with self.assertRaisesRegex(JournalError, r"S1 is disposing: an acquisition is refused \(INACTIVE_ACQUIRE"):
            self.acquire(w, "late", "SESSION")
        self.release(w, a)
        w.append(T.STORY_END, {"story_id": "S1"})
        self.story(w)
        self.acquire(w, "wt", "WORKTREE")  # the same id in the next attempt
        with self.assertRaisesRegex(JournalError, "'wt' is not an unreleased acquisition of the current attempt"):
            self.release(w, a)


class Identity(Journal2, unittest.TestCase):
    def spec(self, w, names, aggregate):
        return w.append(T.RUN_SPEC_RESOLVED, {"runspec_hash": "f" * 64, "aggregate_min_grade": aggregate,
                                              "capabilities": names, "revision": SHA})

    def test_capabilities_resolve_once_and_the_spec_names_them_with_their_minimum_grade(self):
        w = self.writer()
        w.append(T.CAPABILITY_RESOLVED, cap("kernel"))
        with self.assertRaisesRegex(JournalError, r"capability 'kernel' is resolved once per run"):
            w.append(T.CAPABILITY_RESOLVED, cap("kernel", grade="OPAQUE"))
        w.append(T.CAPABILITY_RESOLVED, cap("model", grade="ATTESTED", enforcement="PARTIAL"))
        with self.assertRaisesRegex(JournalError, r"capabilities \['tool'\] were not resolved before the RunSpec"):
            self.spec(w, ["kernel", "tool"], "VERIFIED")
        with self.assertRaisesRegex(JournalError, r"^run/spec-resolved: aggregate_min_grade VERIFIED is not the "
                                                  r"weakest grade, ATTESTED \(§23\)$"):
            self.spec(w, ["kernel", "model"], "VERIFIED")
        with self.assertRaisesRegex(JournalError, r"wrong kind or enum \['capabilities'\]"):
            self.spec(w, [], "VERIFIED")
        self.spec(w, ["kernel", "model"], "ATTESTED")
        with self.assertRaisesRegex(JournalError, "the RunSpec is resolved once per run"):
            self.spec(w, ["kernel"], "VERIFIED")
        w.append(T.CAPABILITY_RESOLVED, cap("late", grade="OPAQUE"))
        with self.assertRaisesRegex(JournalError, r"wrong kind or enum \['binding'\]"):
            w.append(T.CAPABILITY_RESOLVED, {**cap("x"), "binding": {"digest": 1}})

    def test_the_minimum_grade_orders_opaque_below_attested_below_verified(self):
        for grades, weakest in ((["VERIFIED", "OPAQUE"], "OPAQUE"), (["ATTESTED", "VERIFIED"], "ATTESTED"),
                                (["VERIFIED"], "VERIFIED"), (["OPAQUE", "ATTESTED"], "OPAQUE")):
            with self.subTest(grades=grades):
                w = self.writer(self.dir / f"{'-'.join(grades)}.jsonl")
                for n, g in enumerate(grades):
                    w.append(T.CAPABILITY_RESOLVED, cap(f"c{n}", grade=g))
                names = [f"c{n}" for n in range(len(grades))]
                for other in {"VERIFIED", "ATTESTED", "OPAQUE"} - {weakest}:
                    with self.assertRaises(JournalError):
                        self.spec(w, names, other)
                self.spec(w, names, weakest)


class Operations(Journal2, unittest.TestCase):
    def test_a_tool_is_invoked_once_in_an_open_attempt_and_has_one_result_that_cites_it(self):
        w = self.writer()
        with self.assertRaisesRegex(JournalError, "S1 has no open attempt to invoke a tool in"):
            w.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "pytest"})
        self.story(w)
        inv = w.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "pytest"})
        with self.assertRaisesRegex(JournalError, r"call 'c1' was already invoked"):
            w.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "pytest"})
        with self.assertRaisesRegex(JournalError, r"a result cites the tool/invoked of call 'c1', and only it"):
            w.append(T.TOOL_RESULT, result("S1", "c1"))
        with self.assertRaisesRegex(JournalError, r"a result cites the tool/invoked of call 'c9', and only it"):
            w.append(T.TOOL_RESULT, result("S1", "c9"), source_seqs=(inv.seq,))
        w.append(T.STORY_BEGIN, {"story_id": "S2", "parent": SHA})
        with self.assertRaisesRegex(JournalError, r"call 'c1' was invoked for S1, not S2"):
            w.append(T.TOOL_RESULT, result("S2", "c1"), source_seqs=(inv.seq,))
        w.append(T.TOOL_RESULT, result("S1", "c1", "SIGNALLED", 9, "UNKNOWN"), source_seqs=(inv.seq,))
        with self.assertRaisesRegex(JournalError, r"call 'c1' already has its result"):
            w.append(T.TOOL_RESULT, result("S1", "c1"), source_seqs=(inv.seq,))

    def test_closers_are_synthetic_signals_come_with_provenance_and_not_started_cites_nothing(self):
        w = self.writer()
        self.story(w)
        inv = w.append(T.TOOL_INVOKED, {"story_id": "S1", "call_id": "c1", "tool": "t"})
        bad = [
            (result("S1", "c1", "OUTCOME_UNKNOWN"), "OUTCOME_UNKNOWN and NOT_STARTED are closers, always synthetic"),
            (result("S1", "c1", synthetic=True), "OUTCOME_UNKNOWN and NOT_STARTED are closers, always synthetic"),
            (result("S1", "c1", "SIGNALLED", 0, "UNKNOWN"), "a signal number is recorded exactly when"),
            (result("S1", "c1", "FAILED", 15, "NONE"), "a signal number is recorded exactly when"),
            (result("S1", "c1", "SIGNALLED", 15, "NONE"), "a SIGNALLED outcome names its provenance"),
            (result("S1", "c1", "COMPLETED", 0, "CONTROLLER"), "a SIGNALLED outcome names its provenance"),
        ]
        for data, message in bad:
            with self.subTest(data=data), self.assertRaisesRegex(JournalError, message):
                w.append(T.TOOL_RESULT, data, source_seqs=(inv.seq,))
        with self.assertRaisesRegex(JournalError, "NOT_STARTED closes a call that was never dispatched"):
            w.append(T.TOOL_RESULT, result("S1", "c1", "NOT_STARTED", synthetic=True), source_seqs=(inv.seq,))
        with self.assertRaisesRegex(JournalError, "NOT_STARTED closes a call that was never dispatched"):
            w.append(T.TOOL_RESULT, result("S1", "c2", "NOT_STARTED", synthetic=True), source_seqs=(inv.seq,))
        with self.assertRaisesRegex(JournalError, "S9 has not begun"):
            w.append(T.TOOL_RESULT, result("S9", "c2", "NOT_STARTED", synthetic=True))
        w.append(T.TOOL_RESULT, result("S1", "c2", "NOT_STARTED", synthetic=True))
        w.append(T.TOOL_RESULT, result("S1", "c1", "OUTCOME_UNKNOWN", synthetic=True), source_seqs=(inv.seq,))

    def test_a_provider_result_closes_one_request_of_its_story(self):
        w = self.writer()
        self.story(w)
        w.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": SHA, "admitted": True, "developer_call_permitted": True,
                                    "dispositions": {"C1": "READY"}})
        req = w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        data = {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False, "detail": ""}
        for bad, message in (({**data, "outcome": "NOT_STARTED", "synthetic": True}, "a provider result is COMPLETED"),
                             ({**data, "outcome": "SIGNALLED"}, "a provider result is COMPLETED"),
                             ({**data, "outcome": "OUTCOME_UNKNOWN"}, "OUTCOME_UNKNOWN is a closer, always synthetic"),
                             ({**data, "synthetic": True}, "OUTCOME_UNKNOWN is a closer, always synthetic")):
            with self.subTest(data=bad), self.assertRaisesRegex(JournalError, message):
                w.append(T.PROVIDER_RESULT, bad, source_seqs=(req.seq,))
        with self.assertRaisesRegex(JournalError, "cites exactly one provider/request"):
            w.append(T.PROVIDER_RESULT, data)
        w.append(T.PROVIDER_RESULT, data, source_seqs=(req.seq,))
        with self.assertRaisesRegex(JournalError, rf"the provider/request at seq {req.seq} already has its result"):
            w.append(T.PROVIDER_RESULT, {**data, "outcome": "OUTCOME_UNKNOWN", "synthetic": True},
                     source_seqs=(req.seq,))
        second = w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        w.append(T.PROVIDER_RESULT, {**data, "outcome": "FAILED"}, source_seqs=(second.seq,))  # its own result


class Writer2(Journal2, unittest.TestCase):
    def test_the_surface_has_no_update_or_delete_verb_and_every_append_is_fsyncd(self):
        self.assertEqual(sorted(n for n in dir(f2.JournalWriter2) if not n.startswith("_")),
                         ["append", "close", "emit", "events", "head", "path"])
        w = self.writer()
        with mock.patch.object(f2.os, "fsync", wraps=os.fsync) as fsync:
            w.emit(T.RUN_END, {})
        self.assertEqual(fsync.call_count, 1)
        self.assertEqual(w.path, self.path)
        self.assertEqual(w.head, f2.reconstruct(self.text()).head())
        empty = f2.JournalWriter2(self.dir / "empty.jsonl")
        self.assertEqual(empty.head, ev.GENESIS)
        empty.close()  # Windows keeps an open file: an unclosed writer breaks the temp directory's cleanup
        with self.assertRaisesRegex(JournalError, "an event has a typed EventType"):
            w.append("run/end", {})
        w.close()
        w.close()
        with self.assertRaisesRegex(JournalError, "^the writer is closed$"):
            w.append(T.RUN_END, {})

    def test_a_failed_write_or_fsync_leaves_the_log_unchanged_and_poisons_the_writer(self):
        for name, (call, error) in {"disk full": ("write", OSError(errno.ENOSPC, "No space left on device")),
                                    "fsync failure": ("fsync", OSError(errno.EIO, "Input/output error")),
                                    "short write": ("write", None)}.items():
            with self.subTest(fault=name):
                path = self.dir / f"{name}.jsonl"
                w = self.writer(path)
                size, before = path.stat().st_size, w.events
                patch = mock.patch.object(f2.os, call, side_effect=error) if error else \
                    mock.patch.object(f2.os, "write", lambda fd, b, real=os.write: real(fd, b[:5]))
                detail = r"short write: 5 of \d+ bytes" if error is None else ".*"
                with patch, self.assertRaisesRegex(JournalError, rf"^append of run/end at seq 1 failed \(OSError: "
                                                                 rf"{detail}\); the journal did not grow$"):
                    w.append(T.RUN_END, {})
                self.assertEqual((w.events, path.stat().st_size), (before, size))
                with self.assertRaisesRegex(JournalError, "failed .* and accepts nothing more$"):
                    w.append(T.RUN_END, {})
                again = f2.JournalWriter2(path)
                self.addCleanup(again.close)
                self.assertEqual(again.events, before)

    def test_a_torn_tail_or_an_unknown_type_is_never_extended_and_the_seq_is_assigned_here(self):
        w = self.writer()
        with mock.patch.object(f2.os, "fsync", side_effect=OSError(errno.EIO, "gone")), \
                mock.patch.object(f2.os, "ftruncate", side_effect=OSError(errno.EIO, "gone")), \
                self.assertRaises(JournalError):
            w.append(T.RUN_END, {})
        w.close()
        self.assertGreater(len(self.text().splitlines()), 1)  # the truncation failed: the line stays
        self.path.write_bytes(self.text()[:-20].encode("utf-8"))  # and an append cut short is a torn tail
        with self.assertRaisesRegex(JournalError, r"ends in a torn append; repair it \(WP-4.6\) before extending it$"):
            f2.JournalWriter2(self.path)
        other = self.dir / "other.jsonl"
        w2 = self.writer(other)
        w2.close()
        stranger = Event(1, "report/progress", {}, 0.0, ignorable=True)
        other.write_bytes((other.read_bytes().decode() + ev.encode(stranger, ev.link(w2.head, stranger))).encode())
        with self.assertRaisesRegex(JournalError, r"holds event types this format-2 writer does not know \(seqs \[1\]\)"):
            f2.JournalWriter2(other)
        third = self.writer(self.dir / "third.jsonl")
        with mock.patch.object(f2.JournalWriter2, "_assign", lambda self: len(self._events) + 1), \
                self.assertRaisesRegex(JournalError, "seq == index"):
            third.append(T.RUN_END, {})
        self.assertEqual(len(third.events), 1)

    def test_the_journal_is_opened_binary_append_and_repair_time_is_kept(self):
        opened = []
        real = os.open
        with mock.patch.object(f2.os, "open", lambda p, flags, mode=0o777: opened.append(flags) or real(p, flags, mode)):
            w = self.writer()
        for flag in ("O_WRONLY", "O_CREAT", "O_APPEND"):
            self.assertTrue(opened[0] & getattr(os, flag), flag)
        with mock.patch.object(f2.os, "O_BINARY", 0x8000, create=True), \
                mock.patch.object(f2.os, "open", lambda p, flags, mode=0o777: opened.append(flags) or real(p, flags, mode)):
            f2.JournalWriter2(self.dir / "b.jsonl").close()
        self.assertTrue(opened[-1] & 0x8000)
        e = w.append(T.RUN_END, {"synthetic": True}, time=7.5)
        self.assertEqual(e.time, 7.5)
        rejected = mock.Mock(side_effect=JournalError("refused by the projections"))
        with self.assertRaisesRegex(JournalError, "refused by the projections"):
            w.append(T.RUN_END, {}, check=rejected)
        self.assertEqual(len(w.events), 2)


BEGIN_2 = {"journal_format": 2, "run_id": "run-p4"}

if __name__ == "__main__":
    unittest.main()
