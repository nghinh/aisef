#!/usr/bin/env python3 -P
"""Step 5 (owner decision 2026-10-28): the single supplementary measurement scope at the merged head
(fce3d7b7 + the two kill-test edits). Union of (A) the 62 MISSING and (B) every target whose kill-test
CLOSURE includes an edited test file. Counted once. Read-only; mutant counts from the scope manifest;
duration from measured throughput. Regenerates SUPPLEMENTARY-SCOPE.json.

    python -P closure-evidence/v2/v2.1/tools/supplementary_scope.py
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve()
V21 = HERE.parents[1]                      # closure-evidence/v2/v2.1
ROOT = HERE.parents[4]                      # repo root
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))
import mutation as m                        # noqa: E402
from validation.qualification import s2_mutation_record as S2  # noqa: E402

HEAD = "fce3d7b7"
EDITED = {"tests/v2/test_v21_pm8_diagnostics.py", "tests/v2/test_v21_fa_grep_worker.py"}
s = json.load(open(V21 / "MUTATION-SUMMARY.json"))
miss = set(s["MISSING_TARGETS"])
maf = set(s["classes"]["measured_at_final_head"])
reuse = set(s["classes"]["reused_after_mechanical_proof"])
mutants = {t: v["mutants"] for t, v in json.load(open(V21 / "REQUALIFICATION-MANIFEST-9.json"))["mutation"]["targets"].items()}

cache, affected = {}, set()
for t, kills in m.V21_TARGETS.items():
    key = tuple(kills)
    if key not in cache:
        cache[key] = S2.closure(ROOT, HEAD, key)
    if EDITED & cache[key]:
        affected.add(t)

scope = miss | affected
def msum(ts): return sum(mutants.get(t, 0) for t in ts)
tot = msum(scope)
doc = {
 "merged_head": "fce3d7b7 + 2 kill-test edits (tests/v2/test_v21_pm8_diagnostics.py, test_v21_fa_grep_worker.py)",
 "scope_targets": len(scope), "scope_mutants_estimate": tot,
 "groups": {
   "missing_62": {"targets": len(miss), "mutants": msum(miss)},
   "closure_affected_by_edits": {"targets": len(affected), "mutants": msum(affected),
      "previously_reuse": {"targets": len(affected & reuse), "mutants": msum(affected & reuse)},
      "previously_measured_at_head": {"targets": len(affected & maf), "mutants": msum(affected & maf)}},
   "union": {"missing_only": {"targets": len(miss - affected), "mutants": msum(miss - affected)},
             "missing_and_affected": {"targets": len(miss & affected), "mutants": msum(miss & affected)},
             "affected_only": {"targets": len(affected - miss), "mutants": msum(affected - miss)}},
 },
 "edited_file_reach": {f: sum(1 for k in cache.values() if f in k) for f in sorted(EDITED)},
 "duration_estimate_2workers_mutation_compute_only": {
   "fast_88_per_h_days": round(tot / 88 / 24, 1), "giant_63_per_h_days": round(tot / 63 / 24, 1),
   "worst_40_per_h_days": round(tot / 40 / 24, 1)},
 "targets": sorted(scope),
 "mutant_counts_source": "REQUALIFICATION-MANIFEST-9 (estimate; generator at head may shift a few)",
 "duration_note": "mutation-compute wall time only, 2 workers; excludes survivor audit + suites",
}
json.dump(doc, open(V21 / "SUPPLEMENTARY-SCOPE.json", "w"), indent=1, ensure_ascii=False)
print(f"scope: {len(scope)} targets / {tot} mutants  (62 MISSING + {len(affected)} closure-affected)")
print("wrote SUPPLEMENTARY-SCOPE.json")
