"""Báo cáo nghiệm thu — gom bằng chứng đã có, không kể lại."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.state import StateStore, StoryStatus  # noqa: E402
from aisdlc.harness.observe import MOCKUP_MAP, EvidenceStore, Event  # noqa: E402
from aisdlc.phases.report import build, write  # noqa: E402

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


class TestHarnessEvidence(ReportTestCase):
    def test_missing_evidence_is_said_plainly(self):
        harness = build(self.project).harness
        self.assertEqual(len(harness), 6)
        self.assertIn("chưa có bằng chứng", harness["5 Guardrail"])

    def test_present_evidence_names_the_artifact(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        self.assertIn("settings.json", build(self.project).harness["5 Guardrail"])


class TestOutput(ReportTestCase):
    def test_written_to_docs(self):
        path = write(self.project)
        self.assertTrue(path.is_file())
        self.assertIn("Báo cáo nghiệm thu", path.read_text(encoding="utf-8"))

    def test_custom_path(self):
        out = self.project / "bao-cao.md"
        self.assertEqual(write(self.project, out=out), out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
