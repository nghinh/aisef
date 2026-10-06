"""V2.1: `aisef bundle ...` reaches aisef2.app.bundle_cli with its arguments untouched, like `aisef run` reaches
aisef2.app.cli (tests/test_cli.py TestRunIsV2); V1's parser never sees them."""

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aisef.cli.parser import main  # noqa: E402


class BundleIsV2(unittest.TestCase):
    def test_migrate_through_the_aisef_command(self):
        src = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"
        with tempfile.TemporaryDirectory() as t, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["bundle", "migrate", str(src), "--out", str(pathlib.Path(t) / "m.json")]), 0)
            self.assertTrue((pathlib.Path(t) / "m.json").is_file())
        self.assertIn('"specs_rebound": 59', out.getvalue())

    def test_a_refusal_is_exit_2(self):
        with tempfile.TemporaryDirectory() as t, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["bundle", "migrate", str(pathlib.Path(t) / "none.json"), "--out",
                                   str(pathlib.Path(t) / "m.json")]), 2)


if __name__ == "__main__":
    unittest.main()
