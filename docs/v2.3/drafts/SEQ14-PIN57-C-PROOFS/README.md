# SEQ14-PIN57-C proof transcripts (2026-11-26)

Measured in a worktree at HEAD `50960ffa1f398a0ae112a38f70540d65d7bbfa33` (release/v2.3-big) with
`docs/v2.3/drafts/SEQ14-PIN57-C.patch` (sha256 `ed7a55d89368707dc1897d191a6e1fdd70ad8f5b70ab74ffec9dc21e4236baac`)
applied for every "AFTER" transcript, then reverted. Each file records its exact command and exit code.
Owner ruling 2026-11-26 §3 authorized development and testing of the amendment; landing it is the owner's act.

| file | what it proves |
|---|---|
| `a-red-before.txt` | red-before on the clean tree: no test references `V23_CHECKERS`, the three known-bad fixtures or the checker names; `len(cc.REGISTRY) == 57`; Q0P-2 names 8 uncovered modules (the 4 PIN-57 modules + the 4 ground_truth files) |
| `b1-q0-round-sealing.txt` | `AISEF_SEALING=1 python3 -m unittest tests.v23.test_v23_q0_round -v` AFTER: the re-pinned assertions pass; the ONLY reds are the Q0RoundV23 tests carrying the three known waits (OD-B1B, P5-PROPOSAL currency, F5 cut-over) and the still-unwritten round record — they REMAIN visible per the ruling |
| `b2-unregistered-checkers.txt` | the new always-run drift pins (`tests/v23/test_v23_unregistered_checkers.py`): 5/5 green |
| `b3-seq13-wiring.txt` | `tests/v23/test_v23_seq13_wiring.py` 19/19 green, including the two seq-14 arms (the patch's closed file set + draft sha; the seq-13 patch alone now skips nothing, like R2–R5 before it) |
| `b4-wiring-sealing.txt` | `Seq13Wiring` + `Q0Wiring` green under `AISEF_SEALING=1`: sealing_gate.py == v2.2.0 + SEQ13-WIRING-R6.patch + the seq-14 patch's sealing_gate hunks, and every V23_PINNED pin holds |
| `b5-q0-check-after.txt` | `python3 -P validation/v23/q0_round.py --check` AFTER: exit 1, fail-closed; FAIL lines are exactly the three uncalibrated waits, their three dropped() lines, `calibrated 56 of 59`, and the missing round record; the eight Q0P-2 scope lines are GONE; delta prints `+ f5_gate`, `+ released_evidence` for owner review |
| `c-replay-v22.txt` | `python3 -P validation/v23/replay_v22.py` AFTER: the v2.2.0 replay is UNCHANGED (PASS) |
| `d-calibrate-new-checkers.txt` | `cc.calibrate` of the two newly registered checkers against their committed known-bad fixtures: clean passes, fixture rejected for the named reason, always-PASS mutant rejected |
| `ruff-touched-files.txt` | `ruff check` over all seven touched files: clean |

Also run (not captured to a file, green): `tests.test_meta` (34 tests — the new test file passes the encoding scans),
`tests.v2.test_sealing_gate`, `tests.v23.test_v23_rounds.Coverage`, `tests.v23.test_v23_rounds.LedgerHistory`,
`tests.v23.test_v23_ledger_digest` (18 tests together).
