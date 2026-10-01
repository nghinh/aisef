# LedgerLock — Epics & Stories

**Source PRD:** `_bmad-output/prd.md`
**Source architecture:** `_bmad-output/architecture.md`
**Source experience:** `_bmad-output/EXPERIENCE.md`

**Stories:** 15 across 5 epics. Each story adds behaviour no earlier story delivers. Every story has ≤8 acceptance criteria. Acceptance criteria are falsifiable at the branch point: each criterion asserts something that is not already true of code that exists before the story starts. No criterion is a placeholder, no-op, or duplicate of another criterion in the same story. Write scopes are split so stories that may run in parallel never share a file.

---

## Epic 1: Foundation, Hash-Chain Append & Rid Semantics

A Python developer can import `ledgerlock`, open a `Ledger` at a path, and append `put`/`delete` mutations that are durably committed to a SHA-256-chained JSONL file. The on-disk format — line shape, canonical-bytes encoding, `GENESIS` `prev_hash`, NFC key normalization, `os.fsync` before return — is frozen. `append` enforces idempotent replay by `rid`, conflict detection by `rid`, and tombstone semantics for `delete` in one rid-lookup code path.

**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-13, FR-14.

### Story 1.1: Package skeleton, CLI surface, and NFC key normalization

**As a** Python developer
**I want** a `ledgerlock` package importable from a `pyproject.toml` declaring stdlib-only runtime, with `format.normalize_key` exposed and a CLI module that registers `verify`/`snapshot`/`apply`/`repair-tail` argparse subcommands (whose bodies defer to later stories)
**So that** downstream stories have a working package boundary, NFC normalization is byte-exact, and the runtime import surface contains only the stdlib allowlist.

**Acceptance criteria:**

- Given any string `s`, `from ledgerlock.format import normalize_key; normalize_key(s)` returns `unicodedata.normalize("NFC", s)` byte-for-byte.
- Given the NFC string `"\u00e9"` (U+00E9) and its NFD decomposition `"e\u0301"`, calling `normalize_key` on each returns byte-identical results equal to `"\u00e9"`.
- Given a fresh `pyproject.toml` declaring `name = "ledgerlock"` and `requires-python = ">=3.11"`, an empty `ledgerlock/` package, and an empty `tests/` directory, `python -c "import ledgerlock; print(ledgerlock.__file__)"` prints a path ending in `ledgerlock/__init__.py` with no exception.
- Given the `ledgerlock/` package source tree, `grep -RE "^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)" ledgerlock/` exits `1` (zero matches).
- Given the `ledgerlock/` package source tree, `grep -RE "os\.system|subprocess\.|socket\." ledgerlock/` exits `1` (zero matches).
- Given an `__init__.py`, `from ledgerlock import Ledger, ConflictError` returns both names without exception and `Ledger` is a callable class.

**Story metadata:**
- covers: FR-1, FR-14
- ac_proof: 1=CHANGE_REQUIRED/FR-1, 2=CHANGE_REQUIRED/FR-1, 3=CHANGE_REQUIRED/FR-14, 4=NEGATIVE_INVARIANT/FR-14, 5=NEGATIVE_INVARIANT/FR-14, 6=CHANGE_REQUIRED/FR-14
- write_scope: pyproject.toml, ledgerlock/__init__.py, ledgerlock/__main__.py, ledgerlock/format.py, tests/__init__.py, tests/test_skeleton.py, tests/test_nfc_normalization.py, README.md
- depends_on: none
- screens: none

### Story 1.2: `format.canonical_bytes` and `format.GENESIS` constant

**As a** Python developer extending the chain logic
**I want** `format.canonical_bytes` to encode a line dict deterministically and `format.GENESIS` to be the literal seven-character string `"GENESIS"`
**So that** every later layer hashes and compares lines identically and the `prev_hash` of the first line is unambiguous.

**Acceptance criteria:**

- Given a dict `line` whose `hash` and `prev_hash` are unset, `canonical_bytes(line)` returns exactly `json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
- Given a second dict element-equal to the first, `canonical_bytes` on it returns bytes byte-identical to the first call's bytes.
- Given a dict whose value includes a non-ASCII string (e.g. `"é"` U+00E9), `canonical_bytes` encodes it as UTF-8 literal (`\xc3\xa9`, not `\u00e9`) and is byte-stable across two invocations.
- Given two dicts whose keys differ only in insertion order, `canonical_bytes` returns byte-identical bytes.
- Given `from ledgerlock.format import GENESIS`, `GENESIS == "GENESIS"` (literal seven-character string, distinct from any 64-char hex string).
- Given `canonical_bytes` called twice on the same dict after round-tripping through `json.loads`, the returned bytes equal the original bytes.

**Story metadata:**
- covers: FR-2
- ac_proof: 1=CHANGE_REQUIRED/FR-2, 2=CHANGE_REQUIRED/FR-2, 3=CHANGE_REQUIRED/FR-2, 4=CHANGE_REQUIRED/FR-2, 5=CHANGE_REQUIRED/FR-2, 6=CHANGE_REQUIRED/FR-2
- write_scope: ledgerlock/format.py, tests/test_format.py
- depends_on: 1.1
- screens: none

### Story 1.3: `format.line_hash` SHA-256 hex digest

**As a** Python developer extending the chain logic
**I want** `format.line_hash(prev_hash, line)` to return `SHA-256((prev_hash + "|" + canonical_bytes(line_with_hash_fields_emptied)).encode("utf-8")).hexdigest()` as exactly 64 lowercase hex characters
**So that** writer and verifier agree on the chain hash byte-for-byte.

**Acceptance criteria:**

- Given a `prev_hash` string and a line dict with hash fields emptied, `line_hash(prev_hash, line)` returns exactly 64 lowercase hex characters.
- Given two distinct `prev_hash` values against the same line, `line_hash` on each returns different results.
- Given a line dict whose `hash` and `prev_hash` are already set, `line_hash` ignores them (it operates on a copy with those fields emptied).
- Given the same `(prev_hash, line)` pair, `line_hash` returns the same digest across two invocations.
- Given a `prev_hash` of literal `"GENESIS"`, `line_hash` accepts the non-hex seven-character string without raising.

**Story metadata:**
- covers: FR-2
- ac_proof: 1=CHANGE_REQUIRED/FR-2, 2=CHANGE_REQUIRED/FR-2, 3=CHANGE_REQUIRED/FR-2, 4=CHANGE_REQUIRED/FR-2, 5=CHANGE_REQUIRED/FR-2
- write_scope: ledgerlock/format.py, tests/test_format.py
- depends_on: 1.2
- screens: none

### Story 1.4: `store.read_lines` and `store.write_atomic` (pure I/O primitives)

**As a** Python developer integrating LedgerLock
**I want** `store.read_lines(path)` to return the JSONL bytes split by newlines and `store.write_atomic(path, lines)` to atomically replace the file via temp-file + `fsync` + `os.replace` in the same directory
**So that** `verify`, `snapshot`, and `apply_batch` can rely on a single I/O contract and a crash never leaves a partial write.

**Acceptance criteria:**

- Given a JSONL with N lines, `store.read_lines(path)` returns a list of N `bytes` objects, each line's trailing `\n` stripped.
- Given a missing file path, `store.read_lines(path)` raises `FileNotFoundError`.
- Given an empty file (zero bytes), `store.read_lines(path)` returns an empty list.
- Given `store.write_atomic(path, [b"{...}\n", b"{...}\n"])`, the path's bytes equal the concatenation and a separate `read_lines` call returns the two lines.
- Given `store.write_atomic` called with a non-empty existing path, a simulated crash between temp-write and `os.replace` (e.g. patching `os.replace` to raise) leaves the original path byte-identical.
- Given a call to `store.write_atomic`, the temp file used is created in the same directory as the target path (so `os.replace` is atomic on POSIX).

**Story metadata:**
- covers: FR-13
- ac_proof: 1=CHANGE_REQUIRED/FR-13, 2=CHANGE_REQUIRED/FR-13, 3=CHANGE_REQUIRED/FR-13, 4=CHANGE_REQUIRED/FR-13, 5=CHANGE_REQUIRED/FR-13, 6=CHANGE_REQUIRED/FR-13
- write_scope: ledgerlock/store.py, tests/test_store.py
- depends_on: 1.3
- screens: none

### Story 1.5: `Ledger.append` writes a hash-chained line with fsync and rejects empty keys

**As a** Python developer and a library caller integrating LedgerLock
**I want** `Ledger.append(("put", key, value, rid, ts))` (or `("delete", key, rid, ts)`) to NFC-normalize the key, append exactly one new line whose `hash` is `line_hash(prev_hash, line)` and whose `prev_hash` matches the prior committed line's `hash` (or `"GENESIS"` for the first line), `fsync` the bytes before return, and raise `ValueError` on an empty key after NFC normalization
**So that** mutations are durable on return, the on-disk format is byte-exact, and misuse is caught before any line is written.

**Acceptance criteria:**

- Given a fresh `Ledger(path)` whose JSONL does not yet exist, `append(("put", "k", {"v": 1}, "r1", 100))` creates the file with exactly one line terminated by `\n` whose `op == "put"`, `key == "k"`, `id == "r1"`, `ts == 100`, `value == {"v": 1}`, `prev_hash == "GENESIS"`, and `hash == format.line_hash("GENESIS", line_with_hash_fields_emptied)`.
- Given a second `append` after the first, the new line's `prev_hash` equals the first line's stored `hash` and its own `hash` equals `line_hash(first_hash, new_line_emptied)`.
- Given `append(("put", "", "v", "r", 1))` against an empty ledger, `ValueError` is raised and no file is created.
- Given an existing JSONL written by a previous `Ledger` instance, a fresh `Ledger` opened on the same path computes its first `append`'s `prev_hash` from the tail of the file (the new instance reads the tail from disk, not from any in-memory state).
- Given `append` returns successfully on an empty path, a separate process opening the same path finds the new line present and the file terminated by `\n`.

**Story metadata:**
- covers: FR-1, FR-2, FR-13
- ac_proof: 1=CHANGE_REQUIRED/FR-2, 2=CHANGE_REQUIRED/FR-2, 3=CHANGE_REQUIRED/FR-1, 4=CHANGE_REQUIRED/FR-2, 5=CHANGE_REQUIRED/FR-13
- write_scope: ledgerlock/ledger.py, ledgerlock/__init__.py, tests/test_ledger.py
- depends_on: 1.4
- screens: none

### Story 1.6: `Ledger.append` enforces rid-based replay, conflict, and tombstone semantics

**As a** Python developer whose message handler retries after a crash, and a library caller whose two requests race on the same key
**I want** `Ledger.append` to look up the most recent committed mutation per NFC-normalized key, return the original line as an idempotent no-op when `rid` matches, raise `ConflictError` (with `key`, `incoming_rid`, `committed_rid`, `batch_index=None`) when `rid` differs, and treat a `delete` line as a tombstone whose subsequent `put` is replayed when the `rid` matches and conflicts when it differs
**So that** at-least-once delivery does not double-write and conflicting requests cannot silently overwrite each other.

**Acceptance criteria:**

- Given a committed `put("k", "v1", "r1", 100)`, `append(("put", "k", "anything", "r1", 999))` (same `rid`, different value and ts) returns the original line dict byte-for-byte with `replayed is True`, `committed is False`, and the chain length is unchanged.
- Given the same committed line, `append(("put", "k", "v2", "r2", 200))` (different `rid`) raises `ConflictError` with `key == "k"`, `incoming_rid == "r2"`, `committed_rid == "r1"`, `batch_index is None`, and the JSONL is byte-identical to its pre-call state.
- Given a committed `delete("k", "r1", 100)`, `append(("put", "k", "v", "r2", 200))` (different `rid`) raises `ConflictError`.
- Given the same committed `delete("k", "r1", 100)`, `append(("put", "k", "v", "r1", 200))` (same `rid`) returns the delete line dict byte-for-byte with `replayed is True`, `committed is False`.
- Given a key committed with NFC form `"\u00e9"` (U+00E9) and `rid == "r1"`, `append(("put", "e\u0301", "v2", "r1", 200))` (NFD form, same `rid`) is a replay: the returned line dict's `key` equals `"\u00e9"` byte-exact, `replayed is True`, and the chain length is unchanged.

**Story metadata:**
- covers: FR-3, FR-4, FR-5
- ac_proof: 1=CHANGE_REQUIRED/FR-3, 2=CHANGE_REQUIRED/FR-4, 3=CHANGE_REQUIRED/FR-5, 4=CHANGE_REQUIRED/FR-5, 5=CHANGE_REQUIRED/FR-3
- write_scope: ledgerlock/ledger.py, tests/test_conflict.py
- depends_on: 1.5
- screens: none

---

## Epic 2: Independent Verify & Deterministic Snapshot

A library caller (or CI operator) calls `Ledger.verify()` and gets a verdict computed end-to-end from disk with no reliance on `append`-time cache; the verifier detects byte edits committed between `append` and `verify`. A separate caller materializes the current state via `Ledger.snapshot()` as a UTF-8-codepoint-sorted JSON object, byte-stable for a given chain.

**FRs covered:** FR-6, FR-7, FR-9.

### Story 2.1: End-to-end verify from disk ignores in-memory state

**As a** library caller or CI operator
**I want** `Ledger.verify()` to read the JSONL end-to-end from disk, recompute every line's hash from the canonical-bytes scheme, and return `{"ok": bool, "first_bad_index": int | None}`, reading no field from in-memory state set by `append`
**So that** I can detect tampering without trusting any in-memory cache.

**Acceptance criteria:**

- Given a JSONL with N valid lines written through `Ledger.append`, `verify()` returns `{"ok": True, "first_bad_index": None}` without raising.
- Given a zero-byte JSONL, `verify()` returns `{"ok": True, "first_bad_index": None}` without raising.
- Given a missing JSONL file path, `verify()` raises `FileNotFoundError`.
- Given a JSONL whose line at index `i` has had its `hash` field overwritten with `"0" * 64` out-of-band after `append` returned, `verify()` from a fresh `Ledger` instance returns `{"ok": False, "first_bad_index": i}` (or the earlier index whose chain is now broken).
- Given a JSONL whose `value` field on line `i` is mutated out-of-band after `append` (e.g. `"v1"` → `"v2"`), `verify()` from a fresh `Ledger` instance returns `{"ok": False, "first_bad_index": i}`.

**Story metadata:**
- covers: FR-6, FR-7
- ac_proof: 1=CHANGE_REQUIRED/FR-6, 2=CHANGE_REQUIRED/FR-6, 3=CHANGE_REQUIRED/FR-6, 4=CHANGE_REQUIRED/FR-7, 5=CHANGE_REQUIRED/FR-7
- write_scope: ledgerlock/ledger.py, tests/test_verify_independent.py
- depends_on: 1.6
- screens: none

### Story 2.2: Deterministic snapshot sorted by NFC key

**As a** library caller or operator
**I want** `Ledger.snapshot()` to return a JSON object whose keys are NFC-normalized, sorted in UTF-8 codepoint order, with the most recent live `put` value per key and tombstoned keys absent
**So that** two snapshots of the same chain are byte-identical and diffable.

**Acceptance criteria:**

- Given `put("a", 1, r, t)`, `put("c", 3, r, t)`, `put("b", 2, r, t)` written in that order, two calls to `snapshot()` with no intervening mutations return equal dicts and `json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` lists keys in `a, b, c` order.
- Given a committed `put("k", "v", "r1", t1)`, `delete("k", "r2", t2)` raises `ConflictError` (requirements §4.5: a different `rid` mutating the same key MUST conflict) and a following `snapshot()` still returns `{"k": "v"}` — the refused delete changed nothing.
- Given `delete("k2", "r3", t3)` on a key with no committed mutation (a tombstone, requirements §4.4), `snapshot()` returns a dict with no key `"k2"`.
- Given `put("e\u0301", "v", r, t)` (NFD form) and a follow-up `put("\u00e9", "v2", r, t)` with the same `rid` (idempotent replay), `snapshot()` returns a dict with the NFC key `"\u00e9"` and value `"v"`.
- Given two `Ledger` instances opened in succession over the same on-disk chain, each `snapshot()` returns equal dicts.

**Story metadata:**
- covers: FR-9
- ac_proof: 1=CHANGE_REQUIRED/FR-9, 2=CHANGE_REQUIRED/FR-9, 3=CHANGE_REQUIRED/FR-9, 4=CHANGE_REQUIRED/FR-9, 5=CHANGE_REQUIRED/FR-9
- write_scope: ledgerlock/ledger.py, tests/test_snapshot_determinism.py
- depends_on: 2.1
- screens: none

---

## Epic 3: Atomic Batch & Repair-Tail Recovery

A library caller commits N mutations atomically: a crash anywhere leaves the JSONL either fully updated or byte-identical to its pre-batch state; any conflict inside the batch rejects the whole batch. A separate operator strips a truncated final line from a JSONL whose last line is unparseable, leaving a clean chain; mid-chain corruption is refused.

**FRs covered:** FR-8, FR-10.

### Story 3.1: Atomic `apply_batch` rejects on any conflict

**As a** library caller committing N mutations as a logical unit
**I want** `apply_batch(ops)` to validate every element against the pre-batch committed state, raise `ConflictError` and append nothing on any conflict, otherwise write all N lines atomically via temp-file + `fsync` + `os.replace`
**So that** a crash or a conflict leaves the JSONL either fully updated or byte-identical to its pre-batch state.

**Acceptance criteria:**

- Given an empty ledger and a batch of 3 conflict-free `put` elements, `apply_batch(ops)` produces a JSONL with exactly 3 new lines whose chain verifies end-to-end and whose first batch line's `prev_hash` equals `"GENESIS"`.
- Given a ledger with one committed `put("k", "v1", "r1", 100)` and a batch `[("put", "k", "v2", "r1", 200), ("put", "k2", 2, "r2", 201)]`, the first element is an idempotent replay against the pre-batch state and the batch appends exactly one new line (for `k2`); the JSONL gains exactly one line.
- Given an empty ledger and a batch `[("put", "k", "v1", "r1", 100), ("put", "k", "v2", "r2", 200)]`, `apply_batch` raises `ConflictError` with `key == "k"`, `incoming_rid == "r2"`, `committed_rid == "r1"`, `batch_index == 1`, and the JSONL on disk is byte-identical to its pre-batch state.
- Given a ledger whose most recent committed mutation on `k` has `rid == "r1"` and a batch whose element 0 targets `k` with `rid == "r2"`, `apply_batch` raises `ConflictError` with `batch_index == 0` and the JSONL is unchanged.
- Given a simulated crash between temp-file write and `os.replace` (e.g. by patching `os.replace` to raise), `apply_batch` against a non-empty ledger leaves the JSONL byte-identical to its pre-batch state and `verify()` returns `{"ok": True, "first_bad_index": None}`.

**Story metadata:**
- covers: FR-8, FR-13
- ac_proof: 1=CHANGE_REQUIRED/FR-8, 2=CHANGE_REQUIRED/FR-8, 3=CHANGE_REQUIRED/FR-8, 4=CHANGE_REQUIRED/FR-8, 5=CHANGE_REQUIRED/FR-13
- write_scope: ledgerlock/ledger.py, tests/test_atomic_batch.py
- depends_on: 2.1
- screens: none

### Story 3.2: `repair_tail` strips only a truncated final line

**As an** operator recovering from a process crash that truncated the JSONL
**I want** `Ledger.repair_tail()` to rewrite the JSONL with the truncated final line removed iff the rest of the chain verifies cleanly, leave a clean chain as a no-op, and refuse on mid-chain corruption
**So that** a half-written tail never blocks recovery but a tampered middle never silently self-heals.

**Acceptance criteria:**

- Given a JSONL whose last line is truncated (last byte is not `\n` OR the last line does not parse) and whose preceding lines form a valid chain, `repair_tail()` rewrites the JSONL with the truncated final line removed: every preserved line's bytes are unchanged and a subsequent `verify()` returns `{"ok": True, "first_bad_index": None}`; the new final byte is `\n`.
- Given a clean JSONL whose every line parses and verifies, `repair_tail()` returns without raising and the file is byte-identical before and after.
- Given a JSONL with a truncated final line AND a mid-chain corruption at an earlier index `i < len(lines) - 1`, `repair_tail()` does NOT modify the file (byte-identical before and after) and the verify verdict reports the earlier corruption.
- Given a JSONL whose last line parses but whose own `hash` is broken (a tail tampering, not a truncation), `repair_tail()` does not modify the file and reports the corruption via the verdict.

**Story metadata:**
- covers: FR-10
- ac_proof: 1=CHANGE_REQUIRED/FR-10, 2=CHANGE_REQUIRED/FR-10, 3=CHANGE_REQUIRED/FR-10, 4=CHANGE_REQUIRED/FR-10
- write_scope: ledgerlock/ledger.py, tests/test_repair_tail.py
- depends_on: 3.1
- screens: none

---

## Epic 4: CLI Surface & Exit-Code Contract

An operator runs `python -m ledgerlock <verify|snapshot|apply|repair-tail> <args>` and gets a stable exit-code contract (0/2/3/4/5) and a one-line stderr status line per invocation; stdout stays silent on success so CI pipelines and `|` consumers do not parse human prose.

**FRs covered:** FR-11, FR-12.

### Story 4.1: CLI subcommands wire library operations and write the snapshot to `--out`

**As an** operator or CI pipeline
**I want** `python -m ledgerlock verify <ledger>`, `... snapshot <ledger> --out <f>`, `... apply --batch <b> <ledger>`, and `... repair-tail <ledger>` to invoke the corresponding `Ledger` operations, write the snapshot to `--out`, and read the batch from `--batch`
**So that** the library is reachable without writing Python.

Scope note: the **error** exit codes (`3` I/O, `4` conflict, `5` corruption) are STORY-04-02's contract, and the stderr status shapes beyond `verify` are STORY-04-03's. Implement the success paths here; do not pre-empt them.

**Acceptance criteria:**

- Given `snapshot` invoked without `--out`, the CLI exits `2`.
- Given any subcommand invoked with the wrong number of positional arguments, the CLI exits with code `2` and writes nothing to stdout.
- Given the same checkout, `python -m ledgerlock --help` in a subprocess exits `0` and the stdout argparse usage line contains each of the literal strings `verify`, `snapshot`, `apply`, and `repair-tail`.
- Given a fresh JSONL written via `Ledger.append`, `python -m ledgerlock verify <ledger>` in a subprocess exits `0`, stdout is empty, and stderr contains exactly one line whose first word is `verify` and which contains the substring `ok`.
- Given the same fresh JSONL, `python -m ledgerlock snapshot <ledger> --out <snap>` exits `0`, stdout is empty, and the contents of `<snap>` equal `json.dumps(Ledger.snapshot(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"` byte-for-byte.
- Given a `batch.json` containing three conflict-free `put` elements and a fresh ledger, `python -m ledgerlock apply --batch <batch.json> <ledger>` exits `0`, stdout is empty, and the JSONL contains exactly the lines from the batch (verified by `verify()`).
- Given a clean JSONL, `python -m ledgerlock repair-tail <ledger>` exits `0`, stdout is empty, and the JSONL is byte-identical before and after.

**Story metadata:**
- covers: FR-11, FR-12
- ac_proof: 1=CHANGE_REQUIRED/FR-11, 2=CHANGE_REQUIRED/FR-11, 3=CHANGE_REQUIRED/FR-11, 4=CHANGE_REQUIRED/FR-11, 5=CHANGE_REQUIRED/FR-11, 6=CHANGE_REQUIRED/FR-12, 7=CHANGE_REQUIRED/FR-12
- write_scope: ledgerlock/cli.py, ledgerlock/__main__.py, tests/test_cli_exit_codes.py
- depends_on: 3.2
- screens: none

### Story 4.2: Exact exit-code contract for the CLI

**As a** CI pipeline branching on `$?`
**I want** the CLI to exit with exactly `0/2/3/4/5` mapped from the documented library and argparse outcomes
**So that** exit-code gating works reliably across all subcommands and scenarios.

**Acceptance criteria:**

- Given `apply --batch` invoked with a missing batch file, the CLI exits `3` and writes nothing to stdout.
- Given a JSONL with one committed `put("k", "v1", "r1", 100)` and a batch file whose element 0 is `("put", "k", "v2", "r2", 200)`, `apply --batch <b.json> <ledger>` exits `4`, writes nothing to stdout, and leaves the JSONL byte-identical to its pre-call state.
- Given a JSONL whose line 17 has been mutated out-of-band on disk, `verify` exits `5` and writes nothing to stdout.
- Given a JSONL with mid-chain corruption at line 17, `repair-tail` exits `5` and writes nothing to stdout.

**Story metadata:**
- covers: FR-12
- ac_proof: 1=CHANGE_REQUIRED/FR-12, 2=CHANGE_REQUIRED/FR-12, 3=CHANGE_REQUIRED/FR-12, 4=CHANGE_REQUIRED/FR-12
- write_scope: ledgerlock/cli.py, tests/test_cli_exit_codes.py
- depends_on: 4.1
- screens: none

### Story 4.3: Stderr status shapes on success

**As a** shell user reading one-line diagnostics
**I want** the CLI to print a stable status-line shape to stderr on success for `apply`, `snapshot`, and `repair-tail`
**So that** operators can grep stderr without parsing human prose.

**Acceptance criteria:**

- Given every success path for `verify ok`, the CLI writes nothing to stdout and a single line beginning with `verify` to stderr.
- Given every success path for `apply` (atomic batch committed), the CLI writes nothing to stdout and a single line beginning with `apply` to stderr that mentions the count of appended lines.
- Given every success path for `snapshot`, the CLI writes nothing to stdout and a single line beginning with `snapshot` to stderr that mentions the destination path.
- Given every success path for `repair-tail` (clean chain or successful repair), the CLI writes nothing to stdout and a single line beginning with `repair-tail` to stderr.
- Given any success path, the captured stdout via `subprocess.PIPE` equals `b""`.

**Story metadata:**
- covers: FR-12
- ac_proof: 1=PRESERVE_REQUIRED/FR-12, 2=CHANGE_REQUIRED/FR-12, 3=CHANGE_REQUIRED/FR-12, 4=CHANGE_REQUIRED/FR-12, 5=PRESERVE_REQUIRED/FR-12
- write_scope: ledgerlock/cli.py, tests/test_cli_exit_codes.py
- depends_on: 4.2
- screens: none

---

## Epic 5: Quality Gates — Coverage, Parity & No-Side-Channels

A maintainer runs the test suite under both `unittest discover` and `pytest` and gets identical pass/fail outcomes; `coverage report` shows ≥85% line coverage against `ledgerlock/`; the runtime import surface contains only the stdlib allowlist — no `socket`, `subprocess`, `os.system`, or any networking module.

**FRs covered:** FR-14.

### Story 5.1: Property-based round-trip test for hash chain and snapshot stability

**As a** maintainer who needs to know the chain is honest across hundreds of mutation sequences
**I want** a property-based test that generates random mutation sequences (mix of `put`/`delete`, mix of `rid` collisions and conflicts), applies them through the library, and asserts the round-trip invariants
**So that** regressions in idempotency, conflict, hash-chain integrity, or snapshot stability surface without hand-crafted fixtures.

**Acceptance criteria:**

- Given the library at this point in the epic chain, when the property test runs 50 random mutation sequences against a temp JSONL (each sequence a list of `(op, key, value, rid, ts)` tuples; seeded with a fixed seed for reproducibility), then for every sequence that did not raise `ConflictError`, `verify()` returns `{"ok": True, "first_bad_index": None}` AND two calls to `snapshot()` return equal dicts.
- Given the same property test, when a sequence raises `ConflictError`, the JSONL on disk after the sequence is byte-identical to its pre-sequence state for any prefix up to (and including) the offending element, and the chain length did not grow past that prefix.
- Given the same property test, when it is executed under `python -m unittest discover` and again under `pytest`, both runs report the same total passed/failed counts for the property-test module.

**Story metadata:**
- covers: FR-2, FR-3, FR-4, FR-8, FR-9, FR-14
- ac_proof: 1=PRESERVE_REQUIRED/FR-2, 2=PRESERVE_REQUIRED/FR-8, 3=PRESERVE_REQUIRED/FR-14
- story_type: VERIFICATION_ONLY
- write_scope: tests/test_property_roundtrip.py
- depends_on: 3.1
- screens: none

### Story 5.2: Coverage ≥85% and unittest/pytest parity gate

**As a** maintainer gating the MVP
**I want** `coverage run -m unittest discover && coverage report` to show ≥85% line coverage against `ledgerlock/` (test code excluded) and `pytest` to report the same total passed/failed counts as `python -m unittest discover`
**So that** quality gates block regressions in any code path.

**Acceptance criteria:**

- Given the full test suite at this point in the epic chain, `coverage run -m unittest discover && coverage report --include=ledgerlock/*` shows a `ledgerlock/` total line coverage ≥85%.
- Given the same full test suite, `pytest` discovers and runs the same suite and reports the same total passed/failed counts as `python -m unittest discover`.
- Given the full test suite at this point, the `tests/` source itself is excluded from the coverage measurement.

**Story metadata:**
- covers: FR-14
- ac_proof: 1=CHANGE_REQUIRED/FR-14, 2=PRESERVE_REQUIRED/FR-14, 3=CHANGE_REQUIRED/FR-14
- write_scope: tests/test_coverage_gate.py, pyproject.toml
- depends_on: 5.1
- screens: none

### Story 5.3: No-side-channels grep guard test

**As a** security reviewer
**I want** a test that greps the `ledgerlock/` source tree at test time and fails on any forbidden import or call (`socket`, `subprocess`, `os.system`, `urllib`, `http`, `asyncio`, `http.server`, `http.client`, `socketserver`, `ssl`, `multiprocessing`, `ctypes`)
**So that** a drift that quietly reintroduces a third-party or side-channel import cannot ship.

**Acceptance criteria:**

- Given the `ledgerlock/` source tree, `grep -RE "^(import|from) (socket|subprocess|requests|http|urllib|asyncio|ssl|multiprocessing|ctypes|http\.server|http\.client|socketserver)" ledgerlock/` returns no matches and the test passes.
- Given the `ledgerlock/` source tree, `grep -RE "os\.system|subprocess\.|socket\." ledgerlock/` returns no matches and the test passes.

**Story metadata:**
- covers: FR-14
- ac_proof: 1=NEGATIVE_INVARIANT/FR-14, 2=NEGATIVE_INVARIANT/FR-14
- story_type: VERIFICATION_ONLY
- write_scope: tests/test_no_side_channels.py
- depends_on: 5.1
- screens: none