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
