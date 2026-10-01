# STORY-03-01: Atomic `apply_batch` rejects on any conflict

## Acceptance Criteria

1. [AC-STORY-03-01-1] Given an empty ledger and a batch of 3 conflict-free `put` elements, `apply_batch(ops)` produces a JSONL with exactly 3 new lines whose chain verifies end-to-end and whose first batch line's `prev_hash` equals `"GENESIS"`.
2. [AC-STORY-03-01-2] Given a ledger with one committed `put("k", "v1", "r1", 100)` and a batch `[("put", "k", "v2", "r1", 200), ("put", "k2", 2, "r2", 201)]`, the first element is an idempotent replay against the pre-batch state and the batch appends exactly one new line (for `k2`); the JSONL gains exactly one line.
3. [AC-STORY-03-01-3] Given an empty ledger and a batch `[("put", "k", "v1", "r1", 100), ("put", "k", "v2", "r2", 200)]`, `apply_batch` raises `ConflictError` with `key == "k"`, `incoming_rid == "r2"`, `committed_rid == "r1"`, `batch_index == 1`, and the JSONL on disk is byte-identical to its pre-batch state.
4. [AC-STORY-03-01-4] Given a ledger whose most recent committed mutation on `k` has `rid == "r1"` and a batch whose element 0 targets `k` with `rid == "r2"`, `apply_batch` raises `ConflictError` with `batch_index == 0` and the JSONL is unchanged.
5. [AC-STORY-03-01-5] Given a simulated crash between temp-file write and `os.replace` (e.g. by patching `os.replace` to raise), `apply_batch` against a non-empty ledger leaves the JSONL byte-identical to its pre-batch state and `verify()` returns `{"ok": True, "first_bad_index": None}`.

## Recorded Scope

- `ledgerlock/ledger.py`
- `tests/test_atomic_batch.py`

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

- STORY-02-01

## Requirements

### FR-8: Atomic `apply_batch`

`Ledger.apply_batch(ops)` and `ledgerlock apply --batch <file>` MUST take the process-wide lock, write all lines to a sibling temp file, `fsync` the temp file, then `os.replace` it over the JSONL path. If the process crashes at any point, the JSONL on disk MUST either reflect the full batch or be byte-identical to its pre-batch state.

Verifiable Consequences:

- Applying a batch of N lines results in exactly N appended lines with
- Within a batch, idempotent replays (matching `rid` on a key) and
- Simulating a crash between temp-file write and `os.replace` (e.g.
- The temp file is created in the same directory as the JSONL (so the

### FR-13: `fsync` before return

Every successful `append` (and the equivalent `apply_batch` path) MUST ensure that the JSONL bytes are flushed to the underlying storage device before the function returns successfully. Acceptable implementations: write-then-fsync-then-rename (temp-file pattern), or `f.flush(); os.fsync(fd)` on an append-mode handle before close.

Verifiable Consequences:

- A test that simulates a power cut after `append` returns
- No code path returns success without an `fsync` on either the

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
