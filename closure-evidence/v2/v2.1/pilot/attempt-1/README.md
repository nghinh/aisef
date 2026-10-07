# Pilot attempt 1 (2026-10-08, at ff115be) — stopped: the disk filled; not a measurement of the orders

**What it was.** Owner 2026-10-07 step 7: nine representative targets on four lanes, each lane running its targets
twice in fresh worktrees at ff115be — the declared kill-set order (`decl`) and the committed execution-order table
(`ord`, closure-evidence/v2/v2.1/EXECUTION-ORDER.json) — lanes 1 and 3 declared first, lanes 2 and 4 table first.
Started 02:34:56 under the heavy lock (`pilot.sh`, `pworker.sh`, as they ran; attempt 2 adds a disk guard to both).

**What stopped it.** Between about 03:10 and 03:20 (+07) the data volume reached 2.0 GiB free of 460 GiB (the
lead's own scratch held 58 GiB of old worktrees and tree copies, and a parallel hand-mutant check added ~1.4 GB).
`No space left on device` reached four lanes: `l2-decl` stopped before its first target (RUNNER_EXCEPTION copying
the pristine tree: 36 NOT_RUN), `l4-decl` stopped at `_watch`'s second mutant (1 KILLED, 1 INFRA, 31 NOT_RUN),
`l2-ord` stopped at `endpoint_problem`'s 18th mutant (OSError 28: 1 INFRA, 18 NOT_RUN), and `l1-decl` logged one.
At 03:29 the lead stopped the rest under control (`STOP.log`: SIGTERM to the two lane shells so no second order
started, then to the two `mutation.py run` processes after checking their cwd is their lane worktree); each
`owned_run` measured escaped 0, harness orphans 0 → 0; the heavy lock was released. 26 GiB were then freed by
removing the lead's own scratch worktrees after archiving every untracked/modified file of each.

**What it shows, and does not.**
- Fail-closed under a real infrastructure fault: every ENOSPC-affected mutant is INFRA or NOT_RUN and its target
  carries an error; none is KILLED (owner step 2: an infrastructure error is never counted as a kill).
- One clean comparison only — `cli_invocation.py::AGENT/guarded` (lane 4, both orders complete): 19 of 19 KILLED in
  both, the same class for every mutant; runner time 393 s declared vs 336 s table (0.855×) although the table
  order ran more files per mutant (38 vs 22 of the mutants' own runs). One target is not a measurement of the
  orders; attempt 2 repeats the whole pilot.
- `story_runner.py::_fail` (34/34 KILLED) and `lineage.py::claims` (7 KILLED, 5 SURVIVED) finished in their
  declared order only; `cli.py::_parser` was in progress at the stop (its MUTANT lines in `l1-decl.log` are in-progress
  checkpoints, not results).
- `attempt1-compare.json` is `pilot_compare.py` over these records; its "differ" rows are NOT_RUN/INFRA against
  KILLED — caused by the fault, not by the order.
