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
