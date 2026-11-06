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

## 7. Discrepancies requiring owner decision (why Gate-2 STOPS)
1. **Write-once committed v2.1/cycle2 records** (`Q5-KERNEL-COMPARISON.json`, `CONFORMANCE-RULING.json`, `C2-ORCHESTRATION-CONFORMANCE-REPAIR.json`): refreshing in place requires deleting the committed record (**violates "no overwrite/modification of historical evidence"**); writing an `--out` successor requires editing each gated test's hardcoded path (**violates "no code scope beyond H1/H2"**). → **Decision: successor-path (+ accept the minimal test path-binding edit as in-scope) OR declare these standing OPEN CONDITIONs.**
2. **Destructive ledger scope**: 7 of 14 unledgered sites pre-date H1/H2. Appending all 14 makes the sealing gate green but refreshes non-H1/H2 drift; appending only the 7 H1/H2 rows keeps the gate red. → **Decision: full-ledger refresh (recommended; additive, live-ledger, no historical overwrite) OR H1/H2-only.**
3. **RC2 freeze & Q5 scope**: RC2 freeze needs a reproducible staging CI build; "cùng RC" = same code `1c42aaad` but mechanically a new `V2.1.0-RC2-FREEZE.json`. Q5 was never run for 2.1.0 (it shipped under the scoped `release_qualify` gate), has no dry mode, and is **not** named in the owner's gate-3 list. → **Decision: confirm RC2-freeze is in scope (after the staging build) and that Q5 is OUT of scope for this reseal.**

No reseal committed. Awaiting owner decisions on §7 before executing the (then fully-specified, append-only) reseal.
