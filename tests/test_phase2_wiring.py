"""Phase-2 wiring tests: findings, server_identity, budget, qualify.

These verify the unified modules interact correctly with the rest of the
codebase at the seam the project now exposes. They are *not* behavioral
tests of the inner modules (covered by their dedicated suites) — they
verify the wire-up so future callers can rely on the contract.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

from aisef.control.findings import (
    Finding,
    FindingBook,
    Severity,
    Status,
    Trust,
)
from aisef.control.qualification import (
    Decision,
    Inputs,
    PHASE_RUN,
    Profile,
    StorySnapshot,
    qualify,
)
from aisef.harness.server_identity import (
    acquire_port_lease,
    ready_with_identity,
    release_port_lease,
)
from aisef.control.budget import (
    BudgetConfig,
    BudgetExceeded,
    BudgetGuard,
    BudgetLedger,
)


class TestQualifyProjectSeesPlan(unittest.TestCase):
    """`qualify(PHASE_RUN)` exposes its decision surface so ``run.py`` can
    defer to it instead of reimplementing "should we stop" everywhere."""

    def test_qualify_rejects_pending_stories_explicitly(self):
        """Project that hasn't run yet: every story is *pending*, the
        policy returns STOP and names the cause. `run.py` now projects
        pending→failed before calling the policy to avoid the false
        STOP (see ``_build_qstories_from_plan``)."""
        v = qualify(
            Profile(phase=PHASE_RUN, attempt=0, max_retries=1),
            Inputs(
                artifact_root_exists=True,
                run_ownership_ok=True,
                plan_error="",
                stories=(
                    StorySnapshot(story_id="S1", status="pending"),
                    StorySnapshot(story_id="S2", status="pending"),
                ),
            ),
        )
        # Pending falls into "stories in unexpected state" — and the
        # whole point is that *run.py* projects pending→failed before
        # calling the policy.  This test pins the contract.
        self.assertEqual(v.decision, Decision.STOP)
        self.assertIn("pending", v.reason)

    def test_qualify_failed_story_within_retries_returns_verify(self):
        """A failed story with retries remaining → verify, so the
        loop can dispatch another attempt."""
        v = qualify(
            Profile(phase=PHASE_RUN, attempt=0, max_retries=3),
            Inputs(
                artifact_root_exists=True,
                run_ownership_ok=True,
                plan_error="",
                stories=(
                    StorySnapshot(story_id="S1", status="failed"),
                ),
            ),
        )
        self.assertEqual(v.decision, Decision.VERIFY)


class TestFindingsInterlock(unittest.TestCase):
    """Findings and existing stringly-typed lists must round-trip via
    `FindingBook` so callers migrating one site at a time don't lose
    evidence semantics."""

    def test_string_lists_round_trip_through_book(self):
        raw_lines = [
            "[critical] src/pay.py:42  Race in checkout pipeline",
            "[high] src/api.py:7  Token logged on error",
        ]
        book = FindingBook.from_lines(raw_lines, source="reviewer")
        self.assertEqual(len(book), 2)
        self.assertEqual(set(f.severity for f in book), {Severity.CRITICAL.value, Severity.HIGH.value})
        # Round-trip → same shape.
        self.assertEqual(book.to_lines(), raw_lines)
        # Parsed findings have stable ids derived from the line text.
        ids = {f.id for f in book}
        self.assertEqual(len(ids), 2)


class TestFindingsLifecycleAntiGoalpost(unittest.TestCase):
    """Find 6.1 prevention: closing a finding without evidence requires a
    matching `previous_prescription` (the bug the policy was added for)."""

    def test_closes_with_prescription_match_without_evidence(self):
        from aisef.control.findings import apply_transition
        f = Finding.make(
            source="reviewer", trust=Trust.REVIEWER.value,
            severity=Severity.HIGH.value, status=Status.OPEN.value,
            file="src/x.py", line=10, body="loop without bound",
            behavior_id="b1", prescription="add upper bound",
        )
        # Force-close without evidence by referencing the same prescription.
        f2 = apply_transition(
            f, to=Status.CLOSED, evidence="",
            previous_prescription="add upper bound",
            force_prescription_match=True,
        )
        self.assertEqual(f2.status, Status.CLOSED.value)

    def test_rejects_close_on_different_prescription(self):
        from aisef.control.findings import apply_transition, TransitionError
        f = Finding.make(
            source="reviewer", trust=Trust.REVIEWER.value,
            severity=Severity.HIGH.value, status=Status.OPEN.value,
            file="src/x.py", line=10, body="loop without bound",
            behavior_id="b1", prescription="add upper bound",
        )
        with self.assertRaises(TransitionError):
            apply_transition(
                f, to=Status.CLOSED, evidence="",
                previous_prescription="refactor entirely",
                force_prescription_match=True,
            )


class TestServerIdentityLeaseSeparatesRuns(unittest.TestCase):
    """Two concurrent runs trying to claim the same port must not stomp
    each other's lease file."""

    def test_other_run_lease_does_not_impede_new_acquire(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            root_a = Path(a)
            root_b = Path(b)
            fd = acquire_port_lease(root_a, "rA", "http://127.0.0.1:1")
            self.assertIsNotNone(fd)
            try:
                # Run B starts in a different root and sees nothing.
                fd_b = acquire_port_lease(root_b, "rB", "http://127.0.0.1:2")
                self.assertIsNotNone(fd_b)
                release_port_lease(root_b, "rB", fd=fd_b)
            finally:
                release_port_lease(root_a, "rA", fd=fd)


class TestBudgetShortCircuitsWhenNoCaps(unittest.TestCase):
    """When the project sets zero caps, the guard must not allocate, not
    touch disk, and not block any paid call."""

    def test_no_caps_no_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            guard = BudgetGuard(BudgetLedger(Path(d)))
            # Never call `configure`; treat as no caps.
            with guard.reserve(story_id="S") as r:
                # Should be a no-op context; allocation = 0.
                self.assertIsNone(r.token)
                r.actual_usd = 0.42
                r.actual_turns = 1
            state = BudgetLedger(Path(d)).load()
            self.assertEqual(state.spent_usd, 0.0)


class TestBudgetCapBlocksWithException(unittest.TestCase):
    """Cross-tier: cost cap blocks the call *before* it dispatches, by
    raising ``BudgetExceeded``. The exception carries the same payload
    the ledger persisted so callers can show the user the actual headroom."""

    def test_cap_blocks_pre_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            guard = BudgetGuard(BudgetLedger(Path(d)))
            guard.configure(BudgetConfig(cap_usd=0.10))
            with self.assertRaises(BudgetExceeded):
                with guard.reserve(story_id="S", est_usd=5.0):
                    pass  # never reached


if __name__ == "__main__":
    unittest.main()
