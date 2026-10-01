# STORY-05-03: No-side-channels grep guard test

## Acceptance Criteria

1. [AC-STORY-05-03-1] Given the `ledgerlock/` source tree, `grep -RE "^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)" ledgerlock/` returns no matches and the test passes.
2. [AC-STORY-05-03-2] Given the `ledgerlock/` source tree, `grep -RE "os\.system|subprocess\.|socket\." ledgerlock/` returns no matches and the test passes.
3. [AC-STORY-05-03-3] Given the same test module, when it is executed under `python -m unittest discover` and again under `pytest`, both runners discover and execute the test.

## Recorded Scope

- `tests/test_no_side_channels.py`

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

- STORY-05-01

## Requirements

### FR-14: No network, no subprocess, no extra files

The runtime MUST NOT import `socket`, `subprocess`, or any networking module. The runtime MUST NOT call `os.system`, `subprocess.*`, or `socket.*`. The runtime MUST NOT open any file other than the configured ledger path, the explicit `--batch` input path, and the explicit `--out` output path.

Verifiable Consequences:

- `grep -RE "^(import|from) (socket|subprocess|requests|http|
- `grep -RE "os\.system|subprocess\.|socket\." ledgerlock/` returns
- A runtime trace (e.g. `strace -f -e trace=openat`) of any

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
