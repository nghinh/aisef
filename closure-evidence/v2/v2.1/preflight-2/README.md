# Campaign 2 preflight at 7577e16 (2026-10-08)

`pre2.sh` ran, serially under the heavy lock, at a detached checkout of 7577e16 with the workers' environment
(`env -i`, PATH without opencode, scratch HOME/XDG/TMPDIR):

1. `tests.v2.test_v21_mutation_runner` + `tests.v2.test_v21_execution_order`: 59 tests OK (484.6 s) — `pre2-runner.log`.
2. `scratchpad/m21/preflight.py` (campaign 1's preflight): **failed to start** (`AttributeError: ... _FAILED`). It was
   written for runner 1; runner v2 removed those globals and replaced that preflight with T0 (docs/v2.1/
   MUTATION-RUNNER-V2.md §5: its "leaked 0" was blind, PL-4). Kept as the failed run it was — `pre2-preflight.log`.
3. The T0 sweep (`sweep.py`, lane c2tests' tool; lint-only edit: an unused `re` import dropped): every distinct
   (null mutant, kill file) pair of the 444 V2.1 targets through the runner's own T0 — **132 of 132 PASS**, no
   residue, no leak, no error; 5,140 s of T0 runs, 5,328 s wall — `pre2-sweep.log`, rows in `../T0-SWEEP.json`.
   Against the 33f4012 sweep, the 113 pairs with the same key took 0.968× the time (median; p10 0.895, p90 1.022).
