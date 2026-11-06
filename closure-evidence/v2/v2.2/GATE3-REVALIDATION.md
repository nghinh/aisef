# Gate-3 REVALIDATION — AISEF v2.2 (owner gate-3 corrective round)

**VERDICT: both gate-3 FAIL causes CLEARED; every mandatory measure passes under the owner's
H1/H2-scoped ruling. The sealing record-currency tier stays red — a *byte-identical, pre-existing*
wave-divergence set that this corrective did **not** touch (zero failures added). That is reported as the
logged OPEN CONDITIONS, **not** a full-sealing PASS. Gate-3 acceptance and the separate wave-2 reseal are
owner decisions. No tag v2.2, no publish, no Đợt-3.**

Measured 2026-11-07 (+07). HEAD `a9a93305`.
- Commit 1 `24e74477` (aisef2 tree `d3352a7e`) — owner #1 + #2: the false-gone fix + the real post-H2 test seam.
- Commit 2 `a9a93305` (aisef2 tree `ac7c1705`) — owner #4: scoped, append-only probe-calibration re-derive.

Supersedes `GATE3-ACCEPTANCE.md` (the e8a76db0 FAIL/STOP measurement). Prior state: windows-3.11 unit had a
new H1/H2-scope failure + a latent in-scope false-gone gap; ubuntu-3.12 flaked. The owner approved fixing
both (directive: Windows test-seam APPROVED; false-gone fix APPROVED WITH CONDITIONS; ubuntu-3.12 RE-RUN FIRST).

---

## 1. Mandatory measures (owner gate-3 list)

| # | Measure | Result |
|---|---------|--------|
| 1 | Full suite RAW (local darwin) | ✅ **GREEN** — `Ran 8077 tests → OK (skipped=57)` in 4511s, exit 0. No RunRefused, no calibration-admission cascade. |
| 2 | Mandatory CI Ubuntu / Windows / macOS (run `42253171509` @ `a9a93305`) | ◐ unit tier **all green**; sealing red (§4). ubuntu 3.11/3.12/3.13/3.14 ✅, **windows 3.11 ✅ (the fix)**, macos 3.12 ✅, lint ✅, wheel ✅, **sealing ❌ (pre-existing wave-divergence, unchanged — §4)**. |
| 3 | Sealing PASS (H1/H2-scoped, per owner ruling) | ◐ **SCOPED PASS** — the H1/H2-touched items admit (re-derived calibrations current; the round-3 H1/H2 destructive sites ledgered). The 21 red items are the pre-existing wave-divergence OPEN CONDITIONS, **byte-identical to the gate-3 baseline set** (§4). Not a full-sealing PASS. |
| 4 | Targeted mutation + H1/H2 regression | ✅ regression **35 OK**; mutation **8/8 KILLED** (whole module) **and 8/8 KILLED by the new tests alone** (§3). |
| 5 | `--verify` + calibration bindings + provenance | ✅ `release_calibration --check` PASS, `freeze_manifest --check` PASS, `v1_evidence_guard --check` PASS, `ruff` clean. |

---

## 2. The two gate-3 FAIL causes — both cleared

### 2a. Windows 3.11 unit — `test_an_eperm_from_kill_is_not_taken_for_gone` — FIXED (owner #1)
- **Was:** the test fault-injected `client.os.kill`→EPERM. Post-H2, `pid_alive` on Windows routes through the
  `OpenProcess`/`GetExitCodeProcess` branch, which never calls `os.kill`; the injected EPERM was inert, so the
  real probe read absent pid 4242 as gone and the test failed on Windows only — a real regression masked by the
  calibration cascade until the reseal cleared it.
- **Now:** the test exercises the **real post-H2 seam on both platforms** — it asserts the pure Windows decision
  `_win_liveness(...)` directly, drives `_is_gone` through a mocked `pid_alive`, and keeps the POSIX `os.kill`
  EPERM case under `if os.name == "posix"`. Added `WinLivenessDecision` (8 cases: alive / genuinely-gone /
  access-denied / resource-exhaustion / unknown-failure / unreadable-exit / exited-259 / the exact-87 boundary)
  and `PidAlivePosixSeam` (5 cases, `skipUnless(posix)`). **No skip, waive, or loosened assertion.**
- **CI:** windows-3.11 unit = **SUCCESS** at `a9a93305`.

### 2b. Ubuntu 3.12 — `test_what_is_measured_decides_not_the_name_of_the_tool` — FLAKE, re-run GREEN (owner #3)
- Per directive: re-ran CI on the **same code candidate**, `PROBE_TIMEOUT=60` and the sandbox mechanism
  **unchanged** — no timeout raised, no allowance added, no test change.
- **Result:** ubuntu-3.12 unit = **SUCCESS**. The earlier failure (bubblewrap probe exceeding 60s on a loaded
  runner, 3174s suite) was **infra-load flake, not a regression**. `confine.py` was untouched by H1/H2 and the
  reseal, consistent with a load artifact. No change proposed.

---

## 3. The fix detects the deviation (owner #1: "not merely RED→GREEN"; owner #2: fail-closed)

**Decision-table change is one edit:** `_win_liveness` concludes GONE **only** on `ERROR_INVALID_PARAMETER (87)`
("no such pid"). Access-denied (5), resource exhaustion (`ERROR_NOT_ENOUGH_MEMORY 8`, `ERROR_NO_SYSTEM_RESOURCES
1450`), every unknown `OpenProcess`-NULL error, and an unreadable exit code all **fail closed to ALIVE** —
honoring the function's own invariant ("Ambiguity always reads as ALIVE, never dead"). The old code mapped only
`==5` to alive, so a genuinely-live process under quota exhaustion could be read gone (a false-gone = a
weakening). The `GetExitCodeProcess` branch is carried over verbatim; **no signal/kill authority added**, decision
table otherwise unchanged (confirmed in §4: 0 new destructive sites).

**Targeted mutation — 8 mutants, each a distinct way to break the guard:**

| | Mutant | Whole module | New tests **alone** |
|---|--------|:---:|:---:|
| W1 | `!=87` → `==87` | KILLED | KILLED |
| W2 | revert to the old `==5` false-gone bug | KILLED | KILLED |
| W3 | always ALIVE | KILLED | KILLED |
| W4 | always GONE | KILLED | KILLED |
| W5 | invert the `STILL_ACTIVE(259)` check | KILLED | KILLED |
| W6 | unreadable exit code → GONE | KILLED | KILLED |
| P1 | POSIX `ProcessLookupError` → ALIVE | KILLED | KILLED |
| P2 | POSIX other `OSError` → GONE | KILLED | KILLED |

**8/8 KILLED by the new/retargeted selectors in isolation** (`WinLivenessDecision`, `PidAlivePosixSeam`,
`test_an_eperm_from_kill_is_not_taken_for_gone`) — so the new tests themselves catch every deviation, including
the exact old bug (W2); they are not riding on a pre-existing sibling.

---

## 4. Sealing impact & record-currency (owner #4: STOP on any new out-of-scope record or unexplained discrepancy)

**STOP criterion NOT triggered.** Both parts proven, not assumed:

**(a) No new record out of scope.** The only record this round created is
`closure-evidence/v2/v2.1/V2.1.0-PROBE-CALIBRATIONS-3.json` — in-scope, append-only, exactly what the approved
scoped re-derive emits. The prior three calibration records are byte-untouched; 2.0 / cycle-2 records never
written (the suite's own refuse-on-exist guards fire as expected in the log).

**(b) No unexplained discrepancy — the sealing red is byte-identical to the gate-3 baseline.**

The sealing job failing-test set at HEAD (`42253171509`) vs. the gate-3 baseline (`42228222348` @ e8a76db0):

```
both:  FAILED (failures=21)
both:  same 18 unique test ids, same multiplicities
         3× test_historical_records_read_as_before
         3× test_every_checker_has_a_committed_fixture_that_fails_it_for_the_named_reason
         1× each: test_this_tree_passes_and_every_site_is_ledgered,
                  test_INV_MUTATION_AUTHORITY_...are_ledgered,
                  test_every_checker_is_calibrated_and_the_committed_record_is_current,
                  test_Q5_19_the_kernel_comparison_record_binds_this_tree,
                  test_the_committed_ruling_is_what_this_tree_derives,
                  test_15 / test_15b (C2 orchestration conformance),
                  test_P5_8 / test_on_this_tree_the_committed_proposal_is_current (PLAN-V2.2),
                  test_the_V2_007_exception..., and the rest.
only change:  test count 8061 → 8074  = the +13 new H1/H2 tests, all passing (failures held at 21)
```

These 21 are the standing wave-divergence OPEN CONDITIONS — stale records against the wave-2 delta
(CONFORMANCE-RULING, Q5-KERNEL-COMPARISON, PLAN-V2.2 proposal, C2 orchestration conformance, mutation
record-currency for `journal/fold.py`, `runtime/run_scope.py`, `invariants/registry.py`, checker-calibration
fixtures). They were red before this corrective and are red after; the re-derive re-pointed only the 4 probe
digests and does not re-write those wave records (a separate owner-gated reseal).

**Destructive authority — 0 new sites.** HEAD lists the same **7** unledgered destructive sites as the gate-3
baseline. Five are in files this round never touched (`test_v21_pw_lineage_continue.py`,
`test_v22_client_pin_fence.py`, `test_v22_hardening_p1_run_pin_fence.py`). The two in the edited PL7 file are
pre-existing `addCleanup(lambda: (p.kill(), p.wait()))` sites: `p.kill(` count is **2 at baseline and 2 at HEAD**,
merely line-shifted +7 (53→60, 108→115) by the new import block. The `os.kill(pid, 0)` strings the new
`PidAlivePosixSeam` docstring/skip-reason add are text, not destructive calls — correctly absent from the
checker's list.

---

## 5. Remaining risks & OPEN CONDITIONS (reported separately per owner #5)

1. **Sealing wave-divergence (21 items)** — pre-existing, unchanged by this corrective. Clearing them is the
   separate wave-2 reseal (re-write the stale records on the current tree), which is **not** in this corrective's
   approved scope. Until the owner rules on that reseal, this is **not** a full-sealing PASS.
2. **Residual Windows exposure, now bounded.** The false-gone gap the adversarial pass surfaced is closed in code
   and pinned by tests, but Windows `OpenProcess` error semantics are not exercised against a live Win32 kernel in
   CI (unit CI mocks the seam; `win-oskill-repro` covers the `os.kill` reproduction only). The fix is
   conservative (fail-closed) and mutation-pinned, so the risk is a *missing positive confirmation on real
   Windows*, not a known defect.
3. **No release action taken.** No tag v2.2, no publish, no Đợt-3. The calibration re-derive is local + pushed to
   the branch only.

---

## Appendix — commands & artifacts
- Full suite log: `scratchpad/fullsuite_corrective.out` → `Ran 8077 tests … OK (skipped=57)`.
- CI run `42253171509` (HEAD) vs baseline `42228222348`: `gh run view … --json jobs` / `--log-failed`.
- Mutation harnesses: `scratchpad/mut_falsegone.py` (whole module, 8/8), `scratchpad/mut_isolate_newtests.py`
  (new selectors alone, 8/8); both mutate `aisef2/runtime/process_range.py` in place and restore in `finally`
  (verified clean after).
- Guards on HEAD: `release_calibration.py --check` PASS, `freeze_manifest.py --check` PASS,
  `v1_evidence_guard.py --check` PASS, `ruff check` clean.
