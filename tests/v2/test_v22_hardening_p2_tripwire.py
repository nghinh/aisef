"""ROADMAP-2.2 wave-2 hardening P2 — tripwire serve-surface regression guards (owner #1 GO, 2026-11-06).

Pins six wave-2 survived-mutant gaps on `aisef2/app/tripwire.py` that the existing suite could not catch
because its fixtures were too clean (valid JSON, all-ASCII needles, unfrozen lists): the fail-closed
`_bundle_hit` except arm, `_canonical`'s JSON separators, `scan_text`'s JSON-escaped spelling for a
non-ASCII needle, and `_fragments`' recursion into FROZEN (tuple) arrays. The shipped code is correct —
these assertions fail only if a regression reintroduces one of those mutations. No product change."""
from __future__ import annotations

import json
import types
import unittest

from aisef2.app import tripwire
from aisef2.product.contract import freeze


class BundleHitFailsClosed(unittest.TestCase):
    def test_a_marker_bearing_but_unparseable_doc_is_refused_not_guessed(self):
        # tripwire.py:102 `except ValueError: return True` — a bundle marker in text that does not parse as a
        # single JSON object must refuse (fail closed), not be guessed CLEAN. None/False both turn it fail-open.
        project = types.SimpleNamespace(contracts=(), plan=types.SimpleNamespace(plan_hash="x"))
        self.assertIs(tripwire._bundle_hit("aisef-v2-project/1 {this is not valid json", project), True)
        self.assertIs(tripwire._bundle_hit("aisef-v2-authoring/1 <<corrupt>>", project), True)


class CanonicalSeparators(unittest.TestCase):
    def test_composite_needles_keep_the_json_item_and_pair_separators(self):
        # tripwire.py:37 separators=(",", ":"): emptying either blinds every composite needle to a real,
        # compact-canonical JSON leak (the kernel's own serialization).
        self.assertEqual(tripwire._canonical([1, 2, 3]), "[1,2,3]")
        self.assertEqual(tripwire._canonical({"a": 1, "b": 2}), '{"a":1,"b":2}')


class ScanTextEscapedSpelling(unittest.TestCase):
    def test_a_non_ascii_needle_is_caught_in_its_json_escaped_spelling(self):
        # tripwire.py:90 json.dumps(needle, ensure_ascii=False): the kernel serializes ensure_ascii=False, so a
        # leak carries the literal-unicode escaped spelling. The ensure_ascii=True mutant scans for the \uXXXX
        # spelling (absent) while the raw clause misses the escaped quote — a non-ASCII needle slips through.
        needle = 'café "total" ' + "z" * 12
        esc = json.dumps(needle, ensure_ascii=False)[1:-1]
        hits = tripwire.scan_text(f"log: {esc}", {needle: "BC-X"})
        self.assertEqual([h["contract"] for h in hits], ["BC-X"])


class FragmentsFrozenTuple(unittest.TestCase):
    def test_recursion_reaches_leaves_inside_a_frozen_tuple_array(self):
        # tripwire.py:46 isinstance(value, (list, tuple)): production specs are frozen (freeze() turns every
        # array into a tuple), so dropping `tuple` stops recursion into every array and the nested leaf never
        # becomes a needle. Exercise the exact frozen shape the kernel runs on.
        leaf = "the-grand-total-of-the-ledger"
        frozen = freeze({"scenario": ["expect", leaf]})          # MappingProxyType holding a tuple value
        self.assertIn(leaf, tripwire._fragments(frozen))
        self.assertIn(leaf, tripwire._fragments((("expect", leaf),)))   # a bare frozen tuple


if __name__ == "__main__":
    unittest.main()
