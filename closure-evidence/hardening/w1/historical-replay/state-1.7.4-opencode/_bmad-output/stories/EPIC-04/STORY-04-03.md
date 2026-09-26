# STORY-04-03: Stderr status shapes on success

## Acceptance Criteria

1. [AC-STORY-04-03-1] Given every success path for `verify ok`, the CLI writes nothing to stdout and a single line beginning with `verify` to stderr.
2. [AC-STORY-04-03-2] Given every success path for `apply` (atomic batch committed), the CLI writes nothing to stdout and a single line beginning with `apply` to stderr that mentions the count of appended lines.
3. [AC-STORY-04-03-3] Given every success path for `snapshot`, the CLI writes nothing to stdout and a single line beginning with `snapshot` to stderr that mentions the destination path.
4. [AC-STORY-04-03-4] Given every success path for `repair-tail` (clean chain or successful repair), the CLI writes nothing to stdout and a single line beginning with `repair-tail` to stderr.
5. [AC-STORY-04-03-5] Given any success path, the captured stdout via `subprocess.PIPE` equals `b""`.

## Recorded Scope

- `ledgerlock/cli.py`
- `tests/test_cli_exit_codes.py`

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

- STORY-04-02

## Requirements

### FR-12: Exact exit-code contract

The CLI MUST exit with exactly: `0` success, `2` usage error, `3` I/O error, `4` conflict, `5` corruption. Any other exit code is a bug.

Verifiable Consequences:

- Calling any subcommand with the wrong number of positional
- Calling `apply --batch` with a missing batch file exits `3`.
- Calling `apply` with a batch containing a conflicting element
- Calling `verify` on a corrupted ledger exits `5`.
- All four success-path subcommands exit `0` on their happy path.

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
