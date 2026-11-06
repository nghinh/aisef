# FINDING-WIN-OSKILL-001 — Safe-fix plan

**Status: PLAN ONLY — NOT APPLIED. The v2.2 kernel is frozen; no code in `aisef2/` is changed by this document.**
Prepared under owner decision #2 (2026-11-06): *analyze and prepare a safe fix — Windows reproduction test, process-authority impact, regression plan — but do not patch the kernel before the plan is tabled.*

Date: 2026-11-06 · Branch: master · Analysis: read-only, 6-agent workflow `wf_472215a4-623` (4 analysis + 2 adversarial refutation), both refutations **failed** (claims survived).

---

## 1. The finding

`aisef2/app/client.py:46` (helper `_is_gone`) probes process liveness with a bare
`os.kill(pid, 0)`, documented as *"existence probe only; no signal is ever sent."*
That contract is **true on POSIX and false on Windows**: CPython's `os.kill` has no `kill(2)`
syscall to call, so `os.kill(pid, 0)` on Windows is **destructive or error — never a safe probe**.

## 2. Windows semantics of `os.kill(pid, 0)` (authoritative, version-aware)

`signal.CTRL_C_EVENT == 0`, so `os.kill(pid, 0)` enters CPython's console-control branch
(`GenerateConsoleCtrlEvent(0, pid)`), **not** a "check-only" path:

- **CPython ≤ 3.12** (and 3.13 before the GH-128937 backport, ~Feb 2025): for an ordinary pid
  that is not a process-group leader sharing the caller's console, `GenerateConsoleCtrlEvent`
  fails and the code **falls through to `OpenProcess(PROCESS_ALL_ACCESS)` + `TerminateProcess(handle, 0)`**
  — the target is **unconditionally terminated with exit code 0**.
- **CPython ≥ 3.14 / 3.13.x post-fix**: the console branch now `return`s on failure, so sig 0 no
  longer reaches `TerminateProcess`; instead it either delivers a real **Ctrl+C** to the target's
  console process group (can terminate it) or **raises `OSError`**. Still never a liveness probe.

Net: on **every** deployed CPython, `os.kill(pid, 0)` on Windows can kill the target or raise —
it never returns the POSIX "exists / permission" answer. Sources:
`https://docs.python.org/3/library/os.html#os.kill` ("Any other value for sig will cause the
process to be unconditionally killed by the TerminateProcess API, and the exit code will be set to sig");
CPython `Modules/posixmodule.c` `os_kill_impl` (v3.12.0 confirmed by read); CPython PR gh-58689 /
GH-128932 / GH-128937 (the 3.13 error-handling fix). The repo already documents this hazard:
`validation/p12_watchdog.py:84` ("`os.kill(pid, 0)` is NOT a probe on Windows (it can terminate the process)"),
`tests/hardening/adapters/test_conformance.py:135`, `tests/test_meta.py:462`.

## 3. Site inventory

| Site | Tree | Kind | Note |
|---|---|---|---|
| `aisef2/app/client.py:46` | **v2.2 kernel** | `os.kill(pid, 0)` existence probe | **the only signal-0 probe in `aisef2/`**; subject of this finding |
| `aisef/control/state.py:73` | V1 legacy | `os.kill(pid, 0)` | POSIX **fallback only** — Windows takes an earlier OpenProcess/GetExitCodeProcess branch (`state.py:61–71`); already safe |
| `aisef/harness/process_owner.py:153, :164` | V1 legacy | `os.killpg(pgid, 0)` | guarded POSIX-only (`if sys.platform=="win32": return []`, :148) — already safe |

All other `os.kill*` in `aisef2/` send real signals, not signal 0 (`process_range.py:178, :189`,
`range_anchor.py:39`) and are correctly POSIX-gated.

## 4. Reachability on Windows — **UNREACHABLE in the shipped product** (high confidence; adversarially corroborated)

`_is_gone` has exactly one production caller chain:
`_is_gone` (client.py:72) ← `_release_session` (client.py:54) ← `session()` `finally` (client.py:365).
It runs **only** inside `except RangeEscaped:`. On Windows:

- `BACKEND = _Posix if POSIX else _Job` (`process_range.py:304`, `POSIX = os.name=="posix"` :40) → Windows uses `_Job`.
- `_Job.escaped()` is a hard `return []` (`process_range.py:277–278`; Job created with `KILL_ON_JOB_CLOSE`
  and **no `BREAKAWAY_OK`**, :250 — no member can leave the job).
- `flight.escaped` is written **only** from `self.escaped()` (`:503, :519`) → always empty on Windows.
- The sole `raise RangeEscaped` (`:534`) is guarded by non-empty `flight.escaped` (`still`, `:531–533`) → **never raised** under `_Job`.
- Secondary guard: even a hypothetical `RangeEscaped` is defused because `left_the_range()` returns the same empty dict, so `_release_session`'s `if not left: raise` (client.py:68–69) re-raises **before** `_is_gone`.

**Adversarial verification (refute-unreachable): could NOT refute.** It also corrected the mechanism:
unreachability is guaranteed by the hardcoded `[]` in `_Job.escaped()`, *not* by the OS no-breakaway flag
(a real OS breakaway would make an escapee invisible to both `members()` and `escaped()` — a separate
silent-containment concern — but would still never populate `flight.escaped`, so it only *reinforces* unreachability).

**Caveats (do not open a native-Windows path):**
1. **Cygwin/MSYS2 Python** reports `os.name=="posix"` → `_Posix` backend → `_is_gone`/`os.kill(pid,0)` *are* reachable — but under Cygwin `os.kill(pid,0)` is a genuine POSIX probe, so no hazard.
2. **Test path gap:** `tests/v2/test_v21_pl7_session_teardown.py:98–136` (`IsGoneConfirmation`) calls `client._is_gone` directly and **mocks `os.kill`**, so it is blind to real Windows behavior; the real-process variant `PL7RealProcessTeardown` is `@skipUnless(sys.platform=='linux')`. **No test exercises real Windows `_is_gone`.** This is the regression-surface gap §9 closes.

## 5. Process-authority impact (INV-MUTATION-AUTHORITY)

The probe runs in the **kernel controller view** during session release; the pid is **controller-derived**
(an escapee of the controller's own range), never named by subject/implementation output.

- **Clause 1** ("untrusted output MUST NOT expand destructive authority") — **not breached**: the subject cannot steer this to an arbitrary victim (this is *not* the V1-PF-001 "subject picks the victim" class).
- **Clause 2** ("destructive authority only from an independently-established controller view") — the actor is the controller, **but** the site is ledgered as a pure READ (`LIVENESS_PROBE_SIGNAL_0`, "no signal delivered") while on Windows it is an actual terminate → an **unledgered destructive op**, i.e. a *letter-level* breach of the audit regime **if reachable**. Aggravator: on Windows `process_table()`→`_ps_table()` raises (no `ps`), so `present=None` and the start-time pid-reuse guard is skipped → the terminate could land on a **reused/unrelated pid**.

**Severity if reachable: HIGH / release-blocking** (undeclared terminate; semantic inversion — a liveness
*read* manufactures the "gone" evidence the grace loop then trusts; no pid-reuse protection on Windows).
**Severity given unreachability: LOW / LATENT** — the invariant **holds in the shipped product**. It is a
contract-hygiene / defense-in-depth defect whose safety rests on a **cross-module coincidence**
(`_Job.escaped()==[]`), not on any guard at the probe itself. Any future change that lets a Windows range
report an escapee (adding `BREAKAWAY_OK`, a non-Job backend, a fallback) promotes it to active HIGH with no
further warning — which is why the owner-approved guarded fix is worth preparing now.

## 6. Why PR/branch CI is green today (and the inconsistency to note)

`validation/v2/destructive_authority.py` is a **fail-closed** ledger checker. `client.py:46` has **no
ledger row** (verified: 0 rows under `aisef2/app/` in `destructive_sites.json`), so a whole-tree
`da.check(ROOT)` **would fail** on it. But the two whole-tree assertions
(`tests/v2/p0/test_destructive_authority.py:47`, `tests/v2/p5/test_invariants.py:995`) are **`@sealing`-gated**
(`sealing_gate.py` GATED :30, :32) → they only run with `AISEF_SEALING=1` (master/tags, "honestly RED until
owner reseals") and are a **visible SKIP** on branch/PR CI → the missing row never surfaces there.

Two items for the ĐO CUỐI report:
1. `sealing_gate.py:10–13` explicitly says live-tree static checks should **not** be gated ("those run everywhere; a red one is a real finding") — yet these two whole-tree static checks **are** gated. That inconsistency is exactly what let `client.py:46` slip the PR signal.
2. Even un-gated, the checker is the **wrong guard** for this: the `LIVENESS_PROBE_SIGNAL_0` class passes on **argument shape alone** (`os.kill` + 2 args + literal `0`, `destructive_authority.py:427–430`) with **no platform dimension** — it would equally bless a Windows-unsafe probe.

## 7. Safe-fix design (recommendation — NOT applied)

Root cause (ponytail — fix once, at the shared probe): `_is_gone` calls `os.kill(pid,0)` directly. The
product already owns the correct cross-platform read-only probe: `aisef/control/state.py:46` `pid_alive()`
(POSIX signal-0; Windows `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess == STILL_ACTIVE(259)`),
"proven on Linux, macOS and Windows CI" (`p12_watchdog.py:84`).

- **Option A (recommended) — route the fallback through a Windows-safe existence check.** Replace the raw
  `os.kill(pid, 0)` branch in `_is_gone` with the `pid_alive` pattern: existence→alive (return `False`,
  cannot prove gone), confirmed-absent→gone (return `True`). Mapping is `return not pid_alive(pid)` under the
  "never wrongly dead" bias `pid_alive` already carries, preserving `_is_gone`'s conservative refuse-side
  contract. Keeps POSIX behavior byte-identical (its `pid_alive` POSIX branch is the same `os.kill(pid,0)`),
  makes the "no signal is ever sent" docstring **true on all platforms**, and removes the latent Windows
  authority-expansion. Open question for the owner: an `aisef2`-native helper vs. importing the V1
  `aisef.control.state.pid_alive` (V1 is second-class; a tiny `aisef2` copy avoids a kernel→legacy coupling).
- **Option B (minimal) — POSIX-gate the probe.** `if os.name != "posix": return False` before the `os.kill`,
  since the whole escapee path is POSIX-only by construction. Smaller diff, but leaves `_is_gone` unable to
  answer on a hypothetical future Windows escapee (always "alive→refuse"), and does nothing for the Cygwin
  case (harmless there anyway). Honest but less complete than A.

Either option is **test-only in effect on POSIX** (no behavior change) and touches a frozen-kernel file, so it
is owner-gated. Recommendation: **Option A**, landed together with §8 and §9 as one reviewed change after owner go.

## 8. Windows reproduction test (authored — staged, not yet wired)

Delivered as `closure-evidence/v2/v2.2/win-oskill/repro_test_win_oskill.py`. It is **staged out of test
collection on purpose** so Windows CI stays green before the fix (owner #6) — on unfixed CPython ≤3.12 it
would turn Windows CI **red** by demonstrating the bug. It is written to **move into `tests/v2/` with the fix**.

What it pins (`@skipUnless(sys.platform=="win32")`): spawn a real, harmless long-lived child; assert it is
alive; call `client._is_gone(child.pid, <stub proc, created=None>)` with `os.kill` **unmocked**; assert the
child is **still alive afterwards** (fails on unfixed Windows — the child is TerminateProcess'd / Ctrl-C'd)
and that `_is_gone` returned `False` for a live process. On Windows `process_table()` raises (no `ps`), so the
call takes exactly the `os.kill(pid,0)` fallback branch — the hazardous path. After Option A/B it passes.

## 9. Regression plan (inputs — reuse existing machinery)

1. **Behavioral guard (Windows):** move §8's test into `tests/v2/` with the fix. Closes the gap that
   `IsGoneConfirmation` mocks `os.kill` and `PL7RealProcessTeardown` is Linux-only.
2. **Static guard (cross-platform, runs on PR CI):** extend the existing AST meta-scan
   `tests/test_meta.py::TestKhongDungApiChiCoTrenPosix` (currently scans `aisef/` only, and its `POSIX_ONLY`
   set has `killpg` but not bare `kill`): (a) widen scope to **both `aisef/` and `aisef2/`**; (b) add a
   **value-trap** rule — flag any `os.kill(<x>, 0)` (2nd arg literal `0`) in product code not inside a
   `sys.platform=='win32'`/`os.name=='nt'` guard and not delegating to the shared safe probe. The existing
   name-only scan structurally cannot catch this (the trap is the argument *value*, not a POSIX-only name).
   Its self-test (`test_phep_quet_that_su_thay_duoc_loi`) is the template for proving the new rule.
3. **Ledger/authority (owner-gated kernel change):** optionally tighten `LIVENESS_PROBE_SIGNAL_0`
   (`destructive_authority.py:427–430`) to also require a platform guard, **and** move the two whole-tree
   `da.check(ROOT)` assertions out of the sealing gate per `sealing_gate.py:10–13`. Flag that touching
   `destructive_authority.py` / the registry is itself a kernel change needing separate owner sign-off
   (consistent with owner #4: no registry changes without approval).

## 10. Evidence index

`aisef2/app/client.py:31–51,:54,:66–76,:365` · `aisef2/runtime/process_range.py:40,:250,:277–278,:304,:432–443,:503,:519,:531–534,:55–57,:6–9` ·
`aisef/control/state.py:46–78` · `validation/v2/destructive_authority.py:33,:37,:64,:427–430,:451–489,:504–505` ·
`validation/v2/destructive_sites.json` (no `aisef2/app/` row) · `validation/p12_watchdog.py:83–92` ·
`tests/v2/sealing_gate.py:10–13,:20–25,:30,:32` · `tests/v2/p0/test_destructive_authority.py:45–50,:72–74` ·
`tests/v2/test_v21_pl7_session_teardown.py:98–136,:179` · `tests/test_meta.py:459–545` · `tests/v2/p4/test_process_range.py:38–59` ·
`tests/hardening/adapters/test_conformance.py:129–140`.

## Appendix — adversarial verification

| Claim | Verdict | Residual |
|---|---|---|
| `os.kill(pid,0)` at client.py:46 is **unreachable on native Windows** | **not refuted** (structural: `_Job.escaped()==[]`) | Cygwin-posix reaches it but safely; tests call it directly (mocked) |
| `os.kill(pid,0)` is **destructive on Windows** in all deployed CPython | **not refuted** | post-3.13-fix kills via Ctrl+C event / raises `OSError` instead of TerminateProcess, still never a safe probe |

**Bottom line:** latent, not live. Invariant holds in the shipped product. Guarded fix (Option A) + §8 test +
§9 static guard, landed as one owner-approved change. Not applied here; kernel frozen.
