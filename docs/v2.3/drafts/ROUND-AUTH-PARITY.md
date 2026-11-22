# ROUND-AUTH parity — the evidence for ledger seq 13 (draft R5; R4, R3 and R2 superseded), items 1–9

Owner status: **CONDITIONAL HOLD**. The principle of a separate v2.3 qualification round is approved. The seq 13 draft
is not authorized for the ledger. This page is the evidence the owner asked for before any ratification request. It
is a draft and authorizes nothing.

Code commit: `f237ad14` on `v23/roundauth`, based on `release/v2.3-big` at `1e25ef84`; review-finding fix commit
`5a0b1c24` (§7); Q0-1 commit `860dcbe6` (§8, the distinct v2.3 Q0 round, draft R4) on top of `0a034025`; Q0-1
review-fix commit `29c40b07` (§9, draft R5) on top of `860dcbe6`.
v2.2.0 = `da3ea33f3b695aaca73e87a704145a0193aced23`.

**What R5 supersedes (§9).** R5 supersedes R4: the current draft is `LEDGER-SEQ-13-DRAFT-R5.md` with
`SEQ13-WIRING-R5.patch`. R4 and its patch (`a0f79fc1…`) must not be ratified or applied. Five review findings against
R4 were each reproduced by a verifier and are fixed fail-closed in `29c40b07`; §8 is kept as measured history.

**What R4 superseded (§8).** R4 superseded R3: the current draft is `LEDGER-SEQ-13-DRAFT-R4.md` with
`SEQ13-WIRING-R4.patch`. R3 and its patch (`40e6b57a…`) must not be ratified or applied. The R3 rows of §4b and §7 are
kept as measured history. Their mechanisms (the pins and the round check) carry over to R4 unchanged, extended by Q0.
Host for every measurement: Darwin 25.5.0 arm64, CPython 3.14.7, git 2.53.0.

Evidence, all new files under `docs/v2.3/evidence/round-auth/`. Each was written once with `open(…, "x")` and
carries no local path.

**Placement finding (for the integrator).** The evidence was first committed under `closure-evidence/v2.3/round-auth/`,
as Amendment A2 directs (`80046dbe`). That location is inside the V1 evidence guard's protected set:
`validation/v2/v1_evidence_guard.py` protects every tracked file under `closure-evidence/` except `closure-evidence/v2/`.
Measured at `80046dbe`:
* `tests/v2/test_v1_evidence_guard.py::Detective.test_repository_matches_the_baseline` FAILS ("committed addition to
  protected evidence", 4 files);
* Q0 regenerates as 56/57 (`v1_evidence_guard` not calibrated), so the Q0 record is no longer byte-identical.

The next commit moves the four files, bytes unchanged, to `docs/v2.3/evidence/round-auth/`, beside W1a's
`docs/v2.3/evidence/F5-*`. Q0 is re-measured there in §5. **Any track that follows A2 literally hits the same red.**
The integrator decides the final location; the guard is not touched.

| File | sha256 | Item |
|---|---|---|
| `REPLAY-V22-2026-11-21.json` | `e7ef54c745b35ae709cc6fd591e9a42767899956defc4db1688c4ac48f33f8ae` | 2 |
| `COVERAGE-MAP-2026-11-21.json` | `2bb5b5501b7ab966cef61ca13ca5bbbe4c40f9692284bce037e21ef4e9bd8c8d` | 3 |
| `NEGATIVE-CONTROLS-2026-11-21.json` | `15087001cd877db180ea51f72be8db7b34aa103b99ac3fd4ea0e7ee013270969` | 4 |
| `HISTORY-IDENTITY-2026-11-21.json` | `cc18861af3712821335c16ebbdc31604cef974d7006f726ab840dad2d9dad91f` | 5 |
| `docs/v2.3/drafts/SEQ13-WIRING.patch` (R2's; not applied; **must not be applied**, RA-GP-1) | `c5bfc527182c9f5969532630b680b98e746c867ebf351e28e3b5c4e5c2bbd68b` | 4b |
| `docs/v2.3/drafts/SEQ13-WIRING-R3.patch` (R3's; not applied) | `40e6b57adff814933c863c14b3e32a413b5f7b79a8bf0d187889e5635ea1cca5` | 7 |

Tools: `validation/v23/replay_v22.py` (sha256 `3414936eac1e1b70ef626c12b1348f8c2d2c90041980bdb743e5a6ff8fcf9a46`,
LF), `validation/v23/ledger_digest.py`. Tests: `tests/v23/test_v23_rounds.py` (sha256
`62061facbc0f49335991165e44c73fb4eb48a673faf10ebf8ea688691d1e32d3` at `f237ad14`, measured in items 1–6;
`79433cacb80ba7abf9234dfaaac39c996486ea745b2a1849f3a619aa2aa56620` at `5a0b1c24`, the bytes the R3 patch pins),
`tests/v23/test_v23_replay_v22.py`, `tests/v23/test_v23_ledger_digest.py`, `tests/v23/test_v23_seq13_wiring.py` (§7). The scratch harnesses of items 4 and 5 are not committed; the evidence files
carry their sha256.

## 1. The 11 v2.2-round sealing-gated tests and what each enforces

They are the ids of `replay_v22.V22_REPLAYED`, and each is in `tests/v2/sealing_gate.py` GATED (W1-DESIGN §2.6,
"Replayed at v2.2.0 (11)"). The other 7 GATED entries keep running at HEAD, as §2.6 states. All 18 files are
byte-identical at HEAD (`COVERAGE-MAP` `byte_identical_at_head`).

| # | Test | Node | What it enforces |
|---|---|---|---|
| 1 | `test_c2_delivery_experiment.py::PlanCorrection.test_the_committed_record_is_what_this_tree_derives` | PLAN | `c2_plan_correction.check_v22()`: selects the v2.2 record bound to (round v2.2, HEAD:aisef2), re-derives it and requires exact render equality. Also: the derived verdict is `PLAN CORRECTION ADMITTED STATICALLY`; the 2.0 record is history (its v2.0.0 blob); the committed 2.0 verdict. |
| 2 | `test_c2_k_nowork_001.py::Record.test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after` | K-NOWORK | `check_v22()`: the rehearsal record binds this tree (BOUND bytes + kernel content digest). BOUND includes the v2.1 plan correction. The 2.0 record is history. |
| 3 | `test_c2_orchestration_conformance.py::Record.test_15_…` | ORCH | `release_differences_v22()`: only the release's named changes, each by content through the v2.2 CONFORMANCE-RULING. Plus the frozen cycle-2 record's facts: 7 items, 6 identical; the pre-satisfied story differs by exactly the adequacy stage; the defect reproducer (old raised, new commits). |
| 4 | `test_c2_p10_cohort_static.py::Record.test_the_evidence_record_re_derives_from_the_tree` | P10-COHORT | `check_version_forward()`: the record re-derives, including the census of every `*.json`/`*.jsonl` (cohort count 0). Also: verdict; every adversarial case holds; `problems_of` rejects a broken one. |
| 5 | `test_c2_p10_profile_freeze.py::Checker.test_the_evidence_record_re_derives` | P10-PROFILE | `check_version_forward()`: the record re-derives. Verdict `attestation qualified`, 0 live provider calls, the six FIX-* grades. |
| 6 | `test_c2_p5_acceptance.py::Acceptance.test_the_acceptance_re_derives_on_this_tree` | P5-REVERIFICATION | The owner's 2.0 acceptance is intact as history. The v2.2 reverification re-derives, with its P5-FALSIFIABILITY and P5-PROPOSAL upstreams resolved for round v2.2. |
| 7 | `test_c2_p5_acceptance.py::KernelProvenance.test_on_this_tree_the_committed_proposal_is_current` | P5-PROPOSAL | `check_v22_proposal()`: the v2.2 proposal is exactly current. The 2.0 proposal is history. |
| 8 | `test_v21_mutation_runner.py::Classify.test_historical_records_read_as_before` | (MUTATION, not a DAG node) | For the 8 historical phases (P1–P6, C2-ORCH, C2-P10): no runner-2 entry, and the legacy rule `problems_of` holds: complete, phase-consistent, source unchanged (whole file), mutants > 0, survivors audited. Also: V2.1 refuses a non-classifying runner. |
| 9 | `test_p5_plan_v22_proposal.py::Record.test_P5_8_committed_record_is_current` | P5-PROPOSAL | Proposal history intact and the v2.2 proposal current. The authoring aid's `check()` finds only the two expected history-stale messages. No approval given; no decision-3 mapping approved. |
| 10 | `test_p9_reproduction.py::KernelComparison.test_Q5_19_the_kernel_comparison_record_binds_this_tree` | Q5 | `check_v22()`: the comparison binds `q5.py`, the tool, the fixtures and both kernels' content digests. |
| 11 | `test_v21_conformance_ruling.py::CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives` | CONFORMANCE-RULING | `check_version_forward()`: the v2.2 ruling re-derives (rows bound by LF sha). Also: the v2.1 ruling is committed as it is. |

## 2. Replay at v2.2.0: all 11 PASS

`python3 -P validation/v23/replay_v22.py --tree <v2.2.0 worktree> --out …/REPLAY-V22-2026-11-21.json`, run at
2026-11-21T11:02:09Z.

**Preflight.** The tree must be exactly `da3ea33f`, with no tracked, untracked or ignored file. Each id must be in that
tree's own GATED list.

**How each test runs.** Each test runs alone under the tree's own `validation/v2/owned_run.py`, with
`AISEF_SEALING=1` and the env guard:
* no PATH directory holding `opencode`;
* XDG data/state/cache in scratch;
* no PYTHONPATH and no other AISEF_* variable;
* no bytecode written.

**Verdict `PASS`.** Every test ran 1, skipped 0, with owned_run exit 0, 0 residual processes and the range released
empty. Every record a test opened equals its v2.2.0 committed bytes (4,583 record reads in total). The tree was still
clean afterwards.

| # | Test | Outcome | Ran / skipped | Duration (s) | Records read |
|---|---|---|---|---|---|
| 1 | PlanCorrection | PASS | 1 / 0 | 0.84 | 14 |
| 2 | K-NOWORK Record | PASS | 1 / 0 | 0.36 | 5 |
| 3 | ORCH test_15 | PASS | 1 / 0 | 5.05 | 35 |
| 4 | P10-COHORT Record | PASS | 1 / 0 | 13.32 | 4,428 (the census) |
| 5 | P10-PROFILE Checker | PASS | 1 / 0 | 1.35 | 4 |
| 6 | P5 Acceptance | PASS | 1 / 0 | 1.03 | 21 |
| 7 | P5 KernelProvenance | PASS | 1 / 0 | 0.45 | 11 |
| 8 | Classify historical | PASS | 1 / 0 | 0.31 | 9 |
| 9 | P5_8 | PASS | 1 / 0 | 0.52 | 11 |
| 10 | Q5_19 | PASS | 1 / 0 | 0.82 | 16 |
| 11 | CommittedRuling | PASS | 1 / 0 | 4.95 | 29 |

The evidence file holds each test's tree commit and aisef2 tree (`e865d65c…`), wall time, owned_run summary, log
sha256, and the path + sha256 of every record read.

**Declared limit.** The read set is the test process's `open` audit events. Child processes and `git show` reads are
not listed. They stay covered by the test's own verdict and by the clean-tree rule.

Other replays of the same 11:
* The same 11 also PASS at HEAD today: `f237ad14`'s parent `d522dd84`, kernel unchanged since v2.2.0, 11 tests in
  25.4 s. They turn red only when W1a/W1b edit the kernel or the ruling rows (W1-DESIGN §2.6; not measured here).
* The gated `RoundV23.test_replay_v22` (fresh `git clone --shared` at v2.2.0) also passed in the
  `AISEF_SEALING=1` run of `tests/v23/test_v23_rounds.py` at the first code commit.

## 3. Historical control → its enforced v2.3 counterpart (assertion level)

**The pairing.** Each replayed test keeps its control twice:
* history: the test itself, at v2.2.0 (item 2);
* round v2.3: `tests/v23/test_v23_rounds.py::RoundV23.<counterpart>` (map in `replay_v22.COUNTERPART`).

**What a counterpart does.** It runs the same assertions verbatim inside `version_forward.in_round("v2.3")`, where each
node's own check selects the verified head of its chain (W1-DESIGN §2.6). Before them, it asserts three things:
* **(i)** the round is open: ledger seq 13 `AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED` is committed by `human:owner`
  (since §7: exactly one, whose ruling digest is the reviewed draft R3's, with the owner's words quoting it);
* **(ii)** the round-v2.3 selection exists: `vf.in_round` and `currency_dag.validate(round=)`;
* **(iii)** the node's round-v2.3 state is MEASURED or VERIFIED_REUSE.

**The rebound assertion.** Only one assertion is not round-aware: the legacy whole-file mutation rule
`m.problems_of(record, ROOT, phase)`. It is rebound to `self.f5_problems(m, record, phase)`, which keeps every legacy
problem except the whole-file source rule ("target changed since the mutation run — re-run it"). It also requires
each live entry of the record to be MEASURED or VERIFIED_REUSE in the F5 engine (`validation/v23/impact.classify`,
W1-DESIGN §2.3).

**Measured map** (`COVERAGE-MAP-2026-11-21.json`, AST of each test's v2.2.0 blob against the counterpart AST):
40 assertions, 39 verbatim, 1 rebound, 0 gaps.

**Always-run guards.**
* `Coverage.test_every_v22_assertion_has_its_counterpart` re-checks this map on every branch.
* `Coverage.test_a_dropped_assertion_is_a_gap` shows a removed assertion is caught.
* `Coverage.test_the_counterpart_map_is_closed` and `Coverage.test_the_round_gate_list_is_closed` are AST closures
  over `round_gate` ↔ `V23_GATED`, the round's own closed list.

| v2.2 # | v2.2 line | v2.2 assertion | Kind | Counterpart assertion | Covered |
|---|---|---|---|---|---|
| 1 | 62 | `self.assertEqual(pc.check_v22(), [])` | verbatim | same | yes |
| 1 | 63 | `self.assertEqual(pc.record_v22(self.b)['verdict'], 'PLAN CORRECTION ADMITTED STATICALLY')` | verbatim | same | yes |
| 1 | 64 | `self.assertEqual(pc.history_problems(), [])` | verbatim | same | yes |
| 1 | 65 | `self.assertEqual(json.loads((ROOT / pc.OUT_REL).read_text(encoding='utf-8'))['verdict'], 'PLAN CORRECTION A...` | verbatim | same | yes |
| 2 | 261 | `self.assertEqual(kn.check_v22(), [])` | verbatim | same | yes |
| 2 | 262 | `self.assertIn('closure-evidence/v2/v2.1/PLAN-V2.2-CORRECTION-1.json', kn.BOUND)` | verbatim | same | yes |
| 2 | 263 | `self.assertEqual(kn.history_problems(), [])` | verbatim | same | yes |
| 3 | 732 | `self.assertEqual(rp.release_differences_v22(), [])` | verbatim | same | yes |
| 3 | 736 | `self.assertEqual((eq['items'], eq['identical'], staged), (7, 6, ['pre-satisfied']))` | verbatim | same | yes |
| 3 | 737 | `self.assertTrue(all((v['outcomes_identical'] for v in eq['by_item'].values())))` | verbatim | same | yes |
| 3 | 738 | `self.assertEqual(sorted((i for i, v in eq['by_item'].items() if not v['journal_identical_but_kernel_identit...` | verbatim | same | yes |
| 3 | 740 | `self.assertEqual(k['removed_from_the_old_journal'], {'story/resource-acquired': 3, 'tests/adequacy': 1, 'st...` | verbatim | same | yes |
| 3 | 742 | `self.assertEqual(k['adequacy_stage_events_in_the_new_journal'], {})` | verbatim | same | yes |
| 3 | 743 | `self.assertTrue(k['journal_identical_but_kernel_identity_and_the_adequacy_stage'])` | verbatim | same | yes |
| 3 | 744 | `self.assertTrue(k['subprocesses_identical_but_the_tests_of_the_stage'] and k['other_observations_identical_...` | verbatim | same | yes |
| 3 | 745 | `self.assertEqual((k['subprocesses']['old']['tests'], k['subprocesses']['new']['tests']), (3, 0))` | verbatim | same | yes |
| 3 | 747 | `self.assertEqual(old['raised'], 'InvariantError: cycle 1 proves a story with exactly one probe factory')` | verbatim | same | yes |
| 3 | 748 | `self.assertEqual((new['raised'], new['attempts']), (None, ['COMMIT']))` | verbatim | same | yes |
| 4 | 104 | `self.assertEqual(B.check_version_forward(), [])` | verbatim | same | yes |
| 4 | 106 | `self.assertEqual((rec['verdict'], rec['census']['cohort_count'], rec['census']['cohort_records']), ('machin...` | verbatim | same | yes |
| 4 | 108 | `self.assertTrue(all((c['holds'] for c in rec['adversarial'])))` | verbatim | same | yes |
| 4 | 111 | `self.assertTrue(B.problems_of(broken))` | verbatim | same | yes |
| 5 | 200 | `self.assertEqual(B.check_version_forward(), [])` | verbatim | same | yes |
| 5 | 202 | `self.assertEqual((rec['verdict'], rec['live_provider_calls']), ('attestation qualified', 0))` | verbatim | same | yes |
| 5 | 203 | `self.assertEqual({c['id']: c['grade'] for c in rec['classifications'] if c['id'].startswith('FIX-')}, {'FIX...` | verbatim | same | yes |
| 6 | 69 | `self.assertEqual(A.history_problems(), [])` | verbatim | same | yes |
| 6 | 70 | `self.assertEqual(A.reverification_v22_problems(), [])` | verbatim | same | yes |
| 7 | 549 | `self.assertEqual(A.check_v22_proposal(), [])` | verbatim | same | yes |
| 7 | 550 | `self.assertEqual(A.proposal_history_problems(), [])` | verbatim | same | yes |
| 8 | 1696 | `self.assertFalse([t for t in record['targets'] if t.get('runner')])` | verbatim | same | yes |
| 8 | 1697 | `self.assertEqual(m.problems_of(record, ROOT, phase), [])` | rebound | `self.assertEqual(self.f5_problems(m, record, phase), [])` | yes |
| 8 | 1702 | `self.assertIn(f'{t}: measured by a runner that does not classify — re-measure', problems)` | verbatim | same | yes |
| 9 | 146 | `self.assertEqual(PA.proposal_history_problems(), [])` | verbatim | same | yes |
| 9 | 147 | `self.assertEqual(PA.check_v22_proposal(), [])` | verbatim | same | yes |
| 9 | 151 | `self.assertEqual(found, [])` | verbatim | same | yes |
| 9 | 153 | `self.assertEqual(rec['approvals']['given'], [])` | verbatim | same | yes |
| 9 | 154 | `self.assertFalse(any((m['approved'] for m in rec['decision_3_mappings'])))` | verbatim | same | yes |
| 10 | 478 | `self.assertEqual(self.M.check_v22(), [])` | verbatim | same | yes |
| 11 | 169 | `self.assertEqual(R.check_version_forward(), [])` | verbatim | same | yes |
| 11 | 170 | `self.assertTrue(R.tolerated(), f'{R.OUT_REL} is not committed as it is')` | verbatim | same | yes |

Correctness differences, stated rather than hidden. None is an assertion-level gap:
* **Selection.** v2.2 picks the record bound to (round v2.2, HEAD:aisef2). Round v2.3 picks the verified chain head
  and requires its node state. This rests on W1-DESIGN §2.6's premise: every node check either re-derives and
  compares exactly, or carries its own identity guard (its table, all 10 checks PASS at `1bf5dd2f`).
* **The rebound rule.** It differs from the whole-file rule exactly as F5 does:
  * it accepts an unreferenced edit in the same file (N2);
  * it rejects dependency, kill-test and generator changes that the whole-file rule accepts (N3–N6).
* **The MUTATION loop.** It reads the 8 historical phases (`V22_HISTORICAL`, measured from `m.RECORDS` at v2.2.0;
  `validation/v2/mutation.py` is byte-identical there and at HEAD). It asserts that HEAD still maps them to the same
  files. Without this, a later v2.3 phase (runner 2) would trip the runner-free assertion that was meant for history.
* **Measured now vs later.** The counterparts' own green is measured only with the round-v2.3 parts stubbed (item 4b
  cell `C_stub-pass`: the 39 verbatim assertions and the legacy half of the rebound one pass at HEAD). Their real green needs L1-F5's `in_round` /
  `validate(round=)` and seq 13. If L1-F5's interface differs from §2.6, the counterparts fail closed (red), never
  pass.
* **The VERIFIED_REUSE design.** A node designed VERIFIED_REUSE passes on its v2.2 head once the round is open.

**Genuine gap: none at assertion level.** One sensitivity finding about a historical control is in §4a: test_15 alone
misses a byte of its own record.

## 4. Negative-control propagation

### 4a. One corrupted input record per replayed test (scratch copy of v2.2.0, never committed)

**Method.** Each case changes one character, so the JSON stays valid, in one record from the test's measured read set.
It then runs `replay_v22.py --tree <copy> --only <test>` and restores the record. Case 11 is a second, semantic
corruption of the ORCH record: `"identical": 6 → 5`, a field test_15 asserts.

| Case | Test | Corrupted record | Corruption | Replay exit | Problems naming the record | The test itself |
|---|---|---|---|---|---|---|
| 0 | `test_c2_delivery_experiment::PlanCorrection.test_the_committed_record_is_what_this` | `closure-evidence/v2/v2.2/PLAN-V2.2-CORRECTION-1.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 1 | `test_c2_k_nowork_001::Record.test_the_record_binds_this_tree_and_sh` | `closure-evidence/v2/v2.2/K-NOWORK-001-REHEARSAL.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 2 | `test_c2_orchestration_conformance::Record.test_15_the_record_binds_this_tree_and` | `closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json` | last hex digit of the first quoted sha256 | 1 | 2 | PASS |
| 3 | `test_c2_p10_cohort_static::Record.test_the_evidence_record_re_derives_fr` | `closure-evidence/v2/v2.2/P10-COHORT-MACHINERY.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 4 | `test_c2_p10_profile_freeze::Checker.test_the_evidence_record_re_derives` | `closure-evidence/v2/v2.2/P10-PROFILE-FREEZE.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 5 | `test_c2_p5_acceptance::Acceptance.test_the_acceptance_re_derives_on_this` | `closure-evidence/v2/v2.2/C2-P5-ACCEPTANCE-REVERIFICATION.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 6 | `test_c2_p5_acceptance::KernelProvenance.test_on_this_tree_the_committed_propos` | `closure-evidence/v2/v2.2/P5-PLAN-V2.2-PROPOSAL.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 7 | `test_v21_mutation_runner::Classify.test_historical_records_read_as_before` | `closure-evidence/v2/P1-MUTATION.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 8 | `test_p5_plan_v22_proposal::Record.test_P5_8_committed_record_is_current` | `closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 9 | `test_p9_reproduction::KernelComparison.test_Q5_19_the_kernel_comparison_recor` | `closure-evidence/v2/v2.2/Q5-KERNEL-COMPARISON.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 10 | `test_v21_conformance_ruling::CommittedRuling.test_the_committed_ruling_is_what_this` | `closure-evidence/v2/v2.2/CONFORMANCE-RULING.json` | last hex digit of the first quoted sha256 | 1 | 2 | FAIL |
| 11 | `test_c2_orchestration_conformance::Record.test_15_the_record_binds_this_tree_and` | `closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json` | single_probe_equivalence.identical 6 -> 5 (a field test_15 asserts) | 1 | 2 | FAIL |

**Result.** All 12 cases exit 1. Every case names the record twice: once by the clean-tree rule and once by
the committed-bytes rule. The historical test itself fails in 11 of 12 cases.
After restoring, the copy is clean and the full 11-test replay PASSes (exit 0).

**Finding (genuine, about a v2.2 control).** Case 2 changes `old_kernel.kernel_digest` in
`closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json`. test_15 does not detect it: it PASSes. The
replay rejects it anyway. This is why R2 makes "every record read equal to its v2.2.0 committed bytes" part of
`subject_to`.

### 4b. The seq 13 wiring and the release gate path (scratch copy of HEAD, never committed)

**Superseded.** This subsection measured R2's patch `c5bfc527…`. Review finding RA-GP-1 (§7) showed that its skip is
unconditional; R3's patch replaces it and is measured in §7.

**The patch.** `docs/v2.3/drafts/SEQ13-WIRING.patch` changes `tests/v2/sealing_gate.py` only:
* adds `V22_REPLAYED`;
* turns `sealing` into a function. The id comes from `inspect.getfile` (repo-relative) + `__qualname__`, never
  `__module__`. A replayed id is skipped with the reason "round v2.2 history: replayed at v2.2.0 …".

GATED is byte-identical, as checked by AST, and `test_sealing_gate.py` is unedited. The patch passes
`git apply --check` on `f237ad14`.

**The gate path.**
* `release.yml` `publish` needs `tests`.
* `tests` = `uses ./.github/workflows/tests.yml`.
* tests.yml `sealing` runs on master and tags with
  `AISEF_SEALING=1 python -P validation/v2/owned_run.py -- python -m unittest discover -s tests -q`.

**Discovery.** With the patch, `discover -s tests` (no pattern) finds 8,389 tests, including 13 `RoundV23` and 2
`Seq13Wiring`, with 0 failed imports.

**The truth table.** That job command, restricted to `-p test_v23_rounds.py`, under the env guard:

| Cell | Expected | Exit | Summary | Failing tests |
|---|---|---|---|---|
| C_real-fail__R_stub-fail | red | 1 | Ran 20 tests in 2.215s, FAILED (failures=12) | test_CONFORMANCE_RULING, test_K_NOWORK, test_MUTATION_historical, test_ORCH, test_P10_COHORT, test_P10_PROFILE, test_P5_PROPOSAL_P5_8, test_P5_PROPOSAL_kernel_provenance, test_P5_REVERIFICATION, test_PLAN, test_Q5, test_replay_v22 |
| C_real-fail__R_stub-pass | red | 1 | Ran 20 tests in 3.953s, FAILED (failures=11) | test_CONFORMANCE_RULING, test_K_NOWORK, test_MUTATION_historical, test_ORCH, test_P10_COHORT, test_P10_PROFILE, test_P5_PROPOSAL_P5_8, test_P5_PROPOSAL_kernel_provenance, test_P5_REVERIFICATION, test_PLAN, test_Q5 |
| C_stub-pass__R_stub-fail | red | 1 | Ran 20 tests in 70.208s, FAILED (failures=1) | test_replay_v22 |
| C_stub-pass__R_stub-pass | green | 0 | Ran 20 tests in 28.742s, OK | — |
| pre-patch__C_stub-pass__R_stub-pass | red (Seq13Wiring only) | 1 | Ran 20 tests in 27.672s, FAILED (failures=12) | test_V22_REPLAYED_is_the_replayed_set_and_each_is_gated, test_each_replayed_test_is_skipped_at_head_naming_the_replay |

**Other checks with the patch applied.**
* `test_sealing_gate.py` passes (3 tests): the GATED closure is intact.
* The 11 V22_REPLAYED tests run at HEAD under `AISEF_SEALING=1` exit 0, with 11 skips naming the replay.

**Reading the table.**
* The gate is red when a counterpart fails, when the replay fails, or both.
* It is green only when both pass.
* Before the patch it is red only on `Seq13Wiring`.
* Without stubs, at the code commit, the 11 counterparts fail on "round v2.3 is not open". The ledger has no seq 13,
  and there is no `in_round` and no `validate(round=)`. So the gate is closed today, as it should be.

**NOT_DONE.**
* The full sealing job (the whole suite) was not run: project rule, the integrator's batch.
* The real replay inside the patched copy was not run: a fresh 1.8 GB clone, against the 15 GiB disk floor. Stubs were
  used. The real gated replay passed at the pre-patch commit.

## 5. Q0 and v2.2 history identity (`HISTORY-IDENTITY-2026-11-21.json`)

**Q0 record** (`closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json`):
* sha256 `714625b14e8972f166b37a467b5f83761d1f2672d076e5f5f0f342e2eb91332c` at v2.2.0 and at HEAD;
* `git log da3ea33f..HEAD` of the path is empty.

**Q0 regenerated deterministically** in scratch copies: `render(run())`, env guard.
* At v2.2.0: 250.6 s, 57/57 calibrated, `problems_of` = [], `history_problems` = [], bytes sha256 `714625b1…`, equal to
  the committed record.
* At `d522dd84`: 258.6 s, the same result.
* At `80046dbe` (evidence under `closure-evidence/v2.3/`): 56/57; `v1_evidence_guard` is not calibrated. See the
  placement finding at the top.
* At `f4a530b6` (evidence moved to `docs/v2.3/evidence/round-auth/`): 252.8 s, 57/57, [] / [], bytes sha256
  `714625b1…`, equal to the committed record. `tests/v2/test_v1_evidence_guard.py` and `tests/test_onboarding_digest.py`
  pass there. This is measured after `HISTORY-IDENTITY` was written, so it is recorded here only.

**`closure-evidence/v2`** (`git diff --name-status da3ea33f..HEAD`) has only additions, 9 of them, none by this track:
* `cycle2/C2-CLOSURE-AUDIT.json`, `cycle2/C2-CLOSURE-AUDIT.md`;
* `cycle2/C2-HISTORY-FREEZE-CANDIDATE.json`, `cycle2/C2-LEDGERLOCK-FAILURE-TRIAGE.json`;
* `cycle2/C2-ORCHESTRATION-CHANGE-REVIEW.json`;
* `v2.2/RELEASE-MUTATION-GATE-EVALUATION.json`, `v2.2/RELEASE-MUTATION-SCOPE-AMENDMENT.json`;
* `v2.2/V2.2-MUTATION-CAMPAIGN-FREEZE.json`, `v2.2/V2.2-RELEASE-GO-NO-GO.md`.

**Every original v2.2 evidence file is unchanged.** All 8,645 v2.2.0 files under `closure-evidence/` (6,339 under
`closure-evidence/v2`) have the same mode, blob and path at HEAD: 0 changed or removed.

**Ledger** (`RELEASE-DECISIONS.json`):
* byte-identical to v2.2.0 (seq 1–12);
* the per-entry canonical sha256 values are in the evidence file;
* `LedgerHistory.test_entries_1_to_12_are_the_v2_2_0_entries` re-checks entries 1–12 on every branch.

## 6. The revised drafts

* `docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R5.md` — the current draft (§9); its ruling digest is in §9.5. Changes vs
  R4 and their reasons are in R5.
* `LEDGER-SEQ-13-DRAFT-R4.md` — unchanged, `8db40e8c65c0094b36812ff6338819e8afbe91388e8f058647ae935a6978d63b`, pinned
  by `tests/v23/test_v23_ledger_digest.py`. **Superseded by R5; not to be ratified** (§9).
* `LEDGER-SEQ-13-DRAFT-R3.md` — unchanged, `72e296b6b2f991e7f66a82bcebb9baff3bf337954b722316defa16db94a2dd9f`,
  now pinned by `tests/v23/test_v23_ledger_digest.py`. **Superseded by R4; not to be ratified** (§8).
* `LEDGER-SEQ-13-DRAFT-R2.md` — unchanged, `a7fa9f97c6a324f3f1d53df2ca42cd8c46135751977bcdafa5c3d63716daa940`,
  now pinned by `tests/v23/test_v23_ledger_digest.py`. **Not to be ratified** (§7).
* `LEDGER-SEQ-13-DRAFT.md` (R1) — unchanged, `824091110a8bb0fcf8726e889f4ff0c3f11e8f102dfa18f028e343a968caa79b`.

All four are recomputed by `validation/v23/ledger_digest.py`.

## 7. Review findings RA-GP-1 and RA-INT-2 (fixed fail-closed in `5a0b1c24`)

Both findings were MEDIUM, and a verifier reproduced each one independently at `c6344aa4` before the fix.

### RA-GP-1 — R2's wiring skipped the 11 unconditionally

**Defect.** With `SEQ13-WIRING.patch` applied, `sealing()` skipped every V22_REPLAYED id with no condition. Every
closure over the counterparts (Coverage, Seq13Wiring, `test_replay_v22`) lives in `tests/v23/test_v23_rounds.py`,
which nothing protected. Deleting that file, or a one-line edit of `round_gate` (variant D), dropped the 11 controls
and the replay, and the sealing job stayed green.

**Fix** (`SEQ13-WIRING-R3.patch`, still `tests/v2/sealing_gate.py` only; GATED byte-identical, checked by test). This is
the finding's option 2; option 1 (an AST check) does not close variant D.
* `V23_PINNED` pins the sha256 of the LF bytes of the four files the skip stands on:

  | Pinned file | sha256 (LF) |
  |---|---|
  | `tests/v23/__init__.py` (empty; without it `discover` does not find tests/v23) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
  | `tests/v23/test_v23_rounds.py` | `79433cacb80ba7abf9234dfaaac39c996486ea745b2a1849f3a619aa2aa56620` |
  | `validation/v23/ledger_digest.py` | `660624c01b47811b8b9d2f41f371d4b721bb8b7c802eaa87b656c05f99ee3df9` |
  | `validation/v23/replay_v22.py` | `3414936eac1e1b70ef626c12b1348f8c2d2c90041980bdb743e5a6ff8fcf9a46` |

* `sealing()` skips a V22_REPLAYED id only while `V23_PINS_HOLD`. Otherwise it falls back to the ordinary gate: under
  `AISEF_SEALING=1` the v2.2 test runs, as it did before seq 13; without it, it is the usual visible skip.
* `Seq13Wiring.test_the_applied_wiring_is_exactly_the_reviewed_patch_and_its_pins_hold` requires HEAD's
  `sealing_gate.py` to be exactly v2.2.0's plus the patch whose sha256 the reviewed draft names, with every pin
  holding. So "any wiring other than the named patch" is now a red test, not only a sentence.

**Regression tests** (`tests/v23/test_v23_seq13_wiring.py::WiringR3`, always run, throwaway trees). For each of the
four files, deleting it or editing it un-skips all 11. Variant D un-skips all 11. A CRLF checkout keeps the pins. A
broken pin without the sealing tier is the ordinary skip. The drafted pins equal this tree's files. On R2's patch,
the same deletion skips all 11: the contrast.

**Measured end to end.** Setup: a scratch APFS copy of `5a0b1c24` with the R3 patch applied, `AISEF_SEALING=1`, the
env guard. Each run covers the 11 ids, `test_sealing_gate.py` and every tests/v23 module. `RoundV23.test_replay_v22`
is left out (a 1.8 GB clone at the disk floor). Logs stay in scratch and are given by sha256.

| Scenario | Wiring | The 11 v2.2 tests | Run | Gate | Log sha256 |
|---|---|---|---|---|---|
| A: intact | R3 | 11 SKIP, naming the replay | ran 59, failures 11 (the counterparts: "round v2.3 is not open"); Seq13Wiring 3/3 OK | red | `94ec3d1659db291f84d8acd687467dcf6bdd2c090a17bf8757a2884c2586ac6f` |
| B: counterparts file and regression module deleted, committed | R3 | 11 RUN, 11 PASS (the kernel is still v2.2.0's) | ran 28, 0 failures, 0 skipped | green, on the 11 themselves | `46f3acc725d4eb00694ee2c4ed45e686fa98446e55c10ad1acf3a04ba75d7ae9` |
| B + a kernel edit (one comment line in `aisef2/orchestrate/story_runner.py`, committed) | R3 | 11 RUN, 10 FAIL | ran 28, 10 failures | red | `7cf9727c6f9419a79f105e0b75a2c4247190f7fdea26746e12f8248b57e1ab06` |
| the same tree | R2 `c5bfc527…` | 11 SKIP | ran 28, 0 failures, 11 skipped | **green: the finding** | `91239eb0441916590b30ddafab91174fa6724b64e8c1dd48c365f7e1817a3a73` |
| D: `round_gate` neutered + the kernel edit | R3 | 11 RUN, 10 FAIL, 0 SKIP | ran 59, 14 failures (10 v2.2 + 4 WiringR3), 15 skipped (RoundV23, Seq13Wiring) | red | `483e841a1318a0f163d0b99d6aa1be71f83707060e9cbb073014ad1e92e88dc5` |

In the kernel-edit rows, the 11th test (`Classify.test_historical_records_read_as_before`) passes, because
`story_runner.py` is not a mutation target. **Reading:** with R3's wiring, removing or neutering the replacement
restores the v2.2.0 behaviour: the original controls run, and they go red as soon as the kernel moves. It no longer
drops them.

### RA-INT-2 — any seq 13 with the right id opened the round

**Defect.** `round_v23_missing` checked only seq, id, approver and `QUALIFICATION_ROUND`. It accepted all of these:
the R2 placeholder authority, R1 verbatim, an empty or missing authority, a minimal entry, and a doctored decision.

**Fix:** `tests/v23/test_v23_rounds.py::ledger_seq13_problems`. The HEAD-committed check is kept. It then requires:
* exactly one seq 13, with the id, `human:owner` and `QUALIFICATION_ROUND` v2.3, and `decision` an object;
* its canonical ruling digest equal to that of the reviewed draft `LEDGER-SEQ-13-DRAFT-R3.md` as committed at HEAD.
  `reviewed_draft` refuses a draft whose HEAD blob differs from the blob of any commit that added it, so the draft
  cannot be rewritten to match an entry;
* `authority` not empty and not the `<…>` placeholder;
* `authority` quoting that digest. R2 says the owner's instruction names the digest; this makes it checked.

**Why no digest constant.** The finding asked for a constant in the code. A constant in a pinned file would be a hash
cycle: R3 names the patch by sha256, the patch pins `test_v23_rounds.py`, and that file would hold R3's digest. The
binding therefore runs through two things: the never-rewritten reviewed draft, which the pinned file names by path,
and the owner's own words, which must quote the digest.

**Regression tests** (`tests/v23/test_v23_seq13_wiring.py::LedgerSeq13`, throwaway repositories holding ledger 1–12
plus one appended entry and the R3 draft).
* Refused: all six of the verifier's entries; R2 approved in words quoting R2's digest; a doctored entry approved in
  words quoting its own digest; R3 with words that quote no digest or another digest; a second seq 13; a rewritten
  draft with a matching entry; an uncommitted ledger change.
* Controls refused as before: approver `agent`, round `v2.4`, id `X`, a non-object `decision`.
* Opens: R3 with the owner's words quoting its digest. This is the only case that opens.

### What the fix does not close (stated, not hidden)

* The counterparts call code the pins do not cover: `validation/v23/impact.py` (the F5 engine, W1a's) and L1-F5's
  `version_forward.in_round` / `currency_dag.validate(round=)`. A wrong change there weakens a counterpart without
  un-skipping the 11. Pinning them would freeze other lanes' code. They carry their own tests and qualification.
* A coordinated forgery is not stopped: a ledger entry plus owner words that the owner did not write, or a history
  rewrite of the R3 draft. No in-tree check can tell forged owner words from real ones; the existing consumers
  (`p5_acceptance.py` V22_AUTHORITY) have the same limit.
* Workflow edits and a sibling test module that monkeypatches RoundV23 at import are outside this mechanism, as they
  are for v2.2.0's GATED closure.
* Any later edit of a pinned file, for example to follow L1-F5's real interface, needs a new patch and a new ruling
  (R4). This is the intended cost.
* W1-DESIGN §7 says `sealing_gate.py` changes "only for V22_REPLAYED". R2's patch already went beyond that (`sealing`
  became a function), and R3 adds the pins that guard the skip. The integrator should confirm this reading.

## 8. Q0-1: the distinct v2.3 Q0 round (draft R4; superseded by R5, §9)

The owner, 2026-11-22: approve the architectural direction of a distinct v2.3 Q0 qualification round, without modifying
or invalidating the historical v2.2 Q0 record. Before the final ruling the owner asked for six things: a byte-identical
historical replay; mandatory v2.3 counterparts; red on a deleted or broken counterpart; fail-closed on a missing or
corrupted historical record; the exact Q0 delta, affected code and negative tests; and the revised seq-13 object.

The design and the full 57-checker delta are in `docs/v2.3/amendments/Q0-1-V23-ROUND.md`. Nothing here applies the
patch, writes the ledger or writes the round-v2.3 Q0 record. `tests/v2/**`, `closure-evidence/**`, `validation/v2/**`,
`aisef2/**`, R1–R3 and their patches are unchanged versus `0a034025`.

Evidence, all new files under `docs/v2.3/evidence/q0-round/`, each written once with `open(…, "x")`, with no local path:

| File | sha256 | What |
|---|---|---|
| `REPLAY-V22-Q0-2026-11-21.json` | `0f8bd55cd078e38115976c0c3d68fcf89f70fa37698654e048d5457e886e513c` | the 11 and the Q0 class replayed at v2.2.0 (§8.2) |
| `COVERAGE-MAP-2026-11-21.json` | `644d874c610a8c8315554db2e402ac8bad9fa51d6006aaa902680714e054fc2c` | assertion map: 11 + 9 Q0 methods (§8.3) |
| `Q0-DELTA-2026-11-21.json` | `f885b37454f99fa51c332c46fab9ee54b6e84876c5654a9ac4697d94f582ad54` | the measured Q0 delta (§8.1) |
| `NEGATIVE-CONTROLS-2026-11-21.json` | `6ee4f872d35da24fb5c1ff6027584d22208e97f74f4ff3b107d3d9571550bea8` | historical negatives and the end-to-end scenarios (§8.2, §8.5) |
| `docs/v2.3/drafts/SEQ13-WIRING-R4.patch` (not applied) | `a0f79fc19b0841d22cf6800051dd4dfddeab21b3860d38f1587c89f61fa24254` | the wiring (§8.4) |

Tools: `validation/v23/q0_round.py` (new), `validation/v23/replay_v22.py` (extended). Raw logs and harnesses stay in
scratch, referenced by sha256 inside the evidence. Host for every measurement: Darwin 25.5.0 arm64, CPython 3.14.7,
git 2.53.0.

### 8.1 The exact Q0 delta (measured)

| Scenario | Lane | Calibrated | Record | Moved |
|---|---|---|---|---|
| base `0a034025` | — | 57/57 | byte-identical `714625b1…` | — |
| A: comment after `aisef2/app/run.py:693` | W1b L1-LIFECYCLE | 54/57 | `a05d0d46…` | b1_bindings clean (25 run.py targets), currency_dag clean, mutation clean |
| B: new empty `validation/v2/gen_probe_grammar.py` | W5-main L5-AUTHOR | 57/57 | `fb76bd15…` | `uncovered_checker_modules` (problems_of red) |
| C: comment appended to `story_runner.py` | W1b and later | 55/57 | `a8186826…` | currency_dag, mutation clean; b1 known-bad `observed[0]` |
| D: comment appended to `validation/v2/except_boundaries.py` | W1a L1-AUTHCHK | 56/57 | `fd7ba14c…` | mutation clean (9 targets) |
| E: seq 13 appended to the ledger | owner | 57/57 | byte-identical | — |

**Finding.** W1-DESIGN.md:299 ("Q0-1 is not triggered") does not hold:

* A shows `b1_bindings`' clean red from the first W1b edit of `run.py`, which the story_runner-only probe could not
  see (scope row OD-Q0-1-W1B, confirmed);
* D shows L1-AUTHCHK moves Q0 already in W1a.

Committing seq 13 itself does not move Q0 (E).

### 8.2 Historical side: byte-identical replay at v2.2.0, fail closed

`replay_v22.py --tree <APFS clone of the v2.2.0 worktree>` ran all 12 at 2026-11-21T17:20:55Z. **Verdict PASS**, exit 0:

* the 11 PASS, as in §2;
* `CheckerCalibration` PASS: 9 ran, 0 skipped, 245.56 s, owned_run clean;
* all 4,734 records it read are the v2.2.0 committed bytes;
* the Q0 record is committed = in the tree = regenerated, each `714625b14e8972f166b37a467b5f83761d1f2672d076e5f5f0f342e2eb91332c`.

The regenerated bytes are `cc.render(CheckerCalibration.result)` from the class's own run.

| Case (same clone, record restored after each) | Exit | Q0 record | Problems naming it | Log sha256 |
|---|---|---|---|---|
| full replay (12) | 0 | byte-identical | — | `57a099ad704e6851dd7575a7654e781bd87e5c67c6705e55965a436ebde5fbc7` |
| Q0 record deleted | 1 | tree `None`, regenerated `714625b1…` | "is missing from the tree (fail closed)"; "tree not clean: D …"; the test's FileNotFoundError | `bced832ec1e620c9795135709a2abdf0e412081182e817442d9317cd6edbfbc9` |
| Q0 record corrupted (`checker_count` 57 → 58, valid JSON) | 1 | tree `e2b94bc1…` | "in the tree is not the v2.2.0 committed bytes (corrupted)"; "record … is not the v2.2.0 committed bytes"; "tree not clean: M …"; the test's render mismatch | `8d9de76efa68b846d260b25d20217b6d1f55ccc69d6f418ddc2f2a99f872f989` |

**Observed side effect (new with Q0, stated).** The full replay's own Q0 calibration, which is v2.2.0 code, writes
bytecode for some child processes into the tree. The two negatives therefore ran on a clone that held 9 ignored
`__pycache__` entries. The preflight named each one as "tree not clean: !! …", next to the record problems.

* `RoundV23.test_replay_v22` uses a fresh clone per run, removed afterwards, so it is not affected.
* A reused `--tree` must be cleaned (`git clean -fdX`) before the next replay, or the preflight refuses it.

The always-run `Q0Replay` tests (synthetic v2.2.0 trees) cover five cases:

* intact, regenerated byte-identically;
* missing;
* corrupted;
* regenerated-but-different while the test itself passes. This one is stricter than the v2.2 test, as §4a was;
* a class that cannot calibrate (named "was not regenerated").

### 8.3 v2.3 side: the counterpart and the map

`tests/v23/test_v23_q0_round.py::Q0RoundV23` holds the v2.2 class's 9 tests, bodies verbatim, on `q0_round.run()` (the
same calibration on HEAD, in round v2.3). It adds four v2.3 conditions: the round is open (seq 13 = R4, by digest, in
the owner's words), the v2.2 record is still `714625b1…`, no v2.2 checker is dropped, and
`docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json` equals what HEAD derives.

`replay_v22.py --coverage` gives 59 assertions over 20 entries (the 11 + the 9 Q0 methods): 57 verbatim, 2 rebound
(the mutation rule of §3, and the Q0 record assertion `cc.OUT_REL`/`cc.render` → `Q.V23_REL`/`Q.render`), **0 gaps**.
`Q0Coverage` re-checks this on every branch, and shows that a dropped Q0 assertion is a gap.

### 8.4 The wiring: `SEQ13-WIRING-R4.patch` (sha256 `a0f79fc19b0841d22cf6800051dd4dfddeab21b3860d38f1587c89f61fa24254`)

R3's mechanism, extended; `tests/v2/sealing_gate.py` only; GATED byte-identical (`WiringR4`):

* `V22_REPLAYED_Q0 = ("tests/v2/p0/test_checker_calibration.py::CheckerCalibration",)` joins the skip;
* `V23_PINNED` (LF sha256):

| Pinned file | sha256 |
|---|---|
| `tests/v23/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/v23/test_v23_q0_round.py` | `8bdf86cd908e224bb2d3df60a16aad7cf17ccaf6a2e601791044ecd91d963004` |
| `tests/v23/test_v23_rounds.py` | `7594e4d7ff0d51070dd78f918aea5515fe8c17d31fe9eacb98a3c0f9f7e3ad0c` |
| `validation/v23/ledger_digest.py` | `660624c01b47811b8b9d2f41f371d4b721bb8b7c802eaa87b656c05f99ee3df9` |
| `validation/v23/q0_round.py` | `e7b487a2a44ffa903a27a4d0aa92d53a9e0de4735012cb185189d941ea09df8f` |
| `validation/v23/replay_v22.py` | `3f54e22b0f201072be279c058381e2dee3726bd86ac09bc52b3a09bbb788f87e` |

The Q0 test is skipped at HEAD only while all six hold; any broken pin un-skips all 12. `Seq13Wiring` and `Q0Wiring`
each require every pin to hold, so the gate is red while either file survives. R3's patch, applied to this tree, skips
nothing: its pins no longer hold (`WiringR4.test_R3s_patch_never_skips_q0_and_on_this_tree_skips_nothing`).

### 8.5 Negative controls, end to end

Setup:

* an APFS clone of the worktree (`0a034025` + this change), with the R4 patch applied and committed in the clone;
* `AISEF_SEALING=1 python -P validation/v2/owned_run.py -- python -P run_ids.py <clone>`: the sealing job restricted to
  the 11 + the Q0 class by name, `tests/v2/test_sealing_gate.py`, and everything `discover` finds under
  `test_v23*` (so a deleted `tests/v23/__init__.py` hides tests/v23, as in the real job);
* the env guard;
* `RoundV23.test_replay_v22` left out: the replay is measured in §8.2.

O-rows use a harness-level **round-open stub**, because L1-F5 does not exist yet:

* a no-op `in_round` and a `validate(round=)`;
* a seq 13 that is the provisional R4 entry, with a "SCRATCH-COPY STUB" authority quoting its digest
  `1fb2e077…`, committed only in the clone;
* only the Q0 tests are kept.

The provisional draft differs from R4 only in `EVIDENCE_REVIEWED`, which cannot name the evidence it produces.

| Scenario | The 11 (v2.2) | Q0 class (v2.2) | Q0RoundV23 | Q0Wiring / Seq13Wiring | Exit | Gate | Log sha256 |
|---|---|---|---|---|---|---|---|
| S1_intact_no_seq13: none: R4 applied, no seq 13 in the ledger (ran 169: 20 failures, 0 errors, 20 skipped) | 11 SKIP | 9 SKIP | 9 FAIL | 1 OK / 3 OK | 1 | **red** | `24196ec9694078f2d657036ba3b0b618431432afa070a54c6243f13c40036bc5` |
| S2_q0_counterpart_deleted: tests/v23/test_v23_q0_round.py deleted (committed) (ran 144: 25 failures, 19 errors, 0 skipped) | 11 OK | 9 OK | not run | not run / 1 FAIL, 1 OK | 1 | **red** | `30091383fdd53e27cf175c0247483ac9cd205fa405ac0e492fbf28b103942d20` |
| S3_q0_round_module_deleted: validation/v23/q0_round.py deleted (committed) (ran 145: 23 failures, 20 errors, 0 skipped) | 11 OK | 9 OK | not run | not run / 1 FAIL, 1 OK | 1 | **red** | `8c6967046620747159410c41240a7c2e26bbf3216b19015e2a30274fbc0e7fde` |
| S4_q0_counterpart_open_neutered: tests/v23/test_v23_q0_round.py: Q0RoundV23.open() returns instead of failing on a closed round (committed) (ran 169: 28 failures, 0 errors, 0 skipped) | 11 OK | 9 OK | 1 FAIL, 8 OK | 1 FAIL / 1 FAIL, 1 OK | 1 | **red** | `6c29f20245c5687e35b8d4c11712b4961e14323eb0438251725d803a1f58ec8a` |
| S5_tests_v23_init_deleted: tests/v23/__init__.py deleted (committed): discover no longer finds tests/v23 (ran 97: 0 failures, 0 errors, 0 skipped) | 11 OK | 9 OK | not run | not run / not run | 0 | **green** | `1a58f0dc0888ee2ccba5d408356dd5c9044c87df5efe82309e975b08c24a0c8f` |
| S6_tests_v23_init_deleted_plus_run_py_edit: tests/v23/__init__.py deleted + one comment line after aisef2/app/run.py:693 (committed) (ran 97: 14 failures, 0 errors, 0 skipped) | 10 FAIL, 1 OK | 1 FAIL, 7 OK | not run | not run / not run | 1 | **red** | `1d4e5e71839bf6756513e522871795bcd844c40417ce0d235b8e8a13685aa7fd` |
| S7_test_v23_rounds_deleted: tests/v23/test_v23_rounds.py deleted (committed) (ran 114: 0 failures, 2 errors, 0 skipped) | 11 OK | 9 OK | not run | not run / not run | 1 | **red** | `277c392b3d31a003ce8a9feeb04f8fc6fe9fa9d48b62123357986de392d5e3e7` |
| O0_round_open_stub_record_missing: round-open stub; no round-v2.3 Q0 record (ran 40: 1 failures, 0 errors, 9 skipped) | not run | 9 SKIP | 1 FAIL, 8 OK | 1 OK / 3 OK | 1 | **red** | `002a8b84e762e365095de9f5bf2f371478725905c7d88de426c5e0af251d7daa` |
| O1_round_open_stub_record_current: round-open stub; the record written by q0_round.py --write and committed (ran 40: 0 failures, 0 errors, 9 skipped) | not run | 9 SKIP | 9 OK | 1 OK / 3 OK | 0 | **green** | `1fbc5806bd47c263c1cdf0863877cdd57d134ce9ec4bb31e2006557507e4b982` |
| O2_round_open_stub_record_stale_after_run_py_edit: round-open stub; the O1 record committed, then one comment line after aisef2/app/run.py:693 committed (ran 40: 4 failures, 0 errors, 9 skipped) | not run | 9 SKIP | 1 FAIL, 7 OK | 1 OK / 3 OK | 1 | **red** | `fe0e3b0ab3457fde954c85fb568aa4dc59a3c6af57b02e201416612b627cb535` |
| O3_round_open_stub_record_one_byte_changed: round-open stub; the O1 record with calibrated_count 57 -> 56 (valid JSON) (ran 40: 1 failures, 0 errors, 9 skipped) | not run | 9 SKIP | 1 FAIL, 8 OK | 1 OK / 3 OK | 1 | **red** | `079d1329c1c764c5e7165770fde42d5cd71dc4f913f6ea5daff4b6cd193b1dc4` |
| O4_round_open_stub_v22_record_corrupted_at_head: round-open stub; O1 record; the v2.2 Q0 record's checker_count 57 -> 58 at HEAD (ran 40: 5 failures, 0 errors, 9 skipped) | not run | 9 SKIP | 1 FAIL, 8 OK | 1 OK / 3 OK | 1 | **red** | `6931c1dffe6c397014dd16d1934be0e3eb1b06484445d3f23e73f05e0255e73e` |
| O5_round_open_stub_v22_record_deleted_at_head: round-open stub; O1 record; the v2.2 Q0 record deleted at HEAD (ran 33: 1 failures, 1 errors, 9 skipped) | not run | 9 SKIP | 1 FAIL, 8 OK | 1 OK / 3 OK | 1 | **red** | `bd5e2c3bb6df387158fbd0a04f9bab931e0b69a2549126ab18c035fb62ee2d85` |

Per-test lines in the logs omit subTest failures; the SUMMARY counts in the evidence include them.

**Reading.**

* **Intact without seq 13 (S1): red.** Every counterpart fails on the closed round. Q0RoundV23's test 1 names the
  missing record too.
* **Deleting or breaking the Q0 counterpart or q0_round.py (S2–S4), or `test_v23_rounds.py` (S7): red.** The 12 v2.2
  tests run again, and the surviving wiring test, Coverage or import fails.
* **Deleting `tests/v23/__init__.py` (S5) hides all of tests/v23: the v2.2.0 gate itself.** All 12 original
  controls run and pass, because nothing has moved yet (as R3's scenario B). With one comment line in `run.py` (S6)
  they are red, Q0 included (b1_bindings uncalibrated).
* **With the round open (stubbed), only the current record is green (O1).** Missing (O0), stale after a run.py edit
  (O2), one byte changed (O3), and the v2.2 record corrupted (O4) or deleted (O5) at HEAD are each red on Q0RoundV23
  test 1, naming the cause.

The record the real writer produced in O1 has a `calibration` body exactly equal to the v2.2 record's JSON: nothing
has moved yet.

### 8.6 Regression tests (always run, seconds)

* `tests/v23/test_v23_q0_round.py`:
  * `Q0Record`: record missing, not JSON, not UTF-8, stale, one byte changed, CRLF and current; v2.2 history missing,
    corrupted or truncated, and CRLF; a dropped checker and a short registry; the writer refuses a closed round, an
    existing file and an uncalibrated tree, and writes once; `run()` enters round v2.3;
  * `Q0Coverage`;
  * `Q0Replay`.
* `tests/v23/test_v23_seq13_wiring.py`:
  * `WiringR4`: 6 pins; deleting or editing each un-skips all 12; variant D; CRLF; the ordinary skip without the
    tier; the R2 and R3 contrasts;
  * `LedgerSeq13` now also refuses R3 approved in words quoting R3's digest.
* `tests/v23/test_v23_ledger_digest.py`: pins R3 `72e296b6…` and R4 `8db40e8c65c0094b36812ff6338819e8afbe91388e8f058647ae935a6978d63b`; R4 only extends R3's `SCOPE`,
  `EVIDENCE_REVIEWED` and `NOT_AUTHORIZED`.

### 8.7 The revised seq-13 object

`docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R4.md`, **canonical ruling digest `8db40e8c65c0094b36812ff6338819e8afbe91388e8f058647ae935a6978d63b`**. The authority stays a placeholder
that asks for the owner's own words quoting the digest; there is no signature and no approval date. The changes vs R3,
field by field, are in R4.

**R4 supersedes R3** (and R3's patch `40e6b57a…`): neither is to be ratified or applied. R1–R3 are unchanged and
digest as recorded. **R5 supersedes R4 (§9).**

### 8.8 NOT_DONE (stated)

* Full suite and full sealing job: not run (project rule; the integrator's batch).
* `RoundV23.test_replay_v22` was not run inside the patched clone: a second full checkout during the e2e copy would
  break the one-copy rule. The same tool replayed all 12 at v2.2.0 on its own (§8.2).
* The round-v2.3 Q0 record is not committed. It cannot be: the writer refuses until seq 13 (R4) is committed and the
  round exists (L1-F5). Its green was shown only with the harness stub (O1).
* Not decided, and not to be decided by this track: OD-Q0-1-W1B / OD-B1B (`b1_bindings`), OD-NEWMOD, the F5 cut-over,
  L1-F5's round path. **Final E5 qualification waits at this boundary.**
* Measured after the evidence was written, so recorded here only: on an APFS clone of the final tree of this commit (everything above committed in the clone, the patch not applied), Q0 regenerates **57/57, byte-identical** (`714625b1…`), 230.5 s, with `problems_of` = [] and `history_problems` = []. Targeted tests in the worktree (unsealed, env guard): `discover -s tests/v23` ran 73, OK, 26 skipped (gated); `tests/v2/test_sealing_gate.py` 3 OK; `tests/v2/test_v1_evidence_guard.py` 26 OK; `tests/v2/p0/test_checker_calibration.py` 13 ran, OK, 9 skipped (gated). ruff clean.

## 9. The Q0-1 review findings and draft R5 (fixed fail-closed in `29c40b07`)

A review of R4 (`860dcbe6`) found five defects, and a verifier reproduced each one. Each is fixed fail-closed, none by
an allowlist or an exception. The design and the corrected delta are in `docs/v2.3/amendments/Q0-1-R5.md`;
`Q0-1-V23-ROUND.md` is unchanged. Nothing here applies a patch, writes the ledger or writes the round-v2.3 Q0 record.
`tests/v2/**`, `validation/v2/**`, `closure-evidence/**`, `aisef2/**`, R1–R4 and their patches, and the evidence files
are unchanged versus `860dcbe6`. `tests/v23/__init__.py` is still 0 bytes.

### 9.1 Findings and fixes

| ID | Severity | Defect (as reproduced) | Fix | Regression tests | Status |
|---|---|---|---|---|---|
| Q0P-1 | HIGH | Weakening the b1 fixture's `"expect"` to `""` before the first write: the writer wrote 57/57 and the restricted sealing run was green (ran 40, 0 failures). The same edit fails v2.2.0's gate. | `q0_round.contract_problems`, in `problems`: each v2.2 checker keeps `package`, `fixture` and `expected`, and its fixture file keeps its v2.2.0 LF bytes. No exception list. `delta` prints the per-checker change against the v2.2 record. | `Q0Contract` (5), `Q0Rules` | FIXED, measured (§9.2 F2, F2h) |
| Q0P-2 | MEDIUM | A new `validation/v23` checker module with an unledgered `os.kill` and an encoding defect: Q0 stayed 57/57 with no problem. Widened scopes found 6 unledgered sites. | `q0_round.v23_scope_problems`, in `problems`: a `validation/v23` module is a registered source or in the closed `NOT_CHECKERS_V23`; destructive_authority `SCOPES` covers `validation/v23` and `tests/v23`; the calibrated encoding scan runs over `validation/v23`. | `Q0Scope` (4), `Q0Rules` | FIXED in round v2.3's rule, measured (§9.2 F3, §9.3). Ledgering the 6 sites and registering `impact.py` stay with L1-AUTHCHK and L1-F5. |
| Q0P-3 | MEDIUM | `p5_acceptance` `GUARDS` runs the v2.2 `checker_calibration.py --check`, which no v2.3 tree passes (measured: exit 1 after edit A). So a re-derived P5 record could never be green. W1-DESIGN.md:266's VR justification pointed at an impossible gate. | `q0_round.CHECK_ARGV` = `validation/v23/q0_round.py --check`, which now also needs the round open. `test_v23_rounds.p5_q0_guard_problems`, asserted in `RoundV23.test_P5_REVERIFICATION`: a re-derived P5 record must record that guard. Affected consumers listed; VR and gate 3 restated (amendment §3). | `Q0Guard`; `Q0Record` (closed round makes `--check` red) | FIXED in the counterpart and the ruling. Unit-measured only: the real round-v2.3 P5 record needs L1-F5 and L1-QUAL's round-aware `GUARDS`. |
| Q0R-INT-1 | MEDIUM | A merge (resolved by hand, or `-X theirs`) or a `--depth 1` clone hid the reviewed draft's add commit, so a rewritten R4 opened the round. | `reviewed_draft`: `--full-history`; refuses a shallow repository; `GIT_NO_REPLACE_OBJECTS=1`. R5 tells the owner to digest through `reviewed_draft`. | `LedgerSeq13`: both merges refused, a benign merge opens; a shallow clone refused, a full clone opens | FIXED, measured (real git, throwaway repositories) |
| Q0R-INT-2 | MEDIUM | R4 named the Q0-1 amendment by path only, on a "hash cycle" reason that holds only for this page. The amendment could be edited after approval with nothing turning red. | R5's `BOUND_SHA256` binds both amendments and the 8 evidence files by LF sha256. `ledger_seq13_problems` keeps the round closed while any differs. The reason is corrected: only this page is unbound. | `LedgerSeq13.test_every_bound_file_must_stay_as_reviewed`; `Digest.test_R5_binds_…` | FIXED, measured (throwaway repositories) |

### 9.2 Measured end to end (R5 applied in an APFS clone)

**Setup.**

* An APFS clone of the worktree at `860dcbe6` plus this pass, committed in the clone. The clone's `.git` was replaced by
  a new repository that borrows the main object store read-only; it is not shallow.
* The R5 patch applied and committed in the clone only.
* `AISEF_SEALING=1 python -P validation/v2/owned_run.py -- python -P run_ids.py <clone>`: the sealing job restricted
  as in §8.5, under the env guard.
* Run 2026-11-21T20:39Z–21:10Z (UTC, system clock).

**Harness stubs (labelled).**

* Round-open stub: a no-op `in_round`, a `validate(round=)`, and a seq 13 that is R5's entry with a "SCRATCH-COPY STUB"
  authority quoting R5's digest. It is committed in the clone only.
* `STUB_SCOPE=1`: `v23_scope_problems` returns `[]`. It stands in for L1-F5's registered `impact.py` and L1-AUTHCHK's
  widened `SCOPES`. It is used in F1, F2 and F2h only. F3 runs the real rule.

| Scenario | Writer (`q0_round.py --write`) | Restricted sealing run | Gate | Log sha256 |
|---|---|---|---|---|
| S1: R5 applied, no seq 13 | — | ran 186: 20 failures (the 11 RoundV23 and 9 Q0RoundV23 counterparts, "round v2.3 is not open"), 20 skipped (the 11 and the Q0 class, naming the replay) | **red** | `d11359975ca571908e908d83824b68c62a38861f7454f248a4b8938d432b5654` |
| F1: round and scope stubbed (control) | rc 0, 57/57, "0 change(s)" against the v2.2 record, record written | Q0 set: ran 25, 0 failures, 9 skipped (the v2.2 class) | **green** | writer `54352cd12db3e4b0d88a05b9c09e2157a56a8b3fc405405b64f48b066227d13c`, run `568b9c7926a13de723e5fb925a186c13285392a1342fb0ee9b2a1f6411862f5c` |
| F2: the verifier's Q0P-1 edit (b1 `"expect": ""`) before the first write | **rc 1, no record**: `DELTA b1_bindings.expected: 'moved since the manifest froze' -> ''`; FAIL expected `''` is not its v2.2 contract; FAIL the fixture is not its v2.2.0 bytes | — | **refused** | `456102aec3f4a3893e939a125656ca57675036f8f386d8de910dd917d203edff` |
| F2h: the same edit, the record hand-sealed (`render(run())`, bypassing the writer) and committed | hand: 57/57 | ran 25, 1 failure: Q0RoundV23 test 1 names the two contract problems, and only those (the record is current) | **red** | hand `28a506ce41227af5cfe978b94eb9d7ed6580790c519c11ce2dd8825871a13f42`, run `b27bda528dd02d9d91923b0b824a0437a00eaa13ec3070b312183a234dd23f8c` |
| F3: round stubbed, scope rule real | **rc 1, no record**: `validation/v23/impact.py` has no calibration; `SCOPES` does not cover `validation/v23` or `tests/v23`; 57/57, 0 changes | — | **refused** | `5b112dcd08a328fd18227e9093e59704c8b42aa64ba1af68fa2537ded082f3af` |

**Reading.**

* Under R4 the verifier measured F2's edit as writer rc 0 and run exit 0 (ran 40, 0 failures). Under R5 the writer
  refuses it (F2). A record sealed by hand is red at the gate (F2h), even though the record itself is current.
* With the stand-ins for the lanes' deliverables, the gate can still go green (F1).
* F1's writer measured 0 changes against the v2.2 record at this tree. This pass moves nothing in the v2.2 Q0: 57/57,
  with a calibration body equal to `714625b1…`'s.
* With the real scope rule, round v2.3 Q0 is red today on `impact.py` and `SCOPES` (F3), beside the closed round and
  the missing record.

Before the scenarios, the clone's sealed wiring and regression tests were run:
`ONLY="Seq13Wiring|Q0Wiring|test_sealing_gate|WiringR5|LedgerSeq13|Digest"` ran 31, 0 failures. Raw logs and the harness
(`e2e_r5.py` `28086444…`, `run_ids.py` `f04f4642…`, `stub_write.py` `9dd452a3…`, `guard.sh` `507ae907…`,
`mkcopy.sh` `96576d62…`) stay in scratch. The clone was deleted afterwards.

### 9.3 Measured in the worktree (no copy, env guard)

* `v23_scope_problems()` at `29c40b07` returns 3 problems: `validation/v23/impact.py` has no calibration, and
  `SCOPES` does not cover `validation/v23`, nor `tests/v23` (0.3 s).
* `contract_problems(<the v2.2 record>)` returns `[]`: all 57 fixtures equal v2.2.0's (0.6 s).
* `discover -s tests/v23`: ran 90, OK, 26 skipped (gated).
* `tests/v2/test_sealing_gate.py`: 3 OK.
* `tests/v2/test_v1_evidence_guard.py`: 26 OK.
* `tests/v2/p0/test_checker_calibration.py`: 13 ran, OK, 9 skipped (gated).
* `tests/test_meta.py` encoding scan: 2 OK.
* `ruff check tests/v23 validation/v23`: clean.
* `git apply --check docs/v2.3/drafts/SEQ13-WIRING-R5.patch`: passes.

### 9.4 The wiring: `SEQ13-WIRING-R5.patch` (sha256 `ceab41236847845be64831b16966fd1eecfbc120771372678eb02543595a91b3`)

It uses R4's mechanism, unchanged, on `tests/v2/sealing_gate.py` only, with GATED byte-identical (`WiringR5`). Only the
pins are re-taken:

| Pinned file | sha256 (LF) | vs R4 |
|---|---|---|
| `tests/v23/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | same |
| `tests/v23/test_v23_q0_round.py` | `653c06423a4eeaac7888a26c593f900eff8755a915ff64a57398f4e4a0048b86` | changed |
| `tests/v23/test_v23_rounds.py` | `ddef983626724a35a83c499d731f049641e92d2c566fd49d44c7b25d8e6b7cbc` | changed |
| `validation/v23/ledger_digest.py` | `660624c01b47811b8b9d2f41f371d4b721bb8b7c802eaa87b656c05f99ee3df9` | same |
| `validation/v23/q0_round.py` | `038906381a500a0c40e179803078c471527f960b884644d34eea64b4ff85fccf` | changed |
| `validation/v23/replay_v22.py` | `3f54e22b0f201072be279c058381e2dee3726bd86ac09bc52b3a09bbb788f87e` | same |

R4's patch applied to this tree skips none of the 12, because its pins no longer hold
(`WiringR5.test_R4s_patch_on_this_tree_skips_nothing`).

### 9.5 The revised seq-13 object

`docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R5.md` (file sha256 `d94a08bbc788b9324aae390c9ebb38cb23a344c5f19095c6ee53433c17c02d79`),
**canonical ruling digest `44d73a7851e08eb08b57c96a3b6fe7f03b74dc180a9bda6e6c90a0715b3224f5`**.

* The authority stays a placeholder that asks for the owner's own words quoting the digest. There is no signature and
  no approval date.
* R5 extends each of R4's `SCOPE`, `Q0_ROUND`, `SEALING_GATE`, `EVIDENCE_REVIEWED`, `NOT_AUTHORIZED` and `subject_to`
  by appending to it, so R4's text is a prefix of each (tested).
* `GATED_TEST_WIRING` names the R5 patch.
* The one new field is `BOUND_SHA256`:

| Bound file | LF sha256 |
|---|---|
| `docs/v2.3/amendments/Q0-1-V23-ROUND.md` | `0e0d0fbf822861134a073dac7da1be3ae2b2329c77ebf803ab7774809a7f8178` |
| `docs/v2.3/amendments/Q0-1-R5.md` | `d34e34b211bd0127af4a19964d98483ae005947f235f4a45624eeba6142130da` |
| `docs/v2.3/evidence/q0-round/COVERAGE-MAP-2026-11-21.json` | `644d874c610a8c8315554db2e402ac8bad9fa51d6006aaa902680714e054fc2c` |
| `docs/v2.3/evidence/q0-round/NEGATIVE-CONTROLS-2026-11-21.json` | `6ee4f872d35da24fb5c1ff6027584d22208e97f74f4ff3b107d3d9571550bea8` |
| `docs/v2.3/evidence/q0-round/Q0-DELTA-2026-11-21.json` | `f885b37454f99fa51c332c46fab9ee54b6e84876c5654a9ac4697d94f582ad54` |
| `docs/v2.3/evidence/q0-round/REPLAY-V22-Q0-2026-11-21.json` | `0f8bd55cd078e38115976c0c3d68fcf89f70fa37698654e048d5457e886e513c` |
| `docs/v2.3/evidence/round-auth/COVERAGE-MAP-2026-11-21.json` | `2bb5b5501b7ab966cef61ca13ca5bbbe4c40f9692284bce037e21ef4e9bd8c8d` |
| `docs/v2.3/evidence/round-auth/HISTORY-IDENTITY-2026-11-21.json` | `cc18861af3712821335c16ebbdc31604cef974d7006f726ab840dad2d9dad91f` |
| `docs/v2.3/evidence/round-auth/NEGATIVE-CONTROLS-2026-11-21.json` | `15087001cd877db180ea51f72be8db7b34aa103b99ac3fd4ea0e7ee013270969` |
| `docs/v2.3/evidence/round-auth/REPLAY-V22-2026-11-21.json` | `e7ef54c745b35ae709cc6fd591e9a42767899956defc4db1688c4ac48f33f8ae` |

This page quotes the digest, so it is the only page named by path alone. No bound file quotes the digest (tested).

### 9.6 NOT_DONE and residuals (stated)

**NOT_DONE.**

* Full suite and full sealing job: not run (project rule; the integrator's batch).
* `RoundV23.test_replay_v22` was not run in the patched clone, because of the one-copy rule. `replay_v22.py` is
  unchanged since R4 (its pin `3f54e22b…` is the same), so §8.2's replay of all 12 at v2.2.0 still applies to these
  bytes.
* Q0P-3 is measured on unit fakes only. The real round-v2.3 P5 record needs L1-F5's round selection and L1-QUAL's
  round-aware `GUARDS` / `guard_problems`.
* F1's green stands on the two labelled stubs. The real green needs the owner's seq 13, L1-F5 (`in_round`,
  `validate(round=)`, `impact.py` as a registered source), and L1-AUTHCHK (`SCOPES` widened, the 6 sites ledgered).
* The round-v2.3 Q0 record is not committed: the writer refuses it on this tree (F3).

**Residuals.**

* A checker's code can be weakened while it still fails its unchanged fixture for the named reason. This is Q0's own
  limit, the same in v2.2.
* `NOT_CHECKERS_V23` (`__init__`, `q0_round`, `replay_v22`, `ledger_digest`) is a ruling choice. If the owner wants
  `replay_v22.py` or `ledger_digest.py` calibrated as Q0 checkers, that is R6.
* `BOUND_SHA256` checks the working-tree bytes the sealing job sees.
* Two things are not detectable in-tree, as before: owner words the owner did not write, and a rewrite of the
  repository's own history.

## Reproduce

    python3 -P validation/v23/replay_v22.py                       # fresh clone at v2.2.0, all 11, exit 0 = PASS
    python3 -P validation/v23/replay_v22.py --coverage            # 40 assertions, 0 gaps
    python3 -P validation/v23/ledger_digest.py docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT*.md
    python3 -P -m unittest discover -s tests/v23 -t . -p test_v23_seq13_wiring.py   # RA-GP-1 / RA-INT-2 regressions
    AISEF_SEALING=1 python -P validation/v2/owned_run.py -- python -m unittest discover -s tests -q -p test_v23_rounds.py   # red today: round not open
    python3 -P validation/v23/q0_round.py --check                  # round-v2.3 Q0 vs this tree (red today: no record)
    python3 -P -m unittest discover -s tests/v23 -t . -p test_v23_q0_round.py   # Q0-1 controls (Q0RoundV23/Q0Wiring gated)
    python3 -P -c "import sys; sys.path.insert(0, '.'); from tests.v23.test_v23_rounds import reviewed_draft; from validation.v23.ledger_digest import digest; print(digest(reviewed_draft()))"   # R5's digest, from the draft as first committed (§9)

## 10. CI-portability corrections and draft R6 (re-pin; measured 2026-11-22)

The owner-ruled CI-portability corrections (2026-11-22) changed the bytes of two files R5's patch pins, so the seq-13
draft is re-issued as R6. Nothing here is applied or ratified: the owner status stays **CONDITIONAL HOLD**, R6 is not
authorized for the ledger, and `tests/v2/**`, `validation/v2/**`, `closure-evidence/**`, `aisef2/**`, R1–R5, their
patches and every file under `docs/v2.3/evidence` dated 2026-11-21 are unchanged.

**What changed (the fixes are the CI-portability batch's; each keeps or restores a check, none relaxes one).**

* `validation/v23/replay_v22.py` (`3f54e22b…` → `6b7195ec4aafb4cefcb304ad94325331853360206330d25e95af26e4449adc60`):
  F1 — `_child` reports record paths '/'-joined on every host; on a `\`-separated host the committed-bytes rule had
  dropped every record (failed open). F2 — `v22_clone` checks out with `-c core.autocrlf=false`, so the replayed tree
  is the committed bytes over a system-wide `autocrlf=true`. F3 — `coverage` sets `byte_identical_at_head` from
  `git hash-object --path` of the working-tree file against the v2.2.0 blob id (raw bytes wherever git applies no
  conversion, so exactly as strict as before on the Linux and macOS legs).
* `tests/v23/test_v23_q0_round.py` (`653c0642…` → `9b9433f33c1176367a80dd2a3144f37f8f3e2250d6cd62df9a3956bb3ca8c7cb`):
  the CRLF-checkout fixtures are built from LF-normalised bytes and the synthetic-tree writes pass `newline="\n"`, so
  each simulation feeds the product genuine CRLF on a CRLF host too; the docstring's wiring reference tracks R6.
* Not pinned, same batch: `tests/v23/test_v23_replay_v22.py` and `tests/v23/test_v23_seq13_wiring.py` carry the same
  fixture corrections (`newline="\n"` writes; `LedgerSeq13.setUpClass` takes the draft's LF bytes).
* For R6 itself: `tests/v23/test_v23_rounds.py` (`a8ab309988a6e9dd66bfa782dd6b5f65b204066ea73b511870d17451690323f3`)
  points `SEQ13_DRAFT_REL`/`SEQ13_PATCH_REL` at R6; `test_v23_seq13_wiring.py` renames the wiring class to `WiringR6`,
  adds `test_R5s_patch_on_this_tree_skips_nothing` and refuses R5 approved in words quoting R5's digest;
  `test_v23_ledger_digest.py` pins R6 and asserts every other ruling field is R5's verbatim.

**The wiring: `SEQ13-WIRING-R6.patch` (sha256 `25e7fc47b8e8bdde6f246daf68445dba5119c56cf3e6e3054c86e84fe45e8758`).**
R5's mechanism byte-for-byte on `tests/v2/sealing_gate.py` only; only the six pins are re-taken
(`git apply --check` passes on this tree):

| Pinned file | sha256 (LF) | vs R5 |
|---|---|---|
| `tests/v23/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | same |
| `tests/v23/test_v23_q0_round.py` | `9b9433f33c1176367a80dd2a3144f37f8f3e2250d6cd62df9a3956bb3ca8c7cb` | changed |
| `tests/v23/test_v23_rounds.py` | `a8ab309988a6e9dd66bfa782dd6b5f65b204066ea73b511870d17451690323f3` | changed |
| `validation/v23/ledger_digest.py` | `660624c01b47811b8b9d2f41f371d4b721bb8b7c802eaa87b656c05f99ee3df9` | same |
| `validation/v23/q0_round.py` | `038906381a500a0c40e179803078c471527f960b884644d34eea64b4ff85fccf` | same |
| `validation/v23/replay_v22.py` | `6b7195ec4aafb4cefcb304ad94325331853360206330d25e95af26e4449adc60` | changed |

R5's patch applied to this tree skips none of the 12, because its pins no longer hold
(`WiringR6.test_R5s_patch_on_this_tree_skips_nothing`).

**Re-derived evidence (the fixed tool, 2026-11-22; `--out`, written once).** The 2026-11-21 files stay committed as
measured history; `NEGATIVE-CONTROLS` (both), `Q0-DELTA` and `HISTORY-IDENTITY` came from scratch harnesses that are
not committed, so they are not re-derived and keep their reviewed bytes (their recorded `tool_sha256` names the
superseded tool, as measured then).

| File | sha256 (LF) | vs its 2026-11-21 counterpart |
|---|---|---|
| `round-auth/REPLAY-V22-2026-11-22.json` | `b72c65ff731b3336db07717a8d4c0299b79217df875a8929558e23a4d557d5ec` | verdict PASS; 12 tests (the tool's replay set includes the Q0 class since Q0-1; the 2026-11-21 file predates it with 11); the 11 shared ids have identical outcomes and record sets |
| `q0-round/REPLAY-V22-Q0-2026-11-22.json` | `3f49d43a8940cdc8b0e074311a0173ded6ec6cb932e3c43abd3de6ad7a487df3` | verdict PASS, 12/12, 4,734 Q0-class record reads; the field-level diff is exactly {`tool_sha256`, `date_utc`, `tree_source` (given → fresh-clone), `tests[].wall_s`, `tests[].duration_s`, `tests[].log_sha256`} — every record path/sha/committed flag and the Q0 identity (`714625b1…` committed = tree = regenerated) identical |
| `q0-round/COVERAGE-MAP-2026-11-22.json` | `6415fd11d9f6d2dacfe40ee7d9c6b33f82eaad1983f0681be48eada53b5d7898` | 59 assertions over 20 tests, 0 gaps; the field-level diff is exactly {`tool_sha256`, `counterparts_sha256`, `q0_counterpart_sha256`} |

On this POSIX host F1 and F2 are no-ops and F3 equals the raw-bytes comparison, which the diffs above confirm.

**The revised seq-13 object.** `docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R6.md` (file sha256
`84cf5291e28899455337700054b16ea37f8c9873f7d4439fdc702033398e7a09`), **canonical ruling digest
`a1469d009f2456fccde4a3b3e3706a993e6bc1524b5512873dbcefe6ccec01f0`**.

* The authority stays a placeholder that asks for the owner's own words quoting the digest. There is no signature and
  no approval date. **R6 supersedes R5; R5 is not to be ratified.** R1–R5 digest as recorded.
* Every ruling field except `GATED_TEST_WIRING`, `EVIDENCE_REVIEWED` and `BOUND_SHA256` is carried over from R5
  verbatim (`Digest.test_R5_is_unchanged_and_R6_repins_the_wiring_for_the_portability_fixes`).
* `BOUND_SHA256` swaps exactly the three re-derived files for their 2026-11-22 versions and keeps the two amendments
  and the five remaining evidence files at their reviewed bytes.

**Measured in the worktree (env guard, no AISEF_SEALING; gated classes skip).**

* `test_v23_rounds.py`: ran 21, OK (16 skipped). `test_v23_seq13_wiring.py`: ran 17, OK.
  `test_v23_ledger_digest.py`: ran 10, OK. `test_v23_q0_round.py`: ran 36, OK (10 skipped).
  `test_v23_replay_v22.py`: ran 9, OK.
* The full replay at v2.2.0 (fresh clone): all 12 PASS, exit 0, twice (the two `--out` runs above).
* `ruff check` on every touched file: clean.
* Negative control: in a scratch APFS copy, the R6 draft committed and then rewritten in place is refused by
  `reviewed_draft` ("is not the draft as first committed"), and `ledger_seq13_problems` returns
  "the ledger or the reviewed draft is unreadable: ValueError". The real tree is never touched.

## 11. Seq 13 committed (ROUND-AUTH R6 ratified; measured 2026-11-22, 14:54 UTC)

The owner's 2026-11-22 ruling ("W1a ACCEPTANCE AND W1b AUTHORIZATION", section B) approved the exact R6 proposal by
its canonical ruling digest `a1469d009f2456fccde4a3b3e3706a993e6bc1524b5512873dbcefe6ccec01f0` and the wiring patch
by sha256 `25e7fc47b8e8bdde6f246daf68445dba5119c56cf3e6e3054c86e84fe45e8758`, and instructed the append. Executed and measured at the commits below.

* `6910810d` — CIGOV-R1 decided first (option (a), byte-prefix; the amendment's Decision section), so the ledger
  append passes the released-evidence guard by the typed append-only rule, never an exception. Two defects of the
  rule's first draft (duplicate-JSON-key smuggle; index-only rewrite) were found by independent adversarial
  verification and fixed fail-closed with regression tests before the commit.
* `fd3b842c` — entry 13 appended (authority: the owner's section-B words verbatim with date and channel, quoting the
  digest; approver `human:owner`; entries 1–12 byte-identical), and `SEQ13-WIRING-R6.patch` applied, nothing else.
* Pre-append verification, each green before the write: both digests recomputed from the committed files (file and
  `reviewed_draft` paths agree); the complete proposed JSON matches R6 (the entry is the draft object, only the
  placeholder replaced); V23_PINNED all hold; `tests/v2/sealing_gate.py` byte-identical to v2.2.0's; the historical
  v2.2 replay PASS live (11 tests + the Q0 class, every record byte-identical at v2.2.0, the Q0 record regenerated
  `714625b1…`); the Q0 negative controls green (36 tests).
* Gate parity after the commit: `ledger_seq13_problems() == []`; `Seq13Wiring` (3 tests) and `Q0Wiring` (1 test)
  PASS under `AISEF_SEALING=1`; the 12 replayed v2.2 tests are skipped at HEAD naming the replay, and only while
  every pin holds; `LedgerHistory`, `LedgerAppendOnly` (CT-5), `HistoryKept` (CT-6) and the released-evidence guard
  all PASS on the committed tree.
* The round is NOT open: `round_v23_missing()` names exactly the two L1-F5 edges (`version_forward.in_round`,
  `currency_dag.validate(round=…)`), and a counterpart run under `AISEF_SEALING=1` FAILS with that same message —
  never skips. That red is the designed, truthful state until lane L1-F5 lands.
