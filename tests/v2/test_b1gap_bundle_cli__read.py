"""B1 gap kill tests: aisef2/app/bundle_cli.py::_read (mutation campaign, one test per surviving mutant)."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402


class Read(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    # kills: L1063 string ')' emptied
    def test_refusal_parenthesizes_the_exception_type_name(self) -> None:
        """A non-JSON file is refused with BundleError whose message carries the failing exception's type name in
        balanced parentheses: "(JSONDecodeError)". That parenthesized type name is the one semantic value of the
        message a tool or operator keys on; the mutant empties the closing ')' constant and leaves it unterminated."""
        bad = self.tmp / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(B.BundleError) as ctx:
            bundle_cli._read(bad)
        msg = str(ctx.exception)
        self.assertTrue(msg.startswith(str(bad)))                      # names the file
        self.assertIsNotNone(ctx.exception.__cause__)                  # chained from the real failure
        name = type(ctx.exception.__cause__).__name__
        self.assertEqual(name, "JSONDecodeError")
        # the smallest stable substring the mutant destroys: the type name closed by ')'
        self.assertIn(f"({name})", msg)


if __name__ == "__main__":
    unittest.main()
