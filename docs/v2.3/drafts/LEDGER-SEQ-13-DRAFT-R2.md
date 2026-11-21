# DRAFT R2 — owner ledger entry seq 13 (ROUND-AUTH). Not evidence until the owner commits it.

Status: owner CONDITIONAL HOLD. The principle of a separate v2.3 qualification round is approved; this draft is
**not** authorized for the ledger. R1 (`LEDGER-SEQ-13-DRAFT.md`, ruling digest
`824091110a8bb0fcf8726e889f4ff0c3f11e8f102dfa18f028e343a968caa79b`) stays unchanged as the record of what was first
proposed. The evidence the owner asked for before any ratification request is in `ROUND-AUTH-PARITY.md`.

The agent never writes `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`. If the owner approves, the owner (or the
agent on the owner's explicit instruction naming this entry and this digest) appends exactly this object as entry 13,
replacing only the `authority` placeholder with the owner's own words; entries 1–12 stay byte-identical (CT-5).

```json
{
 "seq": 13,
 "id": "AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED",
 "authority": "<owner's own words, quoted verbatim, with date and channel>",
 "approver": "human:owner",
 "decision": {
  "QUALIFICATION_ROUND": "v2.3",
  "BRANCH": "release/v2.3-big",
  "SCOPE": "re-derive round-v2.3 supersession records, append-only as new files (never in place of a v2.2 or earlier record), for the currency-DAG nodes whose own guard fires, and a v2.3 CONFORMANCE-RULING whose rows name the v2.3 changes to validation/v2/mutation.py (F5) and aisef2/orchestrate/story_runner.py (E5)",
  "GATED_TEST_WIRING": "exactly docs/v2.3/drafts/SEQ13-WIRING.patch (sha256 c5bfc527182c9f5969532630b680b98e746c867ebf351e28e3b5c4e5c2bbd68b), which changes tests/v2/sealing_gate.py only: V22_REPLAYED names the 11 v2.2-round sealing-gated tests of validation/v23/replay_v22.py, and `sealing` becomes a function that skips those 11 at HEAD naming the replay; GATED, the 18 gated test files and tests/v2/test_sealing_gate.py stay byte-identical. The 11 run at v2.2.0 through tests/v23/test_v23_rounds.py::RoundV23.test_replay_v22; their round-v2.3 counterparts are tests/v23/test_v23_rounds.py::RoundV23, under the round's own closed list V23_GATED. This is the separate owner approval ledger seq 8 (C4_SEPARATE) reserves; no automatic migration.",
  "SEALING_GATE": "the tests.yml sealing job, which release.yml requires through its tests job, is green for round v2.3 only when RoundV23 (the 11 counterparts, each with its node MEASURED or VERIFIED_REUSE; the v2.2.0 replay; the in-tree v2.2-selection companion) and Seq13Wiring pass; no allowlist, exception or skip opens it",
  "EVIDENCE_REVIEWED": "docs/v2.3/evidence/round-auth/: REPLAY-V22-2026-11-21.json e7ef54c745b35ae709cc6fd591e9a42767899956defc4db1688c4ac48f33f8ae; COVERAGE-MAP-2026-11-21.json 2bb5b5501b7ab966cef61ca13ca5bbbe4c40f9692284bce037e21ef4e9bd8c8d; NEGATIVE-CONTROLS-2026-11-21.json 15087001cd877db180ea51f72be8db7b34aa103b99ac3fd4ea0e7ee013270969; HISTORY-IDENTITY-2026-11-21.json cc18861af3712821335c16ebbdc31604cef974d7006f726ab840dad2d9dad91f",
  "NOT_AUTHORIZED": "rewriting any v2.2 or earlier record; publishing; tagging; any change of the v2.2.0 ledger entries 1-12; any edit of the 18 sealing-gated test files, of GATED or of tests/v2/test_sealing_gate.py; any wiring other than the named patch; any allowlist or exception that lets the sealing job pass with a red counterpart or replay"
 },
 "subject_to": "W1-DESIGN.md §2.6 (F5-ROUND) and §11 gate 3: the v2.2 round replays at v2.2.0 inside the mandatory sealing job (replay_v22.py exit 0: all 11 PASS, every record read equal to its v2.2.0 committed bytes) and the Q0 record stays byte-identical; the v2.3 round is current only when every RoundV23 counterpart passes",
 "cost": "USD 0"
}
```

canonical ruling digest: `a7fa9f97c6a324f3f1d53df2ca42cd8c46135751977bcdafa5c3d63716daa940`. It is the sha256 of
`json.dumps({seq, id, decision, subject_to, cost}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` in UTF-8,
recomputed by `python3 -P validation/v23/ledger_digest.py docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R2.md` (tested by
`tests/v23/test_v23_ledger_digest.py`).

## Changes vs R1 (each: what, why)

| Field | R1 | R2 | Why |
|---|---|---|---|
| `SCOPE` | records under `closure-evidence/v2/v2.3/` | location-free: "append-only as new files, never in place of a v2.2 or earlier record" | The integrator's Amendment A2 places new evidence under `closure-evidence/v2.3/<topic>/`, which is inside the V1 evidence guard's protected set (every tracked file under `closure-evidence/` except `closure-evidence/v2/`; measured: an addition there turns `tests/v2/test_v1_evidence_guard.py` red and moves Q0 to 56/57). W1-DESIGN §2.6 `load_series` names `closure-evidence/v2/v2.3/`. The ruling should not settle a mechanism detail, so it binds the property (append-only, new files) instead. **Open:** L1-F5 / the integrator fix the path. |
| `GATED_TEST_WIRING` | `V22_REPLAYED` in `sealing_gate.py`; counterparts "NEW gated tests (`tests/v2/test_v23_rounds.py`)" | the exact patch, by sha256; `sealing_gate.py` only; GATED, the 18 files and `test_sealing_gate.py` byte-identical; counterparts at `tests/v23/test_v23_rounds.py::RoundV23` under `V23_GATED` | (a) A2 placement moves new tests to `tests/v23/`. (b) W1-DESIGN §7 keeps GATED byte-identical and `test_sealing_gate.py` unedited, but its regex admits only `tests/v2/` ids: the counterparts therefore keep their own gate (`round_gate`, the same `AISEF_SEALING=1` switch) and their own closed list, with an always-run AST closure test. (c) Naming the patch by digest makes the approval exact: any other wiring is outside it. |
| `SEALING_GATE` | — | new | States what opens the release path and that nothing else does, including no allowlist and no exception. |
| `EVIDENCE_REVIEWED` | — | new | Binds the approval to the four evidence files the owner reviewed, by sha256. `ROUND-AUTH-PARITY.md` is cited by path only, because it quotes this digest. |
| `NOT_AUTHORIZED` | records, publish, tag, entries 1–12 | adds: no edit of the 18 gated files, GATED or `test_sealing_gate.py`; no other wiring; no allowlist or exception | Closes the routes by which a sealing check could be weakened under this entry. |
| `subject_to` | replay "byte-identically" + Q0 byte-identical | the same, made operational: replay exit 0 inside the mandatory job, all 11 PASS, every record read equal to its committed bytes; v2.3 current only when every counterpart passes | "Byte-identically" now has a measured meaning. The committed-bytes rule matters: the negative control shows that `test_15` alone misses a one-character change of its cycle-2 record (ROUND-AUTH-PARITY.md §4a). |
| `seq`, `id`, `authority`, `approver`, `QUALIFICATION_ROUND`, `BRANCH`, `cost` | — | unchanged | `authority` stays a placeholder for the owner's own words. There is no signature and no approval date. |

## What approval would and would not do

* It would let the patch be applied (`git apply docs/v2.3/drafts/SEQ13-WIRING.patch`, commit on the branch). It would
  then turn `Seq13Wiring` green. The 11 counterparts stay red until the round-v2.3 selection of W1-DESIGN §2.6 lands
  (lane L1-F5: `version_forward.in_round`, `currency_dag.validate(round=…)`, measured: neither exists at the code
  commit) and each node is MEASURED or VERIFIED_REUSE.
* It authorizes no record, no publish and no tag. Committing the entry is the owner's act.
