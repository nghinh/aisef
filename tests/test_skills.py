from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.kit.skills import Skill, load_skill, parse_frontmatter, scan

FM_BASIC = "---\nname: foo\ndescription: bar\n---\nbody"
FM_FOLDED = "---\ndescription: >-\n  line one\n  line two\n---\n"
FM_PIPE = "---\ndescription: |\n  line one\n  line two\n---\n"
FM_LIST = "---\ntags:\n- a\n- b\n- c\n---\n"
FM_EMPTY_LINES = "---\nname: x\n\ndescription: y\n---\n"
FM_NO_FENCE = "name: foo\ndescription: bar\n"
FM_UNCLOSED = "---\nname: foo\n"
FM_EMPTY = "---\n---\n"

SKILL_MD = "---\nname: performing-audit\ndescription: Audit stuff\ndomain: security\nsubdomain: compliance\ntags:\n- audit\n- sec\n---\nBody text.\n"


class TestParseFrontmatter(unittest.TestCase):
    def test_basic_kv(self):
        d = parse_frontmatter(FM_BASIC)
        self.assertEqual(d["name"], "foo")
        self.assertEqual(d["description"], "bar")

    def test_folded_block(self):
        d = parse_frontmatter(FM_FOLDED)
        self.assertEqual(d["description"], "line one line two")

    def test_pipe_block(self):
        d = parse_frontmatter(FM_PIPE)
        self.assertEqual(d["description"], "line one line two")

    def test_list(self):
        d = parse_frontmatter(FM_LIST)
        self.assertEqual(d["tags"], ["a", "b", "c"])

    def test_empty_lines_ignored(self):
        d = parse_frontmatter(FM_EMPTY_LINES)
        self.assertEqual(d["name"], "x")
        self.assertEqual(d["description"], "y")

    def test_no_fence(self):
        self.assertEqual(parse_frontmatter(FM_NO_FENCE), {})

    def test_unclosed_fence(self):
        self.assertEqual(parse_frontmatter(FM_UNCLOSED), {})

    def test_empty_frontmatter(self):
        self.assertEqual(parse_frontmatter(FM_EMPTY), {})

    def test_empty_string(self):
        self.assertEqual(parse_frontmatter(""), {})


class TestSkillVerb(unittest.TestCase):
    def test_verb_split(self):
        s = Skill(name="performing-audit", path=Path("."))
        self.assertEqual(s.verb, "performing")

    def test_verb_no_dash(self):
        s = Skill(name="audit", path=Path("."))
        self.assertEqual(s.verb, "audit")

    def test_verb_lowercase(self):
        s = Skill(name="Performing-Audit", path=Path("."))
        self.assertEqual(s.verb, "performing")


class TestLoadSkill(unittest.TestCase):
    def test_valid_skill(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "my-skill"
            sd.mkdir()
            (sd / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
            s = load_skill(sd)
            self.assertIsNotNone(s)
            self.assertEqual(s.name, "performing-audit")
            self.assertEqual(s.domain, "security")
            self.assertEqual(s.tags, ("audit", "sec"))

    def test_missing_skill_md(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_skill(Path(d)))

    def test_name_falls_back_to_dirname(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "fallback-name"
            sd.mkdir()
            (sd / "SKILL.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")
            s = load_skill(sd)
            self.assertEqual(s.name, "fallback-name")

    def test_tags_as_string(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "s"
            sd.mkdir()
            (sd / "SKILL.md").write_text("---\ntags: solo\n---\n", encoding="utf-8")
            s = load_skill(sd)
            self.assertEqual(s.tags, ("solo",))

    def test_tags_missing(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "s"
            sd.mkdir()
            (sd / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
            s = load_skill(sd)
            self.assertEqual(s.tags, ())


class TestScan(unittest.TestCase):
    def test_finds_multiple_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("zz-skill", "aa-skill", "mm-skill"):
                sd = Path(d) / name
                sd.mkdir()
                (sd / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
            result = scan(Path(d))
            self.assertEqual([s.name for s in result], ["aa-skill", "mm-skill", "zz-skill"])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(scan(Path(d)), [])

    def test_nonexistent_dir(self):
        self.assertEqual(scan(Path("/nonexistent-dir-xyzzy")), [])

    def test_skips_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "valid").mkdir()
            (Path(d) / "valid" / "SKILL.md").write_text("---\nname: ok\n---\n", encoding="utf-8")
            (Path(d) / "empty").mkdir()
            result = scan(Path(d))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "ok")


if __name__ == "__main__":
    unittest.main()
