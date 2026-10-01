# STORY-02-01: End-to-end verify from disk ignores in-memory state

## Acceptance Criteria

1. [AC-STORY-02-01-1] Given a JSONL with N valid lines written through `Ledger.append`, `verify()` returns `{"ok": True, "first_bad_index": None}` without raising.
2. [AC-STORY-02-01-2] Given a zero-byte JSONL, `verify()` returns `{"ok": True, "first_bad_index": None}` without raising.
3. [AC-STORY-02-01-3] Given a missing JSONL file path, `verify()` raises `FileNotFoundError`.
4. [AC-STORY-02-01-4] Given a JSONL whose line at index `i` has had its `hash` field overwritten with `"0" * 64` out-of-band after `append` returned, `verify()` from a fresh `Ledger` instance returns `{"ok": False, "first_bad_index": i}` (or the earlier index whose chain is now broken).
5. [AC-STORY-02-01-5] Given a JSONL whose `value` field on line `i` is mutated out-of-band after `append` (e.g. `"v1"` → `"v2"`), `verify()` from a fresh `Ledger` instance returns `{"ok": False, "first_bad_index": i}`.

## Recorded Scope

- `ledgerlock/ledger.py`
- `tests/test_verify_independent.py`

Harness added because the story's verification contract requires them (error 21):
- `tests`
- `test`
- `pytest.ini`
- `conftest.py`

Guard blocks all writes outside this list. Needing to write elsewhere means the scope declaration is wrong — stop and report, do not work around it.

## Definition of Done

This story must pass the following verification types. Types not configured on the project are **not** counted as passing — they are gaps, and the gate will flag them.

- `unit`
- `e2e`
- `security`

## Dependencies

- STORY-01-06

## Requirements

### FR-6: End-to-end verify from disk

`Ledger.verify()` and `ledgerlock verify` MUST read the JSONL from disk end-to-end, recompute the hash of every line using only the file's own `prev_hash` and the canonical-bytes scheme, and return a verdict `{"ok": bool, "first_bad_index": int | None}` where `first_bad_index` is the zero-based index of the first violating line or `None` when `ok` is `True`.

Verifiable Consequences:

- On a fresh ledger with N valid lines, verify returns
- Mutating any byte in any committed line (the `value`, `op`, `hash`,
- Calling verify immediately after `append`, without re-opening the

### FR-7: Verifier does not trust in-memory cache

The `verify` implementation MUST NOT read any field from in-memory state set by `append`. The implementation MUST recompute the chain solely from the on-disk bytes.

Verifiable Consequences:

- A test that constructs a `Ledger`, calls `append`, then directly
- The `Ledger.verify` source contains no attribute read from the

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
