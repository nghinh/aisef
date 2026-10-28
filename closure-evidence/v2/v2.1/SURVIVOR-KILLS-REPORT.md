# V2.1 — the two unaudited survivors, killed by behavioral tests (owner decision 2026-10-28, step 3)

Branch `v2.1/survivor-kills` (off `v2.1/probe-window` @ step-2). Both survivors are **real coverage
gaps, not equivalent mutants** — each has a legitimate behavioral kill. **No product bug**: in both
the original is correct; the mutant weakens it, and a new test now catches the weakening. So no patch
is prepared (per the directive: do not fabricate a requirement to kill a mutant).

Proof for each: the new test **passes on the original** and **fails on the mutant** (the one-line
mutation applied in place, run, reverted — product files left byte-clean).

## 1. `aisef2/app/diagnostics.py::access_of` — `L106 host=True -> host=False`

**What the line does.** `access_of` states who of a run's model sessions can read a folder. It lists
the directories the sandbox command line mounts with `confine.targets(full, host=True)` — `host=True`
returns **only the HOST's binds** (`--bind`, `--ro-bind`), the mounts that actually expose host data.
`host=False` additionally returns the sandbox-*made* mounts (`--tmpfs`, `--proc`, `--dev`), which
expose nothing of the host. If the folder is under a listed mount, the statement is `SAME_USER` (a
session can read it); else `SESSIONS_CONFINED`.

**Why the mutant is observably wrong.** `confine.argv` always emits `--tmpfs /tmp` and `--tmpfs <HOME>`
(plus `--proc /proc`, `--dev /dev`). With `host=False` the mutant treats those as host mounts, so a run
directory located under `/tmp` is read as `SAME_USER` — claiming a session can read it — when in fact
the session gets a **fresh empty tmpfs** at `/tmp`, exposing nothing. The correct statement is
`SESSIONS_CONFINED`.

**Why it was KILLED before and SURVIVED now.** The `host=True` vs `host=False` results differ only when
the inspected folder sits under a sandbox-made mount point (`/tmp`, `HOME`, `/proc`, `/dev`). The
existing tests put the inspected folder under the OS temp dir; on the **macOS** measurement host that is
`/var/folders/...`, not `/tmp`, so the two agree and the mutant survives. On Linux (`/tmp`) the same
tests would kill it — platform-dependent coverage, not a behavior change.

**The kill** (`tests/v2/test_v21_pm8_diagnostics.py::TheStatementOfWhoCanRead`,
`test_a_sandbox_made_mount_over_the_run_directory_is_not_a_host_mount`): a run directory `/tmp/...`,
asserting `/tmp` is in `targets(host=False)` but not `targets(host=True)`, and that `access_of` returns
`SESSIONS_CONFINED`. Platform-independent: `/tmp` realpaths to `/private/tmp` on macOS and matches there
too. original → `SESSIONS_CONFINED`; mutant → `SAME_USER` (fails).

## 2. `aisef2/probe/file_artifact.py::_worker_facts` — `L432 sorted(set(skipped)) -> list(set(skipped))`

**What the line does.** `_worker_facts` validates a grep worker's result — *data from another process,
never trusted for its shape*. `skipped_binary` must be the canonical **ascending, distinct** list of
file indexes: `skipped != sorted(set(skipped))` rejects anything that is not.

**Why the mutant is observably wrong.** `list(set(skipped))` keeps *distinct* but drops *ascending*: it
yields CPython's set-iteration order. A distinct-but-descending input that equals its own set order —
e.g. `[8, 0]`, since `list({8, 0}) == [8, 0]` — is wrongly **accepted** by the mutant and correctly
**rejected** by the original. The existing `"skipped out of order": [2, 1]` case does not expose this,
because `list(set([2, 1]))` happens to be ascending (`[1, 2]`), so both forms reject it.

**The kill** (`tests/v2/test_v21_fa_grep_worker.py::TheResultIsDataFromAnotherProcess`,
`test_skipped_binary_must_be_ascending_not_merely_distinct`): `skipped_binary=[8, 0]` over 9 files must
be `BAD_RESULT`; the ascending `[0, 8]` of the same indexes is accepted (not a blanket refusal). A
precondition `assertEqual(list({8, 0}), [8, 0])` documents the set-order witness and fails loudly if a
future interpreter changes it (so the test can never silently stop killing the mutant).

## Mutation-scope impact (handed to step 5)

Both kills were added to existing kill-test files, so no `V21_TARGETS` change is needed. Editing these
two test files changes their bytes, so every target whose kill-test closure includes
`test_v21_pm8_diagnostics.py` or `test_v21_fa_grep_worker.py` must be re-measured at the merged head —
quantified in step 5, together with the 62 MISSING, as one supplementary scope (not two passes).
