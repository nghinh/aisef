# V2.1 — coverage table over all 614 targets, set-verified (owner decision 2026-10-28, step 2)

**Merged measurement head:** `d043231e` (product tree `aisef2/` object SHA `5f34a3f3…`, byte-identical to
`fce3d7b7`; the two kill-test edits are the only change). Verified by
[tools/verify_coverage_614.py](tools/verify_coverage_614.py) → [COVERAGE-614-TABLE.json](COVERAGE-614-TABLE.json).

The table below is checked **by set operations, not by adding numbers**: the three parts are pairwise disjoint
and their union equals `V21_TARGETS` exactly.

| part | n | definition (set) |
|---|---:|---|
| new_measure (scope) | **90** | `MISSING(62) ∪ closure_affected_by_edits` |
| still-valid measured-at-head | **162** | `measured_at_final_head(180) \ closure_affected` |
| still-valid reused | **362** | `reused_after_mechanical_proof(372) \ closure_affected` |
| **total** | **614** | `= \|V21_TARGETS\|` |

```
pairwise disjoint : True
union == all 614  : True
sum               : 90 + 162 + 362 = 614
```

**Why 180→162 and 372→362.** The 36 targets whose kill-test closure now contains an edited test file
(`closure_affected`) split as **18 ex-measured-at-head + 10 ex-reused + 8 already-MISSING**. Editing a kill
test makes any prior measurement that used it stale, so the 18 drop out of measured-at-head and the 10 out of
reuse; both are folded into the 90-target scope (the 8 were already MISSING, counted once). After the
supplementary run: `180 − 18 = 162` at-head measurements stay valid, `372 − 10 = 362` reuse stays valid, and
the `90` are re-measured — a clean partition of the 614.

**Ground invariant** (already asserted by the record and re-checked here): `measured_at_final_head (180)`,
`reused_after_mechanical_proof (372)` and `MISSING (62)` are themselves pairwise disjoint and their union is the
614. No proof was loosened, no `measured_on` changed, no valid result re-run — the partition is derived purely
from the frozen `proof()` classes and the import-graph closure at the merged head.
