# LedgerLock — Requirements

## 1. Purpose

LedgerLock is an append-only, tamper-evident key/value ledger with cryptographic
hash chaining, idempotent mutating operations, and crash-safe atomic batch writes.
It is implemented as a Python 3.11+ library using only the standard library, with a
deterministic snapshot/verify CLI. No network, server, UI, or database is involved.

## 2. Non-Goals

- No network listener / HTTP server / web UI / desktop UI.
- No external database (SQLite, Postgres, etc.). Storage is a single JSONL file.
- No client/server split. This is a single-process library + CLI.
- No third-party runtime dependencies (no `cryptography`, no `pynacl`, no `requests`).

## 3. Storage

### 3.1 Key normalization (Unicode NFC)

All keys are normalized to Unicode NFC before any storage, lookup, hashing, or
serialization step. Two strings that differ only in NFC/NFD representation MUST be
treated as the same key. Equivalence is checked using `unicodedata.normalize("NFC", s)`.
Comparison of the normalized form MUST be byte-exact.

### 3.2 JSONL hash chain

The ledger is a single JSONL file. Each line is one of:

- `{ "op": "put", "key": "<nfc>", "value": <json>, "ts": <int>, "id": "<rid>" }`
- `{ "op": "delete", "key": "<nfc>", "ts": <int>, "id": "<rid>" }`

Each line carries a `"hash"` field that is computed over the canonical bytes of
the line with `"hash"` and `"prev_hash"` fields set to the empty string, then:

    hash = SHA-256( prev_hash || "|" || canonical_bytes )
    prev_hash of the next line = this hash

The first line's `prev_hash` is the literal string `"GENESIS"` (64 hex chars of
zeros OR the literal string `"GENESIS"` — implementation choice, but it MUST be
documented and constant). The chain is append-only: existing records MUST NOT be
rewritten in place.

### 3.3 Tamper evidence

Any modification to a committed line (mutating `value`, swapping `op`, or
modifying `hash`) MUST be detected by an independent full verify that does not
trust any cached metadata. Verify returns a structured verdict:

- `ok=True` if every line's recomputed hash matches its stored `hash` AND
  every line's stored `prev_hash` matches the previous line's stored `hash`.
- `ok=False` and `first_bad_index=<i>` on the first violation.

### 3.4 Independent verify

The verify implementation MUST NOT read any field from in-memory state set by
`append`. It MUST recompute the chain from disk end-to-end. This rule applies
whether verify is called from CLI or library.

## 4. Idempotency and Conflict Semantics

### 4.1 Request IDs

Every mutating operation (`put`, `delete`) takes a request id (`rid`). A `rid`
is a non-empty UTF-8 string supplied by the caller (UUID4, ULID, etc. — format
opaque to LedgerLock).

### 4.2 Idempotency

If the same `rid` is replayed, the second call MUST return the same result
and MUST NOT append a new line to the chain.

### 4.3 Conflict

If a different `rid` tries to mutate a key whose last committed mutation used a
different `rid`, the call MUST raise `ConflictError` (or return an error result
depending on CLI surface) and MUST NOT append a new line.

### 4.4 Tombstones

A `delete` produces a tombstone line. A subsequent `put` on the same key with a
different `rid` MUST conflict against the tombstone just as it would against a
live value. A subsequent `put` with the same `rid` as the tombstone is an
idempotent replay and MUST be a no-op returning the same result as the delete.

### 4.5 Key-with-different-rid-different-op semantics

A `put` on key `k` with `rid=r1`, then a `delete` on key `k` with `rid=r2` —
the second MUST conflict. Replays of either MUST NOT conflict.

## 5. Atomic Batch Mutation

`apply_batch(ops)` accepts an iterable of (op, key, value, rid, ts) tuples
under the lock, writes all lines to a sibling temp file, fsyncs the temp file,
then renames it over the JSONL path. If the process crashes at any point,
the JSONL on disk MUST either reflect the full batch or be byte-identical to
its pre-batch state — never a partial batch.

The CLI equivalent is `ledgerlock apply --batch <file>` which reads the batch
spec and performs the same atomic operation.

## 6. Deterministic Snapshot

`snapshot()` returns a deterministic, sorted JSON document representing the
current materialized state: for each key, the most recent committed `put` value
(if not tombstoned by a later `delete`), sorted by NFC-normalized key in
byte order (UTF-8 codepoint order). The snapshot MUST be byte-stable for a given
chain content (same chain → same snapshot bytes).

The CLI `ledgerlock snapshot --out <file>` writes this same document.

## 7. Repair-tail

If the JSONL ends in a truncated line (last byte is not `\n` and the last line
does not parse / hash), `ledgerlock repair-tail` MUST rewrite the file with the
truncated final line removed and verify cleanly afterwards. No other content
may be modified. If the chain is clean, `repair-tail` is a no-op. If the chain
is corrupt in the middle (not at the tail), `repair-tail` MUST refuse.

## 8. Durability

After a successful `append`, the bytes MUST be durably on disk before the
function returns successfully. Implementation: write to temp file, fsync, then
rename; or open the JSONL in append mode and call `f.flush(); os.fsync(fd)`
before close.

## 9. CLI Exit Codes (exact contract)

`ledgerlock` (or `python -m ledgerlock`) MUST exit with:

- `0` — success (append / verify ok / snapshot ok / repair-tail no-op or repair ok)
- `2` — usage error (bad arguments)
- `3` — I/O error (file not found, permission denied)
- `4` — conflict (rid mismatch on a key)
- `5` — corruption (verify reports `ok=False` or repair-tail finds non-tail corruption)

`verify` exiting `0` means the chain is intact. `verify` exiting `5` means
corruption. Any other exit code is a bug.

## 10. Language / Runtime

- Python 3.11+ required (use `from __future__ import annotations`).
- Stdlib only. Allowed: `hashlib`, `json`, `os`, `sys`, `pathlib`, `tempfile`,
  `argparse`, `unittest`, `typing`, `unicodedata`, `uuid`.
- No `pip install` of any runtime dependency.

## 11. Tests and Coverage

- Unit tests covering every requirement in §3–§9.
- ≥85% line coverage measured by `coverage.py` (a dev-only dependency, not a
  runtime one — allowed only for the test phase).
- Tests must be runnable with `python -m unittest discover` AND `pytest` if
  pytest is available; results MUST agree.

## 12. No Side Channels

- No `socket`, no `subprocess`, no `os.system`.
- No opening of files outside the configured ledger path except the explicit
  batch input and snapshot output paths supplied by the caller.

## 13. Repository layout

```
ledgerlock/
  __init__.py
  ledger.py        # core: Ledger, ConflictError, append, verify, snapshot, apply_batch
  cli.py           # argparse CLI, exact exit codes
tests/
  test_*.py        # unittest.TestCase based
docs/
  requirements.md  # this file
README.md
pyproject.toml     # stdlib only; coverage as optional dev dep
```

## 14. Acceptance

A run passes if:

1. `python -m ledgerlock verify path/to/ledger.jsonl` exits 0 on a fresh ledger.
2. `python -m ledgerlock snapshot path/to/ledger.jsonl` produces deterministic bytes.
3. `python -m ledgerlock apply --batch batch.json path/to/ledger.jsonl` commits atomically.
4. `python -m ledgerlock repair-tail path/to/ledger.jsonl` fixes a truncated tail.
5. `coverage run -m unittest discover && coverage report` reports ≥85%.
6. No third-party imports succeed at runtime.