# Q0-1 — a distinct v2.3 Q0 qualification round (delta, design, wiring)

Status: **draft for the owner's final ruling; authorizes nothing.** Owner, 2026-11-22: the architectural direction of a
distinct v2.3 Q0 round is approved; the historical v2.2 Q0 record must not be modified or invalidated; seq 13 is not
appended until the owner approves its exact contents. The exact seq-13 object is
`docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R4.md`; its digest and the evidence table are in
`docs/v2.3/drafts/ROUND-AUTH-PARITY.md` §8.

This amendment adds to W1-DESIGN.md §2.6 ("Q0 byte-identity"), §11 gate 3 and §12 (Q0-1). Nothing in W1-DESIGN.md
is edited. It corrects one claim there (§6 below).

## 1. What stays history and what is new

| | Round v2.2 (history, unchanged) | Round v2.3 (new) |
|---|---|---|
| Record | `closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json`, sha256 `714625b14e8972f166b37a467b5f83761d1f2672d076e5f5f0f342e2eb91332c`, never rewritten | `docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json`, written once by `validation/v23/q0_round.py --write` |
| Test | `tests/v2/p0/test_checker_calibration.py::CheckerCalibration` (GATED, byte-identical) | `tests/v23/test_v23_q0_round.py::Q0RoundV23` (`round_gate`, closed list `V23_GATED`) |
| Where it runs | at v2.2.0, by `validation/v23/replay_v22.py` (`Q0_REPLAYED`), inside the sealing job through `RoundV23.test_replay_v22` | at HEAD, in the sealing job |
| What it derives | `checker_calibration.run()` on v2.2.0's bytes; the record the replayed run derives MUST be byte-identical to the committed one | the same `checker_calibration.run()` on the HEAD tree inside `version_forward.in_round("v2.3")` |
| When it is green | always, at v2.2.0 (measured) | only with seq 13 committed by the owner, the v2.2 record still its v2.2.0 bytes, every registered checker calibrated, no v2.2 checker dropped, and the v2.3 record equal to what HEAD derives |

Nothing relaxes a checker. A v2.3 edit that moves a Q0 clean result keeps round v2.3 red until that checker is
calibrated again in round v2.3. Which edits do that is the delta below.

## 2. The exact Q0 delta

### 2.1 Measured

Method: an APFS clone of `0a034025` (the copy's `.git` replaced by a new repository whose object store borrows the
main one read-only), one representative edit per scenario, committed in the clone; Q0 regenerated (`render(run())`)
in its own process under the mutation-worker env guard; each checker's entry diffed against the committed record.
Host: Darwin 25.5.0 arm64, CPython 3.14.7. Evidence: `docs/v2.3/evidence/q0-round/Q0-DELTA-2026-11-21.json`.

| Scenario (lane that makes this edit) | Calibrated | Record | What moved |
|---|---|---|---|
| base (no edit) | 57/57 | byte-identical (`714625b1…`) | nothing |
| A: one comment line after `aisef2/app/run.py:693` (W1b L1-LIFECYCLE, DAG.md:338; later every lane that owns `run.py`) | **54/57** | moves (`a05d0d46…`) | `b1_bindings` clean red: 25 × "`aisef2/app/run.py` moved since the manifest froze"; `currency_dag` clean red (no v2.2 record binds the kernel); `mutation` clean red (25 run.py targets "target changed") |
| B: a new empty `validation/v2/gen_probe_grammar.py` (W5-main L5-AUTHOR, DAG.md:384) | 57/57 | moves (`fb76bd15…`) | `uncovered_checker_modules` = [that file]: `problems_of` red |
| C: one comment line appended to `aisef2/orchestrate/story_runner.py` (W1b; W2b L2-ACCOUNTING; W3 L3-SANDBOX; W4) | **55/57** | moves (`a8186826…`) | `currency_dag` and `mutation` (11 targets) clean red; `b1_bindings` known-bad `observed[0]` becomes the live kernel id (calibration holds, bytes move). Same as W1-DESIGN M4. |
| D: one comment line appended to `validation/v2/except_boundaries.py` (W1a L1-AUTHCHK, DAG.md:339) | **56/57** | moves (`fd7ba14c…`) | `mutation` clean red: its 9 targets "target changed" |
| E: ledger seq 13 appended (a throwaway entry; the owner's act) | 57/57 | byte-identical | nothing: committing seq 13 does not move Q0 |

Each run took 235–244 s.

### 2.2 Every checker (57) against the planned v2.3 edits

`cc` = `validation/v2/checker_calibration.py`. "Moves" means the clean result, the calibration or the record bytes.
MEASURED = scenarios A–E above; ANALYSED = code reading only, not measured.

| # | Checker (`cc` lines) | What its clean reads | Planned edits that reach it | Moves? |
|---|---|---|---|---|
| 1 | freeze_manifest (75-87) | RFC, approval, manifests, amendments, exceptions (`freeze_manifest.py:47`, `:188`) | none | no — MEASURED A–E |
| 2 | v1_evidence_guard (90-109) | every tracked file under `closure-evidence/` except `v2/` (`v1_evidence_guard.py:149`) | any new file under `closure-evidence/v2.3/` (Amendment A2 as written) | **yes if A2's path is used** (measured at `80046dbe`: 56/57, parity §5); no with `docs/v2.3/evidence/` |
| 3 | arch_catalog (112-117) | `aisef2/arch/enums.py` VOCABULARIES vs `docs/implementation/v2/arch-catalog.md` (`gen_arch_catalog.py:37-39`, `:79`) | a new vocabulary member (W2b L2-JOURNAL FORMAT-4, DAG.md:355; W1-DESIGN.md:298 forbids it for E5) | clean red until the catalog is regenerated — ANALYSED |
| 4 | f_conformance (120-127) | the RFC against the code's frozen sets (`freeze_conformance.load_inputs`) | a change of a frozen set (e.g. `Owner`, W2a L2-LIFECYCLE `control/owner.py`, DAG.md:352) — an RFC change, itself a STOP | not planned — ANALYSED |
| 5, 6, 38, 39 | plan_validate, plan_docs_check, plan_semantics, plan_baseline (130-154, 472-487) | the cycle-1 plan manifest and `docs/implementation/v2/` | none | no — MEASURED A–E |
| 7 | state_model_prover (157-171) | git history at `6ac6f74` | none | no |
| 8 | v2_encoding_scanner (213-225) | every `validation/v2/*.py` through `tests/test_meta.py`'s scanner | a new or edited `validation/v2` module with an encoding defect; W3 L3-PLATFORM edits the test_meta scan scope (DAG.md:367) | clean red only on a defect; the fixture's `observed` moves only if the scanner's message changes — ANALYSED |
| 9 | packaging_check (228-232) | `pyproject.toml` | W6 L6-RELEASE version bump (DAG.md:393) | no, unless the fixture's anchor text is edited — ANALYSED |
| 10 | run_history (235-240) | P1–P10 run histories + policy | none | no |
| 11 | **b1_bindings** (174-183) | raw sha256 of every B1 target source, the registry sha (`b1_bindings_check.py:14-31`; only lines starting `kernel ` dropped, `cc:181`) | sources and target counts in `B1-RISK-MANIFEST.json`: `app/run.py` 25, `app/bundle_cli.py` 45, `runtime/process_range.py` 25, `runtime/run_scope.py` 13, `app/adapters.py` 12, `app/client.py` 11, `journal/fold.py` 11, `app/settings.py` 10, `app/tripwire.py` 8, `app/bundle.py` 6, `app/verify.py` 5, `invariants/registry.py` 4 (+ registry sha), `app/feedback.py` 2 — owned by W1b (:338), W2a (:353), W2b (:356-357), W2c (:358), W3 (:366), W4a (:373-375), W4b (:376-377), W5 (:384-385) | **yes, from the first W1b edit — MEASURED A.** The known-bad `observed[0]` also moves on ANY kernel edit (MEASURED C). Round v2.3 stays red here until the owner rules OD-Q0-1-W1B / OD-B1B (a v2.3 B1 manifest, or holding the edits). W1-DESIGN's `kernel=` known-bad fix (:292) covers `observed[0]` only, never the clean. |
| 12 | **currency_dag** (186-191) | the 10 currency-DAG node checks under the v2.2 selection (round v2.2 + HEAD:aisef2) | any kernel edit (W1b on) | **yes — MEASURED A, C.** Green again only through L1-F5's round-v2.3 path (W1-DESIGN §2.6) and ROUND-AUTH |
| 13 | version_forward (194-210) | a synthetic chain | L1-F5 edits `version_forward.py`, keeping `CURRENT_ROUND` and the v2.2 `validate_chain` byte-unchanged (W1-DESIGN.md:296) | no, if L1-F5 keeps that promise — ANALYSED |
| 14–23 | the 10 kernel rules (243-249, 575-585) | every `aisef2/**/*.py` (`kernel_static_checks.py:290-292`) | every new or edited kernel module of W1b–W5 (incl. the 9 new ones: `journal/{sign,format4,transitions}`, the verdict projection, `app/{client_adapter,keybroker,harness_layer,draft,grade}`, `probe/diagnose`); L1-AUTHCHK tightening (DAG.md:331-332 requires clean `[]` and unchanged known-bad messages) | clean red only on a real violation — MEASURED unchanged for A, C; ANALYSED for W2–W5 |
| 24 | except_boundaries (252-255) | every `aisef2/**/*.py` (`except_boundaries.py:160-169`) | as 14–23; L1-AUTHCHK edits the checker | its own entry: as 14–23. Editing the file moves **mutation** (9 targets) — MEASURED D |
| 25 | invariants_doc (258-268) | `aisef2/invariants/registry.py` vs `docs/implementation/v2/INVARIANTS-V2.md` | a new invariant (W2c L2-AUTH `invariants/evidence.py`, DAG.md:358) | clean red until the doc is regenerated — ANALYSED |
| 26 | **mutation** (323-339) | every phase record against the whole-file LF digest of each target source (`mutation.py:2616`) | every edit of a target source: aisef2 (`run.py` 25, `story_runner.py` 11, …) and `validation/v2` (`old_path_audit` 33, `cleanup_authority` 16, `gen_migration_table` 14, `except_boundaries` 9, `destructive_authority` 6) — W1a L1-AUTHCHK, W1b, every W2–W5 kernel lane | **yes — MEASURED A, C, D.** Round v2.3 needs the F5 rule after the staged cut-over (W1-DESIGN.md:220) |
| 27 | cleanup_authority (291-320) | a live child of the runner; a synthetic host table | L1-AUTHCHK edits the checker | own entry no (tightening keeps the messages); the edit moves **mutation** (16 targets) — ANALYSED, D-like |
| 28 | destructive_authority (271-288) | every destructive call site in `SCOPES = ("aisef2", "validation/v2", "tests/v2")` against `destructive_sites.json` (`destructive_authority.py:33`, `:451`) | new destructive calls in W2a/W3 (`process_range`, `confine`); L1-AUTHCHK widening SCOPES to `validation/v21` + `validation/qualification` (5 unledgered process sites, W1-DESIGN §7) | clean red until each site is ledgered; editing the file moves **mutation** (6 targets). `validation/v23` and `tests/v23` are outside SCOPES today — ANALYSED |
| 29–34, 41 | p1…p6_evidence (342-375) | committed property records re-derived from kernel behaviour | behaviour lanes W2–W4 (journal, projections, quality, runtime) | no for comment edits (MEASURED A, C); a behaviour change must be re-measured per lane — ANALYSED |
| 35 | owned_run (435-438) | a live process range (`aisef2/runtime/process_range.py`) | W2a L2-PROBE-OS, W3 L3-SANDBOX edit `process_range.py` | only if its behaviour changes — ANALYSED |
| 36 | refmodel_independence (441-444) | `tests/v2/refmodel` imports | L1-AUTHCHK edits the checker | no — ANALYSED |
| 37 | gen_specs (459-469) | `tests/v2/fixtures/p1/corpus` | none | no |
| 40 | migration_table (447-456) | V1 proof modes vs `P6-MIGRATION-TABLE.json` + its doc | W5-early L5-EARLY edits `aisef/cli/*`, `aisef/control/budget.py` (DAG.md:383) | clean red if a V1 mode changes — ANALYSED |
| 42, 43 | old_path_audit, release_inventory (378-406) | the tree's authorities vs the content-addressed release inventory (`release_inventory.py:28-31`, `:54`) | any authority added or removed: new `aisef2/app` modules (W3 `client_adapter`, `keybroker`; W4 `harness_layer`; W5 `draft`, `grade`), `bundle_cli.py` edits | clean red ("UNENUMERATED authority") until a new inventory file and pin; the known-bad `observed` lists live authorities, so it can move too. Editing `old_path_audit.py` moves **mutation** (33 targets) — ANALYSED |
| 44 | authority_limits (409-415) | `bundle_cli.migrate`/`approve` and `review_verify.verify` sources | W2c, W4a, W5 edit `bundle_cli.py`; W5 L5-GATEWAY edits `review_verify.py` | the known-bad `observed` quotes `bundle_cli.py` line numbers (`:669`, `:672`, `:404`): an edit that shifts those lines moves the record bytes even while calibrated — ANALYSED |
| 45 | execution_order (418-432) | `EXECUTION-ORDER-9.json` vs `T0-SWEEP-8.json` and the live null-mutant digests | a re-shaping edit of a target (not a comment) | no for A, C, D (MEASURED); re-shaping: yes (W1-DESIGN.md:293, fix `at=V2_2_0`) |
| 46 | cycle2_baseline (490-507) | immutable files and trees, and `aisef2/probe/{protocol,python_callable}.py` (`cycle2_baseline.py:48-62`, `:231`) | W2a L2-PROBE-OS edits `aisef2/probe/*.py` (DAG.md:353) | clean red if either probe source changes — ANALYSED |
| 47 | probe_catalog_closure (510-514) | probe identities (catalog digests) | a probe identity change (V21-24/25: keep = no change; a change is an immutable-evidence STOP, DAG §5a) | no while kept — ANALYSED |
| 48–52 | the 5 probe rules (517-523) | `aisef2/probe/**` | E3 (W2a), `probe/diagnose.py` (W5-early) | clean red only on a violation — ANALYSED |
| 53–56 | cohort_confined, cohort_boundary, development_regression_bound, no_cohort_record (526-559) | `aisef2/cohort/**` (read-only until W6), the LedgerLock binding, a census of every JSON record | W6 L6-EVAL (#64–#66, B2 records) | W6 only — ANALYSED |
| 57 | profile_freeze (562-568) | the profile-freeze record | none | no |
| — | registry: `uncovered_checker_modules` (607-613), `checker_count` | every `validation/v2/*.py` must be some checker's source | W5-main `gen_probe_grammar.py` (DAG.md:384) | **yes — MEASURED B.** The honest fix is a new registered checker with its own fixture (58 checkers), which only round v2.3 can record |

**Reading.** The v2.2 record cannot stay byte-identical past the first W1a L1-AUTHCHK commit (D) or the first W1b
commit (A, C). Only a distinct round can record v2.3's Q0 without rewriting history, and three entries
(`b1_bindings`, `currency_dag`, `mutation`) stay red in round v2.3 too until their own v2.3 rule or owner ruling
lands. The round records what the tree derives. It never makes a red checker green.

## 3. Design

### 3.1 Historical side: the v2.2 Q0 replayed at v2.2.0

`validation/v23/replay_v22.py` gains `Q0_REPLAYED = "tests/v2/p0/test_checker_calibration.py::CheckerCalibration"`
and `REPLAYED = (*V22_REPLAYED, Q0_REPLAYED)`, the default set. The Q0 class runs like the 11: alone, under v2.2.0's
own `owned_run.py`, with `AISEF_SEALING=1`, the env guard, the clean-tree preflight and the committed-bytes rule. In
addition:

* after the class ran, the child renders the class's own `setUpClass` result with the module it calibrated with
  (`cc.render(CheckerCalibration.result)`). There is no second calibration and no edit of v2.2.0 code;
* `q0_identity` takes three sha256: the record committed at v2.2.0, the file in the tree, and the regenerated bytes.
  They must be equal;
* `q0_problems` names each way this can fail, closed: not committed, missing from the tree, corrupted in the tree, not
  regenerated (the class could not calibrate), regenerated but not byte-identical. The last one is caught even when the
  test itself would pass.

`coverage()` maps each of the class's 9 test methods to the same-named `Q0RoundV23` method. All assertions are
verbatim except one, `REBOUND`: the record assertion `(ROOT / cc.OUT_REL).read_text(…) == cc.render(self.result)`
becomes `(ROOT / Q.V23_REL).read_text(…) == Q.render(self.result)`.

### 3.2 v2.3 side: `validation/v23/q0_round.py` and `Q0RoundV23`

* `run()` = `checker_calibration.run()` inside `version_forward.in_round("v2.3")`. While L1-F5's `in_round` does not
  exist it runs the v2.2 rules: stricter for the round-aware cleans, so possibly red and never a false green. The
  counterpart fails on the closed round anyway.
* `render(result)` wraps the result with the round's identity: round `v2.3`, and the historical record by path and
  sha256.
* `history_problems()`: the v2.2 record is present and its LF sha256 is `714625b1…`, else fail closed naming it.
* `record_problems()`: the v2.3 record is missing, corrupted (not UTF-8 JSON) or stale (not what HEAD derives).
* `dropped()`: every checker the v2.2 record calibrated is calibrated in round v2.3. A round may add a checker, never
  drop one.
* `problems()` adds the count rule: every registered checker is calibrated.
* `--write` refuses while round v2.3 is closed (`test_v23_rounds.round_v23_missing`), while any checker is
  uncalibrated, or when the file exists (`open(…, "x")`). A re-seal is `git rm` plus `--write` in one commit.

`tests/v23/test_v23_q0_round.py`:

* `Q0RoundV23` (`round_gate`): the v2.2 class's 9 tests, bodies verbatim. Test 1 first asserts, in one message: round
  open + history intact + nothing dropped + the v2.3 record current. Tests 2–9 first assert the round is open. So under
  `AISEF_SEALING=1` every test FAILS, never skips, until seq 13 (R4) is committed and the record is written.
* `Q0Wiring` (`round_gate`): `V22_REPLAYED_Q0` is exactly the Q0 class, it is in GATED, this file and `q0_round.py`
  are pinned, every pin holds, and the v2.2 class is skipped at HEAD naming the replay.
* Always run: `Q0Record` (each record and history failure mode on throwaway roots; the writer), `Q0Coverage` (9 methods,
  0 gaps, one rebound, a dropped assertion is a gap), `Q0Replay` (the replay on synthetic v2.2.0 trees: intact,
  missing, corrupted, regenerated-but-different, could-not-calibrate).

Cost. The v2.2 class's 250 s calibration does not run at HEAD any more (skipped by the wiring). `Q0RoundV23` runs it,
once, in `setUpClass`, even on a closed round, so test 1 can name the record's state. The replay adds one calibration at
v2.2.0 (245.6 s measured). Net: one extra Q0 run per sealing job.

W1-DESIGN §2.6 plans `tests/v2/test_v23_q0_byte_identity.py`. Its part (ii) asserts that after E5 `render(run())` equals
the committed v2.2 record. MEASURED A shows that cannot hold, so its round-v2.3 replacement is `Q0RoundV23`, against
the round's own record. Its part (i) (in-tree `observed` equality for five checkers) remains L1-F5's to build. Under
Amendment A2 any new test goes in `tests/v23/`.

### 3.3 Placement of the round-v2.3 record

It goes at `docs/v2.3/evidence/q0-round/`, beside W1a's F5 evidence and the round-auth evidence. There are two
alternatives, and each turns a gate red:

* Under `closure-evidence/v2.3/` the V1 evidence guard fails (`v1_evidence_guard.py:149`; measured at `80046dbe`:
  `test_v1_evidence_guard` red and Q0 56/57).
* Under `closure-evidence/v2/` the new file sits inside a mutation COPY root, so it invalidates every F5 target (R2S).
  It also falls inside `cycle2_baseline`'s guarded trees when written under one of them.

The record carries no commit id: it is derivable content only. A commit id would be a hash cycle with the commit that
holds it.

### 3.4 Wiring: `docs/v2.3/drafts/SEQ13-WIRING-R4.patch` (never applied on the branch)

This is R3's mechanism, extended, and it still changes `tests/v2/sealing_gate.py` only:

* `V22_REPLAYED_Q0 = ("tests/v2/p0/test_checker_calibration.py::CheckerCalibration",)` is added;
* `sealing()` skips a `V22_REPLAYED` or `V22_REPLAYED_Q0` test only while `V23_PINS_HOLD`;
* `V23_PINNED` grows to 6 files: `tests/v23/__init__.py`, `tests/v23/test_v23_q0_round.py`,
  `tests/v23/test_v23_rounds.py`, `validation/v23/ledger_digest.py`, `validation/v23/q0_round.py`,
  `validation/v23/replay_v22.py`. The Q0 test therefore joins the replayed set only together with its pinned
  counterpart; deleting or editing any pinned file un-skips all 12.

GATED, the 18 gated test files and `tests/v2/test_sealing_gate.py` stay byte-identical (checked by
`WiringR4.test_the_patch_is_current_and_keeps_GATED`). `tests/v23/test_v23_rounds.py` now names R4's draft and patch
(`SEQ13_DRAFT_REL`, `SEQ13_PATCH_REL`), so the round opens only for R4's digest in the owner's words. R3's patch,
applied today, skips nothing: its pins no longer hold
(`WiringR4.test_R3s_patch_never_skips_q0_and_on_this_tree_skips_nothing`).

## 4. Affected code (this amendment's commit)

| File | Change |
|---|---|
| `validation/v23/q0_round.py` | NEW: the round-v2.3 Q0 |
| `validation/v23/replay_v22.py` | the Q0 replay, its byte-identity check, Q0 coverage |
| `tests/v23/test_v23_q0_round.py` | NEW: `Q0RoundV23`, `Q0Wiring`, and the always-run controls |
| `tests/v23/test_v23_rounds.py` | names R4's draft and patch; `V23_GATED` gains the two Q0 classes |
| `tests/v23/test_v23_seq13_wiring.py` | `WiringR4`: 6 pins, the 12, the R3 contrast; R3 approved is refused |
| `tests/v23/test_v23_ledger_digest.py` | pins R3's digest; R4 as stated and only extending R3 |
| `docs/v2.3/drafts/SEQ13-WIRING-R4.patch`, `LEDGER-SEQ-13-DRAFT-R4.md` | NEW: wiring and seq-13 object |
| `docs/v2.3/evidence/q0-round/*` | NEW: evidence (parity §8) |

These are untouched: `closure-evidence/**` (including the v2.2 Q0 record), `tests/v2/**` (including
`tests/v2/p0/test_checker_calibration.py` and `sealing_gate.py`), `validation/v2/**`, `aisef2/**`, the workflows, and
R1–R3 with their patches.

## 5. What this does not decide, and residuals

* **Not decided:** OD-Q0-1-W1B / OD-B1B (b1_bindings at the first W1b run.py edit), OD-NEWMOD (gen_probe_grammar.py),
  the F5 cut-over (`mutation`) and L1-F5's round path (`currency_dag`). Each stays the owner's or its lane's. **Final
  E5 qualification waits at this boundary**: with W1b's `run.py:693` edit, round v2.3 Q0 is red on `b1_bindings`
  (MEASURED A) until the owner rules.
* The calibration code itself is not pinned: `validation/v2/checker_calibration.py` and the checker modules are owned
  by L1-F5 and L1-AUTHCHK and carry planned edits. These still hold:
  * the replay runs v2.2.0's own code;
  * `Q0RoundV23`'s verbatim self-tests catch a calibration that cannot say NO (always-PASS mutant, fail-everything,
    wrong reason, missing or stale fixture);
  * `dropped()` catches a removed checker;
  * the record equality catches any change in what HEAD derives.
  
  Not caught: a checker weakened yet still failing its fixture for the named reason. That is Q0's own limit, the same
  in v2.2.
* If L1-F5's `in_round` did not govern the module instances calibration uses, the round-aware cleans would be computed
  with the v2.2 rules: red, never green. (`currency_dag.py` imports `validation.v2.version_forward` by package, so it
  shares the round with `q0_round.run`.)
* A coordinated forgery is not detectable in-tree, as in R3: owner words the owner did not write, or a history rewrite
  of the R4 draft.
* The round-v2.3 Q0 record is not written. It cannot be: the writer refuses while the round is closed, and the round
  needs seq 13 and L1-F5.

## 6. Correction of W1-DESIGN.md:286-299

The text there says "Clean (`:181`) unchanged … Verdict: byte-identity is mechanically feasible for every checker.
Q0-1 is not triggered". That verdict rests on a probe that edited `aisef2/orchestrate/story_runner.py` only (:286).

* That probe does not cover `aisef2/app/run.py`: the B1 manifest binds the raw sha256 of `run.py` for 25 of its 177
  targets. The first W1b edit at `run.py:693` turns `b1_bindings`' clean red (MEASURED A). `cc:181` drops only lines
  starting `kernel `, and the planned `kernel=` known-bad fix leaves the clean unchanged.
* L1-AUTHCHK's W1a edits of `except_boundaries.py`, `destructive_authority.py` and `cleanup_authority.py` move the
  `mutation` clean under the v2.2 rule (MEASURED D). W1-DESIGN's remedy is the F5 rule, which is a v2.3-round rule.

**Q0-1 is triggered in W1a and W1b.** This amendment's distinct round is the design answer the owner approved in
principle. The `b1_bindings` entry still needs the owner's ruling.
