# Gate-3 final-acceptance measurement — AISEF v2.2 (owner Option A, H1/H2-scoped reseal)

**VERDICT: FAIL → STOP at Gate-3.** Gate-1 is **not** fully closed. The substantive gate-1 fix (the
calibration-admission cascade) is proven cleared, and the H1/H2 guards are not weakened for their threat
model, but the mandatory tri-OS CI does **not** uniformly pass: the Windows unit tier has one **new,
H1/H2-scope** failure that cannot be waived, and an adversarial verification surfaced one **latent, in-scope**
guard gap. Both trace to the same root — the Windows liveness-probe seam is untested. Per owner directives
#3 ("only when every mandatory measure PASSES may Gate-1 be fully closed"), #4 ("no waiver to hide a new
error", "don't loosen tests") and #5 ("stop at any failing gate, present to owner"), this stops here for an
owner ruling. No tag, no publish, no Đợt-3, no unilateral code/test change.

RC = reseal commit `edc18a8d` (aisef2 tree `9dcddb1b`). Measured 2026-11-06.

## 1. Mandatory measures (owner gate-3 list)

| # | Measure | Result |
|---|---|---|
| 1 | Full suite RAW (re-run) — local darwin | ✅ **GREEN** `Ran 8064 tests → OK (skipped=57)`; 0 RunRefused, 0 calibration-admission (was 67F/46E pre-reseal). Gate-1 OPEN CONDITION cleared. |
| 2 | Mandatory CI Ubuntu / Windows / macOS (run `42228222348`) | ❌ **FAIL** — see §2. ubuntu 3.11/3.13/3.14 ✅, macos 3.12 ✅, lint ✅, wheel ✅; **ubuntu 3.12 ❌ (flake)**, **windows 3.11 ❌ (new, H1/H2-scope)**, sealing ❌ (OPEN CONDITIONS). |
| 3 | Sealing PASS (H1/H2-scoped, per owner ruling) | ◐ **SCOPED PASS** — H1/H2-touched sealing items green (re-derived calibrations admit; the 7 round-3 destructive rows ledgered). The wave-divergence items (CONFORMANCE-RULING, Q5-KERNEL-COMPARISON) + 7 pre-existing destructive rows remain red = the **logged pre-existing OPEN CONDITIONS**, not waived. |
| 4 | Targeted mutation + H1/H2 regression | ✅ 6/6 KILLED (resealed tree, green baseline); `Ran 24 OK (skipped 4)`. |
| 5 | `--verify` + calibration bindings + provenance | ✅ offline trust-loop/`--verify` green; `release_calibration --check` PASS; `freeze_manifest --check` + `v1_evidence_guard --check` PASS (historical byte-identical). |

## 2. The two unexpected CI unit failures (each a single test)

### 2a. Windows 3.11 — `test_v21_pl7_session_teardown.IsGoneConfirmation.test_an_eperm_from_kill_is_not_taken_for_gone` — NEW, H1/H2-SCOPE, NOT WAIVABLE
```
tests/v2/test_v21_pl7_session_teardown.py:118
    self.assertFalse(client._is_gone(4242, Proc(4242, 1, None, None, "x")))
AssertionError: True is not false
```
- **Root cause.** The test fault-injects by mocking `client.os.kill`→`PermissionError(EPERM)`. On POSIX, `pid_alive` (process_range.py:150-156) calls `os.kill(pid,0)` on the same `os` module object, so the mock bites → EPERM → alive → `_is_gone`=False → **passes** (darwin + ubuntu all versions). On Windows, H2 routes `pid_alive` through the `os.name=="nt"` `OpenProcess`/`GetExitCodeProcess` branch (process_range.py:132-149), which **never calls `os.kill`** — the injected EPERM is inert, the real probe reads absent pid 4242 as gone → `_is_gone`=True → `assertFalse(True)` **fails**. The sibling `test_an_esrch_from_kill_on_an_absent_pid_is_gone` (same seam) passed on Windows, confirming the seam, not the guard, is the issue.
- **Baseline — H2 introduced it.** Windows unit 3.11: parent `ddf1b3d2` = **SUCCESS** → RC `1c42aaad` = **FAILURE** (43F+1E = the calibration cascade + this one) → reseal `edc18a8d` = **1 FAILURE** (reseal cleared the cascade; this survives).
- **Corrects Gate-1.** The earlier "Windows RED→GREEN" was the dedicated `win-oskill-repro` workflow (which tests `test_v22_win_oskill_is_gone`). The full `tests` workflow's Windows **unit tier** regressed GREEN→RED at H2 on this one test; that regression was masked by the calibration cascade until the reseal cleared it.
- **Not a production weakening (threat model).** The real Windows path reads ACCESS_DENIED (5) and all handle/exit-code ambiguity as **alive** (process_range.py:142,146,147) and drops the destructive signal-0 the old `os.kill(pid,0)` carried — a net safety improvement. See §3.
- **Classification.** NEW failure, caused by the H2 change, within H1/H2 scope → **not** a pre-existing OPEN CONDITION. Must not be waived or hidden by loosening the test.

### 2b. Ubuntu 3.12 — `test_v21_confine.FailClosed.test_what_is_measured_decides_not_the_name_of_the_tool` — INFRA FLAKE
```
test_v21_confine.py:513  self.assertIn(want, rep["problems"])
AssertionError: 'a file of the run directory was readable' not found in
  ['the sandbox did not run the probe (exit None): TimeoutExpired: timed out after 60 seconds', ...]
```
- **Root cause.** `confine.py:376-379` runs the probe under `subprocess.run(timeout=PROBE_TIMEOUT=60)`; on a slow/loaded runner (this suite took 3174s) the bubblewrap sandbox exceeded 60s → `TimeoutExpired`. The failing test hard-asserts the probe-ran problems and, unlike its **sibling** at `test_v21_confine.py:547-554` which tolerates this exact timeout under CI load, has no timeout tolerance.
- **Independent of this work.** Passed on ubuntu 3.11/3.13/3.14, macos 3.12, and the local darwin full suite. `git show 1c42aaad edc18a8d` touched **neither** `confine.py` nor the `process_table`/sandbox path (reseal touched only `calibrations.py`, `destructive_sites.json`, a calibration record). **Flake / pre-existing test-robustness gap**, not a defect of the reseal or H1/H2. A re-run is expected to pass.

## 3. Adversarial verification of the "guard not weakened" claim (5 reviewers)
Workflow `wf_078c3fa2-3f7`. Claim A (Windows guard not weakened): **CONFIRMED ×2, REFUTED ×1**. Claim B (ubuntu-3.12 flake): **CONFIRMED ×2** (unanimous).

All three Claim-A reviewers agree on the facts:
- **Upheld (threat model).** For an escapee the kernel itself spawned (a developer child, same session, still running), `OpenProcess(0x1000)` succeeds → `GetExitCodeProcess`→ `STILL_ACTIVE(259)` → **alive**; an access-denied live process → `ERROR_ACCESS_DENIED(5)` → **alive** (process_range.py:142). The destructive signal-0 is gone. H2 did **not** weaken `_is_gone` for its threat model — it is strictly safer.
- **LATENT IN-SCOPE GAP (the dissent, conceded by the other two as a residual caveat).** `process_range.py:142` maps **only** `ERROR_ACCESS_DENIED(5)` to alive; **every other** `OpenProcess`-NULL error → gone. This contradicts the function's own docstring invariant (process_range.py:128-129: *"Ambiguity always reads as ALIVE, never dead: a wrong 'dead' is the costlier mistake here"*). Under resource/quota exhaustion (`ERROR_NOT_ENOUGH_MEMORY(8)`, `ERROR_NO_SYSTEM_RESOURCES(1450)`) a **genuinely live** process can yield a non-5 error → `pid_alive`=False → `_is_gone`=True → a live escapee counted gone → session keeps its outcome (a false-gone = a weakening). This path is **untested** (the suite fault-injects the POSIX `os.kill` seam only — the same coverage hole behind 2a). `ERROR_INVALID_PARAMETER(87)` genuinely means "no such pid" and correctly reads gone, so it is not part of the hole. Mitigations noted but not relied on: `_release_session` re-polls `_is_gone` over `ESCAPEE_GRACE_S` (a transient would have to coincide across all escapee pids in one poll); and Windows `ProcessRange` may use a job-object no-breakaway model that rarely raises `RangeEscaped` (unconfirmed — bounds exposure if true).

## 4. Root cause tying 2a + 3 together, and the owner decisions

Both 2a (Windows CI failure) and the §3 latent gap have **one root: the Windows `OpenProcess` liveness seam has no direct test coverage.** The only test that "covers" EPERM-not-gone injects the POSIX `os.kill`, which the Windows path does not use.

**Decisions for the owner (I will not act unilaterally in this gated flow):**
1. **Windows test seam (2a).** Fix the test to exercise the real Windows seam (fault-inject `pid_alive`/`OpenProcess`, not `os.kill`; or `skipUnless(os.name=="posix")` the `os.kill` injection and add an nt-seam case). This **strengthens** coverage and turns Windows CI green — it does not loosen. It is a test-only change within H1/H2 scope. Approve?
2. **Latent guard gap (§3).** Optionally tighten `process_range.py:142` to honor its own invariant — treat only "no such pid" (`ERROR_INVALID_PARAMETER 87`) as gone and every other `OpenProcess` failure as **alive** — closing the resource-exhaustion false-gone. This is a ~1-line guard change to the H2 code. Approve, defer as a logged finding, or rule out-of-scope?
3. **Ubuntu 3.12 flake (2b).** Accept as a pre-existing flake (CI re-run to confirm green), or additionally harden the brittle test to tolerate the sandbox timeout like its sibling?

Until an owner ruling: Gate-1 stays open on the Windows unit tier; Gate-3 is not a PASS; no FINAL RELEASE READINESS report is issued. Boundary held: no tag v2.2, no publish, no Đợt-3.
