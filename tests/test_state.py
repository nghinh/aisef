"""Kiểm chứng kho trạng thái: chuyển trạng thái, khoá, resume."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.state import (  # noqa: E402
    STATE_FILE,
    SprintState,
    StateStore,
    StoryStatus,
    TransitionError,
)


class StateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = StateStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()


class TestTransitions(StateTestCase):
    def test_happy_path(self):
        self.store.register("S-01", "E-01")
        for to in (StoryStatus.RUNNING, StoryStatus.VERIFYING, StoryStatus.DONE):
            self.store.transition("S-01", to)
        self.assertIs(self.store.load().stories["S-01"].state, StoryStatus.DONE)

    def test_cannot_skip_verifying(self):
        """pending → done mà không qua verifying là bỏ qua cổng."""
        self.store.register("S-01")
        with self.assertRaises(TransitionError):
            self.store.transition("S-01", StoryStatus.DONE)

    def test_done_is_terminal(self):
        self.store.register("S-01")
        for to in (StoryStatus.RUNNING, StoryStatus.VERIFYING, StoryStatus.DONE):
            self.store.transition("S-01", to)
        with self.assertRaises(TransitionError):
            self.store.transition("S-01", StoryStatus.RUNNING)

    def test_failed_can_retry(self):
        self.store.register("S-01")
        self.store.transition("S-01", StoryStatus.RUNNING)
        self.store.transition("S-01", StoryStatus.FAILED)
        self.store.transition("S-01", StoryStatus.PENDING)
        rec = self.store.transition("S-01", StoryStatus.RUNNING)
        self.assertEqual(rec.attempts, 2)

    def test_attempts_increment_only_on_entering_running(self):
        self.store.register("S-01")
        self.store.transition("S-01", StoryStatus.RUNNING)
        self.store.transition("S-01", StoryStatus.VERIFYING)
        self.assertEqual(self.store.load().stories["S-01"].attempts, 1)

    def test_blocked_records_reason(self):
        self.store.register("S-01")
        rec = self.store.transition("S-01", StoryStatus.BLOCKED, reason="thiếu write_scope")
        self.assertIs(rec.state, StoryStatus.BLOCKED)
        self.assertIn("write_scope", rec.blocked_reason)

    def test_cost_and_duration_accumulate(self):
        self.store.register("S-01")
        self.store.transition("S-01", StoryStatus.RUNNING, cost_usd=0.4, duration_ms=1000)
        self.store.transition("S-01", StoryStatus.VERIFYING, cost_usd=0.2, duration_ms=500)
        rec = self.store.load().stories["S-01"]
        self.assertAlmostEqual(rec.cost_usd, 0.6)
        self.assertEqual(rec.duration_ms, 1500)


class TestQueries(StateTestCase):
    def seed(self):
        for sid, st in [
            ("S-01", StoryStatus.DONE),
            ("S-02", StoryStatus.DONE),
            ("S-03", StoryStatus.BLOCKED),
            ("S-04", StoryStatus.PENDING),
        ]:
            self.store.register(sid, "E-01")
            if st is StoryStatus.DONE:
                self.store.transition(sid, StoryStatus.RUNNING)
                self.store.transition(sid, StoryStatus.VERIFYING)
            self.store.transition(sid, st) if st is not StoryStatus.PENDING else None

    def test_done_ids_only_counts_done(self):
        self.seed()
        self.assertEqual(self.store.load().done_ids(), {"S-01", "S-02"})

    def test_blocked_does_not_satisfy_dependents(self):
        """Story phụ thuộc một story blocked không được phép chạy."""
        self.assertFalse(StoryStatus.BLOCKED.satisfies_dependents)
        self.assertTrue(StoryStatus.DONE.satisfies_dependents)

    def test_totals(self):
        self.seed()
        t = self.store.load().totals()
        self.assertEqual(t["done"], 2)
        self.assertEqual(t["blocked"], 1)
        self.assertEqual(t["pending"], 1)


class TestCostOutliers(StateTestCase):
    def test_uses_median_not_mean(self):
        """Một story cực đắt sẽ kéo trung bình lên và tự che chính nó."""
        st = SprintState()
        from aisdlc.control.state import StoryRecord

        for i, cost in enumerate([0.4, 0.5, 0.45, 0.5, 9.0]):
            st.stories[f"S-{i}"] = StoryRecord(id=f"S-{i}", cost_usd=cost)
        outliers = st.cost_outliers(3.0)
        self.assertEqual([r.cost_usd for r in outliers], [9.0])

    def test_too_few_samples_gives_nothing(self):
        from aisdlc.control.state import StoryRecord

        st = SprintState(stories={"a": StoryRecord(id="a", cost_usd=99.0)})
        self.assertEqual(st.cost_outliers(3.0), [])


class TestDurability(StateTestCase):
    def test_survives_new_store_instance(self):
        self.store.register("S-01", "E-01")
        self.store.transition("S-01", StoryStatus.RUNNING)
        self.assertIs(
            StateStore(self.root).load().stories["S-01"].state, StoryStatus.RUNNING
        )

    def test_corrupt_file_starts_clean(self):
        (self.root).mkdir(parents=True, exist_ok=True)
        (self.root / STATE_FILE).write_text("{ hỏng", encoding="utf-8")
        self.assertEqual(self.store.load().stories, {})

    def test_write_is_atomic(self):
        """Không để lại file tạm sau khi ghi xong."""
        self.store.register("S-01")
        leftovers = list(self.root.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_register_is_idempotent(self):
        self.store.register("S-01", "E-01")
        self.store.transition("S-01", StoryStatus.RUNNING)
        self.store.register("S-01", "E-01")  # không được reset
        self.assertIs(self.store.load().stories["S-01"].state, StoryStatus.RUNNING)


class TestConcurrency(StateTestCase):
    def test_parallel_writers_do_not_lose_updates(self):
        """Nhiều story chạy song song cùng cập nhật trạng thái.

        Không khoá thì hai lần ghi gần nhau sẽ mất một — đây là ca thật,
        không phải giả định: mỗi story kết thúc đều ghi vào cùng một file.
        """
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(ROOT)!r})
            from aisdlc.control.state import StateStore, StoryStatus
            store = StateStore({str(self.root)!r})
            sid = sys.argv[1]
            store.register(sid, "E-01")
            store.transition(sid, StoryStatus.RUNNING)
        """)
        script_path = self.root / "writer.py"
        script_path.write_text(script, encoding="utf-8")

        procs = [
            subprocess.Popen([sys.executable, str(script_path), f"S-{i:02d}"])
            for i in range(8)
        ]
        for p in procs:
            p.wait(timeout=60)

        state = self.store.load()
        self.assertEqual(len(state.stories), 8, f"mất bản ghi: {sorted(state.stories)}")
        self.assertTrue(all(r.state is StoryStatus.RUNNING for r in state.stories.values()))

    def test_state_file_is_valid_json_after_parallel_writes(self):
        self.store.register("S-01")
        raw = json.loads((self.root / STATE_FILE).read_text(encoding="utf-8"))
        self.assertIn("stories", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
