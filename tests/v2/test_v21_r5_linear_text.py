"""V2.1 (owner decision of 2026-10-15, item 4, the sibling of the reproducer's pattern): the two places the kernel reads a
model's reply with a pattern of its own — the model reviewer's `{...}` document (`adapters._braces`) and the OCR
comment's fenced reproducer block (`review_ocr._fence`) — take time linear in the text.

Both patterns are static, not the model's: the model supplies the text. `re.search(r"\\{.*\\}", text, re.S)` tries every
`{` and reads to the end of the text for each, so a reply of `{` and no `}` after them costs the square of its length
(measured: 0.026 s at 10,000 characters and 0.103 s at 20,000, four times for every doubling); `REPRODUCER_FENCE` does the
same for a comment of many openings and no close (0.062 s at 1,000 openings, 0.25 s at 2,000). The replacements find the same span by
scans, and the pattern's own grammar confirms it. Pinned here: the replacement gives exactly what the pattern gave —
exhaustively over every text of a small alphabet up to a length, and over a seeded draw of longer ones built from the
pieces of a fence — and ends in a bounded time on the texts that cost the pattern the square."""

from __future__ import annotations

import itertools
import pathlib
import random
import re
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters, review_ocr  # noqa: E402

BRACES = re.compile(r"\{.*\}", re.S)      # the pattern as it was, for comparison only
OPEN = "```aisef-reproducer\n"
#: the texts below cost the old patterns the square of their length (minutes at 400,000 characters, by the rate measured
#: above); the scans take milliseconds, and the bound is far above that and far below the squares
BOUND_S = 5.0


def old_braces(text: str):
    m = BRACES.search(text)
    return m.group(0) if m else None


def view(m: re.Match | None):
    return None if m is None else (m.start(), m.end(), m.group(1))


class BracesAreWhatThePatternMatched(unittest.TestCase):
    def test_every_text_of_four_characters_up_to_length_eight(self):
        for n in range(9):
            for chars in itertools.product("{}a\n", repeat=n):
                text = "".join(chars)
                self.assertEqual(adapters._braces(text), old_braces(text), repr(text))

    def test_the_shapes_a_reply_has(self):
        for text, want in (
                ('{"findings": []}', '{"findings": []}'),
                ('prose {"findings": [{"id": "a"}]} more prose', '{"findings": [{"id": "a"}]}'),
                ('first {"a": 1} then {"b": 2} end', '{"a": 1} then {"b": 2}'),     # greedy: to the last `}`
                ("```json\n{\n  \"findings\": []\n}\n```", "{\n  \"findings\": []\n}"),
                ("} {", None), ("{", None), ("}", None), ("", None), ("no braces", None), ("{}", "{}"), ("}{}", "{}"),
                ("{ }", "{ }"), ("{\n}", "{\n}"), ("{{}", "{{}"), ("{}}", "{}}")):
            with self.subTest(text):
                self.assertEqual(adapters._braces(text), want)
                self.assertEqual(old_braces(text), want)

    def test_a_reply_of_openings_and_no_close_is_linear(self):
        for text in ("{" * 400_000, "{" * 200_000 + "x" * 200_000, ("{ " * 200_000), "{\n" * 200_000,
                     "}" * 400_000, "{" * 400_000 + "}"):
            began = time.monotonic()
            got = adapters._braces(text)
            self.assertLess(time.monotonic() - began, BOUND_S)
            self.assertEqual(got, text if text.endswith("}") and "{" in text else None)


class FenceIsWhatThePatternMatched(unittest.TestCase):
    PIECES = ("```aisef-reproducer", "\n", "{", "}", " ", "\t", "```", "a", "\r\n", "\n\n", "x}", "{}", "\n```", "}\n```")

    def same(self, text: str) -> None:
        self.assertEqual(view(review_ocr._fence(text)), view(review_ocr.REPRODUCER_FENCE.search(text)), repr(text))

    def test_every_text_of_up_to_four_pieces(self):
        for n in range(5):
            for pieces in itertools.product(self.PIECES, repeat=n):
                self.same("".join(pieces))

    def test_a_draw_of_longer_texts(self):
        rnd = random.Random(20261015)
        for _ in range(60_000):
            self.same("".join(rnd.choice(self.PIECES) for _ in range(rnd.randint(5, 24))))

    def test_the_shapes_a_comment_has(self):
        block = OPEN + '{"clause": "R-1/1"}\n```'
        for text in (block, "text before\n" + block + "\ntext after", block + "\n" + block, OPEN + "{ not json }\n```\n" + block,
                     OPEN + '{"a": {"b": 1}}  \n```', OPEN + "{}\n\n\n```", OPEN + "{}\n``", "```aisef-reproducer {}\n```",
                     "```aisef-reproducer\n\n{}\n```", "```aisef-reproducer\n [] \n```", OPEN + "{}```", "x" * 100,
                     OPEN + "{" + "}" * 5 + "\n```", OPEN + '{"a": "}\n```"}\n```'):
            with self.subTest(text[:40]):
                self.same(text)

    def test_what_a_comment_carries_is_what_it_carried(self):
        for content, rep, rest in (
                ('see\n' + OPEN + '{"clause": "R-1/1", "n": 1}\n```\nthanks', {"clause": "R-1/1", "n": 1}, "see\n\nthanks"),
                (OPEN + "{ not json }\n```", None, OPEN + "{ not json }\n```"),
                ("no block", None, "no block")):
            with self.subTest(content[:30]):
                self.assertEqual(review_ocr.reproducer_of(content), (rep, rest))

    def test_a_comment_of_openings_and_no_close_is_linear(self):
        for text in (OPEN + "{" * 400_000, (OPEN + "{") * 20_000, (OPEN + "{\n") * 20_000, OPEN + "{" + "}" * 400_000,
                     OPEN + "{" + "} " * 200_000, "```aisef-reproducer\n" * 20_000, OPEN[:-1] + " " * 400_000,
                     ("```aisef-reproducer" + " " * 1000) * 400, OPEN + "{" + "}" + " " * 400_000,
                     (OPEN + "{}" + " " * 1000) * 400):
            began = time.monotonic()
            got = review_ocr.reproducer_of(text)
            self.assertLess(time.monotonic() - began, BOUND_S)
            self.assertEqual(got, (None, text))

    def test_a_block_after_many_openings_is_found_in_linear_time(self):
        """The first opening decides: when it closes the block is the pattern's match, however much comes before and
        after; the cost is the text's, not its square."""
        text = "x" * 200_000 + OPEN + '{"clause": "R-1/1"}\n```' + "y" * 200_000
        began = time.monotonic()
        rep, rest = review_ocr.reproducer_of(text)
        self.assertLess(time.monotonic() - began, BOUND_S)
        self.assertEqual((rep, rest), ({"clause": "R-1/1"}, "x" * 200_000 + "y" * 200_000))


if __name__ == "__main__":
    unittest.main()
