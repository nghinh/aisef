"""V2.1 (D) mutation-survivor batch T20b: the run's account (aisef2/app/usage.py::usage) as the evidence it is.

`usage()` is the single writer of `RUN.json` `usage` (run.py) and the single re-deriver of it (`--verify`, lineage):
the verifier calls the same function and compares, so a field that is dropped, renamed or miscounted here is dropped,
renamed or miscounted on both sides and still VERIFIED. Only a test of the account itself sees it. What is pinned:
what the journal says (requests, retries, with the story each belongs to), each session's row with its lower-bound
marker, the provenance of a money figure (currency, source, effective date), an unreadable preflight ledger that must
not cost the record, and a wall time that is computed from integer timestamps and never from half a record."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import usage  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}
ZERO = dict.fromkeys(usage.CLASSES, 0)


def step(i=100, o=10, r=2, cr=50, cw=0):
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": i, "output": o, "reasoning": r,
                                                                  "cache": {"read": cr, "write": cw}}}})


BLIND = json.dumps({"type": "step_finish", "part": {}})      # a finished step that reports no tokens


class Account(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = pathlib.Path(self._tmp.name)
        (self.out / "sessions").mkdir()

    def log(self, name, *lines):
        (self.out / "sessions" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


class JournalCounts(Account):
    """The account's requests and retries are what the journal decided — the `provider/request` events and the
    `story/retry` events, each retry attributed to the story it names — never a total of events and never a side
    counter. A run that retried a story must still produce an account (a KeyError here would turn the record's
    `usage` into an error and cost it `no_progress` and the lineage).

    Pins aisef2/app/usage.py::usage [19, 23, 45, 49, 58, 75, 76, 94, 95]."""

    def events(self):
        seq = iter(range(1, 100))

        def ev(t, story):
            return {"seq": next(seq), "type": t, "data": {"story_id": story}}
        return [ev("provider/request", "S1"), ev("failure/observed", "S1"), ev("provider/request", "S2"),
                ev("provider/result", "S1"), ev("provider/request", "S2"), ev("story/retry", "S2"),
                ev("story/retry", "S1"), ev("story/retry", "S2"), ev("provider/request", "S1")]

    def test_requests_are_the_provider_requests_and_retries_are_per_story(self):
        u = usage.usage(self.out, self.events(), None, {})
        # 9 events, 4 of them requests, 3 retries: no figure can stand in for another
        self.assertEqual(u["provider_requests_journaled"], 4)
        self.assertEqual(u["retries"], {"S1": 1, "S2": 2})

    def test_a_journal_without_requests_or_retries_counts_none(self):
        u = usage.usage(self.out, [{"seq": 1, "type": "story/commit", "data": {"story_id": "S1"}}], None, {})
        self.assertEqual((u["provider_requests_journaled"], u["retries"]), (0, {}))


class SessionRows(Account):
    """Each session has its row: its file name, its tokens by class, its finished steps and the steps that reported
    no tokens. Without a price table the rows are the only place that says a session's tokens are a lower bound
    (`steps_without_tokens`); with one each row also holds its cost, and a session that is partial has `null`.

    Pins aisef2/app/usage.py::usage [20, 27, 28, 46, 56]."""

    DEV = {"session": "S1.developer.1.jsonl", "steps": 1, "steps_without_tokens": 0,
           "tokens": {"input": 100, "cache_read": 50, "cache_write": 0, "output": 10, "reasoning": 2}}
    REV = {"session": "S2.reviewer.1.jsonl", "steps": 1, "steps_without_tokens": 1, "tokens": ZERO}

    def setUp(self) -> None:
        super().setUp()
        self.log("S1.developer.1.jsonl", step())
        self.log("S2.reviewer.1.jsonl", BLIND)

    def test_rows_without_prices(self):
        self.assertEqual(usage.usage(self.out, [], None, {})["sessions"], [self.DEV, self.REV])

    def test_rows_with_prices_carry_the_cost_or_null(self):
        # (100 * 1.0 + 50 * 0.1 + (10 + 2) * 4.0) / 1e6; the blind session's cost is unknown, never 0
        self.assertEqual(usage.usage(self.out, [], PRICES, {})["sessions"],
                         [{**self.DEV, "cost": 0.000153}, {**self.REV, "cost": None}])


class PriceProvenance(Account):
    """A figure of money names its unit and the table it came from: the account passes the operator's currency,
    source and effective date through. `price_problem` refuses a table without them precisely so the money can be
    traced; an account that dropped them would make that requirement empty (lineage copies the cost record on).

    Pins aisef2/app/usage.py::usage [38, 39, 40, 63, 64, 65]."""

    def test_the_cost_names_currency_source_and_effective_date_of_the_table(self):
        table = {**PRICES, "currency": "EUR", "source": "vendor price page", "effective_date": "2026-09-30"}
        self.assertIsNone(usage.price_problem(table))
        self.log("S1.developer.1.jsonl", step(i=1_000_000, o=0, r=0, cr=0))
        cost = usage.usage(self.out, [], table, {})["cost"]
        self.assertEqual((cost["currency"], cost["source"], cost["effective_date"]),
                         ("EUR", "vendor price page", "2026-09-30"))
        self.assertEqual((cost["value"], cost["status"]), (1.0, "known"))


class UnreadablePreflightLedger(Account):
    """A preflight ledger that does not read — a file that is not JSON (a torn last line is what a killed writer
    leaves), a row without its `n`, a path that is a directory — must not abort the account: `usage()` returns, the
    preflight is `null` (not an invented figure) and the sessions' tokens are there. Run.py records `usage` as an
    error when the call raises, and loses `no_progress` and `lineage_usage` with it. Deliberately not asserted: the
    run's cost status when the ledger does not read (an owner decision, see the batch report).

    Pins aisef2/app/usage.py::usage [29, 30, 31, 37]."""

    def account_with(self, write_ledger):
        (self.out / "preflight").mkdir(exist_ok=True)
        ledger = self.out / "preflight" / "LEDGER.jsonl"
        if ledger.is_dir():
            ledger.rmdir()
        ledger.unlink(missing_ok=True)
        write_ledger(ledger)
        self.log("S1.developer.1.jsonl", step(i=1_000_000, o=0, r=0, cr=0))
        return usage.usage(self.out, [], PRICES, {})

    def test_an_unreadable_ledger_leaves_the_preflight_null_and_the_account_produced(self):
        cases = {
            "not JSON (ValueError)": lambda p: p.write_text("{not json", encoding="utf-8"),
            "a row without n (KeyError)": lambda p: p.write_text('{"event": "sent"}\n', encoding="utf-8"),
            "a directory at the path (OSError)": lambda p: p.mkdir(),
        }
        for name, write in cases.items():
            with self.subTest(name):
                u = self.account_with(write)
                self.assertIsNone(u["preflight"])
                self.assertEqual(u["tokens"]["input"], 1_000_000)


class WallTime(Account):
    """The wall time is the record's `finished - started` when both are numbers — integers as well as floats (JSON
    keeps `1` an int; the clock is injectable) — and `null` when either is missing: `--verify` re-derives it from a
    record read from disk, which may have lost one timestamp, and must answer from the evidence rather than die.

    Pins aisef2/app/usage.py::usage [72, 106, 108]."""

    def wall(self, rec):
        return usage.usage(self.out, [], None, rec)["wall_s"]

    def test_integer_timestamps_are_numbers(self):
        self.assertEqual(self.wall({"started": 1, "finished": 4}), 3)          # [106] [108]
        self.assertEqual(self.wall({"started": 1.0, "finished": 4}), 3.0)      # [108]
        self.assertEqual(self.wall({"started": 1, "finished": 4.5}), 3.5)      # [106]

    def test_a_record_with_one_timestamp_has_no_wall_time_and_does_not_raise(self):
        self.assertIsNone(self.wall({"started": 1.0}))
        self.assertIsNone(self.wall({"finished": 3.0}))
        self.assertIsNone(self.wall({"started": 1.0, "finished": None}))
        self.assertEqual(self.wall({"started": 1.0, "finished": 3.5}), 2.5)


if __name__ == "__main__":
    unittest.main()
