# Phase 13 — targeted mutation testing of decision-critical kernel code

Tool: `validation/mutate.py` (stdlib; each mutant is one AST change at one site, run in its own copy of the
repository against the target's named tests; non-zero exit KILLS, exit 0 SURVIVES; `equivalent` entries are
reported separately and never count as survivors). Targets: `validation/mutation-targets.json` — 28 functions,
270 mutants (`--list`), operators CMP, NOT, ANDOR, BOOL, STR, VERDICT, INCR, RET, DROPCALL:

| area | functions |
|---|---|
| freshness / evidence validity | `identity.fresh`, `gate._stale_for`, `gate._latest_per_check`, `gate.verdict_recorded` |
| closure probes | `closure._is_ancestor`, `probe_review_and_security`, `probe_evidence_at_candidate` |
| approvals | `ApprovalStore.status`, `.content_hash`, `._upstream_stale` |
| leases / budget | `state.claim_is_live`, `StateStore.transition`, `budget._reservation_live`, `budget._check_caps` |
| ownership / processes | `ownership.classify`, `process_owner.reap`, `process_owner.survivors` |
| judgment / routing | `implement.deadlock_reason`, `_same_complaint`, `_paths_outside`, `finding_bound`, `Verdict.bound_blocking`, `structured_plan_defects`, `_verifier_budget_cap`, `_absent_stages`, `nop_deadlock` |
| adapters / tools | `stream.exit_status_of`, `tools.unrunnable_reason` |

Rule (owner directive): **no surviving P0/P1-significant mutation is acceptable.** Every survivor is classified:
(a) KILLED by a new deterministic test that names the mutant's site and the invariant it would have broken, or
(b) EQUIVALENT — the mutant cannot change any observable decision — listed under `equivalent` with the reason, or
(c) NOT SIGNIFICANT — the mutant changes only a message, a log line or an ordering with no control effect; listed
with the reason, and counted separately. Nothing is left unclassified. The run is executed with no other CPU-heavy
job on the machine (a timing failure would count as a kill and hide a survivor). Results:
`closure-evidence/hardening/mutation-results.json`; the survivor classification is appended to this file.

## Run 1 (2026-09-17, bb31522 tree, 4 workers, no other CPU-heavy job)

271 mutants generated, 210 killed, 61 survived, 0 declared equivalent; 1326 s. Survivors by function: nop_deadlock 12,
_same_complaint 8, StateStore.transition 8, reap 7, _paths_outside 5, exit_status_of 4, _verifier_budget_cap 3,
unrunnable_reason 3, claim_is_live 3, fresh 3, deadlock_reason 2, _check_caps 2, _upstream_stale 1.

Classification of run 1's survivors (every one):

- **Cited-test gap, not a proof gap** — the target named test files that never reach the function; the tests that
  do exist elsewhere and are now cited: nop_deadlock (`test_implement::TestBeTacDoKeHoachTheoNopControl`,
  scan8a `TestSS32…`), _same_complaint (`test_same_complaint_finding.py`, `test_findings.py`), _paths_outside
  (`test_sibling_scan::TestSS25…`), fresh (`test_evidence_schema.py`), exit_status_of (`test_stream::TestExitStatus`).
- **Real gaps, killed by new tests** (each names the mutant's site and the invariant): `_verifier_budget_cap`
  (a cap in EITHER verifier; lock contention is not a cap — `TestVerifierBudgetCapReadsBothVerifiers`);
  `deadlock_reason` line 3129 (an infra attempt between two positions does not break the pair —
  `TestDeadlockPairSurvivesAnInfraAttempt`); `claim_is_live` ×3 and `transition` ×8 (no claim is not live; an
  orphaned claim is not live even with a term; a term-less foreign claim is not live; an unattributed write is
  refused against a foreign live claim but not a local one; only the owner's write refreshes the term; evidence and
  worktree survive a transition that does not name them — `TestLeaseEdges`); `reap` (SIGTERM first with a grace
  wait, hard kill for a SIGTERM-ignoring child — `TestReapTerminatesGracefullyBeforeItKills`); `unrunnable_reason`
  (exit 127 alone; missing manifest vs missing dependencies vs missing tool — `TestUnrunnableReasonBranches`);
  `exit_status_of` (max_cost alone; 429 status alone and rate-limit text alone; connection text alone; permission
  vs plain error — `TestExitStatusBranches`); `fresh` (unbound never fresh; legacy record fresh for a legacy decider,
  with and without the file's story — `TestFreshEdges`); `_check_caps` (wall-clock cap — `TestWallClockCap`);
  `_upstream_stale` (a gate outside the order has no upstream — `TestGatesOutsideTheOrderHaveNoUpstream`).
- **EQUIVALENT** (declared in `validation/mutation-targets.json` with the reason): `deadlock_reason` line 3141
  (`or`→`and` falls through to `_same_complaint(x, [])`, which returns False — the same ""); `reap` lines 120/126
  (dropping `time.sleep` inside the deadline loop is a busy wait with the same exit condition).
- **NOT SIGNIFICANT**: `reap` line 125 (`Lt → GtE` skips the second grace wait: the return value still filters by
  `pid_alive`, and `survivors()` verifies afterwards — latency, never a wrong "dead"); `fresh` line 122 (the branch
  chooses between two reason WORDINGS of the same `Freshness(False)` — control never reads the wording; the
  Phase 16 test does assert "schema 1" in the stale reason, so this one is also expected to be killed by run 2).

Run 2 (same tree + the new tests, cited; 1240 s): 271 generated, 251 killed, 17 survived, 3 excluded as equivalent.
The 17: `_same_complaint` ×8 — the legacy token-overlap fallback, unreached by the finding-id tests
(`TestLegacyTokenOverlapRule` now pins the verbatim, two-noun, one-noun and low-ratio cases; the `not x or not y`
guard is EQUIVALENT); `_paths_outside` ×5 (`TestPathsOutsideEdges`: a root manifest is a path, a technology word is
not, in-scope is not reported, duplicates once, a dict finding's file, an empty scope); `nop_deadlock` ×1
(`TestNopDeadlockPositions`: one verdict alone is "", one verdict plus two no-ops is the plan diagnosis);
`deadlock_reason` ×1 — the review_findings `or` → `and`, EQUIVALENT (the same-complaint check of an empty list is
False), declared by its own id; `StateStore.transition` ×1 — the `or` inside the refusal MESSAGE, NOT SIGNIFICANT;
`unrunnable_reason` ×1 — the `or` inside the generic reason MESSAGE, NOT SIGNIFICANT. One correction on the way: run
1's equivalence entry named the wrong site (it pointed at `write_scope or []` → `and`, which turns a non-empty scope
into an empty one and would report an in-scope repeat as stuck — SIGNIFICANT); that entry was removed and the mutant
is killed by `TestInScopeRepeatIsNotStuck`. `validation/mutate.py` gained a `not_significant` list (reported with its
reason, never a survivor) beside `equivalent`.

Run 3 (authoritative, quiet CPU, 1172 s): **271 generated, 265 killed, 0 survived, 6 excluded** — 4 EQUIVALENT
(`deadlock_reason` review_findings guard; `_same_complaint` empty-token guard; `reap` busy-wait ×2) and 2 NOT
SIGNIFICANT (two message wordings), each declared by mutant id with its reason in `validation/mutation-targets.json`.
No surviving mutation of any significance: the owner's rule holds. Results: `closure-evidence/hardening/mutation-results.json`.
