"""Paired A/B/C memory harness — paired fresh-agent benchmark for memory benefit.

Public entry points:
- `run_all(scenario_ids=None, attempts=3)`: reproduce all default scenarios across all arms.
- `run_arm(arm, scenario_id, attempts=3, fixture=None)`: run one arm against one scenario.
- `verify_lock()`: refuse to run if HEAD moved since lock, unless `AISEF_MEMORY_BENCH_FORCE=1`.
- `lock_path`: filesystem location of the lock file (`framework/bench/memory_compare/lock.json`).

All public functions honour the inviolables in the parent directive:
- A: memory off; harness never reads/writes memory.
- B: memory on, local provider only — never opens network, never imports a remote
  adapter.
- C: OpenViking only — never silently downgraded; if unavailable, arm reports
  ``status='unavailable'`` and never runs a local fallback.
- No real model call is made. Execution is via `llm_stub.FakeAgent`, which is
  purely deterministic and produces the same decisions for the same fixture.
- Each per-arm invocation writes a JSON result file under
  ``framework/bench/memory_compare/results/``; reruns read fixtures and never
  fabricate missing numbers. If a budget cap is exceeded the arm records
  ``budget_exhausted=True`` and partial attempts; no imputation.

The harness reuses ``aisef/memory.py`` (``LocalMemory``, ``authority``,
``make_record``, ``project_id``) and the harness agent-side is a deliberately
trivial deterministic stub — see `llm_stub`. The existing `aisef/memory_bench`
scripted-retrieval benchmark is **not** modified; this is a separate harness
that operates against scenario fixtures and produces paired-arm scores.

The runner is offline-reproducible: same lock, same fixture, same scenario
inputs always produce the same JSON output (modulo ``wall_ms`` which is excluded
from the deterministic signature).
"""
from .lock import (
    CANDIDATE_SHA,
    CONFIG_HASH,
    EFFECTIVE_CONFIG_SNAPSHOT,
    LOCK_PATH,
    SIGNATURE,
    TOGGLE_SIGNATURE,
    LockMismatch,
    lock_signature,
    verify_lock,
)
from .runner import ArmBudget, Attempt, run_all, run_arm
from .scenarios import SCENARIOS, load_fixture
from .scoring import (
    ARM_RESULTS_DIR,
    PRIMARY_METRIC,
    score_from_results,
    score_to_markdown,
)

__all__ = [
    "ARM_RESULTS_DIR",
    "CANDIDATE_SHA",
    "CONFIG_HASH",
    "EFFECTIVE_CONFIG_SNAPSHOT",
    "LOCK_PATH",
    "PRIMARY_METRIC",
    "SCENARIOS",
    "SIGNATURE",
    "TOGGLE_SIGNATURE",
    "ArmBudget",
    "Attempt",
    "LockMismatch",
    "load_fixture",
    "lock_signature",
    "run_all",
    "run_arm",
    "score_from_results",
    "score_to_markdown",
    "verify_lock",
]
