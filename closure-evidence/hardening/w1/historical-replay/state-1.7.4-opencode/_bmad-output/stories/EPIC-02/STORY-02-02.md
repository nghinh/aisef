# STORY-02-02: Deterministic snapshot sorted by NFC key

## Acceptance Criteria

1. [AC-STORY-02-02-1] Given `put("a", 1, r, t)`, `put("c", 3, r, t)`, `put("b", 2, r, t)` written in that order, two calls to `snapshot()` with no intervening mutations return equal dicts and `json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` lists keys in `a, b, c` order.
2. [AC-STORY-02-02-2] Given `put("k", "v", r1, t1)` followed by `delete("k", r2, t2)`, `snapshot()` returns a dict with no key `"k"`.
3. [AC-STORY-02-02-3] Given `put("e\u0301", "v", r, t)` (NFD form) and a follow-up `put("\u00e9", "v2", r, t)` with the same `rid` (idempotent replay), `snapshot()` returns a dict with the NFC key `"\u00e9"` and value `"v"`.
4. [AC-STORY-02-02-4] Given two `Ledger` instances opened in succession over the same on-disk chain, each `snapshot()` returns equal dicts.

## Recorded Scope

- `ledgerlock/ledger.py`
- `tests/test_snapshot_determinism.py`

Harness added because the story's verification contract requires them (error 21):
- `tests`
- `test`
- `pytest.ini`
- `conftest.py`

Guard blocks all writes outside this list. Needing to write elsewhere means the scope declaration is wrong — stop and report, do not work around it.

## Definition of Done

This story must pass the following verification types. Types not configured on the project are **not** counted as passing — they are gaps, and the gate will flag them.

- `unit`

## Dependencies

- STORY-02-01

## Requirements

### FR-9: Deterministic snapshot

`Ledger.snapshot()` and `ledgerlock snapshot --out <file>` MUST return a JSON document where (a) the top-level object has one entry per key whose most recent committed mutation is a live `put`; (b) the keys are NFC-normalized; (c) the keys are sorted in UTF-8 codepoint order; (d) the value is the JSON value from the most recent live `put` on that key. Tombstoned keys are absent.

Verifiable Consequences:

- Two snapshots taken from the same chain (no intervening mutations)
- A snapshot of a chain containing keys `"a"`, `"c"`, `"b"` in
- After `put("k", "v", r, t)` followed by `delete("k", r2, t2)`, the
- After `put("é" (NFD), v, r, t)`, the snapshot's key is `"é"` (NFC).

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
