"""Regression / fixture tests for the paired A/B/C memory harness.

These tests are deliberately *offline and deterministic*: they exercise
the runner and scorer against small, in-test fixtures. They never call a
real LLM client, never open a network connection, and never rely on a
claude/opencode binary. They are safe to run in CI.

The directive requires scripted-fake-agent-only tests that exercise:

- the three arms (A off / B local / C unavailable)
- the per-arm budget cap
- the scoring logic (repeated_error_rate, useful_memory_precision,
  wrong_memory_rate, harm_rate, unavailable reporting)

Each test isolates its work in a TemporaryDirectory and restores the
results directory to whatever it was before the test ran; failing to do so
would mean re-running the harness repeatedly just to inspect score.json.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


class _IsolatedResults(unittest.TestCase):
    """Swap the harness's results directory for a tmpdir."""

    def setUp(self):
        self._orig_results = ROOT / "framework" / "bench" / "memory_compare" / "results"
        self.tmp = tempfile.mkdtemp(prefix="memory-compare-tests-")
        self.tmp_results = Path(self.tmp) / "results"
        self.tmp_results.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # restore: remove tmp, leave the original results dir untouched.
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestLock(unittest.TestCase):
    def test_lock_file_present_and_valid(self):
        from framework.bench.memory_compare import lock as L
        self.assertTrue(L.LOCK_PATH.is_file(), L.LOCK_PATH)
        data = json.loads(L.LOCK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertTrue(data["candidate_sha"])
        self.assertTrue(data["signature"])
        self.assertTrue(data["toggle_signature"])
        # verify_lock succeeds against the current HEAD
        L.verify_lock(ROOT, L.LOCK_PATH)

    def test_lock_refuses_to_run_when_head_moves(self):
        from framework.bench.memory_compare import lock as L
        fake_lock = Path(tempfile.mkdtemp()) / "lock.json"
        fake_lock.write_text(json.dumps({
            "schema_version": 1,
            "candidate_sha": "0" * 40,
            "effective_config_snapshot": [],
            "config_hash": "deadbeef",
            "toggle_signature": "feedface",
            "signature": "abcd1234",
            "default_arms": ["A", "B", "C"],
        }))
        with self.assertRaises(L.LockMismatch):
            L.verify_lock(ROOT, fake_lock)

    def test_lock_force_override(self):
        import os

        from framework.bench.memory_compare import lock as L
        fake_lock = Path(tempfile.mkdtemp()) / "lock.json"
        fake_lock.write_text(json.dumps({
            "schema_version": 1,
            "candidate_sha": "0" * 40,
            "effective_config_snapshot": [],
            "config_hash": "deadbeef",
            "toggle_signature": "feedface",
            "signature": "abcd1234",
            "default_arms": ["A", "B", "C"],
        }))
        os.environ["AISEF_MEMORY_BENCH_FORCE"] = "1"
        try:
            snap = L.verify_lock(ROOT, fake_lock)
            self.assertEqual(snap.candidate_sha, "0" * 40)
        finally:
            os.environ.pop("AISEF_MEMORY_BENCH_FORCE", None)


class TestScenarios(unittest.TestCase):
    def test_scenario_registry_has_required_set(self):
        from framework.bench.memory_compare.scenarios import SCENARIOS
        ids = {s.id for s in SCENARIOS}
        # three dogfood tasks the directive names
        for dogfood in ("dogfood/par", "dogfood/calc", "dogfood/par_mutation"):
            self.assertIn(dogfood, ids, dogfood)
        # six scripted long-horizon classes the directive describes
        for required in (
            "long_horizon/convention_carry_over",
            "long_horizon/failure_pattern_repeat",
            "long_horizon/reviewer_recurrence",
            "long_horizon/security_recurrence",
            "long_horizon/supersede_authority",
            "long_horizon/tool_env_repeat",
        ):
            self.assertIn(required, ids, required)

    def test_fixtures_load(self):
        from framework.bench.memory_compare.scenarios import SCENARIOS, load_fixture
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.id):
                fixture = load_fixture(scenario.id)
                self.assertIn("scripted_outcomes", fixture)
                self.assertIn("story_sequence", fixture)
                self.assertIsInstance(fixture.get("memory_records", []), list)


class TestRunner(_IsolatedResults):
    def test_arm_a_writes_results_offline(self):
        from framework.bench.memory_compare.runner import RunnerConfig, run_arm
        cfg = RunnerConfig(results_dir=self.tmp_results)
        paths = run_arm("A", "dogfood/calc", attempts=2, cfg=cfg)
        self.assertEqual(len(paths), 2)
        for path in paths:
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["arm"], "A")
            self.assertEqual(record["scenario_id"], "dogfood/calc")
            self.assertEqual(record["chars_injected"], 0,
                             "arm A must not inject memory content")
            self.assertIn(record["outcome"], ("PASS", "FAIL"))

    def test_arm_b_consults_local_memory(self):
        from framework.bench.memory_compare.runner import RunnerConfig, run_arm
        cfg = RunnerConfig(results_dir=self.tmp_results)
        paths = run_arm("B", "long_horizon/convention_carry_over", attempts=2, cfg=cfg)
        self.assertEqual(len(paths), 2)
        for path in paths:
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["arm"], "B")
            self.assertGreater(record["chars_injected"], 0,
                               "arm B must inject at least one memory record")

    def test_arm_c_unavailable_never_silently_downgrades(self):
        from framework.bench.memory_compare.llm_stub import (
            ArmUnavailable,
            scripted_arm_C,
        )
        from framework.bench.memory_compare.scenarios import load_fixture
        fixture = load_fixture("dogfood/calc")
        with self.assertRaises(ArmUnavailable):
            scripted_arm_C(fixture, "dogfood/calc", 0)
        from framework.bench.memory_compare.runner import RunnerConfig, run_arm
        cfg = RunnerConfig(results_dir=self.tmp_results)
        paths = run_arm("C", "dogfood/calc", attempts=1, cfg=cfg)
        self.assertEqual(len(paths), 1)
        record = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(record["outcome"], "UNAVAILABLE")
        self.assertTrue(record["unavailable_reason"],
                        "C must record why it did not run")

    def test_budget_exhaustion_stops_attempts_cleanly(self):
        from framework.bench.memory_compare.runner import (
            ArmBudget,
            RunnerConfig,
            run_arm,
        )
        cfg = RunnerConfig(
            results_dir=self.tmp_results,
            # Cost cap is tight enough that attempt 0 + 0.19 = 0.19 > 0.10
            # causes iter 1 onward to be BUDGET. Calls=2 is also tight.
            budget=ArmBudget(cost=0.10, turns=2, time_seconds=120.0, calls=2),
        )
        paths = run_arm("A", "dogfood/calc", attempts=4, cfg=cfg)
        outcomes = [json.loads(p.read_text(encoding="utf-8"))["outcome"]
                    for p in paths]
        # Cost cap exhausted after attempt 0; remaining 3 are BUDGET.
        self.assertEqual(outcomes.count("BUDGET"), 3,
                         f"expected 3 BUDGET attempts, got {outcomes}")
        self.assertEqual(outcomes[0], "PASS")
        for n in (1, 2, 3):
            self.assertEqual(outcomes[n], "BUDGET", f"attempt {n}: {outcomes}")


class TestScoring(_IsolatedResults):
    def test_score_keys_complete(self):
        from framework.bench.memory_compare.scoring import (
            PRIMARY_METRIC,
            score_from_results,
        )
        self.assertEqual(PRIMARY_METRIC, "repeated_error_rate")
        # write one valid attempt so the empty-results warning is absent
        valid = {
            "arm": "A", "attempt_index": 0, "scenario_id": "dogfood/calc",
            "outcome": "PASS", "budget_exhausted": False,
            "budget": {"cost": 0.1, "turns": 1, "time_seconds": 1.0, "calls": 1},
            "latencies_ms": [0.0], "budget_used": 0.1,
            "chars_injected": 0, "decisions": [],
            "verifier_findings": [], "errors": [],
            "unavailable_reason": "", "repeated_error_id": None,
            "signature": "valid", "run_started_at": "2026-01-01T00:00:00Z",
        }
        self.tmp_results.joinpath("valid__A__dogfood__calc__a00.json").write_text(
            json.dumps(valid), encoding="utf-8")
        result = score_from_results(self.tmp_results)
        self.assertEqual(result.primary_metric, PRIMARY_METRIC)
        self.assertEqual(result.deltas, {})
        self.assertEqual(result.warnings, [])

    def test_score_arm_c_reports_unavailable_status(self):
        # Hand-write a single C-attempt with outcome=UNAVAILABLE.
        record = {
            "arm": "C", "attempt_index": 0,
            "scenario_id": "dogfood/calc",
            "outcome": "UNAVAILABLE",
            "budget_exhausted": False,
            "budget": {"cost": 0, "turns": 0, "time_seconds": 0, "calls": 0},
            "latencies_ms": [0.0], "budget_used": 0.0,
            "chars_injected": 0, "decisions": [],
            "verifier_findings": [],
            "errors": ["OpenViking adapter unavailable"],
            "unavailable_reason": "OpenViking adapter unavailable",
            "repeated_error_id": None,
            "signature": "unavailable-C-test",
            "run_started_at": "2026-01-01T00:00:00Z",
        }
        self.tmp_results.joinpath("unavailable__C__dogfood__calc__a00.json").write_text(
            json.dumps(record), encoding="utf-8")
        from framework.bench.memory_compare.scoring import score_from_results
        result = score_from_results(self.tmp_results)
        self.assertIn("C", result.by_arm)
        self.assertEqual(result.by_arm["C"]["status"], "unavailable")
        self.assertEqual(result.deltas.get("C_status"), "unavailable")

    def test_score_arm_b_useful_memory_precision(self):
        # Two B-attempts: one useful record, one wrong record.
        useful = {
            "arm": "B", "attempt_index": 0, "scenario_id": "long_horizon/convention_carry_over",
            "outcome": "PASS", "budget_exhausted": False,
            "budget": {"cost": 0.1, "turns": 1, "time_seconds": 1.0, "calls": 1},
            "latencies_ms": [1.0], "budget_used": 0.1,
            "chars_injected": 100,
            "decisions": [{"kind": "memory_recalled", "target": "CONVENTION_BOUNDED_RETRY",
                           "score": 0.0, "note": ""}],
            "verifier_findings": [], "errors": [], "rejected": [],
            "unavailable_reason": "", "repeated_error_id": None,
            "signature": "useful", "run_started_at": "2026-01-01T00:00:00Z",
        }
        wrong = dict(useful)
        wrong["attempt_index"] = 1
        wrong["signature"] = "wrong"
        wrong["decisions"] = [{"kind": "memory_recalled", "target": "WRONG_RECORD",
                               "score": 0.0, "note": ""}]
        self.tmp_results.joinpath("useful__B__convention.json").write_text(
            json.dumps(useful), encoding="utf-8")
        self.tmp_results.joinpath("wrong__B__convention.json").write_text(
            json.dumps(wrong), encoding="utf-8")
        from framework.bench.memory_compare.scoring import score_from_results
        result = score_from_results(self.tmp_results)
        self.assertIn("B", result.by_arm)
        self.assertAlmostEqual(result.by_arm["B"]["useful_memory_precision"], 0.5)
        self.assertAlmostEqual(result.by_arm["B"]["wrong_memory_rate"], 0.5)


class TestLLMStub(unittest.TestCase):
    def test_arm_a_decisions_match_scripted_outcomes(self):
        from framework.bench.memory_compare.llm_stub import scripted_arm_A
        from framework.bench.memory_compare.scenarios import load_fixture
        fixture = load_fixture("long_horizon/convention_carry_over")
        attempt = scripted_arm_A(fixture, "long_horizon/convention_carry_over", 0)
        self.assertEqual(attempt.arm, "A")
        self.assertEqual(attempt.repeated_error_id, None)

    def test_arm_b_with_relevant_memory_does_not_repeat_error(self):
        from framework.bench.memory_compare.llm_stub import scripted_arm_B
        from framework.bench.memory_compare.scenarios import load_fixture
        fixture = load_fixture("long_horizon/convention_carry_over")
        # Synthesize a packet containing the relevant source_ref.
        packet = {
            "chars": 200,
            "latency_ms": 1.5,
            "selected": [{"id": "abc", "source": fixture["memory_records"][0]["source_ref"],
                          "score": 1.0, "trust": "deterministic", "status": "active",
                          "role": "developer"}],
            "rejected": [],
        }
        attempt = scripted_arm_B(fixture, "long_horizon/convention_carry_over", 0, packet)
        self.assertIsNone(attempt.repeated_error_id,
                           "with relevant memory, no repeated error")
        kinds = {d.kind for d in attempt.decisions}
        self.assertIn("memory_recalled", kinds)

    def test_arm_b_without_memory_repeats_expected_error(self):
        from framework.bench.memory_compare.llm_stub import scripted_arm_B
        from framework.bench.memory_compare.scenarios import load_fixture
        fixture = load_fixture("long_horizon/convention_carry_over")
        attempt = scripted_arm_B(fixture, "long_horizon/convention_carry_over", 0, None)
        self.assertEqual(attempt.repeated_error_id, fixture["expected_repeated_behavior_id"])


if __name__ == "__main__":
    unittest.main()
