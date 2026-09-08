"""ADR-003 cơ chế B: `skills.inline` dán thân SKILL.md của skill cao điểm nhất vào prompt."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.phases import implement as I  # noqa: E402


class TestInline(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        d = self.project / ".claude" / "skills" / "ui-ux-pro-max"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: ui-ux-pro-max\n---\n# Hướng dẫn UI\n\nDùng token màu.\n", encoding="utf-8")
        (self.project / "_bmad-output").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _route(self):
        entry = NS(id="ui-ux-pro-max", path=".claude/skills/ui-ux-pro-max")
        return NS(picked=[NS(entry=entry, score=10, rationale=["màn hình"])],
                  prompt_section=lambda: "- `ui-ux-pro-max`",
                  as_evidence=lambda: {"offered": [{"id": "ui-ux-pro-max"}], "abstained": False,
                                       "considered": 1, "threshold": 3, "best_rejected": None})

    def test_inline_adds_body_and_telemetry(self):
        cfg = Config({**DEFAULTS, "skills.offer": True, "skills.inline": True})
        with mock.patch.object(I.skill_registry, "load", return_value=None), \
                mock.patch.object(I.skill_router, "route", return_value=self._route()):
            section, ev = I._skills_section(NS(id="S", screens=["a"]), project=self.project,
                                            artifact_root=self.project / "_bmad-output", config=cfg)
        self.assertIn("Dùng token màu.", section)
        self.assertNotIn("name: ui-ux-pro-max", section)  # frontmatter bỏ
        self.assertEqual(ev["inline"], ["ui-ux-pro-max"])

    def test_offer_without_inline_keeps_progressive_disclosure(self):
        cfg = Config({**DEFAULTS, "skills.offer": True, "skills.inline": False})
        with mock.patch.object(I.skill_registry, "load", return_value=None), \
                mock.patch.object(I.skill_router, "route", return_value=self._route()):
            section, ev = I._skills_section(NS(id="S", screens=["a"]), project=self.project,
                                            artifact_root=self.project / "_bmad-output", config=cfg)
        self.assertNotIn("Dùng token màu.", section)
        self.assertNotIn("inline", ev)

    def test_cap(self):
        d = self.project / ".claude" / "skills" / "big"; d.mkdir()
        (d / "SKILL.md").write_text("x" * 20000, encoding="utf-8")
        text = I.inline_skill_text(self.project, ".claude/skills/big")
        self.assertLess(len(text), I.INLINE_SKILL_MAX_CHARS + 100)
        self.assertIn("truncated", text)


if __name__ == "__main__":
    unittest.main()
