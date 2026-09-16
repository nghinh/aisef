# Fix family F1 — IDENTITY / PROVENANCE / FRESHNESS

Closes (frozen defect set, Phase 9): D-035, SS-02, SS-03, SS-09, SS-16, SS-18, SS-20, SS-22, SS-A10, SS-A15,
SS-C2, SS-T1, SS-X1, SS-60 and the FAM-RECOVERY freshness half of SS-04. Invariants: INV-A.1–A.3, INV-C.1, INV-C.3,
INV-D.1–D.3, INV-E.1, INV-E.3, INV-K.2, INV-K.3, INV-P.2.

## 1. One explicit evidence identity

`aisef/control/identity.py` — `EvidenceIdentity` (frozen dataclass, `schema_version = 2`):

| field | source | why it is part of identity |
|---|---|---|
| run_id | run journal | evidence from another run is provenance, not proof |
| story_id | story | |
| story_epoch | `acceptance.contract_fingerprint` (D-033) | a contract change re-opens every verdict |
| attempt / session_id | `Attempt.number` + agent_run id | guard heartbeats and structural proofs bind to the graded SESSION (SS-02/03), which exists before the candidate SHA does |
| candidate_sha | `freeze_candidate` | the build |
| baseline_identity | authoritative baseline `(root_sha, seq)` | nop control / review diff / preservation compare against THIS root (SS-22, SS-18) |
| stage | developer / test / lint / review / security / gate / merge | a proof is for a stage |
| verifier_config_digest | digest of `tools.*`, `verify.*`, `coverage.min`, `security.block_severities` | the spec the gate reads is part of what a verdict means |
| environment_digest | image id / host tool probe digest | a verdict in another environment is not this environment's |
| tree_state_digest | digest of `git status --porcelain -z` + blob ids of dirty paths, relative to `candidate_sha` | the tree the verdict was computed over — the D-035 root cause: hygiene changes the tree, the SHA stays |

Every `Event` gains `identity: dict` (empty for legacy). `EvidenceStore` stamps it from the store's current identity
(today it stamps `detail["candidate"]` only). `seq`/`at` remain audit metadata: no reader may order or select by them
for control (SS-T1: TDD reads position within the candidate's events, not `seq`).

## 2. One authoritative freshness function

`identity.fresh(event, current, *, bind=...) -> Freshness(ok: bool, reason: str)` — the ONLY way a subsystem may ask
"does this record speak for the state I am deciding on". It replaces, in one commit each:

| today | becomes |
|---|---|
| `Evidence.for_candidate(sha)` (SHA-only, keeps unstamped events) | `Evidence.for_identity(current)` — keeps events whose identity binds; legacy schema-1 events bind on candidate only and are flagged `legacy` so the gate can refuse them for control (Phase 16 rule: old evidence never silently satisfies a new gate) |
| `Evidence.candidate` (last event with any `candidate` key — SS-C2) | candidate of record = identity of the last `gate:input`, else the last successful `candidate:frozen`; a `retry:recovery` note is never a candidate of record |
| `run_attempt` `cham_roi` (any `gate:verdict` at this SHA — D-035) | `fresh_verdict(ev, current)`; a no-op session over a candidate with NO fresh verdict → grade it (T6'); the two-strike no-op terminal needs a fresh QUALITY_BLOCK (T6) |
| `_review_complete(_at(...))`, `_pending_review` (SHA) | identity-bound |
| `_at` / `_green_at` (verify-only keep) | identity-bound (a kept result must match config/environment/tree too) |
| gate `_stale_candidates` / `_latest_per_check` | identity-bound; "latest" is the latest FRESH record per check, and a stale latest is stated as UNRUNNABLE exactly as today |
| `cli/harness.py` waiver (last `gate:input` — SS-X1) | the waiver binds to the story branch's current identity; a `gate:input` from a verify-only run at another SHA is refused with the two SHAs named |
| closure G4.5 (`rev-parse --verify` — SS-06 is F6, but the candidate it reads is `Evidence.candidate`) | reads the candidate of record |

## 3. Typed invalidation events

`NOTE evidence:invalidated` `{reason, identity_before, identity_after, invalidated: [seq…]}` written by:

- `recover_out_of_scope` after a restore changed the tree (INV-K.2) — D-035's other half;
- the run loop's worktree refresh when HEAD moved off the frozen candidate (SS-09);
- the wave-end `commit_story` of a failed story, naming the new branch tip (SS-16);
- the reviewer-commit `reset --hard`, naming what it restored and whether it succeeded (SS-A10; the reset also
  preserves out-of-scope dirt described by an open `write-scope:violation` — restore only the reviewer's paths);
- a contract change (epoch bump, already D-033) — now also as this event.

Recovery may only remove paths whose ownership is proven (F4 owns the ownership model; F1 only records).

## 4. Freeze is authoritative

- A refused freeze (`GitError`, unreadable HEAD) yields a typed `ENVIRONMENT_FAILURE` attempt: nothing is graded,
  nothing is stamped under the parent SHA (SS-A15), and the story can never complete with an empty candidate
  (SS-60): `verify_candidate` refuses `candidate == ""`; the gate's `evidence matches candidate` is UNRUNNABLE for a
  story verdict without a candidate (NOT_APPLICABLE stays only for the explicit `aisef gate` CLI without one).
- `verification.completed` carries `candidate_sha` (SS-08 hardening; merge already merges the SHA).

## 5. Baseline identity within the epoch

`base_ref` for the nop control and the review diff is the authoritative baseline's recorded root for the story's
epoch — never a recomputed fork point (SS-22). An unrunnable baseline is re-captured at that root through a temporary
worktree (SS-18, INV-C.3); a refusal is typed and recorded.

## 6. What must be true when F1 closes (per-family definition of done)

RED before / GREEN after for every member above (`tests/hardening/test_verdict_freshness.py`,
`test_sibling_scan.py::TestSS02/03/18`, `scan8a::TestSS09/16/20/22/A10/A15/C2/T1/X1/60`); the model's T6/T6' and
freshness records agree with the kernel (differential `KNOWN` loses `D-035`); fault cells FM-D-07, FM-E-03, FM-E-06,
FM-W-05 GREEN; INV-A.*, C.1, C.3, D.*, E.1, E.3, K.2, K.3, P.2 PROVEN; negative controls, full suite, ruff, Linux and
Windows CI green. No STORY-04-01 special case anywhere.

## 7. Closure record (2026-09-16, branch hardening/systematic-v1)

Implemented as designed: `aisef/control/identity.py` (identity tuple, `fresh()`, `tree_state_digest`, harness-path
exclusions, `CURRENT` context so every store of an attempt stamps the attempt's identity), `Event.identity` +
schema-1 migration on read, `Evidence.for_identity` / `last_fresh` / candidate of record, gate `_stale_for` (freshness,
never recency; evidence pointer at the foreign record), typed UNRUNNABLE for a story attempt without a candidate,
session-bound guard proofs, `run_attempt` no-op decision on a FRESH verdict (T6/T6'), freeze returns no candidate on
failure, `_invalidate_after_tree_change` (recovery) and `_record_head_moved` (refresh / wave-end / manual move),
soft reset + selective restore after a reviewer commit, pinned preservation list on review retries, nop control at
the epoch's baseline root (when it precedes the candidate), baseline re-captured at the root through a temporary
worktree, resume feedback read from `reviewer:verdict`, TDD verdict by position, waiver bound to the story tip,
`verification.completed` carries the candidate.

Members RED → GREEN (markers removed in this commit): D-035, SS-61, SS-02, SS-03, SS-04, SS-09, SS-16, SS-18, SS-20,
SS-22, SS-A10 (2), SS-A15, SS-C2, SS-T1, SS-X1, SS-60; compound CF-05, CF-06; fault cell TestStaleFaults.
Fault matrix 50 GREEN / 19 RED (was 43 / 26). Registry 22 PROVEN / 24 PARTIAL / 4 MISSING (was 12 / 28 / 10).
Differential: 400 traces on the baseline seed range, 0 unexplained, `KNOWN` no longer lists D-035. State model
10 000 traces, 0 violations, 18 conformance scenarios agree or deviate where SS-12/13/14/15/57/59 predict.

Existing tests adapted to the new contract (each change names why): the implement fixture has a HEAD; simulated
guard traces stamp their session; the identical-tree retry writes in scope (an out-of-scope write is restored by
hygiene and legitimately re-graded); the review-recovery fixture seeds identity-stamped evidence; the D-033
fail-closed test now expects capture at the integrated parent (INV-C.3); the gate-qualification staleness test asserts
"no fresh record" rather than "latest record elsewhere", with the inverse as a companion; the interrupted-review test
seeds `reviewer:verdict`.
