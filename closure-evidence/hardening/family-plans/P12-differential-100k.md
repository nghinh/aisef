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
