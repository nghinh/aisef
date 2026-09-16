# STORY-01-01: Package skeleton, CLI surface, and NFC key normalization

## Acceptance Criteria

1. [AC-STORY-01-01-1] Given any string `s`, `from ledgerlock.format import normalize_key; normalize_key(s)` returns `unicodedata.normalize("NFC", s)` byte-for-byte.
2. [AC-STORY-01-01-2] Given the NFC string `"\u00e9"` (U+00E9) and its NFD decomposition `"e\u0301"`, calling `normalize_key` on each returns byte-identical results equal to `"\u00e9"`.
3. [AC-STORY-01-01-3] Given a fresh `pyproject.toml` declaring `name = "ledgerlock"` and `requires-python = ">=3.11"`, an empty `ledgerlock/` package, and an empty `tests/` directory, `python -c "import ledgerlock; print(ledgerlock.__file__)"` prints a path ending in `ledgerlock/__init__.py` with no exception.
4. [AC-STORY-01-01-4] Given the same checkout, `python -m ledgerlock --help` in a subprocess exits `0` and the stdout argparse usage line contains each of the literal strings `verify`, `snapshot`, `apply`, and `repair-tail`.
5. [AC-STORY-01-01-5] Given the `ledgerlock/` package source tree, `grep -RE "^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)" ledgerlock/` exits `1` (zero matches).
6. [AC-STORY-01-01-6] Given the `ledgerlock/` package source tree, `grep -RE "os\.system|subprocess\.|socket\." ledgerlock/` exits `1` (zero matches).
7. [AC-STORY-01-01-7] Given an `__init__.py`, `from ledgerlock import Ledger, ConflictError` returns both names without exception and `Ledger` is a callable class.

## Recorded Scope

- `pyproject.toml`
- `ledgerlock/__init__.py`
- `ledgerlock/__main__.py`
- `ledgerlock/format.py`
- `ledgerlock/cli.py`
- `tests/__init__.py`
- `tests/test_skeleton.py`
- `tests/test_nfc_normalization.py`
- `README.md`
- `poetry.lock`
- `uv.lock`
- `pdm.lock`

Harness added because the story's verification contract requires them (error 21):
- `tests`
- `test`
- `pytest.ini`
- `conftest.py`

Guard blocks all writes outside this list. Needing to write elsewhere means the scope declaration is wrong — stop and report, do not work around it.

## Definition of Done

This story must pass the following verification types. Types not configured on the project are **not** counted as passing — they are gaps, and the gate will flag them.

- `unit`

## Requirements

### FR-1: NFC key normalization

The library MUST normalize every key via `unicodedata.normalize("NFC", key)` before storage, lookup, hashing, or serialization. Two strings that differ only in NFC/NFD representation MUST be treated as the same key.

Verifiable Consequences:

- Given a `put` with key `"\u00e9"` (NFC, U+00E9) committed, a follow-up
- After committing one of the two representations above, a verify on the

### FR-14: No network, no subprocess, no extra files

The runtime MUST NOT import `socket`, `subprocess`, or any networking module. The runtime MUST NOT call `os.system`, `subprocess.*`, or `socket.*`. The runtime MUST NOT open any file other than the configured ledger path, the explicit `--batch` input path, and the explicit `--out` output path.

Verifiable Consequences:

- `grep -RE "^(import|from) (socket|subprocess|requests|http|
- `grep -RE "os\.system|subprocess\.|socket\." ledgerlock/` returns
- A runtime trace (e.g. `strace -f -e trace=openat`) of any

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
