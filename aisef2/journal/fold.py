"""RFC §21 — every read model is a pure fold of a journal prefix; a cache is a shortcut, never an authority.

* **A projection** has an `id`, a `version`, `initial()` and `step(state, event) -> state`. `step` is pure: it reads
  the state it is given — frozen here, so it cannot change it — and returns the next one. States are JSON values, so
  they serialise deterministically (`canonical`). A step that meets an event the projection's rules forbid raises
  `ProjectionError`: the journal violates them, and nothing of the fold is returned.
* `fold(projection, events)` is the from-scratch fold. `Folder` is the incremental one (events in seq order).
* **The from-scratch oracle** (`oracle_problems`): the incremental state after each prefix equals `fold(prefix)`.
* **Caches.** A `CacheRow` binds a state to (projection id, version, journal length, head of that prefix) and seals
  all five with `digest`. `resume` uses a row only when the seal holds and all four still describe the journal, and
  folds the rest; otherwise the row is discarded — never migrated — and the fold starts from scratch. Its answer is
  `fold(journal)` either way: a row may be stale (its length says how stale), never wrong, and never authority
  (PROJ-1). Ceiling: the seal is a digest, not a key — a row re-sealed over a wrong state with the right head passes
  it. So no gate reads a cache (`projections.project` folds the journal); `resume` serves non-gate reads, and the
  oracle is what catches a wrong row.
* **`Authority`** advances a writer and its projections together: each projection steps the new event before a byte
  is written, so an event any projection refuses never reaches the log (§20.3).
* **No projection reads `time`** (§20.2): static check NO_TIME_IN_PROJECTIONS covers this module and projections/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from aisef2.journal.compat import Journal
from aisef2.journal.event import Event, JournalError
from aisef2.product.contract import ContractError, digest, freeze


class ProjectionError(JournalError):
    """The journal violates a projection's rules: the projection has no state for it."""


class Projection(Protocol):
    id: str
    version: int

    def initial(self) -> Any: ...

    def step(self, state: Any, event: Event) -> Any: ...


def _frozen(projection: Projection, state: Any) -> Any:
    try:
        return freeze(state)
    except ContractError as e:
        raise ProjectionError(f"{projection.id}: a state is a JSON value ({e})") from None


def fold(projection: Projection, events: Iterable[Event]) -> Any:
    """The from-scratch fold of `events` (a prefix, in seq order)."""
    state = _frozen(projection, projection.initial())
    for event in events:
        state = _frozen(projection, projection.step(state, event))
    return state


class Folder:
    """The incremental fold: `state` after every event advanced so far, in seq order."""

    def __init__(self, projection: Projection, state: Any = None, seq: int = -1) -> None:
        self.projection = projection
        self.state = _frozen(projection, projection.initial() if state is None else state)
        self.seq = seq

    def peek(self, event: Event) -> Any:
        """The state `event` would lead to; this folder is not advanced."""
        if event.seq <= self.seq:
            raise ProjectionError(f"{self.projection.id}: seq {event.seq} folded after seq {self.seq}")
        return _frozen(self.projection, self.projection.step(self.state, event))

    def advance(self, event: Event) -> Any:
        self.state, self.seq = self.peek(event), event.seq
        return self.state


def oracle_problems(projection: Projection, events: Iterable[Event], *, every: int = 1) -> list[str]:
    """The from-scratch oracle: after every `every`-th prefix (and the last), incremental == fold(prefix)."""
    events = list(events)
    folder, out = Folder(projection), []
    for n, event in enumerate(events, 1):
        folder.advance(event)
        if (n % every == 0 or n == len(events)) and folder.state != fold(projection, events[:n]):
            out.append(f"{projection.id}: incremental state after {n} events differs from fold(prefix)")
    return out


@dataclass(frozen=True)
class CacheRow:
    projection: str
    version: int
    length: int      # physical events folded (skipped ones included)
    head: str        # the journal's chain head at `length`
    state: Any
    digest: str      # seals the five fields above


def _seal(projection: str, version: int, length: int, head: str, state: Any) -> str:
    return digest({"projection": projection, "version": version, "length": length, "head": head, "state": state})


def cache_row(projection: Projection, journal: Journal) -> CacheRow:
    state = fold(projection, journal.events)
    return CacheRow(projection.id, projection.version, journal.length, journal.head(), state,
                    _seal(projection.id, projection.version, journal.length, journal.head(), state))


def resume(projection: Projection, journal: Journal, row: CacheRow | None) -> tuple[Any, str]:
    """(fold(journal), how it was reached): through `row` only when the row still describes this journal."""
    if row is None:
        why = "no cache row"
    elif row.digest != _seal(row.projection, row.version, row.length, row.head, row.state):
        why = "row does not match its seal (edited): discarded"
    elif row.projection != projection.id:
        why = f"row is for {row.projection}: discarded"
    elif row.version != projection.version:
        why = f"row version {row.version} is not {projection.version}: discarded, not migrated"
    elif not 0 <= row.length <= journal.length:
        why = f"row covers {row.length} events; the journal has {journal.length}: discarded"
    elif row.head != journal.head(row.length):
        why = "row head differs from the journal's at its length: discarded — the journal wins"
    else:
        folder = Folder(projection, row.state, row.length - 1)
        for event in journal.events:
            if event.seq >= row.length:
                folder.advance(event)
        return folder.state, f"resumed from the row at {row.length}"
    return fold(projection, journal.events), why


class Authority:
    """A journal writer and its projections, advanced together. `state(id)` is the incremental state."""

    def __init__(self, writer, projections: Iterable[Projection]) -> None:
        self.writer = writer
        self._folders: dict[str, Folder] = {}
        for p in projections:
            if p.id in self._folders:
                raise ProjectionError(f"projection {p.id} registered twice")
            self._folders[p.id] = Folder(p)
            for event in writer.events:
                self._folders[p.id].advance(event)

    def append(self, event_type, data: Mapping, *, source_seqs: tuple[int, ...] = ()) -> Event:
        pending: dict[str, Any] = {}

        def check(event: Event) -> None:
            for pid, folder in self._folders.items():
                pending[pid] = folder.peek(event)

        event = self.writer.append(event_type, data, source_seqs=source_seqs, check=check)
        for pid, folder in self._folders.items():
            folder.state, folder.seq = pending[pid], event.seq
        return event

    def state(self, projection_id: str) -> Any:
        return self._folders[projection_id].state
