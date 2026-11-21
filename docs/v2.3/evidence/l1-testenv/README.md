# L1-TESTENV evidence

## PLATFORM-PARITY.json (moved here; L1TE-R1)

[`PLATFORM-PARITY.json`](PLATFORM-PARITY.json) is the platform-parity preflight of `tests/v23` at `45c87bc4` (darwin and
Linux; the Windows leg is NOT_RUN). Commit `4c0892be` placed it under `closure-evidence/v2.3/l1-testenv/`. That
directory is protected evidence (`validation/v2/v1_evidence_guard.py` protects all of `closure-evidence/` except
`closure-evidence/v2/`). A new file there turned `test_v1_evidence_guard` Detective red, and so the `--check` step of
every tests.yml unit leg. Corrected Amendment A2 puts new evidence here. The file was moved by `git mv` with its bytes
unchanged (sha256 `ece1af65c11ee1baeb70e706550752b710137d892bb0b38b9f149da5e91179cc`). It records the state at
`45c87bc4`, when the V21-36 test was not yet marked.

## V21-36 OPEN: the explicit expected failure (L1TE-R3)

`tests/v23/test_v23_testenv.py` `RealClientGuard.test_a_client_resolvable_on_path_stops_t0_and_run_before_any_target`
asserts the V21-36 guard: `mutation.main` exits 3 before any `run_target` when an executable `opencode` is resolvable
on PATH. That guard is L1-F5's hunk (W1-DESIGN §7, §8; text below), so the test fails until it lands. The test is
marked `@unittest.expectedFailure`, the literal decorator, with the comment `V21-36 OPEN — guard hunk owned by L1-F5`.
It is not skipped.

- **Visible:** the raw discover reports it as `expected failures=1` (`... expected failure` in verbose runs). The
  expected-red scan in `validation/w0_qualification.py` ("0 expected-red tests") lists this file while it lasts.
- **It cannot outlive the fix.** Once the guard exists, the marked test is an unexpected success. An unexpected
  success fails the raw discover (`wasSuccessful()` is false, exit 1) and release qualification
  (`release_qualify.run_suite` adds `unexpectedSuccesses` to the failing set, `release_qualify.py:151`). So the
  hunk's commit must drop the marker.
  `test_the_open_marker_turns_red_once_the_guard_exists` checks this in the suite on every platform: it wraps
  `mutation.main` in the hunk's logic and runs the marked test, which must come out as 1 unexpected success. That test
  is deleted together with the marker.
- **It cannot absorb another failure.** The unmarked `test_v21_36_is_open_exactly_as_measured_or_closed` accepts only
  two states for both modes together. *Open* is the measured red-before, `("reached run_target", 1)`. *Guarded* is
  `(3, 0)` with a refusal that names the client. Anything else fails, whether marker or not.
- **What it does not mean:** while the marker stands, neither the raw discover nor release_qualify counts V21-36 as
  failing. So a green batch is not V21-36 closed. The MASTER-CHECKLIST row stays `NEW_WORK`, and no PASS is claimed for
  V21-36 until the hunk lands and the marker is dropped. (The review's first preference was no marker. The marker was
  set for the integrated batch by the fix-pass directive, so that the batch is not red without saying why.)

Measured on darwin (Darwin 25.5.0, arm64, CPython 3.14.7) on an APFS clone of this fix's tree with no `.git`. Each run
used the mutation-worker env guard: PATH without any directory holding an `opencode` executable, XDG data/state/cache
in scratch. The command was `python3 -P -m unittest discover -v -s tests/v23 -t . -p test_v23_testenv.py`, with
`validation/v2/mutation.py` set as follows:

| `mutation.py` / test file | Result | Log sha256 |
|---|---|---|
| base (`07812c4f…`), as committed | `OK (expected failures=1)`, exit 0 | `2ba54670…` |
| L1-F5 hunk (`c56bfbc5…`) | marked test *unexpected success*; `FAILED (unexpected successes=1)`, exit 1 | `56e331eb…` |
| hunk returning 2 instead of 3 | marked test still expected failure; state test FAIL, exit 1 | `10ccb43e…` |
| hunk guarding `t0` only | state test FAIL, exit 1 | `dbdf4dc1…` |
| hunk whose refusal does not name the client | state test FAIL, exit 1 | `9a5c4afb…` |
| hunk, marker dropped, meta test kept | meta test FAIL, exit 1 | `aedba171…` |
| hunk, marker and meta test dropped (L1-F5's end state) | `OK`, 7 tests, exit 0 | `e561fcbf…` |

In the lane worktree at this fix, `tests/v23` gives `Ran 54`, `FAILED (failures=4, expected failures=1)`, log
`0418b8fb…`. The 4 failures are L1-BUILD's `ContractPinnedToCi` staging.yml pins, which stay red until L1-CIGOV (as
`04802164` states).

## Hand-off to L1-F5 (corrected; L1TE-R2)

The hunk goes at the top of `mutation.main`, right after `argv = ...`. It runs **before the usage refusals**
(diff sha256 `126ed7ee…`, as in `PLATFORM-PARITY.json`):

```python
    # V21-36: the kill-test environment keeps PATH (ENV_KEEP), and the product looks its client up there by name: a
    # mutant that drops a test's client override starts the real, paid client. No kill test runs where one resolves.
    if argv[:1] in (["t0"], ["run"]) and (exe := shutil.which("opencode")):
        print(f"STOPPED before the first target: an executable opencode is resolvable on PATH ({exe}): run the worker "
              "with a PATH that holds no real client (V21-36)", flush=True)
        return 3
```

L1-F5's `--run-affected` joins the guard's modes, and joins `MODES` in the test, once it exists.

**The hunk alone makes existing tests host-dependent.** `tests/v2/test_v21_mutation_runner.py` has 8 tests that call
`main(["t0"|"run", ...])`, selected by AST. Results, measured as above:

| PATH | base `mutation.py` | with the hunk | log sha256 (hunk) |
|---|---|---|---|
| guarded, no client | 8 OK | 8 OK | `f97208f2…` |
| guarded, then an empty `opencode` first on PATH (never executed) | 8 OK | `FAILED (failures=34, errors=1)`, 7 of the 8 tests | `84cecd62…` |

The base-file runs with the same two PATHs are logs `745d79ca…` and `bbed5a18…`. The review also measured the guard
placed just before the first `run_target` instead: 7 failures and 1 error. So rewording or moving the hunk does not
fix this. CI has no `opencode`, so CI stays green and does not show it. Only a host where the client resolves does,
such as an unguarded local batch.

Before the hunk lands, one of the following is required:

- **(a)** The W1 batch and every F5 kill-test run execute under the mutation-worker env guard. The batch evidence
  records the guarded PATH: `command -v opencode` resolves nothing. This fits W1-DESIGN §7 for V21-36 ("no test file
  is edited").
- **(b)** An additive module-level `setUpModule`/`tearDownModule` in `tests/v2/test_v21_mutation_runner.py` strips
  every directory that holds an `opencode` executable from `os.environ["PATH"]`. This edits an existing test file,
  which §7 excludes for V21-36 unless an amendment allows it.

Batch shapes to expect:

- **Before the hunk:** `test_v23_testenv` shows 1 expected failure.
- **With the hunk, the marker and the meta test dropped, and (a) or (b) in place:** green for V21-36.
- **On a host where `opencode` resolves, with neither (a) nor (b):** 35 more reds in `test_v21_mutation_runner`.
  This fails closed: `main` refuses, nothing runs. It costs a batch but loses no trust.
