"""The reviewer (RFC §25, V2-005 §9): a provider request charged to the REVIEW budget, its result, and one `gate/check`
row per finding. A finding blocks — REVIEW_FINDING, owner REVIEW — only with corroborated authority; a model review
alone is advisory. An outage keeps owner PROVIDER; a capability that cannot run is CAPABILITY_UNRUNNABLE."""

from __future__ import annotations

from dataclasses import dataclass

from aisef2.arch.enums import EventType as T, Owner
from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.journal.format2 import OperationOutcome as O
from aisef2.orchestrate import gate
from aisef2.orchestrate.adapters import CapabilityUnrunnable, ProviderOutage, ReadOnlyScope, Reviewer


@dataclass(frozen=True, slots=True)
class Review:
    request_seq: int
    result_seq: int
    checks: tuple[int, ...]
    failure: Classification | None


def _result(run, story_id: str, request_seq: int, outcome: O, detail: str) -> int:
    return run.append(T.PROVIDER_RESULT, {"story_id": story_id, "outcome": outcome.value, "synthetic": False,
                                          "detail": detail}, source_seqs=(request_seq,)).seq


def review(run, story_id: str, scope: ReadOnlyScope, reviewer: Reviewer, criteria: tuple[str, ...]) -> Review:
    request = run.append(T.PROVIDER_REQUEST, {"story_id": story_id, "criteria": list(criteria),
                                              "budget_owner": Owner.REVIEW.value}).seq
    try:
        reviewed = reviewer.review(scope, criteria)
    except ProviderOutage as e:
        seq = _result(run, story_id, request, O.FAILED, f"reviewer outage: {e}")
        return Review(request, seq, (), classify(FailureCode.PROVIDER_UNAVAILABLE))
    except CapabilityUnrunnable as e:
        seq = _result(run, story_id, request, O.FAILED, f"reviewer cannot run: {e}")
        return Review(request, seq, (), classify(FailureCode.CAPABILITY_UNRUNNABLE))
    seq = _result(run, story_id, request, reviewed.outcome, reviewed.detail)
    if reviewed.outcome is not O.COMPLETED:
        return Review(request, seq, (), classify(FailureCode.PROVIDER_UNAVAILABLE))
    checks = [gate.check(run, story_id, f"review:{f.id}", not f.blocks,
                         ("blocking, corroborated by " + ", ".join(f.corroborated_by)) if f.blocks
                         else "advisory: a model review alone is never the sole blocking authority (D-002)" if f.blocking
                         else "informational") for f in reviewed.findings]
    if not checks:
        checks.append(gate.check(run, story_id, "review", True, "reviewed: no finding"))
    failure = classify(FailureCode.REVIEW_FINDING) if any(f.blocks for f in reviewed.findings) else None
    return Review(request, seq, tuple(checks), failure)
