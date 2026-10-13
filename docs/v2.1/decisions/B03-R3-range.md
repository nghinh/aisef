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

All in `tests/v2/test_v21_r3_range_release_contract.py` (32 tests, ~1.8 s: 25 written with the change, 7 added in
the independent review, section 10). Fake anchor, backend and pipes journal
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
| 4 the abandoned StoryScope worker does not end a later caller, and it waits by polling, not by spinning | `AbandonedWorker.test_a_release_the_scope_abandoned_...` | FAIL |
| 1 the claim is ONE critical section: a thread parked inside it holds a second caller out (no lock, or a lock around the read and another around the write, lets both lead) | `ClaimAndWait.test_two_threads_that_arrive_together_are_not_both_leaders` (review) | FAIL |
| 1/2 a caller is held until the release has ENDED, wherever past the ladder it is: parked at `anchor.poll`, `anchor.wait`, `stdin.close`, `stdout.close`, `backend.close` | `ClaimAndWait.test_a_caller_is_held_until_the_release_has_ended_wherever_the_release_is` (review, 5 subtests) | FAIL |
| 2 a caller that arrives before the escapee check is given RangeEscaped (not `None`) | `ClaimAndWait.test_a_caller_waits_for_the_escapee_check_and_is_given_its_outcome` (review) | FAIL |
| 2 an escapee seen at either look (before the ladder; after it: Linux orphan re-parented to the anchor) is named, once | `EscapeeLooks.*` (review, 4) | pass (unchanged behaviour: guards the split of `release`) |

## 6. What is real, what is simulated

* **Real:** `RealRange` (a real target under a real anchor and pipes, two threads); the failed-start test (a real
  anchor); in the ValueError test the `io.TextIOWrapper` and `io.BufferedWriter` are CPython's own (the raw pipe
  under them is a simulated EPIPE writer, and the interleaving is forced by a hook inside its `close()`); the existing real-process
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
  `probe/{cli_invocation,process_effect,python_callable,python_callable_v2}.py`. `validation/`: 15 files
  (`grep -rl process_range validation`, counted in the review; this document said 16), among them `v2/mutation.py`, `v2/p4_evidence.py`, `v2/destructive_authority.py`.
* **Mutation targets to register** (`validation/v2/mutation.py`, the lead's): `ProcessRange.release` (changed),
  `ProcessRange._ladder`, `ProcessRange._release`, `_Flight.__init__` (new) and `ProcessRange.__init__` (changed: two
  lines; its 17 mutants are measured below), with kill files
  `tests/v2/p4/test_process_range.py` and `tests/v2/test_v21_r3_range_release_contract.py`. The sealed P4 record
  names 17 targets of this file (`_abort`, `_close_pipes`, `_signal`, `anchor_returncode`, `escaped`, `members`,
  `release`, `start`, `wait`, `wait_empty`, `_Job.controller_stopped`, `_Posix.abort/escaped/members`, `_ps_table`,
  `descendants`, `targets`); all read "target changed since the mutation run" now, the unchanged ones too.

## 8. Results

Host: macOS arm64, CPython 3.14.7, the machine carrying other sessions' work throughout. Guest: Linux 7.0.12-linuxkit
aarch64, CPython 3.14.8, bubblewrap 0.12.0 (`guest.sh`, one discarded container per command, no network).

**8.1 The new tests.** 25 tests at the implementer's head (~0.5 s); 32 after the review (~1.8 s). The table is the
implementer's measurement of the 25; the review's own runs of the 32 are in section 10.

| where | tree | result |
|---|---|---|
| host | this branch | 40/40 runs OK |
| host | `BASE` file | 12 FAIL + 1 skipped (no claim lock), **40/40 runs each**; the real-`io` test fails with the exact `ValueError: PyMemoryView_FromBuffer(): info->buf must not be NULL` |
| guest (**real run** of the same fake-backend tests: Linux, not a simulation of Linux) | this branch | 25 OK |
| guest (**real run**, as above) | `BASE` file | 12 FAIL + 1 skipped, the same exact ValueError: the reproduction is not macOS's |

**8.2 Mutants** (`kill_check`, the new test file alone, T0 PASS 25 tests; source sha256 `489e7ec3638c...`). This is the
implementer's table of the 25-test file; the review's re-run of it found `release` [17] unstable (INFRA) and its
re-run with the 32-test file is in section 10:

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
* **A flight stranded by an asynchronous exception.** `KeyboardInterrupt` delivered inside the `finally`, before
  `done = True` (two bytecodes), would leave waiters polling; not measured, not closed. (The claim itself is inside
  the `try`: an interrupt between the creation of the flight and its publication reaches the `finally`, which sets
  `done`, so that window does not strand anyone.)
* **Two `wait()` callers share one queue** (finding (d)); not part of this contract, left alone.
* The sealed-record checkers listed in 8.5/8.6 are stale after this change by construction; the lead regenerates them.

## 10. Independent review (branch `v21r3/range-rv`, stacked on `v21r3/range`)

Re-run by a second engineer, on the host (macOS arm64, CPython 3.14.7, a second interpreter 3.12.14), in the Linux
guest (3.14.8), and by mutating the implementation. Nothing in `process_range.py` was changed: the review found no
defect in the product code. It found four gaps in the evidence, all closed by tests (7 added, 32 in the file now).

**10.1 What the 25 tests did not notice (wrong implementations that passed all 25).** Each variant is the committed
`process_range.py` with one thing made wrong; "25/25" is the implementer's file, "32/32" the final one.

| wrong implementation | result on the 25 tests | on the 32 |
|---|---|---|
| the claim without a lock, and without the `_mx` attribute (the one test that looks for `_mx` skips) | 24 OK + 1 skipped | FAIL: `test_two_threads_that_arrive_together_are_not_both_leaders` |
| the claim with a lock, but the check and the write in two critical sections (TOCTOU) | 25/25 OK | FAIL: the same |
| a waiter that returns as soon as the leader is `disposing` (past the ladder, before the reap, the pipe close and the escapee check) | 25/25 OK (by luck of the 20 ms poll: the leader had finished) | FAIL: `test_a_caller_is_held_until_the_release_has_ended_...` (5 subtests) and `..._waits_for_the_escapee_check_...` |
| `flight.done = True` set right after the ladder instead of at the end | 1 failure (a re-entry test, for another reason: no test pinned a waiter against this) | FAIL: the held-until-ended tests |
| the second look at escapees (Linux orphan re-parented to the anchor) deleted | 25/25 OK, and `tests/v2/p4/test_process_range.py` passes too (host and guest) | FAIL: `EscapeeLooks` |

The first two matter most: the claim is exactly where the original defect lives and its window is a few bytecodes.
`RealRange` (two real threads aligned by a barrier) did not see the unlocked claim in 100 runs — the "repeat until it
stops failing" the owner excluded. `ClaimAndWait.test_two_threads_that_arrive_together_are_not_both_leaders` parks one thread INSIDE the claim
(after its read of `_reaped`, through a property on a subclass: nothing of the design's names is needed) and brings a
second one to it. In a correct run the second caller is held and a bounded `Event.wait` (`CLAIM_PROBE_S`, 1 s) runs
out; a claim that lets it through sets the event at once. It is the only test of the file that waits on time, and a
correct implementation can not fail it on a slow machine (a slow machine can only hide a wrong one).

**10.2 `kill_check`, re-run.** The implementer's 25-test file, run again: `ProcessRange.release` 22 KILLED + **1 INFRA**
(mutant [17], `L457 not removed`: `while not current.done:` becomes `while current.done:`, a waiter that spins on the
claim instead of sleeping; alone it was KILLED, KILLED, INFRA in three runs, by a different test each time, because
only a rare hang window made the file fail). The bracket needs the same signature twice, so that mutant would have been
a coin flip in the lead's re-measurement. `AbandonedWorker` now asserts that its late caller is seen *polling*
(`second_is_held() == "waiting"`); [17] is KILLED, by that test, in 5 of 5 runs. With the 32-test file (T0 PASS, 32
tests): `release` 23/23, `_ladder` 15/15, `_release` 12/12, `_Flight.__init__` 2/2, `ProcessRange.__init__` 17/17
KILLED, 69/69. Kills that go only through an exception: `__init__` [0-13] (a dropped element of a tuple unpack:
`ValueError` at construction, which any test that builds a range meets), `_ladder` [8], [9] (`self._grace[None]`:
`TypeError` at the kill stage) and [14] (`s['']`: `KeyError`; the message text is asserted by another test). The
statement-deletion probe below is not a measurement of record.

**10.3 Statement deletions** (a probe of the review, not `kill_check`): each simple statement of `release`, `_ladder`,
`_release`, `_Flight.__init__` and the two new lines of `ProcessRange.__init__` replaced by `pass`, 38 variants, the
32-test file with its bounds shortened to 2 s. 33 FAIL, 3 hang (`flight.done = True`; the EXIT write; its flush: a real
anchor never exits), 2 SURVIVED before the additions: the two escapee looks (the first is killed by
`p4/test_process_range.py`, the second by nothing). After them none survives.

**10.4 Reproduced, not read.** Host `BASE`: 12 FAIL + 1 skipped of the 25, three runs, the exact `ValueError:
PyMemoryView_FromBuffer(): info->buf must not be NULL` from the real-`io` test; the same on 3.12.14 and in the guest
(real run of the fake-backend tests); this branch: 25/25, and 32/32 forty times on the host, three times on 3.12.14
and once in the guest. The alternatives of section 4 re-applied to `BASE` and run against the 32 tests: investigator's
`RLock` 7 failures (86 s), plain `Lock` 8 (116 s: self-deadlocks end at the tests' 10 s bound), swallow 18. Each is the
implementer's count plus the review's tests; one of the RLock/Lock failures is `AbandonedWorker`'s design-bound
assertion that the late caller is seen polling, which a blocking lock does not do although it holds the caller too.
Supplement (100 runs each, a fresh interpreter, `env -i`): `FM2_CLI_SUBJECT_3` on `BASE` 96 pass / 4 fail, the exact
error in 7 outputs, all four failing runs through `run.release()` -> `_close_pipes()`; on this branch 100/100, 0.
Importers re-run on this branch: `p4.test_process_range` 24, `test_c2_cli_invocation` 32, `test_probe_process_effect`
24, `test_v21_confine` 34 (host; guest X1 and hardened), `p4.test_interruption` 20 (3/3 in the foreground),
`test_python_callable_v2` 33, `p2.test_python_callable` 37, `test_c2_p9_harness` 31, `test_p6_orchestration` 32,
`test_no_dual_authority` 17, `p5.test_vacuity` 19, `p5.test_invariants` 50, `p0.test_destructive_authority` 13,
`p4.test_mutation_safety` 10, `hardening.test_process_owner` 7: all OK. The sealed records fail as section 8.6 says:
`BASE` k_nowork OK, p5_acceptance 1, checker_calibration 2, orchestration_conformance 1; this branch 1, 2, 2, 1, and
`PlanCorrection` and `Classify [P4]` for the digest of `process_range.py` / `aisef2/`.

**10.5 What stays open (not changed).** (a) D1 above is worse than "later callers see `None`": the outcome a caller gets
depends on a window of microseconds. Two threads call `release()` and the leader ends in RangeEscaped: a caller that
arrived during the release is given RangeEscaped; one that arrives after it ends gets `None`. In the two by-design tests
the stop thread's exception is read by nobody, so which of the two the probe's own `finally` is decides whether the
leak is seen. The product has no such pair of callers (section 2). The owner's choice is between (i) leaving it, (ii) a
range that remembers the Residual of its last completed release and re-raises it to every later caller until it is
cleared (the sequential outcomes of RangeEscaped change; RangeNotEmpty still re-runs the ladder). (b) A leader that
dies of something that is not a Residual after the reap (a failing `process_table()` in the escapee check) gives its
waiters `None`: the escapee check did not complete for anyone. (c) The sealed records and `docs/v2.1/REPORT.md`
(Q-RANGE row), `MUTATION-RUNNER-V2.md` (the intermittent-failure paragraph) still describe the question as open.

## 11. Follow-up, 2026-10-13 (`range-fu`): the process table's row ends at a line feed and nowhere else

Branch `v21r3/range-fu`, stacked on `v21r3/range-rv`. It owns `_ps_table` (and, as section 11.8 says, `_linux_table`) in
`aisef2/runtime/process_range.py`; `release`, `_release`, `_ladder` and `_Flight` are untouched.

**11.1 The finding, and the correction of the record.** `_ps_table` (macOS, `LINUX` false) read `ps -A -o
pid=,ppid=,pgid=,stat=,command=` in text mode and split it with `str.splitlines()`. The first report blamed "a newline in
a command line": that is not the trigger — `ps` prints a line feed in a command as `\012`. The trigger is a character
`ps` prints raw and `splitlines()` breaks at. Measured on this host (macOS 26.5.2, Darwin 25.5.0, CPython 3.14.7):

| character in the command line | `ps` in a UTF-8 locale | `ps` in the C locale |
|---|---|---|
| U+2028, U+2029 | **raw** | `M-bM^@M-(` (escaped) |
| U+0085 (NEL) | `M^E` (escaped) | `M-BM^E` |
| VT, FF, FS, GS, RS, CR | `^K ^L ^\ ^] ^^ ^M` (escaped) | the same |
| LF | `\012` | `\012` |

So **on this `ps` only U+2028 and U+2029, and only when `ps` itself runs in a UTF-8 locale** (the mutation workers run with
`LANG=en_US.UTF-8`), reach the parser; U+0085 does not reproduce here although the lead's report names it. Other `ps`
versions may differ; the fix does not depend on which characters a `ps` leaves raw.

**11.2 What it did, on `BASE`** (`repro-ps-table.py.txt`: one child of its own per case, `/bin/zsh -c 'echo ready; read
x; : TEXT'`, ended by closing its stdin; 10 characters x 2 locales x 3 shapes = 60 real cases; nothing signalled). With
U+2028 or U+2029 in a UTF-8 locale, three outcomes, by what follows the character:

| text after the character | `process_table()` on `BASE` |
|---|---|
| four or more words (`alpha beta gamma delta`) | `ValueError: invalid literal for int() with base 10: 'alpha'` — every `ProcessRange` operation on the host raises |
| fewer than four words | no error; **the child's `command` is silently cut** at the character (a survivor whose marker follows it is not found by `confine._survivors`) |
| row-shaped text (`99998 1 99998 S x`) | no error; **a process that is not there is in the table** (and the real row of that pid, if there is one, is overwritten) |

After the change: 60 of 60 cases return the whole table, the child's row present, `command` equal to what `ps -p PID -o
command=` prints, and no made-up pid (`repro-after-fix.txt`; before: `repro-before-base.txt`). The second and third
rows of the table are worse than the one the lead reported: they do not raise.

**11.3 The fix.** `_ps_table` reads bytes (no text mode: it also turns CR into LF), decodes with replacement, splits at
`"\n"` only and takes a non-blank line as a row with one pattern — `pid ppid pgid stat [command]`, ASCII digits, columns
separated by spaces, the command the rest of the line as printed (a command that starts with U+2028 keeps it). Blank
lines (the output's end) are no rows. A zombie (stat `Z...`) is skipped, as before.

**11.4 The error, its class and why.** A non-blank line that is not a row raises `ProcessTableError(Exception)`, naming
`line[:80]` as `repr` (a separator is shown, not printed). Not skipped: a row skipped is a process the table cannot see —
a member the emptiness check would call gone, a survivor `_survivors` would miss. The class from how callers treat a
table failure: nobody catches one specifically (`ProcessRange.release`/`members`, `confine._survivors`,
`owned_run.harness_orphans` let it propagate, as the `CalledProcessError` of a failed `ps` always did), and
`StoryScope._release` turns any `Exception` that is not a `Residual` into FAILED and blocks what depends on the range.
So it is **not a `Residual`** (RESIDUAL says "named, not released"; this says nothing about what is alive) and **not a
`RangeError`** (the callers that catch that read it as "the tool could not start" and go on; a table that cannot be
read must not). Both are pinned by tests.

**11.5 Alternatives, run against the 16-test file** (each a copy of `_ps_table` in a scratch tree, with the same typed
error where it raises; "cases" counts subtests):

| alternative | result |
|---|---|
| A. `split("\n")` + the old `split(None, 4)` + `int()`, short lines skipped as before (the literal fix) | 27 cases fail, 7 tests |
| B. as A, but a short line raises too | 18 cases fail, 2 tests: 13 where a command begins with a Unicode-whitespace character (U+2028, U+0085, VT, FF, FS ... — `split(None, 4)` strips it: not "as `ps` printed it"); 5 where `int()` and `split()` accept `+5`, `1_0`, a non-ASCII digit, tab-separated columns, a separator before the pid |
| C. `splitlines()`, lines that are not rows skipped | 24 cases fail, 11 tests (truncated commands, made-up rows, CR) |
| D. text mode, then `split("\n")` | 2 errors: a CR in a command becomes a break |

**11.6 Requirement -> test** (`tests/v2/test_v21_r3_range_fu_ps_table.py`, 16 tests, ~0.8 s; `..._linux_table.py`, 7):

| requirement | test |
|---|---|
| a command holding any of 13 separator characters (U+0085, U+2028, U+2029, VT, FF, FS, GS, RS, CR, US, TAB, NBSP, U+3000) in 5 positions is one row, whole, and nothing after it is a row | `RowIsALine.test_a_command_holding_a_separator_is_one_row_with_the_whole_command` |
| a raw CR / an escaped LF / non-UTF-8 bytes beside a separator / blank lines / no final newline | `RowIsALine.*` (4 tests) |
| zombie skipped; a row without a command has `""`; `ps` is asked for exactly these columns once; a failed `ps` is `CalledProcessError`, never a table | `RowShape.*` |
| 12 shapes of a line that is not a row are `ProcessTableError` naming `repr(line[:80])`, not a `ValueError`/`Residual`/`RangeError`; the 81st character is not named; a separator is shown; no partial table | `NotARow.*` |
| the table readers (`process_table`, `_Posix.members`, `_Posix.escaped`) raise; a `StoryScope` records the release FAILED with the line and leaves the scratch directory | `FailsClosedWhereItIsRead.*` |
| a real `/bin/sh` with U+2028, U+2029, U+0085 in its command line, `ps` in a UTF-8 locale: its row is whole and equals `ps -p`'s; no made-up pid | `RealPs` (macOS only, ~0.2 s: the child waits for its stdin, no sleep, no signal) |

**11.7 Real, simulated, neither.** *Real, on the host (macOS):* the 60-case reproduction before and after; `RealPs`.
*Real, in the Linux guest (`guest.sh`, X1; Python 3.14.8):* the `_linux_table` reproduction and `RealLinux` (section
11.8), before and after; the new test files and `p4.test_process_table`: 27 tests OK, 1 skipped (`RealPs`).
*Simulated:* every other test — a real child process prints bytes I chose, so `subprocess.run`'s capture, `check` and
decoding are the real ones, but the rows are mine; the `/proc` of `LinuxTable` is a directory the test writes.
*Neither:* Windows (the tests are portable by construction: no signal, no path, the POSIX-only ones are skipped; not run
there); a `ps` other than this macOS's; the real OpenCode client.

**11.8 `_linux_table`: the same hazard, another shape (second commit, droppable).** It read `/proc/<pid>/stat` with
`read_text()`. A process named with bytes that are not UTF-8 (`prctl(PR_SET_NAME)`; an executable file with such a
name) raises `UnicodeDecodeError` — not the `OSError` it skips — for the whole host. **Real run in the guest, before:**
`process_table()` after `prctl(15, b"\xff\xfeab")` raised `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff`
(`guest-linux-comm.sh.txt`); after the change it returns the table (`guest-comm-after.txt`). The file is read as bytes and
decoded with replacement, as `cmdline` already was. Nothing else changed there; other failure shapes of that reader
(`rindex`, `f[19]`) were not measured and are untouched.

**11.9 Mutants** (`kill_check`, T0 PASS):

| function | tests | mutants | killed | survived |
|---|---|---|---|---|
| `_ps_table` | the new file (16 tests) | 24 | 24 | 0 |
| `_ps_table` | existing `p4/test_process_table.py` (as changed) alone | 24 | 22 | 2: `' '` emptied (the blank-line strip) and the message prefix emptied — the new file kills both; both files together 24/24 |
| `_linux_table` | `test_v21_r3_range_fu_linux_table.py` | 17 | 17 | 0 |

**11.10 The same property elsewhere** (`grep` over `aisef2/`, `validation/`; fixed only inside `process_range.py`):

| site | verdict |
|---|---|
| `validation/v2/cleanup_authority.py:99` (`_read`, `ps -A ... lstart=,command=`) | **same hazard, and it is the runner's authority.** `splitlines()` + "a continuation line is no row" (skipped). Measured, read-only, `dry_run=True` (`finding-cleanup-authority.py.txt`): a process born before the boundary, not owned, becomes `signalled` once a carrier's command line holds U+2028 + a row naming its pid with the runner as parent. Command lines are implementation output: INV-MUTATION-AUTHORITY. **Not fixed (not mine); the lead's.** |
| `cleanup_authority.py:124` (Windows, PowerShell `|`-joined), `:184` (`carriers`, `ps -E`), `:220` (`cwd_under`, `lsof -Fpn`) | same property; the last two yield candidates that `signal_owned` re-proves against `_read`'s table. Windows' `CommandLine` holds a raw LF, so `split("\n")` would not fix it there: structured output. Not measured. |
| `aisef2/app/client.py:39` (`read_session`) | JSON allows U+2028/U+2029 raw in a string; the event is cut, both halves fail `json.loads`, `except ValueError: continue` drops it: **the model's `text` event is lost silently** (`finding-client-read-session.py.txt`, synthetic log). Not established that the real client writes them raw. `app/usage.py:48` reads only `step_finish` (no free text): not affected as far as the file shows. |
| `aisef2/quality/relevance.py:101` (`story_diff`), `quality/vacuity.py:103` (`file_patches`) | a changed line holding FF, U+0085 or U+2028 is two "lines" to them, one to git: `story_diff` reports the later added lines one off (`[2, 5]` for `[2, 4]`), `file_patches` marks the patch opaque (fails safe) (`finding-diff-parsers.py.txt`, synthetic patch, the real parsers). Developer-controlled input. |
| `aisef2/app/lineage.py:236` (`git worktree list --porcelain`), `app/confine.py:181` (`_sections`, the probe's own output) | a path with U+2028 is cut; low (kernel-named `wt-<story>`; operator-given mounts). `lineage.py:219` reads hex ids: not affected. |
| `aisef2/probe/file_artifact.py:250` | a different question (what a "line" of an observed file is); `probe/cli_invocation.py:415` is `bytes.splitlines()`, which breaks at LF/CR only: not affected |
| `validation/p12_watchdog.py:67`, `validation/v21/sandbox/linux_guest.py:116`, V1 `aisef/harness/process_owner.py:49,177` | the watchdog could match a made-up row (low); `ps()` is a display list; V1 reads `pid ppid` only, exactly two fields: not affected |
| `validation/v2/mutation.py:1317-1378` | every process scan goes through `cleanup_authority` (`host_table`, `carriers`, `cwd_under`): inherits the first row |

**11.11 Existing test changed.** `tests/v2/p4/test_process_table.py`, `NoPidAncestry`: the test that skipped "short
lines" (`   12    10`, pid and ppid only) now expects `ProcessTableError` for it, and is renamed
`test_the_ps_reader_skips_zombies_while_a_line_that_is_not_a_row_and_a_failed_ps_are_errors`; every other assertion is
unchanged. The requirement that moved it is the brief's "never a silently skipped row: a skipped row is a process the
table cannot see". The brief's list of rows to keep is unchanged (a four-field row has an empty command). If the lead
reads "short lines as today" instead, the revert is the one `if` that raises for such a line; the other lines of
this section stand.

**11.12 Not established.** (a) Which `ps` versions print which characters raw; only this host's was measured. (b) That a
real `ps` never prints a short line: the change makes it an error that names the line instead of a silent skip; if one
ever does, every `ProcessRange` operation on that host raises until it is understood. (c) `_linux_table`'s other
failure shapes. (d) Windows. (e) A waiter of a single flight whose leader died of `ProcessTableError` after the reap
gets `None`, as section 10.5 (b) says of any non-`Residual` — this adds one more way to reach it, no new class of it.
