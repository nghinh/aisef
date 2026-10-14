# T0 sweep of campaign 8 — incremental on campaign 7's

`complete.jsonl` = campaign 7's `T0-SWEEP-7.json` rows (402) without the rows of the two kill files whose bytes changed
(`tests/v2/test_v21_r3_conf_policy.py`, `tests/v2/test_v21_r4_probe_record.py`: the suite's rule that a child-process
call that reads text names its encoding), followed by the 2 pairs measured again at **3efb56be4eb73546000c90f17487af4e7851371a** against the null mutant of
`confine.py`: both PASS (`sweep.log`, RC 0). A third campaign-7 row for `test_v21_r3_conf_policy.py` named a null mutant
no current target has (a stale row of an earlier module version); it is not carried over by the sweep. Record
`T0-SWEEP-8.json` (`measured_on` 3efb56be4eb73546000c90f17487af4e7851371a), table `EXECUTION-ORDER-9.json`.
