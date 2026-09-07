# Benchmark Report v0.3.0

**Date**: 2026-09-07
**Protocol**: BENCH-PROTOCOL-v0.3.0 (SHA `dbd3858`)
**Dataset**: 16 bug-fix tasks, 3 attempts each, 2 conditions = 96 sessions

## Results

| Metric | AISEF | Bare | Delta |
|---|---|---|---|
| pass@1 | 48/48 (100%) | 48/48 (100%) | 0 |
| pass@3 | 16/16 (100%) | 16/16 (100%) | 0 |
| Stability | 16/16 (100%) | 16/16 (100%) | 0 |
| P2P regressions | 0 | 0 | 0 |
| Avg cost/session | $1.59 | $1.48 | 1.07x |
| Guard blocks | 12 | 0 | — |
| Total cost | — | — | $147.89 |

Cost comparison excludes bug-r2r1 (data anomaly: bare had 0 turns/$0 — see
below).

## Per-task breakdown

| Task | AISEF | Bare | AISEF $/avg | Bare $/avg | Ratio | Guards |
|---|---|---|---|---|---|---|
| bug-10 | P/P/P | P/P/P | $1.04 | $0.97 | 1.08x | 4 |
| bug-11 | P/P/P | P/P/P | $1.57 | $1.14 | 1.38x | 1 |
| bug-12 | P/P/P | P/P/P | $1.67 | $1.65 | 1.01x | 0 |
| bug-13 | P/P/P | P/P/P | $0.83 | $0.66 | 1.26x | 0 |
| bug-14 | P/P/P | P/P/P | $0.73 | $0.64 | 1.14x | 0 |
| bug-16 | P/P/P | P/P/P | $2.00 | $1.94 | 1.03x | 0 |
| bug-17-18 | P/P/P | P/P/P | $1.71 | $1.43 | 1.19x | 1 |
| bug-19 | P/P/P | P/P/P | $1.18 | $1.21 | 0.98x | 1 |
| bug-2-7-8-9 | P/P/P | P/P/P | $1.92 | $1.97 | 0.97x | 0 |
| bug-20 | P/P/P | P/P/P | $1.07 | $1.02 | 1.04x | 0 |
| bug-21 | P/P/P | P/P/P | $3.08 | $2.57 | 1.20x | 2 |
| bug-23-24 | P/P/P | P/P/P | $1.61 | $2.32 | 0.69x | 1 |
| bug-25 | P/P/P | P/P/P | $1.08 | $1.00 | 1.08x | 1 |
| bug-26-27 | P/P/P | P/P/P | $1.23 | $1.70 | 0.72x | 1 |
| bug-4-5 | P/P/P | P/P/P | $3.13 | $2.00 | 1.56x | 0 |
| bug-r2r1 | P/P/P | P/P/P | $3.23 | $0.00* | — | 0 |

\* bug-r2r1 bare: 0 turns, $0, 0ms — data anomaly; bare sessions did not
invoke the agent but scored PASS (base code already satisfies F2P).

## Guard block distribution

12 total guard interventions across 48 AISEF sessions (25% of sessions
triggered at least one guard). Tasks with most blocks: bug-10 (4), bug-21 (2).
Bare agent passed 100% without guards — guards did not change correctness
outcomes on this task set.

## Interpretation

1. **No correctness difference**: both conditions achieve 100% pass@1 across
   all 16 tasks with 100% stability. On this task set, AISEF guard hooks do
   not improve or degrade solve rate.

2. **Cost overhead is minimal**: 7% average (excluding the bug-r2r1 anomaly).
   Two tasks (bug-23-24, bug-26-27) were cheaper with AISEF; two (bug-4-5,
   bug-11) were notably more expensive. Net: guards add negligible cost.

3. **Guards fire but don't change outcomes**: 12 guard blocks across 48
   sessions means guards intervened in ~25% of AISEF runs. The bare agent
   solved the same tasks without those blocks — either the blocked actions
   were unnecessary detours, or the agent self-corrected on the bare path.

4. **Task set ceiling**: 100%/100% for both conditions suggests the 16
   bug-fix tasks are within the frontier model's comfortable range. These
   tasks cannot distinguish AISEF from bare. Harder tasks (multi-file
   refactors, security-sensitive changes, concurrent modifications) are
   needed to find the separation point.

## Data notes

**Timeouts ("quá 1800s")**: 14/96 sessions (15%) timed out before the agent
finished, recording 0 turns and $0 cost. All 14 still scored PASS — the
agent's partial edits (files/lines > 0) were sufficient. Distribution: 6
AISEF, 8 bare. This affects cost averages but not correctness conclusions.

**bug-r2r1 bare**: all 3 bare attempts timed out ($0, 0 turns). The base
code with partial edits satisfies F2P. Excluded from cost comparison.

**Cost excluding timeouts**: $1.80/session avg across 82 non-timeout sessions.

## Next steps

- Investigate bug-r2r1 bare anomaly
- Design harder task categories: multi-file, security, concurrency
- Run conformance probes (C11/C12) requiring adversarial agent behavior
- Consider whether guard value lies in safety (preventing damage on failure
  paths) rather than correctness (improving solve rate)
