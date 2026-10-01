# CYCLE-2 CAPABILITY GAP MATRIX

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). Derived mechanically from the P10 workload evidence
`closure-evidence/v2/P10/WORKLOAD.json` (sha256 `d43211043dd141d3…`), which holds the kernel's typed answer to each of PLAN-V2.1's 77 criteria; the
machine-readable form is [`cycle2-capability-gap-matrix.json`](cycle2-capability-gap-matrix.json). Nothing here changes the P10 record, the LedgerLock plan or the kernel.

**Cycle-1 baseline the matrix is measured against.** Semantic candidate `7114177834da5a7e4a0fc2c7f8fa9d067e0abaa2`, aisef2 tree
`4d6081940f5b9dae47439f73f0157161e028d804`, one probe kind `probe.python_callable` at digest `1961e84d913edc68…` with observation classes `exists`, `returns`, `raises`, `blocks`
over JSON arguments; the four other `Subject.kind` members of F4 (`cli_invocation`, `file_artifact`, `process_effect`, `http_route`) have no probe.

## 1. Classes

| gap class | count | meaning |
|---|---|---|
| SUPPORTED_BY_CYCLE1 | 10 | compiled by the cycle-1 compiler for python_callable; admitted by StaticPlanAdmission checks 2, 6, 9 |
| UNSUPPORTED_SUBJECT_KIND | 53 | the contract's true kind has no probe: `CompileError: no probe declared for subject kind …` |
| UNSUPPORTED_OBSERVABLE | 8 | python_callable subject, but the observable has no observation class (bytes, a constant's value, a fixture file) — check 9 |
| INVALID_NAMES_TEST_ARTEFACT | 6 | the criterion's subject is a developer test or gate: `ContractError: a contract names the product, never a test` (RFC §7) |
| *overlay:* AMBIGUOUS_NEEDS_HUMAN_CLARIFICATION | 28 | the criterion as written admits more than one contract; the plan author decides, never the harness |

## 2. What Cycle 2 must provide, by need

| need | criteria |
|---|---|
| probe.process_effect | 32 |
| probe.cli_invocation | 17 |
| none | 10 |
| python_callable observable 'returns_bytes' | 6 |
| plan migration to a product subject or out of ProductProof | 6 |
| probe.file_artifact | 4 |
| python_callable observable 'equals' over a non-callable subject | 1 |
| python_callable stimulus 'workspace' | 1 |

## 3. Decisions the matrix cannot make

- **DECISION-1** — witness sets for universally quantified criteria (01-01-1, 04-03-1..5) — plan author, owner sign-off
- **DECISION-2** — controlled in-process fault steps inside the subject's process (01-04-5, 03-01-5): sanction as a stimulus kind, or restate the criteria
- **DECISION-3** — migration of the six test-named criteria (05-01-1..3, 05-02-1..3) to product subjects or out of ProductProof — a LedgerLock PLAN-V2.2, a new development experiment, never a retune of the P10 record
- **DECISION-4** — two-invocation equality/inequality criteria (01-02-2/4/6, 01-03-2/4, 02-02-1/5): restated as fixed expected values (P10's reading) or a probe-defined 'stable' observable

## 4. The 77 criteria

| criterion | story | FR | V1 mode → role/polarity | kind as written | cycle-1 answer | gap class | Cycle-2 need | clarification |
|---|---|---|---|---|---|---|---|---|
| AC-STORY-01-01-1 | STORY-01-01 | FR-1 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | **yes** — universally quantified ('any string s'); a contract holds one stimulus — the plan author must name the witness set (NFD, mixed, empty, ASCII) or restate as a property over a fixed corpus |
| AC-STORY-01-01-2 | STORY-01-01 | FR-1 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | — |
| AC-STORY-01-01-3 | STORY-01-01 | FR-14 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | — |
| AC-STORY-01-01-4 | STORY-01-01 | FR-14 | NEGATIVE_INVARIANT → PRESERVE/MUST_NOT_HOLD | `file_artifact` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.file_artifact | — |
| AC-STORY-01-01-5 | STORY-01-01 | FR-14 | NEGATIVE_INVARIANT → PRESERVE/MUST_NOT_HOLD | `file_artifact` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.file_artifact | — |
| AC-STORY-01-01-6 | STORY-01-01 | FR-14 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | **yes** — one criterion names two symbols (Ledger, ConflictError); one contract names one subject — split into two contracts or accept the class as the witness (P10 chose the class) |
| AC-STORY-01-01-7 | STORY-01-01 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-01-02-1 | STORY-01-02 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'returns_bytes' | — |
| AC-STORY-01-02-2 | STORY-01-02 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'returns_bytes' | **yes** — an equality between two invocations; restate as one invocation with a fixed expected value, or a two-invocation observable ('stable') that the probe defines |
| AC-STORY-01-02-3 | STORY-01-02 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'returns_bytes' | — |
| AC-STORY-01-02-4 | STORY-01-02 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'returns_bytes' | **yes** — as 01-02-2: two dicts differing in insertion order must give identical bytes — restate as one call with a fixed expected value |
| AC-STORY-01-02-5 | STORY-01-02 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'equals' over a non-callable subject | — |
| AC-STORY-01-02-6 | STORY-01-02 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'returns_bytes' | **yes** — as 01-02-2: round-trip stability — two invocations |
| AC-STORY-01-03-1 | STORY-01-03 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | — |
| AC-STORY-01-03-2 | STORY-01-03 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | **yes** — an inequality between two invocations ('different results'); P10 restated it as a second fixed expected value — confirm |
| AC-STORY-01-03-3 | STORY-01-03 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | — |
| AC-STORY-01-03-4 | STORY-01-03 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | **yes** — determinism across two invocations; a fixed expected value already implies it — confirm the restatement |
| AC-STORY-01-03-5 | STORY-01-03 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | — |
| AC-STORY-01-04-1 | STORY-01-04 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable observable 'returns_bytes' | **yes** — 'a JSONL with N lines': N is unbound; the plan author fixes N and the fixture bytes |
| AC-STORY-01-04-2 | STORY-01-04 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | COMPILED | SUPPORTED_BY_CYCLE1 | none | — |
| AC-STORY-01-04-3 | STORY-01-04 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `python_callable` | UNSUPPORTED_OBSERVATION | UNSUPPORTED_OBSERVABLE | python_callable stimulus 'workspace' | — |
| AC-STORY-01-04-4 | STORY-01-04 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-04-5 | STORY-01-04 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — 'a simulated crash (e.g. patching os.replace to raise)': a controlled in-process fault step inside the subject's process — a stimulus kind the owner must sanction (DECISION-2) |
| AC-STORY-01-04-6 | STORY-01-04 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — 'the temp file is created in the same directory': observable requires intercepting the temp-file creation (os-level) — define as a fault-free trace observable or restate as 'after a simulated crash, no temp file remains outside the target directory' |
| AC-STORY-01-05-1 | STORY-01-05 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-05-2 | STORY-01-05 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-05-3 | STORY-01-05 | FR-1 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-05-4 | STORY-01-05 | FR-2 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-05-5 | STORY-01-05 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — 'a separate process opening the same path': a second process is part of the stimulus — a subprocess step in the scenario language |
| AC-STORY-01-06-1 | STORY-01-06 | FR-3 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-06-2 | STORY-01-06 | FR-4 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-06-3 | STORY-01-06 | FR-5 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-06-4 | STORY-01-06 | FR-5 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-01-06-5 | STORY-01-06 | FR-3 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-01-1 | STORY-02-01 | FR-6 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-01-2 | STORY-02-01 | FR-6 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-01-3 | STORY-02-01 | FR-6 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-01-4 | STORY-02-01 | FR-7 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — 'first_bad_index == i (or the earlier index whose chain is now broken)': two acceptable answers — the plan author must fix one (the requirements §3.3 say the first violation) |
| AC-STORY-02-01-5 | STORY-02-01 | FR-7 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-02-1 | STORY-02-02 | FR-9 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — 'two calls return equal dicts' and a key order of the JSON dump: restate as one snapshot with a fixed expected canonical JSON |
| AC-STORY-02-02-2 | STORY-02-02 | FR-9 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-02-3 | STORY-02-02 | FR-9 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-02-4 | STORY-02-02 | FR-9 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-02-02-5 | STORY-02-02 | FR-9 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — 'two Ledger instances opened in succession return equal dicts': a two-construction scenario; the expected value is the fixed snapshot |
| AC-STORY-03-01-1 | STORY-03-01 | FR-8 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-01-2 | STORY-03-01 | FR-8 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-01-3 | STORY-03-01 | FR-8 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-01-4 | STORY-03-01 | FR-8 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-01-5 | STORY-03-01 | FR-13 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | **yes** — as 01-04-5: a controlled in-process fault step (DECISION-2) |
| AC-STORY-03-02-1 | STORY-03-02 | FR-10 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-02-2 | STORY-03-02 | FR-10 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-02-3 | STORY-03-02 | FR-10 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-03-02-4 | STORY-03-02 | FR-10 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.process_effect | — |
| AC-STORY-04-01-1 | STORY-04-01 | FR-11 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-01-2 | STORY-04-01 | FR-12 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-01-3 | STORY-04-01 | FR-11 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-01-4 | STORY-04-01 | FR-11 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-01-5 | STORY-04-01 | FR-11 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-01-6 | STORY-04-01 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-01-7 | STORY-04-01 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-02-1 | STORY-04-02 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-02-2 | STORY-04-02 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | — |
| AC-STORY-04-02-3 | STORY-04-02 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — 'line 17 mutated out-of-band': the fixture must hold >= 18 lines; the tamper is a scenario step over a workspace file |
| AC-STORY-04-02-4 | STORY-04-02 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — as 04-02-3 |
| AC-STORY-04-03-1 | STORY-04-03 | FR-12 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — 'every success path' — universally quantified over invocations; the plan author names the witness invocations (one per subcommand) |
| AC-STORY-04-03-2 | STORY-04-03 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — as 04-03-1; 'mentions the count of appended lines' — the exact stderr shape must be fixed (a regex or a literal), never prose-matched |
| AC-STORY-04-03-3 | STORY-04-03 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — as 04-03-1; 'mentions the destination path' — fix the shape |
| AC-STORY-04-03-4 | STORY-04-03 | FR-12 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — as 04-03-1 |
| AC-STORY-04-03-5 | STORY-04-03 | FR-12 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `cli_invocation` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.cli_invocation | **yes** — 'any success path': a universally quantified duplicate of 04-03-1..4's stdout clause — fold into them or name the witnesses |
| AC-STORY-05-01-1 | STORY-05-01 | FR-2 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `process_effect` | REFUSED_BY_CONTRACT_RULE | INVALID_NAMES_TEST_ARTEFACT | plan migration to a product subject or out of ProductProof | **yes** — the subject is a developer test (property test): RFC §7 forbids; the product property it protects (verify ok and snapshot stable after conflict-free sequences) can be a process_effect PRESERVE contract over fixed seeded sequences — a plan migration the owner must authorize (DECISION-3) |
| AC-STORY-05-01-2 | STORY-05-01 | FR-8 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `process_effect` | REFUSED_BY_CONTRACT_RULE | INVALID_NAMES_TEST_ARTEFACT | plan migration to a product subject or out of ProductProof | **yes** — as 05-01-1 (conflict leaves the file unchanged past the prefix) |
| AC-STORY-05-01-3 | STORY-05-01 | FR-14 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `process_effect` | REFUSED_BY_CONTRACT_RULE | INVALID_NAMES_TEST_ARTEFACT | plan migration to a product subject or out of ProductProof | **yes** — unittest/pytest parity of a test module is an engineering-test property (RFC §15, Q1 test-layout invariance), not a product contract — migrate out of ProductProof (DECISION-3) |
| AC-STORY-05-02-1 | STORY-05-02 | FR-14 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_CONTRACT_RULE | INVALID_NAMES_TEST_ARTEFACT | plan migration to a product subject or out of ProductProof | **yes** — line-coverage >= 85% is a project quality gate (RFC §15 EngineeringTestAdequacy / project policy), not a product behaviour — migrate out of ProductProof (DECISION-3) |
| AC-STORY-05-02-2 | STORY-05-02 | FR-14 | PRESERVE_REQUIRED → PRESERVE/MUST_HOLD | `process_effect` | REFUSED_BY_CONTRACT_RULE | INVALID_NAMES_TEST_ARTEFACT | plan migration to a product subject or out of ProductProof | **yes** — as 05-01-3 |
| AC-STORY-05-02-3 | STORY-05-02 | FR-14 | CHANGE_REQUIRED → INTRODUCE/MUST_HOLD | `process_effect` | REFUSED_BY_CONTRACT_RULE | INVALID_NAMES_TEST_ARTEFACT | plan migration to a product subject or out of ProductProof | **yes** — as 05-02-1 |
| AC-STORY-05-03-1 | STORY-05-03 | FR-14 | NEGATIVE_INVARIANT → PRESERVE/MUST_NOT_HOLD | `file_artifact` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.file_artifact | — |
| AC-STORY-05-03-2 | STORY-05-03 | FR-14 | NEGATIVE_INVARIANT → PRESERVE/MUST_NOT_HOLD | `file_artifact` | REFUSED_BY_COMPILER | UNSUPPORTED_SUBJECT_KIND | probe.file_artifact | — |

## 5. Reading rules

- A criterion's gap class is the kernel's typed answer, not a judgement: `COMPILED` → supported; `REFUSED_BY_COMPILER` → unsupported kind; `UNSUPPORTED_OBSERVATION` (check 9) → unsupported observable; `REFUSED_BY_CONTRACT_RULE` → names a test artefact.
- The overlay flag marks criteria whose *text* admits more than one contract. It is recorded, not resolved: resolving it is plan authoring (a LedgerLock PLAN-V2.2 would be a new development experiment under RFC §30), never a change to the P10 record.
- Ten criteria are provable today; Cycle 2's probe kinds would raise the count to 71 by kind alone; the six test-named criteria need DECISION-3 before any probe can take them; the ambiguous ones need DECISION-1/2/4 before their contracts are frozen.
- No semantics were inferred: where a criterion says 'e.g.' or 'any', the matrix says 'decide', not 'assume'.
