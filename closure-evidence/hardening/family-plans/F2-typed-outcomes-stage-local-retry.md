# Fix family F2 — TYPED OUTCOMES / STAGE-LOCAL RETRY

Closes (frozen defect set): SS-12, SS-13, SS-14, SS-15, SS-19, SS-21, SS-57, SS-58, SS-59, AD-01, AD-03, AD-04,
AD-05 (+ SS-28's adapter reproducer is F3). Invariants: INV-F.1, INV-F.3, INV-F.4, INV-G.1–G.5, INV-N.1.

## 1. One outcome vocabulary, carried as data

`aisef/control/outcome.py` gains the kernel's stage-outcome vocabulary (docs/ASSURANCE-KERNEL.md §4):
`PASS, QUALITY_BLOCK, UNRUNNABLE, ENVIRONMENT_FAILURE, INFRA_FAILURE, AUTH_FAILURE, NOOP, PLAN_CONFLICT,
HUMAN_REQUIRED, ISOLATION_BREACH, MERGE_CONFLICT, ORPHANED, BUDGET`. `Attempt.outcome` (typed) becomes the source of
truth; `infra` / `fatal` / `noop` stay as derived booleans for readers. `StoryOutcome.terminal` (typed class +
reason) accompanies `blocked_reason` (prose for humans). Nothing downstream — the loop, the journal, the differential
classifier — reads prose to decide.

## 2. Session exits → typed outcomes (INV-F.4, INV-G.4/G.5)

`clients/stream.session_outcome(result, *, tree_moved)`:

| provider condition | outcome | budget |
|---|---|---|
| ok, tree moved | graded (candidate) | quality |
| ok, tree untouched | NOOP (F1 decides: fresh block → decision stated; else grade) | nothing-to-grade budget |
| max_turns, tree moved | graded | quality |
| max_turns, untouched | QUALITY (the developer's session, no candidate) | quality |
| timeout, 5xx, rate limit, empty stream, child death, truncated stream | INFRA_FAILURE | infra |
| context overflow, permission, provider cost cap | ENVIRONMENT_FAILURE — never quality (SS-15) | infra |
| 401/403 (from the provider field, never prose — F3) | AUTH_FAILURE, fatal | none |
| zero output (tokens, no tools, tree untouched — `tree_before`, not `changed_files(base_ref)`: SS-59) | ENVIRONMENT_FAILURE, fatal | none |
| kernel budget cap reached | BUDGET — typed terminal, uncharged | none |
| budget ledger lock contention (SS-21) | INFRA_FAILURE with the lock named; never "cap reached" | infra |
| trunk commit | ISOLATION_BREACH, fatal | none |

Adapters (AD-01/03/04/05): an empty stream with exit 0 is INFRA ("stream ended without a result event"); a child that
dies (non-zero exit, no result event) records `exit_code` and stderr in `raw_result` and is INFRA; a result event that
arrives after the timeout decision is recorded but never flips `ok`; both adapters map the same condition to the same
status (the adapter conformance suite is the proof).

## 3. Verifier stages: absence is never a verdict (INV-F.1/F.2, INV-G.1/G.2)

- `_reconcile` / `_reconcile_security` with `verdict is None` after the schema retry → `REVIEW_UNRUNNABLE` /
  `SECURITY_UNRUNNABLE` (no structured verdict) — never scored from prose (SS-57). Prose findings are recorded as
  observations only.
- Security session failure (cut, moved tree, budget) → `Check("security", UNRUNNABLE)` with the failure named, exactly
  as review does since D-032 (SS-13); `SecurityReport.unrunnable` replaces the FAILED-with-error shape.
- `_review_stage` generalises to `_verifier_stage(stage)` for review AND security: bounded per-candidate retries
  (`MAX_REVIEW_RETRIES`), terminal `REVIEW_UNRUNNABLE` / `SECURITY_UNRUNNABLE`, candidate kept, never a developer.
- `BudgetExceeded` inside a verifier session → typed BUDGET terminal (SS-12: the `mockup.RunResult` import goes;
  `clients.stream.RunResult` is the one type).

## 4. Tool / environment stages (INV-F.3, INV-G.3, INV-N.1)

- The gate's `lint` branch maps `detail.unrunnable` → UNRUNNABLE exactly as `test` does (SS-58); `qa:<kind>` runs
  carry `unrunnable` (SS-34 is F5's tool half — the gate side lands here).
- The loop's routing reads the gate's failures by TYPE: any QUALITY_BLOCK → developer (with every finding as
  feedback); only UNRUNNABLE / ENVIRONMENT → retry THAT stage (tool re-verify with `reuse=True`, review, security),
  bounded by the infra budget, terminal `ENVIRONMENT_FAILURE: <stage> unrunnable` (SS-14, SS-19). `_only_review_unrunnable`
  becomes `_blocked_only_by_absence(attempt) -> {stages}`.

## 5. Journal and report

`review.completed` / `verification.completed` record the typed outcome per attempt; the RunReport carries typed
terminals; the differential classifier reads `StoryOutcome.terminal`, and its prose fallback is deleted.

## 6. Definition of done

RED → GREEN: `test_sibling_scan.py::TestSS12/13/14/15/19/23?/26?` (23/26 are F3), `scan8a::TestSS21/19`,
`test_fault_matrix.py::TestToolFaults::test_missing_linter_is_unrunnable`, `TestReviewFaults::test_a_malformed_verdict_never_passes_the_review`,
`TestSecurityFaults` malformed, `TestDeveloperFaults::test_zero_output_on_a_retry…`, `test_compound_faults.py::TestCF02`,
`adapters/test_conformance.py` AD-01/03/04/05 cells; model: `differential.KNOWN` loses SS-12/13/14/15/21/57/59;
fault cells FM-D-04, FM-D-11, FM-T-03, FM-L-02, FM-R-04, FM-R-05, FM-S-02, FM-S-03, FM-C-02 GREEN; INV-F.1/F.3/F.4,
G.1–G.5, N.1 PROVEN; full suite, ruff, Linux + Windows CI.

## 7. Closure record (2026-09-16, branch hardening/systematic-v1)

Implemented as designed, with three corrections found by the differential harness during implementation:

- **Vocabulary carried as data**: `StageOutcome` (13 kinds), `Attempt.outcome`, `StoryOutcome.terminal` + `block(kind, reason)`;
  every loop terminal is typed; the trunk-commit breach is typed where it is detected (no reader infers it from wording).
- **Session exits**: `exit_status_of` → INFRA / ENVIRONMENT (`context`, `permission`, `cost` never charge quality — SS-15);
  `BudgetLocked` (lock contention) is infra and retried (SS-21); a cap is `BUDGET`, typed and uncharged (developer and
  verifier sessions alike — SS-12); the zero-output check diffs THIS session's tree, so it fires on retries (SS-59).
- **Verifier absence is never a verdict**: `_with_schema` returns `(text, verdict, why)` — a schema retry that could
  not EXECUTE (budget cap, cut, moved candidate, reverted tree) is reported as that, never as "prose twice";
  `review_story_v2` / `_reconcile_security` → `REVIEW_UNRUNNABLE` / `SECURITY_UNRUNNABLE` on `verdict is None`
  (SS-57, SS-13); `SecurityReport.unrunnable` replaces the FAILED-with-error shape; the gate scores `security` and
  `lint` UNRUNNABLE from `detail.unrunnable` (SS-13, SS-58), and `criteria have tests` inherits UNRUNNABLE when the
  runner itself could not run (SS-14). Test fakes now answer the structured envelope a production reviewer must.
- **Stage-local retry**: `_absent_stages(attempt)` (empty when anything FAILED) → `_review_stage` re-runs exactly the
  absent stages (review / security / tools) on the frozen candidate with `reuse=True`, bounded per candidate in
  EXECUTIONS (`MAX_REVIEW_RETRIES`, `MAX_TOOL_RETRIES`; a schema retry belongs to its execution — `_security_executions`
  fixed), terminals `REVIEW_UNRUNNABLE` / `SECURITY_UNRUNNABLE` / `ENVIRONMENT_FAILURE`, never a developer session
  and never the developer's quality budget (SS-14, SS-19). A verifier budget cap (`_verifier_budget_cap`) is checked
  before any routing and opens no further session, not even the security reviewer.
- **Absence never PASSes (INV-T.1, same rule, evidence side)**: `real tests` is UNRUNNABLE without a `qa:fake-tests`
  record and `qa.run_suite` records the clean scan too (SS-01); a truncated id list makes `no baseline regression` and
  the tagged-tests check UNRUNNABLE, never a vacuous PASS, with the cap raised to 5000 (SS-33).
- **Adapters** (AD-01/03/04/05): empty stream with exit 0 → INFRA ("stream ended without a result event"); child death
  → `exit_code` + stderr recorded, INFRA; a result event after the timeout decision never flips `ok`; both adapters agree.
- **Differential harness**: the terminal classifier reads `StoryOutcome.terminal` and attempt flags only — the prose
  fallback is deleted (an untyped terminal is a mismatch by construction); executions are counted from evidence
  (`agent_run` names), not client sessions; the model driver mirrors the client's extra session on a malformed verdict;
  the model runs every verifier when the test tool is unrunnable (as the kernel does), re-runs an UNRUNNABLE security
  record, and bounds tool re-runs per candidate (never the infra budget). `KNOWN` is empty.

Members RED → GREEN (markers removed in this commit): SS-12, SS-13 (2), SS-14, SS-15, SS-19, SS-21, SS-57, SS-58,
SS-59, SS-01, SS-33 (2), AD-01, AD-03, AD-04, AD-05; compound CF-02; fault cells FM-D-04, FM-D-11, FM-T-03, FM-L-02,
FM-R-04, FM-R-05, FM-S-02, FM-S-03, FM-C-02. SS-57 is a FAM-PROSE (F3) member closed by this family's rule; F3 re-verifies it.

**Sibling found during implementation (Phase 9 rule — explicit provenance)**: SS-62, differential seed 232 after
`KNOWN` was emptied: a reviewer commit made during the SCHEMA-RETRY session was recorded but not restored (F1's SS-A10
covered the first session only); HEAD stayed off the frozen candidate and a second developer opened over a candidate
that no longer existed. Reproducer `tests/hardening/test_differential.py::TestSeed232ReviewerCommitOnTheSchemaRetry`:
RED at c384383 (run in a throwaway worktree), GREEN after `_with_schema` restores the candidate. Added to F1's member
list as FIXED with this provenance; F1's closure claim stands corrected by this record.

Fault matrix 59 GREEN / 10 RED / 0 NEEDS_TEST (was 50 / 19). Registry 26 PROVEN / 22 PARTIAL / 2 MISSING (was 22 / 24 / 4):
INV-G.2, G.3, G.4, G.5 PROVEN; INV-F.3, F.4, N.1, T.1 stay PARTIAL with their remaining red reproducers named (SS-23,
SS-26, SS-28 — F3; SS-34, SS-45–48 — F5; SS-05, SS-27 — F3/F6). New registry rule: an invariant claimed by an OPEN
member of the frozen set is never PROVEN (`test_a_proven_invariant_is_claimed_by_no_open_defect_of_the_frozen_set`).
Frozen defect set: 32 FIXED / 40 OPEN of 72. Differential: 400 traces (seeds 0–399) 400 matched, 0 unexplained,
`KNOWN = {}`; state model 10 000 traces 0 violations, 18 conformance scenarios agree. Existing tests adapted to the
contract (each names why): fakes answer structured verdicts; the schema-retry cost test counts three runs; the prose-only
deadlock test now asserts REVIEW_UNRUNNABLE with no developer cost and exactly one schema retry; decided-no-op fakes carry
a tool use (a session that looked and declined is not zero output); gate fixtures and the C8 probe record the scan.

**CI on the F1 commit (c384383, run 35092276631)**: Linux 3.11–3.14, lint and wheel green; Windows 3.11 red with two
errors, both test-side and both explained: (1) `TestSS60ADoneStoryHasAFrozenCandidate.setUp` removed `.git` with a plain
`shutil.rmtree` — Windows marks `.git/objects` read-only (`WinError 5`); the fixture now uses `aisef.kit.fetch.remove_tree`,
the helper written for exactly this. (2) `test_memory.IntegrationTests.test_concurrent_writers` timed out on the memory
lock: five writers queue on one file lock, `msvcrt.locking` surfaces the wait as `PermissionError → BlockingIOError`, and
on a runner 25 % slower than the baseline the last writer waited past the 2 s single-writer default; the test measures
correctness (20 ids, 20 records), so it now waits up to 30 s. No kernel change; both fixes ride with this commit and the
Windows job is re-qualified on it.

**2 000-trace differential (seeds 1000–2999) before closure**: 1 984 matched, 16 unexplained, three causes, all resolved
in this commit. (a) Ten seeds: my `_verifier_budget_cap` read the review's absence text first and stopped, so a security
session's budget cap went unnoticed whenever the review in the same round was also absent — the kernel kept opening
sessions after a cap; the check now reads both verifiers. (b) Seed 2531: the KERNEL was right — a no-op session that is
re-graded because hygiene changed the tree is a graded position, and two identical out-of-scope blocks on that candidate
pair into a plan conflict; the model had reset its "previous graded" bookkeeping on every no-op. (c) Seed 2624: the kernel
was wrong — `deadlock_reason` compared adjacent attempt records, so a reviewer mutation (D-032 review re-run) between two
identical out-of-scope blocks hid the plan conflict and the story burned its budget as `did not pass gate`. Registered as
**SS-63** (FAM-JUDGE, INV-Q.1, F3's family) with provenance; reproducer
`tests/hardening/test_differential.py::TestSeed2624PlanConflictSurvivesAVerifierRerun` RED at c384383, GREEN here;
`deadlock_reason` now pairs graded positions (attempts whose reviewer produced a verdict). The 2 000 traces were re-run
after the three changes; the result is recorded in `closure-evidence/hardening/differential-f2-2000.json`.

**Final state at closure (this commit)**: differential 400 traces (seeds 0–399) 400 matched and 2 000 traces (seeds
1000–2999) 2 000 matched, 0 unexplained, `KNOWN = {}` (both JSON records re-run on the finished tree); state model
10 000 traces 0 violations, 18 conformance scenarios agree; full suite 3 311 passed / 20 skipped / 43 expected-red,
every expected-red tagged with a defect id of a later family; ruff clean. Frozen defect set 33 FIXED / 40 OPEN of 73.
Fault matrix 59 GREEN / 10 RED / 0 NEEDS_TEST. Registry 26 PROVEN / 22 PARTIAL / 2 MISSING. Linux and Windows CI on
this commit are the last two conditions of the family's definition of done; they are read from the PR checks.
