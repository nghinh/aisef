# AISEF V2 — event model and Story Transaction proposal

Owner decisions §11 (event-sourced control review) and §12 (Story Transaction lifecycle). A design proposal;
nothing here has been built.

> ## ⚠ Corrected by the architecture board
>
> [`AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md`](AISEF-V2-ARCHITECTURE-BOARD-RESOLUTION.md) **supersedes this
> document** on scope ownership. Part 1 (the event model) stands as written.
>
> | § here | What changed | See |
> |---|---|---|
> | Part 2 · scope ownership | **The `JournalWriter` is owned by `RunScope`, not by `StoryScope`.** The draft had the writer owned by the very scope whose teardown it must record — circular, and it would have failed at implementation. `StoryScope` owns worktree, sandbox, process ranges, sessions, grants, scratch and reviewer scopes, and **emits through the RunScope journal**. | resolution §8 |
> | Part 2 · §2.5 residuals | `RunScope`'s own teardown failure is recorded by a `run/dispose-begin` marker plus a **terminal sink** — a tiny append-only fsync'd file sharing no code with the journal — plus a next-run preflight obligation to report `TORN` runs. The sink is **not evidence** and may never be cited by a gate. | resolution §8 |
> | §1.3 vocabulary | Add `plan/static-admitted`, `story/admitted` (carrying the disposition), `story/plan-drift`, `run/dispose-begin`. `plan/admitted` is renamed `plan/static-admitted` and no longer carries measured baselines — those now belong to `story/admitted`. | resolution §2, §3 |

---

# Part 1 — The event model (§11)

## 1.1 The decision

The owner asked whether V2 should use **event sourcing** or an **append-only journal with deterministic
projections**.

**Finding: for the record of state, those are the same design when done strictly, and V2 should adopt it.** The
distinction that actually matters is a different one, and the external study makes it visible because DeepSeek
Harness contains both halves in one repository:

| | Mechanism | Verdict |
|---|---|---|
| **The log** — session state event-sourced, every read model a pure fold, caches explicitly non-authoritative | `packages/core/session/*`, `session-projection-cache/src/index.ts:9-14` | **ADOPT** |
| **The bus** — Cordis `waterfall`/`bail` dispatch, where a listener can veto built-in behavior by not calling `next()` | `vendor/cordis/src/events.ts:224-242`; used for control at `agent-loop/src/agent.ts:448-464` | **REJECT** |

The concrete instance that settles it: in the harness, **whether a failed model request is retried depends on
which plugins are loaded**, because `agent/request-error` is a waterfall and the failure is rethrown only if no
listener returns `{kind:'retry'}`. For an extensible product that is a feature. For a system whose output is a
qualification verdict it is a determinism defect generator: the same journal, the same failure and a different
plugin set give different behaviour, and the record does not say which set was present.

**So: V2 is event-sourced for state and explicitly *not* event-driven for control.**

> **Writing an event has no effect on control flow. Reading the journal is the only way to learn state. No
> subscriber may change a decision by existing.**

This is a correction to an earlier reading of mine, recorded in
[`CORDIS-ARCHITECTURE-STUDY.md`](CORDIS-ARCHITECTURE-STUDY.md) §5.5.

## 1.2 Envelope

```python
@dataclass(frozen=True)
class Event:
    seq: int                 # dense: seq == index in the journal. Never a timestamp.
    type: str                # the discriminant
    data: Mapping[str, Any]  # JSON-lossless, validated at the append site
    time: float              # recorded, NEVER read by any projection
    ignorable: bool = False  # explicit author-side claim that a reader may skip this type
    source_seqs: tuple[int, ...] = ()   # provenance: the earlier events this one derives from
```

Six properties, each borrowed with its citation, each answering a named V1 family:

1. **`seq == index`, enforced independently at assignment, admission, append and decode**
   (`packages/core/session/src/index.ts:567-581,743`;
   `packages/session/session-persistence/src/storage-contract.ts:145-151`). Answers `FAM-IDENTITY` — our largest
   family is "a control decision selects its evidence by chronological recency". The answer is not to order by
   time more carefully; it is to **never order by time at all**.
2. **`time` is recorded and never read for ordering.** DeepSeek zeroes it wholesale in fixtures and re-derives
   `seq` from file position (`session-snapshot/src/normalize.ts:359-361`;
   `llm-replay/src/index.ts:260-263`).
3. **Validation at the append site** — "a bad event fails at the append site rather than later during a backend
   flush" (`session/src/index.ts:713-715`). Answers `FAM-EVIDENCE-SEMANTICS`.
4. **Unknown required type ⇒ refuse to reconstruct** (`session/src/types.ts:478-487`). `ignorable` makes "safe to
   skip" an explicit per-event claim by the author, not an assumption by the reader. Answers `REPLAY-DRIFT` /
   `FAM-RELEASE`.
5. **No update and no delete verb on the store** (`session-persistence/src/index.ts:147-198`). Logical deletion
   is a new shadowing event. Answers `FAM-RELEASE` and makes our closure-evidence discipline a type rather than
   a rule I follow.
6. **`source_seqs`** — provenance citation, from `SurfaceIntent.sourceEventSeqs`
   (`session/src/types.ts:453-454`). Answers `FAM-IDENTITY` for derived records: a projection output can name the
   exact events it rests on.

Unlike DeepSeek, AISEF writes **synchronously at decision boundaries**. Their 200 ms write-behind
(`session-persistence-jsonl/src/storage.ts:36`) is a latency trade we do not need to make and cannot afford: an
evidence gap at a decision point is precisely the SS-96 condition.

## 1.3 The event vocabulary

Twenty-four types in six groups. The first twenty are the core; the last four are the ones a first cycle could
defer.

**Run**

| type | data | why it exists |
|---|---|---|
| `run/begin` | run id, operator, wall clock | the journal's root |
| `run/spec-resolved` | `RunSpec` hash + per-value layer provenance | binds every later decision to one resolved spec (§I.1–I.2 of the harness study) |
| `run/interrupted` | cause, deterministic closers appended | typed interruption instead of a gap (`session/src/repair.ts`) |
| `run/end` | terminal class, counts | — |

**Plan**

| type | data | why it exists |
|---|---|---|
| `plan/admitted` | one `AdmissionRow` per criterion, measured baselines | the plan-admission record of [`AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md`](AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md) §5 |
| `plan/frozen` | `plan_hash`, baseline SHA | nothing may run against an unfrozen plan |

**Story transaction** (see Part 2)

| type | data |
|---|---|
| `story/begin` | story id, plan hash, parent revision (full SHA) |
| `story/resource-acquired` | label, kind, locator, owning scope |
| `story/resource-released` | label, outcome — **including failure** |
| `story/commit` | candidate SHA, criteria satisfied |
| `story/rollback` | reason, owner, state restored to |
| `story/retry` | attempt n, owner charged, budget remaining |
| `story/dispose` | resources released in order, residuals named |
| `story/end` | terminal class |

**Capability and proof**

| type | data | why it exists |
|---|---|---|
| `capability/resolved` | name, implementation, version, `enforcement` (FULL/PARTIAL/UNAVAILABLE) | a run qualified under `PARTIAL` can never be compared with one under `FULL` |
| `probe/evaluated` | `ProbeResult` incl. `spec_hash`, full revision SHA | the criterion's instrument speaking |
| `proof/verified` | `VerifiedProof` incl. both results and `agreement` | independent verification, disagreement recorded not resolved |

**Execution**

| type | data |
|---|---|
| `provider/request` | route, model, attempt id, request hash |
| `provider/result` | typed code, tokens, latency, `retryable` |
| `tool/invoked` | tool, argv, cwd, sandbox mode, enforcement |
| `tool/result` | typed outcome, owner on failure, evidence ref |

**Control and integrity**

| type | data | why it exists |
|---|---|---|
| `gate/check` | check id, typed outcome, owner, evidence refs | one row per check, never a summary |
| `gate/decision` | verdict, the checks it rests on, spec hashes | the decision cites its inputs by seq |
| `failure/observed` | typed code, owner, retryable, budget target | `FAM-RETRY` / `FAM-BUDGET`: owner and retryability recorded, not inferred later |
| `invariant/violated` | invariant id, owning module, context | uncontainable; see §J.4 of the harness study |

**Deferrable (4)**: `story/resource-released` could initially be folded into `story/dispose`;
`capability/resolved` could start as a `RunSpec` field; `run/interrupted` needs the closer machinery;
`proof/verified` needs two environments. None of the four changes the envelope.

## 1.4 Projections

Every read model is a pure function of a journal prefix. None is stored as authority.

```python
def fold(events: Sequence[Event], projection: Projection) -> State: ...
```

Four properties:

1. **Caches are disclaimed.** Borrowing the wording that matters
   (`session-projection-cache/src/index.ts:9-14`): a cached row is *possibly stale — its `seq` says how stale —
   but never wrong*, and a version mismatch **discards** the row rather than migrating it.
2. **The from-scratch oracle is a test we must actually write**
   (`packages/core/session/tests/derived-cache.spec.ts:17-27`): incremental state must equal
   `fold(journal_prefix)` at every decision point. AISEF asserts this nowhere today, and it is the cheapest
   available defence against `FAM-RECOVERY` and `FAM-QUALIFICATION-MEASUREMENT`.
3. **Budgets and cost are projections, not counters.** SS-64 was a cap that disagreed with what happened. A
   projection cannot disagree with its own log. Take the loud-failure detail too: DeepSeek's pricing **throws**
   when it answers a different occurrence count than asked, "because misalignment would silently misprice nodes"
   (`token-meter/src/route-pricing.ts:29-45`), and its latency projection rejects orphan results
   (`session-stats/tests/projection.spec.ts:284`).
4. **No projection reads `time`.**

---

# Part 2 — Story Transaction (§12)

## 2.1 Why a transaction, and what it owns

A story is the unit that acquires real resources — a worktree, a sandbox, tool grants, a provider session,
subprocesses, scratch storage, an evidence writer, a reviewer environment — and must release all of them, in
order, whatever happens. V1's `FAM-PROCESS` (D-024: "TemporaryDirectory cleanup races a writer inside a
session's `.git`"), `FAM-OWNERSHIP` and `FAM-RECOVERY` are all failures of that.

The structural answer is Cordis's, with two deliberate corrections:

**Borrowed.** A child scope is an **effect of its parent** (`vendor/cordis/src/fiber.ts:265`), so ownership is
one tree and disposal is transitive; resources are acquired as **labelled** effects returning disposers
(`fiber.ts:418-441`); acquisition while the owner is tearing down is **refused**
(`fiber.ts:418-422`, `INACTIVE_EFFECT`).

**Corrected — twice, and both corrections matter more to us than to them:**

1. **Sibling disposal is not ordered.** Cordis's `_unload()` disposes a fiber's effects with `Promise.all`
   (`fiber.ts:675-684`) — concurrently. Reverse order holds *within* an effect, not *across* a scope's effects.
   AISEF's ordering requirements are hard: processes reaped before the sandbox is torn down, the sandbox before
   the worktree is removed, the evidence writer outliving all of them. V2 therefore holds an **explicit ordered
   resource stack**, disposed in reverse acquisition order, each awaited.
2. **Disposal failures are not swallowed.** Cordis routes them to `ctx.logger.error` and drops them
   (`fiber.ts:680-683`). In an assurance system a failed cleanup **is** the evidence — it is how orphans are
   born. V2 emits `story/resource-released` with the failure, types it, and lets it fail `DISPOSE`. DeepSeek
   reaches the same place at the consumer level, keeping disposal failures distinguishable from result failures
   and combining them into an `AggregateError` only when both fail
   (`packages/subagent/tool-subagent/src/index.ts:226-237`).

## 2.2 Interfaces

```python
class Enforcement(Enum):
    FULL = "FULL"; PARTIAL = "PARTIAL"; UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True)
class ResourceRef:
    label: str               # "worktree" | "sandbox" | "provider-session" | "process-range/dev"
    kind: str
    locator: str
    enforcement: Enforcement

class StoryScope(Protocol):
    def acquire(self, label: str, factory: Callable[[], Resource]) -> ResourceRef:
        """Push onto the ordered stack. Refuses if the scope is DISPOSING (INACTIVE_ACQUIRE)."""
    def child(self, label: str) -> "StoryScope":
        """A child scope is itself a resource of this one — acquired through `acquire`."""
```

`acquire` refusing during teardown is `INACTIVE_EFFECT` in our vocabulary, and the reason is identical: a
resource acquired into a dying scope is leaked by construction.

## 2.3 Lifecycle

```
                 ┌──────────────── RETRY ◄─────────┐
                 ▼                                 │
  BEGIN ──► ACTIVE ──► COMMIT ──► DISPOSE ──► ENDED│
                 │                   ▲             │
                 └──► ROLLBACK ──────┴─────────────┘
```

**BEGIN.** Acquire the **evidence lease first**, then the journal writer, then everything else. The lease is a
kernel-held lock taken *before* any read that a later write depends on
(`packages/session/session-persistence-jsonl/src/lease.ts`; `agent-loop/src/index.ts:894-904`), so two runs can
never both believe they own a story's evidence. Emit `story/begin` with the parent revision as a **full SHA** —
W0 correctly refused an abbreviated SHA once already, and the same rule applies here.

**ACTIVE.** Every resource acquisition emits `story/resource-acquired`. A capability's resolution emits
`capability/resolved` carrying its implementation, version and enforcement level. The transaction is **not** a
control authority: it owns resources and records, and the gate decides.

**COMMIT.** Permitted only when every criterion owned by the story has a `proof/verified` with `agreement =
True` and verdict matching its `ProofSpec.expected_at_candidate`. Commit emits `story/commit` and then proceeds
to `DISPOSE`. A commit never depends on a developer test's verdict — that is the TDD check's business, decided
separately (see [`AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md`](AISEF-V2-PROOF-ARCHITECTURE-PROPOSAL.md) §4).

**ROLLBACK.** Restores the story's parent state and emits `story/rollback` with reason and **owner**. Rollback is
not a failure verdict; it is a state operation. The crucial rule, and it is SS-96 restated: *the owner recorded
on rollback is the owner of the failure that caused it*, never the stage that observed it. An `UNRUNNABLE` probe
rolls back with owner `ENVIRONMENT` and charges no developer budget.

**RETRY.** Permitted only against the budget named by the failure's typed outcome. Retryability is a property of
the code, decided once in the taxonomy — `DEFAULT_RETRYABLE_CODES`, and `MISSING_CREDENTIAL` split from
`INVALID_CREDENTIAL` "because the fix differs" with the latter deliberately non-retryable
(`packages/llm/llm/src/error.ts:41-48`; `retry-policy.ts:18-24`). That is D-006 — "credential rejection charged
to quality attempts" — made unexpressible. What DeepSeek's taxonomy does *not* supply is **whose budget pays**;
AISEF's owner field remains necessary and must be carried on every `failure/observed`.

**DISPOSE.** The ordered stack unwinds in reverse acquisition order, each release awaited, each emitting
`story/resource-released` with its outcome. Three rules:

1. **Graceful first, then the ladder.** A cooperative shutdown tier before signals, so a nested scope reaps its
   own descendants first: EOF → bounded grace → SIGTERM → grace → SIGKILL → **unbounded wait**
   (`packages/subagent/subagent-acp/src/run.ts:185-212`). Unbounded at the end is correct: a range that will not
   empty after SIGKILL is a fact to block on and report, not one to time out and forget.
2. **Emptiness is measured, not inferred.** A worktree may not be removed until the process range that could
   write to it is *provably* empty — `kill(pid,0)`/`ESRCH`, `TasksCurrent`, or `isJobEmpty` depending on platform
   (`spawn.ts:418-421`; `subprocess-local/src/index.ts:199-205`). This is what makes D-024's race unexpressible.
3. **Residuals are named.** Anything that could not be released is recorded as a typed residual, and the *next*
   run's preflight is required to detect and report a previous run's surviving range. DeepSeek has the same
   residual and does not do this (`warnFallback`, `subprocess-local/src/index.ts:230-247`); it is a cheap
   improvement over their design, and it turns an uncovered case into a typed observation instead of silence.

**ENDED.** Terminal class recorded. The evidence writer is the last thing released, after the lease.

## 2.4 Interruption

An operator interrupt or crash must not leave a gap. Borrowing `packages/core/session/src/repair.ts:15-18,87-88,119-133`
wholesale:

- synthesize typed closers for anything in flight, distinguishing **`OUTCOME_UNKNOWN`** ("it started and we do
  not know how it ended") from **`NOT_STARTED`** — the proof-layer `Verdict` lattice already has the vocabulary;
- **reuse the last real event's timestamp** so repairing the same journal twice yields byte-identical closers;
- mark every synthetic event as synthetic, so a closer can never be mistaken for a measurement;
- close with `run/interrupted` and a terminal class.

Shutdown itself is bounded and escalating, as in `apps/cli/src/process-shutdown.ts:52-75`: the first signal
disposes within a budget and still writes evidence; a second signal while disposal is pending abandons —
**and records that it was abandoned**. An abandoned teardown is a typed terminal state, not an unexplained gap.

## 2.5 What this does not solve

Stated rather than implied, in the same spirit as the harness's own accepted-TOCTOU comment
(`packages/fs/fs-sandbox/src/index.ts:9-18`):

- **A hard-killed harness still leaks.** If AISEF is SIGKILLed, no disposer runs. The mitigation is the
  next-run preflight of §2.3, which detects rather than prevents. There is no supervisor process in this design,
  and adding one is a real cost that should be decided on evidence, not assumed.
- **Ordered disposal is a discipline in the stack, not a property of the type system.** Acquiring two resources
  whose release order matters, in the wrong order, still produces the wrong teardown. The ordered stack makes it
  reviewable and recorded; it does not make it impossible.
- **The journal is single-writer per story.** Dense `seq` requires it. That is an accepted constraint, and it is
  what the lease enforces.
