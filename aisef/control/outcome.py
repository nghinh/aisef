"""A single outcome type for all gates.

Previously `KindResult` had `ran/ok/skipped/unrunnable`, `Check` had
`passed/skipped` (two versions, in `gate` and `deploy`), and "waived" was a
separate list — four outcomes collapsed into two across three places. Real
consequences were hit (bugs 33/36/37): "unconfigured" showed as "passed",
"environment not set up" showed as "red test". Here there are **six** outcomes,
three questions, one symbol table:

- `blocks`          — blocks the gate (FAILED, UNRUNNABLE)
- `counts_as_done`  — counts as done (PASSED, WAIVED, NOT_APPLICABLE)
- `must_be_named`   — must be surfaced, not silenced (UNCONFIGURED, UNRUNNABLE)

Invariant: every outcome other than PASSED carries a one-line reason, and
UNCONFIGURED/UNRUNNABLE never share the same symbol as PASSED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNRUNNABLE = "unrunnable"            # command exists but environment not set up — not a red test
    UNCONFIGURED = "unconfigured"        # no command / not configured — does not count as passed
    WAIVED = "waived"                    # explicitly waived by a person, reason recorded
    NOT_APPLICABLE = "not-applicable"    # condition does not apply (e.g. story has no UI)

    @property
    def blocks(self) -> bool:
        return self in (Outcome.FAILED, Outcome.UNRUNNABLE)

    @property
    def counts_as_done(self) -> bool:
        return self in (Outcome.PASSED, Outcome.WAIVED, Outcome.NOT_APPLICABLE)

    @property
    def must_be_named(self) -> bool:
        return self in (Outcome.UNCONFIGURED, Outcome.UNRUNNABLE)

    @property
    def mark(self) -> str:
        return MARK[self]


MARK = {
    Outcome.PASSED: "✅",
    Outcome.FAILED: "✗",
    Outcome.UNRUNNABLE: "⚠",
    Outcome.UNCONFIGURED: "○",
    Outcome.WAIVED: "◇",
    Outcome.NOT_APPLICABLE: "–",
}

#: The kernel's typed STAGE / SESSION outcomes (docs/ASSURANCE-KERNEL.md §4). A stage returns one of these, never a
#: boolean or a sentence; the story loop routes on them; `StoryOutcome.terminal` is one of them.
class StageOutcome(str, Enum):
    PASS = "PASS"
    QUALITY_BLOCK = "QUALITY_BLOCK"            # the work is wrong — the developer's
    UNRUNNABLE = "UNRUNNABLE"                  # a verifier said nothing (cut, moved tree, no structured verdict) — retry THAT stage
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"  # tool missing, context window, permission, provider cost cap — never quality
    INFRA_FAILURE = "INFRA_FAILURE"            # provider cut, 5xx, rate limit, dead child, ledger lock — retried on the infra budget
    AUTH_FAILURE = "AUTH_FAILURE"              # credential rejected — fatal, free
    NOOP = "NOOP"                              # the session wrote nothing — F1 decides on a FRESH verdict
    PLAN_CONFLICT = "PLAN_CONFLICT"            # stuck / deadlock — the owner's
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    ISOLATION_BREACH = "ISOLATION_BREACH"      # trunk written from inside a story — fatal
    MERGE_CONFLICT = "MERGE_CONFLICT"
    ORPHANED = "ORPHANED"
    BUDGET = "BUDGET"                          # the kernel's cost cap — typed terminal, uncharged


DEFAULT_REASON = {
    Outcome.FAILED: "failed",
    Outcome.UNRUNNABLE: "cannot run — environment not set up, not a red test",
    Outcome.UNCONFIGURED: "not configured — does not count as passed",
    Outcome.WAIVED: "explicitly waived",
    Outcome.NOT_APPLICABLE: "not applicable",
}


#: Gate check kinds (ADR-005 V9, after Inspect `Score`/TB rubric). Closed: new
#: checks must pick one — who scores this? Deterministic machine (test/lint/
#: coverage), structural matcher (scope, test names, DOM), security review,
#: model-as-judge, or human. `human` is unused; reserved for per-check waiver
#: if a real story needs it (ADR-005 S3 P2).
CHECK_KINDS = ("deterministic", "structural", "security", "model-judge", "human")


@dataclass
class Check:
    """A single gate check. `outcome` also accepts bool for pass/fail-only sites:
    `Check("lint", lint.ok)` — anywhere not strictly pass/fail must specify the
    exact outcome; no more generic `skipped=True`.

    `kind` and `evidence` form the minimal scoring contract (ADR-005 V9): `kind`
    is one of `CHECK_KINDS`; `evidence` is a **pointer** — `seq` values of the
    events the check read to reach its conclusion, not their content (content
    lives in `evidence/*.jsonl`). Empty means the check was derived from
    `gate.evaluate` kwargs rather than events — and the caller must state that.
    No `blocking` field: whether a check blocks is determined by
    `Outcome.blocks`; no check is advisory yet (YAGNI)."""

    name: str
    outcome: Outcome
    detail: str = ""
    kind: str = ""
    evidence: list[int] = field(default_factory=list)
    data: dict = field(default_factory=dict)   # typed payload a consumer may read (SS-32); `detail` stays prose for humans

    def __post_init__(self) -> None:
        if isinstance(self.outcome, bool):
            self.outcome = Outcome.PASSED if self.outcome else Outcome.FAILED
        # Invariant: non-PASSED outcomes always carry a reason — fill it here so
        # `detail` (JSON, feedback, reports) and `line()` say the same thing.
        if not self.detail and self.outcome is not Outcome.PASSED:
            self.detail = DEFAULT_REASON.get(self.outcome, "")

    @property
    def passed(self) -> bool:
        """Does not block the gate. Not synonymous with "passed" — see `outcome`."""
        return not self.outcome.blocks

    @property
    def skipped(self) -> bool:
        return self.outcome in (Outcome.UNCONFIGURED, Outcome.NOT_APPLICABLE, Outcome.WAIVED)

    def line(self) -> str:
        return f"  {self.outcome.mark} {self.name}" + (f" — {self.detail}" if self.detail else "")

    def as_dict(self) -> dict:
        return {"name": self.name, "outcome": self.outcome.value, "passed": self.passed,
                "skipped": self.skipped, "detail": self.detail,
                "kind": self.kind, "evidence": list(self.evidence), **({"data": self.data} if self.data else {})}
