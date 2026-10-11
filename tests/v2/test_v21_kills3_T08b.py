"""V2.1 (D) mutation survivors of aisef2/app/lineage.py::usage_lineage, batch T08b: the lineage's per-run breakdown and
its total (`rec["lineage_usage"]` of a continuation, `aisef run --parent`).

The record is written right after the call and `--verify` does not re-derive it, so these tests are what protects it.
Hermetic: run directories that hold only a session stream; `lineage_account`'s own rules (what is recorded, what is
unaccounted, what is superseded) are measured in test_v21_continue_integrity — here its output is GIVEN, which is what
lets every combination be built without killing a process."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage, usage  # noqa: E402

# input 1.0 USD per million tokens, output 4.0: `step(i=1_000_000, o=0, r=0, cr=0)` costs exactly 1.0 USD.
PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}
ONE_USD = (1_000_000, 0, 0, 0)          # input, output, reasoning, cache read
TWO_USD = (2_000_000, 0, 0, 0)
OWN = {"tokens": {"input": 7, "cache_read": 5, "cache_write": 3, "output": 2, "reasoning": 1},
       "cost": {"value": 0.5, "status": "known", "currency": "USD"}}
ROW_KEYS = {"run", "recorded", "superseded", "tokens", "cost"}


def step(i, o, r, cr):
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": i, "output": o, "reasoning": r,
                                                                  "cache": {"read": cr, "write": 0}}}})


class Hermetic(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)

    def run_dir(self, name: str, spend=ONE_USD) -> pathlib.Path:
        """A run directory holding one finished session of `spend` tokens (no journal, no record)."""
        d = self.root / name
        (d / "sessions").mkdir(parents=True)
        (d / "sessions" / "S1.developer.1.jsonl").write_text(step(*spend) + "\n", encoding="utf-8")
        return d

    @staticmethod
    def account(d: pathlib.Path, recorded: bool = True, unaccounted=(), superseded: bool = False) -> dict:
        a = {"run": str(d), "recorded": recorded, "unaccounted": list(unaccounted)}
        if superseded:                      # `account_of(...) | {"superseded": True}`: present only when True
            a["superseded"] = True
        return a

    def usage_lineage(self, accounts: list, own=OWN, events=()) -> dict:
        with mock.patch.object(lineage, "lineage_account", return_value={"runs": accounts}), \
                mock.patch.object(lineage, "events_of", return_value=(list(events), False)):
            return lineage.usage_lineage(self.root / "pred", self.root / "child", own, PRICES)


class RowsSayWhatEachRunIs(Hermetic):
    """Every row of the lineage's breakdown says which run it is, whether that run has its record (RUN.json) and
    whether it is a superseded sibling — a refused or abandoned child whose preflight may have spent — and this run's
    row is last and recorded. The operator reads the breakdown to see which runs' last step may be missing and which
    spend belongs to the lineage proper.

    Pins aisef2/app/lineage.py::usage_lineage [8, 23, 28, 33, 49, 73]."""

    def test_every_row_says_whether_it_is_recorded_and_superseded_and_this_run_is_last(self):
        a, b, c = self.run_dir("a"), self.run_dir("b"), self.run_dir("c")
        rows = self.usage_lineage([self.account(a, recorded=True), self.account(b, recorded=False),
                                   self.account(c, recorded=True, superseded=True)])["runs"]
        self.assertEqual([r["run"] for r in rows], [str(a), str(b), str(c), "this run"])
        self.assertEqual([(r["recorded"], r["superseded"]) for r in rows[:-1]],
                         [(True, False), (False, False), (True, True)])
        for row in rows:
            self.assertEqual(set(row), ROW_KEYS, row)       # a reader iterating the rows needs the same keys on all
        self.assertEqual(rows[-1], {"run": "this run", "recorded": True, "superseded": False,
                                    "tokens": OWN["tokens"], "cost": OWN["cost"]})


class TotalIsKnownOnlyWhenEveryRunIs(Hermetic):
    """The lineage's total cost is a number only when every run's cost (this run's included) is a number, the sum of
    them with status `known`; one unknown part makes it `null` with a status of the class `unknown` — never `known`
    beside `null` and never a partial sum shown as the whole (a null is not 0).

    Pins aisef2/app/lineage.py::usage_lineage [16, 37, 39, 59] (unknown) and [35, 54, 55, 57, 58, 75] (known)."""

    def test_an_unknown_total_says_so(self):
        runs = [self.run_dir("a"), self.run_dir("b", TWO_USD), self.run_dir("c")]
        r = self.usage_lineage([self.account(runs[0]), self.account(runs[1]), self.account(runs[2], recorded=False)])
        self.assertIsNone(r["cost"]["value"])                  # one run has no record: its last step may be missing
        self.assertTrue(r["cost"]["status"].startswith("unknown"), r["cost"])
        self.assertNotEqual(r["cost"]["status"], "known")
        self.assertEqual(set(r["cost"]), {"value", "status"})

    def test_a_lineage_whose_every_run_is_accounted_has_a_known_total(self):
        a, b = self.run_dir("a"), self.run_dir("b", TWO_USD)
        r = self.usage_lineage([self.account(a), self.account(b)])
        self.assertEqual(r["cost"], {"value": 3.5, "status": "known"})              # 1.0 + 2.0 + this run's 0.5
        self.assertEqual([row["cost"]["value"] for row in r["runs"]], [1.0, 2.0, 0.5])
        self.assertEqual(r["runs"][-1]["cost"], OWN["cost"])                         # this run's cost is its own, whole
        self.assertEqual(r["tokens"], {"input": 3_000_007, "cache_read": 5, "cache_write": 3, "output": 2, "reasoning": 1})


class AnOverriddenCostKeepsWhatIsKnown(Hermetic):
    """A run whose spend is not fully accounted (an entry unaccounted, or no record) has its cost value `null` — its
    known part, currency, source and date kept so the unknown total still states what is known — and a status of the
    class `partial` that names why: the run's unaccounted entries, in order, separated; or, with none, that the run has
    no record.

    Pins aisef2/app/lineage.py::usage_lineage [19, 21, 47, 66, 67, 72, 77]."""

    def setUp(self) -> None:
        super().setUp()
        self.a, self.b = self.run_dir("a"), self.run_dir("b")
        r = self.usage_lineage([self.account(self.a, recorded=True, unaccounted=["u1: first", "u2: second"]),
                                self.account(self.b, recorded=False)])
        self.cost_a, self.cost_b = r["runs"][0]["cost"], r["runs"][1]["cost"]

    def test_a_run_with_unaccounted_entries_names_each_of_them_in_order(self):
        usage_cost = usage.usage(self.a, [], PRICES, {})["cost"]
        self.assertEqual((usage_cost["known"], usage_cost["currency"], usage_cost["status"]), (1.0, "USD", "known"))
        # what usage.usage knew (provenance, the known lower bound) is kept: only the value is withdrawn
        kept = {k: v for k, v in usage_cost.items() if k != "status"}
        self.assertEqual({k: v for k, v in self.cost_a.items() if k != "status"}, {**kept, "value": None})
        status = self.cost_a["status"]
        self.assertTrue(status.startswith("partial"), status)           # the class tag of the status vocabulary
        # the identifying elements, not the sentence: each entry whole, in the order given, and told apart
        first, second = status.find("u1: first"), status.find("u2: second")
        self.assertTrue(0 <= first and first + len("u1: first") <= second, status)
        self.assertNotEqual(status[first + len("u1: first"):second], "", status)

    def test_a_run_with_no_record_and_nothing_unaccounted_says_it_has_no_record(self):
        self.assertIsNone(self.cost_b["value"])
        self.assertEqual((self.cost_b["known"], self.cost_b["currency"]), (1.0, "USD"))
        self.assertTrue(self.cost_b["status"].startswith("partial"), self.cost_b)
        self.assertIn("record", self.cost_b["status"])


class ARetryInAJournalIsAccounted(Hermetic):
    """A lineage run whose journal holds a retry is accounted like any other: the events handed to `usage.usage` keep
    their data (`usage.usage` reads a story/retry's story_id). Were they stripped, `usage_lineage` would raise and
    run.py's `except Exception` would overwrite the run's own `usage` with an error and write no `lineage_usage`.

    Pins aisef2/app/lineage.py::usage_lineage [43, 62]."""

    def test_a_lineage_run_with_a_retry_in_its_journal_returns_its_tokens_and_cost(self):
        a = self.run_dir("a")
        retry = SimpleNamespace(seq=3, type="story/retry", data={"story_id": "S1"})
        r = self.usage_lineage([self.account(a)], events=[retry])
        self.assertEqual(r["runs"][0]["tokens"], usage.usage(a, [], PRICES, {})["tokens"])
        self.assertEqual(r["runs"][0]["tokens"]["input"], 1_000_000)
        self.assertEqual(r["runs"][0]["cost"]["value"], 1.0)


if __name__ == "__main__":
    unittest.main()
