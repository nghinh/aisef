# STORY-01-03: `format.line_hash` SHA-256 hex digest

## Acceptance Criteria

1. [AC-STORY-01-03-1] Given a `prev_hash` string and a line dict with hash fields emptied, `line_hash(prev_hash, line)` returns exactly 64 lowercase hex characters.
2. [AC-STORY-01-03-2] Given two distinct `prev_hash` values against the same line, `line_hash` on each returns different results.
3. [AC-STORY-01-03-3] Given a line dict whose `hash` and `prev_hash` are already set, `line_hash` ignores them (it operates on a copy with those fields emptied).
4. [AC-STORY-01-03-4] Given the same `(prev_hash, line)` pair, `line_hash` returns the same digest across two invocations.
5. [AC-STORY-01-03-5] Given a `prev_hash` of literal `"GENESIS"`, `line_hash` accepts the non-hex seven-character string without raising.

## Recorded Scope

- `ledgerlock/format.py`
- `tests/test_format.py`

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

- STORY-01-02

## Requirements

### FR-2: SHA-256 hash chain over canonical bytes

Each committed line's `hash` field MUST equal `SHA-256(prev_hash || "|" || canonical_bytes)` where `canonical_bytes` is the UTF-8 encoding of the line with `"hash"` and `"prev_hash"` set to `""`, encoded by `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. The first line's `prev_hash` MUST equal the literal string `"GENESIS"`.

Verifiable Consequences:

- For any committed line `i`, recomputing
- For any line `i > 0`, `line[i].prev_hash == line[i-1].hash`.
- For any line `i == 0`, `line[i].prev_hash == "GENESIS"`.
- Existing lines are never rewritten in place; the chain is append-only.

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
