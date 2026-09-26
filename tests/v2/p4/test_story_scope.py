"""WP-4.1 — StoryScope: ordered resource ownership (RFC §17.1, §18; P4-LIFETIME-SEMANTICS.md §2).

Kill set for `story_scope.py`. SCOPE-1 (acquire during disposal is refused), SCOPE-2 (a failed disposer does not stop
the others, and its failure stays recorded) and SCOPE-3 (the same resource graph gives the same disposal order).
"""

import ast
import pathlib
import random
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal.event import JournalError  # noqa: E402
from aisef2.journal.format2 import ResourceKind as K, reconstruct  # noqa: E402
from aisef2.runtime import story_scope as ss  # noqa: E402
from aisef2.runtime.story_scope import Directory, ScopeError, StoryScope  # noqa: E402
from tests.v2.p4.world import Fake, Journal2, emitter, released  # noqa: E402

GRAPH = [("scratch", K.SCRATCH), ("worktree", K.WORKTREE), ("sandbox", K.SANDBOX), ("range", K.PROCESS_RANGE),
         ("session", K.SESSION), ("grant", K.TOOL_GRANT)]


class Scope(Journal2, unittest.TestCase):
    def scope(self, w=None, story="S1", **kw):
        w = w or self.writer()
        self.story(w, story)
        return w, StoryScope(story, emitter(w), **kw)

    def test_ordered_acquire_and_reverse_dispose_round_trip_through_the_journal(self):
        w, s = self.scope()
        log = []
        for name, kind in GRAPH:
            self.assertIs(s.acquire(Fake(name, kind, log)).name, name)
        self.assertEqual(s.held, tuple(n for n, _ in GRAPH))
        report = s.dispose()
        order = [n for n, _ in reversed(GRAPH)]
        self.assertEqual(log, order)
        self.assertEqual(released(w), [(n, "RELEASED") for n in order])
        self.assertTrue(report.ok)
        self.assertEqual(tuple(r.resource for r in report.records), tuple(order))
        self.assertIsInstance(report.records, tuple)  # the report is evidence: immutable
        self.assertEqual((s.state, s.held), ("DISPOSED", ()))
        acquired = {e.data["resource"]: e.seq for e in w.events if e.type == T.STORY_RESOURCE_ACQUIRED.value}
        for e in w.events:
            if e.type == T.STORY_RESOURCE_RELEASED.value:
                self.assertEqual(e.source_seqs, (acquired[e.data["resource"]],))
                self.assertEqual((e.data["story_id"], e.data["synthetic"], e.data["detail"]), ("S1", False, ""))
        self.assertIs(s.dispose(), report)  # once
        self.assertEqual(len(released(w)), len(GRAPH))
        w.close()
        self.assertEqual(reconstruct(self.text()).events, w.events)

    def test_SCOPE_1_acquisition_during_or_after_disposal_is_refused_and_the_offer_released(self):
        w, s = self.scope()
        log = []
        late = []

        class Grabber(Fake):
            def release(inner):
                super().release()
                try:
                    s.acquire(Fake("late", K.SESSION, log))
                except ScopeError as e:
                    late.append(e)

        s.acquire(Grabber("worker", K.SESSION, log))
        s.dispose()
        self.assertEqual([e.code for e in late], ["INACTIVE_ACQUIRE"])
        self.assertIn("S1 is DISPOSING: late refused and released", str(late[0]))
        self.assertEqual(log, ["worker", "late"])
        with self.assertRaises(ScopeError) as after:
            s.acquire(Fake("later", K.SESSION, log))
        self.assertEqual(after.exception.code, "INACTIVE_ACQUIRE")
        self.assertIn("S1 is DISPOSED", str(after.exception))
        self.assertEqual(log, ["worker", "late", "later"])
        self.assertEqual([e.data["resource"] for e in w.events if e.type == T.STORY_RESOURCE_ACQUIRED.value],
                         ["worker"])

    def test_an_acquisition_out_of_disposal_order_is_refused_and_released(self):
        w, s = self.scope()
        log = []
        s.acquire(Fake("range", K.PROCESS_RANGE, log))
        with self.assertRaises(ScopeError) as e:
            s.acquire(Fake("worktree", K.WORKTREE, log))
        self.assertEqual(e.exception.code, "ORDER")
        self.assertEqual(str(e.exception), "ORDER: WORKTREE worktree after PROCESS_RANGE: reverse disposal would release it "
                                           "too late (§17.1); refused and released")
        self.assertEqual((log, s.held), (["worktree"], ("range",)))
        s.acquire(Fake("range-2", K.PROCESS_RANGE, log))  # equal rank is fine

    def test_a_refused_journal_write_on_acquisition_releases_the_resource(self):
        w, s = self.scope()
        log = []
        with mock.patch.object(w, "append", side_effect=JournalError("refused")), \
                self.assertRaisesRegex(JournalError, "refused"):
            s.acquire(Fake("r", K.SESSION, log))
        self.assertEqual((log, s.held), (["r"], ()))

    def test_only_the_most_recent_resource_is_released_before_disposal(self):
        w, s = self.scope()
        log = []
        wt, tool = s.acquire(Fake("wt", K.WORKTREE, log)), s.acquire(Fake("tool", K.PROCESS_RANGE, log, fail="gone"))
        with self.assertRaises(ScopeError) as e:
            s.release(wt)
        self.assertEqual(e.exception.code, "ORDER")
        self.assertEqual(str(e.exception), "ORDER: wt is not the most recent resource of S1: only the top of the stack is "
                                           "released early")
        r = s.release(tool)
        self.assertEqual((r.resource, r.status, r.detail), ("tool", "FAILED", "OSError: gone"))
        self.assertEqual((log, s.held, released(w)), (["tool"], ("wt",), [("tool", "FAILED")]))
        with self.assertRaises(ScopeError):
            s.release(tool)
        s.dispose()
        self.assertEqual(released(w), [("tool", "FAILED"), ("wt", "RELEASED")])

    def test_SCOPE_2_a_failing_first_disposer_does_not_stop_the_rest_and_stays_recorded(self):
        w, s = self.scope()
        log = []
        s.acquire(Fake("scratch", K.SCRATCH, log))
        s.acquire(Fake("worktree", K.WORKTREE, log))
        s.acquire(Fake("session", K.SESSION, log, fail="socket already gone"))
        report = s.dispose()
        self.assertEqual(log, ["session", "worktree", "scratch"])
        self.assertEqual(released(w), [("session", "FAILED"), ("worktree", "RELEASED"), ("scratch", "RELEASED")])
        failed = next(e for e in w.events if e.type == T.STORY_RESOURCE_RELEASED.value)
        self.assertEqual(failed.data["detail"], "OSError: socket already gone")
        self.assertFalse(report.ok)
        self.assertEqual(report.records[0].status, "FAILED")

    def test_a_range_not_proved_empty_makes_what_it_could_write_to_residual_and_nothing_else(self):
        w, s = self.scope()
        log = []
        s.acquire(Fake("scratch", K.SCRATCH, log))
        s.acquire(Fake("worktree", K.WORKTREE, log))
        s.acquire(Fake("range-a", K.PROCESS_RANGE, log))
        s.acquire(Fake("range-b", K.PROCESS_RANGE, log, residual="a grandchild is still writing"))
        s.acquire(Fake("session", K.SESSION, log))
        report = s.dispose()
        self.assertEqual(log, ["session", "range-b", "range-a"])  # the other range is still reaped
        self.assertEqual(released(w), [("session", "RELEASED"), ("range-b", "RESIDUAL"), ("range-a", "RELEASED"),
                                       ("worktree", "RESIDUAL"), ("scratch", "RESIDUAL")])
        details = [e.data["detail"] for e in w.events if e.type == T.STORY_RESOURCE_RELEASED.value]
        self.assertEqual(details[1], "a grandchild is still writing")
        self.assertEqual(details[3:], ["not released: process range range-b was not proved empty (§17.1)"] * 2)
        self.assertFalse(report.ok)
        w2, s2 = self.scope(w, "S2")
        s2.acquire(Fake("wt", K.WORKTREE, log))
        s2.acquire(Fake("range", K.PROCESS_RANGE, log, fail="kill failed"))
        s2.dispose()
        self.assertEqual(released(w)[-2:], [("range", "FAILED"), ("wt", "RESIDUAL")])

    def test_a_hanging_release_is_residual_at_its_bound_and_disposal_goes_on(self):
        w, s = self.scope(release_timeout_s=0.1234567)
        log, hang = [], threading.Event()
        self.addCleanup(hang.set)
        s.acquire(Fake("scratch", K.SCRATCH, log))
        s.acquire(Fake("session", K.SESSION, log, hang=hang))
        t = time.monotonic()
        report = s.dispose()
        self.assertLess(time.monotonic() - t, 5)
        self.assertEqual(released(w), [("session", "RESIDUAL"), ("scratch", "RELEASED")])
        self.assertEqual(report.records[0].detail, "not released: the release was still running after 0.123457s")
        hung = [t for t in threading.enumerate() if t.name == "release session"]
        self.assertEqual([t.daemon for t in hung], [True])  # a hung release never holds the interpreter open
        w2, s2 = self.scope(w, "S2", release_timeout_s=None)
        s2.acquire(Fake("quick", K.SESSION, log, delay=0.05))
        self.assertTrue(s2.dispose().ok)

    def test_abandonment_names_every_remaining_resource_residual(self):
        w, s = self.scope()
        log = []
        for name, kind in GRAPH[:3]:
            s.acquire(Fake(name, kind, log))
        calls = iter([False, True, True])
        s.dispose(abandoned=lambda: next(calls))
        self.assertEqual(log, ["sandbox"])
        self.assertEqual(released(w), [("sandbox", "RELEASED"), ("worktree", "RESIDUAL"), ("scratch", "RESIDUAL")])
        self.assertEqual({e.data["detail"] for e in w.events[-2:]},
                         {"not released: disposal was abandoned (second interrupt, §20.2)"})

    def test_a_broken_journal_during_disposal_still_releases_everything(self):
        w, s = self.scope()
        log = []
        for name, kind in GRAPH[:3]:
            s.acquire(Fake(name, kind, log))
        real = w.append
        with mock.patch.object(w, "append", side_effect=lambda *a, **k: (_ for _ in ()).throw(JournalError("disk"))
                               if a[0] is T.STORY_RESOURCE_RELEASED and a[1]["resource"] == "sandbox" else real(*a, **k)):
            report = s.dispose()
        self.assertEqual(log, ["sandbox", "worktree", "scratch"])  # every resource is still released
        self.assertEqual(report.records[0].unrecorded, "disk")
        # and the journal, missing the sandbox's record, refuses to vouch for any later order
        for r in report.records[1:]:
            self.assertRegex(r.unrecorded, rf"'{r.resource}' released before 'sandbox', acquired after it")
        self.assertFalse(report.ok)
        self.assertEqual(released(w), [])

    def test_SCOPE_3_the_same_resource_graph_gives_the_same_disposal_order_whatever_each_release_takes(self):
        orders = []
        for trial in range(6):
            w, s = self.scope(self.writer(self.dir / f"t{trial}.jsonl"))
            rng, log = random.Random(trial), []
            for name, kind in GRAPH:
                s.acquire(Fake(name, kind, log, delay=rng.choice([0.0, 0.002, 0.01])))
            s.dispose()
            orders.append((tuple(log), tuple(released(w))))
        self.assertEqual(len(set(orders)), 1)
        self.assertEqual(orders[0][0], tuple(n for n, _ in reversed(GRAPH)))

    def test_a_story_scope_owns_no_journal_writer(self):
        tree = ast.parse(pathlib.Path(ss.__file__).read_text(encoding="utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse({"JournalWriter", "JournalWriter2", "aisef2.journal.writer"} & names, names)
        self.assertFalse(any(isinstance(n, ast.ImportFrom) and n.module == "aisef2.journal.writer" for n in ast.walk(tree)))
        w, s = self.scope()
        self.assertFalse([k for k, v in vars(s).items() if type(v).__name__.startswith("JournalWriter")])


class Directories(Journal2, unittest.TestCase):
    def test_a_directory_release_removes_it_and_measures_that_it_is_gone(self):
        d = self.dir / "wt"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "f").write_text("x")
        Directory("wt", K.WORKTREE, d).release()
        self.assertFalse(d.exists())
        Directory("wt", K.WORKTREE, d).release()  # already gone: nothing to do
        with mock.patch.object(ss.shutil, "rmtree"), self.assertRaisesRegex(ss.Residual, "still exists after its "
                                                                                         "removal"):
            d.mkdir()
            Directory("wt", K.WORKTREE, d).release()
        with self.assertRaisesRegex(ValueError, "a directory resource is a worktree, sandbox or scratch, not "
                                                "PROCESS_RANGE"):
            Directory("r", K.PROCESS_RANGE, d)
        for kind in (K.WORKTREE, K.SCRATCH, K.SANDBOX):
            self.assertIs(Directory("x", kind, d).kind, kind)


if __name__ == "__main__":
    unittest.main()
