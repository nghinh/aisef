# P4 — story / run transaction: implementation semantics

Normative for WP-4.1..WP-4.6. It implements RFC §17–§24 and §35 and changes no frozen semantics: F2 routing, F5
probe semantics, P1/P2 admission, P3 journal authority and the six projections are used as they are. Where the RFC
leaves a choice, the choice is made here once, and the tests and evidence cite this file.

## 0. What P4 does not touch

The P3 modules (`aisef2/journal/{event,compat,writer,fold}.py`, `aisef2/journal/projections/`) are sealed
(`P3-FINAL-SEAL.json`) and are not edited. Journal format 1 is immutable. Everything below is added beside them.

## 1. Journal format 2 (§35, F1)

A format bump through the frozen compatibility mechanism: the format is declared once, in `run/begin` at seq 0
(`journal_format: 2`); the envelope (`Event`), the vocabulary and the codec (`event.encode` / `event.decode`, the
chain) are format 1's, unchanged.

* **Reading.** `aisef2.journal.format2.reconstruct(text)` reads the declaration and reads a format-1 journal with the
  P3 reader (`compat.reconstruct`, unchanged) and a format-2 journal under the format-2 schemas. Any other declared
  format refuses. Unknown required types refuse; unknown ignorable types are skipped; a torn tail is reported — the
  same rules, the same messages.
* **Every format-1 type keeps its format-1 schema object**, so a format-1 event means the same in both formats. Two
  format-1 types gain one optional field in format 2 — `run/interrupted` and `run/end` may carry `synthetic: true`
  (a closer written by repair, §7). A format-1 journal can never contain it.
* **New schemas** (types of the frozen vocabulary that format 1 could not write):

| type | fields | cites | rule |
|---|---|---|---|
| `story/resource-acquired` | `story_id`, `resource`, `kind` (`ResourceKind`) | — | a resource id is acquired once per story; its kind's disposal rank is not after the story's previous acquisition (§2) |
| `story/resource-released` | `story_id`, `resource`, `kind`, `status` (`ReleaseStatus`), `detail`, `synthetic` | exactly one `story/resource-acquired` of the story | the cited acquisition is that resource, unreleased, and the most recent unreleased one of the story (reverse order) |
| `capability/resolved` | `name`, `grade` (`IdentityGrade`), `enforcement` (`Enforcement`), `binding` (str → str), `identity` (sha256) | — | a name once per run |
| `run/spec-resolved` | `runspec_hash`, `aggregate_min_grade`, `capabilities`, `revision` (full SHA) | — | once per run; every named capability resolved before it; the aggregate is their minimum |
| `tool/invoked` | `story_id`, `call_id`, `tool` | — | a call id once per run; written when the tool is dispatched |
| `tool/result` | `story_id`, `call_id`, `outcome` (`OperationOutcome`), `signal`, `provenance` (`SignalProvenance`), `synthetic`, `detail` | the `tool/invoked` of the call, except `NOT_STARTED` (cites none) | one result per call; `OUTCOME_UNKNOWN` / `NOT_STARTED` only when `synthetic`; a signal only with `SIGNALLED` |
| `provider/result` | `story_id`, `outcome`, `synthetic`, `detail` | exactly one `provider/request` of the story | one result per request; `OUTCOME_UNKNOWN` only when `synthetic` |

`ResourceKind`, `ReleaseStatus`, `OperationOutcome` and `SignalProvenance` are payload enumerations of format 2 only
(`aisef2.journal.format2`); format 1's enumerations are unchanged. `OUTCOME_UNKNOWN` and `NOT_STARTED` are §20.2's.

* **Writing.** `format2.JournalWriter2` has the P3 writer's surface and discipline (append / emit / events / head /
  path / close; `seq == index` at four layers; validation at the append site; fsync per append; a failed write
  truncates and poisons). It writes format 2 only and never extends a format-1 journal: a format-1 journal is read,
  never re-declared.

## 2. StoryScope (WP-4.1, §17.1, §18)

An explicit ordered stack of resources. `acquire(resource)` pushes and emits `story/resource-acquired`;
`dispose()` releases in reverse order, one at a time, each awaited, and emits one `story/resource-released` per
resource. It emits through the run's journal (a callable handed in); it owns no writer.

* **Disposal rank** (RFC order: processes → sandbox → worktree → scratch): `SESSION`, `TOOL_GRANT`, `REVIEW_SCOPE` 0;
  `PROCESS_RANGE` 1; `SANDBOX` 2; `WORKTREE` 3; `SCRATCH` 4. Acquisition is in non-increasing rank, so reverse
  disposal is in non-decreasing rank. An acquisition that would break it is refused (`ORDER`) — the ordering is a
  property of the stack, and the journal refuses a release out of order (§1).
* **SCOPE-1.** Acquiring while disposing or disposed is refused (`INACTIVE_ACQUIRE`); the offered resource is
  released at once, so it does not escape unaccounted.
* **SCOPE-2.** A release that raises is recorded `FAILED` with its error, and disposal goes on to the next resource.
  One exception, by §17.1: a `PROCESS_RANGE` not proved empty makes every later resource of higher rank (the sandbox,
  worktree and scratch it could write to) `RESIDUAL` — named, not released. Nothing is skipped silently: every
  acquired resource gets exactly one release record.
* **Hanging release.** Each release has a bound (`release_timeout_s`; `None` = unbounded). A release still running
  at its bound is `RESIDUAL` ("still running"), and the range rule above applies.
* **SCOPE-3.** Order is the stack's: the same acquisitions give the same disposal order, never concurrency's.
* `release(resource)` releases the most recent resource early (a tool's range when the tool is done); anything else
  is refused (`ORDER`), so the reverse order holds for early releases too.
* A release whose journal record is refused is still performed; the report names it `unrecorded`, and the journal —
  missing that record — refuses to vouch for any later order.
* `dispose()` returns a report; `DISPOSE` fails (the report says so) when any record is not `RELEASED`.

## 3. Process ranges (WP-4.2, §17.1)

Ownership is established by the operating system, never by PID equality or PID ancestry.

* **POSIX.** A range is a new session and process group whose leader is the range's **anchor**, a small stdlib
  process (`aisef2/runtime/range_anchor.py`) that is the controller's own child and is **not reaped until the range is
  disposed**. While it is unreaped its PID — the group id — cannot be reused, so a signal to the group reaches only
  the range's members. The anchor starts the target, reports its exit status, and watches its control pipe: if the
  controller dies (end of file), the anchor kills its own group. On Linux the anchor is a child subreaper, so a
  descendant that escapes with `setsid` and is orphaned re-parents to it and is reported as a residual. The anchor
  reaps every child except its target, as init would, so an adopted orphan that dies never lingers as a zombie (which
  would still answer `kill(pid, 0)` and keep its group signalable); the target is reaped only by its own wait.
* **Windows.** A Job object with `KILL_ON_JOB_CLOSE` and no breakaway. The anchor is assigned to the job before it
  starts the target, so every descendant is a member; if the controller dies, the job closes and kills them.
* **Emptiness is measured**: POSIX — the live members of the group other than the anchor, from the process table
  (`/proc` on Linux, `ps` on macOS); Windows — the job's own process list. Never the direct child's exit code.
* **Escapes.** A descendant that left the group (`setsid`) is not a member and is never signalled. When one is alive
  at disposal, the release raises `RangeEscaped` (`RESIDUAL`, naming it), so nothing it could write to is released.
  Windows: the job allows no breakaway, so nothing can escape.
* **Ladder** (`release`): cooperative (`SIGINT`) → grace → `SIGTERM` → grace → `SIGKILL` → wait; each signal only
  while the anchor is unreaped. Windows: `TerminateJobObject` (exit status `0xAE5F`, so a controller's stop is
  recognisable) → wait. A range that does not empty is `RangeNotEmpty`
  (`RESIDUAL`), never a silent success. After the anchor is reaped the range never signals again.
* **Signal ledger.** Every signal the controller sends is recorded; §7 reads it for provenance.
* **WIN-PID-1/2 (V1-PF-001).** Where a process table is walked at all (residual *reporting*), the walk has a visited
  set, drops parent edges older than the child (a stale parent), and selects nothing for termination: termination
  targets come only from the ownership mechanism.

## 4. RunScope, lease, sentinel (WP-4.3, §18.1, §19)

* **Begin**: acquire the lease (an OS file lock, released by the OS if the process dies) → preflight (read the
  previous sentinel: `NONE` / `CLEAN` / `TORN`, and the previous run's named residuals) → write and fsync the `OPEN`
  sentinel → open `JournalWriter2` (`run/begin`) → resolve and freeze `RunSpec` (`capability/resolved`…,
  `run/spec-resolved`) → execution.
* **Shutdown** (successful): every StoryScope disposed and every story `ENDED` in the journal
  (P3-RESIDUAL-DISPOSAL-ORDER: otherwise shutdown is refused before anything is written, and the run must be
  interrupted instead, §7) → `run/dispose-begin` → `run/end` → writer closed → `CLEAN` written and fsync'd → lease
  released **last**. A failure at any step leaves the sentinel `OPEN`; the lease is still released last.
* `CLEAN` means a *successful* shutdown (§19: "at successful termination"). An interrupted run, however orderly, leaves
  the sentinel `OPEN`: the next preflight reports it `TORN`, and its journal says it was interrupted.
* `retry(story, limits)` is the only way a story retries: it appends `story/retry` only when the journal-derived
  decision (§6) says yes, citing the failure the decision read.
* The sentinel is written by replace-after-fsync, so a failed `CLEAN` leaves the `OPEN` file intact (RUN-4). It is
  not evidence and no gate may cite it (static check).

## 5. RunSpec and identity grades (WP-4.4, §23, §24)

* `CapabilityIdentity(name, grade, tuple_, enforcement)`. `VERIFIED` binds a locally computed sha256 digest (a
  version label alone is refused); `ATTESTED` binds provider, endpoint, declared model, route, client and a locally
  measured preflight fingerprint (deployment when exposed); `OPAQUE` binds what is known and bars Q6 and sealed
  cohorts.
* `RunSpec(capabilities, aggregate_min_grade, settings, runspec_hash)`; `runspec_hash` binds every capability tuple,
  grade and enforcement level, the settings with their layer provenance and the full revision SHA. Execution
  locators (the checkout path, the journal path) are carried beside it and never hashed. No fallback: a capability
  whose identity cannot be established is `OPAQUE`, never a weaker claim dressed as a stronger one.
* Comparable only with the same capability tuples, grades and enforcement (§23).

## 6. Budgets (WP-4.5, §22)

`aisef2.control.budget` decides a retry from the journal only: the `retry_target` and `budgets` projections of the
journal prefix (P3, unchanged) and the resolved retry counts (`None` = no approved count = no retry). It keeps no
counter; static check NO_SIDE_RETRY_COUNTER refuses one anywhere in `aisef2/` outside the projections.

## 7. Interruption, provenance, repair (WP-4.6, §20.2)

* **Operations** (`aisef2.runtime.tool`): `tool/invoked` is written when a tool is dispatched inside the story's
  process range; `tool/result` records `COMPLETED`, `FAILED` (exit status) or `SIGNALLED` with provenance
  `CONTROLLER` (the range's ledger shows the controller sent that signal) or `UNKNOWN`. A signal exit is never mapped
  to an owner here — no failure code is invented (INTERRUPT-SIG-1, -2).
* **Live interruption** (`RunScope.interrupt`, or `RunScope.interruptible()` around the run's body, which turns a
  SIGINT into it): `run/interrupted {abandoned: false}`; each unfinished operation is closed — dispatched →
  `OUTCOME_UNKNOWN`, not yet dispatched → `NOT_STARTED`, an open provider request → `provider/result OUTCOME_UNKNOWN`
  — all synthetic and at the last real event's time (INTERRUPT-SIG-3); every StoryScope disposes, graceful-first;
  `run/dispose-begin`, `run/end`; the writer closes; the sentinel stays `OPEN`; the lease is released last. A second
  SIGINT during disposal abandons: every resource left is named `RESIDUAL`, `run/interrupted {abandoned: true}` is
  written and nothing follows it.
* **The P2 probe path, corrected by ARCHITECTURE-EXCEPTION-V2-003** (RFC §9.3, approved 2026-09-23). The
  `python_callable` harness now runs inside a P4 process range, and that range's ledger is the one authority on what
  the controller sent. After `DISPATCHED`: the ledger holds the signal → the controller stopped its own observation,
  an interruption (`ProbeInterrupted`, raised, never a `ProbeResult`); it does not → `EXECUTED` +
  `INDETERMINATE(NON_CONTROLLER_SIGNAL)`, owner INTEGRATION, never retried. Before `DISPATCHED` V2-002 is unchanged.
  A probe never signals a process itself and never keeps its own ledger (static rule ONE_SIGNAL_AUTHORITY).
* **Repair** (`aisef2.runtime.repair`), for a journal whose writer died: drop a torn tail (never an event); close
  every open operation `OUTCOME_UNKNOWN`; name every unreleased resource `RESIDUAL`; then `run/interrupted`
  (`abandoned` iff the run was already interrupted) and, unless abandoned, `run/end` — all `synthetic: true`, all at
  the last real event's `time`. A repaired journal has nothing open, so repairing it again adds nothing; repairing
  the same journal twice gives the same bytes. Repair never touches the sentinel: the run stays `TORN`.
* No path creates a sequence gap: closers are appended; a torn tail was never an event.

## INV-MUTATION-AUTHORITY *(standing invariant, owner, 2026-09-24 — enforcement documentation; no RFC text is changed)*

> Mutation, fault injection, test failure, probe result, or implementation-under-test output MUST NOT expand
> host-side destructive authority.
>
> Authority to kill, delete, clean, release, terminate, or mutate external resources MUST come exclusively from an
> independently established controller view.
>
> The implementation-under-test may REDUCE confidence to RESIDUAL_OWNERSHIP_UNKNOWN. It may NEVER expand destructive
> authority.

Origin: P4-FINDING-011 (2026-09-23) — a mutant of `_Posix.escaped` reported every process on the host as escaped,
and the mutation runner, trusting that report, signalled them all. Enforcement:

* runtime — `validation/v2/cleanup_authority.py` is the only way the mutation runner signals a process. A pid, a
  group or a stray that code under mutation *reports* is a claim: it is signalled only once the authority's own
  reading of the host proves it the runner's (parent chain to the runner, born after the boundary in the table's own
  clock; a group only through its leader; a claimed pid only as a proved member of a controller-created group —
  `prove_member`). Anything else is RESIDUAL_OWNERSHIP_UNKNOWN: no action, the step fails. MUT-SAFE-1..8,
  MUT-AUTH-NEG-2 (`tests/v2/p4/test_mutation_safety.py`).
* static — `validation/v2/destructive_authority.py` discovers every destructive call site under `aisef2/`,
  `validation/v2/` and `tests/v2/` (signals, job termination, path removal, shell-level equivalents) and requires
  one row of `validation/v2/destructive_sites.json` per site, declaring a narrow authority source
  (`CONTROLLER_CREATED_HANDLE`, `CONTROLLER_CREATED_PID`, `CONTROLLER_CREATED_PROCESS_GROUP`,
  `INDEPENDENT_HOST_TABLE`, `SCOPE_OWNED_PATH`, `TEST_CREATED_HANDLE`, `TEST_CREATED_PATH`, `DELEGATION`,
  `GUARD_NEGATIVE_PROBE`, `LIVENESS_PROBE_SIGNAL_0`, `COLLECTION_METHOD`) whose derivation shape the checker
  validates. A site without a row, a row without a site, a derivation that no longer matches its class, an ambiguous
  target, or a destructive API outside the taxonomy fails the check, closed. Q0-calibrated with MUT-AUTH-NEG-1.
* the range itself (§3) signals only the group it created and the anchor it holds; a scope (§4) removes only the
  directories it registered; a test signals only the processes it started and removes only the paths it made.

