# Final Release Readiness — AISEF v2.2 (owner post-gate-3 directive)

**STATUS: NOT A RELEASE.** This report answers the owner's post-gate-3 directive (Windows native integration +
v2.2 qualification design/dry-run) so the owner can decide the next step. No tag v2.2, no publish, no Đợt-3, no
scope beyond the directive.

Measured 2026-11-07 (+07). Branch `master`. HEAD at report time `610f5030`; `HEAD:aisef2 = ac7c1705`; v2.1 seal
tree `1d4f0156`.

## 0. Directive status

| # | Owner item | Status |
|---|-----------|--------|
| 1 | Push accepted report `7dda13f5` | ✅ DONE — on `master` (`a9a93305..7dda13f5`), no amend/rewrite |
| 2 | Windows NATIVE Win32 integration (real runner) | ✅ DONE — windows-3.11 unit SUCCESS @ `610f5030` (run `42302873797`); all four properties proven on live Win32; one test-harness bug fixed en route (§2) |
| 3 | v2.2 qualification design + dry-run for the 21 sealing failures | ✅ DONE — §3–§6; all 21 = provenance-only currency, 0 product bugs |
| 4 | This Final Release Readiness report | ✅ this document |

---

## 2. Windows native integration (item 2)

Added `tests/v2/test_v22_win_native_liveness.py` (`skipUnless(os.name=="nt")`), which drives `pid_alive` through
the **real** Win32 `OpenProcess`/`GetExitCodeProcess` on a `windows-latest` runner — not a mock. Four properties:
1. a live (sleeping) child is **not** read GONE;
2. a genuinely-ended child **is** read gone (Popen handle held → no PID-reuse race);
3. the probe **does not terminate** a live process (QUERY_LIMITED only; child survives the probe);
4. a protected process (System PID 4) **fails closed to alive**, plus a best-effort native observation of a real
   `ERROR_ACCESS_DENIED` handle.

**First run (`a88d5011`, run 42289621107).** windows-3.11 unit = FAILED with **errors=1** — but the error was in
the test harness, **not** the kernel:
- The three deterministic property tests (live≠gone, ended→gone, no-terminate) **passed**, and the `pid_alive(4)`
  fail-closed anchor **passed** (the error was at the line *after* it).
- The error: the optional access-denied scan called `process_table()`, which on non-Linux shells out to POSIX `ps`;
  the runner's `ps` returned non-zero → `CalledProcessError`.
- This is **not** a kernel defect and **not** a kernel change (owner #2 STOP condition not met): `_is_gone`
  (`aisef2/app/client.py:42`) already catches a failing `ps` (`subprocess.SubprocessError`) and falls back to
  `pid_alive` — that is FINDING-WIN-OSKILL-001 **H1** by design, so `process_table()` failing on Windows is a
  known/handled condition. The H2 probe `pid_alive` itself never calls `process_table()` on the nt path
  (OpenProcess only), and the Windows `ProcessRange` uses the job-object API — both Windows-native.

**Fix (`610f5030`, test-only).** Replaced the `process_table()` enumeration with a bounded raw Win32 OpenProcess
scan over low PIDs, fully guarded (try/except) so the best-effort observation can never error the test. The four
real assertions are unchanged; no new destructive site (checker still 7).

**Re-measurement (run `42302873797` @ `610f5030`, authoritative per-job conclusions via `gh run view --json jobs`):**
- **windows-latest 3.11 unit = SUCCESS ✅** — the corrected native test runs on a real Win32 runner and all four
  owner-required properties are proven against the live kernel (no mock): a live child is not read gone, an ended
  child is read gone, the live child survives the probe (QUERY_LIMITED only — no unintended terminate), and the
  protected System process fails closed to alive. **Item 2 is satisfied.**
- ubuntu 3.12 / 3.13 / 3.14 unit, macos-3.12 unit, lint, wheel = **SUCCESS**.
- sealing = **FAILURE** — the pre-existing 21 wave-divergence items (§3), unchanged by this test-only commit.
- **ubuntu-latest 3.11 unit = FAILURE (failures=1) — the known infra-load flake, NOT a regression and NOT in scope
  of this change.** The single failure is `v2.test_v21_confine.FailClosed.test_what_is_measured_decides_not_the_name_of_the_tool`
  with `TimeoutExpired: timed out after 60 seconds` on the bubblewrap probe; the suite took **3343 s** (loaded
  runner). This is the *exact* test the owner already ruled a flake in gate-3 (owner #3, re-ran GREEN) — last round
  it landed on ubuntu-3.12, this round on ubuntu-3.11; that version-nondeterminism is the flake signature, not a
  version-specific defect. `confine.py` is untouched by H1/H2 and by `610f5030` (which touches only
  `tests/v2/test_v22_win_native_liveness.py`), so owner #2's STOP condition (new defect / kernel change needed) is
  **not** triggered. Per the gate-3 precedent for this test, a targeted re-run of only this job (same candidate,
  `PROBE_TIMEOUT=60` and sandbox mechanism unchanged — a re-run, not a change) was launched to confirm recovery.
  _Re-run outcome: see §7-note / memory; the Windows result above stands regardless of it._

---

## 3. The 21 sealing failures — full map (owner #3)

17 distinct tests → 21 failures (two run ×N). Every cluster was classified then **adversarially verified**.
Category legend: **RC** record-currency · **CAL** calibration · **CONF** conformance · **LEDG** destructive-ledger
· **FRZ** freeze-provenance. **Product bug: 0 / 10 clusters.**

| Cl | Failing test(s) | Generator | Historical record (v2.1/cycle2) | Stale cause (provenance pin moved) | Cat | Product bug |
|----|-----------------|-----------|---------------------------------|------------------------------------|-----|-------------|
| C1 | test_P5_8_committed_record_is_current ; test_on_this_tree_the_committed_proposal_is_current ; test_the_acceptance_re_derives_on_this_tree | `p5_acceptance.py` (+ `p10_contracts.py` authoring aid, binds `p5_falsifiability.py`) | P5-PLAN-V2.2-PROPOSAL.json ; C2-P5-ACCEPTANCE-REVERIFICATION.json | aisef2_tree 1d4f0156→ac7c1705; file_artifact probe digest be1485d2→ba12a5d2 (CAPABILITY_VERSION 2→3, PM-9); specs[42..50].{probe_digest,semantic_hash,spec_hash_id}; plan_hash; proposal_digest | RC | **No** (measured — §4) |
| C2 | test_15_…probe_story ; test_15b_…release_s_named_changes ; test_the_committed_record_is_what_this_tree_derives | `c2_orchestration_repair.py` ; `c2_plan_correction.py` ; `c2_delivery_experiment.py` | cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json ; PLAN-V2.2-CORRECTION-1.json | probe capability digest cascade from process_range.py/calibrations.py (gate-3 bytes-that-run); falsifiability backing key-match 59→50; 3 hash-equality booleans flip | CONF | **No** |
| C3 | test_the_evidence_record_re_derives ; test_the_evidence_record_re_derives_from_the_tree | `c2_p10_profile.py` ; `c2_p10_cohort.py` | cycle2/P10-PROFILE-FREEZE.json ; cycle2/P10-COHORT-MACHINERY.json | SOURCES sha256 of the record's own sealing-gated test module moved (wave-1 9a3d1377 added a line to each test file) | RC | **No** |
| C4 | test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after | `c2_k_nowork_001.py` | K-NOWORK-001-REHEARSAL.json | kernel_digest / aisef2_tree / source-file-digest moved (the one semantic kernel change, wave2 9f0f7dc1, was cleanly reverted) | RC | **No** |
| C5 | test_Q5_19_the_kernel_comparison_record_binds_this_tree | `v21_q5_compare.py` (binds `q5.py`) | Q5-KERNEL-COMPARISON.json | q5.py digest 479ebe47→c1719ed4 (2-line wave-1 import add); aisef2_tree. Status = ENGINEERING MEASUREMENT, not a Q5 rung | RC | **No** |
| C6 | test_the_committed_ruling_is_what_this_tree_derives | `v21_conformance_ruling.py` | CONFORMANCE-RULING.json | catalog.py ruling row absent from the committed record; 7 rows' sha256_2_1/commits_2_1; probe/plan hashes. derive() runs clean (problems=[], 13 rows) | CONF | **No** |
| C7 | test_every_checker_is_calibrated_and_the_committed_record_is_current ; test_every_checker_has_a_committed_fixture_… (×3: mutation, destructive_authority, execution_order) | `validation/v2/checker_calibration.py` | Q0-CHECKER-CALIBRATION.json | 2/3 checkers digest-only (fold.py source 4fa87887→257daadc; T0-SWEEP null-mutant sha). 3rd = destructive_authority: genuine PASS→FAIL = the 7 unledgered sites (= C9) | CAL (+LEDG) | **No** (test-only ledger gap — §5) |
| C8 | test_historical_records_read_as_before (×3) | `v21_mutation_record.py` (+ legacy P3/P4/P5 records) | MUTATION.json ; MUTATION-SUMMARY.json (test flags legacy phase records) | source_sha256 / FINAL_HEAD tree snapshot pins moved; neither test nor --check re-measures mutation | RC | **No** |
| C9 | test_this_tree_passes_and_every_site_is_ledgered ; test_INV_MUTATION_AUTHORITY_…ledgered | ledger `validation/v2/destructive_sites.json` + checker `destructive_authority.py` (no --write generator) | validation/v2/destructive_sites.json (56 rows) | 7 destructive sites in tests/v2 lack a ledger row — all test-created cleanups (TEST_CREATED_HANDLE / TEST_OWNED_TEMP) | LEDG | **No** (§5) |
| C10 | test_the_V2_007_exception_records_what_the_owner_decided_and_when | `validation/v2/freeze_manifest.py` (test pin) | ARCHITECTURE-EXCEPTION-V2-007.json | promoted_from.sha256 of a docs/ decision-proposal markdown: e0324223→7ca12232 (dated errata appended; proposal kept verbatim). freeze_manifest --check PASSES | FRZ | **No** |

Adversarial verify: **8 CONFIRMED-provenance-only; 2 FLAG (C1, C7)** — both run to ground (§4, §5), neither a product bug.

---

## 4. C1 closed by measurement (the one FLAG that needed a dry-run, not just inference)

The C1 verifier refused to certify provenance-only on reading alone: the `file_artifact` probe gained real new
behavior in wave-2 (CAPABILITY_VERSION 2→3, PM-9 "a selection of no file is an absent subject"), so the 9 specs'
probe digests moved and a `--check` cannot re-execute their mutations.

I ran the **observe-only** `p5_falsifiability.run(matrix=False)` on HEAD (reference + per-spec witness for all 59
specs; writes nothing — a dry-run, not a reseal):
- **59/59 QUALIFIED, 0 not_qualified, 0 reference_not_satisfied**, including all 9 `file_artifact` specs
  (S-10-a/b/c, S-12-a/b/c, S-13-a/b/c): each pristine SATISFIED, mutant REFUTED → the kills still hold on HEAD.
- Guarded re-run with `opencode` stripped from PATH + a tripwire + scratch XDG reproduced **59/59** and the
  tripwire **never fired** → fully offline, opencode never invoked.
- (The dry-run's 18 "problems" are all `P0 M-*: refuted by no spec` — the P0 cross-check leg that `matrix=False`
  deliberately skips, an artifact of the bounded run, **not** failures.)

So the behavioral falsifiability is unchanged on HEAD; the record's 59→50 "backing" number is a stale
semantic-hash **key** mismatch, not a qualification-verdict change. **C1 is provenance-only by measurement.**

---

## 5. C7 ≡ C9 — the one genuine tree-change (test-only ledger-currency gap)

Not a moved digest: the `destructive_authority` static-conformance verdict genuinely flipped PASS→FAIL because **7
destructive sites entered `tests/v2/` after the 2026-10-15 record seal** and are not ledgered:

| # | Site | Call | Authority source (proposed) |
|---|------|------|------------------------------|
| 1,2 | test_v21_pl7_session_teardown.py (addCleanup) | `p.kill()` of a test-spawned Popen | TEST_CREATED_HANDLE |
| 3,4 | test_v21_pw_lineage_continue.py | `.unlink()` of a temp evidence file | TEST_OWNED_TEMP |
| 5,6 | test_v22_client_pin_fence.py | `.unlink()` of a temp log | TEST_OWNED_TEMP |
| 7 | test_v22_hardening_p1_run_pin_fence.py (addCleanup) | `shutil.rmtree()` of the test tempdir | TEST_OWNED_TEMP |

All are `tests/v2/` self-cleanup of resources the test itself created — **no shipped (`aisef2/`) code, no new
runtime authority**. The checker's scope explicitly includes `tests/v2/`, so "it's only tests" is a human waiver
the oracle does not make; honest resolution = **append 7 ledger rows** (the same append-only mechanism the gate-3
reseal used for the H1/H2 rows), each declaring its authority_source. Not done here (design/dry-run only; owner
decision).

---

## 6. v2.2 qualification design, change manifest & before/after digests (owner #3)

**Principle: append-only, separate namespace, zero overwrite.** Every stale record is a v2.1/cycle2 artifact
sealed at an older tree. The design creates a **new v2.2 record** re-derived on `ac7c1705` under
`closure-evidence/v2/v2.2/`, leaving every v2.1/2.0/cycle2 record byte-identical. The sealing tier then binds the
v2.2 records for the current wave while the v2.1 records remain the frozen history.

**Append-only proof — these committed records stay byte-identical (before == after):**

| Record | before-digest (sha256[:12]) | after the v2.2 work |
|--------|------------------------------|---------------------|
| v2.1/P5-PLAN-V2.2-PROPOSAL.json | `b7d74e5956dd` | unchanged |
| v2.1/C2-P5-ACCEPTANCE-REVERIFICATION.json | `86eff5ed3623` | unchanged |
| v2.1/P5-FALSIFIABILITY.json | `5e465c1577b2` | unchanged |
| cycle2/P10-PROFILE-FREEZE.json | `90526a282093` | unchanged |
| cycle2/P10-COHORT-MACHINERY.json | `72e21dffaa3c` | unchanged |
| v2.1/K-NOWORK-001-REHEARSAL.json | `76bb87acf785` | unchanged |
| v2.1/Q5-KERNEL-COMPARISON.json | `e57b20c05055` | unchanged |
| v2.1/CONFORMANCE-RULING.json | `3766b62a086d` | unchanged |
| v2.1/Q0-CHECKER-CALIBRATION.json | `781fe58964df` | unchanged |
| v2.1/MUTATION.json | `69f533b23f47` | unchanged |
| v2.1/ARCHITECTURE-EXCEPTION-V2-007.json | `69aa3ff677ec` | unchanged |
| validation/v2/destructive_sites.json | `78252fc0a0f6` | **+7 rows appended** (C9) |

**New v2.2 records to create (append-only), each re-derived on `ac7c1705` via the record's own `--write`:**
P5-PLAN-V2.2-PROPOSAL, C2-P5-ACCEPTANCE-REVERIFICATION, P5-FALSIFIABILITY, C2-ORCHESTRATION-CONFORMANCE-REPAIR,
PLAN-V2.2-CORRECTION-1, P10-PROFILE-FREEZE, P10-COHORT-MACHINERY, K-NOWORK-001-REHEARSAL, Q5-KERNEL-COMPARISON,
CONFORMANCE-RULING, Q0-CHECKER-CALIBRATION, MUTATION(+SUMMARY) — all under `closure-evidence/v2/v2.2/`.

**Moved pins carried into the v2.2 re-derive (before→after):** aisef2_tree `1d4f0156`→`ac7c1705`; file_artifact
probe digest `be1485d2`→`ba12a5d2`; q5.py `479ebe47`→`c1719ed4`; V2-007 dossier LF-sha `e0324223`→`7ca12232`;
checker mutation target (fold.py) source `4fa87887`→`257daadc`.

**Assurance preserved — no waiver.** The v2.2 qualification runs the **same generators and the same checkers at
the same strictness**, re-deriving on the current tree; nothing is tolerated or skipped. A record stays red until
it genuinely re-derives; the only behavior-bearing re-confirmation (C1's 9 `file_artifact` mutations) is already
measured green (§4). Independent re-verification is preserved because each v2.2 record binds `ac7c1705` and is
reproducible by re-running its generator `--check`.

---

## 7. Remaining risks & release blockers

1. **Full mandatory sealing is still red (21 items).** Scoped acceptance (gate-3, H1/H2) holds; **full** sealing
   PASS requires the v2.2 re-derive + the 7 ledger rows (owner-gated — not done here). Until then, no full-sealing
   PASS claim.
2. **Windows native positive confirmation — DONE (not a blocker).** Run `42302873797` @ `610f5030`:
   windows-3.11 unit = **SUCCESS**, all four properties proven on the real Win32 kernel (§2). Residual: the
   access-denied *observation* is best-effort (documents when no denied handle is reachable); fail-closed-on-denied
   itself stays pinned by the pure `WinLivenessDecision` (mutation-proven), so this is not an open risk.
   *Orthogonal:* the same run's ubuntu-3.11 hit the known confine/bubblewrap 60s-timeout flake (§2) — `confine.py`
   untouched, targeted re-run in flight to confirm recovery; not a release blocker for item 2.
3. **Acceptance-semantics question for the owner (C10).** The V2-007 promoted-from dossier had dated errata
   appended (proposal kept verbatim); the byte-pin now mismatches. This is write-once-document currency, not a
   changed exception outcome — but whether the appended errata needs its own exception vs. v2.2 record-currency is
   an **owner acceptance-semantics call** (per directive, I do not decide it).
4. **No product defects found** across all 21. C1 measured-benign; C7≡C9 is test-only ledger currency.

---

## 8. Minimal step-sequence to full mandatory sealing PASS (owner #4)

Each step is owner-gated (a reseal/`--write`, outside this design+dry-run). Proposed minimal order:

1. **Owner authorizes the v2.2 re-derive/reseal** (append-only, namespace `closure-evidence/v2/v2.2/`, no historical edit).
2. **Windows native green — ALREADY CONFIRMED** (run `42302873797` @ `610f5030`, windows-3.11 unit PASS; §2). No further action for item 2.
3. **Append the 7 destructive-ledger rows** to `validation/v2/destructive_sites.json`, each with its authority_source (§5); re-run `destructive_authority` + INV-MUTATION-AUTHORITY → green.
4. **Re-derive the v2.2 records** — run each generator `--write` on `ac7c1705` into `closure-evidence/v2/v2.2/` (C1–C6, C8, C10; C7 Q0-CHECKER-CALIBRATION after step 3). The C1 falsifiability re-derive re-runs the 9 `file_artifact` mutations (already measured green in §4).
5. **Re-run full suite + sealing tier** (`AISEF_SEALING=1`) → expect the 21 → 0; confirm `--check`/freeze/v1-evidence/calibration all PASS; verify `git status closure-evidence/` shows only the intended new v2.2 files (no overwrite of v2.1).
6. **Then** the owner may consider release qualification (tag/publish) — **not** in scope now.

Boundary held throughout this report: no tag v2.2, no publish, no Đợt-3, no scope creep.
