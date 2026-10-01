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


def _aisef_tree(sha: str) -> str:
    if not sha:
        return ""
    return subprocess.run(["git", "rev-parse", f"{sha}:aisef"], capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT).stdout.strip()


def _status_of(m: dict) -> str:
    return str(m.get("status", "")).upper()


def criteria(ci: dict, sha: str = "") -> list[dict]:
    """INV-T.QUALIFICATION-REGISTER: W0 is QUALIFIED only when the COMPLETE current defect register — the frozen
    families and every later addition, whenever registered — holds no OPEN P0/P1."""
    defects = _json(EV / "hardening-defect-set.json")
    # The frozen families AND everything registered after the freeze (SS-61…): a defect found after the freeze is exactly
    # the kind this gate exists to catch, and reading only `defects_by_fix_family` made it invisible (found 2026-09-17,
    # when SS-65 was registered OPEN and this builder still printed QUALIFIED).
    additions = list(defects.get("additions_after_freeze") or [])
    register: dict[str, dict] = {}
    for m in [m for ms in defects["defects_by_fix_family"].values() for m in ms] + additions:
        if m["id"] in register and _status_of(register[m["id"]]) != _status_of(m):
            register[m["id"]] = {**m, "status": "OPEN"}      # two copies that disagree: the register is not trustworthy → OPEN
        register.setdefault(m["id"], m)
    members = list(register.values())
    def _status(m: dict) -> str:
        return str(m.get("status", "")).upper()
    open_members = [m["id"] for m in members if _status(m) == "OPEN"]
    open_p01 = [m["id"] for m in members if _status(m) == "OPEN" and m.get("severity") in ("P0", "P1")]
    no_status = [m["id"] for m in members if not _status(m)]
    declared_open = int(defects.get("counts", {}).get("by_status", {}).get("OPEN", 0))
    scan_agrees = len(open_members) == declared_open
    matrix = _json(EV / "fault-matrix.json")
    cells = next(v for v in matrix.values() if isinstance(v, list) and v and isinstance(v[0], dict))
    by_status: dict[str, int] = {}
    for c in cells:
        by_status[c["status"].split(" ")[0]] = by_status.get(c["status"].split(" ")[0], 0) + 1
    registry = (ROOT / "aisef" / "invariants.yaml").read_text(encoding="utf-8")
    reg = {k: registry.count(f"status: {k}") for k in ("PROVEN", "PARTIAL", "MISSING")}
    reg["registered"] = len(re.findall(r"^\s*- invariant_id:", registry, re.M))
    matrix_path = EV / "tool-capability-matrix.json"
    matrix = _json(matrix_path) if matrix_path.is_file() else {}
    tree = _aisef_tree(sha)
    red_markers = [str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("*.py")
                   if re.search(r"^\s*@unittest\.expectedFailure", p.read_text(encoding="utf-8"), re.M)]
    diff = _json(EV / "differential-p12-summary.json") if (EV / "differential-p12-summary.json").is_file() else {}
    mut = _json(EV / "mutation-results.json") if (EV / "mutation-results.json").is_file() else {}
    # SS-90: the record's rows are `rows` — reading a key mutate.py never writes made every survivor invisible
    survivors = [r for r in mut.get("rows", []) if r.get("status") == "SURVIVED"]
    # SS-90: traces and mutants measured on another kernel say nothing about this one — both must name the candidate's tree
    p12_digests = list((diff.get("manifest") or {}).get("kernel_digests") or [])
    p12_on_candidate = bool(tree) and p12_digests == [tree]
    conf = _json(EV / "TDD-POLICY-V2-CONFORMANCE.json") if (EV / "TDD-POLICY-V2-CONFORMANCE.json").is_file() else {}
    spec = _json(ROOT / "validation" / "mutation-targets.json")
    mutation_targets = {f"{t['module']}::{t['function']}" for t in spec["targets"]}      # a partial (--only) run is not the set
    unclassified = [r["id"] for r in survivors if not r.get("classification")]
    rows = [
        ("0 P0/P1 open", not open_p01, {"open_p0_p1": open_p01, "scanned": len(members), "additions_after_freeze_scanned": len(additions)}),
        ("0 unfixed confirmed defects from the frozen set", not open_members and scan_agrees,
         {"open": open_members, "counts": defects["counts"]["by_status"], "scan_agrees_with_declared_counts": scan_agrees,
          "members_without_an_explicit_status": no_status}),
        ("0 NEEDS_TEST fault cells", by_status.get("NEEDS_TEST", 0) == 0, {"fault_matrix": by_status}),
        ("fault matrix GREEN", by_status.get("RED", 0) == 0 and by_status.get("GREEN", 0) == len(cells), {"cells": len(cells), "fault_matrix": by_status}),
        ("0 MISSING/PARTIAL invariants", reg["PARTIAL"] == 0 and reg["MISSING"] == 0 and reg["PROVEN"] == reg["registered"] >= 50,
         {"registry": reg}),
        ("default tool capabilities qualified on real images for this product tree (INV-N.DEFAULT-CAPABILITY)",
         matrix.get("pass") is True and bool(tree) and matrix.get("aisef_tree") == tree,
         {"matrix": {k: matrix.get(k) for k in ("generated", "aisef_tree", "pass", "totals")}, "candidate_aisef_tree": tree}),
        ("0 expected-red tests", not red_markers, {"files_with_red_markers": red_markers}),
        ("0 unexplained model/kernel gaps (100 000 traces)", bool(diff) and diff.get("unexplained") == 0 and diff.get("traces", 0) >= 100000
         and (diff.get("manifest") or {}).get("pass") is True and diff.get("invariant_violations") == 0 and p12_on_candidate,
         {"differential": {k: diff.get(k) for k in ("traces", "matched", "unexplained", "invariant_violations", "exceptions", "silent_skips", "traces_per_s", "elapsed_s", "chunks", "manifest", "coverage")},
          "phase12_kernel_digests": p12_digests, "candidate_aisef_tree": tree}),
        ("KNOWN_DEVIATIONS empty", bool(diff) and not diff.get("known_deviations"), {"known_deviations": diff.get("known_deviations")}),
        ("0 safety-significant mutation survivors", bool(mut.get("rows")) and not unclassified and all(r.get("classification") in ("EQUIVALENT", "NOT_SIGNIFICANT", "KILLED_BY_NEW_TEST") for r in survivors)
         and bool(tree) and mut.get("aisef_tree") == tree and not mut.get("only")
         and set(mut.get("targets") or []) == mutation_targets,
         {"mutation": {k: mut.get(k) for k in ("mutations_generated", "killed", "survived", "equivalent", "aisef_tree")}, "unclassified_survivors": unclassified,
          "candidate_aisef_tree": tree}),
        # Owner decision 2026-09-20 section 6: the 100 000 traces are BROAD kernel-regression evidence. They write no
        # story test file, so the nop control is NOT_APPLICABLE in them and the V2 proof obligations are never
        # exercised there. The semantic evidence for the policy is the targeted real-kernel conformance suite, and it
        # must have run on THIS product tree.
        ("TDD proof policy V2 exercised on this product tree (targeted real-kernel conformance)",
         conf.get("pass") is True and bool(tree) and conf.get("aisef_tree") == tree and not conf.get("aisef_dirty")
         and (conf.get("summary") or {}).get("proof_modes_exercised") == "3/3"
         and (conf.get("summary") or {}).get("mismatches") == 0,
         {"conformance": {k: conf.get(k) for k in ("generated", "aisef_tree", "pass")},
          "summary": conf.get("summary"), "candidate_aisef_tree": tree}),
        ("Linux + Windows CI green on the candidate", ci.get("all_green") is True, {"ci": ci}),
    ]
    return [{"criterion": name, "holds": bool(ok), "measured": data} for name, ok, data in rows]


def ci_state(run_id: str, sha: str = "") -> dict:
    """Green only when the run is fully green AND its head is the candidate: a green run of another SHA is old evidence and
    must never satisfy this gate silently."""
    if not run_id:
        return {"all_green": None, "why": "no run id given"}
    try:
        out = subprocess.run(["gh", "run", "view", run_id, "--json", "jobs,headSha,conclusion"], capture_output=True, text=True,
                             encoding="utf-8", timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return {"all_green": None, "why": f"gh unavailable: {e}"}
    d = json.loads(out)
    jobs = {j["name"]: j.get("conclusion") for j in d.get("jobs", [])}
    head_matches = bool(sha) and d.get("headSha") == sha
    return {"run_id": run_id, "head_sha": d.get("headSha"), "candidate_sha": sha, "head_matches_candidate": head_matches, "jobs": jobs,
            "all_green": bool(jobs) and all(v == "success" for v in jobs.values()) and any("windows" in k for k in jobs) and head_matches}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci-run", default="")
    ap.add_argument("--sha", default="")
    ap.add_argument("--out", default=str(EV / "AISEF-W0-QUALIFICATION.json"))
    a = ap.parse_args(argv)
    sha = a.sha or subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT).stdout.strip()
    rows = criteria(ci_state(a.ci_run, a.sha), sha)
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
