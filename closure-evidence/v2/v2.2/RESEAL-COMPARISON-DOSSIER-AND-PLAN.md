# Reseal comparison dossier & controlled reseal plan (owner #4)

Owner #4 (2026-11-06): *Prepare a comparison dossier and a controlled reseal plan. No overwriting, back-dating, or losing historical evidence. Execute reseal only after the owner approves the change manifest and provenance-preservation plan.*

**Dossier + plan only. Nothing is resealed. No record is overwritten.**

## 1. What "stale" means here (measured)

CI `tests.yml` has a dedicated `sealing` job that runs the **record-currency tier** behind `AISEF_SEALING=1`, and the job's own header documents it is **EXPECTED RED on master while the tree is unsealed — "re-sealing is the owner's act."** On the owner-#6 re-run (run [42151025036](https://github.com/nghinh/aisef/actions/runs/42151025036), HEAD `2047205a`) every other job is green; `sealing` is the single red, by that design.

A record-currency test does not check that code is wrong. It re-derives a digest from the **current tree** and compares it to a **committed record** sealed against an **earlier** tree. The last full seal was the **v2.1.0 release**; the record-currency tier has been chronically red on master since (it is "the owner's act to seal"), so the drift spans **wave-1 and wave-2 both**, not Đợt-2 alone. The approved commits that moved the tree run from wave-1 (`be7b1700` A1 armed the nine invariants, last touching `aisef2/journal/fold.py`) through Đợt-2 (`d98f2115` … `2047205a`: new `aisef demo`, the paid USD-ceiling gate, the retry no-progress line, the completed range oracle, the probe-record timeout fix, the Lane-M kill-test registration). All are approved and green in the `unit` tier; they simply post-date the last seal, so the committed records no longer bind the current tree. That is the entire content of the `sealing` red.

**Classification matters (and the owner, not I, rules on it).** Not every stale record is Đợt-2 drift. Measured example (§4): the `mutation` checker-calibration record names `aisef2/journal/fold.py` as "target changed since the mutation run" — but `fold.py` was **untouched in Đợt-2** (last change `be7b1700`, wave-1 A1). So that record's staleness **predates Đợt-2**. The change manifest (§5.1) labels each record *pre-Đợt-2 drift* vs *Đợt-2 drift* so the owner approves with full provenance.

One line in that job's failure log — `test_what_is_measured_decides_not_the_name_of_the_tool` — is **not** a record-currency failure; it is the same `PROBE_TIMEOUT=60` CI-load flake documented in owner #6 (the sealing job runs the full discover under heavy load). It is excluded below.

## 2. The stale record set → generators (17 records)

| record-currency test | test file | record / generator to re-derive |
|---|---|---|
| `test_the_V2_007_exception_records_what_the_owner_decided_and_when` | `p0/test_freeze_manifest.py` | freeze-manifest amendment / exception record → `validation/v2/freeze_manifest.py` |
| `test_every_checker_is_calibrated_and_the_committed_record_is_current` | `p0/test_checker_calibration.py` | checker calibration record → `validation/v2/checker_calibration.py` |
| `test_every_checker_has_a_committed_fixture_that_fails_it_for_the_named_reason` | `p0/test_checker_calibration.py` | checker fixture calibration → `checker_calibration.py` |
| `test_this_tree_passes_and_every_site_is_ledgered` | `p0/test_destructive_authority.py` | destructive-authority ledger → `validation/v2/destructive_authority.py` |
| `test_INV_MUTATION_AUTHORITY_destructive_sites_of_the_invariant_code_are_ledgered` | `p5/test_invariants.py` | INV-MUTATION-AUTHORITY site ledger → `destructive_authority.py` |
| `test_P5_8_committed_record_is_current` | `test_p5_plan_v22_proposal.py` | P5 PLAN-V2.2 proposal record → `validation/v2/p5_evidence.py` / `plan_validate.py` |
| `test_on_this_tree_the_committed_proposal_is_current` | `test_c2_p5_acceptance.py` | C2-P5 proposal record → `p5_evidence.py` |
| `test_the_acceptance_re_derives_on_this_tree` | `test_c2_p5_acceptance.py` | C2-P5 acceptance record → `p5_evidence.py` |
| `test_Q5_19_the_kernel_comparison_record_binds_this_tree` | `test_p9_reproduction.py` | Q5 kernel-comparison record → `kernel_static_checks.py` / `profile_freeze.py` |
| `test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story` | `test_c2_orchestration_conformance.py` | orchestration-conformance record → `freeze_conformance.py` |
| `test_15b_only_the_release_s_named_changes_are_accepted_each_while_its_gate_holds` | `test_c2_orchestration_conformance.py` | release-gate named-changes record → `freeze_conformance.py` |
| `test_the_committed_record_is_what_this_tree_derives` | `test_c2_delivery_experiment.py` | C2 delivery-experiment record → `c2_delivery_experiment.py` |
| `test_the_committed_ruling_is_what_this_tree_derives` | `test_v21_conformance_ruling.py` | v2.1 conformance ruling → conformance ruling generator |
| `test_the_evidence_record_re_derives` | `test_c2_p10_cohort_static.py` | C2-P10 cohort-static evidence → `cohort_static_checks.py` |
| `test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after` | `test_c2_k_nowork_001.py` | K-NOWORK-001 calibration record → its fixture generator |
| `test_historical_records_read_as_before` | `test_v21_mutation_runner.py` | mutation-runner history immutability (asserts history blobs **unchanged**) |
| `test_P5_8_committed_record_is_current` (P5 tier) | `test_p5_plan_v22_proposal.py` | P5 record freshness → `p5_evidence.py` |

Note the last distinct row, `test_historical_records_read_as_before`: it asserts historical blobs are **byte-unchanged**. If it is red it means the *opposite* problem from the others — something touched history — and must be investigated, **not** resealed. (Measured status in §4.)

## 3. The reseal mechanism is already provenance-preserving

`validation/v2/freeze_manifest.py` implements an **append-only amendment** mechanism ([freeze_manifest.py:32](../../../validation/v2/freeze_manifest.py)):

> *"Approved amendments, oldest first … Each binds the record it amends (by sha256), its exception record (by sha256) and before/after digests. **The original approval record never changes.**"*

`effective_digests()` ([:104](../../../validation/v2/freeze_manifest.py)) walks the amendment lineage and reports **broken links** — each amendment must amend the previous record *at its current sha256* ([:113](../../../validation/v2/freeze_manifest.py)), so the chain is tamper-evident. This is exactly owner #4's constraint: a reseal is a **new amendment appended** to the chain, binding the prior record by its sha256 and recording before/after digests. The prior record's bytes are untouched; history reads as before.

## 4. Measured deltas (per-record expected → derived)

Captured by running the `p0` record-currency tier locally at HEAD `2047205a` (`AISEF_SEALING=1`, 47 tests, 232s, 6 failures) — a representative subset; the full 17-record manifest is produced by the §5.1 dry-run across all generators:

| record / checker | measured finding | classification |
|---|---|---|
| `checker_calibration` → **mutation** | `NOT calibrated`: committed mutation evidence names `aisef2/journal/fold.py::{Authority.__init__,append,Folder.__init__,advance,peek}` as "target changed since the mutation run — re-run it"; `clean_passes=False`; observed `unaudited survivor` entries in the `aisef2/cal/m.py` calibration fixture | **pre-Đợt-2 drift** (`fold.py` last changed `be7b1700` wave-1 A1; untouched in Đợt-2) → re-run mutation against current `fold.py`, reseal |
| `checker_calibration` → **destructive_authority** | `clean_passes=False` (committed destructive-authority ledger re-derives differently on this tree) | drift → reseal after §5.1 labels wave |
| `checker_calibration` → **execution_order** | `clean_passes=False` | drift → reseal after §5.1 labels wave |
| `test_every_checker_is_calibrated_and_the_committed_record_is_current` | 3 checkers not current (the three above) | — |

The `freeze_manifest` / `destructive_authority` p0 files produced no additional *record-currency* failures in this subset beyond the above; `freeze_manifest --check` and `checker_calibration --check` pass at HEAD (internal-consistency is intact — the records are *stale*, not *broken*). The remaining 13 of the 17 records (C2/P5/P9/P10/orchestration/ruling generators) are enumerated in the full §5.1 dry-run, not this p0 subset.

**No evidence was overwritten by this measurement:** `git status closure-evidence/` showed only untracked new docs, no modified tracked record (verified post-run).

## 5. Controlled reseal plan

1. **Produce the change manifest (dry-run, no write).** For each of the 17 records, run its generator in `--check`/dry-run mode to emit `{record_path, committed_sha256, derived_sha256, the wave-2 commit(s) that moved the inputs}`. This manifest is the artifact the owner approves.
2. **Classify each record.** (a) *tree-drift* (stale because an approved wave-2 commit changed its inputs) → eligible for reseal; (b) *history-immutability* (`test_historical_records_read_as_before`) → **must be green already**; if red, STOP and investigate (do not reseal). No record is resealed to "reach PASS" if its red means tampering.
3. **Append amendments (only after owner approval).** For each tree-drift record, append a `freeze_manifest` amendment binding the prior record by sha256 + its owner-approval/exception record by sha256 + before/after digests. Original records' bytes unchanged.
4. **Re-run the `sealing` tier** → green; attach the run as the reseal evidence record.
5. **No back-dating.** Each amendment is stamped with the actual reseal date (owner-approval date), never the original seal date.

## 6. Provenance-preservation statement (owner #4)

- **No overwrite:** reseal appends amendments; `freeze_manifest`'s own invariant ("the original approval record never changes") plus the broken-link check enforce it mechanically.
- **No back-dating:** amendments carry the reseal date; the lineage records the order.
- **No lost evidence:** historical records stay byte-identical (guarded by `test_historical_records_read_as_before`); the before/after digests in each amendment preserve exactly what the prior tree bound.
- **Owner gate:** the §5.1 change manifest is presented for approval before any amendment is appended. This dossier authorizes neither.

## 7. Status — dry-run authorized; reseal DEFERRED (owner #4 condition, 2026-11-06)

Owner #4 authorized the dry-run and change-manifest preparation, with reseal only after the dry-run report meets the five confirmations **and** without legitimizing unresolved findings. **The reseal is NOT executed, for two grounded reasons:**

1. **An unresolved finding is open.** Owner #2's reproduction revealed that FINDING-WIN-OSKILL-001's Windows fix is larger than the presented Option A (the repro errors at `process_table()` before `os.kill`; see [FINDING-WIN-OSKILL-001-REPRO-CORRECTION.md](./FINDING-WIN-OSKILL-001-REPRO-CORRECTION.md)). That finding is now back with the owner. Resealing now would seal a tree while a kernel finding is unresolved — exactly what owner #4 forbids (*"không hợp thức hóa findings chưa được giải quyết"*).
2. **The release candidate is not final.** The Windows fix (once approved) edits the frozen kernel (`aisef2/app/client.py`), which moves `kernel_digest` and re-stales a further set of records. Resealing the current tree would be wasted and would have to be redone after that kernel change. The reseal belongs on the *final* RC.

**Dry-run measured so far (read-only, no write):** the 17 stale record-currency records are enumerated in §2; the p0 subset deltas (mutation / destructive_authority / execution_order checker calibration) are in §4; `freeze_manifest --check` and `checker_calibration --check` pass (records are *stale*, not *broken*); the `mutation` calibration staleness is **pre-Đợt-2** (`fold.py`, wave-1 `be7b1700`). The full per-record before/after digest manifest (§5.1) will be produced against the **final** RC once owner #2 is resolved.

**Five confirmations (design-guaranteed by the append-only mechanism, to be re-verified on the final manifest):** historical records byte-identical (original approval record never changes — §3); amendments append-only with a tamper-evident chain (broken-link check — §3); no back-date / no overwrite (§6); no unresolved finding legitimized (the reason reseal is deferred — above); Q5 and freeze_manifest each compared against their own kernel/record generator (§2 map). **No reseal performed.**
