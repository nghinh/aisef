# F5 disposition 1 — every v2.2.0 mutation entry at the W1a-1 head (static engine, no recorder)

Produced by `validation/v23/impact.py --classify --base da3ea33f3b695aaca73e87a704145a0193aced23 --head HEAD --json`
at head `5350f172` (engine fix pass; the later commits on this branch touch only `docs/v2.3/`, which is not a COPY
root, so the classification is unchanged for them). Run time 390.6 s on the pilot host. The full per-target table, with
the proof of each classification (state, component, reason, the inputs compared, entry sha256, platform derivation,
basis), is [`DISPOSITION.json`](DISPOSITION.json): 994 rows, one per entry.

## Disposition (owner categories)

| Owner category | F5 state · component | Targets | Mutants | Proof carried by each row |
|---|---|--:|--:|---|
| VERIFIED_REUSE | VERIFIED_REUSE | **0** | 0 | — |
| MUST_REMEASURE (to count at this head) | INVALIDATED · R1 | **667** | **17,322** | I7, I6, I1 (+I8 for 42), I3, I4, I5, I9 all compared equal first; then R1: "no observation of `<kill file>`; R1 cannot be excluded" (58 distinct kill files named) |
| UNRESOLVED | UNRESOLVED · I6 | **327** | **10,078** | runner-1 entries (P1 19, P2 32, P3 41, P4 68, P5 45, P6 78, C2-P10 39, C2-ORCH 5) carry no platform evidence |

* Basis of the 667: 625 `v2.2.0-accepted@da3ea33f…` and 42 via the pinned B1 reuse ruling (I8).
* Platform (I6, derived per entry): 461 posix/darwin, 63 posix/linux, 140 posix/unproven, 3 windows, 327 unknown.
* Calibration (Δ = ∅, head..head): 667 VERIFIED_REUSE / 17,322 and 327 UNRESOLVED (I6) / 10,078, labelled
  `calibration@…` — the engine does reuse when nothing changed, and never labels a calibration as v2.2.0 acceptance.

**What MUST_REMEASURE means here, honestly.** None of the 667 is shown to be *affected*. The delta since v2.2.0 under a
COPY root is 9 added evidence files under `closure-evidence/v2` (plus this increment's own new test file, additive for
I4), and no `.py` under `aisef2/`. R1 fires because no recorder exists yet, so no kill file has been observed not to
read that delta. INVALIDATED is the fail-closed answer to missing observation, not an impact proof.

## Cross-check against the pilot

[`../F5-PILOT-1/PILOT-1.json`](../F5-PILOT-1/PILOT-1.json): 12 targets / 233 mutants from this table (10 MUST_REMEASURE,
2 UNRESOLVED) were re-measured at `79e9b88f`. Result: identical mutant lists, kill sets, killed counts and survivor sets,
and 0 per-mutant class differences. For those 12 only, the delta changed no kill outcome. This supports R1 being
conservative; it does not move any other row.

## Cost, measured (pilot host, 1 worker)

Record timings × 0.93 (pilot ratio, 10 timed targets) + 38 s/target measured overhead:

| Scope | Targets | Mutants | Serial machine-hours |
|---|--:|--:|--:|
| All 667 MUST_REMEASURE | 667 | 17,322 | **288.5** (wall floor 33.5 h: `aisef2/app/run.py::execute` alone) |
| of which ≤ 10 s/mutant | 413 | 8,411 | 17.8 |
| of which the 20 most expensive | 20 | — | 166.8 |
| 327 UNRESOLVED | 327 | 10,078 | no timings in their records (two measured in the pilot: 0.6 s/mutant) |
| One unmutated observation run of every kill file of the 667 | 235 kill files | 0 | **0.62** (median T0 time; tracing overhead extra) |

## Irreducible scope

Not yet determinable, and no remeasurement is requested. With today's tooling the scope cannot shrink below 667 + 327:
the R1 static scan fires for every kill file (all 262 reach a call it cannot exclude, `os.readlink` in
`aisef2/app/adapters.py`), so without a complete
observation (`os_trace`, Linux) nothing is reusable whenever Δ ≠ ∅. The next W1 increment is the recorder: one
observed, unmutated run per kill file (≈ 0.6 h plus tracing overhead, Linux) decides which of the 667 truly read the
delta. Only the remainder, plus whatever the owner rules for the 327 (PLAT-1 or re-measure), is the irreducible
scope; its exact size and measured cost will be reported before any approval is asked.
