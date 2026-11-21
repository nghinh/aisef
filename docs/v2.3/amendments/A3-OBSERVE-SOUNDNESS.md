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
([`R2S-REPOSITORY-EFFECT.json`](../evidence/f5-observe/R2S-REPOSITORY-EFFECT.json)):
667 INVALIDATED (R2) / 17,322 mutants, 327 UNRESOLVED (I6) / 10,078, 0 VERIFIED_REUSE — the same states and totals as
disposition 2. The component moved from R6 to R2: the impact tests left `tests/v2` (A2), so Δ holds no `.py`, and R2S
fires before R1. Δ is 9 evidence files added under `closure-evidence/v2` since v2.2.0; `tests/v2/test_p9_reproduction.py`
holds the constant `"closure-evidence/v2"` and lies in every S(F) (registry's `TESTS_V2`).

**Cost, stated plainly:** against the v2.2.0 basis, while those 9 files are in Δ, R2S keeps every target that passes
I6 INVALIDATED even with complete, admissible observations. Narrowing it (for example, judging only constants of
code F's processes can execute) is the same question Amendment A1 failed on (mutant-only execution of literal-named
files) and needs its own amendment and soundness argument; none is made here. New evidence goes to
`docs/v2.3/evidence/` (A2 as corrected 2026-11-22), outside COPY, so it does not add to Δ.

## Review 1 (2026-11-22)

*One bounded, fail-closed fix pass over the review of 2026-11-21 (13 CONFIRMED findings, A3-SND-8 reproduced by its
verifier, 10 LOW). The owner ruling is unchanged: the recorder is a development tool, not a VERIFIED_REUSE authority,
and nothing here is wired into `mutation.py check()` or any gate. Every change below can only turn a reuse into a
non-reuse (or a record into a refused one). Each finding has a regression test in `tests/v23/test_v23_review1.py`
(and, where an existing test changed, the reason is given there); every one of those tests was run against the
`8a31f7c8` recorder and engine and fails there (21 tests: 32 failures and 4 errors, every test and every subtest
red), and passes here (`tests/v23`: 110 tests, darwin/audit; Linux/strace in the report of this pass).*

### Confirmed findings

| Finding | What changed | Test | Residual |
|---|---|---|---|
| A3-SND-1 (HIGH) namespace package invisible | R5 judges a directory under COPY that exists (holds a file) at only one of basis and head like an added/removed module file: INVALIDATED when S(F), or what F ran, imports its dotted name. Static, before any observation, both backends; appearance and vanishing. | `test_snd1_a_namespace_package_that_appears_or_vanishes` | A directory reached by a computed import name is R8's (below). A directory decided by a C-level stat in a hooked process and imported by no name is still the C6 discount. |
| A3-SND-2 (HIGH) R8 gated on changed defs | With Δ ≠ ∅, any open R8 site (not in RESOLVED_SITES) in what F ran is INVALIDATED R8, whether or not a Δ `.py` of S(F) changed defs and whether or not Δ holds a `.py`. C9's assumption ("a mutant runs only code of S(F)") now holds by refusal, and C10 covers mutant-only loads. | `test_snd2_a_computed_import_only_a_mutant_takes` (B, B2) | **Cost:** every repository S(F) holds registry.py's `import_module` sites, so no repository target can be reused on an observation while RESOLVED_SITES is empty. `test_n13_comment` now expects R8 for the toy's `dyn.py` target. |
| A3-SND-3 (HIGH) R2S anchors only the naming file's ancestors | R2S matches the literal text of every path construction, after any non-literal anchor (`Path(m.__file__).parent`, a parameter, ROOT), against every Δ path that holds it as whole components at any depth (case-folded): `data/one.txt` names `aisef2/data/one.txt`; a computed construction's literal directory names every path under it. | `test_snd3_a_literal_path_anchored_at_another_modules_file` | A path with no literal part (C9's residual) is unchanged. Precision: a one-component literal (`"x.json"`) names every Δ path with that component. `test_1` of the owner negatives now hides its file name with `''.join`, which the static rule cannot read. |
| A3-SND-4 (HIGH) load_tests taken for unittest's walk | `_own`: a call is the walk's only when it is made by `importlib`'s `_fill_cache` or by `unittest/loader.py`'s `_find_tests`/`_find_test_path` themselves, or through stdlib path helpers only (`genericpath`, `posixpath`, `ntpath`, frozen or not); any other frame in between (tree code: a `load_tests`, a test) makes it a run (`l run`, `s`). Those stdlib frames must lie outside the tree. | `test_snd4_the_kill_files_own_load_tests_is_not_unittests_walk` (L, S) | A `load_tests` that calls `loader.discover()` itself has that walk dropped as the walk's; what it loads is still recorded (D2) and Δ `.py` files of S(F) are R5/R6's. |
| A3-SND-5 (MEDIUM) a `__pycache__`-only directory passes C1 | The recorder refuses a runner tree (the `_pristine` copy) holding any directory that no file of HEAD under COPY implies (an empty directory, or one with only an ignored `__pycache__`). Also closes PROV-6's recorder half. | `test_snd5_a_directory_head_does_not_have_is_refused_by_the_recorder` | `impact._dirty` and the runner's own measurements still do not see such directories (pre-existing runner behaviour, PROV-6); changing that would make `classify` UNRESOLVED on such checkouts and is left to the owner. |
| A3-SND-6 (MEDIUM) annotated/other bindings | Every single-name binding of a literal path is substituted: `=` (each target; a tuple unpacked pairwise), annotated assignment, walrus (a walrus inside a construction stands for its value). A literal path bound any other way (an attribute, several targets, `+=`) counts as a construction text when it is a construction or a constant of two or more components. | `test_snd6_annotated_walrus_and_unpacked_bindings` | A one-component constant bound to an attribute, a dict or a parameter and used later. |
| A3-SND-7 / STR-1 (MEDIUM) strace discount survives execve | strace events carry their segment (the part of a task one image ran; a successful exec starts the next). The import-system discount and the hook reconciliation apply only to a segment whose image ran the hook: before any exec, a forked child with an `F` record; after exactly one exec, an interpreter start `S`; a thread follows its leader's last image. Every other segment is observed for data only. | `test_snd7_str1_an_image_exec_d_in_a_hooked_pid_is_observed_for_data_only` | After two or more execs in one task no segment is discounted (precision only). In a hooked image the discount still covers a C-level stat of a directory or of its own loaded code (C6). |
| BOTH-1 (MEDIUM) chdir / directory opens / statvfs / pathconf | strace: `chdir` (done or failed) and every `O_DIRECTORY` open (done or failed) are lookups, never discounted. audit: the `os.chdir` audit event, a `subprocess.Popen` `cwd`, and wrapped `os.statvfs`/`os.pathconf` are lookups. | `test_both1_chdir_directory_opens_statvfs_and_pathconf_are_lookups` | `DirEntry.stat` and C-level calls under audit (C5's residual). |
| AUD-1 (MEDIUM) launch accounting netted | `_posixsubprocess.fork_exec` is a launch (not counted twice for `subprocess.Popen`); `_isolated` reads the values of `-W`, `-X`, `--check-hash-based-pycs`; each `S` record carries `sys.orig_argv[1:]`; records are matched to launches by identity (`observe._accounting`): a record to a hooked launch in its parent's record (an exec: in its own pid's) with the same argv, a fork child to a fork; surplus and deficit are counted separately, never netted. | `test_aud1_launch_accounting_by_identity` (fork_exec, `-W` value), `test_aud1_accounting_unit` | A launched program that reads the tree and then execs an interpreter in place with the same argv tail is taken for that interpreter (audit only; strace traces it). A child whose parent died first, or a `preexec_fn` fork record, is refused (precision only). |
| A3-SND-8 (MEDIUM) aliases and a fake python (audit) | (C) R2's data/opened sets, the kind check and R3's listed directories compare case- and NFKC-folded paths. (S) A new name made for a tree path — `os.symlink`/`os.link` (hook `a` lines), `symlink`/`link` syscalls (strace), any path through `/proc/<pid>/cwd`, `/proc/<pid>/root` or an fd directory — is the completeness counter `aliases`: R1. (D) identity accounting (AUD-1): the shell named `python-sh` is a launch with no record of its own pid, and its hooked grandchild no launch of its parent's. | `test_snd8_reads_through_another_name_or_a_fake_python` | Alias targets are judged lexically (a link made through a symlinked directory is resolved by text). C5 as written in the claims above is replaced by: "a launch is accounted for only by a record of the launched pid (or, for an exec, of the same pid) with the same argv". |
| PROV-1 (MEDIUM) observation reuse labelled v2.2.0-accepted | A reuse that needed an observation (Δ ≠ ∅) carries basis `observation:<sha256 of the observation digests>@<basis sha>` and `evidence.authority` = none (owner ruling 2026-11-21); `report()` says the same (`observation_authority`). A reuse with Δ = ∅ keeps its label. | `test_prov1_an_observation_based_reuse_carries_no_acceptance_basis`; `test_f3`, `test_n2`, `test_d2` updated | — |
| PROV-2 (MEDIUM) the hook that ran is not bound | The witness holds the hook every observed process imported (`sitecustomize.py`); the manifest names its events directory, the tree's spellings and the nonce; `verify()` recomputes the hook with the engine's own `HOOK` and refuses (R0) any byte difference. Recorder variants in the tests now need an explicit test-only bypass (`state(..., hook=)`). | `test_prov2_the_hook_that_ran_is_bound` | The engine's own code, in memory, is trusted (F1). A same-uid run can still rewrite its witness (PROV-5). |
| PROV-3 (MEDIUM) a child's record passed for the root | The root is the one `S` record whose pid is the pid the runner launched (`ProcessRange.target_pid`, now in the manifest row; audit), or the single top task's `S` record (strace); else `missing_trace_files`. New completeness counters: `kill_file_unseen` (F's own code is not in `loaded`) and `tests_unparsed` (no parsed test, or fewer than ran). | `test_prov3_the_root_record_is_identified` | — |

### LOW findings

| Finding | Disposition | Test |
|---|---|---|
| A3-SND-9 mode-only change dropped from Δ | FIXED: D1 reads `git diff --raw`; a mode change is in Δ (the runner's copy keeps modes). The tree digest still ignores modes (residual: C1 binds bytes, not modes). | `test_snd9_a_mode_change_is_in_delta` |
| AUD-2 posix_spawn file actions | FIXED: `os.posix_spawn`/`posix_spawnp` are wrapped; each `POSIX_SPAWN_OPEN` path is a data read. | `test_aud2_posix_spawn_file_actions` |
| STR-2 chained relative chdirs | FIXED: the cwd closure is iterated to a fixpoint (beyond 4096 candidates: `cwd_unresolved`, R1). Residual: the strace version is not bound (R0 does not compare `tools.strace`). | `test_str2_chained_relative_chdirs` |
| STR-3 a tree path through another name | FIXED: the `aliases` counter (A3-SND-8). | `test_str3_a_tree_path_through_another_name` |
| STR-4 calls outside the traced channel | FIXED in part: `io_uring_setup`, `pidfd_getfd`, `process_vm_readv` are traced and any occurrence is `unobservable_calls` (R1). Residual: `recvmsg` with `SCM_RIGHTS`. | `test_str4_calls_outside_the_traced_channel` |
| STR-5 listing de-duplication by fd number | FIXED: a done open that returns an fd number resets that number's listing state. Residual: an fd number reused through `dup`/`fcntl` (not traced). | `test_str5_a_reused_fd_number_is_a_new_listing` |
| PROV-4 forgery is cheap; impossible combinations admitted | FIXED in part: a strace record must have been taken with this recorder's syscall set (`tools.strace_events`, R0); F must be in `loaded` (PROV-3). Residual (C2, unchanged): a consistent forgery, including a strace claim on a non-Linux host, is not detected; observations need an attested, isolated recorder before they could ever be an authority. | `test_prov4_the_trace_set_is_bound` |
| PROV-5 the run can silence its hook / reach its witness | RESIDUAL, declared here as an addition to "cannot prove" #4: the observed code runs with the recorder's uid; it can set the hook's busy flag (audit: events lost silently) and write its own witness files before `finish()`. | — |
| PROV-6 `__pycache__`-only directory | FIXED in the recorder (A3-SND-5); the runner/engine half is a residual (above). | (A3-SND-5) |
| PROV-7 F1: head's harness runs in the judging process | RESIDUAL (F1 stays open): head's `mutation.py` can still switch rules off in process. | — |

### Changed claims, plainly

* C5 (audit): "accounted for" now means matched by identity (pid, parent pid, argv), not by count; the root is the
  runner's launched pid. A non-Python child started by `_posixsubprocess.fork_exec` is a launch.
* C6/C7: the discount needs an image that ran the hook (strace segments); the walk is recognised only when no tree
  frame stands between it and the call; `chdir` and directory opens are never discounted.
* C8: paths are compared folded; a new name for a tree path is an incompleteness, not a read under another name.
* C9/C10: construction texts match at any depth; with Δ ≠ ∅ any open R8 site refuses tier S.
* C1: the recorder refuses a runner tree with a directory HEAD does not imply; the hook that ran is bound (R0).
* Reuse on an observation never carries an acceptance basis.

Not measured in this pass: the engine on the repository (the states without observations cannot become reuse — R1
and the static rules only grew — but components may move from R2/R6 to R5 or R2 for other reasons); an observation of
any repository kill file.
