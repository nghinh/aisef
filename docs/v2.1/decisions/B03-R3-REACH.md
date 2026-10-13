# B-03 round 3, WP reach — which changed functions does each kill file execute?

Status: tool built, controls pass, mini run on 5 real kill files done. The full set has NOT been run (the lead does that
when the T0 sweep ends). Nothing here changes a product file or a record.

## 1. The owner's decision (2026-10-12, item 6, verbatim)

> Nếu cần đo lại khoảng 235 target để đáp ứng quy tắc hiện có, được thực hiện trong B-03; gom cùng các thay đổi khác
> thành một snapshot để tránh đo lại nhiều đợt. Nếu tái sử dụng được kết quả nào, phải có căn cứ phụ thuộc cụ thể.
> Không nới quy tắc để tránh chi phí đo.

## 2. Reading

A result measured at an earlier snapshot may be kept for a target only on a *specific dependency basis*. The read-set
(`validation/v21/read_set.py`) answers "which files does this kill file open"; every kill file opens
`aisef2/runtime/process_range.py`, and importing a module is not executing a function of it. The basis needed is the
changed functions each kill file **executes**. The rule is not loosened: a target whose kill files execute a changed
function is re-measured; the tool only makes the other case provable.

## 3. What was built

`validation/v21/reach.py` (outside `mutation.COPY`: never a target, and adding it moves no measured tree) and
`validation/v21/test_reach.py` (hand-run `unittest`, never imported by the suite).

```
reach.py --out R.json (--base SHA [--head SHA] | --watch W.json) [--files F...] [--plain] [--control [a..k]]
```

* **Watch list** — `git diff --no-renames base head` over `aisef2/**.py` and `validation/v2/cleanup_authority.py`:
  every function by (file, `co_qualname`-style name) that is new or whose *own* code (decorators, arguments, body; a
  nested def only by what the enclosing code evaluates at the def) differs. Each name carries its kind: `new`,
  `changed`, `docstring`. At HEAD `bcb2cfa`/`beed5a3` against `b5c2457` (campaign 4's snapshot; `3dc827be` gives the same
  diffstat): **51 names in 10 files**.
* **Module-level statements** are not functions. Each watched file's `<module>` code is watched too and recorded as
  `loaded`; `modules[file]` says whether the statements that run at import are `new/changed/docstring/unchanged`, and
  `diff.files[file].module_statements` names them by kind and line. `module_statements_executed` = `loaded` without
  the `unchanged` files.
* **Recorder** — the runner's own `mutation._run_file` (argv, env allowlist, ProcessRange, judgement, leftovers
  settled through `cleanup_authority`) on a fresh copy of its tree, plus PYTHONPATH naming a `sitecustomize.py` (the
  mechanism of `read_set.py`). In each hooked process a `sys.monitoring` PY_START callback returns DISABLE for every
  code object that is not watched, and for a watched one writes one line to the process's own file at the first hit
  (`os.write`, so a SIGKILL after the call has recorded it), then also DISABLEs. Python 3.12+; refused earlier.
* **Output** — `executed`, `executed_in_children`, `executed_from_copy_only`, `other_version`, `loaded`,
  `module_statements_executed`, `outcome`, `seconds`, `processes`, `children {hooked, unhooked_python, other}`,
  `unhooked_python_argv`; a kill file that does not PASS, or whose own import was not seen (the witness), is under
  `not_passed`, `complete` is false and the exit status is 1.

## 4. Design, and what was rejected

| Choice | Why | Rejected |
|---|---|---|
| `sys.monitoring` PY_START + DISABLE | per code object once; measured overhead 19.61 s plain vs 20.11 s hooked on the most process-heavy file (+2.5 %, one pair) | `settrace`/`setprofile` (every call, replaced by any test that traces); `coverage` (line level, third party); instrumenting the tree's source (changes the bytes tests hash and read) |
| open/append/close per hit, no held descriptor | a test that counts or closes descriptors (`closerange`) must not see or lose the recorder (control k; a persistent-fd variant fails it) | one fd held from registration |
| function granularity by `co_qualname` from the AST of both versions | the interpreter's own name; control h checks the AST-derived names against the compiler's | file level (= the read-set) |
| docstring/constant differences count, with a `docstring` kind | a mistake must only ever cost a re-measurement; the kind lets the lead see how many are docstring-only | silently ignoring them |
| fork child re-registers and `restart_events()` | the parent's first hit disabled the event for the child too (control i; the variant without it fails) | one record per process tree |
| a copy of a watched file outside the tree is matched by name, path tail and bytes | `test_v21_confine.py` copies `aisef2` into a venv and runs it there; a path-only recorder cannot see that (control j; path-only and name-only variants fail it) | path-only matching |
| the kill file's own `<module>` is watched as a witness | a PASS whose own import was not seen means the hook never ran: nothing measured | trusting an empty record |

## 5. Requirement → test

| Requirement (WP) | Where it is shown |
|---|---|
| (a) a watched function called ⇒ recorded | control a (`--control`, `Recorder.test_every_control_is_as_expected`) |
| (b) module imported, nothing called ⇒ NOT recorded (the distinction the read-set cannot make) | control b: `executed == []`, `loaded == [toy]` |
| (c) called only in a child that inherits PYTHONPATH ⇒ recorded | control c |
| (d) called in a child with its own `env=` ⇒ NOT recorded, child counted `unhooked_python` | control d: `(0 hooked, 1 unhooked)` |
| (e) from a thread ⇒ recorded | control e |
| (f) SIGKILLed right after the call ⇒ recorded | control f (the test kills the child it started) |
| (g) the recorder changes no PASS/FAIL | control g: a passing and a failing toy, hooked and plain, same outcome and failure signature; real file: `test_v21_confine.py` PASS plain and hooked |
| qualified names are the compiler's | control h; `Walker.test_the_qualified_names_are_the_interpreters` |
| fork, copies, closed descriptors | controls i, j, k |
| watch list semantics (comment, nested, decorator, default, docstring, module statement, annotation, new/removed) | `Walker.*`, `FromGit.*` |
| not-PASS / unseen-witness not measured; plain mode; end to end via `main()` on a toy git repository | `Recorder.test_a_kill_file_that_fails_...`, `..._not_seen_...`, `..._plain_mode_...`, `..._main_end_to_end_...` |

Wrong implementations tried (each fails exactly the control it should): events written at exit (f, i), no at-fork (i),
main-thread-only callback (e), hook not inherited (c, f), import counted as execution (b and all), path-only copy match
(j), name-only copy match (j), descriptor held (k); and for the walker: nested bodies kept (nested/enclosing tests),
no `<locals>` (names), whole-AST compare, no docstring kind.

## 6. The real mini run (macOS, Python 3.14.7, tool at `beed5a3`, base `b5c2457`)

Expected sets were written to `expected.json` from the tests and the code BEFORE the run.

| kill file | s | executed | expected by reading | children (hooked / unhooked py / other) |
|---|---|---|---|---|
| `test_v21_kills3_T11b.py` (review_ocr only) | 0.35 | none | none — **matches** | 0 / 0 / 0 |
| `test_v21_kills3_R05.py` (`usage.usage` only) | 0.55 | `usage.session_tokens`, `client.events` | exactly these two — **matches** | 0 / 0 / 0 |
| `test_v21_r3_range_release_contract.py` | 2.26 | `ProcessRange.__init__`, `_ladder`, `_release`, `release`, `_Flight.__init__`, `_ps_table` | the same six (macOS: not `_linux_table`) — **matches** | 2 / 0 / 5 |
| `p4/test_process_range.py` | 17.99 | the six above + 9 of cleanup_authority (`_read`, `_ps_rows`, `_lines`, `_ps_env`, `host_table`, `carriers`, `_env_rows`, `cwd_under`, `_lsof_cwds`) | the same 15 — **matches** | 53 / 1 / 122 |
| `test_v21_confine.py` | 20.11 | 25: `measure`, `_judge`, `_mounts`, `_mounts.<locals>.text`, `_owned`, `_writes`, `Reviewer.review`, `client.events/read_session`, `redacted(+walk)`, `evidence_manifest`, `no_progress`, `session_tokens`, six process_range, five cleanup_authority | at least `measure`, `_judge`, `_probe` — **`_probe` NOT recorded** | 33 / 29 / 373 |

Two things the run showed that I had not predicted, both reported rather than adjusted:

1. **`T11b` loads `process_range.py` although it imports only `review_ocr`.** `tests/v2/__init__.py` arms the
   invariants, which import `aisef2.quality.test_execution`, which imports `process_range`. So every kill file of
   `tests/v2` has `loaded ⊇ [process_range.py]`, and since that file's import-time statements changed (`import re`,
   the new classes `ProcessTableError` and `_Flight`, the module docstring), `module_statements_executed` is
   non-empty for all of them. My static import closure of the kill file had missed the package `__init__`; the
   measurement did not.
2. **`_probe` is executed by `test_v21_confine.py` but the recorder did not see it.** `measure_in_range` runs
   `confine.measure` from a venv copy of `aisef2` under `python -I -B -c MEASURE` (confine tests lines 201–215): an
   isolated child never loads our sitecustomize. This is control d on a real file: `unhooked_python = 29` is the
   tool saying so. The recorder said `_probe` was executed nowhere it could look, and the one-sided claim is exactly
   that. The lead's expectation (`_probe` is executed) is very likely true; it is just not visible.

Overhead (one file, one pair, a loaded machine — not a statistic): `test_v21_confine.py` 19.61 s plain, 20.11 s hooked.

## 7. How a consumer should read it (a proposal, the decision is the lead's)

For target T with kill files K1..Kn, a standing result is *not contradicted by this record* only if every Ki is
under `kill_files` (PASS, witness seen) and Ki.`executed` holds no watched name, Ki.`other_version` is empty, and
Ki.`children.unhooked_python` is 0 — an unhooked Python child may have run watched code (`_probe`). The
import-time statements need a ruling: for `process_range.py` they are an import, two new class definitions and a
docstring (`diff.files[...].module_statements`), which every kill file executes; accepting them as inert is a
decision with evidence, not something the tool can make. A kill file that only *reads* a changed file's source (AST
scans, grep invariants, hashes) executes none of it: that is `read_set.py`'s `opened`, and both records are needed.

## 8. Real, simulated, neither

* **Real runs, macOS (Darwin 25.5, Python 3.14.7)**: the 5 kill files above through the runner's own `_run_file`
  (6 runs: `test_v21_confine.py` once more plain, for the overhead); the watch list from the real diff.
* **Simulation (synthetic inputs, real recorder)**: the controls and `test_reach.py` run the real hook and real
  processes on a toy tree built by the tool; their kill files are written for the purpose.
* **Not run**: Linux guest (Docker not used), Windows, Python 3.12/3.13, the full set (161 files), the
  `tests.v2.p0.test_destructive_authority` and `tests.v2.p4.test_mutation_safety` modules (the 5-file cap; instead
  the checker `destructive_authority.check()` was called directly and returns `[]`, 51 sites, over a tree whose only
  differences from `bcb2cfa` are the two files in `validation/v21/`).
* Order of work: `R.json` was produced at `beed5a3`. Afterwards three additive changes were made and tested on toy
  trees and unit tests only (the 5-file cap forbade a re-run): `module_statements` in the diff, `unhooked_python_argv`,
  and copy matching with controls j and k. The record format gained keys; none was removed or renamed.

## 9. Residual risk, and what is NOT established

* One-sided: "executed" is a fact; "not executed" is only "not seen in the processes hooked". Unhooked Python
  children (`-I`, `-E`, `-S`, own `env=`), non-Python children, `_posixsubprocess` launches without an audit event,
  C calls and code without a file are outside it (each is a limit string in the output).
* Not established: that any target may keep its result (the rule needs `read_set` and the kill files' own bytes too);
  that the 5 files represent the 161 — the share with `unhooked_python > 0` is unknown until the full run; that the
  copy-matching, `module_statements` and argv additions behave on real files as they do on toy trees; behaviour on
  Windows, Linux and 3.12/3.13.
* A function that is only *defined* (a new def) changes the module's namespace; code that enumerates it (`dir`,
  `inspect.getmembers`) sees that without executing it. Not counted as an import-time statement.
* A docstring-only change is watched (kind `docstring`) because `__doc__` can be read; the lead may filter by kind.
