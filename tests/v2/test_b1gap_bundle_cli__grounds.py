"""B1 gap kill tests for aisef2/app/bundle_cli.py::_grounds.

`_grounds` iterates `kept` (a set) through `sorted(...)`, so the `contracts` list of each
row — and the row order — is deterministic across runs and hash seeds. The surviving mutant
replaces that `sorted()` with `list()`, making the report's `approvals_kept_grounds` order
follow set-iteration (hash) order. Every existing assertion normalizes order away; this file
pins it. Offline, no fixtures: with `assessed={}` every name groups as "current".
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


class GroundsOrderIsDeterministic(unittest.TestCase):
    # Kills: L306 sorted() -> list()
    def test_contracts_of_a_group_are_listed_in_sorted_order(self):
        # A set whose iteration order provably differs from sorted order in THIS process,
        # whatever the hash seed: grow until the orders diverge (first try, in practice).
        kept = None
        for n in range(16, 256):
            candidate = {f"contract-{i:03d}" for i in range(n)}
            if list(candidate) != sorted(candidate):
                kept = candidate
                break
        self.assertIsNotNone(kept, "no set with iteration order != sorted order (fixture)")

        rows = bundle_cli._grounds(kept, {}, {})

        [row] = rows  # every name groups as ("current",): one row
        self.assertEqual(row["from"], {"release": "current"})
        # sorted() on L306 makes the kept ids come out sorted; list() leaks set order.
        self.assertEqual(row["contracts"], sorted(kept))


if __name__ == "__main__":
    unittest.main()
