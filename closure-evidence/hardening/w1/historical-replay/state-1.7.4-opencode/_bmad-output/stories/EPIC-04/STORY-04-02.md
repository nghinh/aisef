# STORY-04-02: Exact exit-code contract for the CLI

## Acceptance Criteria

1. [AC-STORY-04-02-1] Given any subcommand invoked with the wrong number of positional arguments, the CLI exits with code `2` and writes nothing to stdout.
2. [AC-STORY-04-02-2] Given `apply --batch` invoked with a missing batch file, the CLI exits `3` and writes nothing to stdout.
3. [AC-STORY-04-02-3] Given a JSONL with one committed `put("k", "v1", "r1", 100)` and a batch file whose element 0 is `("put", "k", "v2", "r2", 200)`, `apply --batch <b.json> <ledger>` exits `4`, writes nothing to stdout, and leaves the JSONL byte-identical to its pre-call state.
4. [AC-STORY-04-02-4] Given a JSONL whose line 17 has been mutated out-of-band on disk, `verify` exits `5` and writes nothing to stdout.
5. [AC-STORY-04-02-5] Given a JSONL with mid-chain corruption at line 17, `repair-tail` exits `5` and writes nothing to stdout.
6. [AC-STORY-04-02-6] Given `snapshot` invoked without `--out`, the CLI exits `2`.

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

- STORY-04-01

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
