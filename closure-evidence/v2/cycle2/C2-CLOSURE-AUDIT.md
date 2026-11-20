# AISEF V2 — CYCLE-2 FINAL CLOSURE AUDIT

**STOPPED BEFORE CLOSURE ACCEPTANCE — RELEASE BLOCKER RETURNED TO THE OWNER**

Records: `closure-evidence/v2/cycle2/C2-CLOSURE-AUDIT.json`, `closure-evidence/v2/cycle2/C2-LEDGERLOCK-FAILURE-TRIAGE.json`, `closure-evidence/v2/cycle2/C2-ORCHESTRATION-CHANGE-REVIEW.json`, `closure-evidence/v2/cycle2/C2-HISTORY-FREEZE-CANDIDATE.json` (builder `validation/qualification/c2_closure_audit.py`).

## Stop

- **FRAMEWORK_KERNEL_DEFECT (the evidence's reading; class A)** — a fully PRE_SATISFIED story under a blocking tests policy is rolled back and charged a DEVELOPER retry with no developer call (RFC §14 vs §15.3); reproduced without LedgerLock Stories: STORY-02-01, STORY-02-02.
- **ORCHESTRATION CHANGE CLASSIFICATION PENDING** — returned for the Owner's explicit ruling; one journal difference on a misconfiguration failure path is disclosed
- **PACKAGING (a fact, not a Cycle-2 defect)** — pyproject.toml excludes aisef2* from the wheel; version 1.7.6: a release from this tree ships no V2 code

## 1. Final commit lineage

- `c11615aeb1dd9e6ff992b6190f8c39a272636742` (parent `edef4f16e851580fdcc8f88b2a7c8b34f04fda33`) — Final integration candidate: the C2-FINAL history registered, LANE-X's attempts recorded.
- `2dd12265caa47095ac8daebea4eda8f817f812f3` (parent `236b440ff0b3d9811a602c9c61b3b3c769a5a819`) — CYCLE-2 P6/P7/P8/P9/P10 COMPLETE — the consolidated report for the final Owner closure review: closure-evidence/v2/cycle2/C2-FINAL-REPORT.js
- `3ed2c41126e27d1a6b04e5442b56bbf3b6d89f11` (parent `2dd12265caa47095ac8daebea4eda8f817f812f3`) — C2-FINAL-RUN-HISTORY.json seq 28-35: the attempts of the final head 2dd1226 — local suite 5096 OK in the owned range (0/0/0, escaped 0); tes
- product candidate: c11615aeb1dd9e6ff992b6190f8c39a272636742 — the V2 kernel under qualification is its aisef2 tree 254d8f559b879c210c4936321022f1350c4b2f89. Under the existing plane rules the PRODUCT_AFFECTING plane is the V1 wheel content, identical at all three commits: Cycle 2 changes nothing that ships
- qualification candidate: c11615aeb1dd9e6ff992b6190f8c39a272636742 (QP-2.6 R4, Q4-FINAL, Q5-FINAL); QP-2.9 ran on kernel tree 37bf6457f350dd720a2214f04f3896c554ad0904 (the R3 candidate 37dc0dcdf819387b65ee60cf614273df94aaef31) and was not rerun: the kernel files that differ between that tree and the final one are ['A', 'aisef2/cohort/__init__.py', 'A', 'aisef2/cohort/lifecycle.py', 'A', 'aisef2/cohort/preregistration.py'] — the cohort package, which no other kernel module imports (git grep)
- evidence only bookkeeping: 3ed2c41126e27d1a6b04e5442b56bbf3b6d89f11 (one history file). 2dd12265caa47095ac8daebea4eda8f817f812f3 adds evidence and one validation/qualification builder (ASSURANCE_AFFECTING by the rule 'validation/*', outside the trees QP-2.6 consumes)
- release source candidate if approved: the branch head that carries this audit — its aisef2, validation/v2 and tests/v2 trees are the final candidate's (c11615aeb1dd9e6ff992b6190f8c39a272636742). The Owner names it; nothing here does
- release fact for the owner: pyproject.toml excludes aisef2* from the wheel and the version is the V1 one: as the tree stands, a published artifact contains no V2 code. Packaging a V2 release is a PRODUCT_AFFECTING change outside Cycle 2's scope

## 2. Plane identities at each commit

| commit | PRODUCT_AFFECTING | ASSURANCE_AFFECTING | EVIDENCE_ONLY | aisef2 tree |
|---|---|---|---|---|
| `c11615aeb1dd9e6ff992b6190f8c39a272636742` | `68f500984d2b0e8945df76247f54f56554966455b73259ed95b8dcdf7aa5d253` | `bc25aae6c3d350f803d44506478a8ce6805256d9e78d35c663289e8b8fa53fe2` | `6cc95771e86466694796a258f20fb542f67c04f422880cb99ee2058ec0bd2b0c` | `254d8f559b879c210c4936321022f1350c4b2f89` |
| `2dd12265caa47095ac8daebea4eda8f817f812f3` | `68f500984d2b0e8945df76247f54f56554966455b73259ed95b8dcdf7aa5d253` | `a79b6b588e776620d8e3d0708053f4dace6aea0b25fd0aad1ad893eea8110223` | `3dc8f5cfb7ab2a1545df8755cc38a2e7595796dd77f8c7648cf6a8b6426b04ab` | `254d8f559b879c210c4936321022f1350c4b2f89` |
| `3ed2c41126e27d1a6b04e5442b56bbf3b6d89f11` | `68f500984d2b0e8945df76247f54f56554966455b73259ed95b8dcdf7aa5d253` | `a79b6b588e776620d8e3d0708053f4dace6aea0b25fd0aad1ad893eea8110223` | `d155efbbd2d6c4fe17172c90e760f80abf7c3b21a5686f357c8c0f0c897ce6e8` | `254d8f559b879c210c4936321022f1350c4b2f89` |

- active probe digests: `{"probe.file_artifact": "31465b73cbe2440e0e9f6b418665b6f4b1682ee7da2b8968357709daea5e5901", "probe.python_callable_v2": "b71adecf433ea690f0ca03a1cd846778b36387ed48e621924fa58da9a94411fc", "probe.cli_invocation": "5ec17bea4a6763339b5bfda9523ec71dc792b1ed01c6018b5562bff45c70f393", "probe.process_effect": "dbbe4cd51feb988b7b1bfd95aebf243c275c217399d51063d3a85f09b2cfbb23"}`
- inactive cycle1 probe: `{"probe.python_callable": "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf"}`
- plan v22 hash: `"27b679d9513f3dc2f9b5da68a694a3ef1baff50f87eae9903721415a4670a669"`
- semantic hashes aggregate 59: `"83a73da271805c470db4da55f50f542950494aa8b50a31e5b6f07e5364415745"`
- contracts: `59`
- qualification kernel identity: `{"aisef2_tree": "254d8f559b879c210c4936321022f1350c4b2f89", "kernel_digest": "f763b238d9e9c007937b959238feac9d54e6af7d9c1bb707cad1686640526908"}`
- identical across the three: `{"aisef2_tree": true, "probe_tree": true, "validation_v2_tree": true, "tests_v2_tree": true, "plan_and_spec_inputs": true, "PRODUCT_AFFECTING_digest": true}`

## 3. 3ed2c41 local gate

`{"result": "PASS", "tests_run": 5096, "owned_after": 0, "escaped": 0}` (history seq [36, 37, 38, 39, 40, 41, 42, 43])

## 4. 3ed2c41 CI result

run [36846856644]; all PASS: True
- lint: `{"result": "PASS", "tests_run": null, "owned_after": null, "escaped": null}`
- unit (ubuntu-latest, 3.11): `{"result": "PASS", "tests_run": 5093, "owned_after": 0, "escaped": 0}`
- unit (ubuntu-latest, 3.12): `{"result": "PASS", "tests_run": 5093, "owned_after": 0, "escaped": 0}`
- unit (ubuntu-latest, 3.13): `{"result": "PASS", "tests_run": 5093, "owned_after": 0, "escaped": 0}`
- unit (ubuntu-latest, 3.14): `{"result": "PASS", "tests_run": 5093, "owned_after": 0, "escaped": 0}`
- unit (windows-latest, 3.11): `{"result": "PASS", "tests_run": 5090, "owned_after": 0, "escaped": 0}`
- wheel: `{"result": "PASS", "tests_run": null, "owned_after": null, "escaped": null}`

## 5. QP-2.6 R2/R3/R4 lineage

| attempt | candidate | aisef2 tree | validation/v2 | tests/v2 | Q0 | Q1 | Q2 | Q3 | mutants | survivors | audited | unaudited |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R2 | `ac4a6c75b461e409f024965391ce77e7689c0e08` | `37bf6457f350dd720a2214f04f3896c554ad0904` | `2fd461971dd6c92637d45df3948668ec7de59ccd` | `f6b04e08d6da55ad5e626087ebd4d1639960eb62` | FAILED | UNRUNNABLE | UNRUNNABLE | UNRUNNABLE | 14883 | 10 | 10 | 0 |
| R3 | `37dc0dcdf819387b65ee60cf614273df94aaef31` | `37bf6457f350dd720a2214f04f3896c554ad0904` | `2fd461971dd6c92637d45df3948668ec7de59ccd` | `a7d2fb385721891beabab3ac200b974ad81a221c` | GREEN | GREEN | GREEN | GREEN | 14883 | 10 | 10 | 0 |
| R4 | `c11615aeb1dd9e6ff992b6190f8c39a272636742` | `254d8f559b879c210c4936321022f1350c4b2f89` | `7686f004167fc5e940b06bf6ff0248f068d8d116` | `fb9d8e17728a893083575638d9bad3b4faa62196` | GREEN | GREEN | GREEN | GREEN | 15578 | 10 | 10 | 0 |

- R2 linux-py3.11: Q0 GREEN 51 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R2 linux-py3.12: Q0 GREEN 51 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R2 linux-py3.13: Q0 GREEN 51 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R2 linux-py3.14: Q0 GREEN 51 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R2 windows-py3.11: Q0 FAILED 48 pass, 3 fail, 0 n/a; Q1 NOT RUN (a lower rung was not GREEN on this platform); Q2 NOT RUN (a lower rung was not GREEN on this platform); Q3 NOT RUN (a lower rung was not GREEN on this platform)
- R3 linux-py3.11: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R3 linux-py3.12: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R3 linux-py3.13: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R3 linux-py3.14: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R3 windows-py3.11: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 178 pass, 0 fail, 13 n/a; Q3 GREEN 541 pass, 0 fail, 19 n/a
- R4 linux-py3.11: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R4 linux-py3.12: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R4 linux-py3.13: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R4 linux-py3.14: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 189 pass, 0 fail, 2 n/a; Q3 GREEN 559 pass, 0 fail, 1 n/a
- R4 windows-py3.11: Q0 GREEN 52 pass, 0 fail, 0 n/a; Q1 GREEN 396 pass, 0 fail, 0 n/a; Q2 GREEN 178 pass, 0 fail, 13 n/a; Q3 GREEN 541 pass, 0 fail, 19 n/a
- R2: FAILED on Windows (Q0 48/51: validation/qualification/v1_pf_001_policy.py repo_path); kept; V1 product tree `4359f347378e84fcac2d213128c7c26f282c13c0`; PRODUCT_AFFECTING `68f500984d2b0e8945df76247f54f56554966455b73259ed95b8dcdf7aa5d253`
- R3: GREEN; closed C2-P6 (9bd16fa); the candidate LANE-Q ran on; V1 product tree `4359f347378e84fcac2d213128c7c26f282c13c0`; PRODUCT_AFFECTING `68f500984d2b0e8945df76247f54f56554966455b73259ed95b8dcdf7aa5d253`
- R4: GREEN on the final candidate (LANE-Q + LANE-X); V1 product tree `4359f347378e84fcac2d213128c7c26f282c13c0`; PRODUCT_AFFECTING `68f500984d2b0e8945df76247f54f56554966455b73259ed95b8dcdf7aa5d253`

## 6. Final QP-2.6 identity

candidate `c11615aeb1dd9e6ff992b6190f8c39a272636742`; aisef2 `254d8f559b879c210c4936321022f1350c4b2f89`; validation/v2 `7686f004167fc5e940b06bf6ff0248f068d8d116`; tests/v2 `fb9d8e17728a893083575638d9bad3b4faa62196`; summary `f2ca0fcd064b0396224886742483d92a15668fa0a4f94e77e7f82a6759a114d6` GREEN

## 7. Mutation summary

`{"targets": 620, "total": 15578, "killed": 15568, "survivors": 10, "audited_survivors": 10, "unaudited_survivors": 0}`

## 8. The survivor audits

- `tests/v2/refmodel/story_state.py::_TABLE` L19 False->True: the third field (whether the target state is also the outcome) is read only when the target state is not None (model: `if to is not None: ... if is_outcome`); this entry's target is None
- `tests/v2/refmodel/story_state.py::_TABLE` L20 False->True: the third field (whether the target state is also the outcome) is read only when the target state is not None (model: `if to is not None: ... if is_outcome`); this entry's target is None
- `tests/v2/refmodel/story_state.py::_TABLE` L21 False->True: the third field (whether the target state is also the outcome) is read only when the target state is not None (model: `if to is not None: ... if is_outcome`); this entry's target is None
- `tests/v2/refmodel/story_state.py::_TABLE` L22 False->True: the third field (whether the target state is also the outcome) is read only when the target state is not None (model: `if to is not None: ... if is_outcome`); this entry's target is None
- `tests/v2/refmodel/story_state.py::_TABLE` L23 False->True: the third field (whether the target state is also the outcome) is read only when the target state is not None (model: `if to is not None: ... if is_outcome`); this entry's target is None
- `tests/v2/refmodel/budgets.py::model` L75 True->False: zip(strict=) over a four-name tuple and _walk's four-value return: the lengths are always equal, so strict never decides anything
- `tests/v2/refmodel/qualification_counters.py::metrics` L15 element 0 dropped: `pre` is read only through len(pre): a one-element tuple per entry counts the same
- `tests/v2/refmodel/qualification_counters.py::metrics` L15 element 1 dropped: `pre` is read only through len(pre): a one-element tuple per entry counts the same
- `tests/v2/refmodel/qualification_counters.py::model` L41 sorted() -> list(): `unplanned` is read only for truthiness and inside the refusal message
- `tests/v2/refmodel/qualification_counters.py::model` L44 sorted() -> list(): `misplaced` is read only for truthiness and inside the refusal message

## 9. Unaudited survivors

0

## 10. Q4 execution identity

- original: executed at `ac608c1128c0a7b6061277cf9a12c234d86aa545`, candidate named `37dc0dcdf819387b65ee60cf614273df94aaef31`, kernel `{"kernel_tree": "37bf6457f350dd720a2214f04f3896c554ad0904", "kernel_digest": "8e8f00ca9327599f850088181aa64fa8751d8405a5485d52faccb18fa8ef4d3d", "one_identity": "1a4309be81e5ecbd76881debdd52eca59f6640ec1e372999ec44ff4d3dcfa45e"}`, record `06fec168ddff676c880743365a50361bd56faf919456112df5398f788abfbf04`
- final: executed at `849b7e5092b2ecb690ef234939203f0dbe460d97`, candidate `c11615aeb1dd9e6ff992b6190f8c39a272636742`, kernel tree `254d8f559b879c210c4936321022f1350c4b2f89`, digest `f763b238d9e9c007937b959238feac9d54e6af7d9c1bb707cad1686640526908`, record `09e2e3e865e1614702851200a12d789115e5e76eae36b19164a675e798782801` GREEN, fresh: True, lower rung: `['closure-evidence/v2/cycle2/Q0-Q3-R4/SUMMARY.json']`

## 11. Q4 corrigendum audit

- consumed paths changed between the R3 candidate and execution: `[]`
- active probe digests equal to R3: True; pointer preserved: `['closure-evidence/v2/cycle2/Q0-Q3-R2/SUMMARY.json']`; corrigendum `1d529d4dad5c1f5e7faaaf9a89c0a999cef9e0779cc5310716b3f07c11808acd`
- DID THE ORIGINAL MEASUREMENT RUN ON THE SAME CONSUMED IDENTITIES AS THE QUALIFYING CANDIDATE? **YES** — PROVENANCE_POINTER_CORRECTION

## 12. Q5 execution identity

- original: executed at `7e1e94571784c371e7654111e6fdf79c51372dfe`, candidate named `37dc0dcdf819387b65ee60cf614273df94aaef31`, kernel `{"kernel_tree": "37bf6457f350dd720a2214f04f3896c554ad0904", "kernel_digest": "8e8f00ca9327599f850088181aa64fa8751d8405a5485d52faccb18fa8ef4d3d", "one_identity": "7497b610455cf4ca938499dbd296375d482561e2a69c98b2e86207fe34630608"}`, record `84396d361649eafdb7b7561526b920756109989976d38faaea67776a437b85f7`
- final: executed at `f3fb0c8b373426636732100a919c378780a34456`, candidate `c11615aeb1dd9e6ff992b6190f8c39a272636742`, kernel tree `254d8f559b879c210c4936321022f1350c4b2f89`, digest `f763b238d9e9c007937b959238feac9d54e6af7d9c1bb707cad1686640526908`, record `a5875285af8782b99f4fed42309467826086c12c4a05d4b83940479640b93186` GREEN, fresh: True, lower rung: `['closure-evidence/v2/cycle2/Q0-Q3-R4/SUMMARY.json']`

## 13. Q5 corrigendum audit

- consumed paths changed between the R3 candidate and execution: `[]`
- active probe digests equal to R3: True; pointer preserved: `['closure-evidence/v2/cycle2/Q0-Q3-R2/SUMMARY.json']`; corrigendum `1d529d4dad5c1f5e7faaaf9a89c0a999cef9e0779cc5310716b3f07c11808acd`
- DID THE ORIGINAL MEASUREMENT RUN ON THE SAME CONSUMED IDENTITIES AS THE QUALIFYING CANDIDATE? **YES** — PROVENANCE_POINTER_CORRECTION

## 14. Zero tool-result replay

Q5-FINAL `{"items": 12, "green": 12, "expected_model_calls": 31, "consumed_model_calls": 31, "tool_executions": 12, "tool_result_replays": 0, "subprocess_executions": 180, "socket_attempts": 0, "assert_consumed": true, "only_model_stream_replayed": true}`; Q4-FINAL `{"MATCHED": 100000, "DIVERGENCE": 0, "INVARIANT_VIOLATION": 0, "EXCEPTION": 0, "SILENT_SKIP": 0, "requested": 100000, "attempted": 100000, "terminal": 100000, "rows": 100000, "events": 5431248, "matched_with_refusal": 0, "prefix_traces": 10000}`

## 15. Orchestration exact diff

commits `['e3d0560e277024eeb31ddf54a95dba8fb41ae1b6', 'ac88f366f98e5d1f4e2859df1001d430bdb8364c']`
- `aisef2/orchestrate/story_runner.py`: ['StoryInputs', '_attempt', '_probe']
- `aisef2/orchestrate/proof.py`: ['Party', 'Party.__init__', 'Party.run', 'Proof', 'prove']
- the diff itself: `closure-evidence/v2/cycle2/C2-ORCHESTRATION-CHANGE-REVIEW.json` field `15_exact_diff` (125 lines)

## 16. Orchestration classification

**RETURNED FOR THE OWNER'S EXPLICIT RULING — not accepted here**
- reading of the evidence: consistent with ORCH-BUGFIX-NO-SEMANTIC-CHANGE except for the one disclosed journal difference on a misconfiguration failure path; whether that difference is a semantic change is the Owner's ruling
- no frozen item, protocol, event type, payload field, enum, disposition, routing table, budget or projection module changed (item 8, byte/AST evidence)
- single-kind stories behave identically under both kernels: the seven Cycle-1 corpus journals (C2-ORCHESTRATION-CONFORMANCE-REPAIR.json), and three single-kind paths measured here including two misconfigurations — identical
- a multi-kind story: old InvariantError after a developer request; new COMMIT with one proof per obligation
- ONE path differs in what is journaled, with the same outcome, failure code, owner, retryability and detail: the post-merge re-proof of a prior story's spec whose probe kind the current harness did not wire. Old: the story's single (wrong-kind) probe was run on that spec — two probe/evaluated InvalidSpec records and a proof/verified with no verdict — then PROBE_INVALID_SPEC. New: nothing is measured, no record, no proof/verified, then PROBE_INVALID_SPEC. Events for the story: {"old": 37, "new": 34}

## 17. Mixed-probe adversarial evidence

- cannot skip: Parties.test_a_party_without_the_spec_s_probe_runs_nothing_and_makes_no_record
- cannot skip: Parties.test_prove_types_a_party_without_the_spec_s_probe_as_PROBE_INVALID_SPEC_and_seals_nothing
- cannot skip: OneProofPerObligation.test_7_one_INVALID_SPEC_among_READY_is_PROBE_INVALID_from_the_real_probe_or_from_an_unwired_one
- cannot skip: ReproofOfAnotherKind.test_a_prior_spec_whose_probe_the_harness_did_not_wire_is_PROBE_INVALID_SPEC_never_a_crash
- cannot skip: MixedStory.test_8_each_obligation_has_its_own_candidate_records_binding_its_spec_probe_and_candidate
- cannot skip: MixedStory.test_11_no_evaluation_is_shared_two_specs_of_one_kind_and_one_spec_under_two_obligations_each_run
- cannot substitute: OneProofPerObligation.test_10_one_failing_candidate_spec_is_not_masked_by_the_others_passing
- cannot substitute: MixedStory.test_9_each_obligation_has_its_own_verified_proof_citing_its_two_records
- cannot substitute: Parties.test_the_runner_resolves_the_factory_of_the_spec_s_own_probe_identity_or_none
- after tests: `["Ran 23 tests in 123.897s", "OK"]`; generality: the lookup is inputs.probes.get(spec.probe_id): any set of registered probes; the tests use synthetic two- and three-kind stories, permuted orders, and the four LedgerLock stories only as one case

## 18. The six failed-story classifications

| story | class | parent | candidate | gate | retries | developer requests |
|---|---|---|---|---|---|---|
| STORY-01-01 | D DEVELOPER_OR_MODEL_EXECUTION_FAILURE | `136a68dcdc3f416b2a76c561a7df12d1282ad4d5` | `1ff84a73cf0f663f8c4d2759054457d7a3cfcebf` | SUBJECT_ABSENT_AT_CANDIDATE / DEVELOPER; CONTRACT_UNSATISFIED / DEVELOPER | 1 | 2 |
| STORY-02-01 | A FRAMEWORK_KERNEL_DEFECT | `800b085d6417d1b6be343534055b91668d789a98` | `800b085d6417d1b6be343534055b91668d789a98` | TESTS_INADEQUATE / DEVELOPER; TESTS_INADEQUATE / DEVELOPER | 1 | 0 |
| STORY-02-02 | A FRAMEWORK_KERNEL_DEFECT | `800b085d6417d1b6be343534055b91668d789a98` | `800b085d6417d1b6be343534055b91668d789a98` | TESTS_INADEQUATE / DEVELOPER; TESTS_INADEQUATE / DEVELOPER | 1 | 0 |
| STORY-04-01 | D DEVELOPER_OR_MODEL_EXECUTION_FAILURE | `d2f3ed2f4240956748e87983ca964c1af7d0524c` | `None` | PRECONDITION_BROKEN / PLAN | 0 | 0 |
| STORY-05-01 | C BENCHMARK_SPECIFIC_HARNESS_CONFIGURATION | `1efcb8cf723c4c4ca08de00de4b396dabf138247` | `de9cefcc1df7ea36f2187996dbfb055c2bf65142` | TESTS_INADEQUATE / DEVELOPER; TESTS_INADEQUATE / DEVELOPER | 1 | 2 |
| STORY-05-03 | D DEVELOPER_OR_MODEL_EXECUTION_FAILURE | `1efcb8cf723c4c4ca08de00de4b396dabf138247` | `None` | PRECONDITION_BROKEN / PLAN | 0 | 0 |

- **STORY-01-01**: the developer did not create ledgerlock/ledger.py in attempt 1 (S-10-b: SUBJECT_ABSENT_AT_CANDIDATE) and, in attempt 2, wrote `from collections.abc import Iterable, Iterator` in ledgerlock/ledger.py (S-10-a: CONTRACT_UNSATISFIED) — requirement §10 lists the allowed modules and `collections` is not one. The kernel proved each obligation by its own probe, typed both failures DEVELOPER / retryable, retried once within the DEVELOPER limit and rolled back. Contributing, not primary: the epics write_scope of Story 1.1 does not name ledger.py while PLAN-V2.2 places R-10/2 and R-13/1 over it on this story (the prompt carried both).
- **STORY-02-01**: admitted fully PRE_SATISFIED (STORY-01-05's developer had implemented `verify`): developer_call_permitted false, no developer request, candidate = parent, plan-drift emitted, the obligation's VerifiedProof SATISFIED with agreement — everything RFC §14 and §17 name for a story that 'ends STORY_ALREADY_SATISFIED'. The engineering-adequacy stage then ran over a story no developer had been asked to work on: the story-owned test file the harness declares (tests/test_<story>.py) does not exist, which the kernel typed STORY_TESTS_NOT_COLLECTABLE, developer-caused, relevance IRRELEVANT -> INADEQUATE, owner DEVELOPER, developer_chargeable true; under the blocking tests policy that is TESTS_INADEQUATE (DEVELOPER, retryable): one retry charged to the DEVELOPER budget — with no developer call possible, so the retry repeated the same events — then ROLLBACK. The reproducer in this record shows the same rollback and the same charged retry when the story's tests DO exist and pass at the parent (VACUOUS and IRRELEVANT, because the product diff is empty), so the harness's test-path convention is not the cause: under TestsPolicy(blocking=True) a fully PRE_SATISFIED story does not commit, whether its tests are absent (LedgerLock) or present and passing (reproducer). RFC §14: a PRE_SATISFIED obligation MUST 'consume no developer budget' and 'MUST NOT require that correct code be made incorrect' (the only way to make the tests non-vacuous here); §17: 'a commit MUST NOT depend on a developer test verdict'; §15.3 lets a project make INADEQUATE block. The blocking stance is the benchmark harness's choice (no shipped default exists); the defect is the kernel's handling of that permitted stance on a story §14 says ends already satisfied. Two other readings exist and are the Owner's to weigh: C (the stance is qualification-profile-specific and a non-blocking stance commits the story) and E (the RFC does not say how §15.3 applies to a story with no developer call). This record takes A because a legal policy value makes the kernel contradict a §14 MUST, and the ruling forbids choosing the convenient class.
- **STORY-02-02**: admitted fully PRE_SATISFIED (STORY-01-05's developer had implemented `snapshot`): developer_call_permitted false, no developer request, candidate = parent, plan-drift emitted, the obligation's VerifiedProof SATISFIED with agreement — everything RFC §14 and §17 name for a story that 'ends STORY_ALREADY_SATISFIED'. The engineering-adequacy stage then ran over a story no developer had been asked to work on: the story-owned test file the harness declares (tests/test_<story>.py) does not exist, which the kernel typed STORY_TESTS_NOT_COLLECTABLE, developer-caused, relevance IRRELEVANT -> INADEQUATE, owner DEVELOPER, developer_chargeable true; under the blocking tests policy that is TESTS_INADEQUATE (DEVELOPER, retryable): one retry charged to the DEVELOPER budget — with no developer call possible, so the retry repeated the same events — then ROLLBACK. The reproducer in this record shows the same rollback and the same charged retry when the story's tests DO exist and pass at the parent (VACUOUS and IRRELEVANT, because the product diff is empty), so the harness's test-path convention is not the cause: under TestsPolicy(blocking=True) a fully PRE_SATISFIED story does not commit, whether its tests are absent (LedgerLock) or present and passing (reproducer). RFC §14: a PRE_SATISFIED obligation MUST 'consume no developer budget' and 'MUST NOT require that correct code be made incorrect' (the only way to make the tests non-vacuous here); §17: 'a commit MUST NOT depend on a developer test verdict'; §15.3 lets a project make INADEQUATE block. The blocking stance is the benchmark harness's choice (no shipped default exists); the defect is the kernel's handling of that permitted stance on a story §14 says ends already satisfied. Two other readings exist and are the Owner's to weigh: C (the stance is qualification-profile-specific and a non-blocking stance commits the story) and E (the RFC does not say how §15.3 applies to a story with no developer call). This record takes A because a legal policy value makes the kernel contradict a §14 MUST, and the ruling forbids choosing the convenient class.
- **STORY-04-01**: refused at StoryAdmission, owner PLAN, not retryable, no developer call: PRECONDITION_BROKEN on the PRESERVE obligation AC-STORY-04-01-2:S-9-b (R-9/2, exit 2 on a usage error) — the behaviour STORY-01-01 was to introduce and, rolled back, did not. Derivative of STORY-01-01's developer failure; the kernel refused fail-closed as RFC §13/§14 require (a hard plan blocker).
- **STORY-05-01**: the developer wrote only tests/test_story_05_01.py in both attempts (the story's deliverable is a property test; its two obligations are both PRESERVE, READY at the parent: the plan asks this story for no new product behaviour). With no product hunk, vacuity is VACUOUS and relevance IRRELEVANT as RFC §15.1/§15.2 define them, so the assembly is INADEQUATE (DEVELOPER, may block), and the benchmark harness's blocking tests policy rolled the story back after one retry. The kernel followed §15 to the letter; no RFC MUST is contradicted (the developer was called and charged). The blocking policy is the qualification harness's own choice.
- **STORY-05-03**: refused at StoryAdmission, owner PLAN, not retryable, no developer call: PRECONDITION_BROKEN on the PRESERVE obligation AC-STORY-05-03-1:S-10-a (R-10/1, standard library only, allowed modules) — STORY-01-01's obligation, not holding at the parent. Derivative of STORY-01-01's developer failure; refused fail-closed.

## 19. The ProductProof-SATISFIED-but-test-blocked stories

3 stories, not two: STORY-02-01, STORY-02-02, STORY-05-01.
- STORY-02-01: tests `[{"outcome": "INADEQUATE", "owner": "DEVELOPER", "may_block": true, "developer_chargeable": true, "vacuity": "INDETERMINATE", "relevance": "IRRELEVANT", "selection": "STORY_TESTS_NOT_COLLECTABLE", "execution": "tests/test_story_02_01.py could not be collected: import of 'tests.test_story_02_01' failed: the project's own source tree", "regressions": "7 story-owned test(s) ran; 0 failed"}]`
- STORY-02-02: tests `[{"outcome": "INADEQUATE", "owner": "DEVELOPER", "may_block": true, "developer_chargeable": true, "vacuity": "INDETERMINATE", "relevance": "IRRELEVANT", "selection": "STORY_TESTS_NOT_COLLECTABLE", "execution": "tests/test_story_02_02.py could not be collected: import of 'tests.test_story_02_02' failed: the project's own source tree", "regressions": "7 story-owned test(s) ran; 0 failed"}]`
- STORY-05-01: tests `[{"outcome": "INADEQUATE", "owner": "DEVELOPER", "may_block": true, "developer_chargeable": true, "vacuity": "VACUOUS", "relevance": "IRRELEVANT", "selection": "STORY_TESTS_RAN", "execution": "9 story-owned test(s) ran; 0 failed", "regressions": "61 story-owned test(s) ran; 0 failed"}]`
- reproducer without LedgerLock: `{"non_blocking_commits": true, "blocking_rolls_back": true, "blocking_charges_a_developer_retry_with_no_developer_call": true, "the_proofs_are_satisfied_in_both": true}`
- history: the behaviour is Cycle-1 kernel code (WP-6.2), unchanged in Cycle 2; the three tests found that run a fully PRE_SATISFIED story all set the non-blocking stance, so QP-2.9 is the first recorded execution of the path under a blocking one

## 20. Is any failure a shipped/default harness defect

no shipped default exists: the kernel requires the caller to state the stance, constructs none itself, and aisef2 is not in the published wheel (the public `aisef` command is V1). The blocking stance of QP-2.9 is set in validation/qualification/c2_p9.py only
class B stories: 0

## 21. LedgerLock delivery

FAIL — outcomes `{"STORY-01-01": ["RETRY", "ROLLBACK"], "STORY-01-05": ["RETRY", "COMMIT"], "STORY-02-01": ["RETRY", "ROLLBACK"], "STORY-02-02": ["RETRY", "ROLLBACK"], "STORY-03-01": ["COMMIT"], "STORY-04-01": ["ROLLBACK"], "STORY-04-02": ["RETRY", "COMMIT"], "STORY-05-01": ["RETRY", "ROLLBACK"], "STORY-05-03": ["ROLLBACK"]}`

## 22. plan_quality

NOT_CLAIMED

## 23. generalization

NONE; workload class DEVELOPMENT_REGRESSION

## 24. Attempt-1 NO-RECORD (HARNESS)

`closure-evidence/v2/cycle2/P10/NO-RECORD.json` sha256 `98677079fd68c2f21d5d259fba7041c65fde62d4f0c1896396c1482d4fbe529e` — unchanged

## 25. Attempt-2 identity

`{"record": {"path": "closure-evidence/v2/cycle2/P10/attempt-2/LEDGERLOCK-REGRESSION.json", "sha256": "b4ad12f52a061d6a1726304416f3809eed7c065a1c962201a341a079bb8f2ff7"}, "execution_commit": "1f992baa55c28caf8be0c059aa081806bc931b1b", "kernel_tree": "37bf6457f350dd720a2214f04f3896c554ad0904", "journal": {"path": "closure-evidence/v2/cycle2/P10/attempt-2/JOURNAL.json", "sha256": "eda76b7b07ef01596066aab62f15a61443a98607a259fb4d0f453bf5f35250ff"}, "runspec_hash": "4278bd29f717ea047cad14c77b5df88d8850932c737c99d6b1e23d7138eb4c39"}`

## 26. C2-P10 result

`{"cohort_count": 0, "cohort_verdict": "machinery qualified; cohort count = 0", "profile_verdict": "attestation qualified", "live_provider_calls": 0, "workload_selected": false, "cohort_sealed": false}`

## 27. Cohort count

0

## 28. Provider-call count (C2-P10)

0

## 29. History digests

| history | entries | last seq | full history digest | status |
|---|---|---|---|---|
| C2-P0 | 82 | 82 | `93b16417f93db0f6c1444cb358fc48c2ba67137b9621e6b0ba03f8291baf0be0` | SEALED (existing mechanism, earlier ruling) |
| C2-P1 | 15 | 15 | `62780ca2c75f63f0db9f2cd37b64a89961c05a2dd45101aaf819ce9ea743ca8a` | SEALED (existing mechanism, earlier ruling) |
| C2-P2 | 36 | 36 | `9359e5b5a21fcdcba187339f20a3627b933379f884e467811435819ae035e84b` | SEALED (existing mechanism, earlier ruling) |
| C2-P3 | 15 | 15 | `4c29906d98c1b8012b867819dc94bad9824fb8081d3d53d900f1b13cd9948769` | SEALED (existing mechanism, earlier ruling) |
| C2-P4 | 15 | 15 | `5c93dacd54b3248d35af56b7b6b5524f98787ef2d4f49f9708bfd228cbbc59e0` | SEALED (existing mechanism, earlier ruling) |
| C2-INTEGRATION | 17 | 17 | `9be9413ac9d216994d571390562b88a6900d4802a9d7a9ad426529ca9e86240b` | SEALED (existing mechanism, earlier ruling) |
| C2-P5 | 32 | 32 | `a2fa54603e0b5ed847f509ae2ccd4c88c7396a670b52b857984a82fdeb2d41af` | SEALED (existing mechanism, earlier ruling) |
| C2-P6 | 47 | 47 | `112453c0e38cc1b49731b4a49f5d558d0225bd589b9c78281943db241edb05cd` | SEALED (existing mechanism, earlier ruling) |
| C2-P7 | 19 | 19 | `6f27fe66c2e057de23b5f4f6116ff3b2e24b518886c88f9fec417e0329ccce99` | FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL |
| C2-P8 | 3 | 3 | `55e6cd997df97664176a904aed763be13e343fb37eb1ab3e08ba3d7afb564b80` | FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL |
| C2-P9 | 2 | 2 | `42c62c8020533205a93da534df0940fe127977d3e59fb445878d42dcc93de60d` | FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL |
| C2-P10 | 2 | 2 | `74bd5bf5ac3e8e42629e6f85526f98110b7c8e2294953b2d22036bb6cb1fcd34` | FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL |
| C2-FINAL | 43 | 43 | `7bbee75ae25b3ac10b44e791a9d09c34451bb7591623e3d88a0a76b106f79dc4` | FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL |

## 30. History freeze/seal mechanism

existing mechanism usable without changing assurance semantics: NO
- registering a seal is an edit of validation/v2/run_history.py: the validation/v2 tree is an identity QP-2.6 consumed (R4), so the edit would move the qualified candidate
- every Cycle-2 seal so far is an Owner acceptance or a closure written under an Owner ruling; no acceptance of C2-P7..C2-P10 or of the final candidate exists yet to seal against
- used instead: `closure-evidence/v2/cycle2/C2-HISTORY-FREEZE-CANDIDATE.json`, status FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL; mandatory-seal source found: None

## 31. cycle2_baseline

exit 0 ['cycle-2 baseline guard: PASS']

## 32. F1-F11

exit 0 ["summary {'PASS': 11, 'PENDING': 0, 'FAIL': 0} | ratchet violations 0"]

## 33. V1 guard

exit 0 ['V1 evidence guard (DETECTIVE): PASS']

## 34. Cycle-1 drift

`{"probe_id": "probe.python_callable", "catalog_digest": "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf", "module_digest": "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf", "active": false, "active_for_kind": "probe.python_callable_v2", "frozen": "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf", "ok": true}`

## 35. Residual processes

0

## 36. Escaped processes

0

## 37. Release blockers

- **FRAMEWORK_KERNEL_DEFECT (the evidence's reading; class A)**: a fully PRE_SATISFIED story under a blocking tests policy is rolled back and charged a DEVELOPER retry with no developer call (RFC §14 vs §15.3); reproduced without LedgerLock
- **ORCHESTRATION CHANGE CLASSIFICATION PENDING**: returned for the Owner's explicit ruling; one journal difference on a misconfiguration failure path is disclosed
- **PACKAGING (a fact, not a Cycle-2 defect)**: pyproject.toml excludes aisef2* from the wheel; version 1.7.6: a release from this tree ships no V2 code
- acceptance test failing: `['no FRAMEWORK_KERNEL_DEFECT release blocker', 'working tree clean']`; pending the Owner: `['no unapproved orchestration semantic change']`

## 38. PR #6

`{"baseRefName": "master", "headRefName": "hardening/systematic-v1", "headRefOid": "3ed2c41126e27d1a6b04e5442b56bbf3b6d89f11", "isDraft": true, "mergedAt": null, "state": "OPEN"}`

## 39. master

`671ef9b259c560bf07531bc5fed63b07dc28b323`

## 40. Conclusion

The audit stopped before closure acceptance: the ruling's conclusion is not stated.
No benchmark result was tuned or rewritten. LedgerLock delivery remains FAIL and DEVELOPMENT_REGRESSION. No generalization claim is made. No cohort has been selected or sealed. PR #6 remains unmerged. No public release has been performed.
An Owner ruling on the release blocker and on the orchestration classification is required.

