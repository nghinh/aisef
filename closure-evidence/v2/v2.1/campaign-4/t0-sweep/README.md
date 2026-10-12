# T0 sweep of campaign 4 — incremental on campaign 3's

`complete.jsonl` = campaign 3's `campaign-3/t0-sweep/complete.jsonl` (235 rows, measured at 408e1c8 and 206bc79, see its
README) followed by the 18 pairs the round-2 work added, measured at **76e92e8**: the six round-2 kill files
(R01 R02 R03 R04 R05 R07) and `test_v21_defects_lineage2.py` against the null mutants of their targets' modules, and
every kill file of the `lineage.py` targets against `lineage.py`'s NEW null mutant (the module changed: the
`account_of` fix). All 18 PASS (`incremental-pass-at-76e92e8.log`). The 13 rows of the old `lineage.py` null stay in the
file as written and are not used: the table is keyed by the null mutant's digest, and `execution_order.py` finds a row
only for the current one. Record `T0-SWEEP-4.json` (`measured_on` 76e92e8), table `EXECUTION-ORDER-4.json`.
