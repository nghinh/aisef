"""Integration test: budget guard blocks the *paid* client call inside
``implement_story`` before it dispatches.  Uses a scripted client that
records what was dispatched; the guard's ``reserve`` raises
``BudgetExceeded`` before the call returns."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.budget import (
    BudgetConfig,
    BudgetExceeded,
    BudgetGuard,
    BudgetLedger,
)


class _ScriptedClient:
    """Records every ``run`` call; supports ``attach_budget_guard``."""

    def __init__(self):
        self.id = "scripted"
        self.calls: list[str] = []
        self._budget_guard = None

    def attach_budget_guard(self, guard):
        self._budget_guard = guard

    def available(self) -> bool:
        return True

    def capabilities(self) -> dict:
        return {}

    def run(self, spec):
        self.calls.append(spec.story_id)
        from aisef.clients.stream import RunResult
        return RunResult(ok=True, cost_usd=0.10, num_turns=1)


class TestBudgetBlocksBeforeDispatch(unittest.TestCase):
    """When the budget cap is breached, the client is never invoked."""

    def test_reserved_client_run_raises_before_run(self):
        client = _ScriptedClient()
        with tempfile.TemporaryDirectory() as d:
            guard = BudgetGuard(BudgetLedger(Path(d)))
            guard.configure(BudgetConfig(cap_usd=0.05))
            client.attach_budget_guard(guard)
            from aisef.phases.implement import _reserved_client_run

            class _StubSpec:
                story_id = "S1"
                prompt = ""
                timeout_seconds = 60

            with self.assertRaises(BudgetExceeded):
                _reserved_client_run(
                    client, _StubSpec(), story_id="S1",
                    estimate_usd=1.0, estimate_turns=1,
                )
            self.assertEqual(client.calls, [])

    def test_reserved_client_run_passes_when_within_cap(self):
        client = _ScriptedClient()
        with tempfile.TemporaryDirectory() as d:
            guard = BudgetGuard(BudgetLedger(Path(d)))
            guard.configure(BudgetConfig(cap_usd=10.0))
            client.attach_budget_guard(guard)
            from aisef.phases.implement import _reserved_client_run

            class _StubSpec:
                story_id = "S1"
                prompt = ""
                timeout_seconds = 60

            res = _reserved_client_run(
                client, _StubSpec(), story_id="S1",
                estimate_usd=0.0, estimate_turns=1,
            )
            self.assertTrue(res.ok)
            self.assertEqual(client.calls, ["S1"])
            state = BudgetLedger(Path(d)).load()
            self.assertGreater(state.spent_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
