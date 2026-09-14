# Column-2 launch aborted by defect 170 — NOT benchmark data

These 72 rows are **not** an experiment result. Every one is a client startup
failure: `outcome: FAIL`, **0 turns**, 0 USD, and all 72 carry the identical
error `Failed to change directory to .bench-c2/`. No model was ever called.

Cause: `AISEF_BENCH_DIR=.bench-c2` — written exactly that way in the
pre-registered launch command, `BENCH-PREREGISTRATION-C2.md` §5 — produced a
**relative** `KEEP_DIR`, while the default `ROOT / ".bench"` is absolute. The
workspace handed to the client was therefore relative, and the client, running
with its own working directory, could not enter it.

Kept because it is evidence of the defect, and discarded from the cohort because
mixing 72 fabricated FAILs into `results.jsonl` would corrupt the real
experiment. This is not "rerunning a benchmark to improve its result" — there
was no benchmark: nothing ran, nothing was measured.

The danger the numbers illustrate: read naively, this file says *AISEF 0/36,
bare 0/36*. An infrastructure failure would have been read as a measurement.

Fixed in taxonomy row 170 / register D-015. The real Column-2 cohort starts from
an empty `.bench-c2`.
