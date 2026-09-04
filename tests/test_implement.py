"""Vòng đời một story — thử lại, chặn, và phân biệt hai loại thất bại.

Client giả đóng vai agent: nó "viết code" bằng cách ghi file trong phạm vi
(hoặc cố tình ra ngoài), và trả lời rà soát theo kịch bản. Nhờ vậy kiểm
được đúng phần logic điều phối — cái quyết định story xong, thử lại hay bị
chặn — mà không phụ thuộc model.
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
from aisdlc.control.normalize import Story, parse_architecture_file  # noqa: E402
from aisdlc.harness.guardrails import (  # noqa: E402
    ENV_BASE_REF,
    ENV_STORY_ID,
    ENV_WRITE_SCOPE,
)
from aisdlc.harness.observe import AGENT_RUN, EvidenceStore  # noqa: E402
from aisdlc.phases.implement import (  # noqa: E402
    blocking_findings,
    build_context,
    implement_story,
    is_infrastructure_error,
)

FIX = ROOT / "tests" / "fixtures" / "bmad"


class ScriptedClient(ClientAdapter):
    """Agent giả: mỗi lượt viết code theo kịch bản, rồi rà soát theo kịch bản."""

    id = "scripted"

    def __init__(self, *, writes=("src/a.py",), review="không có mục chặn",
                 fail_first=0, fail_error="api_error"):
        self.writes = list(writes)
        self.review = review
        self.review_envs: list[dict] = []
        self.review_prompts: list[str] = []
        self.fail_first = fail_first
        self.fail_error = fail_error
        self.calls: list[str] = []
        self.envs: list[dict] = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        is_review = "Rà soát" in spec.prompt
        self.calls.append("review" if is_review else "develop")
        (self.review_envs if is_review else self.envs).append(dict(spec.env))
        if is_review:
            self.review_prompts.append(spec.prompt)

        if self.fail_first > 0 and not is_review:
            self.fail_first -= 1
            return RunResult(ok=False, error=self.fail_error, cost_usd=0.2)

        if is_review:
            return RunResult(ok=True, text=self.review, cost_usd=0.3)

        for rel in self.writes:
            path = Path(spec.workdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            # File test thì viết như một file test — nội dung quyết định
            # phép kiểm "test giả" có bắt được hay không.
            body = "def test_x():\n    pass\n" if "test_" in path.name else "x = 1\n"
            path.write_text(body, encoding="utf-8")
        return RunResult(ok=True, text="xong", cost_usd=1.0)


class ImplementTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        self.story = Story(
            id="STORY-01-01",
            epic_id="EPIC-01",
            title="Tạo ghi chú",
            acceptance_criteria=["ghi chú mới xuất hiện trong danh sách"],
            covers=["FR-1"],
            write_scope=["src"],
        )

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        return Config({
            **DEFAULTS,
            "tools.test": "true",
            "tools.lint": "true",
            "run.max_retries": 1,
            **over,
        })

    def implement(self, client, **kw):
        return implement_story(
            self.story, project=self.project, artifact_root=self.artifacts,
            client=client, config=kw.pop("config", self.config()), **kw,
        )


class TestHappyPath(ImplementTestCase):
    def test_story_passes_in_one_attempt(self):
        out = self.implement(ScriptedClient())
        self.assertTrue(out.done, out.summary())
        self.assertEqual(len(out.attempts), 1)

    def test_developer_then_reviewer(self):
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(c.calls, ["develop", "review"])

    def test_cong_nhin_thay_cong_viec_agent_da_commit(self):
        """Agent commit trong worktree thì ba cổng vẫn phải thấy diff.

        Không có mốc rẽ nhánh, `changed_files` so với HEAD và trả rỗng —
        phạm vi ghi đạt vô điều kiện, test-thật không kiểm gì, người rà
        soát nhận diff rỗng rồi phải mò cả repo.
        """
        for cmd in (
            ["git", "config", "user.email", "t@t"],
            ["git", "config", "user.name", "t"],
        ):
            subprocess.run(cmd, cwd=self.project, check=True)
        (self.project / "goc.txt").write_text("goc", encoding="utf-8")
        subprocess.run(["git", "add", "goc.txt"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=self.project, check=True)

        work = self.project / ".aisdlc" / "worktrees" / "STORY-01-01"
        subprocess.run(
            ["git", "worktree", "add", "-q", str(work), "-b", "story/x"],
            cwd=self.project, check=True,
        )

        class Committer(ScriptedClient):
            """Agent tử tế: viết xong thì commit, đúng như prompt bảo."""

            def run(self, spec):
                r = super().run(spec)
                if "Rà soát" not in spec.prompt:
                    subprocess.run(["git", "add", "src"], cwd=spec.workdir, check=False)
                    subprocess.run(
                        ["git", "commit", "-qm", "xong"], cwd=spec.workdir, check=False
                    )
                return r

        c = Committer()
        try:
            self.implement(c, workdir=work)
            self.assertTrue(c.envs[0].get(ENV_BASE_REF), "chưa tính được mốc rẽ nhánh")
            self.assertEqual(
                subprocess.run(
                    ["git", "status", "--porcelain"], cwd=work,
                    capture_output=True, text=True, check=True,
                ).stdout.strip(),
                "",
                "agent phải đã commit hết — nếu không, test này không kiểm gì",
            )
            self.assertIn("src/a.py", c.review_prompts[0])
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(work)],
                cwd=self.project, check=False,
            )

    def test_nguoi_ra_soat_nhan_diff_that_khong_chi_ten_file(self):
        """Danh sách tên file bắt người rà soát dựng lại thứ harness đã
        biết — đo trên e9 là 31–43 lượt cho một story nhỏ."""
        from aisdlc.phases.implement import review_diff

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for cmd in (
                ["git", "init", "-q"],
                ["git", "config", "user.email", "t@t"],
                ["git", "config", "user.name", "t"],
            ):
                subprocess.run(cmd, cwd=d, check=True)
            (d / "goc.txt").write_text("goc\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "goc"], cwd=d, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=d,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            (d / "a.py").write_text("def cong(a, b):\n    return a - b\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "them"], cwd=d, check=True)

            got = review_diff(str(d), ["a.py"], base_ref=base)
            self.assertIn("return a - b", got, "diff phải có nội dung, không chỉ tên")
            self.assertIn("- a.py", got)

            # Không có mốc rẽ nhánh thì lùi về danh sách tên, không nổ.
            self.assertEqual(review_diff(str(d), ["a.py"]), "- a.py")

    def test_reviewer_gets_scope_but_not_story_id(self):
        """Người rà soát cần **phạm vi**, không cần **mã story**.

        Thiếu phạm vi: `diff-scope` rơi vào nhánh "chưa khai phạm vi mà
        đã đổi file" và chặn mọi lệnh Bash — người rà soát đốt hết lượt
        để vật lộn với guard thay vì đọc code. Có mã story: guard
        `completion` chặn nó *dừng* khi test đang đỏ, đúng lúc nó có
        nhiều thứ đáng báo cáo nhất.
        """
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(c.review_envs[0].get(ENV_WRITE_SCOPE), "src")
        self.assertNotIn(ENV_STORY_ID, c.review_envs[0])

    def test_guard_context_reaches_the_client_environment(self):
        """Guard chạy trong hook — tiến trình con của client. Không truyền
        qua môi trường thì nó không biết phạm vi và sẽ chặn mọi thứ."""
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(c.envs[0][ENV_WRITE_SCOPE], "src")
        self.assertEqual(c.envs[0][ENV_STORY_ID], "STORY-01-01")

    def test_cost_recorded_per_run(self):
        out = self.implement(ScriptedClient())
        runs = EvidenceStore(self.artifacts).read("STORY-01-01").of(AGENT_RUN)
        self.assertEqual(len(runs), 2)          # viết + rà soát
        self.assertAlmostEqual(out.cost_usd, 1.0)  # chỉ lượt viết tính vào attempt


class TestRetry(ImplementTestCase):
    def test_blocking_review_triggers_a_retry_with_feedback(self):
        c = ScriptedClient(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertEqual(out.quality_attempts, 2)   # lần đầu + 1 lần thử lại
        self.assertIn("bí", out.blocked_reason)

    def test_bi_thi_dung_som_thay_vi_dot_het_han_muc(self):
        """Hai lượt liền cùng một mục chặn thì thử tiếp vô nghĩa.

        Thường là mâu thuẫn ngoài tầm agent — tiêu chí chấp nhận đòi thứ
        `write_scope` cấm. Đo trên e9: 4 lượt y hệt nhau, $9,85, cùng một
        câu về lockfile không được commit.
        """
        c = ScriptedClient(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        out = self.implement(c, config=self.config(**{"run.max_retries": 5}))
        self.assertEqual(out.quality_attempts, 2, "phải dừng ở lượt 2, không chạy tới 6")
        self.assertIn("sửa tiêu chí chấp nhận hoặc write_scope", out.blocked_reason)

    def test_bi_nhan_ra_du_nguoi_ra_soat_doi_cach_dien_dat(self):
        """Người rà soát là một model: cùng một khiếm khuyết được viết lại
        bằng từ khác mỗi lượt. So chuỗi y hệt thì không bao giờ khớp.

        Bốn mục chặn dưới đây là **nguyên văn** bốn lượt của STORY-01-02
        trên e9 — cùng một chuyện (`fake-indexeddb` không được khai trong
        `package.json`), không cặp nào trùng chữ, nên bộ dò so chuỗi im
        suốt và story đốt hết hạn mức: $10,39.
        """
        from aisdlc.phases.implement import deadlock_reason

        muc = [
            "[chặn] package.json / src/store/db.test.ts:1 — `fake-indexeddb` "
            "không được khai ở đâu cả; `npm ls` báo `extraneous`, lockfile có "
            "0 lần nhắc tới nó.",
            "[chặn] package.json — `fake-indexeddb` không được khai ở đâu cả; "
            "nó chỉ tình cờ có mặt",
            "[chặn] package.json — `fake-indexeddb` không được khai ở đâu cả, "
            "`npm ci` là mất sạch bằng chứng của TCCN 7",
        ]

        class Lan:
            infra = False

            def __init__(self, f):
                self.review_findings = [f]

        scope = ["src/domain/note.ts", "src/store/db.ts", "src/store/db.test.ts"]
        for i in range(1, len(muc)):
            with self.subTest(cap=f"{i}-{i + 1}"):
                ly_do = deadlock_reason([Lan(muc[i - 1]), Lan(muc[i])], scope)
                self.assertTrue(ly_do, "phải nhận ra là cùng một chuyện")
                self.assertIn("package.json", ly_do)
                self.assertIn("không nằm trong write_scope", ly_do)

    def test_hai_khiem_khuyet_khac_nhau_tren_cung_tep_khong_phai_bi(self):
        """Cùng tệp nhưng khác khiếm khuyết nghĩa là có dịch chuyển."""
        from aisdlc.phases.implement import deadlock_reason

        class Lan:
            infra = False

            def __init__(self, f):
                self.review_findings = [f]

        self.assertFalse(deadlock_reason(
            [Lan("[chặn] package.json — thiếu khai fake-indexeddb"),
             Lan("[chặn] package.json — khai sai phiên bản vitest")],
            ["src"],
        ))
        self.assertFalse(deadlock_reason(
            [Lan("[chặn] src/store/db.ts — không xử lý hết quota"),
             Lan("[chặn] src/domain/note.ts — rev không tăng đúng 1")],
            ["src"],
        ))

    def test_pham_vi_ghi_co_tep_khai_phu_thuoc(self):
        """Story nào cũng có thể cần thêm một gói.

        BMAD chỉ liệt kê tệp mã nguồn vào `write_scope`, nhưng tiêu chí
        chấp nhận thì đòi "test trên `fake-indexeddb`", "lockfile được
        commit". Không cho chạm tệp khai phụ thuộc thì story không thoả
        nổi tiêu chí của chính nó — hai story liên tiếp trên e9 bí đúng
        vì chuyện này, $20 cho tám lượt không lượt nào qua.
        """
        from aisdlc.phases.implement import effective_write_scope

        (self.project / "package.json").write_text("{}", encoding="utf-8")
        scope = effective_write_scope(self.story, self.project)
        self.assertIn("package.json", scope)
        self.assertIn("package-lock.json", scope)
        self.assertIn("src", scope)          # phần story tự khai còn nguyên
        self.assertNotIn("Cargo.toml", scope)  # dự án không có thì không thêm

    def test_muc_chan_doi_thi_van_thu_tiep(self):
        """Chặn ở chỗ khác nghĩa là lượt vừa rồi có dịch chuyển — thử tiếp."""
        class DoiMuc(ScriptedClient):
            lan = 0

            def run(self, spec):
                if "Rà soát" in spec.prompt:
                    DoiMuc.lan += 1
                    self.review = f"[chặn] src/a.py:1 — khiếm khuyết số {DoiMuc.lan}"
                return super().run(spec)

        DoiMuc.lan = 0
        out = self.implement(DoiMuc(), config=self.config(**{"run.max_retries": 2}))
        self.assertEqual(out.quality_attempts, 3)
        self.assertIn("đã thử", out.blocked_reason)

    def test_out_of_scope_write_fails_the_gate(self):
        c = ScriptedClient(writes=("src/a.py", "ngoai/pham-vi.py"))
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertIn("phạm vi", out.summary())

    def test_feedback_reaches_the_next_attempt(self):
        class Recorder(ScriptedClient):
            prompts: list = []

            def run(self, spec):
                if "Rà soát" not in spec.prompt:
                    Recorder.prompts.append(spec.prompt)
                return super().run(spec)

        Recorder.prompts = []
        self.implement(Recorder(review="[chặn] src/a.py:1 — sai"))
        self.assertGreaterEqual(len(Recorder.prompts), 2)
        self.assertIn("Lượt trước chưa đạt", Recorder.prompts[1])
        self.assertIn("sai", Recorder.prompts[1])


class TestFailureKinds(ImplementTestCase):
    def test_infrastructure_error_does_not_burn_a_retry(self):
        """Mất kết nối không phải agent làm sai. Gộp hai loại lại thì mạng
        chập chờn sẽ chặn oan story."""
        c = ScriptedClient(fail_first=1, fail_error="api_error")
        out = self.implement(c)
        self.assertTrue(out.done, out.summary())
        self.assertEqual(out.quality_attempts, 1)
        self.assertTrue(out.attempts[0].infra)

    def test_repeated_infrastructure_errors_eventually_block(self):
        out = self.implement(ScriptedClient(fail_first=99, fail_error="api_error"))
        self.assertFalse(out.done)
        self.assertIn("hạ tầng", out.blocked_reason)

    def test_classification(self):
        for err in ("api_error", "overloaded", "quá 1800s", "Connection lost"):
            self.assertTrue(is_infrastructure_error(err), err)
        self.assertFalse(is_infrastructure_error("test đỏ"))

    def test_review_that_cannot_run_is_not_clean(self):
        class NoReview(ScriptedClient):
            def run(self, spec):
                if "Rà soát" in spec.prompt:
                    return RunResult(ok=False, error="hết giờ")
                return super().run(spec)

        out = self.implement(NoReview())
        self.assertFalse(out.done)


class TestFakeTestDetection(ImplementTestCase):
    def test_story_that_writes_an_assertionless_test_is_blocked(self):
        """Mốc demo 7: đẩy một story có test giả → cổng chặn, nêu đúng lý do."""
        out = self.implement(ScriptedClient(writes=("src/tests/test_a.py",)))
        self.assertFalse(out.done)
        self.assertIn("test thật", out.summary())


class TestContext(ImplementTestCase):
    def test_architecture_rules_selected_by_requirement(self):
        arch = parse_architecture_file(FIX / "architecture.md")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=arch, contract=None, config=self.config(),
        )
        self.assertIn("AR-1", ctx["architecture_rules"])     # ràng buộc FR-1
        self.assertNotIn("AR-9", ctx["architecture_rules"])  # xếp hạng tìm kiếm

    def test_story_file_is_used_when_present(self):
        path = self.artifacts / "stories" / "EPIC-01" / "STORY-01-01.md"
        path.parent.mkdir(parents=True)
        path.write_text("# hợp đồng đầy đủ của story\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(),
        )
        self.assertIn("hợp đồng đầy đủ", ctx["story_contract"])

    def test_story_without_screens_gets_no_mockup(self):
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(),
        )
        self.assertIn("không dựng màn hình nào", ctx["mockup_section"])


class TestFindings(unittest.TestCase):
    def test_only_blocking_items_count(self):
        text = (
            "- [chặn] src/a.py:10 — mất dữ liệu\n"
            "- [nên sửa] src/b.py:2 — tên biến khó hiểu\n"
            "[góp ý] có thể gộp hai hàm\n"
        )
        found = blocking_findings(text)
        self.assertEqual(len(found), 1)
        self.assertIn("mất dữ liệu", found[0])

    def test_clean_review(self):
        self.assertEqual(blocking_findings("không có mục chặn"), [])

    def test_empty_text(self):
        self.assertEqual(blocking_findings(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
