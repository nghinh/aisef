# SYSTEMATIC HARDENING DESIGN CHECKPOINT (Phases 0–7)

Program: AISEF SYSTEMATIC HARDENING PROGRAM v1 — end the "run project → find bug → patch bug" loop.
Branch: `hardening/systematic-v1` (master untouched; public 1.7.6 = `939f2ab` is the frozen reference baseline).
Date: 2026-09-16. Status: Phases 0–7 complete. **Phases 8–14 not started — owner approval required.**
Not done, by directive: no release, no tag, no LedgerLock replay resumed, no G6.

Verification of this checkpoint (measured on this branch, macOS, Python 3.13):

| what | result |
|---|---|
| `tests/hardening` (registry, family map, sibling scan, verdict freshness, state model, fault matrix) | 42 passed · 27 expected-red (each tagged with its defect id) · 15 conformance subtests |
| state model `AISEF_MODEL_TRACES=10000` | 10 000 traces · 105 949 transitions · **0 property violations** |
| full suite | 3216 passed · 19 skipped · 27 expected-red · 1434 subtests · 0 failures (378 s) |
| ruff (`aisef tests validation`) | clean |
| Windows CI on this branch | **not run** (branch not pushed; a PR is the step that runs it) |

---

## 1. Invariant registry summary

`aisef/invariants.yaml` (machine-readable, loaded by `aisef/control/invariants.py`) → `docs/INVARIANTS.md` (rendered; the registry test fails if the two drift).

| | count |
|---|---|
| invariants (families A–T) | 50 |
| PROVEN (deterministic test green on 1.7.6) | 12 |
| PARTIAL (some enforcement or some test, a known gap) | 28 |
| MISSING (no enforcement; RED reproducer or none) | 10 |

MISSING: INV-C.3 (baseline recapture at root), INV-D.1 (structural proofs bound to the graded session), INV-E.1 (verdict freshness under tree change — D-035), INV-E.3 (resume feedback reader), INV-G.2 (security session failure ≠ verdict), INV-G.5 (budget rejection inside review/security is typed), INV-H.2 (no-op decision reads freshness), INV-I.2 (merge dirt check honours ownership), INV-K.2 (recovery invalidates dependent evidence), INV-S.1 (replay contract).

Every invariant carries: id, domain, statement, why, severity if violated, enforcement points (file::function), deterministic / model / fault tests (each reference resolved to an existing file::Class::method by `tests/hardening/test_invariants_registry.py`), linked defects, status.

## 2. Defect-family map

`closure-evidence/hardening/defect-family-map.json` → `docs/DEFECT-FAMILY-MAP.md`. 13 families, 47 members (all 35 register entries D-001…D-035 plus LedgerLock findings F-7/F-9, Run2-B, OBS-R13, OBS-OC-2, OBS-OC-merge, AC4-ARBITRATION, REPLAY-DRIFT and the taxonomy rows 13/15/25/28/37/38/42 that predate the register).

| family | missing invariant (one line) | members |
|---|---|---|
| FAM-IDENTITY | identity by recency or position instead of the identity tuple | D-004 D-021 D-023 D-033 lỗi-42 |
| FAM-OUTCOME | absence / unrunnable read as pass or fail | D-001 D-005 D-008 D-010 D-012 D-029 |
| FAM-PROSE | prose parsed into control state | D-018 D-026 |
| FAM-RETRY | retry locality and budget accounting | D-006 D-032 |
| FAM-RECOVERY | recovery and resume semantics | D-034 **D-035** OBS-R13 |
| FAM-OWNERSHIP | workspace ownership and generated files | D-011 D-030 OBS-OC-merge lỗi-38/37 |
| FAM-TOOL | tool declared but not available | D-009 D-013 D-028 F-9 Run2-B |
| FAM-PROCESS | process lifecycle and liveness | D-024 D-025 D-027 lỗi-15/13 |
| FAM-SCHEDULER | declared scope vs effective scope | D-031 |
| FAM-APPROVAL | approval and pre-registration binding | D-014 D-017 lỗi-25/28 |
| FAM-RELEASE | release and closure identity | D-007 D-019 D-020 D-022 REPLAY-DRIFT |
| FAM-BENCH | benchmark integrity | D-003 D-015 D-016 |
| FAM-JUDGE | model output as control authority | D-002 F-7 OBS-OC-2 AC4-ARBITRATION |

Reading: the last four public patches (1.7.3–1.7.6) closed nine individual defects across FAM-OUTCOME, FAM-RETRY, FAM-IDENTITY and FAM-RECOVERY; the sibling scan below shows each of those families still has unfixed members of the same shape. That is the loop the program ends.

## 3. Sibling scan findings

`closure-evidence/hardening/sibling-scan.json`. 66 sites examined against the listed anti-patterns (last/latest evidence as truth, SHA-only identity, prose → control state, missing UNRUNNABLE branch, retry reopening the wrong stage, ownership by porcelain, etc.). No production code was changed.

| classification | count |
|---|---|
| CONFIRMED (RED reproducer exists and fails on the invariant assertion) | 23 |
| NEEDS_TEST (anti-pattern present, consequence not yet demonstrated) | 38 |
| NOT_A_DEFECT (examined, safe by construction, reason recorded) | 5 |

CONFIRMED, by proposed severity:

- **P1 (9):** SS-05 `_no_escalation` demotes block findings across a contract epoch (false PASS via the judge); SS-12 `from .mockup import RunResult` — BudgetExceeded inside review/security raises ImportError and kills the sprint; SS-13 a security *session* failure is recorded as a security FAILED check and reopens the developer (D-032's shape on the security stage); SS-14 an UNRUNNABLE deterministic check costs a developer attempt until max_retries; SS-26 `_vang_ma_cua_story` erases an environment failure when a changed file's stem appears in the traceback (TDD passes on a suite that never ran); SS-27 the security noise filter has no severity floor (a critical finding worded with "no rate limit" stops blocking); SS-39 ownership; SS-57 a reviewer that never produces a structured verdict (twice) is scored from prose — a PASS from the *absence* of a verdict; D-035 (OBS-OC-4).
- **P2 (14):** SS-02 guard heartbeat is per story, not per graded session; SS-03 criteria proofs harvested from unstamped runs; SS-04 `_unfinished_review` reads an event name that is never written (dead resume-feedback path); SS-15 `context`/`permission`/`cost` exits charged to quality (D-006's siblings); SS-17 merge refuses on raw porcelain incl. tool artifacts; SS-18 an unrunnable baseline is never re-captured at root; SS-23 all-red tests whose messages contain "not found" are TOOL_UNRUNNABLE (D-029 reversed); SS-24 prose `[block]` overrides a structured pass; SS-25 scope verdict regexed out of prose; SS-28 `auth` exit classified from the agent's prose before the provider field; SS-30 plan machine gate rejects any criterion containing "TODO" (every to-do app); SS-35, SS-36 ownership siblings; SS-58 the gate's lint branch has no UNRUNNABLE path (missing linter = FAILED).

Reproducers: `tests/hardening/test_sibling_scan.py` (21 classes, each `@expectedFailure # SS-xx`) and two cells of `tests/hardening/test_fault_matrix.py` (SS-57, SS-58). An unexpected success is a hard failure, so a fix must remove its marker.

## 4. Kernel transition model

`docs/ASSURANCE-KERNEL.md`. The kernel owns: story identity, stage sequencing, outcome typing, evidence binding, retry/recovery accounting, terminal decisions. Clients, tools and judges *report*; they never decide.

- Identity tuple (9 fields): run_id, story_id, story_epoch, candidate_sha, baseline_root, stage, verifier_config_digest, environment_digest, **tree_state_digest**. Evidence is fresh only when its tuple equals the current one — SHA alone is not identity (this is D-035's root cause and SS-02/03's).
- 12 typed stage outcomes: PASS, QUALITY_BLOCK, UNRUNNABLE, ENVIRONMENT_FAILURE, INFRA_FAILURE, AUTH_FAILURE, NOOP, PLAN_CONFLICT, ISOLATION_BREACH, MERGE_CONFLICT, ORPHANED, HUMAN_REQUIRED. No stage returns a boolean or a string.
- Transition table T1–T35 (state × outcome → next state, budget charged, evidence written). 5 rows are marked `deviation:` — places where the 1.7.6 kernel does something else today (SS-12, SS-13, SS-14, SS-15, D-035). The model in §6 implements the table; the conformance harness measures the real kernel against it.

## 5. Synthetic harness status

`aisef/clients/synthetic.py` — `SyntheticClientAdapter`, registered as `--client synthetic` in `compile.ADAPTERS`. No LLM. A `Script` holds three queues (developer, review, security) of `Step`s; the adapter detects the role from the prompt's first line and records every call.

Step kinds: developer CHANGED / NOOP / ZERO_OUTPUT / TIMEOUT / MAX_TURNS / CRASH / AUTH / CONTEXT / RATE_LIMIT / BUDGET / SCOPE_VIOLATION / TRUNK_COMMIT; review PASS / BLOCK / STUCK / MALFORMED / UNRUNNABLE / MUTATE / COMMIT / BUDGET; security PASS / BLOCK / UNRUNNABLE / MALFORMED / BUDGET. It drives the real `implement_story` in a real isolated worktree with the real gate, so a scenario's outcome is the kernel's, not a mock's.

Two harness facts the synthetic client had to match (documented in the code): a NOOP session must report zero output tokens or it trips the ZERO-OUTPUT fatal; a security BLOCK must carry the JSON verdict envelope or the harness treats it as "no schema", re-asks once, and takes the second answer.

## 6. State-space coverage and first results

`tests/hardening/model.py` (executable model of §4) + `tests/hardening/test_state_model.py`. Results file: `closure-evidence/hardening/state-model-results.json`.

| | |
|---|---|
| seeded traces | 10 000 (default; `AISEF_MODEL_TRACES`) |
| transitions | 105 949 |
| events exercised | 32 of 32 |
| terminal classes reached | 19 (done, exhausted, credential rejected, isolation breach, owner declined plan/merge, recurring infra, REVIEW_UNRUNNABLE, SECURITY_UNRUNNABLE, no-op ×2, environment: tool unrunnable, orphaned at three stages, …) |
| properties asserted after every transition | 10 (P1 identity binding, P2 no PASS from absence, P3 fresh evidence only, P4 UNRUNNABLE never a developer attempt, P5 infra never charges quality, P6 stage locality of retries, P7 monotone budgets, P8 terminal is terminal, P9 no-op needs a fresh verdict, P10 ownership of tree changes) |
| violations | **0** |

Conformance (real kernel through the synthetic client vs the model), 15 scripted scenarios, metric = (done, developer sessions, quality attempts):

- 10 agree: happy path, review unrunnable then pass, review unrunnable exhausted, review block then pass, review stuck, two no-ops, credential rejection, tool red exhausted, scope violation then clean, trunk commit, …
- 5 differ **exactly where a registered defect predicts**: C4 security unrunnable (SS-13), C8 context exit (SS-15), C10 test tool unrunnable (SS-14), C11 budget in review (SS-12), C12 no-op after hygiene (D-035). The test asserts the *difference* for these; when a family fix lands, the assertion flips and the entry must be removed.

One model correction came out of conformance: the real kernel's `quality_attempts` counts every non-infra attempt, the passing one included, and an attempt whose review never ended; the model now uses the same definition. The exhaustion decision is unchanged (taken only on QUALITY_BLOCK).

## 7. Fault matrix

`closure-evidence/hardening/fault-matrix.json` → `docs/FAULT-MATRIX.md`. 11 stages × 8 fault kinds (QUALITY, INFRA, TIMEOUT, CRASH, MALFORMED, NOOP, STALE, INJECTED) plus injected scenarios; 53 cells, each with scenario id, expected state, expected evidence, expected recovery, invariants, test, status.

| status | count |
|---|---|
| GREEN (real kernel behaves as the table says) | 35 |
| RED (linked to a defect; reproducer expected-red) | 15 |
| NEEDS_TEST | 3 (FM-A-03 approval cascade under concurrent edit, FM-P-05 lease expiry mid-merge, FM-W-05 Windows path case) |

RED cells: FM-D-04 (SS-15), FM-D-07 and FM-E-03 (D-035), FM-T-03 (SS-14), FM-T-07 (SS-23), FM-L-02 (SS-58), FM-R-04 (SS-12), FM-R-05 (SS-57), FM-S-02/03 (SS-13), FM-M-02 (SS-17), FM-E-06 (SS-02/03), FM-W-03 (SS-39), FM-W-04 (SS-35), FM-X-01 replay contract (MISSING, Phase 10).

## 8. Confirmed defects discovered BEFORE LedgerLock found them

All 23 CONFIRMED sibling-scan entries except D-035 itself were found by code reading and reproduced deterministically without any project run. Two were found by the fault matrix on first execution, in cells written to test an invariant rather than a symptom:

- **SS-57 (P1, FAM-PROSE):** reviewer answers twice without a structured verdict → `_reconcile` scores the prose → PASS. The 1.7.4 fix (D-032) typed REVIEW_UNRUNNABLE for a *cut* session, not for a *malformed* one.
- **SS-58 (P2, FAM-OUTCOME):** missing linter → gate check `lint` FAILED. The 1.7.3 fix (D-029) taught the `test` branch UNRUNNABLE; the `lint` branch never had the path.

Honest boundary: D-035 (OBS-OC-4) was found by the LedgerLock confirmation run, not by this program; the program reproduced it without OpenCode and placed it in its family. Of the 23, the ones LedgerLock would most plausibly have hit next on its remaining six stories: SS-13 (any security session cut), SS-14 (any sandbox tool hiccup), SS-17 (merge after a coverage run), SS-57 (any OpenCode reviewer answer without JSON).

## 9. Proposed family-level fixes (design only — nothing implemented)

**OBS-OC-4 / D-035 — FAM-RECOVERY + FAM-IDENTITY (INV-E.1, INV-H.2, INV-K.2).** Not "re-grade after hygiene". The abstraction-level fix:
1. Evidence identity gains `tree_state_digest` (candidate SHA + digest of the porcelain state the verdict was computed over). `gate:verdict`, `review:*`, `security:*` events carry it (D-033's `bound_to` pattern, extended).
2. One function `fresh_verdict(ev, candidate, tree)` replaces the three SHA-keyed lookups that exist today (`cham_roi` in `run_attempt`, `_review_complete`, `_security_complete`): a verdict is reused only if its identity tuple matches.
3. `recover_out_of_scope` writes a typed `evidence:invalidated` event naming the verdicts it made stale (the K.2 half). Same event for `--verify-only` re-runs and for a baseline recapture.
4. The no-op decision reads freshness: a no-op session over a candidate with **no fresh verdict** transitions to VERIFY (re-grade), not to "same verdict"; only a no-op over a *fresh* verdict counts toward the two-strike terminal. This is the T20/T21 pair in the kernel table.
5. Regression: `test_verdict_freshness.py` marker removed; model conformance C12 flips; the fault cells FM-D-07/FM-E-03 go GREEN. No STORY-04-01 special case anywhere.

**D-002 (P2, FAM-JUDGE) "a blocking gate decision can rest on the model reviewer alone".** Proposed disposition: **FIXED at family level**, by making the reviewer's block a typed QUALITY_BLOCK whose *findings* must each be bound to a behavior_id or a path inside the write scope (structured verdict, SS-24/SS-25 removed), and by the escalation rule being epoch-scoped (SS-05). The judge still blocks, but only through structured, bound, epoch-scoped findings, and the two-strike deadlock reads those findings, not prose. Deterministic test: a block whose findings bind to nothing is REVIEW_MALFORMED (→ retry, then REVIEW_UNRUNNABLE), never a gate FAILED.

**D-003 (P2, FAM-BENCH) `_analyze.cut_sessions` merges two cohorts.** Proposed: cohort identity = (bench config digest, task set digest) carried on every session record; the analyzer refuses to merge records with different cohort keys and says so. Deterministic test over two synthetic cohorts sharing three tasks. Likely **FIXED**, small.

**D-011 (P2, FAM-OWNERSHIP) bench writes into the framework repo root.** Proposed: every writer in `aisef/bench` takes an explicit workspace root (no `Path.cwd()` default); one test runs a bench session from the repo root and asserts `git status --porcelain` unchanged. Ties to INV-I.1/I.3. Likely **FIXED**.

**D-024 (P2, FAM-PROCESS) TemporaryDirectory cleanup races a writer inside a session's `.git`.** Proposed: the bench-qualification helper must reap the process tree (the 1.7.3 `kill_tree` + wait) before cleanup; test: spawn a child that keeps writing into `.git`, run the helper, assert no `OSError` and no survivor. If the three CI recurrences stop after the fix, **FIXED**; if the writer is outside our tree, **NOT_A_DEFECT with proof** (captured `ps`/`ls -la .git` at failure time, which the current helper does not record — that capture is the first step).

**Other P1 siblings (SS-05, SS-12, SS-13, SS-14, SS-26, SS-27, SS-39, SS-57)** map onto three family fixes: (a) typed stage outcomes for review/security/tool with stage-local retry and infra accounting (covers SS-12/13/14/15/57/58, INV-G.*), (b) structured-only judgment with a severity floor and epoch scoping (covers SS-05/24/25/26/27/28/30, INV-F.2/T.1), (c) ownership by attribution not porcelain (covers SS-17/35/36/39, INV-I.*).

## 10. Files and product surfaces that would change (Phases 8–14)

Product (`aisef/`): `phases/implement.py` (run_attempt no-op shortcut, `_review_complete`/`_security_complete` → `fresh_verdict`, `_reconcile`/`_reconcile_security` prose paths, `_no_escalation` epoch scope, `_vang_ma_cua_story`, `_paths_outside`, `_unfinished_review`, the `mockup.RunResult` import, security stage typing), `control/gate.py` (lint UNRUNNABLE branch, guard/criteria proofs bound to the graded session), `harness/guardrails.py` (GUARD_SEEN stamped per session), `control/security.py` (noise floor), `clients/stream.py` (exit status from provider fields first), `control/machine_gate.py` (placeholder regex), `control/worktree.py` (merge dirt by ownership), `harness/tools.py` (MISSING_TOOL polarity), `harness/observe.py` (identity tuple on events, `evidence:invalidated`), `phases/run.py` (journal outcomes), `bench/` (D-003, D-011). Assurance: `tests/hardening/*` markers removed as families close, KNOWN_DEVIATIONS emptied, fault cells flipped, `invariants.yaml` statuses → PROVEN. Docs: taxonomy rows 190+, register dispositions, INVARIANTS/FAULT-MATRIX re-rendered, CHANGELOG. Public surface: none until qualification (Phase 12) and owner release approval.

## 11. Risks

- **Model and kernel could share a misconception.** The model is hand-written from the same understanding; conformance covers 15 scripted scenarios, not the 10 000 traces. Mitigation in Phase 11: drive the real kernel with the model's random traces through the synthetic client (a replay contract is exactly what FM-X-01 asks for).
- **38 NEEDS_TEST entries** are unproven either way; some will become CONFIRMED during Phase 8 and widen the change.
- **Windows** has not run any of the 69 new tests. A branch PR must go green on the 5-OS matrix before any qualification claim.
- **The synthetic client bypasses the real client plumbing** (OpenCode plugin hooks, Claude stream parsing). SS-02 and SS-28 live there; their fixes need the existing client tests, not the synthetic ones.
- **Scope pressure.** Family fixes touch `implement.py` heavily; the anti-goals (no features, no retry inflation, no gate weakening) must be re-checked per family with the fault matrix, not once at the end.
- **D-035 is live for any operator on public 1.7.6** (a clean candidate can be left ungraded after hygiene); the workaround is `--verify-only`, and no patch release is authorized. This is the owner's call.
