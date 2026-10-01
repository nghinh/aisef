"""RFC §20 — the append-only writer. The journal is the authority; the writer is the only way into it.

* **No update and no delete verb** (§20.5): the public surface is `append` (and `emit`, its P2 sink spelling),
  `events`, `head`, `path` and `close`. Logical deletion is a new, shadowing event.
* **`seq == index` at four independent layers** (§20.1): *assignment* (`_assign`, the only source of a seq; a caller
  never supplies one), *seed admission* (opening an existing journal reconstructs it: every line's seq equals its
  position and its chain links), *append* (`event.validate` re-checks the position before the log grows) and
  *decode* (`event.decode`).
* **Validation at the append site** (§20.3): the payload is validated against format 1 and an optional `check` (the
  projections' pre-check) runs before a byte is written. A bad event fails before the log grows. A `failure/observed`
  is appended with its code only; the journal carries `owner` and `retryable` from the taxonomy (§22).
* **Synchronous** (§20.6): every append is written and fsync'd before it returns — every event may be a decision
  boundary. A failed write or fsync truncates the file back to its last complete event and poisons the writer: its
  durability is no longer known, so it accepts nothing more.
* A journal holding an event type this writer does not know (even an ignorable one), or a torn tail, is not extended:
  the first needs a writer of that format, the second needs repair (WP-4.6).
"""

from __future__ import annotations

import os
import pathlib
import time as _time
from typing import Callable, Mapping

from aisef2.arch.enums import EventType
from aisef2.journal.compat import EMPTY, reconstruct
from aisef2.journal.event import GENESIS, Event, JournalError, carried, encode, link, validate


class JournalWriter:
    def __init__(self, path: str | os.PathLike, *, clock: Callable[[], float] = _time.time) -> None:
        self._path = pathlib.Path(path)
        self._clock = clock
        existing = self._path.read_bytes().decode("utf-8") if self._path.exists() else ""
        journal = reconstruct(existing) if existing else EMPTY
        if journal.torn_tail:
            raise JournalError(f"{self._path} ends in a torn append; repair it (WP-4.6) before extending it")
        if journal.skipped:
            raise JournalError(f"{self._path} holds event types this format-1 writer does not know "
                               f"(seqs {list(journal.skipped)}); it does not extend a journal it cannot read")
        self._events: list[Event] = list(journal.events)
        self._chain: list[str] = list(journal.chain)
        self._fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o644)
        self._broken: str | None = None

    @property
    def path(self) -> pathlib.Path:
        return self._path

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    @property
    def head(self) -> str:
        return self._chain[-1] if self._chain else GENESIS

    def _assign(self) -> int:
        return len(self._events)

    def append(self, event_type: EventType, data: Mapping, *, source_seqs: tuple[int, ...] = (),
               check: Callable[[Event], None] | None = None) -> Event:
        """Validate, pre-check, write and fsync one event; return it. Raises JournalError, the log unchanged."""
        if self._broken is not None:
            raise JournalError(f"the writer failed ({self._broken}) and accepts nothing more")
        if self._fd is None:
            raise JournalError("the writer is closed")
        if not isinstance(event_type, EventType):
            raise JournalError("an event has a typed EventType")
        event = Event(self._assign(), event_type.value, carried(event_type.value, data), self._clock(), False,
                      source_seqs)
        validate(event, self._events)
        if check is not None:
            check(event)
        chain = link(self.head, event)
        line = encode(event, chain).encode("utf-8")
        size = os.fstat(self._fd).st_size
        try:
            written = os.write(self._fd, line)
            if written != len(line):
                raise OSError(f"short write: {written} of {len(line)} bytes")
            os.fsync(self._fd)
        except OSError as e:
            self._broken = f"{type(e).__name__}: {e}"
            try:
                os.ftruncate(self._fd, size)
            except OSError:
                pass  # the torn tail stays; the next reader reports it and refuses to extend it
            raise JournalError(f"append of {event.type} at seq {event.seq} failed ({self._broken}); the journal "
                               "did not grow") from None
        self._events.append(event)
        self._chain.append(chain)
        return event

    def emit(self, event_type: EventType, data: Mapping) -> None:
        """The P2 `MemorySink.emit` spelling: StoryAdmission can write to the journal unchanged."""
        self.append(event_type, data)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
