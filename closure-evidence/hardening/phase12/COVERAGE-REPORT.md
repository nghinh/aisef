# Phase 12 — coverage report (100 000 single-kernel traces)

Rendered 2026-09-21 00:05 +0700 from `phase12/integrity.json` and `phase12/PHASE12-DATASET-MANIFEST.json` by `validation/p12_coverage_report.py`. Kernel: `aisef/` tree `4359f347378e…` (PHASE12_KERNEL_DIGEST), the only digest in the dataset (`4359f347378e`).

## Totals

| traces | matched | unexplained | invariant violations | exceptions | silent skips | chunks complete | ranges |
|---|---|---|---|---|---|---|---|
| 100000 | 100000 | 0 | 0 | 0 | 0 | 10/10 | overlap=False, missing=[] |

## Transitions T1–T34 + T6′ (docs/ASSURANCE-KERNEL.md §6)

Reachable in the single-story differential: **26 / 26 hit**. Unhit reachable: none.

| transition | reachable here | model hits | first seed | covered by |
|---|---|---|---|---|
| T1 | no | 0 | — | claim by a live process — run loop (tests/test_run.py, test_state.py TestLeaseEdges) |
| T2 | no | 0 | — | reclaim of an orphaned claim — reconcile (tests/test_dogfood_ledgerlock.py, scan8a TestSS49) |
| T3 | yes | 60960 | 0 | differential |
| T4 | no | 0 | — | unattributed out-of-scope dirt blocks — hygiene (tests/hardening/test_ownership.py, scan8a TestSS37) |
| T5 | yes | 96486 | 0 | differential |
| T6 | yes | 18851 | 1 | differential |
| T7 | yes | 6437 | 13 | differential |
| T8 | yes | 7448 | 7 | differential |
| T9 | yes | 36432 | 0 | differential |
| T10 | yes | 4055 | 72 | differential |
| T11 | yes | 2027 | 87 | differential |
| T12 | yes | 14689 | 1 | differential |
| T13 | yes | 117612 | 0 | differential |
| T14 | no | 0 | — | pre-staged out-of-scope paths at freeze — tests/test_implement.py (freeze) / scan8a TestSS15 |
| T15 | yes | 112845 | 0 | differential |
| T16 | yes | 11109 | 2 | differential |
| T17 | yes | 66998 | 0 | differential |
| T18 | yes | 28284 | 2 | differential |
| T19 | yes | 4194 | 8 | differential |
| T20 | yes | 37525 | 0 | differential |
| T21 | yes | 9897 | 5 | differential |
| T22 | yes | 102305 | 0 | differential |
| T23 | yes | 23566 | 7 | differential |
| T24 | yes | 34395 | 0 | differential |
| T25 | yes | 60960 | 0 | differential |
| T26 | yes | 46217 | 0 | differential |
| T27 | yes | 8680 | 6 | differential |
| T28 | yes | 5911 | 2 | differential |
| T29 | yes | 34395 | 0 | differential |
| T30 | no | 0 | — | merge conflict — the synthetic merge never conflicts; tests/test_worktree.py (merge conflict), tests/test_run.py |
| T31 | no | 0 | — | process death — crash recovery (tests/test_crash_recovery.py, compound CF-05) |
| T32 | no | 0 | — | contract change — epoch (tests/test_worktree.py TestNhanhCuKhiTieuChiDoi, compound CF-13) |
| T33 | no | 0 | — | owner arbitration — compound CF-13 / test_approvals TestCascade |
| T34 | no | 0 | — | run end commit + worktree removal — tests/test_run.py |
| T6' | yes | 858 | 30 | differential |

### Unreachable here, with justification and deterministic cover

- **T1** — claim by a live process — run loop (tests/test_run.py, test_state.py TestLeaseEdges)
- **T2** — reclaim of an orphaned claim — reconcile (tests/test_dogfood_ledgerlock.py, scan8a TestSS49)
- **T4** — unattributed out-of-scope dirt blocks — hygiene (tests/hardening/test_ownership.py, scan8a TestSS37)
- **T14** — pre-staged out-of-scope paths at freeze — tests/test_implement.py (freeze) / scan8a TestSS15
- **T31** — process death — crash recovery (tests/test_crash_recovery.py, compound CF-05)
- **T32** — contract change — epoch (tests/test_worktree.py TestNhanhCuKhiTieuChiDoi, compound CF-13)
- **T33** — owner arbitration — compound CF-13 / test_approvals TestCascade
- **T34** — run end commit + worktree removal — tests/test_run.py
- **T30** — merge conflict — the synthetic merge never conflicts; tests/test_worktree.py (merge conflict), tests/test_run.py

## Typed outcomes, terminal classes, event and fault kinds

- typed outcomes hit (10): AUTH_FAILURE, ENVIRONMENT_FAILURE, HUMAN_REQUIRED, INFRA_FAILURE, ISOLATION_BREACH, NOOP, PASS, PLAN_CONFLICT, QUALITY_BLOCK, UNRUNNABLE
- terminal classes, model: ['blocked', 'done', 'failed', 'human']; kernel: ['blocked', 'done', 'failed', 'human']
- model event kinds hit (31): DEVELOP_AUTH, DEVELOP_BUDGET, DEVELOP_CHANGED, DEVELOP_CONTEXT, DEVELOP_CRASH, DEVELOP_MAX_TURNS_UNTOUCHED, DEVELOP_MAX_TURNS_WORK, DEVELOP_NOOP, DEVELOP_RATE_LIMIT, DEVELOP_SCOPE_VIOLATION, DEVELOP_TIMEOUT, DEVELOP_TRUNK_COMMIT, DEVELOP_ZERO_OUTPUT, GATE_EVALUATE, REVIEW_BLOCK, REVIEW_BLOCK_OUTSIDE, REVIEW_BLOCK_UNBOUND, REVIEW_BUDGET, REVIEW_MALFORMED, REVIEW_MUTATE, REVIEW_PASS, REVIEW_STUCK, REVIEW_UNRUNNABLE, SECURITY_BLOCK, SECURITY_BUDGET, SECURITY_MALFORMED, SECURITY_PASS, SECURITY_UNRUNNABLE, TEST_FAIL, TEST_PASS, TEST_UNRUNNABLE
- injected fault kinds hit: 28 / 28 possible (all)

## Compound-fault coverage

- traces with ≥ 2 distinct injected faults: 92789
- distinct fault pairs hit: 378 / 378 possible (all)

## Saturation by 10k

| after seeds | transitions seen | new in this chunk |
|---|---|---|
| 10000 | 26 | T10, T11, T12, T13, T15, T16, T17, T18, T19, T20, T21, T22, T23, T24, T25, T26, T27, T28, T29, T3, T5, T6, T6', T7, T8, T9 |
| 20000 | 26 | — |
| 30000 | 26 | — |
| 40000 | 26 | — |
| 50000 | 26 | — |
| 60000 | 26 | — |
| 70000 | 26 | — |
| 80000 | 26 | — |
| 90000 | 26 | — |
| 100000 | 26 | — |

## Per chunk

| chunk | seeds | traces | transitions | runtime s | mismatches | violations | rows | product tree | comparator |
|---|---|---|---|---|---|---|---|---|---|
| 00000 | 0–9999 | 10000 | 73155 | 2343.5 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 10000 | 10000–19999 | 10000 | 72294 | 2251.7 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 20000 | 20000–29999 | 10000 | 73209 | 2333.0 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 30000 | 30000–39999 | 10000 | 72970 | 2300.9 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 40000 | 40000–49999 | 10000 | 73230 | 2328.3 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 50000 | 50000–59999 | 10000 | 72480 | 2324.0 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 60000 | 60000–69999 | 10000 | 72945 | 2316.6 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 70000 | 70000–79999 | 10000 | 73044 | 2288.9 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 80000 | 80000–89999 | 10000 | 72677 | 2307.3 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |
| 90000 | 90000–99999 | 10000 | 73410 | 2315.8 | 0 | 0 | 10000 | 4359f347378e | f8f3a954bc20 |

## Earlier runs (not final qualification evidence)

- `SUPERSEDED_NOT_QUALIFICATION_EVIDENCE` — 8 files under `closure-evidence/hardening/phase12/superseded` (see its README)
- `VALID_HISTORICAL_EVIDENCE_NOT_FINAL_QUALIFICATION` — 21 files under `closure-evidence/hardening/phase12/history-kernel-02a34e0e` (see its README)
- `VALID_HISTORICAL_EVIDENCE_NOT_FINAL_QUALIFICATION` — 21 files under `closure-evidence/hardening/phase12/history-kernel-84014c98` (see its README)
- `VALID_HISTORICAL_EVIDENCE_NOT_FINAL_QUALIFICATION` — 11 files under `closure-evidence/hardening/phase12/history-kernel-a2f6e76b` (see its README)
