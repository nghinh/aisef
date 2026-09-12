# Bench Protocol v1.3

Frozen 2026-09-12, supersedes v0.3.0 once results land.

## Conditions

Same as v0.3.0:

| Condition | Guards | ENV AISEF_* | settings.json | Scoring |
|-----------|--------|-------------|---------------|---------|
| `claude` (AISEF) | compiled hooks (write-scope, destructive, secret, git-stage, injection, process-ref, diff-scope, completion) | yes | yes | hidden-test F2P/P2P |
| `claude-bare` (control) | none | none | none | hidden-test F2P/P2P (same scorer) |

Optional weak-model column in v1.3 (gate under `tests.bench.run --client
<weak>` once results land; protocol frozen once both columns are committed).

## Dataset

30 bug-fix tasks mined from repo history (`tests/bench/tasks/`):

- **18 v0.3.0 tasks** (`bug-2-7-8-9`, `bug-4-5`, …, `bug-r2r1`):
  16 valid, 2 excluded (bug-6 needs Docker, bug-15 has invalid gold).
  Single-file fixes, 1–3 regression tests each.  Sample: simple bug-fix,
  obvious root cause from symptom.

- **12 v1.3 tasks** (`bug-a2-multi-*`, `bug-a2-state-*`, `bug-a2-sec-*`):
  all 12 valid, F2P=108 / P2P=750+ test coverage.  Distribution:
  - 4 multi-file refactor (`multi-1..4`): log parser, runlog, gate
    state, parallel-run state — 5+ src files each.
  - 4 state / concurrency (`state-1..4`): attempt-counting, no-op
    guard, interrupted state, gate pre-condition logic — 4–5 src files
    each.
  - 4 reviewer / scope / security (`sec-1..4`): MCP scope,
    guard-message contents, self-review exception, reviewer scope —
    4–6 src files each.

  Each v1.3 fix touches an average of 4.5 source modules; the
  previous v0.3.0 average was 1.4.  Tasks that fail P2P validation
  (gold does not make all surviving tests pass) are excluded.

Each task: base SHA (before fix), tests.patch (regression tests),
gold.patch (fix), prompt (symptom only, no answer).  Prompt lint: no
SHA, no fix commit name, no URL.

## Scorer

Same as v0.3.0 (`_runner._grade()`):

1. Revert any test files the agent touched
2. Apply hidden `tests.patch`
3. Commit candidate
4. Run `tools.test` at candidate SHA
5. Grade by F2P test names (fail-to-pass) and P2P stability
   (pass-to-pass)

PASS = all F2P green AND no P2P regressions.

## Runs

- 3 attempts per task per condition (v0.3.0 baseline)
- Interleaved per task: AISEF 3× then bare 3×, task order shuffled
- Weak-model column (v1.3): one attempt per task per condition with
  `--client opencode-gpt4-mini` (or equivalent); single run, not power-
  tested
- `pass@1` = fraction of attempts that PASS
- `pass@3` = 1 if any attempt PASS, 0 otherwise
- Stability = all 3 attempts same outcome

## Metrics

Same six as v0.3.0, plus:

7. **Weak-model pass@1** (v1.3 only): same scoring on a non-frontier
   model; documents whether the harness's value survives a quality drop
8. **Cost-difference ratio** = (AISEF cost − bare cost) / bare cost:
   the 7 % overhead reported in v0.3.0 is held as the baseline; v1.3
   re-runs the same metric on harder tasks so any change can be read
   against it

## Integrity

- Protocol SHA: `<filled at freeze>`
- Tasks committed and validated before any run
- No task or verifier modification after seeing results
- If forced to fix: invalidate + rerun both conditions for affected
  tasks

## Why harder tasks

v0.3.0 reported 100 % pass@1 for the 16 simple tasks on both AISEF and
bare; the 7 % AISEF cost overhead was the only signal that the harness
adds anything.  v1.3 doubles the dataset to 30 tasks, half of which
require the agent to reason across more than one module, before any
column is run.  A null result on v1.3 ("AISEF and bare both score
100 %") would be a more meaningful null than the v0.3.0 result because
the floor of difficulty is higher.
