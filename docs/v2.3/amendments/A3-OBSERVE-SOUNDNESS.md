# Amendment A3 — the F5 recorder (`validation/v23/observe.py`) and what an observation may decide (2026-11-21)

*A new file under the freeze rule of W1-DESIGN.md (line 3). It implements §2.9 D3 (the recorder) and binds it into
R0/R1 of `validation/v23/impact.py`. Owner ruling 2026-11-21: the recorder is **approved for development, not as a
VERIFIED_REUSE authority**. Nothing here is read by `validation/v2/mutation.py` `check()` or by any release gate;
impact.py reads an observation only as an input (`--observations DIR`).*

## What was built

* `observe.py --kill-file F --out DIR [--backend auto|strace|audit]`: one unmutated run of one kill file by HEAD's
  own committed runner (`mutation.py` of the HEAD commit, loaded with `v21_snapshot_delta.Rev`): its `_pristine` (so
  `tree_sha256` is that function's digest), `_new_tree` and `_run_file` (argv, environment allowlist, ProcessRange,
  judgement, cleanup through `cleanup_authority`). Additions to the kill test's environment: `PYTHONPATH` naming a
  directory outside the tree with the hook's `sitecustomize.py`, and the marker `AISEF_OBSERVE=<nonce>`.
* Backends: **strace** (Linux: `strace -f -ff -y -s 8192 -e trace=%file,%process,?getdents,getdents64,fchdir`, one file
  per task) with the hook as the tagging layer; **audit** (any POSIX host, the only one on darwin): the hook alone.
* The witness (scratch only: it holds host paths): `manifest.json`, `log.txt`, `hook/*.ev`, `strace/tr.*`. The record
  `observation.json` = `derive(witness)` (a pure function) + the sha256 of every witness file; it holds tree-relative
  paths, digests and versions only.
* impact.py: `observe.verify()` (re-hash, re-derive), the R0 binding below, every incompleteness counter into R1, the
  observed R2 extended to existence, and a static R2 (`R2S`) that fires before any observation.

## Soundness claims

Each claim lists its assumptions and the exact condition under which the engine refuses. "Refuses" means the target
gets that state; it is never reused.

**C1 — An admissible O(F) is one run of head's F by head's runner on head's runner tree.**
Assumptions: the recorder refuses a checkout that differs from HEAD inside the runner's COPY (`impact._dirty`:
tracked changes, untracked and ignored files); the tree digest is `mutation._pristine`'s rule (sha256 over
(path, sha256 of bytes), the runner's records and `__pycache__` left out, pathlib's part order), which the engine
recomputes from git (`impact.tree_digest`); the runner is HEAD's committed `mutation.py`.
Refusal: R0 UNRESOLVED when `commit` ≠ head; `kill_file.path` ≠ F or its sha256 ≠ head's blob; `tree_sha256` ≠ the
recomputed digest, or the digest cannot be computed (a symlink or a submodule under COPY: `None`); `runner_sha256` ≠
head's `validation/v2/mutation.py` blob; `observe_sha256` ≠ head's `validation/v23/observe.py` blob or ≠ the recorder
module the engine itself loaded (it re-derives with it); `outcome` ≠ PASS. Closes the binding half of residual F4.

**C2 — The record is what its witness says.**
Assumption: the witness was not replaced as a whole by a consistent forgery (manifest, traces and record rewritten
together); there is no signature (as for I7, the proof is "equals what was given", not "who measured it").
Refusal: a witness file missing, changed (a truncated file is a changed file) or added after recording → R1
INVALIDATED ("what it held is not known"); a record that differs from `derive()` of its intact witness → R0
UNRESOLVED; no witness → R0; two records of one kill file in one directory → both refused (R0).

**C3 — It is admissible only for an entry measured where it was observed.**
Assumptions: the entry's own traceback frames are the measuring interpreter's (§2.4.3): flavor from R-flavor/W, the
interpreter minor from `/python3.N/` (or `\Python3NN\`) frames (`impact.python_of`).
Refusal (R0): O's family ≠ the claim; the entry's flavor unproven (posix claim); O's flavor ≠ the entry's; the entry's
interpreter unproven; O's python minor ≠ the entry's, or O's implementation is not CPython; O's environment names are
not exactly the runner's (`_FRESH`, `TOKEN`, `PYTHONPATH`, `AISEF_OBSERVE`, plus only `ENV_KEEP` names); a process
read the checkout outside the run's tree. The engine's own interpreter is no longer compared: the observed run, not
the judging process, must match the measurement.

**C4 — strace backend: every task of the run is traced.**
Assumptions: ptrace reports every syscall of every traced task, and `-f` follows fork, vfork, clone and clone3; every
file access of interest goes through the traced set (%file, %process, getdents(64), fchdir).
Refusal (R1 INVALIDATED): a clone/fork/vfork result with no trace file (`untraced_children`, `missing_trace_files`);
more than one trace file no traced task created (`unaccounted_processes`); a hooked process the trace never shows; a
trace file without its `+++` line (`truncated_trace_files`); a cut string (`truncated_strings`); an unparsed line; an
fd with no decoded path (`fd_relative`); a non-zero tracer exit; a `strace:` line in the output (`tracer_errors`).

**C5 — audit backend: every process that runs tree code is hooked, and accounted for.**
Assumptions: every Python process that runs tree code loads the hook (the marker and `PYTHONPATH` reach it, no
`-I`/`-E`/`-S`); every file access in a hooked process raises an audit event (open, os.listdir/scandir, exec,
compile, import, launches, path-changing os/shutil events) or goes through a wrapped `os.stat`/`lstat`/`access`/
`readlink`/`open` (dir_fd).
Refusal (R1 INVALIDATED): a non-Python child, or a Python child the launch predicts unhooked (`untraced_children`);
hooked launches + forks ≠ the hook records (`unaccounted_processes`); no record of the kill file's own process
(`missing_trace_files`); a record without normal exit (`unterminated_processes`: its last lost count is unknown);
lost or unparsed lines; an fd-relative access (`fd_relative`); and, as frozen, any `R1_UNSEEN` word in S(F) without
`os_trace` (`os.readlink` is in every repository closure, so on the repository the audit backend is never sufficient
for Δ ≠ ∅).

**C6 — Absence of an event is not proof of absence: the trace is the ground truth.**
Under strace, per process and per tree-relative path, an open, lookup or listing the trace shows more often than the
hook accounts for is a data read (a listing is attributed to `<native>`, never discounted); a symlink's target
reached through another name is a data read; a process with no hook record is observed for data only.
Assumption (the one discount): in a hooked process, a lookup the hook did not make, of a directory or of code that
process loaded, is the import system's own (`_path_stat`, `path_stats`), which decides only module resolution (R5,
static) and reads code that I1/I2/R6/R7/R8 judge. Residual: a C extension's stat of such a path is discounted with it.

**C7 — The interpreter's own walk to find code is not a read of F.**
Listings and lookups made under `importlib`'s `_fill_cache`, or by unittest's `_find_tests`/`_find_test_path` under
`_do_discovery` before `runTests`, are recorded as the walk's (`l own`, `w`), matched against the trace and dropped.
Assumption: the walk decides only which file is found by name; R4 (the discovery set) and R5 (resolution) judge
that statically, and every file the run then loads is recorded. Residual: the walk is recognised by frame names; code
of the tree that names its functions so is taken for the walk (the R8-SPELLINGS class).

**C8 — A data read decides on bytes and on existence.**
Refusal (R2 INVALIDATED): f ∈ Δ read as data (opened as data, looked up, executed as a program, or opened `load`
when it is not a `.py`); f opened and now removed; any data path whose kind in the runner tree (file / directory /
absent) differs between basis and head (a directory that appeared or vanished, a missing path that now exists).
R3 is unchanged (a Δ file under a listed directory, the registry discount reused). Residual: a directory's metadata
beyond existence and kind (mtime, size, link count) is not judged.

**C9 — An observed read set alone never yields reuse (the static boundary).**
Every rule over S(F) still applies before and besides the observation: I4, R4, R5, R6 and R8/R7 over Δ ∩ S(F) (the
frozen letter, A1 withdrawn), and **R2S**: a Δ path that a file of S(F) names by a literal path — string constants
only (docstrings and comments aside): one constant, consecutive constants joined as a path, a parent directory and its
name, a listed directory, a directory constant — or reaches by a computed path whose literal part is a directory
(`/`, `+`, `os.path.join`, `Path(...)`, `joinpath`, f-strings; one level of names bound to such a directory) →
INVALIDATED, before any observation. This is what judges a mutant's branch: the observation saw only the unmutated run.
Assumption: a mutant runs only code of S(F) (the target is in S(F); a computed-name import or loader is an R8 site).
Residual: a path with no literal directory part (`ROOT / name`, a parameter, an environment value, `%`-formatting,
`str.format`, `"/".join`, two or more levels of names) read only on a mutant's branch is judged by nothing.

**C10 — Dynamic loads cannot hide outside S(F).**
Refusal (D2 UNRESOLVED): a file O(F) saw loaded (an `exec`/`compile`/`import` event of its code) or opened as `.py`
that S(F) does not hold.

**C11 — Fail closed.** R0 and D2 refuse with UNRESOLVED; R1, R2, R2S and R3 with INVALIDATED. With no observation, R1
fires for any Δ ≠ ∅, as before. The recorder adds no state and no allowlist; every rule above can only turn a reuse
into a non-reuse. Each of the owner's nine cases in tests/v23/test_v23_observe.py also shows the reuse that a recorder
or engine variant lacking the guard would have given (red-before).

## What observation cannot prove (plainly)

1. **What a mutant does.** One run of the unmutated tree: a read, listing, child or load that only a mutant makes is
   never observed. Only C9's static boundary judges it, and only for literal or literal-anchored paths.
2. **That the run is repeatable.** Another run may read other files (time, randomness, scheduling, environment
   values, host state, network). The record is evidence about the run it witnessed.
3. **Who recorded it.** Integrity is relative to the witness given (C2); a consistent whole-bundle forgery is not
   detected. The raw witness stays in scratch (host paths), so a committed summary is a report, never an admissible
   input: without its witness, R0/R1 refuse it.
4. **Accesses outside the observable channel.** strace: io_uring, file descriptors inherited from before the run, a
   process that escapes ptrace (a setuid exec, a tracer of its own), a daemon started before the run that reads the
   tree for it. audit: C-level reads in hooked processes (extension modules, `posix.*` called directly), `from os
   import stat` bound before the hook, `DirEntry.stat`.
5. **That the environment's values match the measurement's.** Names are bound; values (PATH, LANG, …) are recorded
   as sha256 only, because legacy entries record none.
6. **Kills on another flavor.** C3 binds the flavor; it does not make a flavor-specific kill flavor-independent
   (§2.7 limitation 5).
7. **That the engine and the recorder are right.** Their code at head is trusted (residual F1): R0 binds an
   observation to head's recorder, not to a reviewed one.

## Residuals carried (from "A1 WITHDRAWN")

* F1 — open: harness, engine and recorder code run inside the judging process and are trusted.
* F4 — the binding half is closed by C1 (tree, kill file, runner, recorder, witness). The observation's digest is
  carried in each state's `evidence.observation`; it is not bound to a committed row, because the witness may not be
  committed (owner rule: raw traces stay in scratch).
* NIT-GITRC, R8-SPELLINGS, T2, T3 — not addressed in this increment.

## Precision (no reuse is claimed)

No observation of a repository kill file has been recorded in this increment. R2S can only add INVALIDATED states.

Measured on the repository at `75080a80` against the v2.2.0 basis, with no observation
([`R2S-REPOSITORY-EFFECT.json`](../../../closure-evidence/v2.3/f5-observe/R2S-REPOSITORY-EFFECT.json)):
667 INVALIDATED (R2) / 17,322 mutants, 327 UNRESOLVED (I6) / 10,078, 0 VERIFIED_REUSE — the same states and totals as
disposition 2. The component moved from R6 to R2: the impact tests left `tests/v2` (A2), so Δ holds no `.py`, and R2S
fires before R1. Δ is 9 evidence files added under `closure-evidence/v2` since v2.2.0; `tests/v2/test_p9_reproduction.py`
holds the constant `"closure-evidence/v2"` and lies in every S(F) (registry's `TESTS_V2`).

**Cost, stated plainly:** against the v2.2.0 basis, while those 9 files are in Δ, R2S keeps every target that passes
I6 INVALIDATED even with complete, admissible observations. Narrowing it (for example, judging only constants of
code F's processes can execute) is the same question Amendment A1 failed on (mutant-only execution of literal-named
files) and needs its own amendment and soundness argument; none is made here. New evidence goes to
`closure-evidence/v2.3/` (A2), outside COPY, so it does not add to Δ.
