# STORY-01-06: `Ledger.append` enforces rid-based replay, conflict, and tombstone semantics

## Acceptance Criteria

1. [AC-STORY-01-06-1] Given a committed `put("k", "v1", "r1", 100)`, `append(("put", "k", "anything", "r1", 999))` (same `rid`, different value and ts) returns the original line dict byte-for-byte with `replayed is True`, `committed is False`, and the chain length is unchanged.
2. [AC-STORY-01-06-2] Given the same committed line, `append(("put", "k", "v2", "r2", 200))` (different `rid`) raises `ConflictError` with `key == "k"`, `incoming_rid == "r2"`, `committed_rid == "r1"`, `batch_index is None`, and the JSONL is byte-identical to its pre-call state.
3. [AC-STORY-01-06-3] Given a committed `delete("k", "r1", 100)`, `append(("put", "k", "v", "r2", 200))` (different `rid`) raises `ConflictError`.
4. [AC-STORY-01-06-4] Given the same committed `delete("k", "r1", 100)`, `append(("put", "k", "v", "r1", 200))` (same `rid`) returns the delete line dict byte-for-byte with `replayed is True`, `committed is False`.
5. [AC-STORY-01-06-5] Given a key committed with NFC form `"\u00e9"` (U+00E9) and `rid == "r1"`, `append(("put", "e\u0301", "v2", "r1", 200))` (NFD form, same `rid`) is a replay: the returned line dict's `key` equals `"\u00e9"` byte-exact, `replayed is True`, and the chain length is unchanged.

## Recorded Scope

- `ledgerlock/ledger.py`
- `tests/test_conflict.py`

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

- STORY-01-05

## Requirements

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

### FR-5: Tombstone semantics for `delete`

A `delete` operation writes a `delete` line to the chain (no `value` field). A subsequent `put` on the same key with a different `rid` MUST conflict. A subsequent `put` with the same `rid` as the tombstone MUST be an idempotent no-op returning the same result as the original delete.

Verifiable Consequences:

- `append(("delete", k, r1, t1))` appends a line with
- After `delete(k, r1, t1)`, `put(k, v, r2, t2)` raises `ConflictError`.
- After `delete(k, r1, t1)`, `put(k, v, r1, t2)` returns the delete

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
