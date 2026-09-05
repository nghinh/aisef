"""P2-12: story giao diện quá lớn cho một phiên phải bị chẻ trước khi vào coding agent.

Đo 2026-09-05 trên e9: 11 và 18 trạng thái đều chạm max_turns ở lượt đầu.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.config import DEFAULTS, Config  # noqa: E402
from aisdlc.control import preflight  # noqa: E402
from aisdlc.control.experience import Experience, Screen  # noqa: E402
from aisdlc.control.normalize import Story  # noqa: E402
from aisdlc.phases.plan import PHASES, build_prompt  # noqa: E402
from aisdlc.phases.story_split import GATE_MEMO  # noqa: E402


def exp(**states):
    return Experience(screens=[Screen(id=k, name=k, states=[f"s{i}" for i in range(n)])
                               for k, n in states.items()])


def story(screens):
    return Story(id="STORY-01-05", epic_id="EPIC-01", title="Sửa ghi chú",
                 acceptance_criteria=["Then xong"], write_scope=["src/a.ts"], screens=screens)


class TestStorySize(unittest.TestCase):
    def setUp(self):
        self.cfg = Config({**DEFAULTS, "tools.test": "npm test", "tools.lint": "npx tsc"})

    def test_e9_note_editor_shape_is_blocked(self):
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"notes-list": 11, "note-editor": 7})):
            d = preflight.story_size_defect(story(["notes-list", "note-editor"]), project=Path("."), config=self.cfg)
            self.assertIsNotNone(d)
            self.assertEqual(d.kind, "story")
            self.assertTrue(d.blocks_run)
            self.assertIn("18 trạng thái", d.evidence)
            pf = preflight.check_story(story(["notes-list", "note-editor"]), project=Path("."), config=self.cfg)
        self.assertFalse(pf.executable)
        self.assertTrue(any(m.capability == "size" for m in pf.story_defects))

    def test_touching_a_screen_built_by_an_earlier_story_counts_one(self):
        """01-05 chạm notes-list (11, của 01-04) và dựng note-editor (7): 8, không chặn."""
        s4 = story(["notes-list"]); s4.id = "STORY-01-04"
        s5 = story(["notes-list", "note-editor"])
        owned = preflight.screen_owners([s4, s5])
        self.assertEqual(owned, {"notes-list": "STORY-01-04", "note-editor": "STORY-01-05"})
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"notes-list": 11, "note-editor": 7})):
            self.assertIsNone(preflight.story_size_defect(s5, project=Path("."), config=self.cfg, owned=owned))
            d4 = preflight.story_size_defect(s4, project=Path("."), config=self.cfg, owned=owned)
        self.assertIsNotNone(d4)
        self.assertIn("11 trạng thái", d4.evidence)

    def test_small_ui_story_passes(self):
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"tags": 4})):
            self.assertIsNone(preflight.story_size_defect(story(["tags"]), project=Path("."), config=self.cfg))

    def test_no_experience_counts_one_state_per_screen(self):
        with mock.patch.object(preflight, "_experience", return_value=None):
            self.assertIsNone(preflight.story_size_defect(story(["a", "b", "c"]), project=Path("."), config=self.cfg))

    def test_threshold_is_config(self):
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"tags": 4})):
            cfg = Config({**DEFAULTS, "story.max_screen_states": 3})
            self.assertIsNotNone(preflight.story_size_defect(story(["tags"]), project=Path("."), config=cfg))

    def test_epics_prompt_carries_last_gate_errors(self):
        epics = next(p for p in PHASES if p.id == "epics")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "_bmad-output"; root.mkdir()
            self.assertNotIn("KHÔNG ĐẠT", build_prompt(epics, project=Path(d)))
            (root / GATE_MEMO).write_text(json.dumps({"errors": ["STORY-01-05 quá lớn: 18 trạng thái"], "warnings": []}), encoding="utf-8")
            text = build_prompt(epics, project=Path(d))
            self.assertIn("KHÔNG ĐẠT", text)
            self.assertIn("18 trạng thái", text)


if __name__ == "__main__":
    unittest.main()
