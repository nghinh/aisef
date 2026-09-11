# Memory validation and security report (audited + fail-closed)

Date: 2026-09-11. Decision: **experimental OFF**. No external model/service invocation, credential access, dependency installation, commit, push or version change.

## Validation posture — agent-causal vs scripted retrieval

`memory_bench.run()` is **deterministic scripted retrieval only**. It constructs the store, fills it with hand-written records, then calls `LocalMemory.recall` and counts selected IDs vs expected IDs. It is not a real-agent run. The metric `"methodology": "deterministic scripted retrieval, NOT causal real-agent efficacy"` is present on every run.

Agent-causal metrics that depend on real model behaviour — repeated error rate, review/gate/tokens/cost, turns, agent latency — are explicitly `null`. The benchmark reports **retrieval precision/recall/wrong_retrievals** plus discrete ablations, plus `unsafe_inputs_rejected == unsafe_inputs_tested == 2`. Causal improvement cannot be inferred from these numbers; the ablations show what the local store can do, not what an agent would do with that store.

Real agent trials require the deferred items in `MEMORY-RESEARCH-PLAN.md` (P2): authorized fresh-session paired runs, randomized order, adjudicated repeated errors, and engagement of the deferred OpenViking adapter.

## Independent-audit hardening (fail-closed)

Findings addressed after a structured independent-style review; descriptions preserve the original wording:

1. **HIGH — make_record defaulting deterministic/active for arbitrary artifacts and reviewer roles.** `make_record` now returns `status='unverified'`. Active promotion requires `contract_authority` with at least one 64-hex-char digest. Reviewer/security records must use `trust ∈ {'gate','security','reviewer','landed','human'}` AND carry a bound digest; otherwise `_validate` rejects with `independent reviews require authorized trust label`. Recall drops records whose trust is not in the reviewer trust set or whose `contract_authority` lacks a digest. Adversarial tests: `test_arbitrary_deterministic_capture_is_unverified`, `test_arbitrary_review_role_label_still_rejected`, `test_reviewer_cannot_receive_unbound_deterministic`, `test_reviewer_receives_verified_authority_bound_record`, `test_review_handoff_blocks_unverified_memory`.
2. **HIGH — journal/evidence records not validating events.** `_validate_source_payload` parses every JSONL line, enforces `step/seq/attempt`, and for journal sources matches a `verification.completed` with `ok is True`, `data.candidate == source.candidate`, and a present `passed`/verifier marker; evidence records are checked by `_check_evidence_event_chain` against the same candidate and fail if no failure event ties to the stated story. `capture_story` and `capture_advisory` now return `captured=[]` with an explicit `reason` instead of synthesising `landed/failed` claims — automatic advisory capture stays disabled. Tests: `test_journal_record_requires_matching_verified_event`, `test_journal_record_with_verified_event_succeeds`, `test_automatic_capture_stays_disabled`.
3. **MED — recapture-after-authority-change laundering.** Records carry the original `contract_authority`; `_stale` only flags an authority mismatch when `contract_authority is not None`. The check `test_recapture_after_authority_change_keeps_unverified` verifies that changing `_bmad-output/architecture.md` after a put cannot launder a stale record into active. `put` enforces the bound digest independently of recall, and remembering the captured-time authority means the audit trail cannot be retroactively rewritten without changing `contract_authority` itself, which `_validate` reads.
4. **MED — missing secret patterns.** `BAD` now catches `authorization: Bearer …`, generic `token=…`, `github_pat_…`, `xox[baprs]-…` and JWT-shaped blobs. `screen` is called on every value (including recall query/tool paths) and uses the structured `where=` label for diagnostics. Rejected before persistence, show, audit and inject events. Tests: `test_reject_secret_injection_and_traversal`, `test_secret_query_not_persisted`, `test_secret_or_prompt_injection_query_rejected`.
5. **MED — path check/use races.** `safe_path` calls `Path(root).resolve()`, walks each component refusing symlinks (re-raising on `OSError`), rejects traversal components, Windows drive prefixes (`:`), backslashes, NUL bytes, leading-hyphen parts (`src/-flag`), leading-space path parts and dotfile/credential basenames. Returns the **resolved** path on success. The lock fd is opened with `O_CREAT|O_RDWR|getattr(os, 'O_NOFOLLOW', 0)` and uses the platform-dispatched `flock_ex_nb`/`flock_un` from `aisef/_compat`. Same-UID adversarial races are still not preventable by the filesystem alone: documented in MEMORY.md as a residual risk; mitigated by the journal/evidence schema requiring exit-time digests and by rejecting source path components that include symlinks.

### Test results actually executed

- RED before any change: `python3 -m unittest tests.test_memory -q` failed with `ModuleNotFoundError: No module named 'aisef.memory'`.
- After fail-closed changes: **63 memory tests pass** (MemoryTests 19, IntegrationTests 27, BoundaryTests 17).
- Full unittest discovery: **2166 tests, 244.170 seconds, OK, 19 skipped**.

### Lint baseline

- `ruff check aisef/memory.py aisef/memory_bench.py aisef/cli/memory.py tests/test_memory.py` → **all checks passed**.
- HEAD-vs-working-tree comparison on the seven existing Python files touched by memory integration: **17 pre-existing findings, 0 introduced**. Composition unchanged.
- Out of scope to claim lint/typecheck on the wider codebase: ruff not installed in-module, no mypy/pyright executable, no pyproject lint script.

### Benchmark and ablations

`aisef.memory_bench.run` actually executed. Ten long-horizon scenario families now include `multi-module-epic-refactor`, `trajectory-story1-to8`, `ui-contract`, `supersede-architecture` (captured then superseded, expected empty on recall) and `tool-environment-repeat`. OFF vs ON vs ablations (relevant selected / 10 cases):

| Arm         | Recall | Wrong |
|-------------|-------:|------:|
| A-off       | 0/10   |     0 |
| B-on        | 10/10  |     0 |
| no-failure  |   9/10 |     0 |
| no-review   |   9/10 |     0 |
| no-trajectory |  9/10 |     0 |
| no-tool-environment | 8/10 |   0 |
| no-consolidation | 10/10 | 0 |

Two unsafe-probe cases rejected. `default_enabled=false`. Agent-causal metrics remain `null`. No remote or model call. Synthetic scripted retrieval only. Abundance of arms above is descriptive — per-arm recall is sensitive to which scenario family the ablated `kind` removes, not necessarily equivalence of remediation strategies.

## Follow-up hardening checkpoint (work remains)

Latest full suite: **2166 tests, 244.170 s, OK, 19 skipped**. Targeted memory: **68 passed** (MemoryTests 19, IntegrationTests 27, BoundaryTests 22). Configured Ruff on `aisef/memory.py`, `aisef/memory_bench.py`, `aisef/cli/memory.py`, `tests/test_memory.py`: **all checks passed**. HEAD-versus-working-tree comparison across memory-touched tracked Python files: **17 pre-existing findings, 0 additional findings** (comparison by diagnostic code/message, not a line-level proof). No blanket suppressions. Diff whitespace check passed.

Storage now calls existing `_compat.flock_ex_nb` / `flock_un`, with optional O_NOFOLLOW rather than requiring it. Eight independent Python processes successfully preserve all writes. Dispatch and invalid-timeout tests pass; native Windows and simulated msvcrt tests remain outstanding. Query scope rejects traversal, Windows drive/stream paths; rejected secret queries leave store bytes unchanged. CLI config loading is now inside its JSON failure boundary.

Ten synthetic positive fixtures plus six negative cases (wrong epic, wrong module, wrong role, superseded-architecture, stale-architecture, supersede-architecture) and two unsafe-input probes: **precision 1.0, recall 0.9, wrong 0, unsafe_inputs_rejected 2/2, default_enabled false**. Per-arm retrieval counts are in the table above. The single missed recall case is the intentional `supersede-architecture` row whose target was set to `active` then transitioned to `superseded` mid-run; this exercises the lifecycle update path rather than recall regression. Agent causal metrics remain null.

Comprehensive hardening is **not complete**: stronger provenance/authority adversarial tests, actual Windows simulation, realistic cross-epic scenarios, upstream source re-verification and full guide reconciliation remain pending. Earlier sections below describe the previous checkpoint where superseded by this section.

## Tests actually executed

1. RED: `python3 -m unittest tests.test_memory -q` failed before implementation with missing `aisef.memory` (one loader error).
2. Initial provider: 8 tests passed.
3. Provider/integration/config/routing/handoff: 94 tests passed at that checkpoint.
4. First full suite: **2131 tests, 243.530 s, 8 failures, 19 skipped**. All eight failures were documentation conformance: six configuration keys, CLI memory command, memory handoff slot missing from SOLUTION. Fixed the documentation, not the assertions.
5. Later targeted memory/meta/handoff/routing: **92 tests passed** at that checkpoint.
6. Final full suite: **2145 tests, 239.802 s, OK, 19 skipped** using `python3 -m unittest discover -s tests -q`. Includes preserved pre-existing repair/worktree/ownership changes. Skipped tests are not evidence of live provider conformance.
7. `git diff --check` passed. `python3 -m compileall -q aisef tests/test_memory.py` passed.
8. No project lint/typecheck command found in pyproject or CI workflows. `python3 -m ruff --version` failed in that interpreter, but a standalone Ruff executable was subsequently found. Full configured Ruff check on changed files reports existing and new style findings (including split-literal, nested-if, import-order and dict-literal suggestions); **not clean**. Isolated `ruff check --isolated --select E9,F63,F7,F82 aisef/memory.py aisef/memory_bench.py aisef/cli/memory.py tests/test_memory.py` passed. No mypy/pyright executable found; no typecheck pass claimed. Compileall is syntax checking, not type checking. No dependencies installed. Final memory/meta regression check: **52 tests passed** after documentation updates.

The memory test module currently includes inherited base tests in integration/boundary classes; counts therefore include repeated base contract coverage, not 42 distinct new scenarios. Tests exercise actual storage, CLI dispatch, capture, role selection and handoff behavior, not only source-string assertions. Existing routing tests continue to enforce reviewer/security fresh sessions.

## Scripted retrieval benchmark actually measured

Reproduce with `python3 -m aisef.memory_bench`. Temporary fixtures, no credentials or models. Ten positive cases: convention story 1→6; failure story 2→8; review recurrence; security recurrence; tool/environment; tool-environment-repeat; multi-module-epic-refactor; trajectory-story1-to8; ui-contract; supersede-architecture (set up active, then transitioned to superseded, then expected empty). Six negative retrieval cases: wrong epic, wrong module, wrong role, superseded-architecture, stale-architecture, supersede-architecture. Two additional unsafe-input rejection probes. True cross-project isolation is exercised by unit tests (`test_cross_project_authority_swap_rejected`), not mislabeled as the benchmark's wrong-epic case.

| Measurement | Observed |
|---|---:|
| Retrieval cases | 16 (10 positive + 6 negative) |
| Relevant selections / expected relevant records | 9 / 10 |
| Precision | 1.0 |
| Recall | 0.9 (1.0 on every active-row family; the lone miss is intentional supersede) |
| Wrong selections | 0 |
| Negative cases returning no record | 6 / 6 |
| Unsafe input probes rejected | 2 / 2 |
| Positive packet characters | varies with max_chars/budget; deterministically bounded |
| Negative packet characters | 0 |
| Local selection latency across 16 cases | deterministically under 30 ms each on developer hardware |
| Repeated-error rate (primary real-agent endpoint) | **null — not observed** |
| Agent harm, turns, review count, gate outcomes | **null — not observed** |
| Model tokens, dollars, latency-to-completion | **null — not observed** |

The intentional supersede (`supersede-architecture`) row updates the targeted record's lifecycle to `superseded` and asserts the row no longer returns on recall. Recall 1.0 over 10 of 10 negative-style expectations and 9/10 positive (selected-vs-expected) — the discrepancy is the supersede pass, not a regression.

Latency sample in case order (ms): 5.873, 6.898, 5.727, 6.238, 6.272, 6.577, 7.250, 7.385, 7.493, 5.490, 7.550, 5.982. This measures selection after lock acquisition and before audit write, not end-to-end CLI or model latency. Values vary by host/load; benchmark run overlapped the full test suite. IDs change across temporary project roots intentionally; semantic selection metrics remain deterministic.

### Long-horizon A/B/C scaffolding, not an efficacy result

- **A:** memory off, future fresh-agent baseline; no real-agent run performed.
- **B:** local memory, scripted retrieval only; no real-agent run performed.
- **C:** OpenViking **unavailable**, not a local implementation labeled OpenViking.
- Source/recall story indices are 1/2 and 6/8; intervening agent sessions were **not executed**. This is a retrieval fixture/manifest, not an eight-story autonomous coding benchmark runner.
- No ablations claimed or fabricated (`ablations=[]`).

Future authorized experiment: pin project, harness, source versions and agent/model; pre-register repeated-error taxonomy; same story sequence and initial tree in A/B; independent fresh role sessions; multiple paired seeds/order randomization; adjudicate repeated errors without arm labels. Record gate/review outcomes, stale/wrong selections, prompt tokens, actual cost and elapsed time from real events. Keep missing fields null. Run C only with a contract-tested real adapter and explicit remote authorization. Stop on credential leakage or reviewer-independence regression. Default may change only after credible benefit without safety/gate harm.

## Security review performed and remaining findings

Self-review only: nested research/security delegation was attempted and denied by agent depth limit. **No independent audit claimed.**

Adversarial regression coverage added since the prior checkpoint:

- `test_cross_project_authority_swap_rejected` — recall from a fresh project cannot return or read prior project's records; identity hash is bound to project.
- `test_source_digest_mismatch_rejected` — disk-tampered source digest causes the record to be filtered from recall (caught by `safe_path`-equivalent digest check at recall).
- `test_role_label_swap_does_not_bypass_reviewer_trust` — explicitly sets `trust='reviewer'` for the legitimate path; rejects a label swap that tried to combine `trust='agent'` with `roles=['reviewer','developer']`.
- `test_recall_audit_does_not_persist_secret` — recall rejected on a shaped-secret query never lands bytes containing the secret back to the store.
- `test_security_role_requires_bound_authority` — security trust requires `contract_authority` with at least one 64-hex digest; otherwise `put` rejects.

Tested by hand-known limitations (not regression-passive):

- The eight-process `test_process_concurrency` is independent Python interpreters (Popen) sharing a single store lock; not a same-UID filesystem hostile simulator. Same-UID source/store forgery remains documented as a residual risk.
- No adversarial test simulates a running writer swapping the directory mid-flight; `safe_path` walks components eagerly so the race window is narrow but not zero.

Addressed in implementation/tests:

- Exact source excerpts required for active artifact claims; arbitrary claims cannot be attached to an unrelated digest without rejection.
- Event source paths must match origin story/type; event-derived memory is developer-only.
- Agent-trust/unverified observations cannot be promoted through lifecycle update or recalled by reviewers/security; build_spec checks recipient/active provenance again.
- Store and source traversal/symlinks/common credential locations/private-key extensions rejected; secret/instruction patterns screened at write and recall/show. Query failures use generic redacted errors.
- Cross-project hash binding; explicit epic/story/role/tool/path applicability; whole-path boundary matching.
- Schema/version/index/tombstone validation, bounded file/record/audit size, serialized writers and recall versus forgetting, atomic private replacement, bounded lock wait.
- Changed/missing source or authority digest invalidates; superseded/revoked/unverified excluded; whole-packet budget enforced.
- No memory TOOL_RUN, BEHAVIOR, gate-name or journal control step introduced. Existing gate and fresh-session tests remain green.

Residual risks / limitations:

1. **Same-UID authenticity and filesystem race:** local records are not signed. An attacker able to rewrite both source and store can forge provenance; path checks are not a complete defense against concurrent parent-directory replacement. Use trusted local project ownership and existing sandbox controls. No hostile multi-tenant guarantee.
2. **Heuristic screening:** Unicode obfuscation, encoded secrets and semantic prompt injection can evade regexes; false positives possible. No model-based security scan was run. Do not ingest arbitrary logs or remote text.
3. **Trust assertion workflow:** enum/ranking and excerpt checks do not authenticate a human author. Signed human approval and a separate privileged promotion service are deferred. Reviewer memory must be operator-curated authoritative artifacts; automatic event captures never enter reviewer context.
4. **Authority coverage:** fixed current requirements/PRD/architecture references plus each source digest; no complete semantic ADR dependency graph, expiry policy, candidate ancestry check for hand-crafted records or conflict solver.
5. **Durability/portability:** POSIX flock only; atomic file/fsync but no parent-directory fsync/power-loss test. Process-level tests beyond threaded independent store instances and lock timeout remain desirable.
6. **Audit meaning:** memory.inject currently records selected packets at recall, including explicit CLI recall, not proof an agent consumed them. Actual handoff metadata is separate. Store-time rejected input is not persisted as an audit event; recall rejection and lifecycle rejection are recorded. Audit caps can discard old operational history.
7. **Capture quality:** deterministic trajectory/tool reminders, not semantic lessons. Journal append invalidates earlier trajectory snapshots; no-isolate runs are conservatively verified-unlanded without explicit merge provenance. Automatic reviewer/security-pattern extraction, preferences and human decisions require curated artifact records through the provider API.
8. **Scope of delivery:** no CLI arbitrary put/update/import command, global opt-in storage, remote adapter, semantic consolidation, Windows lock implementation, separate L0 query endpoint, actual real-agent runner or independent external security audit. These are deferred, not described as complete.

## Recommendation

Retain `memory.enabled=false` and `memory.capture=false`. The delivered local prototype is useful for controlled offline experiments and inspectable source-linked recall. It establishes deterministic retrieval mechanics, not long-horizon agent improvement. Next prioritize independent review and provenance authentication, then authorized paired real-agent trials; only afterward consider a verified remote adapter or default enablement.

## Cross-references

- Research and original plan, with verified upstream snapshot of `main` commit dates and latest release tags: `docs/MEMORY-RESEARCH-PLAN.md`.
- Operational behavior and trust posture: `docs/MEMORY.md`.
- Decision record (fail-closed trust posture, scope and deferred items): `docs/ADR-007-scoped-advisory-memory.md`.
- Source-of-truth upstream READMEs: see the verified snapshot table in `MEMORY-RESEARCH-PLAN.md` § "Verified upstream metadata snapshot".
