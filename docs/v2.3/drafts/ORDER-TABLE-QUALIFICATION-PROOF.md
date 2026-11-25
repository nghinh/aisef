# Execution-order tables — the Decision-3 qualification-proof mapping (2026-11-26)

**Status:** working paper for the order-table RATIFICATION package (owner package #1, decision 3 PROPOSED:
"GO for development and qualification proof … benchmark additional representative targets, including survivors
and long-running targets, before ratifying production RC order tables"). Confers no ratification. E5 timings are
carried as **performance-study input only**, exactly as the proposed decision classifies them.

## 1. The six proof obligations, mapped to what already pins them

| # | Obligation (decision 3) | Pinned by | Where |
|---|---|---|---|
| 1 | Identical mutant enumeration | Order applies to KILL-FILE execution only; enumeration (`mutants()`) runs before and independent of `--order` (the table is validated, then workers consume it per target). Measured: the A/B benchmark enumerated 49/49 identical mutants both sides. | `validation/v2/mutation.py:2977-2996` (order parsing touches only the chain's file order); ORD-1 baseline tests `tests/v2/test_v21_mutation_runner.py:1831`; measured `aisef-private-evidence/2026-11-25-accel-plan/ORDER-MEASUREMENT.json` |
| 2 | Identical KILLED/SURVIVED classifications | ORD-4 rotation property test: "every class, the target's fields, T0 and the verdict are the declared order's"; each (mutant, file) has the same rows in every order. Measured: 49/49 identical verdicts, 0 survivors both sides. | `tests/v2/test_v21_mutation_runner.py:2179` (`test_an_execution_order_changes_no_class_and_the_record_only_where_it_must`); ORD-6 outcome normalisation `validation/v2/mutation.py:2233` |
| 3 | Unchanged confirmed-kill bracket checks | The bracket (killed_by FAIL + control + rerun) is validated over `ran` — the order actually executed — whichever order that is; the rotation test pins that only "which reproduced FAIL came first" may move, never a bracket outcome. | `validation/v2/mutation.py:2645-2653` (acceptance recomputes `ran` from `execution_order` and validates the same bracket rules); the same ORD-4 test |
| 4 | Every survivor runs the complete required kill set | ORD-4 is exactly this invariant: "a SURVIVED needs one PASS per kill file in the order its chain ran them — the declared order, or the table's"; "a mutant not killed ran every file in the table's order". | `tests/v2/test_v21_mutation_runner.py:1450,1916,2179` |
| 5 | Original declared order recoverable and independently verifiable | The record keeps `kill_tests` = the DECLARED list unchanged (ORD-4) and adds `execution_order = {files, from: {path, sha256}}` whole; `--check` refuses any result whose table is not a file committed at HEAD, and `execution_order.py --check` re-derives the table from its committed source record. | `validation/v2/mutation.py:2530-2550,2977-2996`; `validation/v2/execution_order.py` (RULE + `--check`); `tests/v2/test_v21_execution_order.py:67,107` |
| 6 | No dirty or uncommitted record becomes qualified | The one shared admissibility rule: `identity.dirty` must be stated and false, digest-currency on closure/kill_files/enum_modules, T0 all-PASS, I7 (uncommitted) refused verbatim — independent of ordering entirely. | `validation/v2/mutation.py::v23_admissible` (commit 455c6bbc); `tests/v23/test_v23_b1_admissibility.py`, `tests/v23/test_v23_mutation_round.py`; FINDING-B1-DIRTY-ACCEPT-001 |

## 2. What is NOT yet proven / not yet built (the honest gap list)

1. **The production rule is not the benchmarked rule.** The sanctioned `execution_order.py` RULE is
   "ascending T0 seconds, ties by declared position" (a T0-sweep-derived table). The measured −67.8% table was
   **kill-frequency-ordered from E5 positions** — a different derivation the tool does not yet emit. Development
   owed (GO'd by decision 3): a second, versioned rule in `execution_order.py` deriving from a committed
   E5-position record, with `--write`/`--check` re-derivation exactly like the T0 rule, so obligation 5 holds
   for it byte-for-byte. Until then, no production table exists to ratify.
2. **Supplementary benchmark** on representative targets *including survivors and a long-running target* —
   scheduled (bounded, same-machine A/B, identical-verdict assertion incl. ORD-4 survivor-complete-set); the
   first A/B covered two bounded all-killed targets only.
3. **Owner ratification** of the production tables' source citation (package #1 item 3) — after (1)+(2).

## 3. Already-measured performance input (study input, not evidence of admissibility)

- A/B 2026-11-25 (`ordbench`, targets delivery + client_on_path, 49 mutants): declared 76.2 min vs
  frequency-ordered 24.5 min = **−67.8%**, identical verdicts 49/49 KILLED / 0 SURVIVED both sides.
- E5 fleet profile: only 56.5% of kills die in the first 2 files; 79.3% of wall time is spent on files that
  precede the killer; simulated fleet-wide reorder saving −62% (ESTIMATE).
