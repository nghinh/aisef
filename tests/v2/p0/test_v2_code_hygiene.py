"""V1's Windows rule, applied to V2 code: every subprocess call that decodes output declares encoding="utf-8".

V1's meta test scans `aisef/` and `tests/` only. `validation/v2/` also runs on Windows CI — the V1 evidence guard's
detective check is a CI step on every OS — and an undeclared encoding there decodes git output with the locale
codec. This reuses V1's own scanner rather than writing a second one.
"""

import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("_v1_test_meta_scanner", ROOT / "tests" / "test_meta.py")
_tm = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_tm)
_scan = _tm.TestKhongDocDauRaBangBangMaCuaMay("test_phep_quet_that_su_thay_duoc_loi")._thieu


class V2SubprocessEncoding(unittest.TestCase):
    def test_validation_v2_declares_encoding_on_every_decoding_subprocess_call(self):
        missing = [f"{p.relative_to(ROOT)}:{ln}"
                   for p in sorted((ROOT / "validation" / "v2").rglob("*.py")) for ln in _scan(p)]
        self.assertEqual(missing, [], 'missing encoding="utf-8": ' + ", ".join(missing))

    def test_the_reused_scanner_still_says_no(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.py"
            p.write_text("import subprocess\nsubprocess.run(['git'], capture_output=True, text=True)\n",
                         encoding="utf-8")
            self.assertEqual(_scan(p), [2])


if __name__ == "__main__":
    unittest.main()


class V2IsNotShippedInTheAisefWheel(unittest.TestCase):
    """`include = ["aisef*"]` also matches `aisef2`; the exclude keeps V2 scaffolding out of the aisef wheel.

    The one-time proof with the real discovery function is closure-evidence/v2/P0-PACKAGING-EXCLUDE.json; this test
    guards the configuration with the same fnmatchcase filter setuptools applies, and needs no setuptools."""

    def test_aisef2_excluded_and_aisef_kept(self):
        import fnmatch
        import tomllib
        cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["packages"]["find"]
        inc, exc = cfg["include"], cfg.get("exclude", [])

        def shipped(name):
            return any(fnmatch.fnmatchcase(name, p) for p in inc) and not any(fnmatch.fnmatchcase(name, p) for p in exc)

        for name in ("aisef", "aisef.control", "aisef.harness"):
            self.assertTrue(shipped(name), name)
        for name in ("aisef2", "aisef2.arch"):
            self.assertFalse(shipped(name), name)
