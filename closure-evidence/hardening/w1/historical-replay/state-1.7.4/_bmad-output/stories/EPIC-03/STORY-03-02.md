# STORY-03-02: `repair_tail` repairs only the tail: terminates a valid unterminated record, strips a truncated fragment, refuses otherwise

## Acceptance Criteria

1. [AC-STORY-03-02-1] Given a JSONL whose final line parses, satisfies the line schema, carries the correct `prev_hash`/`hash` for its chain position and valid request-id semantics, but whose last byte is not `\n`: `verify()` returns `{"ok": False, "first_bad_index": <index of that final line>, "reason": "unterminated"}` (a repairable tail-integrity condition, not a clean ledger); `repair_tail()` appends exactly one `b"\n"` and changes no other byte — the file afterwards equals the original bytes plus `b"\n"`, no record is removed — and a subsequent `verify()` returns `{"ok": True, "first_bad_index": None}`.
2. [AC-STORY-03-02-2] Given a JSONL whose bytes after the last complete `\n`-terminated line are an incomplete JSON fragment (e.g. ends mid-`{`) and whose preceding lines form a valid chain, `repair_tail()` truncates only that fragment back to the last complete record boundary: every preserved line's bytes are unchanged, the new final byte is `\n`, and a subsequent `verify()` returns `{"ok": True, "first_bad_index": None}`.
3. [AC-STORY-03-02-3] Given a JSONL whose final line parses as JSON but whose own `hash` does not equal the recomputed chain hash (tail tampering, not truncation), `repair_tail()` refuses: the file is byte-identical before and after, no record is deleted, and the corruption is reported via the verify verdict (`ok=False`, `first_bad_index` = that line's index).
4. [AC-STORY-03-02-4] Given a JSONL whose final line parses as JSON but fails any other integrity rule — its `prev_hash` does not match the preceding line's `hash` (wrong chain position), a schema violation (missing or extra field, wrong type), a key that is not NFC-normalized, or a request-id that violates the ledger's rid semantics — `repair_tail()` refuses: byte-identical before and after, no record deleted, and the verify verdict reports the failure.
5. [AC-STORY-03-02-5] Given a JSONL with any corruption at an index earlier than the final line (mid-chain), with or without a damaged tail, `repair_tail()` refuses: the file is byte-identical before and after and the verify verdict reports the earliest corruption.
6. [AC-STORY-03-02-6] Given a JSONL whose final record is valid but unterminated (as in criterion 1), `Ledger.append(...)` and `apply_batch(...)` never write a new record directly after it: either the mutation first repairs the tail by appending the missing `\n` and then appends normally, or it fails safely by raising without modifying the file; in both cases the previously committed record is preserved on its own line, no line ever holds two records, and `verify()` afterwards never reports a concatenated line.
7. [AC-STORY-03-02-7] Given a clean, `\n`-terminated JSONL whose every line parses and verifies, `repair_tail()` returns without raising and the file is byte-identical before and after.

## Recorded Scope

- `ledgerlock/ledger.py`
- `tests/test_repair_tail.py`

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

- STORY-03-01

## Requirements

### FR-10: Repair the tail only, never a committed record

`ledgerlock repair-tail <path>` operates on the final line boundary only
(owner arbitration 2026-09-16, `_bmad-output/decisions/OWNER-ARBITRATION-STORY-03-02.md`):

- (a) **Valid record, missing final newline.** If the final record parses,
  satisfies the schema, carries the correct `prev_hash`/`hash` for its chain
  position and valid request-id semantics, but the file does not end with
  `\n`, the record is VALID and MUST NOT be deleted. This is not a clean
  ledger: `verify` MUST report it as a repairable tail-integrity condition
  (`ok=False`, `first_bad_index` = the final line, `reason="unterminated"`),
  and `repair-tail` MUST repair it by appending exactly the missing `\n`,
  leaving every other byte unchanged.
- (b) **Truly truncated final JSON.** If the bytes after the last complete
  `\n`-terminated line are an incomplete JSON fragment, `repair-tail` MAY
  remove only that fragment, back to the last complete valid record boundary.
- (c) **Semantically corrupt valid JSON.** If the final line parses but fails
  any integrity rule (hash, `prev_hash`, chain position, schema, normalized
  key, request-id consistency), `repair-tail` MUST refuse. It never deletes a
  record to make `verify` pass.
- (d) **Middle corruption.** Any corruption before the final line is not
  repairable by `repair-tail`; it MUST refuse.

After a successful repair, `verify` MUST return `ok=True`. If the chain is
clean and `\n`-terminated, `repair-tail` MUST be a no-op. Every refusal exits
with code `5` and leaves the file byte-identical.

**Future append.** A mutation (`append`, `apply --batch`) MUST NEVER write a
new record directly after a valid record whose final `\n` is missing: it
repairs the tail first or fails safely; it never produces a line holding two
records.

Verifiable Consequences:
- A JSONL whose final record is valid but lacks its `\n` is repaired by
  appending exactly one `\n`; no record is removed; `verify` then returns
  `ok=True`; exit code is `0`.
- A JSONL whose last line is a truncated fragment (e.g. ends mid-`{`) is
  repaired by removing only that fragment; `verify` then returns `ok=True`;
  exit code is `0`.
- A JSONL whose last line parses but fails hash, `prev_hash`, schema, key or
  request-id rules is refused; the file is not modified; exit code is `5`.
- A JSONL with mid-chain corruption (with or without a damaged tail) is
  refused; the file is not modified; exit code is `5`.
- A clean, `\n`-terminated JSONL is left byte-identical after `repair-tail`;
  exit code is `0`.
- An `append` onto a valid unterminated record never concatenates two
  records on one line.

---

_Auto-generated from `epics.md`. Edits here will be lost on next split — edit `epics.md` and run `aisef plan`._
