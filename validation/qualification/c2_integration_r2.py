"""The Cycle-2 integration candidate after owner ruling 2026-09-30 B ("Integration"): LANE-R and LANE-O merged
mechanically, the identities before and after, the guards, and the orchestration adversarial suite under the owned
process range.

    python -P validation/qualification/c2_integration_r2.py --write    # -> closure-evidence/v2/cycle2/C2-INTEGRATION-R2.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import p5_acceptance as pa  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/C2-INTEGRATION-R2.json"
BASE = "45136086c3e4a98534f975e6db979f94165af5f3"        # the stopped QP-2.6 gate (both lanes start here)
LANE_R = "ade198e7612c66655ff911ebb73a8c288e9575d2"      # V1-PF-001 policy correction, calibration, ruling record, corrigendum
LANE_O = "cacaa6bd65a0c627bdb18e1a9fc8c29b98695676"      # C2-ORCHESTRATION-CONFORMANCE-REPAIR
MERGE = "6368ae57ec8ada335546bfd6ee979d98ed80615a"
CANDIDATE = "ac4a6c75b461e409f024965391ce77e7689c0e08"   # MERGE + the C2-P5 kernel provenance rule (owner choice 2026-10-01)
TREES = ("aisef", "aisef2", "aisef2/probe", "validation/v2", "tests/v2")
FROZEN = ("closure-evidence/v2/cycle2/V1-PF-001-RECURRENCE-1.json", "closure-evidence/v2/cycle2/P5-CONTRACT-APPROVALS.json",
          "closure-evidence/v2/cycle2/C2-P5-ACCEPTANCE.json", "closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json",
          "closure-evidence/v2/cycle2/P5-FALSIFIABILITY.json", "closure-evidence/v2/cycle2/Q0-Q3/SUMMARY.json",
          "closure-evidence/v2/cycle2/C2-P6-RUN-HISTORY.json", "closure-evidence/v2/cycle2/CYCLE2-FREEZE-MANIFEST.json",
          "closure-evidence/v2/V2-RETRY-POLICY.json", "closure-evidence/v2/P6-MUTATION.json", "closure-evidence/v2/P6-MIGRATION-TABLE.json",
          "closure-evidence/hardening/AISEF-W0-QUALIFICATION.json")
ORCH_MODULE = "tests.v2.test_c2_orchestration_conformance"


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _changed(a: str, b: str) -> list[str]:
    return sorted(git("diff", "--name-only", a, b).splitlines())


def _run(argv: list[str]) -> dict:
    t = time.monotonic()
    r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8")
    return {"command": "python -P " + " ".join(argv), "exit": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-2:],
            "seconds": round(time.monotonic() - t, 1)}


def _orchestration_suite() -> dict:
    with tempfile.TemporaryDirectory() as d:
        owned = pathlib.Path(d) / "owned.json"
        t = time.monotonic()
        r = subprocess.run([sys.executable, "-P", "validation/v2/owned_run.py", "--out", str(owned), "--",
                            sys.executable, "-m", "unittest", ORCH_MODULE], cwd=ROOT, capture_output=True, encoding="utf-8")
        o = json.loads(owned.read_text(encoding="utf-8"))
    tail = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith(("Ran ", "OK", "FAILED"))]
    return {"module": ORCH_MODULE, "exit": r.returncode, "result": tail, "seconds": round(time.monotonic() - t, 1),
            "owned": {k: o.get(k) for k in ("owned_before", "owned_at_exit", "owned_after", "escaped", "released_empty")}}


def measure() -> dict:
    head = git("rev-parse", "HEAD")
    lane_r, lane_o = _changed(BASE, LANE_R), _changed(BASE, LANE_O)
    accepted = json.loads((ROOT / pa.OUT_REL).read_text(encoding="utf-8"))["verification"]["identities"]
    v = pa.verify(run_guards=False)
    rows = v["identities"]["specs"]
    key = lambda r: [r["spec_id"], r["contract_id"], r["contract_hash"], r["spec_hash_id"], r["semantic_hash"], r["probe_id"], r["probe_digest"]]  # noqa: E731
    frozen = {rel: {"base": git("rev-parse", f"{BASE}:{rel}"), "head": git("rev-parse", f"HEAD:{rel}")} for rel in FROZEN}
    guards = {**{k: _run(argv) for k, argv in pa.GUARDS.items()},
              "mutation": _run(["validation/v2/mutation.py", "--check"]),
              "orchestration_repair_record": _run(["validation/qualification/c2_orchestration_repair.py", "--check"])}
    suite = _orchestration_suite()
    problems = []
    if set(lane_r) & set(lane_o):
        problems.append(f"both lanes changed {sorted(set(lane_r) & set(lane_o))}")
    if [key(r) for r in rows] != [key(r) for r in accepted["specs"]]:
        problems.append("a contract, spec or semantic hash differs from the accepted record")
    if v["identities"]["plan_hash"] != pa.ACCEPTED["plan_hash"] or v["identities"]["catalog"] != accepted["catalog"]:
        problems.append("the plan hash or the probe catalog differs from the accepted record")
    if v["semantic_change"] != "NONE" or v["problems"] or not v["cycle1_drift"]["ok"]:
        problems.append(f"verify: {v['semantic_change']} {v['problems']} cycle1_ok={v['cycle1_drift']['ok']}")
    problems += [f"{rel} changed since the stopped gate" for rel, b in frozen.items() if b["base"] != b["head"]]
    problems += [f"tree {t} changed" for t in ("aisef", "aisef2/probe") if git("rev-parse", f"{BASE}:{t}") != git("rev-parse", f"HEAD:{t}")]
    problems += [f"guard {k}: exit {g['exit']}" for k, g in guards.items() if g["exit"]]
    o = suite["owned"]
    if suite["exit"] or o["owned_after"] or o["escaped"] or not o["released_empty"]:
        problems.append(f"orchestration suite: exit {suite['exit']} owned {o}")
    return {
        "head": head, "candidate": CANDIDATE, "head_is_candidate_or_its_evidence_child": head == CANDIDATE
        or all(p.startswith(("closure-evidence/", "validation/qualification/")) for p in _changed(CANDIDATE, head)),
        "lanes": {"base": BASE, "LANE-R": {"head": LANE_R, "files": lane_r}, "LANE-O": {"head": LANE_O, "files": lane_o},
                  "overlap": sorted(set(lane_r) & set(lane_o)), "merge": MERGE, "merge_kind": "mechanical --no-ff, no conflict",
                  "after_merge": {"commit": CANDIDATE, "files": _changed(MERGE, CANDIDATE),
                                  "why": "the C2-P5 kernel provenance rule (owner choice 2026-10-01): the accepted proposal's "
                                         "identities.aisef2_tree is authoring provenance; nothing semantic tolerated"}},
        "trees": {t: {"base": git("rev-parse", f"{BASE}:{t}"), "lane_r": git("rev-parse", f"{LANE_R}:{t}"),
                      "lane_o": git("rev-parse", f"{LANE_O}:{t}"), "candidate": git("rev-parse", f"{CANDIDATE}:{t}")} for t in TREES},
        "identities": {"contracts": len(rows), "equal_to_accepted_record": [key(r) for r in rows] == [key(r) for r in accepted["specs"]],
                       "contract_spec_semantic_digest": hashlib.sha256(json.dumps([key(r) for r in rows]).encode()).hexdigest(),
                       "plan_hash": v["identities"]["plan_hash"], "proposal_digest": v["identities"]["proposal_digest"],
                       "catalog": {k: e["digest"] + (" (inactive)" if not e["active"] else "") for k, e in v["identities"]["catalog"].items()},
                       "semantic_change": v["semantic_change"], "cycle1_drift": v["cycle1_drift"],
                       "proposal_kernel_provenance": v["proposal_kernel_provenance"]},
        "frozen_evidence_blobs": frozen, "guards": guards, "orchestration_adversarial_suite": suite, "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", required=True)
    ap.parse_args(argv)
    t = time.monotonic()
    m = measure()
    rec = {"record": "AISEF V2 — CYCLE-2 INTEGRATION CANDIDATE (LANE-R + LANE-O, owner ruling 2026-09-30 B)",
           "authority": "owner ruling 2026-09-30 B ('Integration' steps 1-6); owner choice 2026-10-01 (narrow provenance rule)",
           **m, "verdict": "INTEGRATION CANDIDATE VERIFIED — semantic identities unchanged" if not m["problems"] else "PROBLEMS",
           "seconds": round(time.monotonic() - t, 1), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(rec["verdict"])
    for p in m["problems"]:
        print("  " + p)
    return 1 if m["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
