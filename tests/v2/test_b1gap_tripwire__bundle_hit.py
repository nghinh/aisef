"""v2.2 B1 gap kills for aisef2/app/tripwire.py::_bundle_hit — one test per surviving mutant;
every assertion holds on the unmutated tree."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from aisef2.app import tripwire


def project():
    return SimpleNamespace(contracts={"BC-ADD": object()}, plan=SimpleNamespace(plan_hash="a" * 64))


class BundleHitGapKills(unittest.TestCase):
    # kills: L98 returns None — the no-marker early exit must return the identity False, not None
    def test_no_marker_text_returns_identity_false(self):
        self.assertIs(tripwire._bundle_hit("a file with no bundle marker at all", project()), False)


if __name__ == "__main__":
    unittest.main()
