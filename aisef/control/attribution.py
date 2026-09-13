"""Spend attribution — what the money bought (ADR-009 §Open O4).

`ledger.py` answers *which behaviours hold*.  `budget.py` answers *what a run
cost*.  Nothing joined the two, so no one could say what a dollar bought.  This
module is that join and, like `ledger.py`, it is a **projection**: it records
nothing of its own, every number here is recomputable from `evidence/*.jsonl`
plus the behaviour ledger.

The unit of spend is read off the evidence, never assumed
--------------------------------------------------------
`cost_usd` is a unit only when the provider filled it in for **every** model
session.  Measured 2026-09-14 on the four corpora on disk: `todo` reports a
dollar figure for 1 of 180 sessions and `$0.00` for the other 179.  A partial
record is worse than an empty one — averaged over the corpus it yields a number
that is wrong by two orders of magnitude instead of merely missing.  So `unit`
is `usd` only at full coverage; otherwise it is `tokens`, and the caller gets
the price formula rather than a fabricated dollar (the method of
`docs/E4-COST-DECOMPOSITION.md`, which is sound and reused here).

Token counts are not comparable across clients either.  A client whose provider
omits `tokens.cache` (`clients/opencode.py` accumulating `step_finish`) bills
every re-sent prompt as fresh `input`, so its `input` total is a sum over turns
of the whole context.  `Attribution.cache_share` carries that fact so two
corpora are never added into one number.

Six session classes, and why a session's own exit wins
-----------------------------------------------------
A session's `exit_status` outranks the gate verdict that follows it: a session
the turn cap killed never reached the gate on its merits, and charging its
tokens to "the gate blocked this" hides the cap — which is exactly the failure
`docs/E4-COST-DECOMPOSITION.md` §3 found and fixed in the adapter.

* `env-failed`   — `exit_status` in infra / error / timeout: the environment
  ended the session, the agent did nothing wrong, the tokens are still spent.
* `turn-cap`     — `exit_status == max_turns`: the cap ended it.
* `passed`       — session completed, the next gate verdict passed.
* `gate-blocked` — session completed, the next gate verdict blocked.
* `no-verdict`   — session completed and no gate ever scored it (run abandoned).
* `planning`     — session in a `plan-` / `mockup-` / `skill-` evidence file:
  real spend that buys no story behaviour directly.

ADR-009 names the buckets "plan-blocked / code-failed / environment-failed /
passed".  `gate-blocked` is reported with the failing check names alongside
(`blocked_by`), because "code-failed" is not a distinction the evidence records
— the gate names the check, not the layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..harness.observe import AGENT_RUN, NOTE, EvidenceStore
from . import ledger as ledger_mod

PASSED = "passed"
GATE_BLOCKED = "gate-blocked"
TURN_CAP = "turn-cap"
ENV_FAILED = "env-failed"
NO_VERDICT = "no-verdict"
PLANNING = "planning"

#: Print order: what the gate scored first, then what never got scored.
CLASSES = (PASSED, GATE_BLOCKED, TURN_CAP, ENV_FAILED, NO_VERDICT, PLANNING)

#: `exit_status` values meaning the environment ended the session, not the agent.
ENV_EXITS = ("infra", "error", "timeout")
TURN_CAP_EXIT = "max_turns"

USD = "usd"
TOKENS = "tokens"

#: Below this cache share, `input` is a sum over turns of the whole prompt and
#: is not comparable with a caching corpus.  Measured 2026-09-14: `todo-cli`
#: 84%, `todo-e2e` 75%, `todo` 46%, `todo-oc` 4% — the gap is an order of
#: magnitude wide, so any cut in the 10-40% range separates the same corpora.
CACHE_SHARE_COMPARABLE = 0.25


@dataclass
class Spend:
    """What a set of model sessions consumed.  Additive, no derived fields."""

    sessions: int = 0
    turns: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cost_usd: float = 0.0

    def add(self, event) -> "Spend":
        tok = event.tokens or {}
        self.sessions += 1
        self.turns += int(event.detail.get("turns") or 0)
        self.input += int(tok.get("input") or 0)
        self.output += int(tok.get("output") or 0)
        self.cache_read += int(tok.get("cache_read") or 0)
        self.cost_usd += float(event.cost_usd or 0.0)
        return self

    def merge(self, other: "Spend") -> "Spend":
        self.sessions += other.sessions
        self.turns += other.turns
        self.input += other.input
        self.output += other.output
        self.cache_read += other.cache_read
        self.cost_usd += other.cost_usd
        return self

    def amount(self, unit: str) -> float:
        """Spend in the corpus's unit: dollars, or **input** tokens.

        Input only, for the tokens unit: output is 58-392x smaller in the four
        corpora measured 2026-09-14 (`todo-cli` 58x, `todo-e2e` 69x, `todo`
        170x, `todo-oc` 392x), and without a price list there is no defensible
        way to add the two.  `output` stays on the record so a reader who has a
        price list can check the conclusion does not hinge on the choice.
        """
        return self.cost_usd if unit == USD else float(self.input)


@dataclass
class StoryRow:
    """One story: what it consumed, split by class, and what it produced."""

    id: str
    by_class: dict[str, Spend] = field(default_factory=dict)
    verified: int = 0
    gap: int = 0
    reopened: int = 0
    attempts: int = 0                       # gate verdicts scored on this story

    @property
    def net_verified(self) -> int:
        """VERIFIED minus REOPENED — a behaviour that broke again was not bought.

        Same definition as `Ledger.metrics()['loops'][].marginal`, so the two
        readouts cannot disagree about what "net" means.
        """
        return self.verified - self.reopened

    def total(self) -> Spend:
        out = Spend()
        for sp in self.by_class.values():
            out.merge(sp)
        return out

    def spend_of(self, cls: str) -> Spend:
        return self.by_class.setdefault(cls, Spend())


@dataclass
class Attribution:
    """Spend joined to outcomes for one artifact root."""

    root: Path
    unit: str = TOKENS
    #: Sessions carrying `cost_usd > 0` / all sessions.  `unit` is USD only at 1.0.
    cost_coverage: float = 0.0
    stories: dict[str, StoryRow] = field(default_factory=dict)
    #: Gate check name -> times it blocked an attempt.
    blocked_by: dict[str, int] = field(default_factory=dict)
    #: Session role (developer / review / security / review-retry / ...) -> spend.
    by_role: dict[str, Spend] = field(default_factory=dict)
    #: Corpus-level ledger counts.  **Not** the column sum of `stories`: one
    #: behaviour can belong to two stories (an FR both cover), so the per-story
    #: columns overlap while these do not.
    verified: int = 0
    gap: int = 0
    reopened: int = 0

    @property
    def net_verified(self) -> int:
        return self.verified - self.reopened

    @property
    def cache_share(self) -> float:
        """Cache reads as a fraction of all prompt tokens — the comparability key.

        A boolean "did any session report a cache read" is not enough: measured
        2026-09-14, `todo-oc` reports cache on 4% of its prompt tokens and
        `todo-cli` on 84%.  Both "report caching", yet one bills re-sent context
        as fresh `input` and the other does not, so their `input` totals differ
        by construction and must never be added or compared.
        """
        whole = self.total()
        denom = whole.input + whole.cache_read
        return (whole.cache_read / denom) if denom else 0.0

    def by_class(self) -> dict[str, Spend]:
        out: dict[str, Spend] = {}
        for row in self.stories.values():
            for cls, sp in row.by_class.items():
                out.setdefault(cls, Spend()).merge(sp)
        return out

    def total(self) -> Spend:
        out = Spend()
        for sp in self.by_class().values():
            out.merge(sp)
        return out

    def share(self, cls: str) -> float:
        """Fraction of total spend in one class.  0.0 when nothing was spent."""
        whole = self.total().amount(self.unit)
        got = self.by_class().get(cls)
        return (got.amount(self.unit) / whole) if whole and got else 0.0

    def productive_share(self) -> float:
        """Fraction of spend on stories that ended with `net_verified > 0`.

        The complement is the honest name for money that bought nothing: a
        story blocked to the end, or one whose behaviours all reopened.
        """
        whole = self.total().amount(self.unit)
        if not whole:
            return 0.0
        good = sum(r.total().amount(self.unit)
                   for r in self.stories.values() if r.net_verified > 0)
        return good / whole

    def per_unit(self) -> float | None:
        """Net VERIFIED behaviours per dollar, or per **million** input tokens.

        `None` when nothing was spent: no denominator, no number.
        """
        whole = self.total().amount(self.unit)
        if not whole:
            return None
        return self.net_verified / (whole if self.unit == USD else whole / 1e6)


def _class_of_exit(exit_status: str) -> str:
    if exit_status == TURN_CAP_EXIT:
        return TURN_CAP
    return ENV_FAILED if exit_status in ENV_EXITS else ""


def build(artifact_root: Path | str) -> Attribution:
    """Project `evidence/` plus the behaviour ledger into a spend attribution."""
    root = Path(artifact_root)
    led = ledger_mod.build(root)
    summary = led.summary()
    att = Attribution(
        root=root,
        verified=summary["verified"], gap=summary["gap"], reopened=summary["reopened"],
    )

    store = EvidenceStore(root)
    paid = 0
    for sid in store.stories():
        row = att.stories.setdefault(sid, StoryRow(id=sid))
        phase = sid.startswith(ledger_mod.PHASE_PREFIXES) or sid.startswith(ledger_mod.LOOP_PREFIX)
        pending: list = []
        for e in store.read(sid).events:
            if e.kind == AGENT_RUN:
                if e.cost_usd:
                    paid += 1
                att.by_role.setdefault(str(e.detail.get("role") or "?"), Spend()).add(e)
                own = PLANNING if phase else _class_of_exit(str(e.detail.get("exit_status") or ""))
                if own:
                    # The session's own fate is decided; no later verdict can
                    # claim these tokens.
                    row.spend_of(own).add(e)
                else:
                    pending.append(e)
            elif e.kind == NOTE and e.name == "gate:verdict":
                row.attempts += 1
                cls = PASSED if e.ok else GATE_BLOCKED
                if not e.ok:
                    for check in (e.detail.get("failures") or ["unnamed"]):
                        att.blocked_by[str(check)] = att.blocked_by.get(str(check), 0) + 1
                for held in pending:
                    row.spend_of(cls).add(held)
                # Assign by **event order**, not by attempt number: a story run
                # twice has two "attempt 1"s, and keying on the number labels
                # the first run's sessions with the second run's verdict.
                pending = []
        for held in pending:
            row.spend_of(NO_VERDICT).add(held)

    # Stories planned but never run still get a row: an unstarted story with
    # gaps is part of "where the money did not go" and must not vanish.
    for sid in led.stories:
        att.stories.setdefault(sid, StoryRow(id=sid))
    for sid, row in att.stories.items():
        row.verified, row.gap, row.reopened = led.counts_for(sid)

    sessions = att.total().sessions
    att.cost_coverage = (paid / sessions) if sessions else 0.0
    att.unit = USD if sessions and paid == sessions else TOKENS
    return att


def _fmt(amount: float, unit: str) -> str:
    return f"${amount:,.2f}" if unit == USD else f"{amount:,.0f}"


def report_lines(att: Attribution) -> list[str]:
    """Markdown: the unit first, then where the spend went, then what it bought."""
    unit = att.unit
    whole = att.total()
    per = att.per_unit()
    denom = "$" if unit == USD else "M input tokens"
    out = [f"# Spend attribution — `{att.root.parent.name}`", ""]

    if unit == USD:
        out += [f"Unit: **USD** — the provider priced every one of "
                f"{whole.sessions} sessions.", ""]
    else:
        out += [f"Unit: **input tokens** — the provider priced "
                f"{att.cost_coverage:.0%} of {whole.sessions} sessions "
                f"({whole.cost_usd:.2f} USD recorded in total), so dollars here "
                f"would be invented. With `p` = price per 1M input tokens and "
                f"`q` = per 1M output:", "",
                f"    cost ≈ {whole.input / 1e6:.2f} × p + {whole.output / 1e6:.3f} × q", ""]
        share = att.cache_share
        out += [f"Cache reads are {share:.0%} of prompt tokens "
                f"({whole.cache_read:,} cached vs {whole.input:,} fresh); most price "
                f"lists charge them far less, so they are counted separately.", ""]
        if share < CACHE_SHARE_COMPARABLE:
            out += [f"⚠ At {share:.0%} cache, this client bills re-sent context as fresh "
                    "`input`: the totals below are a sum over turns of the whole prompt "
                    "and are **not** comparable with a corpus that caches.", ""]

    out += [f"Net VERIFIED per {denom}: "
            + (f"**{per:.2f}**" if per is not None else "— (nothing spent)"),
            "",
            f"{att.verified} verified · {att.gap} gap · {att.reopened} reopened "
            f"→ net **{att.net_verified}** behaviours "
            f"for {_fmt(whole.amount(unit), unit)} across {whole.sessions} sessions "
            f"({whole.turns:,} turns).", ""]

    by_cls = att.by_class()
    out += ["## Where the spend went", "",
            f"| class | sessions | turns | {unit} | share |", "|---|---|---|---|---|"]
    for cls in CLASSES:
        sp = by_cls.get(cls)
        if not sp or not sp.sessions:
            continue
        out.append(f"| {cls} | {sp.sessions} | {sp.turns:,} | "
                   f"{_fmt(sp.amount(unit), unit)} | {att.share(cls):.0%} |")
    out += ["",
            f"Spend on stories that ended with a net VERIFIED behaviour: "
            f"**{att.productive_share():.0%}**.", ""]

    out += ["## Per story", "",
            "Ledger columns **overlap** between stories (one FR can be covered by "
            "two), so they do not sum to the corpus counts above.", "",
            f"| story | attempts | {unit} | share | passed | gate-blocked | "
            f"turn-cap | env-failed | no-verdict | verified | gap | reopened | net |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    ranked = sorted(att.stories.values(),
                    key=lambda r: (-r.total().amount(unit), r.id))
    for row in ranked:
        tot = row.total()
        if not tot.sessions and not (row.verified or row.gap or row.reopened):
            continue
        cells = [_fmt(row.spend_of(c).amount(unit), unit) if row.spend_of(c).sessions else "—"
                 for c in (PASSED, GATE_BLOCKED, TURN_CAP, ENV_FAILED, NO_VERDICT)]
        share = tot.amount(unit) / whole.amount(unit) if whole.amount(unit) else 0.0
        out.append(f"| {row.id} | {row.attempts} | {_fmt(tot.amount(unit), unit)} | "
                   f"{share:.0%} | " + " | ".join(cells)
                   + f" | {row.verified} | {row.gap} | {row.reopened} | "
                     f"{row.net_verified} |")

    if att.blocked_by:
        out += ["", "## What the gate blocked on", "", "| check | blocks |", "|---|---|"]
        out += [f"| {k} | {v} |" for k, v in
                sorted(att.blocked_by.items(), key=lambda kv: (-kv[1], kv[0]))]

    if att.by_role:
        out += ["", "## By role", "", f"| role | sessions | turns | {unit} | share |",
                "|---|---|---|---|---|"]
        tot_role = sum(sp.amount(unit) for sp in att.by_role.values()) or 1.0
        for role, sp in sorted(att.by_role.items(), key=lambda kv: -kv[1].amount(unit)):
            out.append(f"| {role} | {sp.sessions} | {sp.turns:,} | "
                       f"{_fmt(sp.amount(unit), unit)} | "
                       f"{sp.amount(unit) / tot_role:.0%} |")
    return out + [""]


__all__ = [
    "Attribution", "Spend", "StoryRow", "build", "report_lines",
    "CLASSES", "PASSED", "GATE_BLOCKED", "TURN_CAP", "ENV_FAILED",
    "NO_VERDICT", "PLANNING", "USD", "TOKENS",
]
