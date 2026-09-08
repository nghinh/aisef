"""Kiểm chứng bộ lập lịch: epic tuần tự, story song song theo đợt."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.scheduler import (  # noqa: E402
    CycleError,
    Story,
    UnknownDependencyError,
    build_waves,
    describe,
    paths_overlap,
    plan_epics,
    scopes_conflict,
)


def story(sid, *, epic="E1", deps=(), scope=("src/unique/" + "x",), status="pending"):
    return Story(id=sid, epic_id=epic, depends_on=tuple(deps), write_scope=tuple(scope), status=status)


class TestPathOverlap(unittest.TestCase):
    def test_identical(self):
        self.assertTrue(paths_overlap("src/api", "src/api"))

    def test_parent_child(self):
        self.assertTrue(paths_overlap("src/api", "src/api/users.py"))
        self.assertTrue(paths_overlap("src/api/users.py", "src/api"))

    def test_siblings_do_not_overlap(self):
        self.assertFalse(paths_overlap("src/api/users.py", "src/api/orders.py"))

    def test_string_prefix_is_not_overlap(self):
        """`src/api` và `src/apidocs` là hai vùng khác nhau."""
        self.assertFalse(paths_overlap("src/api", "src/apidocs"))

    def test_trailing_slash_ignored(self):
        self.assertTrue(paths_overlap("src/api/", "src/api"))


class TestScopeConflict(unittest.TestCase):
    def test_disjoint_scopes(self):
        a = story("A", scope=("src/api/users.py",))
        b = story("B", scope=("src/api/orders.py",))
        self.assertFalse(scopes_conflict(a, b))

    def test_shared_file(self):
        a = story("A", scope=("src/models/user.py",))
        b = story("B", scope=("src/models/user.py",))
        self.assertTrue(scopes_conflict(a, b))

    def test_missing_scope_is_treated_as_touching_everything(self):
        """Không khai phạm vi thì phải giả định xấu nhất."""
        a = story("A", scope=())
        b = story("B", scope=("src/api/x.py",))
        self.assertTrue(scopes_conflict(a, b))


class TestWaves(unittest.TestCase):
    def test_independent_disjoint_stories_run_together(self):
        stories = [
            story("A", scope=("src/a.py",)),
            story("B", scope=("src/b.py",)),
            story("C", scope=("src/c.py",)),
        ]
        waves = build_waves(stories)
        self.assertEqual(len(waves), 1)
        self.assertEqual({s.id for s in waves[0]}, {"A", "B", "C"})

    def test_conflicting_scopes_split_into_waves(self):
        """Không phụ thuộc nhau nhưng cùng chạm một file → phải tách đợt."""
        stories = [
            story("A", scope=("src/models/user.py",)),
            story("B", scope=("src/models/user.py",)),
        ]
        waves = build_waves(stories)
        self.assertEqual([len(w) for w in waves], [1, 1])

    def test_dependency_forces_later_wave(self):
        stories = [
            story("A", scope=("src/a.py",)),
            story("B", deps=("A",), scope=("src/b.py",)),
        ]
        waves = build_waves(stories)
        self.assertEqual([[s.id for s in w] for w in waves], [["A"], ["B"]])

    def test_diamond_dependency(self):
        stories = [
            story("A", scope=("src/a.py",)),
            story("B", deps=("A",), scope=("src/b.py",)),
            story("C", deps=("A",), scope=("src/c.py",)),
            story("D", deps=("B", "C"), scope=("src/d.py",)),
        ]
        waves = build_waves(stories)
        self.assertEqual([[s.id for s in w] for w in waves], [["A"], ["B", "C"], ["D"]])

    def test_cycle_detected(self):
        stories = [
            story("A", deps=("B",), scope=("src/a.py",)),
            story("B", deps=("A",), scope=("src/b.py",)),
        ]
        with self.assertRaises(CycleError) as ctx:
            build_waves(stories)
        self.assertIn("A", str(ctx.exception))

    def test_unknown_dependency_rejected(self):
        with self.assertRaises(UnknownDependencyError):
            build_waves([story("A", deps=("KHONG-CO",))])

    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            build_waves([story("A", scope=("src/a.py",)), story("A", scope=("src/b.py",))])

    def test_max_parallel_caps_wave_width(self):
        stories = [story(f"S{i}", scope=(f"src/{i}.py",)) for i in range(5)]
        waves = build_waves(stories, max_parallel=2)
        self.assertTrue(all(len(w) <= 2 for w in waves))
        self.assertEqual(sum(len(w) for w in waves), 5)

    def test_max_parallel_must_be_positive(self):
        with self.assertRaises(ValueError):
            build_waves([story("A")], max_parallel=0)

    def test_done_stories_are_skipped_and_satisfy_deps(self):
        """Chạy lại sau khi dừng giữa chừng: tiếp đúng chỗ dở."""
        stories = [
            story("A", scope=("src/a.py",), status="done"),
            story("B", deps=("A",), scope=("src/b.py",)),
        ]
        waves = build_waves(stories)
        self.assertEqual([[s.id for s in w] for w in waves], [["B"]])

    def test_all_done_gives_no_waves(self):
        stories = [story("A", status="done"), story("B", status="done")]
        self.assertEqual(build_waves(stories), [])

    def test_wave_order_is_stable(self):
        stories = [story(f"S{i}", scope=(f"src/{i}.py",)) for i in range(4)]
        first = [[s.id for s in w] for w in build_waves(stories)]
        second = [[s.id for s in w] for w in build_waves(list(reversed(stories)))]
        self.assertEqual(first, second)


class TestEpicPlanning(unittest.TestCase):
    def test_epics_are_sequential(self):
        stories = [
            story("E1-1", epic="E1", scope=("src/a.py",)),
            story("E2-1", epic="E2", scope=("src/b.py",)),
        ]
        plans = plan_epics(stories)
        self.assertEqual([p.epic_id for p in plans], ["E1", "E2"])
        self.assertEqual(plans[0].story_count, 1)
        self.assertEqual(plans[1].story_count, 1)

    def test_cross_epic_dependency_satisfied_by_epic_order(self):
        """Phụ thuộc sang epic trước không được coi là bế tắc."""
        stories = [
            story("E1-1", epic="E1", scope=("src/a.py",)),
            story("E2-1", epic="E2", deps=("E1-1",), scope=("src/b.py",)),
        ]
        plans = plan_epics(stories, epic_order=["E1", "E2"])
        self.assertEqual([[s.id for s in w] for w in plans[1].waves], [["E2-1"]])

    def test_explicit_epic_order_respected(self):
        stories = [
            story("E1-1", epic="E1", scope=("src/a.py",)),
            story("E2-1", epic="E2", scope=("src/b.py",)),
        ]
        plans = plan_epics(stories, epic_order=["E2", "E1"])
        self.assertEqual([p.epic_id for p in plans], ["E2", "E1"])

    def test_unknown_epic_rejected(self):
        with self.assertRaises(ValueError):
            plan_epics([story("A", epic="E1")], epic_order=["E9"])

    def test_max_width_reported(self):
        stories = [story(f"S{i}", scope=(f"src/{i}.py",)) for i in range(3)]
        plans = plan_epics(stories)
        self.assertEqual(plans[0].max_width, 3)

    def test_describe_is_readable(self):
        stories = [
            story("A", scope=("src/a.py",)),
            story("B", deps=("A",), scope=("src/b.py",)),
        ]
        text = describe(plan_epics(stories))
        self.assertIn("wave 1: A", text)
        self.assertIn("wave 2: B", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
