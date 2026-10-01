# STORY-01-04: `store.read_lines` and `store.write_atomic` (pure I/O primitives)

## Acceptance Criteria

1. [AC-STORY-01-04-1] Given a JSONL with N lines, `store.read_lines(path)` returns a list of N `bytes` objects, each line's trailing `\n` stripped.
2. [AC-STORY-01-04-2] Given a missing file path, `store.read_lines(path)` raises `FileNotFoundError`.
3. [AC-STORY-01-04-3] Given an empty file (zero bytes), `store.read_lines(path)` returns an empty list.
4. [AC-STORY-01-04-4] Given `store.write_atomic(path, [b"{...}\n", b"{...}\n"])`, the path's bytes equal the concatenation and a separate `read_lines` call returns the two lines.
5. [AC-STORY-01-04-5] Given `store.write_atomic` called with a non-empty existing path, a simulated crash between temp-write and `os.replace` (e.g. patching `os.replace` to raise) leaves the original path byte-identical.
6. [AC-STORY-01-04-6] Given a call to `store.write_atomic`, the temp file used is created in the same directory as the target path (so `os.replace` is atomic on POSIX).

## Recorded Scope

- `ledgerlock/store.py`
- `tests/test_store.py`

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

- STORY-01-03

## Requirements

### FR-13: `fsync` before return

Every successful `append` (and the equivalent `apply_batch` path) MUST ensure that the JSONL bytes are flushed to the underlying storage device before the function returns successfully. Acceptable implementations: write-then-fsync-then-rename (temp-file pattern), or `f.flush(); os.fsync(fd)` on an append-mode handle before close.

Verifiable Consequences:

- A test that simulates a power cut after `append` returns
- No code path returns success without an `fsync` on either the

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
