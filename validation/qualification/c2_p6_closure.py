"""C2-P6 closure: QP-2.6 evidence-complete and GREEN on the requalified candidate (owner ruling 2026-09-30 B).

    python -P validation/qualification/c2_p6_closure.py --write   # -> closure-evidence/v2/cycle2/C2-P6-CLOSURE.json

Written after every attempt of the R3 harness commit was appended to C2-P6-RUN-HISTORY.json; closes that history at its
count (run_history.SEALS maps C2-P6 to it). Binds the candidate, its lineage (the integration candidate and the
correction after the failed R2 attempt), the qualification run, SUMMARY.json and every rung record by digest, and names
the earlier attempts kept as evidence. Not an owner acceptance: the owner ruled automatic downstream execution once the
requalified QP-2.6 is GREEN."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/C2-P6-CLOSURE.json"
HISTORY_REL = "closure-evidence/v2/cycle2/C2-P6-RUN-HISTORY.json"
QUAL_RUN, TESTS_RUN, HARNESS_COMMIT = 36796758932, 36796763565, "bfc4f37d8d04fe193c8867e76a5577366d19d989"
LINEAGE = [
    {"attempt": "1", "candidate": "63112544f1146097b69c538d98e09e5a52c547c1", "records": "closure-evidence/v2/cycle2/Q0-Q3",
     "outcome": "GREEN on five platforms — VALID HISTORICAL QUALIFICATION EVIDENCE, not the gate candidate (owner ruling B, Ruling 2)"},
    {"attempt": "R2", "candidate": "ac4a6c75b461e409f024965391ce77e7689c0e08", "harness": "9d855a5b66942db0d917b094ea190745cbebf076",
     "records": "closure-evidence/v2/cycle2/Q0-Q3-R2",
     "outcome": "FAILED: Windows Q0 48/51 — validation/qualification/v1_pf_001_policy.py repo_path returned the runner's absolute path "
                "(PRODUCT, C2-P6 seq 27, 34); Linux 3.11-3.14 GREEN; kept, never overwritten"},
    {"attempt": "R3", "candidate": "37dc0dcdf819387b65ee60cf614273df94aaef31", "harness": HARNESS_COMMIT,
     "records": "closure-evidence/v2/cycle2/Q0-Q3-R3", "outcome": "GREEN on Linux 3.11-3.14 and Windows 3.11 — the gate"},
]


def ident(rel: str) -> dict:
    return {"path": rel, "sha256": hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()}


def build() -> dict:
    entries = json.loads((ROOT / HISTORY_REL).read_text(encoding="utf-8"))["entries"]
    summary_rel = f"{C.OUT_REL}/SUMMARY.json"
    summary = json.loads((ROOT / summary_rel).read_text(encoding="utf-8"))
    if summary["verdict"] != "GREEN":
        raise SystemExit(f"{summary_rel} is {summary['verdict']}: nothing to close")
    records = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / C.OUT_REL).rglob("*.json") if p.name != "SUMMARY.json")
    q3 = {p.stem.split("Q3-")[1]: json.loads(p.read_text(encoding="utf-8"))["v1_pf_001_family_containment"]["fault_I"]
          for p in sorted((ROOT / C.OUT_REL / "Q3").glob("Q3-*.json"))}
    return {
        "record": "AISEF V2 — CYCLE-2 C2-P6 CLOSURE (QP-2.6 requalified: Q0-Q3 evidence-complete and GREEN)",
        "id": "AISEF-V2-CYCLE2-C2-P6-CLOSURE",
        "authority": "owner ruling 2026-09-30 B ('QP-2.6 MUST BE REQUALIFIED ON THE NEW EXACT CANDIDATE'; if GREEN, proceed "
                     "automatically into [QP-2.7 -> QP-2.8 -> QP-2.9] || [WP-2.10.1 -> WP-2.10.2])",
        "written": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate": {"commit": C.SEMANTIC_CANDIDATE, "aisef2_tree": C.KERNEL_TREE, "subject_trees": C.SUBJECT_TREES,
                      "harness_commit": HARNESS_COMMIT, "integration": ident("closure-evidence/v2/cycle2/C2-INTEGRATION-R2.json"),
                      "orchestration_repair": ident("closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json"),
                      "v1_pf_001_decision": ident("closure-evidence/v2/cycle2/V1-PF-001-RECURRENCE-1-DECISION.json"),
                      "c2_p5_acceptance": ident(C.C2_P5_ACCEPTANCE_REL)},
        "lineage": LINEAGE,
        "qualification": {"summary": {**ident(summary_rel), "verdict": summary["verdict"],
                                      "rungs": {k: v["status"] for k, v in summary["rungs"].items()}},
                          "ci_run": QUAL_RUN, "tests_ci_run": TESTS_RUN, "platforms_required": list(C.QUALIFICATION_PLATFORMS),
                          "records": [ident(r) for r in records],
                          "v1_pf_001_family_containment": {k: {"ok": v["ok"], "mechanism": v["mechanism"], "trees": v["full_trees_observed"],
                                                               "residual": v["residual_members"], "v1_walker_calls": len(v["v1_walker_calls"])}
                                                           for k, v in q3.items()}},
        "attempt_history": {"path": HISTORY_REL, "total_attempts": len(entries), "sha256": ident(HISTORY_REL)["sha256"],
                            "failed": [{"seq": e["seq"], "commit": e["commit"][:7], "where": e["where"], "job": e["job"],
                                        "classification": e["classification"], "known_defect": e.get("known_defect"),
                                        "gate_effect": e["gate_effect"]} for e in entries if e["result"] == "FAIL"],
                            "rule": "closed at this count when the requalified QP-2.6 was evidence-complete; the evidence commit's "
                                    "attempts go to C2-P7-RUN-HISTORY.json (LANE-Q); nothing rewritten"},
        "status": "QP-2.6 GREEN on the requalified candidate — LANE-Q (QP-2.7 -> QP-2.8 -> QP-2.9) and LANE-X (WP-2.10.1 -> "
                  "WP-2.10.2) start from it",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", required=True)
    ap.parse_args(argv)
    path = ROOT / OUT_REL
    if path.exists():
        raise SystemExit(f"{OUT_REL} exists: a closure is written once")
    rec = build()
    path.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(OUT_REL, "attempts", rec["attempt_history"]["total_attempts"], "failed", len(rec["attempt_history"]["failed"]),
          "records", len(rec["qualification"]["records"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
