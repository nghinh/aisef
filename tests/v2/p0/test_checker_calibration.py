"""WP-0.5 — every Q0 checker is observed saying NO, and calibration itself can say NO."""

import importlib.util
import pathlib
import sys
import unittest
from dataclasses import replace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
_NAME = "aisef_v2_checker_calibration"
if _NAME in sys.modules:
    cc = sys.modules[_NAME]
else:
    _s = importlib.util.spec_from_file_location(_NAME, ROOT / "validation" / "v2" / "checker_calibration.py")
    cc = importlib.util.module_from_spec(_s)
    sys.modules[_NAME] = cc
    _s.loader.exec_module(cc)


class CheckerCalibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = cc.run()

    def test_every_checker_is_calibrated_and_the_committed_record_is_current(self):
        self.assertEqual(cc.problems_of(self.result), [])
        self.assertEqual(self.result["calibrated_count"], len(cc.REGISTRY))
        self.assertEqual((ROOT / cc.OUT_REL).read_text(encoding="utf-8"), cc.render(self.result))

    def test_every_checker_has_a_committed_fixture_that_fails_it_for_the_named_reason(self):
        for r in self.result["checkers"]:
            with self.subTest(checker=r["checker"]):
                self.assertTrue((ROOT / r["fixture"]).is_file())
                self.assertTrue(r["clean_passes"])
                self.assertTrue(r["rejects_for_the_expected_reason"], r["observed"])

    def test_an_always_pass_checker_fails_calibration(self):
        for make in cc.REGISTRY:
            c = make()
            with self.subTest(checker=c.name):
                self.assertFalse(cc.calibrate(cc.always_pass_mutant(c))["calibrated"])

    def test_a_checker_that_fails_everything_fails_calibration(self):
        c = cc.REGISTRY[0]()
        broken = replace(c, clean=lambda: ["always"], known_bad=lambda fx: ["always"])
        self.assertFalse(cc.calibrate(broken)["calibrated"])

    def test_a_checker_that_rejects_for_the_wrong_reason_fails_calibration(self):
        c = cc.REGISTRY[0]()
        wrong = replace(c, known_bad=lambda fx: ["some unrelated file is missing"])
        self.assertFalse(cc.calibrate(wrong)["calibrated"])

    def test_a_missing_fixture_means_not_calibrated(self):
        c = replace(cc.REGISTRY[0](), name="no_such_checker")
        r = cc.calibrate(c)
        self.assertFalse(r["calibrated"])
        self.assertIn("no committed known-bad fixture", r["reason"])

    def test_a_stale_fixture_that_no_longer_fails_is_a_calibration_failure(self):
        # The REAL packaging checker, fed a fixture whose edit is now a no-op (the defect it planted is gone).
        fx = cc.fixture_for("packaging_check")
        with mock.patch.object(cc, "fixture_for", return_value=dict(fx, replace=fx["find"])):
            r = cc.calibrate(cc._packaging_check())
        self.assertFalse(r["rejects_known_bad"])
        self.assertFalse(r["calibrated"])

    def test_an_uncalibrated_checker_module_is_a_failure(self):
        self.assertEqual(self.result["uncovered_checker_modules"], [])
        dropped = [make() for make in cc.REGISTRY if make is not cc._packaging_check]
        self.assertIn("validation/v2/packaging_check.py", cc.uncovered_checker_modules(dropped))
        bad = dict(self.result, uncovered_checker_modules=["validation/v2/packaging_check.py"])
        self.assertTrue(cc.problems_of(bad))


if __name__ == "__main__":
    unittest.main()
