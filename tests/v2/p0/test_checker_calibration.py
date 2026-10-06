"""WP-0.5 — every Q0 checker is observed saying NO, and calibration itself can say NO."""

import contextlib
import importlib.util
import io
import pathlib
import sys
import tempfile
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
        # V2.1 (owner B-03a): the committed record is the v2.1 one (cc.OUT_REL); 2.0's is history (below)
        self.assertEqual(cc.problems_of(self.result), [])
        self.assertEqual(self.result["calibrated_count"], len(cc.REGISTRY))
        self.assertEqual((ROOT / cc.OUT_REL).read_text(encoding="utf-8"), cc.render(self.result))

    def test_the_2_0_record_is_history(self):
        self.assertNotEqual(cc.OUT_REL, cc.HISTORY_REL)
        self.assertEqual(cc.history_problems(), [])
        tampered = (ROOT / cc.HISTORY_REL).read_bytes() + b" "
        with mock.patch.object(pathlib.Path, "read_bytes", return_value=tampered):
            self.assertEqual(cc.history_problems(), [f"{cc.HISTORY_REL} is not its v2.0.0 blob (history)"])

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


class V21Writers(unittest.TestCase):
    """V2.1 (owner B-03a): a 2.0 record is history and a writer writes only its v2.1 record, once — on a temporary
    ROOT, never the real tree (no calibration run: setUpClass is CheckerCalibration's)."""

    def test_the_2_0_p2_static_admission_record_is_history(self):
        ev = cc._load("aisef_v2_p2_evidence", cc.V2 / "p2_evidence.py")
        rel = ev.HISTORY["WP-2.3"]
        self.assertNotEqual(rel, ev.BUILDERS["WP-2.3"][0])
        self.assertEqual(ev.history_problems(), [])
        tampered = (ROOT / rel).read_bytes() + b" "
        with mock.patch.object(pathlib.Path, "read_bytes", return_value=tampered):
            self.assertEqual(ev.history_problems(), [f"{rel} is not its v2.0.0 blob (history)"])
        with mock.patch.object(ev, "problems_of", return_value=["WP-2.3: property p is false"]):
            self.assertEqual(ev.history_problems(), [f"{rel} (history): WP-2.3: property p is false"])

    def test_each_check_reports_its_2_0_record_s_history(self):
        result = {"checkers": [], "uncovered_checker_modules": [], "checker_count": 0, "calibrated_count": 0,
                  "always_pass_mutants_rejected": 0}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cc, "ROOT", pathlib.Path(tmp)), \
                mock.patch.object(cc, "run", return_value=result), contextlib.redirect_stdout(io.StringIO()) as out:
            (pathlib.Path(tmp) / cc.OUT_REL).parent.mkdir(parents=True)
            (pathlib.Path(tmp) / cc.OUT_REL).write_text(cc.render(result), encoding="utf-8")    # the v2.1 record current
            with mock.patch.object(cc, "history_problems", return_value=[]):
                self.assertEqual(cc.main(["--check"]), 0)
            with mock.patch.object(cc, "history_problems", return_value=["2.0 record tampered"]):
                self.assertEqual(cc.main(["--check"]), 1)
            self.assertIn("FAIL  2.0 record tampered", out.getvalue())
        ev = cc._load("aisef_v2_p2_evidence", cc.V2 / "p2_evidence.py")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ev, "history_problems", return_value=["2.0 record tampered"]) as history:
            self.assertEqual(ev.check(pathlib.Path(tmp)), ["2.0 record tampered"])   # no builder's module here: history alone
        history.assert_called_once_with(pathlib.Path(tmp))

    def test_the_p2_writer_writes_only_the_v2_1_record_and_never_rewrites_it(self):
        ev = cc._load("aisef_v2_p2_evidence", cc.V2 / "p2_evidence.py")
        rel, _, needs = ev.BUILDERS["WP-2.3"]
        first, second = ({"work_package": "WP-2.3", "properties": {"p": True}, "n": n} for n in (1, 2))
        every_need = [b[2] for b in ev.BUILDERS.values()]

        def builders(record):   # every builder buildable, each returning a clean record
            return mock.patch.dict(ev.BUILDERS, {wp: (r, lambda: record, n) for wp, (r, _, n) in ev.BUILDERS.items()})

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ev, "ROOT", pathlib.Path(tmp)), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            root = pathlib.Path(tmp)
            for n in every_need:
                (root / n).parent.mkdir(parents=True, exist_ok=True)
                (root / n).write_text("", encoding="utf-8")
            with builders(first):
                self.assertEqual(ev.main([]), 0)
            with builders(second):
                self.assertEqual(ev.main([]), 1)             # an existing record is never rewritten
            self.assertIn(f"FAIL  refused: {rel} exists", out.getvalue())
            self.assertEqual((root / rel).read_text(encoding="utf-8"), ev.render(first))
            # the v2.1 WP-2.3 record only: never the 2.0 one, never the other four builders' records
            self.assertIn(needs, every_need)
            self.assertEqual(sorted(f.relative_to(root).as_posix() for f in root.rglob("*") if f.is_file()), sorted([*every_need, rel]))

    def test_the_calibration_writer_writes_only_the_v2_1_record_and_never_rewrites_it(self):
        first, second = ({"checkers": [], "uncovered_checker_modules": [], "checker_count": n, "calibrated_count": n,
                          "always_pass_mutants_rejected": n} for n in (0, 1))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cc, "ROOT", pathlib.Path(tmp)), \
                mock.patch.object(cc, "run", side_effect=[first, second]), contextlib.redirect_stdout(io.StringIO()) as out:
            root = pathlib.Path(tmp)
            self.assertEqual(cc.main([]), 0)
            self.assertEqual(cc.main([]), 1)                 # an existing record is never rewritten
            self.assertIn(f"FAIL  refused: {cc.OUT_REL} exists", out.getvalue())
            self.assertEqual((root / cc.OUT_REL).read_text(encoding="utf-8"), cc.render(first))
            self.assertEqual([f.relative_to(root).as_posix() for f in root.rglob("*") if f.is_file()], [cc.OUT_REL])


if __name__ == "__main__":
    unittest.main()
