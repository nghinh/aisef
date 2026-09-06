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
from aisdlc.clients.stream import INFRA_STATUSES, exit_status_of  # noqa: E402
from aisdlc.harness.observe import AGENT_RUN, NOTE, EvidenceStore  # noqa: E402
from aisdlc.phases.implement import (  # noqa: E402
    blocking_findings,
    build_context,
    implement_story,
)

FIX = ROOT / "tests" / "fixtures" / "bmad"


class ScriptedClient(ClientAdapter):
    """Agent giả: mỗi lượt viết code theo kịch bản, rồi rà soát theo kịch bản."""

    id = "scripted"

    def __init__(self, *, writes=("src/a.py",), review="không có mục chặn",
                 security="không có phát hiện bảo mật",
                 fail_first=0, fail_error="api_error"):
        self.writes = list(writes)
        self.review = review
        self.security = security
        self.security_envs: list[dict] = []
        self.review_envs: list[dict] = []
        self.review_prompts: list[str] = []
        self.fail_first = fail_first
        self.fail_error = fail_error
        self.calls: list[str] = []
        self.envs: list[dict] = []
        self.settings_files: list = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        self.settings_files.append(spec.settings_file)
        # Phân loại theo **dòng đầu**: prompt developer lượt 2 mang feedback
        # của reviewer ("[chặn] … Rà soát là báo cáo"), nên dò chuỗi trong
        # toàn prompt sẽ nhận nhầm phiên developer là phiên review.
        dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
        is_security = dau.startswith("# Rà soát bảo mật")
        is_review = dau.startswith("# Rà soát") and not is_security
        if is_security:
            self.calls.append("security")
            self.security_envs.append(dict(spec.env))
            return RunResult(ok=True, text=self.security, cost_usd=0.2)
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
        """Client giả trả văn bản **không** kèm khối JSON, nên mỗi vai rà
        soát tốn thêm đúng một lượt hỏi lại schema (R8). Đó chính là hành vi
        cần: thiếu bản máy đọc thì hỏi lại một lần rồi mới lùi về văn bản.
        Agent thật đọc prompt mới sẽ trả JSON ngay lượt đầu và không có lượt
        thêm nào."""
        c = ScriptedClient()
        self.implement(c)
        self.assertEqual(
            c.calls, ["develop", "review", "review", "security", "security"]
        )

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
        # viết + rà soát + hỏi lại schema + bảo mật + hỏi lại schema: client
        # giả không trả khối JSON nên mỗi vai rà soát tốn thêm đúng 1 lượt
        # (R8), và lượt hỏi lại phải nằm trong bằng chứng để cộng chi phí.
        self.assertEqual(len(runs), 5)
        self.assertEqual(
            [r.name for r in runs][1:],
            ["STORY-01-01-review", "STORY-01-01-review-retry",
             "STORY-01-01-security", "STORY-01-01-security-retry"],
        )
        self.assertAlmostEqual(out.cost_usd, 1.0)  # chỉ lượt viết tính vào attempt


class TestRetry(ImplementTestCase):
    def test_blocking_review_triggers_a_retry_with_feedback(self):
        c = ScriptedClient(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertEqual(out.quality_attempts, 2)   # lần đầu + 1 lần thử lại
        self.assertIn("đã thử", out.blocked_reason)

    def test_bi_thi_dung_som_thay_vi_dot_het_han_muc(self):
        """Lặp lại **và** trỏ ra ngoài phạm vi ghi thì thử tiếp vô nghĩa.

        Đo trên e9: 4 lượt y hệt nhau, $9,85, cùng một câu về lockfile
        không được commit — tệp mà story không được phép chạm.
        """
        c = ScriptedClient(
            review="[chặn] ../khac/thu-vien.py:1 — thiếu khai `mot-goi-nao-do`"
        )
        out = self.implement(c, config=self.config(**{"run.max_retries": 5}))
        self.assertEqual(out.quality_attempts, 2, "phải dừng ở lượt 2, không chạy tới 6")
        self.assertIn("không nằm trong write_scope", out.blocked_reason)

    def test_be_tac_do_ke_hoach_thi_dung_ngay_o_luot_dau(self):
        """Hai model độc lập cùng kết luận story sai thì thử tiếp là đốt
        tiền vào chỗ không có lối ra.

        Đo trên e9, STORY-01-04: người viết khai TCCN 1 không thoả được
        (cần chỉ mục trong `src/store/db.ts`, ngoài phạm vi), người rà
        soát xác nhận "lời khai ĐÚNG SỰ THẬT, đã kiểm chứng" — rồi vòng
        lặp vẫn chạy thêm hai lượt nữa. Bốn lượt, $49,12 cho một story.
        """
        c = ScriptedClient(review=(
            "[bế tắc] TCCN 1 — cần chỉ mục trên `updatedAt` trong "
            "`src/store/db.ts`, ngoài write_scope. Đã kiểm chứng: đúng."
        ))
        out = self.implement(c, config=self.config(**{"run.max_retries": 5}))
        self.assertEqual(out.quality_attempts, 1, "phải dừng ngay lượt đầu")
        self.assertIn("bế tắc do kế hoạch", out.blocked_reason)
        self.assertIn("src/store/db.ts", out.blocked_reason)

    def test_muc_chan_thuong_van_duoc_thu_lai(self):
        """`[chặn]` là lỗi code — sửa được, nên vẫn thử tiếp."""
        c = ScriptedClient(review="[chặn] src/a.py:1 — quên xử lý null")
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertGreater(out.quality_attempts, 1)
        self.assertNotIn("bế tắc do kế hoạch", out.blocked_reason)

    def test_lap_lai_trong_pham_vi_la_chua_sua_khong_phai_khong_sua_duoc(self):
        """Mục chặn lặp lại nhưng tệp nằm trong phạm vi thì vẫn thử tiếp.

        Đo trên e9: STORY-01-02 trượt hai lượt rồi qua ở lượt 3, còn
        STORY-01-04 bị chặn hai lượt liền vì cùng một vi phạm AR-7 trên
        `src/app/list-notes.ts` — tệp nằm ngay trong phạm vi của nó. Dừng
        ở đó là cắt ngang một story còn cứu được.
        """
        c = ScriptedClient(review="[chặn] src/a.py:1 — mất dữ liệu khi lưu")
        out = self.implement(c, config=self.config(**{"run.max_retries": 3}))
        self.assertEqual(out.quality_attempts, 4, "hạn mức lượt thử phải chạy hết")
        self.assertIn("đã thử", out.blocked_reason)

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

    def test_muc_chan_duoc_luu_vao_bang_chung(self):
        """Bản tóm tắt in ra màn hình cắt ngắn mục chặn. Muốn biết hai lượt
        có bị chặn vì cùng một chuyện không thì phải đọc được nguyên văn —
        thiếu chỗ này thì lối duy nhất là mò nhật ký phiên."""
        self.implement(ScriptedClient(review="[chặn] src/a.py:1 — mất dữ liệu"))
        ghi = [
            e for e in EvidenceStore(self.artifacts).read("STORY-01-01").events
            if e.name == "review"
        ]
        self.assertTrue(ghi)
        self.assertIn("mất dữ liệu", ghi[0].detail["findings"][0])
        self.assertFalse(ghi[0].ok)

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
        """Vòng thử lại đọc cùng bảng kết cục với evidence (ADR-005 V11 B)."""
        for err in ("api_error", "overloaded", "quá 1800s", "Connection lost"):
            self.assertIn(exit_status_of(RunResult(ok=False, error=err)), INFRA_STATUSES, err)
        self.assertNotIn(exit_status_of(RunResult(ok=False, error="test đỏ")), INFRA_STATUSES)

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

    def test_ban_do_ma_tat_mac_dinh_thi_slot_rong(self):
        """ADR-005 V7: `context.max_repo_map_chars` = 0 cho tới khi A/B có số —
        slot rỗng, bàn giao ghi `repo_map: (code, 0)`."""
        from aisdlc.phases.implement import handoff_slots

        (self.project / "src").mkdir()
        (self.project / "src" / "a.ts").write_text("export function taoGhiChu() {}\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(),
        )
        self.assertEqual(ctx["repo_map"], "")
        self.assertEqual(handoff_slots(ctx)["repo_map"], ("code", 0))

    def test_ban_do_ma_bat_thi_co_muc_va_ghi_ban_giao(self):
        from aisdlc.phases.implement import handoff_slots

        (self.project / "src").mkdir()
        (self.project / "src" / "a.ts").write_text("export function taoGhiChu() {}\n", encoding="utf-8")
        (self.project / "lib").mkdir()
        (self.project / "lib" / "b.ts").write_text("taoGhiChu()\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(**{"context.max_repo_map_chars": 2000}),
        )
        self.assertTrue(ctx["repo_map"].startswith("## Bản đồ mã quanh phạm vi"))
        self.assertIn("export function taoGhiChu() …", ctx["repo_map"])
        self.assertIn("`lib/b.ts` · taoGhiChu", ctx["repo_map"])
        src, n = handoff_slots(ctx)["repo_map"]
        self.assertEqual(src, "code")
        self.assertGreater(n, 0)

    def test_map_provider_hong_thi_lui_ve_va_noi_tho(self):
        (self.project / "src").mkdir()
        (self.project / "src" / "a.ts").write_text("export function taoGhiChu() {}\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None,
            config=self.config(**{"context.max_repo_map_chars": 2000, "context.map_provider": "khong-co-lenh --x"}),
        )
        self.assertIn("chạy hỏng", ctx["repo_map"])
        self.assertIn("taoGhiChu", ctx["repo_map"])


class TestSchemaRaSoat(ImplementTestCase):
    """R8 nối vào vòng đời thật: agent trả đúng schema thì không tốn lượt thêm."""

    JSON_SACH = '\n\n```json\n{"verdict": "pass", "findings": []}\n```\n'

    def test_json_hop_le_thi_khong_hoi_lai(self):
        c = ScriptedClient(review="không có mục chặn" + self.JSON_SACH,
                           security="không có phát hiện bảo mật" + self.JSON_SACH)
        out = self.implement(c)
        self.assertTrue(out.done, out.summary())
        self.assertEqual(c.calls, ["develop", "review", "security"])

    def test_behavior_id_di_vao_bang_chung_cho_so_hanh_vi(self):
        c = ScriptedClient(review=(
            "- [chặn] src/a.py:1 — mất dữ liệu khi lưu\n\n"
            '```json\n{"verdict": "block", "findings": [{"tag": "chặn", '
            '"file": "src/a.py", "line": 1, "why": "mất dữ liệu khi lưu", '
            '"behavior_id": "AC-STORY-01-01-1"}]}\n```\n'
        ))
        self.implement(c)
        notes = {e.name: e.detail
                 for e in EvidenceStore(self.artifacts).read("STORY-01-01").of(NOTE)}
        self.assertEqual(notes["review:verdict"]["verdict"], "block")
        self.assertEqual(notes["review:verdict"]["findings"][0]["behavior_id"],
                         "AC-STORY-01-01-1")
        self.assertNotIn("review:mismatch", notes)


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


class TestCachLyThanCay(ImplementTestCase):
    """Lỗi 40. Worktree ngăn story giẫm lên nhau, nhưng **không** có gì cấm
    agent `cd` ra ngoài rồi commit thẳng vào thân cây.

    Đã gặp thật: một lượt OpenCode đưa `src/reverse-words.js` lên `main`
    (commit `d583696`, giữ ở thẻ `bang-chung-loi-40` của dự án thử) trong
    khi nhánh story đứng yên. Cổng chỉ thấy "diff rỗng" nên story trượt vì
    lý do sai — còn code chưa qua cổng nào thì đã nằm trên trunk.
    """

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "config", "user.email", "t@t.t"],
                       cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "nen"],
                       cwd=self.project, check=True)
        self.workdir = self.project / "cay-story"
        self.workdir.mkdir()

    def head(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project,
                              capture_output=True, text=True).stdout.strip()

    class PhaCachLy(ClientAdapter):
        """Agent commit thẳng vào thân cây, đúng như lượt OpenCode đã làm."""

        id = "pha-cach-ly"

        def __init__(self, project):
            self.project = project

        def available(self) -> bool:
            return True

        def capabilities(self):
            return {c: Support.NATIVE for c in Capability}

        def build_command(self, spec):
            return ["true"]

        def run(self, spec: RunSpec) -> RunResult:
            tep = self.project / "len-thang-trunk.py"
            if not tep.exists():          # chỉ phiên lập trình mới commit
                tep.write_text("x = 1\n")
                for cmd in (["git", "add", "len-thang-trunk.py"],
                            ["git", "commit", "-q", "-m", "lạc"]):
                    subprocess.run(cmd, cwd=self.project, check=True)
            return RunResult(ok=True, text="xong")

    def test_doi_nhanh_chinh_thi_luot_chay_that_bai(self):
        truoc = self.head()
        out = self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        self.assertFalse(out.done)
        self.assertIn("đổi nhánh chính", out.attempts[0].error)
        self.assertNotEqual(self.head(), truoc)

    def test_ghi_vao_bang_chung_de_ve_sau_truy_duoc(self):
        self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        muc = [e for e in ev.events if e.name == "cách ly"]
        self.assertTrue(muc, "phải có bản ghi cách ly bị phá")
        self.assertFalse(muc[0].ok)
        self.assertNotEqual(muc[0].detail["truoc"], muc[0].detail["sau"])

    def test_tinh_la_loi_ha_tang_khong_phai_loi_chat_luong(self):
        """Không tiêu hạn mức thử lại chất lượng: story chưa hề được chấm."""
        out = self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        self.assertTrue(out.attempts[0].infra)

    def test_khong_doi_thi_khong_bao_gi(self):
        """Agent ngoan không được nhận cảnh báo — guard giả là guard bị gỡ."""
        out = self.implement(ScriptedClient(), workdir=self.workdir)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        self.assertEqual([e for e in ev.events if e.name == "cách ly"], [])
        self.assertNotIn("đổi nhánh chính", out.attempts[0].error or "")

    def test_chay_thang_trong_du_an_thi_khong_kiem(self):
        """`--no-isolate` là cố ý làm việc trên thân cây; kiểm ở đó sẽ
        chặn mọi lượt chạy hợp lệ."""
        out = self.implement(self.PhaCachLy(self.project), workdir=self.project)
        self.assertNotIn("đổi nhánh chính", out.attempts[0].error or "")


class TestCachLyVoLaDungHan(TestCachLyThanCay):
    def test_khong_thu_lai_khi_cach_ly_da_vo(self):
        """Worktree của lượt sau rẽ từ thân cây đã bẩn — thử lại chỉ tiêu
        thêm tiền và làm hỏng sâu hơn."""
        out = self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        self.assertEqual(len(out.attempts), 1)
        self.assertIn("đổi nhánh chính", out.blocked_reason)


class TestVaiRaSoatKhaiToolBiCam(ImplementTestCase):
    """Cấm tool theo vai phải tới được guard — tức phải nằm trong `spec.env`,
    không chỉ trong `spec.disallowed_tools` (cờ mà OpenCode bỏ qua)."""

    def test_reviewer_va_security_khai_tool_bi_cam(self):
        client = ScriptedClient()
        self.implement(client)
        self.assertTrue(client.review_envs, "phải có phiên rà soát")
        self.assertTrue(client.security_envs, "phải có phiên bảo mật")
        for env in client.review_envs + client.security_envs:
            self.assertEqual(env.get("AISDLC_DISALLOWED_TOOLS"), "Write,Edit,NotebookEdit")

    def test_developer_khong_bi_cam(self):
        client = ScriptedClient()
        self.implement(client)
        dev = [e for e in client.envs if e.get("AISDLC_STORY_ID")]
        self.assertTrue(dev)
        for env in dev:
            self.assertNotIn("AISDLC_DISALLOWED_TOOLS", env)

    def test_security_van_khong_mang_ma_story(self):
        """Mã story kích hoạt guard `completion` — người rà soát bảo mật
        không được mang nó, dù nay có env."""
        client = ScriptedClient()
        self.implement(client)
        for env in client.security_envs:
            self.assertNotIn("AISDLC_STORY_ID", env)
            self.assertIn("AISDLC_WRITE_SCOPE", env)


class TestTruyenHookTuongMinh(ImplementTestCase):
    """G4 mảnh 1. Hook Claude Code chỉ chạy nếu `.claude/settings.json` nằm
    trong worktree, tức dự án đã commit nó. Dự án `.gitignore` `.claude/`
    chạy story với zero guard, và bằng chứng trông y hệt agent ngoan.
    `RunSpec.settings_file` có, adapter hỗ trợ `--settings`, nhưng không
    nơi nào đặt — hai dự án thử đều commit `.claude/` nên chưa lộ."""

    def test_co_tep_thi_ca_ba_vai_deu_nhan(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        client = ScriptedClient()
        self.implement(client)
        self.assertGreaterEqual(len(client.settings_files), 3)
        for f in client.settings_files:
            self.assertEqual(Path(f), self.project / ".claude" / "settings.json")

    def test_khong_co_tep_thi_de_trong_khong_bia(self):
        client = ScriptedClient()
        self.implement(client)
        self.assertTrue(client.settings_files)
        for f in client.settings_files:
            self.assertFalse(f, "không có tệp mà vẫn truyền đường dẫn là bịa")


class TestKyVongGuardTheoBaoCaoBienDich(ImplementTestCase):
    """Kỳ vọng guard đọc từ `compile-report.json`: client đã biên dịch hook
    và khai chặn tại nguồn thì phiên developer phải để lại dấu vết."""

    def bao_cao(self, client_id, blocks):
        import json
        (self.artifacts / "compile-report.json").write_text(json.dumps({
            "clients": [{"client": client_id, "written": [], "guards_wired": [],
                         "guards_post_hoc": [], "blocks_at_source": blocks,
                         "degradations": []}]}), encoding="utf-8")

    def muc(self, out):
        return next(c for c in out.attempts[-1].gate.checks if c.name == "guard có chạy")

    def test_chua_bien_dich_thi_khong_doi(self):
        out = self.implement(ScriptedClient())
        self.assertTrue(self.muc(out).skipped)

    def test_da_bien_dich_ma_agent_ghi_khong_qua_guard_thi_truot(self):
        """Agent giả ghi thẳng ra đĩa — đúng hình dạng của một phiên mà hook
        không tới được."""
        self.bao_cao("scripted", True)
        out = self.implement(ScriptedClient())
        self.assertFalse(self.muc(out).passed)
        self.assertFalse(out.done)

    def test_da_bien_dich_va_guard_ghi_dau_vet_thi_qua(self):
        self.bao_cao("scripted", True)
        client = ScriptedClient()
        goc = client.run

        def run_va_ghi(spec):
            r = goc(spec)
            if spec.env.get("AISDLC_STORY_ID"):
                EvidenceStore(self.artifacts).file_change(spec.env["AISDLC_STORY_ID"], "src/a.py")
            return r
        client.run = run_va_ghi
        out = self.implement(client)
        self.assertTrue(self.muc(out).passed)

    def test_client_khac_trong_bao_cao_thi_khong_doi(self):
        self.bao_cao("claude", True)
        out = self.implement(ScriptedClient())
        self.assertTrue(self.muc(out).skipped)


class TestNguoiRaSoatKhongDuocSuaCay(ImplementTestCase):
    """Đo hợp quy 2026-09-05: cấm `Write` ở guard bị lách trên **cả hai
    client** bằng Bash (`echo > tệp`) — Bash thì không cấm được vì người rà
    soát cần chạy test. Lớp hai: chụp cây trước/sau phiên rà soát, khác thì
    hoàn nguyên, ghi bằng chứng, và lượt rà soát không được tính."""

    class ReviewerGhi(ScriptedClient):
        def run(self, spec):
            r = super().run(spec)
            dau = spec.prompt.lstrip().splitlines()[0]
            if dau.startswith("# Rà soát") and not dau.startswith("# Rà soát bảo mật"):
                (Path(spec.workdir) / "src" / "reviewer-da-ghi.py").write_text("x\n")
            return r

    class SecurityGhi(ScriptedClient):
        def run(self, spec):
            r = super().run(spec)
            if spec.prompt.lstrip().startswith("# Rà soát bảo mật"):
                (Path(spec.workdir) / "src" / "a.py").write_text("bi sua\n")
            return r

    def _init_git(self):
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)

    def test_reviewer_ghi_tep_moi_thi_hoan_nguyen_va_khong_tinh(self):
        self._init_git()
        out = self.implement(self.ReviewerGhi())
        self.assertFalse((self.project / "src" / "reviewer-da-ghi.py").exists(), "phải hoàn nguyên")
        chan = out.attempts[-1].review_findings
        self.assertTrue(any("đã sửa cây làm việc" in f for f in chan), chan)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        self.assertTrue(any(e.name == "review:immutable" and not e.ok for e in ev.events))

    def test_security_sua_tep_co_san_thi_hoan_nguyen(self):
        self._init_git()
        out = self.implement(self.SecurityGhi())
        # src/a.py do developer giả viết ("x = 1"); security sửa → phải về như cũ
        self.assertEqual((self.project / "src" / "a.py").read_text(), "x = 1\n")
        self.assertIn("đã sửa cây làm việc", out.attempts[-1].security.error)

    def test_reviewer_ngoan_khong_bi_dung(self):
        self._init_git()
        out = self.implement(ScriptedClient())
        self.assertTrue(out.done)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        self.assertFalse(any(e.name == "review:immutable" for e in ev.events))


class TestGoiBanGiaoDuocGhi(ImplementTestCase):
    """ADR-003 #9: mỗi vai nhận một gói được ghi lại; gói của reviewer/security
    không có slot nguồn `agent` hay `?`."""

    def test_handoffs_recorded_for_every_role(self):
        from aisdlc.harness.observe import HANDOFF
        client = ScriptedClient()
        self.implement(client)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        chuoi = [(e.detail["to"], e.detail["attempt"]) for e in ev.of(HANDOFF)]
        self.assertIn(("developer", 1), chuoi)
        if client.review_prompts:                       # rà soát có chạy thì phải có gói
            self.assertIn(("reviewer", 1), chuoi)
        for e in ev.of(HANDOFF):
            if e.detail["to"] in ("reviewer", "security"):
                nguon = {k: v["source"] for k, v in e.detail["slots"].items()}
                self.assertNotIn("agent", nguon.values(), nguon)
                self.assertNotIn("?", nguon.values(), nguon)
                self.assertIn("diff_summary", nguon)


class TestHarnessKhaiGocDuAn(ImplementTestCase):
    def test_every_role_gets_the_project_root_in_env(self):
        from aisdlc.harness.guardrails import ENV_PROJECT

        class Ghi(ScriptedClient):
            def __init__(self):
                super().__init__()
                self.specs = []

            def run(self, spec):
                self.specs.append(spec)
                return super().run(spec)

        client = Ghi()
        self.implement(client)
        self.assertTrue(client.specs, "không có lượt nào")
        for spec in client.specs:
            self.assertEqual(spec.env.get(ENV_PROJECT), str(self.project), spec.env)


from aisdlc.control.outcome import Outcome  # noqa: E402
from aisdlc.harness.guardrails import head_sha  # noqa: E402
from aisdlc.harness.observe import TOOL_RUN  # noqa: E402


class TestBaselineTruocKhiSua(ImplementTestCase):
    """ADR-004 R9. Harness chạy bộ test **trước** phiên developer và ghi tên
    test; cổng so với lần test ở ứng viên để gọi đúng tên hồi quy trong lượt.

    "Bộ test" giả là một lệnh in output dạng `pytest -v` từ `src/ket-qua.txt`
    — tệp mà developer giả ghi đè, nên kết quả đổi theo lượt như test thật.
    """

    LENH = 'sh -c "cat src/ket-qua.txt; ! grep -q FAILED src/ket-qua.txt"'
    TEN = "không làm đỏ test có sẵn"

    @staticmethod
    def ket_qua(xanh, do=()):
        lines = [f"tests/test_a.py::test_{i} PASSED" for i in xanh]
        lines += [f"tests/test_a.py::test_{i} FAILED" for i in do]
        return "\n".join(lines) + "\n"

    def setUp(self):
        super().setUp()
        for cmd in (["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.project, check=True)
        (self.project / "src").mkdir()
        self.truoc(self.ket_qua(range(1, 11)))

    def truoc(self, text):
        """Trạng thái **có sẵn** trước khi story chạm vào — đã commit."""
        (self.project / "src" / "ket-qua.txt").write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", "src"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=self.project, check=True)

    class DoiKetQua(ScriptedClient):
        """Developer giả: phiên developer ghi đè kết quả test theo kịch bản."""

        def __init__(self, sau, **kw):
            super().__init__(writes=(), **kw)
            self.sau = sau

        def run(self, spec):
            r = super().run(spec)
            if spec.env.get(ENV_STORY_ID):
                (Path(spec.workdir) / "src" / "ket-qua.txt").write_text(self.sau, encoding="utf-8")
            return r

    def chay(self, sau, **over):
        cfg = self.config(**{"tools.test": self.LENH, "run.max_retries": 0, **over})
        return self.implement(self.DoiKetQua(sau), config=cfg)

    def muc(self, out):
        return next(c for c in out.attempts[-1].gate.checks if c.name == self.TEN)

    def evidence(self):
        return EvidenceStore(self.artifacts).read(self.story.id)

    def test_baseline_muoi_xanh_sau_luot_chin_xanh_mot_do_thi_neu_dung_ten(self):
        out = self.chay(self.ket_qua(range(1, 10), do=[10]))
        self.assertFalse(out.done, out.summary())
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("tests/test_a.py::test_10", m.detail)
        self.assertNotIn("test_9", m.detail)

    def test_test_moi_do_do_developer_viet_khong_phai_hoi_quy(self):
        """TDD đỏ đúng nghĩa: mục "test" đỏ, mục này không."""
        out = self.chay(self.ket_qua(range(1, 11), do=[11]))
        self.assertIs(self.muc(out).outcome, Outcome.PASSED)
        self.assertIn("test", [c.name for c in out.attempts[-1].gate.failures])

    def test_do_san_o_baseline_van_do_sau_luot_thi_khong_phai_hoi_quy(self):
        self.truoc(self.ket_qua(range(1, 10), do=[10]))
        out = self.chay(self.ket_qua(range(1, 10), do=[10]))
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertIn("test_10", m.detail)
        goc = self.evidence().last(TOOL_RUN, "test:baseline")
        self.assertEqual(goc.detail["red_before"], ["tests/test_a.py::test_10"])
        self.assertTrue(goc.detail["baseline"])
        self.assertNotIn("candidate", goc.detail, "ứng viên chưa đóng băng lúc chạy baseline")
        self.assertEqual(goc.detail["parent"], head_sha(self.project))

    def test_mat_test_co_san_la_hoi_quy(self):
        out = self.chay(self.ket_qua(range(1, 10)))
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("mất 1 test", m.detail)
        self.assertIn("tests/test_a.py::test_10", m.detail)

    def test_hoi_quy_vao_feedback_luot_sau(self):
        class Ghi(self.DoiKetQua):
            prompts: list = []

            def run(self, spec):
                if spec.env.get(ENV_STORY_ID):
                    Ghi.prompts.append(spec.prompt)
                return super().run(spec)

        Ghi.prompts = []
        cfg = self.config(**{"tools.test": self.LENH, "run.max_retries": 1})
        self.implement(Ghi(self.ket_qua(range(1, 10), do=[10])), config=cfg)
        self.assertEqual(len(Ghi.prompts), 2)
        self.assertIn(self.TEN, Ghi.prompts[1])
        self.assertIn("tests/test_a.py::test_10", Ghi.prompts[1])

    def test_chi_phi_them_la_mot_lan_chay_test_moi_story(self):
        """Baseline chạy một lần trước lượt đầu, không mỗi lượt: hai lượt thử
        → 1 baseline + 2 lần test ứng viên, và thời gian được ghi để đo."""
        cfg = self.config(**{"tools.test": self.LENH, "run.max_retries": 1})
        self.implement(self.DoiKetQua(self.ket_qua(range(1, 10), do=[10])), config=cfg)
        ev = self.evidence()
        self.assertEqual(len(ev.of(TOOL_RUN, "test:baseline")), 1)
        self.assertEqual(len(ev.of(TOOL_RUN, "test")), 2)
        self.assertGreaterEqual(ev.last(TOOL_RUN, "test:baseline").duration_ms, 0)

    def test_tat_bang_cau_hinh_thi_khong_chay_va_cong_noi_ro(self):
        lenh = 'sh -c "echo 1 >> src/dem.txt; cat src/ket-qua.txt"'
        out = self.chay(self.ket_qua(range(1, 11)),
                        **{"tools.test": lenh, "verify.baseline": False})
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("verify.baseline", m.detail)
        self.assertEqual(
            (self.project / "src" / "dem.txt").read_text(encoding="utf-8").count("1"), 1,
            "tắt thì chỉ còn lần test sau đóng băng",
        )

    def test_chua_khai_lenh_test_thi_baseline_la_chua_cau_hinh(self):
        out = self.chay(self.ket_qua(range(1, 11)), **{"tools.test": ""})
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertIn("chưa khai", m.detail)


class TestKetCucChuanHoa(ImplementTestCase):
    def test_cham_tran_luot_la_loi_chat_luong_khong_phai_ha_tang(self):
        """ADR-005 V11 (B): `Attempt.infra` đọc `exit_status`. e9 01-05 chạm
        91/90 hai lần — thử lại phải tính vào hạn mức, không được miễn phí."""
        out = self.implement(ScriptedClient(fail_first=1, fail_error="max_turns"))
        self.assertFalse(out.attempts[0].infra)
        self.assertEqual(out.quality_attempts, 2)
        self.assertNotIn(exit_status_of(RunResult(ok=False, error="max_turns")), INFRA_STATUSES)
class TestTestCoKiemDuocStory(ImplementTestCase):
    """ADR-005 V3 cấp 2 trên dự án giả: harness dựng worktree ở SHA cha, chép
    tệp test của story vào, chạy `tools.test`, ghi `test:nop` mang ứng viên.

    "Runner" là một lệnh in dạng `pytest -v` từ các tệp `tests/test_*.sh` —
    mỗi tệp là một test thật sự **chạy**: test thật hỏi `src/a.py` có tồn tại
    không (ở SHA cha thì không → đỏ), test giả in PASSED vô điều kiện.
    """

    LENH = ("sh -c 'echo \"test session starts\"; "
            "out=$(for f in tests/test_*.sh; do [ -f \"$f\" ] && sh \"$f\"; done); "
            "echo \"$out\"; ! echo \"$out\" | grep -q FAILED'")
    TEN = "test có kiểm được story"
    AC = "tests/test_ac.sh::test_AC_STORY_01_01_1"
    THAT = ('[ -f src/a.py ] && echo "%s PASSED" || echo "%s FAILED"\n' % (AC, AC))
    GIA = 'echo "%s PASSED"\n' % AC

    def setUp(self):
        super().setUp()
        for cmd in (["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.project, check=True)
        (self.project / "goc.txt").write_text("goc\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=self.project, check=True)
        self.story.write_scope = ["src", "tests"]

    class GhiTest(ScriptedClient):
        def __init__(self, than, **kw):
            super().__init__(writes=("src/a.py",), **kw)
            self.than = than

        def run(self, spec):
            r = super().run(spec)
            if spec.env.get(ENV_STORY_ID) and self.than is not None:
                p = Path(spec.workdir) / "tests" / "test_ac.sh"
                p.parent.mkdir(exist_ok=True)
                p.write_text(self.than, encoding="utf-8")
            return r

    def chay(self, than, **over):
        cfg = self.config(**{"tools.test": self.LENH, "run.max_retries": 0, **over})
        return self.implement(self.GhiTest(than), config=cfg)

    def muc(self, out):
        return next(c for c in out.attempts[-1].gate.checks if c.name == self.TEN)

    def evidence(self):
        return EvidenceStore(self.artifacts).read(self.story.id)

    def test_test_that_do_o_sha_cha_thi_dat_va_don_worktree(self):
        out = self.chay(self.THAT)
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.PASSED, out.summary())
        self.assertIn("đỏ hoặc không tồn tại", m.detail)
        nop = self.evidence().last(TOOL_RUN, "test:nop")
        self.assertEqual(nop.detail["candidate"], out.attempts[-1].candidate)
        self.assertEqual(nop.detail["files"], ["tests/test_ac.sh"])
        self.assertEqual(nop.detail["parent"], head_sha(self.project))
        self.assertIn(self.AC, nop.detail["failed_ids"])
        self.assertFalse((self.project / ".aisdlc" / "worktrees" / "STORY-01-01-nop").exists())
        nhanh = subprocess.run(["git", "branch", "--list", "story/STORY-01-01-nop"],
                               cwd=self.project, capture_output=True, text=True).stdout
        self.assertEqual(nhanh.strip(), "", "nhánh tạm phải được xoá")

    def test_test_luon_xanh_la_khong_kiem_duoc_gi_neu_ten(self):
        out = self.chay(self.GIA)
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("xanh cả khi không có mã của story", m.detail)
        self.assertIn(self.AC, m.detail)
        self.assertFalse(out.done)

    def test_khong_them_test_thi_khong_ap_dung_va_khong_dung_gi(self):
        out = self.chay(None)
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("không thêm/sửa", m.detail)
        nop = self.evidence().last(TOOL_RUN, "test:nop")
        self.assertEqual(nop.detail["files"], [])
        self.assertEqual(nop.detail["candidate"], out.attempts[-1].candidate)

    def test_tat_bang_cau_hinh_thi_khong_chay_va_van_ghi(self):
        out = self.chay(self.GIA, **{"verify.nop": False})
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("verify.nop", m.detail)
        nops = self.evidence().of(TOOL_RUN, "test:nop")
        self.assertEqual(len(nops), 1)
        self.assertTrue(nops[0].detail["disabled"])
        self.assertEqual(nops[0].detail["candidate"], out.attempts[-1].candidate)

    def test_khong_biet_sha_cha_thi_khong_chay_duoc(self):
        """Chạy thẳng trong dự án (không điểm rẽ) và tắt baseline → không có
        SHA cha nào để dựng: ⚠, không đoán."""
        out = self.chay(self.GIA, **{"verify.baseline": False})
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertIn("SHA cha", m.detail)
