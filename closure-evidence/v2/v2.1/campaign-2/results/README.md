# Campaign 2 results (B-03b, snapshot 5719f1f, manifest revision 2)

**What ran.** 2026-10-08 10:49 → 2026-10-10 21:42 (+07), 58.9 h, four queue workers (`../tools/qworker.sh` under
`../tools/campaign2.sh`), the committed execution-order table, runner 2. 457 targets from the queue plus the nine
pilot attempt-2 `ord` results the queue left out (`../../pilot/attempt-2/l*-ord.record.json`): **466 of 466 targets,
12,448 of 12,448 mutants**.

| class | mutants |
|---|---|
| KILLED (bracketed, reproduced FAIL) | 10,738 |
| SURVIVED (every kill file PASSed) | 1,676 |
| TIMEOUT | 3 |
| INFRA | 31 |

**The runner's own verdict** (`check.out`: `mutation.py --check` in a fresh detached worktree at the snapshot holding
the merged record, `../tools/check_at_snapshot.sh`): exit 1 — 1,676 unaudited survivors and 34 mutants neither killed
nor survived (5 targets); no inconsistent record, no target changed since its run, no missing result, every other
phase's record as before. **Not a pass**: survivors need a kill test or an audit, and the 34 need a re-run.

**The 34.** 3 TIMEOUT are genuine non-termination or waiting caused by the mutant (`NOTES.md` items 2, 11, 12). 31
INFRA are kills the bracket could not confirm because two kill tests label a subTest with a temp path that differs
every run (`test_v21_continue_integrity.py:620`, `test_v21_confine.py:220`; `NOTES.md` items 3, 10): the mutant fails
the test every time and the unmutated module passes every control, but `_confirm` needs the same signature. None is
counted killed. Fixing it is the owner's choice (a test-side label or a runner-side normalization of the run
directory); either way all 34 are re-measured.

**Hygiene.** 457 `owned_run` records: escaped 0, released empty, harness orphans 0 → 0. The operator's OpenCode store:
database, WAL, SHM, auth and config unchanged; the log and tool-output folder changed by the operator's own OpenCode
desktop app (`CAMPAIGN-2-END.json` `operator_store`).

**Files.** `CAMPAIGN-2-END.json` (counts, the 34, check summary, ownership, every file's sha256 and its uncompressed
sha256); `ACCOUNT.json` (per-target survivor counts, sources); `MUTATION.json.xz` (the merged V2.1 record, 65 MB
uncompressed); `c2-wN.record.json.xz`, `c2-wN.log.xz` (each worker's record and log); `progress.log.xz`, `disk.log.xz`;
`owned.tar.xz`; `store-before.json`, `store-after.json`; `NOTES.md` (what happened during the run).

**To re-check:** `xz -dk MUTATION.json.xz`, put it at `closure-evidence/v2/v2.1/MUTATION.json` in a tree at 5719f1f, run
`python -P validation/v2/mutation.py --check` (PATH without `opencode`).

**What this does not show.** Mutation measures whether the existing tests kill mutants of the code at 5719f1f. It says
nothing about behaviour with a real model, cost or benefit; it does not replace live checks. Results stand for a later
HEAD only as `delta/DELTA.md` allows (30 targets re-measure; 436 provisionally).
