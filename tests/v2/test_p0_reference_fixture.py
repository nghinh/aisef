"""WP-2.0.3 — the LedgerLock reference fixture: static closure, reference GREEN, every mutant RED on its target,
target-specific failures, determinism and the vacuous-runner calibration. The full matrix runs here so that every
CI platform (Linux, Windows) measures it."""

import hashlib
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
_NAME = "aisef_v2_p0_reference_fixture"
if _NAME in sys.modules:
    rf = sys.modules[_NAME]
else:
    _s = importlib.util.spec_from_file_location(_NAME, ROOT / "validation" / "qualification" / "p0_reference_fixture.py")
    rf = importlib.util.module_from_spec(_s)
    sys.modules[_NAME] = rf
    _s.loader.exec_module(rf)


class StaticClosure(unittest.TestCase):
    def test_the_requirements_copy_is_the_frozen_document(self):
        self.assertEqual(hashlib.sha256((rf.FIX / "REQUIREMENTS.md").read_bytes()).hexdigest(), rf.REQUIREMENTS_SHA)

    def test_every_mutant_is_the_reference_plus_exactly_its_catalogued_change(self):
        self.assertEqual(rf.mutant_problems(), [])

    def test_the_reference_and_the_suite_are_stdlib_only_and_independent(self):
        self.assertEqual(rf.stdlib_problems(), [])
        self.assertEqual(rf.independence_problems(), [])

    def test_the_requirement_mapping_is_closed(self):
        self.assertEqual(rf.mapping_problems(), [])


class Matrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acc = rf._module("ledgerlock_reference_acceptance", rf.FIX / "acceptance.py")
        cls.results = rf.run_matrix(cls.acc)
        cls.ev = rf.evaluate(cls.results)

    def test_the_pristine_reference_is_green(self):
        self.assertEqual(self.ev["reference_failures"], [],
                         {a: r["detail"] for a, r in self.results["reference"].items() if not r["ok"]})

    def test_the_reference_acceptance_is_deterministic(self):
        self.assertTrue(self.ev["deterministic"])

    def test_every_mutant_is_red_on_its_target_and_fails_nothing_undeclared(self):
        for mid, r in self.ev["mutants"].items():
            with self.subTest(mutant=mid):
                self.assertTrue(r["red_on_target"], (r["expected_failing"], r["observed_failing"], r["observed_detail"]))
                self.assertEqual(r["undeclared_failures"], [], r["observed_detail"])

    def test_a_vacuous_runner_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            tree = rf._tree_with(rf._catalog()[0], pathlib.Path(t))
            self.assertTrue(rf.vacuous_runner_rejected(self.acc, tree))


if __name__ == "__main__":
    unittest.main()
