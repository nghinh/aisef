# ROUND-AUTH parity — the evidence for ledger seq 13 (draft R2), items 1–5

Owner status: **CONDITIONAL HOLD**. The principle of a separate v2.3 qualification round is approved. The seq 13 draft
is not authorized for the ledger. This page is the evidence the owner asked for before any ratification request. It
is a draft and authorizes nothing.

Code commit: `f237ad14` on `v23/roundauth`, based on `release/v2.3-big` at `1e25ef84`. v2.2.0 = `da3ea33f3b695aaca73e87a704145a0193aced23`.
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
| `docs/v2.3/drafts/SEQ13-WIRING.patch` (not applied) | `c5bfc527182c9f5969532630b680b98e746c867ebf351e28e3b5c4e5c2bbd68b` | 4b |

Tools: `validation/v23/replay_v22.py` (sha256 `3414936eac1e1b70ef626c12b1348f8c2d2c90041980bdb743e5a6ff8fcf9a46`,
LF), `validation/v23/ledger_digest.py`. Tests: `tests/v23/test_v23_rounds.py` (sha256
`62061facbc0f49335991165e44c73fb4eb48a673faf10ebf8ea688691d1e32d3`), `tests/v23/test_v23_replay_v22.py`,
`tests/v23/test_v23_ledger_digest.py`. The scratch harnesses of items 4 and 5 are not committed; the evidence files
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
* **(i)** the round is open: ledger seq 13 `AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED` is committed by `human:owner`;
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
* The later code commit changes only `tests/v23/test_v23_rounds.py`.

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

## 6. The revised draft

`docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R2.md`: canonical ruling digest
`a7fa9f97c6a324f3f1d53df2ca42cd8c46135751977bcdafa5c3d63716daa940` (`validation/v23/ledger_digest.py`). R1 is unchanged
(`824091110a8bb0fcf8726e889f4ff0c3f11e8f102dfa18f028e343a968caa79b`, recomputed by the same script). The changes and
their reasons are in R2.

## Reproduce

    python3 -P validation/v23/replay_v22.py                       # fresh clone at v2.2.0, all 11, exit 0 = PASS
    python3 -P validation/v23/replay_v22.py --coverage            # 40 assertions, 0 gaps
    python3 -P validation/v23/ledger_digest.py docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT*.md
    AISEF_SEALING=1 python -P validation/v2/owned_run.py -- python -m unittest discover -s tests -q -p test_v23_rounds.py   # red today: round not open
