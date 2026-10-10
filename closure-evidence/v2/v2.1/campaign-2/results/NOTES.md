# Campaign 2 — what happened during the run (2026-10-08 10:49 → 2026-10-10 21:42, +07)

Written as the run went (the lead's notes, kept as they were; times +07 unless marked Z), then closed at the end.
The counts and verdicts are in `CAMPAIGN-2-END.json`, `ACCOUNT.json` and `check.out`; nothing here changes them.


1. 2026-10-08 18:10Z digest — monitor defect: the old watch did `cat c2-w*.log | tail -n (cur-seen)`, so new lines in
   any log but the last were never scanned; the TIMEOUT below surfaced only through the 30-min digest. Fixed
   (per-file grep + comm, mon/watch.sh); a rescan of all logs from the start found nothing else missed.
2. TIMEOUT — c2-w3, aisef2/app/bundle_cli.py::continue_from, mutant `L416 In->NotIn`: `while carried not in
   project.stories: carried += "_"` never ends; test_v21_continue_usage and test_v21_continue_integrity each hit the
   900 s limit. Genuine non-termination caused by the mutant; class TIMEOUT, not KILLED, not infra. Owned processes
   0 escaped.
3. INFRA — c2-w2 line 3764, aisef2/app/cli.py::run, mutant `L65 Or swapped`: the mutant FAILs
   test_v21_continue_integrity.AnchorThreatModel.test_the_cli_refuses_anchor_paths_it_would_not_write_and_a_malformed_expected_anchor
   every time (in place, rerun, fresh tree, fresh rerun), the null PASSes every control (4.65, 4.84, 269.37, 273.61 s),
   but the rerun's first-failure signature never equals the first run's: the test labels its subTest with
   `argv[-1]`, an absolute temp path (…/run-XXXX/tmp/tmpYYYY/operator-only/out.anchor) that differs each run, and
   `_confirm` requires `x["first"] == row["first"]`. The runner fails closed (INFRA, not KILLED) — correct by its
   rules. Root cause: a nondeterministic subTest label in a kill file (test line 620 at 5719f1f). Not fixed during
   the campaign (snapshot/runner/kill set frozen). After the campaign, options for the owner:
   (a) test fix — label the subTest by index or by path relative to self.tmp (no assertion changes); the kill file
       is in 91 kill sets, so by the proof rules those targets re-measure unless an exception is approved;
   (b) runner fix — normalize the runner's own run-directory prefix in failure signatures; harness change, not
       covered by the proof; re-measure the INFRA mutants only.
   Either way every INFRA mutant is re-measured; none is counted killed.
4. 2026-10-09 ~06:00 (+07): disk 29 → 24 GiB in ~2 h, ~3 GiB of it swap (4 → 7 GiB; fseventsd at 4.8 GB RSS from
   the runner's tree churn). With the owner's approval in chat, removed 19 of my scratch clones (each re-verified
   just before: HEAD in the repo, no branch outside it, no open file; status, diff and untracked files ≤ 5 MB
   archived in scratchpad/copy-archive/2026-10-09/, list in OK.list): 24 → 31 GiB free. Campaign trees, watchdog
   and workers untouched. Kept: clones holding commits not in the repo (prod/round2-sandbox*, round3*, gap-close)
   and those the Docker VM holds open.
5. cli.py::run finished (c2-w2 line 3875): 100 K / 32 S / 1 INFRA, line ends "ERROR UNCLASSIFIED: 1 mutant(s) neither
   killed nor survived {'INFRA': 1} — re-run them" — the target is unclean and flagged for re-run, as designed. Its
   `survivors` list has 33 names because the runner's field is every non-KILLED mutant (mutation.py:1572), so it
   includes the INFRA `L65 Or swapped`; the account must count per-mutant `class`, never the length of `survivors`.
6. 2026-10-09 ~18:30 (+07): swap 7 → 14 GiB in ~12 h (fseventsd 5.7 GB RSS), free 27 → 20 GiB; at that pace the
   watchdog's 12 GiB STOP would have come ~15 h before the campaign's end. With the owner's approval in chat, removed
   17 more scratch paths (each re-verified just before: HEAD and status equal to the archived ones, nothing open):
   4 clones whose HEAD is in the repo, 2 clean worktrees (rc via `git worktree remove`), 10 clones holding commits
   outside the repo (each first saved as a verified git bundle), and ocr-build/gocache (Go build cache; modcache and
   the OCR binaries kept). Archive: scratchpad/copy-archive/2026-10-09b/ (226 MB). Free 20 → 28 GiB. Campaign trees,
   b03/l3c, watchdog and workers untouched.
7. 2026-10-09 20:08–20:44 (+07): free 26 → 14 GiB in ~1.5 h, swap 14 → 23 GiB. Footprints: fseventsd 21–22 GB,
   XProtectRemediator 7.8 GB, a local ASR job of another Claude session (project bread, python3.13 + torch) ~6 GB,
   Docker Desktop VM ~4 GB. Not done: restarting fseventsd (needs sudo with a password — the owner's to run); the
   other session's job (not mine; it ended by itself). A first `docker desktop stop` was refused by the auto-mode
   classifier; after the owner's explicit authorization in chat it ran at 20:43 (state before in mon/docker/: two
   running containers, both restart=unless-stopped, no host connection, no published port). After: VM down, free
   22 GiB, swap 14 GB; fseventsd still 22 GB (only a restart frees it). Docker is to be started again after the
   campaign (`docker desktop start`; the two containers come back by their policy). No mutant was affected (0 infra).
8. 2026-10-10 06:15 (+07): the owner ran `sudo killall fseventsd` in their terminal (my tab c1 with the same command
   waited for a password I do not enter; closed). Before: fseventsd pid 588 (up 19 d) footprint 33 GB, swap 25.6 GB,
   free 20 GiB. The old process sat in state U for ~1 min, then launchd started pid 9569 (5 MB). After: swap used
   24.7 → 3.4 GB within seconds, free 20 → 25 GiB and rising as swap files go. Campaign workers and watchdog unaffected.
   Lesson: the runner's tree churn under /private/tmp grows fseventsd without bound on this host (4.8 GB → 33 GB in
   ~25 h); a long campaign needs either a periodic fseventsd restart by the owner or its trees on a volume FSEvents
   does not track (a proposal for the next round, not for this campaign).
9. 2026-10-10 07:16 (+07): one hour after the restart, with the campaign churning as before and Docker Desktop
   stopped, fseventsd stays at ~3.7 MB (it was 4.8 GB → 33 GB before). Consistent with an FSEvents client that does
   not drain its queue — Docker Desktop's file sharing (it held 5,136 handles in my scratchpad) is the likeliest; this
   is an inference, not measured (listing fseventsd clients needs root). Watch again when Docker is started.
10. 2026-10-10 ~17:45 (+07), c2-w3, aisef2/app/confine.py::wrap: 24 INFRA mutants (log lines 53692–53748) — the same
    mechanism as item 3. Each mutant FAILs test_v21_confine.CommandLine.test_a_client_directory_that_holds_home_or_the_
    workspace_is_refused in place, on rerun, on a fresh tree and on its rerun, and the null PASSes every control; the
    first-failure signature carries the subTest label `exe=PosixPath('/…/c2-w3.env/tmp/aisef-…/…/opencode')`
    (test line 220 at 5719f1f: `self.subTest(exe=exe)`), a temp path that differs each run, so `_confirm` never sees
    the same signature. Classified INFRA (never KILLED) by the frozen runner, correctly by its rules. Two tests cause
    every INFRA so far (25): test_v21_continue_integrity.py:620 `subTest(argv[-1])` and test_v21_confine.py:220
    `subTest(exe=exe)`. test_v21_confine.py is already a re-measure kill file (changed after the snapshot), so a test-side
    fix there costs no extra re-measurement; continue_integrity is in 91 kill sets. The monitor missed nothing this
    time; the session that watched it ended at ~15:47 and the lines were rescanned at 18:08.
11. 2026-10-10 ~21:20 (+07), c2-w2, aisef2/app/confine.py::_survivors, mutant `L347 condition negated`: TIMEOUT at
    900 s in test_v21_confine.py (test_a_killed_sleeper_is_no_survivor_a_live_one_is, line 373): the mutant makes
    `_survivors` poll `time.sleep(0.05)` forever (KeyboardInterrupt in the tail at confine.py:265). Genuine
    non-termination caused by the mutant; class TIMEOUT, not KILLED, not infra.
12. TIMEOUT — c2-w1, aisef2/app/adapters.py::_bounded, mutant `L281 And swapped` (log line 43228): with
    `while code is None or time.monotonic() < deadline` the loop keeps waiting after the process has ended, until the
    deadline; test_v21_review_chain.py hit the 900 s limit (the tail shows the run blocked in a probe's
    `process_range._line`). A behaviour change caused by the mutant (it waits out the whole budget); class TIMEOUT.
13. Closing counts. Item 10's "24 INFRA" grew to 30 in confine.py::wrap by the target's end (27 K / 12 S / 30 INFRA of
    69); with cli.py::run's one, 31 INFRA, all from the two temp-path subTest labels; 3 TIMEOUT (items 2, 11, 12). No
    other INFRA kind, no escaped process (457 owned_run records: escaped 0, released_empty, harness orphans 0 → 0).
14. Forecasts. The table-order forecast (pilot attempt 2) said ~40 h; the run took 58.9 h. Three reasons, measured:
    survivors were 13.5 % of mutants (pilot 13.3 % but concentrated in the large early targets), the host's load
    (other sessions' jobs, macOS background services, fseventsd/swap) slowed kill files by 25–35 % for hours, and the
    upper-bound model left out the fixed cost of a target (pristine tree, T0 of every kill file): refitted on 210
    finished targets, real ≈ 1.45 × chain + 0.35 × UB; the last ~150 tiny targets cost ~200 s each regardless of
    their mutant count.
