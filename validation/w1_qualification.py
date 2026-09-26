"""W1 three-run qualification record (owner decision "COMPLETE W1 RUNS 2-3", section 8).

Reads the three run records and states each criterion with the number it was measured from. Kernel safety and delivery
reliability are reported separately and never collapsed into one verdict.

    python3 validation/w1_qualification.py --runs 1 2 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W1 = ROOT / "closure-evidence/hardening/w1"
SAFETY = ("false_pass_count", "manual_state_repair", "orphan_state_count", "oracle_mapping_error_count")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--out", default=str(ROOT / "closure-evidence/hardening/AISEF-W1-QUALIFICATION.json"))
    a = ap.parse_args()
    runs = {}
    for r in a.runs:
        f = json.loads((W1 / f"run-{r}/driver.json").read_text(encoding="utf-8"))["phases"]["finish"]
        e = f["exit_criteria"]
        runs[r] = {"classification": f["run_classification"], "stories_done": f["run_metrics"]["stories_done"],
                   "stories_total": f["progress"]["total"], "safety_violations": f["safety_violations"],
                   "false_pass": e["false_pass_count"], "false_block": e["false_block_count"],
                   "manual_state_repair": e["manual_state_repair"], "orphan_state": e.get("orphan_state_count", len(e["orphan_state"])),
                   "drift_records": len(e["drift_records"]), "oracle_mapping_errors": e["oracle_mapping_error_count"],
                   "oracle_not_executed": e.get("oracle_not_executed_count", 0),
                   "oracle_passed_completely": e.get("oracle_passed_completely"),
                   "oracle_results": f["oracle"]["results"], "oracle_parse_complete": f["oracle"]["parse_complete"],
                   "cost_cap_status": f["cost_semantics"]["cost_cap_status"],
                   "usage": f["cost_semantics"]["usage_measured"], "phase_ok": f["ok"]}
    complete = [r for r, v in runs.items() if v["classification"] == "DELIVERY_COMPLETE"]
    framework_failures = [r for r, v in runs.items() if v["classification"] == "FRAMEWORK_FAILURE"]
    safety = {k: sum(runs[r][k.replace("_count", "")] if k.replace("_count", "") in runs[r] else runs[r][k] for r in runs)
              for k in ("false_pass", "manual_state_repair", "orphan_state", "drift_records", "oracle_mapping_errors")}
    kernel_safety = {
        "criterion": "0 framework safety violations across every valid run",
        "runs_measured": len(runs), "per_run_safety_violations": {r: runs[r]["safety_violations"] for r in runs},
        "totals": safety, "framework_failure_runs": framework_failures,
        "every_run_measurable": all(runs[r]["phase_ok"] for r in runs),
        "holds": not framework_failures and all(v == 0 for v in safety.values()) and all(runs[r]["phase_ok"] for r in runs)}
    delivery = {
        "criterion": "at least one DELIVERY_COMPLETE run, and every such run passes the hidden oracle completely",
        "delivery_complete_runs": complete,
        "oracle_complete_on_those": [r for r in complete if runs[r]["oracle_passed_completely"]],
        "stories_done": {r: f"{runs[r]['stories_done']}/{runs[r]['stories_total']}" for r in runs},
        "holds": bool(complete) and all(runs[r]["oracle_passed_completely"] for r in complete)}
    oracle = {
        "criterion": "every oracle check executed and classified; no red discarded, no skip counted as a pass",
        "parse_complete_every_run": all(runs[r]["oracle_parse_complete"] for r in runs),
        "mapping_errors": sum(runs[r]["oracle_mapping_errors"] for r in runs),
        "not_executed_on_a_complete_delivery": sum(runs[r]["oracle_not_executed"] for r in runs),
        "holds": all(runs[r]["oracle_parse_complete"] for r in runs)
                 and sum(runs[r]["oracle_mapping_errors"] + runs[r]["oracle_not_executed"] for r in runs) == 0}
    rec = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "level": "W1", "workload": "LedgerLock",
           "candidate": json.loads((ROOT / "closure-evidence/hardening/P19-FREEZE.json").read_text(encoding="utf-8"))["candidate_sha"],
           "runs": runs,
           "A_kernel_safety": kernel_safety, "B_delivery_reliability": delivery, "C_hidden_oracle_correctness": oracle,
           "D_w1_qualified": kernel_safety["holds"] and delivery["holds"] and oracle["holds"],
           "separation_rule": "kernel safety and model/route delivery reliability are separate verdicts; a legitimate "
                              "model/project stop is not a kernel defect, and kernel safety is not delivery reliability"}
    Path(a.out).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k, v in (("A kernel safety", kernel_safety), ("B delivery reliability", delivery), ("C oracle correctness", oracle)):
        print(("✅ " if v["holds"] else "❌ ") + k + ": " + v["criterion"])
    print(("✅" if rec["D_w1_qualified"] else "❌") + " D W1 QUALIFIED:", rec["D_w1_qualified"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
