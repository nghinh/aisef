"""RFC §35 — journal format 2: a format bump through the frozen compatibility mechanism (P4-LIFETIME-SEMANTICS.md §1).

Format 1 (`aisef2.journal.event`, `compat`, `writer`) is sealed and unchanged. Format 2 is declared the same way — once,
in `run/begin` at seq 0 — and uses the same envelope, vocabulary, codec and chain.

* **A format-1 type means the same in both formats**: every format-1 type except the three below is validated by the
  format-1 validator itself (`event.validate`). `run/begin` declares format 2; `run/interrupted` and `run/end` may carry
  `synthetic: true` (a repair closer). A format-1 journal can contain neither.
* **New schemas** for vocabulary types format 1 could not write: resource ownership (`story/resource-acquired`,
  `story/resource-released`), identity (`capability/resolved`, `run/spec-resolved`) and operations (`tool/invoked`,
  `tool/result`, `provider/result`). Their rules read the journal before them (`_RULES`).
* **`reconstruct`** reads either format: a format-1 journal with the P3 reader, a format-2 journal under these schemas,
  anything else refused. **`JournalWriter2`** writes format 2 only and never extends a format-1 journal.
"""

from __future__ import annotations

import os
import pathlib
import time as _time
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from aisef2.arch.enums import Enforcement, EventType as T, IdentityGrade
from aisef2.journal import compat
from aisef2.journal import event as ev
from aisef2.journal.compat import EMPTY, Journal, UnknownRequiredEvent
from aisef2.journal.event import GENESIS, VOCABULARY, Event, JournalError, Schema, carried, decode, encode, link

FORMAT = 2


class ResourceKind(Enum):  # §18: what a StoryScope owns
    SESSION = "SESSION"
    TOOL_GRANT = "TOOL_GRANT"
    REVIEW_SCOPE = "REVIEW_SCOPE"
    PROCESS_RANGE = "PROCESS_RANGE"
    SANDBOX = "SANDBOX"
    WORKTREE = "WORKTREE"
    SCRATCH = "SCRATCH"


#: §17.1: processes reaped and the range proved empty -> sandbox -> worktree -> scratch. Disposal is in non-decreasing
#: rank, so acquisition is in non-increasing rank.
DISPOSAL_RANK: Mapping[ResourceKind, int] = MappingProxyType({
    ResourceKind.SESSION: 0, ResourceKind.TOOL_GRANT: 0, ResourceKind.REVIEW_SCOPE: 0, ResourceKind.PROCESS_RANGE: 1,
    ResourceKind.SANDBOX: 2, ResourceKind.WORKTREE: 3, ResourceKind.SCRATCH: 4})


class ReleaseStatus(Enum):
    RELEASED = "RELEASED"
    FAILED = "FAILED"        # the release raised; its error is the detail
    RESIDUAL = "RESIDUAL"    # not released: named for the next run's preflight


class OperationOutcome(Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SIGNALLED = "SIGNALLED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"  # §20.2 closer: dispatched, completion not observed
    NOT_STARTED = "NOT_STARTED"          # §20.2 closer: never dispatched


class SignalProvenance(Enum):
    CONTROLLER = "CONTROLLER"  # the controller's signal ledger holds the signal the process died of
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"              # no signal


CLOSERS = frozenset({OperationOutcome.OUTCOME_UNKNOWN.value, OperationOutcome.NOT_STARTED.value})
_GRADE_ORDER = (IdentityGrade.OPAQUE.value, IdentityGrade.ATTESTED.value, IdentityGrade.VERIFIED.value)

# --------------------------------------------------------------------------------------- schemas

_enum, _str, _text, _bool, _count = ev._enum, ev._str, ev._text, ev._bool, ev._count


def _str_map(v: Any) -> bool:
    return isinstance(v, Mapping) and all(_str(k) and _text(x) for k, x in v.items())


def _synthetic_only_true(d: Mapping) -> str | None:
    return None if d.get("synthetic", True) is True else "synthetic is written only as true (a closer); a real event " \
                                                         "omits it"


def _format_rule(d: Mapping) -> str | None:
    return None if d["journal_format"] == FORMAT else \
        f"journal format {d['journal_format']} is not format {FORMAT}: refused, never read under another format"


def _tool_result_rule(d: Mapping) -> str | None:
    signalled = d["outcome"] == OperationOutcome.SIGNALLED.value
    if d["synthetic"] is not (d["outcome"] in CLOSERS):
        return "OUTCOME_UNKNOWN and NOT_STARTED are closers, always synthetic; a measured outcome never is (§20.2)"
    if signalled is not (d["signal"] > 0):
        return "a signal number is recorded exactly when the outcome is SIGNALLED"
    if signalled is (d["provenance"] == SignalProvenance.NONE.value):
        return "a SIGNALLED outcome names its provenance (CONTROLLER or UNKNOWN); any other outcome has none"
    return None


def _provider_result_rule(d: Mapping) -> str | None:
    if d["outcome"] not in (OperationOutcome.COMPLETED.value, OperationOutcome.FAILED.value,
                            OperationOutcome.OUTCOME_UNKNOWN.value):
        return "a provider result is COMPLETED, FAILED or (a closer) OUTCOME_UNKNOWN"
    if d["synthetic"] is not (d["outcome"] == OperationOutcome.OUTCOME_UNKNOWN.value):
        return "OUTCOME_UNKNOWN is a closer, always synthetic; a measured outcome never is (§20.2)"
    return None


#: The format-2 schemas; every other format-1 type is validated by format 1 itself.
SCHEMAS: Mapping[str, Schema] = MappingProxyType({t.value: s for t, s in (
    (T.RUN_BEGIN, Schema({"journal_format": _count, "run_id": _str}, rule=_format_rule)),
    (T.RUN_INTERRUPTED, Schema({"abandoned": _bool}, {"synthetic": _bool}, rule=_synthetic_only_true)),
    (T.RUN_END, Schema({}, {"synthetic": _bool}, rule=_synthetic_only_true)),
    (T.STORY_RESOURCE_ACQUIRED, Schema({"story_id": _str, "resource": _str, "kind": _enum(ResourceKind)})),
    (T.STORY_RESOURCE_RELEASED, Schema({"story_id": _str, "resource": _str, "kind": _enum(ResourceKind),
                                        "status": _enum(ReleaseStatus), "detail": _text, "synthetic": _bool},
                                       cites=ev.Cite(T.STORY_RESOURCE_ACQUIRED, False, "story_id"))),
    (T.CAPABILITY_RESOLVED, Schema({"name": _str, "grade": _enum(IdentityGrade), "enforcement": _enum(Enforcement),
                                    "binding": _str_map, "identity": ev._hex64})),
    (T.RUN_SPEC_RESOLVED, Schema({"runspec_hash": ev._hex64, "aggregate_min_grade": _enum(IdentityGrade),
                                  "capabilities": ev._distinct_strs, "revision": ev._sha})),
    (T.TOOL_INVOKED, Schema({"story_id": _str, "call_id": _str, "tool": _str})),
    (T.TOOL_RESULT, Schema({"story_id": _str, "call_id": _str, "outcome": _enum(OperationOutcome), "signal": _count,
                            "provenance": _enum(SignalProvenance), "synthetic": _bool, "detail": _text},
                           rule=_tool_result_rule)),
    (T.PROVIDER_RESULT, Schema({"story_id": _str, "outcome": _enum(OperationOutcome), "synthetic": _bool,
                                "detail": _text}, cites=ev.Cite(T.PROVIDER_REQUEST, False, "story_id"),
                               rule=_provider_result_rule)),
)})
#: What format 2 can write: format 1's types (by format 1's own schemas) and the schemas above.
WRITABLE = frozenset(ev.SCHEMAS) | frozenset(SCHEMAS)


# --------------------------------------------------------------------------------------- rules over the journal

def _attempt(story: str, prior: Sequence[Event]) -> list[Event] | None:
    """The events of the story's current attempt (from its latest story/begin), or None if it never began."""
    start = next((e.seq for e in reversed(prior) if e.type == T.STORY_BEGIN.value and e.data["story_id"] == story),
                 None)
    return None if start is None else [e for e in prior[start:] if e.data.get("story_id") == story]


def _open_acquisitions(mine: Sequence[Event]) -> list[Event]:
    released = {e.source_seqs[0] for e in mine if e.type == T.STORY_RESOURCE_RELEASED.value}
    return [e for e in mine if e.type == T.STORY_RESOURCE_ACQUIRED.value and e.seq not in released]


def _acquired(event: Event, prior: Sequence[Event]) -> str | None:
    d = event.data
    mine = _attempt(d["story_id"], prior)
    if mine is None:
        return f"{d['story_id']} has not begun"
    if any(e.type in (T.STORY_DISPOSE.value, T.STORY_END.value) for e in mine):
        return f"{d['story_id']} is disposing: an acquisition is refused (INACTIVE_ACQUIRE, §17.1)"
    acquired = [e for e in mine if e.type == T.STORY_RESOURCE_ACQUIRED.value]
    if any(e.data["resource"] == d["resource"] for e in acquired):
        return f"resource {d['resource']!r} is already acquired in this attempt of {d['story_id']}"
    if acquired and DISPOSAL_RANK[ResourceKind(d["kind"])] > DISPOSAL_RANK[ResourceKind(acquired[-1].data["kind"])]:
        return (f"{d['kind']} after {acquired[-1].data['kind']}: reverse disposal would release it later "
                "(§17.1: processes -> sandbox -> worktree -> scratch)")
    return None


def _released(event: Event, prior: Sequence[Event]) -> str | None:
    d = event.data
    cited = prior[event.source_seqs[0]]
    if (cited.data["resource"], cited.data["kind"]) != (d["resource"], d["kind"]):
        return f"cites the acquisition of {cited.data['resource']!r} ({cited.data['kind']}), not this resource"
    unreleased = _open_acquisitions(_attempt(d["story_id"], prior) or [])
    if cited not in unreleased:
        return f"{d['resource']!r} is not an unreleased acquisition of the current attempt of {d['story_id']}"
    if unreleased[-1] is not cited:
        return (f"{d['resource']!r} released before {unreleased[-1].data['resource']!r}, acquired after it: disposal "
                "is in reverse acquisition order (§17.1)")
    return None


def _capability(event: Event, prior: Sequence[Event]) -> str | None:
    if any(e.type == T.CAPABILITY_RESOLVED.value and e.data["name"] == event.data["name"] for e in prior):
        return f"capability {event.data['name']!r} is resolved once per run"
    return None


def _spec(event: Event, prior: Sequence[Event]) -> str | None:
    d = event.data
    if any(e.type == T.RUN_SPEC_RESOLVED.value for e in prior):
        return "the RunSpec is resolved once per run"
    grades = {e.data["name"]: e.data["grade"] for e in prior if e.type == T.CAPABILITY_RESOLVED.value}
    missing = [c for c in d["capabilities"] if c not in grades]
    if missing:
        return f"capabilities {missing} were not resolved before the RunSpec"
    weakest = min((grades[c] for c in d["capabilities"]), key=_GRADE_ORDER.index)
    if d["aggregate_min_grade"] != weakest:
        return f"aggregate_min_grade {d['aggregate_min_grade']} is not the weakest grade, {weakest} (§23)"
    return None


def _invoked(event: Event, prior: Sequence[Event]) -> str | None:
    d = event.data
    if any(e.type == T.TOOL_INVOKED.value and e.data["call_id"] == d["call_id"] for e in prior):
        return f"call {d['call_id']!r} was already invoked"
    mine = _attempt(d["story_id"], prior)
    if mine is None or any(e.type == T.STORY_END.value for e in mine):
        return f"{d['story_id']} has no open attempt to invoke a tool in"
    return None


def _tool_result(event: Event, prior: Sequence[Event]) -> str | None:
    d = event.data
    if any(e.type == T.TOOL_RESULT.value and e.data["call_id"] == d["call_id"] for e in prior):
        return f"call {d['call_id']!r} already has its result"
    invoked = [e for e in prior if e.type == T.TOOL_INVOKED.value and e.data["call_id"] == d["call_id"]]
    if d["outcome"] == OperationOutcome.NOT_STARTED.value:
        if invoked or event.source_seqs:
            return "NOT_STARTED closes a call that was never dispatched: it has no tool/invoked and cites none"
        return None if _attempt(d["story_id"], prior) is not None else f"{d['story_id']} has not begun"
    if list(event.source_seqs) != [e.seq for e in invoked] or not invoked:
        return f"a result cites the tool/invoked of call {d['call_id']!r}, and only it"
    if invoked[0].data["story_id"] != d["story_id"]:
        return f"call {d['call_id']!r} was invoked for {invoked[0].data['story_id']}, not {d['story_id']}"
    return None


def _provider_result(event: Event, prior: Sequence[Event]) -> str | None:
    request = event.source_seqs[0]
    if any(e.type == T.PROVIDER_RESULT.value and e.source_seqs == (request,) for e in prior):
        return f"the provider/request at seq {request} already has its result"
    return None


_RULES: Mapping[str, Callable[[Event, Sequence[Event]], str | None]] = MappingProxyType({
    T.STORY_RESOURCE_ACQUIRED.value: _acquired, T.STORY_RESOURCE_RELEASED.value: _released,
    T.CAPABILITY_RESOLVED.value: _capability, T.RUN_SPEC_RESOLVED.value: _spec, T.TOOL_INVOKED.value: _invoked,
    T.TOOL_RESULT.value: _tool_result, T.PROVIDER_RESULT.value: _provider_result})


def validate(event: Event, prior: Sequence[Event]) -> None:
    """A format-2 event against the journal before it. Raises JournalError."""
    if event.type in ev.SCHEMAS and event.type not in SCHEMAS:
        ev.validate(event, prior)  # a format-1 type: format 1's own validator, so it means the same
        return
    if event.seq != len(prior):
        raise JournalError(f"{event.type} at seq {event.seq}, but the journal holds {len(prior)} events: seq == index")
    schema = SCHEMAS.get(event.type)
    if schema is None:
        why = f"has no payload schema in journal format {FORMAT}; writing it is a format version bump (§35)" \
            if event.type in VOCABULARY else "is not in the event vocabulary"
        raise JournalError(f"{event.type} {why}")
    if event.ignorable:
        raise JournalError(f"{event.type} is a required event in format {FORMAT}; it is never ignorable")
    if (event.seq == 0) is not (event.type == T.RUN_BEGIN.value):
        raise JournalError(f"{event.type} at seq {event.seq}: a journal begins with run/begin, and only once")
    d = event.data
    kinds = {**schema.required, **schema.optional}
    missing = [k for k in schema.required if k not in d]
    unknown = [k for k in d if k not in kinds]
    if missing or unknown:
        raise JournalError(f"{event.type}: fields missing {missing}, not in the schema {unknown}")
    bad = [k for k, v in d.items() if not kinds[k](v)]
    if bad:
        raise JournalError(f"{event.type}: fields of the wrong kind or enum {bad}")
    why = schema.rule(d) if schema.rule else None
    if why:
        raise JournalError(f"{event.type}: {why}")
    if event.type != T.TOOL_RESULT.value:  # a tool result's citation depends on its outcome: its rule checks it
        _cites(event, schema.cites, prior)
    rule = _RULES.get(event.type)
    why = rule(event, prior) if rule else None
    if why:
        raise JournalError(f"{event.type}: {why}")


def _cites(event: Event, cite: ev.Cite | None, prior: Sequence[Event]) -> None:
    if cite is None:
        if event.source_seqs:
            raise JournalError(f"{event.type} cites no event in format {FORMAT}")
        return
    cited = [prior[s] for s in event.source_seqs]
    if len(cited) != 1:
        raise JournalError(f"{event.type} cites exactly one {cite.type.value}")
    if cited[0].type != cite.type.value or cited[0].data.get(cite.key) != event.data[cite.key]:
        raise JournalError(f"{event.type} cites {cited[0].seq}: not a {cite.type.value} with the same {cite.key}")


# --------------------------------------------------------------------------------------- the reader

def declared_format(text: str) -> int | None:
    """The format `run/begin` declares on the first line, or None when there is no complete first run/begin."""
    first, sep, _ = text.partition("\n")
    if not sep:
        return None
    event, _ = decode(first, 0, GENESIS)
    if event.type != T.RUN_BEGIN.value or not _count(event.data.get("journal_format")):
        return None
    return event.data["journal_format"]


def reconstruct(text: str) -> Journal:
    """The journal `text` holds, under the format it declares (1 or 2) — or JournalError; never partial."""
    if not isinstance(text, str):
        raise JournalError("a journal is read as text")
    fmt = declared_format(text)
    if fmt is None or fmt == ev.FORMAT:
        return compat.reconstruct(text)  # format 1, or what format 1 refuses or reports (torn, not a run/begin)
    if fmt != FORMAT:
        raise JournalError(f"journal format {fmt} is neither format {ev.FORMAT} nor format {FORMAT}: refused")
    lines = text.split("\n")
    torn = lines.pop() != ""
    prior: list[Event] = []
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


# --------------------------------------------------------------------------------------- the writer

class JournalWriter2:
    """The P3 writer's discipline for format 2 (writer.py): no update or delete verb; `seq == index` assigned here,
    admitted on open, re-checked at append and on decode; validation and the pre-check before a byte is written; every
    append fsync'd; a failed write or fsync truncates back and poisons the writer."""

    def __init__(self, path: str | os.PathLike, *, clock: Callable[[], float] = _time.time) -> None:
        self._path = pathlib.Path(path)
        self._clock = clock
        existing = self._path.read_bytes().decode("utf-8") if self._path.exists() else ""
        journal = reconstruct(existing) if existing else EMPTY
        if journal.torn_tail:
            raise JournalError(f"{self._path} ends in a torn append; repair it (WP-4.6) before extending it")
        if journal.skipped:
            raise JournalError(f"{self._path} holds event types this format-2 writer does not know "
                               f"(seqs {list(journal.skipped)}); it does not extend a journal it cannot read")
        if journal.events and journal.events[0].data["journal_format"] != FORMAT:
            raise JournalError(f"{self._path} is a format-{journal.events[0].data['journal_format']} journal: it is "
                               "read, never extended under another format")
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

    def append(self, event_type: T, data: Mapping, *, source_seqs: tuple[int, ...] = (),
               check: Callable[[Event], None] | None = None, time: float | None = None) -> Event:
        """Validate, pre-check, write and fsync one event; return it. Raises JournalError, the log unchanged. `time`
        is given only by repair, whose closers reuse the last real event's time (§20.2)."""
        if self._broken is not None:
            raise JournalError(f"the writer failed ({self._broken}) and accepts nothing more")
        if self._fd is None:
            raise JournalError("the writer is closed")
        if not isinstance(event_type, T):
            raise JournalError("an event has a typed EventType")
        event = Event(self._assign(), event_type.value, carried(event_type.value, data),
                      self._clock() if time is None else time, False, source_seqs)
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

    def emit(self, event_type: T, data: Mapping) -> None:
        self.append(event_type, data)

    def close(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)
