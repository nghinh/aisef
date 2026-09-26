"""F4 — WORKSPACE OWNERSHIP: one classifier answers "whose path is this" for every consumer (INV-I.1, INV-I.2).
Porcelain alone never determines blame; unattributed data is never deleted automatically."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import tests  # noqa: E402,F401
from aisef.harness.guardrails import changed_files  # noqa: E402
from aisef.harness.ownership import NOT_A_WRITE, Ownership as O, classify, porcelain_entries  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=False).stdout


class TestOneClassifier(unittest.TestCase):
    def test_every_class_has_a_positive_and_a_negative(self):
        self.assertIs(classify("_bmad-output/evidence/S.jsonl"), O.HARNESS)
        self.assertIs(classify(".aisef/worktrees/S/x"), O.HARNESS)
        self.assertIs(classify(".coverage"), O.VERIFIER)
        self.assertIs(classify("tests/.coverage.host.123"), O.VERIFIER)
        self.assertIs(classify("packages/web/node_modules/left-pad/index.js"), O.VERIFIER)   # nested vendor (SS-39)
        self.assertIs(classify(".claude/settings.local.json"), O.CLIENT_GENERATED)          # SS-38
        self.assertIs(classify(".opencode/state.json"), O.CLIENT_GENERATED)
        self.assertIs(classify("src/a.py", scope=["src"]), O.DEVELOPER)
        self.assertIs(classify("docs/x.md", session_writes=["docs/x.md"]), O.DEVELOPER)
        self.assertIs(classify("src/fixtures/op.json", baseline=["src/fixtures/op.json"], scope=["src"]), O.PREEXISTING)
        self.assertIs(classify("notes.txt"), O.EXTERNAL_UNATTRIBUTED)
        self.assertIs(classify("src/apidocs/x.py", scope=["src/api"]), O.EXTERNAL_UNATTRIBUTED)   # segments, not prefixes
        for rel in ("src/a.py", "notes.txt"):
            self.assertNotIn(classify(rel), NOT_A_WRITE)

    def test_a_staged_rename_yields_the_real_path_never_a_phantom(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "src").mkdir(); (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "c")
            _git(repo, "mv", "src/a.py", "src/b.py")
            entries = porcelain_entries(repo)
            self.assertEqual([p for _, p in entries], ["src/b.py"], entries)
            self.assertEqual(changed_files(str(repo)), ["src/b.py"])

    def test_tool_client_and_harness_paths_are_not_story_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp); _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
            (repo / "goc.txt").write_text("g\n", encoding="utf-8"); _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "c")
            (repo / ".coverage").write_bytes(b"\x00")
            (repo / ".claude").mkdir(); (repo / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
            (repo / "node_modules" / "x").mkdir(parents=True); (repo / "node_modules" / "x" / "i.js").write_text("1", encoding="utf-8")
            (repo / "src").mkdir(); (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(changed_files(str(repo)), ["src/a.py"])


class TestNoArtifactsOutsideAProject(unittest.TestCase):
    """D-011 — a call whose project fell back to the current directory once wrote `_bmad-output/` into the framework
    repository root. An IMPLICIT project must be an AISEF project; otherwise nothing is written and the command says so."""

    def test_an_implicit_project_that_is_not_a_project_writes_nothing(self):
        import os
        from aisef.cli.parser import main
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd(); os.chdir(tmp)
            try:
                rc = main(["verify", "--story", "S-01"])
            finally:
                os.chdir(cwd)
            self.assertNotEqual(rc, 0)
            self.assertFalse((Path(tmp) / "_bmad-output").exists(), "nothing may be written where no project is")
            from aisef.cli._common import _artifact_root
            from aisef.config import ConfigError
            from types import SimpleNamespace
            with self.assertRaises(ConfigError):                       # the refusal itself, not an incidental exit code
                _artifact_root(SimpleNamespace(project=tmp, project_defaulted=True))
            (Path(tmp) / "docs").mkdir(); (Path(tmp) / "docs" / "requirements.md").write_text("# r\n", encoding="utf-8")
            self.assertTrue(_artifact_root(SimpleNamespace(project=tmp, project_defaulted=True)).name == "_bmad-output",
                            "a directory that IS a project is accepted implicitly")

    def test_an_explicit_project_is_honoured_as_before(self):
        from aisef.cli._common import _artifact_root
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = _artifact_root(SimpleNamespace(project=tmp, project_defaulted=False))
            self.assertEqual(root, Path(tmp).resolve() / "_bmad-output")
