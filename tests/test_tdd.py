"""TDD kiểm được (G8): đỏ trước xanh, test biến mất."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from aisef.control.tdd import added_tests, red_before_green, test_delta as _test_delta
from aisef.harness.observe import EvidenceStore


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {p.stderr}")
    return p.stdout.strip()


HAI_TEST = "test('AC-S-1: một', () => {})\ntest('phụ', () => {})\n"


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "T")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "a.test.js").write_text(HAI_TEST, encoding="utf-8")
        (self.repo / "src.js").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "nền")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self._tmp.cleanup()


class TestThemTest(RepoCase):
    def test_new_test_file_counts_even_untracked(self):
        (self.repo / "tests" / "b.test.js").write_text("test('AC-S-2: hai', () => {})\n", encoding="utf-8")
        self.assertEqual(added_tests(self.repo, base_ref=self.base, changed=["tests/b.test.js", "src.js"], story_id="S"),
                         ["tests/b.test.js"])

    def test_new_ac_line_in_existing_file_counts(self):
        (self.repo / "tests" / "a.test.js").write_text(HAI_TEST + "test('AC-S-2: hai', () => {})\n", encoding="utf-8")
        self.assertEqual(added_tests(self.repo, base_ref=self.base, changed=["tests/a.test.js"], story_id="S"),
                         ["tests/a.test.js"])

    def test_refactor_without_tests_is_not_applicable(self):
        (self.repo / "src.js").write_text("y\n", encoding="utf-8")
        self.assertEqual(added_tests(self.repo, base_ref=self.base, changed=["src.js"], story_id="S"), [])

    def test_touching_existing_test_without_new_ac_is_not_adding(self):
        (self.repo / "tests" / "a.test.js").write_text(HAI_TEST.replace("phụ", "phụ 2"), encoding="utf-8")
        self.assertEqual(added_tests(self.repo, base_ref=self.base, changed=["tests/a.test.js"], story_id="S"), [])


class TestTestBienMat(RepoCase):
    def test_fewer_cases_are_reported_with_numbers(self):
        (self.repo / "tests" / "a.test.js").write_text("test('AC-S-1: một', () => {})\n", encoding="utf-8")
        self.assertEqual(_test_delta(self.repo, base_ref=self.base, changed=["tests/a.test.js"]),
                         ["tests/a.test.js: 2 → 1"])

    def test_more_or_equal_is_silent(self):
        (self.repo / "tests" / "a.test.js").write_text(HAI_TEST + "test('ba', () => {})\n", encoding="utf-8")
        self.assertEqual(_test_delta(self.repo, base_ref=self.base, changed=["tests/a.test.js"]), [])


class TestDoTruocXanh(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def ev(self):
        return self.store.read("S")

    def test_green_only_is_unproven(self):
        self.store.tool_run("S", "test", ok=True)
        self.assertFalse(red_before_green(self.ev()))

    def test_red_then_green(self):
        self.store.tool_run("S", "test", ok=False)
        self.store.tool_run("S", "test", ok=True)
        self.assertTrue(red_before_green(self.ev()))

    def test_skipped_is_not_red(self):
        self.store.tool_run("S", "test", ok=False, detail={"skipped": "chưa khai lệnh"})
        self.store.tool_run("S", "test", ok=True)
        self.assertFalse(red_before_green(self.ev()))

    def test_red_after_last_green_does_not_count(self):
        self.store.tool_run("S", "test", ok=True)
        self.store.tool_run("S", "test", ok=False)
        self.assertFalse(red_before_green(self.ev()))
