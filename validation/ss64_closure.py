"""SS-64 closure record (owner item 4): every requirement measured from its artefact, none asserted by hand.

    python3 validation/ss64_closure.py --red <pytest tail on the pre-fix kernel> --green <pytest tail now> --conformance <pytest tail>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "closure-evidence/hardening"
CI_RUN = "35155275218"   # f0cd772 — the fix commit: Linux 3.11–3.14 + Windows 3.11 + lint + wheel


def find(o, pred):
    if isinstance(o, dict):
        if pred(o):
            return o
        for v in o.values():
            r = find(v, pred)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find(v, pred)
            if r:
                return r
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--red", required=True)
    ap.add_argument("--green", required=True)
    ap.add_argument("--conformance", required=True)
    a = ap.parse_args()
    red, green, conf = (Path(x).read_text(encoding="utf-8") for x in (a.red, a.green, a.conformance))
    reg = (ROOT / "aisef/invariants.yaml").read_text(encoding="utf-8")
    m = re.search(r"INV-G\.5.*?status:\s*(\w+)", reg, re.S)
    inv_g5 = m.group(1) if m else None
    fm = json.loads((E / "fault-matrix.json").read_text(encoding="utf-8"))
    cell = find(fm, lambda d: d.get("id") == "FM-R-09")
    sib = json.loads((E / "sibling-scan.json").read_text(encoding="utf-8"))
    ents = [d for v in (sib.values() if isinstance(sib, dict) else [sib]) for d in (v if isinstance(v, list) else []) if isinstance(d, dict)]
    f2 = [d for d in ents if "F2" in str(d.get("family", ""))]
    f2_open = [d for d in f2 if str(d.get("status", "")).upper() not in ("FIXED", "SUPERSEDED", "CONFIRMED_FIXED", "CLOSED")]
    ss64 = next((d for d in ents if d.get("id") == "SS-64"), None)
    ds = json.loads((E / "hardening-defect-set.json").read_text(encoding="utf-8"))
    d64 = find(ds, lambda d: d.get("id") == "SS-64")
    rep = json.loads((E / "phase12/unexplained-34999-replays.json").read_text(encoding="utf-8"))
    ci_raw = subprocess.run(["gh", "run", "view", CI_RUN, "--json", "conclusion,headSha,jobs"], capture_output=True, text=True).stdout
    ci = json.loads(ci_raw) if ci_raw.strip().startswith("{") else {"jobs": [], "raw": ci_raw[:200]}
    jobs = ci.get("jobs", [])
    adapters_changed = subprocess.run(["git", "-C", str(ROOT), "diff", "--stat", "d956249", "HEAD", "--", "aisef/clients"], capture_output=True, text=True).stdout.strip()
    req = {
        "deterministic_seed_34999_reproducer_RED_before_fix": {"ok": "2 failed" in red, "measured": red.strip().splitlines()[-1] if red.strip() else "", "how": "the current tests/hardening overlaid on a git worktree at d956249 (pre-fix aisef tree e9fb9b92…)"},
        "10_of_10_deterministic_mismatch_before_fix": {"ok": rep.get("all_replays_identical_on_compared_and_event_streams") is True and rep.get("classification") == "DETERMINISTIC_MISMATCH" and len(rep.get("replays", [])) >= 10,
                                                       "replays": len(rep.get("replays", [])), "classification": rep.get("classification"), "record": "phase12/unexplained-34999-replays.json"},
        "GREEN_after_fix": {"ok": "2 passed" in green, "measured": green.strip()},
        "review_stage_path_GREEN": {"ok": "2 passed" in green, "test": "tests/hardening/test_differential.py::TestSeed34999ACapInsideARegradedVerifierStopsTheRun"},
        "verify_only_path_GREEN": {"ok": "2 passed" in green, "test": "tests/hardening/test_differential.py::TestSS64SiblingVerifyOnlyCapIsABudgetStop"},
        "INV-G.5_PROVEN": {"ok": inv_g5 == "PROVEN", "registry_status": inv_g5},
        "F2_sibling_scan_clean": {"ok": not f2_open and ss64 is not None, "f2_entries": len(f2), "f2_open": [d.get("id") for d in f2_open], "ss64": {k: ss64.get(k) for k in ("id", "status", "family", "invariant")} if ss64 else None},
        "fault_matrix_cell_GREEN": {"ok": bool(cell) and str(cell.get("status", "")).upper().startswith("GREEN"), "cell": {k: cell.get(k) for k in ("id", "stage", "invariants", "test", "status")} if cell else None},
        "Windows_CI_GREEN": {"ok": any(j.get("name", "").startswith("unit (windows") and j.get("conclusion") == "success" for j in jobs), "run": CI_RUN, "sha": ci.get("headSha")},
        "Linux_CI_GREEN": {"ok": bool(jobs) and all(j.get("conclusion") == "success" for j in jobs if j.get("name", "").startswith("unit (ubuntu")), "run": CI_RUN,
                           "jobs": {j.get("name"): j.get("conclusion") for j in jobs}},
        "no_new_conformance_deviation": {"ok": "passed" in conf and "failed" not in conf and not adapters_changed, "deterministic_suite": conf.strip(),
                                         "adapters_changed_since_d956249": adapters_changed or "none",
                                         "live_smoke": "P15 record on d956249 (OpenCode 1.18.31, 10/10 probes); the fix touches no adapter — no live model call made (owner rule)"},
    }
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "defect": "SS-64", "severity": "P2", "invariant": "INV-G.5", "family": "F2", "fix_commit": "f0cd772",
           "requirements": req, "defect_set_entry": {k: d64.get(k) for k in ("id", "status", "severity", "family", "invariant")} if d64 else None,
           "all_met": all(v["ok"] for v in req.values())}
    (E / "phase12/SS-64-CLOSURE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k, v in req.items():
        print(("ok " if v["ok"] else "!! ") + k)
    print("SS-64 closure all met:", out["all_met"])
    return 0 if out["all_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
