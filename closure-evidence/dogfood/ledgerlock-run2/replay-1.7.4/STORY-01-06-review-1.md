# review — STORY-01-06, attempt 1

session: e61b1861-5959-4770-9d2d-6887585179ed · turns: 19 · $1.41

---

I read the code on disk, the requirements doc, and ran the gate myself.

**Gate evidence (fresh run, this worktree):**
- `pytest -q` → 47 passed; `python -m unittest discover -q` → Ran 47, OK (AD-11 parity holds).
- `ruff check ledgerlock tests` → All checks passed. `ruff format --check` fails only on `store.py`, `test_format.py`, `test_nfc_normalization.py`, `test_skeleton.py`, `test_store.py` — **not** on this story's two files; my previous `should fix` on formatting is resolved for the files in scope, and the rest are other stories' files.
- `mypy` is not installed in this environment — not gradeable.

**Previous items, verified closed:** the `[block]` on the 4-tuple delete shape is fixed — `append(("delete", k, rid, ts))` works, and the AC-3/AC-4 tests now call the documented shape. `_normalize_key` duplication is gone (uses `format.normalize_key`), the committed-line lookup now compares NFC forms (`ledger.py:100`), and the double file read is down to one.

**Acceptance criteria:** all five tests genuinely exercise their criterion, not just the name. AC-1 compares `canonical_bytes(result)` against the stored bytes and the pre-call file bytes; AC-2/AC-3 assert all four error fields plus byte-identical file; AC-4 asserts `assertNotIn("value", result)`, which is the only thing keeping `line["value"] = value` out of tombstone lines; AC-5's `assertEqual(result["key"], "\u00e9")` fails if the incoming NFD key is not normalized (the append would land as a second line and the chain-length assert would go red too). Removing any of the corresponding implementation lines turns a specific test red.

---

```
[should fix] ledgerlock/ledger.py:79 — append does not check that the existing JSONL ends with b"\n" before opening in "ab" mode, so it fuses its new record onto a previously committed line.
  Why: if a prior write was cut exactly at the newline (complete JSON object, missing terminator — the one torn-tail shape that still json-parses), the next append concatenates, producing `{...}{...}\n`. I reproduced it: two committed records end up on one physical line that `store.read_lines` returns as a single unparseable chunk. Recovery then has no good move — repair-tail may only drop the *final incomplete* line (AD-2), and here dropping that line destroys a record that was already committed and fsynced.
  Fix: in `_read_committed` (or before the open at line 79), detect a non-newline-terminated file and raise rather than append — §7 already defines "last byte is not \n" as the torn-tail case that `repair-tail` owns, so refusing is the consistent behaviour. Both the detection and the raise sit in `ledgerlock/ledger.py`, inside write scope.

[suggestion] ledgerlock/ledger.py:84 — the committed return hands back the caller's in-memory `value`, while the replay return hands back the JSON round-trip of the stored line.
  Why: FR-3 says a replay "MUST return the same result as the original call". For any value whose JSON round-trip is not identity — a tuple (returns a tuple first, a list on replay), a dict with int keys (`{1:"a"}` → `{"1":"a"}`) — the two results differ. AC-1's test only uses strings, so it cannot see this.
  Fix: build the committed return from the bytes just written (parse `canonical_bytes(line)` back) so both paths return the on-disk shape.

[suggestion] ledgerlock/ledger.py:43 — neither `operation` nor `rid` is validated at the trust boundary.
  Why: `append(("frobnicate", "k", "v", "r9", 1))` writes and hash-chains a line whose `op` is a shape §3.2 does not define, permanently, in an append-only file. And `rid=""` or `rid=None` is accepted and then serves as the identity key for replay, despite §4.1 requiring a non-empty UTF-8 string — a caller that forgets to set a request id gets silent idempotent no-ops instead of an error.
  Fix: reject `operation not in ("put", "delete")` and a non-string/empty `rid` alongside the existing empty-key check, before any disk read.

[suggestion] ledgerlock/ledger.py:52 — every append fully reads and JSON-parses the whole ledger, so n appends cost O(n²).
  Why: raised on the previous candidate and now halved (one read instead of two), so this is only the residual. It is correct, just quadratic; worth noting before verify/snapshot add their own full scans.
  Fix: none required for this story — record it if a later story adds an in-memory tail/index.
```

No blocking items.

```json
{
  "verdict": "pass",
  "findings": [
    {"tag": "should fix", "file": "ledgerlock/ledger.py", "line": 79,
     "why": "append opens in \"ab\" without checking the file ends with a newline, so a tail cut exactly at the terminator causes the new record to be concatenated onto the previous committed line, leaving a fused unparseable line that repair-tail can only fix by dropping a committed record (AD-2)",
     "behavior_id": "FR-5"},
    {"tag": "should fix", "file": "ledgerlock/ledger.py", "line": 84,
     "why": "committed path returns the caller's in-memory value while the replay path returns the JSON round-trip, so for tuples or non-string dict keys the replay does not return the same result as the original call",
     "behavior_id": "FR-3"},
    {"tag": "should fix", "file": "ledgerlock/ledger.py", "line": 43,
     "why": "no validation of operation or rid: an undefined op string is hash-chained into the append-only file, and an empty or None rid is accepted as the replay identity despite the requirement that rid be a non-empty string",
     "behavior_id": "FR-4"},
    {"tag": "should fix", "file": "ledgerlock/ledger.py", "line": 52,
     "why": "each append parses the entire ledger, making n appends O(n^2); residual of a prior suggestion, now down to a single read per call",
     "behavior_id": ""}
  ]
}
```