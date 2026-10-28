# V2.1 MISSING-62 reconciliation at fce3d7b7 — owner decision 2026-10-28 (step 2)

**Accounting (614):** 180 measured_at_final_head + 372 reuse + 62 MISSING. Verdict **FAIL**.

## Handling of the 62 MISSING (by frozen proof()'s own reasons)

- **46 REMEASURE-TESTS**
- **16 REMEASURE-PRODUCT**

  - REMEASURE-TESTS: module byte-identical at head; kill-test closure changed (owed kill tests, fd1a1658).
  - REMEASURE-PRODUCT: product module changed vs every available measurement.

## Resume-slice reconciliation

- mw0+mw1 measured **199** targets at head → 180 kept at-head, 19 superseded by cleaner reuse, 0 missing.
- MISSING inside slice: **0**; outside slice: **62**.

## Why 180+372+62 ≠ the Oct-20 262/352 plan

- The 262 re-measure / 352 reuse split (memory aisef-trang-thai-2026-10-20) was a PLAN from the read-set/delta tool (validation/qualification/v21_snapshot_delta.py --read-set): a target whose changed module bytes are not in the kill tests' MEASURED runtime read-set at head was ruled reuse-OK.
- This record is built by the FROZEN proof() of v21_mutation_record.py (criteria_sha256 9e6f9d39bee3b765), which is STATIC and FILE-level: any byte change to the module file or to a kill-test closure file disqualifies reuse. It does not consult the runtime read-set. The two gates are different frozen criteria and classify ~20 targets differently in each direction (reuse 352->372, remeasure 262->242).
- Under proof() at fce3d7b7: 614 = 372 reusable + 242 must-measure-at-head (= 180 measured_at_final_head + 62 MISSING). The must-measure set is 242, not 262.
- Operationally dominant: the resume campaign completed a 199-target slice of the must-measure set (disk blocker cut it from 4 workers to 2; see memory 2026-10-21). 180 of the 199 are kept at head; the 62 MISSING are the must-measure targets the slice did not cover.
- The owner's premise 'product snapshot did not change' holds for 46 of the 62 (module byte-identical at head; only the kill-test closure changed — the owed kill tests in commit fd1a1658, added AFTER the campaign snapshot). It does NOT hold for 16: their product module changed between the frozen snapshot and head (fd1a1658 PL-7 teardown hardening; fce3d7b7 calibration re-derivation).

## By module

- 10  `aisef2/app/run.py`
- 7  `aisef2/app/client.py`
- 7  `aisef2/app/lineage.py`
- 6  `aisef2/app/bundle_cli.py`
- 6  `aisef2/runtime/process_range.py`
- 5  `aisef2/app/adapters.py`
- 3  `aisef2/app/bundle.py`
- 3  `aisef2/orchestrate/story_runner.py`
- 2  `aisef2/app/cli.py`
- 2  `aisef2/app/diagnostics.py`
- 2  `aisef2/app/review_ocr.py`
- 2  `aisef2/app/review_verify.py`
- 2  `aisef2/probe/catalog.py`
- 2  `aisef2/probe/cli_invocation.py`
- 1  `aisef2/app/settings.py`
- 1  `aisef2/app/usage.py`
- 1  `aisef2/app/verify.py`

## Kill-test files implicated (file → #MISSING targets whose best result they block)

- 27  `tests/v2/test_v21_continue_usage.py`
- 8  `tests/v2/test_v21_pm8_diagnostics.py`
- 5  `tests/v2/test_v21_ocr_declared.py`
- 5  `tests/v2/test_v21_continue_integrity.py`
- 4  `tests/v2/ledgerlock_candidate.py`
- 4  `tests/v2/test_v21_identity.py`
- 4  `tests/v2/test_v21_review.py`
- 4  `tests/v2/test_v21_review_chain.py`
- 4  `tests/v2/test_v21_migrate_semantics.py`
- 4  `tests/v2/test_v21_x_lineage_proof.py`
- 3  `tests/v2/test_v21_r5_review_deep_input.py`
- 3  `tests/v2/test_v21_bundle_tools.py`
- 3  `tests/v2/test_v21_ocr_identity.py`
- 3  `tests/v2/test_v21_pw_lineage_unread.py`
- 2  `tests/v2/test_s2_kills.py`
- 2  `tests/v2/test_v21_r5_regex_isolation.py`
- 1  `tests/v2/test_v21_pw_lineage_continue.py`
- 1  `tests/v2/test_s2_kills_deterministic.py`
- 1  `tests/v2/test_v21_x_lineage_gone.py`
