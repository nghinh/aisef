# AISEF V2 — P3 control-critical projections: semantics (journal format 1)

**Normative for WP-3.4 (the projections) and WP-3.5 (their independent reference models).** Derived from the frozen
RFC: §17 (story transaction), §20 (journal), §21 (control-critical projections, F11), §22 (owner, retry, budget),
§14 and §29 (plan drift, plan quality). Where the RFC leaves a choice to the implementation, the choice is made here
once, and both implementations follow this text — never each other's code.

## Input

A reconstructed journal (`aisef2.journal.compat.reconstruct`): the events a format-1 reader acts on, in seq order.
Unknown ignorable events are skipped and never reach a projection. Each event has `seq`, `type`, `data`, `time`,
`ignorable`, `source_seqs`. **No projection reads `time`**, and nothing below depends on it.

Format-1 payloads (`aisef2/journal/event.py`, `SCHEMAS`; already validated when a projection sees them):

| type | data | cites (`source_seqs`) |
|---|---|---|
| `run/begin` | `journal_format` (1), `run_id` | — |
| `run/dispose-begin` | — | — |
| `run/interrupted` | `abandoned`: bool | — |
| `run/end` | — | — |
| `plan/frozen` | `plan_id`, `plan_hash`, `roles`: {criterion id → `ObligationRole`} | — |
| `story/begin` | `story_id`, `parent` (full SHA) | — |
| `story/admitted` | `story_id`, `parent`, `admitted`, `developer_call_permitted`, `dispositions`: {criterion → `StoryAdmissionDisposition`} | — |
| `story/plan-drift` | `story_id`, `criterion_id`, `spec_id`, `attributed_to`, `candidates` | — |
| `story/commit` | `story_id`, `revision` | — |
| `story/rollback` | `story_id` | exactly one `failure/observed` of the same story |
| `story/retry` | `story_id` | exactly one `failure/observed` of the same story |
| `story/dispose` | `story_id` | — |
| `story/end` | `story_id` | — |
| `probe/evaluated` | `story_id`, `criterion_id`, `record` | — |
| `provider/request` | `story_id`, `criteria`: non-empty list of distinct criterion ids | — |
| `failure/observed` | `story_id`, `code`, `owner`, `retryable`, `detail` (+ `original` for `UNKNOWN`) | — |
| `gate/check`, `gate/decision` | (not read by any control projection) | |

`owner` and `retryable` on a `failure/observed` are the taxonomy's for its `code` (the journal writes them). A story's
**attempt** runs from one of its `story/begin` events to the next.

## Common rules

* A state is a JSON value: objects with string keys, arrays, strings, integers, floats, booleans, null. Map keys that
  are ids (stories, criteria, owners) appear as given.
* A projection that meets an event its rules below forbid **refuses**: it has no state for that journal (the
  implementation raises `ProjectionError`). Events a projection does not name are ignored by it.
* "The story" is `data.story_id`.

## 1. `story_state` (version 1)

State: `{story_id: {"state": S, "attempt": n, "admitted": bool | null, "outcome": null | "COMMIT" | "ROLLBACK" |
"RETRY"}}`, initially `{}`. `S` is one of `BEGIN, ACTIVE, COMMIT, ROLLBACK, RETRY, DISPOSE, ENDED` (§17's lifecycle).

| event | allowed when | effect |
|---|---|---|
| `story/begin` | the story is absent, or it is `ENDED` with outcome `RETRY` | `{BEGIN, attempt + 1 (1 if absent), admitted null, outcome null}` |
| `story/admitted` | `BEGIN` and `admitted` is null | `admitted` := data.admitted; `state` := `ACTIVE` if admitted, else stays `BEGIN` |
| `story/commit` | `ACTIVE` | `state` and `outcome` := `COMMIT` |
| `story/rollback` | `BEGIN` or `ACTIVE` | `state` and `outcome` := `ROLLBACK` |
| `story/retry` | `BEGIN` or `ACTIVE` | `state` and `outcome` := `RETRY` |
| `story/dispose` | `COMMIT`, `ROLLBACK` or `RETRY` | `state` := `DISPOSE` |
| `story/end` | `DISPOSE` | `state` := `ENDED` |
| `probe/evaluated` | `BEGIN` or `ACTIVE` | none |
| `story/plan-drift` | after the attempt's admission and before its decision: `ACTIVE`, or `BEGIN` with `admitted` false (a blocked story still records its drift, §14) | none |
| `provider/request` | `ACTIVE` | none |
| `failure/observed` | the story is present (any state — a post-merge failure follows `ENDED`) | none |

Anything else for one of these types refuses.

## 2. `failure_owner` (version 1)

The owner of the failure that decided a story's current attempt (§17: a rollback's recorded owner is the owner of the
failure that caused it, never the stage that observed it).

State: `{story_id: {"attempt": n, "begin_seq": s, "observed": {"<seq>": [owner, code]}, "owner": owner | null,
"code": code | null, "failure_seq": seq | null, "cited": bool}}`, initially `{}`. `observed` holds the current
attempt's failures, keyed by their seq as a decimal string.

* `story/begin`: `{attempt + 1 (1 if absent), begin_seq: seq, observed {}, owner null, code null, failure_seq null,
  cited false}`.
* `failure/observed`: refuses if the story is absent. Adds `observed[seq] = [owner, code]`. If not `cited`: `owner`,
  `code`, `failure_seq` := this failure's (the latest failure speaks for the attempt until one is cited).
* `story/rollback`, `story/retry`: refuses if the story is absent or its cited seq is not in `observed` (a failure of
  another attempt, or none). Sets `owner`, `code`, `failure_seq` from the cited failure and `cited` := true. A later
  `failure/observed` in the same attempt does not change them; a later citation (which `story_state` refuses) replaces
  them — the last citation wins.
* So an attempt that ends in `COMMIT` after recovering from a failure still reports that failure's owner: the latest
  failure the attempt observed. Only a citation fixes the owner.

## 3. `budgets` (version 1)

Consumption only — never a limit, never a side counter (§22: budgets are projections of the journal). Retry counts come
from resolved execution policy, which is not in the journal's format 1.

State: `{"retries": {story: {owner: n}}, "developer": {story: {"requests": n, "criteria": {criterion: n}}},
"admission": {story: {"permitted": bool, "ready": [criterion, …]}}, "failures": {story: {"<seq>": owner | null}}}`,
initially all four `{}`. `ready` is sorted. A failure's entry is the budget a retry citing it would charge: its
`owner` when it is `retryable`, null when it is not.

* `story/begin`: removes the story from `admission` and `failures` (a new attempt is admitted again).
* `story/admitted`: `admission[story]` := `{permitted: developer_call_permitted, ready: sorted criteria whose
  disposition is READY}`.
* `provider/request`: refuses unless `admission[story]` exists, is `permitted`, and every criterion in `criteria` is in
  its `ready` (§14: a PRE_SATISFIED criterion consumes no developer budget). Else `developer[story].requests` += 1 and
  each named criterion's count += 1 (a story first seen here starts at `{"requests": 0, "criteria": {}}`).
* `failure/observed`: `failures[story][seq]` := `owner` if `retryable`, else null.
* `story/retry`: refuses unless the cited seq is the **latest** failure in `failures[story]` (the greatest seq) — the
  failure the retry engine read through `retry_target`, so a retry can never reach past a newer, non-retryable failure
  to charge an older one's budget — and its entry is not null (a retry is permitted only against the budget named by
  the failure's typed outcome, §17). Else `retries[story][that owner]` += 1.

## 4. `retry_target` (version 1)

The budget a retry of the story's current attempt would charge. Reads only a failure's `owner` and `retryable` (§22:
the retry engine reads nothing else).

State: `{story_id: {"budget": owner | null, "failure_seq": seq | null}}`, initially `{}`.

* `story/begin`: `{budget null, failure_seq null}`.
* `failure/observed`: refuses if the story is absent. `budget` := `owner` if `retryable` else null; `failure_seq` :=
  seq.

## 5. `terminal_state` (version 1)

State: `{"run": R, "interrupts": n, "stories": {story: "RUNNING" | "OPEN" | "COMMIT" | "ROLLBACK"}, "pending":
{story: "COMMIT" | "ROLLBACK" | "RETRY"}}`, initially `{"run": "NOT_STARTED", "interrupts": 0, "stories": {},
"pending": {}}`. `R` is one of `NOT_STARTED, RUNNING, DISPOSING, INTERRUPTED, ABANDONED, ENDED`. A story is `RUNNING`
while an attempt is open, `OPEN` between attempts (its last attempt ended in `RETRY`), `COMMIT` or `ROLLBACK` once
terminal.

* After `run/end` (`ENDED`) or an abandonment (`ABANDONED`), **any** further event refuses.
* `run/begin`: `NOT_STARTED` → `RUNNING`.
* `run/dispose-begin`: from `RUNNING` or `INTERRUPTED` → `DISPOSING`.
* `run/interrupted` with `abandoned` false: only as the **first** interrupt (`interrupts` is 0), from `RUNNING` or
  `DISPOSING` → `INTERRUPTED`. With `abandoned` true: only after an earlier interrupt (`interrupts` ≥ 1), from
  `INTERRUPTED` or `DISPOSING` → `ABANDONED` — a second interrupt during the bounded shutdown abandons and records that
  it did (§20.2). Either way `interrupts` += 1.
* `run/end`: from `RUNNING`, `DISPOSING` or `INTERRUPTED` → `ENDED`.
* `story/begin`: refuses unless the run is `RUNNING` (no story begins once shutdown or disposal has started, §18) and
  the story is absent or `OPEN` (a terminal story never begins again; a running one is already in an attempt); else
  `stories[story]` := `RUNNING`.
* `story/commit`, `story/rollback`, `story/retry`: refuses unless the story is `RUNNING` with no `pending` outcome (one
  decision per attempt); else `pending[story]` := `COMMIT`, `ROLLBACK`, `RETRY`.
* `story/end`: refuses if the story has no `pending` outcome; else `stories[story]` := that outcome if it is `COMMIT`
  or `ROLLBACK`, `OPEN` if it is `RETRY`; the story leaves `pending`.
* Not enforced here (P4, WP-4.3/WP-4.6): that run disposal begins, and the run ends, only after every story has
  reported a terminal disposal outcome — a story still `RUNNING`, or holding a `pending` outcome, at
  `run/dispose-begin` or `run/end` is what the synthetic closers and typed residuals of §18 and §20.2 will account
  for. Both are accepted in format 1.
* Any run-level transition not listed refuses.

## 6. `qualification_counters` (version 1)

Delivery counts and the three §29 plan-quality metrics. The metrics use each story's **latest** admission, so a retried
story is counted once.

State: `{"roles": {criterion: role} | null, "admissions": {story: {criterion: disposition}}, "drift": {story:
{criterion: attributed_to}}, "committed": n, "rolled_back": n, "retries": n, "failures": {owner: n}, "metrics":
{"introduce_obligations": n, "pre_satisfied_introduce": n, "pre_satisfied_introduce_ratio": float | null,
"fully_pre_satisfied_stories": n, "plan_drift": n, "unattributed_plan_drift": n}}`, initially roles null, the maps
`{}`, the counts 0 and the metrics computed from them.

* `plan/frozen`: refuses if `roles` is already set (a run freezes one plan); else `roles` := data.roles.
* `story/admitted`: refuses if `roles` is null, a disposition names a criterion not in `roles`, or a criterion whose
  role is not `INTRODUCE` is `PRE_SATISFIED` (§13 records PRE_SATISFIED for an INTRODUCE obligation only); else
  `admissions[story]` := `dispositions` (replacing the story's earlier admission) and the story's entry is removed from
  `drift` (the key, not an empty map) — drift, like the ratio, belongs to the story's latest admission.
* `story/plan-drift`: refuses unless `criterion_id` is `PRE_SATISFIED` in `admissions[story]`; else
  `drift[story][criterion_id]` := `attributed_to` (the latest per story and criterion).
* `story/commit`: `committed` += 1. `story/rollback`: `rolled_back` += 1. `story/retry`: `retries` += 1.
* `failure/observed`: `failures[owner]` += 1.
* `metrics`, recomputed after every event from the fields above:
  * `introduce_obligations` — over every story's admission, the criteria whose role is `INTRODUCE`;
  * `pre_satisfied_introduce` — of those, the ones whose disposition is `PRE_SATISFIED`;
  * `pre_satisfied_introduce_ratio` — `pre_satisfied_introduce / introduce_obligations`, null when there are none;
  * `fully_pre_satisfied_stories` — stories whose admission has at least one criterion and every disposition
    `PRE_SATISFIED`;
  * `plan_drift` — `drift` entries; `unattributed_plan_drift` — those whose `attributed_to` is `UNATTRIBUTED`.

The plan-quality **verdict** (PASS / FAIL / NOT_CLAIMED against a preregistered `PlanQualityPolicy`) is not a
projection: it reads these metrics and stays separate from delivery (§29). `pre_satisfied_introduce_ratio` is always a
float (or null): compare states by their canonical JSON, where `1.0` and `1` differ.

## Resolved ambiguities (review of the WP-3.5 reference-model author)

The independent author of the reference models read this document without the implementation and reported where it
was ambiguous or weaker than the RFC. Resolved here, for both implementations:

1. A developer request names distinct criteria — now a format-1 schema rule, so "each named criterion += 1" is exact.
2. A retry cites the attempt's **latest** failure (budgets) — else a retry could charge an older retryable failure past
   a newer non-retryable one (the D-006 shape §22 makes unexpressible).
3. Several citations in one attempt: the last wins in `failure_owner` (`story_state` refuses the second anyway).
4. A committed attempt reports the owner of the latest failure it observed; only a citation fixes an owner.
5. A `failure/observed` for a story that never began is refused by `story_state`, `failure_owner` and `retry_target`,
   recorded by `budgets` and counted by `qualification_counters` — each projection enforces only what it reads; any
   journal the writer accepts through the Authority satisfies all six.
6. A blocked story still records its drift (§14 "MUST emit"): `story_state` allows `story/plan-drift` after a refused
   admission.
7. No story begins once the run is shutting down (§18); a story's outcome needs an open attempt and is recorded once.
8. A second interrupt abandons, a first never does (§20.2).
9. PRE_SATISFIED only on INTRODUCE criteria (§13), and drift only for a PRE_SATISFIED criterion of the story's latest
   admission, cleared by re-admission.
10. `STORY_ALREADY_SATISFIED` (§14) has no format-1 event: a fully PRE_SATISFIED story that verifies at the candidate
    ends through `story/commit`.
