"""Ứng viên đóng băng (ADR-004 R1) — bằng chứng phải trỏ vào một bản.

Không có SHA thì câu "test này chạy trên mã nào" không có câu trả lời, và
"stale" không định nghĩa được: cổng vẫn chấm đạt bằng số liệu của mã đã bị
sửa sau đó. Bốn chỗ được kiểm ở đây: nhật ký (thứ tự mốc), bằng chứng (lọc
theo bản), cổng (mục *bằng chứng đúng candidate*), và phiên rà soát (đọc
đúng bản đã đóng băng, không tạo bản mới).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.control.gate import evaluate  # noqa: E402
from aisdlc.control.journal import STEPS, JournalStore  # noqa: E402
from aisdlc.control.normalize import Story  # noqa: E402
from aisdlc.control.outcome import Outcome  # noqa: E402
from aisdlc.harness.guardrails import head_sha  # noqa: E402
from aisdlc.harness.observe import AGENT_RUN, TOOL_RUN, EvidenceStore  # noqa: E402
from aisdlc.phases.implement import implement_story  # noqa: E402

CANDIDATE = "bằng chứng đúng candidate"


class TestJournalOrder(unittest.TestCase):
    """Mốc đóng băng đứng trước mọi bước kiểm — đó là cả ý nghĩa của nó."""

    def test_candidate_frozen_thay_commit_created(self):
        self.assertIn("candidate.frozen", STEPS)
        self.assertNotIn("commit.created", STEPS)

    def test_thu_tu_moc(self):
        self.assertEqual(STEPS, (
            "attempt.started", "worktree.created", "status.running",
            "changes.detected", "candidate.frozen", "verification.completed",
            "review.completed", "merge.completed", "attempt.committed",
        ))

    def test_dong_bang_truoc_khi_kiem(self):
        self.assertLess(STEPS.index("candidate.frozen"),
                        STEPS.index("verification.completed"))
        self.assertLess(STEPS.index("candidate.frozen"), STEPS.index("review.completed"))


class TestEvidenceCandidate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_kho_dong_dau_ban_vao_moi_su_kien(self):
        EvidenceStore(self.root, candidate="aaa").tool_run("S-01", "test", ok=True)
        ev = EvidenceStore(self.root).read("S-01")
        self.assertEqual(ev.last(TOOL_RUN, "test").detail["candidate"], "aaa")
        self.assertEqual(ev.candidate, "aaa")

    def test_candidate_la_ban_moi_nhat(self):
        EvidenceStore(self.root, candidate="aaa").tool_run("S-01", "test", ok=True)
        EvidenceStore(self.root, candidate="bbb").tool_run("S-01", "test", ok=True)
        self.assertEqual(EvidenceStore(self.root).read("S-01").candidate, "bbb")

    def test_for_candidate_bo_ban_khac_giu_su_kien_khong_khai(self):
        EvidenceStore(self.root, candidate="aaa").tool_run("S-01", "test", ok=True)
        EvidenceStore(self.root, candidate="bbb").tool_run("S-01", "lint", ok=True)
        EvidenceStore(self.root).file_change("S-01", "src/a.py")   # guard ghi: không khai bản

        loc = EvidenceStore(self.root).read("S-01").for_candidate("bbb")
        self.assertIsNone(loc.last(TOOL_RUN, "test"), "phép kiểm ở bản khác phải bị bỏ")
        self.assertIsNotNone(loc.last(TOOL_RUN, "lint"))
        self.assertEqual(len(loc.of("file_change")), 1, "sự kiện không khai bản thì giữ")


class GateCandidateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def xanh(self, sha: str):
        store = EvidenceStore(self.root, candidate=sha)
        store.file_change("S-01", "src/a.py")
        store.tool_run("S-01", "test", ok=True)
        store.tool_run("S-01", "lint", ok=True)

    def gate(self, candidate: str = ""):
        return evaluate(
            "S-01", EvidenceStore(self.root).read("S-01"),
            changed=["src/a.py"], write_scope=["src"], screens=[],
            review_blocking=[], candidate=candidate,
        )

    def muc(self, gate):
        return next(c for c in gate.checks if c.name == CANDIDATE)


class TestGateCandidate(GateCandidateTestCase):
    def test_cung_ban_thi_dat(self):
        self.xanh("aaa")
        g = self.gate("aaa")
        self.assertIs(self.muc(g).outcome, Outcome.PASSED)
        self.assertTrue(g.passed, g.summary())

    def test_ban_khac_thi_stale_va_chan_cong(self):
        self.xanh("aaa")
        g = self.gate("bbb")
        self.assertIs(self.muc(g).outcome, Outcome.UNRUNNABLE)
        self.assertIn("stale", self.muc(g).detail)
        self.assertIn("aaa", self.muc(g).detail)
        self.assertFalse(g.passed)

    def test_stale_khong_bi_ke_thanh_test_do(self):
        """Hai lỗi khác nhau, hai cách sửa khác nhau — không được gộp."""
        self.xanh("aaa")
        g = self.gate("bbb")
        test = next(c for c in g.checks if c.name == "test")
        self.assertNotIn("đỏ", test.detail)
        self.assertIn("chưa", test.detail.lower())

    def test_luot_truoc_o_ban_cu_khong_lam_luot_sau_stale(self):
        """Chạy lại phép kiểm ở bản mới là đủ: lịch sử không phải nợ."""
        self.xanh("aaa")
        self.xanh("bbb")
        g = self.gate("bbb")
        self.assertIs(self.muc(g).outcome, Outcome.PASSED)
        self.assertTrue(g.passed, g.summary())

    def test_khong_truyen_candidate_thi_khong_kiem(self):
        """Test cũ, chạy tay, nhật ký cũ — không kiểm, và nói rõ là không."""
        self.xanh("aaa")
        g = self.gate()
        self.assertIs(self.muc(g).outcome, Outcome.NOT_APPLICABLE)
        self.assertTrue(g.passed, g.summary())


class Client(ClientAdapter):
    """Agent giả: viết code, rồi rà soát theo kịch bản.

    ``review_commits`` cho phiên rà soát tạo một commit — đúng lỗ hổng mà
    hoàn nguyên cây không bịt được.
    """

    id = "scripted"

    def __init__(self, *, review_commits: bool = False):
        self.review_commits = review_commits
        self.calls: list[str] = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        if dau.startswith("# Rà soát bảo mật"):
            self.calls.append("security")
            return RunResult(ok=True, text="không có phát hiện bảo mật", cost_usd=0.1)
        if dau.startswith("# Rà soát"):
            self.calls.append("review")
            if self.review_commits:
                d = Path(spec.workdir)
                (d / "src" / "reviewer.py").write_text("x = 2\n", encoding="utf-8")
                subprocess.run(["git", "add", "src"], cwd=d, check=False)
                subprocess.run(["git", "commit", "-qm", "reviewer"], cwd=d, check=False)
            return RunResult(ok=True, text="không có mục chặn", cost_usd=0.1)
        self.calls.append("develop")
        p = Path(spec.workdir) / "src" / "a.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n", encoding="utf-8")
        return RunResult(ok=True, text="xong", cost_usd=1.0)


class WorktreeCase(unittest.TestCase):
    """Dự án git thật + worktree thật — đóng băng là một commit thật."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        for cmd in (["git", "init", "-q"],
                    ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.project, check=True)
        (self.project / "goc.txt").write_text("goc\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=self.project, check=True)
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        self.work = self.project / ".aisdlc" / "worktrees" / "STORY-01-01"
        subprocess.run(["git", "worktree", "add", "-q", str(self.work), "-b", "story/x"],
                       cwd=self.project, check=True)
        self.story = Story(
            id="STORY-01-01", epic_id="EPIC-01", title="Tạo ghi chú",
            acceptance_criteria=["ghi chú mới xuất hiện"], covers=["FR-1"],
            write_scope=["src"],
        )

    def tearDown(self):
        subprocess.run(["git", "worktree", "remove", "--force", str(self.work)],
                       cwd=self.project, check=False)
        self._tmp.cleanup()

    def implement(self, client):
        return implement_story(
            self.story, project=self.project, workdir=self.work,
            artifact_root=self.artifacts, client=client,
            config=Config({**DEFAULTS, "tools.test": "true", "tools.lint": "true",
                           "run.max_retries": 0}),
        )

    def evidence(self):
        return EvidenceStore(self.artifacts).read(self.story.id)

    def journal(self):
        return JournalStore(self.artifacts).read(self.story.id)


class TestFreeze(WorktreeCase):
    def test_ung_vien_duoc_chot_ngay_sau_phien_developer(self):
        out = self.implement(Client())
        sha = out.attempts[-1].candidate
        self.assertTrue(sha, out.summary())
        self.assertEqual(sha, head_sha(self.work), "ứng viên phải là HEAD của worktree")
        self.assertEqual(
            subprocess.run(["git", "status", "--porcelain"], cwd=self.work,
                           capture_output=True, text=True).stdout.strip(),
            "", "đóng băng nghĩa là không còn gì chưa commit",
        )

    def test_moc_moi_khong_lam_ho_so_giao_dich_bi_ho(self):
        """Số hiệu lượt của mốc mới phải là của giao dịch đang mở, nếu
        không `open_attempt()` để lại một lượt "chưa đóng" và lần chạy sau
        đi dọn một story đã xong."""
        from aisdlc.control.journal import StoryRunTransaction

        with StoryRunTransaction(self.story.id, artifact_root=self.artifacts) as tx:
            self.implement(Client())
            tx.commit()
        j = self.journal()
        self.assertEqual(j.open_attempt(), 0, j.steps())
        self.assertEqual(j.last("candidate.frozen").attempt, 1)

    def test_nhat_ky_ghi_moc_dong_bang_kem_sha(self):
        out = self.implement(Client())
        steps = self.journal().steps()
        self.assertLess(steps.index("changes.detected"), steps.index("candidate.frozen"))
        self.assertEqual(self.journal().last("candidate.frozen").data["sha"],
                         out.attempts[-1].candidate)

    def test_bang_chung_sau_dong_bang_mang_ban(self):
        out = self.implement(Client())
        sha = out.attempts[-1].candidate
        ev = self.evidence()
        for name in ("test", "lint", "qa:fake-tests", "review", "security"):
            got = ev.last(TOOL_RUN, name)
            self.assertIsNotNone(got, name)
            self.assertEqual(got.detail.get("candidate"), sha, name)
        for e in ev.of(AGENT_RUN):
            if e.name.endswith(("-review", "-security")):
                self.assertEqual(e.detail.get("candidate"), sha, e.name)

    def test_phien_developer_khong_gan_ban(self):
        """Nó chạy **trước** khi có ứng viên — gán bản là nói dối về thứ tự."""
        self.implement(Client())
        dev = [e for e in self.evidence().of(AGENT_RUN)
               if not e.name.endswith(("-review", "-security"))]
        self.assertTrue(dev)
        self.assertFalse(dev[0].detail.get("candidate"))

    def test_cong_cham_o_dung_ban_va_khong_stale(self):
        out = self.implement(Client())
        muc = next(c for c in out.attempts[-1].gate.checks if c.name == CANDIDATE)
        self.assertIs(muc.outcome, Outcome.PASSED, out.summary())


class TestReviewerDoiUngVien(WorktreeCase):
    """Hoàn nguyên cây không thấy một `git commit` — nên HEAD phải được so."""

    def test_ra_soat_tao_commit_thi_luot_khong_duoc_tinh(self):
        out = self.implement(Client(review_commits=True))
        self.assertFalse(out.done, out.summary())
        finding = " ".join(out.attempts[-1].review_findings)
        self.assertIn("ứng viên đổi", finding)
        got = self.evidence().last(TOOL_RUN, "review:candidate")
        self.assertIsNotNone(got, "phải ghi bằng chứng lượt rà soát không tính")
        self.assertFalse(got.ok)
        self.assertEqual(got.detail["expected"], out.attempts[-1].candidate)


class TestHopQuyC8(WorktreeCase):
    """C8 tất định: chạy được trong unit test, không gọi model, $0."""

    def test_c8_bat_duoc_bang_chung_stale(self):
        from tests.conformance import _runner as R

        r = R.probe_c8(self.project, self.work)
        self.assertTrue(r.passed, r.detail)
        self.assertEqual(r.cost_usd, 0.0)
        self.assertIn("stale", r.detail + " ")


class TestQaCandidate(unittest.TestCase):
    def test_run_suite_ghi_ban_cua_du_an(self):
        from aisdlc.phases.qa import run_suite

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            for cmd in (["git", "init", "-q"],
                        ["git", "config", "user.email", "t@t"],
                        ["git", "config", "user.name", "t"]):
                subprocess.run(cmd, cwd=project, check=True)
            (project / "a.txt").write_text("a\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=project, check=True)
            subprocess.run(["git", "commit", "-qm", "goc"], cwd=project, check=True)
            root = project / "_bmad-output"

            rep = run_suite(project, config=Config({**DEFAULTS, "verify.unit": "true"}),
                            only=["unit"], has_ui=False, story_id="S-01",
                            artifact_root=root)
            self.assertEqual(rep.candidate, head_sha(project))
            got = EvidenceStore(root).read("S-01").last(TOOL_RUN, "qa:unit")
            self.assertEqual(got.detail.get("candidate"), rep.candidate)


class TestReportCandidate(unittest.TestCase):
    def test_bao_cao_in_sha_bay_ky_tu(self):
        from aisdlc.phases import report as report_mod

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            root = project / "_bmad-output"
            sha = "0123456789abcdef0123456789abcdef01234567"
            EvidenceStore(root, candidate=sha).tool_run("STORY-01-01", "test", ok=True)
            rep = report_mod.build(project)
            self.assertEqual(rep.stories[0]["candidate"], sha[:7])
            self.assertIn("| Candidate |", rep.markdown())
            self.assertIn(sha[:7], rep.markdown())


if __name__ == "__main__":
    unittest.main()
