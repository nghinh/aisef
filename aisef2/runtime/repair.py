"""RFC §20.2 — repair of a journal whose writer died (WP-4.6; P4-LIFETIME-SEMANTICS.md §7).

`closers` names what the journal left open, as synthetic events, all at the last real event's time:

* every tool call without a result: `tool/result` OUTCOME_UNKNOWN (it was dispatched; its outcome was not observed);
* every provider request without a result: `provider/result` OUTCOME_UNKNOWN;
* every unreleased resource, in reverse acquisition order: `story/resource-released` RESIDUAL — named for the next run;
* the run: `run/interrupted` (abandoned when it had already been interrupted: this is the second interruption) and,
  unless abandoned, `run/end`.

`repair(text)` is a pure function: the complete lines, unchanged byte for byte (a torn tail was never an event and is
dropped), then the closers. A repaired journal has nothing open, so repairing it again adds nothing; the same journal
repaired twice gives the same bytes. Formats 2 and 3 are repaired (V2-005): every closer type has the same schema in
both formats, so the closers are validated once, under the format-3 rules, and the journal keeps the format it
declares; a format-1 journal is read, never extended. Repair never touches the sentinel — the run stays TORN — and
never creates a sequence gap.
"""

from __future__ import annotations

import os
import pathlib
from typing import Sequence

from aisef2.arch.enums import ControlProjection as P, EventType as T
from aisef2.journal import format2 as f2
from aisef2.journal import format3 as f3
from aisef2.journal.event import Event, JournalError, carried, encode, link
from aisef2.journal.fold import fold
from aisef2.journal.projections import PROJECTIONS


class RepairError(JournalError):
    """The journal cannot be repaired (it is format 1, or it does not reconstruct)."""


def closers(events: Sequence[Event]) -> list[tuple[T, dict, tuple[int, ...]]]:
    """What `events` leaves open, as (type, payload, cites) — empty when the run already ended or was abandoned."""
    if not events or events[0].data["journal_format"] not in (f2.FORMAT, f3.FORMAT):
        raise RepairError("repair writes format-2 closers for a format-2 journal and format-3 closers for a format-3 "
                          "journal; a format-1 journal is read, never extended")
    terminal = fold(PROJECTIONS[P.TERMINAL_STATE], events)
    if terminal["run"] in ("ENDED", "ABANDONED"):
        return []
    out: list[tuple[T, dict, tuple[int, ...]]] = []
    results = {e.data["call_id"] for e in events if e.type == T.TOOL_RESULT.value}
    for e in events:
        if e.type == T.TOOL_INVOKED.value and e.data["call_id"] not in results:
            out.append((T.TOOL_RESULT, {"story_id": e.data["story_id"], "call_id": e.data["call_id"],
                                        "outcome": "OUTCOME_UNKNOWN", "signal": 0, "provenance": "NONE",
                                        "synthetic": True, "detail": "the run ended without its result (repair)"},
                        (e.seq,)))
    answered = {e.source_seqs[0] for e in events if e.type == T.PROVIDER_RESULT.value}
    for e in events:
        if e.type == T.PROVIDER_REQUEST.value and e.seq not in answered:
            out.append((T.PROVIDER_RESULT, {"story_id": e.data["story_id"], "outcome": "OUTCOME_UNKNOWN",
                                            "synthetic": True, "detail": "the run ended without its result (repair)"},
                        (e.seq,)))
    stories = sorted({e.data["story_id"] for e in events if e.type == T.STORY_RESOURCE_ACQUIRED.value})
    for story in stories:
        for acquired in reversed(f2._open_acquisitions(f2._attempt(story, events) or [])):
            d = acquired.data
            out.append((T.STORY_RESOURCE_RELEASED, {
                "story_id": story, "resource": d["resource"], "kind": d["kind"], "status": "RESIDUAL",
                "detail": "not released: the run ended without disposing it (repair)", "synthetic": True},
                (acquired.seq,)))
    abandoned = terminal["interrupts"] > 0
    out.append((T.RUN_INTERRUPTED, {"abandoned": abandoned, "synthetic": True}, ()))
    if not abandoned:
        out.append((T.RUN_END, {"synthetic": True}, ()))
    return out


def repair(text: str) -> str:
    """`text` with a torn tail dropped and the closers appended. Pure and idempotent."""
    try:
        journal = f3.reconstruct(text)  # formats 1, 2 and 3, each read as written
    except JournalError as e:
        raise RepairError(f"the journal does not reconstruct, so it cannot be repaired: {e}") from None
    complete = text[:text.rfind("\n") + 1]
    events = list(journal.events)
    if journal.skipped:
        raise RepairError(f"the journal holds unknown ignorable events {list(journal.skipped)}: repair extends only a "
                          "journal it can read in full")
    when = next((e.time for e in reversed(events) if not e.data.get("synthetic")), 0.0)
    prev, lines = journal.head(), []
    for event_type, data, cites in closers(events):  # computed in full before the loop extends `events`
        event = Event(len(events), event_type.value, carried(event_type.value, data), when, False, cites)
        f3.validate(event, events)  # the closer schemas are the same objects in formats 2 and 3 (test_v2_005)
        events.append(event)
        prev = link(prev, event)
        lines.append(encode(event, prev))
    for p in PROJECTIONS.values():
        fold(p, events)  # the six projections accept the closed journal, or ProjectionError says why
    return complete + "".join(lines)


def repair_journal(path: str | os.PathLike) -> bool:
    """Repair the journal file in place: its complete lines are kept byte for byte; the closers are appended by a
    durable replace. False when there was nothing to repair."""
    p = pathlib.Path(path)
    text = p.read_bytes().decode("utf-8")
    fixed = repair(text)
    if fixed == text:
        return False
    if not fixed.startswith(text[:text.rfind("\n") + 1]):
        raise RepairError("repair would change an existing event")  # it never does: a guard, not a path
    tmp = p.with_name(p.name + ".repair")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        data = fixed.encode("utf-8")
        if os.write(fd, data) != len(data):
            raise RepairError(f"short write to {tmp}")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, p)
    return True
