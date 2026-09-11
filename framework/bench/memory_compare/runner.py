"""Runner for the paired A/B/C memory harness.

The runner composes:

- A *deterministic* project root template per scenario (built from the
  fixture's `write_scope` and the memory_records it ships). The
  LocalMemory store is wired against this template.
- The `llm_stub` agent. We never call a real provider.
- A per-arm `ArmBudget` with cost/turns/time/calls caps. If the cap is
  exceeded mid-attempt the arm records ``budget_exhausted=True`` and the
  remainder of the attempts are marked ``BUDGET`` rather than fabricated.

The runner writes one JSON file per (arm, scenario, attempt) tuple under
``framework/bench/memory_compare/results/``, named deterministically:
``<signature>__<arm>__<scenario_id>__<attempt>.json``. The signature
embeds the framework candidate SHA, config hash, toggle signature and
arm; that is what scoring uses to count distinct attempts.

Reproducibility:

- Same lock, same fixtures, same N → same per-arm JSON files, modulo
  timestamps and the wall-clock latency fields. Timestamps are emitted as
  ISO-8601 UTC. Latencies are excluded from the signature hash.
- The runner is offline. It does not import any model client. The
  ``BUDGET`` cap (default cost=5.0, turns=20, time=120s, calls=10) is small
  enough that a fully scripted agent never actually exhausts it; the cap is
  a safety net so a malicious or runaway implementation can't loop forever.

Run modes:

- `run_arm(arm, scenario_id, attempts=3)`: single arm, single scenario.
- `run_all(scenario_ids=None, attempts=3)`: every arm × every scenario.
"""
from __future__ import annotations

import copy
import json
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from . import lock as L
from .llm_stub import (
    ARM_A,
    ARM_B,
    ARM_C,
    ArmUnavailable,
    Attempt,
    scripted_arm_A,
    scripted_arm_B,
    scripted_arm_C,
)
from .scenarios import SCENARIOS, load_fixture

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class ArmBudget:
    cost: float = 5.0
    turns: int = 20
    time_seconds: float = 120.0
    calls: int = 10

    def as_dict(self) -> dict:
        return {"cost": self.cost, "turns": self.turns,
                "time_seconds": self.time_seconds, "calls": self.calls}


@dataclass
class RunnerConfig:
    attempts: int = 3
    budget: ArmBudget = field(default_factory=ArmBudget)
    arms: tuple[str, ...] = (ARM_A, ARM_B, ARM_C)
    repo_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[3])
    results_dir: Path = field(default_factory=lambda: RESULTS_DIR)
    lock_path: Path = field(default_factory=lambda: L.LOCK_PATH)

    def with_overrides(self, **kw) -> RunnerConfig:
        merged = copy.deepcopy(self)
        for key, value in kw.items():
            if key == "budget":
                merged.budget = value
            else:
                setattr(merged, key, value)
        return merged


def _safe_scenario(scenario_id: str) -> str:
    return scenario_id.replace("/", "__").replace(".", "_")


def _maybe_make_local_memory(root: Path, fixture: dict, *, lock_payload: dict) -> tuple[object | None, dict | None]:
    """Build a LocalMemory store against an isolated project root and load
    the fixture's pre-canned records.

    Returns (store, packet_or_None). ``packet_or_None`` is the recall
    packet for the next scenario attempt, or None if no records ship.
    """
    from aisef.memory import LocalMemory, authority, make_record
    project = root / "proj"
    project.mkdir(parents=True, exist_ok=True)
    (project / "docs").mkdir(exist_ok=True)
    (project / "_bmad-output").mkdir(exist_ok=True)
    (project / "docs/requirements.md").write_text("bounded retries", encoding="utf-8")
    (project / "_bmad-output/architecture.md").write_text("bounded retries", encoding="utf-8")
    (project / "_bmad-output/prd.md").write_text("bounded retries", encoding="utf-8")
    for record in fixture.get("memory_records", []):
        ref = record["source_ref"]
        path = project / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(record["text"], encoding="utf-8")
    store = LocalMemory(project, timeout=2)
    ids: dict[str, str] = {}
    for record in fixture.get("memory_records", []):
        kwargs = {
            "root": project,
            "source": record["source_ref"],
            "text": record["text"],
            "epic": record["epic"],
            "story": record.get("story", "*"),
            "origin_story": record["origin_story"],
            "paths": list(record["paths"]),
            "roles": list(record["roles"]),
            "tools": list(record["tools"]),
            "kind": ("review_pattern" if record["trust"] == "reviewer"
                     else "security_pattern" if record["trust"] == "security"
                     else "lesson"),
            "trust": record["trust"],
        }
        if record.get("source_type") == "journal":
            kwargs["source_type"] = "journal"
        if record.get("source_type") == "evidence":
            kwargs["source_type"] = "evidence"
        if record.get("candidate"):
            kwargs["candidate"] = record["candidate"]
        row = make_record(**kwargs)
        row["status"] = "active"
        row["contract_authority"] = authority(project)
        ids[record["id"]] = store.put(row)
    if not fixture.get("memory_records"):
        return store, None
    sequence = fixture.get("story_sequence", [])
    story_target = sequence[-1] if sequence else "S1"
    packet = store.recall(
        query=fixture.get("evidence_text", "bounded retries"),
        epic=fixture["memory_records"][0]["epic"],
        story=story_target,
        role=fixture["memory_records"][0]["roles"][0],
        paths=fixture["memory_records"][0]["paths"],
        tool="*",
        budget=int(lock_payload.get("memory_max_chars", 1200)),
    )
    return store, packet


def _within_budget(used: dict, budget: ArmBudget) -> bool:
    return (
        used["cost"] <= budget.cost
        and used["turns"] <= budget.turns
        and used["calls"] <= budget.calls
    )


def _run_arm_attempt(arm: str, scenario_id: str, attempt_index: int, cfg: RunnerConfig,
                     tmpdir: Path) -> tuple[Attempt | None, dict | None]:
    """Run one attempt under one arm.

    Returns (attempt_or_none, recall_packet). ``recall_packet`` is None for
    arms that do not consult local memory (A and C). When the arm hits a
    budget cap, returns ``(None, recall_packet)`` where the partial state
    is in ``recall_packet['_budget_exhausted']``. If C raises
    ArmUnavailable, ``attempt_or_none is None`` and the recall_packet has
    key ``_unavailable``.
    """
    fixture = load_fixture(scenario_id)
    if arm == ARM_A:
        return scripted_arm_A(fixture, scenario_id, attempt_index), None
    if arm == ARM_C:
        try:
            return scripted_arm_C(fixture, scenario_id, attempt_index), None
        except ArmUnavailable as exc:
            return None, {"_unavailable": True, "reason": str(exc)}
    if arm != ARM_B:
        raise ValueError(f"unknown arm: {arm!r}")
    lock_payload = _read_lock_payload(cfg.lock_path)
    _store, packet = _maybe_make_local_memory(tmpdir, fixture, lock_payload=lock_payload)
    if packet is None:
        # B with empty fixture behaves like A but still emits a packet stub.
        attempt = scripted_arm_A(fixture, scenario_id, attempt_index)
        return _swap_arm(attempt, ARM_B), None
    attempt = scripted_arm_B(fixture, scenario_id, attempt_index, memory_payload=packet)
    return attempt, packet


def _swap_arm(attempt: Attempt, arm: str) -> Attempt:
    return Attempt(
        arm=arm, scenario_id=attempt.scenario_id, attempt_index=attempt.attempt_index,
        decisions=attempt.decisions, gate_results=attempt.gate_results,
        verifier_findings=attempt.verifier_findings, errors=attempt.errors,
        repeated_error_id=attempt.repeated_error_id,
        budget_used=attempt.budget_used, chars_injected=attempt.chars_injected,
        latencies_ms=attempt.latencies_ms, outcome=attempt.outcome,
        signature=attempt.signature,
    )


def _read_lock_payload(lock_path: Path) -> dict:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    snap = {k: v for k, v in data.get("effective_config_snapshot", [])}
    return {"memory_max_chars": snap.get("memory.max_chars", 1200),
            "memory_provider": snap.get("memory.provider", "local")}


def _write_attempt(cfg: RunnerConfig, attempt: Attempt, *, budget_exhausted: bool,
                   unavailable_reason: str = "") -> Path:
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_scenario(attempt.scenario_id)
    sig = attempt.signature.replace("/", "_")
    path = cfg.results_dir / f"{sig}__{attempt.arm}__{safe}__a{attempt.attempt_index:02d}.json"
    payload = attempt.to_dict()
    payload["budget"] = cfg.budget.as_dict()
    payload["budget_exhausted"] = budget_exhausted
    payload["unavailable_reason"] = unavailable_reason
    payload["run_started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return path


def run_arm(arm: str, scenario_id: str, *, attempts: int = 3,
            cfg: RunnerConfig | None = None) -> list[Path]:
    """Run ``attempts`` attempts of one (arm, scenario). Returns the list of
    per-attempt result JSON paths written under ``results_dir``.
    """
    config = cfg or RunnerConfig(attempts=attempts)
    config = config.with_overrides(attempts=attempts)
    L.verify_lock(config.repo_root, config.lock_path, arms=config.arms)
    config.results_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    used = {"cost": 0.0, "turns": 0, "calls": 0}
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for attempt_index in range(attempts):
            used["calls"] += 1
            if not _within_budget(used, config.budget):
                attempt = Attempt(
                    arm=arm, scenario_id=scenario_id, attempt_index=attempt_index,
                    decisions=(), gate_results=(), verifier_findings=(),
                    errors=("budget exhausted before this attempt",),
                    repeated_error_id=None, budget_used=used["cost"],
                    chars_injected=0, latencies_ms=(0.0,), outcome="BUDGET",
                    signature=f"budget-{arm}-{scenario_id}-a{attempt_index:02d}",
                )
                paths.append(_write_attempt(config, attempt, budget_exhausted=True))
                continue
            started = time.monotonic()
            attempt, packet = _run_arm_attempt(arm, scenario_id, attempt_index, config, tmpdir)
            elapsed = time.monotonic() - started
            if attempt is None:
                # C unavailable.
                placeholder = Attempt(
                    arm=arm, scenario_id=scenario_id, attempt_index=attempt_index,
                    decisions=(), gate_results=(), verifier_findings=(),
                    errors=((packet or {}).get("reason", ""),) if packet else (),
                    repeated_error_id=None, budget_used=used["cost"],
                    chars_injected=0, latencies_ms=(elapsed * 1000.0,),
                    outcome="UNAVAILABLE",
                    signature=f"unavailable-{arm}-{scenario_id}-a{attempt_index:02d}",
                )
                paths.append(_write_attempt(config, placeholder, budget_exhausted=False,
                                            unavailable_reason=(packet or {}).get("reason", "")))
                continue
            used["cost"] = round(used["cost"] + (attempt.budget_used or 0.0), 6)
            used["turns"] += 1
            if elapsed > config.budget.time_seconds:
                paths.append(_write_attempt(config, attempt, budget_exhausted=True))
                continue
            paths.append(_write_attempt(config, attempt, budget_exhausted=False))
    return paths


def run_all(scenario_ids: Iterable[str] | None = None,
            attempts: int = 3,
            cfg: RunnerConfig | None = None) -> dict[str, list[Path]]:
    """Run every arm against every scenario (filtered by ``scenario_ids`` if given)."""
    config = cfg or RunnerConfig(attempts=attempts)
    config = config.with_overrides(attempts=attempts)
    L.verify_lock(config.repo_root, config.lock_path, arms=config.arms)
    targets = [s for s in SCENARIOS if scenario_ids is None or s.id in set(scenario_ids)]
    out: dict[str, list[Path]] = {}
    for scenario in targets:
        for arm in config.arms:
            key = f"{arm}/{scenario.id}"
            out[key] = run_arm(arm, scenario.id, attempts=attempts, cfg=config)
    return out
