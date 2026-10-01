"""The Cycle-2 final integration candidate (owner ruling 2026-09-30 A/B, integration discipline): LANE-Q (QP-2.7..QP-2.9 on
the QP-2.6 candidate) and LANE-X (C2-P10) merged, with the identity impact analysis that names, for every rung, the
identity it consumed, whether the final candidate changed it, and what was rerun.

    python -P validation/qualification/c2_final_integration.py --write   # -> closure-evidence/v2/cycle2/C2-FINAL-INTEGRATION.json
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import p5_acceptance as pa  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/C2-FINAL-INTEGRATION.json"
QP26_CANDIDATE = "37dc0dcdf819387b65ee60cf614273df94aaef31"   # the QP-2.6 R3 candidate LANE-Q qualified on (kernel 37bf6457)
LANE_X = "6353aa815cdfbea3af477a0eadfae43130be6820"
TREES = ("aisef", "aisef2", "aisef2/probe", "aisef2/orchestrate", "validation/v2", "tests/v2")
NEW_PACKAGE = "aisef2/cohort/"


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _run(argv: list[str]) -> dict:
    t = time.monotonic()
    r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8")
    return {"command": "python -P " + " ".join(argv), "exit": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-2:],
            "seconds": round(time.monotonic() - t, 1)}


def kernel_change() -> dict:
    """What the final candidate changed in aisef2 since the QP-2.6 candidate, and whether anything outside the new package
    can reach it."""
    rows = [ln.split("\t") for ln in git("diff", "--name-status", QP26_CANDIDATE, "HEAD", "--", "aisef2").splitlines() if ln]
    added = sorted(p for s, p in rows if s == "A")
    other = sorted(f"{s} {p}" for s, p in rows if s != "A" or not p.startswith(NEW_PACKAGE))
    importers = []
    for p in sorted((ROOT / "aisef2").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(NEW_PACKAGE):
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""] if isinstance(n, ast.ImportFrom) else []
            importers += [f"{rel}: {m}" for m in mods if m == "aisef2.cohort" or m.startswith("aisef2.cohort.")]
    return {"since": QP26_CANDIDATE, "added": added, "changed_or_removed_outside_the_new_package": other,
            "importers_outside_the_new_package": importers,
            "every_earlier_kernel_file_byte_identical": not other, "unreachable_from_existing_kernel_code": not importers}


def measure() -> dict:
    head = git("rev-parse", "HEAD")
    k = kernel_change()
    v = pa.verify(run_guards=False)
    accepted = json.loads((ROOT / pa.OUT_REL).read_text(encoding="utf-8"))["verification"]["identities"]
    key = lambda r: [r["spec_id"], r["contract_id"], r["contract_hash"], r["spec_hash_id"], r["semantic_hash"], r["probe_id"], r["probe_digest"]]  # noqa: E731
    trees = {t: {"qp26_candidate": git("rev-parse", f"{QP26_CANDIDATE}:{t}"), "final": git("rev-parse", f"HEAD:{t}")} for t in TREES}
    changed = {t for t, x in trees.items() if x["qp26_candidate"] != x["final"]}
    rungs = {
        "QP-2.6 (Q0-Q3)": {"consumes": "the aisef2, validation/v2 and tests/v2 trees (common.SUBJECT_TREES, KERNEL_TREE)",
                           "changed": bool(changed & {"aisef2", "validation/v2", "tests/v2"}), "action": "RERUN in full on the final candidate (R4)"},
        "QP-2.7 (Q4)": {"consumes": "the kernel digest over every aisef2 file, the reference, the generator, the harness",
                        "changed": "aisef2" in changed, "action": "RERUN fresh on the final candidate"},
        "QP-2.8 (Q5)": {"consumes": "one identity over the kernel digest, the corpus, the harness, F1/F9",
                        "changed": "aisef2" in changed, "action": "RERUN (corpus recorded, calibrated and reproduced) on the final candidate"},
        "QP-2.9 (LedgerLock)": {"consumes": "the code its run executes: story_runner and everything it imports, the probes, the compiler, "
                                            "the runtime; the plan, the specs and the profile",
                                "changed": not (k["every_earlier_kernel_file_byte_identical"] and k["unreachable_from_existing_kernel_code"]),
                                "action": "NOT RERUN: every kernel file its run could import is byte-identical to the QP-2.6 candidate's and "
                                          "nothing outside aisef2/cohort imports the new package, so no executed path changed; its "
                                          "evidence stays bound to kernel 37bf6457"},
        "C2-P10 (WP-2.10.1, WP-2.10.2)": {"consumes": "the aisef2 tree it was built on", "changed": git("rev-parse", f"{LANE_X}:aisef2") != trees["aisef2"]["final"],
                                         "action": "its records re-checked here"},
    }
    guards = {"cycle2_baseline": _run(["validation/v2/cycle2_baseline.py", "--check"]),
              "checker_calibration": _run(["validation/v2/checker_calibration.py", "--check"]),
              "f1_f11": _run(["validation/v2/freeze_conformance.py", "--check"]),
              "v1_guard": _run(["validation/v2/v1_evidence_guard.py", "--check"]),
              "run_history": _run(["validation/v2/run_history.py", "check"]),
              "mutation": _run(["validation/v2/mutation.py", "--check"]),
              "orchestration_repair_record": _run(["validation/qualification/c2_orchestration_repair.py", "--check"]),
              "c2_p10_cohort": _run(["validation/qualification/c2_p10_cohort.py", "--check"]),
              "c2_p10_profile": _run(["validation/qualification/c2_p10_profile.py", "--check"])}
    problems = []
    if not k["every_earlier_kernel_file_byte_identical"]:
        problems.append(f"a kernel file outside {NEW_PACKAGE} changed: {k['changed_or_removed_outside_the_new_package']}")
    if not k["unreachable_from_existing_kernel_code"]:
        problems.append(f"existing kernel code imports the new package: {k['importers_outside_the_new_package']}")
    if "aisef" in changed or "aisef2/probe" in changed or "aisef2/orchestrate" in changed:
        problems.append(f"a frozen or qualified tree changed: {sorted(changed)}")
    if [key(r) for r in v["identities"]["specs"]] != [key(r) for r in accepted["specs"]] or v["semantic_change"] != "NONE" or v["problems"]:
        problems.append(f"a contract/spec identity changed: {v['semantic_change']} {v['problems']}")
    if v["identities"]["catalog"] != accepted["catalog"] or not v["cycle1_drift"]["ok"]:
        problems.append("the probe catalog or the Cycle-1 probe changed")
    if rungs["C2-P10 (WP-2.10.1, WP-2.10.2)"]["changed"]:
        problems.append("LANE-X's evidence was built on another kernel tree than the final one")
    problems += [f"guard {n}: exit {g['exit']}" for n, g in guards.items() if g["exit"]]
    return {"head": head, "lane_x": LANE_X, "qp26_candidate": QP26_CANDIDATE, "trees": trees, "changed_trees": sorted(changed),
            "kernel_change": k, "identity_impact": rungs,
            "identities": {"contracts": len(v["identities"]["specs"]), "plan_hash": v["identities"]["plan_hash"],
                           "semantic_change": v["semantic_change"], "proposal_kernel_provenance": v["proposal_kernel_provenance"],
                           "catalog": {n: e["digest"] for n, e in v["identities"]["catalog"].items()}},
            "guards": guards, "problems": problems}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", required=True)
    ap.parse_args(argv)
    t = time.monotonic()
    m = measure()
    rec = {"record": "AISEF V2 — CYCLE-2 FINAL INTEGRATION CANDIDATE (LANE-Q + LANE-X) AND IDENTITY IMPACT ANALYSIS",
           "authority": "owner rulings 2026-09-30 A and B (integration discipline: final integration candidate with identity impact "
                        "analysis; rerun affected rungs if consumed identities change)", **m,
           "verdict": "FINAL INTEGRATION CANDIDATE VERIFIED" if not m["problems"] else "PROBLEMS",
           "seconds": round(time.monotonic() - t, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(rec["verdict"])
    for p in m["problems"]:
        print("  " + p)
    return 1 if m["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
