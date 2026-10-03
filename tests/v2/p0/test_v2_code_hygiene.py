"""V1's Windows rule, applied to V2 code: every subprocess call that decodes output declares encoding="utf-8".

V1's meta test scans `aisef/` and `tests/` only. `validation/v2/` also runs on Windows CI — the V1 evidence guard's
detective check is a CI step on every OS — and an undeclared encoding there decodes git output with the locale
codec. This reuses V1's own scanner rather than writing a second one.
"""

import importlib.util
import io
import pathlib
import tarfile
import tempfile
import unittest
import zipfile

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


_p = importlib.util.spec_from_file_location("packaging_check", ROOT / "validation" / "v2" / "packaging_check.py")
_pc = importlib.util.module_from_spec(_p)
_p.loader.exec_module(_pc)


class V2ShipsInTheAisefWheel(unittest.TestCase):
    """Charter G1/§9: the `aisef` distribution ships exactly `aisef` + `aisef2` (every subpackage), nothing else."""

    PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_exactly_aisef_and_aisef2_ship(self):
        self.assertEqual(_pc.check(self.PYPROJECT), [])
        pkgs = _pc.repo_packages()
        self.assertTrue({"aisef", "aisef2", "aisef2.orchestrate", "aisef2.probe", "tests"} <= set(pkgs), pkgs)

    def test_the_old_exclude_or_a_stray_package_is_refused(self):
        old = self.PYPROJECT.replace('"aisef2.*"]', '"aisef2.*"]\nexclude = ["aisef2*"]')
        self.assertIn("aisef2 would NOT ship in the aisef wheel", _pc.check(old))
        wide = self.PYPROJECT.replace('include = ["aisef", ', 'include = ["tests*", "aisef", ')
        self.assertIn("tests would ship in the aisef wheel but is not aisef or aisef2", _pc.check(wide))

    def test_the_built_artifacts_must_hold_exactly_the_shipped_trees(self):
        with tempfile.TemporaryDirectory() as d:
            root, dist = pathlib.Path(d) / "repo", pathlib.Path(d) / "dist"
            src = ("aisef/__init__.py", "aisef2/__init__.py", "aisef2/app/cli.py")
            for rel in src:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("", encoding="utf-8")
            dist.mkdir()

            def build(wheel_members, sdist_members):
                with zipfile.ZipFile(dist / "aisef-2.0.0-py3-none-any.whl", "w") as z:
                    for m in wheel_members:
                        z.writestr(m, "")
                with tarfile.open(dist / "aisef-2.0.0.tar.gz", "w:gz") as t:
                    for m in sdist_members:
                        t.addfile(tarfile.TarInfo(f"aisef-2.0.0/{m}"), io.BytesIO(b""))
                return _pc.artifact_problems(dist, root)

            self.assertEqual(build([*src, "aisef-2.0.0.dist-info/METADATA"], [*src, "PKG-INFO", "pyproject.toml"]), [])
            bad = build(["aisef/__init__.py", "aisef2/__init__.py", "tests/__init__.py"],
                        [*src, "validation/v2/x.py"])
            self.assertEqual(bad, ["aisef-2.0.0-py3-none-any.whl ships tests — not aisef, aisef2 or metadata",
                                   "aisef-2.0.0-py3-none-any.whl lacks aisef2/app/cli.py",
                                   "aisef-2.0.0.tar.gz ships validation — not aisef, aisef2 or metadata"])


if __name__ == "__main__":
    unittest.main()
