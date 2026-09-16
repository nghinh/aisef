# STORY-05-02: Coverage ≥85% and unittest/pytest parity gate

## Acceptance Criteria

1. [AC-STORY-05-02-1] Given the full test suite at this point in the epic chain, `coverage run -m unittest discover && coverage report --include=ledgerlock/*` shows a `ledgerlock/` total line coverage ≥85%.
2. [AC-STORY-05-02-2] Given the same full test suite, `pytest` discovers and runs the same suite and reports the same total passed/failed counts as `python -m unittest discover`.
3. [AC-STORY-05-02-3] Given the full test suite at this point, the `tests/` source itself is excluded from the coverage measurement.

## Recorded Scope

- `tests/test_coverage_gate.py`
- `pyproject.toml`
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
