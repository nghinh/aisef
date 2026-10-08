# T0 baseline reuse: a proposal for the next round

**Status:** proposal only. **Not used in campaign 2.** Campaign 2 (snapshot `5719f1f`, started 2026-10-08T03:49:41Z,
i.e. 10:49 +07, and still running when this was written) measures every target with its own T0, exactly as the runner
at the snapshot does (`docs/v2.1/MUTATION-RUNNER-V2.md` §5). Adopting reuse needs **the owner's approval and a runner
change with its own tests** (§7), then the confirmation of §8. This document changes no runner code, kill set, queue,
execution-order table or record.

**Owner (2026-10-08), verbatim:** "Chưa dùng chung T0 trong chiến dịch này. Ghi thành đề xuất tối ưu cho vòng sau, kèm
điều kiện tái sử dụng baseline và phép đo xác nhận."

**Written:** branch `v21f/t0prop`, base `3e6ebf1`. **Inputs:** `closure-evidence/v2/v2.1/T0-SWEEP-2.json` (the sweep),
`closure-evidence/v2/v2.1/campaign-2/tools/queue.tsv` (the queue), `closure-evidence/v2/v2.1/pilot/attempt-2/`
(`forecast.json` and the lane records). **Numbers:** `t0_reuse_estimate.py` beside this file, read-only:

```
python3 -B docs/v2.1/proposals/t0_reuse_estimate.py closure-evidence/v2/v2.1/T0-SWEEP-2.json \
  closure-evidence/v2/v2.1/campaign-2/tools/queue.tsv closure-evidence/v2/v2.1/pilot/attempt-2/forecast.json \
  closure-evidence/v2/v2.1/pilot/attempt-2
```

"runner §n" is a section of `docs/v2.1/MUTATION-RUNNER-V2.md`; a bare §n is a section of this document.

## 1. What T0 establishes, and why it runs per target

Before a target's first mutant, `run_target` writes the target's null mutant (`null_mutant`: `ast.unparse` of the
module, and for a `SCRIPT/fn` target the child script re-unparsed inside its constant first) and runs every kill file
once on it, the whole file, no failfast, each run in a clean environment (`_baseline`, `validation/v2/mutation.py`).
One T0 row per kill file gives:

1. **The file passes the bytes every mutant's rewrite produces** (ORD-1). A file that fails the null fails every
   mutant whatever it does, so it is refused for the target: `kill tests fail on the unmutated tree (T0 null mutant)`,
   every mutant NOT_RUN, and the refused file runs once more on the original bytes (`original` rows: a broken snapshot
   or a rewrite-sensitive file).
2. **A clean run:** no residue in the target's tree and nothing left running (runner §2.3, §2.4). A file that leaves either
   at T0 is refused, so a "residue on every run" storm cannot start.
3. **The reference** (VS-6, lead decision Q3): the counts (ran, skipped, expected failures, unexpected successes) and
   the skipped-test ids. Every later PASS of that file must match them exactly, or the row is INFRA, so a mutant that
   skips one more test, or `os._exit(0)`s before the summary, is never a PASS.
4. **`first_test`:** the selector the bracket uses for a module-level failure (an import, `setUpModule`, runner §4.1).
5. **The blame boundary** (PL-4): a process the baseline leaves stops the target as `... before mutant 1 (T0 <file>)`,
   not as mutant 1's fault.

Why per target today: the null depends on the target (a `SCRIPT/fn` null is not the module's null: ORD-1 verifier (b),
runner §5); T0 runs in the target's own fresh tree, under the target's own ownership boundary, right before its mutants; and a
result is self-contained — one result's own rows say what its baseline was, with no reference to another result.

The null is the same for every target of one module outside a child script, and for every target inside the same
child script, which is why reuse is possible at all: the 466 targets of
manifest revision 2 have **29 distinct nulls, 41 kill files and 139 distinct (null, kill file) pairs** (the sweep).

## 2. What T0 costs (measured)

- **The sweep** (`preflight-3/README.md`): every one of the 139 pairs through the runner's own T0, alone under the heavy
  lock, at `70423f9`: 139 of 139 PASS, no residue, no leak; 9 rows with skipped tests; 5,094 s of T0 runs, 5,290 s
  wall.
- **Under campaign load** (pilot attempt 2, `forecast.json`, `ord`): a target's T0 costs `L` = **1.154** × its chain
  (median over the 9 pilot targets; chain = the sum of its kill files' sweep T0 seconds).
- **Campaign 2:** the 457 queued targets hold **1,525 (target, kill file) T0 runs** over the 139 pairs:
  `L × Σ_p n_p × s_p` = **17.3 worker-hours**. Over the 466 targets the forecast's T0 term is 18.0 of
  **161.8 worker-hours**, **11.1 %**.

## 3. What reuse would save (estimate)

Notation: `s_p` = pair p's sweep T0 seconds plus its `overhead_s`; `n_p` = the queued targets holding p; `L` = 1.154.
The pairs are unevenly shared: 19 pairs are held by one target (nothing to save), the largest by 58; the five largest
savings are `test_v21_continue_integrity.py` (≈ 217 s a run) on the nulls of `bundle_cli.py` (23 targets),
`lineage.py` and `run.py` (19 each), and `test_v21_review_chain.py` (≈ 149 s) on `run.py` (19) and `review_ocr.py` (16).

| Rule | Formula | T0 worker-h | Saved worker-h |
|---|---|---|---|
| today (per target) | `L × Σ_p n_p s_p` | 17.3 | — |
| one row per pair, campaign-wide | `L × Σ_p s_p` | 1.6 | 15.7 — **excluded** by §4 (same worker) |
| one row per pair per worker, no window | `≤ L × Σ_p min(n_p, 4) s_p` | ≤ 5.8 | ≥ 11.6 |
| same worker, window 1 h (model) | queue model below | | 2.2 (13 % of T0) |
| same worker, window 2 h (model) | | | 4.4 (25 %) |
| same worker, window 6 h (model) | | | 8.0 (46 %); 7.2 with 10 % sentinels |
| same worker, window 12 h (model) | | | 9.9 (57 %) |
| same worker, window 24 h (model) | | | 11.2 (65 %) |
| same worker, no window (model) | | | 12.1 (70 %) |

**The queue model** (not a measurement): four workers take targets in queue order (longest expected first), each the
next one when it is free, as `qworker.sh` does; a target costs `forecast.py`'s `chain × L + n × (s × S + (1 − s) × K) ×
chain` (pilot survivor rate `s` = 0.133, `K` = 0.132, `S` = 1.134); a (target, file) T0 is saved when the same worker ran
an own T0 of the same pair that started at most `h` hours earlier (a reused row is never a source). The schedule is the
no-reuse one; its makespan is 39.0 h, against the forecast's ≈ 40 h of wall time. Sentinels at a fraction `f` cost
`f × saving`.

**Reading:** at a 6 h window the saving is about **7–8 worker-hours of about 160 (≈ 5 %), about 2 h of about 40 h of
wall time.** Grouping each pair's targets on one worker would move the saving towards the 15.7 h of one row per pair,
but gives up the longest-first balance (an idle tail); that is not modelled. Reuse is a small lever; the dear
end-to-end kill files are the large cost (`pilot/attempt-2/README.md`).

## 4. When one T0 row may stand for another target

All conditions, each recorded in the reusing result (§7) and checked by the record check, never only by the runner:

| # | Condition | Why | Recorded / compared as |
|---|---|---|---|
| C1 | Same module source and the same null-mutant digest | the reference is a property of (null, file); a `SCRIPT/fn` null is not the module's | `source_sha256` of the module; sha256 of `null_mutant(src, func)` |
| C2 | Same kill-file bytes and closure | the file and everything it imports or reads | sha256 of the kill file; its closure inside the COPY tree is C3, outside it C5 |
| C3 | Same COPY tree digest | every file a kill test can read in the tree | `tree_sha256` (runner §2.1: mtime-free; one value across all 8 pilot lanes). Stricter than needed — the sweep at `70423f9` and the pilot at `5719f1f` differ in it and agree in every reference — and kept strict |
| C4 | Same harness and runner version | the runner decides PASS (counts, skips, residue, settle) | sha256 of the running `mutation.py`, `cleanup_authority.py`, `owned_run.py` and the kernel's ProcessRange module (the worker's own files, not the tree's copies); the worker script's sha256 and its `mutation.py run` argv without the target; the record format version |
| C5 | Same worker environment class | 9 of 139 sweep rows skip tests, and skips depend on the host (e.g. the 3 `RealBinary` tests of `test_v21_review_chain.py`); the host can change mid-campaign (the three files found in the host interpreter's site-packages during B-03, origin under separate investigation) | the interpreter (realpath, `sys.version`, platform), the kill-test environment's kept values (`ENV_KEEP`), a digest of the listings of the `PATH` directories, a digest of the interpreter's site-packages (names, sizes, sha256), the OS release |
| C6 | Same worker, same worker session, bounded age | drift grows with time; a stop or restart means the worker's state was unknown | `_worker(root)`; a session id new at every worker start, passed by the worker; source age ≤ `T_max` (proposed 6 h, the owner's to set; the pilot's rows of §8 span about 6 h); never across a stop (exit 3) or a restart sweep |
| C7 | The source row is clean and its target accepted | a row from a target that later stopped or errored comes from a state the runner itself could not vouch for | the source is an own T0 row (never a reused one): PASS, no `residue`, `leaked`, `cleanup` or `stopped`; the source target's result has no `error` and is the accepted result of that target in the account |
| C8 | Skipped ids and counts identical | the reference is exactly what a PASS must match | every own T0 row of the pair on that worker and every sentinel (§8) has the source's counts, skipped ids and `first_test`; any difference disables the pair |

## 5. What is never shared

- **The per-target environment:** the scratch directory, the pristine copy (per `main()`), the tree and its base
  manifest, the ownership boundary (`ca.establish`), the run directories with their fresh HOME/XDG/TMPDIR, the run
  tokens.
- **The settle before the target** (`_settle`): it always runs.
- **The bracket's controls:** every FAIL is still confirmed by two control PASSes of the failing test on the null in the
  target's own tree, the re-run, and the fresh-tree re-measure (runner §4.1, §14 fixes 9 and 10). A KILLED mutant therefore
  never rests on a borrowed row.
- **Refusal:** a non-PASS T0 row is never reused. A target is refused only by its own T0, and the `original` diagnostic
  runs only for its own refused file.
- **Ownership and cleanup authority** (INV-MUTATION-AUTHORITY): nothing in a reused row is an input to a signal or a
  removal. The source's `leaked: []` says nothing about the reusing target's processes.
- **Across workers, sessions, snapshots or campaigns:** nothing. Mutant results are never shared; only the reference is.

## 6. Risks

- **R1 drift.** The reference ages. A host change (site-packages, `PATH`, disk — attempt 1's ENOSPC — or load near the
  900 s timeout) that changes counts or skips shows up under reuse as INFRA rows on mutants instead of a T0 refusal
  before any mutant: a cost, not a false class. A change that alters nothing visible would pass a per-target T0 as
  well. Bounded by C5, C6 and the sentinels.
- **R2 state leakage between targets.** What outlives a target lives outside its scratch: host-level state (the
  interpreter's site-packages, absolute `/tmp` paths, launchd jobs, ports, a real home a test reaches without `HOME`).
  Today the target's own T0 is the first run that can fail on such a leak, before any mutant (fail-closed refusal).
  Under reuse the first such run is mutant 1's. The bracket still runs the null on the target's own tree, so a leak that
  fails the null makes no kill; but the leak no longer shows as a refused target.
- **R3 order effects.** (a) FS-2: today every mutant runs after T0 has run each kill file once in the tree, so the
  unchanged modules' `__pycache__` exists. Under reuse, mutant 1 (and each mutant up to the first run of each file) runs
  in a tree no kill file has run in, a state no campaign-2 mutant was measured in. The caches are of unchanged sources
  (runner §14 fix 1), so imports are the same; the exposure is a kill test that observes caches in the tree (12 test files read
  or set bytecode state; none known to depend on the tree's caches, runner §14 FS-2). §8 step 1 compares every mutant's class
  for this reason. (b) The source ran the file after its own kill set's earlier files; the reuser's kill set differs.
  The clean-run argument (runner §7.1) makes that irrelevant except through (a). (c) How much is reused depends on the queue
  order and on which worker takes which target (§3).
- **R4 ownership and blame.** A null run that would leave a process now first runs as mutant 1's run, so the stop names
  `at mutant 1 (<file>)` instead of `before mutant 1 (T0 <file>)` (PL-4). The classes are unaffected (mutant 1 INFRA,
  the rest NOT_RUN, the target errored); the diagnosis is worse. Reuse must never move authority (§5).
- **R5 correlated nondeterminism.** Per-target T0 gives each target its own draw of a flaky file's skips. Reuse gives
  every reuser the source's draw, so a source taken in a rare state turns into INFRA rows on all its reusers (a cost
  and a re-measure).
- **R6 the record check has a gap reuse would open.** Read in the code at `3e6ebf1` (`_problems_v2`, lines
  1646–1647): the check refuses a T0 row that did not pass, but does not require one T0 row per kill file. That is not
  a defect for today's runner, which writes one per file whenever it runs mutants. But a reused result read by today's
  check would be accepted without its reference being verified. The runner change must therefore mark the format so
  today's check refuses it, and require one verifiable reference per kill file (§7).
- **R7 a new trust input.** Each target is its own `mutation.py run` process (`qworker.sh`), so reuse needs a store
  between invocations. The record check must never trust that store. Every reused reference is copied whole into the
  reusing result and verified against the source result in the account. A missing, stale or edited store can then cost
  a T0, but never change a reference.
- **R8 cascade.** If a source result is discarded or re-measured (a stop, a changed target), every result that reused
  its row loses its reference and is re-measured.
- **R9 a small gain for a new path in an authority-sensitive runner** (§3: about 5 % at a 6 h window).

## 7. The runner change it needs (not built)

- **Runner:** per (target, kill file), when a source satisfying C1–C8 exists in the worker session's store and the
  sentinel draw (§8) is negative, no T0 run: `tg.ref[file]` is taken from the source row and the result records the
  reuse; otherwise an own T0 run, as today. The files that are not reused still run in declared order, and `_settle`
  before the target is unchanged. The store is append-only, lives in a directory the worker names outside every tree and
  scratch, and the runner never removes it, so no destructive site is added.
- **Record** (a new format marker, e.g. `"t0_mode": "reuse-1"`, that today's check refuses): `t0` holds the own rows,
  as today; `t0_reused` holds `[{file, key: {C1–C6 values}, source: {target, worker, session, started, row (whole),
  row_sha256}, age_s}]`; `t0_sentinel` holds `[{file, seed, source row_sha256, match}]`, the sentinel's own row being
  in `t0`; plus the counts `t0_own`, `t0_reused`, `t0_sentinel`. The account summary prints them per target, and the
  campaign report states how many baselines were reused.
- **Check:** every kill file has exactly one own PASS T0 row or one `t0_reused` entry. A reused entry's key must equal
  the result's own values. Its source result must be the accepted one in the account, holding an own T0 row whose
  sha256 is `row_sha256`, and it must satisfy C7. The age must be ≤ `T_max`, and a reused row is never a source. A pair
  with any recorded sentinel mismatch refuses every result that reused it until re-measured. Campaign-2 results keep
  today's verdicts.
- **Tests** (toy targets, like `::T0`): one per key component (changed → an own T0 runs); a source with residue, a
  leak, a stop or an error → no reuse; an age above `T_max` → no reuse; across a session → no reuse; a sentinel mismatch
  → the pair disabled and its reusers refused; a tampered row or a missing source → refused; a reused row never reaches
  `ca.signal_owned` or a removal (like `::Proc`); the `::Order` matrix with reuse on → the same classes in every order;
  every campaign-2 result → the same verdict under the changed check; `mutation.py --check` → unchanged for historical
  phases. Not checked here: whether `proof()` and `S2.account` read a result that carries the new keys unchanged.

## 8. Confirmation before adoption

The required fields are the reference (outcome, the four counts, the skipped ids) and `first_test`. `tail_sha256` is
recorded and compared, but not required: it is not stable for PASS rows (below). With 0 mismatches in `n` independent
comparisons, the 95 % upper bound on the mismatch rate is about `3/n` (rule of three).

**Step 0 — retrospective, free, after campaign 2.** Campaign 2's results will carry up to 1,525 own T0 rows for the 139 pairs,
over 4 workers and about 40 h. For each pair, compare every own row's required fields with every other's, by same or
different worker and by age. Adoption requires them identical within every (pair, worker, `T_max`). Already measured on
pilot attempt 2 (`t0_reuse_estimate.py` with the pilot directory): 44 (target, file) pairs, each with 3 own T0 rows —
the sweep's at `70423f9` (alone, 2026-10-07 21:38–23:07Z) and the `decl` and `ord` lanes' at `5719f1f` (four lanes at a
time, 23:15–03:48Z), each lane in its own worktree, so a different worker id. Required fields identical in **44 of
44**; `tail_sha256` identical in 43 of 44 (`story_runner.py::_fail` × `test_p6_stages.py`: three different tails, all
PASS with the same reference). This step cannot see R3 (a), because every campaign-2 mutant ran after its own T0.

**Step 1 — paired experiment, with the changed runner, before adoption.** Choose the targets before measuring
anything: at least 8 pairs, each with at least 3 targets (the source and reusers at short and near-`T_max` ages),
including the dearest end-to-end pairs, at least 2 pairs with skipped tests, at least 2 `SCRIPT/fn` nulls and some
module-level ones, preferring targets with few mutants. Measure each target in two arms, at one snapshot, in one worker
environment class: A with a per-target T0 (today), B with reuse on. Alternate which arm runs first between pairs, as
the pilot did. Acceptance requires all four:

1. every reused reference in B equals the reuser's own T0 reference in A, on every required field;
2. every mutant's class is the same in A and B (keyed by generator position);
3. B has no INFRA row, TIMEOUT, stop, residue or leak that A lacks;
4. B's records pass the changed check, and A's records pass it as they pass today's.

Also recorded: differences in `killed_by` and `tail_sha256`, the T0 seconds saved, the wall time per target. Any
failure of 1–4: not adopted, and the finding goes to the owner.

**Step 2 — sentinels, in the campaign that adopts it.** A fraction `f` (proposed 0.1) of the reuse opportunities is
drawn as `sha256(seed ‖ target ‖ file) < f × 2^256`, with the seed written in the campaign's start record. The draw is
therefore fixed before any run, reproducible by the check, and not chosen after seeing anything. A sentinel runs the
target's own T0 and uses it, so that target is measured exactly as today, and compares it with the reference it would
have reused. On a mismatch, reuse of that pair stops on that worker at once. At account time, every result that reused
a reference of that pair (on any worker) is refused until re-measured with its own T0, and the mismatch is listed in
the campaign report. The report gives the sentinels run and matched, by age, with the rule-of-three bound.

## 9. Reconciliation with the campaign snapshot `5719f1f`

| File (this commit) | Targets | Tests / harness | Evidence to re-measure |
|---|---|---|---|
| `docs/v2.1/proposals/T0-BASELINE-REUSE.md` (new) | none: not a target module, not a kill file | no test reads it. It lies inside COPY (`docs/v2.1`), so a run at a commit that holds it has a `tree_sha256` different from `5719f1f`'s | none for campaign 2: its workers run detached worktrees at `5719f1f`, which do not hold it |
| `docs/v2.1/proposals/t0_reuse_estimate.py` (new) | none | a read-only script, run by no test or harness; inside COPY like the document | none |

No runner file, kill file, module under `aisef2/`, queue, execution-order table or record is changed.

## 10. Not done, not verified

- No runner code, no test of reuse, no paired experiment, no sentinel.
- The window rows of §3 are a model (forecast costs on the no-reuse schedule), not a measurement. The other rows are
  arithmetic on the measured sweep seconds × the pilot's `L`.
- `T_max` = 6 h and `f` = 0.1 are proposals, not values derived from data.
- Not checked: whether `proof()` and `S2.account` accept a result that carries the new keys.
