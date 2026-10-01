# The Assurance Kernel (systematic hardening v1, Phase 4)

The kernel is the smallest deterministic part of AISEF that is allowed to decide
state. Everything a model produces — developer edits, reviewer text, security
text, tool stdout — is **input evidence** to the kernel, never a decision. This
document names what the kernel owns, the typed outcomes it speaks in, the
identities every piece of evidence must carry, and the explicit transition table
that Phase 6 checks with seeded traces and Phase 7 with injected faults.

Status of this document: **specification for the current kernel**. Where the
code as of 1.7.6 deviates, the row says so (`deviation:`) and names the defect
or invariant; those rows are the Phase 8 work list.

## 1. What the kernel owns

| concern | kernel component (1.7.6) | decides | never decided by |
|---|---|---|---|
| Identity | `acceptance.ac_code`, `acceptance.contract_fingerprint`, `head_sha`, `planes.identity` | which criterion, which story epoch, which candidate, which product | a model, a filename, a position |
| Story epoch | `contract_fingerprint(criteria)` → `story:contract` note | when a contract changed (branch dropped, new baseline) | resume, retry |
| Baseline identity | `implement.run_baseline`, `gate.authoritative_baseline` | the one baseline record for (story, epoch), captured at the integrated parent | the newest record |
| Candidate identity | `implement.freeze_candidate` (commit of in-scope paths) | the exact tree every check binds to | reviewer/security sessions (`_revert_reviewer_writes`, `_candidate_moved` + reset) |
| Evidence provenance | `EvidenceStore` events with `candidate`, `story:contract`, baseline `root/epoch` | whether a record is *about* the thing being graded | chronological order |
| Evidence freshness | **partial** — `gate._at`/`_green_at` bind to candidate; `run_attempt` no-op shortcut binds to candidate only (D-035) | whether a record still describes the evaluated state | the existence of a record |
| Typed outcomes | `control.outcome.Outcome`, review `REVIEW_PASS/BLOCK/REVIEW_UNRUNNABLE`, tools `outcome_kind` | the axis a result lives on | prose |
| FSM transitions | `control.state.StoryStatus` + `ALLOWED`, `run.py` wave loop, `implement_story` loop | legal next states | agents |
| Retry / recovery | `implement_story` (quality vs infra budget, `_review_stage`, `recover_out_of_scope`, no-op policy) | which stage reruns and what is restored | the developer |
| Gate evaluation | `gate.evaluate` (16 named checks, closed kind set) | PASS / blocking outcome per check | free text |
| Approval invalidation | `control.approvals` (hash-bound, cascade) | which human decisions are stale | mtime, existence |
| Lease / recovery | `state.StateStore.claim`, `claim_is_orphaned`, `reconcile_all`, run/merge locks | who owns a story now; what is orphaned | a RUNNING string |
| Merge completion | `run.py` (`candidate.frozen` + `verification.completed` validity, `merge.completed` before `done`) | when work has left the transaction | the gate alone |

## 2. Typed outcomes

Stage outcomes (one per stage execution; the kernel maps every client/tool
result onto exactly one):

| outcome | meaning | budget | routes to |
|---|---|---|---|
| `PASS` | the stage's deterministic or model check is satisfied | — | next stage |
| `QUALITY_BLOCK` | the stage ran and says the work is wrong (structured findings) | quality | developer |
| `UNRUNNABLE` | the stage could not execute (tool/runner missing, reviewer produced no verdict, sandbox refused) | stage retry budget | the same stage |
| `ENVIRONMENT_FAILURE` | declared environment does not match capability (image lacks tool, docker down) | none — operator | `HUMAN_REQUIRED` after bounded retry |
| `INFRA_FAILURE` | transient provider/transport failure (timeout, rate limit, 5xx) | infra | the same stage, with delay |
| `AUTH_FAILURE` | credential rejected — repeats identically | none | `HUMAN_REQUIRED` (fatal) |
| `NOOP` | a developer session ended with the tree exactly as found | none (see §4) | re-evaluation, then developer or terminal |
| `PLAN_CONFLICT` | the plan/contract cannot be satisfied from inside the story (structured `stuck`, criteria green at parent, repeated same-criterion failure) | none | `HUMAN_REQUIRED` |
| `ISOLATION_BREACH` | the session moved the trunk or escaped the worktree | none | terminal for the attempt (fatal) |
| `MERGE_CONFLICT` | integration failed after PASS | none | integration recovery / human |
| `ORPHANED` | a claim whose owner process is dead | none | reclaimable on the next run |
| `HUMAN_REQUIRED` | a decision only the owner can make | none | arbitration → new epoch |

Gate check outcomes stay the six of `control.outcome.Outcome` (PASSED, FAILED,
UNRUNNABLE, UNCONFIGURED, WAIVED, NOT_APPLICABLE). The mapping from a gate to a
stage outcome: any FAILED check of kind deterministic/structural/security/model-judge
→ `QUALITY_BLOCK`; UNRUNNABLE `review` → review `UNRUNNABLE`; UNRUNNABLE
deterministic check → `UNRUNNABLE` of the tool stage; UNCONFIGURED blocks as a
named absence (pre-deploy) and never as `QUALITY_BLOCK`.

Rules: strings never carry two outcomes (D-032 shared one slot); a stage that did
not run never produces a verdict on the work (D-029, D-032); a model verdict
enters only through its structured block (D-026); free-form text is diagnostic.

## 3. Evidence identity and freshness

Every kernel decision reads evidence through an **identity tuple**, never
through "the latest record":

```
EvidenceIdentity = (run_id, story_id, story_epoch, candidate_sha, baseline_root,
                    stage, verifier_config_digest, environment_digest, tree_state_digest)
```

- `tree_state_digest` is what D-035 is missing: the state the verdict was
  computed over includes the worktree's dirty paths, not only HEAD. Retry
  hygiene, reviewer reverts, worktree refresh and `commit_story` change it.
- A record is **fresh** for a decision only if every identity the decision
  depends on matches the current state. A stale record is kept for audit and
  ignored for control. `seq` orders the audit trail; it is never an identity.
- Recovery actions emit evidence (`retry:recovery`, `review:immutable`,
  `review:candidate`) **and** mark dependent records stale (Phase 8/9 work:
  today only the recording half exists).

## 4. No-op semantics

A developer session that changes nothing is a **statement**, not a failure.
Before the kernel may use it as terminal evidence it must establish, in order:

1. the current frozen candidate has a verdict whose identity tuple matches the
   current state (else: re-grade — deterministic gates first, then only the
   model stages whose inputs changed);
2. no stale failed gate remains attached to the candidate;
3. no recovery action changed the evaluated state since that verdict;
4. current valid evidence proves work remains for the developer (a
   `QUALITY_BLOCK` with structured findings inside the write scope).

Only then is a repeated no-op a `PLAN_CONFLICT`/terminal with the reason stated
from that evidence. **deviation (1.7.6):** `run_attempt` stops at "the SHA has
a verdict" (D-035).

## 5. States

Story states are those of `StoryStatus`: `pending`, `running`, `verifying`,
`verified`, `done`, `blocked`, `failed`. Inside `running` the attempt has stage
sub-states: `DEVELOP → FREEZE → VERIFY(deterministic) → REVIEW → SECURITY →
GATE`; after the gate: `MERGE → COMPLETE`. Recovery sub-states: `RECOVERY`
(retry hygiene, reviewer revert, candidate reset), `UNRUNNABLE` (stage retry),
`HUMAN_REQUIRED` (owner arbitration).

## 6. Transition table

Columns: current state · event/outcome · preconditions · next state · retry budget
used · evidence invalidated · human required. `—` means none.

| # | current | event / outcome | preconditions | next | budget | evidence invalidated | human |
|---|---|---|---|---|---|---|---|
| T1 | pending | claim by a live process | no live claim; deps `done` | running / DEVELOP | — | — | no |
| T2 | pending | claim while claim exists and owner dead | `claim_is_orphaned` | running (reclaim), old claim → `ORPHANED` record | — | — | no |
| T3 | running / DEVELOP | attempt opens in a story worktree | **worktree clean of out-of-scope dirt** (hygiene restored attributed dirt; unattributed → T4) | DEVELOP session | — | dependent verdicts of the previous state → stale (deviation: not marked, D-035) | no |
| T4 | running / DEVELOP | out-of-scope dirt no attempt is on record for | — | blocked (reason names paths) | — | — | yes (operator cleans) |
| T5 | DEVELOP | session `ok`, tree moved | not isolation breach | FREEZE | — | — | no |
| T6 | DEVELOP | session `ok`, tree unchanged (`NOOP`) | §4 steps 1–3 hold **and** step 4 proves work remains | DEVELOP (counted no-op) → after `MAX_NOOP`: failed/blocked with the proven reason | quality (no-op count) | — | no |
| T6' | DEVELOP | `NOOP` but §4 step 1 fails (verdict stale or absent) | — | VERIFY on the current frozen candidate (re-grade) | — | stale verdict ignored | no (deviation: D-035 goes to T6) |
| T7 | DEVELOP | `max_turns`, tree moved | — | FREEZE (grade what exists) | quality | — | no |
| T8 | DEVELOP | `max_turns`, tree unchanged | — | as `NOOP` (T6/T6') | quality | — | no |
| T9 | DEVELOP | `INFRA_FAILURE` (timeout/rate limit/5xx) | infra budget > 0 | DEVELOP after `retry_after` | infra | — | no |
| T10 | DEVELOP | `AUTH_FAILURE` | — | blocked (fatal) | — | — | yes |
| T11 | DEVELOP | trunk moved by the session (`ISOLATION_BREACH`) | changed paths are not harness-only | blocked (fatal) | — | — | yes |
| T12 | DEVELOP | out-of-scope writes detected | — | FREEZE (in-scope only) + `write-scope:violation` recorded | — | — | no |
| T13 | FREEZE | commit of in-scope paths | no pre-staged out-of-scope paths | VERIFY; candidate C fixed | — | all evidence not bound to C is not about C | no |
| T14 | FREEZE | pre-staged out-of-scope paths | — | VERIFY on previous HEAD, `candidate:frozen` error recorded (gate fails write scope) | — | — | no |
| T15 | VERIFY | deterministic tools run | tools declared **and** present in the sandbox | REVIEW (or GATE if review not required) | — | — | no |
| T16 | VERIFY | tool missing / runner not importable | — | `UNRUNNABLE` (check ⚠) — never FAILED | — | — | no (operator later) |
| T17 | REVIEW | structured `pass` | reviewer did not mutate the tree | SECURITY | — | — | no |
| T18 | REVIEW | structured `block` | findings reachable inside write scope | GATE → `QUALITY_BLOCK` → DEVELOP | quality | — | no |
| T19 | REVIEW | structured `stuck` (plan conflict) | findings point outside scope / contradict criteria | blocked `PLAN_CONFLICT` | — | — | yes |
| T20 | REVIEW | no verdict / malformed / cut / mutated tree / candidate moved | review executions ≤ 1 + `MAX_REVIEW_RETRIES` | REVIEW again on the same C (`_review_stage`) | review retry | that review execution does not count | no |
| T21 | REVIEW | still no verdict after budget | — | blocked `REVIEW_UNRUNNABLE` (candidate kept) | — | — | yes (`--verify-only` when the reviewer can run) |
| T22 | SECURITY | structured pass / block | did not mutate the tree | GATE | quality if block | — | no |
| T23 | SECURITY | mutated the tree / no report | — | tree restored; security `error` (deviation: no bounded security retry — INV-G partial) | — | that execution does not count | no |
| T24 | GATE | all checks PASSED/WAIVED/NOT_APPLICABLE and evidence bound to C | `evidence matches candidate` | verifying → verified | — | — | no |
| T25 | GATE | any FAILED check | — | DEVELOP with feedback (`QUALITY_BLOCK`) | quality | — | no |
| T26 | GATE | only `review` UNRUNNABLE | — | T20 | — | — | no |
| T27 | GATE | quality attempts > `max_retries` | — | failed ("did not pass gate" only if a gate ran) | — | — | no |
| T28 | GATE | same structured complaint twice / nop deadlock | verdicts structured | blocked `PLAN_CONFLICT` | — | — | yes |
| T29 | verified | merge into trunk | `candidate.frozen` + `verification.completed` same attempt, ok; trunk moved → refresh first | `merge.completed` then done | — | — | no |
| T30 | verified | merge conflict | — | pending (human resolves) / blocked | — | — | yes |
| T31 | any running | process death | — | claim → `ORPHANED` on next reconcile; worktree kept (branch preserved) | — | — | no |
| T32 | any | criteria (contract) changed | — | epoch changes: branch dropped, baseline recaptured at the integrated parent, approvals downstream stale | — | all story evidence of the old epoch | yes (approve) |
| T33 | any | owner arbitration recorded | — | new epoch (T32) | — | as T32 | yes |
| T34 | failed (run end) | `commit_story` + worktree removed | — | branch preserved; next run recreates a clean worktree (no dirt survives) | — | verdicts bound to the removed dirt are stale (deviation: D-035) | no |

Every transition above either exists in 1.7.6 or is marked `deviation`. There
are no implicit transitions: a code path that changes `StoryStatus`, opens a
session, restores files or reuses evidence without a row here is a defect of
this document or of the code, and Phase 3's sweep lists the candidates.

## 7. What clients never do

Client adapters (Claude Code, OpenCode, the Phase 5 synthetic client) produce a
`RunResult`: text, tool uses, exit status, tokens, cost. They never write
`StoryStatus`, never create evidence events that satisfy a gate, never decide
retry, never restore files. A client that commits on the trunk, edits the tree
during review or deletes evidence is an `ISOLATION_BREACH`/`review:immutable`
event, not a decision.
