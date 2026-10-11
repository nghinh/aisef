"""V2.1 mutation survivors of aisef2/app/usage.py, batch T20a: the price-table gate, the session-stream reader, the
account and the no-progress report.

What each class pins is what a reader relies on:

* the price table is an operator-supplied number set that settings.load accepts or refuses before a run starts and that
  multiplies every token count (PriceTable*);
* a session's token classes and its "reported no tokens" steps are read exactly as the Budget's own reader
  (client.read_session) reads the same stream, and a partial report makes the cost unknown, never a number
  (SessionStream);
* the account follows the evidence's content (file names), says why an unknown price is unknown, and counts the
  preflight's spend where the preflight wrote it (Account*);
* `no_progress` reports an attempt only when it repeats the failures of the attempt before it (NoProgress).

`--verify` re-derives `usage` and `no_progress` with the same functions it compares against, so only a test that pins the
fields can see a wrong one. Offline; the oracle is hand-computed numbers and client.read_session, never usage itself."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client, preflight, settings, usage  # noqa: E402
from tests.v2 import test_app_run as base  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}
PRICE_FIELDS = ("input_per_mtok", "cache_read_per_mtok", "cache_write_per_mtok", "output_per_mtok")


def step(i=100, o=10, r=2, cr=50, cw=0):
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": i, "output": o, "reasoning": r,
                                                                  "cache": {"read": cr, "write": cw}}}})


def tokens_step(**tokens):
    return json.dumps({"type": "step_finish", "part": {"tokens": tokens}})


def load_settings(prices):
    return settings.load({**base.SETTINGS, "prices": prices})


class PriceNumbers(unittest.TestCase):
    """Every one of the four prices is a non-negative number (not a bool, a string or null), and the refusal names the
    setting's path and the limit: the operator reads `aisef run: refused: <reason>`.

    Pins aisef2/app/usage.py::price_problem [5, 6, 7, 35, 36]."""

    def test_a_price_that_is_not_a_non_negative_number_is_refused_by_name(self):
        self.assertIsNone(usage.price_problem(PRICES))
        for key in PRICE_FIELDS:
            for bad in (-1, "1", True, None):
                with self.subTest(key=key, bad=bad):
                    why = usage.price_problem({**PRICES, key: bad})
                    self.assertTrue(why)                      # settings.load tests `if why:`: '' would accept it
                    self.assertIn(f"prices.{key}", why)       # the settings path of the offending field
                    self.assertIn("non-negative", why)        # what is required of it
                    with self.assertRaises(settings.SettingsError) as c:
                        load_settings({**PRICES, key: bad})
                    self.assertIn(f"prices.{key}", str(c.exception))

    def test_integer_prices_and_a_free_class_are_prices(self):
        table = {**PRICES, "input_per_mtok": 3, "cache_read_per_mtok": 0, "cache_write_per_mtok": 2, "output_per_mtok": 4}
        self.assertIsNone(usage.price_problem(table))
        self.assertEqual(load_settings(table).prices, table)


class PriceTableShape(unittest.TestCase):
    """The table names its currency and its source, holds exactly the documented keys, and each refusal says which
    setting it is about (the CLI prints the reason alone).

    Pins aisef2/app/usage.py::price_problem [12, 13, 27, 30, 33]."""

    def test_a_currency_that_is_not_a_non_empty_string_is_refused(self):
        for currency in ("", 5, None, ["USD"]):
            with self.subTest(currency=currency):
                why = usage.price_problem({**PRICES, "currency": currency})
                self.assertTrue(why)
                self.assertIn("currency", why)
                with self.assertRaises(settings.SettingsError) as c:
                    load_settings({**PRICES, "currency": currency})
                self.assertIn("currency", str(c.exception))
        self.assertEqual(load_settings({**PRICES, "currency": "EUR"}).prices["currency"], "EUR")

    def test_a_source_that_is_not_a_non_empty_string_is_refused(self):
        for source in ("", 5, ["x"], None):
            with self.subTest(source=source):
                why = usage.price_problem({**PRICES, "source": source})
                self.assertTrue(why)
                self.assertIn("source", why)
                with self.assertRaises(settings.SettingsError):
                    load_settings({**PRICES, "source": source})

    def test_the_key_set_refusal_names_the_setting_and_the_keys(self):
        keys = ("currency", "input_per_mtok", "cache_read_per_mtok", "cache_write_per_mtok", "output_per_mtok", "source",
                "effective_date")
        for table in ({**PRICES, "extra": 1}, ["USD"], "USD"):
            with self.subTest(table=table):
                why = usage.price_problem(table)
                self.assertTrue(why)
                self.assertIn("prices", why)
                for key in keys:
                    self.assertIn(key, why)
                with self.assertRaises(settings.SettingsError) as c:
                    load_settings(table)
                self.assertIn("prices", str(c.exception))


class SessionStream(unittest.TestCase):
    """A session's account is what the Budget's reader (client.read_session) counts for the same stream: the same lines,
    the same steps, the same blind steps, and input = uncached + cache read + cache write, output = output + reasoning.
    A step that reports only part of its tokens reports none: the session's cost is unknown, never a number.

    Pins aisef2/app/usage.py::session_tokens [23, 28, 33, 35, 38, 39]."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = pathlib.Path(self._tmp.name)
        self.sessions = self.out / "sessions"
        self.sessions.mkdir()

    def put(self, *lines, tail=b"", name="S1.developer.1.jsonl") -> pathlib.Path:
        log = self.sessions / name
        log.write_bytes(b"".join(x.encode("utf-8") + b"\n" for x in lines) + tail)
        return log

    def agrees_with_the_budget(self, log: pathlib.Path) -> dict:
        mine, theirs = usage.session_tokens(log), client.read_session(log)
        t = mine["tokens"]
        self.assertEqual(t["input"] + t["cache_read"] + t["cache_write"], theirs["tokens"]["input"])
        self.assertEqual(t["output"] + t["reasoning"], theirs["tokens"]["output"])
        self.assertEqual(mine["steps"], theirs["turns"])
        self.assertEqual(mine["steps_without_tokens"], theirs["steps_without_tokens"])
        return mine

    def test_cache_write_tokens_are_counted_in_their_own_class(self):
        got = self.agrees_with_the_budget(self.put(step(i=100, o=10, r=2, cr=50, cw=7)))
        self.assertEqual(got, {"tokens": {"input": 100, "cache_read": 50, "cache_write": 7, "output": 10, "reasoning": 2},
                               "steps": 1, "steps_without_tokens": 0})
        self.assertEqual(client.read_session(self.sessions / "S1.developer.1.jsonl")["tokens"], {"input": 157, "output": 12})

    def test_a_cache_report_may_lack_a_class(self):
        for cache in ({"read": 5}, {"write": 3}, {}, None):
            with self.subTest(cache=cache):
                log = self.put(tokens_step(**{"input": 100, "output": 10, "cache": cache}))
                got = self.agrees_with_the_budget(log)
                self.assertEqual(got["tokens"], {"input": 100, "cache_read": (cache or {}).get("read", 0),
                                                 "cache_write": (cache or {}).get("write", 0), "output": 10, "reasoning": 0})
                self.assertEqual((got["steps"], got["steps_without_tokens"]), (1, 0))

    def test_a_line_that_is_json_but_not_an_event_object_is_skipped(self):
        """A stray line that parses as JSON but is not an object (a number, null, a list, a string, a boolean) is not an
        event and does not abort the account: the same two steps as the stream without it, as the Budget counts them.
        Whether an indented object counts is not promised, and is not pinned."""
        log = self.put(step(), "123", "null", "[1, 2]", '"text"', "true", step())
        got = self.agrees_with_the_budget(log)
        self.assertEqual((got["steps"], got["steps_without_tokens"]), (2, 0))
        self.assertEqual(got["tokens"], {"input": 200, "cache_read": 100, "cache_write": 0, "output": 20, "reasoning": 4})

    def test_a_log_with_bytes_that_are_not_utf8_is_still_read(self):
        """What a killed client leaves: a line cut inside a multi-byte character, and bytes that are not UTF-8 mid-log."""
        text = b'{"type": "text", "part": {"text": "\xff\xfe"}}\n'
        log = self.sessions / "S1.developer.1.jsonl"
        log.write_bytes(step().encode() + b"\n" + text + step(cw=7).encode() + b"\n"
                        + b'{"type": "text", "part": {"text": "\xe2\x82')
        got = self.agrees_with_the_budget(log)
        self.assertEqual((got["steps"], got["steps_without_tokens"]), (2, 0))
        self.assertEqual(got["tokens"], {"input": 200, "cache_read": 100, "cache_write": 7, "output": 20, "reasoning": 4})

    def test_a_step_that_reports_part_of_its_tokens_reports_none(self):
        partial = {"no input": {"output": 5}, "no output": {"input": 5}, "input not an int": {"input": "5", "output": 1},
                   "output not an int": {"input": 5, "output": "1"}}
        for name, tokens in partial.items():
            with self.subTest(name):
                log = self.put(step(i=100, o=10, r=2, cr=50, cw=7), tokens_step(**tokens))
                got = self.agrees_with_the_budget(log)
                self.assertEqual((got["steps"], got["steps_without_tokens"]), (2, 1))
                self.assertEqual(got["tokens"], {"input": 100, "cache_read": 50, "cache_write": 7, "output": 10, "reasoning": 2})
                u = usage.usage(self.out, [], PRICES, {})
                self.assertIsNone(u["sessions"][0]["cost"])
                self.assertIsNone(u["cost"]["value"])
                self.assertTrue(u["cost"]["status"].startswith("partial"))
                self.assertEqual(u["cost"]["sessions_unknown"], ["S1.developer.1.jsonl"])


class AccountOrderAndWhy(unittest.TestCase):
    """The account is a function of the evidence's content: its sessions (and the unknown ones) in file-name order
    whatever order the directory enumerates, since `--verify` and the anchor workflow move a run directory between
    machines and compare lists. Without a price table the null cost says why.

    Pins aisef2/app/usage.py::usage [8, 17, 34, 36]."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = pathlib.Path(self._tmp.name)
        (self.out / "sessions").mkdir()

    def log(self, name, *lines):
        (self.out / "sessions" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_sessions_follow_the_file_names_not_the_directory(self):
        names = ["S1.developer.1.jsonl", "S2.developer.1.jsonl", "S3.reviewer.1.jsonl", "S4.reviewer.1.jsonl"]
        blind = json.dumps({"type": "step_finish", "part": {}})
        for name, line in zip(names, (step(), blind, step(), blind), strict=True):
            self.log(name, line)
        real = pathlib.Path.glob

        def backwards(path, pattern, *args, **kw):      # a filesystem that enumerates against the names
            return iter(sorted(real(path, pattern, *args, **kw), reverse=True))
        with mock.patch.object(pathlib.Path, "glob", backwards):
            u = usage.usage(self.out, [], PRICES, {})
        self.assertEqual([r["session"] for r in u["sessions"]], names)
        self.assertEqual(u["cost"]["sessions_unknown"], [names[1], names[3]])

    def test_an_unknown_price_says_why(self):
        self.log("S1.developer.1.jsonl", step())
        for prices in (None, {}):
            with self.subTest(prices=prices):
                cost = usage.usage(self.out, [], prices, {})["cost"]
                self.assertEqual((cost["value"], cost["status"]), (None, "unknown"))
                self.assertIn("why", cost)
                self.assertIn("pric", cost["why"].lower())    # the cause: there is no price (or pricing) table


class AccountPreflight(unittest.TestCase):
    """The preflight's spend is paid spend of the run: its requests and tokens are in the account under `preflight`
    (read from the ledger the preflight wrote, out/preflight/LEDGER.jsonl) and in the money, priced like the
    sessions'. Without it a `known` cost would be one preflight short.

    Pins aisef2/app/usage.py::usage [18, 22, 48, 74, 93, 99, 100]."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = pathlib.Path(self._tmp.name)
        (self.out / "sessions").mkdir()
        (self.out / "sessions" / "S1.developer.1.jsonl").write_text(step(i=1_000_000, o=0, r=0, cr=0) + "\n", encoding="utf-8")

        def transport(path, body=None):         # one listing, one probe that spent 1,000,000 in and 500,000 out
            if body is None:
                return 200, {"data": [{"id": "m", "owned_by": "o"}]}
            return 200, {"model": "m", "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}}
        preflight.run("prov/m", 1, transport, self.out / "preflight")
        self.assertTrue((self.out / "preflight" / "LEDGER.jsonl").is_file())

    def test_the_preflights_spend_is_in_the_account_and_in_the_money(self):
        u = usage.usage(self.out, [], PRICES, {})
        self.assertEqual(u["preflight"], {"provider_requests": 2, "turns": 0, "input_tokens": 1_000_000,
                                          "output_tokens": 500_000, "unaccounted": []})
        # sessions 1,000,000 x 1.0 + preflight input 1,000,000 x 1.0 + preflight output 500,000 x 4.0, per million
        self.assertEqual((u["cost"]["value"], u["cost"]["known"], u["cost"]["status"]), (4.0, 4.0, "known"))
        self.assertEqual(u["tokens"], {"input": 1_000_000, "cache_read": 0, "cache_write": 0, "output": 0, "reasoning": 0})


class NoProgress(unittest.TestCase):
    """A story's attempt is reported as repeating only when it observed failures and they are the failures of the
    attempt before it: the report is the owner's evidence that retries changed nothing, so a story that failed
    differently each time, or an attempt that observed none, is not "no progress".

    Pins aisef2/app/usage.py::no_progress [14]."""

    @staticmethod
    def ev(kind, **data):
        return {"type": kind, "data": {"story_id": "S1", **data}}

    def observed(self, code, detail):
        return self.ev("failure/observed", code=code, detail=detail)

    def test_only_the_attempt_that_repeats_the_one_before_is_reported(self):
        events = [self.observed("CONTRACT_UNSATISFIED", "proof of C1"), self.ev("story/retry"),
                  self.observed("TESTS_INADEQUATE", "q"), self.ev("story/retry"),
                  self.observed("TESTS_INADEQUATE", "q"), self.ev("story/rollback")]
        self.assertEqual(usage.no_progress(events), [{"story": "S1", "attempts_repeating_the_one_before": [3],
                                                      "failures": ["TESTS_INADEQUATE: q"]}])

    def test_a_story_that_fails_differently_every_attempt_is_not_reported(self):
        events = [self.observed("CONTRACT_UNSATISFIED", "proof of C1"), self.ev("story/retry"),
                  self.observed("TESTS_INADEQUATE", "q"), self.ev("story/retry"),
                  self.observed("TESTS_INADEQUATE", "r"), self.ev("story/rollback")]
        self.assertEqual(usage.no_progress(events), [])

    def test_attempts_that_observed_no_failure_are_not_a_repeat(self):
        events = [self.ev("story/retry"), self.ev("story/retry"), self.ev("story/rollback")]
        self.assertEqual(usage.no_progress(events), [])


if __name__ == "__main__":
    unittest.main()
