"""DEFECT-1 (batch A15): aisef2/app/review_verify.py::detail — a large reproducer evicts the statement of the finding.

Requirement (module docstring L36-38, ADR-7 "nội dung vào prompt retry"): a blocking finding's statement and the
probe's observation are fed back to the developer on the retry. `detail` is that statement (the gate row the retry prompt
is built from), bounded to 1500 characters. It serialises with sort_keys=True, so `reproducer` sorts BEFORE `severity`,
`summary`, `verification` and `why`: a reproducer that carries a workspace file of a few hundred bytes (a corrupt-file
case, bytes_hex) pushes the bound inside the reproducer and the reviewer's summary, the severity, the verification
status and the probe's reason are cut away — exactly the fields the developer is told the finding by.

Run from the repository root (a checkout of c4c1720):   python3 -B defect-1.py
Fails on the unmutated module; passes on mutant [22] (`sort_keys=True` -> `False`: insertion order puts reproducer last).
"""
import os
import sys
import unittest

sys.path.insert(0, os.getcwd())
from aisef2.app import review_verify as V  # noqa: E402

SUMMARY = "SUMMARY-MARK: three arguments must exit 2, the command sums the first two"


class DetailOfABlockedFinding(unittest.TestCase):
    def test_the_statement_survives_a_large_reproducer(self):
        finding = {"id": "f1", "severity": "high", "summary": SUMMARY, "reproducer": {
            "clause": "R-9/5", "subject": {"kind": "cli_invocation", "locator": "ledgerlock:__main__"},
            "stimulus": {"argv": ["verify", "<ws>/L"], "workspace": {"L": {"bytes_hex": "ab" * 900}}},     # 900 bytes
            "observable": {"exit_code": 5, "within_s": 20}}}
        v = V.Verification(V.CONFIRMED, "probe.cli_invocation refutes the behaviour R-9 is said to demand",
                           "probe.cli_invocation", "REFUTED")
        a = V.Anchor(V.ANCHORED, "clause R-9/5's approved outcome {\"exit_code\":5} (BC-1, BC-2)", ("BC-1", "BC-2"))
        text = V.detail(finding, v, a)
        self.assertLessEqual(len(text), 1500)
        self.assertIn("SUMMARY-MARK", text)                      # what the reviewer says is wrong
        self.assertIn('"severity": "high"', text)
        self.assertIn('"verification": "CONFIRMED"', text)       # the probe's observation
        self.assertIn("refutes the behaviour", text)


if __name__ == "__main__":
    unittest.main()
