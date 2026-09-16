# STORY-05-01: Property-based round-trip test for hash chain and snapshot stability

## Acceptance Criteria

1. [AC-STORY-05-01-1] Given the library at this point in the epic chain, when the property test runs 50 random mutation sequences against a temp JSONL (each sequence a list of `(op, key, value, rid, ts)` tuples; seeded with a fixed seed for reproducibility), then for every sequence that did not raise `ConflictError`, `verify()` returns `{"ok": True, "first_bad_index": None}` AND two calls to `snapshot()` return equal dicts.
2. [AC-STORY-05-01-2] Given the same property test, when a sequence raises `ConflictError`, the JSONL on disk after the sequence is byte-identical to its pre-sequence state for any prefix up to (and including) the offending element, and the chain length did not grow past that prefix.
3. [AC-STORY-05-01-3] Given the same property test, when it is executed under `python -m unittest discover` and again under `pytest`, both runs report the same total passed/failed counts for the property-test module.

## Recorded Scope

- `tests/test_property_roundtrip.py`

Harness added because the story's verification contract requires them (error 21):
- `tests`
- `test`
- `pytest.ini`
- `conftest.py`

Guard blocks all writes outside this list. Needing to write elsewhere means the scope declaration is wrong — stop and report, do not work around it.

## Definition of Done

This story must pass the following verification types. Types not configured on the project are **not** counted as passing — they are gaps, and the gate will flag them.

- `unit`
- `security`

## Dependencies

- STORY-03-01

## Requirements

### FR-2: SHA-256 hash chain over canonical bytes

Each committed line's `hash` field MUST equal `SHA-256(prev_hash || "|" || canonical_bytes)` where `canonical_bytes` is the UTF-8 encoding of the line with `"hash"` and `"prev_hash"` set to `""`, encoded by `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. The first line's `prev_hash` MUST equal the literal string `"GENESIS"`.

Verifiable Consequences:

- For any committed line `i`, recomputing
- For any line `i > 0`, `line[i].prev_hash == line[i-1].hash`.
- For any line `i == 0`, `line[i].prev_hash == "GENESIS"`.
- Existing lines are never rewritten in place; the chain is append-only.

### FR-3: Idempotent replay by `rid`

If `append` (or any element of `apply_batch`) is called with a `rid` that already appears as the `id` of the most recent committed mutation for the same key, the call MUST return the same result as the original call and MUST NOT append a new line to the chain.

Verifiable Consequences:

- Given a committed `put(k, v1, r1, t1)`, calling
- Replaying with the same `rid` and a different `ts` is still a no-op
- A replayed `put` after a tombstone with the same `rid` returns the

### FR-4: Conflict detection by `rid`

If `append` (or any element of `apply_batch`) is called with a `rid` that does NOT match the `id` of the most recent committed mutation for the same key, the call MUST raise `ConflictError` and MUST NOT append a new line.

Verifiable Consequences:

- Given a committed `put(k, v1, r1, t1)`, calling
- The same rule applies for `delete(k, r2, t2)` after
- The most recent committed `rid` is the only one that matters; older

### FR-9: Deterministic snapshot

`Ledger.snapshot()` and `ledgerlock snapshot --out <file>` MUST return a JSON document where (a) the top-level object has one entry per key whose most recent committed mutation is a live `put`; (b) the keys are NFC-normalized; (c) the keys are sorted in UTF-8 codepoint order; (d) the value is the JSON value from the most recent live `put` on that key. Tombstoned keys are absent.

Verifiable Consequences:

- Two snapshots taken from the same chain (no intervening mutations)
- A snapshot of a chain containing keys `"a"`, `"c"`, `"b"` in
- After `put("k", "v", r, t)` followed by `delete("k", r2, t2)`, the
- After `put("é" (NFD), v, r, t)`, the snapshot's key is `"é"` (NFC).

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
