"""DevSecOps — cổng trước triển khai (code) và bộ khung vận hành (model)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.control.approvals import GATE_ARTIFACTS, ApprovalStore, Gate  # noqa: E402
from aisdlc.control.state import StateStore, StoryStatus  # noqa: E402
from aisdlc.phases.deploy import (  # noqa: E402
    CI_PATH,
    INSTALL_SPEC,
    RUNBOOK_PATH,
    RUNBOOK_SECTIONS,
    check_runbook,
    generate,
    pre_deploy,
    write_ci_workflow,
)

GOOD_RUNBOOK = """# Runbook

## Không lưu được ghi chú

**Triệu chứng:** người dùng báo mất chữ vừa gõ.
**Chẩn đoán:** `kubectl logs -l app=notes --since=15m | grep write_failed`
**Xử lý:** `kubectl rollout restart deploy/notes`
**Leo thang:** sau 15 phút chưa hết, gọi trực chính qua kênh #oncall.
"""


class Writer(ClientAdapter):
    """Agent giả: ghi ra các tạo tác được yêu cầu."""

    id = "fake"

    def __init__(self, *, files: dict[str, str] | None = None, ok: bool = True):
        self.files = files if files is not None else {
            "Dockerfile": "FROM alpine\nUSER 1000\n",
            RUNBOOK_PATH: GOOD_RUNBOOK,
        }
        self.ok = ok

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def run(self, spec: RunSpec) -> RunResult:
        if not self.ok:
            return RunResult(ok=False, error="api_error", cost_usd=0.4)
        for rel, text in self.files.items():
            path = Path(spec.workdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return RunResult(ok=True, text="xong", cost_usd=1.2)


class DeployTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "requirements.md").write_text(
            "ứng dụng web React với API FastAPI\n", encoding="utf-8")
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **over):
        return Config({**DEFAULTS, **over})

    def approve_everything(self):
        store = ApprovalStore(self.artifacts)
        for gate in GATE_ARTIFACTS:
            for name in GATE_ARTIFACTS[gate]:
                path = self.artifacts / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("nội dung\n", encoding="utf-8")
            if gate is not Gate.PRE_DEPLOY:
                store.approve(gate, by="nghi")

    def finish_a_story(self):
        state = StateStore(self.artifacts)
        state.register("STORY-01-01", "EPIC-01")
        state.transition("STORY-01-01", StoryStatus.RUNNING)
        state.transition("STORY-01-01", StoryStatus.VERIFYING)
        state.transition("STORY-01-01", StoryStatus.DONE)


class TestRunbook(unittest.TestCase):
    def test_four_sections_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "RUNBOOK.md"
            path.write_text(GOOD_RUNBOOK, encoding="utf-8")
            self.assertTrue(check_runbook(path).passed)

    def test_missing_escalation_fails(self):
        """Runbook thiếu phần leo thang chỉ hữu ích với người đã biết phải
        gọi ai — tức là người không cần runbook."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "RUNBOOK.md"
            path.write_text(GOOD_RUNBOOK.split("**Leo thang:**")[0], encoding="utf-8")
            check = check_runbook(path)
            self.assertFalse(check.passed)
            self.assertIn("leo thang", check.detail)

    def test_absent_file(self):
        self.assertFalse(check_runbook(Path("/khong/co/RUNBOOK.md")).passed)

    def test_sections_are_four(self):
        self.assertEqual(len(RUNBOOK_SECTIONS), 4)


class TestCiWorkflow(DeployTestCase):
    def test_written_where_github_looks(self):
        path = write_ci_workflow(self.project, aisdlc_bin="aisdlc")
        self.assertEqual(path, self.project / CI_PATH)
        self.assertTrue(path.is_file())

    def test_ci_runs_the_same_commands_a_person_runs(self):
        """Viết một quy trình riêng cho CI là cách chắc chắn để hai bên
        trôi khỏi nhau."""
        text = write_ci_workflow(self.project).read_text(encoding="utf-8")
        for command in ("doctor", "verify", "qa", "gates", "status"):
            self.assertIn(f"aisdlc {command}", text)


class TestPreDeployGate(DeployTestCase):
    def test_empty_project_fails_everything(self):
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        self.assertFalse(report.passed)
        self.assertIn("chưa story nào chạy", report.summary())

    def test_unfinished_story_blocks(self):
        self.approve_everything()
        state = StateStore(self.artifacts)
        state.register("STORY-01-02", "EPIC-01")
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        self.assertFalse(report.passed)
        self.assertIn("STORY-01-02", report.summary())

    def test_unapproved_gate_blocks(self):
        self.finish_a_story()
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        self.assertIn("chưa duyệt", report.summary())

    def test_report_is_written_for_the_human_to_read(self):
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        path = report.write(self.artifacts)
        self.assertTrue(path.is_file())
        import json

        self.assertIn("checks", json.loads(path.read_text(encoding="utf-8")))

    def test_running_stories_does_not_stale_the_readiness_approval(self):
        """`sprint-status.json` đổi sau mỗi story. Gắn cổng vào nó thì phê
        duyệt vừa ký đã thành `stale` và cổng bị bỏ qua."""
        from aisdlc.control.approvals import Status

        self.approve_everything()
        self.finish_a_story()
        store = ApprovalStore(self.artifacts)
        self.assertIs(store.status(Gate.READINESS), Status.APPROVED)

    def test_everything_ready_passes(self):
        self.approve_everything()
        self.finish_a_story()
        write_ci_workflow(self.project)
        (self.project / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")
        (self.project / RUNBOOK_PATH).parent.mkdir(parents=True, exist_ok=True)
        (self.project / RUNBOOK_PATH).write_text(GOOD_RUNBOOK, encoding="utf-8")
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        self.assertTrue(report.passed, report.summary())

    def test_qa_not_configured_blocks_release(self):
        """Chưa chạy kiểm định thì không được triển khai."""
        self.approve_everything()
        self.finish_a_story()
        write_ci_workflow(self.project)
        (self.project / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")
        (self.project / RUNBOOK_PATH).parent.mkdir(parents=True, exist_ok=True)
        (self.project / RUNBOOK_PATH).write_text(GOOD_RUNBOOK, encoding="utf-8")
        report = pre_deploy(self.project, config=self.config(), has_ui=False)
        self.assertFalse(report.passed)
        self.assertIn("chưa cấu hình", report.summary())


class TestGenerate(DeployTestCase):
    def test_ci_is_written_by_code_not_by_the_model(self):
        report = generate(self.project, Writer(), config=self.config())
        self.assertTrue((self.project / CI_PATH).is_file())
        self.assertTrue(report.ok, report.summary())

    def test_missing_artifact_is_reported(self):
        report = generate(self.project, Writer(files={"Dockerfile": "FROM alpine\n"}),
                          config=self.config())
        self.assertFalse(report.ok)
        self.assertIn(RUNBOOK_PATH, report.summary())

    def test_incomplete_runbook_counts_as_missing(self):
        bad = GOOD_RUNBOOK.split("**Leo thang:**")[0]
        report = generate(
            self.project,
            Writer(files={"Dockerfile": "FROM alpine\n", RUNBOOK_PATH: bad}),
            config=self.config(),
        )
        self.assertFalse(report.ok)
        self.assertIn("leo thang", report.summary())

    def test_existing_artifacts_are_not_regenerated(self):
        generate(self.project, Writer(), config=self.config())
        second = Writer(files={})   # sẽ không ghi gì
        report = generate(self.project, second, config=self.config())
        self.assertTrue(report.ok)
        self.assertEqual(report.cost_usd, 0.0)

    def test_run_failure_is_reported(self):
        report = generate(self.project, Writer(ok=False), config=self.config())
        self.assertFalse(report.ok)
        self.assertIn("api_error", report.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTenDuAn(unittest.TestCase):
    """Prompt `devsecops` dùng `project.name`; `Path(".").name` là rỗng.

    Lỗi 30, tìm được trong 45 giây đầu chạy bước 6 trên dự án thật:
    `PromptError: devsecops: biến rỗng project_name`. Cùng gốc với lỗi 22
    ở báo cáo nghiệm thu — vá một chỗ dùng không đủ.
    """

    def test_duong_dan_tuong_doi_van_ra_ten_that(self):
        import os
        import tempfile

        from aisdlc.phases.deploy import build_prompt

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "ten-du-an"
            d.mkdir()
            cwd = os.getcwd()
            os.chdir(d)
            try:
                body = build_prompt(Path(".").resolve(), "node")
            finally:
                os.chdir(cwd)
        self.assertIn("ten-du-an", body)


class TestQuyTrinhCI(unittest.TestCase):
    """Quy trình CI phải chạy được trên **máy khác**.

    Lỗi 31: `aisdlc devsecops` ghim đường dẫn tuyệt đối của máy sinh ra nó
    (`/Users/.../bin/aisdlc`) và không có bước nào cài framework — quy
    trình hỏng ngay bước đầu trên GitHub Actions.
    """

    def test_khong_ghim_duong_dan_tuyet_doi_va_co_buoc_cai(self):
        import tempfile

        from aisdlc.phases.deploy import write_ci_workflow

        with tempfile.TemporaryDirectory() as tmp:
            body = write_ci_workflow(tmp).read_text(encoding="utf-8")

        self.assertIn("pip install", body)
        self.assertNotIn("/Users/", body)
        self.assertNotIn("/home/", body)
        for lenh in ("aisdlc doctor", "aisdlc verify", "aisdlc qa", "aisdlc gates"):
            self.assertIn(f"run: {lenh}", body)

    def test_dem_dung_so_tao_tac(self):
        """In "sinh 2" rồi liệt kê 3 dòng làm người đọc nghi ngờ cả phần
        còn lại của báo cáo."""
        from pathlib import Path as _P

        from aisdlc.phases.deploy import DevSecOpsReport

        r = DevSecOpsReport(generated=["Dockerfile", "docs/RUNBOOK.md"],
                            ci_path=_P(".github/workflows/aisdlc.yml"))
        head = r.summary().splitlines()[0]
        self.assertIn("3 tạo tác", head)
        self.assertEqual(sum(1 for l in r.summary().splitlines() if "✅" in l), 3)


class TestInstallSpecDoiDuoc(unittest.TestCase):
    """Gói chưa lên PyPI thì `pip install ai-sdlc` trong CI sẽ hỏng. Quy
    trình sinh ra phải cho trỏ sang thứ pip cài được thật."""

    def test_mac_dinh_la_ten_goi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ci_workflow(tmp)
            self.assertIn(f"pip install --quiet {INSTALL_SPEC}",
                          path.read_text(encoding="utf-8"))

    def test_doi_sang_git_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = "git+https://github.com/ai-sdlc/ai-sdlc@v0.1.0"
            noi_dung = write_ci_workflow(tmp, install_spec=spec).read_text(
                encoding="utf-8")
            self.assertIn(f"pip install --quiet {spec}", noi_dung)
            self.assertNotIn(f"pip install --quiet {INSTALL_SPEC}\n", noi_dung)

    def test_cache_kho_skill_de_ci_khong_clone_lai_moi_luot(self):
        """93 MB skill không nằm trong gói; không cache thì mỗi lượt CI
        clone lại năm kho."""
        with tempfile.TemporaryDirectory() as tmp:
            noi_dung = write_ci_workflow(tmp).read_text(encoding="utf-8")
            self.assertIn("actions/cache@v4", noi_dung)
            self.assertIn("~/.cache/ai-sdlc/references", noi_dung)

    def test_yaml_van_hop_le_sau_khi_them_cache(self):
        """`${{ }}` của GitHub Actions đi qua `str.format` — dễ vỡ."""
        with tempfile.TemporaryDirectory() as tmp:
            noi_dung = write_ci_workflow(tmp).read_text(encoding="utf-8")
            self.assertIn("${{ hashFiles('.ai/config.json') }}", noi_dung)
            self.assertNotIn("{{{", noi_dung)


class TestXongPhaiLaDaMerge(DeployTestCase):
    """Lỗi 42, nhìn từ cổng trước triển khai. `DONE` ghi lúc qua cổng,
    **trước** merge; story xong mà code còn kẹt trên nhánh story thì với
    cổng này nó chưa xong — triển khai là triển khai nhánh chính."""

    def nhat_ky(self, *steps):
        from aisdlc.control.journal import Entry, JournalStore
        j = JournalStore(self.artifacts)
        for s in steps:
            j.record("STORY-01-01", Entry(step=s, attempt=1))

    def test_xong_nhung_chua_merge_thi_chan(self):
        self.approve_everything()
        self.finish_a_story()
        self.nhat_ky("attempt.started", "worktree.created", "commit.created",
                     "attempt.committed")
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        self.assertFalse(report.passed)
        self.assertIn("xong nhưng chưa merge", report.summary())
        self.assertIn("STORY-01-01", report.summary())

    def test_da_merge_thi_qua_muc_nay(self):
        self.approve_everything()
        self.finish_a_story()
        self.nhat_ky("attempt.started", "worktree.created", "merge.completed",
                     "attempt.committed")
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        muc = next(c for c in report.checks if c.name == "mọi story xong")
        self.assertTrue(muc.passed, muc.detail)

    def test_khong_co_nhat_ky_thi_khong_doi_merge(self):
        """Chạy `--no-isolate` hay dữ liệu cũ: không worktree, không đòi merge."""
        self.approve_everything()
        self.finish_a_story()
        report = pre_deploy(self.project, config=self.config(), skip_qa=True)
        muc = next(c for c in report.checks if c.name == "mọi story xong")
        self.assertTrue(muc.passed, muc.detail)


class TestPreDeployKhongChapNhanSuyBien(DeployTestCase):
    """Quyết định 2026-09-05: cổng trước triển khai **không** chấp nhận
    kiểm định chạy ngoài Docker, trừ khi có lý do khai tường minh — và lý
    do ấy ghi vào `pre-deploy.json`. `run` thường vẫn theo
    `sandbox.allow_degraded`.
    """

    def cau_hinh(self, **over):
        # Tắt Docker để đường suy biến là tất định, không phụ thuộc máy.
        return self.config(**{"verify.unit": "true", "sandbox.use_docker": False,
                              "sandbox.allow_degraded": True, **over})

    def muc(self, report, ten):
        return next(c for c in report.checks if c.name == ten)

    def test_suy_bien_khong_waiver_thi_chan(self):
        self.approve_everything(); self.finish_a_story()
        report = pre_deploy(self.project, config=self.cau_hinh())
        m = self.muc(report, "cách ly")
        self.assertFalse(m.passed)
        self.assertIn("ngoài Docker", m.detail)
        self.assertIn("sandbox.pre_deploy_degraded_waiver", m.detail)
        self.assertFalse(report.passed)

    def test_co_waiver_thi_qua_va_ghi_vao_bang_chung(self):
        self.approve_everything(); self.finish_a_story()
        ly_do = "máy CI chưa có Docker, xem ticket OPS-12"
        report = pre_deploy(self.project, config=self.cau_hinh(
            **{"sandbox.pre_deploy_degraded_waiver": ly_do}))
        m = self.muc(report, "cách ly")
        self.assertTrue(m.passed)
        self.assertIn(ly_do, m.detail)
        self.assertEqual(report.degraded_waiver, ly_do)
        import json
        data = json.loads(report.write(self.artifacts).read_text(encoding="utf-8"))
        self.assertEqual(data["degraded_waiver"], ly_do)
        self.assertIn("unit", data["qa"]["degraded"])

    def test_bo_qua_kiem_dinh_thi_muc_cach_ly_cung_bo_qua(self):
        report = pre_deploy(self.project, config=self.cau_hinh(), skip_qa=True)
        m = self.muc(report, "cách ly")
        self.assertTrue(m.skipped)

    def test_khong_co_lan_chay_nao_thi_khong_ket_luan(self):
        """Mọi loại chưa cấu hình → không biết có suy biến hay không; nói
        thế, đừng nói "trong Docker"."""
        self.approve_everything(); self.finish_a_story()
        report = pre_deploy(self.project, config=self.config(
            **{"sandbox.use_docker": False}))
        m = self.muc(report, "cách ly")
        self.assertTrue(m.skipped)
        self.assertIn("không có lần chạy nào", m.detail)

    def test_run_thuong_van_cho_suy_bien(self):
        """Quyết định chỉ chạm cổng trước triển khai."""
        from aisdlc.phases.qa import run_suite
        rep = run_suite(self.project, config=self.cau_hinh(), has_ui=False)
        self.assertEqual([r.kind.id for r in rep.degraded], ["unit"])
        self.assertTrue(rep.release_ready or rep.failed == [])
