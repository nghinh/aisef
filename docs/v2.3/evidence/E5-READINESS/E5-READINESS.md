# E5 readiness at HEAD `1e25ef84` (release/v2.3-big), read-only analysis, 2026-11-21

Scope: what E5 is, its mandatory gates, which prerequisites hold at HEAD, what each E5 edit does to F5/Q0/B1/sealing,
what preparation is safe now, and the ordered steps. Sources read: the plan (`AISEF-v2.3-BIG-UPDATE-PLAN.md`),
`docs/v2.3/{W1-DESIGN,DEPENDENCY-DAG,MASTER-CHECKLIST,CODE-AUDIT,BASELINE,ARCHITECTURE,RELEASE-CHARTER}.md`, the code
(`aisef2/orchestrate/story_runner.py`, `aisef2/app/run.py`, `validation/v2/{b1_bindings_check,checker_calibration,mutation}.py`),
the committed Q0 record and B1 manifest, and (read-only, `git show`) the lane branches `v23/lanes`, `v23/roundauth`,
`worktree-wf_3f073485-4b3-1`. Nothing was run in the main checkout. One scratch computation was made (§3.2, B1 probe),
then deleted.

Labels: **[measured here]** = computed in this analysis; **[doc]** = figure quoted from a design doc, not re-measured;
**[not measured]** = open.

---

## 1. Definition and mandatory acceptance gates

### 1.1 Definition (exact quotes)

- Plan W2 deliverable (`AISEF-v2.3-BIG-UPDATE-PLAN.md:57`): "`E5` typed stage-machine, deterministic sequence and
  finally `story/dispose+story/end`".
- Roadmap source (`docs/ROADMAP-2.2-CHECKLIST.md:115`): "**E5** — `_attempt` thành chuỗi Stage có kiểu + `finally` luôn
  ghi `story/dispose + story/end` (fault không còn làm hỏng cả run); land cùng full suite + mutation re-run (L)
  *(làm TRƯỚC C1/C5)*".
- Charter claim 2 (`docs/v2.3/RELEASE-CHARTER.md:14`): "typed stage lifecycle and deterministic `finally` (`E5/E6/E7`)".
- Frozen design (`W1-DESIGN.md:572-588`): no `finally`, by design. A blind finally raises `ProjectionError` (dispose
  and end are refused before an outcome, `story_state.py:54-61`). "E5 MUST work out what it writes from where the
  attempt is in the journal. E5 MUST NOT write anything on a `BaseException`." The charter claim is met as a
  "deterministic closure". A one-line charter erratum is "proposed for the owner" (`:588`). **That erratum is an owner
  act and has not been taken.**
- Wave: W1b, after W1a's F5 gates (`MASTER-CHECKLIST.md:20`, `DEPENDENCY-DAG.md:32` R11). V21-23 is its DUPLICATE
  (`MASTER-CHECKLIST.md:108`). CODE-AUDIT #2 (P1, `CODE-AUDIT.md:12`) and #39a (`:50`) are in W1b. #39b is W2b (`:51`).

### 1.2 Mandatory acceptance gates (exact quotes, with citations)

| # | Gate | Source |
|---|---|---|
| G-1 | "E5 landed with the fault matrix (§4.5) and the golden byte-identity test (§4.6); `aisef2/` changed only in `story_runner.py` and `run.py`'s refusal branch; qualified through F5 — `currency_dag --affected` lists only nodes whose own guard fired, re-derived as MEASURED; no other Q0 entry moves." | `W1-DESIGN.md:1178-1180` (§11 gate 5) |
| G-2 | Checklist needed work: "typed Stage + _Stages.advance guard and one try…except Exception (no finally) per H1–H9; fault matrix F1–F25/G1–G2/R1 (test_v23_story_lifecycle.py) and golden success-path byte-identity (test_v23_story_golden.py); declared limits §4.8". W0 closure adds: "Add a negative test: a fault raised inside _attempt still journals STORY_DISPOSE+STORY_END and disposes the scope." | `MASTER-CHECKLIST.md:20` |
| G-3 | H9 static shape, with "**no checker edit**": R6 (one constant-label `checks.append(gate.check(...))` per label, after its stage call; exactly one `gate.decision`; `budget.charge` before `run.retry`), R3, and the authority-inventory rows `_attempt`/`_fail`/`run_story` unchanged. "old_path_audit.py MUST NOT be edited, and any violation is STOP Q0-1." | `W1-DESIGN.md:665-670` |
| G-4 | "The real E5 MUST add no `enums.VOCABULARIES` member and no event type. Any other moved entry is STOP Q0-1." "`test_v23_q0_byte_identity` (ii) MUST be re-run on the real E5 commit before gate 3 is claimed." | `W1-DESIGN.md:298`, `:286` |
| G-5 | "The release authority inventory and the six static proofs MUST hold without regeneration (H9), or STOP Q0-1." | `W1-DESIGN.md:815` |
| G-6 | "E5 MUST NOT edit or remove any existing import or module-level statement of `story_runner.py` (it only adds)." "W1 has **one** targeted run, after W1b lands, over W1a ∪ W1b." | `W1-DESIGN.md:842-843` |
| G-7 | "The E5 term is decided by tier R. Its scope and the serial-hour price of the reached set MUST be written to the W1 report before the targeted run." | `W1-DESIGN.md:1147`; also §4.7 heading `:797` |
| G-8 | "K-NOWORK (V21-13) and test_b1gap5 stay green unchanged". Checklist: "E5 (W1b) must keep both K-NOWORK case-E tests green." | `W1-DESIGN.md:772`; `MASTER-CHECKLIST.md:125` |
| G-9 | "INV-IX static proof -> E5 acceptance [G] no gate row before its stage call" | `DEPENDENCY-DAG.md:184` |
| G-10 | Common wave gate: "every changed target is MEASURED; every reused target is VERIFIED_REUSE with its proof; 0 UNRESOLVED accepted; seeded known-bad calibration still FAIL", plus ruff, the full suite on the main tree, and CI on 6 legs + sealing. | `DEPENDENCY-DAG.md:469-482` |
| G-11 | §11 gate 8: the one-function-kernel-change class is judged cold-vs-incremental against baseline (ii). If it misses the 50 % target it is reported "**not met**", "never narrowed by relaxing R1/R2". | `W1-DESIGN.md:1182-1185` |
| G-12 (carried) | W2 exit: "E5's W1b fault-injection tests stay green under E6/E7/E1 (#2)." | `DEPENDENCY-DAG.md:487` |

Ordering rules that hang on these gates: "E5 (W1b) -> W1-EXIT [G] owner ruling: E5 before G6/C5/G9/C1"
(`DEPENDENCY-DAG.md:169`); "E5 before E1/E6/E7 and before C1/C5" (owner directive v2.3 :53); `E5, E6, E7 -> C5`,
`E5 … -> G6`, `E5, C8 -> C1` (`DEPENDENCY-DAG.md:211,215-217`). The owner sentences quoted in the task brief ("next
mandatory kernel milestone after W1 qualification is sound", "independent E5 preparation may proceed…") are not in
the repository at HEAD, so they are treated as the task's framing. The repository rules above say the same thing.

---

## 2. Prerequisites and their state at HEAD `1e25ef84`

Hard edges into E5: `F5-ROUND -> E5 (W1b)` and `F5-MEASURE -> E5 (W1b)` (`DEPENDENCY-DAG.md:167-168`);
`F5 -> E5 and every aisef2/ change` (`:173`).

| Prerequisite | State at HEAD | Evidence |
|---|---|---|
| Kernel untouched in W1a | **MET.** `HEAD:aisef2` = `e865d65c` = `da3ea33f:aisef2`. story_runner.py and run.py are byte-identical to v2.2.0. | `git rev-parse` [measured here] |
| W1a F5 engine | **PARTIAL, NOT MET.** `validation/v23/impact.py` exists (static classify). Disposition 2: 0 VERIFIED_REUSE, 667 INVALIDATED (R6) / 17,322 mutants, 327 UNRESOLVED (I6) / 10,078. Missing at HEAD: `mutation.py` F5 source rule, `--states/--affected/--run-affected`, `V23_REL` writer and read-time supersession, `V23_NEW_TARGETS`. The negative tests name only N1, N2, N8, N14, N20, N23 and N33. §11 gate 1 needs N1–N34 + NA1–NA9. | `docs/v2.3/evidence/F5-DISPOSITION-2/README.md`; `git grep` [measured here] |
| F5-ROUND (`version_forward.in_round`, `currency_dag.validate(round=)`, `rounds.py`, `p5_falsifiability` v2.3 guard, b1 known-bad `kernel=`, execution_order `at=`) | **NOT MET.** None of it is at HEAD. The R3 draft confirms: "neither exists today". | `v23/roundauth:docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R3.md` |
| Recorder (`observe.py`, strace `os_trace`) | **NOT at HEAD.** It is on `worktree-wf_3f073485-4b3-1` (`75080a80`, `f95ff6e8`, `8a31f7c8`) with A2/A3 amendments, and "No observation of a repository kill file has been recorded" (A3:146). The darwin audit backend "is never sufficient for Δ ≠ ∅" on the repository (A3 C5). That branch puts evidence under `closure-evidence/v2.3/f5-observe/`, which breaks the corrected placement rule; it must be `git mv`'d before merge. | `git show` of the branch |
| R2S precision floor | Δ already holds 9 files added under `closure-evidence/v2` since v2.2.0. `tests/v2/test_p9_reproduction.py` names `closure-evidence/v2` and sits in every S(F). So against the v2.2.0 basis, "R2S invalidates every target that passes I6 even with complete observations". **No target can be VERIFIED_REUSE against v2.2.0, with or without E5.** | `…/f5-observe/R2S-REPOSITORY-EFFECT.json` (wf branch) |
| ROUND-AUTH / ledger seq 13 | **NOT MET.** The ledger holds seq 1–12 only (last: `AISEF_V2_2_0_PRODUCTION_PUBLISH_AUTHORIZED_RC2`). HEAD has only the R1 draft. R2 and R3 are on `v23/roundauth`. R3 status: "owner CONDITIONAL HOLD … this draft is **not** authorized for the ledger"; "R2 must not be ratified". It blocks exit gate 3, not the start of W1b (`W1-DESIGN.md:1196-1199`). | `RELEASE-DECISIONS.json` [measured here]; R3 draft |
| Q0-1 boundary | **Not triggered at HEAD.** The Q0 record shows 57/57 calibrated; b1_bindings `clean_problems: []`. **E5 as designed triggers it** (§3.2). | Q0 record [measured here] |
| SCALE-1 (PLAT-1 / DIGEST-READ) | **Undecided.** Default: "build and prove the engine (W1a, all local); measure nothing large". It gates the single targeted run and exit gates 2, 5 and 8. | `W1-DESIGN.md:1200-1205`; `DEPENDENCY-DAG.md:442` |
| L1-BUILD, L1-F2, L1-TESTENV | Done on `v23/lanes` (`04802164`…`4c0892be`), **not merged at HEAD**. Evidence sits at `closure-evidence/v2.3/l1-testenv/PLATFORM-PARITY.json` (placement violation; needs `git mv`). | `git log/diff` |
| L1-QUAL, L1-CIGOV (guard, `mutation-incr.yml`), L1-AUTHCHK | **Not found** at HEAD or on the three lane branches. HEAD has only the REL-GOV runbook and probe drafts (`docs/v2.3/drafts/relgov/`). | `ls`/`git log` |
| CI availability (DISC-1) | `origin/release/v2.3-big` exists at `19a7a4ed` (HEAD is 1 docs commit ahead). Whether DISC-1 is formally closed is not recorded. `BASELINE.md:72` still says "local only". | `git branch -r` |
| Disk | 24 GiB free on the data volume. That is above the 20 GiB floor with a thin margin (the replay clone is 1.8 GB [doc]). | `df -h` [measured here] |

---

## 3. What E5 changes, and the Q0 / B1 / sealing consequences of each edit

### 3.1 Files and mutation targets (frozen §4.4 / §8 / DAG §4)

| Edit | Mutation targets touched |
|---|---|
| `aisef2/orchestrate/story_runner.py`: `from enum import Enum` (added), `class Stage(Enum)` (13 members), `class _Stages` with `advance`, and the `_attempt` handler (one `try…except Exception`, no finally, H1–H9) | **I1: all 11 targets / 411 mutants** (`_attempt` 326, `_fail` 34, `run_story` 11, others 40), because `<imports>` is in every slice, plus about **+156 enum-swap mutants** on `_attempt` [doc §4.2, §4.7a]. Kill sets at HEAD: `_attempt` has 8 kill files [measured here]. |
| `aisef2/app/run.py:693` only: `results[story] = [f"REFUSED: {type(e).__name__}"]` becomes the journal's outcome words (`outcomes_from`, :393-401), else REFUSED | F5 I1: `run.py::execute` only (459 mutants; 22 kill files at HEAD [measured here]). The v2.2 whole-file rule: all **25 run.py targets / 1,087** [doc]. |
| `validation/v2/mutation.py`: append-only hunk, **written by L1-F5** (single writer): new target `_Stages.advance` (in `V23_NEW_TARGETS`, §2.5); `test_v23_story_lifecycle.py` appended last to the kill sets of `_attempt` and `execute`. It must touch no I9 component. | `mutation.py` closure: 1 kill file / 5 targets / 497 [doc §2.8]. Its CONFORMANCE-RULING row is already INVALIDATED by W1a. |
| NEW `test_v23_story_lifecycle.py` (kill file) and `test_v23_story_golden.py` (not a kill file) | see §3.3 (placement conflict) |

Dependent scope (tier R, R0–R8). Strict R6 makes every kill file that loads `story_runner.py` INVALIDATED. R2
(`kernel_digest`, `run.py:93-100`, read by 31 kill files) re-opens ≥ 444 targets / 13,482 mutants for any `aisef2`
byte. Without `os_trace`, R1 re-opens everything [doc §10:1150-1153]. W1b E5 upper bound: **651 targets / 18,308
mutants / 315.8–341.1 serial-h, wall floor 36.55 h (`run.py::execute`)** [doc §10:1141]. Given R2S (§2), the first
v2.3 targeted run is effectively the 667 + (327 unless PLAT-1), close to a full campaign: 288.5 serial-h for the 667
[doc, Disposition 2].

Not changed: `gate.py`, `merge.py`, `run_scope.py`, `story_scope.py`, projections, `old_path_audit.py`,
`destructive_sites.json`, every existing test (§4.4).

### 3.2 Consequences per edit

**(A) `story_runner.py` edit**
- **B1.** `HEAD:aisef2 ≠ e865d65c`, so the `b1_bindings_check.py` CLI FAILs "kernel … is not the frozen e865d65c". The
  b1-linux/windows/rerun preflights refuse, and those workflows are `workflow_dispatch` only. story_runner.py is **not**
  a B1-manifest target source (0 of 177), so the Q0 b1 clean, which drops `kernel ` lines (`checker_calibration.py:181`),
  stays `[]` **[measured here, scratch probe]**. The Q0 b1 *known-bad* `observed[0]` moves ("kernel <new> is not the
  frozen 000000000000"). Fix: `problems(..., kernel=)` (L1-F5, `W1-DESIGN.md:292`).
- **Q0.** On a story_runner-only probe 4 of 57 entries move: mutation clean, currency_dag clean, b1 known-bad,
  execution_order clean. Each has a designed fix (`W1-DESIGN.md:286-299`) [doc; the probe was not the final shape].
  - The mutation clean stays on the v2.2 rule until the staged cut-over (§2.5:220). So Q0 is green on an E5 commit only
    after the 11 targets (+ `_Stages.advance`) have committed v2.3 entries. That means a measurement.
- **Currency DAG (after E5) [doc table :262-273].** INVALIDATED: K-NOWORK and Q5 (`write_v22` under `in_round`);
  CONFORMANCE-RULING (edit + ROUND-AUTH); ORCH (passes once the v2.3 ruling names the bytes); P5-FALS (unless its
  round-v2.3 guard lands). The others stay VR.
- **Sealing.**
  - Without the R3 wiring, a kernel edit makes 10 of the 11 v2.2-round GATED tests FAIL ("B + kernel edit: 11 RUN,
    10 FAIL", ROUND-AUTH-PARITY §7) [doc].
  - With R3 applied (needs seq 13), they skip while the pins hold. Their v2.3 counterparts stay red until the round is
    open and every node is MEASURED/VR.
  - Of the 7 GATED tests that run at HEAD, `CheckerCalibration` = Q0.
- **Static.** H9 R6/R3/authority inventory must hold with no checker edit. **[not measured on any real E5 shape]**.

**(B) `run.py:693` edit: the Q0-1 trigger the design misses**
- The B1 manifest (`closure-evidence/v2/v2.2/B1-RISK-MANIFEST.json`) binds **25 `aisef2/app/run.py::*` targets** to the
  **raw** sha256 `cfb2fb7a…` of run.py. `b1_bindings_check.problems` re-hashes `read_bytes()` with no LF
  normalisation.
- Scratch probe **[measured here]**: an untouched copy gives Q0 b1 clean `[]`. With the :693 hunk applied it gives **25
  problems** ("aisef2/app/run.py::OCR_CHECKS: aisef2/app/run.py moved since the manifest froze", …). With a
  story_runner-only edit it gives `[]`.
- So Q0's `b1_bindings` entry turns `clean_passes: false, calibrated: false`; the record moves to 56/57.
  `checker_calibration --check` FAILs, and the GATED `p0/test_checker_calibration` goes red.
- The design's Q0 table was measured on a story_runner-only probe (`04c55b6a`). Its b1 fix covers only the known-bad
  and says "Clean (`:181`) unchanged" (`W1-DESIGN.md:292`). No fix exists for this entry. By `:298` ("Any other moved
  entry is STOP Q0-1") and DAG §5b Q0-1 ("the change waits if it would move Q0", `:444`), **the run.py hunk as designed
  is a STOP Q0-1.**
- Mutation: the v2.2 rule stales all 25 run.py targets in the Q0 mutation clean (baseline (i): 36 / 1,498 with
  story_runner). F5 I1 is `execute` only. `execute` alone is ≥ 36.55 serial-h, so it sets the wall floor before Q0's
  mutation clean can return [doc M9].
- Currency nodes that bind run.py: "not measured; the audit hook declares them [E]" (`W1-DESIGN.md:813`) **[not measured]**.
- What it buys: without it, every story E5 closes makes `--verify` report "the record's story outcomes are not the
  journal's" (`verify.py:212-216` compares exact lists against `outcomes_from`), and the R1 fault row fails. Option (A)
  "contain and return ROLLBACK" is rejected (breaks `e2e_guest.py:690`, §4.4:714).
- Owner options (none is the agent's to take):
  - **Q-a.** A round-v2.3 b1 clean that accepts a moved B1-bound source only when that target is MEASURED in v2.3.
    The record stays byte-identical, but the semantics of a Q0 checker change. That is an evidence contract.
  - **Q-b.** An append-only v2.3 Q0 record. Q0 is write-once and owner-gated, so this is the larger change.
  - **Q-c.** Defer the :693 hunk to W2b L2-RECORD (E7), which owns run.py. Q0 stays reachable. Raising runs get a
    fail-closed verify FAIL (a false FAIL, never a false PASS) until W2b. This amends §11 gate 5 and the R1 row.
  - **Excluded:** rebinding the B1 manifest (forbidden: rebinding a `source_sha256`).

**(C) `mutation.py` hunk**
- It stays inside L1-F5's single targeted run.
- Reconcile one wording point. §2.5:205 says "Import-time tables MUST stay byte-identical". §4.4 appends a kill file to
  `_attempt`/`execute` through the import-time `PHASE_TARGETS` loop, as B1-amendments 5/6 did. I3 accepts a superset,
  and the measured blockers there concern records and membership, not kill-set lists.

### 3.3 Test placement conflict (needs an amendment before E5 lands)

The corrected A2 rule says new tests go in `tests/v23/`, which is outside every `mutation.COPY` root.

- `COPY = ("aisef2", "tests/v2", …)` (`mutation.py:1543-1547`). `_run_file` runs `discover -s <dir of F> -t tests`
  inside the runner tree (`:2168-2169`).
- So a kill file under `tests/v23/` is absent from the tree the mutants run in. It cannot kill, and the measured
  verdict would be meaningless (outcome **[not measured]**).
- **The golden test can live in `tests/v23/`.** It is not a kill file.
- **The lifecycle test cannot, as a kill file, without an amendment.** Two options:
  - **(P-b)** The frozen location `tests/v2/test_v23_story_lifecycle.py` (§4.4, §8, DAG §4). Under frozen R6 it
    re-opens every I6-passing target. With today's recorder status, E5 re-opens those anyway (R1/R2S), so the added
    cost is 0 in this run. After that the file is part of the v2.3 basis.
  - **(P-d)** Add exactly that file (and the empty `tests/v23/__init__.py`) to COPY. This is an L1-F5 edit, and it
    weakens A2's measured "outside every COPY root" premise for that file.
- Both are design decisions (`docs/v2.3/amendments/<ID>.md`).

**Related, owned by L1-F5 but blocking E5's records.** The frozen design writes `V23_REL`, the v2.3 audits and the
round chains to `closure-evidence/v2/v2.3/` (§2.5, §2.6, §8). The corrected placement forbids that location
(COPY root: R2S) and `closure-evidence/v2.3/` (V1 guard). The record location therefore needs its own amendment before
any E5 measurement is committed. R3's SCOPE is placement-neutral ("append-only as new files").

---

## 4. What may proceed now without crossing the Q0-1 boundary, and what must wait

**Safe now (lands nothing in `aisef2/`, touches no record, moves no Q0 byte):**
1. **Amendment drafts** as new files under `docs/v2.3/amendments/`:
   - the lifecycle kill-file placement (P-b / P-d);
   - the record location under the corrected placement (jointly with L1-F5);
   - the §2.5 / §4.4 kill-set wording;
   - an owner brief for the run.py:693 Q0-1 question (Q-a / Q-b / Q-c, with costs);
   - the charter erratum "deterministic closure" (owner text only).
2. **`tests/v23/test_v23_story_golden.py`**.
   - Reference: the `git show da3ea33f:…story_runner.py` blob, loaded into `sys.modules` first. It FAILs if the blob is
     missing and never skips.
   - At HEAD it is green by construction (blob == HEAD). Committing it costs 0 F5 targets (A2: 0/262 S(F) hold
     `tests/v23/**`). The integrator decides when it lands.
3. **The fault-matrix test (F1–F25, G1–G2, R1) written against the §4.5 interface** in an E5 lane worktree.
   - Its red-before run against HEAD is kept in scratch (expected: C rows red, P rows green **[not measured]**).
   - Do not commit a red test to the release branch. Its final directory waits for the placement amendment.
4. **A scratch prototype** of the §4.3 handler: an APFS clone (`cp -cR`, `.git` removed), mutation-worker env guard,
   `df` ≥ 20 GiB. It measures:
   - (a) the fault matrix, the golden test, K-NOWORK case E, test_b1gap5 and the p6 tests;
   - (b) H9 (old_path_audit R6/R3, release_inventory) with no checker edit;
   - (c) Q0 (≈ 263–279 s [doc]) for story_runner-only and for story_runner + run.py. This confirms §3.2 and gives the
     exact moved-entry list that G-4 requires;
   - (d) the enum-swap mutant count, from the generator only, with nothing executed.

   Evidence stays in scratch, referenced by sha256. F5 classification of a prototype needs git history, so it belongs
   in a lane worktree commit, not in a `.git`-less clone.
5. **The mutation.py append-only hunk drafted as a patch file** for L1-F5 (not applied).
6. **Static preparation for G-7.** Enumerate the run.py binders (§4.7(c)) and draft the W1-report section for the E5
   tier-R scope and its price. The final numbers need the recorder's observations.

**Must wait:**
- Any `aisef2/` commit (story_runner.py, run.py). Gate: W1a F5 gates pass (§11 gate 1 negatives; `--states/--affected/
  --run-affected`; F5-ROUND; the recorder merged with Linux `os_trace`). Hard edges `DEPENDENCY-DAG.md:167-168`.
- The run.py:693 hunk: an owner Q0-1 ruling (or Q-c by amendment + owner, since it changes a W1 exit gate).
- The `mutation.py` hunk: L1-F5 and the placement amendment.
- The single targeted run (W1a ∪ W1b): SCALE-1, the recorder merged, Linux workers (SRV-1 notice or GitHub runners),
  and W1b landed.
- Round-v2.3 re-derivations (K-NOWORK, Q5, CONFORMANCE-RULING, ORCH, P5-FALS), the R3 wiring patch and Q0 gate 3: the
  owner commits seq 13 (R3 is on CONDITIONAL HOLD; R2 must never be applied).
- C1, C5/G9, G6, and E6/E7/E1/E2/E4: E5's mandatory gates first (`DEPENDENCY-DAG.md:169,180-181,211,215-217`).

---

## 5. Ordered next execution steps

| Step | Action | Gate to pass before the next step |
|---|---|---|
| 0 | Integrator: `git mv` the lane evidence out of `closure-evidence/v2.3/` into `docs/v2.3/evidence/<topic>/` on `v23/lanes` and `worktree-wf_3f073485-4b3-1`, fixing references; then merge the L1 lanes. | `test_v1_evidence_guard` + Q0 unchanged |
| 1 | E5 prep: amendment drafts (§4 item 1) and the owner brief for run.py:693 / Q0-1. | integrator review; owner choice on Q-a/b/c |
| 2 | E5 prep: the golden test in `tests/v23` plus the lifecycle-matrix draft with its red-before evidence (scratch). | ruff; golden green at HEAD |
| 3 | E5 prep: scratch prototype (§4 item 4). Confirm H9, the fault matrix, and the exact Q0 moved-entry list for both edit sets. | 0 unexpected Q0 entries for story_runner-only; the b1 clean result recorded for run.py |
| 4 | L1-F5 completes W1a: F5 source rule and the CLI in `mutation.py`, F5-ROUND, b1 `kernel=`, execution_order `at=`, the p5_falsifiability guard, the record location, the recorder plus `os_trace`; N1–N34 and NA1–NA9. | §11 gate 1; base `--check --states` table per gate 2 (A1.2 figures) |
| 5 | Owner: seq 13 (R3 or a successor), SCALE-1, Q0-1 for run.py:693, the charter erratum. | committed ledger entry; written rulings |
| 6 | W1b lands (L1-LIFECYCLE): story_runner.py (imports only added); the run.py hunk only as Q0-1 rules; tests per the placement amendment; mutation.py hunk via L1-F5. | G-1…G-9 locally; `test_v23_q0_byte_identity` (ii) on the real commit; ruff; no new VOCABULARIES member or event type |
| 7 | The W1 report states the E5 tier-R scope and its serial-hour price. | G-7, written before the run |
| 8 | One targeted run over W1a ∪ W1b on Linux (env guard, no paid calls), at the SCALE-1 scope. Survivors are audited append-only; then the staged cut-over. | G-10: every changed target MEASURED, 0 UNRESOLVED accepted, known-bad still FAIL |
| 9 | Round-v2.3 re-derivations under the committed seq 13 and the R3 wiring; Q0 byte-identity. | §11 gate 3 |
| 10 | W1 exit: the integrator's full suite on the main tree, CI 6 legs + sealing + lint + wheel, the cold-vs-incremental table (gate 8, the E5 class reported "not met" if below 50 %), and the E5 checklist row DONE with SHA + tests. | §11 gates 1–9 |
| 11 | Only then: W2 (E6/E7/E1/E2/E4), later C5/G6/C1. | G-12 carried |

## 6. Not done here

- No test, Q0, mutation run or F5 classify was executed. The only computation was the in-memory B1 probe of §3.2.
- The figures marked [doc] were not re-measured.
- The fault-matrix red-before result, the H9 verdict on a real E5 shape, and the run.py binders of §4.7(c) remain
  **[not measured]**.
