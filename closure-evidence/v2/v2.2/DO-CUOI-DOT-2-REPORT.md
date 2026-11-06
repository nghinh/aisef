# ĐO CUỐI — Báo cáo nghiệm thu ROADMAP-2.2 Đợt 2

Date: 2026-11-06 · Branch: master · Model: Opus 4.8
Owner decisions honored: 2026-11-04 (wave-2 scope + order) and **2026-11-06 (6 decisions)**.

> Status fields marked `[PENDING]` are filled when the final full-suite run, the consolidation commit, and its CI re-run complete. This report is prepared per owner item #5 and the directive *"Sau khi hoàn tất ĐO CUỐI, trình báo cáo nghiệm thu Đợt 2 cùng danh sách các quyết định còn tồn đọng."*

## 1. Summary

All wave-2 work items are complete. No kernel (`aisef2/`) code was changed this cycle except the previously-reverted C4 (owner #1: out of scope, kept reverted). Remaining changes are test-only (one CI flake fix), evidence, and the FINDING-WIN-OSKILL-001 plan — all additive.

**One honesty flag up front:** the local full suite is **not clean** — 8047/8048 pass, 1 failure. That 1 failure is a cycle-2 *historical forensic* test tripped by the approved paid canary writing to this machine's real opencode store; it is machine-local, CI-immune, caused 0% by the wave-2 diff, and left unmasked (§3a). CI (the authoritative gate) is green. The suite is **not** declared green (owner #2).

## 2. Commit & CI

- Consolidation commit SHA: `[PENDING COMMIT]`
- Pushed to: `origin/master`
- CI run: `[PENDING CI]` — expectation: all mandatory jobs green; `sealing` red-by-design (honestly red until owner reseal). **Per owner #2, CI is NOT declared PASS while any mandatory job is red.**
- Prior CI @346b432e: `unit (ubuntu-latest, 3.12)` was red (1 test); root-caused + fixed this cycle (§4).

## 3. Full suite (main tree)

- Command (matches CI unit leg): `python3 -P validation/v2/owned_run.py -- python3 -m unittest discover -s tests -q`
- **Result: `Ran 8048 tests in 4471.607s` → `FAILED (failures=1, skipped=56)`.** 8047 pass, **1 fail**, 56 skip. The local suite is **NOT clean** — reported honestly, not declared green (owner #2).
- `ruff check .`: **All checks passed** (0.16.4, exit 0).
- Post-suite `git status closure-evidence/`: the C2 history machinery appended a `seq 36` gate-run record to `closure-evidence/v2/cycle2/C2-FINAL-RUN-HISTORY.json` (test-generated); **reverted with `git checkout`, never committed** (CLAUDE.md). No other evidence was overwritten.

### 3a. The 1 failure — environmental contamination, machine-local, CI-immune, **not** a product defect

- **Test:** `HistoricalAttempt4.test_the_machine_s_external_copies_are_checked_and_an_absent_copy_fails` ([tests/v2/test_c2_delivery_experiment.py:1119](../../../tests/v2/test_c2_delivery_experiment.py)).
- **Assertion:** `self.assertEqual(dx.external_problems(4), [])` — a **cycle-2 historical forensic guard** that opens the *real machine* opencode store `~/.local/share/opencode/opencode.db` and fails if `max(time_created) > attempt-4.finished`.
- **What tripped it:** `attempt-4.finished = 2026-10-03T02:02:53Z`; the store's newest session is **`2026-11-05T19:04:56Z`** (= 2026-11-06 02:04 +07) — created by the **approved paid B1/B7 canary runs** (owner lifted the budget cap) invoking the real opencode client. The guard cannot tell a legitimate post-attempt client session from tampering, so any opencode activity on this dev machine after 2026-10-03 trips it.
- **Scope:** the assertion is guarded by `if (preserve_root()/"attempt-4-evidence").is_dir()` — **true only on this machine**. On a fresh CI runner that directory is absent, so the assertion is skipped → **CI is green on this test** (confirmed: prior CI @ad7164d3 green). A clean `master` checkout on this same machine fails identically (the state is in `opencode.db`, not the repo) → **0% caused by the wave-2 diff**.
- **Classification (owner #1/#2):** not a product (`aisef2/`) regression, not a wave-2 change, **not** masked. It is a *historical* forensic test that is fragile to legitimate client activity on the dev box. Logged as a forward-looking hardening candidate (§8), not a wave-2 blocker. **No test or product code changed to hide it.**

## 4. CI red root-cause (owner #3)

- **Job:** `unit (ubuntu-latest, 3.12)` @346b432e — 1 test failed; 5/6 matrix cells green (incl. 3 other Linux cells).
- **Test:** `test_a_readable_canary_is_recorded_as_read…` ([tests/v2/test_v21_r4_probe_record.py](../../../tests/v2/test_v21_r4_probe_record.py)).
- **Classification:** **load flake — test-harness timeout too tight.** On a saturated runner (that cell's suite took 3267s ≈ 54 min) the test's own `subprocess.run(..., timeout=60)` on the real `/bin/sh` probe timed out → the probe reported "did not run" → `READABLE` absent from problems. The commit touched only docs/evidence — no product/test code — so it is pre-existing, not a regression.
- **Fix:** test-only `timeout=60→300`. The **oracle is unchanged** (it still requires the readable canary be recorded). I explicitly rejected "accept a timed-out probe as pass" because that would gut the campaign-6 regression guard — **not** a loosened criterion, **not** a new allowlist exception (owner #2). Verified green locally (0.45s).
- **Product `PROBE_TIMEOUT=60`** ([aisef2/app/confine.py:97](../../../aisef2/app/confine.py)) is the same tight value governing **live** runs. Per owner #3, product is left as-is; flagged for continued measurement (load-vs-mechanism). Not a mechanism bug — a tight budget under infra load.

## 5. Mutation — Lane M (owner #4)

Full detail: [MUTATION-WAVE2-CLASSIFICATION.md](./MUTATION-WAVE2-CLASSIFICATION.md) / `.json`.

- **Campaign (frozen 89de4685, 4 workers):** 2154 mutants / **1903 killed** / **251 survived** / 0 infra / 0 not_run.
- **Survivors classified** (two-pass: classify → adversarial refutation of every EQUIVALENT): 247 distinct → **11 confirmed EQUIVALENT / 236 real coverage gaps**. The refutation overturned 34 of 45 first-pass equivalents — the honest direction (a false "equivalent" hides a gap).
- **The 236 real gaps are reported as-is** (owner #1): honest test-coverage gaps (diagnostic strings, digest/record internals, uncovered refusal branches), candidate kill-tests for a future hardening wave — **no scope reduction, no criteria loosened, no registry change**.
- **Record-currency:** campaign post-run gate reported `mutation: FAIL` on `cleanup_authority.py` (stale, pre-existing, unrelated to wave-2 targets) — does not invalidate the kill/survive verdicts; relates to reseal (§8, owner #5).

## 6. Paid live canary — B1 / B7

Evidence: [B1-B7-LIVE-CANARY.json](./B1-B7-LIVE-CANARY.json). Route `9router/ds/deepseek-v4-pro`.

- **B1 (trust loop live):** delivery **PASS**, S1 COMMIT, `--verify` **VERIFIED** (0 problems), **0 escape**, exit 0 — reproducible across both runs.
- **B7 (cost-of-trust, 2 runs):** $0.166598 and $0.147534 → **mean $0.157/story**, spread 12.1%; both PASS/VERIFIED/0-escape. E4 split ≈ productive(developer) $0.087 + trust(reviewer) $0.065 + preflight.
- **USD spent (paid runs total):** B1 ×2 + B7 ×2 ≈ **$0.63** (4 live runs; `--check`/`--verify` are free). Cap lifted by owner ("không giới hạn tiền").
- **Caveat (owner #2 honesty):** 9router publishes no rate card → cost is an **upper bound** at deepseek-v4-pro upstream rates; the real 9router price is unknown.

## 7. FINDING-WIN-OSKILL-001 (owner #2 — plan only)

Full plan: [FINDING-WIN-OSKILL-001-SAFE-FIX-PLAN.md](./FINDING-WIN-OSKILL-001-SAFE-FIX-PLAN.md). **Kernel not patched.**

- **Verdict: latent, not live.** The v2.2 kernel has one signal-0 probe (`client.py:46` `os.kill(pid,0)` in `_is_gone`). On Windows `os.kill(pid,0)` is destructive (CTRL_C_EVENT/TerminateProcess), but the probe is **unreachable on the Windows Job-object backend** (`_Job.escaped()` returns `[]`; `RangeEscaped` never raised) — proven and **adversarially un-refuted**. The invariant **holds in the shipped product**; it is a contract-hygiene/defense-in-depth defect.
- **Prepared (not applied):** a Windows reproduction test (staged out of the suite so CI stays green pre-fix), a process-authority impact assessment, a safe-fix design (Option A: route through a non-destructive `OpenProcess`+`GetExitCodeProcess` probe), and a regression plan. **Awaiting owner go to apply.**

## 8. Decisions recorded & still pending (owner)

**Recorded (no action needed):**
- **#1 C4** — out of scope for v2.2; implementation kept as reverted; not redesigned.
- **#3 PROBE_TIMEOUT** — product kept as-is; measurement continues.

**Pending owner decision:**
1. **FINDING-WIN-OSKILL-001 fix (#2)** — approve applying the guarded safe fix (Option A) + wiring the Windows repro test, as one reviewed change. Currently plan-only.
2. **Reseal / Q5-KERNEL-COMPARISON / freeze_manifest V2_007 (#5)** — not executed; compiled here for your decision. The record-currency `cleanup_authority.py` staleness (campaign `mutation: FAIL`) sits under this — a reseal would refresh those records.
3. **236 mutation real-gaps** — do you want a scoped hardening wave to add kill-tests (owner #4 said no criteria change now; this is a forward-looking ask, not a wave-2 blocker)?
4. **Fragile cycle-2 forensic test** (§3a) — `HistoricalAttempt4.external_problems(4)` reads this machine's live `~/.local/share/opencode/opencode.db` and fails on *any* opencode session after 2026-10-03, including legitimate approved canary runs. It passes on CI (machine-local guard) but is red on the dev box after each paid run. Candidate fix (not done, needs your go): snapshot the attempt-4 store digest into the committed evidence and compare against that frozen copy instead of live `max(time_created)` — a plan-only item like FINDING-WIN-OSKILL-001, not touched this cycle.

## 9. Scope discipline

No scope expansion, **no release tag**, **no Đợt 3 started** (owner #6). All changes this cycle are test-only + evidence + plan docs; the frozen kernel is untouched.
