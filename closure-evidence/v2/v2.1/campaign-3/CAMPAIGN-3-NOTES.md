# Campaign 3 — notes that are not numbers

## The one intermittent failure: `ProcessRange.release()` called by two threads (measured 2026-10-12)

**Observed.** T0 of `cli_invocation.py::HARNESS/invoke` (worker c3-w4): `tests/v2/test_c2_cli_invocation.py` FAILED once
(`ERROR test_FM2_CLI_SUBJECT_3_a_controller_stop_is_an_interruption_with_no_result | ValueError: PyMemoryView_FromBuffer():
info->buf must not be NULL`, `aisef2/runtime/process_range.py` `_close_pipes`, `pipe.close()`). That file ran 10 times on
the unmutated tree in the campaign records: 1 FAIL. The target's T0 stopped the target (41 NOT_RUN); the re-run of the
same target alone passed T0 and was 41/41 KILLED. A mutant run that hits it is never a false kill: the bracket (FAIL, two
PASS controls, FAIL again with the same signature) turns it into INFRA, which is how `HARNESS/reported`'s one INFRA read.

**Measured** (an investigator with 400 runs of the single test, plain-pipe reproductions, a deterministic gated
reproduction; files in `flake-process-range/`): the single test fails 3 of 100 idle runs (exact error present in 5), 1 of
240 under load (exact error in 3); all 340 natural runs: 8 exact errors (2.35%), 4 test failures (1.2%). Root cause:
**two threads are inside `release()` of the same range at once, and release has no mutual exclusion.** The test does it
by design (a controller's stop thread calls `release()` while the probe's own `finally: run.release()` runs); the second
`EXIT` write meets EPIPE, bytes stay pending in the `BufferedWriter`, and the two `_close_pipes()` close the same stdin
within microseconds; the loser writes the pending bytes from a freed buffer and CPython raises `ValueError`, which
`except OSError` does not catch. Not the 5 s pump join; not 3.14-specific (the same text from a stdlib-only
reproduction on 3.9.6, 3.12.14, 3.14.3, 3.14.4, 3.14.7). Necessary conditions, each with a control at 0/3000: two
threads, pending bytes after an EPIPE flush, both closes within microseconds.

**Product reach.** No product path was found with two threads inside `release()` at once (every user read; 132 kill files
counted dynamically: 28 release from two threads *sequentially*, max concurrent 1; exactly two kill files overlap:
`test_c2_cli_invocation.py::test_FM2_CLI_SUBJECT_3` and `test_probe_process_effect.py::test_FM2_EFFECT_10`). The failure
is not contained as an observation: it replaces the probe's `ProbeInterrupted` and surfaces as `REFUSED: ValueError` of
one story — fail-closed, never a verdict. Absence in real runs is not proven (a signal handler could re-enter;
StoryScope's 600 s release-timeout thread is abandoned, not joined).

**Not fixed, on purpose, and why.** The fix is one file (`aisef2/runtime/process_range.py`, +9/−1: an `RLock` around
`release`, `process_range.diff`; a deterministic test: 200/200 fail before, 30/30 pass after,
`proposed_test_release_concurrent_pipes.py.txt`; the narrower alternative `except (OSError, ValueError)` is
`process_range.alt-swallow.diff`). But the file is pinned by the manifest (`versions.harness`), every one of the 468
targets has it in its kill-file closure and 235 targets (5,872 of 12,548 mutants) are direct importers: under the delta's
`[product]` rule that is a new pin and a re-measure of ~235 targets (165 of them standing results) — a broad campaign for a
measured 1-5% flake of two tests that no product path is shown to reach, and the classification is already safe
against it. **It is the owner's decision** (recommendation: fix with the next revision that touches the harness anyway; do
not re-measure for it alone). Until then a T0 FAIL with this exact signature is re-run alone, as `c3b` did.

**Not established** (the investigator's list, kept): the CPython C sources were not read (inferred from behaviour:
deterministic repro, 3 controls, 5 interpreter versions); no failing run was captured by the precondition tracer; a
range-level reproduction with a plain `sleep 60` target did not reproduce (0/800); the full-file rate of
`test_c2_cli_invocation.py` was not measured (73 s per run); Linux and Windows were not measured.

## The real OpenCode store

See `results/README.md`: the only difference between before and after is the log directory's newest-entry mtime;
`opencode.log` is held open for writing by the Desktop application's helper (pid 9958, up for days), whose last lines
are its own project-refresh entries.

## Process notes (reported, not hidden)

* The round-2 implementer of R01 ran one text edit of its own test file through `python3` directly (a stdin script
  importing only `re` and `pathlib`) before noticing the wrapper rule; no product or test code ran outside `py.sh`.
* Two of the lead's shell commands used an unquoted heredoc whose backticks zsh executed (command not found / usage
  errors; created two empty scratch directories, removed). Nothing in the repository was affected.
* The wrapper `py.sh` of the survivor work read its PATH from a scratch file that macOS had cleaned; it now computes the
  guard PATH itself. Agents of round 1 ran before that.
