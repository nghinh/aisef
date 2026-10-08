# Pilot attempt 2 (2026-10-08, at 5719f1f, the campaign-2 snapshot) — the two orders measured

**What ran.** Owner 2026-10-07 step 7. Nine representative targets (`lane*.targets`) on four lanes; each lane ran its
targets twice, each time in a fresh detached worktree at 5719f1f: the declared kill-set order (`decl`) and the
committed table `closure-evidence/v2/v2.1/EXECUTION-ORDER.json` (`ord`). Lanes 1 and 3 ran `decl` first, lanes 2 and
4 `ord` first. 06:15:26–10:48 (+07) under the heavy lock, with the disk guard (`disk.log`: 23–27 GiB free throughout).
Scripts as they ran: `pilot.sh`, `pworker.sh`; comparison `pilot_compare.py` → `compare.json`; model `forecast.py`
→ `forecast.json`.

**Classification — the same in both orders for every mutant.** 240 of 240 mutants (keyed by generator position) have
the same class: 208 KILLED, 32 SURVIVED, 0 TIMEOUT, 0 INFRA, 0 NOT_RUN. Every run: escaped 0, harness orphans 0 → 0,
released_empty, worktree status clean. The killing file differs for 96 of the 208 kills (the order decides which
reproduced FAIL comes first, never whether there is one); survivors ran every kill file in both orders.
This attempt had no TIMEOUT or infrastructure fault; attempt 1 (same pilot, ENOSPC) showed that such a fault yields
INFRA/NOT_RUN and an errored target, never KILLED; order independence of the TIMEOUT/INFRA classes is the runner's own
`::Order` toy matrix (docs/v2.1/MUTATION-RUNNER-V2.md §7).

| target | mutants | classes | runner s decl → ord | ord/decl | own runs decl → ord |
|---|---|---|---|---|---|
| cli.py::_parser | 31 | 15 K / 16 S | 5,203 → 4,943 | 0.95 | 95 → 95 |
| run.py::admit | 15 | 15 K | 672 → 644 | 0.96 | 19 → 23 |
| settings.py::endpoint_problem | 36 | 29 K / 7 S | 4,474 → 4,819 | 1.08 | 95 → 105 |
| usage.py::no_progress | 33 | 29 K / 4 S | 3,109 → 3,976 | 1.28 | 41 → 64 |
| lineage.py::claims | 12 | 7 K / 5 S | 2,416 → 2,376 | 0.98 | 19 → 19 |
| story_runner.py::_fail | 34 | 34 K | 363 → 332 | 0.91 | 34 → 34 |
| cli_invocation.py::_harness_failure | 27 | 27 K | 1,037 → 1,076 | 1.04 | 37 → 59 |
| cli_invocation.py::AGENT/guarded | 19 | 19 K | 360 → 356 | 0.99 | 22 → 38 |
| python_callable_v2.py::_watch | 33 | 33 K | 2,605 → 1,055 | 0.41 | 35 → 58 |
| **total** | **240** | **208 K / 32 S** | **20,237 → 19,576** | **0.967** | **397 → 495** |

**Time — a small gain, concentrated, and confounded with load.** Runner time (every row's seconds + overhead, T0
included) fell 3.3 % overall. Only `_watch` gains clearly (0.41×: its declared first file costs 101 s, the table's
first 1.4 s, and cheap files kill most of its mutants; lane 4 ran `ord` first, under full load, and was still faster).
Elsewhere the ratio is 0.91–1.28 and follows the machine's load more than the order: the second run of lanes 1 and 2
ran while other lanes had finished (lane 2's `decl` on an almost idle machine), so `no_progress` and `endpoint_problem`
look slower in `ord`. Survivors cost the same in both orders (every file runs): they are 13 % of the mutants and about
half of the time. Measured per mutant against its target's chain (sum of its kill files' T0 seconds): a KILLED mutant
costs 0.132 of the chain in `ord` and 0.180 in `decl` (mutant-weighted), a SURVIVED one 1.13; T0 costs 1.15 of the
chain (load).

**Forecast (`forecast.json`).** Applied to the 466 targets of manifest revision 2: `ord` 161.8 worker-hours at the
pilot's survivor rate (13.3 %), 111.2 at 4 % (the 2.0 S2 campaign's rate), 197.9 at 20 %; `decl` 182.5 / 135.1 /
216.3. With four workers: about 40 h of wall time at the pilot's rate (28–49 h).

**Decision.** Campaign 2 runs the table order (classification identical on every mutant measured; no target's validity
depends on it; the measured cost per kill is lower) — but reordering alone is a small lever (owner step 8). Where the
time goes (`durations/`): the two dearest kill files, test_v21_continue_integrity.py (232 s, in 91 kill sets) and
test_v21_review_chain.py (158 s, in 78), are 26 and 20 end-to-end runs of 8–19 s each with no dominant fixed wait, so
they get cheaper only if the end-to-end run itself does. Measured levers taken: a dynamic queue (no idle tail),
longest expected target first. Proposed, not taken (they change what the runner measures and need the owner): reusing
one T0 per (null mutant, kill file) pair across the targets that share it (T0 ≈ 11 % of the time; 466 targets share
139 pairs).

**Reuse.** The `ord` lanes ran at the campaign-2 snapshot with the committed table and the campaign's harness: their
nine results are campaign-2 results (the campaign's queue leaves these targets out). The `decl` lanes are pilot
evidence only, so no target has two results in the account.
