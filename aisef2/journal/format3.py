"""RFC §35 — journal format 3: the bump ARCHITECTURE-EXCEPTION-V2-005 approved (owner resolution of the WP-6.2 schema
stop, 2026-09-25 §2–§8, §12).

Formats 1 (`event`, `compat`, `writer`) and 2 (`format2`) are sealed and unchanged: each is read exactly as it was
written, and neither is ever rewritten or upgraded in place (FMT3-7). Format 3 is declared the same way — once, in
`run/begin` at seq 0 — and uses the same envelope, vocabulary, codec and chain.

* **Every one of the 29 vocabulary types has an append-site payload schema** (FMT3-1): formats 1 and 2 kept 25; the
  four that had none — `plan/static-admitted`, `proof/verified`, `tests/adequacy`, `invariant/violated` — are derived
  here from the existing typed objects (`StaticPlanAdmissionResult`, RFC §16's `VerifiedProof`, `EngineeringTestAdequacy`
  and its `TestExecution` axes, `InvariantError`). No new event type; no prose field is control.
* **`failure/observed`** carries the whole taxonomy — the nine V2-005 codes included — and its owner and retryability
  still come from the taxonomy alone (`event.carried`, `event._failure_rule`). Formats 1 and 2 keep their historical
  code set (FMT3-5: a format-2 reader refuses a V2-005 code rather than guessing).
* **`provider/request`** requires `budget_owner` — DEVELOPER, REVIEW or SECURITY in cycle 1 (FMT3-6). The budgets
  projection charges the request to it; a provider failure keeps its own owner, PROVIDER.
* **`proof/verified`** is RFC §16's `VerifiedProof`, losslessly: it cites the implementer's and the verifier's
  `probe/evaluated` records by seq, and its rule re-derives agreement and verdict from those records
  (`verified_proof` reconstructs the object mechanically). Disagreement and instrument mismatch are not events of this
  type: they are `failure/observed` VERIFIER_DISAGREEMENT / PROBE_MISMATCH.
* **`tests/adequacy`** serialises the WP-5 typed adequacy result with its two-axis semantics: UNRUNNABLE carries no
  outcome and keeps its environment provenance; INADEQUATE is DEVELOPER-owned and chargeable; INCOMPLETE is neither
  blocking nor chargeable; ADEQUATE is the positive result.
* **`invariant/violated`** records the invariant, the owning module and a diagnostic context that no projection reads
  (FMT3-8). No correctness property depends on appending it: the `InvariantError` has already escaped.
* **`reconstruct`** reads any declared format (1, 2 or 3) with that format's own validator; anything else is refused.
  **`JournalWriter3`** writes format 3 only and never extends a format-1 or format-2 journal.
"""

from __future__ import annotations

import os
import pathlib
import time as _time
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from aisef2.arch.enums import (
    AdequacyOutcome, BehaviorVerdict, EventType as T, InvariantId, Owner, Relevance, TestExecutionStatus, TestOutcome,
    TestSelection, Vacuity,
)
from aisef2.control.owner import FailureCode
from aisef2.journal import compat
from aisef2.journal import event as ev
from aisef2.journal import format2 as f2
from aisef2.journal.compat import EMPTY, Journal, UnknownRequiredEvent
from aisef2.journal.event import GENESIS, VOCABULARY, Event, JournalError, Schema, carried, decode, encode, link

FORMAT = 3
#: cycle-1 budget owners a provider/request may name (owner resolution §8)
BUDGET_OWNERS = (Owner.DEVELOPER, Owner.REVIEW, Owner.SECURITY)
KNOWN_FORMATS = (ev.FORMAT, f2.FORMAT, FORMAT)

_enum, _str, _text, _bool, _count, _sha, _hex64, _object = (ev._enum, ev._str, ev._text, ev._bool, ev._count, ev._sha,
                                                            ev._hex64, ev._object)
_UNRUNNABLE, _EXECUTED = TestExecutionStatus.UNRUNNABLE.value, TestExecutionStatus.EXECUTED.value


def _opt(f: Callable[[Any], bool]) -> Callable[[Any], bool]:
    return lambda v: v is None or f(v)


def _budget_owner(v: Any) -> bool:
    return isinstance(v, str) and v in {o.value for o in BUDGET_OWNERS}


def _strs_or_empty(v: Any) -> bool:
    return isinstance(v, tuple) and all(_text(x) for x in v)


def _checks(v: Any) -> bool:
    """StaticPlanAdmissionResult.checks: numbered from 1 in order, each named, passed, with its problems."""
    if not isinstance(v, tuple) or not v:
        return False
    for n, c in enumerate(v, 1):
        if not isinstance(c, Mapping) or set(c) != {"number", "name", "passed", "problems"}:
            return False
        if (c["number"], _str(c["name"]), _bool(c["passed"]), _strs_or_empty(c["problems"])) != (n, True, True, True):
            return False
        if c["passed"] is bool(c["problems"]):
            return False
    return True


def _execution(v: Any) -> bool:
    """RFC §15.0's TestExecution, field for field, with the shape's own rules (UNRUNNABLE carries no outcome and no
    selection and is ENVIRONMENT; EXECUTED carries a typed outcome and selection)."""
    if not isinstance(v, Mapping) or set(v) != {"status", "outcome", "selection", "owner_on_failure", "reason"}:
        return False
    typed = (_enum(TestExecutionStatus)(v["status"]), _opt(_text)(v["reason"]), _opt(_enum(Owner))(v["owner_on_failure"]))
    if typed != (True, True, True):
        return False
    if v["status"] == _UNRUNNABLE:
        return (v["outcome"], v["selection"], v["owner_on_failure"], bool(v["reason"])) == \
            (None, None, Owner.ENVIRONMENT.value, True)
    return (_enum(TestOutcome)(v["outcome"]), _enum(TestSelection)(v["selection"])) == (True, True)


def _format_rule(d: Mapping) -> str | None:
    return None if d["journal_format"] == FORMAT else \
        f"journal format {d['journal_format']} is not format {FORMAT}: refused, never read under another format"


def _static_admission_rule(d: Mapping) -> str | None:
    if d["admitted"] is not all(c["passed"] for c in d["checks"]):
        return "admitted is true exactly when every check passed (§12)"
    return None


def _verified_payload_rule(d: Mapping) -> str | None:
    if ("verdict" in d) and not d["agreement"]:
        return "a verdict is set only when agreement is true (§16)"
    return None


def _adequacy_rule(d: Mapping) -> str | None:
    """§15.3's two-axis semantics, as the typed adequacy object states them."""
    unrunnable = d["execution"]["status"] == _UNRUNNABLE or d["regressions"]["status"] == _UNRUNNABLE
    outcome, owner = d["outcome"], d["owner"]
    if unrunnable:
        if outcome is not None or owner != Owner.ENVIRONMENT.value:
            return "an UNRUNNABLE mandatory execution produces no AdequacyOutcome and keeps its environment provenance (§15.3)"
    elif outcome is None:
        return "both mandatory executions EXECUTED: the AdequacyOutcome is defined (§15.3)"
    elif outcome == AdequacyOutcome.INADEQUATE.value:
        if owner != Owner.DEVELOPER.value:
            return "INADEQUATE is owned by DEVELOPER (§15.3)"
    elif owner is not None:
        return f"{outcome} is charged to nobody (§15.3)"
    if d["may_block"] is not (outcome == AdequacyOutcome.INADEQUATE.value):
        return "only INADEQUATE may block, under project policy (§15.3)"
    if d["developer_chargeable"] is not (owner == Owner.DEVELOPER.value):
        return "developer_chargeable is exactly a DEVELOPER-owned result (§15.3)"
    return None


def _failure_schema() -> Schema:
    base = ev.SCHEMAS[T.FAILURE_OBSERVED.value]  # owner and retryable stay the taxonomy's (event.carried, _failure_rule)
    return Schema({**base.required, "code": _enum(FailureCode)}, base.optional, base.cites, base.rule)


#: The format-3 schemas: formats 1 and 2 as they were, the five re-declared here, the four new.
SCHEMAS: Mapping[str, Schema] = MappingProxyType({**ev.SCHEMAS, **f2.SCHEMAS, **{t.value: s for t, s in (
    (T.RUN_BEGIN, Schema({"journal_format": _count, "run_id": _str}, rule=_format_rule)),
    (T.FAILURE_OBSERVED, _failure_schema()),
    (T.PROVIDER_REQUEST, Schema({"story_id": _str, "criteria": ev._distinct_strs, "budget_owner": _budget_owner})),
    (T.PLAN_STATIC_ADMITTED, Schema({"plan_id": _str, "engine_digest": _hex64, "admitted": _bool, "checks": _checks,
                                     "result_digest": _hex64}, rule=_static_admission_rule)),
    (T.PROOF_VERIFIED, Schema({"story_id": _str, "criterion_id": _str, "spec_id": _str, "semantic_hash": _hex64,
                               "candidate": _sha, "agreement": _bool}, {"verdict": _enum(BehaviorVerdict)},
                              rule=_verified_payload_rule)),
    (T.TESTS_ADEQUACY, Schema({"story_id": _str, "execution": _execution, "vacuity": _opt(_enum(Vacuity)),
                               "relevance": _opt(_enum(Relevance)), "regressions": _execution,
                               "outcome": _opt(_enum(AdequacyOutcome)), "owner": _opt(_enum(Owner)), "may_block": _bool,
                               "developer_chargeable": _bool}, {"chronology": _opt(_object)}, rule=_adequacy_rule)),
    (T.INVARIANT_VIOLATED, Schema({"invariant": _enum(InvariantId), "module": _str, "context": _object})),
)}})
WRITABLE = frozenset(SCHEMAS)
#: types whose citations their own rule checks (a result cites by outcome; a proof cites two records)
_SELF_CITED = frozenset({T.TOOL_RESULT.value, T.PROOF_VERIFIED.value})
_INSTRUMENT = ("probe_id", "probe_digest", "enforcement", "semantic_hash")


# --------------------------------------------------------------------------------------- rules over the journal

def _static_admitted(event: Event, prior: Sequence[Event]) -> str | None:
    d = event.data
    if any(e.type == T.PLAN_STATIC_ADMITTED.value and e.data["plan_id"] == d["plan_id"] for e in prior):
        return f"plan {d['plan_id']!r} is statically admitted once per run"
    return None


def _story_active(event: Event, prior: Sequence[Event]) -> str | None:
    mine = f2._attempt(event.data["story_id"], prior)
    if mine is None or any(e.type == T.STORY_END.value for e in mine):
        return f"{event.data['story_id']} has no open attempt"
    return None


def _verified(event: Event, prior: Sequence[Event]) -> str | None:
    """§16: the two cited probe/evaluated records are this story's and criterion's, answer this spec at this candidate,
    share their instrument identity, and agreement and verdict are exactly what the two results say."""
    why = _story_active(event, prior)  # a proof belongs to the attempt it was measured in
    if why:
        return why
    d = event.data
    if len(event.source_seqs) != 2:
        return "cites exactly two probe/evaluated records: the implementer's, then the verifier's (§16)"
    records = []
    for s in event.source_seqs:
        e = prior[s]
        if e.type != T.PROBE_EVALUATED.value or (e.data["story_id"], e.data["criterion_id"]) != (d["story_id"], d["criterion_id"]):
            return f"cites {s}: not a probe/evaluated of {d['story_id']} / {d['criterion_id']}"
        r = e.data["record"]
        if not isinstance(r, Mapping) or not all(k in r for k in ("spec_id", "revision", "result", *_INSTRUMENT)):
            return f"cites {s}: its record is not a sealed ProbeRecord"
        if (r["spec_id"], r["semantic_hash"], r["revision"]) != (d["spec_id"], d["semantic_hash"], d["candidate"]):
            return f"cites {s}: the record answers {r['spec_id']} at {str(r['revision'])[:12]}, not this spec at this candidate"
        records.append(r)
    a, b = records
    if any(a[k] != b[k] for k in _INSTRUMENT):
        return "the two records do not share probe_id, probe_digest, enforcement and semantic_hash: PROBE_MISMATCH is a " \
               "failure/observed, never a proof (§16)"
    agreement = a["result"] == b["result"]
    if d["agreement"] is not agreement:
        return f"agreement is {agreement} by the two records, not {d['agreement']}"
    verdict = a["result"].get("behavior_verdict") if agreement and isinstance(a["result"], Mapping) else None
    if ("verdict" in d) is not (verdict is not None) or ("verdict" in d and d["verdict"] != verdict):
        return f"the verdict is {verdict!r} by the two records" if verdict is not None else \
            "the two results carry no verdict: none is set"
    return None


def _story_active_and_mine(event: Event, prior: Sequence[Event]) -> str | None:
    return _story_active(event, prior)


_RULES: Mapping[str, Callable[[Event, Sequence[Event]], str | None]] = MappingProxyType({
    **f2._RULES, T.PLAN_STATIC_ADMITTED.value: _static_admitted, T.PROOF_VERIFIED.value: _verified,
    T.TESTS_ADEQUACY.value: _story_active_and_mine})


def verified_proof(event: Event, prior: Sequence[Event]) -> dict:
    """RFC §16's VerifiedProof, reconstructed from a validated proof/verified event and the journal before it: the
    fields are the event's own and the two results are the cited records' — nothing is stored twice."""
    if event.type != T.PROOF_VERIFIED.value:
        raise JournalError(f"{event.type} is not a proof/verified")
    a, b = (prior[s].data["record"]["result"] for s in event.source_seqs)
    return {"spec_id": event.data["spec_id"], "candidate_sha": event.data["candidate"], "implementer_result": a,
            "verifier_result": b, "agreement": event.data["agreement"], "verdict": event.data.get("verdict")}


def verified_payload(*, story_id: str, criterion_id: str, spec_id: str, semantic_hash: str, candidate: str,
                     implementer: Mapping, verifier: Mapping) -> dict:
    """The `proof/verified` payload for two sealed probe records (their plain form), computed the way `_verified`
    reads it back: agreement is whether the two results are equal, and the verdict is set only when they agree and
    carry one. Control never reads the verdict from here — it routes on the bound result (§10.1); this only carries
    what the records say into the journal (§16)."""
    a, b = implementer["result"], verifier["result"]
    agreement = a == b
    verdict = a.get("behavior_verdict") if agreement and isinstance(a, Mapping) else None
    payload = {"story_id": story_id, "criterion_id": criterion_id, "spec_id": spec_id, "semantic_hash": semantic_hash,
               "candidate": candidate, "agreement": agreement}
    if verdict is not None:
        payload["verdict"] = verdict
    return payload


def _cites(event: Event, cite: ev.Cite | None, prior: Sequence[Event]) -> None:
    if cite is None:
        if event.source_seqs:
            raise JournalError(f"{event.type} cites no event in format {FORMAT}")
        return
    cited = [prior[s] for s in event.source_seqs]
    if cite.many:
        count_ok, want = len(cited) >= 1, "at least one"
    else:
        count_ok, want = len(cited) == 1, "exactly one"
    if not count_ok:
        raise JournalError(f"{event.type} cites {want} {cite.type.value}")
    wrong = [e.seq for e in cited if (e.type, e.data.get(cite.key)) != (cite.type.value, event.data[cite.key])]
    if wrong:
        raise JournalError(f"{event.type} cites {wrong}: not a {cite.type.value} with the same {cite.key}")


def validate(event: Event, prior: Sequence[Event]) -> None:
    """A format-3 event against the journal before it. Raises JournalError; nothing grows on a refusal."""
    if event.seq != len(prior):
        raise JournalError(f"{event.type} at seq {event.seq}, but the journal holds {len(prior)} events: seq == index")
    schema = SCHEMAS.get(event.type)
    if schema is None:
        raise JournalError(f"{event.type} is not in the event vocabulary")
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
    if event.type not in _SELF_CITED:
        _cites(event, schema.cites, prior)
    rule = _RULES.get(event.type)
    why = rule(event, prior) if rule else None
    if why:
        raise JournalError(f"{event.type}: {why}")


# --------------------------------------------------------------------------------------- the reader

def declared_format(text: str) -> int | None:
    return f2.declared_format(text)


def reconstruct(text: str) -> Journal:
    """The journal `text` holds, under the format it declares — 1 and 2 by their own readers, 3 by this one; any other
    format is refused, never guessed at (FMT3-5)."""
    if not isinstance(text, str):
        raise JournalError("a journal is read as text")
    fmt = declared_format(text)
    if fmt is None or fmt == ev.FORMAT:
        return compat.reconstruct(text)
    if fmt == f2.FORMAT:
        return f2.reconstruct(text)
    if fmt != FORMAT:
        raise JournalError(f"journal format {fmt} is none of the formats this reader knows {list(KNOWN_FORMATS)}: refused")
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

class JournalWriter3:
    """The P3 writer's discipline for format 3: no update or delete verb; `seq == index` assigned here, admitted on
    open, re-checked at append and on decode; validation and the pre-check before a byte is written; every append
    fsync'd; a failed write or fsync truncates back and poisons the writer. It never extends a format-1 or format-2
    journal: those are read, never re-declared (FMT3-7)."""

    def __init__(self, path: str | os.PathLike, *, clock: Callable[[], float] = _time.time) -> None:
        self._path = pathlib.Path(path)
        self._clock = clock
        existing = self._path.read_bytes().decode("utf-8") if self._path.exists() else ""
        journal = reconstruct(existing) if existing else EMPTY
        if journal.torn_tail:
            raise JournalError(f"{self._path} ends in a torn append; repair it (WP-4.6) before extending it")
        if journal.skipped:
            raise JournalError(f"{self._path} holds event types this format-{FORMAT} writer does not know "
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
