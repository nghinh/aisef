# The full suite at d62dcaa (2026-10-12, hermetic)

`tests/` via `python -m unittest discover -v -s tests` under `validation/v2/owned_run.py`, exactly one commit
(`rc-head-before.txt` = `rc-head-after.txt` = `d62dcaaeb70245963de064b5a0a5493a16170e43`), a fresh detached worktree,
`env -i`, PATH without any directory holding `opencode`, scratch HOME/XDG/TMPDIR, the machine-wide heavy lock; before/after
proofs of the hermetic roots (`hermetic-proof-*.json`: nothing written) and of the operator's real OpenCode store
(`real-store-*.json`: the only difference is `.local/share/opencode/log` `newest_entry_mtime_ns`, the Desktop application's
own log, held open for writing by its helper process). 11:04:06Z - 12:08:03Z (64 min). Worktree status after: clean.

**Ran 6,937 tests: 5 failures, 0 errors, 84 skipped.** The five, each with its cause:

| test | why it is red |
|---|---|
| `p0.test_checker_calibration` ... `fails_it_for_the_named_reason` (checker `mutation`) | the checker's clean run on the real record fails: nine unaudited survivors (the owner's four questions) |
| `p0.test_checker_calibration` `every_checker_is_calibrated_and_the_committed_record_is_current` | 53/54 calibrated; `Q0-CHECKER-CALIBRATION.json` cannot be written while `mutation` is red |
| `test_c2_k_nowork_001.Record` | **the lead's ordering error, repaired afterwards**: the record was generated before PLAN-V2.2-CORRECTION-1 was regenerated on the final tree and binds it by digest; K-NOWORK, Q5 and the ruling were regenerated in dependency order in the commits after this one |
| `test_c2_orchestration_conformance.Record.test_15` | the ruling's (e)/(f): the C2-P5 acceptance is not re-verified on 2.1 (blocked by Q0) and the mutation summary is FAIL |
| `test_c2_p5_acceptance.Acceptance` | `C2-P5-ACCEPTANCE-REVERIFICATION.json` is not written: its guard `checker_calibration` exits 1 (`campaign-4/q0/`) |

Nothing was skipped, weakened or edited to make a test pass; the 84 skips are the ones of the earlier suites (platform
and opt-in tests).
