# Phase 12 — differential harness, 100 000 traces

Harness: `tests/hardening/differential.py` — the reference model (`tests/hardening/model.py`) and the real kernel
(`implement_story` with the synthetic client) are driven by the same seeded random trace; the observation (terminal
class, developer sessions, review/security executions, quality attempts, infra attempts, candidates frozen,
processes surviving) is compared field by field; `KNOWN == {}` — every mismatch is unexplained by construction.
Vocabulary at this phase: developer CHANGED / CHANGED_RED / CHANGED_ARTIFACT / CHANGED_ORPHAN / NOOP / TIMEOUT /
CRASH / RATE_LIMIT / CONTEXT / AUTH / SCOPE_VIOLATION / TRUNK_COMMIT / ZERO_OUTPUT / MAX_TURNS_WORK /
MAX_TURNS_UNTOUCHED / BUDGET; reviewer PASS / BLOCK / BLOCK_OUTSIDE / STUCK / MALFORMED / UNRUNNABLE / MUTATE /
COMMIT / BUDGET / BLOCK_UNBOUND; security PASS / BLOCK / UNRUNNABLE / MALFORMED / BUDGET; retries 1–2; test tool
present/missing.

Measured performance (2026-09-17, this host: 8 cores): 6 workers 2.72–3.15 traces/s; 8 workers 3.21 traces/s
(400-trace measurement). 100 000 traces ≈ 31 000 s ≈ 8.7 h. Reported here before the run per the owner's rule; the
target is NOT reduced. The run is executed in ten chunks of 10 000 seeds (`--start 0, 10000, …, 90000`, 8 workers),
each written to `closure-evidence/hardening/differential-p12-<start>.json`, so the timing-sensitive full suite and
the mutation run can take the gaps between chunks (they never share the CPU with a chunk). The consolidation
(`differential-p12-summary.json`: traces, matched, unexplained, elapsed, throughput, seed ranges) is produced by a
script that exits non-zero unless traces ≥ 100 000 and unexplained == 0.

Rule: an unexplained trace is diagnosed by seed (`--seed N`), attributed to the kernel or to the model with the
kernel's typed facts as the arbiter, fixed at its source with a seed-pinned regression test, and the affected chunk
is re-run before the summary is produced. Nothing is added to `KNOWN`.

## Closure record (2026-09-17 13:20, single-kernel dataset — owner decision "FINALIZE PHASE 12 WITH SINGLE-KERNEL EVIDENCE")

**Dataset.** Ten chunks of 10 000 seeds (0–99 999), run 06:36 → 13:20 on one machine, 8 workers, ≈ 4.1 traces/s: 100 000 / 100 000
traces matched the reference model; 0 unexplained mismatches; 0 invariant violations (the model's `check_properties` after every
transition, added to the comparator for this run); 0 worker exceptions (an exception would have been a FAILED row); 0 silent skips
(rows == traces in every chunk); ranges disjoint and complete. Every chunk recorded the product identity it ran against: `aisef/`
tree `84014c980e75…` = PHASE12_KERNEL_DIGEST (`phase12/PHASE12-KERNEL-IDENTITY.json`, git faf3ecd; the chain started at 6470e4e,
whose `aisef/` tree is the same object), on-disk content `4bd5f620…`, invariant registry `466abf4a…`, synthetic adapter `8aeb2319…`,
transition model `983dc3bb…`, comparator `f8f3a954…` — one value each across all ten chunks, `dirty_aisef = []` everywhere.
`phase12/PHASE12-DATASET-MANIFEST.json`: all hard requirements met; per-chunk raw-row artefacts (`*.rows.jsonl.gz`, 336–341 KB each)
with their sha256. Consolidation: `phase12/integrity.json` (exit 0), W0 summary `differential-p12-summary.json`.

**Coverage, not count** (`phase12/COVERAGE-REPORT.md`): 26 / 26 transitions reachable in the single-story differential hit — all 26
already by seed 9 999 (saturation: no new transition in chunks 2–10; first seeds 0–87); the 9 unreachable here (T1, T2, T4, T14,
T30–T34: claim/reclaim, unattributed dirt, pre-staged paths, merge conflict, process death, contract change, arbitration, run end)
each carry their deterministic cover. 10 typed outcomes, 4 terminal classes (blocked, done, failed, human) on both sides, 31 model
event kinds, 28 / 28 injected fault kinds, 378 / 378 distinct fault pairs, 92 789 traces with two or more distinct faults. No
targeted scenario was needed for a reachable transition; the random count was not inflated beyond 100k.

**Superseded.** The first chain (2026-09-16 23:30 → 2026-09-17 06:10: chunks 00000–50000 complete, 60000 killed at 2 000 traces) ran
against up to three kernel states and recorded no digests; it is retained under `phase12/superseded/` as
SUPERSEDED_NOT_QUALIFICATION_EVIDENCE with its diagnostic value stated (59 999 / 60 000 matched; the one mismatch is SS-64). The
targeted re-run sets designed before the decision (4 267 SS-64 seeds + 500 controls) were not used.

**SS-64** (seed 34999, chunk 30000 of the superseded chain; P2, INV-G.5, F2, fixed in f0cd772): `phase12/SS-64-CLOSURE.json` — all
eleven owner requirements measured and met (reproducers RED on a worktree at d956249 and GREEN now on both paths; 10/10 deterministic
replays; INV-G.5 PROVEN; F2 siblings clean; FM-R-09 GREEN; Linux + Windows CI green on f0cd772; deterministic conformance 19 passed,
adapters untouched).

**Infrastructure.** The watchdog was rewritten as a pure decision with deterministic tests (progressing / stalled / dead /
unmeasurable → TOOL_UNAVAILABLE; liveness through the product's cross-platform probe after Windows CI showed `os.kill(pid, 0)` is not
one). Incident: the first armed instance died silently (signal 16) after 3 h while the chain continued; the chain's completion was
verified from the chunk records and a re-armed instance reported CHAIN COMPLETE; a 30-minute heartbeat was added. Comparator
history for the record: the recording/property-check additions and an explicit-encoding fix produced three comparator digests during
the day; the qualification chain was restarted from chunk 00000 after the last of them, so the final dataset carries exactly one.

**Verification after the dataset.** Full local suite 3 428 passed / 20 skipped / 1 444 subtests (528 s); `ruff check .` clean; the
product tree unchanged since PHASE12-KERNEL-IDENTITY. CI on this commit is recorded by the W0 qualification record.

## Closure record — single-kernel dataset (2026-09-17, owner decision "FINALIZE PHASE 12 WITH SINGLE-KERNEL EVIDENCE")

**Dataset.** 10 chunks × 10 000 seeds (0–99 999), 100,000 effective traces, 100,000 matched, 0 unexplained, 0 invariant violations (the model's `check_properties` after every transition), 0 exceptions, 0 silent skips; every chunk COMPLETE with its per-trace rows (`differential-p12-<start>.rows.jsonl.gz`, digests in the manifest). One product tree for all ten: `84014c980e75f3924c2d5a834f58d6b91e64bd47` = PHASE12_KERNEL_DIGEST (git faf3ecd95f7f, `phase12/PHASE12-KERNEL-IDENTITY.json`); one comparator `f8f3a954bc20…`, one model `983dc3bb479f…`; no chunk ran with a dirty `aisef/`. Runtime 6.74 h over 8 workers (4.12 traces/s); per chunk 00000: 2560 s, 10000: 2437 s, 20000: 2410 s, 30000: 2518 s, 40000: 2619 s, 50000: 2492 s, 60000: 2482 s, 70000: 2417 s, 80000: 2143 s, 90000: 2176 s.

**Manifest hard requirements** (`phase12/PHASE12-DATASET-MANIFEST.json`, computed): effective_traces_100000 = True; kernel_digests_exactly_one = True; kernel_digest_equals_PHASE12_KERNEL_DIGEST = True; model_and_comparator_digests_exactly_one = True; model_and_comparator_equal_identity = True; unexplained_mismatches_0 = True; invariant_violations_0 = True; exceptions_0 = True; missing_seed_ranges_0 = True; overlapping_seed_ranges_0 = True; silent_skips_0 = True; every_chunk_complete_with_rows = True; no_dirty_product_tree = True. Pass = True.

**Coverage, not just count** (`phase12/integrity.json`): reachable transitions hit 26/26; typed outcomes hit 10 (AUTH_FAILURE, ENVIRONMENT_FAILURE, HUMAN_REQUIRED, INFRA_FAILURE, ISOLATION_BREACH, NOOP, PASS, PLAN_CONFLICT, QUALITY_BLOCK, UNRUNNABLE); model event kinds 31; scenario fault kinds 28/28; compound faults: 92,789 traces with ≥ 2 distinct fault kinds, 378/378 fault-kind pairs hit; terminal classes ['blocked', 'done', 'failed', 'human'] (model) = ['blocked', 'done', 'failed', 'human'] (kernel). First seed per reachable transition: T3 0 (×60,960), T5 0 (×96,486), T6 1 (×18,851), T7 13 (×6,437), T8 7 (×7,448), T9 0 (×36,432), T10 72 (×4,055), T11 87 (×2,027), T12 1 (×14,689), T13 0 (×117,612), T15 0 (×112,845), T16 2 (×11,109), T17 0 (×66,998), T18 2 (×28,284), T19 8 (×4,194), T20 0 (×37,525), T21 5 (×9,897), T22 0 (×102,305), T23 7 (×23,566), T24 0 (×34,395), T25 0 (×60,960), T26 0 (×46,217), T27 6 (×8,680), T28 2 (×5,911), T29 0 (×34,395), T6' 30 (×858).

Saturation by 10k: after 10,000: 26 transitions; after 20,000: 26 transitions; after 30,000: 26 transitions; after 40,000: 26 transitions; after 50,000: 26 transitions; after 60,000: 26 transitions; after 70,000: 26 transitions; after 80,000: 26 transitions; after 90,000: 26 transitions; after 100,000: 26 transitions. Every reachable transition is first seen inside the first chunk; no transition appears for the first time after 10 000 seeds — the random set is saturated and the count was not inflated beyond 100k.

**Unreachable in this single-story differential, each with its deterministic cover** (T1–T34 + T6′ = 35 rows): T1 — claim by a live process — run loop (tests/test_run.py, test_state.py TestLeaseEdges); T2 — reclaim of an orphaned claim — reconcile (tests/test_dogfood_ledgerlock.py, scan8a TestSS49); T4 — unattributed out-of-scope dirt blocks — hygiene (tests/hardening/test_ownership.py, scan8a TestSS37); T14 — pre-staged out-of-scope paths at freeze — tests/test_implement.py (freeze) / scan8a TestSS15; T30 — merge conflict — the synthetic merge never conflicts; tests/test_worktree.py (merge conflict), tests/test_run.py; T31 — process death — crash recovery (tests/test_crash_recovery.py, compound CF-05); T32 — contract change — epoch (tests/test_worktree.py TestNhanhCuKhiTieuChiDoi, compound CF-13); T33 — owner arbitration — compound CF-13 / test_approvals TestCascade; T34 — run end commit + worktree removal — tests/test_run.py.

**Superseded runs.** The first chain (chunks 00000–50000 complete, 60000 killed) is retained under `phase12/superseded/` marked SUPERSEDED_NOT_QUALIFICATION_EVIDENCE: it ran against up to three kernel states and recorded no digests; diagnostically it matched 59 999/60 000 with the one mismatch being SS-64 (seed 34999), resolved in f0cd772 and closed with 11/11 measured requirements (`phase12/SS-64-CLOSURE.json`: reproducers RED on the pre-fix kernel and GREEN after, 10/10 deterministic replays, INV-G.5 PROVEN, F2 sibling scan clean, FM-R-09 GREEN, Linux + Windows CI green, no conformance deviation). The targeted affected-seed analysis (4267 seeds) stays diagnostic; it is not qualification evidence.

**Regression and lint on the closing tree.** Full suite: 3428 passed, 20 skipped, 1444 subtests (523 s); `ruff check .` clean; `KNOWN_DEVIATIONS` = [] (empty). Watchdog: the first armed instance of the rewritten watchdog died silently with signal 16 after ~3 h while the chain kept running; the chain itself never stalled and completion is established by the ten chunk records, not by the watchdog; a heartbeat was added so a silent death is distinguishable from a quiet watch (2e416e9). CI on the closing commit: recorded in the W0 qualification record.

Phase 12 passes on every owner condition: 0 unexplained traces, 0 unexplained differential mismatches, 0 invariant violations, complete required transition coverage; KNOWN_DEVIATIONS empty. Generated 2026-09-17T13:32:36+0700 from the JSON records above.
