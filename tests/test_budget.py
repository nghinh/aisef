"""In-flight budget reservation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.budget import (  # noqa: E402
    BudgetConfig, BudgetExceeded, BudgetGuard, BudgetLedger, BudgetState,
)


class TestReservation(unittest.TestCase):
    def test_no_caps_means_no_reservation(self):
        with _tempdir() as root:
            guard = BudgetGuard(BudgetLedger(root))
            with guard.reserve(story_id="S1", est_turns=10, est_usd=1.0) as r:
                self.assertIsNone(r.token)
                # Settle doesn't write or refuse when nothing is capped.
                r.actual_turns = 5

    def test_cost_cap_blocks(self):
        with _tempdir() as root:
            guard = BudgetGuard(BudgetLedger(root))
            guard.configure(BudgetConfig(cap_usd=1.0))
            with guard.reserve(est_usd=0.5) as r:
                r.actual_usd = 0.5
            # Second reservation would exceed 1.0 cap.
            with self.assertRaises(BudgetExceeded):
                with guard.reserve(est_usd=0.6):
                    pass

    def test_turn_cap_blocks(self):
        with _tempdir() as root:
            guard = BudgetGuard(BudgetLedger(root))
            guard.configure(BudgetConfig(cap_turns=4))
            with guard.reserve(est_turns=2) as r:
                r.actual_turns = 2
            with self.assertRaises(BudgetExceeded):
                with guard.reserve(est_turns=3):
                    pass

    def test_failed_call_refunds_reservation(self):
        with _tempdir() as root:
            guard = BudgetGuard(BudgetLedger(root))
            guard.configure(BudgetConfig(cap_usd=2.0))
            try:
                with guard.reserve(est_usd=1.5):
                    raise RuntimeError("model call failed")
            except RuntimeError:
                pass
            # Reservation was refunded: ledger is clean.
            state = guard.ledger.load()
            self.assertEqual(len(state.reservations), 0)
            self.assertEqual(state.spent_usd, 0.0)
            # Another attempt within cap is now allowed.
            with guard.reserve(est_usd=1.0) as r:
                r.actual_usd = 0.0

    def test_settle_records_actual(self):
        with _tempdir() as root:
            guard = BudgetGuard(BudgetLedger(root))
            guard.configure(BudgetConfig(cap_usd=5.0))
            with guard.reserve(est_usd=0.0) as r:
                r.actual_usd = 0.4
                r.actual_turns = 3
            state = guard.ledger.load()
            self.assertAlmostEqual(state.spent_usd, 0.4, places=4)
            self.assertEqual(state.spent_turns, 3)

    def test_zero_caps_round_trip_in_state(self):
        with _tempdir() as root:
            guard = BudgetGuard(BudgetLedger(root))
            guard.configure(BudgetConfig(cap_usd=0.0, cap_turns=0,
                                        cap_seconds=0.0))
            state = guard.ledger.load()
            d = state.to_dict()
            self.assertEqual(d["cap_usd"], 0.0)
            rebuilt = BudgetState.from_dict(d)
            self.assertEqual(rebuilt.cap_usd, 0.0)


from contextlib import contextmanager
from tempfile import TemporaryDirectory


@contextmanager
def _tempdir():
    with TemporaryDirectory() as d:
        yield Path(d)


if __name__ == "__main__":
    unittest.main()
