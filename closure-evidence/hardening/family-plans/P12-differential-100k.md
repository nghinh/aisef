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

## Re-run on the SS-65 kernel (owner decision "FIX SS-65 AT CAPABILITY-MODEL LEVEL AND RE-QUALIFY", item 12)

The SS-65 fix changes `aisef/` (tree `84014c98…` → `02a34e0e…`), so the dataset above is moved, unedited, to
`phase12/history-kernel-84014c98/` and marked VALID HISTORICAL EVIDENCE — NOT FINAL QUALIFICATION EVIDENCE. The full
100 000-trace set is re-run against the new product tree after Linux and Windows CI are green on it, with a new
PHASE12-KERNEL-IDENTITY recorded first; every chunk must carry that exact tree, and the consolidation lists both
earlier datasets under their markers.

**Execution mode (item 13): unchanged — sequential chunks, 8 workers each.** Measured on this host: 8 logical cores
(4 performance + 4 efficiency); one chunk already runs 8 worker processes plus their git and sandbox subprocesses
(load average 15–18 during the previous dataset). Running chunks concurrently cannot add throughput here and only adds
contention, and no deterministic test proves concurrent chunks safe (the comparator mutates module state per process,
chunks share the evidence directory). The known-safe mode is kept; expected wall clock ≈ 6 h 45.
