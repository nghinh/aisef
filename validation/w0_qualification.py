"""Phase 18 — W0 SYNTHETIC-KERNEL qualification record (docs/SCALE-QUALIFICATION.md, level W0).

Reads the program's own artifacts and states every exit criterion with the number it was measured from; never
edits any of them. Exit 0 only when every criterion holds. Usage:

    python3 validation/w0_qualification.py --ci-run <github run id> --sha <candidate sha> \
        --out closure-evidence/hardening/AISEF-W0-QUALIFICATION.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "closure-evidence" / "hardening"


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def criteria(ci: dict) -> list[dict]:
    defects = _json(EV / "hardening-defect-set.json")
    members = [m for ms in defects["defects_by_fix_family"].values() for m in ms]
    open_members = [m["id"] for m in members if m["status"] == "OPEN"]
    open_p01 = [m["id"] for m in members if m["status"] == "OPEN" and m["severity"] in ("P0", "P1")]
    matrix = _json(EV / "fault-matrix.json")
    cells = next(v for v in matrix.values() if isinstance(v, list) and v and isinstance(v[0], dict))
    by_status: dict[str, int] = {}
    for c in cells:
        by_status[c["status"].split(" ")[0]] = by_status.get(c["status"].split(" ")[0], 0) + 1
    registry = (ROOT / "aisef" / "invariants.yaml").read_text(encoding="utf-8")
    reg = {k: registry.count(f"status: {k}") for k in ("PROVEN", "PARTIAL", "MISSING")}
    red_markers = [str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("*.py")
                   if re.search(r"^\s*@unittest\.expectedFailure", p.read_text(encoding="utf-8"), re.M)]
    diff = _json(EV / "differential-p12-summary.json") if (EV / "differential-p12-summary.json").is_file() else {}
    mut = _json(EV / "mutation-results.json") if (EV / "mutation-results.json").is_file() else {}
    survivors = [r for r in mut.get("results", []) if r.get("status") == "SURVIVED"]
    unclassified = [r["id"] for r in survivors if not r.get("classification")]
    rows = [
        ("0 P0/P1 open", not open_p01, {"open_p0_p1": open_p01}),
        ("0 unfixed confirmed defects from the frozen set", not open_members, {"open": open_members, "counts": defects["counts"]["by_status"]}),
        ("0 NEEDS_TEST fault cells", by_status.get("NEEDS_TEST", 0) == 0, {"fault_matrix": by_status}),
        ("fault matrix GREEN", by_status.get("RED", 0) == 0 and by_status.get("GREEN", 0) == len(cells), {"cells": len(cells), "fault_matrix": by_status}),
        ("0 MISSING/PARTIAL invariants", reg["PARTIAL"] == 0 and reg["MISSING"] == 0 and reg["PROVEN"] == 50, {"registry": reg}),
        ("0 expected-red tests", not red_markers, {"files_with_red_markers": red_markers}),
        ("0 unexplained model/kernel gaps (100 000 traces)", bool(diff) and diff.get("unexplained") == 0 and diff.get("traces", 0) >= 100000
         and (diff.get("manifest") or {}).get("pass") is True and diff.get("invariant_violations") == 0,
         {"differential": {k: diff.get(k) for k in ("traces", "matched", "unexplained", "invariant_violations", "exceptions", "silent_skips", "traces_per_s", "elapsed_s", "chunks", "manifest", "coverage")}}),
        ("KNOWN_DEVIATIONS empty", bool(diff) and not diff.get("known_deviations"), {"known_deviations": diff.get("known_deviations")}),
        ("0 safety-significant mutation survivors", bool(mut) and not unclassified and all(r.get("classification") in ("EQUIVALENT", "NOT_SIGNIFICANT", "KILLED_BY_NEW_TEST") for r in survivors),
         {"mutation": {k: mut.get(k) for k in ("mutations_generated", "killed", "survived", "equivalent")}, "unclassified_survivors": unclassified}),
        ("Linux + Windows CI green on the candidate", ci.get("all_green") is True, {"ci": ci}),
    ]
    return [{"criterion": name, "holds": bool(ok), "measured": data} for name, ok, data in rows]


def ci_state(run_id: str) -> dict:
    if not run_id:
        return {"all_green": None, "why": "no run id given"}
    try:
        out = subprocess.run(["gh", "run", "view", run_id, "--json", "jobs,headSha,conclusion"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             encoding="utf-8", timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return {"all_green": None, "why": f"gh unavailable: {e}"}
    d = json.loads(out)
    jobs = {j["name"]: j.get("conclusion") for j in d.get("jobs", [])}
    return {"run_id": run_id, "head_sha": d.get("headSha"), "jobs": jobs,
            "all_green": bool(jobs) and all(v == "success" for v in jobs.values()) and any("windows" in k for k in jobs)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci-run", default="")
    ap.add_argument("--sha", default="")
    ap.add_argument("--out", default=str(EV / "AISEF-W0-QUALIFICATION.json"))
    a = ap.parse_args(argv)
    sha = a.sha or subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT).stdout.strip()
    rows = criteria(ci_state(a.ci_run))
    rec = {"level": "W0", "program": "AISEF SYSTEMATIC HARDENING PROGRAM v1", "candidate_sha": sha,
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "qualified": all(r["holds"] for r in rows), "criteria": rows,
           "hidden_oracle": "reference model (tests/hardening/model.py) + differential harness (tests/hardening/differential.py)",
           "repeat_runs": "1 (deterministic; seeds recorded in the differential chunk files)", "known_deviations": []}
    Path(a.out).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        print(("✅" if r["holds"] else "✗"), r["criterion"])
    print("W0 QUALIFIED" if rec["qualified"] else "W0 NOT QUALIFIED", "@", sha[:12])
    return 0 if rec["qualified"] else 1


if __name__ == "__main__":
    sys.exit(main())
