# Gate-2 controlled-reseal DRY-RUN manifest — AISEF v2.2 (owner Option A)

**STOPPED at Gate-2.** The dry-run proved the calibration re-derivation is clean and append-only, but it surfaced **new discrepancies** (write-once committed records; pre-existing non-H1/H2 ledger drift; RC2/Q5 CI-and-scope coupling) that collide with the owner's own reseal constraints and therefore require owner decisions before any reseal is committed. No reseal was performed. All commands below were read-only (`--check`/`--print`/checker default); `git status closure-evidence/ validation/ aisef2/` is clean after them.

Measured 2026-11-06. RC = HEAD `9ec7d106` (code bytes ≡ `1c42aaad`; the only non-code diff is this evidence family). pyproject version = `2.1.0`.

## 1. Commit / digest / working-tree (owner dry-run #1) — CONFIRMED
- HEAD `9ec7d106`; `git diff 1c42aaad HEAD` = docs only (the finding §8). No tracked drift; `release_calibration --check`/`release_rc --check`/`freeze_manifest --check`/`destructive_authority` all left the tree clean.
- aisef2 tree object (pre-reseal) = `87ebf3607b176111b1d07dc863a2977e089bb1fb`.
- Executing digests moved because H2 edited `aisef2/runtime/process_range.py`, which every active probe's EXECUTION_DIGEST hashes.

## 2. Calibration re-derivation + before/after (owner dry-run #2) — CLEAN, append-only
`python3 -P validation/qualification/release_calibration.py --print` → verdict `CALIBRATED`, 0 problems, 19 rows. `--check` → FAIL (stale), as required.

Before/after — only `probe_digest` (and the fresh `demonstrated_at`) change; probe_id, observation_class and both fixture paths are byte-identical; no row added/removed:

| probe | before (shipped) | after (RC tree) |
|---|---|---|
| probe.cli_invocation | `0b59dd56ef12` | `415694b5b21c` |
| probe.file_artifact | `5dcd071d61f1` | `b4ff31381bcf` |
| probe.process_effect | `c37e6b632ee2` | `75e6cf5bfae7` |
| probe.python_callable_v2 | `f381c52f37a0` | `d0c434d1d1cd` |

Append-only by construction (`release_calibration.py:35-48,152-163`): `aisef2/app/calibrations.py` (generated shipped rows) is rewritten in place; the record appends as **`V2.1.0-PROBE-CALIBRATIONS-2.json`** beside the untouched `V2.1.0-PROBE-CALIBRATIONS.json`; 2.0.0's record is hard-refused from rewrite. Timestamps are fresh (now), never back-dated.
**Cascade note:** regenerating `calibrations.py` changes the aisef2 **tree object** again (87ebf36 → a new X). `calibrations.py` is in no probe's PROBE_SOURCES, so the 4 probe digests do **not** re-move; but every `HEAD:aisef2`-bound record must be derived against the **final committed** tree X, not 87ebf36. Reseal order therefore = (1) `--write`, (2) commit, (3) derive tree-bound records.

## 3. Freeze machinery (owner dry-run #3/#4)
- **Architecture freeze manifest** (`validation/v2/freeze_manifest.py` / `AISEF-V2-FREEZE-MANIFEST.json`) binds the RFC markdown, not aisef2 code. `--check` = **PASS**. H1/H2 are code-only → **no amendment required**; the 2.0 history manifest stays byte-identical (pinned by git blob).
- **Release-candidate freeze** (`validation/qualification/release_rc.py` / `V2.1.0-RC1-FREEZE.json`) binds the aisef2 kernel tree. `--check` = **FAIL**: "HEAD's shipped files are not the RC's: [README.md, aisef, aisef2] (a new candidate is needed)" — RC1 was frozen at the older commit `dc63478` (tree `5f34a3f`), so README/aisef also differ. Re-freeze is **append-only**: `release_rc.py --freeze` writes the next `V2.1.0-RC2-FREEZE.json`, refuse-on-exist, never rewrites RC1. **Prerequisite:** a reproducible staging CI build of the reseal commit (to supply `SHA256SUMS` + CI run id) — `--freeze` will not fabricate artifacts.

## 4. Record-currency / sealing tier (AISEF_SEALING=1, 18 gated tests)
Stale set from H1/H2 and how each refreshes:
- **probe calibrations** → §2 (clean, append-only). ✔
- **`test_c2_p5_acceptance` Acceptance + KernelProvenance** → re-derives **live** at test time (binds HEAD:aisef2 + probe execution digests); needs only `calibrations.py` regenerated + a committed tree. No record to rewrite. ✔
- **`Q5-KERNEL-COMPARISON.json`** (tracked) via `v21_q5_compare.py` — opens output mode **`"x"`** (`:297`): refuses if the committed record exists. ⚠ write-once.
- **`CONFORMANCE-RULING.json`** (tracked) via `v21_conformance_ruling.py` — mode **`"x"`** (`:448`), imports `release_calibration`/binds EXECUTION_DIGEST. ⚠ write-once.
- **`C2-ORCHESTRATION-CONFORMANCE-REPAIR.json`** (tracked, cycle-2) — `c2_orchestration_repair.py --write` "refuses on 2.1". ⚠ write-once.
- **`test_v21_mutation_runner::Classify`** — flags edited-file targets; already red from wave-1 independently.
Historical mutation records (P1..V2.0-S2, cycle2) and 2.0 calibration/inventory/Q0 records: must stay **byte-identical** (never rewritten).

## 5. Destructive-authority ledger (`validation/v2/destructive_sites.json`)
`python3 validation/v2/destructive_authority.py` → **FAIL** (exit 1), 14 lines, **purely additive** (0 removed, 0 modified; existing 50 rows untouched). No `--write`; the ledger is hand-maintained (append rows). ROOT check is **@sealing-gated only** (not in mandatory CI). Classified by introducing commit:

**Round-3 H1/H2 (commit `1c42aaad`) — 7 lines:**
- `aisef2/runtime/process_range.py:151` `[pid_alive] os.kill(pid)` → `LIVENESS_PROBE_SIGNAL_0`
- `tests/v2/test_v22_win_oskill_is_gone.py:44,61,72,75,91` `child.kill` + `:111` `child.terminate` → `TEST_CREATED_HANDLE`

**Pre-existing (NOT H1/H2) — 7 lines:** `test_v21_pl7_session_teardown.py:53` (81de22eb), `:108` (fd1a1658); `test_v21_pw_lineage_continue.py:292,:488` (fd1a1658); `test_v22_client_pin_fence.py:110,:119` (76fd9cd8 wave1); `test_v22_hardening_p1_run_pin_fence.py:29` (774d291b wave2 round-2). **The sealing gate was already red before H1/H2.**

## 6. Provenance / `--verify` (owner dry-run #4)
- `aisef run --verify` (per-run evidence re-derivation) and the byte-identity invariants (`v1_evidence_guard.py --check`, `freeze_manifest.py --check`) are **unaffected** by H1/H2 (they bind closure-evidence/ and the RFC, not aisef2/) and are **read-only** verifiers. Only the probe-calibration provenance artifact is stale (§2).

## 7. CRITICAL SCOPE FINDING — the sealing tier is stale from the WHOLE wave delta, not H1/H2
`v21_conformance_ruling.py --check` and `v21_q5_compare.py --check` FAIL on this tree, but the divergence is **not H1/H2**:
- `CONFORMANCE-RULING.json` reports `aisef2/probe/catalog.py: missing — 2.1 changed it`; `aisef2/orchestrate/story_runner.py commits_2_1 … 'v2.1(B, V21-38)' … this tree derives … '30da62a6 wave2: revert C4'`; plus cli_invocation/file_artifact sha/commits/owner-approval drift.
- `Q5-KERNEL-COMPARISON.json`: `q5.py recorded 479ebe47…, now c1719ed4…`; `kernel_2_1 737585ea…, now 045a8fed…`.
- **Both records were frozen at `c186cb22` (2026-10-15)** — before the v2.1.0 release (`7d1da61f`, 11-01) and all three waves — and untouched since. The divergence source `story_runner.py` was last changed by `30da62a6` (wave-2, 11-04); `catalog.py` by the v2.1 migration (10-17).

**Consequence:** making these records bind this tree = regenerating a **full v2.1 conformance / kernel-comparison snapshot** that would absorb the entire wave-1 + wave-2 + round-3 delta and **replace frozen 2026-10-15 release-era records**. That is far beyond H1/H2 and collides with "no code scope beyond H1/H2" + "no overwrite of historical evidence". The sealing tier has been red on master since the waves began, by design (master runs raw; v2.1.0 shipped green via the scoped `release_qualify` allowlist, not by regenerating these). `C2-ORCHESTRATION-CONFORMANCE-REPAIR.json` is explicitly designed-frozen ("never re-written on 2.1"; its test passes by verifying the refusal) — not a blocker.

## 8. What the H1/H2 reseal CLEANLY covers vs. what it does not
**In scope & clean (append-only, strictly H1/H2):**
- **Probe calibrations** — `release_calibration.py --write` (§2). Clears the gate-1 OPEN CONDITION: the 60+ calibration-admission failures in the RAW full suite. This is the substantive fix.
- **Destructive ledger — the 7 round-3 rows** (`process_range.py:151` + the new `test_v22_win_oskill` file). Additive to the live ledger; sealing-gated only (not mandatory CI).

**NOT H1/H2 / needs a separate owner-governed 2.1-line re-qualification:**
- Destructive ledger — the **7 pre-existing** rows (PL-7 era / v2.1 candidate / wave-1 / wave-2 round-2).
- Sealing tier — `CONFORMANCE-RULING.json` + `Q5-KERNEL-COMPARISON.json` (stale from the wave delta; §7).
- **RC2 freeze** (needs a reproducible staging CI build; mechanically a new `V2.1.0-RC2-FREEZE.json`) and **Q5** (never run for 2.1.0; no dry mode; not in the owner's gate-3 list).

## 9. Decisions for the owner (why Gate-2 STOPS)
1. **Reseal scope.** Recommended: execute the **H1/H2-clean reseal only** — (a) `release_calibration.py --write` + append record, (b) append the **7 round-3** destructive rows — committed append-only; and **log the rest (§8 bullet-2) as pre-existing OPEN CONDITIONS** (not waived — logged with this evidence, exactly as gate-1's full-suite-red was). Alternative: full 2.1-line re-qualification (regenerate CONFORMANCE-RULING/Q5-KERNEL-COMPARISON across the whole wave delta + RC2 + Q5) — large, beyond H1/H2, replaces frozen release records.
2. **Destructive pre-existing 7 rows.** Append them too (live ledger is additive, no historical overwrite — makes the destructive sealing check green) OR leave as pre-existing OPEN CONDITION. These are not H1/H2.
3. **Gate-3 "sealing PASS" scope.** Confirm it means "the sealing checks H1/H2 touches are green (calibration + the H1/H2 destructive rows)", with the wave-divergence sealing items (§7) recorded as a pre-existing OPEN CONDITION — because a full sealing-green requires the §1-alternative re-qualification the owner separately governs. I will not narrow this criterion without the owner's ruling.

No reseal committed. Awaiting owner ruling on §9 before executing the (then fully-specified, append-only) reseal.
