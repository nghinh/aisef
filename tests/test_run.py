"""Điều phối đợt — epic tuần tự, story rời nhau chạy song song, resume.

Chạy trên kho git thật với worktree thật: phần đáng nghi nhất của module
này là cách nó cách ly và hợp nhất công việc, và điều đó không kiểm được
bằng bản giả.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.control.state import StateStore, StoryStatus  # noqa: E402
from aisdlc.phases.run import load_plan, run_sprint  # noqa: E402

INDEX = {
    "epics": [{"id": "EPIC-01"}, {"id": "EPIC-02"}],
    "stories": [
        {"id": "STORY-01-01", "epic_id": "EPIC-01", "title": "nền",
         "covers": ["FR-1"], "write_scope": ["src/core"], "depends_on": []},
        {"id": "STORY-01-02", "epic_id": "EPIC-01", "title": "A",
         "covers": ["FR-2"], "write_scope": ["src/a"], "depends_on": ["STORY-01-01"]},
        {"id": "STORY-01-03", "epic_id": "EPIC-01", "title": "B",
         "covers": ["FR-3"], "write_scope": ["src/b"], "depends_on": ["STORY-01-01"]},
        {"id": "STORY-02-01", "epic_id": "EPIC-02", "title": "sau",
         "covers": ["FR-4"], "write_scope": ["src/late"], "depends_on": []},
    ],
    "waves": {
        "EPIC-01": [["STORY-01-01"], ["STORY-01-02", "STORY-01-03"]],
        "EPIC-02": [["STORY-02-01"]],
    },
}


class Agent(ClientAdapter):
    """Agent giả: viết một file trong phạm vi của story, rà soát sạch."""

    id = "fake"

    def __init__(self, *, fail: set[str] | None = None, out_of_scope: set[str] | None = None,
                 overlap_ms: int = 0):
        self.fail = fail or set()
        self.out_of_scope = out_of_scope or set()
        self.lock = threading.Lock()
        self.concurrent = 0
        self.max_concurrent = 0
        self.stories: list[str] = []
        #: Kéo dài mỗi lượt để chồng lấn quan sát được. Công việc chạy vài
        #: micro giây thì hầu như không bao giờ thấy chồng lấn, kể cả khi
        #: nó có thật.
        self.overlap_ms = overlap_ms

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        if "Rà soát" in spec.prompt:
            return RunResult(ok=True, text="không có mục chặn", cost_usd=0.1)

        story_id = spec.env.get("AISDLC_STORY_ID", "")
        scope = spec.env.get("AISDLC_WRITE_SCOPE", "src").split(",")[0]
        with self.lock:
            self.stories.append(story_id)
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            if self.overlap_ms:
                time.sleep(self.overlap_ms / 1000)
            if story_id in self.fail:
                return RunResult(ok=True, text="xong", cost_usd=1.0)  # không ghi gì
            target = scope if story_id not in self.out_of_scope else "ngoai-pham-vi"
            path = Path(spec.workdir) / target / f"{story_id}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {story_id}\n", encoding="utf-8")
            return RunResult(ok=True, text="xong", cost_usd=1.0)
        finally:
            with self.lock:
                self.concurrent -= 1


class RunTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)
        (self.project / "README.md").write_text("dự án\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "đầu tiên"], cwd=self.project, check=True)

        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        (self.artifacts / "stories.index.json").write_text(
            json.dumps(INDEX, ensure_ascii=False), encoding="utf-8"
        )
        # Kế hoạch được commit trước khi hiện thực — đúng như thực tế, vì
        # bản ghi phê duyệt và tài liệu kế hoạch đi qua git giữa các máy.
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "kế hoạch"], cwd=self.project, check=True)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        return Config({**DEFAULTS, "tools.test": "true", "tools.lint": "true",
                       "run.max_retries": 0, **over})

    def run_sprint(self, agent, **kw):
        return run_sprint(self.project, agent, config=kw.pop("config", self.config()), **kw)

    def state(self):
        return StateStore(self.artifacts).load()


class TestPlanLoading(RunTestCase):
    def test_reads_stories_and_waves(self):
        plan = load_plan(self.artifacts)
        self.assertEqual(len(plan.stories), 4)
        self.assertEqual(plan.waves["EPIC-01"][1], ["STORY-01-02", "STORY-01-03"])

    def test_missing_index_is_a_clear_error(self):
        (self.artifacts / "stories.index.json").unlink()
        self.assertIn("aisdlc plan", load_plan(self.artifacts).error)

    def test_broken_index(self):
        (self.artifacts / "stories.index.json").write_text("{ hỏng", encoding="utf-8")
        self.assertIn("hỏng", load_plan(self.artifacts).error)


class TestOrchestration(RunTestCase):
    def test_runs_everything_and_merges(self):
        agent = Agent()
        report = self.run_sprint(agent)
        self.assertTrue(report.ok, report.summary())
        self.assertEqual(len(report.outcomes), 4)
        for name in ("src/core/STORY-01-01.py", "src/a/STORY-01-02.py",
                     "src/late/STORY-02-01.py"):
            self.assertTrue((self.project / name).is_file(), name)

    def test_epics_run_in_order(self):
        agent = Agent()
        self.run_sprint(agent)
        self.assertEqual(agent.stories[0], "STORY-01-01")
        self.assertEqual(agent.stories[-1], "STORY-02-01")

    def test_independent_stories_run_in_parallel(self):
        agent = Agent(overlap_ms=300)
        report = self.run_sprint(agent, only_epic="EPIC-01")
        self.assertGreaterEqual(agent.max_concurrent, 2, report.summary())

    def test_sequential_flag_disables_parallelism(self):
        agent = Agent()
        self.run_sprint(agent, sequential=True)
        self.assertEqual(agent.max_concurrent, 1)

    def test_each_story_gets_its_own_worktree(self):
        """Hai story cùng đợt ghi vào cùng cây thì `git status` của story
        này thấy file của story kia — cổng phạm vi sẽ trượt oan."""
        agent = Agent()
        report = self.run_sprint(agent)
        self.assertTrue(report.ok, report.summary())

    def test_only_epic_limits_the_run(self):
        agent = Agent()
        report = self.run_sprint(agent, only_epic="EPIC-02")
        self.assertEqual([o.story_id for o in report.outcomes], ["STORY-02-01"])

    def test_unknown_epic_is_refused(self):
        self.assertIn("không có", self.run_sprint(Agent(), only_epic="EPIC-99").error)


class TestStopsOnFailure(RunTestCase):
    def test_failed_story_stops_the_sprint(self):
        """Story sau thường dựa trên story trước; chạy tiếp trên nền hỏng
        chỉ nhân số việc phải làm lại."""
        report = self.run_sprint(Agent(fail={"STORY-01-01"}))
        self.assertFalse(report.ok)
        self.assertIn("EPIC-01", report.stopped_at)
        self.assertEqual(len(report.outcomes), 1)

    def test_state_records_the_failure(self):
        self.run_sprint(Agent(fail={"STORY-01-01"}))
        self.assertIs(self.state().stories["STORY-01-01"].state, StoryStatus.FAILED)

    def test_out_of_scope_write_fails_the_story(self):
        report = self.run_sprint(Agent(out_of_scope={"STORY-01-01"}))
        self.assertFalse(report.ok)
        self.assertIn("phạm vi", report.summary())


class TestResume(RunTestCase):
    def test_finished_stories_are_not_rerun(self):
        first = Agent()
        self.run_sprint(first)
        second = Agent()
        report = self.run_sprint(second)
        self.assertEqual(second.stories, [])
        self.assertTrue(report.ok, report.summary())
        self.assertTrue(any(w.skipped for w in report.waves))

    def test_resume_continues_after_a_fix(self):
        self.run_sprint(Agent(fail={"STORY-01-02"}))
        self.assertIs(self.state().stories["STORY-01-02"].state, StoryStatus.FAILED)
        agent = Agent()
        report = self.run_sprint(agent)
        self.assertTrue(report.ok, report.summary())
        self.assertNotIn("STORY-01-01", agent.stories)  # đã xong từ lượt trước
        self.assertIn("STORY-01-02", agent.stories)

    def test_chay_lai_story_that_bai_thi_ban_ghi_phai_theo_kip(self):
        """Làm xong mà sổ vẫn ghi `failed` là báo cáo nói dối.

        Máy trạng thái không có cạnh từ `failed` sang `running`, và
        `_safe_transition` nuốt lỗi — nên lượt chạy lại làm hết việc,
        merge xong, mở đợt sau, mà bản ghi đứng nguyên ở lần thất bại cũ
        và chi phí lượt mới không vào sổ. Quan sát thật trên e9.
        """
        self.run_sprint(Agent(fail={"STORY-01-02"}))
        truoc = self.state().stories["STORY-01-02"]
        self.assertIs(truoc.state, StoryStatus.FAILED)
        self.assertTrue(truoc.blocked_reason)

        self.run_sprint(Agent())
        sau = self.state().stories["STORY-01-02"]
        self.assertIs(sau.state, StoryStatus.DONE, "làm xong rồi thì sổ phải ghi done")
        self.assertFalse(sau.blocked_reason, "lý do chặn cũ phải được xoá")
        self.assertGreater(sau.cost_usd, truoc.cost_usd, "chi phí lượt mới phải vào sổ")

    def test_story_bo_do_vi_tien_trinh_chet_duoc_thu_hoi(self):
        """`running` còn sót là của tiến trình đã chết, không phải đang chạy."""
        self.run_sprint(Agent(fail={"STORY-01-02"}))
        st = StateStore(self.artifacts)
        with st.transaction() as raw:
            raw.stories["STORY-01-02"].status = StoryStatus.RUNNING.value

        self.run_sprint(Agent())
        self.assertIs(self.state().stories["STORY-01-02"].state, StoryStatus.DONE)


class TestPreflight(RunTestCase):
    """Story không chạy được phải bị chặn **trước** khi model được gọi.

    Cổng `stories` đã chấm cùng phép kiểm, nhưng cấu hình dự án đổi được
    sau khi cổng ấy duyệt — và mỗi đồng tiêu cho một story không thể qua
    là tiêu vào chỗ không có lối ra.
    """

    def index_with(self, **over):
        raw = json.loads((self.artifacts / "stories.index.json").read_text())
        for s in raw["stories"]:
            if s["id"] == "STORY-01-01":
                s.update(over)
        (self.artifacts / "stories.index.json").write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8"
        )

    def test_story_ui_thieu_trinh_duyet_thi_chan_truoc_khi_goi_model(self):
        self.index_with(screens=["notes-list"])
        agent = Agent()
        self.run_sprint(agent)
        self.assertNotIn("STORY-01-01", agent.stories, "model không được gọi")
        rec = self.state().stories["STORY-01-01"]
        self.assertIs(rec.state, StoryStatus.BLOCKED)
        self.assertIn("STORY_NOT_EXECUTABLE", rec.blocked_reason)
        self.assertIn("browser", rec.blocked_reason)

    def test_story_khai_thieu_write_scope_thi_chan_truoc_khi_goi_model(self):
        self.index_with(
            acceptance_criteria=["Then `src/khac/thieu.py` sinh ra báo cáo"],
        )
        agent = Agent()
        self.run_sprint(agent)
        self.assertNotIn("STORY-01-01", agent.stories, "model không được gọi")
        self.assertIn(
            "src/khac/thieu.py", self.state().stories["STORY-01-01"].blocked_reason
        )

    def test_thieu_cong_cu_test_thi_chan_truoc_khi_goi_model(self):
        agent = Agent()
        self.run_sprint(agent, config=self.config(**{"tools.test": ""}))
        self.assertEqual(agent.stories, [])
        self.assertIn("tools.test", self.state().stories["STORY-01-01"].blocked_reason)

    def test_story_du_dieu_kien_van_chay_binh_thuong(self):
        agent = Agent()
        report = self.run_sprint(agent)
        self.assertTrue(report.ok, report.summary())
        self.assertIn("STORY-01-01", agent.stories)


class TestTransaction(RunTestCase):
    """Lượt chạy story là một giao dịch — nhật ký sống sót qua tiến trình."""

    def journal(self, sid="STORY-01-01"):
        from aisdlc.control.journal import JournalStore

        return JournalStore(self.artifacts).read(sid)

    def test_story_xong_ghi_du_moc_toi_attempt_committed(self):
        self.run_sprint(Agent())
        steps = self.journal().steps()
        for moc in ("attempt.started", "worktree.created", "status.running",
                    "verification.completed", "review.completed",
                    "commit.created", "merge.completed", "attempt.committed"):
            self.assertIn(moc, steps, steps)

    def test_story_truot_dong_giao_dich_ngay_khong_no_gi(self):
        self.run_sprint(Agent(fail={"STORY-01-01"}))
        j = self.journal()
        self.assertIn("attempt.committed", j.steps())
        self.assertNotIn("merge.completed", j.steps())
        self.assertEqual(j.open_attempt(), 0)

    def test_tien_trinh_chet_giua_chung_thi_luot_sau_don_va_khong_de_running(self):
        """Mô phỏng đúng thứ đã xảy ra: tiến trình bị giết sau khi story
        chuyển sang `running`, để lại nhật ký dở và trạng thái kẹt."""
        from aisdlc.control.journal import Entry, JournalStore

        js = JournalStore(self.artifacts)
        js.record("STORY-01-01", Entry(step="attempt.started", attempt=1))
        js.record("STORY-01-01", Entry(step="worktree.created", attempt=1))
        js.record("STORY-01-01", Entry(step="status.running", attempt=1))
        st = StateStore(self.artifacts)
        st.register("STORY-01-01", "EPIC-01", wave=1)
        st.transition("STORY-01-01", StoryStatus.RUNNING)

        report = self.run_sprint(Agent())
        self.assertTrue(report.reconciled, "phải dọn dấu vết lượt trước")
        self.assertIn("↺", report.summary())
        self.assertIsNot(self.state().stories["STORY-01-01"].state, StoryStatus.RUNNING)
        self.assertTrue(report.ok, report.summary())

    def test_merge_xong_nhung_so_ghi_failed_thi_duoc_dua_ve_done(self):
        """Đã xảy ra trên e9: worktree merge, wave sau khởi động, sổ vẫn
        `failed`, và chạy lại chỉ thấy diff rỗng."""
        from aisdlc.control.journal import Entry, JournalStore

        js = JournalStore(self.artifacts)
        js.record("STORY-01-01", Entry(step="attempt.started", attempt=1))
        js.record("STORY-01-01", Entry(step="merge.completed", attempt=1))
        st = StateStore(self.artifacts)
        st.register("STORY-01-01", "EPIC-01", wave=1)
        st.transition("STORY-01-01", StoryStatus.RUNNING)
        st.transition("STORY-01-01", StoryStatus.FAILED)

        agent = Agent()
        self.run_sprint(agent)
        self.assertIs(self.state().stories["STORY-01-01"].state, StoryStatus.DONE)
        self.assertNotIn("STORY-01-01", agent.stories,
                         "story đã merge thì không chạy lại")


class TestIsolationOff(RunTestCase):
    def test_no_isolate_runs_in_the_project_itself(self):
        report = self.run_sprint(Agent(), only_epic="EPIC-02", isolate=False)
        self.assertTrue(report.ok, report.summary())
        self.assertTrue((self.project / "src/late/STORY-02-01.py").is_file())

    def test_isolation_requires_git(self):
        import shutil

        shutil.rmtree(self.project / ".git")
        self.assertIn("git", self.run_sprint(Agent()).error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
