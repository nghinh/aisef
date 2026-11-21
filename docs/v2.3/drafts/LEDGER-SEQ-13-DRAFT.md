# DRAFT — owner ledger entry seq 13 (ROUND-AUTH). Not evidence until the owner commits it.

The agent never writes `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`. If the owner approves, the owner (or the
agent on the owner's explicit instruction naming this entry) appends exactly this object as entry 13; entries 1–12
stay byte-identical (CT-5).

```json
{
 "seq": 13,
 "id": "AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED",
 "authority": "<owner's own words, quoted verbatim, with date and channel>",
 "approver": "human:owner",
 "decision": {
  "QUALIFICATION_ROUND": "v2.3",
  "BRANCH": "release/v2.3-big",
  "SCOPE": "re-derive round-v2.3 supersession records (append-only, closure-evidence/v2/v2.3/) for the currency-DAG nodes whose own guard fires, and a v2.3 CONFORMANCE-RULING whose rows name the v2.3 changes to validation/v2/mutation.py (F5) and aisef2/orchestrate/story_runner.py (E5)",
  "GATED_TEST_WIRING": "tests/v2/sealing_gate.py V22_REPLAYED: the 11 v2.2-round sealing-gated tests are replayed at v2.2.0 (validation/v23/replay_v22.py) and skipped at HEAD with that reason; their round-v2.3 counterparts are NEW gated tests (tests/v2/test_v23_rounds.py). This is the separate owner approval ledger seq 8 (C4_SEPARATE) reserves; no automatic migration.",
  "NOT_AUTHORIZED": "rewriting any v2.2 or earlier record; publishing; tagging; any change of the v2.2.0 ledger entries 1-12"
 },
 "subject_to": "W1-DESIGN.md §2.6 (F5-ROUND) and §11 gate 3: the v2.2 round replays byte-identically at v2.2.0 and the Q0 record stays byte-identical",
 "cost": "USD 0"
}
```

Why it is needed: W1-DESIGN.md §12 ROUND-AUTH — the v2.3 conformance ruling must quote a committed owner authority
(`v21_conformance_ruling.py:334-337`, `p5_acceptance.py:117-124` refuse uncommitted authority); seq 1–12 cover v2.2 only.
