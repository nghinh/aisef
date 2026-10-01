# STORY-01-02: `format.canonical_bytes` and `format.GENESIS` constant

## Acceptance Criteria

1. [AC-STORY-01-02-1] Given a dict `line` whose `hash` and `prev_hash` are unset, `canonical_bytes(line)` returns exactly `json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
2. [AC-STORY-01-02-2] Given a second dict element-equal to the first, `canonical_bytes` on it returns bytes byte-identical to the first call's bytes.
3. [AC-STORY-01-02-3] Given a dict whose value includes a non-ASCII string (e.g. `"é"` U+00E9), `canonical_bytes` encodes it as UTF-8 literal (`\xc3\xa9`, not `\u00e9`) and is byte-stable across two invocations.
4. [AC-STORY-01-02-4] Given two dicts whose keys differ only in insertion order, `canonical_bytes` returns byte-identical bytes.
5. [AC-STORY-01-02-5] Given `from ledgerlock.format import GENESIS`, `GENESIS == "GENESIS"` (literal seven-character string, distinct from any 64-char hex string).
6. [AC-STORY-01-02-6] Given `canonical_bytes` called twice on the same dict after round-tripping through `json.loads`, the returned bytes equal the original bytes.

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

- STORY-01-01

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
