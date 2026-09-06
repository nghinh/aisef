"""`aisef doc` — tra tài liệu theo yêu cầu, có cache, không bịa (S2)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aisef.kit import docs as D

SEARCH = json.dumps({"results": [{"id": "/other/vitest-plugin", "title": "Vitest Plugin"},
                                  {"id": "/vitest-dev/vitest", "title": "Vitest"}]})


def fake_fetch(calls):
    def f(url):
        calls.append(url)
        if "/search?" in url:
            return SEARCH
        return "### Run Vitest with coverage\n\nnpx vitest --coverage\n"
    return f


class TestLookup(unittest.TestCase):
    def test_picks_exact_name_and_fetches_topic(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            d = D.lookup("vitest", "coverage", fetch=fake_fetch(calls), root=Path(tmp))
        self.assertEqual(d.library, "/vitest-dev/vitest")
        self.assertIn("--coverage", d.text)
        self.assertFalse(d.cached)
        self.assertIn("topic=coverage", calls[1])

    def test_second_call_is_served_from_cache(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            D.lookup("vitest", "coverage", fetch=fake_fetch(calls), root=Path(tmp))
            d = D.lookup("vitest", "coverage", fetch=fake_fetch(calls), root=Path(tmp))
        self.assertTrue(d.cached)
        self.assertEqual(len(calls), 2)   # không gọi mạng lần hai

    def test_unknown_package_is_an_error_not_a_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(D.DocError):
                D.lookup("thu-vien-khong-co", fetch=lambda u: json.dumps({"results": []}), root=Path(tmp))

    def test_empty_body_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(D.DocError):
                D.lookup("vitest", fetch=lambda u: SEARCH if "/search?" in u else "  ", root=Path(tmp))
