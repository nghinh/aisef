"""Phase 12 — which kernel each differential chunk ran against (owner rule A: recorded, never guessed).

A chunk's workers are spawned at its start and import the kernel from disk then. From chunk 60000 the harness records
git HEAD and the dirty state of `aisef/` itself (DIRECTLY_RECORDED). Earlier chunks are attributed from their log's
birth time against the commit log (DERIVABLE_FROM_RAW_EVIDENCE) — except chunks 00000 and 10000, which started while
kernel edits were in progress on disk: their kernel is NOT_AVAILABLE and their seeds are re-run in full on the
candidate. Writes closure-evidence/hardening/phase12/kernel-split.json.

    python3 validation/p12_kernel_split.py --logs <dir with diff-p12-*.log>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = "f0cd772"          # SS-64 — the only aisef change between variant B and the candidate
VARIANT_B = "d956249"    # the tree chunks 20000–40000 ran on
FIRST = "023d6ce"        # HEAD when chunk 00000 started


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", required=True)
    ap.add_argument("--out", default=str(ROOT / "closure-evidence/hardening/phase12/kernel-split.json"))
    a = ap.parse_args()
    commits = []
    for ln in git("log", "--format=%H %ct %s", f"{FIRST}^..HEAD").splitlines()[::-1]:
        h, ct, msg = ln.split(" ", 2)
        commits.append({"commit": h[:12], "committed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(int(ct))), "ct": int(ct),
                        "aisef_tree": git("rev-parse", f"{h}:aisef")[:12], "subject": msg[:72]})
    fix_ct = next(c["ct"] for c in commits if c["commit"].startswith(FIX))
    diff_a = git("diff", "--stat", FIRST, VARIANT_B, "--", "aisef").splitlines()
    diff_b = git("diff", "--stat", VARIANT_B, FIX, "--", "aisef").splitlines()
    chunks = []
    for f in sorted(Path(a.logs).glob("diff-p12-*0000.log")):
        birth = os.stat(f).st_birthtime
        start = int(f.stem.split("-")[-1])
        rec = ROOT / f"closure-evidence/hardening/differential-p12-{start:05d}.json"
        direct = (json.load(open(rec, encoding="utf-8")).get("kernel") if rec.is_file() else None) or None
        head = [c for c in commits if c["ct"] <= birth][-1]["commit"][:7]
        if start <= 10000:
            cls, attr = "NOT_AVAILABLE", (f"working tree at start = HEAD {head} plus edits in progress toward the next commit (P16/P17 gate narrowing, process "
                                          "ownership, replay manifest for 00000; P13 positive session ownership for 10000) — which edits were on disk when the "
                                          "workers were spawned is not recoverable; every seed of the chunk is RE-RUN IN FULL on the candidate kernel")
        elif start <= 40000:
            cls, attr = "DERIVABLE_FROM_RAW_EVIDENCE", (f"{VARIANT_B}'s aisef tree exactly: the chain started 5 s after that commit with a clean tree and {FIX}'s only "
                                                         "aisef change is SS-64; the 4267 seeds whose scenario contains a verifier BUDGET step — the only path SS-64 "
                                                         "changes — are re-run on the candidate, plus a 500-seed control sample")
        elif direct:
            cls, attr = "DIRECTLY_RECORDED", f"{direct['head'][:12]} dirty_aisef={direct['dirty_aisef']}"
        else:
            cls, attr = "DERIVABLE_FROM_RAW_EVIDENCE", f"started after the SS-64 commit; the aisef tree is identical from {FIX} to HEAD"
        chunks.append({"chunk": f"{start:05d}", "log_birth": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(birth)), "head_at_birth": head,
                       "kernel_class": cls, "kernel_head_recorded": (direct or {}).get("head"), "kernel_dirty_aisef_recorded": (direct or {}).get("dirty_aisef"),
                       "candidate_kernel": start >= 50000 and birth > fix_ct, "attribution": attr})
    trees = {c["aisef_tree"] for c in commits if c["ct"] >= fix_ct}
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "candidate_aisef_tree": sorted(trees), "aisef_tree_identical_since_fix": len(trees) == 1,
           "kernel_variants": {"A (chunks 00000, 10000)": "NOT_AVAILABLE — bounded between 023d6ce/bb31522 and the following commit; re-run in full on the candidate",
                               "B (chunks 20000–40000)": f"{VARIANT_B} aisef tree", "C (chunks 50000–90000 + every re-run)": f"{FIX} aisef tree = the candidate"},
           "aisef_diff_A_upper_bound": {"summary": diff_a[-1] if diff_a else "", "files": [ln.split("|")[0].strip() for ln in diff_a[:-1]]},
           "aisef_diff_B_to_candidate": {"summary": diff_b[-1] if diff_b else "", "files": [ln.split("|")[0].strip() for ln in diff_b[:-1]],
                                         "semantics": "SS-64 only: the verifier budget cap precedes stage absence in _review_stage and the verify-only path; invariants.yaml is data"},
           "commits": commits, "chunks": chunks,
           "rule": "Old evidence must never silently satisfy new gates: every seed either has candidate-kernel evidence (chunks 50000–90000, the full re-run of "
                   "00000–19999, the targeted SS-64 re-run and the control sample) or rests on the measured B→candidate diff whose only changed path it does not exercise."}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in chunks:
        print(c["chunk"], c["log_birth"][11:19], "head", c["head_at_birth"], c["kernel_class"], "candidate" if c["candidate_kernel"] else "-")
    print("aisef tree identical since the fix:", out["aisef_tree_identical_since_fix"], out["candidate_aisef_tree"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
