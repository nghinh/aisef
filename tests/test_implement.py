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

import tests  # noqa: E402,F401 — HostProvider vào chỗ docker, không mở container (tests/__init__.py)

from aisef.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisef.clients.stream import RunResult, ToolUse  # noqa: E402
from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.normalize import Story, parse_architecture_file  # noqa: E402
from aisef.harness.guardrails import (  # noqa: E402
    ENV_BASE_REF,
    ENV_STORY_ID,
    ENV_WRITE_SCOPE,
)
from aisef.clients.stream import INFRA_STATUSES, exit_status_of  # noqa: E402
from aisef.harness.observe import AGENT_RUN, NOTE, Event, EvidenceStore  # noqa: E402
from aisef.phases.implement import (  # noqa: F401
    MAX_NOOP,  # noqa: E402
    _unfinished_review,
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
        self.develop_calls = 0
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
        is_security = dau.startswith("# Security review")
        is_review = dau.startswith("# Review") and not is_security
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

        self.develop_calls += 1
        for rel in self.writes:
            path = Path(spec.workdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            # File test thì viết như một file test — nội dung quyết định
            # phép kiểm "test giả" có bắt được hay không.
            body = "def test_x():\n    pass\n" if "test_" in path.name else "x = 1\n"
            # Từ lượt **thứ hai** trở đi viết ra nội dung khác — agent thật
            # thử lại thì sửa khác đi. Ghi lại y hệt là không sửa gì, và
            # harness nay nói đúng như thế (lỗi 68), nên một agent giả ghi lặp
            # sẽ không còn mô tả được một lượt thử lại. Lượt đầu giữ nguyên
            # văn để các phép so nội dung sẵn có vẫn đọc được.
            them = "" if self.develop_calls == 1 else f"# lượt {self.develop_calls}\n"
            path.write_text(body + them, encoding="utf-8")
        return RunResult(ok=True, text="xong", cost_usd=1.0)


class ImplementTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        # A project has a HEAD: without one every candidate freeze fails ("cannot read HEAD") and the loop
        # is exercised on its unfrozen path only (found while resolving SS-01/SS-60, 2026-09-16).
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)
        (self.project / "README.md").write_text("project\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-qm", "entry"], cwd=self.project, check=True)
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

        work = self.project / ".aisef" / "worktrees" / "STORY-01-01"
        subprocess.run(
            ["git", "worktree", "add", "-q", str(work), "-b", "story/x"],
            cwd=self.project, check=True,
        )

        class Committer(ScriptedClient):
            """Agent tử tế: viết xong thì commit, đúng như prompt bảo."""

            def run(self, spec):
                r = super().run(spec)
                if "Review" not in spec.prompt:
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
                    capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
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

    def test_nop_khong_chay_duoc_thi_khong_phai_ket_qua_mong_doi(self):
        """Lỗi 46b. Với phép đối chứng nop, đỏ ở parent là kết quả **cần**.
        Nhưng lệnh test không khởi chạy được (exit 127 trên Windows) cũng cho
        `ok=False`, và gọi đó là "expected" là báo một phép đối chứng chưa hề
        xảy ra."""
        import inspect
        from aisef.phases import implement
        src = inspect.getsource(implement.run_nop)
        self.assertIn("control NOT performed", src)
        i_unrun = src.index("res.unrunnable")
        i_expected = src.index("tests red at parent (expected)")
        self.assertLess(i_unrun, i_expected, "phải hỏi 'chạy được không' trước khi nói 'đỏ đúng như mong đợi'")

    def test_thieu_chinh_ma_cua_story_o_parent_la_do_hop_le(self):
        """Lỗi 120 (todo-cli STORY-01-01, 2026-09-13): cây nop **cố tình**
        không có mã của story, nên "cannot find module ../lib/store" là phép
        đối chứng đang chạy đúng. Luật chung ("chưa test nào xanh thì coi là
        không chạy được") không phân biệt được, vì story đầu của một dự án
        greenfield không có test nào khác để in tên — và phép đối chứng mạnh
        nhất bị ghi là "chưa thực hiện" đúng chỗ cần nó nhất."""
        from aisef.harness.tools import NO_SETUP, ToolResult
        from aisef.phases.implement import _vang_ma_cua_story

        thieu_phu_thuoc = NO_SETUP + " — the project's dependencies are not installed here"
        story = ["lib/store.js", "tests/store.test.js"]

        res = ToolResult("test", ok=False, unrunnable=thieu_phu_thuoc,
                         stdout="Error: Cannot find module '../lib/store'")
        self.assertEqual(_vang_ma_cua_story(res, story), "lib/store.js")

        # Thư viện dự án chưa cài: đúng là môi trường hỏng, phải giữ nguyên.
        res = ToolResult("test", ok=False, unrunnable=thieu_phu_thuoc,
                         stdout="Error: Cannot find module 'express'")
        self.assertEqual(_vang_ma_cua_story(res, story), "")

        # Không phải loại "thiếu phụ thuộc" thì không đụng tới.
        res = ToolResult("test", ok=False, unrunnable="tool not installed or cannot load (exit 127)",
                         stdout="npm: command not found")
        self.assertEqual(_vang_ma_cua_story(res, story), "")

        # Python: tên module là dấu chấm, không phải dấu gạch chéo.
        res = ToolResult("test", ok=False, unrunnable=thieu_phu_thuoc,
                         stdout="ModuleNotFoundError: No module named 'app.store'")
        self.assertEqual(_vang_ma_cua_story(res, ["app/store.py"]), "app/store.py")

        # Tệp test của story không tính: nó **có** trong cây nop.
        res = ToolResult("test", ok=False, unrunnable=thieu_phu_thuoc,
                         stdout="Cannot find module './tests/store.test'")
        self.assertEqual(_vang_ma_cua_story(res, ["tests/store.test.js"]), "")

    def test_run_nop_go_co_khong_chay_duoc_khi_thieu_ma_story(self):
        """Đường thật, không chỉ hàm phụ: `run_nop` phải xoá `unrunnable`
        trước khi ghi bằng chứng, nếu không cổng vẫn đọc UNRUNNABLE."""
        import inspect
        from aisef.phases import implement

        src = inspect.getsource(implement.run_nop)
        i_go = src.index("res.unrunnable = \"\"")
        i_ghi = src.index("record_tool(res, story.id")
        self.assertLess(i_go, i_ghi, "phải phân loại lại **trước** khi ghi")

    def test_nguoi_ra_soat_nhan_diff_that_khong_chi_ten_file(self):
        """Danh sách tên file bắt người rà soát dựng lại thứ harness đã
        biết — đo trên e9 là 31–43 lượt cho một story nhỏ."""
        from aisef.phases.implement import review_diff

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
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
            ).stdout.strip()
            (d / "a.py").write_text("def cong(a, b):\n    return a - b\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "them"], cwd=d, check=True)

            got = review_diff(str(d), ["a.py"], base_ref=base)
            self.assertIn("return a - b", got, "diff phải có nội dung, không chỉ tên")
            self.assertIn("- a.py", got)

            # Không có mốc rẽ nhánh thì lùi về danh sách tên, không nổ.
            self.assertEqual(review_diff(str(d), ["a.py"]), "- a.py")

            # Lỗi 37. Harness tự làm bẩn worktree: nó làm mới plugin guard ở đó
            # mỗi lượt chạy. `git diff` không giới hạn đường dẫn cho người rà
            # soát thấy luôn tệp ấy, và người rà soát chặn story vì "sửa tệp
            # ngoài phạm vi ghi" — còn người rà soát bảo mật mở phiếu high
            # nhắm vào mã do chính harness sinh. Đo trên todo/STORY-01-02
            # 2026-09-09: hai lượt liên tiếp, story bị đánh dấu stuck.
            (d / ".opencode").mkdir()
            (d / ".opencode" / "aisef-guard.ts").write_text(
                'const BIN = ["aisef"]\n', encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "guard"], cwd=d, check=True)
            (d / ".opencode" / "aisef-guard.ts").write_text(
                'const BIN = ["aisef", "moi"]\n', encoding="utf-8")   # harness ghi đè

            got = review_diff(str(d), ["a.py"], base_ref=base)
            self.assertIn("return a - b", got)
            self.assertNotIn("aisef-guard", got,
                             "tệp của harness không phải việc của người rà soát")

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
        self.assertIn("tried", out.blocked_reason)

    def test_ngan_sach_ha_tang_khai_rieng_duoc(self):
        """Phiên mất vì **client**, không vì agent — 502, rate limit, một lời
        gọi tool CLI không phân giải nổi — không chấm gì cả. Nhưng ngân sách
        cho chúng vốn là `max_retries + 1`, nên muốn chịu được một client hay
        hỏng thì phải trả thêm cho cả lượt chất lượng. Đợt C-1b mất 22–32%
        phiên vì cú pháp tool call không phân giải được."""
        class LuonHongHaTang(ScriptedClient):
            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if not dau.startswith("# Review") and not dau.startswith("# Security review"):
                    return RunResult(ok=False, error="api_error 502", cost_usd=0.0)
                return super().run(spec)

        out = self.implement(LuonHongHaTang(),
                             config=self.config(**{"run.max_retries": 0,
                                                   "run.infra_retries": 4}))
        self.assertEqual(len([a for a in out.attempts if a.infra]), 4,
                         "phải dùng đúng ngân sách hạ tầng đã khai")
        self.assertEqual(out.quality_attempts, 0, "hạ tầng không tính lượt chất lượng")

    def test_phien_khong_lam_gi_dung_som_khong_dot_ngan_sach_ha_tang(self):
        """Lỗi 127. Phiên bị cắt có việc đang dở nên đáng cho ngân sách rộng;
        phiên chạy sạch mà viết 0 dòng thì đã **quyết định**, mở lại với đúng
        ngữ cảnh ấy chỉ nhận lại đúng quyết định ấy. Dùng chung một ngân sách
        nghĩa là nâng ngân sách cắt phiên lên 6 làm ca này **tệ hơn**:
        STORY-05-02 tiêu sáu phiên cho kết luận nó có sau hai."""
        class ChiVietLanDau(ScriptedClient):
            """Lượt 1 có việc để chấm (và trượt); từ lượt 2 trở đi từ chối viết."""

            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if dau.startswith("# Review") or dau.startswith("# Security review"):
                    return super().run(spec)
                if inner.develop_calls == 0:
                    return super().run(spec)
                inner.develop_calls += 1
                return RunResult(ok=True, num_turns=7, output_tokens=200,
                                 text="nothing to do", cost_usd=0.0)

        out = self.implement(ChiVietLanDau(review="[chặn] src/a.py:1 — mất dữ liệu"),
                             config=self.config(**{"run.max_retries": 1,
                                                   "run.infra_retries": 6}))
        khong_lam = [a for a in out.attempts if a.noop]
        self.assertEqual(len(khong_lam), 2,
                         f"phải dừng ở {MAX_NOOP} phiên no-op, không đốt hết 6")
        self.assertIn("wrote nothing", out.blocked_reason)
        self.assertIn("same decision", out.blocked_reason)

    def test_ngan_sach_ha_tang_mac_dinh_giu_nguyen_hanh_vi_cu(self):
        from aisef.config import DEFAULTS
        self.assertEqual(DEFAULTS["run.infra_retries"], -1)

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
        self.assertIn("not in the story's write_scope", out.blocked_reason)

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
            "`src/store/db.ts`, ngoài write_scope. Đã kiểm chứng: đúng.\n\n"
            '```json\n{"verdict": "stuck", "findings": [{"tag": "stuck", '
            '"file": "src/store/db.ts", "why": "TCCN 1 cần chỉ mục trên updatedAt, '
            'ngoài write_scope"}]}\n```\n'
        ))
        out = self.implement(c, config=self.config(**{"run.max_retries": 5}))
        self.assertEqual(out.quality_attempts, 1, "phải dừng ngay lượt đầu")
        self.assertIn("deadlock due to plan", out.blocked_reason)
        self.assertIn("src/store/db.ts", out.blocked_reason)

    def test_be_tac_chi_trong_van_xuoi_thi_chan_nhung_khong_ket_thuc(self):
        """D-026 (LedgerLock 2026-09-15): `[stuck]` trong văn xuôi — kể cả câu
        *phủ định* thẻ — không được tự nó kết thúc story. Không có JSON là
        đầu ra có cấu trúc hỏng: chặn (fail-closed), thử lại, không terminal."""
        c = ScriptedClient(review=(
            "The file IS there. So [stuck] doesn't apply.\n"
            "[bế tắc] TCCN 1 — cần chỉ mục trong `src/store/db.ts`, ngoài write_scope."
        ))
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertNotIn("deadlock due to plan", out.blocked_reason)
        self.assertGreater(out.quality_attempts, 1, "văn xuôi chặn lượt, không kết thúc story")

    def test_muc_chan_thuong_van_duoc_thu_lai(self):
        """`[chặn]` là lỗi code — sửa được, nên vẫn thử tiếp."""
        c = ScriptedClient(review="[chặn] src/a.py:1 — quên xử lý null")
        out = self.implement(c, config=self.config(**{"run.max_retries": 2}))
        self.assertGreater(out.quality_attempts, 1)
        self.assertNotIn("deadlock due to plan", out.blocked_reason)

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
        self.assertIn("tried", out.blocked_reason)

    def test_bi_nhan_ra_du_nguoi_ra_soat_doi_cach_dien_dat(self):
        """Người rà soát là một model: cùng một khiếm khuyết được viết lại
        bằng từ khác mỗi lượt. So chuỗi y hệt thì không bao giờ khớp.

        Bốn mục chặn dưới đây là **nguyên văn** bốn lượt của STORY-01-02
        trên e9 — cùng một chuyện (`fake-indexeddb` không được khai trong
        `package.json`), không cặp nào trùng chữ, nên bộ dò so chuỗi im
        suốt và story đốt hết hạn mức: $10,39.
        """
        from aisef.phases.implement import deadlock_reason

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
                self.assertIn("not in the story's write_scope", ly_do)

    def test_hai_khiem_khuyet_khac_nhau_tren_cung_tep_khong_phai_bi(self):
        """Cùng tệp nhưng khác khiếm khuyết nghĩa là có dịch chuyển."""
        from aisef.phases.implement import deadlock_reason

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
        from aisef.phases.implement import effective_write_scope

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
                if "Review" in spec.prompt:
                    DoiMuc.lan += 1
                    self.review = f"[chặn] src/a.py:1 — khiếm khuyết số {DoiMuc.lan}"
                return super().run(spec)

        DoiMuc.lan = 0
        out = self.implement(DoiMuc(), config=self.config(**{"run.max_retries": 2}))
        self.assertEqual(out.quality_attempts, 3)
        self.assertIn("tried", out.blocked_reason)

    def test_out_of_scope_write_fails_the_gate(self):
        c = ScriptedClient(writes=("src/a.py", "ngoai/pham-vi.py"))
        out = self.implement(c)
        self.assertFalse(out.done)
        self.assertIn("write scope", out.summary())

    def test_feedback_reaches_the_next_attempt(self):
        class Recorder(ScriptedClient):
            prompts: list = []

            def run(self, spec):
                if "Review" not in spec.prompt:
                    Recorder.prompts.append(spec.prompt)
                return super().run(spec)

        Recorder.prompts = []
        self.implement(Recorder(review="[chặn] src/a.py:1 — sai"))
        self.assertGreaterEqual(len(Recorder.prompts), 2)
        self.assertIn("Previous attempt did not pass", Recorder.prompts[1])
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
        self.assertIn("infrastructure", out.blocked_reason)

    def test_classification(self):
        """Vòng thử lại đọc cùng bảng kết cục với evidence (ADR-005 V11 B)."""
        for err in ("api_error", "overloaded", "exceeded 1800s", "Connection lost"):
            self.assertIn(exit_status_of(RunResult(ok=False, error=err)), INFRA_STATUSES, err)
        self.assertNotIn(exit_status_of(RunResult(ok=False, error="test đỏ")), INFRA_STATUSES)

    def test_review_that_cannot_run_is_not_clean(self):
        class NoReview(ScriptedClient):
            def run(self, spec):
                if "Review" in spec.prompt:
                    return RunResult(ok=False, error="hết giờ")
                return super().run(spec)

        out = self.implement(NoReview())
        self.assertFalse(out.done)


class TestFakeTestDetection(ImplementTestCase):
    def test_story_that_writes_an_assertionless_test_is_blocked(self):
        """Mốc demo 7: đẩy một story có test giả → cổng chặn, nêu đúng lý do."""
        out = self.implement(ScriptedClient(writes=("src/tests/test_a.py",)))
        self.assertFalse(out.done)
        self.assertIn("real tests", out.summary())


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
        self.assertIn("does not build any screen", ctx["mockup_section"])

    def test_ban_do_ma_tat_mac_dinh_thi_slot_rong(self):
        """ADR-005 V7: `context.max_repo_map_chars` = 0 cho tới khi A/B có số —
        slot rỗng, bàn giao ghi `repo_map: (code, 0)`."""
        from aisef.phases.implement import handoff_slots

        (self.project / "src").mkdir()
        (self.project / "src" / "a.ts").write_text("export function taoGhiChu() {}\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(),
        )
        self.assertEqual(ctx["repo_map"], "")
        self.assertEqual(handoff_slots(ctx)["repo_map"], ("code", 0))

    def test_ban_do_ma_bat_thi_co_muc_va_ghi_ban_giao(self):
        from aisef.phases.implement import handoff_slots

        (self.project / "src").mkdir()
        (self.project / "src" / "a.ts").write_text("export function taoGhiChu() {}\n", encoding="utf-8")
        (self.project / "lib").mkdir()
        (self.project / "lib" / "b.ts").write_text("taoGhiChu()\n", encoding="utf-8")
        ctx = build_context(
            self.story, project=self.project, artifact_root=self.artifacts,
            architecture=None, contract=None, config=self.config(**{"context.max_repo_map_chars": 2000}),
        )
        self.assertTrue(ctx["repo_map"].startswith("## Code map around write scope"))
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
        self.assertIn("failed", ctx["repo_map"])
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


class TestHetLuotNhungCoViecDeCham(ImplementTestCase):
    """Lỗi 130 (todo-cli STORY-03-02, 2026-09-13, MiniMax-M3). Ba phiên liền
    đụng trần 40 lượt, mỗi phiên đã **commit 68 dòng test** vào worktree, và
    harness không chấm một dòng nào: `if not result.ok: return attempt` nằm
    trước chỗ đóng băng ứng viên. Story tiêu sạch ngân sách chất lượng mà không
    hề có một verdict nào — nên developer lượt sau không có phản hồi, và
    `nop_deadlock` không có gì để đọc. Hết **lượt** không đồng nghĩa với viết mã
    sai; cổng mới là thứ phán xử, cái đếm lượt thì không."""

    class HetLuotNhungCoViet(ScriptedClient):
        """Viết đúng như bình thường rồi báo hết lượt."""

        def run(inner, spec):
            dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
            ra = super().run(spec)
            if dau.startswith("# Review") or dau.startswith("# Security review"):
                return ra
            return RunResult(ok=False, error="max_turns: stopped at 40 turns (cap 40)",
                             num_turns=40, output_tokens=ra.output_tokens,
                             text=ra.text, tool_uses=ra.tool_uses, cost_usd=ra.cost_usd)

    def test_cham_ung_vien_va_qua_duoc_cong(self):
        out = self.implement(self.HetLuotNhungCoViet())
        self.assertIsNotNone(out.attempts[-1].gate, "phải có verdict, không được ném việc đi")
        self.assertTrue(out.done, out.attempts[-1].gate.summary())
        self.assertEqual(out.attempts[-1].error, "",
                         "cổng đã phán xử thì lý do hết lượt không còn là kết cục của lượt")

    def test_ghi_lai_phien_chua_xong_vao_bang_chung(self):
        """Chấm không có nghĩa là xoá dấu: phải đọc lại được rằng phiên hết lượt."""
        from aisef.harness.observe import NOTE, EvidenceStore

        self.implement(self.HetLuotNhungCoViet())
        ghi = EvidenceStore(self.artifacts).read("STORY-01-01").of(NOTE, "session:unfinished")
        self.assertTrue(ghi, "phải ghi lại phiên chưa xong")
        self.assertEqual(ghi[-1].detail["exit_status"], "max_turns")
        self.assertEqual(ghi[-1].detail["turns"], 40)

    def test_het_luot_ma_khong_viet_gi_thi_khong_co_gi_cham(self):
        class HetLuotTay(ScriptedClient):
            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if dau.startswith("# Review") or dau.startswith("# Security review"):
                    return super().run(spec)
                # 40 lượt có gọi tool thật, chỉ là không ghi được gì — khác
                # hẳn "0 tool call" (model không dùng nổi tool, đã có chẩn đoán
                # riêng và là fatal).
                return RunResult(ok=False, error="max_turns: stopped at 40 turns (cap 40)",
                                 num_turns=40, output_tokens=100,
                                 tool_uses=[ToolUse(name="bash", tool_use_id="t1", input={})], cost_usd=0.0)

        out = self.implement(HetLuotTay(), config=self.config(**{"run.max_retries": 0}))
        cuoi = out.attempts[-1]
        self.assertIsNone(cuoi.gate, "cổng không hề chạy")
        # ADR-005 V11 (B), đo trên e9 01-05 (chạm 91/90 hai lần): chạm trần lượt
        # là lỗi **chất lượng**, thử lại phải tính hạn mức — miễn phí thì agent
        # loay hoay vô hạn. Kế toán đúng; chỗ sai là câu đóng story.
        self.assertFalse(cuoi.infra)
        self.assertFalse(cuoi.noop)
        self.assertEqual(out.quality_attempts, 1)
        self.assertIn("nothing to grade", out.blocked_reason)
        self.assertIn("max_turns", out.blocked_reason)
        self.assertNotIn("still did not pass gate", out.blocked_reason,
                         "cổng chưa chạy lần nào thì không được báo là trượt cổng")

    def test_viec_cua_luot_truoc_khong_phai_viec_cua_phien_nay(self):
        """Bản vá đầu của lỗi 130 hỏi `changed_files` — tức diff so với nhánh
        gốc, thứ **cũng** mang commit của các lượt trước. Trên đợt chạy thật nó
        in "max_turns but the session left work in the tree — grading it" ngay
        trước dòng "NO-OP: 40 turns, 0 files written": đúng cái bẫy mà chính
        phép kiểm no-op đã ghi lại. "Có để lại việc" phải là **phiên này** làm
        cây dịch chuyển."""
        class VietRoiHetLuotTay(ScriptedClient):
            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if dau.startswith("# Review") or dau.startswith("# Security review"):
                    return super().run(spec)
                if inner.develop_calls == 0:
                    return super().run(spec)          # lượt 1: có việc, bị cổng đánh trượt
                inner.develop_calls += 1
                return RunResult(ok=False, error="max_turns: stopped at 40 turns (cap 40)",
                                 num_turns=40, output_tokens=500, cost_usd=0.0)

        out = self.implement(VietRoiHetLuotTay(review="[chặn] src/a.py:1 — mất dữ liệu"),
                             config=self.config(**{"run.max_retries": 1,
                                                   "run.infra_retries": 2}))
        from aisef.harness.observe import NOTE, EvidenceStore

        sau = out.attempts[1]
        self.assertIsNone(sau.gate, "phiên không viết gì thì không có gì để chấm")
        ghi = EvidenceStore(self.artifacts).read("STORY-01-01").of(NOTE, "session:unfinished")
        self.assertFalse(ghi[-1].detail["moved_tree"],
                         "việc của lượt trước không phải việc của phiên này")

    def test_loi_ha_tang_van_tra_ve_ngay_khong_cham(self):
        """Nhà cung cấp cắt phiên thì lượt thử lại không tốn ngân sách chất
        lượng và lượt sau chấm đúng cây ấy — đóng băng ở đây chỉ thêm một verdict
        cho một cây sắp bị viết tiếp."""
        class BiCatNhungCoViet(ScriptedClient):
            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                ra = super().run(spec)
                if dau.startswith("# Review") or dau.startswith("# Security review"):
                    return ra
                return RunResult(ok=False, error="api_error 502", num_turns=5,
                                 output_tokens=ra.output_tokens, tool_uses=ra.tool_uses,
                                 cost_usd=0.0)

        out = self.implement(BiCatNhungCoViet(),
                             config=self.config(**{"run.max_retries": 0,
                                                   "run.infra_retries": 1}))
        self.assertTrue(all(a.gate is None for a in out.attempts))
        self.assertTrue(out.attempts[-1].infra)


class TestBeTacDoKeHoachTheoNopControl(unittest.TestCase):
    """Lỗi 126 (todo-cli STORY-03-02, 2026-09-13). Bốn tiêu chí của story đã
    được STORY-03-01 làm xong từ sóng trước. `tests verify story` đỏ hai lượt
    liền với **đúng** bốn mã ấy — không test nào developer viết ra có thể đỏ ở
    điểm rẽ cho hành vi đã nằm sẵn trên nhánh chính. Developer nhận ra và viết
    0 dòng, đúng; harness đọc thành phiên no-op, tiêu sạch ngân sách hạ tầng
    mở lại nó sáu lần, rồi báo "sessions kept producing nothing to grade" —
    một lỗi kế hoạch mô tả thành lỗi client."""

    def _luot(self, ma, *, infra=False):
        from aisef.control.gate import StoryGate
        from aisef.control.outcome import Check, Outcome
        from aisef.phases.implement import Attempt
        g = StoryGate(story_id="STORY-03-02")
        g.checks.append(Check("tests verify story", Outcome.FAILED,
                              "tests verify nothing — still green without story code "
                              f"(parent SHA a25a56d): {', '.join(m + ': x' for m in ma)}"))
        a = Attempt(number=1)
        a.gate = g
        a.infra = infra
        return a

    def test_hai_luot_cung_bo_ma_la_be_tac_ke_hoach(self):
        from aisef.phases.implement import nop_deadlock
        ma = ["AC-STORY-03-02-1", "AC-STORY-03-02-2"]
        ly_do = nop_deadlock([self._luot(ma), self._luot(ma)])
        self.assertIn("already satisfied at the branch point", ly_do)
        for m in ma:
            self.assertIn(m, ly_do)
        self.assertIn("fix the criteria or drop the story", ly_do)

    def test_bo_ma_doi_thi_chua_ket_luan(self):
        """Developer sửa được: lượt sau đỏ ở tiêu chí khác nghĩa là có tiến bộ."""
        from aisef.phases.implement import nop_deadlock
        self.assertEqual(nop_deadlock([self._luot(["AC-STORY-03-02-1", "AC-STORY-03-02-2"]),
                                       self._luot(["AC-STORY-03-02-2"])]), "")

    def test_mot_luot_thi_chua_ket_luan(self):
        from aisef.phases.implement import nop_deadlock
        self.assertEqual(nop_deadlock([self._luot(["AC-STORY-03-02-1"])]), "")

    def test_luot_ha_tang_khong_tinh(self):
        """Phiên bị cắt không chấm gì; xen vào giữa không được xoá dấu vết
        của hai lượt đã chấm."""
        from aisef.phases.implement import nop_deadlock
        ma = ["AC-STORY-03-02-1"]
        ly_do = nop_deadlock([self._luot(ma), self._luot([], infra=True), self._luot(ma)])
        self.assertIn("already satisfied", ly_do)

    def test_mot_luot_cham_roi_hai_phien_khong_lam_gi_cung_du(self):
        """Lỗi 127, STORY-05-02: chỉ **một** lượt được chấm ra verdict ấy, rồi
        developer từ chối viết — năm phiên liền. Chính sự từ chối là dữ liệu thứ
        hai: đó là cách duy nhất developer nói được "việc này xong rồi". Bản vá
        126 đòi hai lượt được chấm nên trượt ca này, cùng một lỗi kế hoạch mà
        hai kết cục khác nhau."""
        from aisef.phases.implement import Attempt, nop_deadlock
        def khong_lam():
            a = Attempt(number=1); a.infra = True; a.noop = True
            return a
        ma = ["AC-STORY-05-02-1", "AC-STORY-05-02-2"]
        ly_do = nop_deadlock([self._luot(ma), khong_lam(), khong_lam()])
        self.assertIn("already satisfied at the branch point", ly_do)
        for m in ma:
            self.assertIn(m, ly_do)

    def test_mot_phien_khong_lam_gi_thi_chua_du(self):
        """Một lần có thể là phiên xui; hai lần là quyết định."""
        from aisef.phases.implement import Attempt, nop_deadlock
        a = Attempt(number=1); a.infra = True; a.noop = True
        self.assertEqual(nop_deadlock([self._luot(["AC-STORY-05-02-1"]), a]), "")

    def test_dem_no_op_lien_tiep(self):
        from aisef.phases.implement import Attempt, MAX_NOOP, _noop_lien_tiep
        def khong_lam():
            a = Attempt(number=1); a.infra = True; a.noop = True
            return a
        def bi_cat():
            a = Attempt(number=1); a.infra = True
            return a
        self.assertEqual(MAX_NOOP, 2)
        self.assertEqual(_noop_lien_tiep([khong_lam(), khong_lam()]), 2)
        # Phiên bị cắt **ngắt** chuỗi: nó có việc đang dở, không phải quyết định.
        self.assertEqual(_noop_lien_tiep([khong_lam(), bi_cat()]), 0)
        self.assertEqual(_noop_lien_tiep([khong_lam(), bi_cat(), khong_lam()]), 1)
        self.assertEqual(_noop_lien_tiep([]), 0)

    def test_truot_vi_ly_do_khac_thi_khong_ket_luan(self):
        from aisef.control.gate import StoryGate
        from aisef.control.outcome import Check, Outcome
        from aisef.phases.implement import Attempt, nop_deadlock
        def khac():
            g = StoryGate(story_id="S")
            g.checks.append(Check("security", Outcome.FAILED, "1 blocking items"))
            a = Attempt(number=1); a.gate = g
            return a
        self.assertEqual(nop_deadlock([khac(), khac()]), "")


class TestSlotDaChungMinh(unittest.TestCase):
    """Lỗi 124 (todo-cli STORY-01-01, 2026-09-13). Người rà soát bảo mật chặn
    ba lượt liền với "lstatSync nuốt ENOENT nên phép kiểm symlink không bao giờ
    chạy" — trong khi ứng viên mang sẵn `AC-STORY-01-01-4: save refuses to write
    to broken symlink target` **đang xanh**, và `lstat` trên symlink gãy không
    ném ENOENT (đo bằng node: `isSymbolicLink() === true`). Story chết vì một
    khẳng định mà một câu lệnh bác bỏ được, và người rà soát không hề biết có
    test ấy: slot `validation` gửi cho nó là "(standard gate only)"."""

    def _story(self, n=4):
        from aisef.control.normalize import Story
        return Story(id="STORY-01-01", epic_id="EPIC-01", title="t",
                     acceptance_criteria=[f"tiêu chí {i}" for i in range(1, n + 1)])

    def _ev(self, events):
        from aisef.harness.observe import Evidence
        return Evidence(story_id="STORY-01-01", events=events)

    def _run(self, **detail):
        from aisef.harness.observe import Event
        return Event(kind="tool_run", name="test", ok=detail.pop("ok", True), detail=detail)

    def test_liet_ke_test_xanh_mang_ma_tieu_chi(self):
        from aisef.phases.implement import proven_text
        ev = self._ev([self._run(candidate="aaa", test_ids=[
            "AC-STORY-01-01-4: save refuses to write to broken symlink target",
            "AC-STORY-01-01-1: load returns empty array",
            "khong mang ma",
        ], failed_ids=[])])
        ra = proven_text(ev, self._story(), candidate="aaa", max_chars=1500)
        self.assertIn("AC-STORY-01-01-4", ra)
        self.assertIn("broken symlink target", ra)
        self.assertNotIn("khong mang ma", ra)

    def test_test_do_hoac_bo_qua_khong_phai_da_chung_minh(self):
        from aisef.phases.implement import proven_text
        ev = self._ev([self._run(candidate="aaa", ok=False,
                                 test_ids=["AC-STORY-01-01-4: x"], failed_ids=["AC-STORY-01-01-4: x"])])
        self.assertIn("no green test run", proven_text(ev, self._story(), candidate="aaa", max_chars=1500))
        ev = self._ev([self._run(candidate="aaa", test_ids=["AC-STORY-01-01-4: x"],
                                 failed_ids=[], skipped_ids=["AC-STORY-01-01-4: x"])])
        self.assertIn("no green test carries a criterion code",
                      proven_text(ev, self._story(), candidate="aaa", max_chars=1500))

    def test_lan_chay_o_ung_vien_khac_khong_duoc_tinh(self):
        """Cùng luật ADR-004 R1 như cổng: bằng chứng của bản khác không chấm
        bản này — và cũng không được dùng để bảo người rà soát yên tâm."""
        from aisef.phases.implement import proven_text
        ev = self._ev([self._run(candidate="bbb", test_ids=["AC-STORY-01-01-4: x"], failed_ids=[])])
        self.assertIn("no green test run", proven_text(ev, self._story(), candidate="aaa", max_chars=1500))

    def test_runner_khong_in_ten_thi_noi_thang(self):
        from aisef.phases.implement import proven_text
        ev = self._ev([self._run(candidate="aaa", test_ids=[], failed_ids=[])])
        self.assertIn("printed no test names", proven_text(ev, self._story(), candidate="aaa", max_chars=1500))

    def test_ca_hai_vai_ra_soat_deu_nhan_slot(self):
        from aisef.phases.implement import SLOT_SOURCE
        self.assertEqual(SLOT_SOURCE["proven"], "evidence")
        from aisef.phases.implement import load_catalog

        cat = load_catalog()
        for ten in ("story-review", "story-security-review"):
            with self.subTest(prompt=ten):
                self.assertIn("proven", cat.get(ten).slots)


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

    def test_the_van_ban_giua_dong_van_la_muc_chan(self):
        """Lỗi 16 giữ nguyên: thẻ dán liền vào chữ trước nó vẫn là mục chặn."""
        found = blocking_findings(
            "...whether each test can detect regressions.[block] tests/todo.spec.js:217 "
            "— assertion never fails")
        self.assertEqual(len(found), 1)
        self.assertIn("todo.spec.js:217", found[0])

    def test_nhac_the_giua_van_xuoi_khong_phai_muc_chan(self):
        """Lỗi 141 (todo-oc STORY-04-02, 2026-09-13): khối JSON khai **2** mục
        chặn, trình đọc văn bản đếm **29** — cổng in "29 blocking items" và
        developer lượt sau nhận đúng hai vấn đề ấy mười bốn lần. Người rà soát
        cân nhắc dài thì nhắc thẻ giữa câu ("This is a [block].", "I'll keep the
        [block] tag"), và nhắc lại kết luận ở mỗi phần tóm tắt.

        Phân biệt bằng **hình dạng prompt đã quy định**: `[tag] path:line — mô
        tả`. Có đường dẫn là mục; không có là đang nói *về* thẻ."""
        for van_xuoi in ("This is a **[block]** — the AC literally says non-whitespace.",
                         "I'll mark it as a [block] finding.",
                         "So the [block] tag is fine for this review.",
                         "- [block] because: the rule is grouped."):
            with self.subTest(dong=van_xuoi):
                self.assertEqual(blocking_findings(van_xuoi), [])

    def test_dung_hinh_dang_thi_van_la_muc_chan(self):
        for dong in ("[block] index.html:171-176 — two selectors share one rule",
                     "- [block] lib/store.js:83 — wrong syscall in the rethrow",
                     "**[block] tests/sit/a.test.js:53** — regex has no anchor",
                     "…detect regressions.[block] tests/todo.spec.js:217 — never fails"):
            with self.subTest(dong=dong):
                self.assertEqual(len(blocking_findings(dong)), 1, dong)

    def test_stuck_khong_can_duong_dan(self):
        """`[stuck]` là kết luận về **kế hoạch** — không có tệp nào để trỏ."""
        found = blocking_findings(
            "[stuck] the criteria cannot be met from inside this story's write scope")
        self.assertEqual(len(found), 1)

    def test_nhac_lai_cung_mot_muc_la_mot_muc(self):
        from aisef.phases.implement import _gop_trung
        lap = ["[block] index.html:171 — same rule",
               "[block] index.html:171 — same rule, restated in the summary",
               "[block] index.html:587 — another one"]
        self.assertEqual(len(_gop_trung(lap)), 2)

    def test_hai_muc_khong_co_vi_tri_van_la_hai(self):
        from aisef.phases.implement import _gop_trung
        self.assertEqual(len(_gop_trung(["[stuck] criteria A cannot be met",
                                         "[stuck] criteria B contradicts AD-3"])), 2)

    def test_the_trong_dau_nguoc_la_nhac_ten_khong_phai_neu_ra(self):
        """Lỗi 122 (todo-cli 2026-09-13). Hai câu thật, hai story trượt:

        * người rà soát nghĩ thành tiếng — "whether this is a `[block]` or
          `[should fix]`:" — bị đếm thành mục chặn;
        * người rà soát nhắc lại lượt trước — "The `[block]` item from the
          previous review (lib/store.js:83) persists" — trong khi khối JSON
          của **chính** lượt ấy khai `verdict: pass`, không mục chặn nào.

        Trong dấu nháy ngược là **gọi tên** thẻ, không phải giương nó lên.
        Mục chặn thật vẫn tới cổng qua khối JSON (hợp nhất hai nguồn)."""
        self.assertEqual(blocking_findings(
            "Now let me think about whether this is a `[block]` or `[should fix]`:"), [])
        self.assertEqual(blocking_findings(
            "The `[block]` item from the previous review (lib/store.js:83) persists — "
            "the syscall is still `open` when the failure is in `rename`."), [])
        self.assertEqual(blocking_findings("Đây là `[chặn]` hay `[nên sửa]`?"), [])


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
                              capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()

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
                tep.write_text("x = 1\n", encoding="utf-8")
                for cmd in (["git", "add", "len-thang-trunk.py"],
                            ["git", "commit", "-q", "-m", "lạc"]):
                    subprocess.run(cmd, cwd=self.project, check=True)
            return RunResult(ok=True, text="xong")

    def test_doi_nhanh_chinh_thi_luot_chay_that_bai(self):
        truoc = self.head()
        out = self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        self.assertFalse(out.done)
        self.assertIn("main branch moved during this session", out.attempts[0].error)
        self.assertNotEqual(self.head(), truoc)

    class CommitNgoaiStory(ScriptedClient):
        """Người vận hành commit **artifact của harness** trong lúc phiên chạy."""

        def __init__(self, project, **kw):
            super().__init__(**kw)
            self.project = project

        def build_command(self, spec):
            return ["true"]

        def run(self, spec: RunSpec):
            d = self.project / "_bmad-output"
            d.mkdir(exist_ok=True)
            tep = d / "ghi-chu.json"
            if not tep.exists():
                tep.write_text("{}\n", encoding="utf-8")
                for cmd in (["git", "add", "-f", "_bmad-output/ghi-chu.json"],
                            ["git", "commit", "-q", "-m", "chore: state"]):
                    subprocess.run(cmd, cwd=self.project, check=True)
            return RunResult(ok=True, text="xong")

    def test_commit_ngoai_story_khong_bi_bao_la_agent_thoat_worktree(self):
        """Lỗi 135, gặp thật ngày 2026-09-13 trên `todo-oc`: người vận hành
        commit `_bmad-output/` giữa lúc phiên chạy, và harness bảo "revert" —
        tức bảo họ vứt chính commit của mình. Ai làm nhánh chính dịch chuyển
        quyết định phải làm gì, và hai câu trả lời ngược nhau; cây nói ai."""
        out = self.implement(self.CommitNgoaiStory(self.project), workdir=self.workdir)
        loi = out.attempts[0].error
        self.assertIn("main branch moved during this session", loi)
        self.assertIn("_bmad-output/", loi)
        self.assertIn("commit made outside the story", loi)
        self.assertNotIn("Revert and re-run", loi)

        ev = EvidenceStore(self.artifacts).read(self.story.id)
        muc = [e for e in ev.events if e.name == "isolation"][-1]
        self.assertTrue(muc.detail["harness_only"])

    def test_ghi_vao_bang_chung_de_ve_sau_truy_duoc(self):
        self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        muc = [e for e in ev.events if e.name == "isolation"]
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
        self.assertEqual([e for e in ev.events if e.name == "isolation"], [])
        self.assertNotIn("main branch moved during this session", out.attempts[0].error or "")

    def test_chay_thang_trong_du_an_thi_khong_kiem(self):
        """`--no-isolate` là cố ý làm việc trên thân cây; kiểm ở đó sẽ
        chặn mọi lượt chạy hợp lệ."""
        out = self.implement(self.PhaCachLy(self.project), workdir=self.project)
        self.assertNotIn("main branch moved during this session", out.attempts[0].error or "")


class TestCachLyVoLaDungHan(TestCachLyThanCay):
    def test_khong_thu_lai_khi_cach_ly_da_vo(self):
        """Worktree của lượt sau rẽ từ thân cây đã bẩn — thử lại chỉ tiêu
        thêm tiền và làm hỏng sâu hơn."""
        out = self.implement(self.PhaCachLy(self.project), workdir=self.workdir)
        self.assertEqual(len(out.attempts), 1)
        self.assertIn("main branch moved during this session", out.blocked_reason)


class TestVaiRaSoatKhaiToolBiCam(ImplementTestCase):
    """Cấm tool theo vai phải tới được guard — tức phải nằm trong `spec.env`,
    không chỉ trong `spec.disallowed_tools` (cờ mà OpenCode bỏ qua)."""

    def test_reviewer_va_security_khai_tool_bi_cam(self):
        client = ScriptedClient()
        self.implement(client)
        self.assertTrue(client.review_envs, "phải có phiên rà soát")
        self.assertTrue(client.security_envs, "phải có phiên bảo mật")
        for env in client.review_envs + client.security_envs:
            self.assertEqual(env.get("AISEF_DISALLOWED_TOOLS"), "Write,Edit,NotebookEdit")

    def test_developer_khong_bi_cam(self):
        client = ScriptedClient()
        self.implement(client)
        dev = [e for e in client.envs if e.get("AISEF_STORY_ID")]
        self.assertTrue(dev)
        for env in dev:
            self.assertNotIn("AISEF_DISALLOWED_TOOLS", env)

    def test_security_van_khong_mang_ma_story(self):
        """Mã story kích hoạt guard `completion` — người rà soát bảo mật
        không được mang nó, dù nay có env."""
        client = ScriptedClient()
        self.implement(client)
        for env in client.security_envs:
            self.assertNotIn("AISEF_STORY_ID", env)
            self.assertIn("AISEF_WRITE_SCOPE", env)


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
        """`guards_wired` phải thật: kỳ vọng đọc từ đó, không từ
        `blocks_at_source` — một client có 9/10 guard chặn tại nguồn vẫn phải
        để lại dấu vết (lỗi 121)."""
        import json
        (self.artifacts / "compile-report.json").write_text(json.dumps({
            "clients": [{"client": client_id, "written": [],
                         "guards_wired": ["write-scope"] if blocks else [],
                         "guards_post_hoc": [], "blocks_at_source": blocks,
                         "degradations": []}]}), encoding="utf-8")

    def muc(self, out):
        return next(c for c in out.attempts[-1].gate.checks if c.name == "guard ran")

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
            if spec.env.get("AISEF_STORY_ID"):
                # the guard hook runs inside the session and stamps it (control/identity.py, SS-02): a trace
                # that names no session proves nothing about the session that produced the candidate
                from aisef.control.identity import EvidenceIdentity
                who = EvidenceIdentity(story_id=spec.env["AISEF_STORY_ID"], session_id=spec.env.get("AISEF_SESSION_ID", ""),
                                       attempt=int(spec.env.get("AISEF_ATTEMPT") or 0))
                EvidenceStore(self.artifacts, identity=who).file_change(spec.env["AISEF_STORY_ID"], "src/a.py")
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
            if dau.startswith("# Review") and not dau.startswith("# Security review"):
                (Path(spec.workdir) / "src" / "reviewer-da-ghi.py").write_text("x\n", encoding="utf-8")
            return r

    class SecurityGhi(ScriptedClient):
        def run(self, spec):
            r = super().run(spec)
            if spec.prompt.lstrip().startswith("# Security review"):
                (Path(spec.workdir) / "src" / "a.py").write_text("bi sua\n", encoding="utf-8")
            return r

    def _init_git(self):
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.project, check=True)

    def test_reviewer_ghi_tep_moi_thi_hoan_nguyen_va_khong_tinh(self):
        self._init_git()
        out = self.implement(self.ReviewerGhi())
        self.assertFalse((self.project / "src" / "reviewer-da-ghi.py").exists(), "phải hoàn nguyên")
        # D-032: một phiên rà soát tự sửa cây là phiên **không chạy được** — thử
        # lại giai đoạn rà soát trên đúng ứng viên (có giới hạn), không phải một
        # mục chặn của người rà soát và không mở lại developer.
        self.assertIn("modified the working tree", out.attempts[-1].review_unrunnable)
        self.assertEqual(out.attempts[-1].review_findings, [])
        self.assertIn("REVIEW_UNRUNNABLE", out.blocked_reason)
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        self.assertTrue(any(e.name == "review:immutable" and not e.ok for e in ev.events))

    def test_security_sua_tep_co_san_thi_hoan_nguyen(self):
        self._init_git()
        out = self.implement(self.SecurityGhi())
        # src/a.py do developer giả viết ("x = 1"); security sửa → phải về như cũ
        noi_dung = (self.project / "src" / "a.py").read_text(encoding="utf-8")
        self.assertTrue(noi_dung.startswith("x = 1\n"), noi_dung)
        self.assertNotIn("bi sua", noi_dung, "phải hoàn nguyên bản security đã ghi đè")
        self.assertIn("modified the working tree", out.attempts[-1].security.error)

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
        from aisef.harness.observe import HANDOFF
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
        from aisef.harness.guardrails import ENV_PROJECT

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


from aisef.control.outcome import Outcome  # noqa: E402
from aisef.harness.guardrails import head_sha  # noqa: E402
from aisef.harness.observe import TOOL_RUN  # noqa: E402


class TestBaselineTruocKhiSua(ImplementTestCase):
    """ADR-004 R9. Harness chạy bộ test **trước** phiên developer và ghi tên
    test; cổng so với lần test ở ứng viên để gọi đúng tên hồi quy trong lượt.

    "Bộ test" giả là một lệnh in output dạng `pytest -v` từ `src/ket-qua.txt`
    — tệp mà developer giả ghi đè, nên kết quả đổi theo lượt như test thật.
    """

    LENH = 'sh -c "cat src/ket-qua.txt; ! grep -q FAILED src/ket-qua.txt"'
    TEN = "no baseline regression"

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
                # Mỗi phiên developer để lại dấu riêng: kịch bản này cố ý cho
                # ra **cùng** kết quả test ở mọi lượt, mà ghi lại y hệt thì
                # harness gọi đúng tên là "phiên không viết gì" (lỗi 68) và
                # không chấm nữa — lượt thử lại sẽ biến mất khỏi phép đo.
                (Path(spec.workdir) / "src" / "luot.txt").write_text(
                    str(self.develop_calls), encoding="utf-8")
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
        self.assertIn("lost 1 test", m.detail)
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
        self.assertIn("no baseline", m.detail)


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

    TEN = "tests verify story"
    AC = "tests/test_ac.py::test_AC_STORY_01_01_1"
    THAT = ('import os\nprint("%s " + ("PASSED" if os.path.exists("src/a.py") else "FAILED"))\n' % AC)
    GIA = 'print("%s PASSED")\n' % AC

    #: Runner: run every `tests/test_*.py` in the worktree and print their
    #: lines like `pytest -v`. Written in Python, not `sh -c` — Windows has no
    #: `sh`, so this whole class only ever ran on POSIX.
    RUNNER = (
        "import glob, subprocess, sys\n"
        'print("test session starts")\n'
        "out = []\n"
        'for f in sorted(glob.glob("tests/test_*.py")):\n'
        "    out.append(subprocess.run([sys.executable, f], capture_output=True,\n"
        "                              text=True).stdout.strip())\n"
        'text = "\\n".join(x for x in out if x)\n'
        "print(text)\n"
        'sys.exit(1 if "FAILED" in text else 0)\n'
    )

    def setUp(self):
        super().setUp()
        from aisef.clients.base import quote_command

        self._ngoai = tempfile.TemporaryDirectory()
        runner = Path(self._ngoai.name) / "runner.py"     # outside the repo: not a change
        runner.write_text(self.RUNNER, encoding="utf-8")
        self.LENH = quote_command([sys.executable, str(runner)])
        self.addCleanup(self._ngoai.cleanup)
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
                p = Path(spec.workdir) / "tests" / "test_ac.py"
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
        self.assertIn("red or absent", m.detail)
        nop = self.evidence().last(TOOL_RUN, "test:nop")
        self.assertEqual(nop.detail["candidate"], out.attempts[-1].candidate)
        self.assertEqual(nop.detail["files"], ["tests/test_ac.py"])
        self.assertEqual(nop.detail["parent"], head_sha(self.project))
        self.assertIn(self.AC, nop.detail["failed_ids"])
        self.assertFalse((self.project / ".aisef" / "worktrees" / "STORY-01-01-nop").exists())
        nhanh = subprocess.run(["git", "branch", "--list", "story/STORY-01-01-nop"],
                               cwd=self.project, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        self.assertEqual(nhanh.strip(), "", "nhánh tạm phải được xoá")

    def test_test_luon_xanh_la_khong_kiem_duoc_gi_neu_ten(self):
        out = self.chay(self.GIA)
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("still green without story code", m.detail)
        self.assertIn(self.AC, m.detail)
        self.assertFalse(out.done)

    def test_khong_them_test_thi_khong_ap_dung_va_khong_dung_gi(self):
        out = self.chay(None)
        m = self.muc(out)
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("did not add/modify", m.detail)
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
        self.assertIn("parent SHA", m.detail)

    def test_gate_input_ghi_ngay_truoc_verdict_va_replay_ra_cung_ket_cuc(self):
        """ADR-005 V4: đầu vào cổng nằm trong bằng chứng; replay bằng luật hiện
        tại cho đúng mục chặn đã ghi."""
        from aisef.control import replay as R

        out = self.chay(self.GIA)
        ev = self.evidence()
        vao, ra = ev.last(NOTE, "gate:input"), ev.last(NOTE, "gate:verdict")
        self.assertEqual(ra.seq, vao.seq + 1, "đầu vào ghi ngay trước phán quyết")
        self.assertEqual(vao.detail["attempt"], ra.detail["attempt"])
        for k in ("changed", "write_scope", "screens", "contract", "review_blocking", "security",
                  "block_severities", "guard_expected", "acceptance", "coverage_min",
                  "added_tests", "candidate", "preservation"):
            self.assertIn(k, vao.detail, k)
        self.assertEqual(vao.detail["candidate"], out.attempts[-1].candidate)
        self.assertEqual(vao.detail["added_tests"], ["tests/test_ac.py"])
        [r] = R.replay(ev)
        self.assertEqual(r.now, ra.detail["failures"])
        self.assertEqual(r.changed(), [])



class TestBanDoKeHoachChoNguoiRaSoat(ImplementTestCase):
    """Lỗi 58, nửa dữ liệu: người rà soát phải **thấy** kế hoạch thì lời dặn
    "yêu cầu thuộc story khác thì im lặng" mới kiểm chứng được. Chỉ mục bằng
    chứng không dùng được cho việc này — nó bó trong một epic và **rỗng** trên
    dự án mới, đúng lúc cần nhất."""

    def roadmap(self):
        from aisef.phases.implement import _roadmap
        return _roadmap(self.story, self.artifacts, self.config())

    def viet_index(self, n=14):
        import json
        (self.artifacts / "stories.index.json").write_text(json.dumps({"stories": [
            {"id": f"STORY-{i // 3 + 1:02d}-{i % 3 + 1:02d}", "title": f"việc {i}"}
            for i in range(n)
        ]}), encoding="utf-8")

    def test_liet_ke_moi_story_ke_ca_epic_khac(self):
        self.viet_index()
        text = self.roadmap()
        self.assertIn("STORY-05-02", text, text)          # epic khác hẳn
        self.assertEqual(text.count("\n") + 1, 14)

    def test_danh_dau_story_dang_ra_soat(self):
        import json
        (self.artifacts / "stories.index.json").write_text(json.dumps({"stories": [
            {"id": self.story.id, "title": "vỏ ứng dụng"},
            {"id": "STORY-02-01", "title": "tạo task"},
        ]}), encoding="utf-8")
        text = self.roadmap()
        self.assertIn("← the story under review", text)
        self.assertTrue(text.splitlines()[0].endswith("← the story under review"), text)

    def test_khong_co_chi_muc_thi_noi_ra_chu_khong_de_trong(self):
        self.assertIn("no story index", self.roadmap())


class TestLuotBiNgatGiuLaiLoiRaSoat(ImplementTestCase):
    """Lỗi 66. `feedback` là biến cục bộ của vòng thử lại nên chết theo tiến
    trình; bằng chứng thì không. Story chạy lại sau khi bị ngắt mở lại ở lượt
    1 với lời chặn của người rà soát nằm im trong `evidence`, tác giả nộp lại
    đúng bản đã bị từ chối, người rà soát nêu lại đúng mục ấy — mất một lượt
    trong ngân sách chỉ vì bị ngắt (todo-e2e/STORY-01-02 10/09)."""

    def setUp(self):
        super().setUp()
        for cmd in (["git", "config", "user.email", "t@t.t"],
                    ["git", "config", "user.name", "T"],
                    ["git", "commit", "-q", "--allow-empty", "-m", "nen"]):
            subprocess.run(cmd, cwd=self.project, check=True)

    def _head(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project,
                              capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()

    def _ghi(self, sha: str, findings: list[str]) -> None:
        # the reviewer's verdict is recorded as `reviewer:verdict` — `NOTE review` was never written by the
        # kernel, which is why the reader stayed dead until F1 (SS-04)
        EvidenceStore(self.artifacts, candidate=sha).record("STORY-01-01", Event(
            kind=NOTE, name="reviewer:verdict", ok=not findings,
            detail={"verdict": "block" if findings else "pass", "findings": findings, "attempt": 2}))

    def test_muc_chan_con_lai_duoc_giao_lai_cho_luot_dau(self):
        self._ghi(self._head(), ["[block] tests/a.spec.js:217 — không chạm JSON.stringify"])
        fb = _unfinished_review(self.artifacts, "STORY-01-01", self.project)
        self.assertIn("tests/a.spec.js:217", fb)
        self.assertIn("still blocking", fb)

    def test_ban_khac_thi_khong_giao_lai(self):
        """Cây dựng lại từ gốc không mang bản mà lời chặn nói tới."""
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "khac"],
                       cwd=self.project, check=True)
        self._ghi("0" * 40, ["[block] tests/a.spec.js:217 — không chạm JSON.stringify"])
        self.assertEqual(_unfinished_review(self.artifacts, "STORY-01-01", self.project), "")

    def test_lan_dau_chay_thi_khong_co_gi(self):
        self.assertEqual(_unfinished_review(self.artifacts, "STORY-01-01", self.project), "")

    def test_luot_truoc_qua_ra_soat_thi_khong_giao_lai(self):
        self._ghi(self._head(), [])
        self.assertEqual(_unfinished_review(self.artifacts, "STORY-01-01", self.project), "")


class TestLuotKhongVietGiThiKhongPhaiUngVien(ImplementTestCase):
    """Lỗi 68. `changed_files` đo với `base_ref`, nên ở lượt thử lại nó mang
    theo việc của lượt trước: một phiên viết **0 tệp** trông y như một phiên
    viết 2 tệp. `todo-e2e` STORY-02-01 10/09: agent chạy 7 turn, sửa 0 dòng,
    harness vẫn đóng băng ứng viên rồi trả tiền cho cả verify + review +
    security trên đúng cái cây nó vừa rà soát xong — và tính cho story một
    lượt."""

    class ImLang(ScriptedClient):
        """Lượt 1 viết code; từ lượt 2 trở đi không đụng vào tệp nào."""

        def __init__(self, **kw):
            super().__init__(**kw)
            self.develop_turns = 0

        def run(self, spec):
            dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
            if not dau.startswith("# Review") and not dau.startswith("# Security review"):
                self.develop_turns += 1
                if self.develop_turns > 1:
                    self.calls.append("develop")
                    return RunResult(ok=True, text="đã xem, không cần sửa", cost_usd=0.4,
                                     num_turns=7, output_tokens=1616)
            return super().run(spec)

    def setUp(self):
        super().setUp()
        for cmd in (["git", "config", "user.email", "t@t.t"],
                    ["git", "config", "user.name", "T"],
                    ["git", "commit", "-q", "--allow-empty", "-m", "nen"]):
            subprocess.run(cmd, cwd=self.project, check=True)
        from aisef.control.worktree import WorktreeManager
        self.tree = WorktreeManager(self.project).create(self.story.id)

    def so_lan_ra_soat(self) -> int:
        """Số **ứng viên** đã được rà soát — không phải số lần gọi client: một
        bản rà soát thiếu khối JSON bị hỏi lại đúng một lần (SCHEMA_REMINDER),
        nên đếm lời gọi sẽ đếm đôi."""
        return len(EvidenceStore(self.artifacts).read(self.story.id).of(TOOL_RUN, "review"))

    def chay(self, client):
        return implement_story(
            self.story, project=self.project, workdir=self.tree.path,
            artifact_root=self.artifacts, client=client, config=self.config())

    def test_khong_ra_soat_lai_cay_y_het_va_khong_tinh_luot(self):
        # Both writes inside the write scope: an out-of-scope write would be restored by retry hygiene before
        # attempt 2, and a tree that hygiene changed is legitimately re-graded (D-035 / INV-E.1) — that is not
        # the "identical tree" this test is about.
        client = self.ImLang(writes=("src/a.py", "src/b.py"),
                             review="[chặn] src/a.py:1 — thiếu kiểm tra")
        report = self.chay(client)
        self.assertEqual(self.so_lan_ra_soat(), 1,
                         "cây không đổi thì không có gì mới để rà soát")
        im = [a for a in report.attempts if "wrote nothing" in a.error]
        self.assertTrue(im, "phải nói thẳng phiên đã không viết gì")
        self.assertTrue(im[0].infra, "story chưa từng được chấm thì đừng tính lượt của nó")
        # Lỗi 102: tính như `infra` là đúng về **kế toán**, nhưng lý do đưa
        # cho người đọc không được nói đây là lỗi hạ tầng.
        self.assertTrue(im[0].noop)
        self.assertNotIn("infrastructure", report.blocked_reason)
        if report.blocked_reason:
            self.assertIn("nothing to grade", report.blocked_reason)

    def test_luot_dau_im_lang_cung_khong_phai_ung_vien(self):
        """`todo-e2e` STORY-03-01 10/09: im lặng ngay **lượt đầu** — chưa có
        việc của lượt trước nên diff rỗng, phép chẩn cũ đòi `tool_uses == 0`
        nên không nổ, và cổng vẫn chạy: 4 mục đỏ cho **một** nguyên nhân, mở
        đầu bằng "guard did not evaluate any write … hook cannot reach
        worktree?" — đẩy người đọc đi tìm một lỗi hook không tồn tại."""

        class ImNgayTuDau(ScriptedClient):
            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if not dau.startswith("# Review") and not dau.startswith("# Security review"):
                    inner.calls.append("develop")
                    # Có gọi công cụ (đọc code) nhưng không ghi gì — khác hẳn
                    # ca "0 tool call" mà phép chẩn zero-output đã bắt.
                    return RunResult(ok=True, text="không có gì để sửa", cost_usd=0.4,
                                     num_turns=7, output_tokens=870,
                                     tool_uses=[ToolUse(name="Read", tool_use_id="t1", input={})])
                return super().run(spec)

        client = ImNgayTuDau()
        report = self.chay(client)
        self.assertEqual(self.so_lan_ra_soat(), 0, "không viết gì thì không có gì để rà soát")
        self.assertEqual(client.calls.count("security"), 0)
        self.assertTrue(all(a.infra for a in report.attempts), report.summary())
        self.assertIn("main branch", report.attempts[0].error,
                      "phải chỉ chỗ đáng nghi khi diff rỗng ngay từ đầu")

    def test_cay_chua_ai_cham_thi_van_phai_cham_du_phien_im_lang(self):
        """Lỗi 70 — do chính bản vá 68/69 đẻ ra. Kết luận của cổng **không**
        chỉ phụ thuộc vào cây: nó còn đọc bản đặc tả. `todo-e2e` STORY-03-01
        10/09: người rà soát chặn `[stuck]` vì AD-9 mâu thuẫn với một tiêu chí
        đã duyệt; AD-9 được sửa, worktree hợp nhất bản sửa, agent viết 0 dòng
        vì **việc đã xong**. Bỏ qua ở đây là chôn việc đã làm dưới câu "biết
        rồi": story cạn ngân sách infra rồi BLOCKED trong khi code đã sẵn."""

        class KhongBaoGioViet(ScriptedClient):
            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if not dau.startswith("# Review") and not dau.startswith("# Security review"):
                    inner.calls.append("develop")
                    return RunResult(ok=True, text="việc đã xong", cost_usd=0.4,
                                     num_turns=14, output_tokens=900,
                                     tool_uses=[ToolUse(name="Read", tool_use_id="t1", input={})])
                return super().run(spec)

        # Việc của lượt chạy trước nằm sẵn trên nhánh story và **chưa** có kết
        # luận nào gắn với nó (bản đặc tả vừa đổi sau lần chấm cũ).
        (self.tree.path / "src").mkdir(parents=True, exist_ok=True)
        (self.tree.path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.tree.path / "tests").mkdir(parents=True, exist_ok=True)
        (self.tree.path / "tests" / "test_a.py").write_text(
            "def test_x():\n    pass\n", encoding="utf-8")
        for cmd in (["git", "add", "-A"], ["git", "commit", "-qm", "việc của lượt trước"]):
            subprocess.run(cmd, cwd=self.tree.path, check=True)

        client = KhongBaoGioViet()
        self.chay(client)
        self.assertEqual(self.so_lan_ra_soat(), 1,
                         "cây có việc mà chưa ai chấm thì phải được chấm")

    def test_luot_co_viet_that_van_duoc_cham_binh_thuong(self):
        """Chỉ *phiên im lặng* mới bị chặn; lượt sửa thật vẫn đi qua cổng.

        Ghi lại **đúng nội dung cũ** cũng là không đổi: cây y hệt thì cổng
        cho lại đúng kết quả cũ, nên phép so là nội dung, không phải lời kể
        của agent."""

        class SuaThat(ScriptedClient):
            def __init__(inner, **kw):
                super().__init__(**kw)
                inner.vong = 0

            def run(inner, spec):
                dau = spec.prompt.lstrip().splitlines()[0] if spec.prompt.strip() else ""
                if not dau.startswith("# Review") and not dau.startswith("# Security review"):
                    inner.vong += 1
                    if inner.vong > 1:
                        inner.calls.append("develop")
                        (Path(spec.workdir) / "src" / "a.py").write_text(
                            f"x = {inner.vong}\n", encoding="utf-8")
                        return RunResult(ok=True, text="đã sửa", cost_usd=1.0)
                return super().run(spec)

        client = SuaThat(writes=("src/a.py", "tests/test_a.py"),
                         review="[chặn] src/a.py:1 — thiếu kiểm tra")
        self.chay(client)
        self.assertEqual(self.so_lan_ra_soat(), 2, "hai lượt sửa thật, hai lần rà soát")


class TestChoTruocKhiThuLaiKhiBiGioiHanTanSuat(unittest.TestCase):
    """Vòng lặp story phải **chờ** rồi mới thử lại khi nhà cung cấp bảo chờ.

    Không chờ thì ba lượt hạ tầng cháy trong vài giây và story bị chặn vì một
    thứ chỉ cần nghỉ mười giây.
    """

    def test_attempt_mang_theo_thoi_gian_cho(self):
        from aisef.clients.stream import RunResult, retry_delay_seconds
        r = RunResult(ok=False, error="429 rate limit, retry after 8s")
        self.assertEqual(retry_delay_seconds(r), 8.0)

    def test_vong_lap_goi_sleep_dung_so_giay(self):
        """Chứng minh bằng chỗ gọi: `time.sleep` được gọi với đúng số nhà cung
        cấp nói, trước khi `continue`."""
        import re as _re
        from pathlib import Path as _Path

        from aisef.phases import implement
        src = _Path(implement.__file__).read_text(encoding="utf-8")
        # Neo vào chỗ **của vòng lặp** (`infra_budget`), không vào chuỗi
        # `if attempt.infra:` — chuỗi ấy còn xuất hiện trong `run_attempt`.
        khoi = src[src.index("infra_budget -= 1"):]
        khoi = khoi[:khoi.index("continue") + len("continue")]
        self.assertIn("cho = attempt.retry_after", khoi)
        self.assertIn("time.sleep(cho)", khoi)
        self.assertTrue(_re.search(r"if cho:\s*\n\s*time\.sleep\(cho\)", khoi),
                        "chỉ được ngủ khi nhà cung cấp thật sự nói thời gian chờ")
