"""B1 gap kill tests for aisef2/app/bundle_cli.py::_write_new (pin L1077).

_write_new is the single serializer for every file the bundle tools write
(init's authoring.json, the seal/approve/continue bundles): canonical JSON,
sorted keys, ensure_ascii=False, one trailing newline. These tests pin the
two surviving-mutant-observable properties of the written bytes directly.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


class WriteNew(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    # kills: L1077 string '\n' emptied
    def test_write_new_appends_exactly_one_trailing_newline(self):
        path = self.tmp / "doc.json"
        bundle_cli._write_new(path, {"a": 1})
        raw = path.read_bytes()
        self.assertTrue(raw.endswith(b"}\n"), raw)      # last byte is the appended 0x0A
        self.assertFalse(raw.endswith(b"\n\n"), raw)    # ... and only one of it

    # kills: L1077 True->False
    def test_write_new_writes_keys_in_sorted_order(self):
        path = self.tmp / "doc.json"
        # insertion order deliberately unsorted: sort_keys=True must reorder it
        bundle_cli._write_new(path, {"zeta": 1, "alpha": 2})
        raw = path.read_bytes()
        self.assertLess(raw.index(b'"alpha"'), raw.index(b'"zeta"'), raw)


if __name__ == "__main__":
    unittest.main()
