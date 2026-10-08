# T0 baseline reuse: a proposal for the next round

**Status:** proposal only. **Not used in campaign 2.** Campaign 2 (snapshot `5719f1f`, started 2026-10-08T03:49:41Z,
i.e. 10:49 +07, and still running when this was written) measures every target with its own T0, exactly as the runner
at the snapshot does (`docs/v2.1/MUTATION-RUNNER-V2.md` §5). Adopting reuse needs **the owner's approval and a runner
change with its own tests** (§7), then the confirmation of §8. This document changes no runner code, kill set, queue,
execution-order table or record.

**Owner (2026-10-08), verbatim:** "Chưa dùng chung T0 trong chiến dịch này. Ghi thành đề xuất tối ưu cho vòng sau, kèm
điều kiện tái sử dụng baseline và phép đo xác nhận."

**Written:** branch `v21f/t0prop`, base `3e6ebf1`; revision 2 answers the round-1 review (§11). **Inputs:**
`closure-evidence/v2/v2.1/T0-SWEEP-2.json` (the sweep), `closure-evidence/v2/v2.1/campaign-2/tools/queue.tsv` and
`queue-all.tsv` (the queue, 457 and 466 targets), `closure-evidence/v2/v2.1/pilot/attempt-2/` (`forecast.json` and the
lane records). **Numbers:** `t0_reuse_estimate.py` beside this file, read-only:

```
python3 -B docs/v2.1/proposals/t0_reuse_estimate.py closure-evidence/v2/v2.1/T0-SWEEP-2.json \
  closure-evidence/v2/v2.1/campaign-2/tools/queue.tsv closure-evidence/v2/v2.1/campaign-2/tools/queue-all.tsv \
  closure-evidence/v2/v2.1/pilot/attempt-2/forecast.json closure-evidence/v2/v2.1/pilot/attempt-2
```

"runner §n" is a section of `docs/v2.1/MUTATION-RUNNER-V2.md`; a bare §n is a section of this document. Code lines
are `validation/v2/mutation.py` at `c6df6bd`, identical to `3e6ebf1` and `5719f1f` in the runner functions.

## 1. What T0 establishes, and why it runs per target

Before a target's first mutant, `run_target` writes the target's null mutant (`null_mutant`: `ast.unparse` of the
module, and for a `SCRIPT/fn` target the child script re-unparsed inside its constant first) and runs every kill file
once on it, the whole file, no failfast, each run in a clean environment (`_baseline`). One T0 row per kill file gives:

1. **The file passes the bytes every mutant's rewrite produces** (ORD-1). A file that fails the null fails every
   mutant whatever it does, so it is refused for the target: `kill tests fail on the unmutated tree (T0 null mutant)`,
   every mutant NOT_RUN, and the refused file runs once more on the original bytes (`original` rows: a broken snapshot
   or a rewrite-sensitive file). The cost of a refusal is one T0 run and one `original` run (lines 1542–1547).
2. **A clean run:** no residue in the target's tree and nothing left running (runner §2.3, §2.4). A file that leaves
   either at T0 is refused, so a "residue on every run" storm cannot start.
3. **The reference** (VS-6, lead decision Q3): the counts (ran, skipped, expected failures, unexpected successes) and
   the skipped-test ids. Every later whole-file PASS of that file must match them exactly, or the row is INFRA, so a
   mutant that skips one more test, or `os._exit(0)`s before the summary, is never a PASS.
4. **`first_test`:** the selector the bracket uses for a module-level failure (an import, `setUpModule`, runner §4.1).
5. **The blame boundary** (PL-4): a process the baseline leaves stops the target as `... before mutant 1 (T0 <file>)`,
   not as mutant 1's fault.

Why per target today: the null depends on the target (a `SCRIPT/fn` null is not the module's null: ORD-1 verifier (b),
runner §5); T0 runs in the target's own fresh tree, under the target's own ownership boundary, right before its
mutants; and a result is self-contained — one result's own rows say what its baseline was, with no reference to
another result. Reuse gives part of that last property up; R10 says which part and §7 what is kept.

The null is the same for every target of one module outside a child script, and for every target inside the same
child script, which is why reuse is possible at all: the 466 targets of manifest revision 2 have **29 distinct nulls,
41 kill files and 139 distinct (null, kill file) pairs** (the sweep).

## 2. What T0 costs (measured)

- **The sweep** (`preflight-3/README.md`): every one of the 139 pairs through the runner's own T0, alone under the heavy
  lock, at `70423f9`: 139 of 139 PASS, no residue, no leak; 9 rows with skipped tests; 5,094 s of T0 runs (plus 40 s of
  `overhead_s`), 5,290 s wall.
- **Under campaign load** (pilot attempt 2, `forecast.json`, `ord`): a target's T0 costs `L` = **1.154** × its chain.
  `L` is the median over the 9 pilot targets of (its T0 rows' `seconds` + `overhead_s`) / chain, and the chain is the
  sum of its kill files' sweep T0 `seconds`, so `L` already holds the overhead (forecast.py). Every figure below uses
  that one basis: a T0 run of pair p costs `L × sec_p`, with `sec_p` the sweep's `seconds` alone.
- **Campaign 2:** the 457 queued targets hold **1,525 (target, kill file) T0 runs** over the 139 pairs:
  `L × Σ_p n_p × sec_p` = **17.20 worker-hours**, of a model total of **156.5 worker-hours** for those 457 targets
  (forecast.py's cost per target, §3): **11.0 %**. Over all 466 targets (the 9 pilot targets included,
  `queue-all.tsv`) the same terms are 17.96 of **161.8 worker-hours** (forecast.json's figure), **11.1 %**.

## 3. What reuse would save (estimate, netted)

Notation: `sec_p` = pair p's sweep T0 seconds; `n_p` = the queued targets holding p; `L` = 1.154. The pairs are
unevenly shared: 19 pairs are held by one target (nothing to save), the largest by 58; the five largest savings are
`test_v21_continue_integrity.py` (216–218 s in the sweep) on the nulls of `bundle_cli.py` (23 targets), `lineage.py` and
`run.py` (19 each), and `test_v21_review_chain.py` (148 s) on `run.py` (19) and `review_ocr.py` (16).

**Gross:** the T0 seconds a rule would not run.

| Rule | Formula | T0 worker-h | Saved worker-h (gross) |
|---|---|---|---|
| today (per target) | `L × Σ_p n_p sec_p` | 17.20 | — |
| one row per pair, campaign-wide | `L × Σ_p sec_p` | 1.63 | 15.57 — **excluded** by §4 (same worker) |
| one row per pair per worker, no window | `≤ L × Σ_p min(n_p, 4) sec_p` | ≤ 5.73 | ≥ 11.47 |
| same worker, window `h` (model) | `saved(h) = L × Σ_{(t, f) reused} sec_p` | | 1 h: 2.04 · 2 h: 4.34 · **6 h: 8.01** · 12 h: 9.72 · 24 h: 11.04 · none: 12.09 |

**The queue model** (not a measurement): four workers take targets in queue order (longest expected first), each the
next one when it is free, as `qworker.sh` does; a target t costs forecast.py's
`cost(t) = chain × L + n × (s × S + (1 − s) × K) × chain` (pilot survivor rate `s` = 0.133, `K` = 0.132, `S` = 1.134,
unrounded as forecast.py derives them); a (target, file) T0 is saved when the same worker ran an own T0 of the same
pair that started at most `h` hours earlier (a reused row is never a source). The schedule is the no-reuse one; its
makespan is 39.1 h, against the forecast's ≈ 40 h of wall time.

**Net:** what §4–§7 give back, per term.

```
net(h) ≈ saved(h) × (1 − f) × φ − Σ_{invalid source rows} cascade(row) − trips(h) − compile moved
```

- **Sentinels** `(1 − f)`, `f` = 0.1: a sentinel runs its own T0 anyway (§8 step 2).
- **Close-out** `φ`: a reused file whose result holds no whole-file PASS of its own runs its own T0 after the last
  mutant (§7, R10). That costs what the reuse saved, so only reuses of files that a mutant's whole-file run PASSes keep
  their saving. Measured on the pilot's table-order lanes (the campaign's order), by sweep seconds over the 44
  (target, file) pairs: no run at all 12 (685 s, 28.9 %), no whole-file PASS 17 (925 s, 39.1 %, the 12 included),
  PASS only 13 (973 s, 41.1 %), PASS and FAIL 14 (471 s, 19.9 %): **φ = 0.609**. All 17 lie in the 5 pilot targets
  with no survivor (17 of their 25 files); a target with a survivor PASSes every file (SURVIVED needs one PASS per
  kill file). The declared-order lanes give 0.688. The stricter trip of §7 (also at a reused file's first FAIL)
  keeps only the PASS-only files: **φ = 0.411**.
- **Trips** (§7): one own T0 per tripped file. **0** trip events in the pilot's 88 (target, file, lane) measurements
  (both orders), so 0 here; under drift they replace the storm of §6 R1, they do not add to it.
- **Cascade** (§6 R8): re-measuring the reusers of an invalid source row; not netted because no rate is measured
  (0 mismatches so far, §8); sized below.
- **Compile moved:** `_env` does not set `PYTHONDONTWRITEBYTECODE`, so today T0 fills the tree's `__pycache__`; under
  reuse a mutant's first run of each file compiles instead. Moved, not saved; **not measured**.

| Window | gross `saved(h)` | × 0.9 (sentinels) | net, close-out (φ 0.609) | net, strict trip (φ 0.411) |
|---|---|---|---|---|
| 1 h | 2.04 | 1.84 | 1.12 | 0.76 |
| 2 h | 4.34 | 3.91 | 2.38 | 1.61 |
| **6 h** | 8.01 | 7.21 | **4.39** | 2.96 |
| 12 h | 9.72 | 8.75 | 5.33 | 3.59 |
| 24 h | 11.04 | 9.93 | 6.05 | 4.08 |
| no window | 12.09 | 10.88 | 6.63 | 4.47 |

**The cascade, sized** (6 h model): 342 source rows feed 874 reuses (reusers per source row: median 2, max 13).
Re-measuring the reusers of one source row costs median 0.27, mean 0.42, max 1.89 worker-h (one target: 0.34 h on
average); of every reuser of one pair on all workers median 0.71, max 6.57 h. About **10 invalid source rows** cancel
the 4.39 h. Under C7's first wording (the source must be the accepted result of its target), each re-measured source
target voided its reusers: 100 source targets, mean 0.31 h each, so about **14 routine re-measures** (the survivor
loop appended kill files to 4 of the 9 pilot targets, re-measured after campaign 2) would have cancelled it; C7 now
binds the row, not the result (§4).

**Reading:** at a 6 h window the net saving is about **4.4 worker-hours of 156.5 (≈ 2.8 %)**, 3.0 h (≈ 1.9 %) under
the strict trip, about 1 h of about 39 h of wall time, before any cascade, trip or moved compile. Not modelled: a
worker stop (exit 3 ends its session and every reuse on it, C6), and φ is from 9 targets — it falls as the survivor
loop leaves more targets without survivors. Grouping each pair's targets on one worker would move the gross towards
15.6 h, but gives up the longest-first balance (an idle tail); not modelled. Reuse is a small lever; the dear
end-to-end kill files are the large cost (`pilot/attempt-2/README.md`).

## 4. When one T0 row may stand for another target

All conditions, each recorded in the reusing result (§7) and checked by the record check, never only by the runner.
C1–C6 form the key; each value is taken at the source's T0 (and kept in its row's key) and again at the reusing
target's start, after `_settle` and before its first run, and the two must be equal.

| # | Condition | Why | Recorded / compared as |
|---|---|---|---|
| C1 | Same module source and the same null-mutant digest | the reference is a property of (null, file); a `SCRIPT/fn` null is not the module's | `source_sha256` of the module; sha256 of `null_mutant(src, func)` |
| C2 | Same kill-file bytes and closure | the file and everything it imports or reads | sha256 of the kill file; its closure inside the COPY tree is C3, outside it C5 |
| C3 | Same COPY tree digest | every file a kill test can read in the tree | `tree_sha256` (runner §2.1: mtime-free; one value across all 8 pilot lanes). Stricter than needed — the sweep at `70423f9` and the pilot at `5719f1f` differ in it and agree in every reference — and kept strict |
| C4 | Same harness and runner | the runner decides PASS (counts, skips, residue, settle) | sha256 of **every module the runner process loaded from the worker's root**, read by the runner from `sys.modules` after it has imported `_run_file`'s two lazy imports, so no hand list can miss one. Measured at `c6df6bd`: `validation/v2/mutation.py` and `cleanup_authority.py` at import, and 28 more from `aisef2` through `runtime/process_range.py` and `runtime/story_scope.py` (`Residual`), which pull in `arch/enums.py`, `errors.py`, `journal/{compat,event,format2}.py`, `control/{owner,routing}.py`, `plan/{drift,obligation,static_admission,story_admission}.py`, `probe/{calibration,protocol}.py`, `product/{approval,compiler,contract,outcome,spec}.py` and the package `__init__`s. Plus `owned_run.py` (the runner's parent), the worker script's sha256 and its `mutation.py run` argv without the target, the worker checkout's HEAD commit, and the record format (`runner`) |
| C5 | Same worker environment class | the host decides some skips, and it can change mid-campaign (the three files found in the host interpreter's site-packages during B-03, origin under separate investigation) | the interpreter (realpath, `sys.version`, `os.name`, `sys.platform`), the kill-test environment's kept values (`ENV_KEEP`), a digest of the listings of the `PATH` directories, a digest of the interpreter's site-packages (names, sizes, sha256), the OS release, whether a symlink can be made in the target's scratch. Host-dependent skips measured in the 41 kill files: `os.name`/`sys.platform` decorators in 16 files and two runtime `skipTest`s when no symlink can be made (`test_c2_file_artifact.py:593`, `test_release_s2_kernel.py:259`); none of them skipped in the sweep. The sweep's 9 skip-bearing rows do **not** depend on the host: 7 are `test_v21_review_chain.py`'s `RealBinary` (3 tests, `skipUnless(os.environ.get("AISEF_TEST_OCR_EXE"))`, a variable `ENV_KEEP` never passes, so they skip on every host), 2 are `test_c2_k_nowork_001.py` and `test_c2_orchestration_conformance.py` (4 tests each, `skipUnless` a `validation/qualification/*.py` that COPY leaves out: C3) |
| C6 | Same worker, same worker session, bounded age | drift grows with time; a stop or restart means the worker's state was unknown | `_worker(root)`; a session id new at every worker start, passed by the worker; source age ≤ `T_max` (proposed 6 h, the owner's to set from §8 step 0 on campaign 2's own rows — the pilot has no two T0 rows of one pair on one worker, so it says nothing about aging); never across a stop (exit 3) or a restart sweep |
| C7 | The source row is clean, and still valid | a row from a state the runner could not vouch for is no reference; a later re-measure of the source target does not change the row | the source is an own T0 row (never a reused one): PASS, no `residue`, `leaked`, `cleanup` or `stopped`; its result neither stopped nor refused a kill file (at T0, a trip or a close-out); the row is copied whole into the reusing result and is found, by `row_sha256`, in the campaign's committed evidence (the source worker's results as written, never rewritten by a later re-measure); no mismatch has invalidated it (C8). A superseded source result does **not** void its reusers |
| C8 | Skipped ids and counts identical | the reference is exactly what a PASS must match | every own T0 row of the pair on that worker (a later source, a sentinel, a trip, a close-out) has the source's counts, skipped ids and `first_test`; any difference invalidates the source row it should have matched and stops reuse of the pair on that worker for the session |

## 5. What is never shared

- **The per-target environment:** the scratch directory, the pristine copy (per `main()`), the tree and its base
  manifest, the ownership boundary (`ca.establish`), the run directories with their fresh HOME/XDG/TMPDIR, the run
  tokens.
- **The settle before the target** (`_settle`): it always runs.
- **The bracket's runs:** every FAIL is still confirmed by two control PASSes of the failing test on the null in the
  target's own tree, the re-run, and the fresh-tree re-measure (runner §4.1, §14 fixes 9 and 10). A KILLED mutant's
  verdict therefore rests on runs in its own tree. The one borrowed input it uses is the control's selector for a
  module-level failure (`_select` with the reference's `first_test`, line 1361); it is identical under C2 (the same
  file bytes), and a wrong one fails closed: a selector that selects nothing makes the control INFRA (no test ran:
  exit 5 with no summary, or "every test skipped"), the kill is not confirmed in place, and the file is re-measured
  whole on a fresh tree.
- **Refusal:** a non-PASS T0 row is never reused. A target is refused only by its own T0 runs — at its start for a
  file it does not reuse, at a trip, or at the close-out (§7) — never by another target's row, and the `original`
  diagnostic runs only for its own refused file.
- **Ownership and cleanup authority** (INV-MUTATION-AUTHORITY): nothing in a reused row is an input to a signal or a
  removal. The source's `leaked: []` says nothing about the reusing target's processes.
- **Across workers, sessions, snapshots or campaigns:** nothing. Mutant results are never shared; only the reference is.

## 6. Risks

- **R1 drift.** The reference ages. A host change (site-packages, `PATH`, disk — attempt 1's ENOSPC — or load near the
  900 s timeout) that changes what the null does shows up under reuse after the first mutant instead of before it.
  Without a trip it would be a storm: each mutant reaching a file the null now fails pays a FAIL, a selected control
  (FAIL), a fresh whole-file re-measure (FAIL) and a fresh whole-file control (FAIL), and ends INFRA — up to 3
  whole-file runs and 1 selected run per mutant against one T0 run today — while other files still give confirmed
  kills, and the target ends UNCLASSIFIED instead of refused. The trip of §7 removes that: the first such event runs
  the file's own T0 and refuses the target as today. Drift is also **not only a cost**: VS-6 judges a PASS against the
  borrowed reference (`_outcome`, `[_counts(s), skipped_tests] != ref`). If drift makes the reuser's own reference
  differ from the borrowed one, a mutant whose run reproduces the borrowed counts and skipped ids exactly is PASS under
  reuse where today it is INFRA: **INFRA can become SURVIVED**. It needs an exact match to the borrowed reference; any
  run of that file in the target that does not match is INFRA, which trips and refuses the target; it never produces
  KILLED (a kill needs the bracket's null controls in the target's own tree); and a SURVIVED is accepted only with an
  audit or after a new kill test. Bounded by C5, C6, the trip, the close-out and the sentinels; not excluded.
- **R2 state leakage between targets.** What outlives a target lives outside its scratch: host-level state (the
  interpreter's site-packages, absolute `/tmp` paths, launchd jobs, ports, a real home a test reaches without `HOME`).
  Today the target's own T0 is the first run that can fail on such a leak, before any mutant (fail-closed refusal).
  Under reuse the first run of a reused file in the target is a mutant's run or, for a file no mutant's whole-file run
  PASSed, the close-out after the last mutant (§7). A leak that fails the null then trips or fails the close-out, and
  the target is refused as today; until then mutants have been measured, and the bracket's controls on the target's
  own tree keep any leak that fails the null from making a kill.
- **R3 order effects.** (a) FS-2: today every mutant runs after T0 has run each kill file once in the tree, so the
  unchanged modules' `__pycache__` exists. Under reuse, mutant 1 (and each mutant up to the first run of each file)
  runs in a tree no kill file has run in, a state no campaign-2 mutant was measured in. The caches are of unchanged
  sources (runner §14 fix 1), so imports are the same; the exposure is a kill test that observes caches in the tree
  (runner §14 FS-2: 12 test files under tests/v2 read or set bytecode state, none known to depend on the tree's caches;
  not re-checked here). §8 step 1 compares every mutant's class for this reason. (b) The source ran the file after its
  own kill set's earlier files; the reuser's kill set differs. The clean-run argument (runner §7.1) makes that
  irrelevant except through (a). (c) How much is reused depends on the queue order and on which worker takes which
  target (§3).
- **R4 ownership and blame.** A null run that would leave a process now first runs as a mutant's run or as the
  close-out, so the stop names `at mutant <m> (<file>)` or `after the last mutant (T0 close-out <file>)` instead of
  `before mutant 1 (T0 <file>)` (PL-4). The classes are unaffected (that mutant INFRA, the rest NOT_RUN, the target
  errored); the diagnosis is worse. Reuse must never move authority (§5).
- **R5 correlated nondeterminism.** Per-target T0 gives each target its own draw of a flaky file's skips. Reuse gives
  every reuser the source's draw, so a source taken in a rare state turns into INFRA rows on its reusers — each the
  first one trips (§7) — and a re-measure.
- **R6 the record check has a gap reuse would open.** Read in the code at `3e6ebf1` (`_problems_v2`, lines
  1646–1647): the check refuses a T0 row that did not pass, but does not require one T0 row per kill file, and it never
  compares a PASS row with its file's reference (for SURVIVED it only asks for one PASS per kill file). Neither is a
  defect for today's runner, which writes one T0 row per file whenever it runs mutants and judges every whole-file run
  against it. On the runner side, `_outcome` with no reference (`tg.ref.get(rel, {}).get("ref")`, line 1280) silently
  drops VS-6: a missing reference turns into a PASS that needs only `ran > skipped`. Reuse creates a new path to a
  missing or misapplied reference, so the change marks the format so today's check refuses it, and adds both checks
  and a runner assertion (§7).
- **R7 a new trust input.** Each target is its own `mutation.py run` process (`qworker.sh`), so reuse needs a store
  between invocations. The record check must never trust that store. Every reused reference is copied whole into the
  reusing result and verified against the source row in committed evidence. A missing, stale or edited store can then
  cost a T0, but never change a reference.
- **R8 cascade.** A reuser rests on its source row. With C7 as revised, a re-measure of the source target for another
  reason (routine: a kill file appended by the survivor loop) does not void its reusers, since the row is bound by
  sha256 to committed evidence and the row itself does not change. A reuser is refused when its source row is invalid
  (tampered, missing from committed evidence, failing C7) or a mismatch (C8, a trip, a close-out, a sentinel)
  invalidated it. Cost per invalid source row, in the 6 h model: median 0.27, mean 0.42, max 1.89 worker-h; about 10
  cancel the net saving (§3). Refusing every reuser of a pair on all workers instead would cost median 0.71, max 6.57 h
  per pair; §8 leaves that to the owner per finding.
- **R9 a small gain for a new path in an authority-sensitive runner** (§3: about 2.8 % net at a 6 h window).
- **R10 self-containment.** Under reuse some kill files may never run in the reusing target's result. In the pilot's
  table-order lanes, **12 of the 44 (target, file) pairs have no run besides T0**: `run.py::admit` × 6 files
  (`test_v21_verify.py`, `test_v21_continue_usage.py`, `test_v21_review_chain.py` (148 s), `test_v21_continue_integrity.py`
  (216 s), `test_app_run.py`, `test_s2_kills.py`), `story_runner.py::_fail` × 5 (`test_v21_orchestration.py`,
  `test_release_s2_kernel.py`, `test_c2_k_nowork_001.py`, `test_c2_k_presat_001.py`,
  `test_c2_orchestration_conformance.py` — two of them the skip-bearing pairs), and `cli_invocation.py::AGENT/guarded`
  × `test_c2_cli_invocation.py`; 17 have no whole-file PASS. Reused, such a file's ORD-1 pass, clean run and skip
  reference would rest wholly on another target, and a leak or a state fault in it would never be observed in this
  target — and this is exactly where the gross saving comes from. **Mitigation** (§7, the close-out): every reused
  file with no whole-file PASS in the result runs its own T0 after the last mutant, so every kill file has at least one
  whole-file run in the target's own tree judged against its reference and checked for residue and leftovers (its own
  T0, a mutant's PASS, or the close-out). It costs the saving on those files (φ, §3). **What still rests on the
  source:** for a file whose only own whole-file runs are mutants' PASSes, the null's own PASS in this tree is not
  observed; ORD-1's rewrite part holds by C1–C3 (the same null bytes, file and tree), and the environment part is
  observed only through those mutants' PASSes, which match the reference exactly. A mutant can in principle pass a
  file whose null would fail in this tree; then that mutant is SURVIVED (needs an audit or a kill), never KILLED. The
  strict trip of §7 removes that case for files that also FAIL somewhere, at φ 0.411.

## 7. The runner change it needs (not built)

- **Runner:** per (target, kill file), when a source satisfying C1–C8 exists in the worker session's store and the
  sentinel draw (§8) is negative, no T0 run at the start: `tg.ref[file]` is taken from the source row and the result
  records the reuse; otherwise an own T0 run, as today. The files that are not reused still run in declared order, and
  `_settle` before the target is unchanged. Before mutant 1 the runner asserts that `tg.ref` holds every kill file,
  and stops the target (`RUNNER_EXCEPTION`) if not, so `_outcome`'s no-reference path is reached only by a T0 run and
  by a selected run. The store is append-only, lives in a directory the worker names outside every tree and scratch,
  and the runner never removes it, so no destructive site is added.
- **Trip** (keeps the fail-closed refusal): for a reused file, on the first of — a whole-file run of it (a mutant's
  row, a fresh re-measure, a fresh control) whose outcome is neither PASS nor FAIL (INFRA, including "counts or skipped
  tests differ from T0's", or TIMEOUT); a null control on it, selected or fresh, that does not PASS; a run of it that
  leaves residue or a leftover — the runner runs that file's own T0 at once (the null in the tree, the whole file, no
  failfast, `role: t0`, `tripped_at` the mutant), then writes the mutant back and:
  - not PASS, residue or a leftover: the target is **refused as today** (`error` = `kill tests fail on the unmutated
    tree (T0 null mutant, tripped at mutant <m>)`), the file runs once on the original bytes (`original`), the current
    and the remaining mutants are NOT_RUN; the finished ones keep their rows, and the check refuses the result for its
    `error`, as today. Cost: the runs up to the event, one T0 and one `original` run, not the storm of R1;
  - PASS with a reference other than the borrowed one: the target is refused (`error` = the two references), and the
    source row is invalidated (C8, R8);
  - PASS with the borrowed reference: the own row becomes the file's reference and the chain goes on.
  A FAIL by itself is not a trip: its bracket's two null controls are the check on the null, and a control that does
  not pass trips. **Stricter alternative** for the owner: trip also at a reused file's first FAIL; it closes R10's
  last case for files that FAIL somewhere and leaves φ at 0.411 instead of 0.609 (§3).
- **Close-out:** after the last mutant, every reused file with no whole-file PASS in the result (no mutant row, fresh
  re-measure or fresh control of it that PASSed against its reference) runs its own T0 (`role: t0`,
  `close_out: true`), with the trip's three outcomes; a stop there names `after the last mutant (T0 close-out
  <file>)`. A refused close-out refuses the target with its mutants measured: the same verdict as today's refusal, at
  the cost of the whole target.
- **Record:** the format marker is the runner version, **`"runner": 3`**. A key such as `"t0_mode"` would not do:
  `_problems_v2` ignores unknown keys, and the only refusal of a runner version in today's check is `problems_of`'s
  for V2.1 (lines 1688–1690: `runner != 2` → "measured by a runner that does not classify — re-measure"), the record
  every V2.1 target is written into. `target_problems` (line 1655) reads any `runner != 2` result by the legacy rules,
  so the changed check routes runner 3 to its own rules. `t0` holds the own rows, as today (start, trip, close-out,
  sentinel); `t0_reused` holds `[{file, key: {C1–C6 values}, source: {target, worker, session, started, row (whole),
  row_sha256}, age_s, tripped, closed_out}]`; `t0_sentinel` holds `[{file, seed, source row_sha256, match}]`; plus the
  counts `t0_own`, `t0_reused`, `t0_sentinel`, `t0_tripped`, `t0_close_out`. The account summary prints them per
  target, and the campaign report states how many baselines were reused, tripped and closed out.
- **Check:** every kill file has exactly one reference: one own PASS T0 row at the start or one `t0_reused` entry,
  plus any trip, close-out or sentinel row, each PASS with the same reference. A reused entry's key must equal the
  result's own values; its source row must satisfy C7 and be found by `row_sha256` in the committed evidence; the age
  must be ≤ `T_max`, and a reused row is never a source. **Every whole-file PASS row** (no `select`) of every mutant has
  the counts and skipped tests of its file's reference (own or reused). **Every reused file** has at least one
  whole-file PASS row in the result (a mutant's, or the close-out). A source row invalidated by a mismatch refuses
  every result that reused it until each is re-measured. Campaign-2 results keep today's verdicts (the PASS-row check
  holds for them by construction: the runner judged each such row against its own T0).
- **Tests** (toy targets, like `::T0`): one per key component (changed → an own T0 runs); a source with residue, a
  leak, a stop or an error → no reuse; an age above `T_max` → no reuse; across a session → no reuse; a superseded
  source result → its reusers still accepted, a tampered or missing source row → refused; the trip — a reused file the
  null fails in the reuser's tree → exactly one own T0 run, then refused as today (with its `original` row), a reused
  file that leaves residue → the same, an own T0 equal to the borrowed reference → the chain goes on, a different one
  → refused and the source invalidated; the close-out — a reused file no mutant reaches, and one only FAILed → a
  close-out row, a reused file a mutant PASSes → none; a PASS row whose counts differ from its reference → refused by
  the check; `tg.ref` missing a kill file → the target stops before mutant 1; a runner-3 result → refused by today's
  check in V2.1; a reused row never reaches `ca.signal_owned` or a removal (like `::Proc`); the `::Order` matrix with
  reuse on → the same classes in every order; every campaign-2 result → the same verdict under the changed check;
  `mutation.py --check` → unchanged for historical phases. Not checked here: whether `proof()` and `S2.account` read a
  result that carries the new keys unchanged.

## 8. Confirmation before adoption

The required fields are the reference (outcome, the four counts, the skipped ids) and `first_test`. `tail_sha256` is
recorded and compared, but not required: it is not stable for PASS rows (below). With 0 mismatches in `n`
**independent** comparisons, the 95 % upper bound on the mismatch rate is about `3/n` (rule of three). Comparisons are
not independent when they share a source row (its reusers share its draw) or a worker (its host): `n` counts distinct
source rows, and the bound is also given per worker, where it is wider.

**Step 0 — retrospective, free, after campaign 2.** Campaign 2's results will carry up to 1,525 own T0 rows for the
139 pairs, over 4 workers and about 40 h. For each pair, compare every own row's required fields with every other's,
by same or different worker and by age. These same-worker pairs at every age are the data `T_max` is to be set from;
adoption requires the rows identical within every (pair, worker, `T_max`). Already measured on pilot attempt 2
(`t0_reuse_estimate.py`): 44 (target, file) pairs, each with 3 own T0 rows — the sweep's at `70423f9` (alone,
2026-10-07 21:38–23:07Z) and the `decl` and `ord` lanes' at `5719f1f` (four lanes at a time, 23:15–03:48Z), each lane
in its own worktree. That is 9 distinct workers and 2 snapshots, and no two rows of one pair on one worker. Required
fields identical in **44 of 44** (95 % bound about 3/44 ≈ 6.8 %, across workers); `tail_sha256` identical in 43 of 44
(`story_runner.py::_fail` × `test_p6_stages.py`: three different tails, all PASS with the same reference). It measures
identity **across** workers and snapshots, not aging on one worker, so it does not support `T_max`. It cannot see R3
(a), because every campaign-2 mutant ran after its own T0.

**Step 1 — paired experiment, with the changed runner, before adoption.** Choose the targets before measuring
anything: at least 8 pairs, each with at least 3 targets (the source and reusers at short and near-`T_max` ages),
including the dearest end-to-end pairs, at least 2 pairs with skipped tests, at least 2 `SCRIPT/fn` nulls and some
module-level ones, at least 2 targets with no survivor (where close-outs happen), preferring targets with few mutants.
Measure each target in two arms, at one snapshot, in one worker environment class: A with a per-target T0 (today), B
with reuse on. Alternate which arm runs first between pairs, as the pilot did. Acceptance requires all four:

1. every reused reference in B equals the reuser's own T0 reference in A, on every required field;
2. every mutant's class is the same in A and B (keyed by generator position);
3. B has no INFRA row, TIMEOUT, stop, residue, leak or trip that A lacks;
4. B's records pass the changed check, and A's records pass it as they pass today's.

Also recorded: differences in `killed_by` and `tail_sha256`, B's trips and close-outs, the T0 seconds saved net of
them, the wall time per target. Any failure of 1–4: not adopted, and the finding goes to the owner.

**Step 2 — sentinels, in the campaign that adopts it.** A fraction `f` (proposed 0.1) of the reuse opportunities is
drawn as `sha256(seed ‖ target ‖ file) < f × 2^256`, with the seed written in the campaign's start record. The draw is
therefore fixed before any run, reproducible by the check, and not chosen after seeing anything. A sentinel runs the
target's own T0 and uses it, so that target is measured exactly as today, and compares it with the reference it would
have reused. **What it covers:** in the 6 h model a source row has a median of 2 reusers, so a median source row gets
no sentinel with probability 0.9² = 0.81; about 73 of the 342 source rows get one. The sentinel is not the only check:
with §7, every reused reference is compared in the reuser's own tree at least once — each mutant's whole-file PASS of
the file is judged against it (a mismatch is INFRA and trips), and a file with no such PASS runs the close-out. What
only a trip, a close-out or a sentinel sees is the null's own run, and `first_test`. On a mismatch, reuse of that pair
stops on that worker at once, every result that reused that source row is refused until re-measured with its own T0,
and the mismatch is listed in the campaign report; whether every other reuser of the pair, on any worker, is
re-measured too (R8: median 0.71 h, max 6.57 h a pair) is the owner's call per finding. The report gives the
sentinels run and matched, by age and by worker, with the rule-of-three bound over distinct source rows.

## 9. Reconciliation with the campaign snapshot `5719f1f`

| File (this commit) | Targets | Tests / harness | Evidence to re-measure |
|---|---|---|---|
| `docs/v2.1/proposals/T0-BASELINE-REUSE.md` (revised) | none: not a target module, not a kill file | no test reads it. It lies inside COPY (`docs/v2.1`), so a run at a commit that holds it has a `tree_sha256` different from `5719f1f`'s | none for campaign 2: its workers run detached worktrees at `5719f1f`, which do not hold it |
| `docs/v2.1/proposals/t0_reuse_estimate.py` (revised: one cost basis, queue-all, the pilot coverage, the net and the cascade) | none | a read-only script, run by no test or harness; inside COPY like the document | none |

No runner file, kill file, module under `aisef2/`, queue, execution-order table or record is changed.

## 10. Not done, not verified

- No runner code, no test of reuse, no paired experiment, no sentinel; the trip and the close-out are designs.
- The window rows of §3 are a model (forecast costs on the no-reuse schedule), not a measurement; φ is measured on 9
  pilot targets and applied to the campaign as a factor; the trip count is 0 in the pilot, not under drift.
- Not measured: the bytecode compile that reuse moves from T0 to a mutant's first run; the cost of worker stops.
- `T_max` = 6 h and `f` = 0.1 are proposals, not values derived from data; step 0 on campaign 2's rows is where
  `T_max` is to come from.
- Not checked: whether `proof()` and `S2.account` accept a result that carries the new keys; campaign 2's live T0
  rows (its workers' directories were not read); the "12 test files read or set bytecode state" of runner §14.

## 11. Review resolutions (round 1, 2026-10-08)

| # | Severity | Point | Resolution |
|---|---|---|---|
| 1 | major | reuse removed the fail-closed refusal; a storm of up to 3 whole-file + 1 selected runs per mutant | §7 trip: the first INFRA/TIMEOUT, failed null control, residue or leftover on a reused file runs its own T0 and refuses the target as today; §6 R1; strict variant offered |
| 2 | major | some kill files never run in the reusing result (12 of 44 pairs, pilot `ord`) | §6 R10 with the pilot's list; §7 close-out restores one whole-file run per kill file in the target's own tree; what still rests on the source stated; R2/R4 corrected |
| 3 | major | saving not netted; C7 made the cascade large | §3 net formula with φ 0.609 / 0.411, sentinels, trips, compile moved; cascade sized (≈ 10 invalid rows, ≈ 14 voided sources under the old C7); C7 binds the row by sha256 to committed evidence, supersession no longer voids |
| 4 | minor | R1 "a cost, not a false class" too strong | R1: INFRA → SURVIVED possible, needs an exact match, never KILLED |
| 5 | minor | `t0_mode` would not be refused | §7 Record: `"runner": 3`, with the lines that refuse it and the legacy routing |
| 6 | minor | the check never verifies how a reference was used; `_outcome` with no reference drops VS-6; §5's KILLED sentence absolute | §7 Check: every whole-file PASS equals its reference, every reused file has one; runner asserts `tg.ref` before mutant 1; §5 qualified (the borrowed selector fails closed) |
| 7 | minor | overhead counted twice; 457 and 466 on different bases | one basis (`L × sec`): 17.20 of 156.5 h (457), 17.96 of 161.8 h (466); every row recomputed; compile move named, not measured |
| 8 | minor | C5's example wrong; capture time unstated | C5: the measured host-dependent skips (16 files' platform decorators, 2 symlink `skipTest`s), the 9 sweep rows explained (7 `RealBinary`, 2 COPY), values taken at the source's T0 and each reuser's start |
| 9 | minor | C4's module list by hand, incomplete | C4: every module loaded from the worker's root, read from `sys.modules`; measured list of 30 at `c6df6bd` |
| 10 | minor | statistics weaker than the text | §8: independence unit = source row, per-worker bounds, P(no sentinel) 0.81, ≈ 73 of 342 rows sentineled, step 0's 44/44 is cross-worker only; C6 no longer cites the pilot for `T_max` |
