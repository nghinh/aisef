"""Review findings, verified (V2.1, proposal C; RFC §25, D-002: a model review alone never blocks).

A reviewer — the model reviewer, or Open Code Review (app/review_ocr.py) — only *finds*. A finding becomes evidence
here, and nowhere else: it may carry a **reproducer**, the behaviour it says the requirement demands, written in a
probe's own grammar and citing the requirement clause —

    {"clause": "R-9/3", "subject": {"kind": "cli_invocation", "locator": "ledgerlock:__main__"},
     "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"]}, "observable": {"exit_code": 3, "within_s": 10}}

— and AISEF runs that observation with its own trusted, calibrated probe on the candidate. The finding is CONFIRMED
when the probe executes and REFUTES the stated behaviour (the candidate does not do what the finding says the
requirement demands): the probe is the corroborating authority D-002 asks for. NOT_REPRODUCED when it is SATISFIED;
UNVERIFIABLE when there is no reproducer, the clause names no requirement of the project, the subject is outside the
product, the probe cannot give the observation a meaning (refused, not degraded), is not calibrated for that class at
the bytes that run, or cannot run.

**Anchoring: whose expectation it is.** A confirmation proves the candidate does not do what the finding states —
never that the requirement demands it. A reproducible finding with a wrong expectation must not block by itself, so
blocking also needs the expectation to be the cited clause's *approved* outcome (`anchor`), decided from the bundle's
approved contracts and sealed clause facts only — never from the reviewer's text:

* ANCHORED — approved contracts of the cited clause observe the same subject, observe every expected key, and all
  expect exactly the finding's values; that this is the clause's constant outcome (not one input's result) is shown by
  at least two such contracts with distinct stimuli, or by one whose clause text states every expected value and no
  other number. Example: LedgerLock R-9/3 ("exit 3 on an I/O error", two approved contracts on two stimuli).
* CONTRADICTS_APPROVED — an approved contract of the requirement on the same subject and the same stimulus expects
  other values, or the clause's shown constant outcome is not the finding's: a false finding.
* UNANCHORED — no approved contract declares the clause, none observes this subject or these keys, the clause's
  contracts expect different values (the outcome depends on the input: `add(2, 3)` returning 5 says nothing about
  `add(2, 2)`), or one contract with a clause text that does not state the value.

The known limit, measured in tests rather than hidden: anchoring decides that the expected value is the clause's
approved outcome; it cannot decide that a NEW stimulus falls under the clause's condition (a reviewer claiming a
corrupt file is an I/O error). A stimulus an approved contract decides differently is caught (CONTRADICTS_APPROVED).

Policy (settings `review`): under `fix-loop` a CONFIRMED and ANCHORED finding at or above `min_severity` blocks
(REVIEW_FINDING, owner REVIEW, retryable through the taxonomy's REVIEW limit: the bounded fix loop), its statement and
the probe's observation fed back to the developer on the retry; everything else is triage — journaled with its
verification and anchor, never blocking. `advisory` keeps 2.0.0's behaviour: nothing blocks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import BehaviorVerdict, Enforcement, Polarity, SubjectAbsence, SubjectKind
from aisef2.probe import catalog
from aisef2.probe.calibration import calibration_for, executing
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe
from aisef2.product.compiler import ProbeRef
from aisef2.product.contract import BehaviorContract, ContractError, Subject, plain
from aisef2.product.outcome import Executed

CONFIRMED, NOT_REPRODUCED, UNVERIFIABLE = "CONFIRMED", "NOT_REPRODUCED", "UNVERIFIABLE"
ANCHORED, UNANCHORED, CONTRADICTS_APPROVED = "ANCHORED", "UNANCHORED", "CONTRADICTS_APPROVED"
SEVERITIES = ("low", "medium", "high", "critical")
POLICIES = ("fix-loop", "advisory")
REPRODUCER_KEYS = ("clause", "subject", "stimulus", "observable")


@dataclass(frozen=True, slots=True)
class Verification:
    status: str
    reason: str
    probe: str | None = None
    observed: str | None = None     # the probe's verdict on the stated behaviour, when it executed

    def evidence(self) -> str:
        return f"probe:{self.probe}:{self.observed}" if self.status == CONFIRMED else ""


def severity_of(finding: Mapping) -> str:
    """The finding's declared severity, `low` when it declares none the scale knows (never raised by default)."""
    s = str(finding.get("severity", "")).lower()
    return s if s in SEVERITIES else "low"


def reproducer_contract(finding: Mapping, requirements: Mapping[str, object], product_roots) -> BehaviorContract | str:
    """The finding's reproducer as an (unapproved, never compiled into the plan) MUST_HOLD contract, or why not.

    The finding's prose — its id and the first 500 characters of its summary — is the contract's id and rationale, which
    no control path reads, so it never decides the verdict. The contract's hash is over UTF-8, which has no form for a
    lone surrogate (`json.loads` yields one from a model's "\\ud800"): each is written as its own escape, `\\ud800`; text
    that encodes is hashed as it is. A surrogate in the reproducer itself (stimulus, observable, locator) is not prose:
    the reproducer is refused, naming why."""
    r = finding.get("reproducer")
    if not isinstance(r, Mapping):
        return "no reproducer: the finding states no observable behaviour"
    if sorted(r) != sorted(REPRODUCER_KEYS):
        return f"a reproducer holds exactly {list(REPRODUCER_KEYS)}"
    clause = r["clause"]
    rid = clause.split("/")[0] if isinstance(clause, str) else None
    if rid not in requirements:
        return f"the clause {clause!r} names no requirement of the project"
    subject = r["subject"]
    if not isinstance(subject, Mapping) or sorted(subject) != ["kind", "locator"]:
        return "a reproducer's subject is {kind, locator}"
    locator = str(subject["locator"])
    top = locator.removeprefix("path:").split("/")[0].split(":")[0].split(".")[0]
    if top not in product_roots:
        return f"the subject {locator!r} is not in the product ({sorted(product_roots)})"
    try:
        cid, why = (t.encode("utf-8", "backslashreplace").decode("utf-8")
                    for t in (f"REVIEW-{finding.get('id', 'finding')}", str(finding.get("summary", ""))[:500]))
        return BehaviorContract.create(id=cid, requirement_ids=(rid,),
                                       subject=Subject(SubjectKind(subject["kind"]), locator), stimulus=r["stimulus"],
                                       observable=r["observable"], polarity=Polarity.MUST_HOLD,
                                       subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale=why)
    except (ContractError, ValueError, TypeError) as e:
        return f"the reproducer is not a contract: {e}"


def verify(finding: Mapping, *, requirements: Mapping, product_roots, root: str, revision: str,
           timeout_s: float, interpreter: str) -> Verification:
    """Run the finding's reproducer with the active probe of its subject kind on the checkout `root` at `revision`."""
    from aisef2.app.bundle_cli import _mint      # compile_spec's mapping, without the approval gate: never approved
    c = reproducer_contract(finding, requirements, product_roots)
    if isinstance(c, str):
        return Verification(UNVERIFIABLE, c)
    entry = catalog.active().get(c.subject.kind)
    if entry is None:
        return Verification(UNVERIFIABLE, f"no active probe observes {c.subject.kind.value}")
    spec = _mint(c, ProbeRef(entry.probe_id, entry.probe_digest))
    cls = catalog.registry().observation_class(spec.probe_id, spec.probe_digest, spec)
    if cls is None:
        return Verification(UNVERIFIABLE, f"{entry.probe_id} gives the reproducer's observation no meaning (refused)",
                            entry.probe_id)
    from aisef2.app.run import calibrations
    if calibration_for(calibrations(), entry.probe_id, executing(entry.factory), cls) is None:
        return Verification(UNVERIFIABLE, f"{entry.probe_id} is not calibrated for {cls!r} at the bytes that run: an "
                            "unqualified observation corroborates nothing", entry.probe_id)
    probe = entry.factory()
    result = bound_result(run_probe(probe, spec, RevisionRef(revision, root), ExecutionEnv(interpreter, timeout_s,
                                                                                           Enforcement.PARTIAL)),
                          spec=spec, revision=revision, enforcement=probe.enforcement())     # PROBE-BIND-1
    if not isinstance(result, Executed):
        return Verification(UNVERIFIABLE, f"the probe did not execute the reproducer: {result}"[:300], entry.probe_id)
    v = result.behavior_verdict
    if v is BehaviorVerdict.REFUTED:
        return Verification(CONFIRMED, f"{entry.probe_id} refutes the behaviour {c.requirement_ids[0]} is said to demand",
                            entry.probe_id, v.value)
    return Verification(NOT_REPRODUCED, f"{entry.probe_id} observes the stated behaviour: the finding does not reproduce",
                        entry.probe_id, v.value)


@dataclass(frozen=True, slots=True)
class Anchor:
    status: str
    reason: str
    contracts: tuple[str, ...] = ()


def _canon(value) -> str:
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _stimulus(value) -> str:
    """A stimulus's identity for comparison: its keys with an empty value (None, {}, [], "") are the grammar's default."""
    return _canon({k: v for k, v in plain(value).items() if v not in (None, {}, [], "")})


def _scalars(value) -> list:
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in _scalars(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _scalars(v)]
    return [value]


_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")


def _states(text: str, values: Mapping) -> bool:
    """Whether a clause text states every expected value literally and no other number (a boolean or a null cannot be
    stated): the sealed text, never the reviewer's."""
    scalars = _scalars(values)
    if not scalars or any(isinstance(s, bool) or s is None for s in scalars):
        return False
    numbers = {float(n) for n in _NUMBER.findall(text)}
    wanted = {float(s) for s in scalars if isinstance(s, (int, float))}
    return numbers == wanted and all(s in text for s in scalars if isinstance(s, str))


def _approved_by_clause(project) -> dict[str, list[tuple[BehaviorContract, Mapping]]]:
    """Clause label -> (approved contract, criterion facts) of the plan's criteria. A label is the facts' clause, and
    also `<requirement>/<clause>` (the form the reviewer is asked to cite)."""
    approved = {(a.contract_id, a.contract_hash) for a in project.approvals}
    out: dict[str, list] = {}
    for o in project.plan.obligations:
        facts = project.facts.get(o.criterion_id) or {}
        spec = project.specs.get(o.product_proof_spec_id)
        c = project.contracts.get(spec.contract_id) if spec is not None else None
        if c is None or (c.id, c.contract_hash) not in approved:
            continue
        for label in {str(facts.get("clause")), f"{facts.get('requirement')}/{facts.get('clause')}"}:
            if all((c.id != d.id for d, _ in out.get(label, []))):
                out.setdefault(label, []).append((c, facts))
    return out


def anchor(finding: Mapping, project) -> Anchor:
    """Whether the finding's expected behaviour is the cited clause's approved outcome (module docstring)."""
    c = reproducer_contract(finding, project.requirements, project.product_roots)
    if isinstance(c, str):
        return Anchor(UNANCHORED, c)
    clause = str(finding["reproducer"]["clause"])
    rid = c.requirement_ids[0]
    subject = (c.subject.kind, c.subject.locator)
    keys = sorted(k for k in c.observable if k != "within_s")
    expected = {k: plain(c.observable[k]) for k in keys}
    approved = {d.id: d for group in _approved_by_clause(project).values() for d, _ in group}
    for d in approved.values():     # the same stimulus, decided otherwise by an approved contract: a false finding
        if rid in d.requirement_ids and (d.subject.kind, d.subject.locator) == subject \
                and _stimulus(d.stimulus) == _stimulus(c.stimulus) and {k: plain(d.observable.get(k)) for k in keys} != expected:
            return Anchor(CONTRADICTS_APPROVED, f"approved contract {d.id} decides this stimulus otherwise: "
                                                f"{_canon({k: d.observable.get(k) for k in keys})[:200]}", (d.id,))
    group = _approved_by_clause(project).get(clause, [])
    if not group:
        return Anchor(UNANCHORED, f"no approved contract of the bundle declares clause {clause!r}")
    same = [(d, f) for d, f in group if (d.subject.kind, d.subject.locator) == subject]
    if not same:
        return Anchor(UNANCHORED, f"no approved contract of clause {clause} observes {c.subject.locator}")
    if not keys or not all(k in d.observable for d, _ in same for k in keys):
        return Anchor(UNANCHORED, f"the approved contracts of clause {clause} do not observe {keys}")
    outcomes = {_canon({k: d.observable[k] for k in keys}) for d, _ in same}
    ids = tuple(sorted(d.id for d, _ in same))
    if len(outcomes) > 1:
        return Anchor(UNANCHORED, f"the approved contracts of clause {clause} expect different values for different "
                                  "stimuli: its outcome depends on the input", ids)
    constant = {k: plain(same[0][0].observable[k]) for k in keys}
    shown = len({_stimulus(d.stimulus) for d, _ in same}) >= 2 or all(_states(str(f.get("clause_text", "")), constant)
                                                                    for _, f in same)
    if not shown:
        return Anchor(UNANCHORED, f"one approved contract of clause {clause} does not show its outcome is the clause's "
                                  "constant (its clause text does not state the value)", ids)
    if constant != expected:
        return Anchor(CONTRADICTS_APPROVED, f"clause {clause}'s approved outcome is {_canon(constant)[:200]}", ids)
    return Anchor(ANCHORED, f"clause {clause}'s approved outcome {_canon(constant)[:200]} ({', '.join(ids)})", ids)


def blocks(v: Verification, finding: Mapping, policy: str, min_severity: str, anchored: Anchor | None) -> bool:
    """Under `fix-loop`: CONFIRMED and ANCHORED at or above the severity floor. Nothing else ever blocks."""
    return (policy == "fix-loop" and v.status == CONFIRMED and anchored is not None and anchored.status == ANCHORED
            and SEVERITIES.index(severity_of(finding)) >= SEVERITIES.index(min_severity))


def detail(finding: Mapping, v: Verification, anchored: Anchor | None = None) -> str:
    """The journaled statement of a finding (the gate row the developer's retry prompt is built from): bounded text."""
    r = finding.get("reproducer") if isinstance(finding.get("reproducer"), Mapping) else {}
    return json.dumps({"finding": str(finding.get("id"))[:80], "severity": severity_of(finding),
                       "summary": str(finding.get("summary", ""))[:400], "clause": r.get("clause"),
                       "verification": v.status, "why": v.reason[:300],
                       **({"anchor": anchored.status, "anchor_why": anchored.reason[:300]} if anchored else {}),
                       "reproducer": {k: r.get(k) for k in ("subject", "stimulus", "observable")} if r else None},
                      ensure_ascii=False, sort_keys=True)[:1500]
