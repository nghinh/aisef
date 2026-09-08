from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.cli._common import EXIT_USAGE  # noqa: E402
from aisef.cli.parser import build_parser, main  # noqa: E402
from aisef.harness.guardrails import GUARD_MATCHERS  # noqa: E402


class TestBuildParser(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_returns_parser(self):
        import argparse
        self.assertIsInstance(self.parser, argparse.ArgumentParser)

    def test_project_defaults_to_dot(self):
        args = self.parser.parse_args(["doctor"])
        self.assertEqual(args.project, ".")

    def test_subcommands_parse(self):
        simple = [
            "setup", "doctor", "gates", "status", "report", "dashboard",
        ]
        for cmd in simple:
            with self.subTest(cmd=cmd):
                args = self.parser.parse_args([cmd])
                self.assertEqual(args.command, cmd)

    def test_subcommands_with_positional(self):
        cases = [
            (["change", "FR-1", "desc"], "change"),
            (["doc", "react"], "doc"),
            (["review", "prd"], "review"),
            (["approve", "prd"], "approve"),
            (["reject", "prd", "--note", "bad"], "reject"),
            (["tool", "test"], "tool"),
            (["evidence", "STORY-01-04"], "evidence"),
            (["auto-approve", "all"], "auto-approve"),
            (["guard", sorted(GUARD_MATCHERS)[0]], "guard"),
        ]
        for argv, expected in cases:
            with self.subTest(cmd=expected):
                args = self.parser.parse_args(argv)
                self.assertEqual(args.command, expected)

    def test_init_stack_choices(self):
        for stack in ("react", "python", "go", "node"):
            args = self.parser.parse_args(["init", "--stack", stack])
            self.assertEqual(args.stack, stack)
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["init", "--stack", "rust"])

    def test_run_verify_only_with_story(self):
        args = self.parser.parse_args(["run", "--verify-only", "--story", "S-01"])
        self.assertTrue(args.verify_only)
        self.assertEqual(args.story, "S-01")

    def test_guard_accepts_all_matchers(self):
        for kind in sorted(GUARD_MATCHERS):
            args = self.parser.parse_args(["guard", kind])
            self.assertEqual(args.kind, kind)

    def test_guard_rejects_unknown(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["guard", "nonexistent-guard"])


class TestMain(unittest.TestCase):
    def test_bad_command_exits_with_error(self):
        with self.assertRaises(SystemExit) as cm:
            main(["--project", ".", "zzz-no-such-cmd"])
        self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
