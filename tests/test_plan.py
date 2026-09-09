"""Bộ chạy pipeline BMAD — kiểm bằng client giả, không tiêu tiền thật.

Client giả chỉ làm hai việc: ghi file mà pha yêu cầu và trả về JSON status.
Nhờ vậy kiểm được đúng thứ cần kiểm — *thứ tự* pha, chỗ *dừng*, và cách xử
lý khi agent nói một đằng đĩa một nẻo — mà không phụ thuộc model.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisef.clients.stream import RunResult  # noqa: E402
from aisef.config import Config, DEFAULTS  # noqa: E402
from aisef.control.approvals import GATE_ARTIFACTS, ApprovalStore, Gate, Status  # noqa: E402
from aisef.phases.plan import (  # noqa: E402
    ARTIFACT_ROOT,
    PHASES,
    build_prompt,
    run_pipeline,
)

FIX = ROOT / "tests" / "fixtures" / "bmad"
#: Artifact thật (hoặc đúng khuôn thật) — client giả chép ra để pha sau và
#: cổng máy làm việc trên dữ liệu có hình dạng thật.
REAL = {"prd.md": FIX / "prd.md", "architecture.md": FIX / "architecture.md",
        "epics.md": FIX / "epics.md",
        # Lỗi 50: khuôn cũ ghi một EXPERIENCE.md không có bảng màn hình — thứ
        # mà chính pipeline không đọc nổi. Dùng bản thật để cổng `ux` làm việc
        # trên hình dạng thật.
        "EXPERIENCE.md": FIX / "EXPERIENCE.md"}


class FakeClient(ClientAdapter):
    """Ghi ra file pha yêu cầu, rồi trả JSON status."""

    id = "fake"

    def __init__(self, *, status="complete", open_questions=(), skip=(), fail=()):
        self.status = status
        self.open_questions = list(open_questions)
        self.skip = set(skip)          # pha "quên" ghi file
        self.fail = set(fail)          # pha chạy hỏng
        self.calls: list[str] = []

    def available(self) -> bool:
        return True

    def capabilities(self):
        return {c: Support.NATIVE for c in Capability}

    def _phase_for(self, prompt: str):
        for p in PHASES:
            if f"Use the {p.skill} skill" in prompt:
                return p
        raise AssertionError("prompt không khớp pha nào")

    def run(self, spec: RunSpec) -> RunResult:
        phase = self._phase_for(spec.prompt)
        self.calls.append(phase.id)

        if phase.id in self.fail:
            return RunResult(ok=False, error="api_error", cost_usd=0.5)

        out = spec.workdir / ARTIFACT_ROOT
        out.mkdir(parents=True, exist_ok=True)
        artifacts = {}
        for name in phase.artifacts:
            if phase.id not in self.skip:
                self._write(out / name, phase.id)
            artifacts[name] = f"{ARTIFACT_ROOT}/{name}"

        body = {
            "status": self.status,
            "intent": "create",
            "assumptions": [],
            "open_questions": self.open_questions,
            **artifacts,
        }
        import json

        return RunResult(ok=True, cost_usd=1.25, text="xong.\n\n" + json.dumps(body))

    @staticmethod
    def _write(path: Path, phase_id: str) -> None:
        real = REAL.get(path.name)
        if real and real.is_file():
            path.write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.write_text(f"# {path.stem}\n\nsinh bởi pha {phase_id}\n", encoding="utf-8")


class PlanTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "requirements.md").write_text("# yêu cầu\n", encoding="utf-8")
        self.artifacts = self.project / ARTIFACT_ROOT
        self.store = ApprovalStore(self.artifacts)
        self.cfg = Config(dict(DEFAULTS))

    def tearDown(self):
        self._tmp.cleanup()

    def run_plan(self, client, **kw):
        return run_pipeline(self.project, client, config=self.cfg, **kw)


class TestPhaseContract(unittest.TestCase):
    def test_gated_phases_write_exactly_what_the_gate_hashes(self):
        """Nếu pha ghi ra file khác với file cổng băm, cổng sẽ băm rỗng và
        im lặng cho qua mọi thay đổi — một cổng nhìn thì có, thực thì không."""
        for phase in PHASES:
            if phase.gate is not None:
                self.assertEqual(phase.artifacts, GATE_ARTIFACTS[phase.gate], phase.id)

    def test_needs_come_from_earlier_phases(self):
        produced: set[str] = set()
        for phase in PHASES:
            for need in phase.needs:
                self.assertIn(need, produced, f"{phase.id} cần {need} chưa ai sinh")
            produced.update(phase.artifacts)

    def test_prompt_declares_headless_and_output_path(self):
        p = build_prompt(PHASES[1])  # prd
        self.assertTrue(p.startswith("headless: true"))
        self.assertIn("Use the bmad-prd skill", p)
        self.assertIn(f"{ARTIFACT_ROOT}/prd.md", p)
        self.assertIn("open_questions", p)

    def test_prd_prompt_defers_oqs_downstream_resolves(self):
        """PRD tells agent to put unknowns in open_questions;
        downstream phases tell agent to resolve OQs with MVP defaults."""
        prd = build_prompt(PHASES[1])  # prd
        self.assertIn("open_questions", prd)
        self.assertNotIn("resolve each one", prd)
        for phase in PHASES[2:]:  # architecture, ux, epics
            p = build_prompt(phase)
            self.assertIn("resolve each one", p, f"{phase.id} should resolve OQs")
            self.assertNotIn("goes in open_questions", p, f"{phase.id} should not defer OQs")


class TestStopsAtGates(PlanTestCase):
    def test_stops_at_first_gate(self):
        c = FakeClient()
        r = self.run_plan(c)
        self.assertEqual(r.waiting_on, Gate.PRD)
        self.assertEqual(c.calls, ["project-context", "prd"])
        self.assertFalse(r.complete)

    def test_continues_after_human_approves(self):
        c = FakeClient()
        self.run_plan(c)
        self.store.approve(Gate.PRD, by="nghi")
        r = self.run_plan(FakeClient())
        self.assertEqual(r.waiting_on, Gate.ARCHITECTURE)

    def test_finished_phases_are_not_rerun(self):
        """Chạy lại không được trả tiền làm lại việc đã xong."""
        self.run_plan(FakeClient())
        self.store.approve(Gate.PRD)
        second = FakeClient()
        self.run_plan(second)
        self.assertNotIn("prd", second.calls)
        self.assertNotIn("project-context", second.calls)

    def test_force_reruns_everything(self):
        self.run_plan(FakeClient())
        c = FakeClient()
        self.run_plan(c, force=True)
        self.assertIn("project-context", c.calls)

    def test_auto_approve_runs_straight_through(self):
        r = self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        self.assertTrue(r.complete, r.summary())
        self.assertEqual(len(r.outcomes), len(PHASES) + 1)  # + bước tách story
        self.assertEqual(self.store.status(Gate.EPICS), Status.APPROVED)
        self.assertEqual(self.store.status(Gate.STORIES), Status.APPROVED)

    def test_split_produces_one_file_per_story(self):
        self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        files = sorted((self.artifacts / "stories").rglob("STORY-*.md"))
        self.assertEqual(len(files), 12)
        self.assertTrue((self.artifacts / "stories.index.json").is_file())

    def test_stops_at_stories_gate_when_not_auto(self):
        auto = frozenset(Gate) - {Gate.STORIES}
        r = self.run_plan(FakeClient(), auto_approve=auto)
        self.assertEqual(r.waiting_on, Gate.STORIES)
        self.assertTrue((self.artifacts / "stories.index.json").is_file())

    def test_auto_approve_subset_stops_at_the_first_gate_not_in_it(self):
        r = self.run_plan(FakeClient(), auto_approve=frozenset({Gate.PRD}))
        self.assertEqual(r.waiting_on, Gate.ARCHITECTURE)

    def test_auto_approval_is_marked_auto(self):
        """Phải truy được artifact nào chưa từng có người thật xem."""
        self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        self.assertTrue(self.store.load(Gate.PRD).was_auto)


class TestRecordsEvidence(PlanTestCase):
    def test_open_questions_recorded_even_when_auto_approved(self):
        c = FakeClient(status="partial", open_questions=["ai sở hữu dữ liệu?"])
        self.run_plan(c, auto_approve=frozenset(Gate))
        note = self.store.load(Gate.PRD).note
        self.assertIn("partial", note)
        self.assertIn("1 open questions", note)

    def test_machine_checks_saved_with_approval(self):
        self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        checks = self.store.load(Gate.PRD).machine_checks
        self.assertEqual(checks["bmad_status"], "complete")
        self.assertEqual(checks["machine gate"], "pass")

    def test_cost_accumulates_across_phases(self):
        r = self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        self.assertAlmostEqual(r.total_cost_usd, 1.25 * len(PHASES))

    def test_split_step_costs_nothing(self):
        """Tách story là code, không gọi model."""
        r = self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        self.assertEqual(r.outcomes[-1].cost_usd, 0.0)


class TestFailures(PlanTestCase):
    def test_claimed_artifact_that_is_not_on_disk_fails_the_phase(self):
        """Lời khai của agent không phải bằng chứng — kiểm đĩa."""
        r = self.run_plan(FakeClient(skip={"prd"}))
        self.assertEqual(r.failed_at, "prd")
        self.assertIn("missing", r.outcomes[-1].error)

    def test_infrastructure_error_is_retried_not_abandoned(self):
        """Một lần đứt kết nối đã tiêu tiền mà không sinh ra gì; bỏ luôn
        thì lần chạy sau phải trả lại từ đầu."""

        class Flaky(FakeClient):
            def __init__(self):
                super().__init__()
                self.left = 1

            def run(self, spec):
                if self.left:
                    self.left -= 1
                    self.calls.append("hỏng")
                    return RunResult(ok=False, error="api_error", cost_usd=0.5)
                return super().run(spec)

        c = Flaky()
        r = self.run_plan(c)
        self.assertEqual(r.waiting_on, Gate.PRD)
        self.assertEqual(r.outcomes[0].infra_retries, 1)
        self.assertAlmostEqual(r.outcomes[0].cost_usd, 1.75)  # cả lượt hỏng
        # Và nói ra trong nhật ký: một `SSE read timed out` sau 22 phút, thử
        # lại lặng lẽ, hiện ra thành 36 phút chỉ có một dòng `START` bất động
        # (đo trên `todo-e3` 2026-09-09).
        log = (self.project / "_bmad-output" / "run.log").read_text(encoding="utf-8")
        self.assertIn("RETRY (infra)", log)
        self.assertIn("api_error", log)

    def test_pha_bi_bo_qua_khong_hua_mot_khoang_cho(self):
        """`START timeout=1800s` ngay trên `SKIP` đọc thành nửa giờ chờ không
        hề xảy ra — dòng ấy chỉ dành cho pha thật sự có chờ."""
        self.run_plan(FakeClient())          # lượt đầu sinh đủ tạo tác
        (self.project / "_bmad-output" / "run.log").unlink()
        self.run_plan(FakeClient())          # lượt hai bỏ qua
        log = (self.project / "_bmad-output" / "run.log").read_text(encoding="utf-8")
        for dong in log.splitlines():
            if "SKIP (artifacts exist)" in dong:
                pha = dong.split("phase=")[1].split()[0]
                self.assertNotIn(f"phase={pha} START", log, f"{pha}: hứa chờ rồi bỏ qua")

    def test_quality_failure_is_not_retried(self):
        """Chạy lại một lượt đã hỏng vì nội dung chỉ tốn tiền lần nữa."""
        c = FakeClient(skip={"project-context"})
        r = self.run_plan(c)
        self.assertEqual(r.failed_at, "project-context")
        self.assertEqual(c.calls.count("project-context"), 1)

    def test_run_failure_stops_after_the_budget(self):
        r = self.run_plan(FakeClient(fail={"project-context"}))
        self.assertEqual(r.failed_at, "project-context")
        self.assertIn("api_error", r.outcomes[-1].error)

    def test_blocked_status_stops_with_reason(self):
        import json

        class Blocked(FakeClient):
            def run(self, spec):
                self.calls.append(self._phase_for(spec.prompt).id)
                return RunResult(
                    ok=True,
                    text=json.dumps({"status": "blocked", "reason": "thiếu yêu cầu gốc"}),
                )

        r = self.run_plan(Blocked())
        self.assertEqual(r.failed_at, "project-context")
        self.assertIn("thiếu yêu cầu gốc", r.outcomes[-1].error)

    def test_machine_gate_failure_blocks_before_asking_a_human(self):
        """Không mời người xem một PRD mà máy đã biết là hỏng."""

        class BadPrd(FakeClient):
            @staticmethod
            def _write(path: Path, phase_id: str) -> None:
                path.write_text("# PRD rỗng\n\nkhông có yêu cầu nào.\n", encoding="utf-8")

        r = self.run_plan(BadPrd())
        self.assertEqual(r.failed_at, "prd")
        self.assertIsNone(r.waiting_on)
        self.assertFalse(r.outcomes[-1].machine_gate.passed)

    def test_missing_input_fails_without_spending(self):
        """Pha sau không được chạy khi thiếu đầu vào — chạy chỉ tốn tiền."""
        c = FakeClient(skip={"prd"})
        self.run_plan(c)
        # prd không ghi file; architecture phải không bao giờ được gọi
        self.assertNotIn("architecture", c.calls)


    def test_agent_fails_but_artifacts_on_disk_recovers(self):
        """Agent exit != 0 but wrote all files → phase should recover, not fail."""
        import json

        class FailButWrite(FakeClient):
            def run(self, spec):
                phase = self._phase_for(spec.prompt)
                self.calls.append(phase.id)
                out = spec.workdir / ARTIFACT_ROOT
                out.mkdir(parents=True, exist_ok=True)
                for name in phase.artifacts:
                    self._write(out / name, phase.id)
                body = json.dumps({"status": "complete", "intent": "create"})
                return RunResult(ok=False, error="max_turns", cost_usd=1.0,
                                 text="xong.\n\n" + body)

        r = self.run_plan(FailButWrite(), auto_approve=frozenset(Gate))
        self.assertTrue(r.complete, r.summary())


class TestSummary(PlanTestCase):
    def test_waiting_summary_tells_the_next_command(self):
        text = self.run_plan(FakeClient()).summary()
        self.assertIn("aisef review prd", text)

    def test_failure_summary_shows_machine_gate_errors(self):
        class BadPrd(FakeClient):
            @staticmethod
            def _write(path: Path, phase_id: str) -> None:
                path.write_text("# rỗng\n", encoding="utf-8")

        text = self.run_plan(BadPrd()).summary()
        self.assertIn("FAIL", text)
        self.assertIn("functional requirements", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestGitReadiness(unittest.TestCase):
    def test_ensure_git_no_repo(self):
        from aisef.cli._common import _ensure_git
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # no .git, no user config → should init then fail on missing user
            code = _ensure_git(d)
            self.assertIsNotNone(code)

    def test_ensure_git_configured_repo(self):
        from aisef.cli._common import _ensure_git
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init"], cwd=d, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=d, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=d, capture_output=True)
            Path(d, "f").write_text("x", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=d, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=d, capture_output=True)
            code = _ensure_git(d)
            self.assertIsNone(code)


class TestCongUxDoiDanhMucManHinh(unittest.TestCase):
    """Lỗi 50. `EXPERIENCE.md` là hợp đồng giữa phase `ux` và mọi bước sau:
    mockup dựng một tệp cho mỗi màn hình, story tham chiếu `screen_id`. Nhưng
    yêu cầu ấy chưa từng được nói cho bên viết, cũng chưa từng được kiểm ở
    cổng của chính nó.

    Đo 2026-09-09 trên todo-e2e (chạy từ requirements): agent viết một tài liệu
    tốt, mô tả "one surface, the Todo List screen" bằng văn xuôi, cổng `ux`
    **duyệt**, rồi `aisef mockup` chết một phase sau với "EXPERIENCE.md does not
    list any screens" — đổ lỗi cho tài liệu thay vì cho bước đã nhận nó.
    """

    def test_khong_co_man_hinh_thi_cong_ux_chan(self):
        from aisef.control.experience import parse_experience
        from aisef.control.machine_gate import check_experience
        exp = parse_experience("# EXPERIENCE\n\n## Information Architecture\n\n"
                               "One surface, the Todo List screen. No navigation.\n")
        r = check_experience(exp)
        self.assertFalse(r.passed)
        self.assertIn("screen inventory", r.errors[0])

    def test_co_bang_thi_qua(self):
        from aisef.control.experience import parse_experience
        from aisef.control.machine_gate import check_experience
        exp = parse_experience("# EXPERIENCE\n\n## Screen Inventory\n\n"
                               "| Screen | Route | Purpose |\n|---|---|---|\n"
                               "| Todo List | / | Create and manage tasks |\n")
        self.assertTrue(check_experience(exp).passed, check_experience(exp).errors)

    def test_prompt_ux_noi_ro_hinh_dang_bang(self):
        """Bên sản xuất phải đọc được yêu cầu, không phải đoán."""
        from aisef.phases.plan import PHASES, build_prompt
        ux = next(p for p in PHASES if p.id == "ux")
        t = build_prompt(ux)
        self.assertIn("| Screen | Route | Purpose |", t)
        self.assertIn("screen_id", t)
        prd = next(p for p in PHASES if p.id == "prd")
        self.assertNotIn("| Screen | Route | Purpose |", build_prompt(prd),
                         "chỉ phase ux mới cần bảng này")
