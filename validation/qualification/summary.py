"""Assemble `closure-evidence/v2/Q0-Q3/SUMMARY.json` from the per-platform rung records, and verify it.

    python -P validation/qualification/summary.py            # write
    python -P validation/qualification/summary.py --check    # exit 1 if the summary is stale or a binding does not hold

A rung is GREEN only when every qualification platform (Linux and Windows) holds a GREEN record for it bound to the
frozen subject; any other platform's record is kept as a non-gate observation. Nothing here is a claim without its
underlying record: every record is bound by path and sha256.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

SUMMARY_REL = f"{C.OUT_REL}/SUMMARY.json"
RUNGS = ("Q0", "Q1", "Q2", "Q3")


def _records(out: pathlib.Path) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {r: [] for r in RUNGS}
    for rung in RUNGS:
        for p in sorted((out / rung).glob(f"{rung}-*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            found[rung].append({"path": p.relative_to(ROOT).as_posix(), "sha256": C.lf_sha(p), "record": rec})
    return found


def _bound(rec: dict) -> bool:
    s = rec.get("subject", {})
    return (s.get("seal_commit"), s.get("semantic_candidate"), s.get("kernel_tree"), s.get("head_kernel_tree")) == \
        (C.SEAL_COMMIT, C.SEMANTIC_CANDIDATE, C.KERNEL_TREE, C.KERNEL_TREE) and s.get("kernel_tree_is_the_candidates") is True


def assemble() -> dict:
    ident = C.identity()
    out = ROOT / C.OUT_REL
    found = _records(out)
    rungs, problems = {}, []
    for rung in RUNGS:
        per_platform, gate = {}, {}
        for entry in found[rung]:
            rec = entry["record"]
            plat = rec.get("platform", {})
            key = plat.get("label", entry["path"])
            row = {"path": entry["path"], "sha256": entry["sha256"], "status": rec.get("status"), "os": plat.get("os"), "python": plat.get("python"),
                   "ci_run": plat.get("ci_run"), "bound_to_subject": _bound(rec), "harness_digest": rec.get("harness_digest_at_run"),
                   "counts": rec.get("counts"), "seconds": rec.get("seconds"), "qualification_platform": plat.get("qualification_platform")}
            per_platform[key] = row
            if plat.get("qualification_platform"):
                gate.setdefault(plat["os"], []).append(row)
        missing = [p for p in C.QUALIFICATION_PLATFORMS if p not in gate]
        statuses = {os_: [r["status"] for r in rows] for os_, rows in gate.items()}
        unbound = [r["path"] for rows in gate.values() for r in rows if not r["bound_to_subject"]]
        if missing:
            status = C.UNRUNNABLE
        elif unbound:
            status = C.UNRUNNABLE
        elif all(all(s == C.GREEN for s in ss) for ss in statuses.values()):
            status = C.GREEN
        elif any(s == C.FAILED for ss in statuses.values() for s in ss):
            status = C.FAILED
        else:
            status = C.UNRUNNABLE
        rungs[rung] = {"status": status, "qualification_platforms_required": list(C.QUALIFICATION_PLATFORMS), "missing_platforms": missing,
                       "unbound_records": unbound, "records": per_platform}
        if status != C.GREEN:
            problems.append(f"{rung}: {status} (missing {missing}, unbound {unbound}, statuses {statuses})")
    # detail bindings from one Linux record of each rung (the Windows record binds the same subject)
    def pick(rung, key, default=None):
        for entry in found[rung]:
            rec = entry["record"]
            if rec.get("platform", {}).get("os") == "linux" and rec.get("status") == C.GREEN:
                return rec.get(key, default)
        return default
    q0 = pick("Q0", "checker_calibration")
    q2 = pick("Q2", "product_mutation")
    q2c = pick("Q2", "probe_capability_calibration")
    q3 = pick("Q3", "fault_matrix")
    q3r = pick("Q3", "v2_006_race")
    residual = {}   # the owned-range measurement around each platform's whole run (validation/v2/owned_run.py --out)
    for p in sorted((out / "PLATFORMS").glob("*.json")) if (out / "PLATFORMS").exists() else []:
        m = json.loads(p.read_text(encoding="utf-8"))
        residual[p.stem] = {"path": p.relative_to(ROOT).as_posix(), "sha256": C.lf_sha(p), "exit": m.get("exit"),
                            "owned_before": m.get("owned_before"), "owned_at_exit": m.get("owned_at_exit"), "owned_after": m.get("owned_after"),
                            "escaped": len(m.get("escaped", [])), "released_empty": m.get("released_empty"), "mechanism": m.get("mechanism"),
                            "ci_run": m.get("ci_run"), "os": m.get("os")}
        if m.get("owned_after") or m.get("escaped") or not m.get("released_empty"):
            problems.append(f"residual processes on {p.stem}: {residual[p.stem]}")
    for plat in C.QUALIFICATION_PLATFORMS:
        if not any(v.get("os") == plat for v in residual.values()):
            problems.append(f"no owned-range measurement for {plat}")
    overall = C.GREEN if all(r["status"] == C.GREEN for r in rungs.values()) else (
        C.FAILED if any(r["status"] == C.FAILED for r in rungs.values()) else C.UNRUNNABLE)
    return {
        "record": "AISEF V2 — Q0–Q3 QUALIFICATION SUMMARY (QP-7)", "work_package": "QP-7", "rfc_sections": ["27"],
        "authority": "AISEF V2 — P7 / QP-7 EXECUTION AUTHORIZATION / Q0 → Q1 → Q2 → Q3 QUALIFICATION (owner, 2026-09-27)",
        "verdict": overall, "rung_status_model": {"GREEN": "every applicable case passed on every qualification platform",
                                                  "FAILED": "a case executed and failed", "UNRUNNABLE": "could not execute or measure; never presented as FAILED"},
        "subject": {"seal_commit": C.SEAL_COMMIT, "semantic_candidate": C.SEMANTIC_CANDIDATE, "kernel_tree": C.KERNEL_TREE,
                    "v1_product_tree": C.V1_PRODUCT_TREE, "head_at_assembly": ident["head"], "head_kernel_tree": ident["head_kernel_tree"],
                    "rfc": ident["rfc"], "probe": ident["probe"], "harness": ident["harness"]},
        "rungs": rungs,
        "q0": {"checker_calibration_count": (q0 or {}).get("calibrated"), "checkers_discovered": (q0 or {}).get("discovered"),
               "f1_f11": pick("Q0", "f1_f11", {}).get("summary") if pick("Q0", "f1_f11") else None,
               "v2_006": {k: v for k, v in (pick("Q0", "v2_006") or {}).items() if k in ("lineage_ends_at_V2_006", "f5_row_sha256", "probe_digest")}},
        "q2": {"mutation": (q2 or {}).get("totals"), "mutation_records": {k: {"path": v["path"], "sha256": v["sha256"]} for k, v in ((q2 or {}).get("phases") or {}).items()},
               "calibration_inventory": (q2c or {}).get("fresh"), "calibration_digest": C.sha_text(json.dumps((q2c or {}).get("fresh"), sort_keys=True)) if q2c else None},
        "q3": {"fault_matrix_rows": (q3 or {}).get("rows"), "fault_matrix_classes": (q3 or {}).get("classes"),
               "fault_matrix_digest": C.sha_text(json.dumps([{k: r[k] for k in ("id", "class", "cases", "expected")} for r in (q3 or {}).get("matrix", [])], sort_keys=True)) if q3 else None,
               "v1_matrix_cells": (pick("Q3", "v1_fault_matrix") or {}).get("cells"), "race_10_observations": (q3r or {}).get("RACE_10_observations")},
        "platform_identities": {rung: {k: {"os": v["os"], "python": v["python"], "ci_run": v["ci_run"], "status": v["status"]} for k, v in r["records"].items()}
                                for rung, r in rungs.items()},
        "residual_processes": residual,
        "problems": problems, "at": C.now(),
    }


def check() -> list[str]:
    fresh = assemble()
    committed = ROOT / SUMMARY_REL
    out = list(fresh["problems"])
    if not committed.exists():
        return out + [f"{SUMMARY_REL} is missing"]
    old = json.loads(committed.read_text(encoding="utf-8"))
    for k in ("verdict", "subject", "rungs", "q0", "q2", "q3"):
        a, b = old.get(k), fresh.get(k)
        if k == "subject":
            a, b = {x: y for x, y in a.items() if x != "head_at_assembly"}, {x: y for x, y in b.items() if x != "head_at_assembly"}
        if a != b:
            out.append(f"{SUMMARY_REL} is stale in {k}")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
        for p in problems:
            print(f"FAIL  {p}")
        print("qualification summary: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    rec = assemble()
    C.write(SUMMARY_REL, rec)
    print(f"wrote {SUMMARY_REL}: {rec['verdict']} | " + " ".join(f"{k}={v['status']}" for k, v in rec["rungs"].items()))
    for p in rec["problems"]:
        print(f"    {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
