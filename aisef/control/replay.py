"""Re-score story gates on recorded evidence (ADR-005 V4) — like Inspect AI's
`inspect score` or Harbor's `regrade`, built from what we already have.

`gate.evaluate` is pure over `Evidence` + kwargs, and since V4 `implement`
records those kwargs in a `note gate:input` just before `gate:verdict`. So for
every attempt that has this record, the **current** gate can re-score an **old**
attempt: slice evidence at the `gate:input` `seq` (exactly the events the gate
saw), reconstruct kwargs, call `evaluate`, compare blocking checks against the
recorded `gate:verdict`. $0, deterministic, and this is what 17/25 mis-scored
bugs need: fix a gate rule and immediately see which attempts change outcome,
before paying for another agent run.

Re-scores **merged rules** on recorded reviewer/security findings — no model
calls. Attempts without `gate:input` (pre-V4 evidence) are reported as
non-replayable; kwargs are never guessed from other sources.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..harness.observe import NOTE, Evidence, Event
from .gate import StoryGate, evaluate
from .security import parse as parse_security

GATE_INPUT = "gate:input"
GATE_VERDICT = "gate:verdict"

BANNER = ("replay: re-score gate rules (gate.evaluate from current code) on recorded "
          "evidence and reviewer/security findings — no model calls")


@dataclass
class Replay:
    story_id: str
    attempt: int
    seq: int                      # seq of `gate:input`
    candidate: str
    gate: StoryGate
    #: Blocking checks recorded in the `gate:verdict` after this input; None = no verdict.
    recorded: list[str] | None

    @property
    def now(self) -> list[str]:
        return [c.name for c in self.gate.failures]

    def rows(self) -> list[tuple[str, str, str]]:
        """(check name, recorded, now): recorded only knows blocked/not — `gate:verdict`
        only stores blocking check names; now has full six-outcome detail."""
        prev = set(self.recorded or [])
        return [(c.name, "✗" if c.name in prev else "·", c.outcome.mark) for c in self.gate.checks]

    def changed(self) -> list[str]:
        """Checks whose blocking status changed — the only comparison possible with the old record."""
        if self.recorded is None:
            return []
        prev, current = set(self.recorded), set(self.now)
        return sorted(prev ^ current)

    def summary(self) -> str:
        head = (f"{self.story_id} attempt {self.attempt} · candidate {self.candidate[:7] or '—'} · "
                f"recorded: {'PASS' if self.recorded == [] else 'FAIL' if self.recorded else 'no verdict'}"
                f" · now: {'PASS' if self.gate.passed else 'FAIL'}")
        lines = [head, "  check                            | recorded | now"]
        for name, prev, current in self.rows():
            marker = " ≠" if name in self.changed() else ""
            lines.append(f"  {name:<32} | {prev:^6} | {current}{marker}")
        changed = self.changed()
        lines.append("  diff: " + (", ".join(changed) if changed else "none — same blocking checks"))
        return "\n".join(lines)


def kwargs_from(detail: dict) -> dict:
    """Reconstruct `evaluate` kwargs from `gate:input`. `security` is stored in
    the same shape as `tool_run security` ({findings: ["[severity] ..."], error})
    so `parse` can read it back; other keys are plain JSON."""
    kw = {k: v for k, v in detail.items() if k not in ("attempt",)}
    sec = kw.get("security")
    if sec is not None:
        rep = parse_security("\n".join(sec.get("findings") or []))
        rep.error = str(sec.get("error") or "")
        kw["security"] = rep
    return kw


def _pairs(evidence: Evidence) -> list[tuple[Event, Event | None]]:
    """Pair each `gate:input` with the **first** `gate:verdict` after it.

    Pairing is by **position** in the time-sorted event list, not by the
    ``seq`` number printed in the file. Numeric comparison breaks when a
    build that could not read the file tail reset the ``_next_seq`` counter
    (bug 42 → bug 47).  Two events on disk now carry ``seq`` values that
    are out of order while their timestamps are perfectly ordered.
    """
    inputs = evidence.of(NOTE, GATE_INPUT)
    verdicts = evidence.of(NOTE, GATE_VERDICT)
    out = []
    for i, inp in enumerate(inputs):
        try:
            inp_idx = evidence.events.index(inp)
        except ValueError:
            continue
        try:
            boundary_idx = evidence.events.index(inputs[i + 1]) if i + 1 < len(inputs) else len(evidence.events)
        except ValueError:
            boundary_idx = len(evidence.events)
        v = next(
            (v for v in verdicts
             if inp_idx < evidence.events.index(v) < boundary_idx),
            None,
        )
        out.append((inp, v))
    return out


def unreplayable(evidence: Evidence) -> list[int]:
    """Attempt numbers that have a `gate:verdict` without a preceding `gate:input`
    — pre-V4 evidence. Returns attempt numbers so the reader knows what was skipped."""
    co = {id(v) for _, v in _pairs(evidence) if v is not None}
    return [int(v.detail.get("attempt") or 0)
            for v in evidence.of(NOTE, GATE_VERDICT) if id(v) not in co]


def replay(evidence: Evidence, *, attempt: int = 0) -> list[Replay]:
    """Re-score all attempts that have a `gate:input` (or only the given `attempt`)."""
    out = []
    for inp, verdict in _pairs(evidence):
        attempt_num = int(inp.detail.get("attempt") or 0)
        if attempt and attempt_num != attempt:
            continue
        # Use position-in-sorted-list, not ``seq``, so a build that reset the
        # counter mid-file doesn't make replay look at the wrong slice of the
        # log (bug 47 / bug 42).
        slice_end = evidence.events.index(inp) + 1 if inp in evidence.events else len(evidence.events)
        before = Evidence(
            story_id=evidence.story_id,
            events=evidence.events[:slice_end],
        )
        kw = kwargs_from(inp.detail)
        gate = evaluate(evidence.story_id, before, **kw)
        out.append(Replay(
            story_id=evidence.story_id, attempt=attempt_num, seq=inp.seq,
            candidate=str(kw.get("candidate") or ""), gate=gate,
            recorded=None if verdict is None else [str(x) for x in verdict.detail.get("failures") or []],
        ))
    return out
