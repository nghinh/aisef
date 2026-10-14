# Round 4 — what was derived, in what order, and what each tool said

Everything below was written on a **committed** tree by its own tool, once; none was written to make a test green.

| step | commit (tree it was written on) | outcome |
|---|---|---|
| encoding rule: two child-process calls | `3efb56b` | `tests/test_meta.py` green; both kill files pass |
| T0 of the two pairs, order table | `5df323a` (`T0-SWEEP-8`, `EXECUTION-ORDER-9`) | both PASS |
| manifest rev 8 | `08b4ee0` (snapshot `5df323a`) | `--check` PASS |
| campaign 8 | results `d992268` | 12 targets / 680 mutants: 673 KILLED, 7 SURVIVED (audited), 0 TIMEOUT/INFRA/NOT_RUN; 0 differences from the previous result |
| V2.1 mutation record | `42e0305`, written at FINAL_HEAD `8043387` | 528 targets, 13,581 mutants, 13,388 KILLED, 193 SURVIVED (136 AUDITED + 57 EQUIVALENT, 0 unaudited), `MUTATION_VERDICT` **PASS**; `--check` PASS at `725226f` and again at `c186cb2` |
| Q0 checker calibration | `79cf437` | 54/54 checkers calibrated, always-PASS mutants rejected 54/54 (the mutation checker ran on the real record) |
| C2-P5 acceptance re-verification | `c186cb2` | "C2-P5 ACCEPTANCE BOUNDARY RE-VERIFIED ON 2.1 — NO NEW OWNER ACCEPTANCE" |
| K-NOWORK-001 rehearsal | `c186cb2` | REPRODUCED AND CORRECTED (703 s) |
| Q5 kernel comparison | `c186cb2` | 6 identical, 5 identity-only, 3 differ (engineering measurement, not owner-approved evidence) |
| conformance ruling | `c186cb2` | 12 rows |
| basis of the 516 results that stand | `45554e0` | read-set at `c186cb2` (166 kill files), three deltas `--check` PASS, 0 provisional, scope = the 12 measured |
| full suite | `45554e0` | [SUITE.md](SUITE.md): 7305 tests OK, 85 skipped |

The first read-set of this campaign was measured at `08b4ee0`, before the three derived records that lie inside
`mutation.COPY` were regenerated: a file that does not exist at the head cannot be cleared by a measurement at that
head (the delta kept 522 results provisional). It was set aside and measured again at `c186cb2`; the tables here are
those.
