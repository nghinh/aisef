"""Báo cáo nghiệm thu — gom bằng chứng đã có, không kể lại."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.state import StateStore, StoryStatus  # noqa: E402
from aisef.harness.observe import MOCKUP_MAP, EvidenceStore, Event  # noqa: E402
from aisef.phases.report import build, write  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "bmad"


class ReportTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.artifacts = self.project / "_bmad-output"
        self.artifacts.mkdir()
        import shutil

        shutil.copy(FIX / "prd.md", self.artifacts / "prd.md")

    def tearDown(self):
        self._tmp.cleanup()

    def write_index(self, stories):
        (self.artifacts / "stories.index.json").write_text(
            json.dumps({"stories": stories}, ensure_ascii=False), encoding="utf-8"
        )


class TestTraceability(ReportTestCase):
    def test_every_requirement_appears(self):
        report = build(self.project)
        self.assertEqual(len(report.traceability), 17)

    def test_uncovered_requirements_are_named(self):
        """Báo cáo phải nói thẳng cái gì chưa phủ, không im lặng cho qua."""
        report = build(self.project)
        self.assertEqual(len(report.uncovered), 17)
        self.assertIn("FR-1", report.markdown())

    def test_story_coverage_shows_up(self):
        self.write_index([{"id": "STORY-01-01", "covers": ["FR-1", "FR-2"]}])
        report = build(self.project)
        row = next(r for r in report.traceability if r.requirement == "FR-1")
        self.assertEqual(row.stories, ["STORY-01-01"])
        self.assertNotIn("FR-1", report.uncovered)

    def test_test_evidence_is_read_from_disk_not_claimed(self):
        self.write_index([{"id": "STORY-01-01", "covers": ["FR-1"]}])
        store = EvidenceStore(self.artifacts)
        store.file_change("STORY-01-01", "src/a.ts")
        store.tool_run("STORY-01-01", "test", ok=True)
        row = next(r for r in build(self.project).traceability if r.requirement == "FR-1")
        self.assertTrue(row.tested)

    def test_red_tests_do_not_count_as_tested(self):
        self.write_index([{"id": "STORY-01-01", "covers": ["FR-1"]}])
        EvidenceStore(self.artifacts).tool_run("STORY-01-01", "test", ok=False)
        row = next(r for r in build(self.project).traceability if r.requirement == "FR-1")
        self.assertFalse(row.tested)


class TestOperations(ReportTestCase):
    def test_cost_and_runs_come_from_evidence(self):
        store = EvidenceStore(self.artifacts)
        store.record("STORY-01-01", Event(kind="agent_run", cost_usd=1.5, duration_ms=9000))
        store.record("STORY-01-01", Event(kind="agent_run", cost_usd=0.5, duration_ms=1000))
        report = build(self.project)
        row = report.stories[0]
        self.assertEqual(row["runs"], 2)
        self.assertAlmostEqual(row["cost"], 2.0)
        self.assertAlmostEqual(report.total_cost_usd, 2.0)

    def test_story_status_from_state(self):
        state = StateStore(self.artifacts)
        state.register("STORY-01-01", "EPIC-01")
        state.transition("STORY-01-01", StoryStatus.RUNNING)
        self.assertEqual(build(self.project).stories[0]["status"], "running")

    def test_mockup_column_only_for_ui_stories(self):
        self.write_index([
            {"id": "STORY-01-01", "covers": ["FR-1"], "screens": ["danh-sach"]},
            {"id": "STORY-01-02", "covers": ["FR-2"], "screens": []},
        ])
        store = EvidenceStore(self.artifacts)
        store.record("STORY-01-01", Event(kind=MOCKUP_MAP, name="danh-sach", ok=True))
        store.record("STORY-01-02", Event(kind="agent_run", cost_usd=0.1))
        rows = {s["id"]: s["mockup"] for s in build(self.project).stories}
        self.assertEqual(rows["STORY-01-01"], "✅")
        self.assertEqual(rows["STORY-01-02"], "—")


class TestPlanningCost(ReportTestCase):
    def test_planning_runs_are_not_stories(self):
        """Chỉ ghi chi phí story thì tổng thiếu mất phần đắt nhất của
        những dự án nhỏ — lập kế hoạch tốn $7.92 trong lượt chạy thật."""
        store = EvidenceStore(self.artifacts)
        store.record("plan-prd", Event(kind="agent_run", cost_usd=1.88))
        store.record("mockup-danh-sach", Event(kind="agent_run", cost_usd=0.4))
        store.record("STORY-01-01", Event(kind="agent_run", cost_usd=1.0))

        report = build(self.project)
        self.assertEqual([s["id"] for s in report.stories], ["STORY-01-01"])
        self.assertEqual(sorted(p["id"] for p in report.phases),
                         ["mockup-danh-sach", "plan-prd"])
        self.assertAlmostEqual(report.total_cost_usd, 3.28)

    def test_phase_table_in_the_markdown(self):
        EvidenceStore(self.artifacts).record("plan-ux", Event(kind="agent_run", cost_usd=3.71))
        self.assertIn("Chi phí lập kế hoạch", build(self.project).markdown())

    def test_planning_runs_do_not_count_as_harness_story_evidence(self):
        EvidenceStore(self.artifacts).record("plan-ux", Event(kind="agent_run", cost_usd=1.0))
        self.assertIn("chưa có bằng chứng", build(self.project).harness["2 Tool"])


class TestHarnessEvidence(ReportTestCase):
    def test_missing_evidence_is_said_plainly(self):
        harness = build(self.project).harness
        self.assertEqual(len(harness), 6)
        self.assertIn("chưa có bằng chứng", harness["5 Guardrail"])

    def test_isolation_reports_what_actually_happened(self):
        """Báo "có sandbox" khi thực tế chạy thẳng trên máy là đúng loại tự
        khai mà cả framework này sinh ra để chống."""
        store = EvidenceStore(self.artifacts)
        store.tool_run("STORY-01-01", "test", ok=True,
                       detail={"isolation": "subprocess", "degraded": True})
        note = build(self.project).harness["3 Sandbox"]
        self.assertIn("subprocess", note)
        self.assertIn("suy biến", note)

    def test_isolation_with_a_container(self):
        EvidenceStore(self.artifacts).tool_run(
            "STORY-01-01", "test", ok=True,
            detail={"isolation": "docker/WORKSPACE_WRITE", "degraded": False})
        note = build(self.project).harness["3 Sandbox"]
        self.assertIn("docker", note)
        self.assertNotIn("suy biến", note)

    def test_present_evidence_names_the_artifact(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        self.assertIn("settings.json", build(self.project).harness["5 Guardrail"])


class TestPreDeploySection(ReportTestCase):
    def test_absent_when_never_scored(self):
        self.assertIn("Chưa chấm", build(self.project).markdown())

    def test_reads_the_report_that_was_signed(self):
        from aisef.control.approvals import PRE_DEPLOY_REPORT

        (self.artifacts / PRE_DEPLOY_REPORT).write_text(json.dumps({
            "passed": False,
            "checks": [{"name": "runbook", "passed": False, "detail": "thiếu mục: leo thang"}],
            "qa": {"release_ready": False, "failed": ["unit"], "unconfigured": ["perf"]},
        }, ensure_ascii=False), encoding="utf-8")
        text = build(self.project).markdown()
        self.assertIn("leo thang", text)
        self.assertIn("chưa cấu hình = perf", text)

    def test_dau_theo_ket_cuc_khong_theo_khong_chan(self):
        """Mục – không áp dụng / ◇ miễn không được in ✅ (QĐ C-a, QĐ5 2026-09-06)."""
        from aisef.control.approvals import PRE_DEPLOY_REPORT

        (self.artifacts / PRE_DEPLOY_REPORT).write_text(json.dumps({
            "passed": True,
            "checks": [
                {"name": "phạm vi", "outcome": "passed", "passed": True, "detail": "EPIC-01: 7 story"},
                {"name": "ngoài phạm vi nghiệm thu", "outcome": "not-applicable", "passed": True,
                 "detail": "16 story không chấm"},
                {"name": "miễn tường minh", "outcome": "waived", "passed": True, "detail": "mutation — lý do"},
                {"name": "runbook", "passed": False, "detail": "thiếu"},
            ],
            "scope": {"epic": "EPIC-01", "stories": ["STORY-01-01"], "outside": ["STORY-02-01"]},
        }, ensure_ascii=False), encoding="utf-8")
        text = build(self.project).markdown()
        self.assertIn("| phạm vi | ✅ EPIC-01: 7 story |", text)
        self.assertIn("| ngoài phạm vi nghiệm thu | – 16 story không chấm |", text)
        self.assertIn("| miễn tường minh | ◇ mutation — lý do |", text)
        self.assertIn("| runbook | ✗ thiếu |", text)
        self.assertIn("Phạm vi nghiệm thu: **EPIC-01**", text)
        self.assertIn("Ngoài phạm vi (chưa nghiệm thu): 1 story", text)

    def test_yeu_cau_chi_co_story_ngoai_pham_vi_thi_noi_ngoai_pham_vi(self):
        from aisef.control.approvals import PRE_DEPLOY_REPORT

        self.write_index([{"id": "STORY-02-01", "epic_id": "EPIC-02", "covers": ["FR-1"]}])
        (self.artifacts / PRE_DEPLOY_REPORT).write_text(json.dumps({
            "passed": True, "checks": [],
            "scope": {"epic": "EPIC-01", "stories": [], "outside": ["STORY-02-01"]},
        }), encoding="utf-8")
        text = build(self.project).markdown()
        row = next(l for l in text.splitlines() if l.startswith("| FR-1 |"))
        self.assertTrue(row.endswith("| STORY-02-01 | ngoài phạm vi |"), row)
        # Không có phạm vi thì vẫn "—" như cũ.
        (self.artifacts / PRE_DEPLOY_REPORT).unlink()
        text = build(self.project).markdown()
        row = next(l for l in text.splitlines() if l.startswith("| FR-1 |"))
        self.assertTrue(row.endswith("| STORY-02-01 | — |"), row)


class TestCongStoryChungNhan(ReportTestCase):
    """ADR-005 V9: báo cáo in "mục cổng có đủ 3 control: n/N" đọc từ bảng
    test, không phải câu "cổng 6 điều kiện" kể tay."""

    def test_so_doc_tu_bang_qualification(self):
        from aisef.control.gate import CHECK_NAMES, qualification_table

        report = build(self.project)
        self.assertEqual(set(report.qualification), set(CHECK_NAMES))
        du = sum(all(v.values()) for v in qualification_table().values())
        self.assertIn(f"mục cổng có đủ 3 control: {du}/{len(CHECK_NAMES)}", report.markdown())
        self.assertNotIn("6 điều kiện", report.markdown())

    def test_khong_co_thu_muc_tests_thi_in_dau_hoi_khong_in_0(self):
        from aisef.control.gate import CHECK_NAMES
        from aisef.phases.report import Report

        text = Report(project="x", qualification={}).markdown()
        self.assertIn(f"mục cổng có đủ 3 control: ?/{len(CHECK_NAMES)}", text)


class TestOutput(ReportTestCase):
    def test_written_to_docs(self):
        path = write(self.project)
        self.assertTrue(path.is_file())
        self.assertIn("Báo cáo nghiệm thu", path.read_text(encoding="utf-8"))

    def test_tieu_de_co_ten_du_an_ke_ca_khi_chay_tai_cho(self):
        """CLI mặc định `--project .`, và `Path(".").name` là chuỗi rỗng —
        báo cáo ra "# Báo cáo nghiệm thu — " cụt lủn."""
        import os

        cwd = os.getcwd()
        os.chdir(self.project)
        try:
            text = build(".").markdown()
        finally:
            os.chdir(cwd)
        self.assertIn(f"# Báo cáo nghiệm thu — {self.project.name}", text)

    def test_custom_path(self):
        out = self.project / "bao-cao.md"
        self.assertEqual(write(self.project, out=out), out)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTieuChiCoTestTrongBaoCao(ReportTestCase):
    def test_column_counts_from_last_green_run(self):
        from aisef.harness.observe import EvidenceStore
        self.write_index([{"id": "S-1", "epic_id": "E", "title": "t", "covers": ["FR-1"],
                           "acceptance_criteria": ["a", "b"], "screens": []}])
        ev = EvidenceStore(self.artifacts)
        ev.tool_run("S-1", "test", ok=True, detail={"test_format": "node-spec", "test_ids": ["AC-S-1-1: a"]})
        rep = build(self.project)
        self.assertEqual(next(s for s in rep.stories if s["id"] == "S-1")["ac"], "1/2")
        self.assertIn("| TCCN có test |", rep.markdown())

    def test_unreadable_names_show_unknown_not_full(self):
        from aisef.harness.observe import EvidenceStore
        self.write_index([{"id": "S-1", "epic_id": "E", "title": "t", "covers": [],
                           "acceptance_criteria": ["a"], "screens": []}])
        EvidenceStore(self.artifacts).tool_run("S-1", "test", ok=True, detail={"test_format": "", "test_ids": []})
        self.assertEqual(next(s for s in build(self.project).stories if s["id"] == "S-1")["ac"], "?/1")


class TestChuoiBanGiaoTrongBaoCao(ReportTestCase):
    def test_chain_from_handoff_events(self):
        from aisef.harness.observe import EvidenceStore
        self.write_index([{"id": "S-1", "epic_id": "E", "title": "t", "covers": [], "acceptance_criteria": [], "screens": []}])
        ev = EvidenceStore(self.artifacts)
        ev.handoff("S-1", frm="plan", to="developer", attempt=1, slots={"story_contract": ("artifact", 10)})
        ev.handoff("S-1", frm="developer", to="reviewer", attempt=1, slots={"diff_summary": ("git", 5)})
        ev.handoff("S-1", frm="gate", to="developer", attempt=2, slots={"story_contract": ("artifact+gate+review", 12)})
        rep = build(self.project)
        self.assertEqual(next(s for s in rep.stories if s["id"] == "S-1")["handoffs"],
                         "developer#1 → reviewer#1 → developer#2")
        self.assertIn("- S-1: developer#1 → reviewer#1 → developer#2", rep.markdown())
