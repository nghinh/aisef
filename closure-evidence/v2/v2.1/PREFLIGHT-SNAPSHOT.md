# V2.1 supplementary campaign — preflight snapshot (owner decision 2026-10-28, approved 2026-10-29, step 1)

Machine-readable: [PREFLIGHT-SNAPSHOT.json](PREFLIGHT-SNAPSHOT.json).

## Pinned measurement commit
**`d043231e11b677b0c9a551c8d978f486315411fe`** — the merge of the two verified survivor kill tests (`50812da2`)
into the candidate `v2.1/probe-window`.

- **Product identity (proven):** `aisef2/` tree object SHA `5f34a3f32bb101e007db67922e694efdd9c7dcad`,
  **byte-identical** at `fce3d7b7` and `d043231e` (`git rev-parse fce3d7b7:aisef2 == d043231e:aisef2`). The only
  change vs `fce3d7b7` is one added test method in each of the two kill-test files.
- Edited kill tests (blob @merged vs @fce3d7b7): `test_v21_pm8_diagnostics.py` `6e92339f`/`854c1aac`;
  `test_v21_fa_grep_worker.py` `df1e0efb`/`8ce9467c`.

## Gates
| gate | result |
|---|---|
| `ruff` 0.16.4 | **CLEAN** |
| `test_meta` | 34 **OK** |
| `test_v21_pm8_diagnostics` (edited) | 65 **OK** |
| `test_v21_fa_grep_worker` (edited) | 43 **OK** |
| v1 evidence guard | **PASS** |
| full unit suite (`owned_run` → `unittest discover`) | **RED: 19 failures / 89 skipped / 7978 run / 4904 s**; provider calls escaped **0** |
| per-target **T0 rehearsal** (hermetic, clean worktree @ `d043231e`) | **PASS** (`run_story`, `StoryResult.revision`); 354 s; escaped **0** |

## The 19 suite failures — measured, not assumed
All 19 are **pre-existing record-currency / tree-binding meta-tests** on the unsealed closure branch
("committed record is current / binds this tree / ledgered / calibrated / conformance ruling"). Evidence:

- Their **test files are byte-unchanged since the campaign-9 snapshot `4ec961e`** — not caused by this merge
  (the merge touched only the two kill-test files + a report).
- `test_v21_conformance_ruling`'s own docstring: *"Red until the ruling is generated on the final 2.1 tree and
  committed (the lead's step)."* `test_checker_calibration` fails literally because `_attempt has no mutation
  result` — the 62-gap this campaign measures to close.
- They can go green **only by regenerating/sealing records — which the owner forbade this round**. So the suite is
  red *by design* on a pre-seal branch; forcing it green would be the reseal that is not permitted.

Modules: checker_calibration (4), destructive_authority (1), freeze_manifest (1), p5 invariants (2),
c2_delivery_experiment (2), c2_k_nowork_001 (1), c2_orchestration_conformance (2), c2_p5_acceptance (2),
p5_plan_v22_proposal (1), p9_reproduction (1), v21_conformance_ruling (1), v21_read_set (1).

## Why the red suite does **not** corrupt the measurement
Only **two** of the twelve failing modules are kill-test files (`test_c2_k_nowork_001.py`,
`test_c2_orchestration_conformance.py`), used by **3 of the 90** scoped targets (`StoryResult.revision`,
`_Held.__call__`, `_attempt`). The T0 rehearsal proves the mutation runner **auto-skips** the record-currency
tests in its hermetic environment (`k_nowork` ran 17 / skipped 4; `orch_conformance` ran 24 / skipped 4 — the
skipped ones are exactly the failing tests), so **T0 PASSes**. Eight already-measured-at-head targets use the
same two files with clean results. The other 87 targets' kill-sets contain none of the failing modules.

**Conclusion:** per-target T0 baselines are sound; the campaign measures validly. The 19 failures are recorded as
the known pre-seal open-closure state — not retried to green, not resealed. Limits held: no
push/tag/publish/release/paid-provider/`APPROVE.sh`/self-acceptance.
