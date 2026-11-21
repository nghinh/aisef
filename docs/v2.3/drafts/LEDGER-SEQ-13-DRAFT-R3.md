# DRAFT R3 — owner ledger entry seq 13 (ROUND-AUTH). Not evidence until the owner commits it.

Status: owner CONDITIONAL HOLD. The principle of a separate v2.3 qualification round is approved; this draft is
**not** authorized for the ledger. R1 (`LEDGER-SEQ-13-DRAFT.md`, ruling digest
`824091110a8bb0fcf8726e889f4ff0c3f11e8f102dfa18f028e343a968caa79b`) and R2 (`LEDGER-SEQ-13-DRAFT-R2.md`, ruling digest
`a7fa9f97c6a324f3f1d53df2ca42cd8c46135751977bcdafa5c3d63716daa940`) stay unchanged as the record of what was proposed.
**R2 must not be ratified:** its wiring patch (`SEQ13-WIRING.patch`, sha256 `c5bfc527…`) skips the 11 v2.2 tests
unconditionally (review finding RA-GP-1), and its round check accepts any seq 13 with the right id (RA-INT-2). R3 fixes
both; the evidence is `ROUND-AUTH-PARITY.md` §7.

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
  "SCOPE": "re-derive round-v2.3 supersession records, append-only as new files (never in place of a v2.2 or earlier record), for the currency-DAG nodes whose own guard fires, and a v2.3 CONFORMANCE-RULING whose rows name the v2.3 changes to validation/v2/mutation.py (F5) and aisef2/orchestrate/story_runner.py (E5)",
  "GATED_TEST_WIRING": "exactly docs/v2.3/drafts/SEQ13-WIRING-R3.patch (sha256 40e6b57adff814933c863c14b3e32a413b5f7b79a8bf0d187889e5635ea1cca5), which changes tests/v2/sealing_gate.py only: V22_REPLAYED names the 11 v2.2-round sealing-gated tests of validation/v23/replay_v22.py; V23_PINNED pins, by the sha256 of their LF bytes, tests/v23/__init__.py, tests/v23/test_v23_rounds.py, validation/v23/ledger_digest.py and validation/v23/replay_v22.py; `sealing` becomes a function that skips those 11 at HEAD, naming the replay, only while every pinned file is exactly as pinned, and otherwise lets them run under AISEF_SEALING=1 as before. GATED, the 18 gated test files and tests/v2/test_sealing_gate.py stay byte-identical. The 11 run at v2.2.0 through tests/v23/test_v23_rounds.py::RoundV23.test_replay_v22; their round-v2.3 counterparts are tests/v23/test_v23_rounds.py::RoundV23, under the round's own closed list V23_GATED; Seq13Wiring requires tests/v2/sealing_gate.py to be exactly v2.2.0's plus this patch. This is the separate owner approval ledger seq 8 (C4_SEPARATE) reserves; no automatic migration.",
  "SEALING_GATE": "the tests.yml sealing job, which release.yml requires through its tests job, is green for round v2.3 only when RoundV23 (the 11 counterparts, each with its node MEASURED or VERIFIED_REUSE; the v2.2.0 replay; the in-tree v2.2-selection companion) and Seq13Wiring pass; the round is open only for exactly one committed seq 13 whose canonical ruling digest is this draft's and whose authority, the owner's own words and not a placeholder, quotes that digest; no allowlist, exception or skip opens it",
  "EVIDENCE_REVIEWED": "docs/v2.3/evidence/round-auth/: REPLAY-V22-2026-11-21.json e7ef54c745b35ae709cc6fd591e9a42767899956defc4db1688c4ac48f33f8ae; COVERAGE-MAP-2026-11-21.json 2bb5b5501b7ab966cef61ca13ca5bbbe4c40f9692284bce037e21ef4e9bd8c8d; NEGATIVE-CONTROLS-2026-11-21.json 15087001cd877db180ea51f72be8db7b34aa103b99ac3fd4ea0e7ee013270969; HISTORY-IDENTITY-2026-11-21.json cc18861af3712821335c16ebbdc31604cef974d7006f726ab840dad2d9dad91f; and the review findings RA-GP-1 and RA-INT-2, fixed fail-closed with their regression tests tests/v23/test_v23_seq13_wiring.py (docs/v2.3/drafts/ROUND-AUTH-PARITY.md §7)",
  "NOT_AUTHORIZED": "rewriting any v2.2 or earlier record; publishing; tagging; any change of the v2.2.0 ledger entries 1-12; any edit of the 18 sealing-gated test files, of GATED or of tests/v2/test_sealing_gate.py; any wiring other than the named patch; any allowlist or exception that lets the sealing job pass with a red counterpart or replay; re-pinning or removing V23_PINNED; any change of this draft after it is committed (a later ruling is a new draft file)"
 },
 "subject_to": "W1-DESIGN.md §2.6 (F5-ROUND) and §11 gate 3: the v2.2 round replays at v2.2.0 inside the mandatory sealing job (replay_v22.py exit 0: all 11 PASS, every record read equal to its v2.2.0 committed bytes) and the Q0 record stays byte-identical; the v2.3 round is current only when every RoundV23 counterpart passes",
 "cost": "USD 0"
}
```

canonical ruling digest: `72e296b6b2f991e7f66a82bcebb9baff3bf337954b722316defa16db94a2dd9f`. It is the sha256 of
`json.dumps({seq, id, decision, subject_to, cost}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` in UTF-8,
recomputed by `python3 -P validation/v23/ledger_digest.py docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R3.md` (tested by
`tests/v23/test_v23_ledger_digest.py`).

## Changes vs R2 (each: what, why)

| Field | R2 | R3 | Why |
|---|---|---|---|
| `GATED_TEST_WIRING` | `SEQ13-WIRING.patch` (`c5bfc527…`): the 11 are skipped unconditionally | `SEQ13-WIRING-R3.patch` (`40e6b57adff814933c863c14b3e32a413b5f7b79a8bf0d187889e5635ea1cca5`): `V23_PINNED` pins the four files the skip stands on; the skip holds only while every pin holds, otherwise the 11 run under `AISEF_SEALING=1`; `Seq13Wiring` requires `sealing_gate.py` = v2.2.0's + this patch | RA-GP-1: with R2's patch, deleting `tests/v23/test_v23_rounds.py` (or a one-line edit of `round_gate`) dropped all 11 controls and the replay, and the sealing job stayed green (measured by the reviewer and re-measured, §7). |
| `SEALING_GATE` | what opens the release path | adds: the round is open only for exactly one committed seq 13 whose canonical ruling digest is this draft's and whose `authority` quotes it | RA-INT-2: R2's round check accepted the placeholder, R1, a minimal entry, or a doctored decision (measured, §7). |
| `EVIDENCE_REVIEWED` | four evidence files by sha256 | the same four, plus the two findings and their regression tests, by path | The fix is part of what the owner reviews. |
| `NOT_AUTHORIZED` | R2's list | adds: re-pinning or removing `V23_PINNED`; any change of this draft once committed | Closes re-pinning as a route to a silent skip; a later ruling is a new file, so the committed draft stays the reviewed text (`reviewed_draft` refuses a draft whose blob differs from the commit that added it). |
| `authority` (outside the digest) | placeholder | placeholder that asks for the digest | The round check requires the owner's words to quote the ruling digest: that is how "the ruling the owner approves" is bound without a constant (a constant in the pinned file would be a hash cycle: this ruling names the patch, and the patch pins that file). |
| `seq`, `id`, `approver`, `QUALIFICATION_ROUND`, `BRANCH`, `SCOPE`, `subject_to`, `cost` | — | unchanged | No signature and no approval date. |

## What approval would and would not do

* It would let `SEQ13-WIRING-R3.patch` be applied (`git apply docs/v2.3/drafts/SEQ13-WIRING-R3.patch`, commit on the
  branch). That turns `Seq13Wiring` green. The 11 counterparts stay red until the round-v2.3 selection of W1-DESIGN §2.6
  lands (lane L1-F5: `version_forward.in_round`, `currency_dag.validate(round=…)`; neither exists today) and each node is
  MEASURED or VERIFIED_REUSE.
* Any later edit of a pinned file (for example to follow L1-F5's interface) un-skips the 11 and needs a new patch and a
  new ruling (R4). That is the intended cost of an exact approval.
* It authorizes no record, no publish and no tag. Committing the entry is the owner's act.
