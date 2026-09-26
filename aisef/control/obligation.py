"""What each acceptance criterion must SHOW between its story's parent and its candidate (TDD proof policy V2).

Policy V1 asked one question of every criterion — *is its test red without this story's code?* — and treated every
other answer as the developer's failure. In a compositional plan that is wrong three ways: a behaviour an upstream
story legitimately delivered, a behaviour this story must merely preserve, and a prohibition that holds on an empty
tree can none of them be red at the parent, and no correct implementation can make them red. V1 sent the developer
back to rewrite correct code for what is a **planning** fact (measured: W1 workload V1, 8 refused attempts across
three profiles, 0 of them a false block — see W1-DELIVERY-FAILURE-DECOMPOSITION.json).

V2 makes the obligation explicit **planning data** — never inferred from the criterion's prose at runtime (owner
decision 2026-09-20, section 9) — and judges each criterion by its own obligation:

    CHANGE_REQUIRED     parent PROVEN RED  -> candidate GREEN   this story contributes the behaviour
    PRESERVE_REQUIRED   parent GREEN       -> candidate GREEN   this story must not break what it inherits
    NEGATIVE_INVARIANT  parent GREEN       -> candidate GREEN   a prohibition that holds before and after

Only CHANGE_REQUIRED is evidence that the story itself contributed something, so a normal implementation story must
carry at least one (`story_contribution`); a story whose whole contract is already satisfied at entry is a plan
defect, not a developer failure, and must not consume developer attempts (sections 5, 8, 12).

Evidence comes from ONE proof engine: the SS-81 states in `control/proof.py`. Nothing here re-reads a test run.
"""
from __future__ import annotations

from enum import Enum

from . import proof


class Mode(str, Enum):
    CHANGE_REQUIRED = "CHANGE_REQUIRED"
    PRESERVE_REQUIRED = "PRESERVE_REQUIRED"
    NEGATIVE_INVARIANT = "NEGATIVE_INVARIANT"


class Side(str, Enum):
    """What one side (parent or candidate) shows for one criterion, read from the proof states of its tests."""

    RED = "RED"                  # every test of the criterion proves red (RED_EXECUTED / RED_COLLECTION_BOUND_TO_STORY)
    GREEN = "GREEN"              # every test ran and passed
    MIXED = "MIXED"              # some green, some red — the criterion is partly satisfied already
    NO_EVIDENCE = "NO_EVIDENCE"  # tests exist but their states prove nothing: unrunnable, not collected, skipped, absent
    NO_TESTS = "NO_TESTS"        # no test carries this criterion's code at all


class Outcome(str, Enum):
    SATISFIED = "SATISFIED"
    DEVELOPER_QUALITY_BLOCK = "DEVELOPER_QUALITY_BLOCK"        # the obligation is sound; the candidate does not meet it
    DEVELOPER_REGRESSION = "DEVELOPER_REGRESSION"              # inherited behaviour / prohibition broken by this story
    PLAN_OVERLAP = "PLAN_OVERLAP"                              # CHANGE_REQUIRED already satisfied at story entry
    PLAN_PRECONDITION_MISSING = "PLAN_PRECONDITION_MISSING"    # nothing to preserve / prohibition already violated
    PLAN_METADATA_MISSING = "PLAN_METADATA_MISSING"            # no declared obligation, or an unknown mode
    NO_EVIDENCE = "NO_EVIDENCE"                                # a side did not answer — never a pass


class Owner(str, Enum):
    PLAN = "PLAN"
    DEVELOPER = "DEVELOPER"
    ENVIRONMENT = "ENVIRONMENT"
    VERIFIER = "VERIFIER"


#: Outcome -> who must act. Routing (owner section 12) reads this, never the outcome's wording.
OWNER_OF = {
    Outcome.SATISFIED: None,
    Outcome.DEVELOPER_QUALITY_BLOCK: Owner.DEVELOPER,
    Outcome.DEVELOPER_REGRESSION: Owner.DEVELOPER,
    Outcome.PLAN_OVERLAP: Owner.PLAN,
    Outcome.PLAN_PRECONDITION_MISSING: Owner.PLAN,
    Outcome.PLAN_METADATA_MISSING: Owner.PLAN,
    Outcome.NO_EVIDENCE: Owner.ENVIRONMENT,
}

EXPECTED = {Mode.CHANGE_REQUIRED: "RED -> GREEN", Mode.PRESERVE_REQUIRED: "GREEN -> GREEN",
            Mode.NEGATIVE_INVARIANT: "GREEN -> GREEN"}

#: A story whose criteria carry no CHANGE_REQUIRED obligation contributes no new behaviour. Only a story type that
#: says so explicitly may look like that.
VERIFICATION_ONLY = "VERIFICATION_ONLY"
NORMAL = "NORMAL"
STORY_TYPES = (NORMAL, VERIFICATION_ONLY)


def side(states: dict[str, tuple[proof.Proof, str]] | None) -> Side:
    """One criterion's side, from the proof states of the tests carrying its code."""
    if not states:
        return Side.NO_TESTS
    values = [p for p, _ in states.values()]
    red = [p for p in values if p in proof.PROVES_RED]
    green = [p for p in values if p is proof.Proof.GREEN_EXECUTED]
    if len(red) == len(values):
        return Side.RED
    if len(green) == len(values):
        return Side.GREEN
    if red and green and len(red) + len(green) == len(values):
        return Side.MIXED
    return Side.NO_EVIDENCE


def evaluate(mode: Mode | str | None, parent: Side, candidate: Side) -> tuple[Outcome, str]:
    """One criterion's verdict from its declared obligation and the two sides. Pure; no I/O, no prose parsing."""
    try:
        m = Mode(mode)
    except ValueError:
        return Outcome.PLAN_METADATA_MISSING, (f"no declared proof obligation ({mode!r}) — the plan must say what this "
                                               "criterion has to show; the kernel never guesses it from the wording")
    if candidate is Side.NO_TESTS:
        return Outcome.DEVELOPER_QUALITY_BLOCK, ("no test at the candidate carries this criterion's code — the "
                                                 "criterion is unverified whatever the code does")
    if m is Mode.CHANGE_REQUIRED:
        if parent in (Side.GREEN, Side.MIXED):
            return Outcome.PLAN_OVERLAP, ("declared CHANGE_REQUIRED, but the behaviour is already there at the story's "
                                          f"parent ({parent.value.lower()}) — an upstream story or the plan already "
                                          "delivers it; correct the plan, do not rewrite working code")
        if parent in (Side.NO_EVIDENCE, Side.NO_TESTS):
            return Outcome.NO_EVIDENCE, "the parent run shows nothing about this criterion — no evidence is never proof"
        if candidate is Side.GREEN:
            return Outcome.SATISFIED, "red at the parent, green at the candidate"
        if candidate is Side.NO_EVIDENCE:
            return Outcome.NO_EVIDENCE, "the candidate run shows nothing about this criterion"
        return Outcome.DEVELOPER_QUALITY_BLOCK, f"still {candidate.value.lower()} at the candidate"
    # PRESERVE_REQUIRED and NEGATIVE_INVARIANT share the transition; only what a missing precondition means differs.
    if parent in (Side.NO_EVIDENCE, Side.NO_TESTS):
        return Outcome.NO_EVIDENCE, "the parent run shows nothing about this criterion — no evidence is never proof"
    if parent in (Side.RED, Side.MIXED):
        why = ("the behaviour this story must preserve is not present at its parent"
               if m is Mode.PRESERVE_REQUIRED else "the prohibition is already violated at this story's parent")
        return Outcome.PLAN_PRECONDITION_MISSING, f"{why} ({parent.value.lower()}) — a plan defect, not this story's"
    if candidate is Side.GREEN:
        return Outcome.SATISFIED, "green at the parent and still green at the candidate"
    if candidate is Side.NO_EVIDENCE:
        return Outcome.NO_EVIDENCE, "the candidate run shows nothing about this criterion"
    return Outcome.DEVELOPER_REGRESSION, ("this story broke behaviour it inherited" if m is Mode.PRESERVE_REQUIRED
                                          else "this story broke a prohibition that held at its parent")


def states_of(states: dict | None) -> list[str]:
    """The distinct SS-81 states behind one side, named — what the gate reports as "observed proof state"."""
    return sorted({p.value for p, _ in (states or {}).values()})


def row(ac_id: str, mode, requirement: str, parent: Side, candidate: Side,
        parent_states: list[str] | None = None, candidate_states: list[str] | None = None,
        tests: list[str] | None = None) -> dict:
    """The structured line the gate reports for one criterion (owner section 11) — never 'tests green on first run'."""
    outcome, why = evaluate(mode, parent, candidate)
    m = mode.value if isinstance(mode, Mode) else mode
    return {"ac_id": ac_id, "requirement": requirement, "proof_mode": m,
            "parent": parent.value, "candidate": candidate.value,
            "parent_states": list(parent_states or []), "candidate_states": list(candidate_states or []),
            "tests": sorted(tests or []),
            "expected_transition": EXPECTED.get(Mode(m), "") if m in Mode.__members__ else "",
            "actual_transition": f"{parent.value} -> {candidate.value}",
            "outcome": outcome.value, "owner": (OWNER_OF[outcome].value if OWNER_OF[outcome] else None), "why": why}


def judge(obligations: dict, parent_states: dict, candidate_states: dict, codes: list[str]) -> list[dict]:
    """One row per criterion code. `obligations`: AC code -> {'proof_mode', 'requirement'} (planning data).
    `parent_states` / `candidate_states`: AC code -> {test id: (Proof, why)} (one proof engine, both sides)."""
    out = []
    for code in codes:
        decl = obligations.get(code) or {}
        out.append(row(code, decl.get("proof_mode"), str(decl.get("requirement") or ""),
                       side(parent_states.get(code)), side(candidate_states.get(code)),
                       states_of(parent_states.get(code)), states_of(candidate_states.get(code)),
                       list(candidate_states.get(code) or parent_states.get(code) or {})))
    return out


def blocking(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["outcome"] != Outcome.SATISFIED.value]


def owners(rows: list[dict]) -> set[str]:
    return {r["owner"] for r in rows if r["owner"]}


def story_contribution(obligations: dict, codes: list[str], story_type: str = NORMAL) -> tuple[bool, str]:
    """Owner section 8: a normal implementation story must carry at least one CHANGE_REQUIRED obligation. Checked
    from planning data alone, so it can run before the first developer call."""
    declared = [(obligations.get(c) or {}).get("proof_mode") for c in codes]
    unknown = [c for c, m in zip(codes, declared, strict=True) if m not in Mode.__members__]
    if unknown:
        return False, (f"{len(unknown)} of {len(codes)} criteria declare no valid proof obligation: "
                       + ", ".join(unknown[:3]) + ("…" if len(unknown) > 3 else ""))
    if story_type == VERIFICATION_ONLY:
        return True, "verification-only story: no new behaviour is expected of it"
    n = sum(1 for m in declared if m == Mode.CHANGE_REQUIRED.value)
    if n:
        return True, f"{n} of {len(codes)} criteria are CHANGE_REQUIRED"
    return False, ("every criterion is already satisfied at this story's entry (no CHANGE_REQUIRED obligation) — the "
                   f"story contributes no behaviour: correct the plan or declare it {VERIFICATION_ONLY}")
