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

from aisdlc.clients.base import Capability, ClientAdapter, RunSpec, Support  # noqa: E402
from aisdlc.clients.stream import RunResult  # noqa: E402
from aisdlc.config import Config, DEFAULTS  # noqa: E402
from aisdlc.control.approvals import GATE_ARTIFACTS, ApprovalStore, Gate, Status  # noqa: E402
from aisdlc.phases.plan import (  # noqa: E402
    ARTIFACT_ROOT,
    PHASES,
    build_prompt,
    run_pipeline,
)

FIX = ROOT / "tests" / "fixtures" / "bmad"
#: Artifact thật (hoặc đúng khuôn thật) — client giả chép ra để pha sau và
#: cổng máy làm việc trên dữ liệu có hình dạng thật.
REAL = {"prd.md": FIX / "prd.md", "architecture.md": FIX / "architecture.md",
        "epics.md": FIX / "epics.md"}


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
        self.assertIn("1 câu hỏi mở", note)

    def test_machine_checks_saved_with_approval(self):
        self.run_plan(FakeClient(), auto_approve=frozenset(Gate))
        checks = self.store.load(Gate.PRD).machine_checks
        self.assertEqual(checks["bmad_status"], "complete")
        self.assertEqual(checks["cổng máy"], "đạt")

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
        self.assertIn("không thấy", r.outcomes[-1].error)

    def test_run_failure_stops_the_pipeline(self):
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


class TestSummary(PlanTestCase):
    def test_waiting_summary_tells_the_next_command(self):
        text = self.run_plan(FakeClient()).summary()
        self.assertIn("aisdlc review prd", text)

    def test_failure_summary_shows_machine_gate_errors(self):
        class BadPrd(FakeClient):
            @staticmethod
            def _write(path: Path, phase_id: str) -> None:
                path.write_text("# rỗng\n", encoding="utf-8")

        text = self.run_plan(BadPrd()).summary()
        self.assertIn("KHÔNG ĐẠT", text)
        self.assertIn("yêu cầu chức năng", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
