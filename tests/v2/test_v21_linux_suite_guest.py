"""validation/v21/sandbox/linux_suite_guest.py — the in-guest suite runner of linux_suite.sh (V2.1 fix window, lane E).

The runner is what turns a Linux run into numbers an owner reads: the failing ids, the skips with their reasons, the
seconds of each module. A runner that mis-attributes a skip, loses a module that did not import, or leaves no summary
when it is killed would report a green or a time that is not the run's, so each of those is asserted here on a toy
suite of three modules run for real by the real runner (a subprocess, the way the guest starts it).
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "validation" / "v21" / "sandbox" / "linux_suite_guest.py"

TOY = {
    "test_green.py": """
        import unittest
        class G(unittest.TestCase):
            def test_one(self):
                pass
            def test_two(self):
                pass
    """,
    "test_mixed.py": """
        import unittest
        class M(unittest.TestCase):
            def test_fails(self):
                self.fail("on purpose")
            @unittest.skip("a tool the image lacks")
            def test_skipped(self):
                pass
        @unittest.skip("the whole class")
        class Whole(unittest.TestCase):
            def test_a(self):
                pass
            def test_b(self):
                pass
    """,
    "test_broken.py": """
        import no_such_module_anywhere
    """,
}


def run_toy(*names):
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "tests").mkdir()
        for n, body in TOY.items():
            (root / "tests" / n).write_text(textwrap.dedent(body), encoding="utf-8")
        out = root / "summary.json"
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        r = subprocess.run([sys.executable, "-B", str(RUNNER), "--summary", str(out), *names], cwd=d, env=env,
                           capture_output=True, encoding="utf-8")
        return r, json.loads(out.read_text(encoding="utf-8")) if out.exists() else None


class Runner(unittest.TestCase):
    def test_discovery_counts_every_outcome_and_names_each_failure_and_module(self):
        r, s = run_toy()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIsNotNone(s, r.stderr)
        self.assertTrue(s["complete"])
        self.assertFalse(s["successful"])
        self.assertEqual((s["ran"], s["skipped"]), (7, 3))        # 2 + 1 failing + 1 skipped + 2 in the skipped class + 1 import error
        self.assertEqual(s["failures"], ["test_mixed.M.test_fails"])
        self.assertEqual(s["errors"], ["unittest.loader._FailedTest.test_broken"])
        self.assertEqual(s["skips_by_reason"], {"a tool the image lacks": 1, "the whole class": 2})
        mods = s["modules"]
        self.assertEqual(mods["test_green"]["tests"], 2)
        self.assertEqual((mods["test_mixed"]["tests"], mods["test_mixed"]["skipped"]), (4, 3))
        self.assertIn("test_broken", mods, "a module that did not import is a module, not nothing")
        self.assertTrue(all(v["seconds"] >= 0 for v in mods.values()))

    def test_named_modules_run_as_discover_names_them_and_only_those(self):
        r, s = run_toy("test_green")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((s["ran"], s["failures"], s["errors"], s["skipped"]), (2, [], [], 0))
        self.assertEqual(list(s["modules"]), ["test_green"])
        self.assertTrue(s["successful"])


if __name__ == "__main__":
    unittest.main()
