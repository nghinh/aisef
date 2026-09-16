"""In-flight budget reservation."""

from __future__ import annotations

import sys
import tempfile
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


class TestReservationHeadroomCountsInFlight(unittest.TestCase):
    """Regression test: a second reserve whose total with an outstanding
    reservation would exceed the cap was passing the per-call check,
    letting two parallel calls burn past the cap before settle noticed."""

    def test_second_reserve_respects_first_outstanding(self):
        with _tempdir() as root:
            g = BudgetGuard(BudgetLedger(root))
            g.configure(BudgetConfig(cap_usd=0.10))
            # First reservation holds 0.06; second 0.06 alone fits cap,
            # but 0.06 + 0.06 = 0.12 > 0.10 must be blocked.
            with g.reserve(story_id="S1", est_usd=0.06, est_turns=1) as r1:
                with self.assertRaises(BudgetExceeded):
                    with g.reserve(story_id="S2", est_usd=0.06, est_turns=1):
                        pass
                r1.actual_usd = 0.06

    def test_second_turn_reserve_respects_first(self):
        with _tempdir() as root:
            g = BudgetGuard(BudgetLedger(root))
            g.configure(BudgetConfig(cap_turns=4))
            with g.reserve(est_turns=3, est_usd=0.0) as r1:
                with self.assertRaises(BudgetExceeded):
                    with g.reserve(est_turns=2, est_usd=0.0):
                        pass
                r1.actual_turns = 3

    def test_check_caps_sees_in_flight_reservations(self):
        # Direct test of the cap math, bypassing the lock so the
        # behavioural gap is reproducible even when concurrency
        # happens to serialise.
        from aisef.control.budget import BudgetState, _check_caps
        state = BudgetState(cap_usd=0.10, spent_usd=0.0)
        state.reservations = [{"est_usd": 0.06, "est_turns": 1, "id": "r1"}]
        with self.assertRaisesRegex(BudgetExceeded, "cost cap"):
            _check_caps(state, est_usd=0.06, est_turns=1, est_seconds=0.0)

    def test_check_caps_turn_sees_in_flight_reservations(self):
        from aisef.control.budget import BudgetState, _check_caps
        state = BudgetState(cap_turns=4, spent_turns=0)
        state.reservations = [{"est_usd": 0.0, "est_turns": 3, "id": "r1"}]
        with self.assertRaisesRegex(BudgetExceeded, "turn cap"):
            _check_caps(state, est_usd=0.0, est_turns=2, est_seconds=0.0)

    def test_settled_reservation_frees_headroom(self):
        with _tempdir() as root:
            g = BudgetGuard(BudgetLedger(root))
            g.configure(BudgetConfig(cap_usd=0.10))
            with g.reserve(story_id="S1", est_usd=0.06, est_turns=1) as r1:
                r1.actual_usd = 0.06
            # After S1 settled, the only thing on the books is the
            # settled spend (0.06).  A small reserve that fits below
            # the post-spend headroom must still succeed.
            with g.reserve(story_id="S2", est_usd=0.03, est_turns=1) as r2:
                r2.actual_usd = 0.03


from contextlib import contextmanager
from tempfile import TemporaryDirectory


@contextmanager
def _tempdir():
    with TemporaryDirectory() as d:
        yield Path(d)


if __name__ == "__main__":
    unittest.main()


class TestCanhBaoTruocKhiCham(unittest.TestCase):
    """Chặn tại trần là đúng nhưng tới quá muộn: lần đầu người biết là lúc
    story dừng giữa chừng. Cảnh báo ở 80 % cho họ kịp quyết định."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.guard = BudgetGuard(BudgetLedger(Path(self._tmp.name)))

    def tearDown(self):
        self._tmp.cleanup()

    def _chay(self, tien: float) -> str:
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.guard.reserve(est_usd=0.01) as r:
            r.actual_usd = tien
        return err.getvalue()

    def test_vuot_80_phan_tram_thi_keu_co_so(self):
        self.guard.configure(BudgetConfig(cap_usd=1.0))
        ra = self._chay(0.85)
        self.assertIn("$0.85", ra)
        self.assertIn("$1.00", ra)
        self.assertIn("85%", ra)

    def test_duoi_nguong_thi_im(self):
        self.guard.configure(BudgetConfig(cap_usd=1.0))
        self.assertEqual(self._chay(0.5), "")

    def test_keu_mot_lan_thoi(self):
        """Kêu ở mọi lượt còn lại là cách nhanh nhất để người ta thôi đọc."""
        self.guard.configure(BudgetConfig(cap_usd=1.0))
        self.assertIn("⚠", self._chay(0.85))
        self.assertEqual(self._chay(0.02), "")

    def test_khong_khai_tran_thi_khong_co_gi_de_canh_bao(self):
        self.assertEqual(self._chay(999.0), "")

    def test_co_da_keu_song_qua_lan_chay_khac(self):
        """Cờ nằm trên đĩa: tiến trình sau không kêu lại cùng một ngưỡng."""
        self.guard.configure(BudgetConfig(cap_usd=1.0))
        self.assertIn("⚠", self._chay(0.85))
        khac = BudgetGuard(BudgetLedger(Path(self._tmp.name)))
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), khac.reserve(est_usd=0.01) as r:
            r.actual_usd = 0.01
        self.assertEqual(err.getvalue(), "")

    def test_tran_luot_cung_canh_bao(self):
        self.guard.configure(BudgetConfig(cap_turns=10))
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.guard.reserve(est_turns=1) as r:
            r.actual_turns = 9
        self.assertIn("9 lượt / 10 lượt", err.getvalue())


class TestAReservationReleaseIsRecorded(unittest.TestCase):
    """F5 / SS-52: a reservation whose owner died or whose term expired is released AND recorded — `released` names
    the reservation, the owner and why — and the record survives a save/load round trip."""

    def test_dead_owner_and_expired_term_are_released_with_their_reason(self):
        import os
        import socket
        import time
        from aisef.control.budget import BudgetState, _prune_dead_reservations
        now = time.time()
        dead_pid = 2 ** 22 - 7                     # never a live pid on a developer box
        st = BudgetState(reservations=[
            {"id": "r-dead", "owner": f"{socket.gethostname()}:{dead_pid}", "est_usd": 1.5, "expires_at": now + 600},
            {"id": "r-old", "owner": "other-host:1", "est_usd": 2.0, "expires_at": now - 1},
            {"id": "r-live", "owner": f"{socket.gethostname()}:{os.getpid()}", "est_usd": 0.5, "expires_at": now + 600}])
        dead = _prune_dead_reservations(st)
        self.assertEqual(sorted(r["id"] for r in dead), ["r-dead", "r-old"])
        self.assertEqual([r["id"] for r in st.reservations], ["r-live"])
        why = {r["id"]: r["why"] for r in st.released}
        self.assertEqual(why, {"r-dead": "owner dead", "r-old": "term expired"})
        self.assertEqual(BudgetState.from_dict(st.to_dict() if hasattr(st, "to_dict") else __import__("dataclasses").asdict(st)).released, st.released)
