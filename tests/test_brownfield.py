"""Tests cho brownfield support: detect, baseline, provider, plan integration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestBrownfieldDetect(unittest.TestCase):
    def test_greenfield_empty(self):
        from aisef.codebase.detect import detect
        with tempfile.TemporaryDirectory() as d:
            sig = detect(Path(d))
            self.assertEqual(sig.source_files, 0)
            self.assertFalse(sig.is_brownfield)

    def test_brownfield_threshold(self):
        from aisef.codebase.detect import detect
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for i in range(3):
                (p / f"mod{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
            sig = detect(p)
            self.assertEqual(sig.source_files, 3)
            self.assertTrue(sig.is_brownfield)
            self.assertIn("py", sig.languages)

    def test_skills_the_framework_installed_are_not_the_project(self):
        """Lỗi 109: `aisef setup` cài 155 skill vào `.claude/skills`, 213 tệp
        trong đó là Python. Mọi dự án AISEF — kể cả dự án rỗng — vì thế đọc ra
        là brownfield với vài trăm tệp nguồn và ngôn ngữ chính là `py`, bất kể
        nó được viết bằng gì."""
        from aisef.codebase.detect import detect
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / ".claude" / "skills" / "mot-skill" / "scripts").mkdir(parents=True)
            for i in range(5):
                (p / ".claude" / "skills" / "mot-skill" / "scripts" / f"a{i}.py").write_text(
                    "x = 1\n", encoding="utf-8")
            (p / ".opencode" / "plugin").mkdir(parents=True)
            (p / ".opencode" / "plugin" / "aisef-guard.ts").write_text("//\n", encoding="utf-8")
            (p / "index.js").write_text("export const x = 1\n", encoding="utf-8")
            sig = detect(p)
            self.assertEqual(sig.source_files, 1)
            self.assertEqual(list(sig.languages), ["js"])
            self.assertFalse(sig.is_brownfield)

    def test_baseline_greenfield_names_what_is_already_there(self):
        """Dưới ngưỡng brownfield ≠ rỗng. `baseline.md` là thứ **duy nhất** nói
        cho planner biết trên đĩa có gì; nếu nó chỉ nói "chưa có mã nguồn" thì
        planner viết story tạo lại `package.json` đã có (lỗi 110)."""
        from aisef.codebase.baseline import build_baseline
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "package.json").write_text(
                '{"name": "taskbook", "type": "module", '
                '"bin": {"taskbook": "./bin/t.js"}, "scripts": {"test": "node --test"}}',
                encoding="utf-8")
            (p / ".claude" / "skills" / "s" / "scripts").mkdir(parents=True)
            (p / ".claude" / "skills" / "s" / "scripts" / "a.py").write_text("x=1\n", encoding="utf-8")
            text = build_baseline(p)
            self.assertIn("package.json", text)
            self.assertIn("`test`", text)
            self.assertIn("no runtime dependencies", text)
            # Skill của khung không phải mã của dự án, kể cả ở đây.
            self.assertNotIn(".claude", text)

    def test_skips_hidden_and_node_modules(self):
        from aisef.codebase.detect import detect
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / ".git").mkdir()
            (p / ".git" / "config.py").write_text("x = 1\n", encoding="utf-8")
            (p / "node_modules").mkdir()
            (p / "node_modules" / "lib.js").write_text("export default 1;\n", encoding="utf-8")
            (p / "real.py").write_text("x = 1\n", encoding="utf-8")
            sig = detect(p)
            self.assertEqual(sig.source_files, 1)

    def test_config_files_detected(self):
        from aisef.codebase.detect import detect
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            sig = detect(p)
            self.assertGreaterEqual(len(sig.config_files), 1)
            self.assertIn("pip", sig.package_managers)

    def test_summary(self):
        from aisef.codebase.detect import BrownfieldSignal
        sig = BrownfieldSignal(source_files=10, test_files=2,
                               config_files=["pyproject.toml"],
                               ci_present=True, schema_files=0,
                               doc_files=["README.md"],
                               languages={"py": 8, "ts": 2},
                               package_managers=["pyproject.toml"],
                               total_loc=500)
        s = sig.summary
        self.assertIn("10", s)
        self.assertIn("py", s)


class TestBasicProvider(unittest.TestCase):
    def test_available_always(self):
        from aisef.codebase.basic import BasicProvider
        self.assertTrue(BasicProvider.available())

    def test_build(self):
        from aisef.codebase.basic import BasicProvider
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.py").write_text("import b\n", encoding="utf-8")
            (p / "b.py").write_text("x = 1\n", encoding="utf-8")
            prov = BasicProvider()
            r = prov.build(p)
            self.assertGreaterEqual(r.nodes, 2)

    def test_impact_finds_reverse_import(self):
        from aisef.codebase.basic import BasicProvider
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "config.py").write_text("X = 1\n", encoding="utf-8")
            (p / "main.py").write_text("from config import X\n", encoding="utf-8")
            (p / "other.py").write_text("y = 2\n", encoding="utf-8")
            prov = BasicProvider()
            r = prov.impact(p, ["config.py"])
            ids = [n.id for n in r.affected]
            self.assertIn("config.py", ids)
            self.assertIn("main.py", ids)
            self.assertNotIn("other.py", ids)

    def test_query(self):
        from aisef.codebase.basic import BasicProvider
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "hello.py").write_text("def greet(): pass\n", encoding="utf-8")
            prov = BasicProvider()
            r = prov.query(p, "greet")
            self.assertTrue(r.answer)


class TestGraphifyProvider(unittest.TestCase):
    def test_available_checks_cli(self):
        from aisef.codebase.graphify import GraphifyProvider
        # Should not crash — returns True/False based on CLI availability
        result = GraphifyProvider.available()
        self.assertIsInstance(result, bool)

    def test_has_graph_false_without_dir(self):
        from aisef.codebase.graphify import GraphifyProvider
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(GraphifyProvider().has_graph(Path(d)))


class TestResolve(unittest.TestCase):
    def test_resolve_basic_fallback(self):
        from aisef.codebase.basic import BasicProvider
        from aisef.codebase.provider import resolve
        with tempfile.TemporaryDirectory() as d:
            p = resolve(Path(d), preference="auto")
            self.assertIsInstance(p, BasicProvider)

    def test_resolve_explicit_basic(self):
        from aisef.codebase.basic import BasicProvider
        from aisef.codebase.provider import resolve
        with tempfile.TemporaryDirectory() as d:
            p = resolve(Path(d), preference="basic")
            self.assertIsInstance(p, BasicProvider)


class TestBaseline(unittest.TestCase):
    def test_build_baseline(self):
        from aisef.codebase.baseline import build_baseline
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for i in range(3):
                (p / f"mod{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
            out = p / "baseline.md"
            text = build_baseline(p, output=out)
            self.assertTrue(out.is_file())
            self.assertIn("brownfield", text.lower())
            self.assertIn(".py", text)

    def test_build_baseline_greenfield(self):
        from aisef.codebase.baseline import build_baseline
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.py").write_text("x = 1\n", encoding="utf-8")
            text = build_baseline(p)
            self.assertIn("Greenfield", text)

    def test_build_baseline_with_provider(self):
        from aisef.codebase.baseline import build_baseline
        from aisef.codebase.basic import BasicProvider
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for i in range(3):
                (p / f"m{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
            text = build_baseline(p, provider=BasicProvider())
            self.assertIn("basic", text.lower())


class TestPlanBrownfield(unittest.TestCase):
    def test_prompt_greenfield_baseline_khong_noi_da_co_ma_nguon(self):
        """`baseline.md` có thể tồn tại cho một dự án **chưa** brownfield. Nói
        với planner "dự án ĐÃ CÓ mã nguồn" và "chỉ sinh delta" thì mâu thuẫn
        ngay với dòng đầu của chính baseline ấy, và có thể làm nó bỏ luôn việc
        cần lập kế hoạch."""
        from aisef.phases.plan import PHASES, build_prompt
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "_bmad-output").mkdir()
            (p / "_bmad-output" / "baseline.md").write_text(
                "# Baseline — Greenfield\n\nChưa có mã nguồn đáng kể.\n\n"
                "## Đã có sẵn trên đĩa\n\n- `package.json` — `type`; `bin`\n",
                encoding="utf-8")
            t = build_prompt(next(x for x in PHASES if x.id == "epics"), p)
        self.assertIn("Already on disk", t)
        self.assertIn("package.json", t)
        self.assertNotIn("ALREADY HAS source code", t)
        self.assertNotIn("Produce a DELTA", t)

    def test_is_brownfield_false_without_baseline(self):
        from aisef.phases.plan import _is_brownfield
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(_is_brownfield(Path(d)))

    def test_is_brownfield_true_with_baseline(self):
        from aisef.phases.plan import _is_brownfield
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "_bmad-output").mkdir()
            (p / "_bmad-output" / "baseline.md").write_text("# Baseline\n", encoding="utf-8")
            self.assertTrue(_is_brownfield(p))

    def test_brownfield_context_empty_without_baseline(self):
        from aisef.phases.plan import _brownfield_context
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_brownfield_context(Path(d)), "")

    def test_brownfield_context_includes_rules(self):
        from aisef.phases.plan import _brownfield_context
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "_bmad-output").mkdir()
            (p / "_bmad-output" / "baseline.md").write_text("# Baseline\n100 files\n", encoding="utf-8")
            ctx = _brownfield_context(p)
            self.assertIn("Brownfield Context", ctx)
            self.assertIn("ground truth", ctx)
            self.assertIn("DELTA", ctx)

    def test_build_prompt_brownfield_includes_baseline(self):
        from aisef.phases.plan import PHASES, build_prompt
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "_bmad-output").mkdir()
            (p / "_bmad-output" / "baseline.md").write_text("# Baseline\n", encoding="utf-8")
            prompt = build_prompt(PHASES[0], project=p)
            self.assertIn("baseline.md", prompt)
            self.assertIn("Brownfield Context", prompt)

    def test_build_prompt_greenfield_no_baseline(self):
        from aisef.phases.plan import PHASES, build_prompt
        with tempfile.TemporaryDirectory() as d:
            prompt = build_prompt(PHASES[0], project=Path(d))
            self.assertNotIn("baseline.md", prompt)
            self.assertNotIn("Brownfield", prompt)


class TestBlastRadius(unittest.TestCase):
    def test_blast_radius_empty_greenfield(self):
        from aisef.phases.implement import _blast_radius_section
        from aisef.control.normalize import Story
        s = Story(id="S-01", epic_id="E-01", title="test",
                  acceptance_criteria=[], covers=[], write_scope=["app.py"])
        with tempfile.TemporaryDirectory() as d:
            result = _blast_radius_section(s, project=Path(d), config=None)
            self.assertEqual(result, "")

    def test_blast_radius_nonempty_brownfield(self):
        from aisef.phases.implement import _blast_radius_section
        from aisef.control.normalize import Story
        s = Story(id="S-01", epic_id="E-01", title="test",
                  acceptance_criteria=[], covers=[], write_scope=["config.py"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "_bmad-output").mkdir()
            (p / "_bmad-output" / "baseline.md").write_text("# Baseline\n", encoding="utf-8")
            (p / "config.py").write_text("X = 1\n", encoding="utf-8")
            (p / "main.py").write_text("from config import X\n", encoding="utf-8")
            result = _blast_radius_section(s, project=p, config=None)
            # Should find affected files
            self.assertIn("Blast Radius", result)
            self.assertTrue("config" in result)


class TestChangeBrownfield(unittest.TestCase):
    def test_change_adds_brownfield_note(self):
        from aisef.control.change import apply
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "docs").mkdir()
            (p / "docs" / "requirements.md").write_text("# Req\n", encoding="utf-8")
            (p / "_bmad-output").mkdir()
            (p / "_bmad-output" / "baseline.md").write_text("# Baseline\n", encoding="utf-8")
            r = apply(p, "FR-1", "add feature X")
            self.assertTrue(r.story_file.is_file())
            content = r.story_file.read_text(encoding="utf-8")
            self.assertIn("Brownfield", content)
            self.assertTrue(any("blast-radius" in s for s in r.next_steps))

    def test_change_greenfield_no_brownfield_note(self):
        from aisef.control.change import apply
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "docs").mkdir()
            (p / "docs" / "requirements.md").write_text("# Req\n", encoding="utf-8")
            (p / "_bmad-output").mkdir()
            r = apply(p, "FR-1", "add feature X")
            content = r.story_file.read_text(encoding="utf-8")
            self.assertNotIn("Brownfield", content)
            self.assertFalse(any("blast-radius" in s for s in r.next_steps))


if __name__ == "__main__":
    unittest.main()
