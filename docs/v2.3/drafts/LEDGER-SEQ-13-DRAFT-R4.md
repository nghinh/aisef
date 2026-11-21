# DRAFT R4 — owner ledger entry seq 13 (ROUND-AUTH + Q0-1). Not evidence until the owner commits it.

Status: owner CONDITIONAL HOLD. The owner approved (2026-11-22) the architectural direction of a distinct v2.3 Q0
qualification round, without modifying or invalidating the historical v2.2 Q0 record; this draft is **not** authorized
for the ledger. R1 (`LEDGER-SEQ-13-DRAFT.md`, `824091110a8bb0fcf8726e889f4ff0c3f11e8f102dfa18f028e343a968caa79b`), R2
(`LEDGER-SEQ-13-DRAFT-R2.md`, `a7fa9f97c6a324f3f1d53df2ca42cd8c46135751977bcdafa5c3d63716daa940`) and R3
(`LEDGER-SEQ-13-DRAFT-R3.md`, `72e296b6b2f991e7f66a82bcebb9baff3bf337954b722316defa16db94a2dd9f`) stay unchanged as the record of what was proposed.
**R4 supersedes R3; R3 must not be ratified.** R3's wiring does not cover Q0: under R3 the v2.2 Q0 test stays the
only Q0 control at HEAD and turns red on the first W1a L1-AUTHCHK or W1b edit (the measured delta in
`docs/v2.3/amendments/Q0-1-V23-ROUND.md`). R3's pins also no longer hold on this tree, so applied now it would skip
none of the 11 either (`tests/v23/test_v23_seq13_wiring.py::WiringR4.test_R3s_patch_never_skips_q0_and_on_this_tree_skips_nothing`).

The agent never writes `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`. If the owner approves, the owner (or the
agent on the owner's explicit instruction naming this entry and this digest) appends exactly this object as entry 13,
replacing only the `authority` placeholder with the owner's own words, which must quote the digest below; entries 1–12
stay byte-identical (CT-5).

```json
{
 "seq": 13,
 "id": "AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED",
 "authority": "<owner's own words, quoted verbatim, with date and channel, naming the ruling digest stated below this block>",
 "approver": "human:owner",
 "decision": {
  "QUALIFICATION_ROUND": "v2.3",
  "BRANCH": "release/v2.3-big",
  "SCOPE": "re-derive round-v2.3 supersession records, append-only as new files (never in place of a v2.2 or earlier record), for the currency-DAG nodes whose own guard fires, and a v2.3 CONFORMANCE-RULING whose rows name the v2.3 changes to validation/v2/mutation.py (F5) and aisef2/orchestrate/story_runner.py (E5); and the round-v2.3 Q0 calibration record docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json, written once as a new file by validation/v23/q0_round.py --write (never under closure-evidence/), beside the v2.2 Q0 record closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json, which stays history",
  "Q0_ROUND": "round v2.3 has its own Q0 qualification round: validation/v2/checker_calibration.run() on the HEAD tree inside version_forward.in_round('v2.3') (validation/v23/q0_round.py), recorded in docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json. The v2.2 Q0 record closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json (sha256 714625b14e8972f166b37a467b5f83761d1f2672d076e5f5f0f342e2eb91332c) and its GATED test tests/v2/p0/test_checker_calibration.py::CheckerCalibration stay byte-identical as history and are replayed at v2.2.0, where the record the replayed run derives must be byte-identical to the committed one. A v2.3 edit that moves a Q0 clean result (docs/v2.3/amendments/Q0-1-V23-ROUND.md, delta table: b1_bindings from the first edit of aisef2/app/run.py; mutation and currency_dag on any kernel or target-source edit until their round-v2.3 rules land; uncovered_checker_modules for any new validation/v2 module) keeps round v2.3 red until that checker is calibrated again in round v2.3. This entry relaxes no checker, fixture or expected reason and decides none of the owner decisions that table names (OD-Q0-1-W1B, OD-B1B, OD-NEWMOD)",
  "GATED_TEST_WIRING": "exactly docs/v2.3/drafts/SEQ13-WIRING-R4.patch (sha256 a0f79fc19b0841d22cf6800051dd4dfddeab21b3860d38f1587c89f61fa24254), which changes tests/v2/sealing_gate.py only: V22_REPLAYED names the 11 v2.2-round sealing-gated tests of validation/v23/replay_v22.py; V22_REPLAYED_Q0 names the v2.2 round's GATED Q0 calibration class tests/v2/p0/test_checker_calibration.py::CheckerCalibration (replay_v22.Q0_REPLAYED); V23_PINNED pins, by the sha256 of their LF bytes, tests/v23/__init__.py, tests/v23/test_v23_q0_round.py, tests/v23/test_v23_rounds.py, validation/v23/ledger_digest.py, validation/v23/q0_round.py and validation/v23/replay_v22.py; `sealing` becomes a function that skips those 12 at HEAD, naming the replay, only while every pinned file is exactly as pinned, and otherwise lets them run under AISEF_SEALING=1 as before. GATED, the 18 gated test files and tests/v2/test_sealing_gate.py stay byte-identical. The 12 run at v2.2.0 through tests/v23/test_v23_rounds.py::RoundV23.test_replay_v22; their round-v2.3 counterparts are tests/v23/test_v23_rounds.py::RoundV23 and tests/v23/test_v23_q0_round.py::Q0RoundV23, under the round's own closed list V23_GATED; Seq13Wiring requires tests/v2/sealing_gate.py to be exactly v2.2.0's plus this patch, and Seq13Wiring and Q0Wiring each require every pin to hold. This is the separate owner approval ledger seq 8 (C4_SEPARATE) reserves; no automatic migration.",
  "SEALING_GATE": "the tests.yml sealing job, which release.yml requires through its tests job, is green for round v2.3 only when RoundV23 (the 11 counterparts, each with its node MEASURED or VERIFIED_REUSE; the v2.2.0 replay of the 11 and of the Q0 class, whose derived record must be byte-identical to the committed one; the in-tree v2.2-selection companion), Seq13Wiring, Q0RoundV23 (the v2.2 Q0 class's nine tests, verbatim, on the HEAD tree in round v2.3: every registered checker calibrated, none of the v2.2 record's checkers dropped, the v2.2 Q0 record still its v2.2.0 bytes, and the round-v2.3 Q0 record present and equal to what the HEAD tree derives) and Q0Wiring pass; the round is open only for exactly one committed seq 13 whose canonical ruling digest is this draft's and whose authority, the owner's own words and not a placeholder, quotes that digest; no allowlist, exception or skip opens it",
  "EVIDENCE_REVIEWED": "docs/v2.3/evidence/round-auth/: REPLAY-V22-2026-11-21.json e7ef54c745b35ae709cc6fd591e9a42767899956defc4db1688c4ac48f33f8ae; COVERAGE-MAP-2026-11-21.json 2bb5b5501b7ab966cef61ca13ca5bbbe4c40f9692284bce037e21ef4e9bd8c8d; NEGATIVE-CONTROLS-2026-11-21.json 15087001cd877db180ea51f72be8db7b34aa103b99ac3fd4ea0e7ee013270969; HISTORY-IDENTITY-2026-11-21.json cc18861af3712821335c16ebbdc31604cef974d7006f726ab840dad2d9dad91f; and the review findings RA-GP-1 and RA-INT-2, fixed fail-closed with their regression tests tests/v23/test_v23_seq13_wiring.py (docs/v2.3/drafts/ROUND-AUTH-PARITY.md §7); for Q0-1, docs/v2.3/evidence/q0-round/: REPLAY-V22-Q0-2026-11-21.json 0f8bd55cd078e38115976c0c3d68fcf89f70fa37698654e048d5457e886e513c; COVERAGE-MAP-2026-11-21.json 644d874c610a8c8315554db2e402ac8bad9fa51d6006aaa902680714e054fc2c; Q0-DELTA-2026-11-21.json f885b37454f99fa51c332c46fab9ee54b6e84876c5654a9ac4697d94f582ad54; NEGATIVE-CONTROLS-2026-11-21.json 6ee4f872d35da24fb5c1ff6027584d22208e97f74f4ff3b107d3d9571550bea8; the design and delta table docs/v2.3/amendments/Q0-1-V23-ROUND.md (docs/v2.3/drafts/ROUND-AUTH-PARITY.md §8)",
  "NOT_AUTHORIZED": "rewriting any v2.2 or earlier record; publishing; tagging; any change of the v2.2.0 ledger entries 1-12; any edit of the 18 sealing-gated test files, of GATED or of tests/v2/test_sealing_gate.py; any wiring other than the named patch; any allowlist or exception that lets the sealing job pass with a red counterpart or replay; re-pinning or removing V23_PINNED; any change of this draft after it is committed (a later ruling is a new draft file); rewriting, regenerating, moving or deleting the v2.2 Q0 record closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json; any edit of tests/v2/p0/test_checker_calibration.py; relaxing a Q0 checker (removing a rule, a registry entry, a known-bad fixture or its expected reason) to make round v2.3 green; any round-v2.3 Q0 record under closure-evidence/; deciding OD-Q0-1-W1B, OD-B1B or OD-NEWMOD (each stays the owner's)"
 },
 "subject_to": "W1-DESIGN.md §2.6 (F5-ROUND) and §11 gate 3, as amended by docs/v2.3/amendments/Q0-1-V23-ROUND.md: the v2.2 round replays at v2.2.0 inside the mandatory sealing job (replay_v22.py exit 0: all 11 and the Q0 class PASS, every record read equal to its v2.2.0 committed bytes, and the Q0 record the replayed run derives byte-identical to the committed one); the v2.2 Q0 record stays byte-identical at HEAD; the v2.3 round is current only when every RoundV23 and Q0RoundV23 test passes",
 "cost": "USD 0"
}
```

canonical ruling digest: `8db40e8c65c0094b36812ff6338819e8afbe91388e8f058647ae935a6978d63b`. It is the sha256 of
`json.dumps({seq, id, decision, subject_to, cost}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` in UTF-8,
recomputed by `python3 -P validation/v23/ledger_digest.py docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R4.md` (tested by
`tests/v23/test_v23_ledger_digest.py`).

## Changes vs R3 (each: what, why)

| Field | R3 | R4 | Why |
|---|---|---|---|
| `SCOPE` | the round-v2.3 supersession records and the v2.3 CONFORMANCE-RULING | adds the round-v2.3 Q0 record `docs/v2.3/evidence/q0-round/Q0-CHECKER-CALIBRATION-V23.json`, a new file written once, beside the v2.2 Q0 record | The owner approved a distinct v2.3 Q0 round that leaves the v2.2 record untouched; the round needs a record of its own. |
| `Q0_ROUND` | — (new field) | what the round-v2.3 Q0 is, what stays history, and that a moved clean result keeps the round red | Makes the Q0 boundary part of the ruling's digest: the owner approves exactly this rule, and that it relaxes nothing and decides no named owner decision. |
| `GATED_TEST_WIRING` | `SEQ13-WIRING-R3.patch` (`40e6b57a…`), 4 pins, the 11 | `SEQ13-WIRING-R4.patch` (`a0f79fc19b0841d22cf6800051dd4dfddeab21b3860d38f1587c89f61fa24254`): adds `V22_REPLAYED_Q0` (the Q0 class), 6 pins (adds `tests/v23/test_v23_q0_round.py`, `validation/v23/q0_round.py`; re-pins `test_v23_rounds.py` and `replay_v22.py`, which R4 changed) | The Q0 test joins the replayed set only together with its pinned v2.3 counterpart: deleting or editing either file un-skips all 12 (measured, parity §8). |
| `SEALING_GATE` | RoundV23, Seq13Wiring | adds the Q0 replay (byte-identical regenerated record), `Q0RoundV23` and `Q0Wiring` | The gate a release passes must hold the Q0 round. |
| `EVIDENCE_REVIEWED` | four round-auth files and RA-GP-1/RA-INT-2 | adds the four Q0-1 evidence files by sha256, and the amendment and parity §8 by path | Those two pages are named by path only: parity §8 quotes this digest, so a sha256 of it here would be a hash cycle. |
| `NOT_AUTHORIZED` | R3's list | adds: touching the v2.2 Q0 record or its test; relaxing a Q0 checker; a round-v2.3 Q0 record under `closure-evidence/`; deciding OD-Q0-1-W1B / OD-B1B / OD-NEWMOD | Keeps the v2.2 record immutable and the Q0 decisions with the owner. |
| `subject_to` | the 11 replay and "the Q0 record stays byte-identical" | the 11 and the Q0 class replay, with the regenerated record byte-identical; round v2.3 also needs Q0RoundV23 | States Q0 identity as measured, in the right round. |
| `seq`, `id`, `approver`, `authority`, `QUALIFICATION_ROUND`, `BRANCH`, `cost` | — | unchanged | No signature and no approval date. |

## What approval would and would not do

* It would let `SEQ13-WIRING-R4.patch` be applied (`git apply docs/v2.3/drafts/SEQ13-WIRING-R4.patch`, commit on the
  branch). That turns `Seq13Wiring` and `Q0Wiring` green. The 11 counterparts stay red until the round-v2.3 selection of
  W1-DESIGN §2.6 lands (lane L1-F5: `version_forward.in_round`, `currency_dag.validate(round=…)`) and each node is
  MEASURED or VERIFIED_REUSE; `Q0RoundV23` stays red until then too, and until the round-v2.3 Q0 record is written
  (`python3 -P validation/v23/q0_round.py --write`, which refuses while the round is closed or any checker is
  uncalibrated) and committed.
* It decides nothing about the checkers a v2.3 edit moves: from the first W1b edit of `aisef2/app/run.py`,
  `b1_bindings` is uncalibrated in both rounds (measured), and round v2.3 stays red until the owner rules OD-Q0-1-W1B /
  OD-B1B. Final E5 qualification therefore still waits at the Q0-1 decision boundary.
* Any later edit of a pinned file un-skips the 12 and needs a new patch and a new ruling (R5).
* It authorizes no record, no publish and no tag. Committing the entry is the owner's act.
