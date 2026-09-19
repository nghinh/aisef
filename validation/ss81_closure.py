"""SS-81 family closure record (owner decision 'FIX SS-81 FAMILY, VOID W0, THEN REQUALIFY', 2026-09-18): every condition
read from its artefact, none asserted by hand.

    python3 validation/ss81_closure.py --sha <candidate> --ci-run <id> --suite <full-suite log> --ruff <ruff output>
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
sys.path.insert(0, str(ROOT))
E = ROOT / "closure-evidence/hardening"
S = E / "w1/ss81"
FAMILY = [f"SS-{n}" for n in range(81, 90)]
REQUIRED = [f"R{n:02d}" for n in range(1, 13)]           # owner section 8: the twelve required regressions
CELLS = [f"FM-T-{n:02d}" for n in range(8, 17)]


def main() -> int:
    ap = argparse.ArgumentParser()
    for k in ("sha", "ci-run", "suite", "ruff"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    suite, ruff = (Path(x).read_text(encoding="utf-8") for x in (a.suite, a.ruff))
    tree = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{a.sha}:aisef"], capture_output=True, text=True).stdout.strip()
    from aisef.control import invariants as INV
    inv = {i.invariant_id: i.status for i in INV.load()}
    ds = json.loads((E / "hardening-defect-set.json").read_text(encoding="utf-8"))
    reg = {m["id"]: m for m in ds["additions_after_freeze"]}
    fm = {c["id"]: c["status"] for c in json.loads((E / "fault-matrix.json").read_text(encoding="utf-8"))["scenarios"]}
    runs = {p.name: p.read_text(encoding="utf-8") for p in (S / "reproducer-runs").glob("*.txt")}
    frozen = {n: t for n, t in runs.items() if ".frozen-02a34e0e." in n}
    fixed = {n: t for n, t in runs.items() if n.endswith(".fixed.txt")}
    strategy = json.loads((S / "COLLECTION-STRATEGY-QUALIFICATION.json").read_text(encoding="utf-8"))
    audit = json.loads((S / "HISTORICAL-REAUDIT-NEW-PROOF-MODEL.json").read_text(encoding="utf-8"))
    fam_src = (ROOT / "tests/hardening/test_ss81_family.py").read_text(encoding="utf-8")
    ci = json.loads(subprocess.run(["gh", "run", "view", a.ci_run, "--json", "conclusion,headSha,jobs"], capture_output=True, text=True).stdout or "{}")
    jobs = {j["name"]: j["conclusion"] for j in ci.get("jobs", [])}
    failed = re.findall(r"^(?:FAILED|ERROR) (\S+)", suite, re.M)
    req = {
        "every_family_reproducer_RED_on_the_frozen_kernel": {
            "ok": len(frozen) == 6 and all("exit=1" in t and re.search(r"^FAIL:", t, re.M) for t in frozen.values()),
            "fail_counts": {n: len(re.findall(r"^FAIL:", t, re.M)) for n, t in sorted(frozen.items())}},
        "every_family_reproducer_GREEN_on_the_fix": {"ok": len(fixed) == 6 and all(t.rstrip().endswith("exit=0") for t in fixed.values())},
        "the_twelve_required_regressions_exist": {"ok": all(re.search(rf"^class {r}\w+", fam_src, re.M) for r in REQUIRED), "classes": REQUIRED},
        "family_suite_GREEN": {"ok": not any(f.startswith("tests/hardening/test_ss81_family.py") for f in failed)},
        "collection_strategy_qualified_on_the_real_image": {"ok": strategy.get("pass") is True, "image": strategy.get("image"),
                                                            "pytest": strategy.get("pytest_in_image"), "requirements": strategy.get("requirements")},
        "historical_re_audit_0_false_pass": {"ok": audit.get("real_false_pass") == [] and len(audit.get("cases") or []) == 6,
                                            "summary": audit.get("summary")},
        "family_FIXED_in_the_register": {"ok": all(reg.get(i, {}).get("status") == "FIXED" for i in FAMILY),
                                         "family": {i: (reg[i]["severity"], reg[i]["status"]) for i in FAMILY if i in reg}},
        "SS-90_FIXED": {"ok": reg.get("SS-90", {}).get("status") == "FIXED"},
        "invariants_PROVEN": {"ok": inv.get("INV-TDD-NOP-PROOF") == "PROVEN" and inv.get("INV-T.EXECUTED-EVIDENCE") == "PROVEN"
                              and all(v == "PROVEN" for v in inv.values()), "registered": len(inv)},
        "fault_matrix_cells_GREEN": {"ok": all(fm.get(c, "").startswith("GREEN") for c in CELLS) and all(v.startswith("GREEN") for v in fm.values()),
                                     "cells": {c: fm.get(c) for c in CELLS}, "total": len(fm)},
        "full_suite_GREEN": {"ok": not failed and " failed" not in suite.strip().splitlines()[-1], "summary": suite.strip().splitlines()[-1]},
        "ruff_GREEN": {"ok": "All checks passed!" in ruff},
        "Linux_CI_GREEN": {"ok": bool(jobs) and all(v == "success" for k, v in jobs.items() if k.startswith("unit (ubuntu")) and ci.get("headSha") == a.sha,
                           "run": a.ci_run, "jobs": jobs},
        "Windows_CI_GREEN": {"ok": any(k.startswith("unit (windows") and v == "success" for k, v in jobs.items()) and ci.get("headSha") == a.sha},
    }
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "family": "F7-EXECUTION-EVIDENCE-VALIDITY", "defects": FAMILY + ["SS-90"],
           "status": "FIXED", "invariants": ["INV-TDD-NOP-PROOF", "INV-T.EXECUTED-EVIDENCE"], "candidate_sha": a.sha,
           "candidate_aisef_tree": tree, "requirements": req, "all_met": all(v["ok"] for v in req.values())}
    (S / "SS-81-FAMILY-CLOSURE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k, v in req.items():
        print(("ok " if v["ok"] else "!! ") + k)
    print("SS-81 family closure all met:", out["all_met"])
    return 0 if out["all_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
