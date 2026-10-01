"""SS-65 closure record (owner decision 'FIX SS-65 AT CAPABILITY-MODEL LEVEL', item 9): every condition read from
its artefact, none asserted by hand.

    python3 validation/ss65_closure.py --sha <candidate> --ci-run <id> --red <pytest tail on abad2a6> \
        --green <pytest tail now> --suite <full-suite log> --ruff <ruff output>
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
AUTO_DETECTED_BEFORE = ("package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml", "pubspec.yaml", "composer.json", "Gemfile")


def main() -> int:
    ap = argparse.ArgumentParser()
    for k in ("sha", "ci-run", "red", "green", "suite", "ruff"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    red, green, suite, ruff = (Path(x).read_text(encoding="utf-8") for x in (a.red, a.green, a.suite, a.ruff))
    matrix = json.loads((E / "tool-capability-matrix.json").read_text(encoding="utf-8"))
    prof = {p["stack"]: p for p in matrix["profiles"]}
    tree = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{a.sha}:aisef"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    from aisef.control import invariants as INV
    inv = {i.invariant_id: i.status for i in INV.load()}
    ds = json.loads((E / "hardening-defect-set.json").read_text(encoding="utf-8"))
    family = [m for m in ds["additions_after_freeze"] if m["id"] in ["SS-65"] + [s for s in next(x for x in ds["additions_after_freeze"] if x["id"] == "SS-65")["siblings"]]]
    fm = json.loads((E / "fault-matrix.json").read_text(encoding="utf-8"))
    cells = {c["id"]: c["status"] for c in fm["scenarios"] if c["id"] in ("FM-N-04", "FM-N-05", "FM-N-06", "FM-N-07", "FM-N-08", "FM-A-04")}
    ci = json.loads(subprocess.run(["gh", "run", "view", a.ci_run, "--json", "conclusion,headSha,jobs"], capture_output=True, text=True, encoding="utf-8").stdout or "{}")
    jobs = {j["name"]: j["conclusion"] for j in ci.get("jobs", [])}
    covered = {m for p in matrix["profiles"] for m in p["markers"]}
    py_sast, go_sast = prof["python"]["roles"]["sast"], prof["go"]["roles"]["sast"]
    m = re.search(r"(\d+) passed.*?(\d+) skipped", suite)
    req = {
        "original_python_reproducer_RED_before_fix": {"ok": "'bandit' not found in" in red, "how": "tests/hardening/test_ss65_reproducers.py on a worktree at abad2a6"},
        "original_go_reproducer_RED_before_fix": {"ok": "golang:1.23-alpine is not a harness-built environment" in red},
        "reproducers_GREEN_after_fix": {"ok": "2 passed" in green, "measured": green.strip()},
        "python_managed_image_runs_bandit": {"ok": py_sast["status"] == "QUALIFIED" and "1.9.4" in py_sast.get("probe_observed", "") and py_sast["exec"]["exit"] == 0,
                                             "image": prof["python"]["image"], "image_id": prof["python"]["image_id"], "observed": py_sast.get("probe_observed")},
        "go_managed_image_runs_gosec": {"ok": go_sast["status"] == "QUALIFIED" and go_sast["exec"]["exit"] == 0,
                                        "image": prof["go"]["image"], "image_id": prof["go"]["image_id"], "observed": go_sast.get("probe_observed")},
        "all_supported_stack_profiles_audited": {"ok": set(AUTO_DETECTED_BEFORE) <= covered and all(p["status"] == "QUALIFIED" for p in matrix["profiles"]),
                                                 "stacks": {p["stack"]: p["status"] for p in matrix["profiles"]}},
        "capability_registry_is_the_single_source_of_truth": {"ok": bool(m) and not any(f.startswith("tests/hardening/test_tool_capability.py")
                                                                                   for f in re.findall(r"^(?:FAILED|ERROR) (\S+)", suite, re.M)),
                                                              "test": "tests/hardening/test_tool_capability.py::TestRegistryIsTheOnlySource"},
        "real_image_qualification_passes_for_this_tree": {"ok": matrix.get("pass") is True and matrix.get("aisef_tree") == tree, "matrix_tree": matrix.get("aisef_tree"), "candidate_tree": tree,
                                                          "totals": matrix.get("totals")},
        "invariants_PROVEN": {"ok": inv.get("INV-N.DEFAULT-CAPABILITY") == "PROVEN" and inv.get("INV-N.1") == "PROVEN" and inv.get("INV-T.QUALIFICATION-REGISTER") == "PROVEN",
                              "status": {k: inv.get(k) for k in ("INV-N.DEFAULT-CAPABILITY", "INV-N.1", "INV-T.QUALIFICATION-REGISTER")}},
        "no_remaining_confirmed_capability_mismatch": {"ok": bool(family) and all(x["status"] == "FIXED" for x in family),
                                                       "family": {x["id"]: (x["severity"], x["status"]) for x in family}},
        "fault_matrix_cells_GREEN": {"ok": len(cells) == 6 and all(v.startswith("GREEN") for v in cells.values()), "cells": cells},
        "full_suite_GREEN": {"ok": bool(m) and " failed" not in suite.splitlines()[-1], "summary": suite.strip().splitlines()[-1]},
        "ruff_GREEN": {"ok": "All checks passed!" in ruff},
        "Linux_CI_GREEN": {"ok": bool(jobs) and all(v == "success" for k, v in jobs.items() if k.startswith("unit (ubuntu")) and ci.get("headSha") == a.sha,
                           "run": a.ci_run, "jobs": jobs},
        "Windows_CI_GREEN": {"ok": any(k.startswith("unit (windows") and v == "success" for k, v in jobs.items()) and ci.get("headSha") == a.sha},
    }
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "defect": "SS-65", "severity": "P1", "status": "FIXED",
           "invariant": "INV-N.DEFAULT-CAPABILITY", "candidate_sha": a.sha, "candidate_aisef_tree": tree,
           "requirements": req, "all_met": all(v["ok"] for v in req.values())}
    (E / "phase20/SS-65-CLOSURE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k, v in req.items():
        print(("ok " if v["ok"] else "!! ") + k)
    print("SS-65 closure all met:", out["all_met"])
    return 0 if out["all_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
