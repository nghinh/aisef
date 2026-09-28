"""Core of the LedgerLock reference: the JSONL hash chain (§3.2), tamper evidence and the independent verify
(§3.3, §3.4), idempotency and conflicts (§4), the atomic batch (§5), the deterministic snapshot (§6), repair-tail
(§7) and durability (§8). Every decision starts from the bytes on disk; nothing an instance remembers decides a
verdict.

Interpretations this reference fixes (the requirements leave them open):

* canonical bytes of a line (§3.2): JSON with sorted keys, no whitespace, non-ASCII kept, `hash` and `prev_hash`
  set to the empty string; the first line's `prev_hash` is the literal "GENESIS";
* a request id is replayed when any committed line carries it, whatever its op or key (§4.2);
* a mutation on a ledger file that does not exist yet creates it; reads of a missing ledger are I/O errors (§9);
* a final line that lacks its newline but parses and hashes is complete; "truncated" means the final line is
  unterminated AND does not parse or hash (§7);
* a batch is an iterable of (op, key, value, rid, ts); `value` is ignored for a delete (§5).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import typing
import unicodedata

GENESIS = "GENESIS"


class ConflictError(Exception):
    """A different rid tried to mutate a key whose last committed mutation used another rid (§4.3-§4.5)."""


class CorruptionError(Exception):
    """The chain is corrupt where an operation cannot proceed (§7: corruption not confined to the tail)."""


class Result(typing.NamedTuple):
    op: str
    key: str
    rid: str
    index: int
    hash: str


class Verdict(typing.NamedTuple):
    ok: bool
    first_bad_index: typing.Optional[int]
    length: int


# --------------------------------------------------------------------------------------- the chain (§3.1, §3.2)

def normalize_key(key: str) -> str:
    """Keys are NFC before any storage, lookup, hashing or serialisation step (§3.1)."""
    return unicodedata.normalize("NFC", key)


def canonical_bytes(record: dict) -> bytes:
    """The canonical bytes of a line: hash and prev_hash blanked, keys sorted, no whitespace (§3.2)."""
    blank = dict(record, hash="", prev_hash="")
    return json.dumps(blank, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def line_hash(prev_hash: str, record: dict) -> str:
    """hash = SHA-256(prev_hash || "|" || canonical_bytes) (§3.2)."""
    return hashlib.sha256(prev_hash.encode("utf-8") + b"|" + canonical_bytes(record)).hexdigest()


def encode_line(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def scan(raw: bytes) -> typing.Tuple[list, typing.Optional[int], bool]:
    """The lines of the file: the parsed records up to the first line that does not parse, that line's index (or
    None), and whether the file ends without a newline (an unterminated final line)."""
    if raw == b"":
        return [], None, False
    parts = raw.split(b"\n")
    unterminated = parts[-1] != b""
    lines = parts if unterminated else parts[:-1]
    records = []
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return records, i, unterminated
        if not isinstance(rec, dict):
            return records, i, unterminated
        records.append(rec)
    return records, None, unterminated


def verify_records(records: list, unparsable: typing.Optional[int] = None) -> Verdict:
    """Recompute the chain over the parsed records (§3.3): the first line whose stored hash is not the recomputed
    one, or whose prev_hash is not the previous line's stored hash, is the first bad index; an unparsable line is
    bad where it stands."""
    prev = GENESIS
    total = len(records) + (0 if unparsable is None else 1)
    for i, rec in enumerate(records):
        linked = rec.get("prev_hash") == prev
        intact = rec.get("hash") == line_hash(prev, rec)
        if not (linked and intact):
            return Verdict(False, i, total)
        prev = rec["hash"]
    if unparsable is not None:
        return Verdict(False, unparsable, total)
    return Verdict(True, None, total)


def verify_raw(raw: bytes) -> Verdict:
    records, unparsable, _ = scan(raw)
    return verify_records(records, unparsable)


# --------------------------------------------------------------------------------------- disk (§8)

def _read_raw(path: str, missing_ok: bool = False) -> bytes:
    if missing_ok and not os.path.exists(path):
        return b""
    with open(path, "rb") as f:
        return f.read()


def _fsync_write(path: str, data: bytes) -> None:
    """Write `data` to a sibling temp file, fsync it, rename it over `path`: the file is either the old bytes or the
    new bytes, never partial (§5, §8)."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".ledgerlock-", dir=directory)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(fd)
    os.replace(tmp, path)


def _append_bytes(path: str, line: bytes, needs_newline: bool) -> None:
    """Append one line durably: flush and fsync before close (§8)."""
    with open(path, "ab") as f:
        if needs_newline:
            f.write(b"\n")
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


# --------------------------------------------------------------------------------------- semantics (§4)

def _by_rid(records: list) -> dict:
    return {rec["id"]: (i, rec) for i, rec in enumerate(records)}


def _last_mutation(records: list) -> dict:
    return {rec["key"]: rec for rec in records}


def _result_of(index: int, rec: dict) -> Result:
    return Result(rec["op"], rec["key"], rec["id"], index, rec["hash"])


def _plan(records: list, seen: dict, last: dict, op: str, key: str, value, rid: str, ts: int, prev: str):
    """What one mutation means against the chain as it stands: ("replay", Result) for a replayed rid (§4.2),
    ("conflict", None) for a different rid on a mutated key (§4.3-§4.5), or ("append", record) with the new line."""
    if op not in ("put", "delete"):
        raise ValueError(f"unknown op {op!r}")
    if not isinstance(rid, str) or rid == "":
        raise ValueError("rid must be a non-empty string")
    if not isinstance(ts, int) or isinstance(ts, bool):
        raise ValueError("ts must be an integer")
    key = normalize_key(key)
    if rid in seen:
        return "replay", _result_of(seen[rid][0], seen[rid][1])
    last_rec = last.get(key)
    if last_rec is not None and last_rec["id"] != rid:
        return "conflict", None
    record = {"op": op, "key": key, "ts": ts, "id": rid}
    if op == "put":
        record["value"] = value
    record["prev_hash"] = prev
    record["hash"] = line_hash(prev, record)
    return "append", record


class Ledger:
    """One JSONL ledger at `path`."""

    def __init__(self, path: str) -> None:
        self.path = os.fspath(path)
        self._known_length = None   # what this instance last wrote; informative only, never a verdict's input

    # ----- reads

    def _records(self, missing_ok: bool) -> typing.Tuple[list, bytes]:
        raw = _read_raw(self.path, missing_ok)
        records, unparsable, _ = scan(raw)
        if unparsable is not None:
            raise CorruptionError(f"line {unparsable} does not parse; verify or repair-tail first")
        return records, raw

    def verify(self) -> Verdict:
        """Recomputed from disk end to end (§3.4)."""
        raw = _read_raw(self.path)
        return verify_raw(raw)

    def snapshot(self) -> bytes:
        """The materialised state, keys in UTF-8 byte order, byte-stable for a given chain (§6)."""
        records, _ = self._records(missing_ok=False)
        return snapshot_records(records)

    # ----- mutations

    def append(self, op: str, key: str, value, rid: str, ts: int) -> Result:
        """One durable mutation, idempotent by rid, conflicting by key (§4, §8)."""
        records, raw = self._records(missing_ok=True)
        prev = records[-1]["hash"] if records else GENESIS
        kind, payload = _plan(records, _by_rid(records), _last_mutation(records), op, key, value, rid, ts, prev)
        if kind == "replay":
            return payload
        if kind == "conflict":
            raise ConflictError(f"key {normalize_key(key)!r} was last mutated by another rid")
        _append_bytes(self.path, encode_line(payload), needs_newline=bool(raw) and not raw.endswith(b"\n"))
        self._known_length = len(records) + 1
        return _result_of(len(records), payload)

    def put(self, key: str, value, rid: str, ts: int) -> Result:
        return self.append("put", key, value, rid, ts)

    def delete(self, key: str, rid: str, ts: int) -> Result:
        return self.append("delete", key, None, rid, ts)

    def apply_batch(self, ops) -> typing.List[Result]:
        """All or nothing (§5): every op is planned against the chain and the batch so far; the new lines are
        written to a sibling temp file, fsynced and renamed over the ledger. A conflict anywhere commits nothing."""
        records, raw = self._records(missing_ok=True)
        seen, last = _by_rid(records), _last_mutation(records)
        prev = GENESIS if not records else records[-1]["hash"]
        index = len(records)
        new_lines, results = [], []
        for op, key, value, rid, ts in ops:
            kind, payload = _plan(records, seen, last, op, key, value, rid, ts, prev)
            if kind == "replay":
                results.append(payload)
                continue
            if kind == "conflict":
                raise ConflictError(f"batch op {len(results)}: key {normalize_key(key)!r} was last mutated by another rid")
            last[payload["key"]] = payload
            results.append(_result_of(index, payload))
            new_lines.append(encode_line(payload))
            prev = payload["hash"]
            index += 1
        if new_lines:
            joiner = b"\n" if raw and not raw.endswith(b"\n") else b""
            _fsync_write(self.path, raw + joiner + b"".join(new_lines))
            self._known_length = index
        return results

    def repair_tail(self) -> bool:
        """Remove a truncated final line (§7): a no-op on a clean chain, a refusal when the corruption is not
        confined to the tail. Returns whether the file was rewritten."""
        raw = _read_raw(self.path)
        records, unparsable, unterminated = scan(raw)
        verdict = verify_records(records, unparsable)
        if verdict.ok:
            return False
        total = verdict.length
        if not (unterminated and verdict.first_bad_index == total - 1):
            raise CorruptionError(f"corruption at line {verdict.first_bad_index} is not confined to the tail")
        head = raw.split(b"\n")[:total - 1]
        _fsync_write(self.path, b"\n".join(head) + (b"\n" if head else b""))
        if not self.verify().ok:
            raise CorruptionError("the chain does not verify after removing the tail")
        return True


def snapshot_records(records: list) -> bytes:
    """For each key the most recent committed put unless tombstoned later, sorted by NFC key in UTF-8 byte order,
    serialised the same way for the same chain (§6)."""
    state = {}
    for rec in records:
        if rec["op"] == "put":
            state[rec["key"]] = rec["value"]
        else:
            state.pop(rec["key"], None)
    items = sorted(state.items(), key=lambda kv: kv[0].encode("utf-8"))
    return (json.dumps(dict(items), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


# --------------------------------------------------------------------------------------- module-level API (§13)

def append(path: str, op: str, key: str, value, rid: str, ts: int) -> Result:
    return Ledger(path).append(op, key, value, rid, ts)


def verify(path: str) -> Verdict:
    return Ledger(path).verify()


def snapshot(path: str) -> bytes:
    return Ledger(path).snapshot()


def apply_batch(path: str, ops) -> typing.List[Result]:
    return Ledger(path).apply_batch(ops)
