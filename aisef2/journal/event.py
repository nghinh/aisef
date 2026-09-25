"""RFC §20 — the event envelope (F1) and journal format 1: payload schemas, validation, the line codec.

* **`Event`** is the RFC's envelope, field for field. `seq` is dense — `seq == index` — and never a timestamp. `time`
  is recorded and never read by a projection (static check NO_TIME_IN_PROJECTIONS). `ignorable` is the author's
  claim that a reader may skip the type.
* **Journal format 1** (`FORMAT`). Every type a format-1 writer may write has a payload schema in `SCHEMAS`: its
  fields exactly, each field's kind (typed enums by value), the events it must cite in `source_seqs`, and any rule
  across fields. A type of the frozen vocabulary with no schema here cannot be written in format 1: giving it one is
  a format version bump, a writer-side obligation (§35). Every format-1 type is required — never `ignorable`.
* **`validate(event, prior)`** runs at the append site and again on decode: a bad event fails before the log grows,
  and a bad line fails reconstruction.
* **Storage.** One canonical JSON line per event, `{"chain", "event"}`, where `chain_n = sha256(chain_{n-1} ‖
  event_id_n)` from `GENESIS`. Editing or removing an old event breaks every later link; the last link, `head`, is the
  journal's identity for a prefix. Ceiling: a tail rewritten together with its links is caught only against an anchor
  held outside the journal (a cache row, an evidence record) — `head` is what such anchors bind.
* **Historical code set.** `failure/observed` under format 1 (and format 2, which reuses this schema) admits exactly
  the codes the formats were written with (`FORMAT_2_CODES`); the nine V2-005 codes are format 3's (§35, FMT3-5).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from aisef2.arch.enums import ControlProjection, EventType, ObligationRole, Owner, StoryAdmissionDisposition
from aisef2.control.owner import FORMAT_2_CODES, TAXONOMY, FailureCode
from aisef2.plan.drift import UNATTRIBUTED
from aisef2.plan.story_admission import BLOCKING
from aisef2.product.contract import ContractError, canonical, freeze

FORMAT = 1
GENESIS = "0" * 64
_SHA = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
VOCABULARY = frozenset(t.value for t in EventType)


class JournalError(ValueError):
    """A journal, or an event offered to one, is not valid. Nothing of it is authoritative."""


def _count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


@dataclass(frozen=True)
class Event:
    seq: int                            # dense: seq == index. MUST NOT be a timestamp.
    type: str                           # the discriminant
    data: Mapping[str, Any]             # JSON-lossless; validated at the append site
    time: float                         # recorded; MUST NOT be read by any projection
    ignorable: bool = False             # explicit author-side claim that a reader may skip this type
    source_seqs: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not _count(self.seq):
            raise JournalError(f"seq is a dense index, a non-negative int: {self.seq!r}")
        if not isinstance(self.type, str) or not self.type:
            raise JournalError("an event has a non-empty type")
        if not isinstance(self.data, Mapping):
            raise JournalError(f"{self.type}: data is a mapping")
        try:
            object.__setattr__(self, "data", freeze(self.data))
        except ContractError as e:
            raise JournalError(f"{self.type}: data is not JSON-lossless: {e}") from None
        if isinstance(self.time, bool) or not isinstance(self.time, (int, float)) or not math.isfinite(self.time):
            raise JournalError(f"{self.type}: time is a finite number")
        object.__setattr__(self, "time", float(self.time))
        if not isinstance(self.ignorable, bool):
            raise JournalError(f"{self.type}: ignorable is a bool")
        seqs = tuple(self.source_seqs) if isinstance(self.source_seqs, (list, tuple)) else None
        if seqs is None or not all(_count(s) for s in seqs) or any(a >= b for a, b in itertools.pairwise(seqs)) \
                or any(s >= self.seq for s in seqs):
            raise JournalError(f"{self.type}: source_seqs cite earlier events, each once, in order")
        object.__setattr__(self, "source_seqs", seqs)


def event_id(event: Event) -> str:
    """The event's content identity: sha256 of its canonical envelope."""
    return hashlib.sha256(canonical(event).encode("utf-8")).hexdigest()


def link(prev: str, event: Event) -> str:
    return hashlib.sha256((prev + event_id(event)).encode("ascii")).hexdigest()


# --------------------------------------------------------------------------------------- format 1 schemas

def _str(v: Any) -> bool:
    return isinstance(v, str) and v != ""


def _text(v: Any) -> bool:
    return isinstance(v, str)


def _sha(v: Any) -> bool:
    return isinstance(v, str) and _SHA.fullmatch(v) is not None


def _hex64(v: Any) -> bool:
    return isinstance(v, str) and _HEX64.fullmatch(v) is not None


def _bool(v: Any) -> bool:
    return isinstance(v, bool)


def _strs(v: Any) -> bool:
    return isinstance(v, tuple) and all(_str(x) for x in v)


def _distinct_strs(v: Any) -> bool:
    return _strs(v) and len(v) > 0 and len(set(v)) == len(v)


def _object(v: Any) -> bool:
    return isinstance(v, Mapping)


def _enum(e) -> Callable[[Any], bool]:
    values = frozenset(m.value for m in e)
    return lambda v: isinstance(v, str) and v in values


def _codes(names: frozenset[str]) -> Callable[[Any], bool]:
    """A FailureCode member whose name is in `names`: the code set a journal format was written with."""
    return lambda v: isinstance(v, str) and v in names and v in {c.value for c in FailureCode}


def _enums(e) -> Callable[[Any], bool]:
    one = _enum(e)
    return lambda v: isinstance(v, tuple) and len(v) > 0 and all(one(x) for x in v)


def _enum_map(e) -> Callable[[Any], bool]:
    one = _enum(e)
    return lambda v: isinstance(v, Mapping) and all(_str(k) and one(x) for k, x in v.items())


@dataclass(frozen=True)
class Cite:
    """The events an event must cite: `type`, exactly one (`many` False) or at least one, sharing `key`'s value."""
    type: EventType
    many: bool
    key: str


@dataclass(frozen=True)
class Schema:
    required: Mapping[str, Callable[[Any], bool]]
    optional: Mapping[str, Callable[[Any], bool]] = field(default_factory=dict)
    cites: Cite | None = None
    rule: Callable[[Mapping[str, Any]], str | None] | None = None


def _format_rule(d: Mapping) -> str | None:
    return None if d["journal_format"] == FORMAT else \
        f"journal format {d['journal_format']} is not format {FORMAT}: refused, never read under another format"


def _admission_rule(d: Mapping) -> str | None:
    blocked = any(StoryAdmissionDisposition(v) in BLOCKING for v in d["dispositions"].values())
    ready = any(v == StoryAdmissionDisposition.READY.value for v in d["dispositions"].values())
    if not d["dispositions"]:
        return "an admission records at least one disposition"
    if d["admitted"] is blocked or d["developer_call_permitted"] is not (d["admitted"] and ready):
        return "admitted and developer_call_permitted are those the dispositions derive (§13)"
    return None


def _drift_rule(d: Mapping) -> str | None:
    want = d["candidates"][0] if len(d["candidates"]) == 1 else UNATTRIBUTED
    return None if d["attributed_to"] == want else \
        f"attributed_to {d['attributed_to']!r}: with candidates {list(d['candidates'])} it is {want!r} (§14)"


def _failure_rule(d: Mapping) -> str | None:
    code = FailureCode(d["code"])
    c = TAXONOMY[code]
    if (d["owner"], d["retryable"]) != (c.owner.value, c.budget is not None):
        return (f"{code.value} carries owner {d['owner']}, retryable {d['retryable']}; the taxonomy fixes "
                f"{c.owner.value}, {c.budget is not None} — a call site never decides them (§22)")
    if (code is FailureCode.UNKNOWN) is not ("original" in d):
        return "a foreign error flattens to UNKNOWN and keeps its original as data; only UNKNOWN carries one (§22)"
    return None


SCHEMAS: Mapping[str, Schema] = MappingProxyType({t.value: s for t, s in (
    (EventType.RUN_BEGIN, Schema({"journal_format": _count, "run_id": _str}, rule=_format_rule)),
    (EventType.RUN_DISPOSE_BEGIN, Schema({})),
    (EventType.RUN_INTERRUPTED, Schema({"abandoned": _bool})),
    (EventType.RUN_END, Schema({})),
    (EventType.PLAN_FROZEN, Schema({"plan_id": _str, "plan_hash": _hex64, "roles": _enum_map(ObligationRole)})),
    (EventType.STORY_BEGIN, Schema({"story_id": _str, "parent": _sha})),
    (EventType.STORY_ADMITTED, Schema({"story_id": _str, "parent": _sha, "admitted": _bool,
                                       "developer_call_permitted": _bool,
                                       "dispositions": _enum_map(StoryAdmissionDisposition)}, rule=_admission_rule)),
    (EventType.STORY_PLAN_DRIFT, Schema({"story_id": _str, "criterion_id": _str, "spec_id": _str,
                                         "attributed_to": _str, "candidates": _strs}, rule=_drift_rule)),
    (EventType.STORY_COMMIT, Schema({"story_id": _str, "revision": _sha})),
    (EventType.STORY_ROLLBACK, Schema({"story_id": _str}, cites=Cite(EventType.FAILURE_OBSERVED, False, "story_id"))),
    (EventType.STORY_RETRY, Schema({"story_id": _str}, cites=Cite(EventType.FAILURE_OBSERVED, False, "story_id"))),
    (EventType.STORY_DISPOSE, Schema({"story_id": _str})),
    (EventType.STORY_END, Schema({"story_id": _str})),
    (EventType.PROBE_EVALUATED, Schema({"story_id": _str, "criterion_id": _str, "record": _object})),
    (EventType.PROVIDER_REQUEST, Schema({"story_id": _str, "criteria": _distinct_strs})),
    (EventType.FAILURE_OBSERVED, Schema({"story_id": _str, "code": _codes(FORMAT_2_CODES), "owner": _enum(Owner),
                                         "retryable": _bool, "detail": _text}, {"original": _str},
                                        rule=_failure_rule)),
    (EventType.GATE_CHECK, Schema({"gate": _str, "check": _str, "passed": _bool, "detail": _text})),
    (EventType.GATE_DECISION, Schema({"gate": _str, "passed": _bool, "projections": _enums(ControlProjection)},
                                     cites=Cite(EventType.GATE_CHECK, True, "gate"))),
)})


def carried(event_type: str, data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The payload as written: `failure/observed` carries `owner` and `retryable` from the taxonomy (§22) — the call
    site names the code and never supplies either. Every other type is written as given."""
    if event_type != EventType.FAILURE_OBSERVED.value:
        return data
    if not isinstance(data, Mapping) or {"owner", "retryable"} & set(data):
        raise JournalError("failure/observed: owner and retryable come from the taxonomy, never from the call site "
                           "(§22)")
    if data.get("code") not in {c.value for c in FailureCode}:
        raise JournalError(f"failure/observed: code {data.get('code')!r} is not a taxonomy code; a foreign error "
                           "flattens to UNKNOWN (§22)")
    c = TAXONOMY[FailureCode(data["code"])]
    return {**data, "owner": c.owner.value, "retryable": c.budget is not None}


def validate(event: Event, prior: Sequence[Event]) -> None:
    """A format-1 event against the journal before it: position, type, payload, citations. Raises JournalError."""
    if event.seq != len(prior):
        raise JournalError(f"{event.type} at seq {event.seq}, but the journal holds {len(prior)} events: seq == index")
    schema = SCHEMAS.get(event.type)
    if schema is None:
        why = f"has no payload schema in journal format {FORMAT}; writing it is a format version bump (§35)" \
            if event.type in VOCABULARY else "is not in the event vocabulary"
        raise JournalError(f"{event.type} {why}")
    if event.ignorable:
        raise JournalError(f"{event.type} is a required event in format {FORMAT}; it is never ignorable")
    if (event.seq == 0) is not (event.type == EventType.RUN_BEGIN.value):
        raise JournalError(f"{event.type} at seq {event.seq}: a journal begins with run/begin, and only once")
    d = event.data  # frozen: its keys iterate sorted
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
    _cites(event, schema.cites, prior)


def _cites(event: Event, cite: Cite | None, prior: Sequence[Event]) -> None:
    if cite is None:
        if event.source_seqs:
            raise JournalError(f"{event.type} cites no event in format {FORMAT}")
        return
    cited = [prior[s] for s in event.source_seqs]
    if not cited or (not cite.many and len(cited) != 1):
        raise JournalError(f"{event.type} cites {'at least one' if cite.many else 'exactly one'} {cite.type.value}")
    wrong = [e.seq for e in cited if e.type != cite.type.value or e.data.get(cite.key) != event.data[cite.key]]
    if wrong:
        raise JournalError(f"{event.type} cites {wrong}: not a {cite.type.value} with the same {cite.key}")


# --------------------------------------------------------------------------------------- the line codec

_FIELDS = tuple(f.name for f in fields(Event))


def encode(event: Event, chain: str) -> str:
    return canonical({"chain": chain, "event": event}) + "\n"


def decode(line: str, index: int, prev: str) -> tuple[Event, str]:
    """One stored line at physical position `index`: its envelope, `seq == index`, its chain link, its canonical form.
    The payload is not validated here — that is the reader's (compat.reconstruct), which knows the format."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        raise JournalError(f"line {index} is not JSON") from None
    if not isinstance(obj, dict) or set(obj) != {"chain", "event"} or not isinstance(obj["event"], dict) \
            or set(obj["event"]) != set(_FIELDS):
        raise JournalError(f"line {index} is not a stored event {{chain, event: {list(_FIELDS)}}}")
    event = Event(**obj["event"])
    if event.seq != index:
        raise JournalError(f"line {index} holds seq {event.seq}: seq == index is broken (a gap, a duplicate or a "
                           "reordering); the journal is refused, never partially read")
    chain = link(prev, event)
    if obj["chain"] != chain:
        raise JournalError(f"line {index}: the chain does not link — an earlier event was edited or removed, or this "
                           "one was")
    if line != encode(event, chain).rstrip("\n"):
        raise JournalError(f"line {index} is not the canonical encoding of its event")
    return event, chain
