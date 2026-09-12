"""Design contract — serialization and lookup."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.design_contract import (  # noqa: E402
    DesignContract,
    ScreenContract,
    load,
)


class TestScreenContract(unittest.TestCase):
    def test_round_trip(self):
        sc = ScreenContract(
            id="SCR-01", name="Login", route="/login",
            components=[], data_roles=["user"], states=["default"],
        )
        d = sc.as_dict()
        sc2 = ScreenContract.from_dict(d)
        self.assertEqual(sc2.id, "SCR-01")
        self.assertEqual(sc2.name, "Login")
        self.assertEqual(sc2.data_roles, ["user"])

    def test_from_dict_defaults(self):
        sc = ScreenContract.from_dict({"id": "X"})
        self.assertEqual(sc.name, "")
        self.assertEqual(sc.components, [])
        self.assertFalse(sc.whole_page)
        self.assertEqual(sc.duplicates, 0)

    def test_from_dict_empty(self):
        sc = ScreenContract.from_dict({})
        self.assertEqual(sc.id, "")


class TestDesignContract(unittest.TestCase):
    def test_by_id(self):
        dc = DesignContract(screens=[
            ScreenContract(id="A"), ScreenContract(id="B"),
        ])
        self.assertEqual(dc.by_id("A").id, "A")
        self.assertIsNone(dc.by_id("C"))

    def test_ids(self):
        dc = DesignContract(screens=[
            ScreenContract(id="A"), ScreenContract(id="B"),
        ])
        self.assertEqual(dc.ids, ["A", "B"])

    def test_slice_for(self):
        dc = DesignContract(screens=[
            ScreenContract(id="A", name="Login"),
        ])
        s = dc.slice_for("A")
        self.assertIsNotNone(s)
        self.assertEqual(s["id"], "A")
        self.assertIsNone(dc.slice_for("Z"))

    def test_write_and_load(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        dc = DesignContract(screens=[
            ScreenContract(id="S1", name="Home", route="/"),
        ])
        path = dc.write(root)
        self.assertTrue(path.exists())

        loaded = load(root)
        self.assertEqual(len(loaded.screens), 1)
        self.assertEqual(loaded.screens[0].id, "S1")
        tmp.cleanup()

    def test_load_empty_returns_empty(self):
        tmp = tempfile.TemporaryDirectory()
        dc = load(tmp.name)
        self.assertEqual(dc.screens, [])
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
