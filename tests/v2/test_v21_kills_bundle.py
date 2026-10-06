"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/bundle.py's V2.1 mutation targets, each class named by
the target and the mutants it kills. In the kill set of exactly the targets it kills (validation/v2/mutation.py)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle  # noqa: E402


class Strings(unittest.TestCase):
    """_strings — "L53 string ': a' emptied", "L53 string ' non-empty' emptied", "L53 conditional negated", "L53 string
    ' list of non-empty strings, not ' emptied": a refused list says where it is, what it must be (non-empty when the
    caller requires it) and what it was (V2.1 A3: the operator is told the JSON path and the expected type)."""

    def refused(self, v, **kw) -> str:
        with self.assertRaises(bundle.BundleError) as c:
            bundle._strings(v, "$.stories.S1.tests", **kw)
        return str(c.exception)

    def test_each_refusal_names_the_path_the_expected_list_and_the_type_it_got(self):
        self.assertEqual(self.refused("tests/a.py"), "$.stories.S1.tests: a list of non-empty strings, not str")
        self.assertEqual(self.refused(["a", ""]), "$.stories.S1.tests: a list of non-empty strings, not list")
        self.assertEqual(self.refused([], empty=False), "$.stories.S1.tests: a non-empty list of non-empty strings, not list")
        self.assertEqual(self.refused(None, empty=False), "$.stories.S1.tests: a non-empty list of non-empty strings, not NoneType")
        self.assertEqual(bundle._strings([], "$.x"), [])
        self.assertEqual(bundle._strings(["a"], "$.x", empty=False), ["a"])


if __name__ == "__main__":
    unittest.main()
