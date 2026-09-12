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


class TestLockSidecarStableAcrossSave(unittest.TestCase):
    """Regression test: flock on the state file was a no-op when
    ``os.replace`` swapped the inode.  Lock must move to a never-replaced
    sidecar so concurrent ``reserve()`` calls serialise correctly even
    after a save."""

    def test_lock_held_by_outer_reserve_blocks_inner_reserve(self):
        with _tempdir() as root:
            g1 = BudgetGuard(BudgetLedger(root))
            g2 = BudgetGuard(BudgetLedger(root))
            g1.configure(BudgetConfig(cap_usd=10.0))
            with g1.reserve(story_id="S1", est_usd=0.5, est_turns=1) as r1:
                # Inner reserve on a second guard must be blocked while
                # the outer reserve holds the lock — even though the
                # outer guard already saved reservations to its ledger.
                with self.assertRaises(BudgetExceeded):
                    with g2.reserve(story_id="S2", est_usd=0.5, est_turns=1):
                        pass
                r1.actual_usd = 0.5

    def test_lock_path_is_sidecar_not_state_file(self):
        with _tempdir() as root:
            ledger = BudgetLedger(root)
            # The state file is rewritten via os.replace (swap-inode on
            # some filesystems).  The lock must NOT be on it.
            self.assertNotEqual(ledger.lock_path, ledger.path)
            self.assertEqual(ledger.lock_path.name,
                             ledger.path.name + ".lock")

    def test_state_save_does_not_unlink_lock(self):
        with _tempdir() as root:
            g = BudgetGuard(BudgetLedger(root))
            g.configure(BudgetConfig(cap_usd=1.0))
            with g.reserve(est_usd=0.1, est_turns=1) as r:
                self.assertTrue(g.ledger.lock_path.exists())
                r.actual_usd = 0.1
            self.assertTrue(g.ledger.lock_path.exists())


from contextlib import contextmanager
from tempfile import TemporaryDirectory


@contextmanager
def _tempdir():
    with TemporaryDirectory() as d:
        yield Path(d)


if __name__ == "__main__":
    unittest.main()
