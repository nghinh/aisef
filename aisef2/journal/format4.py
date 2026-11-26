"""Journal format 4 — THE one new writer format of v2.3 (contract C-1, FORMAT-4-DESIGN-DRAFT.md §4–§5,
frozen blob 41506829d2; owner freeze 2026-11-26, docs/v2.3/amendments/C-1-FORMAT-4-FREEZE.md).

Formats 1–3 are sealed and unchanged; their journals are read by DELEGATION to `format3.reconstruct` (CR-1) and
never extended by this writer. Format 4 = format 3's schemas and rules, with the C-1 §4 deltas and the transition
table (`journal.transitions`) as the ONE story-lifecycle rule:

* **`run/begin`** (§4.1) requires `kernel_digest` and `signer` (sha256 fingerprint of the run's ephemeral public
  key — CR-7: the signed-run discriminator lives inside the hash chain); optional `bundle_digest` (Q4 default).
* **`provider/request`** (§4.2, E2) requires `reservation {turns, max_usd}`; null means "explicitly unbounded",
  never "absent". **`provider/result`** (§4.3, E4) requires `segment` (null, or `{session, sha256, offset, bytes}`)
  under rule R-SEGMENT: COMPLETED ⇒ non-null, synthetic closer ⇒ null, FAILED ⇒ either and `detail` says which.
* **`provider/attestation`** (§4.4, C7) and **`story/completed`** (§4.5, G6) are the two NEW kinds. Their
  `EventType` members land with the measured CORE-2 batch (C-1 §7 Q1/M12): until then this module names every kind
  by its LITERAL string — `VOCABULARY4` is the 29 v2.2.0 names plus the two, never computed from the live enum
  (§4.10, the M4 sealed-reader defect class).
* **V21-10 hardening** (§4.8): R-SEALED (every cited probe record's `record_digest` re-derives — Q3 measured,
  primary form), R-GATE (no passing decision over a failed check), R-COMMIT (no commit in an attempt without a
  `proof/verified` — Q2 measured, STRICT form). **R-CLOSED** (§4.6, C5/G9): `run/end` is refused while any
  `provider/request` is unanswered. `story/resource-acquired` gains optional `base` (sha) for WORKTREE.
* **`tests/adequacy`** (§4.7, #93) gains OPTIONAL `audit {reason, vacuity, relevance}` — production always emits it
  (the `quality.payload()` edit lands with the measured batch); synthetic test journals stay writable without it.
* **`failure/observed`** admits exactly `FORMAT_4_CODES` — the 22 v2.2.0 literals (§4.9, V21-57 KEEP).
* **`reconstruct`** reads formats 1–3 by `format3.reconstruct` UNCHANGED and format 4 by this module; any other
  number is refused, never guessed (FMT3-5). **`JournalWriter4`** is the P3 discipline verbatim (M6/FMT3-7: the
  sealed triplicates are not refactored — the lazy diff is the copy, per the frozen design itself).

Declared limitations (C-1 §11): L1 the chain is unkeyed until A2 integration — `signer` is a declaration the
verifier binds later; L2 `reservation` is owner-typed DATA, no monetary cap is enforced here; L3 `segment` seals
the LOCAL stream bytes, not what the provider served; L4 formats ≤2 keep their own sealed rules entirely; L7 the
R-rules are defense in depth against hand-built journals — the kernel already cannot write the negatives (M3).
"""

from __future__ import annotations

import math
import os
import pathlib
import time as _time
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from aisef2.arch.enums import EventType as T
from aisef2.journal import event as ev
from aisef2.journal import format2 as f2
from aisef2.journal import format3 as f3
from aisef2.journal.compat import EMPTY, Journal, UnknownRequiredEvent
from aisef2.journal.event import GENESIS, Event, JournalError, Schema, carried, decode, encode, link
from aisef2.journal.transitions import STORY, WITHIN, symbol_of
from aisef2.product.contract import digest

FORMAT = 4
KNOWN_FORMATS = (1, 2, 3, 4)

#: The two format-4 kinds (C-1 §4.4/§4.5). Their EventType members land with the measured CORE-2 batch; this layer
#: treats kinds as strings until then (and after: a member's .value is the same string).
PROVIDER_ATTESTATION = "provider/attestation"
STORY_COMPLETED = "story/completed"

#: §4.10 — the 29 v2.2.0 event names as LITERALS (never the live enum: enum growth must not re-open this reader)
#: plus the two new kinds: 31 names.
VOCABULARY4: frozenset[str] = frozenset({
    "run/begin", "run/spec-resolved", "run/dispose-begin", "run/interrupted", "run/end",
    "plan/static-admitted", "plan/frozen",
    "story/begin", "story/admitted", "story/plan-drift", "story/resource-acquired", "story/resource-released",
    "story/commit", "story/rollback", "story/retry", "story/dispose", "story/end",
    "capability/resolved", "probe/evaluated", "proof/verified", "provider/request", "provider/result",
    "tool/invoked", "tool/result", "tests/adequacy", "gate/check", "gate/decision",
    "failure/observed", "invariant/violated",
    PROVIDER_ATTESTATION, STORY_COMPLETED,
})

#: §4.9 — the 22 FailureCode literals at v2.2.0 (13 FORMAT_2_CODES + 9 V2-005), V21-57 default KEEP: no 23rd code.
FORMAT_4_CODES: frozenset[str] = frozenset({
    "PROBE_UNRUNNABLE", "PROBE_INVALID_SPEC", "CONTRACT_UNSATISFIED", "SUBJECT_ABSENT_AT_CANDIDATE",
    "PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "POST_MERGE_REGRESSION", "POST_MERGE_SUBJECT_LOST",
    "NON_CONTROLLER_SIGNAL", "MISSING_CREDENTIAL", "INVALID_CREDENTIAL", "PROVIDER_UNAVAILABLE", "UNKNOWN",
    "VERIFIER_DISAGREEMENT", "PROBE_MISMATCH", "MERGE_CONFLICT", "TESTS_UNRUNNABLE", "TESTS_INADEQUATE",
    "REVIEW_FINDING", "SECURITY_FINDING", "CAPABILITY_UNRUNNABLE", "RESOURCE_ACQUISITION_FAILED",
})

_str, _text, _bool, _count, _sha, _hex64 = ev._str, ev._text, ev._bool, ev._count, ev._sha, ev._hex64


# --------------------------------------------------------------------------------------- §4 field kinds

def _usd(v: Any) -> bool:
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0)


def _reservation(v: Any) -> bool:
    """§4.2: exactly {turns, max_usd}; null means "explicitly unbounded", never "absent"."""
    return isinstance(v, Mapping) and set(v) == {"turns", "max_usd"} \
        and (v["turns"] is None or _count(v["turns"])) and _usd(v["max_usd"])


def _segment(v: Any) -> bool:
    """§4.3: null, or exactly {session, sha256, offset, bytes} over the exact byte range."""
    if v is None:
        return True
    return isinstance(v, Mapping) and set(v) == {"session", "sha256", "offset", "bytes"} \
        and _str(v["session"]) and _hex64(v["sha256"]) and _count(v["offset"]) and _count(v["bytes"])


def _vacuity_audit(v: Any) -> bool:
    return v is None or (isinstance(v, Mapping) and set(v) == {"neutralised", "attributed", "reason"}
                         and _bool(v["neutralised"]) and _text(v["attributed"]) and _text(v["reason"]))


def _relevance_audit(v: Any) -> bool:
    return v is None or (isinstance(v, Mapping) and set(v) == {"intersections", "unmeasured"}
                         and _count(v["intersections"]) and ev._strs(v["unmeasured"]))


def _audit(v: Any) -> bool:
    """§4.7 (#93): the blocking quality verdict's audit inputs — exactly {reason, vacuity, relevance}."""
    return isinstance(v, Mapping) and set(v) == {"reason", "vacuity", "relevance"} \
        and _text(v["reason"]) and _vacuity_audit(v["vacuity"]) and _relevance_audit(v["relevance"])


# --------------------------------------------------------------------------------------- §4 payload rules

def _format_rule(d: Mapping) -> str | None:
    return None if d["journal_format"] == FORMAT else \
        f"journal format {d['journal_format']} is not format {FORMAT}: refused, never read under another format"


def _result_rule(d: Mapping) -> str | None:
    """f2's provider/result rule plus R-SEGMENT (§4.3): the segment's nullity follows the outcome."""
    why = f2._provider_result_rule(d)
    if why:
        return why
    if d["outcome"] == f2.OperationOutcome.COMPLETED.value and d["segment"] is None:
        return "R-SEGMENT: a COMPLETED provider/result seals its stream segment into the chain; segment is non-null"
    if d["synthetic"] and d["segment"] is not None:
        return "R-SEGMENT: a synthetic closer is DEFINED as accounting no bytes (repair charges the reservation); " \
               "segment is null"
    return None


def _acquired_rule(d: Mapping) -> str | None:
    if "base" in d and d["kind"] != f2.ResourceKind.WORKTREE.value:
        return f"base is the revision a WORKTREE was created at (§4.6); a {d['kind']} acquisition carries none"
    return None


def _failure_schema() -> Schema:
    base = ev.SCHEMAS[T.FAILURE_OBSERVED.value]  # owner and retryable stay the taxonomy's
    return Schema({**base.required, "code": ev._codes(FORMAT_4_CODES)}, base.optional, base.cites, base.rule)


def _adequacy_schema() -> Schema:
    base = f3.SCHEMAS[T.TESTS_ADEQUACY.value]
    return Schema(base.required, {**base.optional, "audit": _audit}, base.cites, base.rule)


#: Format-4 schemas: format 3's (which carry formats 1 and 2 where unchanged), the §4 deltas re-declared, the two
#: new kinds added. New required fields appear ONLY here; formats 1–3 never admit them (CR-3).
SCHEMAS: Mapping[str, Schema] = MappingProxyType({**f3.SCHEMAS, **{
    T.RUN_BEGIN.value: Schema({"journal_format": _count, "run_id": _str, "kernel_digest": _hex64, "signer": _hex64},
                              {"bundle_digest": _hex64}, rule=_format_rule),
    T.FAILURE_OBSERVED.value: _failure_schema(),
    T.PROVIDER_REQUEST.value: Schema({"story_id": _str, "criteria": ev._distinct_strs,
                                      "budget_owner": f3._budget_owner, "reservation": _reservation}),
    T.PROVIDER_RESULT.value: Schema({"story_id": _str, "outcome": ev._enum(f2.OperationOutcome), "synthetic": _bool,
                                     "detail": _text, "segment": _segment},
                                    cites=ev.Cite(T.PROVIDER_REQUEST, False, "story_id"), rule=_result_rule),
    T.TESTS_ADEQUACY.value: _adequacy_schema(),
    T.STORY_RESOURCE_ACQUIRED.value: Schema({"story_id": _str, "resource": _str,
                                             "kind": ev._enum(f2.ResourceKind)}, {"base": _sha},
                                            rule=_acquired_rule),
    PROVIDER_ATTESTATION: Schema({"session": _str, "expected": _str, "observed": _text, "passed": _bool,
                                  "detail": _text}, {"story_id": _str}),
    STORY_COMPLETED: Schema({"story_id": _str, "revision": _sha, "fingerprint": _hex64},
                            cites=ev.Cite(T.STORY_COMMIT, False, "story_id")),
}})
WRITABLE = frozenset(SCHEMAS)


# --------------------------------------------------------------------------------------- the lifecycle table rule

#: The kinds the §3 table governs: the STORY movers and the WITHIN kinds. Resource/tool kinds keep format 2's rules.
_MOVER_KINDS = frozenset({"story/begin", "story/admitted", "story/commit", "story/rollback", "story/retry",
                          "story/dispose", "story/end"})
_LIFECYCLE = _MOVER_KINDS | frozenset(WITHIN)


def _story_state_of(story_id: str, prior: Sequence[Event]) -> str:
    """The table state of `story_id` after `prior` (already-validated events): STORY moves only."""
    state = "ABSENT"
    for e in prior:
        if e.data.get("story_id") != story_id:
            continue
        to = STORY.get((state, symbol_of(e.type, e.data)))
        if to is not None:
            state = to
    return state


def _lifecycle(event: Event, prior: Sequence[Event]) -> str | None:
    """The ONE story-lifecycle rule (C-1 §5): legality IS a table lookup — no ad-hoc `_story_active`."""
    story_id = event.data["story_id"]
    state = _story_state_of(story_id, prior)
    symbol = symbol_of(event.type, event.data)
    if (state, symbol) in STORY:
        return None
    within = WITHIN.get(symbol)
    if within is not None and state in within:
        return None
    return (f"transitions: {event.type} at seq {event.seq} for {story_id} in state {state}: "
            f"no STORY row ({state}, {symbol}) and {state} is not WITHIN[{symbol}]")


# --------------------------------------------------------------------------------------- §4.8/§4.6 rules

def _verified4(event: Event, prior: Sequence[Event]) -> str | None:
    """format 3's `_verified` with the table owning activity, plus R-SEALED (§4.8, Q3 primary form): each cited
    record's seal re-derives from the plain mapping the journal stores — `digest(record minus record_digest)`."""
    d = event.data
    if len(event.source_seqs) != 2:
        return "cites exactly two probe/evaluated records: the implementer's, then the verifier's (§16)"
    records = []
    for s in event.source_seqs:
        e = prior[s]
        if e.type != T.PROBE_EVALUATED.value \
                or (e.data["story_id"], e.data["criterion_id"]) != (d["story_id"], d["criterion_id"]):
            return f"cites {s}: not a probe/evaluated of {d['story_id']} / {d['criterion_id']}"
        r = e.data["record"]
        if not isinstance(r, Mapping) \
                or not all(k in r for k in ("spec_id", "revision", "result", "record_digest", *f3._INSTRUMENT)):
            return f"cites {s}: its record is not a sealed ProbeRecord"
        sealed = digest({k: v for k, v in r.items() if k != "record_digest"})
        if r["record_digest"] != sealed:
            return (f"R-SEALED: {event.type} at seq {event.seq} cites {s}: record_digest "
                    f"{str(r['record_digest'])[:12]} does not re-derive ({sealed[:12]}); an edited record is refused")
        if (r["spec_id"], r["semantic_hash"], r["revision"]) != (d["spec_id"], d["semantic_hash"], d["candidate"]):
            return f"cites {s}: the record answers {r['spec_id']} at {str(r['revision'])[:12]}, not this spec at " \
                   "this candidate"
        records.append(r)
    a, b = records
    if any(a[k] != b[k] for k in f3._INSTRUMENT):
        return "the two records do not share probe_id, probe_digest, enforcement and semantic_hash: PROBE_MISMATCH " \
               "is a failure/observed, never a proof (§16)"
    agreement = a["result"] == b["result"]
    if d["agreement"] is not agreement:
        return f"agreement is {agreement} by the two records, not {d['agreement']}"
    verdict = a["result"].get("behavior_verdict") if agreement and isinstance(a["result"], Mapping) else None
    if ("verdict" in d) is not (verdict is not None) or ("verdict" in d and d["verdict"] != verdict):
        return f"the verdict is {verdict!r} by the two records" if verdict is not None else \
            "the two results carry no verdict: none is set"
    return None


def _gate4(event: Event, prior: Sequence[Event]) -> str | None:
    """R-GATE (§4.8): a passing decision over a failed check is refused (the cites check has already bound every
    cited event to a gate/check of the same gate)."""
    if event.data["passed"] is not True:
        return None
    failed = [s for s in event.source_seqs if prior[s].data["passed"] is False]
    if failed:
        return f"R-GATE: {event.type} at seq {event.seq} with passed true cites failed gate/check {failed}"
    return None


def _commit4(event: Event, prior: Sequence[Event]) -> str | None:
    """R-COMMIT (§4.8, Q2 STRICT form): no commit in an attempt holding no proof/verified."""
    story_id = event.data["story_id"]
    mine = f2._attempt(story_id, prior) or []
    if not any(e.type == T.PROOF_VERIFIED.value for e in mine):
        return f"R-COMMIT: {event.type} at seq {event.seq}: the attempt of {story_id} holds no proof/verified"
    return None


def _closed4(event: Event, prior: Sequence[Event]) -> str | None:
    """R-CLOSED (§4.6, G9's closing-identity core): every provider/request has exactly one accounted outcome
    before the run may close. The interrupt path writes closers first (M7), so it still ends cleanly."""
    answered = {e.source_seqs[0] for e in prior if e.type == T.PROVIDER_RESULT.value}
    unanswered = [e for e in prior if e.type == T.PROVIDER_REQUEST.value and e.seq not in answered]
    if unanswered:
        first = unanswered[0]
        return (f"R-CLOSED: {event.type} at seq {event.seq}: the provider/request at seq {first.seq} "
                f"({first.data['story_id']}) has no provider/result; every request is accounted before the run "
                "closes")
    return None


def _attestation4(event: Event, prior: Sequence[Event]) -> str | None:
    """§4.4: an attestation lands at any point after run/begin (seq 0, structurally) and before run/end."""
    if any(e.type == T.RUN_END.value for e in prior):
        return f"{event.type} at seq {event.seq}: an attestation probe lands before run/end (§4.4)"
    return None


def _completed4(event: Event, prior: Sequence[Event]) -> str | None:
    """§4.5: at most one marker per story per run (the table holds it WITHIN ENDED_COMMIT; the cites check binds
    it to exactly one story/commit of the same story_id)."""
    story_id = event.data["story_id"]
    if any(e.type == STORY_COMPLETED and e.data["story_id"] == story_id for e in prior):
        return f"{event.type} at seq {event.seq}: {story_id} is marked completed at most once per story per run"
    return None


def _rules() -> Mapping[str, Callable[[Event, Sequence[Event]], str | None]]:
    rules = dict(f3._RULES)  # f2/f3 rules for non-lifecycle kinds (resources, tools, capabilities, plan, results)
    del rules[T.TESTS_ADEQUACY.value]       # activity is the table's, not an ad-hoc _story_active
    rules[T.PROOF_VERIFIED.value] = _verified4
    rules[T.GATE_DECISION.value] = _gate4
    rules[T.STORY_COMMIT.value] = _commit4
    rules[T.RUN_END.value] = _closed4
    rules[PROVIDER_ATTESTATION] = _attestation4
    rules[STORY_COMPLETED] = _completed4
    return MappingProxyType(rules)


_RULES = _rules()


def validate(event: Event, prior: Sequence[Event]) -> None:
    """A format-4 event against the journal before it. Raises JournalError; nothing grows on a refusal."""
    if event.seq != len(prior):
        raise JournalError(f"{event.type} at seq {event.seq}, but the journal holds {len(prior)} events: seq == index")
    schema = SCHEMAS.get(event.type)
    if schema is None or event.type not in VOCABULARY4:
        raise JournalError(f"{event.type} is not in the format-{FORMAT} event vocabulary")
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
    if event.type in _LIFECYCLE:  # the table speaks before citations: T8's refusal names the state, not the cite
        why = _lifecycle(event, prior)
        if why:
            raise JournalError(f"{event.type}: {why}")
    if event.type not in f3._SELF_CITED:
        f3._cites(event, schema.cites, prior)
    rule = _RULES.get(event.type)
    why = rule(event, prior) if rule else None
    if why:
        raise JournalError(f"{event.type}: {why}")


# --------------------------------------------------------------------------------------- the reader

def declared_format(text: str) -> int | None:
    return f2.declared_format(text)


def reconstruct(text: str) -> Journal:
    """The journal `text` holds: formats 1–3 by DELEGATION to `format3.reconstruct`, unchanged (CR-1); format 4 by
    this module; any other format refused by number, never guessed at (FMT3-5)."""
    if not isinstance(text, str):
        raise JournalError("a journal is read as text")
    fmt = declared_format(text)
    if fmt is None or fmt in (ev.FORMAT, f2.FORMAT, f3.FORMAT):
        return f3.reconstruct(text)
    if fmt != FORMAT:
        raise JournalError(f"journal format {fmt} is none of the formats this reader knows {list(KNOWN_FORMATS)}: "
                           "refused")
    lines = text.split("\n")
    torn = lines.pop() != ""
    prior: list[Event] = []
    known, chain, skipped = [], [], []
    prev = GENESIS
    for n, line in enumerate(lines):
        event, prev = decode(line, n, prev)
        if event.type in VOCABULARY4:
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

class JournalWriter4:
    """The P3 writer's discipline for format 4: no update or delete verb; `seq == index` assigned here, admitted on
    open, re-checked at append and on decode; validation and the pre-check before a byte is written; every append
    fsync'd; a failed write or fsync truncates back and poisons the writer. It never extends a journal of another
    format: those are read, never re-declared (FMT3-7). Until the measured batch lands the two new EventType
    members, `append` also takes a format-4 kind by its literal string (VOCABULARY4)."""

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

    def append(self, event_type: T | str, data: Mapping, *, source_seqs: tuple[int, ...] = (),
               check: Callable[[Event], None] | None = None, time: float | None = None) -> Event:
        """Validate, pre-check, write and fsync one event; return it. Raises JournalError, the log unchanged. `time`
        is given only by repair, whose closers reuse the last real event's time (§20.2)."""
        if self._broken is not None:
            raise JournalError(f"the writer failed ({self._broken}) and accepts nothing more")
        if self._fd is None:
            raise JournalError("the writer is closed")
        if isinstance(event_type, T):
            kind = event_type.value
        elif isinstance(event_type, str) and event_type in VOCABULARY4:
            kind = event_type
        else:
            raise JournalError("an event has a typed EventType (or, until the measured batch lands the two new "
                               "members, a format-4 kind named by its VOCABULARY4 literal)")
        event = Event(self._assign(), kind, carried(kind, data),
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

    def emit(self, event_type: T | str, data: Mapping) -> None:
        self.append(event_type, data)

    def close(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)
