"""P7-FINDING-001 — the targeted real-path reproducer (owner's diagnostic authorization §5, §7; after the kernel
correction, the natural stress of the correction authorization §17-§18: 0 disagreements required, the stale-bytecode
condition counted where it arose).

    python -P validation/qualification/diag_orch9.py --runs 250 [--shard N] [--keep-going] [--print] [--out DIR]

Runs the real ORCH_9_and_10 case of tests/v2/test_p6_orchestration.py `--runs` times in this process — a fresh
repository, two real worktrees, the real python_callable probe for both parties, the real test runner, the real merger
and a RunScope each time; nothing mocked, no delay, no retry, no ordering imposed (§3) — and reads back what the case's
ProofObserver saw: for every proof, what the two checkouts held before it and what the proof decided; for the whole
run, when S0's checkout wrote its files and when S2's developer wrote app/calc.py — the interval inside which the
pre-correction mechanism arose on the natural path (the stale-bytecode condition: one checkout holding bytecode of
another source that an in-tree reader would take for its source). Since the correction the observation writes no
bytecode and reads none from the tree, so the condition cannot arise from the observation and cannot split a proof:
every disagreement is a finding — kept in full with owner §2's evidence, the loop stops, the exit status says so.
Before the correction a run whose S2 failed by VERIFIER_DISAGREEMENT was a reproduction (kept in full, the loop
stopped unless --keep-going); the fields still say so, so a record of either candidate reads the same way.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import statistics
import sys
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.orchestrate import workspace as W  # noqa: E402
from tests.v2 import test_p6_orchestration as T  # noqa: E402
from validation.qualification import common as C  # noqa: E402

CASE = "test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back"
OUT_REL = "closure-evidence/v2/P7-FINDING-001"
REAL_CHECKOUT = W.GitWorkspace.checkout


def _party(facts: dict) -> dict:
    header = facts.get("bytecode_header") or {}
    return {"source_mtime_ns": facts.get("source_mtime_ns"), "source_mtime_s": facts.get("source_mtime_s"),
            "source_size": facts.get("source_size"), "bytecode_source_mtime": header.get("source_mtime"),
            "bytecode_source_size": header.get("source_size"), "bytecode_valid_for_source": facts.get("bytecode_valid_for_source"),
            "bytecode_stale": facts.get("bytecode_stale"), "head": facts.get("head")}


def one(index: int) -> dict:
    marks: dict[str, int | None] = {}

    def checkout(self, name, revision):   # observational: the time the worktree's files were written, read after the fact
        co = REAL_CHECKOUT(self, name, revision)
        try:
            marks[name] = os.stat(pathlib.Path(co.path, "app", "__init__.py")).st_mtime_ns
        except OSError:
            marks[name] = None
        return co

    case = T.Orchestration(CASE)
    result = unittest.TestResult()
    started = time.perf_counter()
    with mock.patch.object(W.GitWorkspace, "checkout", checkout):
        case.run(result)
    seconds = round(time.perf_counter() - started, 3)
    seen = getattr(case, "observed", None)
    run = {"run": index, "seconds": seconds, "ok": result.wasSuccessful(), "worktree_written_ns": marks,
           "story_failures": None, "proofs": [], "reproduced": False, "unexplained_divergences": 0, "disagreements": []}
    if seen is None:
        run["outcome"] = "NO_OBSERVATION (the case did not reach its stories)"
        run["unittest"] = [(t.id(), tb[-3000:]) for t, tb in result.failures + result.errors]
        return run
    run["story_failures"] = seen.story_failures
    for e in seen.proofs:
        pred = e["predicted_divergence"]
        run["proofs"].append({"story_id": e["story_id"], "criterion_id": e["criterion_id"], "point": e["point"],
                              "candidate": e["candidate"], "agreement": e["agreement"], "failure": e["failure"],
                              "stale_bytecode_condition": pred["divergence"], "condition": pred,
                              "implementer": _party(e["before"]["implementer"]), "verifier": _party(e["before"]["verifier"]),
                              "explained": e["agreement"]})   # since the correction: agreement, whatever the checkouts hold
    run["unexplained_divergences"] = sum(1 for p in run["proofs"] if not p["explained"])
    run["reproduced"] = any(f[0] == "VERIFIER_DISAGREEMENT" for f in seen.story_failures.get("S2", []))
    c0 = next((p for p in run["proofs"] if (p["story_id"], p["criterion_id"], p["point"]) == ("S2", "C0", "POST_MERGE")), None)
    t_add = marks.get("wt-S0")
    if c0 is not None and t_add is not None and c0["implementer"]["source_mtime_ns"] is not None:
        t_dev, t_ver = c0["implementer"]["source_mtime_ns"], c0["verifier"]["source_mtime_ns"]
        header = c0["implementer"]["bytecode_source_mtime"]
        run["interval"] = {
            "S0_checkout_wrote_ns": t_add, "S2_developer_wrote_calc_ns": t_dev, "S2_verifier_calc_written_ns": t_ver,
            "D_ms": round((t_dev - t_add) / 1e6, 1), "W_ms": round((t_ver - t_dev) / 1e6, 1) if t_ver is not None else None,
            "bytecode_header_second": header, "S0_checkout_second": t_add // 10 ** 9, "S2_developer_second": t_dev // 10 ** 9,
            "S2_verifier_second": t_ver // 10 ** 9 if t_ver is not None else None,
            "implementer_same_second_as_bytecode": header == (t_dev // 10 ** 9) & 0xFFFFFFFF,
            "verifier_same_second_as_bytecode": header == ((t_ver // 10 ** 9) & 0xFFFFFFFF) if t_ver is not None else None,
        }
    if run["reproduced"] or run["unexplained_divergences"] or not run["ok"]:
        run["disagreements"] = seen.disagreements
        run["unittest"] = [(t.id(), tb[-3000:]) for t, tb in result.failures + result.errors]
    if run["reproduced"]:
        run["outcome"] = "REPRODUCED"
    elif run["unexplained_divergences"]:
        run["outcome"] = "UNEXPLAINED_DIVERGENCE"
    elif run["ok"]:
        run["outcome"] = "PASS"
    else:
        run["outcome"] = "OTHER_FAILURE"
    return run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=250)
    ap.add_argument("--shard", type=int, default=1)
    ap.add_argument("--keep-going", action="store_true", help="measure every run even after a reproduction")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--out", default=OUT_REL)
    a = ap.parse_args(argv)
    ident = C.identity()
    plat = C.platform_id()
    label = plat["label"]
    record = {"record": "P7-FINDING-001 real-path reproduction attempt", "finding": "P7-FINDING-001",
              "owner_authorization": "P7-FINDING-001 DIAGNOSTIC AUTHORIZATION §5 (targeted real-path reproducer, nothing mocked, "
                                     "no delay, no retry, no ordering imposed)",
              "case": f"tests.v2.test_p6_orchestration.Orchestration.{CASE}", "subject": ident, "subject_problems": C.subject_problems(ident),
              "platform": plat, "shard": a.shard, "runs_requested": a.runs, "stop_on_reproduction": not a.keep_going,
              "started": C.now(), "runs": []}
    stopped = None
    for i in range(1, a.runs + 1):
        r = one(i)
        record["runs"].append(r)
        iv = r.get("interval") or {}
        print(f"run {i}: {r['outcome']} D={iv.get('D_ms')}ms W={iv.get('W_ms')}ms same_second="
              f"{iv.get('implementer_same_second_as_bytecode')}/{iv.get('verifier_same_second_as_bytecode')} "
              f"proofs={len(r['proofs'])} {r['seconds']}s", flush=True)
        if r["outcome"] == "UNEXPLAINED_DIVERGENCE" or (r["outcome"] == "REPRODUCED" and not a.keep_going):
            stopped = r["outcome"]
            break
    runs = record["runs"]
    ds = [r["interval"]["D_ms"] for r in runs if r.get("interval")]
    record["finished"] = C.now()
    record["stopped_on"] = stopped
    record["totals"] = {
        "runs_executed": len(runs), "reproduced": sum(r["reproduced"] for r in runs),
        "stale_bytecode_conditions": sum(any(p["stale_bytecode_condition"] for p in r["proofs"]) for r in runs),
        "bytecode_beside_a_source_in_any_checkout": sum(any(p[party]["bytecode_source_size"] is not None for p in r["proofs"] for party in ("implementer", "verifier")) for r in runs),
        "unexplained_divergences": sum(r["unexplained_divergences"] for r in runs),
        "other_failures": sum(r["outcome"] == "OTHER_FAILURE" for r in runs), "no_observation": sum(r["outcome"].startswith("NO_OBS") for r in runs),
        "runs_with_D_under_1000ms": sum(d < 1000 for d in ds), "D_ms_min": min(ds) if ds else None,
        "D_ms_median": statistics.median(ds) if ds else None, "D_ms_max": max(ds) if ds else None,
        "seconds_per_run_median": statistics.median(r["seconds"] for r in runs) if runs else None,
    }
    record["harness_digest_at_run"] = C.harness_digest()
    rel = f"{a.out}/diag-orch9-{label}-shard{a.shard}.json"
    C.write(rel, record)
    if a.print:
        C.emit(rel, record)
    t = record["totals"]
    print(f"{label} shard {a.shard}: {t['runs_executed']} runs, reproduced {t['reproduced']}, stale-bytecode conditions {t['stale_bytecode_conditions']}, "
          f"bytecode beside a source {t['bytecode_beside_a_source_in_any_checkout']}, unexplained {t['unexplained_divergences']}, "
          f"other failures {t['other_failures']}, D<1s in {t['runs_with_D_under_1000ms']}, D median {t['D_ms_median']} ms")
    return 2 if t["unexplained_divergences"] or t["other_failures"] or t["no_observation"] else 0


if __name__ == "__main__":
    sys.exit(main())
