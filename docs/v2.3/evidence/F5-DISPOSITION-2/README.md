# F5 disposition 2 — final W1a-1 engine (supersedes disposition 1)

Produced by `validation/v23/impact.py --classify --base da3ea33f3b695aaca73e87a704145a0193aced23 --head HEAD --json`
at head `63a957a4`, the engine after the final fail-closed pass (Amendment A1 withdrawn: R5–R8 judge Δ ∩ S(F) again,
as the frozen §2.9 letter says). The per-target table with each row's proof is [`DISPOSITION.json`](DISPOSITION.json)
(994 rows). [Disposition 1](../F5-DISPOSITION-1/README.md) is kept unchanged as history. It was produced by the engine
with A1, which a re-review showed to be unsound; its counts are the same, only its component differs.

| Owner category | F5 state · component | Targets | Mutants |
|---|---|--:|--:|
| VERIFIED_REUSE | VERIFIED_REUSE | **0** | 0 |
| MUST_REMEASURE (to count at this head) | INVALIDATED · R6 | **667** | **17,322** |
| UNRESOLVED | UNRESOLVED · I6 | **327** | **10,078** |

* **Why R6 now, not R1.** This increment adds `tests/v2/test_v23_impact.py`. Every kill file reaches
  `aisef2/invariants/registry.py`, whose `tests/v2` literal puts every `tests/v2` file into every S(F). A new file is a
  change of import-time statements, so frozen R6 fires for all 667 before R1 is consulted. R1 (no observation) would
  fire for them as well. Neither is an impact proof: the pilot measured 10 of these 667 (plus 2 of the 327) with 0
  outcome differences ([pilot](../F5-PILOT-1/PILOT-1.json)).
* **Precision cost of the frozen letter.** Today, any new or changed file under `tests/v2` re-opens every target that
  passes I6. This is the measured face of EVID-COUPLING-01 / KERNEL-COUPLING-01 at the test-directory level. A sound
  narrowing needs the recorder's observation of what each kill file actually loads, not a static exception.
* Acceptance labels: no non-reuse row carries an acceptance basis. Every row names the run's base in
  `evidence.run_base` (994/994). The calibration run (head..head) gives 667 VERIFIED_REUSE labelled `calibration@…` and
  327 UNRESOLVED (I6).
* Platform (I6): 461 posix/darwin, 63 posix/linux, 140 posix/unproven, 3 windows, 327 unknown.
* Costs and the irreducible-scope analysis in disposition 1 still hold: the same 667 and 327 targets.
  * Remeasuring the 667 costs 288.5 serial machine-hours; one observation run of their 235 kill files costs 0.62 h.
  * No remeasurement is requested before the recorder exists.
