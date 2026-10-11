"""validation/v21/kill_check.py: the position filter of --only (a tool, not a kill file)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import mutation as m  # noqa: E402
from validation.v21 import kill_check as kc  # noqa: E402

SCRIPT_MODULE = (
    "SCRIPT = \"\"\"\n"
    "def f(x, y):\n"
    "    if x > 0 and y > 0:\n"
    "        return x + y\n"
    "    return 0\n"
    "\"\"\"\n"
)


class OnlyPositions(unittest.TestCase):
    def test_a_script_target_keeps_exactly_the_listed_positions_of_its_one_list(self):
        full = m.mutants(SCRIPT_MODULE, "SCRIPT/f", {})
        self.assertGreater(len(full), 3)
        want = {1, 3}
        original = m.mutants
        self.addCleanup(setattr, m, "mutants", original)
        m.mutants = kc.only_positions(original, want)
        got = m.mutants(SCRIPT_MODULE, "SCRIPT/f", {})
        self.assertEqual([d for d, _ in got], [full[i][0] for i in sorted(want)])

    def test_a_plain_target_is_filtered_the_same_way(self):
        src = "def f(x):\n    return x > 0 and x < 9\n"
        full = m.mutants(src, "f", {})
        original = m.mutants
        self.addCleanup(setattr, m, "mutants", original)
        m.mutants = kc.only_positions(original, {0, len(full) - 1})
        self.assertEqual([d for d, _ in m.mutants(src, "f", {})], [full[0][0], full[-1][0]])


if __name__ == "__main__":
    unittest.main()
