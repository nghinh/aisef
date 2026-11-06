# FINDING-WIN-OSKILL-001 — reproduction result & corrected scope (owner #2 STOP)

Owner #2 (2026-11-06, CONDITIONAL GO): *Option A approved with conditions — Windows reproduction RED on old code and GREEN after fix; no process-authority expansion; decision table + invariants preserved; full regression + mutation targeted pass. Apply the kernel patch only after the preconditions are proven. **If anything changes beyond the presented plan, STOP and request approval again.***

**The reproduction ran, and it changed the plan. STOPPING. No kernel patch applied.** Below is the measured result and the corrected (larger) fix scope for re-approval.

## 1. Reproduction ran RED — but not where the finding predicted

Opt-in job `win-oskill-repro.yml` on `windows-latest`, run [42172469919](https://github.com/nghinh/aisef/actions/runs/42172469919) at commit `ddf1b3d2` (old `_is_gone`): **the `reproduce` job failed in 35s** — so the test is RED on old code, as required. But the Windows log shows the failure is an **ERROR, not the destructive-`os.kill` assertion**:

```
test_is_gone_must_not_terminate_a_live_escapee_on_windows ... ERROR
  File "...\win-oskill\repro_test_win_oskill.py", line 45, in test_is_gone...
subprocess.CalledProcessError: Command '['ps', '-A', '-o', 'pid=,ppid=,pgid=,stat=,command=']' returned non-zero exit status 1.
```

Line 45 is the `client._is_gone(child.pid, _Proc())` call. `_is_gone` first calls `process_table()`; on Windows that runs `ps` ([process_range.py:99](../../../aisef2/runtime/process_range.py), `check=True`). On the runner a `ps` exists and exits 1, raising `subprocess.CalledProcessError` — which the module documents as *propagating* ([process_range.py:64](../../../aisef2/runtime/process_range.py)). `_is_gone` catches only `(ProcessTableError, OSError, UnicodeDecodeError)`, so `CalledProcessError` **propagates uncaught** and the test errors **before the `os.kill` branch is ever reached**.

## 2. What this means for Option A

Option A fixes only the `os.kill(pid, 0)` fallback. But on this Windows path, control never reaches that fallback — it dies earlier at `process_table()`. **So Option A alone would leave the reproduction RED** (it would still error at `process_table`). The owner's precondition "GREEN after fix" cannot be met by the presented plan. The fix must be larger than presented → re-approval (owner #2's own stop condition).

## 3. There are TWO latent hazards on the Windows `_is_gone` path, not one

Both are latent/unreachable in production (the FINDING's original verdict stands: `_Job.escaped()` returns `[]` on the Windows Job backend, so `_is_gone` is only called from `except RangeEscaped`, which never fires on Windows). The direct-call reproduction forces the path and exposes both:

- **H1 — `process_table()` failure is uncaught.** On Windows `ps` is absent or fails. If it **fails** (exits non-zero, `ps` present) → `CalledProcessError` → uncaught → `_is_gone` raises (this is what the runner hit). `_is_gone`'s `except` does not include `subprocess.SubprocessError`.
- **H2 — `os.kill(pid, 0)` is destructive on Windows.** Only reached if `process_table()` raises something `_is_gone` **does** catch — i.e. if `ps` is **absent** → `FileNotFoundError` (an `OSError`) → caught → `present=None` → falls to `os.kill(pid, 0)`, which on Windows routes to a console-control/`TerminateProcess` path (the original finding). So which hazard triggers depends on whether the Windows host has a failing `ps` (H1) or no `ps` (H2).

Option A addresses **H2 only**. A Windows-correct `_is_gone` needs **both**: catch the `process_table()` failure (add `subprocess.SubprocessError` to the caught set, or treat any `process_table` failure as "table unreadable → fall through to the safe probe") **and** replace the destructive `os.kill` with the query-only probe (Option A).

## 4. Revised fix plan (for re-approval — NOT applied)

1. **H1:** in `_is_gone`, broaden the `process_table()` guard so a `ps` failure (`subprocess.SubprocessError`, incl. `CalledProcessError`) is treated like any other unreadable table — `present = None`, fall through — never an uncaught raise.
2. **H2 (Option A, unchanged):** replace the `os.kill(pid, 0)` fallback with a platform split — POSIX keeps `os.kill(pid, 0)`; Windows uses the query-only `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetExitCodeProcess == STILL_ACTIVE(259)` probe (the `aisef/control/state.py::pid_alive` pattern, **inlined** — no new `aisef2`→`aisef` dependency, which would itself be a change beyond scope).
3. **Reproduction (revised):** the current repro cannot isolate H2 on a host whose `ps` fails (it stops at H1). Make it deterministic: mock `process_table` to raise `ProcessTableError` so execution reaches the `os.kill`/probe branch, and assert the live child survives and `gone is False`. Keep the end-to-end Windows variant for H1. Both RED on old code, GREEN after the combined fix.
4. **Regression (c):** move the repro into `tests/v2/` (skipUnless win32) + a POSIX companion pinning the decision table (confirmed-absent → gone; reused pid → gone; EPERM/exists-not-ours → not gone). Retire the opt-in job once in the mandatory suite.

## 5. Authority preservation — still holds for the revised fix

Both H1 and H2 fixes **reduce or preserve** authority, never expand it:
- H1 only broadens an *exception catch* (a `ps` failure becomes "unreadable table" instead of an uncaught raise) — no new capability, no signalling.
- H2 replaces a latent *destructive* probe with a *query-only* handle (`PROCESS_QUERY_LIMITED_INFORMATION`, no `PROCESS_TERMINATE`) — strict authority reduction. INV-MUTATION-AUTHORITY satisfied; `_is_gone`'s decision table (absent→gone; exists-not-ours→not-gone; running→not-gone; ambiguous→not-gone, refuse side) is preserved exactly.

## 6. STOP

The reproduction proved the fix scope exceeds the presented Option A (H1 is new). Per owner #2, the kernel is **not** patched; this corrected finding + revised plan is presented for separate approval. The RED-on-old evidence is captured (run 42172469919). GREEN-after-fix, full regression, and mutation-targeted will be produced once the revised plan is approved.

## 7. IMPLEMENTED — owner round-3 APPROVED WITH CONDITIONS (2026-11-06)

Owner round-3 #1 approved the extended H1+H2 fix. Applied as the smallest diff that meets every condition; **nothing beyond H1/H2**.

**H1 — `process_table()` failure never distorts the verdict.** [client.py `_is_gone`](../../../aisef2/app/client.py): the guard now catches `subprocess.SubprocessError` alongside `(ProcessTableError, OSError, UnicodeDecodeError)`, so a `ps` that exits non-zero (`CalledProcessError`) is treated as an unreadable table — `present = None`, fall through to the per-pid probe — never an uncaught raise. An observation failure is **not** evidence of exit; UNKNOWN does not become GONE.

**H2 — the fallback probe is read-only on both platforms.** The bare `os.kill(pid, 0)` is replaced by [`process_range.pid_alive`](../../../aisef2/runtime/process_range.py): POSIX keeps `os.kill(pid, 0)` (non-destructive there); Windows uses a query-only `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetExitCodeProcess == STILL_ACTIVE(259)` handle — **no `PROCESS_TERMINATE`**, mirroring this module's own Job backend (no new `aisef2`→`aisef` dependency). `_is_gone` returns `not pid_alive(pid)`.

**Decision table preserved exactly** (verified against the unchanged `test_v21_pl7_session_teardown.py`): provably-absent → gone; reused pid (different start time) → gone; running / not-ours (EPERM) / any ambiguous or unreadable observation → NOT gone (the refuse side). `client.os` and `process_range.os` are the same module object, so the existing fault-injection tests that patch `client.os.kill` still reach the probe.

**Authority preserved/reduced (INV-MUTATION-AUTHORITY).** The destructive-authority checker derives the new `pid_alive` site as `os.kill(pid, 0)` → **`LIVENESS_PROBE_SIGNAL_0`** (literal-0 second argument) — the same safe classification as the existing ledgered probes; H2 removes a latent *destructive* call and adds only a *query* handle. No signal/kill authority is added.

**Evidence conditions:**
- **Windows RED-before:** run [42172469919](https://github.com/nghinh/aisef/actions/runs/42172469919) at `ddf1b3d2` (the repro erred at `process_table()`/H1). **Windows GREEN-after:** `win-oskill-repro.yml` re-dispatched at the fixed commit (same file, RED→GREEN).
- **POSIX H1 RED→GREEN mechanism** reproduced locally: the old except-set lets `CalledProcessError` propagate; the new set catches it.
- **POSIX + Windows regression:** `tests/v2/test_v22_win_oskill_is_gone.py` (new mandatory-suite guard: H1 fall-through, H2 read-only probe + decision table, Windows non-destructive case) + the unchanged `_is_gone` teardown/range-release suites — green. Full suite + mutation-targeted reported on the RC.

**Deferred to the controlled reseal (owner #2/#4, NOT a hand-edit now):** the `@sealing`-gated destructive-authority ledger (`validation/v2/destructive_sites.json`) must, when regenerated at reseal, gain three rows — `aisef2/runtime/process_range.py::pid_alive os.kill` → `LIVENESS_PROBE_SIGNAL_0`, and the new test's `child.kill`/`child.terminate` → `TEST_CREATED_HANDLE`. No stale `client.py` row exists to drop (the old site was never in the committed ledger — the record is pre-existing-stale, dossier §4). The mandatory (non-sealing) suite does not gate on this.

## 8. Acceptance measurement (owner round-3 #1) — RC `1c42aaad`, measured 2026-11-06

**H1/H2 own guards — NOT weakened (the substance of owner #1):**
- **Windows RED→GREEN:** run [42172469919](https://github.com/nghinh/aisef/actions/runs/42172469919) (`ddf1b3d2`, erred at `process_table()`) → run [42199837106](https://github.com/nghinh/aisef/actions/runs/42199837106) (`1c42aaad`, `✓ reproduce 38s`).
- **POSIX regression:** `tests/v2/test_v22_win_oskill_is_gone.py` and `tests/v2/test_v21_pl7_session_teardown.py` (incl. `IsGoneConfirmation`) both **PASS** in the full run — the `_is_gone` decision table is preserved.
- **Mutation targeted — 6/6 KILLED** (green baseline, residual-clean `git diff --stat aisef2/` empty): M1 drop `subprocess.SubprocessError` (H1), M2 drop `not pid_alive` (H2), M3 `pid<=0` flip, M4 `ProcessLookupError` flip, M5 alive-return flip, M6 `OSError` flip. Harness `scratchpad/mut_h1h2.py`, green-baseline-first, reverts each mutant.
- **No regression in the changed code:** zero failing tracebacks enter `aisef2/app/client.py` or `aisef2/runtime/process_range.py`.

**Full RAW suite — RED, but PRE-EXISTING and not an H1/H2 defect (STOP at this gate, owner #5):**
- Local POSIX full run (`owned_run.py -- unittest discover -s tests`): 7994 ran, **67 F / 46 E / 57 skip**, 3913 s. Owned-process ledger clean (`escaped=0 released_empty=True`).
- **Root cause = calibration/record currency, not logic.** 60+ failures/errors are one root: `RunRefused: the plan is not admitted (RFC §12) … no ProbeCapabilityCalibration for probe.python_callable_v2@… executing d0c434d1d1cd`. A calibration admits only when its `probe_digest == executing(probe)` ([calibration.py `executing`/`calibration_for`](../../../aisef2/probe/calibration.py)); any change to `aisef2/` bytes moves the executing digest, so the shipped records (last re-derived at `fce3d7b7`, v2.1 candidate) no longer admit → admission refuses → cascade (incl. `test…continue_integrity` returning `1`=refused where it expected `-9`=killed; setUpModule/setUpClass ERRORs at `R.execute`).
- **Pre-existing on master:** `tests.yml` is `failure` on `ddf1b3d2` (parent, pre-H1/H2) and on **every** wave-2 commit back to 2026-11-04 — the raw master suite has been calibration-stale since wave-2 (`9d1c1314`) changed kernel bytes without re-deriving calibrations. H1/H2 moved the executing digest again (to `d0c434d1d1cd`) but added **no new failure class**. On master the raw suite is red by design; only the release tag applies the scoped qualification (`release_qualify.py`).
- **Cure = owner gate #2 reseal.** Re-deriving the shipped probe calibrations + records on the RC bytes (`d0c434d1d1cd`) is exactly the reseal's change-manifest / before-after-digest step; after it the raw suite and the tag-scoped qualification go green. This is the documented `aisef2/`-byte-change ⇒ calibration-stale coupling, not a weakened guard.
