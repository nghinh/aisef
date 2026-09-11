# ADR-008 — Paired A/B/C memory harness scope (addendum to ADR-007)

Date: 2026-09-11. Status: **experimental OFF, harness shipped**. The
parent directive for Phase 1 was: build a paired fresh-agent benchmark
that **measures** the proposed benefit of memory, without enabling memory
itself. This addendum records how the harness answers the question "should
memory be on by default?" without going causal.

## Decision

Adopt a paired A/B/C harness (`framework/bench/memory_compare/`) that:

- measures scripted-simulated behaviour, not real-agent efficacy;
- locks the framework candidate SHA, the effective config hash and the
  per-arm toggle signature into a single lock file;
- runs three arms (A: memory off, B: local, C: OpenViking) against a
  committed fixture set;
- uses local scripted-replay agents under fixture-only runs, never a
  paid model client, unless explicitly authorized later;
- reports a primary metric (`repeated_error_rate`) plus secondaries
  (`pass@1`, `useful_memory_precision`, `wrong_memory_rate`,
  `stale_memory_rate`, `harm_rate`, plus latency / turns / chars / cost);
- refuses C with explicit `status='unavailable'`, never silently
  downgrades to B.

The companion `aisef.memory_bench` remains the deterministic retrieval
fixture. It is **not** modified; this harness is a sibling that operates
against scenario fixtures and produces paired-arm scores.

## How this answers "should memory be on by default?"

The harness is a paired trial scaffold, not an efficacy proof. It
answers two practical questions before any causal claim is allowed:

1. **Is the harness wired correctly?** The scripted agent under B calls
   `LocalMemory.recall` and emits decisions consistent with the recall
   packet; under A it never does. The regression tests under
   `framework/bench/memory_compare/tests/test_memory_bench.py` exercise
   both paths and the budget caps.
2. **What would the *scripted* ceiling be?** Under the scripted
   `scripted_outcomes` block, B matches A on `pass@1` and
   `repeated_error_rate` while injecting useful records
   (`useful_memory_precision ≈ 0.9` against the labelled positive set).
   This is what a deterministic fixture says — not what a real agent
   would say. It establishes a *floor*, not a ceiling.

Causal efficacy still requires the deferred real-agent trials
(`MEMORY-RESEARCH-PLAN.md` § P2): paired fresh-agent sessions, randomized
order, adjudicated repeated errors, multiple seeds. Those are *not* part
of this harness or this phase.

## What this does NOT justify

- Flipping `memory.enabled` to `true`. The harness is a reproduction
  scaffold; it does not produce causal evidence. Default-on is the
  decision of a future phase against P2 evidence.
- Opening a remote OpenViking adapter. C remains an explicit refusal.
  A real adapter is P2 per `MEMORY-RESEARCH-PLAN.md`.
- Removing or weakening gate / evidence / reviewer-independence. The
  `harm_rate` field is wired so any reviewer/security injection
  attempts land in `verifier_findings`. The structural guard remains
  the source of truth — this harness only measures, never weakens.
- Touching the existing dogfood tests
  (`tests/dogfood/test_{par,calc,par_mutation}.py`). The harness ships
  shape-compatible fixtures and explicitly states "must NOT modify
  existing dogfood tests." Reproducing real `claude`/`opencode` numbers
  remains an opt-in real-agent run under `AISEF_DOGFOOD=1`.

## Implementation references (linking forward, not rewriting)

- Harness code: `framework/bench/memory_compare/__init__.py`,
  `.../runner.py`, `.../scoring.py`, `.../scenarios.py`, `.../llm_stub.py`,
  `.../lock.py`, `.../__main__.py`. Lock file: `.../lock.json`. Tests:
  `.../tests/test_memory_bench.py`.
- Companion retrieval benchmark: `aisef/memory_bench.py` (untouched).
- Methodology, reproducibility, limitations:
  `docs/MEMORY-BENCH.md`.
- Plan / status: `docs/MEMORY-RESEARCH-PLAN.md` § P1 / P2,
  `docs/MEMORY-VALIDATION.md`.
- Prior decision this extends: `docs/ADR-007-scoped-advisory-memory.md`.

## Consequence

The harness delivers a deterministic, offline, lockable paired
A/B/C scaffold. Until P2 trials close the causal gap, `memory.enabled`
remains `false` and every metric in `results/score.{md,json}` carries
`"methodology": "scripted simulated agent, NOT causal real-agent
efficacy"`. The lock file is the single source of truth for what
counts as the same framework candidate across runs.
