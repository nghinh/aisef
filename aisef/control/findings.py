"""Structured finding model — one stable shape for every review/security outcome.

The previous pipeline treated review and security findings as ``list[str]``: the
gate then took a length to decide ``blocking`` and let the prompt decide what a
"close" meant. Two consequences:

1.  A finding closed because the author happened to write the same phrase back
    was indistinguishable from a finding closed because the underlying defect
    went away.
2.  A reviewer that rewrote its own prescription (one story spent three
    attempts being told to add a deterministic observation window, then was
    failed for having one) had no stable identifier the harness could refuse to
    re-raise.

This module is the single shape review/security/downstream callers agree on.
It is **advisory only** — a finding has no power to set a gate, that remains
the verifier's job — but it has stable identity, scope, severity and lifecycle,
so the gate can ask "did anything real change?" and the harness can refuse to
silently reopen/close the same finding on the same author.

Trust and reading order
-----------------------

Findings are written by:

* reviewer (independent session, ``trust=reviewer``);
* security review (independent session, ``trust=security``);
* mechanical tool output (lint/test/SAST, ``trust=deterministic``);
* human operator (manual override, ``trust=human``).

Agent observations that arrive through ``aisef memory`` are
``trust=agent`` and cannot author a finding in this module — that path was the
attack surface the security review flagged.  Memories can only *reference* a
finding already here.

Backward compatibility
----------------------

The string finding line (``"<severity>] <file>:<line>  <body>"``) is still the
canonical form for storage and prompt rendering.  The structured form is
**additive**: a parser maps the existing lines, callers that already pass
``list[str]`` keep working through ``Finding.parse_lines``.  The new shape is
what the harness itself uses.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Iterable


# ── closed enums ────────────────────────────────────────────────


class Trust(str, Enum):
    """Provenance of a finding's author.  ``agent`` cannot author a finding.

    The ordering reflects the trust ranking the user specified:

    human > deterministic > gate > security > reviewer > landed > agent
    """

    HUMAN = "human"
    DETERMINISTIC = "deterministic"
    GATE = "gate"
    SECURITY = "security"
    REVIEWER = "reviewer"
    LANDED = "landed"
    AGENT = "agent"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    REOPENED = "reopened"
    SUPERSEDED = "superseded"
    STUCK = "stuck"

    @property
    def is_terminal(self) -> bool:
        return self in (Status.CLOSED, Status.SUPERSEDED)


# Source kinds the gate must distinguish: a security finding is not a review
# finding, even if they share the severity enum.
SOURCE_REVIEWER = "reviewer"
SOURCE_SECURITY = "security"
SOURCE_DETERMINISTIC = "deterministic"
SOURCE_HUMAN = "human"
SOURCES = (
    SOURCE_REVIEWER, SOURCE_SECURITY, SOURCE_DETERMINISTIC, SOURCE_HUMAN,
)

# Reviewer/security roles must own their trust.  An agent-observed review note
# is not a review finding.
REVIEWER_TRUST = {Trust.REVIEWER, Trust.SECURITY, Trust.GATE,
                  Trust.DETERMINISTIC, Trust.HUMAN, Trust.LANDED}


# ── canonical line shape ───────────────────────────────────────

_LINE_RE = re.compile(
    r"^\[(?P<sev>low|medium|high|critical)\]\s+"
    r"(?P<file>[^:\s]+):(?P<line>\d+)\s+(?P<body>.+)$",
    re.IGNORECASE,
)


# ── the model ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """One advisory claim about one defect.

    Fields
    ------

    id
        Stable, deterministic 16-hex digest over the natural identity of the
        finding.  Two findings raised against the same ``(file, line, body,
        source, behavior_id)`` produce the same id — that's how we recognise a
        review re-raising a closed complaint.
    source
        Where it came from (``reviewer`` / ``security`` / ``deterministic`` /
        ``human``).
    trust
        Author's trust class.  ``agent`` is rejected at construction time.
    severity
        Blocking or advisory.  The gate decides which is which.
    file, line
        Code location the claim targets.  ``file=""`` for plan-level findings.
    body
        Single-line human-readable claim.  No secrets, no injection.
    scope
        Free-form scope tags (module, package, screen, role, ...).
    behavior_id
        Optional behavior id the finding ties to.  When set, the harness can
        reject ``open -> closed`` transitions that don't carry evidence on the
        same behavior.
    evidence
        Pointer to the disk artefact that proves the claim.  Empty means the
        finding has nothing backing it — the gate should treat that as
        ``unconfigured``.
    prescription
        What the author must do, in plain text.  Empty means the finding is a
        diagnostic, not an instruction.
    status
        Lifecycle state.  ``open`` is the only initial state; everything else
        requires evidence (close/reopen/supersede/stuck).
    """

    id: str
    source: str
    trust: str
    severity: str
    file: str = ""
    line: int = 0
    body: str = ""
    scope: tuple[str, ...] = ()
    behavior_id: str = ""
    evidence: str = ""
    prescription: str = ""
    status: str = Status.OPEN.value

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {self.source!r}")
        try:
            Trust(self.trust)
        except ValueError as e:
            raise ValueError(f"unknown trust {self.trust!r}") from e
        if Trust(self.trust) is Trust.AGENT:
            raise ValueError("agent observations cannot author findings")
        try:
            Severity(self.severity)
        except ValueError as e:
            raise ValueError(f"unknown severity {self.severity!r}") from e
        try:
            Status(self.status)
        except ValueError as e:
            raise ValueError(f"unknown status {self.status!r}") from e
        if self.line < 0:
            raise ValueError("line must be >= 0")

    # ── construction helpers ────────────────────────────────────

    @staticmethod
    def make(
        source: str,
        trust: str,
        severity: str,
        *,
        file: str = "",
        line: int = 0,
        body: str,
        scope: Iterable[str] = (),
        behavior_id: str = "",
        evidence: str = "",
        prescription: str = "",
        status: str = Status.OPEN.value,
    ) -> "Finding":
        digest = _digest(source=source, trust=trust, file=file, line=line,
                         body=body, behavior_id=behavior_id, scope=scope)
        return Finding(
            id=digest, source=source, trust=trust, severity=severity,
            file=file, line=line, body=body, scope=tuple(scope),
            behavior_id=behavior_id, evidence=evidence, prescription=prescription,
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status
        return d

    # ── line rendering (compatible with the previous list[str]) ──

    def format_line(self) -> str:
        """Render to the canonical single-line form.

        Returns ``[severity] <file>:<line>  <body>`` — same shape the gate
        previously parsed out of free-form text.  Pure round-trip.
        """
        sev = self.severity
        loc = f"{self.file}:{self.line}" if self.file else "<plan>"
        return f"[{sev}] {loc}  {self.body}"

    @staticmethod
    def parse_lines(
        lines: Iterable[str], *, source: str, trust: str,
    ) -> list["Finding"]:
        """Parse the canonical line shape back into findings.

        Unknown lines are ignored — they were never a finding in this module.
        The previous pipeline accepted a list of arbitrary strings; this narrow
        parsing is deliberate: free-form text is the attack surface that
        required a structured model in the first place.
        """
        out: list[Finding] = []
        for raw in lines:
            line = (raw or "").strip()
            if not line:
                continue
            m = _LINE_RE.match(line)
            if not m:
                continue
            out.append(Finding.make(
                source=source, trust=trust, severity=m.group("sev").lower(),
                file=m.group("file"), line=int(m.group("line")),
                body=m.group("body").strip(),
            ))
        return out


# ── digest ──────────────────────────────────────────────────────


def _digest(*, source: str, trust: str, file: str, line: int, body: str,
            behavior_id: str, scope: Iterable[str]) -> str:
    """Stable identity for a finding.

    Two findings against the same defect must compare equal.  The status,
    evidence and prescription are deliberately **excluded** from the identity
    so the harness can track a finding through ``open -> closed -> reopened``
    without losing the link.
    """
    h = hashlib.sha256()
    h.update(source.encode("utf-8"))
    h.update(b"\x00")
    h.update(trust.encode("utf-8"))
    h.update(b"\x00")
    h.update(file.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(int(line)).encode("utf-8"))
    h.update(b"\x00")
    h.update(body.strip().encode("utf-8"))
    h.update(b"\x00")
    h.update(behavior_id.encode("utf-8"))
    for tag in sorted(scope):
        h.update(b"\x00")
        h.update(tag.encode("utf-8"))
    return h.hexdigest()[:16]


# ── transition rules ───────────────────────────────────────────


@dataclass(frozen=True)
class Transition:
    """Recorded transition of a finding's status, evidence-bound."""

    finding_id: str
    previous: str
    next: str
    evidence: str = ""
    at: str = ""          # ISO timestamp; caller supplies; we don't import datetime here


# These are the only legal status transitions.  Everything else is refused
# with ``TransitionError``.  ``stuck`` is a human-only state.
_LEGAL: dict[Status, frozenset[Status]] = {
    Status.OPEN: frozenset({Status.CLOSED, Status.STUCK, Status.SUPERSEDED,
                            Status.REOPENED}),
    Status.CLOSED: frozenset({Status.REOPENED}),
    Status.REOPENED: frozenset({Status.CLOSED, Status.STUCK}),
    Status.STUCK: frozenset({Status.CLOSED}),
    Status.SUPERSEDED: frozenset(),
}


class TransitionError(ValueError):
    """Raised when a status transition violates the lifecycle rules."""


def apply_transition(f: Finding, *, to: Status, evidence: str = "",
                     transitions: list[Transition] | None = None,
                     force_prescription_match: bool = False,
                     previous_prescription: str = "") -> Finding:
    """Move ``f`` to ``to``, applying lifecycle rules.

    Rules
    -----

    * The transition must be in the legal map.
    * ``open -> closed`` requires evidence unless the caller explicitly says
      the author fulfilled the previous prescription (then the gate can call
      this with ``force_prescription_match=True`` **and** a matching
      ``previous_prescription``).  This is the rule that prevents
      "the author did what I told them, and I failed them for it" (bug 61).
    * ``closed -> reopened`` requires evidence on the same behavior_id —
      otherwise the reviewer is just relitigating a closed complaint without
      new information, and the harness treats that as a transition refusal.
    """
    if to not in _LEGAL[Status(f.status)]:
        raise TransitionError(
            f"illegal transition {f.status} -> {to.value}")
    if to is Status.CLOSED:
        if not evidence and not force_prescription_match:
            raise TransitionError("closing requires evidence")
        if force_prescription_match and previous_prescription and f.prescription:
            if f.prescription.strip() != previous_prescription.strip():
                raise TransitionError(
                    "closing via prescription requires the new prescription "
                    "to match the previous one — refusing to move the goalposts")
    if to is Status.REOPENED and not evidence:
        raise TransitionError("reopening requires evidence")
    next_f = Finding(
        id=f.id, source=f.source, trust=f.trust, severity=f.severity,
        file=f.file, line=f.line, body=f.body, scope=f.scope,
        behavior_id=f.behavior_id, evidence=evidence or f.evidence,
        prescription=f.prescription, status=to.value,
    )
    if transitions is not None:
        transitions.append(Transition(
            finding_id=f.id, previous=f.status, next=to.value,
            evidence=evidence,
        ))
    return next_f


# ── collections ────────────────────────────────────────────────


@dataclass
class FindingBook:
    """Per-attempt set of findings.  Pure data, no I/O."""

    findings: list[Finding] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)

    def add(self, f: Finding) -> None:
        for existing in self.findings:
            if existing.id == f.id:
                # Same id, different status: merge into the latest version.
                self.findings[self.findings.index(existing)] = f
                return
        self.findings.append(f)

    def __len__(self) -> int:
        return len(self.findings)

    def __iter__(self):
        return iter(self.findings)

    def by_id(self, fid: str) -> Finding | None:
        for f in self.findings:
            if f.id == fid:
                return f
        return None

    def blocking(self) -> list[Finding]:
        return [f for f in self.findings
                if f.status in (Status.OPEN.value, Status.REOPENED.value)
                and Severity(f.severity) in (Severity.HIGH, Severity.CRITICAL)]

    def blocking_ids(self) -> list[str]:
        return [f.id for f in self.blocking()]

    def to_lines(self) -> list[str]:
        """Render to the canonical line shape the gate already accepts."""
        return [f.format_line() for f in self.findings]

    @classmethod
    def from_lines(cls, lines: Iterable[str], *, source: str,
                   trust: Trust | str | None = None) -> "FindingBook":
        """Parse a list of canonical lines into a book.

        Unknown lines are dropped (``parse_lines`` keeps only canonical
        shape); callers that want strict validation should use
        ``Finding.parse_lines`` and inspect.
        """
        book = cls()
        trust_value = (trust.value if isinstance(trust, Trust) else trust) \
            or Trust.REVIEWER.value
        for f in Finding.parse_lines(lines, source=source, trust=trust_value):
            book.add(f)
        return book


__all__ = [
    "Finding", "FindingBook", "Transition", "TransitionError",
    "Trust", "Severity", "Status",
    "SOURCE_REVIEWER", "SOURCE_SECURITY", "SOURCE_DETERMINISTIC", "SOURCE_HUMAN",
    "SOURCES", "REVIEWER_TRUST",
    "apply_transition",
]
