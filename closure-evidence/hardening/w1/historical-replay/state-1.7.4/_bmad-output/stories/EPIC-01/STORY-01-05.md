# STORY-01-05: `Ledger.append` writes a hash-chained line with fsync and rejects empty keys

## Acceptance Criteria

1. [AC-STORY-01-05-1] Given a fresh `Ledger(path)` whose JSONL does not yet exist, `append(("put", "k", {"v": 1}, "r1", 100))` creates the file with exactly one line terminated by `\n` whose `op == "put"`, `key == "k"`, `id == "r1"`, `ts == 100`, `value == {"v": 1}`, `prev_hash == "GENESIS"`, and `hash == format.line_hash("GENESIS", line_with_hash_fields_emptied)`.
2. [AC-STORY-01-05-2] Given a second `append` after the first, the new line's `prev_hash` equals the first line's stored `hash` and its own `hash` equals `line_hash(first_hash, new_line_emptied)`.
3. [AC-STORY-01-05-3] Given `append(("put", "", "v", "r", 1))` against an empty ledger, `ValueError` is raised and no file is created.
4. [AC-STORY-01-05-4] Given an existing JSONL written by a previous `Ledger` instance, a fresh `Ledger` opened on the same path computes its first `append`'s `prev_hash` from the tail of the file (the new instance reads the tail from disk, not from any in-memory state).
5. [AC-STORY-01-05-5] Given `append` returns successfully on an empty path, a separate process opening the same path finds the new line present and the file terminated by `\n`.

## Recorded Scope

- `ledgerlock/ledger.py`
- `ledgerlock/__init__.py`
- `tests/test_ledger.py`

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

- STORY-01-04

## Requirements

### FR-1: NFC key normalization

The library MUST normalize every key via `unicodedata.normalize("NFC", key)` before storage, lookup, hashing, or serialization. Two strings that differ only in NFC/NFD representation MUST be treated as the same key.

Verifiable Consequences:

- Given a `put` with key `"\u00e9"` (NFC, U+00E9) committed, a follow-up
- After committing one of the two representations above, a verify on the

### FR-2: SHA-256 hash chain over canonical bytes

Each committed line's `hash` field MUST equal `SHA-256(prev_hash || "|" || canonical_bytes)` where `canonical_bytes` is the UTF-8 encoding of the line with `"hash"` and `"prev_hash"` set to `""`, encoded by `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. The first line's `prev_hash` MUST equal the literal string `"GENESIS"`.

Verifiable Consequences:

- For any committed line `i`, recomputing
- For any line `i > 0`, `line[i].prev_hash == line[i-1].hash`.
- For any line `i == 0`, `line[i].prev_hash == "GENESIS"`.
- Existing lines are never rewritten in place; the chain is append-only.

### FR-13: `fsync` before return

Every successful `append` (and the equivalent `apply_batch` path) MUST ensure that the JSONL bytes are flushed to the underlying storage device before the function returns successfully. Acceptable implementations: write-then-fsync-then-rename (temp-file pattern), or `f.flush(); os.fsync(fd)` on an append-mode handle before close.

Verifiable Consequences:

- A test that simulates a power cut after `append` returns
- No code path returns success without an `fsync` on either the

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
