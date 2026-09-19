"""SS-92 (sibling of SS-23) — a lint or sast run that EXECUTED and reported findings is recorded as TOOL_UNRUNNABLE
("tool not installed or cannot load (not found)") when the findings quote source text containing a missing-tool
marker. Found in W1 PROFILE-W1-OC-GPT56SOL-T80-RO run 1 (2026-09-19): bandit scanned 51 187 lines, reported
1039/31/26 low/medium/high issues, exit 1 — and the kernel recorded that the tool is not installed, because a quoted
test line reads `assert "not found: Ghost" in err`. SS-23 fixed this for `test` only ("any named test proves the
runner ran"); lint and sast print the offending source lines. Fails on the frozen kernel 40393cd / a2f6e76b.

    PYTHONPATH=<tree> python closure-evidence/hardening/w1/run-gpt56sol-ro-1/repro_SS92_quoted_source_reads_as_missing_tool.py
"""
import unittest

from aisef.harness.tools import unrunnable_reason

BANDIT = """Run started:2026-09-19 05:47:46
>> Issue: [B101:assert_used] Use of assert detected.
   Severity: Low   Confidence: High
   Location: ./tests/test_cli.py:173:4
172	    rc, out, err = run("get", "Ghost")
173	    assert "not found: Ghost" in err
--------------------------------------------------
Code scanned:
	Total lines of code: 51187
Run metrics:
	Total issues (by severity):
		Low: 1039
		Medium: 31
		High: 26
Files skipped (0):
"""
RUFF = """tests/test_cli.py:173:5: F841 Local variable `msg` is assigned to but never used
    |
173 |     msg = "not found: Ghost"
    |     ^^^ F841
Found 1 error.
"""


class SS92(unittest.TestCase):
    def test_a_sast_run_that_reported_findings_is_a_result_not_a_missing_tool(self):
        self.assertEqual(unrunnable_reason("sast", 1, BANDIT), "")

    def test_a_lint_run_that_reported_findings_is_a_result_not_a_missing_tool(self):
        self.assertEqual(unrunnable_reason("lint", 1, RUFF), "")

    def test_control_a_missing_linter_is_still_unrunnable(self):
        self.assertNotEqual(unrunnable_reason("lint", 127, "sh: ruff: command not found"), "")


if __name__ == "__main__":
    unittest.main()
