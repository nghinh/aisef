# Campaign 3 — what ran, what it measured, what stayed open (2026-10-11/12)

Manifest rev 3 (`REQUALIFICATION-MANIFEST-3.json`), snapshot `f860e57`, runner v2 with the signature fix and positional
audits, execution order `EXECUTION-ORDER-3.json`, 4 workers (`c3-w1..4`), hermetic environment (`env -i`, PATH without
`opencode`, scratch HOME/XDG/TMPDIR), machine-wide heavy lock, Docker stopped. Started 2026-10-11 12:41:49Z (19:41
+07), finished 2026-10-12 03:13:53Z (10:13 +07): **14.54 h**. Every worker's tree was clean after (`*.status-after`
empty); no worker stopped, no STOP file, no ownership failure; 199 queue lines, 199 exits (1 each: survivors exist).

## Numbers

| | targets | mutants | KILLED | SURVIVED | TIMEOUT | INFRA | NOT_RUN |
|---|---|---|---|---|---|---|---|
| campaign 3, as run (c3-w1..4) | 199 | 7,867 | 7,583 | 242 | 0 | 1 | 41 |
| re-run of the 2 targets that did not close (`c3b-w1`, same snapshot) | 2 | 67 | 67 | 0 | 0 | 0 | 0 |
| campaign 3 after the re-run | 199 | 7,867 | 7,625 | 242 | 0 | 0 | 0 |

The two targets that did not close, and why (a result stays what it was measured as; the re-run is a continuation of
the history, imported as `c3b-w1`, linked here):

* `aisef2/probe/cli_invocation.py::HARNESS/invoke` — 41 NOT_RUN: the T0 baseline of `test_c2_cli_invocation.py` FAILED
  once on the null mutant (`ValueError: PyMemoryView_FromBuffer(): info->buf must not be NULL`, raised at
  `aisef2/runtime/process_range.py:352`, `ProcessRange._close_pipes`), PASS on the original tree of the same run and in
  every other run of that file in the campaign (the T0 sweep, five sibling targets, the full suite). The runner stops a
  target whose T0 fails: nothing was classified. The re-run alone: T0 PASS, 41/41 KILLED. The cause is investigated
  separately (see `CAMPAIGN-3-NOTES.md`); this is **not** a timeout raised or a classification changed.
* `aisef2/probe/process_effect.py::HARNESS/reported` — 1 INFRA (`HARNESS L99 dict entry 0 dropped`): the kill file
  FAILed twice with different failure signatures, so the kill was not confirmed (rule: a bracketed reproduced FAIL with
  the same signature). The re-run: 26/26 KILLED.

## The runner-impact check (owner point 2)

20 targets whose campaign-2 result STANDS by the delta (no input changed) were measured again on purpose
(628 mutants, 20 modules' worth of kill files). **Every mutant list and every mutant class is identical to
campaign 2** (0 differences; `COMPARE-WITH-CAMPAIGN-2.json` → `impact`). So the runner's changes (signature, positional
audits, ps parser) moved no class on this sample; they did not alter classes of targets the campaign did not re-run
beyond this evidence, which is a sample, not a proof for the other 249.

## Campaign 2's 34 unresolved mutants (31 INFRA, 3 TIMEOUT)

All 34 are now measured, and every one of them is KILLED (matched by target and description without the line number;
a description with several occurrences lists all candidates, all KILLED): `COMPARE-WITH-CAMPAIGN-2.json` →
`unresolved`. The 3 TIMEOUTs became KILLED by confirmed FAILs of the fast-failing tests of round 1 (no timeout was
raised); the 31 INFRA (confine.wrap, cli.run) are real kills whose failure signatures differed only by a runner temp
name, which the signature fix removes.

## Survivors at this snapshot

242 SURVIVED. Against the positional audits at `f860e57`: 144 AUDITED, 56
EQUIVALENT, **42 unaudited** (`SURVIVORS-AUDIT-STATUS-AT-F860E57.json`). The 15 audit entries that no
longer match a survivor are mutants that are KILLED now; they are pruned from the audit file when round 2 is integrated.
Round 2 (the 42) is in `closure-evidence/v2/v2.1/mutation/ROUND-2.md`.

## The operator's real OpenCode store

Stat before/after (`store-before.json`, `store-after.json`): the only field that differs is
`.local/share/opencode/log.newest_entry_mtime_ns` (2026-10-11T12:02:06Z ->
2026-10-12T03:02:13Z); entry count and the directory's mtime are unchanged,
`opencode.db`, `auth.json`, the configuration are byte-stable. Attribution, measured (2026-10-11 and again after the
campaign): `opencode.log` is held open for writing by a helper process of `/Applications/OpenCode.app` (the Desktop
application, running for days, not started by this work; `lsof`), and its last lines are the application's own
project-refresh entries. No process of this campaign had an `opencode` binary on its PATH.
