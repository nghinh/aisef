#!/usr/bin/env python3 -P
"""Step 2 (owner decision 2026-10-28): lock the coverage table over all 614 targets by SET OPERATIONS,
not by adding numbers. After the supplementary run at the merged head, the partition must be

    new_measure (scope)            = 62 MISSING  ∪  closure-affected-by-edits          = 90
    still-valid measured-at-head   = measured_at_final_head  \\  closure-affected        = 162
    still-valid reused             = reused_after_mechanical_proof  \\  closure-affected = 362
                                                                                   total = 614

These three must be pairwise disjoint and their union must equal V21_TARGETS exactly. Closure is the
import-graph of each target's kill-set, computed at the MERGED head (the two edits added no imports, so
membership is stable, but we compute at the real head to be exact). Read-only; writes COVERAGE-614-TABLE.*.

    python -P closure-evidence/v2/v2.1/tools/verify_coverage_614.py
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve()
V21 = HERE.parents[1]
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))
import mutation as m                                              # noqa: E402
from validation.qualification import s2_mutation_record as S2    # noqa: E402

MERGED_HEAD = "d043231e"   # fce3d7b7 (product) + the two kill-test edits (step 1 preflight merge)
EDITED = {"tests/v2/test_v21_pm8_diagnostics.py", "tests/v2/test_v21_fa_grep_worker.py"}

s = json.load(open(V21 / "MUTATION-SUMMARY.json"))
ALL = set(m.V21_TARGETS)                                          # the 614 targets, ground truth
M = set(s["classes"]["measured_at_final_head"])
R = set(s["classes"]["reused_after_mechanical_proof"])
Miss = set(s["MISSING_TARGETS"])

# invariant the record already asserts: M/R/Miss partition the 614
assert len(ALL) == 614, f"V21_TARGETS != 614: {len(ALL)}"
assert M | R | Miss == ALL, "M|R|Miss != all 614"
assert not (M & R) and not (M & Miss) and not (R & Miss), "M/R/Miss not disjoint"

# closure-affected: a target whose kill-set closure (at the merged head) contains an edited test file
cache, affected = {}, set()
for t, kills in m.V21_TARGETS.items():
    key = tuple(kills)
    if key not in cache:
        cache[key] = S2.closure(ROOT, MERGED_HEAD, key)
    if EDITED & cache[key]:
        affected.add(t)

scope = Miss | affected                 # measure once
new_valid = M - affected                # still-valid at-head measurements, reused
new_reused = R - affected               # still-valid mechanical-proof reuse

# --- the checks that matter: a genuine partition of the 614 ---
parts = {"new_measure": scope, "still_valid_measured": new_valid, "still_valid_reused": new_reused}
names = list(parts)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        inter = parts[names[i]] & parts[names[j]]
        assert not inter, f"OVERLAP {names[i]} & {names[j]}: {sorted(inter)[:5]}"
union = scope | new_valid | new_reused
assert union == ALL, f"partition misses {len(ALL - union)} / extra {len(union - ALL)}"

doc = {
 "merged_head": MERGED_HEAD,
 "total_targets": len(ALL),
 "partition": {
   "new_measure_scope":      {"n": len(scope),      "why": "62 MISSING ∪ closure-affected by the 2 edits"},
   "still_valid_measured":   {"n": len(new_valid),  "why": "measured_at_final_head minus closure-affected"},
   "still_valid_reused":     {"n": len(new_reused), "why": "reused_after_mechanical_proof minus closure-affected"},
 },
 "sum_check": len(scope) + len(new_valid) + len(new_reused),
 "set_checks": {"pairwise_disjoint": True, "union_equals_V21_TARGETS": True},
 "affected_breakdown": {
   "affected_total": len(affected),
   "affected_in_measured": len(affected & M),   # become stale -> re-measured
   "affected_in_reused":   len(affected & R),   # were reusable -> re-measured
   "affected_in_missing":  len(affected & Miss) # already MISSING; counted once in scope
 },
 "expected_by_owner": {"still_valid_measured": 162, "still_valid_reused": 362, "new_measure": 90},
 "matches_owner_table": len(new_valid) == 162 and len(new_reused) == 362 and len(scope) == 90,
}
json.dump(doc, open(V21 / "COVERAGE-614-TABLE.json", "w"), indent=1, ensure_ascii=False)

print("=== 614 coverage partition (set-verified at merged head %s) ===" % MERGED_HEAD)
print(f"  new_measure (scope)          {len(scope):4}")
print(f"  still-valid measured-at-head {len(new_valid):4}")
print(f"  still-valid reused           {len(new_reused):4}")
print(f"  {'-'*34}")
print(f"  sum                          {len(scope)+len(new_valid)+len(new_reused):4}  (|V21_TARGETS| = {len(ALL)})")
print("  pairwise disjoint: True   union == all 614: True")
print(f"  affected: {len(affected)} = {len(affected&M)} ex-measured + {len(affected&R)} ex-reused + {len(affected&Miss)} already-MISSING")
print(f"  matches owner's 162/362/90 table: {doc['matches_owner_table']}")
print("wrote COVERAGE-614-TABLE.json")
