# T0 sweep of campaign 7 — incremental on campaign 6's

`complete.jsonl` = campaign 6's `T0-SWEEP-6.json` rows (401) followed by the **1** pair round 4b added, measured at
**534435f**: `tests/v2/test_v21_r4_probe_record.py` against the null mutant of `confine.py`. It PASSes (`sweep.log`,
RC 0). The changed kill file `test_v21_r3_judge_not_run.py` keeps its key (module, null mutant, path): its T0 row is
campaign 6's, its content changed, and the runner measures it again at every mutant. Record `T0-SWEEP-7.json`
(`measured_on` 534435f), table `EXECUTION-ORDER-8.json`.
