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
