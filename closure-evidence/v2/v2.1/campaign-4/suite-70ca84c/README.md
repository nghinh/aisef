# The full suite on the final candidate: 70ca84c (2026-10-12, hermetic)

Same procedure as `../suite-d62dcaa/README.md`: `tests/` via `python -m unittest discover -v -s tests` under `owned_run.py`,
exactly one commit (`rc-head-before.txt` = `rc-head-after.txt` = `70ca84c605bd742e07665c2336271bca44ef8da1`), fresh detached
worktree, `env -i`, no `opencode` on PATH, scratch HOME/XDG/TMPDIR, heavy lock; hermetic roots empty before and after,
worktree clean after; the operator's real OpenCode store differs only in the log directory's newest-entry mtime (the
Desktop application's own log). 12:24:31Z - 13:26:01Z (61 min).

**Ran 6,937 tests: 4 failures, 0 errors, 84 skipped.** All four are one fact — the V2.1 mutation record is FAIL for nine
survivors that are the owner's decisions — seen from four tests:

| test | why it is red |
|---|---|
| `p0.test_checker_calibration` ... `fails_it_for_the_named_reason` (checker `mutation`) | the checker's clean run on the real record fails (9 unaudited survivors) |
| `p0.test_checker_calibration` `every_checker_is_calibrated_and_the_committed_record_is_current` | 53/54 calibrated; `Q0-CHECKER-CALIBRATION.json` cannot be written while `mutation` is red |
| `test_c2_orchestration_conformance.Record.test_15` | the ruling's (e)/(f): the C2-P5 acceptance is not re-verified on 2.1 (Q0), the mutation summary is FAIL |
| `test_c2_p5_acceptance.Acceptance` | `C2-P5-ACCEPTANCE-REVERIFICATION.json` is not written: its guard `checker_calibration` exits 1 (`../q0/`) |

Compared with the first suite of the round (`../suite-d62dcaa`, 5 failures): K-NOWORK-001 is green (its record was
regenerated after the plan correction it binds). Compared with `8d2bf01`, 7 failures: the K-NOWORK, Q5, ruling and
`P5_8` records are on the final tree. Nothing was skipped, weakened or edited to turn a test green; the code tree is the
campaign-4 snapshot's (`b5c2457`): the commits since touch only `docs/v2.1/` (REPORT §0, STATUS) and `closure-evidence/`.
