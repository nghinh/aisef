"""RFC §20 property 4, §35 — the one reader: reconstruction under journal format 1, with format compatibility.

`reconstruct(text)` decodes every stored line and yields the events a format-1 reader may act on:

* an event of a type this format knows is validated as the writer validated it (`event.validate`); a malformed one
  refuses the whole journal;
* an **unknown type marked `ignorable`** is skipped — its seq is kept, it is never folded — and reconstruction goes on;
* an **unknown type without `ignorable`** refuses reconstruction: never a partial state, never a default meaning;
* the journal declares its format once, in `run/begin` at seq 0; another format, or a second declaration later in the
  stream (a mixed stream), is refused;
* a final chunk without its line end is a **torn tail**: an append that never completed. It is reported, never
  decoded and never authoritative.

A reader never negotiates: a version bump is the writer's obligation (§35).
"""

from __future__ import annotations

from dataclasses import dataclass

from aisef2.journal.event import GENESIS, VOCABULARY, Event, JournalError, decode, validate


class UnknownRequiredEvent(JournalError):
    """An event type this reader does not know, not marked ignorable: the journal cannot be reconstructed."""


@dataclass(frozen=True)
class Journal:
    events: tuple[Event, ...]      # every event a format-1 reader acts on, in seq order
    chain: tuple[str, ...]         # chain[n] is the link after physical line n (skipped lines included)
    skipped: tuple[int, ...]       # seqs of unknown ignorable events
    torn_tail: bool                # a final chunk without its line end was present (and ignored)

    @property
    def length(self) -> int:
        """Physical events: known and skipped."""
        return len(self.chain)

    def head(self, length: int | None = None) -> str:
        """The chain link after the first `length` events (all of them by default); GENESIS for none."""
        n = self.length if length is None else length
        if not 0 <= n <= self.length:
            raise JournalError(f"no prefix of length {n} in a journal of {self.length}")
        return self.chain[n - 1] if n else GENESIS


EMPTY = Journal((), (), (), False)


def reconstruct(text: str) -> Journal:
    """The journal `text` holds, under format 1 — or JournalError; nothing partial is ever returned."""
    if not isinstance(text, str):
        raise JournalError("a journal is read as text")
    lines = text.split("\n")
    torn = lines.pop() != ""          # the chunk after the last line end: empty unless an append was torn
    prior: list[Event] = []           # every physical event, for positions and citations
    known, chain, skipped = [], [], []
    prev = GENESIS
    for n, line in enumerate(lines):
        event, prev = decode(line, n, prev)
        if event.type in VOCABULARY:
            validate(event, prior)
            known.append(event)
        elif event.ignorable:
            skipped.append(event.seq)
        else:
            raise UnknownRequiredEvent(f"seq {n}: unknown event type {event.type!r} is not marked ignorable — this "
                                       "reader refuses to reconstruct the journal (§20.4)")
        prior.append(event)
        chain.append(prev)
    return Journal(tuple(known), tuple(chain), tuple(skipped), torn)
