# T0 sweep of campaign 6 — incremental on campaign 5's

`complete.jsonl` = campaign 5's `T0-SWEEP-5.json` rows (373) followed by the **28** pairs round 4 added, measured at
**73af60c** (the code tree of 537f0b5): every kill file of the targets of `confine.py` (20 pairs) and
`process_range.py` (6) against the NEW null mutant of its module (the modules changed: `_sections`, `_judge`,
`_Posix.abort`), and the two new kill files (`test_v21_r4_anchor_nonascii.py`, `test_v21_r4_uncalibrated_qualifier.py`)
against the null mutant of `review_verify.py`. All 401 rows PASS (`sweep.log`, RC 0; the 28 new ones took 175 s).
Rows keyed by an old null mutant's digest stay as written and are not used: the table is keyed by the null mutant's
digest and `execution_order.py` finds a row only for the current one. Record `T0-SWEEP-6.json` (`measured_on`
73af60c), table `EXECUTION-ORDER-7.json` (528 targets ordered, none in declared order).
