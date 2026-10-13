# T0 sweep of campaign 5 — incremental on campaign 4's

`complete.jsonl` = campaign 4's `campaign-4/t0-sweep/complete.jsonl` (253 rows) followed by the **120** pairs B-03 round 3
added, measured at **bcb2cfa** (the code tree of 9f336fb): every kill file of the targets of `confine.py`, `adapters.py`,
`run.py`, `lineage.py`, `verify.py`, `usage.py`, `review_verify.py`, `client.py`, `process_range.py` and
`cleanup_authority.py` against the NEW null mutant of its module (the modules changed), and every new kill file
(`test_v21_r3_*`) against the null mutants of the targets it was registered with. All 120 PASS
(`incremental-pass-at-bcb2cfa.log`, RC 0). Rows keyed by an old null mutant's digest stay in the file as written and
are not used: the table is keyed by the null mutant's digest and `execution_order.py` finds a row only for the current
one. Record `T0-SWEEP-5.json` (`measured_on` bcb2cfa), table `EXECUTION-ORDER-6.json`.
