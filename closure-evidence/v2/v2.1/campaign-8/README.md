# Campaign 8 — B-03 round 4c (the suite's encoding rule)

Why: the full-suite pre-run at `1043186` found two child-process calls that read text with no `encoding=`
(`tests/test_meta.py`, lesson 99) in two pinned kill files. The fix is one keyword in each call; the files are pinned by
sha256, so it is a manifest revision and a re-measurement of the targets that register them.

| step | where |
|---|---|
| T0 of the two changed pairs (both PASS), account | `t0-sweep/`, `../T0-SWEEP-8.json`, `../EXECUTION-ORDER-9.json` |
| manifest rev 8 (snapshot `5df323a`) | `../REQUALIFICATION-MANIFEST-8.json` |
| the 12 targets / 680 mutants measured: 673 KILLED, 7 SURVIVED (audited), 0 TIMEOUT/INFRA/NOT_RUN | `results/`, `../mutation-workers/c8-w*` |
| the other 516 stand: read-set at `c186cb2` (the commit carrying the regenerated derived records), three deltas, the exact reading, the scope | `read-set.json`, `delta-from-*`, `DATA-READ-ANALYSIS-from-*`, `SCOPE.json`, `tools/scope8.py` |

Every mutant of the 12 targets has the class it had in the previous measurement (0 differences). The seven survivors are
the audited ones (`_probe` 3, `_judge` 3, `measure` 1). Provisional results at `c186cb2`: 0 in each delta (the first
read-set was measured at `08b4ee0`, before three derived records that lie inside `mutation.COPY` were regenerated: those
files did not exist at that head and a measurement at a head cannot clear a file it does not hold; it was set aside and
measured again here).
