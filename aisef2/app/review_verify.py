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
the bytes that run, or cannot run. What a confirmation
does not prove: that the reviewer read the requirement right — the clause is cited so a person can judge the triage.

Policy (settings `review`, `fix-loop` by default): a CONFIRMED finding at or above `min_severity` blocks
(REVIEW_FINDING, owner REVIEW, retryable through the taxonomy's REVIEW limit: the bounded fix loop), its statement and
the probe's observation fed back to the developer on the retry; everything else is triage — journaled, never blocking.
`advisory` keeps 2.0.0's behaviour: nothing blocks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import BehaviorVerdict, Enforcement, Polarity, SubjectAbsence, SubjectKind
from aisef2.probe import catalog
from aisef2.probe.calibration import calibration_for, executing
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe
from aisef2.product.compiler import ProbeRef
from aisef2.product.contract import BehaviorContract, ContractError, Subject
from aisef2.product.outcome import Executed

CONFIRMED, NOT_REPRODUCED, UNVERIFIABLE = "CONFIRMED", "NOT_REPRODUCED", "UNVERIFIABLE"
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
    """The finding's reproducer as an (unapproved, never compiled into the plan) MUST_HOLD contract, or why not."""
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
        return BehaviorContract.create(id=f"REVIEW-{finding.get('id', 'finding')}", requirement_ids=(rid,),
                                       subject=Subject(SubjectKind(subject["kind"]), locator), stimulus=r["stimulus"],
                                       observable=r["observable"], polarity=Polarity.MUST_HOLD,
                                       subject_absence=SubjectAbsence.REQUIRES_SUBJECT,
                                       rationale=str(finding.get("summary", ""))[:500])
    except (ContractError, ValueError, TypeError) as e:
        return f"the reproducer is not a contract: {e}"


def verify(finding: Mapping, *, requirements: Mapping, product_roots, root: str, revision: str,
           timeout_s: float, interpreter: str) -> Verification:
    """Run the finding's reproducer with the active probe of its subject kind on the checkout `root` at `revision`."""
    from aisef2.app.bundle_cli import _mint      # compile_spec's mapping, without the approval gate (ids only)
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


def blocks(v: Verification, finding: Mapping, policy: str, min_severity: str) -> bool:
    return (policy == "fix-loop" and v.status == CONFIRMED
            and SEVERITIES.index(severity_of(finding)) >= SEVERITIES.index(min_severity))


def detail(finding: Mapping, v: Verification) -> str:
    """The journaled statement of a finding (the gate row the developer's retry prompt is built from): bounded text."""
    r = finding.get("reproducer") if isinstance(finding.get("reproducer"), Mapping) else {}
    return json.dumps({"finding": str(finding.get("id"))[:80], "severity": severity_of(finding),
                       "summary": str(finding.get("summary", ""))[:400], "clause": r.get("clause"),
                       "verification": v.status, "why": v.reason[:300],
                       "reproducer": {k: r.get(k) for k in ("subject", "stimulus", "observable")} if r else None},
                      ensure_ascii=False, sort_keys=True)[:1500]
