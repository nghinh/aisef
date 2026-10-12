# B03-R3-range — `ProcessRange.release` called by more than one thread

Status: implemented on branch `v21r3/range` (base `3dc827b`). Files: `aisef2/runtime/process_range.py`,
`tests/v2/test_v21_r3_range_release_contract.py`, this document. Nothing else changed.

## 1. The owner's decision (2026-10-12, item 6)

> Tôi chọn sửa lỗi thay vì giữ flake 1–5%. Trước hết xác minh hợp đồng gọi đồng thời; lựa chọn RLock hay cách sửa khác phải dựa trên đường gọi thực tế.
> Có test tái hiện bằng điều phối luồng có kiểm soát, kiểm tra tính idempotent, quyền sở hữu tiến trình và tránh deadlock. Không chỉ lặp test nhiều lần rồi kết luận hết lỗi.
> Phân tích phạm vi bằng chứng bị ảnh hưởng. [...]

In English: fix the defect rather than keep a 1–5 % flake; first establish the contract for concurrent calls — RLock
or another fix is to follow from the real call paths; reproduce the race with controlled thread coordination and
test idempotence, process ownership and deadlock avoidance, never by repeating a test until it stops failing;
analyse which evidence is affected. The re-measurement is the lead's; section 7 lists what this change touches.

## 2. What was established first: the real call paths

Every caller of `ProcessRange.release()` (and of `_abort`, `_signal`, `wait_empty`, `members`) was read. The product
creates two kinds of thread that touch a range and installs one signal handler.

| caller | file:line | thread it runs on | can it overlap another caller of the same range | expects | on an exception |
|---|---|---|---|---|---|
| `client.session` | `aisef2/app/client.py:213-218` | the caller's; the range is a local | no | return, or RangeNotEmpty / RangeEscaped | propagates out of `finally`; the stream is redacted in an outer `finally` |
| `adapters._bounded` | `aisef2/app/adapters.py:283-291` | the caller's; local | no | as above | propagates |
| `test_execution.execute` | `aisef2/quality/test_execution.py:453-469` | the caller's; `on_range` hands the range to a StoryScope; a pump thread reads `run.output` only | no: the scope's release (a worker) comes after, in program order | ladder on the deadline, else a no-op | propagates |
| the four probes | `probe/cli_invocation.py:1015-1029`, `process_effect.py:885-899`, `python_callable.py:296-308`, `python_callable_v2.py:483-497` | the probe's evaluating thread | not in the product. **By design in two tests**: a controller's stop thread calls `release()` while the probe's own `finally: run.release()` runs (`test_c2_cli_invocation.py::FM2_CLI_SUBJECT_3`, `test_probe_process_effect.py::FM2_EFFECT_10`) | RangeNotEmpty / RangeEscaped propagate ("a leak is never silent", §17.1); `_after_dispatch` reads `run.ledger` | propagates through `run_probe` |
| `StoryScope._release` | `aisef2/runtime/story_scope.py:152-177` (`release` :109, `dispose` :119, the refused `acquire` :90-97) | **a daemon worker thread per release** (bound `RELEASE_TIMEOUT_S` = 600 s; inline when `None`), joined with the bound and **abandoned, not joined,** at it | the worker may still be inside `release()` after the scope moved on. Nothing releases that range again through the scope: it was popped before the release (:115, :127) or never pushed. A later direct caller is not found in the product; it is constructed in `AbandonedWorker` | Residual -> RESIDUAL; any other `Exception` -> FAILED; `InvariantError` re-raised | recorded in the journal, never lost |
| `Ranged.release` | `aisef2/orchestrate/proof.py:50-51` | `StoryScope._release`'s worker | after the probe's own release, same logical thread of control | a no-op after the probe's own | as the scope |
| `ToolCall.finish` | `aisef2/runtime/tool.py:77-92` | the main thread, through `scope.release`; `outcome()` reads `ledger` / `returncode` after | no (popped; a second `scope.release` only when the first was not made) | RESIDUAL recorded | as the scope |
| `RunScope.interrupt` -> `dispose` | `aisef2/runtime/run_scope.py:204-247` | the main thread, in `except KeyboardInterrupt` — the interrupted frame has already unwound | no | RESIDUAL / abandoned | as the scope |
| `_run_file` (mutation runner) | `validation/v2/mutation.py:1556`, `:1583` | the runner's thread | **sequential twice** on one range: RangeNotEmpty, a cleanup by the authority, `_wait` lowered (:1581), `release()` again | the second call **re-runs the ladder** | `_Stop` |
| `owned_run`, `c2_p9`, `q3`, `linux_guest` | `validation/...` | one thread each | no | return / the two exceptions | as written there |

* **Signal handlers.** The product installs one: `run_scope.py:254` (`_second_interrupt_abandons`), and it only sets
  `_abandon` (`interrupt()` returns at once in state INTERRUPTED). It never calls `release`. `range_anchor.py:88-89`
  are the anchor's own handlers, in another process. A default SIGINT raises `KeyboardInterrupt` in the main thread:
  that unwinds `release()` (the frame is gone before any `except` upstream runs); it does not re-enter it.
* **Threads that touch a range without releasing it:** the range's own `_pumper` (anchor stdout -> queue), and the
  `_pump` threads of `test_execution.py:483` and `python_callable.py:315` (they read `run.output`).
* **Windows (`_Job`).** The same Python-level contract: `terminate()` is reached only through `_signal`; `close()`
  is guarded by `if self.handle`; both are now reached by one thread.

Findings. (a) No product path was found with two threads inside `release()` of one range at once — the investigator's
reading stands, now with the table. (b) The paths that *can* are the two tests above (by design), an abandoned
StoryScope worker followed by a later direct call (constructed, not found), and a future signal handler that calls
`release`. (c) The mutation runner's twice-sequential call is a real caller that needs the second call to run the
ladder again. (d) `wait()` may be called by two threads (the probe's `_watch` and the release's own `wait(0.0)` /
`wait(1.0)`); they share one queue. That is outside this contract and is left as it was.

## 3. The contract

1. **Mutual exclusion.** At most one thread runs the ladder, the EXIT write, the reap and the pipe close of one range.
2. **Idempotence.** A call after a release has ended does nothing observable — no signal, no ledger row, no second
   write or close — and returns as it always did: `None` once the anchor is reaped; a new ladder after RangeNotEmpty
   (today's behaviour, and `mutation.py:1583` relies on it). A caller that **waited for a release in flight** is
   given its outcome: the same RangeNotEmpty or RangeEscaped. That is the silent-leak path: with a lock, the thread
   that ran the release gets RangeEscaped and the other returns `None` — and the first may be a stop thread nobody
   reads (in the two by-design tests the probe's own `finally` is the one that must see the leak, §17.1).
3. **Ownership.** No signal is sent after the anchor is reaped, and a caller that waited never signals a range
   another thread emptied. In `BASE` the guard in `_signal` is a check-then-act: a thread past `if self._reaped`
   and about to `os.killpg(self.group, ...)` while another measures the range empty and reaps the anchor signals a
   group id the anchor no longer pins — the pid-reuse hazard (`test_no_signal_is_sent_after_the_anchor_was_reaped`
   records `('SIGINT', True)` on `BASE`, 40/40 runs). Across threads it is closed by (1); on one thread by the
   `disposing` flag below.
4. **No deadlock.**
   * *Same thread, re-entered* (a signal handler, a finalizer): returns; it never waits for itself. Every blocking
     primitive in `release` is one the same thread can take again (`RLock`) or does not hold (`time.sleep`): see
     the design.
   * *Another thread, waiting:* waits exactly as long as the release in flight (the ladder is bounded by `grace_s`
     and `wait_s`; with `wait_s=None` the last stage waits as long as the members live — as the caller's own ladder
     would have). A waiter holds nothing.
   * *The abandoned StoryScope worker:* a later caller waits for it and is free when it ends. It cannot hang a
     controller that did not hang before: before, that caller ran a ladder of its own against the same members and
     ended when they did. One stuck for another reason (`anchor.wait()`) would have stuck its own call there too.
   * *`start()` failing -> `_abort()`:* `_abort` is `start`'s own path and runs before the range is shared
     (`on_range` is called after `start()` returns, in every caller), so it overlaps nothing. After it `_reaped` is
     set and `release()` returns at once (test, POSIX).

## 4. Design: one release in flight; its second caller waits and is given its outcome

`release()` claims a `_Flight` — the leading thread, `disposing`, the escapees seen, a `done` flag, the `outcome` —
under `_mx`, an `RLock` that guards the flight pointer and nothing else.

* **No flight in progress** (none yet, or the last has `done` set): return if the range was never started or its
  anchor is reaped; otherwise claim a flight and lead it: `_ladder`, then `disposing = True`, then `_release`'s EXIT
  write, reap, pipe close, backend close and escapee check. `done` is set in a `finally`, after the last statement.
* **A flight in progress, led by another thread:** poll its `done` flag with `time.sleep(POLL_S)` — as `wait_empty`
  does, so a main thread stays interruptible on every OS and nothing is held that a handler could meet — and when it
  ends in RangeNotEmpty or RangeEscaped, raise a **copy** of it (same type and text, `__cause__` the leader's);
  otherwise look again. A leader that died of anything else (a failing signal, a KeyboardInterrupt) produced no
  outcome of the range: the waiter leads next, exactly as a later call would.
* **A flight in progress, led by this thread** (re-entry): if it is not yet `disposing` the call runs `_ladder` —
  the range is empty, or RangeNotEmpty, when it returns, which is what a handler wants — and in every case it returns
  without touching the anchor, the pipes or the backend: the frame below disposes. Once `disposing` is set nothing in
  this process signals the range (`_ladder` is the only caller of `_signal`) and the anchor may be reaped; a
  re-entry in that window therefore only returns. A handler that lands inside the claim re-enters `_mx`.

The ladder, the EXIT write and both exception messages are the old text, byte for byte (`release` was split into
`release`, `_ladder`, `_release`; `_signal`, `_abort`, `_close_pipes`, `start`, `wait`, `members`, `escaped`,
`wait_empty` are unchanged). The outcome is raised after the `finally`, not from an `except` that ends in a bare
`raise`: the kernel's except-boundary audit (`tests/v2/p5/test_invariants.py:396`, census `RERAISES == 8`) counts
such a handler, and this one is not a boundary that could hold an `InvariantError`; the first version moved the
census to 9 and was restructured rather than the pin.

### Alternatives rejected, with what was measured

The final test file was run against each alternative applied to `BASE`'s file (kept in the hand-over directory):

| alternative | mutual-exclusion tests | what it fails | verdict |
|---|---|---|---|
| **BASE** | **fail**, 40/40 runs, including the exact `ValueError: PyMemoryView_FromBuffer(): info->buf must not be NULL` from real `io` objects | 12 of 25 (1 skipped: no claim lock) | the defect |
| `RLock` around release (the investigator's `process_range.diff`) | pass | 5 of 25: a re-entered call runs the whole disposal and the frame below **repeats** it (pipes closed twice, anchor waited twice, backend closed twice: `(2, 2, 2)`); the waiter gets **`None` for RangeEscaped** (the silent leak) and **runs a second ladder** for RangeNotEmpty (6 signals for one release, twice the wait) | fixes the race, not the contract |
| plain `Lock` | pass | 6 of 25, **3 by deadlock** (a handler re-entering the releasing thread waits for itself; the test's 10 s bound ends it) | rejected: a hang is worse than the flake |
| `except (OSError, ValueError)` (`process_range.alt-swallow.diff`) | **fail** | 11 of 25 | hides the symptom: two ladders, two EXIT writes, a signal after the reap still happen |

`RLock` was therefore not chosen for itself: the contract needed an owner (re-entry), an outcome (the waiter) and a
phase (ownership), which a lock does not carry. The investigator's diff remains a correct fix of the reported
flake; it is not a fix of the contract. (An `RLock` *is* what guards the claim: a handler may land inside it.)

## 5. Requirement -> test

All in `tests/v2/test_v21_r3_range_release_contract.py` (25 tests, ~0.6 s). Fake anchor, backend and pipes journal
every operation with the thread that did it; a thread is **parked** inside the operation the race needs, the second
caller is brought to "polling for the first" (seen in the `time.sleep` the module calls) or — in an implementation
that does not make it wait — "already running inside" (two threads in the backend), and only then is the first one
let go. No process and no sleep of the test's own, except `RealRange` and the POSIX failed-start test.

| requirement | test | on BASE |
|---|---|---|
| 1 one ladder, one EXIT write, one close per pipe, one reap, never two threads inside | `MutualExclusion.test_two_threads_releasing_one_range_run_one_ladder_one_exit_write_and_one_close` | FAIL |
| 1 the second caller waits while the first is stuck, and both end when it does | `MutualExclusion.test_the_second_caller_is_not_released_before_the_first_has_finished` | FAIL |
| 1 the reported failure itself, from real `io` objects (EPIPE, pending bytes, both close) | `MutualExclusion.test_the_real_pipe_close_of_a_second_releaser_never_meets_the_first` | FAIL: the exact ValueError |
| 1/3 a real range, a real stop thread and owner aligned by a barrier (integration, not the proof) | `RealRange.test_a_stop_thread_and_the_owner_release_one_real_range_once` | FAIL: two cooperative signals |
| 2 a call after the end touches nothing, returns `None` | `Idempotence.test_a_call_after_the_release_ended_does_nothing_observable_and_returns` | pass (unchanged) |
| 2 never started; exited by itself; empty but exit unreported; message text; no table read without escapees | `Idempotence.*` (5) | pass (unchanged) |
| 2 RangeNotEmpty, then a later call runs the ladder again (`mutation.py:1583`) | `Idempotence.test_RangeNotEmpty_then_a_later_call_runs_the_ladder_again_as_it_always_did` | pass (unchanged) |
| 2 RangeEscaped to the caller; a later call returns `None` | `Idempotence.test_RangeEscaped_is_raised_to_the_caller_and_a_later_call_returns_as_it_always_did` | pass (unchanged) |
| 2 the waiter is given RangeEscaped / RangeNotEmpty, no second ladder | `SharedOutcome.test_a_caller_that_waited_is_given_RangeEscaped_...`, `..._RangeNotEmpty_and_no_second_ladder_runs` | FAIL |
| 2 a failure that is no outcome is not handed to the waiter, who leads | `SharedOutcome.test_a_failure_that_is_not_an_outcome_...` | pass |
| 3 no signal after the reap | `Ownership.test_no_signal_is_sent_after_the_anchor_was_reaped` | FAIL |
| 3 a waiter never signals a range another thread emptied | `Ownership.test_a_caller_that_waited_never_signals_a_range_the_other_thread_emptied` | FAIL |
| 3 the guard refuses after the reap | `Ownership.test_the_signal_guard_refuses_after_the_reap` | pass |
| 4 re-entry in the ladder stops the range, the frame below disposes once | `Reentry.test_a_call_inside_the_ladder_stops_the_range_and_the_frame_below_disposes` | FAIL |
| 4 re-entry past the ladder does nothing | `Reentry.test_a_call_past_the_ladder_returns_at_once_...` | FAIL |
| 4 re-entry that cannot empty raises to its caller only; the next call completes | `Reentry.test_a_call_inside_the_ladder_that_cannot_empty_...` | pass |
| 4 a handler inside the claim hangs nothing (design-bound; skipped where there is no claim lock) | `Reentry.test_a_call_that_arrives_while_a_release_is_being_claimed_hangs_nothing` | skipped |
| 4 a failed `start()` leaves a range whose release returns (POSIX) | `Reentry.test_a_failed_start_leaves_a_range_whose_release_returns_at_once` | pass |
| 4 a handler on a waiting thread waits too (design-bound) | `WaitingCaller.test_a_call_that_arrives_on_a_waiting_thread_waits_too_and_hangs_nothing` | FAIL |
| 4 the abandoned StoryScope worker does not end a later caller | `AbandonedWorker.test_a_release_the_scope_abandoned_...` | FAIL |

## 6. What is real, what is simulated

* **Real:** `RealRange` (a real target under a real anchor and pipes, two threads); the failed-start test (a real
  anchor); the real `io.TextIOWrapper` over `io.BufferedWriter` in the ValueError test; the existing real-process
  tests run on the host and in the Linux guest (section 8); the 200-run loops of the two by-design tests.
* **Simulated:** every other test: a fake anchor, backend and pipes with thread parking. The "signal handler" is a
  call made from inside a backend operation (or the module's `time.sleep`, or the claim lock) on the same thread — a
  real asynchronous signal cannot be made deterministic.
* **Neither:** Windows (not run here), Python 3.11–3.13 (3.14.7 on the host, 3.14.8 in the guest).

## 7. Evidence scope (what this change touches; the re-measurement is the lead's)

* **Pinned file:** `aisef2/runtime/process_range.py` (`versions.harness`): a new digest. Sealed records that bind it
  or `aisef2/`'s tree are stale until regenerated (section 8).
* **Surface:** added `_Flight`, `ProcessRange._mx`, `_flight`, `_ladder`, `_release`. Changed behaviour:
  `ProcessRange.release` under concurrency and re-entry. Unchanged: signatures, return values, both exception
  classes and their text, `ledger`, `_wait`, `_reaped`, `_anchor`, `_cwd` (read by `mutation.py:1575-1581` and tests).
* **Importers (product):** `app/client.py`, `app/adapters.py`, `app/confine.py` (`process_table` only),
  `quality/test_execution.py`, `quality/vacuity.py`, `runtime/tool.py`, `orchestrate/security.py` (`RangeError`),
  `probe/{cli_invocation,process_effect,python_callable,python_callable_v2}.py`. `validation/`: 16 files
  (`grep -rl process_range`), among them `v2/mutation.py`, `v2/p4_evidence.py`, `v2/destructive_authority.py`.
* **Mutation targets to register** (`validation/v2/mutation.py`, the lead's): `ProcessRange.release` (changed),
  `ProcessRange._ladder`, `ProcessRange._release`, `_Flight.__init__` (new), with kill files
  `tests/v2/p4/test_process_range.py` and `tests/v2/test_v21_r3_range_release_contract.py`. The sealed P4 record
  names 17 targets of this file (`_abort`, `_close_pipes`, `_signal`, `anchor_returncode`, `escaped`, `members`,
  `release`, `start`, `wait`, `wait_empty`, `_Job.controller_stopped`, `_Posix.abort/escaped/members`, `_ps_table`,
  `descendants`, `targets`); all read "target changed since the mutation run" now, the unchanged ones too.

## 8. Results

Host: macOS arm64, CPython 3.14.7, the machine carrying other sessions' work throughout. Guest: Linux 7.0.12-linuxkit
aarch64, CPython 3.14.8, bubblewrap 0.12.0 (`guest.sh`, one discarded container per command, no network).

**8.1 The new tests.** 25 tests, ~0.5 s.

| where | tree | result |
|---|---|---|
| host | this branch | 40/40 runs OK |
| host | `BASE` file | 12 FAIL + 1 skipped (no claim lock), **40/40 runs each**; the real-`io` test fails with the exact `ValueError: PyMemoryView_FromBuffer(): info->buf must not be NULL` |
| guest (**real run**) | this branch | 25 OK |
| guest (**real run**) | `BASE` file | 12 FAIL + 1 skipped, the same exact ValueError: the reproduction is not macOS's |

**8.2 Mutants** (`kill_check`, the new test file alone, T0 PASS 25 tests; source sha256 `489e7ec3638c...`):

| function | mutants | KILLED | SURVIVED |
|---|---|---|---|
| `ProcessRange.release` (changed) | 23 | 23 | 0 |
| `ProcessRange._ladder` (new) | 15 | 15 | 0 |
| `ProcessRange._release` (new) | 12 | 12 | 0 |
| `_Flight.__init__` (new) | 2 | 2 | 0 |
| `ProcessRange.__init__` (changed: two lines) | 17 | 17 | 0 |

No survivor, so no disposition to defend. Output: `kc-*.json` in the hand-over directory.

**8.3 The two by-design tests, looped — a supplement, not the proof** (each run a fresh interpreter, `env -i`, PATH
without `opencode`):

| test | host `BASE` | host this branch | guest `BASE` | guest this branch |
|---|---|---|---|---|
| `FM2_CLI_SUBJECT_3` | 195/200 pass, 5 fail; the exact error in 6 outputs | 200/200; 0 | 100/100; 0 | 100/100; 0 |
| `FM2_EFFECT_10` | 200/200 pass, **the exact error in 2 outputs** (it died in the stop thread, which the test does not read) | 200/200; 0 | not run | not run |

The guest loop on `BASE` shows no failure in 100 runs: it does not discriminate; the deterministic tests do.

**8.4 The existing real range tests** (this branch): `tests/v2/p4/test_process_range.py` 24 OK (host, guest),
`tests/v2/test_c2_cli_invocation.py` 32 OK, `tests/v2/test_probe_process_effect.py` 24 OK,
`tests/v2/test_v21_confine.py` 34 OK (host; guest under both profiles, X1 and hardened),
`tests.v2.p0.test_destructive_authority` 13 OK, `tests.v2.p4.test_mutation_safety` 10 OK,
`tests/v2/p5/test_invariants.py` 50 OK. `ruff check .` passes.

**8.5 Every test module that references `process_range`, or a validation module that reads it** (55 modules, 1,122
tests, run once each on the final code): 52 OK; 3 not:

| module | result | why |
|---|---|---|
| `tests.v2.p4.test_interruption` | 1 error in the sweep; **OK 3/3 in the foreground**, on this branch and on `BASE` | the sweep ran as a background job, whose children ignore SIGINT; this test needs it delivered (D3) |
| `tests.v2.test_c2_delivery_experiment` | 1 failure: `PlanCorrection.test_the_committed_record_is_what_this_tree_derives` | sealed record bound to `git rev-parse HEAD:aisef2`: stale by construction |
| `tests.v2.test_v21_mutation_runner` | 1 failure: `Classify.test_historical_records_read_as_before [P4]` | the sealed P4 record names 17 targets of `process_range.py`: "target changed since the mutation run" |

**8.6 The sealed-record checkers, `BASE` against this branch** (`BASE` run in a git checkout of `3dc827b`; these
are the lead's to regenerate, reported, not fixed):

| test | `BASE` | this branch |
|---|---|---|
| `test_c2_k_nowork_001` | OK | 1 failure: `kernel.after.kernel_digest is not this tree's aisef2` |
| `test_c2_p5_acceptance` | 1 failure (`C2-P5-ACCEPTANCE-REVERIFICATION.json` is missing) | 2: that one, and `KernelProvenance...proposal_is_current` (`record.identities.aisef2_tree`) |
| `test_c2_delivery_experiment.PlanCorrection` | OK | 1 failure (above) |
| `test_v21_mutation_runner.Classify` | OK | 1 failure (above) |
| `p0.test_checker_calibration` | 2 failures | 2 failures: the same two; the `mutation` checker's clean problems now also name 5 `process_range.py` targets |
| `test_c2_orchestration_conformance` | 1 failure | 1 failure: the same |
| `test_v21_mutation_record`, `test_p5_falsifiability`, `p2.test_mutation_targets` | OK | OK |

So this change adds four failing tests to `BASE`'s four, all of them records bound to a tree or a file digest of
`aisef2/`; none is a behaviour.

## 9. Not established, residual risks, decisions needed

* **D1 — a leak after the first report (decision for the owner, not changed).** Measured (an experiment, not a
  test; the same on `BASE`): the probe's own `release()` raises RangeEscaped; `Party.run`'s `finally` then calls
  `scope.release(Ranged)`, which finds the anchor reaped, returns `None`, and the scope records **RELEASED**. The
  worktree and scratch after it are then not held back (`StoryScope.dispose`'s `blocked_by` is set only by a
  non-RELEASED range), against §17.1 ("nothing that depends on the range may be released"). A range could remember a
  completed release's outcome and re-raise it to every later caller; that changes what every sequential caller
  sees, so it is not done here.
* **D2 — Windows failed `adopt` (from reading, not run).** `_Job.abort` terminates and closes the job; an anchor that
  never joined it (`OpenProcess` / `AssignProcessToJobObject` failed) is not in it, and `_abort` then
  `_anchor.wait()`s for a process that waits on its stdin. Unchanged here; one fix is to kill the anchor by its own
  handle in `_abort`. The POSIX failed-start test is skipped on Windows for that reason.
* **D3 — a pre-existing hang, unexplained.** `tests/v2/p4/test_interruption.py::RealSignals::test_SIGINT_mid_story_...`
  did not finish within its 30 s once in 150 runs on `BASE` (run 30 of a loop of single runs; 0 in 150 on this tree,
  0 in 500 under a `faulthandler` probe on `BASE`): no release is in flight when its SIGINT lands, the controller
  had not exited, and no stack was captured. It is not caused by this change and was not explained. Separately,
  run as a *background* job (`&`, `nohup`) the test fails every time on any tree — the job's children inherit SIGINT
  as ignored (measured) — an artifact of how a sweep is run, not of the code; both sweeps of this WP hit it, and it
  passes 3/3 in the foreground on `BASE` and on this tree.
* **Waiters inherit the leader's bound.** With `wait_s=None` a waiter can wait without bound — as its own ladder
  would have. If a signal handler ever calls `scope.dispose()` while the main thread is inside `release()`, the
  worker it starts waits for the suspended frame and is cut at `RELEASE_TIMEOUT_S` (600 s) by the scope, where
  before it ran a ladder alongside. The product has no such handler (section 2).
* **A flight stranded by an asynchronous exception.** `KeyboardInterrupt` delivered in the few bytecodes between the
  claim and the `try`, or inside the `finally` before `done = True`, would leave waiters polling (the same window
  exists around every `with lock:`); not measured, not closed.
* **Two `wait()` callers share one queue** (finding (d)); not part of this contract, left alone.
* The sealed-record checkers listed in 8.5/8.6 are stale after this change by construction; the lead regenerates them.
