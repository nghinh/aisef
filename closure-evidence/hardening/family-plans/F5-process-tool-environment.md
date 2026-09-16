# Fix family F5 — PROCESS / TOOL / ENVIRONMENT

Closes (frozen defect set): SS-34, SS-45, SS-46, SS-47, SS-48, SS-49, SS-50, SS-51, SS-52, D-024; compound
FM-C-11 (a process left by the session survives workspace removal) and fault cell FM-P-05. Invariants: INV-N.1,
INV-L.1, INV-L.2, INV-M.1; INV-F.3 loses SS-34.

Owner rules (Phase 10): *terminate / reap / verify / remove*; *every declared tool is probed*; *a missing tool is
UNRUNNABLE or ENVIRONMENT_FAILURE, never a behavioural RED*.

## 1. Tools: presence is measured, never inferred from a string (INV-N.1, INV-F.3)

- **SS-34** `qa.run_suite` records `unrunnable` and `outcome` on every `qa:<kind>` tool_run (as `test`/`lint` do);
  the story gate scores a `qa:<kind>` check UNRUNNABLE from `detail.unrunnable`, never FAILED.
- **SS-45** `declared_tools(cfg, project)` yields the RESOLVED command per evidence kind — `command_for(kind, …)`,
  auto-detected defaults included (bandit, gosec, cargo audit, npm test) — so `check_tools` probes what `aisef tool
  <kind>` will actually run; `doctor` prints one line per resolved tool.
- **SS-47** `ToolCheck.present` is tri-state: `True` / `False` / `None` (UNJUDGED — a project-local runner the probe
  cannot build). UNJUDGED is printed as such, never as present; `_missing_tools` does not stop the run on it, and the
  story's first `tool` run settles it (its record is the proof, per INV-N.1's "exists in the declared environment").
- **SS-46** `_missing_tools` probes whenever an execution environment is CHOSEN — a declared image, a stack image
  `image_for` picks, or the host when docker is off — not only when `sandbox.image` was typed; only the fake provider
  skips it. One `command -v` per resolved tool, before any paid session.
- **SS-48** `provisioned()` adds `verify.unit` (and every `verify.<kind>` with a command) only when the probe for that
  command says present or UNJUDGED; a command the probe reports missing does not provision the capability — the
  pre-flight names it and no session starts on it.

## 2. Processes: the attempt owns its process tree (INV-L.1, INV-L.2; FM-C-11, D-024)

- Sessions already start in their own process group (POSIX `start_new_session`; Windows `CREATE_NEW_PROCESS_GROUP`)
  and `kill_tree` is used at the turn cap / timeout. The gap is the NORMAL end: a grandchild the agent left (a dev
  server, a `git gc`) outlives the session, then races the workspace removal (D-024's `.git` not empty) or survives it
  (FM-C-11).
- `clients/base.py::reap_session(proc)` runs on EVERY exit of `_stream_with_timeout`: POSIX — while the group still
  has members (`killpg(pgid, 0)` succeeds), SIGTERM the group, wait up to 2 s, SIGKILL, verify; Windows — the session
  is assigned to a Job Object created with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (ctypes, stdlib), closing the job
  after the root exits kills every descendant; both record `process:reaped {pids, how}` in the session's `RunResult`
  (`raw_result["reaped"]`) so evidence shows it. Sandboxed tool runs (`harness/sandbox.py`) reap the same way.
- `WorktreeManager.remove` / the story's workspace teardown call `reap` for the attempt first and refuse to remove a
  tree whose group still has a live member (typed `ORPHANED` outcome, path kept) — terminate, reap, VERIFY, then remove.
- **D-024** disappears as a consequence: the bench helper's cleanup no longer races a writer; the helper additionally
  retries its cleanup once through `remove_tree` (Windows read-only objects, same helper as SS-60).

## 3. Leases: a claim is a lease with an owner and a term (INV-M.1)

- **SS-49** `reconcile_story` asks `claim_is_orphaned` before resetting a RUNNING/VERIFYING claim: a live owner on
  this host is left alone (result `live`, not `undo`); another host's claim is left alone unless its LEASE expired.
- **SS-50** `StateStore.claim` records `lease_until` (now + `run.lease_seconds`, default 1800) beside `claimed_by`;
  `heartbeat(story_id, owner)` extends it (called per attempt); `transition(..., owner=)` refuses a write from a
  non-owner while the lease is live (`TransitionError`); the kernel passes `owner=machine_id()` at its sites.
- **SS-51** `acquire_port_lease` locks a file keyed by `host:port` of `base_url` (one lease per port), recording
  `run_id`; the second contender gets `None`. `mockup_verify.already_running` treats a reachable port as OURS only when
  the lease file is ours (run_id) or its recorded pid is alive on this host — a 404 proves nothing (INV-R.2's rule).
- **SS-52** reservations carry `owner` (machine_id) and `expires_at` (now + max(2·est_seconds, 600 s));
  `_check_caps` ignores a reservation whose owner pid is dead on this host or whose term expired, records the release
  (`budget:reservation-expired`), and `doctor` lists live reservations with their owners.

## 4. Definition of done

RED → GREEN: `scan8a/test_group_d.py::TestSS34/45/46/47/48/49/50/51/52`, `test_compound_faults.py::TestCF11`,
`test_bench_qualification` cleanup no longer flaky (three consecutive full runs); new `tests/hardening/test_process_owner.py`
(a grandchild left by a session is dead before the workspace is removed, on POSIX and — via the job object — on Windows
CI; a live claim survives reconcile; a dead run's reservation expires); fault cells FM-P-05, FM-C-11 GREEN; INV-N.1,
L.1, L.2, M.1 PROVEN (F.3 loses SS-34); model: `PROCESS_DEATH` and `TOOL_UNRUNNABLE` already exist — the differential
adds a developer step that leaves a background process and the observation asserts no survivor; full suite, ruff,
Linux + Windows CI (the Windows job object is exercised there).

## 5. Closure record (2026-09-17, branch hardening/systematic-v1)

Implemented as designed, with the deviations named below (each is a smaller construction that meets the same rule,
never a weaker rule):

- **Tools.** `qa:<kind>` records `unrunnable` / `outcome`; the gate scores it UNRUNNABLE. `declared_tools(cfg,
  project)` resolves every kind through `command_for` (defaults included), so `check_tools` and `doctor` probe what
  `aisef tool <kind>` runs. `ToolCheck.ok` is tri-state (`None` = UNJUDGED, printed as such, never present; the
  existing field is kept rather than a new `present`). `_missing_tools` probes whenever an environment is chosen
  (only the fake provider skips) and stops only on `ok is False`; `provisioned()` consults the probe.
- **Processes.** `harness/process_owner.py` (`children_of`, `reap`: terminate → wait → kill → VERIFY, `reap_group`,
  `reap_new_children`, `survivors`, `win_job`: a Job Object with KILL_ON_JOB_CLOSE, ctypes only) instead of a
  `reap_session` in `clients/base.py`: `_stream_with_timeout` binds the session to the job at start and reaps its
  process group on EVERY exit; `_owned_run` (every client session, in-process clients included) reaps every child the
  harness process gained during the session; `harness/sandbox.py` reaps the same way. Pids land in
  `raw_result["reaped"]` / `SandboxResult.reaped`, never silent. The plan's refusal at `WorktreeManager.remove` is
  realised one step earlier, where the verification is: a survivor of terminate → kill is typed on the attempt
  (`Attempt.orphans`, ENVIRONMENT_FAILURE, fatal, `process` tool_run) and the wave loop keeps that workspace and names
  the pids; `remove` itself is unchanged because it is only reached for a story whose sessions were verified dead.
  D-024 disappears as a consequence; the bench helper's cleanup additionally retries once through `remove_tree`.
- **Leases.** `StoryRecord.lease_until`; `claim` and every owner write refresh the term; `heartbeat`; `transition(...,
  owner=)` refuses a non-owner while the lease is live; the kernel passes `owner=machine_id()`. The term is the
  constant `LEASE_SECONDS = 6 h`, not a `run.lease_seconds` key: a term is only consulted for a claim this host cannot
  judge by pid, and 30 min is shorter than one attempt (session timeout plus verifiers), which would let a second host
  reclaim a story mid-attempt; nobody tunes it. A claim WITHOUT a term is a pre-F5 claim, not a lease: only a live
  local pid keeps it, and another host's term-less claim stays reclaimable (found by the existing orphaned-claim
  test, which models the LedgerLock host). `reconcile_story` returns `live` instead of `undo` for a live claim. The
  port lease is keyed by `host:port` (`_port_key`), released through the run's `.owner` record;
  `ready_with_identity` is tri-state and `mockup_verify` accepts a reachable port as ours only with structural proof.
  Reservations carry `owner` and `expires_at`; `_check_caps` sums live ones only; a released reservation is RECORDED
  (`BudgetState.released`, last 50, with why: owner dead / term expired) and `doctor` lists live reservations with
  their owners and counts the dead or expired ones.

Members RED → GREEN (markers removed in this commit): SS-34, SS-45, SS-46, SS-47, SS-48, SS-49, SS-50, SS-51 (2),
SS-52; compound CF-11; D-024 FIXED with disposition. New: `tests/hardening/test_process_owner.py` (a child left by a
session is reaped and recorded; a survivor of the reaper is typed and keeps the workspace — through `_owned_run`,
through `run_attempt`, and through the real wave loop in `tests/test_run.py`); reservation-release record and doctor
listing tests. Existing tests adapted to the F5 contract (each names why): the declared-tools count includes the
resolved default `sast`; the port lock is named by the port; the process-count bench.

Differential: the developer vocabulary gains `CHANGED_ORPHAN` (the session leaves a background process) and the
observation compares `orphans_surviving` (model: 0). Negative control recorded: with `reap_new_children` disabled the
sleeper outlives the story (1); enabled, 0. The first 2000-trace run found one unexplained trace, seed 569, and it
was a MODEL defect: the model kept one out-of-scope flag per candidate, so a no-op re-graded on the same candidate
(T6') overwrote its predecessor's flag and the gate read one candidate as both positions of a plan-conflict pair; the
kernel pairs the two real complaints (in scope, then outside) and correctly lets the retry limit decide. The model now
keeps the flag per position (`tests/hardening/test_differential.py::TestSeed569…`); the kernel is unchanged. Results
(re-run after the model fix): see the numbers below.

Final numbers (2026-09-17): differential `differential-f5-400.json` 400/400 matched, `differential-f5-2000.json`
2000/2000 matched, 0 unexplained, `KNOWN == {}` (the first 2000-run's single unexplained trace was the model defect above,
fixed before the re-run). Full suite 3365 passed / 20 skipped / 8 expected-red / 0 failed (1444 subtests, 565 s); ruff
clean. Fault matrix 65 GREEN / 4 RED / 0 NEEDS_TEST (was 63 / 6). Registry 42 PROVEN / 7 PARTIAL / 1 MISSING (was
39 / 10 / 1): INV-N.1, INV-L.1, INV-L.2, INV-M.1 promoted; INV-F.3 stays PARTIAL while an OPEN F6 member claims it.
Defect set 66 FIXED / 1 SUPERSEDED / 6 OPEN (was 56 / 1 / 16); the 6 OPEN are F6's.

CI on 612efce (run 35119273174): Linux 3.11–3.14, lint, wheel green; Windows 3.11 RED on one cause — two toolhelp
snapshot walkers (`clients/base.kill_tree`, F1-era, and the new `process_owner._children_win32`) with two struct
classes on the shared `ctypes.windll.kernel32`, whose per-function argument types are cached, so every story on
Windows crashed at the reaper's first snapshot (`expected LP_PROCESSENTRY32W instance`). Fixed in the F6 commit: one
walker (`process_owner._snapshot_win32`) behind a private `WinDLL` with explicit prototypes, used by `children_of`,
`kill_tree` and the job object; the F6 commit's Windows job re-qualifies both families.
