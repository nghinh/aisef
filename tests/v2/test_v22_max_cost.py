"""ROADMAP-2.2 C2 — the live dollar ceiling. `settings.max_cost` (optional, needs a price table) makes `Budget` carry
the run's spend in money, computed from the five token classes the SAME way the post-hoc account reads them
(`usage.session_tokens`/`_usd`), and stop the run when the cost reaches the ceiling. Cost that cannot be known (a
finished step reported no tokens) is already `unaccounted`, so the run fails closed regardless; the figure is None so
no partial number passes for the total. Absent max_cost ⇒ the budget is 2.0.0's four counters, byte for byte.

This is the offline proof the owner required before any paid run: a fake stream whose cost crosses the ceiling stops
the run at the ceiling (`reached` is what the run loop breaks on), and a fake step with no tokens fails closed."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from aisef2.app import client, settings
from aisef2.app.verify import verify
from tests.v2 import test_app_run as e2e

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 5.0, "source": "test", "effective_date": "2026-11-04"}
LIMITS = {"provider_requests": 99, "turns": 99, "input_tokens": 10 ** 9, "output_tokens": 10 ** 9}
ZERO = dict.fromkeys(LIMITS, 0)


def _session(dirpath: pathlib.Path, name: str, steps: list[dict]) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "step_finish", "part": {"tokens": tk}}) for tk in steps]
    (dirpath / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


class SettingsMaxCost(unittest.TestCase):
    def test_max_cost_needs_prices_and_is_a_positive_amount(self):
        base = {k: v for k, v in e2e.SETTINGS.items() if k not in ("prices", "max_cost")}
        with self.assertRaisesRegex(settings.SettingsError, "needs a price table"):
            settings.load({**base, "max_cost": 5.0})
        for bad in (0, -1, True, "5"):
            with self.assertRaises(settings.SettingsError):
                settings.load({**base, "prices": PRICES, "max_cost": bad})
        s = settings.load({**base, "prices": PRICES, "max_cost": 2.5})
        self.assertEqual(s.max_cost, 2.5)
        self.assertIn("max_cost", settings.OPTIONAL)

    def test_absent_is_none(self):
        base = {k: v for k, v in e2e.SETTINGS.items() if k != "max_cost"}
        self.assertIsNone(settings.load(base).max_cost)


class BudgetCost(unittest.TestCase):
    def budget(self, steps_per_session: list[list[dict]], max_cost: float | None, base: dict = ZERO):
        d = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        logs = d / "sessions"
        for i, steps in enumerate(steps_per_session):
            _session(logs, f"s{i}.jsonl", steps)
        return client.Budget(LIMITS, base, logs, lambda: sum(len(s) for s in steps_per_session),
                             prices=PRICES, max_cost=max_cost)

    def test_cost_is_the_five_classes_against_the_price_table(self):
        # 2,000,000 input @ $1/Mtok = $2.00; 100,000 output @ $5/Mtok = $0.50; reasoning priced as output
        b = self.budget([[{"input": 2_000_000, "output": 100_000, "reasoning": 0}]], max_cost=10.0)
        self.assertEqual(b.spend()["cost"], 2.5)
        # cache_read $0.1/Mtok, cache_write $1.25/Mtok
        b = self.budget([[{"input": 0, "output": 0, "cache": {"read": 1_000_000, "write": 1_000_000}}]], max_cost=10.0)
        self.assertEqual(b.spend()["cost"], round(0.1 + 1.25, 6))

    def test_reached_fires_at_the_dollar_ceiling_and_the_run_stops(self):
        steps = [[{"input": 2_000_000, "output": 0}]]            # $2.00
        self.assertIsNone(self.budget(steps, max_cost=2.01).reached())          # under: run continues
        self.assertEqual(self.budget(steps, max_cost=2.00).reached(), "max_cost: 2.0 of 2.0")   # at: stop
        self.assertEqual(self.budget(steps, max_cost=1.50).reached(), "max_cost: 2.0 of 1.5")   # over: stop

    def test_exceeded_is_strictly_past_the_ceiling(self):
        steps = [[{"input": 2_000_000, "output": 0}]]            # $2.00
        self.assertIsNone(self.budget(steps, max_cost=2.00).exceeded())         # exactly at is not exceeded
        self.assertEqual(self.budget(steps, max_cost=1.99).exceeded(), "max_cost exceeded: 2.0 of 1.99")

    def test_every_session_including_retry_attempts_counts_toward_the_ceiling(self):
        # C9: spend() sums every session log in out/sessions; a stuck story's retry attempts each leave a session, so
        # their spend counts toward the dollar ceiling exactly like a first attempt's — no attempt is exempt
        attempts = [[{"input": 1_000_000, "output": 0}] for _ in range(3)]      # three attempts, $1.00 each
        b = self.budget(attempts, max_cost=2.50)
        self.assertEqual(b.spend()["cost"], 3.0)
        self.assertEqual(b.reached(), "max_cost: 3.0 of 2.5")

    def test_base_and_inherited_count_toward_the_ceiling(self):
        base = {"provider_requests": 0, "turns": 0, "input_tokens": 3_000_000, "output_tokens": 0}   # preflight $3.00
        b = self.budget([[{"input": 0, "output": 0}]], max_cost=2.50, base=base)
        self.assertEqual(b.spend()["cost"], 3.0)
        self.assertEqual(b.reached(), "max_cost: 3.0 of 2.5")

    def test_a_step_with_no_tokens_fails_closed_and_the_cost_is_none(self):
        b = self.budget([[{"input": 5, "output": 5}, {"part_without_tokens": True}]], max_cost=1.0)
        # the second "step" has no tokens dict → steps_without_tokens → unaccounted → the run stops, cost unknown
        spent = b.spend()
        self.assertIsNone(spent["cost"])
        self.assertTrue(spent["unaccounted"])
        self.assertTrue(b.reached().startswith("unaccounted"))

    def test_without_max_cost_the_spend_is_byte_for_byte_the_old_four_counters(self):
        d = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        logs = d / "sessions"
        _session(logs, "s0.jsonl", [{"input": 10, "output": 2}])
        plain = client.Budget(LIMITS, ZERO, logs, lambda: 1)                       # 2.0.0 construction
        priced_no_cap = client.Budget(LIMITS, ZERO, logs, lambda: 1, prices=PRICES)  # prices but no ceiling
        self.assertEqual(set(plain.spend()), set(priced_no_cap.spend()))
        self.assertNotIn("cost", plain.spend())
        self.assertNotIn("max_cost", plain.spend())
        self.assertIsNone(plain.reached())


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class MaxCostStopsTheRun(e2e.ProductBase):
    """The offline fake-client demonstration: a run whose spend crosses the dollar ceiling does no further work. The
    price table is scaled so the preflight's own tokens already exceed the ceiling; at the story loop's budget check
    the first (only) story is NOT_RUN and the run FAILs, its budget_stop naming max_cost. The run still verifies from
    its journal — stopping on budget is an honest outcome, not a broken record."""

    def test_a_run_does_no_work_once_the_dollar_ceiling_is_crossed(self):
        dear = {**PRICES, "input_per_mtok": 100000.0, "cache_read_per_mtok": 100000.0,
                "cache_write_per_mtok": 100000.0, "output_per_mtok": 100000.0}
        self.settings = settings.load({**e2e.SETTINGS, "prices": dear, "max_cost": 0.01})
        rec = self.execute()
        # the preflight's own tokens already exceed $0.01, so the story loop's budget check refuses the one story
        # before it starts: no code is written, nothing delivered, and the stop names max_cost
        self.assertEqual(rec["delivery_verdict"], "NOT_REACHED", rec.get("budget_stop"))
        self.assertIn("max_cost", rec["budget_stop"])
        self.assertEqual(rec["story_outcomes"], {"S1": [f"NOT_RUN: max_cost: {rec['budget']['spent']['cost']} of 0.01"]})
        self.assertEqual(verify(self.project, self.tmp / "out")["verdict"], "VERIFIED")

    def test_a_generous_ceiling_lets_the_same_run_deliver(self):
        dear = {**PRICES, "input_per_mtok": 100000.0, "cache_read_per_mtok": 100000.0,
                "cache_write_per_mtok": 100000.0, "output_per_mtok": 100000.0}
        self.settings = settings.load({**e2e.SETTINGS, "prices": dear, "max_cost": 1000.0})
        rec = self.execute()
        self.assertEqual((rec["delivery_verdict"], rec["budget_stop"]), ("PASS", None))
        self.assertIsNotNone(rec["budget"]["spent"]["cost"])        # the cost is recorded, under the ceiling


if __name__ == "__main__":
    unittest.main()
