"""Scoring for the paired A/B/C memory harness.

The primary metric is ``repeated_error_rate``: the fraction of (attempt,
story) pairs where ``repeated_error_id`` matches the scenario's
``expected_repeated_behavior_id``. A successful experiment shows B
substantially below A on this metric *without* raising any of:

- ``pass@1`` dropping (memory should not break working baselines)
- ``harm_rate`` lifting (memory should not inject harmful records into
  reviewer/security slots; tracked by the gate results and the
  ``verifier_findings`` outputs)
- ``wrong_memory_rate`` lifting (B should not pick irrelevant records;
  measured against the manually labelled positive set in
  ``fixtures/useful_memory_positives.json``)
- ``stale_memory_rate`` lifting (B should not return records whose
  source has drifted; measured by running ``consolidate`` against the
  scripted store)

The manual positive set is committed with the harness so re-runs do not
fabricate labels. Updating it requires a new lock signature (the lock is
a function of the harness code; **not** of the labels themselves, but
of the schema). A future change to the positive set should be made
alongside a new harness version.

A note on causal vs scripted: the directive explicitly says the
scripted metrics are **not causal** evidence about default-on. They are a
deterministic reproduction harness whose purpose is to detect regressions
in the runner/scoring code and to bound the harness's own variance.
Real paired-agent trials (deferred to P2) are what establishes causal
efficacy.

Outputs:

- ``score.json`` under ``results/``: full primary metrics, per-arm and
  per-scenario breakdown, and the per-arm aggregate comparing B vs A and
  C vs A (where C is available).
- ``score.md`` under ``results/``: a Markdown table for human review.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

PRIMARY_METRIC = "repeated_error_rate"
ARM_RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class ArmStats:
    arm: str
    attempts: int = 0
    unavailable: int = 0
    budget_exhausted: int = 0
    repeated_error_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    budget_count: int = 0
    wrong_memory_count: int = 0
    stale_memory_count: int = 0
    harmful_injection_count: int = 0
    useful_memory_count: int = 0
    total_latency_ms: float = 0.0
    total_turns: int = 0
    total_chars_injected: int = 0
    total_budget_used: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoreResult:
    primary_metric: str
    by_arm: dict[str, dict] = field(default_factory=dict)
    by_scenario: dict[str, dict] = field(default_factory=dict)
    deltas: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "primary_metric": self.primary_metric,
            "by_arm": self.by_arm,
            "by_scenario": self.by_scenario,
            "deltas": self.deltas,
            "warnings": self.warnings,
            "methodology": (
                "scripted simulated agent, NOT causal real-agent efficacy; "
                "see docs/MEMORY-BENCH.md for limitations"
            ),
        }


def _iter_attempt_files(results_dir: Path) -> Iterable[Path]:
    if not results_dir.is_dir():
        return
    yield from sorted(results_dir.glob("*.json"))


def _read_attempt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregated(arms_stats: dict[str, ArmStats]) -> dict[str, dict]:
    out = {}
    for arm, stats in arms_stats.items():
        # Exclude UNAVAILABLE attempts from pass@1 / repeated-error denominators:
        # an unavailable arm did not produce a verdict, so reporting 0.0 would
        # be misleading. Denominator is the count of available attempts.
        available = max(stats.attempts - stats.unavailable, 1)
        useful_plus_wrong = stats.useful_memory_count + stats.wrong_memory_count
        useful_plus_stale = stats.useful_memory_count + stats.stale_memory_count
        out[arm] = {
            "attempts": stats.attempts,
            "available": stats.attempts - stats.unavailable,
            "unavailable": stats.unavailable,
            "budget_exhausted": stats.budget_exhausted,
            "status": "unavailable" if stats.unavailable == stats.attempts
                       and stats.attempts > 0 else "ok",
            "repeated_error_rate": round(stats.repeated_error_count / available, 6),
            "pass@1": round(stats.pass_count / available, 6),
            "wrong_memory_rate": round(stats.wrong_memory_count / max(useful_plus_wrong, 1), 6),
            "stale_memory_rate": round(stats.stale_memory_count / max(useful_plus_stale, 1), 6),
            "harm_rate": round(stats.harmful_injection_count / available, 6),
            "useful_memory_precision": round(stats.useful_memory_count / max(useful_plus_wrong, 1), 6),
            "average_turns": round(stats.total_turns / available, 6),
            "average_latency_ms": round(stats.total_latency_ms / max(available, 1), 6),
            "chars_injected": stats.total_chars_injected,
            "budget_used_usd": round(stats.total_budget_used, 6),
        }
    return out


def _safe_ratio(num: int, den: int) -> float:
    return num / den if den > 0 else 0.0


def score_from_results(results_dir: Path = ARM_RESULTS_DIR) -> ScoreResult:
    """Aggregate the per-attempt JSON files under ``results_dir`` into a ScoreResult."""
    arms_stats: dict[str, ArmStats] = defaultdict(lambda: ArmStats(arm="?"))
    by_scenario: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    warnings: list[str] = []

    positives_path = Path(__file__).resolve().parent / "fixtures" / "useful_memory_positives.json"
    positives: dict[str, set[str]] = {}
    if positives_path.is_file():
        positives = json.loads(positives_path.read_text(encoding="utf-8"))

    for path in _iter_attempt_files(results_dir):
        record = _read_attempt(path)
        arm = record["arm"]
        scenario_id = record["scenario_id"]
        stats = arms_stats[arm]
        stats.arm = arm
        stats.attempts += 1
        if record.get("outcome") == "UNAVAILABLE":
            stats.unavailable += 1
            continue
        if record.get("outcome") == "BUDGET" or record.get("budget_exhausted"):
            stats.budget_exhausted += 1
            stats.budget_count += 1
        stats.total_latency_ms += float(record.get("latencies_ms", [0])[0] or 0.0)
        stats.total_turns += 1 if record.get("outcome") in ("PASS", "FAIL") else 0
        stats.total_chars_injected += int(record.get("chars_injected", 0))
        stats.total_budget_used += float(record.get("budget_used", 0.0))
        if record.get("outcome") == "PASS":
            stats.pass_count += 1
        elif record.get("outcome") == "FAIL":
            stats.fail_count += 1
        if record.get("repeated_error_id"):
            stats.repeated_error_count += 1
        decisions = record.get("decisions", [])
        selected = [d["target"] for d in decisions if d.get("kind") == "memory_recalled"]
        stale = [d["target"] for d in decisions if d.get("kind") == "stale_recall"]
        rejected = record.get("rejections", [])
        for record_id in selected:
            if scenario_id in positives:
                if record_id in positives[scenario_id]:
                    stats.useful_memory_count += 1
                else:
                    stats.wrong_memory_count += 1
            else:
                # no label set: count as wrong (unverifiable) rather than useful
                stats.wrong_memory_count += 1
        for record_id in stale:
            stats.stale_memory_count += 1
        for r in rejected:
            if isinstance(r, dict) and r.get("category") == "reviewer_independence":
                stats.harmful_injection_count += 1
        by_scenario[scenario_id][arm].append({
            "pass": 1 if record.get("outcome") == "PASS" else 0,
            "repeated_error": 1 if record.get("repeated_error_id") else 0,
            "chars_injected": int(record.get("chars_injected", 0)),
            "latency_ms": float(record.get("latencies_ms", [0])[0] or 0.0),
        })

    by_scenario_agg: dict[str, dict] = {}
    for scenario_id, arm_data in by_scenario.items():
        agg = {}
        for arm, rows in arm_data.items():
            n = max(len(rows), 1)
            agg[arm] = {
                "attempts": len(rows),
                "repeated_error_rate": round(_safe_ratio(sum(v["repeated_error"] for v in rows), n), 6),
                "pass@1": round(_safe_ratio(sum(v["pass"] for v in rows), n), 6),
                "average_chars_injected": round(_safe_ratio(sum(v["chars_injected"] for v in rows), n), 6),
                "average_latency_ms": round(_safe_ratio(sum(v["latency_ms"] for v in rows), n), 6),
            }
        by_scenario_agg[scenario_id] = agg

    aggregated = _aggregated(arms_stats)

    deltas: dict[str, float] = {}
    if "A" in aggregated and "B" in aggregated:
        deltas["B-A_repeated_error_rate"] = round(
            aggregated["B"]["repeated_error_rate"] - aggregated["A"]["repeated_error_rate"], 6)
        deltas["B-A_pass@1"] = round(
            aggregated["B"]["pass@1"] - aggregated["A"]["pass@1"], 6)
        deltas["B-A_harm_rate"] = round(
            aggregated["B"]["harm_rate"] - aggregated["A"]["harm_rate"], 6)
        deltas["B-A_average_turns"] = round(
            aggregated["B"]["average_turns"] - aggregated["A"]["average_turns"], 6)
        deltas["B_useful_memory_precision"] = aggregated["B"].get("useful_memory_precision", 0)
    if "C" in aggregated:
        c_status = aggregated["C"].get("status", "ok")
        deltas["C_status"] = c_status
        deltas["C_unavailable_attempts"] = aggregated["C"].get("unavailable", 0)
    if not any(arm in arms_stats for arm in ("A", "B", "C")):
        warnings.append("no per-arm result files found under results_dir; check that runner.py was invoked")
    if "B" in aggregated and aggregated["B"]["repeated_error_rate"] == 0 and aggregated["B"]["available"] > 0:
        warnings.append(
            "B repeated_error_rate is 0 across available attempts; "
            "this is the *scripted* ceiling — real-agent trials "
            "(MEMORY-RESEARCH-PLAN.md P2) are required for causal evidence."
        )

    if not any(arm in arms_stats for arm in ("A", "B", "C")):
        warnings.append("no per-arm result files found under results_dir; check that runner.py was invoked")

    return ScoreResult(
        primary_metric=PRIMARY_METRIC,
        by_arm=aggregated,
        by_scenario=by_scenario_agg,
        deltas=deltas,
        warnings=warnings,
    )


def score_to_json(score: ScoreResult, target_dir: Path = ARM_RESULTS_DIR) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "score.json"
    path.write_text(json.dumps(score.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def score_to_markdown(score: ScoreResult, target_dir: Path = ARM_RESULTS_DIR) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "score.md"
    lines = [
        "# Paired A/B/C memory harness — score",
        "",
        f"Primary metric: `{score.primary_metric}`",
        "",
        "## Per arm",
        "",
        "| arm | status | attempts | repeated_error_rate | pass@1 | wrong_memory_rate | stale_memory_rate | harm_rate | useful_memory_precision | avg turns | avg latency (ms) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, stats in score.by_arm.items():
        lines.append(
            f"| {arm} | {stats.get('status', 'ok')} | {stats['attempts']} | "
            f"{stats['repeated_error_rate']:.4f} | {stats['pass@1']:.4f} | "
            f"{stats['wrong_memory_rate']:.4f} | {stats['stale_memory_rate']:.4f} | "
            f"{stats['harm_rate']:.4f} | {stats['useful_memory_precision']:.4f} | "
            f"{stats['average_turns']:.2f} | {stats['average_latency_ms']:.2f} |"
        )
    if score.by_scenario:
        lines += ["", "## Per scenario × arm", "",
                  "| scenario | arm | attempts | repeated_error_rate | pass@1 |",
                  "|---|---|---|---|---|"]
        for scenario_id, by_arm in sorted(score.by_scenario.items()):
            for arm in sorted(by_arm):
                row = by_arm[arm]
                lines.append(
                    f"| {scenario_id} | {arm} | {row['attempts']} | "
                    f"{row['repeated_error_rate']:.4f} | {row['pass@1']:.4f} |"
                )
    if score.deltas:
        lines += ["", "## A vs B / A vs C deltas", ""]
        for key, value in score.deltas.items():
            lines.append(f"- `{key}` = `{value}`")
    if score.warnings:
        lines += ["", "## Warnings", ""]
        for w in score.warnings:
            lines.append(f"- {w}")
    lines += ["", "## Methodology", "",
              ("_scripted simulated agent; not causal real-agent efficacy; "
               "see docs/MEMORY-BENCH.md for limitations_")]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
