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
