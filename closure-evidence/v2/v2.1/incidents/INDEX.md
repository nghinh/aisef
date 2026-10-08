# AISEF 2.1 (B-03) — incident history

Every incident of the B-03 requalification round, in order, with what happened, what it cost, what was kept and where
the record is. An incident is never rewritten; a later correction is a new row or a new record.

| # | when (+07) | what happened | consequence | kept as | record |
|---|---|---|---|---|---|
| 1 | 2026-10-07 01:56–02:50 | Isolation proof, round 1 at 880881f: under concurrent load a two-runs claim race in a test made one worker's verdict differ | concurrency was not proven; the test was made deterministic (7fe1062), round 2 at cc53596 held | the failing round, unchanged | `isolation/round-1-880881f/`, `isolation/ISOLATION-SUMMARY.json` |
| 2 | 2026-10-07 08:58 | Campaign 1 (runner 1, cc53596) stopped under control: the runner let stale bytecode decide outcomes (17 of 20 same-second same-size pairs) and an identity file "killed" the null mutant of 5 modules (5,709 mutants); 29 confirmed audit findings | none of its results reused (0 of 18); runner v2 written | logs, records, audit, reuse table | `campaign-1-stopped/CAMPAIGN-1-STOP.json` |
| 3 | 2026-10-07 17:28–19:39 | Sandbox hand-mutant runs of `test_v21_confine.py`, killed at a 150 s limit, left three empty probe files in the system interpreter's site-packages | the host was written by a test; files untouched since, removal awaits approval; tests to be made host-safe by construction | the files, the logs that date them | `incidents/2026-10-07-site-packages-probe-files/` |
| 4 | 2026-10-08 ~02:30 | Integrating the product tracks: the sandbox branch's tests SIGKILLed pids reported by the code under test, and its probe deleted files the subject made (INV-MUTATION-AUTHORITY); the lead's earlier round-4 verification of that branch had missed it | fixed before the campaign (373a723 tests, 3c5f136 product), checked under the dangerous mutants | the commits and their messages | git history of v2.1/foundation (bae2ffe..e6b06eb) |
| 5 | 2026-10-08 03:10–03:29 | Pilot attempt 1 (ff115be): the data volume reached 2.0 GiB free — the lead's scratch held 58 GiB of old worktrees — and ENOSPC stopped four lanes | INFRA / NOT_RUN only, never KILLED; stopped under control; 26 GiB freed after archiving every scratch worktree's untracked files; disk guards added; pilot repeated | every lane's log and record | `pilot/attempt-1/README.md` |
| 6 | 2026-10-08 04:32 | Full suite at the integration commit e6b06eb: two new failures — four subprocess calls without `encoding`, and `execution_order.py` an uncalibrated checker | fixed (4de044e, 3fae5e1); the other failures were the known records to re-derive | the suite log | `preflight-3/README.md` (summary) |
| 7 | 2026-10-08 ~10:55 | The campaign-2 start record's first write failed (a script error) and the commit claimed a file it did not contain | the unpushed commit was amended within minutes to contain the record its message names (3e6ebf1) | — | `campaign-2/CAMPAIGN-2-START.json` |

Status of campaign 2 at the time of this index: **started 2026-10-08 10:49 (+07) and running** at 5719f1f — not
finished. Progress is logged every 5 minutes by the campaign's watchdog (targets and mutants classified per class,
targets running, infrastructure errors, free disk, ETA).
