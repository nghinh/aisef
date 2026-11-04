"""`aisef demo` (ROADMAP-2.2 B3+G5): the packaged example runs offline through seal→approve→run→verify,
and the three scenarios reach the three verdicts the kernel distinguishes — including the escape, the
honest boundary: a delivered run whose code is still wrong where no contract looks."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import demo  # noqa: E402


@unittest.skipUnless(os.name == "posix", "the fake developer is a script started by its shebang")
class Demo(unittest.TestCase):
    def test_the_trust_loop_reaches_its_three_verdicts_offline(self):
        with tempfile.TemporaryDirectory() as t:
            rows = demo.run_demo(pathlib.Path(t))
        by = {r["mode"]: r for r in rows if "mode" in r}
        # correct: delivered and the run verifies from its own journal
        self.assertEqual((by["correct"]["delivery"], by["correct"]["verify"]), ("PASS", "VERIFIED"))
        self.assertEqual(by["correct"]["stories"], {"S1": ["COMMIT"]})
        # caught: an in-scope regression is refused and the repository is rolled back (never a delivery)
        self.assertEqual(by["caught"]["delivery"], "FAIL")
        self.assertIn("ROLLBACK", by["caught"]["stories"]["S1"])
        self.assertEqual(by["caught"]["verify"], "VERIFIED")
        # escape (G5): the contract pins only add(2, 3) == 5, so `return 5` is delivered — and still wrong
        self.assertEqual(by["escape"]["delivery"], "PASS")
        self.assertEqual(by["escape"]["verify"], "VERIFIED")
        self.assertIn("returns 5", by["escape"]["gap"])

    def test_main_runs_and_exits_zero(self):
        self.assertEqual(demo.main([]), 0)


if __name__ == "__main__":
    unittest.main()
