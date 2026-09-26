"""Observation — structured events, cost, and latency per story.

Without observation there is no way to tell whether the agent is doing well
or silently drifting. But plain "logging" is not enough: what is needed is
**machine-readable evidence**, because two different places depend on it:

* the story gate asks "are tests green, lint clean, mockup matched";
* the `completion` guard asks "was there a test run **after** the last file
  edit" — that is how it blocks the agent from declaring done without re-running
  tests.

Therefore each event has a monotonically increasing ``seq`` and ``at``
(process-monotonic timestamp). Compare ordering by ``seq``, not wall clock:
the evidence file travels through git between machines.

One file per story, append-only and atomic: multiple processes (agent running
tools, guard running in a hook) writing to the same story is normal under
parallel execution.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..clients.stream import exit_status_of
from ..control.identity import CONTROL_FIELDS, CURRENT, NON_CANDIDATE_NOTES, SESSION_FIELDS, EvidenceIdentity, fresh

EVIDENCE_DIR = "evidence"

#: Event kinds. Closed set so readers don't have to guess.
TOOL_RUN = "tool_run"          # ran test/lint/sast/screenshot...
FILE_CHANGE = "file_change"    # agent wrote a file
AGENT_RUN = "agent_run"        # one model invocation
GUARD_BLOCK = "guard_block"    # guard blocked an operation
GUARD_SEEN = "guard_seen"      # hook reached this session (recorded once per story)
GUARD_CHECK = "guard_check"    # each guard run (pass or block) — telemetry v0.4.0
MOCKUP_MAP = "mockup_map"      # real screen compared against mockup
NOTE = "note"
HANDOFF = "handoff"            # handoff package: which role receives which slot, from which source
BEHAVIOR = "behavior"          # behavior status: verified | gap | reopened
SKILL_USE = "skill_use"        # agent invoked a skill in the session — observe, don't block


@dataclass
class Event:
    kind: str
    name: str = ""
    ok: bool = True
    seq: int = 0
    at: float = 0.0
    duration_ms: int = 0
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    #: the identity tuple this record was written under (control/identity.py); {} = schema 1
    identity: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Evidence:
    """All events for a story, loaded from disk."""

    story_id: str
    events: list[Event] = field(default_factory=list)

    def of(self, kind: str, name: str = "") -> list[Event]:
        return [
            e for e in self.events
            if e.kind == kind and (not name or e.name == name)
        ]

    @property
    def candidate(self) -> str:
        """Candidate of record: the SHA of the most recent **grading or freeze** (ADR-004 R1). Notes that
        merely mention a candidate — a recovery, an invalidation — are not gradings (SS-C2)."""
        for e in reversed(self.events):
            if e.kind == NOTE and e.name in NON_CANDIDATE_NOTES:
                continue
            sha = str(e.detail.get("candidate") or "")
            if sha:
                return sha
        return ""

    def for_identity(self, current: EvidenceIdentity, fields: tuple[str, ...] = CONTROL_FIELDS) -> "Evidence":
        """Evidence usable for deciding on `current`: records that are fresh for it, plus unbound
        observations (no candidate, no session — guard self-records of legacy hooks, manual tool runs);
        a record bound to another identity, or lacking a field the decider binds on, is dropped."""
        keep = []
        for e in self.events:
            ident = EvidenceIdentity.of(e, self.story_id)
            if not ident.bound or fresh(e, current, fields, story_id=self.story_id).ok:
                keep.append(e)
            elif ident.session_id and not ident.candidate_sha and fresh(e, current, SESSION_FIELDS, story_id=self.story_id).ok:
                keep.append(e)      # a proof of THIS session (guard heartbeat, file change) — it names no candidate yet
        return Evidence(story_id=self.story_id, events=keep)

    def last_fresh(self, kind: str, name: str, current: EvidenceIdentity,
                   fields: tuple[str, ...] = CONTROL_FIELDS) -> Event | None:
        """The most recent record of a check that is fresh for `current` — the only "latest" a decision may read."""
        for e in reversed(self.of(kind, name)):
            if fresh(e, current, fields, story_id=self.story_id).ok:
                return e
        return None

    def for_candidate(self, sha: str) -> "Evidence":
        """Evidence usable for grading build ``sha``.

        Events recorded against a **different** build are dropped: they describe
        code that no longer exists. Events with **no** candidate stamp are kept —
        they are not candidate-bound evidence (guard self-records, manual tool
        runs, legacy logs), and dropping them would blind the gate rather than
        tighten it.
        """
        return Evidence(
            story_id=self.story_id,
            events=[e for e in self.events
                    if str(e.detail.get("candidate") or "") in ("", sha)],
        )

    def last(self, kind: str, name: str = "") -> Event | None:
        found = self.of(kind, name)
        return found[-1] if found else None

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self.events)

    @property
    def total_duration_ms(self) -> int:
        return sum(e.duration_ms for e in self.events)

    @property
    def guard_reached(self) -> bool:
        """Whether the hook reached this story's session — any guard trace
        suffices. Measured on `par`: worktree without `.claude/` and no
        `--settings` -> 0 traces even if the story ran fully; with `--settings` -> present."""
        return bool(self.of(GUARD_SEEN) or self.of(GUARD_BLOCK) or self.of(FILE_CHANGE))

    @property
    def guard_blocks(self) -> list[Event]:
        """Guard blocks, recorded by **the guard itself** — independent of
        whether the client emits an event stream."""
        return self.of(GUARD_BLOCK)

    def tests_green(self) -> bool:
        """Whether the most recent test run passed."""
        last = self.last(TOOL_RUN, "test")
        return bool(last and last.ok)

    def after_last(self, kind: str, name: str) -> list[Event]:
        """Events recorded after the last `kind`/`name` — by **position** in
        this time-ordered list, not by `seq`.

        `seq` is assigned per write and restarts whenever a file was written
        by a build that could not read the tail (bug 42). Comparing the
        numbers then makes an old event look newer: todo/STORY-02-01 carried
        six `file_change` events with seq 161-166 recorded 33 minutes
        **before** the test run at seq 144, and the story was refused three
        attempts running for "5 files changed since the most recent test run"
        while nothing had changed since. Position after sorting is what
        "after" means.
        """
        moc = -1
        for i, e in enumerate(self.events):
            if e.kind == kind and e.name == name:
                moc = i
        return self.events[moc + 1:]

    def after_event(self, event: Event) -> list[Event]:
        """Events recorded after the given event — by **position** in this
        time-ordered list. Symmetric to ``after_last`` but anchored on a
        specific event rather than a kind/name pair. Use this when ``seq``
        cannot be trusted for ordering (evidence written by a build that
        reset the counter). Bug 47: gate/replay used to compare by ``seq``
        directly; the time-sorted position is what "after" really means.
        """
        try:
            idx = self.events.index(event)
        except ValueError:
            return []
        return self.events[idx + 1:]

    def stale_since_last_test(self) -> list[str]:
        """Files modified **after** the most recent test run.

        This is the question the `completion` guard needs: a green test from ten
        minutes ago says nothing about code just written.
        """
        touched: list[str] = []
        for e in self.after_last(TOOL_RUN, "test"):
            if e.kind != FILE_CHANGE:
                continue
            path = str(e.detail.get("path") or e.name)
            if path and path not in touched:
                touched.append(path)
        return touched

    def summary(self) -> str:
        by_kind: dict[str, int] = {}
        for e in self.events:
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        parts = [f"{k}={v}" for k, v in sorted(by_kind.items())]
        if self.total_cost_usd:
            parts.append(f"${self.total_cost_usd:.2f}")
        return f"{self.story_id}: " + " · ".join(parts) if parts else f"{self.story_id}: (empty)"


class EvidenceStore:
    """Read/write ``evidence/{story}.jsonl``.

    ``candidate`` is the SHA of the build being verified: every event recorded
    through this store stamps that build into ``detail`` (ADR-004 R1). Stamped
    here, in one place, instead of requiring every caller to remember — any
    caller that forgets silently produces evidence bound to no build.
    """

    def __init__(self, artifact_root: Path | str, *, candidate: str = "",
                 identity: EvidenceIdentity | None = None):
        if identity is None:
            now = CURRENT.get()
            # a store built with a bare candidate inside a verified attempt stamps that attempt's identity —
            # for the same candidate; a different candidate is a different state and keeps schema 1
            if now is not None and (not candidate or candidate == now.candidate_sha):
                identity = now
        if identity is not None and not candidate:
            candidate = identity.candidate_sha
        self.identity = identity
        self.root = Path(artifact_root) / EVIDENCE_DIR
        self.candidate = candidate

    def path(self, story_id: str) -> Path:
        return self.root / f"{story_id}.jsonl"

    def record(self, story_id: str, event: Event) -> Event:
        """Append one event. `seq` is determined by the file, not by the
        caller — two processes writing concurrently still produce consistent ordering."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(story_id)

        event.at = event.at or time.time()
        if self.candidate and not event.detail.get("candidate"):
            event.detail = {**event.detail, "candidate": self.candidate}
        if self.identity is not None and not event.identity:
            event.identity = self.identity.as_dict()
        # Open in append mode and write one line: a short line under PIPE_BUF
        # is atomic on POSIX, so no separate lock is needed.
        with path.open("a", encoding="utf-8") as fh:
            event.seq = self._next_seq(path)
            fh.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return event

    def _next_seq(self, path: Path) -> int:
        """Next sequence number, read from the end of the file.

        Reads the tail rather than the whole file, but **grows the window
        until a complete line is in it**. A single event can exceed any fixed
        window — a review verdict with findings, a tool tail — and then the
        window holds one truncated line, nothing parses, and this used to
        answer `1`. Numbering restarted mid-file, `read()` sorts by `seq`, so
        events from an old run sorted *after* the current ones and every
        "latest result" check read a stale event: the gate reported evidence
        recorded at a candidate three builds back and refused the story
        (todo/STORY-01-02 2026-09-09 — 3 restarts in one file, each right
        after a line over 4 KB).
        """
        if not path.is_file():
            return 1
        try:
            size = path.stat().st_size
            if size == 0:
                return 1
            chunk = 4096
            while True:
                with path.open("rb") as fh:
                    fh.seek(-min(chunk, size), 2)
                    tail = fh.read().decode("utf-8", errors="replace")
                for line in reversed(tail.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        return int(json.loads(line).get("seq") or 0) + 1
                    except (json.JSONDecodeError, TypeError, ValueError):
                        break      # truncated by the window — widen and retry
                if chunk >= size:
                    return 1       # whole file read, nothing parseable
                chunk *= 8
        except OSError:
            return 1

    def read(self, story_id: str) -> Evidence:
        ev = Evidence(story_id=story_id)
        path = self.path(story_id)
        if not path.is_file():
            return ev
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue  # one corrupt line must not lose the entire evidence file
            if not isinstance(data, dict):
                continue
            ev.events.append(
                Event(
                    kind=str(data.get("kind", "")),
                    name=str(data.get("name", "")),
                    ok=bool(data.get("ok", True)),
                    seq=int(data.get("seq") or 0),
                    at=float(data.get("at") or 0.0),
                    duration_ms=int(data.get("duration_ms") or 0),
                    cost_usd=float(data.get("cost_usd") or 0.0),
                    tokens=data.get("tokens") or {},
                    detail=data.get("detail") or {},
                    identity=data.get("identity") if isinstance(data.get("identity"), dict) else {},
                )
            )
        # By time **then** sequence. Files written before the fix above carry
        # restarted numbering, and sorting those by `seq` alone puts an old
        # run's events after this run's — heals them on read instead of
        # leaving every gate reading the wrong build.
        ev.events.sort(key=lambda e: (e.at, e.seq))
        return ev

    def stories(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))

    # ------------------------------------------------------------ utilities

    def tool_run(
        self,
        story_id: str,
        name: str,
        *,
        ok: bool,
        duration_ms: int = 0,
        detail: dict | None = None,
    ) -> Event:
        return self.record(
            story_id,
            Event(kind=TOOL_RUN, name=name, ok=ok, duration_ms=duration_ms,
                  detail=detail or {}),
        )

    def handoff(self, story_id: str, *, frm: str, to: str, attempt: int,
                slots: dict[str, tuple[str, int]], memory: dict | None = None) -> Event:
        """Handoff package for a role: which slot, from which source, how many chars.
        Answers "what did the reviewer see" from disk — and lets the machine check
        invariants: a reviewer/security package must not contain the developer's words."""
        return self.record(
            story_id,
            Event(kind=HANDOFF, name=f"{frm}->{to}",
                  detail={"from": frm, "to": to, "attempt": attempt,
                          "slots": {k: {"source": s, "chars": n} for k, (s, n) in slots.items()},
                          **({"memory": memory} if memory is not None else {})}),
        )

    def behavior(self, story_id: str, *, id: str, status: str, candidate: str = "",
                 source: dict | None = None, prev: str = "") -> Event:
        """Status of a behavior, concluded by a phase (review identified a gap,
        preservation gate detected a regression).

        The behavior ledger (`control/ledger.py`) reads both this event and
        inferences from prior evidence — so recording here **adds a source**,
        not the only source, and omitting it loses nothing already measured.
        """
        return self.record(
            story_id,
            Event(kind=BEHAVIOR, name=id, ok=(status == "verified"),
                  detail={"id": id, "status": status, "candidate": candidate,
                          "source": source or {}, "prev": prev}),
        )

    def file_change(self, story_id: str, path: str, *, detail: dict | None = None) -> Event:
        return self.record(
            story_id,
            Event(kind=FILE_CHANGE, name=Path(path).name,
                  detail={"path": path, **(detail or {})}),
        )

    def agent_run(self, story_id: str, result, *, name: str = "", prompt_chars: int = 0,
                  skills: dict | None = None, role: str = "", model: str = "",
                  client: str = "", tool_calls: int = -1,
                  response_snippet: str = "") -> Event:
        """Record one model invocation from `RunResult` — cost and latency
        taken from the client stream, not estimated."""
        return self.record(
            story_id,
            Event(
                kind=AGENT_RUN,
                name=name or "story",
                ok=result.ok,
                duration_ms=result.duration_ms,
                cost_usd=result.cost_usd,
                tokens={
                    "input": result.input_tokens,
                    "output": result.output_tokens,
                    "cache_creation": result.cache_creation_tokens,
                    "cache_read": result.cache_read_tokens,
                },
                detail={
                    "session_id": result.session_id,
                    "turns": result.num_turns,
                    # Loaded context size — measured, replacing the knob
                    # `story.max_context_tokens` which was never read by any code.
                    "prompt_chars": prompt_chars,
                    "guard_blocked": result.guard_blocked,
                    # The flag alone doesn't say which guard blocked or why.
                    # Without this field, next time requires digging through session logs.
                    "guard_messages": list(result.guard_messages)[:5],
                    "permission_limited": result.permission_limited,
                    "error": result.error,
                    # Normalized exit status (ADR-005 V11 B) — `aisef status` counts
                    # by this key, not by re-parsing the `error` string.
                    "exit_status": exit_status_of(result),
                    # Skills invited / opened — measured, not guessed (ADR-003 #1).
                    "skills": skills or {},
                    "role": role,
                    # The model the **stream** reported, with the requested one
                    # as fallback: `spec.model` is empty whenever no route model
                    # is configured, which is how all 145 sessions of the O1
                    # qualification corpus came to carry `model: ""` — a rate
                    # that cannot be split per model (ADR-009 O1).
                    "model": (getattr(result, "model", "") or model),
                    # Which client ran it. One project accumulates evidence from
                    # several clients across runs (todo-oc holds both a
                    # `.claude/` and a `.opencode/`), so this belongs on the
                    # event, not on the project.
                    "client": client,
                    "tool_calls": tool_calls,
                    "response_snippet": response_snippet[:300] if response_snippet else "",
                },
            ),
        )
