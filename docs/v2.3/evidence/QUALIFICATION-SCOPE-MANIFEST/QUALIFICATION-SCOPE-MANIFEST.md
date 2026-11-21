# AISEF v2.3 — frozen qualification-scope manifest

**Status.** Read-only analysis. It is frozen by its digest (below) and **binds nothing until the owner commits it**. No mutant
ran and no target was measured or reused. The only execution was one T0 run (unmutated) of each of the 35 kill files of
the 327 runner-1 targets, used as a cost input (`scripts/t0_legacy.py`, env guard on, 190 s in all).
That run qualifies nothing.

* Pin: `release/v2.3-big` @ `1e25ef84`. Basis: v2.2.0 = `da3ea33f`.
* `validation/v2/mutation.py`: LF sha256 `07812c4fdf23…`, unchanged since v2.2.0: True.
* Every record in `mutation.RECORDS` is blob-identical between v2.2.0 and the pin. The generator asserts this.
* F5 state per row comes from two sources:
  * disposition 2 (`docs/v2.3/evidence/F5-DISPOSITION-2/DISPOSITION.json`, sha256 `ef3418095d83…`, engine head `63a957a4`);
  * the recorder-track engine run (`75080a80`, no observations, sha256 `8fcb97603084…`).
* For all 994 entries, `entry_sha256` was recomputed as sha256(canonical(entry)) and equals both dispositions.
* Rows are in `SCOPE-MANIFEST.json`: 994 registry rows, 40 MEASURE_NEW rows, 26 EDITED_NO_V220_TARGET rows and an inventory-only section.
* Generator: `scripts/manifest.py` (sha256 `03595bb702f5…`). This file is rendered from the JSON by `scripts/render_md.py`.

**Manifest digest:** `632c3ac459746db89cf0fd000a309b0c8cb26287acf231a4ac1aca0c5eccac61`. It is the sha256 of canonical JSON (sort_keys, separators `(',',':')`,
ensure_ascii=False, UTF-8) of the whole of `SCOPE-MANIFEST.json` without its `manifest_digest` field: basis, rules, owner decisions,
summary, rows, new rows, inventory and the checker-findings disposition. It supersedes the earlier `85450512…`, which covered only
rules, decisions and rows, and only in a projected form (finding RC-1). Verify from the JSON alone, in this folder:

```
python3 -P -c "import hashlib,json;d=json.load(open('SCOPE-MANIFEST.json',encoding='utf-8'));d.pop('manifest_digest');print(hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())"
```

Reproducibility (measured in the correction pass): widening the digest exposed one hash-seed-dependent list order (the tie order of
the per-wave top files), now sorted. Two regenerations with generator `03595bb702f5…` under `PYTHONHASHSEED=1` and `=2`
gave a byte-identical `SCOPE-MANIFEST.json`.

## 1. Frozen rules

* **FR1.** Every v2.2.0-enforced control (C-REG, C-CUR, C-NOAUDIT, C-HIST, C-B1M, C-B1B, C-OPTC, C-WIN, Q0 calibration of the checkers) stays mandatory at the final RC. Retiring, rebinding or relaxing any of them needs an explicit committed owner decision.
* **FR2.** No inventory is promoted: no superseded row, empty-phase record, record outside mutation.RECORDS, worker log, historical campaign or unbound field (kill-set names, kill-file content, closure, platform, ruling authenticity beyond is_file) is v2.3 evidence.
* **FR3.** Every target whose module any v2.3 lane owns for edit (DAG §4, W1-DESIGN §8, globs expanded at v2.2.0), or whose LF digest at the final RC differs from v2.2.0, is CHANGED_TRUST_CRITICAL: measured at the final RC, never reused. The set is monotone; an unplanned change adds to it, and only an owner decision removes a planned module that ended untouched. The digest clause is evaluated mechanically over every target module at the final RC; a row whose module a design option may edit without lane ownership carries planned_change_possible.
* **FR4.** New code is MEASURE_NEW, measured at the final RC: every design-declared target; every mutation._root with >= 1 site in a module created after v2.2.0 that OD-NEWMOD or OD-F5ENG brings into scope (an OD-NEWVAL module only if the owner extends scope); and the v2.3-added or changed authority roots of validation/v2/mutation.py (OD-F5ENG). An existing module that a lane edits and that has no v2.2.0 target is not a target by this rule: it has a row under OD-EDITNOTARGET with its v2.2.0 control and its cost if promoted. Roots not yet written are enumerated at their wave's design freeze.
* **FR5.** A REUSE_CANDIDATE is reused only by a proven F5 VERIFIED_REUSE at the final RC, produced by the engine version the owner authorized (pinned by digest in the final-RC record), with its proof committed; otherwise it is measured. UNRESOLVED is never accepted.
* **FR6.** Release evidence for each target is its final-RC measurement by the runner-2 classifier: genuine outcome, T0 PASS, NOT_RUN never PASS, every survivor audited at the measured digest in the append-only v2.3 audit file, except NO_AUDIT targets, which must be fully killed (C-NOAUDIT). posix targets on the host family SCALE-1 names; the 3 Windows-only targets natively (OD-WIN). Per-wave measurements (DAG §6, unless OD-WAVE replaces it) are wave-gate evidence and never enter the release claim.
* **FR7.** Every owner decision defaults to the trust-keeping choice until the owner commits another one.
* **FR8.** No 667-, 891-, 994-target or final-RC campaign runs without the owner's separate authorization (OD-RUN-FINAL). Until then the final-RC set is NOT_RUN and the release is blocked; nothing in this manifest is a measurement.

## 2. Registry inventory vs mandatory release qualification

At v2.2.0, **all 994 registry entries were mandatory**. C-REG (unit job) and C-CUR (`mutation.check()` → Q0 → GATED
`test_checker_calibration` → sealing job → `publish`) bind every one of them. So no registry entry is inventory-only.
Inventory-only rows are the ones **outside** the 994: 120 superseded or retired rows (2,149 mutants) in the checked
records, and 475 rows (11,049 mutants) of the 8 records whose phase has no live target. Gated tests read them
(C-HIST tests/v2/test_v21_mutation_runner.py:1689-1697; GATED tests/v2/sealing_gate.py:44 (asserts no runner key over every row, superseded ones included); GATED tests/v2/sealing_gate.py:35 reads the K-PRESAT-001/K-NOWORK-001 records through validation/qualification/c2_orchestration_repair.py (any difference excused while mutation.check() is clean, :713)), but they bind no per-target verdict.
223 further paths under `closure-evidence/` name "mutation" (any case, any extension) and are neither in `mutation.RECORDS` nor the
audit file, so `check()` reads none of them: draft or tool script 6, exception request 1, record, summary, manifest or note outside RECORDS 20, ruling 1, test-run transcript 10, worker log/history/record 185.
None of these is promoted (FR2).

| v2.2.0 control | targets | citation (computed, file:line at the pin) |
|---|---|---|
| C-REG + C-CUR (every entry) | 994 | tests/v2/p2/test_mutation_targets.py:32 (unit job, every OS: .github/workflows/tests.yml:9); validation/v2/mutation.py:2616-2624 -> validation/v2/mutation.py:2602-2613 -> validation/v2/mutation.py:2519-2565 (full chain per row in the JSON) |
| C-B1M + C-B1B (risk gate, seq 9) | 177 / 5,909 mutants | RELEASE-DECISIONS seq 9; B1-RISK-MANIFEST.json; checker_calibration `_b1_bindings` |
| C-OPTC (Option C reuse ruling) | 42 | mutation.py `verified_reuse_current`; seq 12 |
| C-WIN (native Windows) | 3 | STATUS MUTATION.WINDOWS_NATIVE; seq 10 |
| C-HIST (runner-1 rows read as before) | 327 | test_v21_mutation_runner `test_historical_records_read_as_before`, GATED |
| C-NOAUDIT | 1 | mutation.py `NO_AUDIT` |

### 2.1 Reconciliation (every count recomputed from primary sources)

| identity | targets | mutants | serial worker-h, point (band) |
|---|---|---|---|
| **registry** = `mutation.TARGETS` | 994 | 27,400 | — |
| = ACTIVE_HISTORICAL (runner-2, V2.1 record, timed) | 667 | 17,322 | 291.7 (154.3–405.7) |
| + LEGACY_UNPROVEN (runner-1, P1–P6/C2-ORCH/C2-P10, untimed) | 327 | 10,078 | 17.1 (4.8–75.7) [E] |
| = CHANGED_TRUST_CRITICAL (module owned by a lane) | 891 | 24,236 | 299.0 (157.6–458.2) |
| + REUSE_CANDIDATE | 103 | 3,164 | 9.8 (1.5–23.3) |
| MEASURE_NEW rows with code (all decisions) | 21 | 8,189 | 123.9 (2.2–173.1) [E] |
| MEASURE_NEW rows not yet written | 19 | unknown | UNDETERMINED |
| EDITED_NO_V220_TARGET modules, whole module, if promoted (OD-EDITNOTARGET; not in any default set) | 26 | 12,288 | 186.3 (3.3–260.2) [E] |

* **Legacy reconstruction status (the 327).** 0 are PROVEN. The strongest leads are: OT 49 (1,806 mutants), D1 4 (34 mutants), D2 2 (104 mutants), D3 272 (8,134 mutants).
  OT means an uncommitted out-of-tree launch script. D1–D3 are committed hints that do not bind the producing run. None of them is I6
  evidence under the current engine. Each row carries its grade, its intro commit and what the engine would conclude per acceptance mode.
* **Planned changes.** They were parsed from DAG §4 (40 lane rows, with the W1 rows of W1-DESIGN §8 and the W6
  cohort sentence). 70 of 86 target modules are owned for edit.
  * DAG W1 vs W1-DESIGN §8: the only difference is the integrator's `docs/v2.3/*.md`.
  * Tokens excluded: 6 (a hunk owned by another lane, the probe-commit-only workflow, and master-only README/docs).
  * The paragraph permits one file that no lane row owns, `validation/v2/v1_evidence_guard.py`. It is not a target module.
  * Target modules whose digest moved since v2.2.0, at the pin or on any of the 3 tracks: 0.
* **Agreement with the earlier scratch proposal.** v23 class agrees on 994/994 rows and
  planned waves agree on 994/994. That proposal was read only for this comparison.

### 2.2 Cross-tab: v23 class × history class × F5 state

| v23 class | history | F5 disposition 2 | F5 recorder track | targets | mutants |
|---|---|---|---|---|---|
| CHANGED_TRUST_CRITICAL | ACTIVE_HISTORICAL | INVALIDATED R6 | INVALIDATED R2 | 656 | 17,099 |
| CHANGED_TRUST_CRITICAL | LEGACY_UNPROVEN | UNRESOLVED I6 | UNRESOLVED I6 | 235 | 7,137 |
| REUSE_CANDIDATE | ACTIVE_HISTORICAL | INVALIDATED R6 | INVALIDATED R2 | 11 | 223 |
| REUSE_CANDIDATE | LEGACY_UNPROVEN | UNRESOLVED I6 | UNRESOLVED I6 | 92 | 2,941 |

No row is VERIFIED_REUSE under either engine.
* On the release branch, 667 rows are R6: the new `tests/v2/test_v23_impact.py` enters every S(F) through the `tests/v2`
  literal at `aisef2/invariants/registry.py:40`.
* On the recorder track, after the A2 move, the same 667 are R2S. `tests/v2/test_p9_reproduction.py` holds the constant `'closure-evidence/v2'`, and
  9 files were added under it since v2.2.0. **Against the v2.2.0 basis this is permanent**:
  those files stay in Δ, so no I6-passing target can become VERIFIED_REUSE against v2.2.0 unless R2S is narrowed (OD-R2S).
* The 327 are UNRESOLVED (I6) under both engines.

## 3. MINIMAL DEFENSIBLE MUST_REMEASURE set at the final RC (under the default owner decisions)

| part | targets | mutants | serial worker-h point (band) |
|---|---|---|---|
| Registry MUST: CHANGED_TRUST_CRITICAL | 891 | 24,236 | 299.0 (157.6–458.2) |
| Registry MUST: unchanged legacy (I6; OD-PLAT1 default re-measure) | 92 | 2,941 | 9.6 (1.3–22.9) |
| Registry MUST: unchanged B1 targets (OD-B1M default measure) | 4 | 76 | 0.1 (0.1–0.1) |
| Registry MUST: `require_armed` (design #32) | 1 | 13 | 0.0 (0.0–0.0) |
| **Registry MUST, total** | 988 | 27,266 | 308.7 (159.0–481.2) |
| Registry CONDITIONAL (F5 must prove reuse; expected: measured) | 6 | 134 | 0.1 (0.1–0.2) |
| MEASURE_NEW with code, in default scope | 17 | 892 | 13.3 (0.4–18.7) [E] |
| **Final-RC measure set (F5 reuses nothing: the expected case)** | **1011** | **28,292** | **322.2 (159.5–500.1)** |
| Program under **all** defaults: the final-RC pass + DAG §6 per-wave gates (OD-WAVE default) | — | — | 1363.1–3154.3 (point; module- to closure-level) |

* **Which headline.** 322.21 h is the final-RC pass. Under every default, OD-WAVE keeps DAG §6, so the per-wave gates
  (1040.9–2832.1 h point) are paid too: 1363.1–3154.3 serial-h in all.
  The final-RC-only figure holds only if the owner takes OD-WAVE. Per-wave runs never enter the release claim (FR6).
* **The point is one model point, not a value inside a bound.** It uses the aggregate pilot ratio; the band uses the per-target
  pilot extremes. Sensitivity of the point to the ratio: aggregate (the point) (0.9331): 322.2 h, K=8 40.3 h, floor 33.7 h; median of the 10 per-target ratios (0.7592): 273.3 h, K=8 34.2 h, floor 27.4 h; aggregate without the heaviest pilot target (0.7349): 266.5 h, K=8 33.3 h, floor 26.6 h.
* **Not calibrated for the final host.** Every timed cost comes from one darwin host at K=1. 63 linux-flavoured rows (119.3 h point)
  and the heavy tail (`execute` linux, `verify` linux, `continue_from` linux, `context_pack` linux) stay uncalibrated until SCALE-1 names the host.
  Host variance on record: `docs/v2.3/MUTATION-IMPACT-BASELINE.md:111 records run.py::execute from 5.83 h to 36.55 h across hosts`.

The table excludes 15 default-scope rows whose code is not yet written (new modules, and mutation.py's
v2.3 authority roots under OD-F5ENG); their roots are enumerated at each design freeze. It also excludes the E5 enum-swap mutants (≈ +156) that `_attempt` gains.

* **The conditional 6** are `_arms`, `_load_script`, `arm`, `register`, `resolve`, `test_directories` in `registry.py`, saving 0.14 h at most.
  Each has two independent reuse blockers. (1) `aisef2/orchestrate/story_runner.py` is in its S2 kill closure, and W1b E5 adds
  import and class statements (strict R6). (2) R2S holds against the v2.2.0 basis.
  **Expected reuse: 0.** Claiming it would also make the reuse engine a release-critical mutation target (OD-F5ENG):
  `impact.py` + `observe.py` hold 3,644 mutants at their newest bytes, and the recorder lane reports 350–400 s per run of their test file (not measured here). **So the
  trust-keeping and cheaper choice is to claim no reuse and measure the 6.** If every conditional row were reused, the
  set would be 1,007 targets / 31,802 mutants / 377.26 h point, engine targets included (finding RC-4).
* **Wall time.** The schedule is LPT (longest first), assuming independent workers at pilot-host speed:
  * Point: K=1 322.2 h; K=4 **80.6 h**; K=8 **40.3 h**.
  * Band: K=4 39.9–125.0 h, K=8 19.9–62.5 h.
  * The floor is the longest single target, `aisef2/app/run.py::execute`: 17.6 h low, 33.7 h point, 47.2 h high.
    A target cannot be split: K=9 35.8 h, K=10 33.7 h, K=12 33.7 h (point).
  * **K>1 needs a host that SCALE-1 has not named yet.** Each worker holds a pristine copy of `mutation.COPY` (1.53 GiB committed)
    and a full tree per target, and the old tree is removed only after the new copy: 3.06 GiB steady,
    4.59 GiB at the transient peak, with no disk guard in the runner (validation/v2/mutation.py:1847-1865; validation/v2/mutation.py:1889-1901; validation/v2/mutation.py:2692; no disk guard in validation/v2/mutation.py).
    Free space needed to keep the 20 GiB floor: K=1 24.6 GiB, K=4 38.4 GiB, K=8 56.7 GiB.
    The measured host had 24 GiB free, 16 GiB RAM and 8 logical CPUs:
    max K = 1 at steady state and 0 at the transient peak. So every K>1 wall above is conditional on a SCALE-1 host.
  * RAM per worker and worker contention at K>1 are **UNMEASURED**.
* **The heavy tail.** The 5 longest targets are `aisef2/app/run.py::execute` 33.7 h, `aisef2/app/verify.py::verify` 11.7 h, `aisef2/app/bundle_cli.py::continue_from` 10.7 h, `aisef2/app/feedback.py::context_pack` 10.2 h, `aisef2/orchestrate/story_runner.py::_attempt` 8.9 h.
* **Survivor audits (not in the hours).** Today there are 348 survivors on
  97 CHANGED targets and 22 on REUSE targets.
  557 positional audits exist, and none carries over a digest change (`audit_of`). The final-RC survivor
  count and the audit effort are UNDETERMINED.

### 3.1 Cost basis (how every number above is made)

* **Timed rows (667).** Point = v2.2.0 record seconds, scaled from F5-PILOT-1: test part × 0.9331, T0 part × 1.038,
  plus 38.1 s per target of pilot overhead. This is one model point.
  * The aggregate ratio is dominated by one target: `aisef2/app/review_ocr.py::OCR` holds 0.621 of the
    pilot's basis test seconds. Without it the ratio is 0.7349. The 10 per-target test ratios are
    0.489, 0.514, 0.617, 0.624, 0.725, 0.793, 0.93, 0.937, 1.054, 1.304; T0 ratios range 0.46–1.247.
  * Band (finding CC-1): the same model at the per-target extremes. Low = min test and T0 ratio + overhead per target. High = max test and
    T0 ratio + max(overhead per target, 1.96 s per mutant), or the record's own seconds + overhead_s if higher.
    It spans what the pilot measured on one host; it is not a bound for another host.
  * The V2.1 records themselves total 313.65 h. Their overhead is 11.0 h, against
    the 7.06 h this model allows.
* **Untimed runner-1 rows (327).** No row timings exist. Of their 35 kill files, 34 passed T0 when **measured here, once each**
  (Darwin 25.5.0 arm64, CPython 3.14.7).
  * Point = max(T0-calibration ratio 0.34 × mutants × ΣT0, 0.613 s × mutants) + T0 + overhead.
    The ratio is mutant-seconds over mutants × own ΣT0, fit on the 667 timed entries. The floor is the
    pilot's measured mutant-row rate on its 2 legacy targets (finding CC-6).
  * Low = calibration p10 (0.045), no floor.
  * High = mutants × (ΣT0 + 3 × max T0) + recorded timeouts × 900 s + T0 + per-mutant overhead. This bound holds for
    665/667 timed entries; the 2 exceptions are `process_range` targets.
  * Check against the 2 legacy targets the pilot re-measured: `attribute` measured 9.0 s, model 9.3 s, band 0.3–10.4 s; `reconstruct` measured 26.6 s, model 101.6 s, band 22.7–1068.0 s.
    **The band held for 2/2; the point was off by ×1.0–×3.8 per target.** The floor is the pilot rate on these same 2 targets, so this check no longer tests the point
    independently. The 327-row point is labelled [E], and the band is the honest figure.
  * Host check of measured vs v2.2 record median T0 on the 8 kill files that have both: test_budgets.py 0.85→0.52, test_interruption.py 3.28→2.57, test_process_range.py 18.48→17.58, test_run_scope.py 1.08→0.45, test_invariants.py 6.37→4.08, test_c2_orchestration_conformance.py 43.13→45.75, test_fold_oracle.py 19.45→9.51, test_p6_stages.py 7.86→8.37.
  * **Supersedes W1-DESIGN §10's legacy figure for this manifest.** W1-DESIGN.md:185 and :1154 price the 327 at [E] 16.2–182.5 serial-h
    from V2.1's generic per-mutant median and mean (5.8 / 65.2 s), with no measurement of their kill files. This manifest uses each kill
    file's measured T0 and a calibration fit on the 667 timed entries: 17.1 (4.8–75.7) h. W1-DESIGN is committed text and is not edited.
* **Rows without a usable kill set** (new rows without one, and the OD-T0COPY rows). They use a per-mutant rate band, which is not a bound:
  low = pilot runner-1 rate 0.89 s; point = pilot ratio × V2.1 **mean** mutant seconds 58.41 s
  (the mean is total / mutants, the expected per-mutant cost; the median 3.76 s under-states a sum: finding CC-5);
  high = max per-target pilot ratio × the mean. #33's rows use the T0 model on their declared kill files.
* **Mutant counts.**
  * Registry rows: the v2.2.0 records. Changed code will have other counts at the final RC.
  * New rows: `count_sites` (the same site rules as `mutation.mutants()`). It is asserted equal to `mutants()` on
    `obligation.py`, `static_admission.py` and `registry.py`, and on 7 large module versions (`scripts/verify_counts.py`).

### 3.2 Measured finding — 5 targets cannot be measured as registered (OD-T0COPY)

`tests/v2/test_no_dual_authority.py` fails T0 in the runner's tree: it loads `validation/qualification/release_inventory.py` at import,
and `validation/qualification` is not a `mutation.COPY` root. It is in the registered kill set of
`audit`, `check`, `compare`, `inventory`, `proofs` (`validation/v2/old_path_audit.py`, 497 mutants, runner-1).
Runner 2 refuses a target whose T0 row does not pass, so these cannot become MEASURED at the final RC until the runner tree is fixed
(an L1-F5 `mutation.py` hunk). The trust-keeping default fixes the tree. It does not drop the kill file and does not accept the v2.2.0 row.
Their cost uses the rate band.

## 4. What must be measured NOW versus at the final RC

* **CHANGED (891).** 860 have a planned module change in W1b or later. Measuring them now is
  overwritten by a later wave by construction.
  * The other 31 are W1a-only: the authority checkers `cleanup_authority`, `destructive_authority` and
    `except_boundaries`. FR3 still measures them at the final RC, so a measurement now does not enter the release claim either.
  * The cost of re-measuring per wave instead of once (DAG §6 as written, module-level estimate) is 1041 serial-h
    across W1a–W6. Under the S2 static closure, which counts every target whose kill closure holds a file the wave edits and no F5
    tiers, it is 2832 h. Compare about 322 h for one final-RC pass.
  * Check: the W1a S2-closure scope computed here (89 targets) equals W1-DESIGN §10's baseline (ii) (89 targets).
* **REUSE_CANDIDATE (103).** 96 have a planned-change file in
  the S2 kill closure or in the target module's own closure.
  * The remaining 7 are `aisef2/product/{compiler,outcome,spec}`. All are
    runner-1 (I6, measured anyway under OD-PLAT1). Their kill files are `tests/v2` modules, so their S(F) is expected (not measured:
    I6 fires first) to hold every `tests/v2` file through `registry.py`'s `TESTS_V2` literal, as it does for the other 667.
  * So any later `tests/v2` edit would re-open them. The plan has several in W1a: `sealing_gate.py`, `test_freeze_manifest.py`, additive
    test edits and new fixtures.
  * A measurement now is expected to be wasted for them as well.
* **E5 reach.** 651 targets / 18,308 mutants
  have `story_runner.py` in their S2 kill closure. This reproduces W1-DESIGN §10's "W1b E5 upper bound 651 / 18,308".

**Conclusion: measure nothing now for release qualification.**
* Do now (no campaign): decide OD-Q0-1-W1B before W1b; fix OD-T0COPY with the L1-F5 runner hunk; enumerate MEASURE_NEW roots at each
  design freeze; and keep new tests under `tests/v23` and new evidence under `docs/v2.3/evidence/` (A2), so that no further Δ enters
  every S(F).
* Per-wave measurements, if the owner keeps DAG §6 as written (the OD-WAVE default), are wave-gate evidence and not release evidence.

## 5. Levers

**Reduce cost without reducing the release claim's trust:**
1. Measure each target **once, at the final RC** (§4). The release claim is unchanged, because intermediate measurements of code that
   changes again carry no weight under FR3. *Cost of the lever:* a kill-power regression introduced in wave *w* is found only at the
   final RC, not at *w*'s exit. This changes the DAG §6 gate text, so it needs **OD-WAVE** (default: DAG as written). **Until the owner
   takes OD-WAVE this lever is not in effect**, and the program pays the per-wave gates on top of the final-RC pass
   (1363.1–3154.3 h point in all).
2. **Claim no reuse** (§3). Measuring the 6 conditional rows costs 0.14 h; qualifying the reuse
   engine as a release-critical target would cost far more. Under FR5 nothing is lost.
3. **Heavy tail first** (LPT) and K ≈ 8–9 workers, **on a SCALE-1 host with the free space of §3** (K=8 needs 56.7 GiB free;
   the measured host fits K=1 at steady state). This cuts wall time only, down to the 33.7 h point floor.
   The 3 Windows-only targets run natively in parallel (OD-WIN).
4. **Keep Δ out of every S(F).** New tests go under `tests/v23`, new evidence under `docs/v2.3/evidence/`, and kill files are not
   edited without need (`sealing_gate.py` re-opens 47 targets). This keeps per-wave and observation costs down. It cannot make
   CHANGED rows reusable (FR3).
5. Fix the runner tree once, before the run (OD-T0COPY), so the run is not stopped part-way.

**Would reduce trust (named, not taken):**
* Relaxing FR3 (OD-R3). Against v2.2.0 the saving is 0 anyway while R2S holds.
* Accepting the platform-unbound v2.2.0 currency of the legacy targets (OD-PLAT1 / tier D / I8).
* A DIGEST-READ discount.
* Narrowing R2S without an observation proof (OD-R2S).
* Treating F5 VERIFIED_REUSE as seq 9's "measured" (OD-B1M).
* Sampling mutants or skipping heavy targets (`execute`).
* Carrying survivor audits across a digest change.
* Dropping `test_no_dual_authority.py` from a kill set.
* Counting NOT_RUN or a darwin-only run of linux-flavoured killers as PASS.
* Retiring C-B1B or C-HIST without ROUND-AUTH.
* Promoting any inventory row or intermediate wave measurement to final-RC evidence.

## 6. Per-wave cost if DAG §6 stays as written (OD-WAVE default), point serial-h

| wave | module-level targets | module-level h | S2-closure-level targets | S2-closure-level h | top re-opening files (closure) |
|---|---|---|---|---|---|
| W1a | 31 | 0.59 | 89 | 73.69 | `tests/v2/sealing_gate.py` 47, `validation/qualification/authority_limits.py` 31 |
| W1b | 36 | 67.41 | 651 | 297.81 | `aisef2/orchestrate/story_runner.py` 651, `aisef2/app/run.py` 560 |
| W2a | 407 | 84.26 | 910 | 307.53 | `aisef2/probe/__init__.py` 910, `aisef2/probe/protocol.py` 910 |
| W2b | 193 | 121.38 | 903 | 307.42 | `aisef2/plan/story_admission.py` 903, `aisef2/plan/drift.py` 899 |
| W2c | 91 | 119.83 | 745 | 300.86 | `aisef2/journal/fold.py` 745, `aisef2/journal/projections/__init__.py` 745 |
| W3 | 541 | 187.95 | 853 | 305.75 | `aisef2/runtime/story_scope.py` 851, `aisef2/runtime/process_range.py` 788 |
| W4a | 210 | 177.55 | 944 | 307.98 | `aisef2/plan/obligation.py` 942, `aisef2/plan/drift.py` 899 |
| W4b | 115 | 127.36 | 903 | 307.42 | `aisef2/control/routing.py` 903, `aisef2/journal/projections/__init__.py` 745 |
| W5-early | 3 | 0.07 | 651 | 297.81 | `aisef2/orchestrate/seam.py` 651, `aisef/cli/_common.py` 237 |
| W5-main | 158 | 153.92 | 899 | 307.32 | `aisef2/plan/static_admission.py` 899, `aisef2/orchestrate/adapters.py` 672 |
| W6 | 39 | 0.54 | 60 | 18.54 | `aisef2/cohort/__init__.py` 44, `aisef2/cohort/lifecycle.py` 44 |

* CHANGED targets by number of waves changing their module: 1: 276, 2: 460, 3: 78, 4: 41, 5: 11, 7: 25.
* Module-level counts a module's every target, which over-counts N2-style edits. The S2 closure counts by the static rule, without
  F5 tiers or observations. Both are estimates, not measurements.

## 7. Owner decisions (none is taken here; FR7 defaults apply)

| ID | question | default without a decision |
|---|---|---|
| OD-RUN-FINAL | Authorize the final-RC measurement of the manifest's MUST set (a >= 994-target campaign) on a named host and K. | not run: release blocked (FR8) |
| OD-Q0-1-W1B | B1 binds the raw sha256 of aisef2/app/run.py (25 B1 targets); W1b edits run.py:693, so Q0 b1_bindings stops being clean. | the run.py:693 edit waits (DAG Q0-1 'the change waits') |
| OD-B1B | Rebind C-B1B to a v2.3 manifest of the frozen CHANGED u NEW scope at the final RC, or retire it. | rebind (a); never retire silently |
| OD-HIST | Replace C-HIST (problems_of against this tree for the 327) by V22_REPLAYED + a v2.3 counterpart (needs ROUND-AUTH seq 13). | no retirement without ROUND-AUTH; counterpart asserts each of the 327 has a committed v2.3 MEASURED entry |
| OD-B1M | May F5 VERIFIED_REUSE satisfy seq 9's 'genuine measured outcome' for the 4 unchanged-module B1 targets? | measure them |
| OD-PLAT1 | Accept platform-unbound v2.2.0 currency (I8 ruling / tier D) for the 92 unchanged legacy targets. | re-measure |
| OD-WAVE | Replace DAG §6 per-wave 'every changed target is MEASURED' by per-wave --affected + targeted tests + T0, measuring once at the final RC. | DAG §6 as written: the per-wave gates cost 1040.9-2832.1 serial-h point on top of the final-RC pass (program_serial_h_under_all_defaults) |
| OD-W1RUN | Bound W1's targeted run to an F5 validation cohort instead of the W1-DESIGN §10 scope. | W1 gate as written; nothing large runs before SCALE-1 |
| OD-WIN | Native Windows for the 3 Windows-only targets at the final RC (seq 10 covered v2.2 only; a CI leg needs DISC-1). | NOT_RUN -> release blocked |
| OD-NEWMOD | Apply FR4 to the new aisef2 modules of W2-W6 and to validation/v2/gen_probe_grammar.py. | apply FR4 |
| OD-F5ENG | Make the F5 reuse engine (impact.py, observe.py), the round/audit modules (rounds, replay_v22, audits, ledger_digest) and the v2.3 authority roots of validation/v2/mutation.py (F5 source rule, read-time supersession, audit dispatch) mutation targets. | round/audit modules and mutation.py's v2.3 authority roots: targets (they bind C-HIST's counterpart and C-CUR's audits). Reuse engine: claim no reuse at the final RC, so it binds no verdict; if any reuse is claimed, the engine becomes a target first |
| OD-NEWVAL | Extend mutation scope to new validation/qualification and non-authority validation/v23 modules (v2.2.0 precedent: validation/qualification has no targets). | v2.2.0 precedent (not targets); they stay covered by their own red-before tests; promoting them adds trust |
| OD-EDITNOTARGET | Promote existing modules that a v2.3 lane edits and that had no v2.2.0 target (other than mutation.py's authority roots, OD-F5ENG) to mutation targets. Each row names its v2.2.0 control and its whole-module count at the pin. | v2.2.0 precedent: not targets; each keeps its v2.2.0 control (Q0 known-bad calibration for validation/v2 checkers, test_checker_calibration for checker_calibration.py, own unit tests otherwise). This is not below v2.2.0; promoting them adds trust at the listed cost |
| OD-REGCOMPLETE | CODE-AUDIT #33 completeness: target registry.py::_inv, armed, render, or exempt them in writing. | target them |
| OD-R3 | Keep FR3 (CHANGED never reused), stricter than DAG §6 / W1-DESIGN N2. | keep FR3 |
| OD-UNTOUCHED | May a planned module byte-identical to v2.2.0 at the final RC leave CHANGED_TRUST_CRITICAL? | no |
| OD-T0COPY | A registered kill file fails T0 in the runner's COPY tree (measured): tests/v2/test_no_dual_authority.py loads validation/qualification/release_inventory.py, which is outside mutation.COPY. Its targets cannot be MEASURED as registered. | fix the runner tree (L1-F5: COPY gains the missing root) and measure; never drop the kill file or accept the v2.2.0 row |
| OD-R2S | Narrow the recorder-track R2S directory-constant rule for tests/v2/test_p9_reproduction.py (it keeps every I6-passing target INVALIDATED against v2.2.0). | keep R2S (narrowing needs its own amendment and proof) |

Scope dependencies: ROUND-AUTH (seq 13; OD-HIST), SCALE-1 incl. PLAT-1 and DIGEST-READ, Q0-1 (OD-Q0-1-W1B), DISC-1 (CI legs), and the owner's
separate authorization for any ≥ 667-target run (OD-RUN-FINAL).

## 8. New rows (MEASURE_NEW and EDITED_NO_V220_TARGET), by the decision they depend on

| decision | rows | mutants known | rows without code |
|---|---|---|---|
| None | 13 | 134 | 1 |
| OD-EDITNOTARGET | 26 | 12,288 | 0 |
| OD-F5ENG | 7 | 4,353 | 3 |
| OD-NEWMOD | 11 | 0 | 11 |
| OD-NEWVAL | 6 | 3,653 | 4 |
| OD-REGCOMPLETE | 3 | 49 | 0 |

`None` is design-declared and needs no decision: `obligation.py` ×7 (all roots), `static_admission.py` ×3 (#77),
`registry.py::{mechanism_digest,_identity}` (#33) and `_Stages.advance` (E5, not yet written).
`OD-F5ENG` also holds mutation.py's v2.3 authority roots (in the default scope, not yet written).
Rows outside the default scope (not in §3), other than OD-EDITNOTARGET's: `validation/qualification/c2_closure_audit.py` (OD-NEWVAL, 3,470 mutants), `validation/qualification/release_governance.py` (OD-NEWVAL), `validation/qualification/test_markers.py` (OD-NEWVAL, 183 mutants), `validation/v23/ground_truth/**` (OD-NEWVAL), `validation/v23/guest_new_user*.py` (OD-NEWVAL), `validation/v23/impact.py` (OD-F5ENG, 2,419 mutants), `validation/v23/observe.py` (OD-F5ENG, 1,225 mutants), `validation/v23/released_evidence_guard.py` (OD-NEWVAL).

### 8.1 Existing modules a lane edits that had no v2.2.0 target (findings RC-2 / CC-2)

FR4 does not make these targets by itself. `validation/v2/mutation.py`'s v2.3 authority roots follow OD-F5ENG (default: targets, like
`audits.py`); every other module follows OD-EDITNOTARGET (default: the v2.2.0 precedent, which is not below v2.2.0). Counts are every
root of the whole module at the pin (count_sites, equal to `mutation.mutants()` on all of them); the roots v2.3 changes are a subset.
By group: product (aisef2/, aisef/): 7 modules, 1,976 mutants; validation/qualification: 11 modules, 7,880 mutants; validation/v2: 9 modules, 7,496 mutants.

| module | wave | decision (default) | roots | mutants | v2.2.0 control |
|---|---|---|---|---|---|
| `aisef/cli/_common.py` | W5-early | OD-EDITNOTARGET (not a target) | 9 | 78 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `aisef/cli/closure.py` | W5-early | OD-EDITNOTARGET (not a target) | 2 | 82 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `aisef/cli/implement.py` | W5-early | OD-EDITNOTARGET (not a target) | 18 | 593 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `aisef/cli/parser.py` | W5-main | OD-EDITNOTARGET (not a target) | 7 | 443 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `aisef/control/budget.py` | W5-early | OD-EDITNOTARGET (not a target) | 18 | 218 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `aisef2/app/calibrations.py` | W2a | OD-EDITNOTARGET (not a target) | 1 | 323 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `aisef2/app/demo.py` | W2c | OD-EDITNOTARGET (not a target) | 10 | 239 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/authority_limits.py` | W1a | OD-EDITNOTARGET (not a target) | 47 | 834 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/p5_acceptance.py` | W1a | OD-EDITNOTARGET (not a target) | 71 | 2,117 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/p5_falsifiability.py` | W1a | OD-EDITNOTARGET (not a target) | 39 | 846 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/q2.py` | W1a | OD-EDITNOTARGET (not a target) | 12 | 946 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/release_bundle.py` | W6 | OD-EDITNOTARGET (not a target) | 6 | 271 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/release_calibration.py` | W1a | OD-EDITNOTARGET (not a target) | 10 | 186 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/release_qualify.py` | W1a | OD-EDITNOTARGET (not a target) | 9 | 244 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/release_rc.py` | W6 | OD-EDITNOTARGET (not a target) | 15 | 241 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/release_smoke.py` | W6 | OD-EDITNOTARGET (not a target) | 42 | 1,307 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/repro_dist.py` | W1a | OD-EDITNOTARGET (not a target) | 2 | 31 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/qualification/v21_conformance_ruling.py` | W1a | OD-EDITNOTARGET (not a target) | 24 | 857 | its own unit tests only; no mutation target and no Q0 checker at v2.2.0 |
| `validation/v2/b1_bindings_check.py` | W1a | OD-EDITNOTARGET (not a target) | 2 | 55 | Q0 known-bad calibration + own tests |
| `validation/v2/checker_calibration.py` | W1a | OD-EDITNOTARGET (not a target) | 60 | 823 | tests/v2/p0/test_checker_calibration.py (GATED through tests/v2/sealing_gate.py) |
| `validation/v2/currency_dag.py` | W1a | OD-EDITNOTARGET (not a target) | 7 | 193 | Q0 known-bad calibration + own tests |
| `validation/v2/execution_order.py` | W1a | OD-EDITNOTARGET (not a target) | 6 | 159 | Q0 known-bad calibration + own tests |
| `validation/v2/kernel_static_checks.py` | W1a | OD-EDITNOTARGET (not a target) | 23 | 399 | Q0 known-bad calibration + own tests |
| `validation/v2/mutation.py` | W1a | OD-F5ENG (target) | 162 | 5,064 | Q0 known-bad calibration + own tests |
| `validation/v2/probe_static_checks.py` | W1a | OD-EDITNOTARGET (not a target) | 24 | 523 | Q0 known-bad calibration + own tests |
| `validation/v2/refmodel_independence.py` | W1a | OD-EDITNOTARGET (not a target) | 6 | 69 | Q0 known-bad calibration + own tests |
| `validation/v2/version_forward.py` | W1a | OD-EDITNOTARGET (not a target) | 14 | 211 | Q0 known-bad calibration + own tests |

## 9. Not done / limits

* Nothing was measured or reused, and no F5 engine was run. Every F5 state is read from the two committed or scratch dispositions.
* Mutant counts and kill sets of changed code at the final RC are unknown; costs use v2.2.0 rows.
* Final-RC survivors and audit effort: UNDETERMINED. Worker contention: UNMEASURED. Final host: UNDETERMINED until SCALE-1.
* The S2 static closure is a lower bound of F5's S(F). Absence of a planned change in it is not proof of no impact.
* The planned-change set is the plan as written at the pin. FR3 adds any unplanned change at the final RC.

Reproduce, from this folder:
* `python3 -B -P scripts/manifest.py <repo> <w1a2 scratch>`. Its inputs are `work/t0-legacy.json` (from `scripts/t0_legacy.py`) and
  `work/verify_counts.out` (from `scripts/verify_counts.py`).
  Also `work/verify_counts_edited.out` (from `scripts/verify_counts_edited.py`).
* Then `python3 -B -P scripts/render_md.py`.

## 10. Checker findings — disposition

Two adversarial checks (reconciliation RC-1..6, cost CC-1..6) were re-verified against primary sources (git objects at the pin and
at v2.2.0, the pilot evidence, the runner source) in a bounded correction pass. Each verdict and correction below is also in
`checker_findings_disposition` in the JSON, inside the digest.

| ID | severity | verdict | evidence (re-verified) | correction |
|---|---|---|---|---|
| RC-1 | MEDIUM | ACCEPT | Re-computed: the old manifest_digest.of recipe applied to the published owner_decisions objects gives b6d73db4..., the claimed 85450512... comes only from the [id, question, default] arrays render_md.py built; basis, summary and inventory_only were outside it. | The digest is now the sha256 of canonical JSON of the whole published document minus its manifest_digest field (basis, rules, owner_decisions, summary, rows, new_rows, inventory_only, this table), hashed in the published form; manifest_digest.verify is a one-line verifier that needs only SCOPE-MANIFEST.json, and render_md.py re-derives it the same way. 85450512... is superseded. |
| RC-2 + CC-2 | MEDIUM | ACCEPT | The generator's own parse of DAG §4 / W1-DESIGN §8 finds 27 existing .py modules (outside tests/, aisef2/plan/obligation.py excluded: it already has #77 rows) that a lane edits and that have no v2.2.0 target, 17,352 whole-module sites at the pin (every root, module-level assignments included; count_sites == mutation.mutants() on all of them, scripts/verify_counts_edited.py). RC-2's 10 modules (def roots only) and CC-2's list (its 1,653 product mutants match exactly) are subsets. FR4 as written covered them; no row did. OD-F5ENG made audits.py a target while mutation.py's audit dispatch was unaddressed. | FR4 now states what the rows apply. mutation.py's v2.3 authority roots (F5 source rule, read-time supersession, audit dispatch) follow the OD-F5ENG default and are MEASURE_NEW (not yet written, so uncounted), for the same reason as audits.py. Every other module has a row under the new OD-EDITNOTARGET, default the v2.2.0 precedent, with its v2.2.0 control (Q0 known-bad calibration for validation/v2 checkers) and its cost if promoted. No row left the default set; one was added to it. |
| RC-3 | LOW | ACCEPT | CODE-AUDIT.md:174 (#13 option (b)) updates registry.py:171-176; the W2c L2-AUTH row (DAG:358) does not own registry.py. W2b L2-JOURNAL (DAG:355), L2-ACCOUNTING (DAG:357) and W4b L4-MONITOR (DAG:377) edit the projections that tests/v2/refmodel/* mirror (their docstrings cite P3-PROJECTION-SEMANTICS). All 16 refmodel rows and 5 of the 11 registry.py rows are MEASURE; the other 6 are in the final set. | FR3 states its digest clause is evaluated mechanically at the final RC; 27 rows carry planned_change_possible with the citation. No class or count changed. |
| RC-4 | LOW | ACCEPT | The scenario was agg(must_reg + must_new) = 1,005 / 28,158, without the impact.py + observe.py rows the OD-F5ENG default adds on any reuse claim. | Renamed final_rc_measure_set_if_every_conditional_row_is_reused_incl_engine_targets, now 1,007 targets / 31,802 mutants / 377.26 h point, against 1,011 / 28,292 / 322.21 h if nothing is reused. |
| RC-5 | LOW | ACCEPT | git ls-tree at the pin: the case-sensitive MUTATION*.json regex missed the worker histories/logs, the hardening results, the exception request, drafts and transcripts. | inventory_only.other_mutation_files lists every closure-evidence path naming 'mutation' in any case and extension, minus RECORDS and AUDITS_REL: 223 paths (draft or tool script 6, exception request 1, record, summary, manifest or note outside RECORDS 20, ruling 1, test-run transcript 10, worker log/history/record 185). None is promoted (FR2). |
| RC-6 | LOW | ACCEPT | mutation.py:1442 NO_AUDIT = {outcome.py::contract_satisfaction}; audit_of returns None for it (:1539) and the survivor branches refuse audits (:2532, :2584). | FR6 now excepts NO_AUDIT targets, which must be fully killed (C-NOAUDIT). |
| CC-1 | MEDIUM | ACCEPT | compare.json: per-target test ratios 0.489-1.304, T0 ratios 0.46-1.247; aisef2/app/review_ocr.py::OCR holds 0.621 of the basis test seconds; without it the ratio is 0.7349. The old band spanned [aggregate, record] only. | Timed bands use the per-target extremes: final set 322.21 h point (159.48-500.14); floor 17.6-47.2 h. The point is one model point (sensitivity: aggregate (the point) 322.2 h; median of the 10 per-target ratios 273.3 h; aggregate without the heaviest pilot target 266.5 h). 63 linux-flavoured rows (119.3 h) are marked uncalibrated until SCALE-1. |
| CC-3 | MEDIUM | ACCEPT | DAG §6 (DEPENDENCY-DAG.md:476): every changed target is MEASURED at each wave exit; OD-WAVE's default keeps it, while FR6 said 'measured once'. | FR6 reworded (final-RC measurement is the release evidence; per-wave runs never enter the release claim). Under all defaults the program costs 1363.1-3154.3 serial-h point (final-RC pass + per-wave gates); 322.21 h holds only if the owner takes OD-WAVE. |
| CC-4 | MEDIUM | ACCEPT | mutation.py _pristine/_new_tree/main: one pristine copy per worker plus a fresh full copy per target, old tree removed after the new copy; no disk guard. Committed COPY = 1.53 GiB; this host: 24 GiB free, 16 GiB RAM, 8 logical CPUs. | worker_resources: 3.06 GiB steady / 4.59 GiB transient per worker; free space needed at the 20 GiB floor: K=1 24.6 GiB, K=4 38.4 GiB, K=8 56.7 GiB. Measured host max K: 1 at steady state, 0 at the transient peak. K>1 walls are conditional on a SCALE-1 host; RAM per worker UNMEASURED. |
| CC-5 | LOW | ACCEPT | V2.1 mutant seconds: median 3.76, mean 58.41 (= total / mutants, the expected per-mutant cost); median x n under-states a sum. | Rate-band point = pilot ratio x mean; low = pilot runner-1 rate; high = max per-target pilot ratio x mean. Default-scope new rows: 13.35 h point; the 5 OD-T0COPY rows: 7.58 h point. |
| CC-6 | LOW | ACCEPT | W1-DESIGN.md:185 and :1154 price the 327 at [E] 16.2-182.5 serial-h from V2.1 per-mutant median/mean (5.8 / 65.2 s) with no measurement of their kill files. The pilot measured 0.613 s per mutant (mutant rows) on its 2 legacy targets; 143 legacy rows' model rate was below it. | The T0-model point is floored at 0.613 s/mutant (+0.40 h). The 327 now cost 17.12 h point (4.78-75.72), of which 7.58 h are the 5 OD-T0COPY rows under the CC-5 mean rate. This manifest's measured-T0 estimate replaces W1-DESIGN §10's [E] 16.2-182.5 h for its own purposes, because it uses each kill file's measured T0 and a calibration fit on the 667 timed entries; W1-DESIGN (committed text) is not edited. |
