# FINDING-WIN-OSKILL-001 — authority-preservation assessment, regression coverage, Windows-proof method (owner #2)

Owner #2 (2026-11-06): *Option A approved in principle. Implement only after proving (a) the reproduction test runs on Windows, (b) process authority is preserved, (c) regression coverage exists. If the change touches an invariant or the frozen kernel, STOP and present for separate owner approval.*

This extends [FINDING-WIN-OSKILL-001-SAFE-FIX-PLAN.md](./FINDING-WIN-OSKILL-001-SAFE-FIX-PLAN.md). **The kernel is NOT patched.** Option A edits `aisef2/app/client.py` — the frozen kernel — so by owner #2's own condition this STOPS here for a separate approval. Below is the complete evidence package for that approval.

## A. The site and Option A (restated, exact)

`_is_gone(pid, proc)` ([aisef2/app/client.py:31](../../../aisef2/app/client.py)) decides whether an escapee that left the process range is **provably gone**. Its contract: return `True` only when the pid is confirmed absent; on any ambiguity (EPERM, unreadable table, success) return `False` → the caller **refuses the session**. The hazardous line is the per-pid fallback:

```python
os.kill(pid, 0)   # existence probe only; no signal is ever sent ...
```

On POSIX `kill(pid, 0)` is a read-only existence check — correct. On Windows `os.kill(pid, 0)` is **destructive**: `signal.CTRL_C_EVENT == 0`, so it routes to a console-control event, and on CPython ≤ 3.12 falls through to `OpenProcess` + `TerminateProcess(handle, 0)` — it terminates the pid it was asked only to probe (≥ 3.13-fix / 3.14 raise `OSError` instead). Either way it is never a safe probe.

**Option A:** keep the POSIX `os.kill(pid, 0)` branch; on Windows read liveness through the read-only probe already proven in the V1 kernel — `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION=0x1000)` + `GetExitCodeProcess == STILL_ACTIVE(259)` — the exact `aisef/control/state.py::pid_alive` pattern. `_is_gone` returns gone only when that probe confirms not-present; access-denied / ambiguous → alive → refuse side.

## B. (b) Process-authority preservation — the core of owner #2

Invariant at stake: **INV-MUTATION-AUTHORITY** — a liveness/probe operation must never expand destructive authority; kill/delete/release come only from an independent controller view.

- **Direction of change: authority is *reduced*, never expanded.** Current Windows behavior is a latent *destructive* capability (a probe that can `TerminateProcess`). Option A replaces it with a *query-only* handle (`PROCESS_QUERY_LIMITED_INFORMATION`, no `PROCESS_TERMINATE`). The post-fix code cannot signal or terminate anything. This is the strict-subset direction INV-MUTATION-AUTHORITY requires; Option A *removes* an accidental authority, which is why it is a hardening, not a new power.
- **Semantics preserved exactly.** `_is_gone`'s decision table is unchanged:
  | situation | current (POSIX intent) | Option A (Windows) | gone? |
  |---|---|---|---|
  | pid confirmed absent | `ProcessLookupError`/ESRCH | OpenProcess fails, not ACCESS_DENIED | **True** |
  | exists, not ours | EPERM → False | ACCESS_DENIED(5) → alive → False | False (refuse side) |
  | exists, ours, running | success → False | `STILL_ACTIVE` → False | False |
  | ambiguous/error | OSError → False | any doubt → alive → False | False (refuse side) |
  The conservative rule — *"treat as alive unless provably gone; a wrong 'dead' is the costlier mistake"* — is identical in both, so the escapee-grace refusal logic (`RangeEscaped` → re-check over `ESCAPEE_GRACE_S`) behaves exactly as before. No control decision widens.
- **No new authority surface.** `pid_alive` opens a query-limited handle and closes it; it never holds, inherits, or passes a handle with terminate rights. No journal/gate/seal path changes.

## C. (a) Windows reproduction — method and proof

The reproduction test is [win-oskill/repro_test_win_oskill.py](./win-oskill/repro_test_win_oskill.py): spawns a real child, calls `client._is_gone(child.pid, _Proc())` with `os.kill` **unmocked**, asserts the child **survives** and that a live pid is not reported gone. On Windows `process_table()` raises (no `ps`), so `_is_gone` takes exactly the `os.kill` fallback — the hazardous branch. It self-skips off Windows.

- **Expected on current (unfixed) kernel, Windows CPython ≤ 3.12:** RED — the probe terminates the child (reproduction).
- **Expected after Option A:** GREEN — the query-only probe leaves the child alive.

Because the test is RED-by-design on the current kernel, it must **not** go in the mandatory suite (it would make the `unit(windows-latest)` job red and violate owner #6). The proof runs through an **opt-in, manual** CI job (`workflow_dispatch` only, never on push) that runs just this one test on `windows-latest`: [.github/workflows/win-oskill-repro.yml](../../../.github/workflows/win-oskill-repro.yml). Dispatch: `gh workflow run win-oskill-repro.yml`. Its RED run is the reproduction evidence; its GREEN run after Option A is the fix proof. **The reproduction-run result will be captured and attached here before the Option-A approval is acted on.**

## D. (c) Regression coverage plan

On approval, applied as one reviewed change:
1. **Move** `repro_test_win_oskill.py` into `tests/v2/` as a permanent test (keeps the `@skipUnless(win32)` guard — green everywhere, meaningful on Windows). It is now a standing regression guard: it fails if anyone reintroduces a destructive probe on the escapee path.
2. **POSIX companion** in the same file: assert `_is_gone` still (i) reports a confirmed-absent pid as gone, (ii) reports a reused pid (different start time) as gone, (iii) reports an EPERM/exists-not-ours pid as **not** gone (refuse side) — pinning the decision table B above so Option A cannot regress the conservative semantics.
3. Retire the opt-in `win-oskill-repro.yml` once the test is in the mandatory suite (the `unit(windows-latest)` cell then runs it every push).

## E. STOP (owner #2 condition)

Option A modifies `aisef2/app/client.py` (frozen kernel). Per owner #2, this **stops here**. Deliverables ready for the separate approval: the exact diff (below), the authority assessment (B), the Windows reproduction harness + its RED evidence (C), and the regression plan (D). **Not applied.**

### Option-A diff (ready, NOT applied)
Replace the `os.kill(pid, 0)` try-block in `_is_gone` with a platform split: POSIX keeps `os.kill(pid, 0)` (ESRCH→gone, else→alive); Windows calls the `pid_alive`-pattern query-only probe and returns `gone = (probe says not-present)`, with every ambiguity → alive. Net diff ≈ 8 lines in one function; no signature, caller, invariant-registry, or journal change.
