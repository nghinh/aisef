"""Một lượt chạy story là một giao dịch — nhật ký và hoà giải.

Mọi ca ở đây là một chuyện **đã xảy ra thật** trên e9: tiến trình bị
giết để lại `running` vĩnh viễn, worktree merge xong mà sổ vẫn ghi
`failed`, và chạy lại một story đã merge thì chỉ thấy diff rỗng rồi thử
mù cho tới hết hạn mức.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.journal import (  # noqa: E402
    Journal,
    ABORTED,
    RECONCILED,
    STEPS,
    Entry,
    JournalStore,
    StoryRunTransaction,
    reconcile_all,
    reconcile_story,
)
from aisef.control.state import StateStore, StoryStatus  # noqa: E402


class JournalTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = JournalStore(self.root)
        self.state = StateStore(self.root)
        self.state.register("STORY-01-01", "EPIC-01", wave=1)

    def tearDown(self):
        self._tmp.cleanup()

    def rec(self, step, attempt=1, **data):
        return self.store.record("STORY-01-01", Entry(step=step, attempt=attempt, data=data))

    def status(self):
        return self.state.load().stories["STORY-01-01"].state

    def to(self, *states):
        for s in states:
            self.state.transition("STORY-01-01", s)


class TestJournalStore(JournalTestCase):
    def test_seq_do_file_quyet_dinh(self):
        a, b = self.rec("attempt.started"), self.rec("worktree.created")
        self.assertEqual((a.seq, b.seq), (1, 2))

    def test_dong_hong_khong_lam_mat_ca_nhat_ky(self):
        self.rec("attempt.started")
        with self.store.path("STORY-01-01").open("a", encoding="utf-8") as fh:
            fh.write("{ không phải json\n")
        self.rec("status.running")
        self.assertEqual(
            self.store.read("STORY-01-01").steps(),
            ["attempt.started", "status.running"],
        )

    def test_moc_theo_dung_hop_dong(self):
        """`STEPS` là hợp đồng: đọc nhật ký rồi so với nó là biết lượt
        chạy dừng ở đâu."""
        self.assertEqual(STEPS[0], "attempt.started")
        self.assertEqual(STEPS[-1], "attempt.committed")
        self.assertIn("merge.completed", STEPS)


class TestTransaction(JournalTestCase):
    def test_ket_thuc_binh_thuong_thi_dong_giao_dich(self):
        with StoryRunTransaction("STORY-01-01", artifact_root=self.root) as tx:
            tx.record("status.running")
            tx.commit()
        j = self.store.read("STORY-01-01")
        self.assertEqual(j.open_attempt(), 0)
        self.assertNotIn(ABORTED, j.steps())

    def test_loi_giua_chung_thi_ghi_lai_va_khong_nuot_loi(self):
        with self.assertRaises(RuntimeError):
            with StoryRunTransaction("STORY-01-01", artifact_root=self.root) as tx:
                tx.record("status.running")
                raise RuntimeError("agent chết")
        j = self.store.read("STORY-01-01")
        self.assertIn(ABORTED, j.steps())
        self.assertIn("agent chết", j.last(ABORTED).data["reason"])

    def test_luot_do_duoc_nhan_ra(self):
        with StoryRunTransaction("STORY-01-01", artifact_root=self.root):
            pass  # thoát mà không commit
        # `attempt.aborted` đóng lượt lại
        self.assertEqual(self.store.read("STORY-01-01").open_attempt(), 0)

        self.rec("attempt.started", attempt=2)
        self.assertEqual(self.store.read("STORY-01-01").open_attempt(), 2)


class TestReconcile(JournalTestCase):
    def kwargs(self, worktrees=None):
        return dict(artifact_root=self.root, state=self.state, worktrees=worktrees)

    def test_tien_trinh_chet_thi_khong_de_running_vinh_vien(self):
        """Đã xảy ra: `aisef status` báo `running` mãi, không lệnh nào gỡ."""
        self.rec("attempt.started")
        self.rec("status.running")
        self.to(StoryStatus.RUNNING)

        r = reconcile_story("STORY-01-01", **self.kwargs())
        self.assertIsNotNone(r)
        self.assertEqual(r.action, "undo")
        self.assertIs(self.status(), StoryStatus.PENDING)

    def test_merge_xong_thi_trang_thai_phai_duoi_kip(self):
        """Đã xảy ra: worktree merge vào nhánh chính, wave sau khởi động,
        mà sổ vẫn ghi `failed` và chi phí lượt ấy không vào đâu cả."""
        self.rec("attempt.started")
        self.rec("merge.completed")
        self.to(StoryStatus.RUNNING, StoryStatus.FAILED)

        r = reconcile_story("STORY-01-01", **self.kwargs())
        self.assertEqual(r.action, "roll-forward")
        self.assertIs(self.status(), StoryStatus.DONE)

    def test_khong_gia_vo_hoan_nguyen_thu_da_merge(self):
        """Merge là mốc không quay lại được. Hoà giải phải đi tiếp, không
        được đưa story về `pending` để chạy lại trên diff rỗng."""
        self.rec("attempt.started")
        self.rec("merge.completed")
        self.to(StoryStatus.RUNNING)
        reconcile_story("STORY-01-01", **self.kwargs())
        self.assertIs(self.status(), StoryStatus.DONE)

    def test_chay_lai_story_da_merge_thi_nhan_ra_da_xong(self):
        """Không nhận ra thì worktree mới rẽ từ nhánh đã chứa sẵn công
        việc: diff rỗng, người rà soát nói "không có gì để rà", story thử
        mù cho tới hết hạn mức."""
        self.rec("attempt.started")
        self.rec("merge.completed")
        self.rec("attempt.committed")
        self.to(StoryStatus.RUNNING, StoryStatus.FAILED)

        reconcile_all(**self.kwargs())
        self.assertIs(self.status(), StoryStatus.DONE,
                      "story đã merge phải được nhận là xong, không chạy lại")

    def test_story_binh_thuong_khong_bi_dung_toi(self):
        self.rec("attempt.started")
        self.rec("merge.completed")
        self.rec("attempt.committed")
        self.to(StoryStatus.RUNNING, StoryStatus.VERIFYING, StoryStatus.DONE)
        self.assertEqual(reconcile_all(**self.kwargs()), [])
        self.assertIs(self.status(), StoryStatus.DONE)

    def test_khong_co_nhat_ky_thi_khong_lam_gi(self):
        self.assertEqual(reconcile_all(**self.kwargs()), [])

    def test_hoa_giai_duoc_ghi_lai(self):
        """Harness vừa sửa trạng thái của story thì phải nói ra, không
        nuốt — đúng bài học của `except TransitionError: pass`."""
        self.rec("attempt.started")
        self.to(StoryStatus.RUNNING)
        reconcile_story("STORY-01-01", **self.kwargs())
        self.assertIn(RECONCILED, self.store.read("STORY-01-01").steps())

    def test_worktree_duoc_don_nhung_nhanh_giu_lai(self):
        """Commit trong nhánh là công việc thật — dọn thư mục không được
        làm nó biến mất."""
        goi = []

        class Worktrees:
            def remove(self, sid, delete_branch=False):
                goi.append((sid, delete_branch))

        self.rec("attempt.started")
        self.to(StoryStatus.RUNNING)
        reconcile_story("STORY-01-01", **self.kwargs(worktrees=Worktrees()))
        self.assertEqual(goi, [("STORY-01-01", False)])


class TestCrashRecovery(JournalTestCase):
    """v0.4.1: giết giữa story → state đúng, evidence còn nguyên."""

    def test_evidence_survives_crash(self):
        """JSONL append-only nên sự kiện đã ghi không mất khi tiến trình chết."""
        from aisef.harness.observe import EvidenceStore, Event, TOOL_RUN
        ev = EvidenceStore(self.root)
        ev.record("STORY-01-01", Event(kind=TOOL_RUN, name="test", ok=True))
        self.rec("attempt.started")
        self.to(StoryStatus.RUNNING)
        # "crash" — tiến trình chết, reconcile dọn
        reconcile_all(artifact_root=self.root, state=self.state)
        self.assertIs(self.status(), StoryStatus.PENDING)
        # evidence vẫn còn
        self.assertEqual(len(ev.read("STORY-01-01").of(TOOL_RUN)), 1)

    def test_candidate_sha_survives_reconcile(self):
        """Candidate SHA ghi trước crash phải còn trong nhật ký sau reconcile."""
        self.rec("attempt.started")
        self.rec("candidate.frozen", sha="abc123")
        self.to(StoryStatus.RUNNING)
        reconcile_all(artifact_root=self.root, state=self.state)
        j = self.store.read("STORY-01-01")
        shas = [e.data.get("sha") for e in j.entries if e.step == "candidate.frozen"]
        self.assertIn("abc123", shas)


class TestJournalIsMachineReadable(JournalTestCase):
    def test_moi_dong_la_json_co_du_truong(self):
        self.rec("worktree.created", path="/tmp/x")
        raw = json.loads(self.store.path("STORY-01-01").read_text().splitlines()[0])
        self.assertEqual(
            sorted(raw), ["at", "attempt", "data", "seq", "step", "undo"]
        )


if __name__ == "__main__":
    unittest.main()


class TestCanMerge(unittest.TestCase):
    """`DONE` ghi lúc qua cổng, trước merge — riêng trạng thái không trả
    lời được "code đã lên nhánh chính chưa". Nhật ký thì trả lời được."""

    def journal(self, *steps):
        j = Journal(story_id="S-01")
        for i, s in enumerate(steps, 1):
            j.entries.append(Entry(step=s, attempt=1, seq=i))
        return j

    def test_co_worktree_ma_chua_merge_thi_can_merge(self):
        self.assertTrue(self.journal(
            "attempt.started", "worktree.created", "candidate.frozen", "attempt.committed"
        ).needs_merge)

    def test_da_merge_thi_khong(self):
        self.assertFalse(self.journal(
            "attempt.started", "worktree.created", "merge.completed", "attempt.committed"
        ).needs_merge)

    def test_chay_thang_trong_du_an_thi_khong_co_buoc_merge(self):
        """`--no-isolate`: không có worktree, không có gì để merge."""
        self.assertFalse(self.journal("attempt.started", "attempt.committed").needs_merge)

    def test_nhat_ky_trong_thi_khong(self):
        self.assertFalse(Journal(story_id="S-01").needs_merge)

    def test_nhat_ky_cu_thieu_worktree_created_nhung_co_commit_created(self):
        """`commit.created` là **tên cũ** của mốc chốt bản (ADR-004 R1 đổi
        thành `candidate.frozen`); nó chỉ xảy ra trong worktree, nên nhật ký
        đã ghi trên đĩa vẫn phải đọc ra "còn nợ merge"."""
        self.assertTrue(self.journal("attempt.started", "commit.created",
                                     "attempt.committed").needs_merge)
