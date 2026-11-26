# AISEF v2.3 — C5 PARALLEL STORY EXECUTION (lane L4-PARALLEL, W4a) — DRAFT against the FROZEN C-1

**Status:** DRAFT, implementation-ready, written against contract C-1 (FORMAT-4 freeze, owner ruling 2026-11-26,
`docs/v2.3/amendments/C-1-FORMAT-4-FREEZE.md`) at HEAD 50960ffa. Every schema fact below is FROZEN input
(design §4.6, §3.1, §7); nothing here re-opens it. Changes after the lane starts are dated amendments.

**Covers:** C5 (MASTER-CHECKLIST:53) + #5 (wave derivation must reconcile story- vs criterion-level
`depends_on`) + the G9 pattern (IMPROVEMENT-ROADMAP.md:203-205, design reference only). Prerequisites per
DEPENDENCY-DAG.md:211-213: E5 (landed, W1b), E6/C-1 (frozen 2026-11-26), E7 (W2b; the `run_stories()` seam).

---

## 1. Measured facts that fix this design (verified in THIS tree, 2026-11-26)

| # | Fact | Evidence |
|---|---|---|
| C1 | Stories run strictly serially today: `for story in project.order():` dispatches one `sr.run_story` at a time; `budget.reached()` is checked per story before dispatch; `delivered` (regression-test inputs) is updated after each commit. | `aisef2/app/run.py:674-698`, `:675`, `:683`, `:690` |
| C2 | `Project.order()` is a linear topological sort appending `ready[0]` one at a time, ties by name; it reads ONLY story-level `depends_on`. Criterion-level `depends_on` exists on every `PlanObligation` and is never reconciled against it (CODE-AUDIT #5). | `aisef2/app/bundle.py:124-136`, `:95-102` (schema), `:146` (obligation `depends_on`) |
| C3 | The journal has exactly one writer, owned by RunScope; every production append goes through `Authority`, which `peek`s all six projections and then commits folder state AFTER `writer.append` returns — a read-check-write sequence with NO lock. Two threads interleaving `Authority.append` can commit stale folder state or race `_assign()` (`seq == index`). | `aisef2/runtime/run_scope.py:102,123-125,144-148`; `aisef2/journal/fold.py:133-160`; `aisef2/journal/writer.py:59-60,62-94` |
| C4 | The writer is synchronous and self-protecting per append: validate + pre-check before a byte, fsync every append, truncate-and-poison on a failed write. Nothing in it assumes a single thread except seq assignment (C3). | `aisef2/journal/writer.py:62-94` (P3 discipline) |
| C5f | Per-story isolation already exists: every attempt acquires its own scratch + implementer worktree + verifier worktree (`wt-{story_id}`, `verifier-wt-{story_id}`) as git worktrees of the one repo; names are unique per story, re-acquired per attempt after disposal. | `aisef2/orchestrate/story_runner.py:239-241`; `aisef2/orchestrate/workspace.py:130-138` |
| C6 | The merge point is a compare-and-swap on the shared branch: `GitMerger.merge` reads `tip = base()`, merges in a worktree named `merge-{tip}-{candidate}`, then `update-ref refs/heads/main head tip` and RAISES RuntimeError ("branch moved during the merge") if the tip moved. Concurrent merges therefore do not corrupt main — the loser gets an untyped UNKNOWN failure, which burns an attempt. | `aisef2/orchestrate/workspace.py:174-200`, CAS at `:189-192` |
| C7 | An attempt's parent is read at its begin: `base = merger.base()` (the main tip), journaled as `story/begin.parent`. `_committed(run)` (admission + PRESERVE scope) reads the STORY_STATE projection at call time. | `aisef2/orchestrate/story_runner.py:222-223`, `:187-188`, `:256-257`, `:317-318` |
| C8 | `_freeze_plan` is check-then-act: `if not any(e.type == PLAN_FROZEN ...)` then append — two concurrent first stories would write two `plan/frozen` events. | `aisef2/orchestrate/story_runner.py:191-194` |
| C9 | Stories spend their wall time blocked in SUBPROCESSES: every developer/reviewer call is one `opencode run` child process with its own per-story, per-attempt log file (`{story_id}.developer.{attempt}.jsonl`). The kernel itself is I/O-bound per story, not CPU-bound. | `aisef2/app/client.py:298-307`; `aisef2/app/adapters.py:76-87` |
| C10 | The runtime already anticipates non-main-thread execution: `_second_interrupt_abandons` installs a SIGINT handler only on the main thread. The run lease is one OS lock per run (RUN-2) — a second PROCESS cannot share the writer at all. | `aisef2/runtime/run_scope.py:252-260`, `:58-86` |
| C11 | StoryState folds per `story_id` (a dict keyed by sid): interleaved events of DIFFERENT stories are already legal under the frozen table; all `STORY`/`WITHIN` rules are per-story. The run-level `RUN` table is story-blind. | `aisef2/journal/projections/story_state.py:26-71`; FORMAT-4 §3.1 |
| C12 | The E5 contained-fault machinery is per-attempt and self-closing: one handler from `story/begin` to POST_MERGE, synthetic closers for the attempt's own unanswered `provider/request`s, DECIDE..END always written. Nothing in it reads another story's state. | `aisef2/orchestrate/story_runner.py:236,409-446,447-466`, closers `:419-425` |
| C13 | Interrupt closes unanswered requests run-wide and is driven from the thread that calls it; `run.append` is legal in states RUNNING and INTERRUPTED only. | `aisef2/runtime/run_scope.py:206-249`, `:144-148` |
| C14 | Frozen C-1 inputs this design builds on and may not change: §4.6 (closing identity, quoted verbatim in §3.5 below), §3.1 (the table; `story/begin` legal only from ABSENT/ENDED_RETRY), R-CLOSED, optional `base` on `story/resource-acquired` for `kind == WORKTREE`. | FORMAT-4-DESIGN-DRAFT.md §3.1, §4.6; C-1-FORMAT-4-FREEZE.md |
| C15 | File ownership (DAG §4 W4a, plan §2): L4-PARALLEL owns `plan/drift.py`, `app/{bundle,bundle_cli,run}.py`, `plan/{static_admission,obligation}.py`, `orchestrate/{workspace,story_runner}.py`, `journal/writer.py`, `runtime/story_scope.py`. `run.py` handoff: L2-RECORD → L3-CLIENT (D1 hunks) → **L4-PARALLEL/RESUME** → L5-AUTHOR. `app/settings.py` is L4-REVIEWER's (W4a). `runtime/run_scope.py` is owned by NO W4 lane. | DEPENDENCY-DAG.md:373; ACCELERATED-DELIVERY-PLAN.md §2:52-54 |

## 2. Scope and non-goals

C5 parallelizes ACROSS stories, never within one. Non-goals, so nobody waits on this lane for them:
- N1. No second journal, no buffered/deferred appends: the journal is the live authority mid-attempt
  (budget.charge, gates, projections read it) — the G9 "write after the pool drains" half does NOT transfer;
  what transfers is the serialized append point + the closing identity check (frozen §4.6 says exactly this).
- N2. No preemptive cancellation of a running story (SIGINT waits for in-flight attempts; §3.7).
- N3. No bundle `write_scope` schema. Per-story worktrees + the serial landing lock arbitrate write conflicts
  (a true conflict is a typed MERGE CONFLICT, C6); a declared write-scope field is BUNDLE-FORMAT-2 (C-6) territory.
- N4. No change to `Project.order()` semantics (serial mode and every existing caller keep byte-identical behavior).
- N5. C1 (stall monitor) and BUNDLE-FORMAT-2 are separate L4 items; C5 only guarantees C1's input exists
  (per-story worktrees, DAG:218).
- N6. No process-based workers (C10: the lease and the in-memory Authority forbid it); no async rewrite.

## 3. The mechanism (normative)

### 3.1 Waves — NEW `Project.waves()` + the #5 reconciliation (`aisef2/app/bundle.py`)

- `story_edges(self) -> Mapping[str, frozenset[str]]`: the UNION of (a) story-level `stories[s]["depends_on"]`
  and (b) criterion-level edges lifted to stories: for each obligation o and each d in `o.depends_on`, an edge
  `story_of(o) <- story_of(criterion d)` when the stories differ (C2).
- **#5 refusal at load/seal** (W4 gate, DAG:489): a lifted edge NOT covered by a story-level edge (directly or
  transitively) is an UNDER-DECLARED dependency → `BundleError` naming both criteria and both stories. `load`
  refuses it (bundle.py), `seal` refuses it and `lint` reports it (bundle_cli.py). A 2.2-sealed bundle whose
  declarations already cover its criterion edges loads unchanged.
- `waves(self) -> list[list[str]]`: Kahn layers over `story_edges`, each wave sorted by name. Invariants pinned
  by test: `order()` is unchanged; `[s for w in waves() for s in w]` is a valid linearization of the same DAG;
  cycle refusal identical to `order()`'s.

### 3.2 Worker model — threads (decided from the engine, not preference)

`concurrent.futures.ThreadPoolExecutor(max_workers=width)`. Grounds: stories block in `opencode` subprocesses
(C9) so threads buy full overlap of the paid wall time; RunScope/Authority/StoryScope are in-process objects
and the run lease is one OS lock (C10) — processes cannot share the writer; the runtime already guards the
main-thread-only SIGINT path (C10). `width` comes from settings key `parallel` (int ≥ 1, default 1 = serial,
OFF by default) — a one-hunk request to L4-REVIEWER (settings.py owner, §4); `execute()` also takes
`workers: int | None = None` as the test override.

### 3.3 The serialized append point — NEW `aisef2/orchestrate/parallel.py`, class `LockedRun`

ONE `threading.RLock`, owned by `LockedRun`, a facade constructed by the driver around the RunScope and handed
to `run_story` in place of `run` (duck-typed: `run_story` only calls `append`, `state`, `events`, `retry`,
`story`, `.journal` reads none). EVERY method acquires the lock: `append` (serializes Authority's
peek-then-commit and the writer's `_assign`, C3), `state`, `events` (returns the tuple snapshot), `retry`,
`story` (serializes the `_scopes` dict). The lock lives in C5's own new file — NOT in `run_scope.py` (owned by
no W4 lane, C15) and NOT in the sealed writers (FMT3-7). Serial mode (`width == 1`) bypasses the facade
entirely: zero new code on the 2.2-equivalent path. `ponytail:` one global run lock — per-projection locks
only if append contention ever measures as the bottleneck; the appends are µs beside provider minutes.

### 3.4 The landing lock — MERGE..END serial, the rest parallel

Stage boundaries (E5 Stage enum, story_runner.py:57-73):
- **Parallel across a wave:** ACQUIRE(1) .. REVIEW_SCAN(8) — per-story worktrees (C5f), per-story sessions and
  log files (C9), per-story scratch. Journal appends interleave across stories through the one `LockedRun`
  (legal per C11); each story's own events stay in order because each story is single-threaded.
- **Serial under `LockedRun.landing` (a second RLock in the facade):** MERGE(9) .. END(13), including the B7
  revert paths and the exception handler's revert (C12). Grounds: the CAS at C6 makes a concurrent merge an
  untyped RuntimeError → UNKNOWN failure — serializing the landing turns a race into a queue; POST_MERGE
  reprove must see a stable tip; DECIDE..END appends are trivial. Implementation: `run_story` cannot be edited
  for this without touching the E5-sealed flow, so the landing lock wraps the ADAPTER: `parallel.py` hands each
  story an `Adapters` whose `merger` is a `LockedMerger(merger, landing_lock)` — `base()` unlocked (C7 reads a
  snapshot), `merge()`/`revert()` hold the lock for their own call only. The stage SPAN (merge → reprove →
  decide) is not one critical section; what is serialized is every main-mutating git operation, which is what
  the CAS protects. A reprove that then fails because a sibling landed first is the existing typed post-merge
  path (revert + CONTRACT failure), identical to the serial run where that sibling ran earlier. Zero
  story_runner.py edits.
- **Driver-serial:** `_freeze_plan` once, before wave 1, from the driver thread (fixes C8); `delivered` and
  `results` dicts are written only at wave boundaries in the driver thread (C1 fact).

### 3.5 The closing identity — FORMAT-4 §4.6, verbatim, as the contract

> - The journal stays ONE serial append chain whatever C5 parallelizes (restating the P3 writer invariant;
>   C5's executor serializes at the append point -- design reference G9).
> - `story/resource-acquired` gains optional `base` (sha), written for `kind == WORKTREE`: the revision the
>   per-story worktree was created at, so interleaved attempts stay attributable.
> - Rule R-CLOSED (f4 `run/end` rule): `run/end` is REFUSED while any `provider/request` in the journal has
>   no `provider/result` -- every request has exactly one accounted outcome before the run may close (G9's
>   closing-identity core; the interrupt path already writes closers first, M7). The remaining G9 checks
>   (attempt count vs session count, duplicate labels) are derivations in C5's verify step, not events.

C5 implements its side: (a) `base` written at acquisition — `StoryScope.acquire` payload gains `base` when the
resource is a WORKTREE checkout and the journal format is ≥ 4 (`runtime/story_scope.py` hunk; the revision is
the `Checkout`'s own, workspace.py:130-138); (b) the verify-step derivation `closing_identity(events, sessions)`
in `parallel.py`: every `provider/request` answered exactly once (source_seqs pairing), per-story attempt count
== `story/begin` count == per-story session-log count by role, no duplicate `(story_id, attempt, role)` label —
each violation a diagnostic sentence naming what a mismatch means (G9's ledger.assert_identity analogue). Wired
into RUN.json (`rec["closing_identity"]`) by the run.py driver hunk and into `--verify` by L2-AUTH later (not
this lane).

### 3.6 Budget and journal invariants preserved (each with its mechanism)

| Invariant | How C5 keeps it |
|---|---|
| seq == index at four layers; fsync; truncate-and-poison | untouched — all appends through the one locked point (§3.3); the writer never sees concurrency |
| projection pre-check before a byte | untouched — Authority runs inside the lock |
| per-story event order (table legality) | each story single-threaded; cross-story interleaving legal per C11; `base` attributes worktrees (§3.5) |
| budget never silently overspends | `budget.reached()` checked per story AT DISPATCH (as today, C1); f4 `reservation` is written before every dispatch (E2, W2b) so a kill mid-wave charges `max(reservation, stream)`; overshoot is bounded by `width - 1` in-flight sessions — over-stop, never unaccounted. `ponytail:` dispatch-time check only; a mid-wave hard stop needs C1's monitor, not C5 |
| retry only against the journal-derived budget | `run.retry` via the facade, under the lock |
| one `plan/frozen` | driver freezes before wave 1 (§3.4) |
| R-CLOSED at run/end | E5 closers (C12) + interrupt closers (C13) answer every request before `run/end`; the f4 writer enforces it |
| serial == parallel typed outcomes | pinned by test P9 (§5) on offline adapters; identity is on typed outcomes + failure codes, never on event interleaving (W4 gate wording, DAG:489) |

### 3.7 Interrupt during a wave

First SIGINT (main thread, driver): stop dispatching; `shutdown(cancel_futures=True)` on the pool; WAIT for
in-flight attempts — each closes itself through E5 H1-H6 (C12) within its session timeouts; then
`run.interrupt()` as today (closers for anything still unanswered, dispose, run/end, C13). Second SIGINT:
`_abandon` as today. Workers never install signal handlers (C10 guard already enforces this shape).

## 4. File-touch list — single-writer schedule (plan §2) and registry flags

F5 rule: every file below with registered mutation targets changes the kernel digest ⇒ its edits land inside
the ORCH-1 measured batch (KERNEL-COUPLING-01; one batch, one measurement — LÔ discipline). Target counts
measured 2026-11-26 against `validation.v2.mutation.TARGETS` (994 total).

| File | Edit | Owner/phase | Registry targets |
|---|---|---|---|
| NEW `aisef2/orchestrate/parallel.py` | `LockedRun`, `LockedMerger`, wave executor `run_waves()`, `closing_identity()` | L4-PARALLEL W4a | 0 today — REGISTER new targets (lock discipline, identity derivation) with kill file `test_v23_parallel.py` |
| `aisef2/app/bundle.py` | `story_edges`, `waves()`, #5 refusal at load | L4-PARALLEL W4a | **6** |
| `aisef2/app/bundle_cli.py` | #5 refusal at seal + lint row | L4-PARALLEL W4a | **45** |
| `aisef2/app/run.py` | driver: wave dispatch via `run_waves()`, pre-wave `_freeze_plan`, `workers` kwarg + settings read, `closing_identity` into RUN.json | L4-PARALLEL W4a, then HANDOFF to L4-RESUME (plan §2:53) | **25** |
| `aisef2/runtime/story_scope.py` | optional `base` on WORKTREE acquire payload (f4 only) | L4-PARALLEL W4a | **8** |
| `aisef2/app/settings.py` | parse `parallel` (default 1) — ONE-HUNK REQUEST to L4-REVIEWER (same phase); integrator logs the exception if L4-PARALLEL lands it | L4-REVIEWER W4a | **10** |
| `aisef2/orchestrate/story_runner.py` | owned; **NO edit** (declared so the diff reviewer flags any — the facade and LockedMerger make zero edits necessary) | L4-PARALLEL W4a | 11 |
| `aisef2/orchestrate/workspace.py`, `aisef2/journal/writer.py`, `aisef2/plan/{static_admission,obligation,drift}.py` | owned; **NO edit** | L4-PARALLEL W4a | 17 / 2 / 13+0+4 |
| NEW `tests/v2/{test_v23_waves,test_v23_parallel}.py` | §5 | L4-PARALLEL W4a | kill files |

Not C5's, requested from nobody: `runtime/run_scope.py` (no W4 owner — C5 does not touch it, by design §3.3).

## 5. Test plan — interleaving fault matrix

`tests/v2/test_v23_waves.py` (pure, no threads): wave derivation, #5 under-declaration refusal (W4 gate),
`order()` byte-stability, cycle refusal, lifted-edge transitive coverage.

`tests/v2/test_v23_parallel.py` (offline fake adapters; barrier-synchronized where a race is the subject):
| # | Injection | Expected |
|---|---|---|
| P1 | two stories appending through `LockedRun` under a start barrier, 200 events | seq == index, chain reconstructs, all six projections fold == serial oracle (reuses freeze-package §4b T10 corpus discipline + T17 fold oracle) |
| P2 | same story dispatched twice in one wave (duplicate label) | executor refuses dispatch; defense: the table refuses the second `story/begin` at append (frozen §3.1; freeze-package T5 control reused) |
| P3 | parallel first wave | exactly one `plan/frozen` |
| P4 | RETRY inside a wave after a sibling landed | re-begin at the new tip; typed outcome identical to the serial order where the sibling ran first |
| P5 | budget ceiling reached mid-wave | in-flight stories finish and close; next story/wave NOT dispatched; `budget_stop` names it; spend ≤ ceiling + (width−1 in-flight), all accounted |
| P6 | SIGINT mid-wave (then a second) | dispatch stops; E5 self-closure per attempt; interrupt closers; R-CLOSED holds at run/end (reuses freeze-package §4a R-CLOSED companion positive) |
| P7 | two wave-siblings editing the same file | first merge lands; second is a typed CONFLICT or a clean revert path — never the C6 RuntimeError (the landing lock's kill test: remove the lock → UNKNOWN appears) |
| P8 | closing identity over P1-P7 journals | every request answered once; attempts == sessions per story/role; no duplicate labels; seeded violations (an orphan request, a doubled session log) each produce their named diagnostic |
| P9 | 3-story independent plan + diamond DAG, serial vs width-3 | identical typed outcomes (outcome word + failure code per attempt), identical delivery verdict; event-order constraints hold (reconstruct + fold green) |
| P10 | wave disposal with a RESIDUAL scope in one sibling | siblings end clean; the residual story's refusal is its own (E5), not the wave's |
| — | E5 fault matrix F1-F25/G1-G2 re-run with width 2 | stays green (W2 gate #2 carried forward) |

Freeze-package §4 controls REUSED (not re-written): T5/T6 (double begin), T13/R-CLOSED, §4.6 `base` schema
control, T10 golden corpus, T17 fold oracle. Mutant classes registered for the new file: drop the append lock
→ P1; drop the landing lock → P7; skip a closing-identity clause → P8's seeded violations.

## 6. Declared limitations

- L1. Budget overshoot bound: up to `width - 1` extra in-flight sessions past a ceiling hit — accounted, never
  silent (§3.6). The dollar cap (C2) has the same granularity.
- L2. Candidate-time PRESERVE coverage inside a wave: siblings do not re-prove each other's PRESERVEs at
  candidate (they are not yet committed, C7); the post-merge reprove under the serialized landing — which sees
  every landed sibling — is the binding check, exactly as V21-38 assigns it (story_runner.py:313-318).
  Pinned by P4/P9.
- L3. `regression_tests` for wave members is computed at dispatch from stories delivered in EARLIER waves (C1);
  wave siblings' tests join at the next wave. Serial-run superset identity holds at wave granularity only.
- L4. Interrupt latency = the slowest in-flight session's timeout (N2).
- L5. Journal event INTERLEAVING differs serial vs parallel; identity claims are typed-outcome claims (P9).

## 7. Open questions, each with its default (no STOP)

- **QC1 settings knob:** `parallel` parsed in settings.py (L4-REVIEWER hunk, default). Fallback if the hunk is
  refused: `execute(workers=)` only, CLI `--parallel` deferred to the run.py handoff window.
- **QC2 write-scope:** not in C5 (N3). Default stands unless BUNDLE-FORMAT-2 (C-6) freezes a field; then waves
  intersect it as an additional edge source — additive, no rework.
- **QC3 wave width cap:** default `min(width, len(wave))`, no global clamp. If the owner wants a hard cap tied
  to provider rate limits, it is a settings concern, not an executor change.
- **QC4 `base()` snapshot:** parent = main tip at attempt begin, read through the facade (C7 rule unchanged).
  Default: keep; a wave-start frozen base would CHANGE serial semantics and is rejected.
- **QC5 ORCH-1 batch boundary:** C5 lands green with `parallel` default 1 (production behavior byte-identical);
  the measured batch is the code + tests; flipping a bundle's runs to width > 1 is an operator act, not a gate.
