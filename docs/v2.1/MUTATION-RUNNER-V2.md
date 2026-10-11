# Mutation runner v2: the runner contract

**Status:** implemented on branch `v21r/runner` (worktree `.claude/worktrees/v21r-runner`, based on `c9c736f`), commits
listed in §9; the provers' open items after it are fixed by the series of §14, which corrects every claim below that it
changes. Not pushed. The V2.1 campaign has not been restarted.
**Closes:** every confirmed finding of the V2.1 runner audit (`scratchpad/audit/AUDIT-FINDINGS.json`). Where an
auditor and a verifier disagree, the verifier wins. ORD-8 was refuted and is not a basis for any rule here.
**Reviewed:** the two design reviews of 2026-10-07 (evidence validity; feasibility and cost). §13 lists each issue they
raised, whether it holds, and what this contract does about it; where a review changed a rule, the section below
already states the changed rule.
**Runner:** `validation/v2/mutation.py`. **Record tools:** `validation/qualification/v21_mutation_record.py`, which
reuses `s2_mutation_record.py`. **Authority:** `validation/v2/cleanup_authority.py` (`ca`).
**Tests:** `tests/v2/test_v21_mutation_runner.py` (toy targets and toy kill files built in a temporary root, driven
through the real `run_target`, `_run_tests`, `mutants`, `main`, the real ProcessRange and the real `ca`). Not a kill file.

## 0. Binding rules (owner, verbatim) and what they mean here

- "Xác minh việc đổi thứ tự không làm đổi phân loại trên mẫu có cả killed, survivor và trường hợp lỗi/timeout. Kiểm
  tra mỗi mutant/test có môi trường sạch, không phụ thuộc trạng thái test trước. Timeout hoặc lỗi hạ tầng không được tự
  tính là killed." → §2 (every run starts clean), §3 (per-run outcomes), §4 (a kill is a FAIL the bracket confirms; a
  timeout or an infrastructure fault is never one), §7 (the order matrix).
- "Giữ nguyên tất cả test bắt buộc. Chỉ short-circuit khi đã có bằng chứng giết mutant hợp lệ; survivor phải chạy hết bộ
  test." → §4.1: the chain stops only on a confirmed FAIL; SURVIVED needs one PASS per kill file. §6: no test is
  removed; methods move unchanged to files that stay in the suite.
- "Không dùng nhận định 'mutant tương đương' như lý do đủ để sửa mã." → No rule here depends on equivalence. A survivor
  stays a survivor until a kill test or an audit settles it.
- "Không bỏ test, giảm assertion, thêm skip/xfail hoặc nới oracle để đạt PASS." → No test is skipped, weakened or
  removed. §6 moves whole methods, byte-identical, and adds semantic restatements beside them. The only new skip guards
  are POSIX guards on the runner's own new tests, which drive POSIX process ranges (as the existing CleanupAuthority
  and PthChannel classes do).
- INV-MUTATION-AUTHORITY → §2.4. Only `ca.signal_owned` signals, and only with its own ownership proof. An environment
  token, a command line or a range report is never proof. A process that only names the work tree, such as an
  operator's `tail -f`, is never signalled. The new tests signal nothing: their helpers end themselves on a sentinel.
  Toy kill tests signal only themselves, except one that SIGKILLs its parent once it has proven it the range anchor the
  test's own run started (§3.3).

The cost of these rules: (a) a kill costs three short extra runs, the bracket (§4.1, §14 fix 9); (b) a mutant that hangs in k files
costs k × TIMEOUT; (c) any process the runner cannot prove is its own stops the target, and the worker with it. §10
gives the measured numbers.

## 1. Bytecode (BC-1, BC-2, BC-3, BC-4, ORD-3; BC-5/6 info) — commit 1

### 1.1 Mechanism closed

A timestamp `.pyc` is accepted when `int(st_mtime) & 0xFFFFFFFF` and the source size match its header. Two versions of
the mutated file of one size, written in one whole second, therefore share a `.pyc`, and the second runs the first
one's code. The `.pyc` can be written by the unittest process or by any child of it; a `-I` or `-E` child ignores
`PYTHONDONTWRITEBYTECODE` and `PYTHONPYCACHEPREFIX` and writes into the tree. Neither `-B` nor an environment flag
stops a `.pyc` from being read (BC-2). Deleting `__pycache__` misses a pycache prefix (BC-4).

### 1.2 Change: every version gets a whole-second mtime that no earlier version had

```python
def _write_version(path: pathlib.Path, src: str, last: int) -> int:
    path.write_text(src, encoding="utf-8")
    stamp = max(last + 1, int(time.time()))
    os.utime(path, (stamp, stamp))
    return stamp
```

- `last` starts at the original's own mtime in the pristine copy (`copy2` keeps the checkout's), so every stamp is
  above it (BC-5).
- **Every** write of the mutated file goes through `_write_version` (via `_write`): the T0 null mutant, every mutant,
  the bracket's control and re-run (§4.1), the restore after a tree rebuild (§2.3) and the T0 diagnostic on the
  original bytes (§5). One `last` per target makes stamps unique across all versions of the target (BC-4 condition 1).
- Nothing else changes for bytecode: no `-B`, no `PYTHONDONTWRITEBYTECODE`, no `PYTHONPYCACHEPREFIX`, no
  `__pycache__` purge — none of them closes the mechanism (BC-2, BC-4, ORD-3). The kill-test environment is an
  allowlist (§2.2), so an operator shell's `PYTHONDONTWRITEBYTECODE=1` never reaches a kill test either.
- The tree check (§2.3) ignores `__pycache__` on purpose: the stamp, not a bytecode-free tree, makes bytecode safe.
  FS-2's fixture `.pyc` always matches its never-mutated source; no kill file is edited for FS-2. The stamp itself is
  checked after every run, and any `.py` whose mtime changed is residue (§14 fix 1); what a `__pycache__` can still
  decide is bounded by the fresh re-measure (§14 fix 10, FS-2).

### 1.3 Tests (`::Bytecode`)

1. The trap is live on this host: an `-I` child writes `V = 'A'`'s `.pyc`; `V = 'B'`, same size, same second, read by
   a `-B` child with `PYTHONDONTWRITEBYTECODE=1`, gives `A`.
2. `_write_version`: 20 consecutive same-size versions, each read back correctly by a `-B` child, an `-I` child and a
   child under `PYTHONPYCACHEPREFIX` (BC-4).
3. 30 stamps written in under a second: whole seconds, strictly increasing, above the original's.
4. End to end: a toy whose only kill file asserts through an `-I` child; same-size neighbours of different designed
   classes are asserted present (no "0 wrong with 0 exposures"); every mutant gets its designed class. With the stamp
   switched off (one fixed second) they do not — measured: 3 false survivors, a stale chain.
5. §7's matrix carries the same channel (`test_k`) and its stamp-off control.

BC-3 (screening the old V2.1 records) needs no runner change: no old result is reused (§8).

## 2. A clean environment for every kill-file run (FS-1, FS-3, FS-4, ORD-5, PL-1, PL-3, PL-4, PL-6, PL-8) — commit 2

**Closed:** one tree, one HOME/XDG and one TMPDIR were shared by every kill file of every mutant of a target (and
HOME/XDG by every target of a worker); detached helpers carried state between runs (PL-1); the live record was copied
into later targets' trees (FS-4). State one run left decided later runs, as false kills and as false survivors, across
files of one mutant too (ORD-5 case S), so a fresh tree per mutant is not enough.

**The rule:** a run's outcome counts because the run started clean, and every run starts clean. A run that leaves
something behind keeps its own outcome — it started clean (PL-1 verifier) — and what it left is named on its own row
and removed before the next run. If it cannot be removed, the target stops.

### 2.1 The pristine copy (FS-4)

`main()` builds one pristine copy of the COPY parts per invocation, before the first target and before any record is
written, and every tree is copied from it. The runner's own record files are left out by exact path, never by a name
pattern. Each target result records `tree_sha256`: sha256 over the sorted (path, sha256 of bytes) pairs of the pristine
copy — no mtimes — so it can be compared across worktrees. A direct caller of `run_target` (checker_calibration, the
tests) passes no copy and gets one of its own.

### 2.2 A fresh environment per run (FS-3, PL-8, ORD-5 H)

Each kill-file run gets its own directory in the target's scratch directory (beside the trees, never inside one), and
the environment is an allowlist:

- `PATH`, `LANG`, `USER`, `LOGNAME` — the worker env's keys; on Windows also `SYSTEMROOT`/`SystemRoot`/`WINDIR`, which
  Python needs to start there (feasibility review);
- `HOME`, `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME` → fresh directories of the
  run (on Windows also `USERPROFILE`, `TEMP`, `TMP`, since `expanduser` reads `USERPROFILE` there);
- `AISEF_MUTATION_RUN=<worker>:<run>`, where `<worker>` is sha256 of the runner's root, so it is stable across restarts
  of one worker and different between workers (evidence review).

Under the workers' `env -i` this is the key set kill tests already had; the directories are fresh and the token is
added. `PYTHON*`, `AISEF_TEST_OCR_EXE` and anything else of an operator shell never reach a kill test. `kill-test.log`
is in the run's directory. The run's directory is removed after the run (§2.4 order); a removal failure makes that row
INFRA. Directories are removed only through the `TemporaryDirectory` objects the runner created; no destructive call
site is added, and `destructive_sites.json` is unchanged (the tests signal and delete nothing either, §0).

### 2.3 The tree: checked after every run, rebuilt when it differs (FS-1, ORD-5)

- The base manifest is taken right after each tree is built: relpath → `("d", mode)` for a directory, `(kind, size,
  mtime_ns, mode)` otherwise (lstat), `__pycache__` subtrees and the mutated file left out. Directory mtimes are never
  compared (creating `__pycache__` changes them; FS-1 verifier (c)).
- After every run: paths added or removed, a change of type or mode, and a file whose content differs from the
  pristine copy's are **residue** (content is compared only where the stat differs, so a file only touched or rewritten
  with its own bytes is not residue; feasibility review); so is a mutated file that no longer holds the version under
  test. Residue `{"added", "removed", "changed"}` (each list ≤ 50) goes on the run's own row, and the tree is rebuilt:
  a new tree from the pristine copy, the version under test written with `_write_version`, a new base manifest, the old
  tree removed.
- The cwd is the tree, so `../x` (the tree's holder) and `../../x` (the target's scratch) are reachable too: the
  holder must hold only `tree` (anything else is residue `beside`, and the rebuild replaces the holder), and the scratch
  only that holder and the target's own pristine copy (anything else, `scratch`, cannot be removed by the runner: the
  target stops, RESIDUE_UNREMOVABLE) — §14 fix 2.
- The ownership boundary names the target's scratch directory, which holds every tree and run directory, so a rebuild
  does not move it.
- Measured cost: a stat walk of the 1,995-file COPY tree takes 0.03–0.04 s (ORD-5 verifier); a rebuild 0.5–1.6 s, paid
  only on residue. A kill file that leaves residue at T0 is refused for the target (§5), so a "residue on every run"
  storm cannot start.

### 2.4 Processes: found by token or by naming the scratch, signalled only with proof, settled (PL-1, PL-3, PL-4, PL-6)

New read-only `ca.carriers(prefix, table)`: the processes whose environment holds the prefix — Linux
`/proc/<pid>/environ`, macOS `ps -E -ww -A` (measured: an inherited token shows for a Homebrew python3, not for
`/bin/sleep`), Windows none. Candidates only, like `ca.strays`; stdlib only; MUT-SAFE-8 still holds.

After every run, in this order (evidence review: order fixed, findings on the run's own row):

1. **Settle:** `found = ca.strays(boundary) ∪ ca.carriers("AISEF_MUTATION_RUN=<worker>:") ∪ ca.cwd_under(<scratch>/)`
   — command-line matching is kept in the union because code under mutation builds scrubbed environments (PL-6
   verifier); the cwd scan finds a helper that has neither the token nor a scratch path (§14 fix 4). `ca.signal_owned`
   signals what it proves the runner's (ancestry, birth, group leadership); every pid found, signalled or not, is then
   watched in the authority's own host table for `SETTLE_S` = 60 s (§14 fix 5; it was 5 s); nothing is signalled while
   watching (PL-7). Found
   processes go on the row as `leaked` (`pid`, `command`, `proved`), the signals with their proofs as `cleanup`. A pid
   still alive after the grace raises a stop: RESIDUAL_OWNERSHIP_UNKNOWN. A host table that cannot be read (`ps` fork
   failure) is a stop too: HOST_TABLE_UNREADABLE.
2. **Remove the run directory.** A failure makes the row INFRA.
3. **Check the tree**, rebuild on residue (§2.3).

One settle also runs before T0 ("before the target"), and `main()` sweeps once before its first target: processes
carrying this worker's token or naming any of its scratch directories (`<TMPDIR>/aisef-mut-<worker>-*`), watched for
`SETTLE_S`, never signalled (they were born before this run's boundary, so nothing about them can be proven); one
still alive and `main()` exits 3 before measuring anything (PL-3 verifier (e)).

**A stop** keeps every finished mutant as measured, makes the current one INFRA (`why` = the stop), the rest NOT_RUN,
sets `error` and `stopped` on the target, and `main()` exits 3 after writing the record (§4.4). The worker never runs
beside a process it cannot prove its own: an operator's `tail -f <scratch>/...` stops it, never signalled. The runbook
rule: follow the worker log (it carries a `MUTANT` line per mutant), never a path inside the scratch directory, and
never put that path or the token in a tool shell's command text.

**Release** (inside the run, VS-7/PL-5): `wait_s=RELEASE_WAIT_S` (60 s) is passed at mutation.py's call site;
ProcessRange's own default stays (tests/v2/p4 asserts it) and the kernel is not edited. On a `Residual`, the members,
the escapees seen before release and the pids release() itself named are settled as in step 1, with the anchor's group
signalled only while the anchor is unreaped (PL-5 (b)). Then:

- `RangeEscaped` whose escapees are gone (proven and signalled, or gone by themselves within the grace): the run keeps
  its outcome and the escapee is named (PL-1, PL-7 verifiers; evidence and feasibility reviews). A mutant's class then
  does not depend on whether `escaped()` saw the helper (Linux sees it, macOS does not).
- `RangeNotEmpty`: the row is INFRA (`judged_before_release` keeps what the run itself said); the anchor is reaped once
  its group is gone; a range that still will not empty stops the target.
- Anything unproven and still alive stops the target, as in step 1.

**Not added:** (a cwd-in-tree scan was not added here; §14 fix 4 adds it) a "born during the run, now ppid 1" quarantine (false hits from launchd
jobs); Linux `PR_SET_CHILD_SUBREAPER`; taking the ownership proof before release() (ORD-7 (b); lead decision Q4: no
change to the authority model).

### 2.5 Tests (`::Env`, `::Proc`)

| Test | Old failure | New behaviour |
|---|---|---|
| `Env.test_a_mutant_that_writes_the_tree_cannot_decide_a_later_file_or_mutant` | ORD-5 case S: `tidy()`'s mutants "condition negated" and "True->False" leave `.scratch`; `test_c` asserts it absent. With the restore off, every later `test_c` run fails (old runner: 8/8 false kills). | Both orders: all 8 SURVIVED; the residue is on the two writing runs of `test_s`, nowhere else. |
| `Env.test_home_xdg_tmpdir_are_fresh_and_removed_per_run` | ORD-5 H, PL-8, FS-3: `test_k` writes `$HOME/.k`, `$XDG_CONFIG_HOME/k` and a `mkdtemp`. One shared HOME: the unmutated tree fails. | `test_h` passes every run; the shell's `PYTHONDONTWRITEBYTECODE` does not reach it; no `mkdtemp` is left in the worker TMPDIR. |
| `Env.test_the_live_record_never_enters_a_tree` | FS-4: a copy that takes the live record along fails the kill file on the unmutated tree. | `main()` over two toy targets, both orders, with a record present before and written between targets: no error, one `tree_sha256`. |
| `Proc.test_a_detached_helper_that_names_no_tree_is_found_by_its_token` | PL-1: without the token scan, the helper (setsid, names no tree) lives on unseen and the target "completes" beside it. | RESIDUAL_OWNERSHIP_UNKNOWN at that mutant; classes INFRA then NOT_RUN; `leaked` names it `proved: false`; nothing signalled; it is alive afterwards and ends on its sentinel. |
| `Proc.test_a_baseline_stray_is_blamed_on_the_baseline` | PL-4: the leak was blamed on mutant 1. | `RESIDUAL_OWNERSHIP_UNKNOWN before mutant 1 (T0 tests/v2/test_l.py)`, every mutant NOT_RUN. |
| `Proc.test_an_outside_process_naming_the_tree_is_never_signalled` | PL-6: an operator-like process naming the scratch, born before the boundary. | Stop before the target; never signalled; it exits 0 on its sentinel. |
| `Proc.test_an_ownership_failure_mid_target_keeps_what_was_measured` | VS-4/PL-6: results 1..N-1 were discarded. | A reparented process (not a descendant) appears after mutant 1: mutant 1 SURVIVED kept, mutant 2 INFRA, stopped, nothing signalled. |
| `Proc.test_a_short_lived_escapee_settles_instead_of_aborting` | PL-7: a timed-out test's watchdog decided timeout vs target error by scheduling. | 3 of 3 repetitions: TIMEOUT, no stop. |
| `Proc.test_a_restarted_worker_never_runs_beside_what_an_earlier_run_left` | PL-3 (e): a restarted worker had a new token and never saw the leftover. | `main()` exits 3 before the first target; no record written; the leftover is not signalled. |
| `Proc.test_a_range_that_never_empties_is_bounded_and_never_a_kill` (commit 6, macOS only: the mechanism the VS-7 verifier measured there) | VS-7/PL-5: the test ignores SIGINT/SIGTERM and its child leaves the group, then rejoins it after the group SIGKILL; release() waited without limit. | Release gives up after RELEASE_WAIT_S (patched to 3 s); the row is INFRA `residual: RangeNotEmpty` with `judged_before_release` TIMEOUT; the authority signals the group it proves the runner's (the unreaped anchor's); the target goes on. |

## 3. Per-run outcomes (VS-1, VS-3, VS-5, VS-6, ORD-6) — commit 3

**Closed:** the exit status alone decided, and nothing was recorded. Any non-zero exit was a kill (signal deaths, exit
5, an import failure, a lost report channel); any exit 0 a pass (all tests skipped, `os._exit(0)` before the summary).

### 3.1 The outcome of one run

The kill command is `python -m unittest discover -v -f -s <dir> -t tests -p <file>` (`-f` kept: VS-5 verifier; `-v`
names every test and every skip). The summary is read only after the **last** `Ran N tests in` line, so text a test
prints cannot forge the counts. Its `first` — the failure's **header** — is the whole first header line (`FAIL: test_b
(v2.t.A.test_b) [q]`, a subtest's `[msg]` or `(params)` kept) plus the class of the exception its traceback ended in
(`| AssertionError`). Both reviews measured that a narrower pattern gave `None` for every subTest failure, and
`None == None` matched any re-run. The bracket compares `signature(first)`: `first` with the runner's own temp names
replaced (§15; "the signature" below is that, "the header" the raw line); the record keeps `first` as it was printed.
The header is the line after the report's own `=`×70 separator (§15), so one line a test prints is not the first
failure; a test that prints the separator and a `FAIL:` line itself still is.

| Outcome | When |
|---|---|
| **PASS** | Exit 0, `OK`, no failure/error/unexpected success; at T0 at least one test unskipped; afterwards exactly T0's counts (ran, skipped, expected failures, unexpected successes) **and** T0's skipped-test ids (lead decision Q3) |
| **FAIL** | Exit 1, `FAILED`, at least one failure, error or unexpected success, and a signature. **Not yet a kill** (§4.1). |
| **TIMEOUT** | `wait()` returned no status and `monotonic() − t0 ≥ TIMEOUT`, measured before release() (WaitContract: a timeout never returns before its deadline) |
| **INFRA** | Everything else, each with `why`: a report channel lost before the deadline (VS-3); a signal; exit 5; any other exit; no summary (`os._exit`, a crash); a FAIL with no signature; counts or skips that differ from T0's; a spawn failure (VS-4 (b)); RangeNotEmpty; a run directory that could not be removed; a FAIL the bracket did not confirm (§4.1) |

Measured on Python 3.14 and confirmed by both reviews: a test module that fails to import, and an infrastructure
`OSError` raised in a test, end in a normal `FAILED (errors=1)` summary with exit 1 — a FAIL row, not INFRA. Whether
such a failure is infrastructure is decided by the bracket (§4.1), never by exception class or traceback location: the
VS-1, VS-5 and PL-2 verifiers measured that class-based rules demote genuine kills (EADDRINUSE, ENOENT, EMFILE caused by
the mutant, a mutant that signals its own test) and accept infrastructure faults that surface as assertions.

### 3.2 The row (ORD-6)

Every run — T0, a mutant's run, the bracket's control and re-run, the T0 diagnostic — yields one row: `file`, `role`
(absent for a mutant's own run; `t0`, `control`, `rerun`, `original`), `select` (the `-k` pattern, §4.1), `outcome`,
`why`, `exit`, `seconds`, `overhead_s` (the runner's own time for the run: directory setup, settle, tree check), the
counts, `first`, `skipped_tests`, `first_test` (T0 only), `tail_sha256`, `tail` (non-PASS rows only: the record stays
small; feasibility review), and when they occur `residue`, `leaked`, `cleanup`, `residual`, `judged_before_release`,
`stopped`. The tail is normalised before it is hashed: the run, tree and scratch paths become `<run>`, `<tree>`,
`<scratch>`, a test's own default mkdtemp name directly under `<run>/tmp` becomes `<mkdtemp>` (§15), `Ran N tests in
X.XXXs` becomes `Ran N tests`, addresses are masked, so identical outcomes hash identically
across runs and orders. The module globals `_FAILED`, `_TIMED_OUT`, `_CLEANUP` are gone.

### 3.3 Tests (`::Outcome`)

- Pure: `_summary` on captured texts (OK; skips with a docstring and a subtest skip; a subtest FAIL; a failed import;
  a test that prints a forged `Ran 9 tests ... OK` before the real summary; `NO TESTS RAN`; no summary); `_outcome` for
  every row of the table; `_select` for a test, a subtest, a setUpClass, a setUpModule and a failed import.
- Faults switched on after T0 (`test_fault` reads a flag the test writes once `_baseline` returns): SIGKILL, SIGTERM,
  `os._exit(5)`, an ImportError, EMFILE, a helper's exit code surfacing as an AssertionError. Old runner: both true
  survivors "killed". Now: every faulted row INFRA, no mutant KILLED, the target refused (`UNCLASSIFIED`), each mutant
  named by `target_problems`; without the fault, 2 SURVIVED.
- A one-shot EMFILE in the first run after T0, before a file that validly kills (VS-5 E1/E2): that row is INFRA (`kill
  not confirmed`), the chain goes on, the next file's kill is confirmed — KILLED in both kill-set orders.
- The test SIGKILLs its own range anchor: INFRA `report channel lost after 0.0Xs` in under 1.5 s; a real expiry
  (TIMEOUT patched to 2 s) is TIMEOUT. It signals only a parent `anchor_guard` proves the anchor of the test's own
  run: a child of the test process running `range_anchor.py`, leader of the toy's group and session (that pid stays
  the anchor or its zombie until the test process reaps it); unproven, the toy FAILs and signals nothing — measured:
  with the guard told another controller pid, the mutant is KILLED by that FAIL and the test fails.
- A file whose every test is skipped is refused at T0; a mutant that skips one more test, or `os._exit(0)`s before the
  summary, is INFRA.

## 4. Per-mutant classification and the record (VS-2, VS-4, ORD-2, ORD-6, PL-2, VS-8/ORD-4 compatibility) — commit 3

### 4.1 One mutant: the chain, and the bracket that confirms a kill

```python
def _mutant(tg, entry, src):
    rows = entry["files"] = []
    _write(tg, src)
    for rel in tg.tests:                       # kill-set order; each run clean (§2)
        row = _run_file(tg, rel, rows)
        if row["outcome"] != "FAIL":
            continue                           # TIMEOUT and INFRA never stop the chain
        sel = _select(row["first"], tg.ref[rel]["first_test"])
        _write(tg, tg.null)                    # the unmutated module (the T0 null mutant)
        control = _run_file(tg, rel, rows, select=sel, role="control")
        _write(tg, src)
        again = _run_file(tg, rel, rows, select=sel, role="rerun")
        if control["outcome"] == "PASS" and again["outcome"] == "FAIL" and again["first"] == row["first"]:
            entry["killed_by"] = {"file": rel, "first": row["first"], "seconds": row["seconds"]}
            return                             # the only early stop
        row["outcome"], row["why"] = "INFRA", "kill not confirmed: ..."
```

- **The bracket** (evidence review, critical; it resolves Q6): a FAIL is a kill only when, right away and each in a
  fresh environment, the unmutated module PASSES what failed and the mutant FAILS it again with the same signature (§15).
  Since §14 fix 9 the unmutated module must PASS twice in a row (`BRACKET`), and since fix 10 a FAIL not confirmed in
  place is measured once more on a fresh tree, the whole file (`_remeasure`); the code above is the first version.
  `_select` runs only what failed: the failing test (a subtest's whole test), the class for a setUpClass failure, and
  for a module-level failure (an import, setUpModule) the file's first test from T0, which imports the module and sets
  it up — measured: a failed import still reports under any `-k`. A fault present at the first run and gone by the
  control is not confirmed (the re-run passes too); a fault that persists fails the control. The cost is about one
  test's time per kill, twice — not a pass of the file — and the per-target closing control of the earlier draft is
  dropped, which also removes its order dependence (evidence review, minor 5).
- A mutant-caused failure that is not an assertion (an OSError from a wrong path, a module-level table that breaks an
  import, a mutant that signals its own test with a summary printed) is a kill when the bracket confirms it: the
  unmutated module passes and the mutant reproduces. A run with no summary at all (exit < 0, exit 5, `os._exit`) is
  INFRA and never confirmed (lead decision Q1: such a mutant gets a kill test in the survivor loop).

```python
def mutant_class(outcomes):        # outcomes: the mutant's own rows; a FAIL here is a confirmed one
    if "FAIL" in outcomes: return "KILLED"
    if all(o == "PASS" for o in outcomes): return "SURVIVED"
    if all(o in ("PASS", "TIMEOUT") for o in outcomes): return "TIMEOUT"
    return "INFRA"
```

| Class | When | Stops the chain? | Counts as |
|---|---|---|---|
| KILLED | a FAIL the bracket confirmed | yes, on that file | killed |
| SURVIVED | every kill file ran and PASSed | no | survivor; `AUDITED` may excuse it |
| TIMEOUT | no confirmed FAIL, a TIMEOUT, every other file PASS | no | neither; the target is refused |
| INFRA | no confirmed FAIL and an INFRA row, or the target stopped at this mutant | no | neither; the target is refused |
| NOT_RUN | the target stopped (or T0 refused it) before this mutant | n/a | neither; the target is refused |

No per-mutant time budget: a budget below the sum of the per-file timeouts brings order dependence back (ORD-2
verifier). A mutant that hangs in k files costs k × 900 s (50 of 36,148 committed results hung at all).

### 4.2 The record (runner 2)

Mutant entry: `mutant`, `class`, `killed` (true only for KILLED), `killed_by`, `files` (every row, control and re-run
rows whole), `why` (a stopped mutant), `strays_reaped` and `cleanup` (signals sent with proof, never an estimate: PL-3),
and `timed_out` — the legacy key — **only for the TIMEOUT class**, listing the files that timed out. `S2._timeouts`
counts results that carry it, so in runner-2 records it counts exactly the TIMEOUT class, independently of order, with
`s2_mutation_record.py` untouched.

Target entry: `target`, `runner: 2`, `kill_tests` (the declared list, which `proof()` pins; each chain runs it in that
order unless an execution-order table gives another, recorded as `execution_order`: the table's entry — `files`,
`seconds`, `from` — with main's stamp `table`, `table_sha256`, `table_commit`: §7.2), `source_sha256`,
`tree_sha256`, `mutants`, `killed`, `survivors` (every non-KILLED mutant, generator order), `classes`,
`killed_by_timeout` (= the TIMEOUT class count), `strays_reaped`, `t0`, `original` (when T0 refused a file), `results`
(every generated mutant in generator order, NOT_RUN included, so `proof()`'s mutant-list comparison stays meaningful),
and `error`/`stopped`/`leaked` when they apply. **Any TIMEOUT, INFRA or NOT_RUN mutant gives the target an `error`**
(`UNCLASSIFIED: n mutant(s) neither killed nor survived {...} — re-run them`, unless it already has one): the frozen
`S2.account` and both `proof()`s refuse an errored result, so no audit can excuse such a mutant without any edit to the
frozen tools (both reviews: `S2.account` alone did not refuse an un-errored INFRA mutant).

Field meanings that shift (feasibility review): `UNAUDITED_SURVIVORS` in the v2.1 summary now counts every non-KILLED,
non-audited mutant (TIMEOUT, INFRA and NOT_RUN included); `KILLED_BY_TIMEOUT` counts the TIMEOUT class, which is not
a kill. `v21_mutation_record.build`'s `KILLED` counts results with `killed` and no `timed_out` (on old records equal to
the old `sum(killed) − timeouts`); a `CLASSES` total is added. `build` is not a criterion: `criteria_sha256()` is
unchanged.

### 4.3 What the checks read

- `mutation.target_problems`: a result with `"runner": 2` goes to `_problems_v2`; every other result — every historical
  record — takes the legacy body, byte for byte. `_problems_v2`: the error; a changed source; no mutants; for SURVIVED
  the legacy survivor rule with the same message text (`unaudited survivor {m!r}`; `NO_AUDIT` targets: `survivor {m!r}
  (must be fully killed; audits not accepted)` — checker_calibration's known-bad fixture expects the first); for any
  other non-KILLED class `mutant {m!r} is {class} ({why}): neither killed nor survived — re-run it`, which no audit
  excuses; and consistency: results list every mutant, `survivors` is the non-KILLED list, `killed` the KILLED count and
  each entry's `killed` its class, every KILLED carries its confirmed bracket (FAIL, control PASS, re-run FAIL with the
  same signature, same file), every SURVIVED has one PASS per kill file — in the order its chain ran them — and an
  un-errored target has only PASS T0 rows. An `execution_order`, when the record has the key, is read by the runner's
  own rule (`_order_problem`, §7.2): malformed, it is an inconsistent record and never the declared order; without its
  table's path and sha256 it is inconsistent; with a table that was not committed at the run's HEAD it is refused.
- `mutation.problems_of`: for phase `V2.1` only, a target result without `"runner": 2` is refused ("measured by a runner
  that does not classify — re-measure"). Historical phases keep today's behaviour.

### 4.4 Stopping, and keeping what is finished (VS-4, PL-6, PL-3 (e))

- A start failure (`OSError`/`RangeError` from `ProcessRange.start`) is one INFRA row; the chain and the target go on.
- A stop (§2.4) or an unexpected exception inside a mutant (`RUNNER_EXCEPTION`) keeps mutants 1..N-1, makes N INFRA and
  N+1.. NOT_RUN, sets `error` (`<CODE> at mutant 'd' (file): ...`, `<CODE> before mutant 1 (T0 file): ...` or `<CODE>
  before the target: ...`) and `stopped`; `main()` writes the record, prints `STOPPED <target>: ...` and the targets not
  run, and exits 3.
- `main()` prints one `MUTANT <json>` line per finished mutant, flushed; the worker log is kept byte for byte by
  `import_worker`, so a worker killed mid-target loses nothing it measured.
- Cost of a stop (feasibility review: the earlier claim "at most the rest of one target" was wrong): the frozen tools
  refuse an errored result, so a stopped target is re-measured from mutant 1, and the worker's remaining targets wait
  for an operator restart. A resume path is not built (YAGNI): stops have been rare (0 RESIDUAL_OWNERSHIP_UNKNOWN in
  919 committed targets, PL-3 verifier) and a resumed result would need its own proof that both halves ran on one tree.

### 4.5 Tests (`::Classify`)

1. `mutant_class` over every permutation of every multiset of size ≤ 4 of {PASS, FAIL, TIMEOUT, INFRA}: one class.
2. VS-2/ORD-2: `test_hang` hangs on both mutants. Hang first and hang last: KILLED, no `timed_out`, `target_problems`
   empty; the first order's rows show TIMEOUT then FAIL. Hang with a weak file: TIMEOUT 2/2, `timed_out` names the hang
   file, the weak file ran for every mutant, `target_problems` names both, `S2.account` refuses it even with both
   mutants put in the audited set.
3. VS-4 (b): the third run of the target cannot start (BlockingIOError): one INFRA row, that mutant INFRA, the other
   KILLED, no stop; `main()` goes on and the record holds the second target, classified.
4. ORD-6: an assertion kill names its file and signature and carries a confirmed bracket; an `os._exit(5)` file is
   INFRA `exit 5, no unittest summary`; an environment ImportError is INFRA `kill not confirmed: the unmutated module
   FAIL`. The old records of the three were byte-identical.
5. A hand-edited record — a KILLED with no bracket, a survivor list that is not the unkilled mutants, an INFRA mutant
   put in `AUDITED` — is refused.
6. Historical records read as before: for every committed record of P1..V2.0-S2, no entry carries `runner`, and
   `problems_of(record, ROOT, phase) == []`, as at c9c736f; V2.1 refuses a legacy-shaped result. The per-commit gate
   also diffs `mutation.py --check` against c9c736f's output (§9): identical at every commit.

## 5. T0: the baseline is the null mutant (PL-4, ORD-1 gate, VS-6) — commit 4

**Closed:** the baseline ran the original bytes; every mutant runs `ast.unparse` output, so a file that fails *any*
rewrite (ORD-1) "killed" every mutant; the baseline recorded no counts and checked for no strays.

```python
def null_mutant(module_src, func):
    tree = ast.parse(module_src)
    script, _, inner = func.partition("/")
    if inner:                                   # SCRIPT/fn: the child script is re-unparsed inside its constant first
        const = _script(tree, script)
        const.value = ast.unparse(ast.parse(const.value))
    return ast.unparse(tree)
```

Before the first mutant, `run_target` writes the null with `_write_version` and runs **each kill file on its own,
the whole file (no failfast)**, in a clean environment. Each T0 row must be PASS, leave no residue and nothing running;
its counts and skipped tests become the file's reference (§3.1), its first test the module-level selector (§4.1), and
the null is what the bracket's control runs on.

- A file that does not pass is **refused for the target**: `error` = `kill tests fail on the unmutated tree (T0 null
  mutant): <file>: <outcome> <signature|why>[ (left residue)][ (left processes)]; ...`, every mutant NOT_RUN. Each
  refused file is run once on the original bytes (`original` rows): both fail — the snapshot is broken; only the null
  fails — the file is rewrite-sensitive (ORD-1). The prefix is today's, which operators and checker_calibration read.
- T0 replaces the original-bytes baseline at the same cost (lead decision Q7).
- `mutation.py t0 TARGET... [--tests FILE...]`: T0 alone, rows printed, nothing written, exit 1 if any T0 row fails.
  It replaces `scratchpad/m21/preflight.py`, whose "leaked 0" was blind (PL-4), and is the tool of §6's sweep.
- A per-target T0 made by mutants()' own rewrite is required (ORD-1 verifier (b)): a module-level null accepts the
  `"-I", "-S", "-B"` count in process_effect while every HARNESS/* mutant fails it.

Tests (`::T0`): `null_mutant` is the rewrite every mutant gets, on 8 real V2.1 targets — for the 3 SCRIPT targets the
module with the script left out has the same AST and the script parses to the same tree (the feasibility review showed
a whole-module AST comparison is false for them) — and the rewrite of every mutant is that mutant; a toy kill file that
pins source text is refused, named, and its original row PASSes, while with the original as the baseline (the old
runner) it "kills" 3 of 3 mutants against a truth of 1; the `t0` command.

## 6. ORD-1: the rewrite-sensitive kill-file methods — commits 5 and 5b

**Closed:** kill-file methods that assert on module bytes or source text fail the null mutant of the modules they read,
so they "killed" every mutant there whatever it did — 260 targets and 5,709 mutants for `test_v21_identity.py` alone —
which also broke mutation.py's own docstring rule that identity-only killers are never kill tests.

### 6.1 The measurement: every (null mutant, kill file) pair, through the runner's own T0

At 6ab3c09 (commit 4, before any split), `scratchpad/runner-v2/impl/sweep.py` ran T0 — `run_target(..., t0_only=True)`,
the same code a campaign runs — once per distinct (null mutant, kill file) pair of the 444 V2.1 targets, capturing every
failing test, not only the first: **129 pairs over 28 distinct nulls, 5,656 s** under `heavy.sh` (the feasibility
review's count). 113 pairs PASSed; no pair left residue or a process. 16 failed, and the original bytes passed every one
of them (rewrite-sensitive files, not a broken snapshot). They refuse **260 targets** (cli_invocation 86, process_effect
79, file_artifact 45, python_callable_v2 31, run.py 19). The failing methods, with the nulls (and the number of targets
behind each) they fail:

| File | Method | Fails the null of |
|---|---|---|
| test_v21_identity.py | `ThreeIdentities.test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now` | every probe null: ci ×3 (59 + 13 + 14), file_artifact (45), pe ×2 (50, 29), pc2 ×2 (20, 11) |
| test_v21_identity.py | `ThreeIdentities.test_calibrations_of_other_bytes_admit_nothing` | the same 8 |
| test_v21_identity.py | `PthChannel.test_every_active_probe_launch_carries_minus_S` | ci ×3, pe HARNESS (29), pc2 ×2 — not pe's module-level null (2 occurrences survive in the script constants) |
| test_v21_identity.py | `PthChannel.test_the_run_gives_the_probes_this_interpreter_and_the_tests_their_own` | app/run.py (19) |
| test_probe_process_effect.py | `Identity.test_PE_Q0_the_module_passes_the_six_probe_rules_with_its_catalog_facts` | pe HARNESS (29), pe module-level (6) |
| test_probe_process_effect_bytecode.py | `Bytecode.test_FM2_PYC_EFFECT_5_..._the_reproducer_detects_it` | pe HARNESS (29) |
| test_c2_cli_protocol.py | `Identity.test_CLI_Q0_the_module_passes_the_probe_rules_with_its_catalog_facts` | ci HARNESS (14) |
| test_c2_cli_invocation.py | `Bytecode.test_FM2_PYC_CLI_4_..._the_reproducer_detects_the_defect` | ci HARNESS (14) |
| test_python_callable_v2.py | `Q0.test_PCV2_Q0_the_probe_source_rules_pass_on_this_module` | pc2 HARNESS (11) |
| test_python_callable_v2_bytecode.py | `BytecodeV2.test_FM2_PYC_V2_5b_…`, `…_7_…`, `…_9_…` | pc2 HARNESS (11) |

The last three bytecode rows were not in the feasibility review's list: they inject a controlled defect by replacing
the subject's command-line text inside `HARNESS` (`assert HARNESS.count(FLAGS) == 1`), which the reformatted script no
longer holds. Every other method of the 36 kill files passed every null that holds it.

### 6.2 The identity split (commits 5 and 5b)

`test_v21_identity.py` is a V2.1 file whose four failing methods are pinned to bytes or text: they move, as whole
methods with byte-identical bodies, to `tests/v2/test_v21_identity_bytes.py` (in the suite, never a kill file;
`PthChannel`'s decorator, docstring and `setUp` copied verbatim because the moved methods run under that fixture). The
semantic file keeps its name, so `_V21_ID` and every kill-set list are unchanged and the scope manifest's `--check`
stays green; only imports the moved methods alone used are dropped. `mutation.NOT_KILL_FILES` names the bytes file;
`run_target` refuses a kill set naming one; `::KillSets` asserts no kill set does. Re-swept after the split: the 16
(null, `test_v21_identity.py`) pairs PASS, 16/16. The 7 C2-era pairs of §6.1 were not re-swept and still fail (the 60
targets of §6.3, N1); "16/16 failing pairs now pass" would overstate it (order-equivalence prover).

Two moved methods also carried valid kill evidence, restated beside them in commit 5b (ORD-1 verifier (c); reviews E9,
F8; Q5):

- `test_every_active_probe_launch_starts_minus_I_minus_S_minus_B` — the `_harness_argv(...)[1:4]` assertion,
  unchanged (ci/pe/pc2 `_harness_argv`).
- `test_calibrations_bound_to_the_bytes_that_run_admit_and_other_bytes_admit_nothing` — each shipped row re-bound at
  run time to `executing(<its catalog factory>)`, so it holds for any version of the probe modules: the rebound rows
  admit the migrated 2.0.0 bundle, the same rows at `'0'*64` fail exactly check 9 naming the executing digest, and
  `calibrations()` with no rows is the shipped table (run.py `admit` and `calibrations`, bundle `load`, bundle_cli
  `migrate`).

Re-swept after 5b: the 16 (null, `test_v21_identity.py`) pairs PASS, 16/16. The other two moved methods carry nothing valid for any target that held them
(text of run.py; shipped rows whose only killable reader, `calibration.py::executing`, keeps `test_the_cycle1_probe_
keeps_its_one_frozen_digest` and the rebound restatement).

### 6.3 The C2-era kill files: an owner decision (N1)

The other eight methods of §6.1 live in six 2.0-era kill files. Unlike the identity methods, most of them are **valid** kill
evidence for some targets and invalid for others: `CLI_Q0`, `PCV2_Q0` and the three bytecode reproducers fail only the
HARNESS nulls; on the same modules' module-level targets they pass T0, and they detect real defects there (a source-rule
violation, a stale-bytecode reproducer that no longer fires). Moving them out of their files would lose that evidence
for every module-level target, the kind of loss §6.2 avoided with restatements; and a 2.0-era generator
(`validation/qualification/c2_effect_harness.py --run`) looks `PE-Q0` up by name in its file. So this work does not
edit them. T0 refuses the 60 targets they fail — 14 cli HARNESS/*, 29 + 6 process_effect, 11 python_callable_v2
HARNESS/* — with `kill tests fail on the unmutated tree (T0 null mutant): <file>: FAIL <signature>`, fail-closed, until
the owner rules among:

1. move each method unchanged to a non-kill file (the identity rule), accepting new survivors on the module-level
   targets that only it killed, to be killed by new tests in the survivor loop; `PE_Q0` loses nothing (it fails every
   null that holds it) but its 2.0 generator would no longer find it;
2. rewrite each text-based precondition or defect injection to act on the parsed script (AST) instead of its text, so
   the method passes every null — a change of 2.0 kill tests, which B-03d's rule ("không sửa kỳ vọng chỉ để test
   xanh") puts with the owner;
3. let the runner exclude, per target, only the methods that fail that target's T0, recorded on the target — a new
   runner rule that weakens kill sets automatically, which this contract does not adopt without the owner.

**Lead decision (2026-10-07): option 2**, under the owner's B-03b authorization and the 2026-10-07 delegation of the
campaign's optimization within B-03, recorded here for the owner to overturn. Grounds:

- Options 1 and 3 weaken a kill set (1 drops a method from it; 3 lets the runner drop one per target); option 2 keeps
  every method, its name, its file and its assertions. Only how the method observes or injects into the child script
  changes — from the script's text to its parsed form (`ast.unparse` of the parsed script, used on both sides) — which
  is exactly what the null mutant's own rewrite does, so the method's meaning is the same and it no longer depends on
  the formatting the rewrite changes. No expectation is edited, so the B-03d rule ("không sửa kỳ vọng chỉ để test xanh")
  is not engaged.
- Measured (`closure-evidence/v2/v2.1/runner-v2/N1-OPTION-2-EVIDENCE.json`, each method run through the runner's own
  `_run_file`, old bytes against new): every method passes the unmodified tree, old and new; on the module-level mutants
  sampled for each method (40 or 57), and for the three Q0 methods on every module-level mutant of the targets holding
  their file (PE_Q0 215, CLI_Q0 616 with the AGENT/* ones, PCV2_Q0 481), old and new kill exactly the same mutants
  (`killed_by_old_not_new` and `killed_by_new_not_old` empty for all eight; kills 0–48 per method); each injected
  defect still trips its rule on the original module. The six files pass whole at 33f4012 (122 tests).
- T0 sweep at 33f4012: 129 of 129 pairs PASS, 0 of 444 targets refused (was 16 failing pairs and 260 refused targets at
  6ab3c09, before the split and option 2).
- Commits 3ffef74, 44c9c56, b0351a1, a83ebed, a12e0c7, 33f4012 (one per file), merged at a333d93. The 2.0 records,
  corpus and ruling are untouched; those files are 2.0 tests, kept in force, not 2.0 evidence.

### 6.4 What changes and does not

- Every V2.1 target holding `_V21_ID` changes its kill-test closure (the file's bytes changed), so no old result for
  those targets passes `proof()`; none was to be reused anyway (§8).
- The conformance ruling generator (`validation/qualification/v21_conformance_ruling.py`, B-03d) names the moved
  methods by id; its four ROWS ids are re-pointed to `tests.v2.test_v21_identity_bytes.*` (commit 5) and the two
  restatements are added beside them (5b). `missing_tests()` returns `[]` and `derive()` has no problem; the one failure
  of `tests/v2/test_v21_conformance_ruling.py` is the pre-existing "no ruling" (CONFORMANCE-RULING.json is not written
  yet). These rows are B-03d evidence: the owner should see them before the ruling is written.

## 7. Order independence (owner rule; VS-2, ORD-2, ORD-5, PL-1, BC-1, ORD-3) — commit 6

### 7.1 The argument

Write o(m, f) for the outcome of kill file f on mutant m in a run that starts clean: the tree is the pristine copy plus
m's bytes with a stamp no earlier version had; HOME, XDG and TMPDIR are fresh; nothing of this worker's token and
nothing naming its scratch is alive.

1. **Every run starts clean** (§1, §2), and a run that could not start clean does not start: the target stops. So
   o(m, f) depends on m and f only. Kill files are assumed deterministic. One that is not is caught often, not always
   (classification prover: the earlier claim "it shows as an unconfirmed FAIL" was wrong): a file that fails a run
   with probability p, whatever the mutant, gives a confirmed false KILLED only if its first run fails, both controls
   pass and the re-run fails with the same signature — about p²(1−p)²(1+p) per survivor-file with the two controls of
   §14 fix 9 and the fresh re-measure of fix 10 (the p³ term: unconfirmed in place, then the same again on a fresh tree;
   it was about p²(1−p) with one control), and a file that fails every other run of itself is caught every time.
   It can also differ between orders (§7.3).
2. **The bracket is a function of (m, f)** too: it runs only what f's FAIL named, on the null and on m, each clean. So
   whether f's FAIL is confirmed depends on m and f only, and the confirmed outcomes O(m) = {o(m, f)} are a function of
   m and the kill *set*.
3. **The class is a function of the multiset O(m)** (`mutant_class`).
4. **Short-circuit cannot change the class**: the chain stops only at a confirmed FAIL, which makes the class KILLED;
   in any other order that FAIL is still in the set — the runner reaches it or stops earlier on another confirmed FAIL,
   KILLED either way. Without a confirmed FAIL nothing stops early and every file runs.
5. **Order-dependent fields:** `killed_by` and the rows before it; neither is the class, and the reuse tooling must not
   compare them. `timed_out` exists only on the TIMEOUT class, which runs every file, so it is order-free; so is
   `S2._timeouts`.
6. **Target-level fields:** `classes`, `killed`, `survivors` are functions of the classes. A stop is order-dependent
   (whether a leaking file is reached for a mutant killed earlier: ORD-7) but it is a stop, never a class; the stopped
   mutant is INFRA and refused.

### 7.2 The test (`::Order`)

Toy `f(x, verbose=False)` with seven mutants and five kill files, all in every rotation of the kill set (each file in
each position, each pair in both relative orders), TIMEOUT patched to 2 s:

| File | Does | Gives |
|---|---|---|
| `test_a` | asserts `.scratch` absent and `f(1) == "pos"` | FAIL on 4 mutants |
| `test_h` | loops while `f(-1)` is `"pos"` or `""` | TIMEOUT on 3 mutants (2 of them killed by a/k) |
| `test_i` | SIGKILLs itself when `f(±1)` is None | INFRA on 2 mutants (1 of them killed by a/k) |
| `test_c` | writes `.scratch` into the tree when `verbose` defaults to True | residue for the survivor |
| `test_k` | asserts `f(1)` through an `-I` child | the bytecode channel (same-size neighbours of different classes) |

Designed truth: 4 KILLED (two of them after a TIMEOUT row in some orders, one after an INFRA row), 1 SURVIVED that
leaves residue, 1 TIMEOUT, 1 INFRA. Asserted: the sample covers each kind (and the same-size neighbours); every order
gives every mutant its designed class; `classes`, `killed`, `survivors` and the set of mutants with `timed_out` are
identical across orders; the error is the same `UNCLASSIFIED` in every order and nothing stops; every kill is bracketed
exactly once; and every (mutant, file) run has the same outcome, header, exit status and (for PASS and FAIL) the same
normalised tail hash in every order (the toy's labels name no temp path; a failure that names one has another raw header on
every run and in every order — its `signature` and its tail hash are the same, §15) — o(m, f) does not depend on what ran before. **Controls:** with the stamp off
(§1), the tree restore off (§2) and the old stop-at-first-non-PASS rule (§3, §4), each in one order, the classes differ
from the truth, so the toy cannot pass vacuously. Runtime, measured 2026-10-08 at 76e0eca under `heavy.sh` with the
workers' `env -i`: the `Order` class takes 193 s (9 matrix runs — the 5 rotations and the 4 rotations of one declared
set through a table — and 3 controls in one order each); the whole runner test file, 56 tests, 484 s. It is
POSIX-only. (At commit 6 the file had 36 tests and took 252 s, the matrix about 115 s of it.)

**Execution order (ORD-4).** `mutation.py run --order TABLE.json TARGET...` runs the chains of each target the table
orders in its entry's order; every other target, and every T0, runs the declared order. Without a table nothing
changes: the declared order, no `execution_order`.

- *Provenance rule.* A table is derived, never written by hand, and only from a committed measurement:
  `validation/v2/execution_order.py --write SWEEP.json TABLE.json` refuses a T0 sweep record that is not committed at
  HEAD (HEAD's blob must be the bytes it reads) and applies one rule — a V2.1 target whose null mutant (`null_mutant()`
  of the target's module at the tree the table is derived on, hashed as the sweep keys it) has a PASS T0 row for every
  kill file runs its kill set in **ascending T0 seconds of each kill file on that null mutant, ties by declared
  position**; any other target (a file never measured on that null, a T0 that did not pass, a module changed since) is
  listed under `declared_order`, with why, and runs in declared order. The table is `{"table", "tool", "rule", "from":
  {"path", "sha256", "measured_on"}, "orders": {target: {"files", "seconds", "from": {"path", "sha256"}}},
  "declared_order": {target: why}}`. `--check TABLE.json` re-derives it from the record its `from` names and fails
  unless that record is committed at HEAD and the table is byte for byte what it derives now. The order decides only
  which reproduced FAIL comes first (§7.1 steps 4–5), so a stale table costs time, never a class.
- *The sweep record.* `execution_order.py --record SWEEP.jsonl MEASURED_ON OUT.json` writes the committed format —
  `{"record", "measured_on": the full commit the sweep ran at, "rows": [every JSONL line, unchanged]}` — and never
  replaces a file. A row is one (null mutant, kill file) pair run through the runner's own T0 (§6.1): `module`, `null`
  (sha256 of the null mutant's text), `file`, `targets`, `rows` (its T0 row: `role: "t0"`, `outcome`, `seconds`, …),
  `original`, `error`. The sweep to commit under `closure-evidence/v2/v2.1/` is lane c2tests' `sweep-final.jsonl`,
  measured at 33f4012: 129 pairs, 28 distinct null mutants, 36 kill files, 5,302 s of T0 runs (5,491 s wall). Derived
  from an uncommitted copy of it at this branch (a dry run: `--write` itself refuses an uncommitted record), all 444
  V2.1 targets get an order, 340 of them other than the declared one.
- *main* refuses misuse before anything runs — `--order` once, first, with a table and the targets it is for; a name
  that is not a target; an unreadable table, bad JSON, or no `orders` object — and checks **every** entry, for the
  targets it runs and the ones it does not, with run_target's own rule (`_order_problem`: `files` is the declared kill
  set as a multiset, `from` names the record by path and sha256): one bad entry stops main before the first target, so
  no earlier target runs for hours first and no refused entry replaces a result in the record. It stamps each entry
  with `table` (its path in the repository), `table_sha256` and `table_commit` — HEAD's commit when HEAD holds exactly
  those bytes, else null and a `WARNING` line: an uncommitted table is recorded, not refused, so a pilot can still run
  one, and `--check` refuses every result it ordered.
- *The record* keeps the declared `kill_tests` and the stamped entry as `execution_order`; T0 runs the declared order.
  `_problems_v2` reads the key, when present, by `_order_problem` too: a malformed one (`{}`, null, a list, no
  `files`, `files: null`, no `from`) is an inconsistent record, never read as the declared order and never a crash; a
  SURVIVED needs one PASS per kill file in that order; an entry without its table's path and sha256 is inconsistent;
  and one whose `table_commit` is null is refused ("commit it and re-run") — `v21_mutation_record.py` reports it
  through `problems_of`.

`Order.test_an_execution_order_changes_no_class_and_the_record_only_where_it_must` runs the declared set in the four
other rotations through such a table: every class, the target's fields, T0 and `target_problems` equal the declared
order's; each (mutant, file) has the same rows (clock left out) in all nine runs of the matrix; a mutant not killed ran
every file in the table's order; a kill is the first file in that order whose FAIL reproduces, and nothing ran after
it; and at least one kill moved to another file. Controls: a chain that ignores the table fails that test; a record
check that ignores `execution_order` fails `Classify.test_a_survivor_is_read_in_the_order_its_chain_ran`. The
refusals, the record check's agreement with the runner and the provenance are tested in `KillSets` (`run` misuse, every
entry before the first target, the stamp), `Classify` (malformed `execution_order`, an uncommitted table) and
`tests/v2/test_v21_execution_order.py` (the rule, `--record`, `--write`, `--check`, `committed`; fixture
`tests/v2/fixtures/execution_order/`), each with a control that fails it (§14, final verifier 1–4).

### 7.3 Limits, stated

- **A detached process with no token, no scratch path in its command line and a working directory outside the
  scratch** is invisible (a helper that `chdir`s away, or one started with its own `cwd`). Since §14 fix 4 a constructed
  environment or a platform binary that kept the cwd it inherited is found by the cwd scan. The PL-1 grep found one
  detached spawn in the 36 V2.1 kill files (`test_v21_continue_integrity.py` MUL_SLOW, which the test waits for).
- **A kill file whose outcome is nondeterministic** (load-dependent timeouts, `PYTHONHASHSEED` — unpinned, as in the
  workers, OBS-S2-12) can differ between orders through nondeterminism; the rows show it.
- **Stops are order-dependent** (§7.1 step 6) and never produce a class. Concretely (ORD-7): a leftover that outlives
  the grace (`SETTLE_S`, 60 s since §14 fix 5) stops the target in an order that reaches its file and not in one where
  an earlier file kills first; the re-run is deterministic, so in that order the target is never classified. Such a
  stop belongs in the campaign manifest as an order-dependent target fate; removing it needs ownership taken before
  release() (ORD-7 (b)), an authority-model change for the owner.
- **A `__pycache__` written during a run persists in the tree** (FS-2: the ledgerlock fixture's, and every package's):
  the residue manifest leaves `__pycache__` out, and removing it after every run needs either a destructive site
  outside the closed authority-source set, an environment change every bytecode reproducer would see, or a rebuild per
  run (§14, FS-2). Import semantics are unaffected (the caches are of unchanged sources); a FAIL it could cause is
  re-measured on a fresh tree (§14 fix 10); a PASS it could cause (a test that passes only beside a cache) is not.
- **Nondeterministic kill files**: the residual false-kill rate of §7.1 step 1.

## 8. What this does NOT change

- **Historical records and their `check()`:** P1..P6, C2-*, K-*, V2.0-S2 are read by the unchanged legacy branch;
  `mutation.py --check` prints the same output as at c9c736f (diffed at every commit, §9). Their verdicts are not
  re-read under the new rules: P2/P4's 35 legacy clock-only kills still pass `--check` (lead decision Q2). Running
  `mutation.py run` on a historical-phase target would write runner-2 entries into a sealed record; the runbook forbids
  it and this work never does it.
- **Frozen criteria:** `s2_mutation_record.py` is not edited. In `v21_mutation_record.py`, `PHASE`, `SNAPSHOT`,
  `EXCLUDED`, `proof`, `_current`, `CRITERIA` and `FROZEN_CRITERIA_SHA256` are not edited; `criteria_sha256()` is
  unchanged (the Phase test asserts it).
- **Kill sets and their order:** `V21_TARGETS` and every `*_TARGETS` list are byte-identical; the files keep their
  names, so `REQUALIFICATION-MANIFEST.json`'s `--check` stays green. No kill set is reordered: an execution order
  (cheapest first) is given by a table (`run --order`, §7.2) and recorded as `execution_order` beside the declared
  `kill_tests`, so `proof()` keeps comparing the declared list (ORD-4 verifier). This work commits no table and no
  sweep record: the generator derives a table only from a sweep record committed at HEAD, which the lead commits.
- **`closure-evidence/`:** no record is edited.
- **The kernel** (`aisef2/`): untouched, ProcessRange's default `wait_s` included.
- **TIMEOUT stays 900 s per file.**
- **Reuse:** no result measured by the old runner is reused (VS-1, BC-3, ORD-1); `problems_of("V2.1")` refuses them.
  The stopped cc53596 worker histories (m21-w1..w4) must not be imported.

## 9. Commits

| # | Commit | Concern | Tests it carries |
|---|---|---|---|
| 1 | `4a26723` | bytecode: `_write_version` (§1) | `::Bytecode` |
| 2 | `e15cad6` | clean environment: pristine copy, allowlisted fresh env and token, tree check and rebuild, `ca.carriers`, settle and stop, restart sweep (§2); verdicts still the old runner's | `::Env`, `::Proc` |
| 3 | `ce5f4ef` | classification and record: per-run outcomes, the bracket, `mutant_class`, the runner-2 record, the stop, `target_problems`/`problems_of`, v21 `build` (§3, §4) | `::Outcome`, `::Classify`, `::Proc` (PL-7, mid-target stop) |
| 4 | `6ab3c09` | T0: `null_mutant`, T0 per file, the original diagnostic, `mutation.py t0` (§5) | `::T0` |
| 5 | `ba853fd` | the identity split, `NOT_KILL_FILES`, the conformance ruling's ids re-pointed (§6.2) | `::KillSets`; the T0 sweep table in the message |
| 5b | `c08760b` | the two semantic restatements (§6.2) | re-swept: 16/16 identity-file pairs |
| 6 | `9cba6e0` | the order-independence matrix and the bounded release (§7, §2.4) | `::Order`, `::Proc` (VS-7/PL-5) |
| 7 | `671d78e` | the contract, with the reviews' resolutions and the measurements | — |
| fix 1–13 | §14 | the provers' open items, one commit each, each with its test | §14 |
| ORD-4 | `f6151aa` | the execution-order table: `run --order`, `execution_order`, the record check (§7.2) | `::Order` table rotations, `::Classify`, `::KillSets` |
| guard | `f2e0777` | the toy that kills its range anchor proves it is that anchor (§3.3) | `::Outcome` |
| ord 1–4 | `eec1bcf`, `4a3b31b`, `8fc1350`, `76e0eca` | the final verifier's items on the execution order (§14) | `::KillSets`, `::Classify`, `test_v21_execution_order` |

No kill-set reorder is in this series: the owner asked for it as a separate, later commit (§8). The execution-order
table (lane execorder, §7.2) runs a declared set in another order without reordering it.

Commits 1–5 ran, under `env -i` with the guard PATH and `python3 -P`, the heavy parts under `heavy.sh`: `ruff check`
on the changed files; `mutation.py --check` diffed against c9c736f's output (identical at every commit);
`destructive_authority.py --check` (PASS, ledger unchanged); `v21_requalification.py --check` (PASS);
`test_mutation_safety`, `p2/test_mutation_targets`, `p4/test_process_range` PROC_OWN_1, `test_s2_mutation_record`,
`test_v21_mutation_record`, `test_v21_mutation_runner`; and the mutation checker's calibration
(`checker_calibration._mutation`), whose observed problems are identical to the committed 2.0 record's. Commits 5 and
5b added `test_v21_identity`, `test_v21_identity_bytes`, `test_v21_conformance_ruling` and the T0 re-sweep of the
changed file; commit 6 (tests only) ran ruff, `destructive_authority --check`, `mutation.py --check` and the whole
runner test file. No full suite was run.

## 10. Overhead: measured

### 10.1 Old runner against new, same tree, same targets (measured 2026-10-07, `heavy.sh`, the workers' `env -i`)

Both runners ran `mutation.py run <target>` on one tree — `git archive c08760b` (the split identity file included) —
once with c9c736f's `mutation.py` dropped in, once with c08760b's (`scratchpad/runner-v2/impl/measure.sh`). Three
small V2.1 targets, each with a 2-file kill set:

| Target | Mutants | Old wall | New wall | Δ | New: runs (T0 / mutant / control / re-run) | New: kill-test s + runner s |
|---|---|---|---|---|---|---|
| `static_admission.py::check_contradictions` | 32 | 16.0 s | 46.3 s | +189 % | 2 / 32 / 32 / 32 | 17.0 + 26.8 |
| `cli_invocation.py::_stream_bytes` | 7 | 6.7 s | 15.5 s | +132 % | 2 / 7 / 7 / 7 | 7.0 + 6.2 |
| `process_effect.py::_flat_ok` | 3 | 10.2 s | 14.8 s | +45 % | 2 / 3 / 3 / 3 | 9.8 + 3.0 |

- **Classes:** every mutant (42) has the same verdict under both runners (all KILLED, by the first kill file); no
  difference to explain.
- **Per run, the runners cost the same:** on `check_contradictions` a run costs 0.43 s new (0.16 s of kill test, 0.27 s
  of range start and release, settle — two `ps` reads — run directory and tree check) against 0.47 s old (16.0 s over
  34 runs, its range, interpreter start and one `ps` read per mutant included).
- **The whole difference is the bracket** (§4.1): two more runs per KILLED mutant (three since §14 fix 9), here about 0.43 s each (only the
  failing test runs, but the interpreter, the range and the module import are paid), so about **+0.9 s per kill**.
  A survivor pays no bracket: its cost is today's (one run per kill file) plus the settle per file (≈ 0.1 s).
- On these kill-dominated, sub-second targets the overhead is far above the earlier draft's 25 % acceptance bar. The
  responsible item is the bracket, which the evidence review's critical finding (E1) requires; no weaker rule is
  proposed. Two levers that keep every rule, not built (YAGNI until the owner asks): read the host table once per
  settle for both `strays` and `carriers` (one `ps -E` instead of two reads, ≈ 0.05 s a run), and skip the control's
  separate interpreter start by running the control and the re-run in one range (it would no longer be two clean
  runs, so it needs its own argument).

### 10.2 What the campaign pays

- **Kills:** about +0.9 s per kill on fast files, more where a file's import or `setUpClass` is heavy (unmeasured). The
  V2.0-S2 campaign had 12,248 kills in 12,727 mutants; at that ratio, V2.1's 11,363 mutants give about 10,900 kills,
  about +2.7 CPU-hours — under an hour of wall time on 4 workers. §14 fix 9 adds one control run per kill (about
  +0.45 s each, +1.4 CPU-hours), fix 4 a 0.02 s `lsof` read per run; fix 10 costs only on an unconfirmed FAIL.
- **T0** is the old baseline's cost (one pass of each kill file per target); the sweep measured 129 distinct pairs in
  5,656 s; the campaign's per-target T0 is about 15 CPU-hours (feasibility review), as the old baseline was.
- **The large changes are not overhead but evidence:** the 200 targets the split unmasks (§6) now run their kill sets
  until a confirmed kill instead of dying at `test_v21_identity.py`, and a TIMEOUT no longer stops the chain (k × 900 s
  for a mutant that hangs in k files; 50 of 36,148 committed results hung). For the 5,709 masked mutants the feasibility review puts it
  between 49 worker-hours (each stopping at the identity file, as before) and 173 (each running its whole kill set),
  against the old campaign estimate of 63.8; where it lands depends on where each mutant's first valid kill sits, and
  only the campaign itself can say.
- **Record size:** PASS rows keep no tail; measured on `check_contradictions`, a row is 0.33 KB without one and
  1.8 KB with one (non-PASS rows; FAIL rows of kills and their re-runs).

## 11. Coverage of every confirmed finding

| Finding | Mechanism closed | Change (§, commit) | Test: old failure → new behaviour |
|---|---|---|---|
| VS-1 | any non-zero exit was a kill; no cause recorded | §3.1, §3.2, §4.1 bracket (3) | `Outcome` faults after T0 → INFRA rows, 0 KILLED, refused |
| VS-2 | a timeout was a kill and stopped the chain; `timed_out` order-dependent | §3.1 TIMEOUT, §4.1 no stop, §4.2 `timed_out` only on the TIMEOUT class (3) | `Classify` 2 |
| VS-3 | a lost report channel was a timeout | §3.1, judged by the clock before release (3) | `Outcome` anchor loss / real expiry |
| VS-4 | an infra event discarded mutants 1..N-1 or killed the worker | §4.4 (3); outside a mutant: §14 fix 8 | `Proc` mid-target stop, `Classify` 3, §14 fix 8 |
| VS-5 | failfast hid a valid kill behind an infra ERROR, in a file and across files | §4.1 the bracket; an unconfirmed FAIL continues the chain (3); in a file: §14 fix 10 | `Outcome` transient EMFILE, both orders; §14 fix 10 |
| VS-6 | exit 0 accepted with any count; vacuous baseline | §3.1 counts and skipped ids against T0; T0 refuses all-skipped (3, 4); §14 fixes 10, 13 | `Outcome` vacuous pass; §14 |
| VS-7 / PL-5 | Residual → kill; unbounded release | §2.4 release (3) | `Proc` bounded release (macOS) |
| FS-1 | shared tree/HOME/TMPDIR | §2.2, §2.3 (2) | `Env` case S, HOME; `Order` restore-off control |
| FS-2 | fixture .pyc in the tree | harmless under §1 (1); not removed — §7.3, §14 | `Order` bytecode channel; §14 fix 10 (presence toy) |
| FS-3 | mkdtemp leaks into the worker TMPDIR | §2.2 (2) | `Env` HOME/XDG/TMPDIR |
| FS-4 | the live record copied into later trees | §2.1 (2) | `Env` live record |
| BC-1 | same-second same-size versions shared a .pyc | §1.2 (1) | `Bytecode` 1–4, `Order` stamp-off control |
| BC-2 | `-I` children write, `-B` parents read | §1.2 (1) | `Bytecode` 1–2 |
| BC-3 | 24 exposed old V2.1 kills | no reuse; `problems_of("V2.1")` (3) | `Classify` 6 |
| BC-4 | a purge misses a pycache prefix | §1.2 (1) | `Bytecode` 2 under PYTHONPYCACHEPREFIX |
| PL-1 | detached helpers unseen | §2.4 token ∪ command line ∪ cwd (§14 fix 4), settle after every run (2) | `Proc` token helper, cwd helper |
| PL-2 | infra fault after the baseline became kills | §4.1 bracket per kill (3), two controls (§14 fix 9) | `Outcome` persistent and transient faults, TIME_WAIT stand-in |
| PL-3 | `strays_reaped` 0 by construction; strays persisted | §2.4 (signals counted only with proof; stop; restart sweep) (2) | `Proc` cases, restarted worker |
| PL-4 | baseline unchecked; leak blamed on mutant 1 | §2.4 settle after every run including T0 (2, 4) | `Proc` baseline stray |
| PL-6 | an outside process naming the tree aborted the target and lost its results | §2.4, §4.4 (2, 3) | `Proc` outside process, mid-target stop |
| PL-7 | timeout vs abort depended on a helper's exit speed | §2.4 settle; RangeEscaped keeps the outcome (2, 3) | `Proc` short-lived escapee (3/3) |
| ORD-1 | byte/text-identity tests "killed" every mutant of 5 modules | §5 T0 gate, §6 split (4, 5, 5b); 60 targets refused pending N1 | `T0` toy; §6.1 sweep (129 pairs) |
| ORD-2 | stop on timeout or any non-zero exit | §4.1 (3) | `Order`, `Classify` 1 |
| ORD-3 | fast first files widen stale-bytecode exposure | §1 (1) | `Order` (fast `test_k` first in a rotation) |
| ORD-4 | the reuse proof pins kill-set order | not changed: a table derived from a committed T0 sweep record gives the execution order, recorded as `execution_order` beside the declared `kill_tests` with the committed table it came from (§7.2, §8); relaxing the proof is the owner's (§14) | `Order` execution-order rotations; `Classify` survivor order, malformed order, uncommitted table; `KillSets` refusals and stamp; `test_v21_execution_order` |
| ORD-5 | cross-file and cross-mutant state | §2.2, §2.3 per run (2) | `Env` case S; `Order` |
| ORD-6 | no killing file or cause recorded | §3.2, §4.2 (3) | `Classify` 4 |
| ORD-7 | target fate depends on whether an escaping file is reached | a stop, never a class; settle narrows the window (2, 3); a 60 s grace (§14 fix 5); §7.3 | `Proc` stops; §14 fix 5 |
| VS-8, FS-5, FS-6, BC-5..7, PL-8, ORD-9, ORD-10 (info) | — | VS-8 → §8; FS-5 → `MUTANT` lines and runbook; PL-8 → §2.2 | — |

## 12. Open questions for the owner

The lead decisions of 2026-10-07 on Q1–Q8 stand as recorded below, with two changes the reviews forced: Q3 is
implemented (skipped-test ids are compared, from `-v`), Q5 is resolved by a restatement (§6) instead of surfacing
survivors, and Q6 by the bracket per kill instead of a closing control per target.

- **Q1** INFRA forever for a reproducing non-assertion failure with no summary — stands. (A mutant-caused failure with a
  summary is confirmed by the bracket and is KILLED, §4.1.)
- **Q2** the 35 legacy clock-only kills (P2/P4) stay historical — stands.
- **Q3** skipped-test ids compared — implemented (§3.1). The expected-skip allowlist with reasons belongs to the new
  campaign manifest, which is not written here: T0 rows carry `skipped_tests` for it.
- **Q4** no change to the authority model — stands.
- **Q5** resolved by the semantic restatement of §6 (rebound calibrations), before commit 5, as both reviews asked.
- **Q6** resolved by the bracket (§4.1).
- **Q7** T0 replaces the original-bytes baseline — stands; the original runs only for a refused file.
- **Q8** stop the worker on any ownership failure — stands.

New, for the owner:

- **N1 (§6.3).** Eight methods in six C2-era kill files failed the null mutant of 60 V2.1 targets (14 cli_invocation
  HARNESS/*, 29 process_effect HARNESS/*, 6 process_effect module-level, 11 python_callable_v2 HARNESS/*). **Decided by
  the lead, 2026-10-07: option 2** (§6.3, grounds and measurements there); T0 now refuses none. The owner may overturn
  it: option 1 or 3 would re-open those 60 targets' kill sets.
- **N2.** The conformance ruling's re-pointed and added behaviour-test ids (§6.4) are B-03d evidence; review them
  before `v21_conformance_ruling.py --write`.
- **N3.** The bounded-release test runs on macOS only (§2.5): the rejoin mechanism was measured there; on Linux the
  anchor is a subreaper and the same toy may take another path. The rule is the same on both. So does §14's release-budget
  test.
- **N4 (§14).** FS-2: whether a `__pycache__` a run writes must be removed after every run, and by which of the three
  routes §14 lists (each needs an owner decision or a full T0 sweep first).

## 13. Review resolutions (2026-10-07)

Every issue of both reviews was checked against the code and, where it made a measurable claim, against a measurement.
"Holds" means the issue is correct; the resolution is what this contract and its implementation do.

**Evidence-validity review**

| # | Sev. | Issue | Holds? | Resolution |
|---|---|---|---|---|
| E1 | critical | A reproduced infrastructure ERROR (summary printed, exit 1) is KILLED; the closing control misses a fault that clears before it | Yes (measured: an ImportError and an OSError end in `FAILED (errors=1)`, exit 1) | The bracket per kill (§4.1): null PASS, then mutant FAIL with the same signature, right after, each clean; no closing control. `Outcome` faults and transient-fault tests |
| E2 | major | `first` was None for every subTest failure; None == None counted as reproduced | Yes (Python 3.14: `FAIL: test_b (v2.t.A.test_b) [q]`) | The signature is the whole header plus the exception class; a FAIL with no signature is INFRA (§3.1). `Outcome` summary cases |
| E3 | major | PL-7 not closed: any Residual made the row INFRA, so a helper's exit speed decided the class | Yes | RangeEscaped with the escapees gone keeps the run's outcome, the escapee named; only RangeNotEmpty is INFRA (§2.4). `Proc` short-lived escapee 3/3 |
| E4 | major | A restarted worker has a new token and runs beside the leftover that stopped the previous one | Yes | `<worker>` = sha256 of the root; `main()` sweeps the worker's token and scratch prefix before its first target and exits 3 while anything is alive (§2.4). `Proc` restarted worker |
| E5 | major | The specified tests signal processes they cannot prove they own | Yes | No test signals anything: helpers end themselves on a sentinel or a bounded lifetime; liveness is read from `ca.host_table()`; `destructive_sites.json` unchanged (§0, §2.2) |
| E6 | minor | The closing control makes class and stop depend on kill-set order | Yes | The closing control is dropped; the bracket validates each kill where it happens (§4.1) |
| E7 | minor | Re-run evidence and signal proofs could be lost; quiesce findings went on the wrong row | Yes | Settling happens at the end of each run, on that run's own row; control and re-run rows are kept whole; a row is in the record before anything can stop the target; `MUTANT` is printed after the mutant's last settle (§2.4, §3.2) |
| E8 | minor | `_quiesce`'s step order unspecified; run directory removed at contradictory times | Yes | Fixed order after every run: settle, remove the run directory (a failure is INFRA), check and rebuild the tree; the boundary names the scratch directory, so a rebuild never moves it (§2.4) |
| E9 | minor | Moving `test_calibrations_of_other_bytes_admit_nothing` drops valid run.py evidence | Yes | Commit 5b restates it bound to the bytes under test (§6.2) |
| E10 | minor | `S2.account` does not refuse an un-errored INFRA mutant | Yes (reproduced by the feasibility review's `account.py`) | Any TIMEOUT/INFRA/NOT_RUN mutant gives the target an `UNCLASSIFIED` error, which the frozen tools refuse (§4.2). `Classify` 2 asserts `S2.account` refuses even with the mutants audited |

**Feasibility, cost and compatibility review**

| # | Sev. | Issue | Holds? | Resolution |
|---|---|---|---|---|
| F1 | critical | Three more kill files count text in child scripts; T0 refuses 60 targets the identity split does not unmask | Yes, and wider: the T0 sweep (§6.1) finds 8 methods in 6 C2-era files, 60 targets; three bytecode-family methods were missed by the review | Measured exactly (§6.1). Not edited: most of these methods are valid kill evidence for the same modules' module-level targets, so a move would lose it; T0 refuses the 60 targets, fail-closed, and the options go to the owner (§6.3, N1) |
| F2 | major | The split breaks the B-03d conformance ruling generator (`missing_tests`) | Yes | Commit 5 re-points the four ROWS ids to `tests.v2.test_v21_identity_bytes`; 5b adds the restatements beside them; `tests/v2/test_v21_conformance_ruling.py` is in the gate of 5 and 5b. The rows are B-03d evidence: listed for the owner (§6.4) |
| F3 | major | PROC-OWN-1 calls `mutation._run_tests` and pins `(False, 0)` | Yes | `_run_tests(root, tests, boundary)` keeps its contract as a wrapper over `_run_file` (a TIMEOUT is not passed); PROC_OWN_1 is in every gate |
| F4 | major | subTest signatures (same as E2) | Yes | As E2 |
| F5 | major | The outcome table does not match what unittest prints for an import failure or an infra OSError | Yes | §3.1 and §3.3 state the measured behaviour; the bracket decides (E1) |
| F6 | major | No cross-platform plan: Windows needs SYSTEMROOT; Linux and macOS classify a leaking mutant differently | Yes | Windows keys kept and Windows' own HOME/TEMP pointed at the fresh directories (§2.2); RangeEscaped keeps the outcome, so the class no longer depends on whether `escaped()` saw the helper (§2.4); POSIX guards on the new process tests, a darwin guard on the one mechanism measured only there (group rejoin) |
| F7 | major | §10's numbers were guesses; the sample could not see the big cost changes | Yes | §10 reports measurements on real targets, old runner against new on the same tree, and the campaign-level consequences stated from the sweep |
| F8 | major | The split does not preserve the kill sets' evidence for run.py/bundle/bundle_cli | Yes | As E9: 5b's rebound restatement; the claim "no evidence is lost" is now made only with it |
| F9 | minor | §6.3's 16-run sample covers half the distinct nulls | Yes | The full sweep: every distinct (null, kill file) pair — 129 — through the runner's own T0 (§6.1), before the split; and again for the changed files after it |
| F10 | minor | Mtime-only changes would count as residue; the 6 longest files were never measured | Yes | Content is compared where the stat differs (§2.3); the sweep ran all 36 kill files through T0, which refuses residue |
| F11 | minor | A stop costs the whole target, not "at most the rest of one target" | Yes | The cost claim is corrected; no resume path (§4.4) |
| F12 | minor | `S2.account` refuses INFRA only through `target_problems`; field meanings shift | Yes | As E10; the shifted meanings are stated (§4.2) |
| F13 | minor | New tests add destructive call sites the ledger must record | Yes as stated | The tests make no destructive call (E5), so no row is needed; `destructive_authority --check` passes at every commit |
| F14 | minor | Record files would grow to tens of MB | Yes | Only non-PASS rows keep `tail`; every row keeps `tail_sha256` and its counts (§3.2) |
| F15 | minor | §5.4's AST equality is false for SCRIPT targets | Yes (measured) | The test compares the module with the script left out plus the parsed script (§5) |
| F16 | minor | The order test's runtime was guessed | Yes | Measured (§7.2): rotations only, and each control in one order |

## 14. The provers' open items (fix series, 2026-10-07)

Five provers re-checked commits 1–7 by lens and left the items below open or new. Each was reproduced or read against
the code before any change; each fix is its own commit with its own test in `tests/v2/test_v21_mutation_runner.py`, and
each test was also run with the old code swapped in (or the protection switched off) to show it fails there. Every
commit kept `mutation.py --check` identical to c9c736f's output (§8), `destructive_authority --check` PASS (no
destructive site added: every removal is still a `TemporaryDirectory` cleanup), and ruff clean.

| Fix | Commit | Item (lens) | Holds? | Change | Test |
|---|---|---|---|---|---|
| 1 | `ae975d4` | the stamp is not checked after a run: a kill file that rewrites the mutated module with its own bytes brings BC-1's collision back (bytecode) | Yes (prover: 3/5 false SURVIVED, no error) | the mutated file must keep `st_mtime_ns == stamp * 10**9`; any `.py` whose mtime changed is residue | `Bytecode.test_a_touched_source_is_residue_so_the_stamp_cannot_be_lost` |
| 2 | `870b132` | `../x` and `../../x` from the tree are not checked (filesystem-state) | Yes (prover: 2 false SURVIVED in both orders) | holder must hold only `tree` (else rebuild); scratch only the holder and its pristine copy (else stop) | `Env.test_what_a_run_leaves_beside_the_tree_is_residue_too` |
| 3 | `0089945` | one empty `ps` read reads as "every process gone" (process-env) | Yes | `ca._read` and `ca.carriers` raise when `ps` fails or does not list itself; the runner stops HOST_TABLE_UNREADABLE | `Proc.test_a_host_table_that_cannot_be_read_stops_instead_of_reading_as_empty` |
| 4 | `aca1280` | PL-1 (3): a helper with its own environment and no scratch path is invisible (process-env) | Yes (prover: order flipped 5/8 mutants, clean record) | new read-only `ca.cwd_under`: processes born after the boundary whose cwd is in the scratch (macOS `lsof`, Linux `/proc`); candidates only, unprovable ones stop the target | `Proc.test_a_helper_with_its_own_environment_is_found_by_its_cwd` |
| 5 | `cd4b336` | ORD-7: an escapee outliving 5 s stops the target in one order only (order-equivalence) | Yes; narrowed, not removed | `SETTLE_S` 5 s → 60 s (covers the measured 8 s and 30 s helpers; paid only while one is alive) | `Proc.test_an_escapee_that_ends_within_the_grace_does_not_make_the_order_decide` |
| 6 | `457ca93` | Residual pids taken by a regex over text the code under test controls (process-env) | Yes (prover: `max(1, 2)` → watch launchd → stop) | the list release() ends its message with, read after the exact prefix rebuilt from the range's name and ledger; another shape stops | `Proc.test_the_pids_release_names_are_read_from_its_list_not_from_command_text` |
| 7 | `012ff83` | the second release() after RangeNotEmpty gets a fresh RELEASE_WAIT_S (process-env) | Yes (prover: 129 s at the default) | the second call gets what is left of one budget | `Proc.test_one_release_budget_per_run` (macOS) |
| 8 | `269baf5` | VS-4: establish, the first tree and T0 outside the guard; main has no per-target guard (classification) | Yes; and a latent `KeyError` (a run-directory failure in a mutant's chain left a row with no outcome) | any exception in `_run_file` is a RUNNER_EXCEPTION stop with a well-formed row; run_target guards establish/tree/T0; main writes an errored entry, prints STOPPED and NOT RUN (now the targets not yet run), exits 3 | `Classify.test_a_runner_failure_outside_a_mutant_keeps_what_was_measured_and_names_what_did_not_run` |
| 9 | `8a51b33` | PL-2: a fault the control's PASS leaves for the re-run (TIME_WAIT) confirms a false kill (process-env, major) | Yes (prover: 2/2 aligned runs, clean record) | `BRACKET`: two control PASSes, then the re-run; `_confirmed` reads the same | `Outcome.test_a_fault_a_passing_run_leaves_for_the_next_is_never_a_kill` |
| 10 | `95748ea` | VS-5 in a file; VS-6 (b) a test that cannot run alone; FS-2's presence mechanism (classification, order-equivalence) | Yes, all three | `_remeasure`: an unconfirmed FAIL keeps its row as `unconfirmed`, the file runs once more, whole, on a rebuilt tree; a FAIL there is bracketed whole, each run in a new tree | `Outcome.test_an_unconfirmed_fail_is_measured_again_on_a_fresh_tree` |
| 11 | `2f8ec29` | `mutation.py t0` prints PASS for a refused kill set (order-equivalence) | Yes | no T0 row is a failure | `T0.test_the_t0_command_runs_t0_alone_and_writes_nothing` |
| 12 | `7e8e26e` | `timed_out` in execution order (order-equivalence) | Yes | sorted | `Classify.test_timed_out_does_not_depend_on_the_order` |
| 13 | `f72fb5b` | VS-6 (a): "re-run them" for mutants a re-run cannot confirm (classification) | Yes | the error says how many end with no summary and need a kill test or a ruling | `Classify.test_the_error_says_which_unclassified_mutants_a_re_run_cannot_resolve` |
| guard | `f2e0777` | a toy kill test SIGKILLs its parent without proving it is its range anchor (final verifier, minor) | Yes | `anchor_guard`: the parent is signalled only when it is a child of the test process running `range_anchor.py` and leads the toy's group and session | `Outcome.test_a_lost_report_channel_is_not_a_timeout` (and the guard's negative: a plain child gets 0) |
| ord 1 | `eec1bcf` | `run A --order T` ran A then refused; `run --order` raised IndexError; `run --order T` ran every target (final verifier, minor) | Yes | misuse and any name that is not a target are refused, with the usage, before anything runs | `KillSets.test_run_misuse_is_refused_before_anything_runs` |
| ord 2 | `4a3b31b` | a bad table entry was refused only at its target's turn, after earlier targets ran, and its NOT_RUN entry replaced the record's result (final verifier, minor) | Yes | `_order_problem`, one rule; main checks every entry before the first target | `KillSets.test_main_refuses_a_table_with_any_bad_entry_before_the_first_target_runs` |
| ord 3 | `8fc1350` | `_problems_v2` read `{}`/null as the declared order and crashed on a list or `files: null` (final verifier, minor) | Yes | the record check reads the key by `_order_problem` | `Classify.test_the_record_check_and_the_runner_agree_on_what_an_execution_order_is` |
| ord 4 | `76e0eca` | a table's provenance: nothing tied it to a measurement or to a committed file (final verifier, minor) | Yes | `validation/v2/execution_order.py` (rule, `--record`, `--write`, `--check`); `from` = record path and sha256; main's stamp with `table_commit`; `_problems_v2` refuses an uncommitted table | `test_v21_execution_order` (3); `KillSets` stamp; `Classify.test_a_result_ordered_by_a_table_that_was_not_committed_is_refused` |
| doc | this commit | the report's "16/16 failing pairs now pass" (order-equivalence) | Yes | §6.2: 16/16 identity-file pairs; the 7 C2-era pairs still fail (N1) | — |
| doc | this commit | §7.1's claim that a nondeterministic file "shows as an unconfirmed FAIL" (classification) | Yes | the residual rate stated (§7.1 step 1) | fix 10's parity case |

**Not fixed, and why:**

- **FS-2 — a `__pycache__` written during a run persists in the tree** (filesystem-state; the order-equivalence prover's
  toy8 is the same mechanism). Its classification effects in the FAIL direction are closed by fix 10 (toy8: SURVIVED x2
  in both orders), and its import effects cannot occur (the caches are of sources fix 1 proves unchanged). The cache
  itself is not removed: (a) removing it after every run needs a destructive call site whose target the closed
  authority-source set of `destructive_authority.py` cannot express (a path the runner found by walking its own tree) —
  an INV-MUTATION-AUTHORITY change for the owner; (b) `PYTHONDONTWRITEBYTECODE`/`PYTHONPYCACHEPREFIX` for every kill test
  would change what the bytecode reproducers measure (12 test files under tests/v2 read or set bytecode state) and needs a full T0 sweep before
  adoption; (c) a rebuild after every run costs 0.5–1.6 s a run (2–3× the campaign); precompiling the pristine copy
  would put `.pyc` files where kill tests assert none (`plain.rglob("*.pyc") == []`). What stays open: a test that
  passes only beside a cache an earlier run wrote. None is known.
- **ORD-4 — the reuse proof pins kill-set order** (order-equivalence). Unchanged by instruction (the reorder is a later,
  separate commit, §8): `proof()`, the Phase test and the scope manifest fail loudly on any reorder, and no reorder exists
  yet. Relaxing them changes frozen criteria — the owner's decision. Running a declared set in another order needs none
  of that (§7.2): `kill_tests` stays the declared list.
- **ORD-7's residue** — a leftover living longer than 60 s still stops the target in the orders that reach its file
  (§7.3). Removing it needs ownership taken before release() (ORD-7 (b)), an authority-model change for the owner.
- **The prover's optional extras not built:** every `.py`'s mtime is in fix 1 (built); a widened signature with the
  assertion message (PL-2, optional), pinning `PYTHONHASHSEED`, or T0 run twice to record reproducibility (VS-6
  nondeterminism, optional: T0 twice would cost hours on the 257 s file) — owner's call.

**Overhead of the fix series, measured** (2026-10-07, `heavy.sh`, the workers' `env -i`; `mutation.py run` on a
`git archive` of 671d78e and of f72fb5b, the same two named targets; `scratchpad/runner-v2/fixer/measure.sh`):

| Target | Mutants | 671d78e | f72fb5b | Runs (primary / control / re-run) | Runner s per run |
|---|---|---|---|---|---|
| `cli_invocation.py::_stream_bytes` | 7 | 16.1 s | 20.5 s | 7 / 7 → 14 / 7 | 0.27 → 0.29 |
| `process_effect.py::_flat_ok` | 3 | 15.3 s | 17.3 s | 3 / 3 → 6 / 3 | 0.27 → 0.29 |

Every mutant has the same class under both (all KILLED). The difference is the second control (fix 9): one run per
kill, about 0.6 s each here, so about +1.8 CPU-hours over ~10,900 kills; the cwd read (fix 4) adds about 0.02 s per
run; the fresh re-measure (fix 10) and the 60 s grace (fix 5) cost nothing on these targets. The runner's own test
file: 56 tests, 484 s under `heavy.sh` at 76e0eca; the `Order` class alone, 193 s (48 tests and 417 s after the fix
series; 36 tests and 252 s at commit 6).


## 15. Campaign 2's finding: a temp path in a subTest label (2026-10-10)

**What campaign 2 showed.** 31 of 12,448 mutants ended INFRA although each failed its kill test on every run and the
unmutated module passed every control: 30 in `confine.py::wrap`, 1 in `cli.py::run`. Both kill tests name a path in a
subTest label — `subTest(exe=exe)` (`test_v21_confine.py:220` at 5719f1f; line 424 at this head) and
`subTest(argv[-1])` (`test_v21_continue_integrity.py:620`) — and the path is under the run's own TMPDIR
(`<scratch>/run-<8>/tmp/tmp<8>/…`), which is new on every run. The failure header (§3.1) is the whole line, so
the bracket's re-run (and the fresh-tree re-run) never had the header of the first failure and the runner, correctly
by its rules, did not call it a kill. Three further mutants were TIMEOUT (a mutant that never terminates or waits out its
budget): a different matter. `confine.py::_survivors` is in the re-measure set; `adapters.py::_bounded` and
`bundle_cli.py::continue_from` are not (their kill files are unchanged), so they stay unresolved — and `--check` red for
them — until a kill test that fails fast instead of hanging puts them in it (the survivor work's first items).

**The change** (`signature`, `_RUNNER_DIR`, `_MKDTEMP`; used by `_confirm` and `_confirmed` and nowhere else; `_tail` maps
the same mkdtemp name; `_HEAD` is anchored to the report). The signature the bracket compares is `first` with three
kinds of NAME replaced and nothing around them touched: a run directory `run-<8>` or a tree `tree-<8>` directly under a
runner scratch directory (`aisef-mut-<worker 12 hex>-<8>/run-<8>` → `aisef-mut-…/<run#n>`), and a test's default
mkdtemp name directly under the run's TMPDIR (`<run#n>/tmp/tmp<8>` → `<run#n>/tmp/<mkdtemp#m>`). `n`, `m` count the
distinct names of a kind in order of first appearance in that header, so which names coincide survives (`src is dst`
is not `src is not dst`); the scratch name stays, so another target's or worker's directory is another name; a `<`
already in the header is doubled first, so a literal `<run#1>` is not a replaced name; text before, between and after
the names (the rest of a path, a drive letter, a parameter, a counter) and the exception class are never touched but for
that doubling. A
function of the recorded `first` alone, so the record check applies the same rule to the row as written; the record
keeps the header as the run printed it. `_outcome` (PASS, FAIL, TIMEOUT, INFRA), the controls, the second control, the
fresh re-measure and the classification are untouched: the rule only widens "same failure" from "same string" to
"same string but for the runner's own random names". Two further changes ride with it, both from the review. `_HEAD`
takes the header after the report's own `=`×70 line, so a line a test prints (or a docstring under `-v`) is no longer
taken for the first failure; one that prints the separator and a `FAIL:` line is still, and that stays open. It feeds
`_outcome` (a FAIL needs a header), so it is evidenced on the record: of the 21,613 rows that kept a header and a tail, 17,547
have the header directly after a separator line, 760 have the tail cut before it, 3,306 do not hold it, and none has it
after anything else (`header_position_in_kept_tails`); a failure whose header is not after a separator reads INFRA
(fail-closed), never a kill. And `_tail` maps the test's mkdtemp name too, so a row's `tail_sha256` of such a
failure is the same on every run (POSIX spelling; see the limits). ORD-6's byte-for-byte claim is NOT extended to `first` of such a row: it is raw by design and
differs between runs and orders (as it did); what is the same is its `signature(first)` and its `tail_sha256`, and the
class. The determinism tests compare raw `first` and pass because their toys name no temp path.

**What it cannot do, and its limits.**
- It cannot turn a failure that is not the same into a kill: another test, subtest, parameter, directory or exception
  class keeps another signature (`Signature.test_the_signature_replaces_only_the_runners_own_temp_names`), a label that
  carries a per-run counter is still INFRA (`…test_a_failure_that_differs_in_more_than_temp_names_is_still_not_a_kill`),
  and it cannot create a FAIL: a PASS, a TIMEOUT, an INFRA row or a lost summary decides as before, before the
  signature is read. A kill file whose label carries something else that changes on every run (a pid, a clock, a port)
  is not helped; it stays INFRA and is named.
- By shape alone, a fixed name under the run's TMPDIR that looks like mkdtemp's (`tmp` + 8 of `[a-z0-9_]`, e.g.
  `tmpbackup_a`) is replaced like one, and a run directory of the same scratch from an earlier run is `<run#n>` like
  this one; both only matter for a re-run that fails in a sibling subtest that differs in exactly that and nothing
  else. Not covered, and fail-closed: a second mkdtemp level, a mkdtemp name with a suffix of name characters or another
  prefix, a relative spelling, upper-cased or 8.3 Windows names — they stay INFRA.
- A kill test that fails for a reason of its own, independent of the mutant, on some runs (a flaky test whose label
  carries a temp path) could be confirmed by a bracket whose first failure and re-run are both that flake: before, the
  differing paths made it INFRA. The unmutated controls (two PASSes, then the fresh re-measure) are what stops it, as for any
  kill; the rule does not make a flake more likely to pass them. The separators of a path are not part of a name: `/`
  and `//` are one directory (`Signature.…replaces_only_the_runners_own_temp_names`).
- `tail_sha256` maps the mkdtemp name after `<run>` is substituted, which is `str(path)`: a Windows repr that spells the
  path with forward slashes (`repr(WindowsPath)`) is left alone, so on Windows a row's `tail_sha256` of such a failure can
  still differ between runs. Only the signature, which reads the header, is spelled both ways. The sentence above about
  `tail_sha256` is POSIX.
- A record written by this runner is read by this runner's `--check`. The earlier runner (and
  `campaign-2/tools/check_at_snapshot.sh` at 5719f1f) reads a KILLED entry whose re-run differs only in temp names as
  "KILLED without a confirmed kill": fail-closed, and the reason for running the re-measure's check with this runner.

**Which campaign-2 results stand.** The runner is a harness the reuse proof does not cover, so the argument is made here
and checked on the record (`campaign-2/tools/replay_signature.py`, run over the 12,448 results as written;
`campaign-2/results/SIGNATURE-REPLAY.json`):

| Class | Why the runner change cannot move it | Check on the record |
|---|---|---|
| KILLED (10,738) | its bracket was confirmed by string equality; equal strings have equal signatures | all 10,738 are confirmed under the rule (`killed_not_confirmed: []`) |
| SURVIVED (1,676) | all but 2 have no FAIL row: no bracket, no signature read. The 2 carry an unconfirmed FAIL row whose re-run PASSed — the rule does not change a PASS | 0 whose in-place bracket is confirmed under the rule: none can move |
| TIMEOUT (3), NOT_RUN (0) | decided by the outcomes before any signature is read; a TIMEOUT mutant with an unconfirmed FAIL row would be the exception | none carries a FAIL row |
| INFRA (31) | the only class the rule can change, and only toward KILLED | the in-place bracket of all 31 (controls PASS ×2, re-run FAIL) is confirmed under the rule, by signature only |

A SURVIVED or TIMEOUT mutant that carries an unconfirmed FAIL row whose in-place bracket differs only in temp names would
be KILLED when measured again; the replay shows none in campaign 2, and the claim "the rule cannot move SURVIVED" is
therefore a measurement on this record, not a property of the code. No campaign-2 result is invalidated by the change and
none is promoted by it; the class of the 31 is not rewritten — only a re-run decides — and the re-run is part of the
rev-3 measurement: both targets (`confine.py::wrap`, `cli.py::run`) are already in the re-measure set of
`campaign-2/delta/DELTA.md` because `test_v21_confine.py` changed. The delta and manifest revision 3 are re-derived at
the head that carries this change before that run.

**Tests** (`::Signature`, 5): the toy reproduces the campaign's INFRA with the rule switched off and is KILLED with it
on; a label with a per-run counter stays not-a-kill; the function's cases (what it replaces, what it keeps — text before
a path, aliasing, another directory, a lookalike, a literal placeholder, Windows spellings, non-strings, a 200 kB header
under 5 s); the record check; a printed `FAIL:` line is not the header.

## 16. Audits by position (B-03, 2026-10-11)

`AUDITED` is keyed by (target, description). A description is not an identity: the generator mutates every occurrence
of a line's literal or operator, and 125 of campaign 2's 1,676 survivors share their description with a sibling mutant
of the same target (55 of them with a sibling that was killed, the rest with another survivor). An audit by
description would excuse a sibling nobody looked at.

The V2.1 audits are therefore **positional**, in `closure-evidence/v2/v2.1/mutation/SURVIVOR-AUDITS.json`
(`mutation.AUDITS_REL`): `{"entries": [{target, index, mutant, class, source_sha256, group, grounds,
consumers_checked, exceptions_checked}]}`. An entry covers mutant `index` of `target`'s list when its description
is `mutant`, the result was measured on a module whose digest is `source_sha256`, and the mutant SURVIVED. A TIMEOUT,
an INFRA or a NOT_RUN mutant is never audited away. `class` is `EQUIVALENT` (no observable difference, proved from
the code) or `AUDITED` (it differs, and no consumer or contract the entry names depends on it); neither is a kill
and the summary keeps them apart from KILLED (`AUDITED_BY_CLASS`). Each entry names, for itself, the consumers it
checked and the exceptions it looked for; `group` shares one reasoning between mutants but never replaces those two
lists. A malformed entry, an entry audited twice, or a file that is not an object with `entries` counts for nothing
and is a problem of the V2.1 phase (`problems_of`). `NO_AUDIT` targets accept none. The V2.0 reference-model entries
of `AUDITED` are read by description as before.

The record builder (`v21_mutation_record.py`) reads the audits through a view that removes exactly the audited
positions from `survivors` before the frozen S2 accounting sees them; the record keeps every result as it was
measured. Tests: `test_v21_mutation_runner.PositionalAudits` (6).

## 17. Campaign 3's T0 sweep (B-03, 2026-10-11)

Before campaign 3 the §6.1 measurement was repeated on the tree that campaign measures: every distinct (null mutant,
kill file) pair of the 468 V2.1 targets through the runner's own T0 — **235 pairs, 29 null mutants, 133 kill files**
(`closure-evidence/v2/v2.1/campaign-3/tools/sweep.py`; record `T0-SWEEP-3.json`; table `EXECUTION-ORDER-3.json`;
account in `campaign-3/t0-sweep/README.md`). First pass at 408e1c8: 234 PASS and one FAIL, and the original bytes passed
that one: `test_v21_confine.HostGuard.test_nothing_is_copied_or_probed_outside_the_tests_directory` made its faulty
kernel copy by replacing the literal text `get_paths()["purelib"]) / probe_file`, which the module the runner writes
(`ast.unparse`: single quotes) does not contain, so the test failed on the null mutant — and, had T0 not stopped it,
would have failed on every mutant of `confine.py`, a kill of every one of them by a fault of the test. Fixed at 206bc79
(a pattern over either quote style); second pass PASS.

The rule it adds for a kill file that edits product source: match the **tokens**, never the spelling — the runner
writes every module through `ast.unparse` (quotes, line breaks, parentheses, comments and blank lines are not the
committed text), and T0 is where a file that depends on the spelling is found. The same holds for a test that
compares source text, counts lines or asserts on a line number.
