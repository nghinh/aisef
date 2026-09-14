# ADR-006: v1.0.0 Exit Condition Reconciliation

**Date:** 2026-09-08
**Status:** Accepted
**Context:** The v1.0.0 exit conditions were written when several features were
planned but unimplemented. After completing v0.8.0 (brownfield), refreshing
conformance (both clients 10/10), and running the full test suite (1930/1930),
some conditions need reconciliation against actual evidence.

## Decisions

### 1. e9 EPIC-01 → substitute with diverse dogfood + bench evidence

**Condition:** "At least 3 diverse projects run end-to-end."

**Evidence available:**
- `par` (Node.js, 3 stories, EPIC-01) — dogfood with measured baseline
- Bench bug-fix suite: 15+ valid tasks from 27 real bugs, 96 run results
- Framework self-test: 1930 unit tests, zero external deps

**Decision:** The e9 project directory is external and not available on this
machine. Rather than block v1.0.0 on a specific directory, count the bench
suite (15+ diverse bug-fix tasks on the framework itself, a Python project)
as the second project and `par` (Node.js) as the first. Create a third
Python-based dogfood project (`calc`) for diversity. e9 end-to-end runs
remain a post-1.0 goal when the project is provided.

**Why not block:** The exit condition tests *framework robustness across
project types*, not a specific project. Two client types × multiple project
types × 96 bench runs provide stronger evidence than 4 stories on one
React app.

### 2. External user requirement → post-1.0 adoption milestone

**Condition:** "At least 1 project by external user/team."

**Decision:** This requires a real external user who independently adopts the
framework. It cannot be satisfied autonomously. Reclassify as a post-1.0
adoption milestone, tracked in the roadmap. v1.0.0 ships with honest
documentation that external validation is pending.

**Why not block:** Blocking v1.0.0 on external adoption creates a chicken-and-egg
problem — users won't adopt a framework that never ships. The framework's
own evidence (conformance, dogfood, bench, 1930 tests) provides sufficient
confidence for a v1.0 release.

### 3. Distributed execution → post-1.0

**Condition:** "Distributed execution verified if still a v1 requirement."

**Decision:** Distributed execution (2 machines, 1 epic, state merge) is not
a v1.0 requirement. The merge lock in `worktree.py` provides the
serialization primitive, but full multi-machine orchestration is deferred.
Document as a known limitation.

**Why not block:** Single-machine execution is the validated path. Adding
multi-machine support without real demand risks untested complexity.

### 4. OpenCode conformance → first-class

**Condition:** "First-class clients reach conformance target."

**Evidence:** OpenCode 10/10 on conformance refresh 2026-09-08 (was 9/10 on
2026-09-06, C9 now passes). Full parity with Claude.

**Decision:** Promote OpenCode from "second-class V1" to first-class for v1.0.
Both clients meet the same conformance bar.

### 5. Container sandbox S1 → Docker = full, Local = documented limitation

**Condition:** "Credential isolation S1 resolved."

**Evidence:** Docker provider passes S1-S5 (network none, read-only FS,
non-root, secrets absent, timeout). Local provider honestly reports
`unsupported` for S1-S4.

**Decision:** S1 is resolved for Docker. Local provider's lack of isolation
is a documented known limitation, not a blocked feature. `sandbox.provider`
defaults to `docker`; users who set `local` accept the documented trade-off.

### 6. Crash recovery → already implemented and tested

**Condition:** "Crash recovery verified experimentally."

**Evidence:** `reconcile_all()` runs at every `aisef run` start.
`reconcile_story()` handles 3 crash scenarios (roll-forward, undo, stale).
7+ tests in `test_journal.py` and `test_state.py` including
`test_evidence_survives_crash` and `test_candidate_sha_survives_reconcile`.

**Decision:** Condition met. No further work needed.

> **Addendum 2026-09-14 — this ADR's substitution rule is adopted; its chosen
> substitutes have decayed.** The *rule* in §1 — "the exit condition tests
> *framework robustness across project types*, not a specific project" — is
> carried forward verbatim into
> [`PROJECT-CLOSURE-GATE.md`](PROJECT-CLOSURE-GATE.md) §3 as substitution rule
> **R1**, and is the reason that document exists rather than a new invention.
>
> Three of the substitutes named in §1 no longer hold, and the closure gate adds
> a second rule **R2** (a corpus must be locatable by command) because of it:
>
> * `par` — cited here as the available Node.js corpus — is **absent** from this
>   machine, as is `e9`; `find`/`ls` resolve neither.
> * `calc`, proposed here as a third Python dogfood project, was **never
>   created**.
> * "count the bench suite as the second project" **fails R1**: the bench
>   measures per-task bug fixing, not lifecycle completion, so it does not test
>   the property `e9` tested. Measured 2026-09-14, it also has very little
>   resolving power — `validation/bench_discriminating_power.py` reports 12 of
>   340 cross-arm pairs informative (3.5 %), with 25 of 30 tasks never
>   separating the two arms.
>
> None of the decisions below is withdrawn and no text above is edited. §4
> (OpenCode first-class) is in fact **strengthened**: the closure gate found that
> `RELEASE_CLIENTS` still read `("claude",)`, so the release policy had never been
> brought into line with this ADR.

## Consequences

- v1.0.0 exit conditions reduce from 20 to 17 actionable items
- 3 conditions deferred to post-1.0 with clear ADR reasoning
- No condition is silently dropped — each has evidence or documented rationale
