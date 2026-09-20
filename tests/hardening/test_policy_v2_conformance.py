"""The TDD proof policy V2 conformance scenarios, as a test (owner decision 2026-09-20 §2, §6).

`tests.hardening.policy_v2` drives the REAL kernel — real git project, real pytest, real `run_nop` at the parent
SHA, the real gate and the real routing — through every proof mode and compares it against a reference model of
the policy written from the decision itself. Phase 12's random traces cannot do this: their fixtures set
`tools.test = true` and write no story test file, so the nop control is NOT_APPLICABLE and the obligations are
never exercised. Running the scenarios here means a policy regression fails the ordinary suite and CI, not only
the qualification artifact.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from tests.hardening import policy_v2 as P  # noqa: E402


class TestPolicyV2Conformance(unittest.TestCase):
    """One subtest per scenario: a mismatch names the case, the field, and both sides."""

    def test_every_scenario_matches_the_reference_model(self):
        for case in P.SCENARIOS:
            with self.subTest(case=case.id, title=case.title):
                r = P.compare(case)
                self.assertEqual(r["mismatches"], [], f"{case.id}: {case.title}")

    def test_the_suite_exercises_all_three_proof_modes_and_all_three_owners(self):
        """The gap this suite exists to close: a scenario set that never reaches a mode proves nothing about it."""
        modes = {c.mode for case in P.SCENARIOS for c in case.crits}
        self.assertLessEqual({"CHANGE_REQUIRED", "PRESERVE_REQUIRED", "NEGATIVE_INVARIANT"}, modes)
        owners = {P.model_ac(c.mode, c.parent, c.candidate)[1] for case in P.SCENARIOS for c in case.crits}
        self.assertLessEqual({P.PLAN, P.DEVELOPER, P.ENVIRONMENT}, owners)


class TestTheReferenceModelIsNotTheProduct(unittest.TestCase):
    """The model must be a second opinion. If it ever imports the kernel's own table, the comparison is vacuous."""

    def test_the_model_does_not_read_the_products_obligation_table(self):
        import ast

        tree = ast.parse((ROOT / "tests/hardening/policy_v2.py").read_text(encoding="utf-8"))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
            f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
            for a in n.names}
        self.assertEqual([m for m in imported if "obligation" in m], [])


if __name__ == "__main__":
    unittest.main()
