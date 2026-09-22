"""RFC §19 — RunTerminationSentinel (P4-LIFETIME-SEMANTICS.md §4). Not evidence, not authoritative state.

It answers one question: *was clean termination durably observed outside the journal?* `OPEN` is written and fsync'd
after the lease is held and before the journal is opened; `CLEAN` only after the journal writer closed successfully.
Every write is replace-after-fsync, so a `CLEAN` that cannot be recorded leaves the `OPEN` file as it was (RUN-4).
The next run's preflight reports `OPEN` as `TORN` — conservatively: a torn run may have a durable `run/end` (RUN-1) —
and names the residuals the previous run's journal records. No gate may cite the sentinel (static check
SENTINEL_IS_NOT_EVIDENCE).
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass

from aisef2.arch.enums import EventType as T
from aisef2.journal.event import JournalError

OPEN, CLEAN = "OPEN", "CLEAN"
NONE, TORN = "NONE", "TORN"


class SentinelError(Exception):
    """The sentinel could not be written as the protocol requires."""


@dataclass(frozen=True)
class Preflight:
    previous: str                    # NONE (no earlier run), CLEAN, or TORN
    run_id: str | None
    journal: str | None              # the previous run's journal: an execution locator, never an identity
    residuals: tuple[str, ...] = ()  # what that journal records as not released or not closed (§17.1)


def _fsync_dir(path: pathlib.Path) -> None:
    if os.name != "posix":
        return  # NTFS journals its metadata; a directory cannot be opened for fsync there
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: pathlib.Path, record: dict) -> None:
    """Durably replace the sentinel: write a sibling, fsync it, rename it over, fsync the directory."""
    tmp = path.with_name(path.name + ".tmp")
    data = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        if os.write(fd, data) != len(data):
            raise SentinelError(f"short write to {tmp}")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def read(path: str | os.PathLike) -> dict | None:
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        record = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "UNREADABLE"}
    return record if isinstance(record, dict) else {"state": "UNREADABLE"}


def mark_open(path: str | os.PathLike, run_id: str, journal: str | os.PathLike) -> None:
    _write(pathlib.Path(path), {"state": OPEN, "run_id": run_id, "journal": str(journal)})


def mark_clean(path: str | os.PathLike, run_id: str) -> None:
    """OPEN -> CLEAN for this run, durably, or raise with the OPEN file untouched."""
    p = pathlib.Path(path)
    current = read(p)
    if current is None or current.get("state") != OPEN or current.get("run_id") != run_id:
        raise SentinelError(f"{p} is not the OPEN sentinel of run {run_id}: {current}")
    _write(p, {**current, "state": CLEAN})


def residuals(journal_text: str) -> tuple[str, ...]:
    """What a run's journal records as not released or not closed: FAILED or RESIDUAL releases, acquisitions never
    released, tool calls and provider requests without a result."""
    from aisef2.journal.format2 import reconstruct
    try:
        j = reconstruct(journal_text)
    except JournalError as e:
        return (f"the journal cannot be reconstructed: {e}",)
    out = [f"torn tail after seq {len(j.events) - 1}"] if j.torn_tail else []
    released = {e.source_seqs[0] for e in j.events if e.type == T.STORY_RESOURCE_RELEASED.value}
    for e in j.events:
        d = e.data
        if e.type == T.STORY_RESOURCE_RELEASED.value and d["status"] != "RELEASED":
            out.append(f"{d['story_id']}: {d['kind']} {d['resource']} {d['status']}: {d['detail']}")
        elif e.type == T.STORY_RESOURCE_ACQUIRED.value and e.seq not in released:
            out.append(f"{d['story_id']}: {d['kind']} {d['resource']} acquired at seq {e.seq}, never released")
    results = {e.data["call_id"] for e in j.events if e.type == T.TOOL_RESULT.value}
    answered = {e.source_seqs[0] for e in j.events if e.type == T.PROVIDER_RESULT.value}
    out += [f"{e.data['story_id']}: tool call {e.data['call_id']} ({e.data['tool']}) has no result"
            for e in j.events if e.type == T.TOOL_INVOKED.value and e.data["call_id"] not in results]
    fmt2 = bool(j.events) and j.events[0].data["journal_format"] == 2
    out += [f"{e.data['story_id']}: provider/request at seq {e.seq} has no result" for e in j.events
            if fmt2 and e.type == T.PROVIDER_REQUEST.value and e.seq not in answered]
    return tuple(out)


def preflight(path: str | os.PathLike) -> Preflight:
    """The previous run, as the sentinel and its journal record it. Read only after the lease is held (§18.1)."""
    record = read(path)
    if record is None:
        return Preflight(NONE, None, None)
    state = CLEAN if record.get("state") == CLEAN else TORN
    journal = record.get("journal")
    found: tuple[str, ...] = ()
    if isinstance(journal, str) and pathlib.Path(journal).exists():
        found = residuals(pathlib.Path(journal).read_bytes().decode("utf-8"))
    elif state == TORN:
        found = (f"the journal {journal!r} is missing",)
    return Preflight(state, record.get("run_id"), journal, found)
