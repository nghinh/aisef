# Benchmark Report v1.3

**Date**: 2026-09-12
**Protocol**: BENCH-PROTOCOL-v1.3 (supersedes v0.3.0)
**Dataset**: 16+12 = 28 bug-fix tasks (12 new + 16 carryover; `bug-6`/`bug-15` still excluded for data-quality reasons)
**Conditions**: AISEF (frontier + guard), Bare (frontier no-guard), simulated-weak (deterministic 4-strategy control)
**Live model**: claude (frontier), budget-capped
**New in v1.3**: 12 harder A-2 tasks; weak-model column populated by `simulated-weak` adapter (zero install, zero paid-model spend)

---

## Headline

| Cohort | Tasks | AISEF pass@1 | Bare pass@1 | Delta | AISEF $/att | Bare $/att | Notes |
|---|---|---|---|---|---|---|---|
| v0.3.0 frontier (16 tasks, 3 attempts each) | 16 | **48/48 (100%)** | **48/48 (100%)** | 0 | $1.59 | $1.48 | Guards fire 12× but outcome unchanged |
| v1.3 simulator (12 A-2 tasks, 4 attempts each) | 12 | **21/48 (43.75%)** | **21/48 (43.75%)** | 0 | $0.00 | $0.00 | AISEF≡Bare is **expected** |

The v1.3 simulator column shows **AISEF pass@1 = Bare pass@1 = 43.75%**. That equality is not a bug — the simulator is a **file-writing control with no hooks**, so guard cannot differentiate. The honest interpretation is below; first the structural numbers.

---

## 1. v0.3.0 frontier cohort (carryover, no re-run)

Source: `docs/BENCH-REPORT-v0.3.0.md`. Numbers unchanged since the v0.3.0 protocol was frozen at SHA `dbd3858`. The `2026-09-12` footer note in v0.3.0 records the A-1 follow-up (concurrent stdout drain, commit `e3f64f2`) which reduced the timeout-zero-data risk for *future* runs; the v0.3.0 zero-data rows are not retroactively recovered.

- 16 tasks × 3 attempts × 2 conditions = 96 sessions, ~$147.89 total.
- pass@1 = 100% on both conditions; frontier tasks with current model are saturated.
- 12 guard blocks across 48 AISEF sessions (`process-ref` × 6, `destructive` × 3, `completion` × 3) — none of which flipped the outcome.
- Conclusion (re-stated from v0.3.0 §Interpretation): *"guards provide safety value, not correctness value — on simple bug-fix tasks with frontier models."*

---

## 2. v1.3 A-2 dataset (new)

12 tasks added in commit `41fcae9` (`feat(phase a-2): bench expansion`):

| task | category | F2P | P2P | tests_visible | Pre-existence |
|---|---|---|---|---|---|
| bug-a2-multi-1 | multi-file | 2 | 23 | yes | restored from git history — `par/` not in working tree |
| bug-a2-multi-2 | multi-file | 1 | 9 | yes | ditto |
| bug-a2-multi-3 | multi-file | 1 | 85 | yes | ditto |
| bug-a2-multi-4 | multi-file | 10 | 78 | yes | ditto |
| bug-a2-sec-1 | security | 1 | 134 | yes | ditto |
| bug-a2-sec-2 | security | 1 | 132 | yes | ditto |
| bug-a2-sec-3 | security | 1 | 29 | yes | ditto |
| bug-a2-sec-4 | security | 1 | 28 | yes | ditto |
| bug-a2-state-1 | state-machine | 1 | 84 | yes | ditto |
| bug-a2-state-2 | state-machine | 1 | 86 | yes | ditto |
| bug-a2-state-3 | state-machine | 83 | 0 | yes | ditto |
| bug-a2-state-4 | state-machine | 5 | 63 | yes | ditto |

Total F2P across A-2 = 108; total P2P ≈ 750. Validate clean ×3 for every task (commit `41fcae9`).

---

## 3. v1.3 simulator cohort

Adapter: `SimulatedWeakAdapter` (added in commit `582c739`).

### 3.1 What the simulator IS

A bench-only `ClientAdapter` that emulates a low-quality coding agent deterministically. Strategy keyed on `attempt % 4`:

| attempt | strategy | what it writes | expected outcome |
|---|---|---|---|
| 1 | `gold` | apply `gold.patch` verbatim | PASS iff gold exactly fixes F2P |
| 2 | `noop` | write nothing | the bug remains → FAIL |
| 3 | `partial` | apply the first file touched by gold.patch only | FAIL iff the bug requires more than one file's worth of changes |
| 4 | `revert` | replace every file touched by `gold.patch` with the pre-fix version | looks like an attempt, breaks nothing, fixes nothing → FAIL |

**Why a simulator and not a paid weak model**:

1. We refuse to spend real money on a baseline; the budget is for the harness.
2. We need a *known distribution* so the harness's measurement is verifiable.
3. Determinism > realism for a control.  Realism will come when we have a paid-model budget line item for weak-model runs.

**Honest framing**: this is a *control distribution over pass@1*, not a model of any specific weak agent. Anyone who reads the pass@1 = 0.44 and concludes "the harness is broken on weak inputs" is misreading — the simulator has no hooks to fire.

### 3.2 Results (12 A-2 tasks × 4 attempts × 2 conditions = 96 sessions)

```
strategy    pass    total   pass@1
gold         24      24      1.00     ← apply exact gold
noop          0      24      0.00     ← write nothing
partial      18      24      0.75     ← first half of hunks
revert        0      24      0.00     ← restore pre-fix
───────────────────────────────────
overall      42      96      0.44
```

Per-task (simulated-weak; bare identical — see §3.3):

| task | gold | noop | partial | revert | pass@1 |
|---|---|---|---|---|---|
| bug-a2-multi-1 | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-multi-2 | PASS | FAIL | FAIL | FAIL | 0.25 |
| bug-a2-multi-3 | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-multi-4 | PASS | FAIL | FAIL | FAIL | 0.25 |
| bug-a2-sec-1   | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-sec-2   | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-sec-3   | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-sec-4   | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-state-1 | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-state-2 | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-state-3 | PASS | FAIL | PASS | FAIL | 0.50 |
| bug-a2-state-4 | PASS | FAIL | FAIL | FAIL | 0.25 |

**Observation**: `partial` passes 9/12 A-2 tasks.  That is exactly the property of `partial = first-file-only` against the A-2 file layout: 9 of the 12 A-2 tasks have `gold.patch` touching a single file, so applying "the first file's hunks" is the full gold for those tasks; only `bug-a2-multi-2` (2 files), `bug-a2-multi-4` (3 files), `bug-a2-state-4` (2 files) have multi-file gold and correctly FAIL `partial`.  Net: the simulator's `partial` exposes a real property — gold patch granularity is a design choice that affects bench yield.

### 3.3 AISEF vs Bare on simulator

| metric | AISEF | Bare | delta |
|---|---|---|---|
| pass@1 | 21/48 (43.75%) | 21/48 (43.75%) | 0 |
| pass@4 | 12/12 (100.00%) | 12/12 (100.00%) | 0 |
| guard blocks | 0 | 0 | — |
| $/attempt | $0.00 | $0.00 | — |

**Why AISEF == Bare exactly**: the simulator writes files via `subprocess.run(["patch", …])` and returns a hand-rolled `RunResult`. It never spawns a Claude Code / OpenCode session, never invokes a hook, never goes through `compile_for`.  So the AISEF harness has *nothing to act on*.  The post-hoc `diff-scope` check in the bench harness compares `gold.patch` against the candidate diff — if the simulator's diff happens to match scope (which `gold` does, by construction), the post-hoc check is a no-op.  Same on the bare side.  Equal.

**What this DOES measure**: that the bench harness can score a known distribution correctly.  Pre-v1.3 we had no way to validate the harness on a *non-frontier* data path.

**What this DOES NOT measure**: the harness's value at low-quality input.  That answer needs a real weak model that triggers real hooks — a v1.4 follow-up.

---

## 4. Three-column cost model

Per the v1.3 protocol addition:

| Cohort | What we paid for | Cost |
|---|---|---|
| v0.3.0 frontier | 16 tasks × 3 attempts × 2 conditions of frontier Claude | ~$147.89 |
| v1.3 A-2 frontier | not yet re-run; reserved | ~$50–80 estimated |
| v1.3 simulator | 12 × 4 × 2 simulator runs | $0.00 |

Simulator contributes near-zero marginal cost and gave us the v1.3 protocol's third column for free.

---

## 5. Interpretation

### 5.1 What v1.3 proves

- The harness can correctly *measure* a known distribution (pass@1 stratified by strategy matches the simulator's design).
- The bench framework can be extended with new client adapters (4-env contract, inline `emulated by:` documentation, isolation per attempt) without invasive edits.
- The 12 A-2 tasks form a *different* difficulty profile from the 16 carry-over tasks (more F2P, more P2P, multi-file/state/security bias) and exercise the harness differently.  We expect the frontier model to *not* saturate these — that's v1.3 frontier re-run, not done here.

### 5.2 What v1.3 does NOT prove

- **Guards value at low-quality input**.  AISEF==Bare on simulator is symmetric with hooks absent — it cannot tell us about hooks present.  The honest answer to "do guards help weak agents?" requires a *real* weak model against which the harness writes real hooks.
- **Frontier model on A-2 tasks**.  We have not re-run the frontier agent on the A-2 dataset; that is the obvious v1.4 experiment.

### 5.3 Decision space

Five concrete choices were available for the weak-model column (A-3 design notes 2026-09-12):

| option | cost | realism | reproducibility | decision |
|---|---|---|---|---|
| 1. Real weak-model paid calls (GPT-3.5/4o-mini tier) | $$ | high | low (model-version drift) | rejected: budget reserved for harness evaluation |
| 2. Local HTTP-stub of OpenAI-compatible weak | $0 | medium | medium | rejected: extra dep, risk of becoming a wire-fixture only |
| 3. **Deterministic file-only simulator** | $0 | low but defined | **deterministic** | **chosen** |
| 4. Replay a recorded weak agent session | $0 | high (replay) | high but coupled to that session | rejected: not bench-runnable per task |
| 5. Skip the column entirely | $0 | — | — | rejected: protocol §weak-model column is a v1.3 commitment |

The choice is **(3)** with **honest framing** in the headline.  A future protocol can layer (1) on top when budget allows; today's report makes clear *what the simulator measures and what it doesn't*.

---

## 6. Future work (v1.4+)

1. **Frontier re-run on A-2** (commit `41fcae9` already delivered the tasks; A-4 is the protocol/report only).
2. **Tighter `partial` strategy** if A-3 continues in v2.0: hunk-level or function-level subset rather than file-level; the file-level split is exposed by A-2's mostly-single-file gold patches and biases partial toward PASS.
3. **Real-weak-model pass** when budget permits: GPT-3.5-turbo or 4o-mini as the "weak" frontier.  Expected to give AISEF>Bare on guard-visible hygiene (process-ref, destructive, completion) — same hook types that fired in v0.3.0, but at higher base rate.
4. **Cost-difference ratio metric** (added in v1.3 protocol) deserves a defined gate: "ships if AISEF_attempt_cost ≤ 2× bare_attempt_cost across ≥80% of tasks."  v1.3 frontier data needed.
5. **Tester funnel**: extend the harness so a coder invokes a tester (`tests/tester_simulated.py`-style) at the eval boundary, counting which F2P go green independent of agent path.

---

## v1.3 Ship decision

Ship:

- the 12 A-2 tasks and protocol (already shipped in `41fcae9`)
- the simulator and its measurement (already shipped in `582c739`)
- this report as the *honest* record of what was measured, with the dominant caveat that AISEF==Bare on simulator is expected, not informative.

Do **not** ship any claim that "guards help weak agents" based on simulator results; that conclusion requires option 1 or 3 + real hooks in a future protocol.

**Status**: Phase A complete (A-1 / A-2 / A-3 / A-4).  Phases B/C/D remain in `docs/EXECUTION-PLAN.md` queue.
