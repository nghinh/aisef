"""Reference LedgerLock — the W1 oracle's INDEPENDENT calibration fixture.

Written from docs/requirements.md alone (§3–§9, §12, §13). Never derived from, compared with, or corrected against
any AISEF-generated implementation. Choices the requirements leave open are marked `choice:` and listed in
ORACLE-INDEPENDENCE.json. The mutants in calibrate.py are one-line edits of this file, each removing one required
behaviour, so that every oracle assertion is shown to catch the defect it names.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
from pathlib import Path

GENESIS = "GENESIS"  # §3.2: the first line's prev_hash — documented and constant (choice: the literal string)


class ConflictError(Exception):
    """§4.3: a different rid mutates a key whose last committed mutation used another rid."""


class CorruptionError(Exception):
    """§3.3 / §7: the chain does not verify, or repair-tail is refused."""

    def __init__(self, first_bad_index: int, msg: str = ""):
        super().__init__(msg or f"corruption at line {first_bad_index}")
        self.first_bad_index = first_bad_index


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)  # §3.1


def canonical(rec: dict) -> bytes:
    """§3.2: the line with `hash` and `prev_hash` set to the empty string (choice: sorted keys, compact separators)."""
    body = {k: v for k, v in rec.items() if k not in ("hash", "prev_hash")}
    body["hash"] = ""
    body["prev_hash"] = ""
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def chain_hash(prev_hash: str, rec: dict) -> str:
    return hashlib.sha256(prev_hash.encode("utf-8") + b"|" + canonical(rec)).hexdigest()  # §3.2


def scan(data: bytes) -> tuple[list[dict], int | None]:
    """§3.3 / §3.4: recompute the whole chain from raw bytes. Returns (verified records, first_bad_index)."""
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    recs: list[dict] = []
    prev = GENESIS
    for i, raw in enumerate(lines):
        try:
            rec = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return recs, i
        if not isinstance(rec, dict) or rec.get("prev_hash") != prev or rec.get("hash") != chain_hash(prev, rec):
            return recs, i
        recs.append(rec)
        prev = rec["hash"]
    return recs, None


def write_atomic(path: Path, data: bytes) -> None:
    """§5 / §8: sibling temp file, fsync, rename over the ledger."""
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Ledger:
    def __init__(self, path):
        self.path = Path(path)  # choice: the constructor takes the ledger path (§13 names only the class)

    def _bytes(self) -> bytes:
        return self.path.read_bytes() if self.path.exists() else b""

    def _load(self) -> list[dict]:
        recs, bad = scan(self._bytes())
        if bad is not None:
            raise CorruptionError(bad)
        return recs

    @staticmethod
    def _line(rec: dict) -> bytes:
        return json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"

    @staticmethod
    def _result(rec: dict) -> dict:
        return {"op": rec["op"], "key": rec["key"], "id": rec["id"], "hash": rec["hash"]}

    def verify(self) -> dict:
        """§3.3 / §3.4: from disk only; a missing file is an I/O error (OSError)."""
        _, bad = scan(self.path.read_bytes())
        return {"ok": bad is None, "first_bad_index": bad}

    def append(self, op: str, key: str, rid: str, ts: int, value=None) -> dict:
        return self.apply_batch([(op, key, value, rid, ts)])[0]

    def apply_batch(self, ops) -> list[dict]:
        """§5: the whole batch or nothing. §4: a replayed rid is a no-op with the same result; another rid on a key
        (live value or tombstone) conflicts and appends nothing."""
        recs = self._load()
        by_rid = {r["id"]: r for r in recs}
        last = {r["key"]: r for r in recs}
        prev = recs[-1]["hash"] if recs else GENESIS
        results: list[dict] = []
        new: list[dict] = []
        for op, key, value, rid, ts in ops:
            if op not in ("put", "delete"):
                raise ValueError(f"unknown op {op!r}")
            if not isinstance(rid, str) or not rid:
                raise ValueError("rid must be a non-empty string")  # §4.1
            key = nfc(key)
            if rid in by_rid:
                results.append(self._result(by_rid[rid]))  # §4.2 / §4.4: replay
                continue
            if key in last and last[key]["id"] != rid:
                raise ConflictError(f"key {key!r}: last mutation by rid {last[key]['id']!r}, not {rid!r}")  # §4.3–§4.5
            rec = {"op": op, "key": key, "ts": int(ts), "id": rid}
            if op == "put":
                rec["value"] = value
            rec["prev_hash"] = prev
            rec["hash"] = chain_hash(prev, rec)
            prev = rec["hash"]
            new.append(rec)
            by_rid[rid] = rec
            last[key] = rec
            results.append(self._result(rec))
        if new:
            write_atomic(self.path, self._bytes() + b"".join(self._line(r) for r in new))
        return results

    def snapshot(self) -> bytes:
        """§6: the materialised state, keys sorted in UTF-8 byte order, byte-stable for a given chain."""
        state: dict = {}
        for r in self._load():
            if r["op"] == "put":
                state[r["key"]] = r["value"]
            else:
                state.pop(r["key"], None)
        doc = {k: state[k] for k in sorted(state, key=lambda s: s.encode("utf-8"))}
        return (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")

    def repair_tail(self) -> bool:
        """§7: remove exactly a truncated final line; a clean chain is a no-op; anything else is refused."""
        data = self.path.read_bytes()
        _, bad = scan(data)
        if bad is None:
            return False
        lines = data.split(b"\n")
        if lines and lines[-1] == b"":
            lines.pop()
        truncated = not data.endswith(b"\n") and bad == len(lines) - 1
        if not truncated:
            raise CorruptionError(bad, "corruption is not a truncated tail; refusing")
        write_atomic(self.path, data[: len(data) - len(lines[-1])])
        return True
