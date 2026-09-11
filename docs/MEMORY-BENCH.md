# Paired A/B/C memory benchmark — methodology, datasets, arms, interpretation

This document covers the paired-fresh-agent harness that backs the question
"should memory be on by default?" It is the implementation companion of
ADR-008; all numbers in this repository come from the **scripted
deterministic** agent, not from a real paid model call.

## 1. Methodology

The harness lives under `framework/bench/memory_compare/` and is a sibling of
`aisef.memory_bench`. The relationship is:

- `aisef.memory_bench.run()` answers "what can the local store retrieve,
  deterministically?" It is purely retrieval-only and proves nothing about
  an agent's behaviour.
- This harness answers "given three different memory postures, what does
  the same scripted agent do across N attempts of each scenario?" It is
  a paired A/B/C test whose primary metric is repeated_error_rate.

The harness is **offline by design** and **does not call a real client**.
Production of causal evidence about memory benefit requires the deferred
real-agent trials (P2 of `MEMORY-RESEARCH-PLAN.md`).

### Locked framework candidate

`framework/bench/memory_compare/lock.json` pins four invariants of every
run that calls `run_arm` / `run_all`:

1. `candidate_sha` — `git rev-parse HEAD` at lock authoring. Subsequent
   runs refuse to start unless `AISEF_MEMORY_BENCH_FORCE=1` is set.
   Memory is benchmarked against *this* candidate.
2. `effective_config_snapshot` — names of the memory-related `aisef.config`
   keys with their default values. Renames, default flips or range changes
   invalidate the comparison.
3. `toggle_signature` — derived from the union of provider/toggle names.
   A flip in `AISEF_MEMORY_ARMS` voids the comparison.
4. `signature` — aggregate over the three above plus the lock schema
   version, embedded in every per-arm result JSON.

To refresh after an intentional harness change:

```sh
python3 -m framework.bench.memory_compare --write-lock
```

To refuse run when HEAD has moved:

```sh
python3 -m framework.bench.memory_compare --check-lock
```

## 2. Arms

| arm | behaviour | matchable on |
|---|---|---|
| **A** memory off | scripted agent replays the scripted `scripted_outcomes` of each fixture without consulting any store. | writes exactly `0` chars injected, latency 0.0 ms. |
| **B** memory on, local | scripted agent queries `LocalMemory.recall` against a fixture-derived store and emits decisions consistent with the recall packet. | `chars_injected > 0`, `latency_ms > 0`, ``provider == "local"``. |
| **C** memory on, OpenViking | **never silently downgraded**. The harness raises `ArmUnavailable` and records `outcome="UNAVAILABLE"` for every attempt. `by_arm["C"]` therefore carries `status="unavailable"` and `unavailable=N`. | no model call, no fake local fallback, honest refusal. |

Per-arm budgets:

- cost cap 5.0 USD
- turns cap 20
- time cap 120.0 s
- calls cap 10

A budget exhaustion produces `outcome="BUDGET"` on the affected attempt;
the rest of the per-scenario attempts also stop rather than fabricate
missing numbers. The runner never imputes metrics.

## 3. Scenario set

The parent directive requires:

- existing dogfood reproducible tasks: `tests/dogfood/test_par.py`,
  `tests/dogfood/test_calc.py`, `tests/dogfood/test_par_mutation.py`.
  These stay unchanged. The harness does **not** call them: it ships a
  shape-compatible fixture (`SCENARIOS → DOGFOOD_TRIPLES`) and a scripted
  replay of one attempt per `STORY-01-0x`. Real `claude`/`opencode` runs
  remain opt-in under `AISEF_DOGFOOD=1`.
- four required long-horizon scripted micro-stories covering the named
  behaviour classes. The directive names six behaviour classes
  (convention carry-over, failure pattern repeat, reviewer recurrence,
  security recurrence, supersede authority, tool-env repeat), so the
  harness registers **six** long-horizon scenarios, one per class:
  `framework/bench/memory_compare/scenarios.py::_scenario_definitions`.

Each scenario's `fixture` is hand-authored deterministic JSON. The
scripted agent replays its `scripted_outcomes` block in attempt order. A
real agent would have to fail or succeed on the same tasks; here we emit
either a `repeated_error_id` matching the scenario's
`expected_repeated_behavior_id` (failure) or `None` (success).

## 4. Primary metric and justification

**Primary**: `repeated_error_rate` — fraction of attempts where
`repeated_error_id` equals the scenario's `expected_repeated_behavior_id`.

Justification: the parent directive names "repeated error" as the single
behaviour class that the harness is meant to bound. Memory's claim to
default-on is "without memory an agent makes the same mistake N times;
with memory it doesn't". The metric captures exactly that pair across
both arms A and B, in the same scenario, with the same scripted agent
otherwise.

**Secondaries**:

- `pass@1` — fraction of attempts that PASS. Memory should not regress
  working baselines.
- `useful_memory_precision` — fraction of *selected* memory records that
  appear in the manually labelled positive set
  (`framework/bench/memory_compare/fixtures/useful_memory_positives.json`).
- `wrong_memory_rate` — complement of precision in the selected set.
- `stale_memory_rate` — fraction of selected records whose `consolidate`
  output marks them stale.
- `harm_rate` — fraction of attempts where the `verifier_findings` list
  contains a `reviewer_independence`-flagged entry. Currently 0 in the
  scripted harness; the structural guard is what binds this in
  `aisef/memory.py::_validate`.
- `average_turns`, `average_latency_ms`, `chars_injected`,
  `budget_used_usd` — operational telemetry, not gating criteria.

**Why not causal efficacy?**

The scripted harness has the same scripted `scripted_outcomes` block
under both arms in the absence of a real LLM and a real agent loop. It
cannot establish whether memory *causes* improvements; it can only show
that the runner and scorer are wired correctly and that B does not
inject worse records than A in the same scenario.

## 5. Reproducibility

```sh
python3 -m framework.bench.memory_compare run --attempts 3
python3 -m framework.bench.memory_compare score
cat framework/bench/memory_compare/results/score.md
```

Same lock, same fixtures, same `--attempts` → same `score.json` modulo
`average_latency_ms` and `run_started_at` (timer-only fields). That is
intentional: the harness is reproducible *as a deterministic pipeline*,
not as a wall-clock measurement.

There is **no requirement for credentials, network, or a paid model**.
If you have credentials and want to graduate from scripted to real agent
runs, do so under controlled experimental conditions per
`docs/MEMORY-RESEARCH-PLAN.md` § P2 — that is the next phase, not this
one.

## 6. Limitations — read me before citing numbers

1. **Scripted, not causal.** The agent never consults a real LLM. It is
   a deterministic decision replay built on top of the real local memory
   store (`aisef/memory.py::LocalMemory`). The primary metric is what a
   the-store-operates-correctly check produces; it is not what a real
   agent does. Causal claims require P2 paired real-agent trials.
2. **Off-policy scoring.** The scoring function operates on per-arm JSON
   files written by `runner.py`; we never reach inside a journal or an
   evidence stream to re-derive outcomes. If the runner has a bug that
   writes incorrect JSON, the score inherits the bug. The dedicated
   regression tests in
   `framework/bench/memory_compare/tests/test_memory_bench.py` exercise
   the runner/scoring paths offline.
3. **Latency is local selection, not end-to-end.** The harness measures
   `LocalMemory.recall`'s selection latency in the temp project root;
   end-to-end CLI latency, real network latency, and model latency are
   not exercised.
4. **Offline-only scoring.** The script does not consult a remote
   OpenViking adapter. The "C" arm is a synchronous refusal. To advance
   C from "unavailable" to a real arm requires the deferred adapter
   (`MEMORY-RESEARCH-PLAN.md` § P2 / R2 of `MEMORY-VALIDATION.md`).
5. **Positive memory set is committed to disk.** The manually labelled
   `fixtures/useful_memory_positives.json` is small and verified by
   hand against the scenario's `memory_records`. Future labellers must
   re-validate before adding new scenarios.
6. **Per-scenario deterministic, not ensemble.** A single fixture per
   scenario class. The harness does not randomise story order or seed;
   that belongs to the deferred real-agent trial.
7. **Budget exhaustion is not stitched across arms.** Each arm runs its
   own budget; exhaustion in arm B does not pretend arm A also exhausted.
8. **No real model call.** The C arm reports ``status='unavailable'``
   and produces no fabricated numbers. If you have credentials you
   trust, integrate them under the gated
   `MEMORY-RESEARCH-PLAN.md` P2 protocol; the harness itself stays
   offline.
9. **Suite not full.** Three arm-internal regressions are covered. The
   full AISEF test suite (2000+ tests) gates this phase too; see the
   full-unittest run log in the PR description.

## 7. What would warrant default-on?

- A future non-scripted trial passes the `B-A_repeated_error_rate < 0`
  bar with statistical power over multiple seeds **without** raising
  `B-A_harm_rate`, `B-A_pass@1`, or any reviewer-independence regression.
- A contract-tested OpenViking adapter (deletion, metadata filtering,
  timeout, schema and failure handling) plus explicit remote opt-in.
- Human-approved cross-project/global memory with a separate promotion
  workflow (not automation).
- An external security audit (not the self-audit captured in
  `MEMORY-VALIDATION.md`).

Until these exist, the harness confirms the harness, not the agent.
This document intentionally does not flip `memory.enabled` to `true`.
