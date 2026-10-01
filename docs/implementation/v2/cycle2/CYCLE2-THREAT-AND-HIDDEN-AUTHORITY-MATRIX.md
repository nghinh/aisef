# CYCLE-2 THREAT AND HIDDEN-AUTHORITY MATRIX

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). P7-FINDING-001
was a hidden authority: the observation depended on bytecode the revision carried and on a file date's second, so two
checkouts of one revision observed different code. This matrix lists, for every proposed probe kind, every authority
that could decide a verdict besides the immutable revision, the `ProductProofSpec` and the capability identity — and the
mechanism that removes or binds it. A row with no mechanism is a design gap, not an acceptable residual.

Legend: **removed** = the authority cannot reach the verdict; **bound** = it can, and its identity enters the RunSpec
or the record so two runs are comparable only when it is equal; **declared** = it is the named weakest path of a
`PARTIAL` claim.

## 1. Matrix

| hidden authority | `cli_invocation` | `file_artifact` | `process_effect` | `python_callable` (ext.) |
|---|---|---|---|---|
| **bytecode cache** (P7-FINDING-001) | removed: `-B` + `-X pycache_prefix=<fresh per evaluation>`; the prefix dir is created empty and lies outside the checkout | removed: no interpreter runs against the revision | removed: as cli_invocation; the scenario interpreter runs under the same flags | removed (Cycle-1 correction) |
| **shell profile** (`.zshrc`, `.bashrc`, `PROFILE`) | removed: no shell; argv exec with `shell=False`; the interpreter is an absolute path | removed: git invoked by absolute path, `shell=False` | removed | removed |
| **PATH** | removed: the interpreter comes from `ExecutionEnv.interpreter` (absolute, its digest a capability); the subject's own `subprocess` use is the declared weakest path | removed: `git` resolved once at RunSpec time, its digest a capability | removed (harness); a `subprocess` step uses the same absolute interpreter | removed |
| **locale / encoding** | bound and pinned: `LC_ALL=C.UTF-8`, `LANG=C.UTF-8`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`; captured streams compared as bytes; a spec that needs another encoding declares it and the harness pins that | removed: blobs read as bytes; text grep decodes with the spec's declared encoding (default utf-8, errors → `REFUTED` with the offending file named) | pinned as cli_invocation | pinned |
| **current directory** | removed: cwd is the fresh evaluation directory; the checkout root is passed absolute; `sys.path[0]` is the harness's `-I` (no script dir) plus the revision root and `src/` added explicitly | removed: paths resolved against the tree, not cwd | removed | removed |
| **environment variables** | removed: allowlist only (`_scrubbed_env`), plus the pinned set above; `PYTHONHASHSEED=0`; nothing of `PYTHON*` from the host; recorded set hashed into `detail` | removed: git runs with `GIT_CONFIG_COUNT` pins (no maintenance, no gc) and no user config (`GIT_CONFIG_NOSYSTEM=1`, `HOME=<fresh>`) | removed as cli_invocation | removed |
| **timestamps / clock** | removed from verdicts: no probe reads the clock except for the window deadline; `ts` values in stimuli are data; captured streams are never timestamp-normalised (a spec that prints a clock value is unprovable and must not be written) | removed: the tree has no times | removed: `time.time`/`datetime.now` inside the subject are not intercepted — a scenario whose result depends on them is not deterministic and its calibration fails on the negative fixture by design | removed |
| **file metadata** (mtime, mode, owner) | removed: the workspace is written by the harness with fixed content; mtimes are never observed; modes are not observed unless a class declares them (none proposed) | removed: modes read from the tree (`100644`/`100755`) only when the spec asks (`content` class may bind `mode`); working-file modes ignored | removed as cli_invocation; `equals_before` compares bytes, never metadata | removed |
| **network** | declared: `PARTIAL`; the subject may open sockets; `FULL` only with an OS sandbox capability named in the RunSpec; the harness process itself keeps the Q5 socket guard during qualification runs | removed: no execution | declared as cli_invocation | declared |
| **process inheritance** (fds, groups, signals, stdin) | removed: `close_fds=True`, stdin from the stimulus or devnull, the owned process range's session/group/job; the controller's signal ledger is the only signal authority (§9.3) | n/a | removed; a `subprocess` step is a child of the harness inside the same range | removed |
| **tool version** (interpreter, git, OS libs) | bound: interpreter digest and version, git digest and version are RunSpec capabilities; `runspec_hash` differs when they differ; comparability requires equality (§23) | bound: git digest | bound: interpreter digest | bound |
| **OS differences** (path separators, CRLF, case folding, `os.replace` semantics, signals, job objects) | bound and normalised: paths recorded in POSIX form; text files written with the spec's `newline`; streams compared as bytes; exit statuses recorded as CPython reports them per platform; the platform enters the record and Q5 binds it; Windows uses the job-object backend of the process range | removed: the tree is platform-free; case-collision paths are refused at admission | bound as cli_invocation; `os.replace` atomicity is the subject's, observed by the file class on both platforms in Q3 | bound |
| **previous execution residue** (temp files, leftover processes, stale workspaces) | removed: a fresh evaluation directory per evaluation, released by its handle; a residual is the range's `Residual`, never reused; the workspace name carries the nonce | n/a | removed | removed |
| **developer test layout** (ARCH-LESSON-001) | removed: the probe never names or discovers a test; Q1's test-layout invariance is extended to the new kinds (the same spec under every layout gives the same verdict) | removed | removed | removed |
| **checkout metadata** (git index, worktree state, autocrlf) | removed: cli_invocation runs code from the checkout files, so `-B` and the fresh prefix make the *source* the only input; the verifier's independent checkout (P6) stays the second witness | removed: object store, not checkout | removed as cli_invocation | removed |
| **ambient proxies / provider variables** | removed: not in the allowlist; a subject that reads them sees none | n/a | removed | removed |
| **the recording (Q5)** | removed: never replayed; the probe is re-executed in Q5 and compared to the expectation | removed | removed | removed |

## 2. Threats specific to the scenario probe (`process_effect`)

| threat | mechanism |
|---|---|
| a `fault` step leaks past its `call` and decides a later step | the patch is installed by a context manager around exactly one call; the harness asserts the original attribute is restored before the next step, else `HARNESS_FAILED` |
| the subject caches state between steps in module globals | intended: the scenario models one process's life; a criterion that needs a fresh process uses `subprocess` or a second `construct` — and the harness refuses a second `construct` unless the class declares it (`allow_reconstruct`) so the author states it |
| a step's result is unserialisable and silently compared as `None` | `returned_unserializable` is a distinct fact; equality against a JSON expectation is `REFUTED`, and the class says so in `detail` |
| the workspace path leaks into the verdict (an observable that compares an absolute path) | placeholders are re-applied on the way out: any occurrence of the evaluation directory in a returned value is replaced by `<ws>` before comparison |
| a scenario reads the repository outside the workspace | the subject may; `PARTIAL` declares it; Q3 injects a scenario that does and shows the record names the path |

## 3. Threats specific to `file_artifact`

| threat | mechanism |
|---|---|
| the working tree differs from the committed tree (dirty checkout, autocrlf) | content and existence come from the object store at the revision SHA; the checkout path in `RevisionRef` is used only to locate the repository |
| a symlink in the tree points outside | `git ls-tree` mode `120000` entries are refused for content classes (`HARNESS_FAILED` with the entry named) |
| a regex that matches across lines or is catastrophic | regex compiled with a bounded pattern length and evaluated per line with a per-file size cap; a cap exceeded is `HARNESS_FAILED`, not a verdict |

## 4. What the matrix proves for the core invariants

- **Semantic determinism / Reproducible qualification.** Every row is removed, bound or declared; nothing is "usually
  stable". A verdict is a function of (revision SHA, `ProductProofSpec`, capability identities) because every other
  input is either absent from the evaluation or part of the identity.
- **Independent evidence.** The verifier's separate checkout (P6) remains a second witness for every kind; a kind that
  reads the object store makes the two witnesses read the same bytes by construction.
- **Memory is context, never evidence.** No probe reads a previous evaluation, a cache or a recording.
- **No developer artefact executed at parent.** Admission at the parent runs the same probes over the parent revision;
  the workspace and pre-steps are contract content, never developer files; test files are refused by the contract rule.
- **No prose as control state.** Every observable is a typed shape (exact bytes, a digest, a regex declared by the
  author, a count, an exception name with attributes); `detail` is never read.
