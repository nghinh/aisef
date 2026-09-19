# STORY-04-01: CLI subcommands wire library operations and write the snapshot to `--out`

## Acceptance Criteria

1. [AC-STORY-04-01-1] Given a fresh JSONL written via `Ledger.append`, `python -m ledgerlock verify <ledger>` in a subprocess exits `0`, stdout is empty, and stderr contains exactly one line whose first word is `verify` and which contains the substring `ok`.
2. [AC-STORY-04-01-2] Given the same fresh JSONL, `python -m ledgerlock snapshot <ledger> --out <snap>` exits `0`, stdout is empty, and the contents of `<snap>` equal `json.dumps(Ledger.snapshot(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"` byte-for-byte.
3. [AC-STORY-04-01-3] Given a `batch.json` containing three conflict-free `put` elements and a fresh ledger, `python -m ledgerlock apply --batch <batch.json> <ledger>` exits `0`, stdout is empty, and the JSONL contains exactly the lines from the batch (verified by `verify()`).
4. [AC-STORY-04-01-4] Given a ledger whose final record is otherwise fully valid but whose final newline is missing, when `python -m ledgerlock repair-tail <ledger>` is executed in a subprocess, then the exit code is `0`, stdout is empty, the command appends exactly one missing `\n`, no other byte is changed, no committed record is removed, and a subsequent `verify()` reports the ledger clean (`{"ok": True, "first_bad_index": None}`).

_Owner arbitration 2026-09-16 (`_bmad-output/decisions/OWNER-ARBITRATION-STORY-04-01.md`): the former AC-4 (clean JSONL → exit 0, empty stdout, byte-identical) is satisfied by the integrated parent's CLI stub and is therefore not a story-proving criterion; that behaviour stays covered as preservation of STORY-03-02's clean-file no-op and by STORY-04-03's success-line contract._

## Recorded Scope

- `ledgerlock/cli.py`
- `ledgerlock/__main__.py`
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

- STORY-03-02

## Requirements

### FR-11: CLI subcommands

The CLI MUST expose the subcommands `verify`, `snapshot`, `apply --batch <batch-file>`, and `repair-tail`. `snapshot` MUST accept `--out <file>`; defaults are not permitted for `--out` when the operator wants a deterministic artifact path (the caller supplies the path).

Verifiable Consequences:

- `python -m ledgerlock verify path/to/ledger.jsonl` exits `0` on a
- `python -m ledgerlock snapshot path/to/ledger.jsonl --out
- `python -m ledgerlock apply --batch batch.json path/to/ledger.jsonl`
- `python -m ledgerlock repair-tail path/to/ledger.jsonl` exits `0`

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
