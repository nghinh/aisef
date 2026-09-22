"""WP-3.3 — the pure-fold engine and the from-scratch oracle (RFC §21; F11). FOLD-1, FOLD-2 and PROJ-1 are here.

Kill set for `fold.py::fold`, `Folder`, `oracle_problems` and `resume`: generated runs (tests/v2/p3/journal_gen.py)
through all six projections, prefix by prefix.
"""

import dataclasses
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ControlProjection as P, EventType as T  # noqa: E402
from aisef2.journal import fold as fo  # noqa: E402
from aisef2.journal.compat import reconstruct  # noqa: E402
from aisef2.journal.event import JournalError  # noqa: E402
from aisef2.journal.projections import PROJECTIONS, project  # noqa: E402
from aisef2.journal.writer import JournalWriter  # noqa: E402
from aisef2.product.contract import canonical, digest  # noqa: E402
from tests.v2.p3 import journal_gen as gen  # noqa: E402

SIX = list(PROJECTIONS.values())


def journal(seed, **kw):
    return reconstruct(gen.journal(seed, **kw))


class Counter:
    id, version = "counter", 1

    def initial(self):
        return {"n": 0, "types": []}

    def step(self, state, event):
        return {"n": state["n"] + 1, "types": [*state["types"], event.type]}


class Oracle(unittest.TestCase):
    def test_FOLD_1_incremental_equals_full_fold_for_every_prefix(self):
        for seed in range(40):
            events = journal(seed, stories=2 + seed % 4).events
            for p in SIX:
                with self.subTest(seed=seed, projection=p.id):
                    self.assertEqual(fo.oracle_problems(p, events), [])

    def test_large_generated_journals_at_sampled_decision_points(self):
        for seed in (101, 202):
            events = journal(seed, stories=40).events
            self.assertGreater(len(events), 300)
            for p in SIX:
                with self.subTest(seed=seed, projection=p.id):
                    self.assertEqual(fo.oracle_problems(p, events, every=37), [])

    def test_the_oracle_sees_a_step_that_depends_on_history_it_should_not(self):
        class Leaky(Counter):
            id = "leaky"
            seen = 0

            def step(self, state, event):  # incremental folds share `seen`; a from-scratch fold starts it again
                Leaky.seen += 1
                return {"n": Leaky.seen, "types": []}
        events = journal(3).events
        for every in (1, 3, len(events) + 5):
            with self.subTest(every=every):
                Leaky.seen = 0
                want = [f"leaky: incremental state after {n} events differs from fold(prefix)"
                        for n in range(1, len(events) + 1) if n % every == 0 or n == len(events)]
                self.assertEqual(fo.oracle_problems(Leaky(), events, every=every), want)
                self.assertEqual(fo.oracle_problems(Counter(), events, every=every), [])

    def test_FOLD_2_wall_clock_time_is_not_control_state(self):
        for seed in range(15):
            rng = random.Random(seed)
            a = journal(seed)
            b = reconstruct(gen.journal(seed, times=lambda n, rng=rng: 1.7e9 + rng.uniform(0, 1e6)))
            self.assertNotEqual(a.head(), b.head())  # the journals differ ...
            self.assertEqual([dataclasses.replace(e, time=0.0) for e in a.events],
                             [dataclasses.replace(e, time=0.0) for e in b.events])  # ... only in time
            for p in SIX:
                with self.subTest(seed=seed, projection=p.id):
                    self.assertEqual(fo.fold(p, a.events), fo.fold(p, b.events))

    def test_empty_journal_one_event_and_replay_twice(self):
        for p in SIX:
            with self.subTest(projection=p.id):
                self.assertEqual(fo.fold(p, []), fo.fold(p, ()))
                self.assertEqual(canonical(fo.fold(p, [])), canonical(p.initial()))
                one = journal(0).events[:1]
                self.assertEqual(fo.fold(p, one), fo.Folder(p).advance(one[0]))
                events = journal(9).events
                self.assertEqual(canonical(fo.fold(p, events)), canonical(fo.fold(p, events)))

    def test_an_interrupted_tail_folds_as_its_complete_prefix(self):
        text = gen.journal(5)
        cut = text[:len(text) - 30]
        torn = reconstruct(cut)
        complete = reconstruct(cut[:cut.rindex("\n") + 1])
        self.assertTrue(torn.torn_tail)
        self.assertEqual(torn.events, complete.events)
        for p in SIX:
            with self.subTest(projection=p.id):
                self.assertEqual(fo.fold(p, torn.events), fo.fold(p, complete.events))

    def test_serialisation_is_deterministic_across_processes(self):
        here = {p.id: digest(fo.fold(p, journal(11).events)) for p in SIX}
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from aisef2.journal.compat import reconstruct; "
                "from aisef2.journal.fold import fold; from aisef2.journal.projections import PROJECTIONS; "
                "from aisef2.product.contract import digest; from tests.v2.p3 import journal_gen as g; "
                "j = reconstruct(g.journal(11)); print({p.id: digest(fold(p, j.events)) for p in PROJECTIONS.values()})")
        out = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, encoding="utf-8",
                             cwd=str(ROOT)).stdout.strip()
        self.assertEqual(out, str(here))


class Purity(unittest.TestCase):
    def test_a_step_cannot_change_the_state_it_is_given(self):
        class Mutating(Counter):
            id = "mutating"

            def step(self, state, event):
                state["n"] += 1
                return state
        with self.assertRaises(TypeError):
            fo.fold(Mutating(), journal(1).events)
        before = fo.fold(Counter(), journal(1).events[:3])
        folder = fo.Folder(Counter(), before, 2)
        folder.peek(journal(1).events[3])
        self.assertEqual((folder.state, folder.seq), (before, 2))

    def test_a_state_is_a_JSON_value(self):
        class Setty(Counter):
            id = "setty"

            def step(self, state, event):
                return {"n": {1, 2}}
        with self.assertRaisesRegex(fo.ProjectionError, r"^setty: a state is a JSON value \(set is not JSON-shaped "
                                                         r"data\)$"):
            fo.fold(Setty(), journal(1).events)

    def test_events_fold_in_seq_order(self):
        events = journal(2).events
        folder = fo.Folder(Counter())
        folder.advance(events[1])
        for e in (events[0], events[1]):
            with self.subTest(seq=e.seq), self.assertRaisesRegex(fo.ProjectionError,
                                                                 f"^counter: seq {e.seq} folded after seq 1$"):
                folder.advance(e)
        self.assertIsInstance(fo.ProjectionError("x"), JournalError)


class Caches(unittest.TestCase):
    def setUp(self):
        self.full = journal(21)
        self.p = PROJECTIONS[P.BUDGETS]
        self.truth = fo.fold(self.p, self.full.events)
        half = reconstruct(gen.journal(21)[:self.cut(gen.journal(21))])
        self.half = half
        self.row = fo.cache_row(self.p, half)

    @staticmethod
    def cut(text):
        lines = text.splitlines(keepends=True)
        return sum(len(x) for x in lines[:len(lines) // 2])

    def test_a_stale_row_is_a_shortcut_and_the_answer_is_the_full_fold(self):
        state, how = fo.resume(self.p, self.full, self.row)
        self.assertEqual((state, how), (self.truth, f"resumed from the row at {self.half.length}"))
        self.assertLess(self.row.length, self.full.length)
        self.assertEqual(fo.resume(self.p, self.full, fo.cache_row(self.p, self.full))[0], self.truth)
        self.assertEqual(fo.resume(self.p, self.full, None), (self.truth, "no cache row"))

    def test_PROJ_1_a_row_that_differs_from_the_journal_is_discarded_and_the_journal_wins(self):
        row = self.row
        other = fo.cache_row(self.p, reconstruct(gen.journal(22)))
        wrong = dataclasses.replace(row, state={**row.state, "retries": {"S1": {"DEVELOPER": 99}}})
        forged = dataclasses.replace(wrong, digest=fo._seal(row.projection, row.version, row.length, row.head,
                                                            wrong.state))
        cases = {
            "edited state": (wrong, "row does not match its seal (edited): discarded"),
            "another journal": (dataclasses.replace(other, length=min(other.length, self.full.length)), None),
            "another projection": (fo.cache_row(PROJECTIONS[P.STORY_STATE], self.half),
                                   "row is for story_state: discarded"),
            "ahead of the journal": (fo.cache_row(self.p, reconstruct(gen.journal(21, stories=9))), None),
        }
        for name, (bad, why) in cases.items():
            with self.subTest(case=name):
                state, how = fo.resume(self.p, self.full, bad)
                self.assertEqual(state, self.truth)
                self.assertTrue(how.endswith("discarded") or "discarded" in how, how)
                if why:
                    self.assertEqual(how, why)
        # the ceiling: a row re-sealed over a wrong state, with the right head, passes resume's checks ...
        state, how = fo.resume(self.p, self.full, forged)
        self.assertEqual((state == self.truth, how.startswith("resumed")), (False, True))
        # ... so a gate never reads a cache: project() folds the journal, and the oracle catches the row
        self.assertEqual(project(self.full, P.BUDGETS), self.truth)
        self.assertNotEqual(forged.state, fo.fold(self.p, self.half.events))
        version = dataclasses.replace(row, version=2)
        version = dataclasses.replace(version, digest=fo._seal(row.projection, 2, row.length, row.head, row.state))
        self.assertEqual(fo.resume(self.p, self.full, version),
                         (self.truth, "row version 2 is not 1: discarded, not migrated"))
        moved = dataclasses.replace(row, head="f" * 64)
        moved = dataclasses.replace(moved, digest=fo._seal(row.projection, 1, row.length, "f" * 64, row.state))
        self.assertEqual(fo.resume(self.p, self.full, moved),
                         (self.truth, "row head differs from the journal's at its length: discarded — the journal wins"))
        ahead = dataclasses.replace(row, length=self.full.length + 1)
        ahead = dataclasses.replace(ahead, digest=fo._seal(row.projection, 1, ahead.length, row.head, row.state))
        self.assertEqual(fo.resume(self.p, self.full, ahead)[1],
                         f"row covers {ahead.length} events; the journal has {self.full.length}: discarded")

    def test_the_seal_binds_every_field_by_name(self):
        r = self.row
        self.assertEqual(r.digest, digest({"projection": r.projection, "version": r.version, "length": r.length,
                                           "head": r.head, "state": r.state}))
        for field, value in (("projection", "budgetz"), ("version", 7), ("length", r.length - 1), ("head", "e" * 64),
                             ("state", {})):
            with self.subTest(field=field):
                edited = dataclasses.replace(r, **{field: value})
                self.assertEqual(fo.resume(self.p, self.full, edited),
                                 (self.truth, "row does not match its seal (edited): discarded"))

    def test_a_gate_reads_only_the_six_and_only_from_the_journal(self):
        self.assertEqual(set(PROJECTIONS), set(P))
        with self.assertRaises(TypeError):
            PROJECTIONS["progress_report"] = Counter()
        for bad in ("budgets", "progress_report", None, Counter()):
            with self.subTest(bad=bad), self.assertRaisesRegex(fo.ProjectionError, "one of the six control-critical"):
                project(self.full, bad)
        self.assertEqual(project(self.full, P.BUDGETS), self.truth)
        self.assertNotIn("cache", __import__("inspect").signature(project).parameters)


class Authority(unittest.TestCase):
    def test_the_incremental_state_is_the_fold_and_a_refused_event_never_reaches_the_log(self):
        with tempfile.TemporaryDirectory(prefix="aisef2-authority-") as d:
            path = pathlib.Path(d, "j.jsonl")
            w = JournalWriter(path, clock=lambda: 0.0)
            a = fo.Authority(w, SIX)
            specs = gen.specs(31)[:60]
            for type_, data, cites in specs:
                got = a.append(T(type_), data, source_seqs=cites)
                self.assertEqual(got, w.events[-1])
            j = reconstruct(path.read_text(encoding="utf-8"))
            for p in SIX:
                self.assertEqual(a.state(p.id), fo.fold(p, j.events))
            size = path.stat().st_size
            with self.assertRaisesRegex(fo.ProjectionError, "not a §17 transition"):
                a.append(T.STORY_COMMIT, {"story_id": "S-never-begun", "revision": "a" * 40})
            self.assertEqual((path.stat().st_size, len(w.events)), (size, len(specs)))
            with self.assertRaisesRegex(fo.ProjectionError, "^projection budgets registered twice$"):
                fo.Authority(w, [PROJECTIONS[P.BUDGETS], PROJECTIONS[P.BUDGETS]])
            again = fo.Authority(JournalWriter(path), SIX)  # re-opened: seeded by folding what is there
            self.assertEqual([again.state(p.id) for p in SIX], [a.state(p.id) for p in SIX])
            w.close()
            again.writer.close()


if __name__ == "__main__":
    unittest.main()
