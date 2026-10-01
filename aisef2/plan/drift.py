"""RFC §14, §29 — PRE_SATISFIED and PLAN_DRIFT: the plan claim moves, the product claim does not.

* **PRE_SATISFIED** (an INTRODUCE obligation whose ContractSatisfaction at the actual parent is SATISFIED) is recorded,
  emits `story/plan-drift`, and consumes **no developer budget**: it never enters the developer's work, and nothing
  asks for correct code to be made wrong — its candidate expectation stays SATISFIED.
* **Remaining work.** If other obligations are READY the story continues on those. If every obligation is PRE_SATISFIED
  the story ends **STORY_ALREADY_SATISFIED**: the developer call is skipped and every obligation is still verified,
  independently, at the candidate (§16).
* **Attribution through the dependency DAG** (`attribute`). The introducer is the completed story, upstream of this
  one in the story DAG, whose own parent did not satisfy the spec and whose merged revision did. The measurements are
  inputs (the journal's, or a harness re-measurement); this module runs no probe. If no upstream story flips the
  spec, or more than one does, the introducer cannot be identified: **UNATTRIBUTED**, with the candidates kept as
  data. (RFC §36 leaves attribution tie-breaks to the implementation; this one never blames a story arbitrarily.)
* **Plan quality** (§29): three projections over the drift records and admissions, and a verdict that is
  NOT_CLAIMED unless a threshold was preregistered. It is never folded into delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from aisef2.arch.enums import ContractSatisfaction, EventType, StoryAdmissionDisposition
from aisef2.errors import InvariantError
from aisef2.plan.obligation import Plan, PlanQualityPolicy
from aisef2.plan.static_admission import depends_on_story, story_graph
from aisef2.plan.story_admission import MemorySink, StoryAdmissionResult

UNATTRIBUTED = "UNATTRIBUTED"
D = StoryAdmissionDisposition


@dataclass(frozen=True, slots=True)
class CompletedStory:
    """A completed story and what the spec measured on either side of it (None: not measured there)."""
    story_id: str
    at_parent: ContractSatisfaction | None
    at_merge: ContractSatisfaction | None


@dataclass(frozen=True, slots=True)
class PlanDrift:
    story_id: str
    criterion_id: str
    spec_id: str
    attributed_to: str
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoryContinuation:
    """What a story does after admission: its developer work, and what must be verified at the candidate."""
    story_id: str
    already_satisfied: bool
    developer_work: tuple[str, ...]
    verify_at_candidate: tuple[str, ...]
    drift: tuple[PlanDrift, ...]


def attribute(plan: Plan, story_id: str, spec_id: str, completed: Iterable[CompletedStory]) -> tuple[str, tuple[str, ...]]:
    """(introducer or UNATTRIBUTED, candidates): the upstream completed stories that flipped the spec to SATISFIED."""
    graph = story_graph(plan)
    candidates = tuple(sorted(
        c.story_id for c in completed
        if depends_on_story(graph, story_id, c.story_id)
        and c.at_parent is not None and c.at_parent is not ContractSatisfaction.SATISFIED
        and c.at_merge is ContractSatisfaction.SATISFIED))
    return (candidates[0] if len(candidates) == 1 else UNATTRIBUTED), candidates


def continue_story(plan: Plan, admission: StoryAdmissionResult, completed: Mapping[str, Iterable[CompletedStory]],
                   sink: MemorySink) -> StoryContinuation:
    """§14 after an admitted story: record and attribute each PRE_SATISFIED, and say what the developer and the
    candidate verification must cover. `completed` maps a spec id to its measurements across completed stories."""
    if not admission.admitted:
        raise InvariantError(f"story {admission.story_id} was not admitted; it does not continue")
    by_criterion = {o.criterion_id: o for o in plan.obligations if o.story_id == admission.story_id}
    drift = []
    for a in admission.obligations:
        if a.decision.disposition is D.PRE_SATISFIED:
            spec_id = by_criterion[a.criterion_id].product_proof_spec_id
            to, candidates = attribute(plan, admission.story_id, spec_id, completed.get(spec_id, ()))
            d = PlanDrift(admission.story_id, a.criterion_id, spec_id, to, candidates)
            sink.emit(EventType.STORY_PLAN_DRIFT, {"story_id": d.story_id, "criterion_id": d.criterion_id,
                                                   "spec_id": d.spec_id, "attributed_to": d.attributed_to,
                                                   "candidates": list(d.candidates)})
            drift.append(d)
    work = tuple(a.criterion_id for a in admission.obligations if a.decision.disposition is D.READY)
    return StoryContinuation(admission.story_id, not work, work,
                             tuple(a.criterion_id for a in admission.obligations), tuple(drift))


def budget_problems(events) -> list[str]:
    """§14: developer budget is charged by `provider/request` events; each may charge only criteria its story's
    `story/admitted` recorded READY — never a PRE_SATISFIED one (nor a blocked one)."""
    admitted: dict[str, Mapping[str, str]] = {}
    out = []
    for n, (event_type, data) in enumerate(events):
        if event_type is EventType.STORY_ADMITTED:
            admitted[data["story_id"]] = data["dispositions"]
        elif event_type is EventType.PROVIDER_REQUEST:
            dispositions = admitted.get(data["story_id"], {})
            out += [f"event {n}: provider/request charges {c}, which is {dispositions.get(c, 'not admitted')}"
                    for c in data.get("criteria", ()) if dispositions.get(c) != D.READY.value]
    return out


@dataclass(frozen=True, slots=True)
class PlanQuality:
    pre_satisfied_introduce_ratio: float | None
    fully_pre_satisfied_stories: int
    unattributed_plan_drift: int
    verdict: str


def plan_quality(policy: PlanQualityPolicy, admissions: Sequence[StoryAdmissionResult], plan: Plan,
                 drift: Sequence[PlanDrift]) -> PlanQuality:
    """§29: the three metrics and a separate plan-quality verdict — NOT_CLAIMED without a preregistered threshold."""
    role = {(o.story_id, o.criterion_id): o.role.value for o in plan.obligations}
    introduce = [a.decision.disposition for s in admissions for a in s.obligations
                 if role[(s.story_id, a.criterion_id)] == "INTRODUCE"]
    ratio = sum(d is D.PRE_SATISFIED for d in introduce) / len(introduce) if introduce else None
    full = sum(1 for s in admissions if s.obligations and all(a.decision.disposition is D.PRE_SATISFIED
                                                              for a in s.obligations))
    unattributed = sum(1 for d in drift if d.attributed_to == UNATTRIBUTED)
    limits = [(ratio, policy.max_pre_satisfied_introduce_ratio), (full, policy.max_fully_pre_satisfied_stories),
              (unattributed, policy.max_unattributed_plan_drift)]
    registered = [(value, limit) for value, limit in limits if limit is not None]
    if not registered:
        verdict = "NOT_CLAIMED"
    else:
        verdict = "PASS" if all(value is None or value <= limit for value, limit in registered) else "FAIL"
    return PlanQuality(ratio, full, unattributed, verdict)
