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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401 — HostProvider vào chỗ docker, không mở container (tests/__init__.py)

from aisef.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.journal import Entry as JEntry  # noqa: E402
from aisef.control.journal import JournalStore  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.state import StateStore, StoryStatus  # noqa: E402
from aisef.control.worktree import WorktreeManager  # noqa: E402
from aisef.harness.observe import AGENT_RUN, NOTE, TOOL_RUN, EvidenceStore  # noqa: E402
from aisef.phases.run import load_plan, run_sprint, run_verify_only  # noqa: E402

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
                 overlap_ms: int = 0, meet: set[str] | None = None):
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
        #: Các story phải **gặp nhau** trong lượt chạy: mỗi story trong tập
        #: này đứng chờ ở rào cho tới khi tất cả cùng tới. Song song thật thì
        #: rào mở ngay; tuần tự thì story đầu chờ đến hết giờ và rào vỡ. Khác
        #: `overlap_ms`: không phụ thuộc đồng hồ, nên không đổi màu theo tải
        #: máy (P0-2: 300 ms chồng lấn thua một `git worktree add` dưới tải).
        self.meet = meet or set()
        self.barrier = threading.Barrier(len(self.meet), timeout=20) if self.meet else None
        self.met = False

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        if dau.startswith("# Security review"):
            return RunResult(ok=True, text="không có phát hiện bảo mật", cost_usd=0.1)
        if dau.startswith("# Review"):
            return RunResult(ok=True, text="không có mục chặn", cost_usd=0.1)

        story_id = spec.env.get("AISEF_STORY_ID", "")
        scope = spec.env.get("AISEF_WRITE_SCOPE", "src").split(",")[0]
        with self.lock:
            self.stories.append(story_id)
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            if self.barrier is not None and story_id in self.meet:
                try:
                    self.barrier.wait()
                    self.met = True
                except threading.BrokenBarrierError:
                    pass  # tuần tự: ghi nhận bằng `met` = False
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


class TestRunOwnership(RunTestCase):
    def test_live_owner_blocks_recovery_across_processes(self):
        from aisef.control.worktree import run_ownership

        sid = "STORY-01-01"
        state = StateStore(self.artifacts)
        state.register(sid, "EPIC-01")
        state.transition(sid, StoryStatus.RUNNING)
        journal = JournalStore(self.artifacts)
        journal.record(sid, JEntry(step="attempt.started", attempt=1))
        manager = WorktreeManager(self.project)
        tree = manager.create(sid)
        marker = tree.path / "owner.txt"
        marker.write_text("active owner", encoding="utf-8")
        before = journal.path(sid).read_bytes()
        with run_ownership(self.project):
            proc = subprocess.run(
                [sys.executable, "-c",
                 "import sys; from aisef.phases.run import run_sprint; "
                 "r=run_sprint(sys.argv[1], None); "
                 "sys.exit(0 if 'another run owns' in r.error else 1)",
                 str(self.project)], cwd=ROOT, capture_output=True, timeout=20,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
        self.assertEqual(marker.read_text(encoding="utf-8"), "active owner")
        self.assertEqual(journal.path(sid).read_bytes(), before)
        self.assertEqual(state.load().stories[sid].state, StoryStatus.RUNNING)

    def test_lock_releases_after_exception_and_shares_worktree_identity(self):
        from aisef.control.worktree import RunOwnedError, run_ownership

        tree = WorktreeManager(self.project).create("STORY-01-01")
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            with run_ownership(self.project):
                with self.assertRaises(RunOwnedError):
                    with run_ownership(tree.path):
                        self.fail("worktree bypassed ownership")
                raise RuntimeError("interrupted")
        with run_ownership(tree.path):
            pass

    def test_entrypoint_retains_ownership_during_recovery(self):
        from aisef.control.worktree import RunOwnedError, run_ownership

        def recover(**kwargs):
            with self.assertRaises(RunOwnedError):
                with run_ownership(self.project):
                    self.fail("ownership released before recovery")
            raise RuntimeError("recovery interrupted")

        with patch("aisef.phases.run.reconcile_all", side_effect=recover):
            with self.assertRaisesRegex(RuntimeError, "recovery interrupted"):
                self.run_sprint(Agent())
        with run_ownership(self.project):
            pass

    def test_competing_entrypoints_do_not_reconcile_or_create_worktrees(self):
        from aisef._compat import flock_ex_nb, flock_un
        from aisef.phases.improve import improve

        lock_path = self.project / ".aisef" / "run.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as owner:
            flock_ex_nb(owner.fileno())
            try:
                for entry, module, kwargs in (
                    (run_sprint, "aisef.phases.run", {}),
                    (run_sprint, "aisef.phases.run", {"isolate": False}),
                    (run_verify_only, "aisef.phases.run", {"story_id": "STORY-01-01"}),
                    (improve, "aisef.phases.improve", {"epic_id": "EPIC-01"}),
                ):
                    with self.subTest(entry=entry.__name__, kwargs=kwargs):
                        with patch(module + ".WorktreeManager") as worktrees, \
                                patch(module + ".reconcile_all") as reconcile, \
                                patch(module + ".load_plan") as plan:
                            report = entry(self.project, Agent(), config=self.config(), **kwargs)
                        self.assertIn("another run owns", report.error)
                        worktrees.assert_not_called()
                        reconcile.assert_not_called()
                        plan.assert_not_called()
            finally:
                flock_un(owner.fileno())


class TestPlanLoading(RunTestCase):
    def test_reads_stories_and_waves(self):
        plan = load_plan(self.artifacts)
        self.assertEqual(len(plan.stories), 4)
        self.assertEqual(plan.waves["EPIC-01"][1], ["STORY-01-02", "STORY-01-03"])

    def test_missing_index_is_a_clear_error(self):
        (self.artifacts / "stories.index.json").unlink()
        self.assertIn("aisef plan", load_plan(self.artifacts).error)

    def test_broken_index(self):
        (self.artifacts / "stories.index.json").write_text("{ hỏng", encoding="utf-8")
        self.assertIn("corrupted", load_plan(self.artifacts).error)


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
        """Đợt 1 của EPIC-01 có hai story độc lập; chúng phải gặp nhau ở rào.

        Trước 2026-09-05 phép này đo chồng lấn 300 ms bằng đồng hồ: dưới
        tải, dựng worktree cho story thứ hai lâu hơn 300 ms và phép đổi màu
        dù bộ điều phối vẫn song song (P0-2, 1/33 lần). Rào không có đồng hồ.
        """
        agent = Agent(meet={"STORY-01-02", "STORY-01-03"})
        report = self.run_sprint(agent, only_epic="EPIC-01")
        self.assertTrue(agent.met, report.summary())
        self.assertGreaterEqual(agent.max_concurrent, 2, report.summary())

    def test_sequential_run_breaks_the_barrier(self):
        """Phép rào phải đỏ khi không song song — nếu không nó không đo gì."""
        agent = Agent(meet={"STORY-01-02", "STORY-01-03"})
        agent.barrier = threading.Barrier(2, timeout=1)
        self.run_sprint(agent, only_epic="EPIC-01", sequential=True)
        self.assertFalse(agent.met)

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
        self.assertIn("not in plan", self.run_sprint(Agent(), only_epic="EPIC-99").error)


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
        self.assertIn("write_scope", report.summary())


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
        raw = json.loads((self.artifacts / "stories.index.json").read_text(encoding="utf-8"))
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

    def test_story_qua_co_thi_chan_truoc_khi_goi_model(self):
        """ADR-004 R5: điểm cỡ vượt `story.max_complexity` → không tiêu đồng nào.

        Cổng `stories` đã chấm cùng phép kiểm; đây là lần chặn thứ hai, vì
        kế hoạch sửa được sau khi cổng ấy duyệt.
        """
        self.index_with(acceptance_criteria=[f"Then điều {i}" for i in range(20)])
        agent = Agent()
        self.run_sprint(agent)
        self.assertNotIn("STORY-01-01", agent.stories, "model không được gọi")
        rec = self.state().stories["STORY-01-01"]
        self.assertIs(rec.state, StoryStatus.BLOCKED)
        self.assertIn("story.max_complexity", rec.blocked_reason)
        self.assertIn("split by acceptance criteria", rec.blocked_reason)

    def test_story_xong_thi_ghi_bang_hieu_chuan_co_story(self):
        """Ngưỡng chỉ đáng tin khi có bảng đối chiếu điểm ↔ lượt thật."""
        from aisef.control import complexity

        self.run_sprint(Agent())
        rows = complexity.load_calibration(self.artifacts)
        self.assertIn("STORY-01-01", rows)
        row = rows["STORY-01-01"]
        self.assertEqual(row["threshold"], DEFAULTS["story.max_complexity"])
        self.assertIn("write_scope", row["components"])
        self.assertEqual(row["attempts"], 1)

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
        from aisef.control.journal import JournalStore

        return JournalStore(self.artifacts).read(sid)

    def test_story_xong_ghi_du_moc_toi_attempt_committed(self):
        self.run_sprint(Agent())
        steps = self.journal().steps()
        for moc in ("attempt.started", "worktree.created", "status.running",
                    "changes.detected", "candidate.frozen",
                    "verification.completed", "review.completed",
                    "merge.completed", "attempt.committed"):
            self.assertIn(moc, steps, steps)

    def test_ung_vien_dong_bang_truoc_khi_kiem(self):
        """ADR-004 R1: `candidate.frozen` đứng trước mọi bước kiểm — bằng
        chứng chỉ có nghĩa khi nó trỏ vào một bản cụ thể."""
        self.run_sprint(Agent())
        steps = self.journal().steps()
        self.assertLess(steps.index("candidate.frozen"),
                        steps.index("verification.completed"), steps)
        self.assertLess(steps.index("changes.detected"),
                        steps.index("candidate.frozen"), steps)
        self.assertNotIn("commit.created", steps)
        sha = self.journal().last("candidate.frozen").data.get("sha")
        self.assertTrue(sha, "mốc đóng băng phải mang SHA")

    def test_story_truot_dong_giao_dich_ngay_khong_no_gi(self):
        self.run_sprint(Agent(fail={"STORY-01-01"}))
        j = self.journal()
        self.assertIn("attempt.committed", j.steps())
        self.assertNotIn("merge.completed", j.steps())
        self.assertEqual(j.open_attempt(), 0)

    def test_tien_trinh_chet_giua_chung_thi_luot_sau_don_va_khong_de_running(self):
        """Mô phỏng đúng thứ đã xảy ra: tiến trình bị giết sau khi story
        chuyển sang `running`, để lại nhật ký dở và trạng thái kẹt."""
        from aisef.control.journal import Entry, JournalStore

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
        from aisef.control.journal import Entry, JournalStore

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


class TestDonWorktree(RunTestCase):
    """Worktree nằm trong cây dự án — công cụ của dự án nhìn thấy chúng.

    Lỗi 35, đo trên e9: `vitest` ở gốc dự án quét vào
    `.aisef/worktrees/STORY-01-04/` và nhặt test của story đang dở, rồi
    cổng trước triển khai báo "unit đỏ". Test không đỏ — nó đọc nhầm cây.
    `.gitignore` che được git, nhưng vitest/eslint/tsc không đọc nó khi
    tìm tệp.
    """

    def worktree(self, sid="STORY-01-01"):
        return self.project / ".aisef" / "worktrees" / sid

    def test_story_truot_khong_de_lai_thu_muc_trong_cay_du_an(self):
        self.run_sprint(Agent(fail={"STORY-01-01"}))
        self.assertFalse(self.worktree().exists(),
                         "worktree của story trượt phải được gỡ")

    def test_cong_viec_do_dang_van_con_trong_nhanh(self):
        """Gỡ thư mục không được làm mất công việc: nhánh giữ nó."""
        self.run_sprint(Agent(out_of_scope={"STORY-01-01"}))
        nhanh = subprocess.run(
            ["git", "branch", "--list", "story/STORY-01-01"],
            cwd=self.project, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
        self.assertIn("story/STORY-01-01", nhanh)

    def test_story_xong_cung_khong_de_lai_thu_muc(self):
        self.run_sprint(Agent())
        self.assertFalse(self.worktree().exists())


class TestIsolationOff(RunTestCase):
    def test_no_isolate_runs_in_the_project_itself(self):
        report = self.run_sprint(Agent(), only_epic="EPIC-02", isolate=False)
        self.assertTrue(report.ok, report.summary())
        self.assertTrue((self.project / "src/late/STORY-02-01.py").is_file())

    def test_isolation_requires_git(self):
        from aisef.kit.fetch import remove_tree

        remove_tree(self.project / ".git")   # `.git/objects` is read-only on Windows
        self.assertIn("git", self.run_sprint(Agent()).error)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestMergeDungRoiChayLai(RunTestCase):
    """Lỗi 42. `DONE` được ghi khi story qua cổng — **trước** bước merge.

    Merge đụng thì story đứng lại ở DONE-nhưng-chưa-merge. Lượt chạy sau
    thấy DONE và bỏ qua, nên công việc nằm mãi trên nhánh story: không ai
    đưa vào nhánh chính, không ai báo, và `aisef status` nói story xong.

    Gặp thật trên `par` khi merge STORY-02-01 đụng một tệp chưa theo dõi
    ở cây chính: story `XONG`, `main` không đổi, chạy lại báo "đã xong từ
    trước, bỏ qua".
    """

    def sinh_story_da_xong_nhung_chua_merge(self, sid="STORY-01-01"):
        """Dựng đúng hiện trạng ấy: nhánh story có việc, sổ ghi DONE, nhật
        ký **không** có `merge.completed`."""
        wt = WorktreeManager(self.project)
        w = wt.create(sid)
        # Ghi đúng trong `write_scope` của story, nếu không `commit_story`
        # không stage gì và nhánh rỗng — rồi merge báo "already up to date"
        # và phép thử đo nhầm chuyện khác.
        (Path(w.path) / "src" / "core").mkdir(parents=True, exist_ok=True)
        (Path(w.path) / "src" / "core" / "a.py").write_text("x = 1\n", encoding="utf-8")
        wt.commit_story(sid, f"{sid}: việc", paths=["src/core"])
        wt.remove(sid)

        j = JournalStore(self.artifacts)
        j.record(sid, JEntry(step="attempt.started", attempt=1))
        j.record(sid, JEntry(step="worktree.created", attempt=1))  # lượt thật luôn có
        sha = subprocess.run(["git", "rev-parse", wt.branch_for(sid)], cwd=self.project,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        j.record(sid, JEntry(step="candidate.frozen", attempt=1, data={"sha": sha}))
        j.record(sid, JEntry(step="verification.completed", attempt=1, data={"ok": True}))
        # Lượt chạy **kết thúc gọn** — không phải bị giết giữa chừng, nếu
        # không thì reconciler sẽ hoàn nguyên nó và ta đo nhầm chuyện khác.
        j.record(sid, JEntry(step="attempt.committed", attempt=1))

        st = StateStore(self.artifacts)
        st.register(sid, "EPIC-01", wave=1)
        for b in (StoryStatus.RUNNING, StoryStatus.VERIFYING, StoryStatus.DONE):
            st.transition(sid, b)
        return sid

    def head_co(self, path: str) -> bool:
        r = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", path],
                           cwd=self.project, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return bool(r.stdout.strip())

    def test_khong_bo_qua_story_da_xong_ma_chua_merge(self):
        self.sinh_story_da_xong_nhung_chua_merge()
        self.assertFalse(self.head_co("src/core/a.py"), "tiền đề: chưa có trên main")

        self.run_sprint(Agent(), only_epic="EPIC-01")

        self.assertTrue(self.head_co("src/core/a.py"),
                        "công việc phải được merge vào nhánh chính")

    def test_legacy_unbound_candidate_requires_reverification(self):
        sid = self.sinh_story_da_xong_nhung_chua_merge()
        path = JournalStore(self.artifacts).path(sid)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows = [row for row in rows if row["step"] not in
                ("candidate.frozen", "verification.completed")]
        rows.append({"step": "commit.created", "attempt": 1})
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        agent = Agent()
        result = self.run_sprint(agent, only_epic="EPIC-01")
        self.assertFalse(self.head_co("src/core/a.py"))
        self.assertFalse(result.ok)
        self.assertNotIn(sid, agent.stories)

    def test_verified_branch_drift_is_not_integrated(self):
        sid = self.sinh_story_da_xong_nhung_chua_merge()
        wm = WorktreeManager(self.project)
        wt = wm.create(sid, refresh=False)
        (wt.path / "src/core/a.py").write_text("unverified = True\n")
        wm.commit_story(sid, paths=["src/core"])
        result = self.run_sprint(Agent(), only_epic="EPIC-01")
        self.assertFalse(self.head_co("src/core/a.py"))
        self.assertFalse(result.ok)

    def test_verified_residual_is_not_committed_or_integrated(self):
        sid = self.sinh_story_da_xong_nhung_chua_merge()
        wm = WorktreeManager(self.project)
        wt = wm.create(sid, refresh=False)
        (wt.path / "src/core/a.py").write_text("unverified = True\n")
        result = self.run_sprint(Agent(), only_epic="EPIC-01")
        self.assertFalse(self.head_co("src/core/a.py"))
        self.assertFalse(result.ok)
        self.assertEqual((wt.path / "src/core/a.py").read_text(), "unverified = True\n")

    def test_khong_hien_thuc_lai_story_da_xong(self):
        """Chỉ merge lại, không chạy agent lần nữa — công việc đã có sẵn."""
        sid = self.sinh_story_da_xong_nhung_chua_merge()
        agent = Agent()
        self.run_sprint(agent, only_epic="EPIC-01")
        self.assertNotIn(sid, agent.stories)

    def test_da_merge_roi_thi_van_bo_qua(self):
        """Guard giả là guard bị gỡ: story đã merge không được đụng lại."""
        sid = self.sinh_story_da_xong_nhung_chua_merge()
        JournalStore(self.artifacts).record(
            sid, JEntry(step="merge.completed", attempt=1))
        r = self.run_sprint(Agent(), only_epic="EPIC-01")
        self.assertIn(sid, r.waves[0].skipped)


class TestDoneChiSauMerge(RunTestCase):
    """Bất biến G12: trong `sprint-status.json`, `done` không bao giờ đứng
    trước `merge.completed` của nhật ký."""

    def test_merge_dung_thi_verified_khong_phai_done(self):
        """Hai story cùng đợt cố ý chạm một tệp → merge story thứ hai đụng."""
        # STORY-01-02 (src/a) và STORY-01-03 (src/b) cùng đợt 2. Ép đụng bằng
        # cách để agent giả của 01-03 cũng ghi vào src/a/STORY-01-02.py.
        class Dung(Agent):
            def run(self, spec):
                r = super().run(spec)
                if spec.env.get("AISEF_STORY_ID") == "STORY-01-03":
                    p = Path(spec.workdir) / "src" / "a" / "STORY-01-02.py"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("# đụng\n", encoding="utf-8")
                return r
        # cho 01-03 quyền ghi src/a để guard `phạm vi ghi` không chặn trước.
        # Hai story **cùng đợt** (đợt 2 của INDEX) và cùng rẽ từ một gốc:
        # 01-02 merge trước, 01-03 mang cùng đường dẫn nội dung khác → đụng.
        idx = json.loads((self.artifacts / "stories.index.json").read_text(encoding="utf-8"))
        for st in idx["stories"]:
            if st["id"] == "STORY-01-03":
                st["write_scope"] = ["src/b", "src/a"]
        (self.artifacts / "stories.index.json").write_text(json.dumps(idx), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "ép đụng"], cwd=self.project, check=True)

        r = self.run_sprint(Dung(), only_epic="EPIC-01")
        st = self.state()
        self.assertIn("STORY-01-03", [w for wv in r.waves for w in wv.merge_conflicts])
        self.assertIs(st.stories["STORY-01-03"].state, StoryStatus.VERIFIED)
        self.assertIs(st.stories["STORY-01-02"].state, StoryStatus.DONE)

    def test_done_sau_merge_completed_theo_thu_tu_ghi(self):
        from aisef.control.journal import JournalStore
        self.run_sprint(Agent(), only_epic="EPIC-01")
        st = self.state()
        for sid, rec in st.stories.items():
            with self.subTest(story=sid):
                self.assertIs(rec.state, StoryStatus.DONE)
                j = JournalStore(self.artifacts).read(sid)
                self.assertTrue(j.merged(), f"{sid} done mà nhật ký chưa merge")

    def test_khong_cach_ly_thi_done_ngay(self):
        """`--no-isolate` không có bước merge → `done` ngay, không qua
        `verified`. Chỉ nhìn story đầu: ở chế độ này story sau thấy file
        chưa commit của story trước và trượt `phạm vi ghi` — hạn chế có
        sẵn của chạy không cách ly, không thuộc G12."""
        self.run_sprint(Agent(), only_epic="EPIC-01", isolate=False)
        self.assertIs(self.state().stories["STORY-01-01"].state, StoryStatus.DONE)


class TestVerifyOnly(RunTestCase):
    """ADR-004 R13 — lượt kiểm-lại trên ứng viên đã đóng băng.

    e9 STORY-01-07 (2026-09-06) trượt lượt 3 chỉ vì e2e nhạy tải máy; ứng
    viên `a60612e` đo lại 10/10 xanh, rà soát và bảo mật ở đúng SHA ấy đều ✅
    — mà harness chỉ biết "lượt mới = phiên developer mới", $10–15 để dựng
    lại thứ đã có. Ở đây "e2e nhạy tải" là một lệnh `sit` đọc tệp cờ ngoài
    kho: chưa có cờ → ✗, có cờ → ✅. Điều phải chứng minh: chỉ phép kiểm đỏ
    được chạy lại, model không bị gọi lại khi SHA không đổi, cổng vẫn chấm đủ,
    và lượt này không ăn vào `run.max_retries`.
    """

    SID = "STORY-01-01"

    def setUp(self):
        super().setUp()
        index = json.loads((self.artifacts / "stories.index.json").read_text(encoding="utf-8"))
        index["stories"][0]["verification_contract"] = ["unit", "sit"]
        (self.artifacts / "stories.index.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "hợp đồng sit"], cwd=self.project, check=True)
        self._co = tempfile.TemporaryDirectory()
        self.co = Path(self._co.name) / "xanh"
        # `test -f` is a POSIX builtin — on Windows the flag could never turn
        # green, so the half of every test after "tải máy đã hết" never ran.
        self.co_check = Path(self._co.name) / "co.py"
        self.co_check.write_text(
            "import os, sys\nsys.exit(0 if os.path.exists(sys.argv[1]) else 1)\n",
            encoding="utf-8")

    def tearDown(self):
        self._co.cleanup()
        super().tearDown()

    def cfg(self):
        # Không Docker: lệnh `sit` phải thấy tệp cờ trên máy này, và phép thử
        # không được đổi màu theo việc máy có daemon hay không.
        from aisef.clients.base import quote_command
        sit = quote_command([sys.executable, str(self.co_check), str(self.co)])
        return self.config(**{"verify.sit": sit, "sandbox.use_docker": False})

    def truot_vi_sit(self, agent):
        r = self.run_sprint(agent, only_epic="EPIC-01", config=self.cfg())
        self.assertFalse(r.ok, r.summary())
        gate = r.outcomes[0].attempts[-1].gate
        self.assertEqual([c.name for c in gate.failures], ["sit"], gate.summary())
        self.assertIs(self.state().stories[self.SID].state, StoryStatus.FAILED)
        return r

    def kiem_lai(self, agent):
        return run_verify_only(self.project, agent, story_id=self.SID, config=self.cfg())

    def evidence(self):
        return EvidenceStore(self.artifacts).read(self.SID)

    def journal(self):
        return JournalStore(self.artifacts).read(self.SID)

    def head_co(self, path: str) -> bool:
        r = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", path],
                           cwd=self.project, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return bool(r.stdout.strip())

    def test_chay_lai_dung_phep_kiem_do_giu_ra_soat_cung_sha_roi_merge(self):
        agent = Agent()
        self.truot_vi_sit(agent)
        n_dev, n_model = len(agent.stories), len(self.evidence().of(AGENT_RUN))

        self.co.write_text("", encoding="utf-8")          # "tải máy" đã hết
        r = self.kiem_lai(agent)

        self.assertTrue(r.ok, r.summary())
        self.assertIs(self.state().stories[self.SID].state, StoryStatus.DONE)
        self.assertTrue(self.head_co("src/core/STORY-01-01.py"), "phải merge vào nhánh chính")
        self.assertEqual(len(agent.stories), n_dev, "không có phiên developer mới")
        ev = self.evidence()
        self.assertEqual(len(ev.of(AGENT_RUN)), n_model,
                         "SHA không đổi: không gọi lại reviewer lẫn security")
        note = ev.last(NOTE, "verify-only")
        self.assertEqual(note.detail["reran"], ["qa:sit"])
        # `test:nop` (ADR-005 V3) giữ được: story không thêm tệp test là sự thật
        # của SHA, chạy lại cho cùng câu trả lời với giá $0.
        self.assertEqual(sorted(note.detail["kept"]),
                         ["lint", "qa:fake-tests", "review", "security", "test", "test:nop"])
        self.assertIn("attempt.committed", self.journal().steps())

    def test_ra_soat_o_sha_khac_thi_goi_lai_reviewer(self):
        agent = Agent()
        self.truot_vi_sit(agent)
        n_dev, n_model = len(agent.stories), len(self.evidence().of(AGENT_RUN))
        # Nhánh story tiến thêm một commit (sửa tay) → ứng viên mới, lời rà
        # soát cũ nói về bản khác.
        wt = WorktreeManager(self.project)
        w = wt.create(self.SID, refresh=False)
        (Path(w.path) / "src" / "core" / "sua.py").write_text("y = 2\n", encoding="utf-8")
        wt.commit_story(self.SID, "sửa tay", paths=["src/core"])
        wt.remove(self.SID)

        self.co.write_text("", encoding="utf-8")
        r = self.kiem_lai(agent)

        self.assertTrue(r.ok, r.summary())
        self.assertEqual(len(agent.stories), n_dev, "vẫn không có phiên developer")
        # Client giả không trả JSON nên mỗi vai rà soát tốn 2 lượt (R8 hỏi
        # lại một lần) — đếm theo vai, không đếm số lượt.
        moi = [e.name for e in self.evidence().of(AGENT_RUN)][n_model:]
        self.assertTrue(moi and all("-review" in n or "-security" in n for n in moi), moi)
        self.assertTrue(any("-review" in n for n in moi), "reviewer phải đọc lại bản mới")
        self.assertTrue(any("-security" in n for n in moi), "security phải đọc lại bản mới")
        note = self.evidence().last(NOTE, "verify-only")
        self.assertIn("review", note.detail["reran"])
        self.assertIn("security", note.detail["reran"])

    def test_tu_choi_khi_chua_co_ung_vien(self):
        r = self.kiem_lai(Agent())
        self.assertIn("no candidate to re-verify", r.error)
        self.assertNotIn(self.SID, self.state().stories, "từ chối trước khi chạm trạng thái")

    def test_tu_choi_story_da_xong(self):
        self.co.write_text("", encoding="utf-8")
        self.run_sprint(Agent(), only_epic="EPIC-01", config=self.cfg())
        self.assertIs(self.state().stories[self.SID].state, StoryStatus.DONE)
        r = self.kiem_lai(Agent())
        self.assertIn("already done", r.error)

    def test_truot_khong_tinh_vao_max_retries(self):
        agent = Agent()
        self.truot_vi_sit(agent)
        luot = self.state().stories[self.SID].attempts

        r = self.kiem_lai(agent)        # cờ vẫn chưa có: sit ✗ lần nữa

        self.assertFalse(r.ok, r.summary())
        rec = self.state().stories[self.SID]
        self.assertIs(rec.state, StoryStatus.FAILED)
        self.assertIn("re-verify", rec.blocked_reason)
        self.assertIn("sit", rec.blocked_reason)
        self.assertEqual(rec.attempts, luot, "kiểm lại không phải lượt developer")
        self.assertEqual(r.outcomes[0].quality_attempts, 0)
        self.assertEqual(len(agent.stories), 1)
        self.assertTrue(self.journal().last("candidate.frozen").data.get("verify_only"))
        self.assertFalse(self.journal().last("candidate.frozen").data.get("error"))

    def test_nhanh_chinh_tien_len_van_cham_dung_ung_vien_va_noi_ra(self):
        agent = Agent()
        self.truot_vi_sit(agent)
        sha_cu = self.journal().last("candidate.frozen").data["sha"]
        n_model = len(self.evidence().of(AGENT_RUN))
        (self.project / "khac.txt").write_text("main đi tiếp\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "main tiến lên"], cwd=self.project, check=True)

        self.co.write_text("", encoding="utf-8")
        r = self.kiem_lai(agent)

        self.assertTrue(r.ok, r.summary())
        self.assertEqual(self.journal().last("candidate.frozen").data["sha"], sha_cu,
                         "không mang nhánh chính vào: ứng viên là bản đã được chấm")
        self.assertEqual(len(self.evidence().of(AGENT_RUN)), n_model)
        note = self.evidence().last(NOTE, "verify-only")
        self.assertTrue(note.detail["main_ahead"], "phải nói ra là nhánh chính đã tiến lên")
        self.assertTrue(self.head_co("src/core/STORY-01-01.py"))
        self.assertTrue(self.head_co("khac.txt"), "merge không làm mất phần mới của main")


class TestVerifyOnlyRepeat(RunTestCase):
    """ADR-004 R13 `--repeat k` — tách "đỏ vì mã" khỏi "đỏ vì tải máy".

    Lỗi 22: e9 STORY-01-07 trượt lượt 3 vì `autosave.spec.ts:210` nhạy tải,
    đo lại 10/10 xanh — $28,76 cho một lượt developer dựng lại thứ đã có.
    Ở đây lệnh test giả in tên theo `pytest -v`; lần gọi thứ i cho `test_on`
    kết cục là chữ thứ i của mẫu (G xanh / R đỏ). Thứ tự gọi: baseline (1)
    → lượt developer (2, đỏ để story trượt và kiểm lại phải chạy lại test)
    → kiểm lại k lần (3…). Điều phải chứng minh: đổi kết cục giữa các lần
    → UNRUNNABLE "không ổn định" nêu tên (không phải trượt, không phải đạt);
    đỏ mọi lần → FAILED; xanh mọi lần → đạt; k = 1 không đổi gì.
    """

    SID = "STORY-01-01"

    def setUp(self):
        super().setUp()
        self._co = tempfile.TemporaryDirectory()
        self.co = Path(self._co.name)

    def tearDown(self):
        self._co.cleanup()
        super().tearDown()

    def lenh_test(self, mau: str) -> str:
        """Lệnh test giả, đếm số lần gọi. Viết bằng Python chứ không phải `sh`:
        Windows không có `sh`, nên cả lớp này chưa từng chạy ở đó."""
        from aisef.clients.base import quote_command

        script, dem = self.co / "test_gia.py", self.co / "n"
        script.write_text(
            "import pathlib, sys\n"
            f"mau = {mau!r}\n"
            f"dem = pathlib.Path({str(dem)!r})\n"
            "n = (int(dem.read_text()) if dem.exists() else 0) + 1\n"
            "dem.write_text(str(n))\n"
            "print('tests/test_x.py::test_lung PASSED')\n"
            "if mau[n - 1:n] == 'R':\n"
            "    print('tests/test_x.py::test_on FAILED')\n"
            "    sys.exit(1)\n"
            "print('tests/test_x.py::test_on PASSED')\n",
            encoding="utf-8",
        )
        return quote_command([sys.executable, str(script)])

    def cfg(self, mau: str):
        return self.config(**{"tools.test": self.lenh_test(mau), "sandbox.use_docker": False})

    def truot_vi_test(self, agent, cfg):
        r = self.run_sprint(agent, only_epic="EPIC-01", config=cfg)
        self.assertFalse(r.ok, r.summary())
        self.assertIn("test", [c.name for c in r.outcomes[0].attempts[-1].gate.failures])

    def kiem_lai(self, agent, cfg, k):
        return run_verify_only(self.project, agent, story_id=self.SID, config=cfg, repeat=k)

    def muc(self, r, ten):
        return next(c for c in r.outcomes[0].attempts[-1].gate.checks if c.name == ten)

    def evidence(self):
        return EvidenceStore(self.artifacts).read(self.SID)

    def test_do_mot_lan_xanh_hai_lan_la_khong_on_dinh_khong_phai_truot(self):
        agent, cfg = Agent(), self.cfg("GR" + "GGR")
        self.truot_vi_test(agent, cfg)
        # Ứng viên không đổi giữa lượt developer và kiểm lại (không có gì để
        # commit): lần test đỏ của lượt developer cũng mang SHA này — đếm phần thêm.
        sha = JournalStore(self.artifacts).read(self.SID).last("candidate.frozen").data["sha"]
        n_truoc = len([e for e in self.evidence().of(TOOL_RUN, "test") if e.detail.get("candidate") == sha])

        r = self.kiem_lai(agent, cfg, 3)

        self.assertFalse(r.ok, r.summary())
        m = self.muc(r, "test")
        self.assertIs(m.outcome, Outcome.UNRUNNABLE, m.detail)
        self.assertIn("unstable", m.detail)
        self.assertIn("tests/test_x.py::test_on", m.detail)
        self.assertNotIn("test_lung", m.detail, "test ổn định không bị nêu tên")
        bl = self.muc(r, "no baseline regression")
        self.assertIsNot(bl.outcome, Outcome.FAILED,
                         f"xanh ở baseline, đỏ ở lần cuối vì flaky — không phải làm đỏ: {bl.detail}")
        note = self.evidence().last(NOTE, "verify-only.repeat")
        self.assertEqual(note.detail["k"], 3)
        self.assertEqual(note.detail["flaky_ids"], ["tests/test_x.py::test_on"])
        self.assertEqual(note.detail["stable_red"], [])
        self.assertEqual(self.evidence().last(NOTE, "verify-only").detail["candidate"], sha)
        chay = [e for e in self.evidence().of(TOOL_RUN, "test") if e.detail.get("candidate") == sha]
        self.assertEqual(len(chay) - n_truoc, 3, "k lần tool_run test, mỗi lần mang candidate")
        self.assertEqual(len(agent.stories), 1, "không có phiên developer")
        self.assertIn("test", self.state().stories[self.SID].blocked_reason)

    def test_do_moi_lan_la_truot_that(self):
        agent, cfg = Agent(), self.cfg("GR" + "RRR")
        self.truot_vi_test(agent, cfg)

        r = self.kiem_lai(agent, cfg, 3)

        self.assertFalse(r.ok)
        m = self.muc(r, "test")
        self.assertIs(m.outcome, Outcome.FAILED, m.detail)
        note = self.evidence().last(NOTE, "verify-only.repeat")
        self.assertEqual(note.detail["stable_red"], ["tests/test_x.py::test_on"])
        self.assertEqual(note.detail["flaky_ids"], [])

    def test_xanh_moi_lan_la_dat(self):
        agent, cfg = Agent(), self.cfg("GR" + "GGG")
        self.truot_vi_test(agent, cfg)

        r = self.kiem_lai(agent, cfg, 3)

        self.assertTrue(r.ok, r.summary())
        self.assertIs(self.state().stories[self.SID].state, StoryStatus.DONE)
        note = self.evidence().last(NOTE, "verify-only.repeat")
        self.assertTrue(note.ok)
        self.assertEqual(note.detail["flaky_ids"], [])

    def test_k_bang_1_la_hanh_vi_cu(self):
        agent, cfg = Agent(), self.cfg("GR" + "G")
        self.truot_vi_test(agent, cfg)

        r = self.kiem_lai(agent, cfg, 1)

        self.assertTrue(r.ok, r.summary())
        self.assertIsNone(self.evidence().last(NOTE, "verify-only.repeat"))


class TestSoSachHanhViTuoiSauDotChay(unittest.TestCase):
    """Lỗi 129 (todo-cli 2026-09-13). Sổ hành vi là **phép chiếu** từ bằng
    chứng: mọi người dùng nó đều dựng lại, nên không có gì phụ thuộc vào tệp.
    Nhưng tệp là artifact người đọc và commit vào git, và sau đợt chạy nó nói
    mọi hành vi đều là `gap` trong khi phép chiếu có 34 verified, 5 reopened.
    Một artifact nói ngược lại chính cái máy đang thấy còn tệ hơn không có."""

    def test_ghi_lai_so_sach_cuoi_dot(self):
        import inspect
        from aisef.phases import run as run_mod

        src = inspect.getsource(run_mod._run_sprint_owned)
        i_ghi = src.index("led.write(artifact_root)")
        i_xong = src.index('f"sprint DONE')
        self.assertLess(i_ghi, i_xong, "phải ghi trước khi báo xong")
        self.assertIn("ledger_mod.build(artifact_root)", src,
                      "phải dựng lại từ bằng chứng, không chép sổ cũ")
        self.assertIn("except OSError", src,
                      "thư mục artifact chỉ đọc không được làm sập cả đợt chạy")
