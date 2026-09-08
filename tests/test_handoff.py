"""ADR-003 #9 — gói bàn giao ghi lại được và bất biến "reviewer không nhận lời developer";
#1 — telemetry skill đo từ luồng tool_use."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aisef.config import DEFAULTS, Config
from aisef.control.normalize import Story
from aisef.harness.observe import HANDOFF, EvidenceStore
from aisef.phases.implement import SLOT_SOURCE, _skills_section, handoff_slots, skills_used

REVIEW_CTX = {"story_id": "S", "story_title": "t", "story_contract": "c", "architecture_rules": "a",
              "write_scope": "src", "mockup_section": "m", "tools": "x", "skills": "k",
              "diff_summary": "diff", "impact": "i", "repo_map": "r", "_skills": {"enabled": False}}


class TestNguonSlot(unittest.TestCase):
    def test_reviewer_packet_has_no_agent_source(self):
        slots = handoff_slots(REVIEW_CTX)
        self.assertNotIn("_skills", slots)
        for k, (src, n) in slots.items():
            self.assertNotEqual(src, "agent", k)
            self.assertNotEqual(src, "?", f"slot {k} chưa khai nguồn trong SLOT_SOURCE")
            self.assertGreater(n, 0)

    def test_unknown_slot_is_visible_not_silently_valid(self):
        self.assertEqual(handoff_slots({"la": "x"})["la"], ("?", 1))

    def test_feedback_marks_the_contract_as_mixed(self):
        self.assertEqual(handoff_slots({"story_contract": "c"}, feedback=True)["story_contract"][0],
                         "artifact+gate+review")

    def test_every_declared_source_is_a_machine_or_artifact(self):
        # `ledger` là phép chiếu từ evidence — máy, không phải lời agent.
        # `evidence` là bản ghi đã lưu của chính vai đó ở lượt trước, đọc lại
        # từ đĩa; điều bị cấm là lời **agent khác** trong phiên này.
        self.assertTrue(set(SLOT_SOURCE.values())
                        <= {"artifact", "config", "router", "git", "code", "ledger", "evidence"})


class TestSuKienHandoff(unittest.TestCase):
    def test_event_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = EvidenceStore(tmp)
            st.handoff("S", frm="developer", to="reviewer", attempt=2, slots={"diff_summary": ("git", 12)})
            e = st.read("S").of(HANDOFF)[0]
            self.assertEqual(e.name, "developer->reviewer")
            self.assertEqual(e.detail["slots"]["diff_summary"], {"source": "git", "chars": 12})
            self.assertEqual(e.detail["attempt"], 2)


class TestSkillTelemetry(unittest.TestCase):
    def test_used_read_from_tool_uses(self):
        r = SimpleNamespace(tool_uses=[SimpleNamespace(name="Read", input={}),
                                       SimpleNamespace(name="Skill", input={"skill": "aisef-mockup-html"})])
        self.assertEqual(skills_used(r), ["aisef-mockup-html"])

    def test_no_stream_means_empty_not_guess(self):
        self.assertEqual(skills_used(SimpleNamespace()), [])

    def test_section_off_by_default_and_says_so(self):
        st = Story(id="S", epic_id="E", title="t")
        with tempfile.TemporaryDirectory() as tmp:
            text, ev = _skills_section(st, project=Path(tmp), artifact_root=Path(tmp), config=Config(dict(DEFAULTS)))
        self.assertIn("skills.offer", text)
        self.assertEqual(ev, {"enabled": False})

    def test_section_on_with_empty_registry_abstains(self):
        st = Story(id="S", epic_id="E", title="t")
        with tempfile.TemporaryDirectory() as tmp:
            text, ev = _skills_section(st, project=Path(tmp), artifact_root=Path(tmp),
                                       config=Config({**DEFAULTS, "skills.offer": True}))
        self.assertTrue(ev["enabled"])
        self.assertTrue(ev["abstained"])
        self.assertIn("No skill matched", text)
