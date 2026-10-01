"""Merge and post-merge proof (RFC §26, WP-6.2). The merger's typed outcome decides: a conflict is MERGE_CONFLICT,
owner INTEGRATION, never DEVELOPER, never read from text. After a merge the story's obligations and every PRESERVE
obligation of a committed story are re-proved at the merged revision, by the same two-party proof; a regression is
INTEGRATION and the merge is rolled back."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import MeasurementPoint, ObligationRole
from aisef2.control.owner import Classification, FailureCode, classify, flatten
from aisef2.orchestrate import gate
from aisef2.orchestrate.adapters import Merge, MergeOutcome, Merger
from aisef2.orchestrate.proof import Party, Proof, prove


@dataclass(frozen=True, slots=True)
class Merged:
    merge: Merge | None
    check: int
    failure: Classification | None


def merge(run, story_id: str, merger: Merger, candidate: str) -> Merged:
    try:
        outcome = merger.merge(candidate)
    except Exception as e:  # a merger that broke: flattened, never interpreted (§22)
        code, _original = flatten(e)
        check = gate.check(run, story_id, "merge", False, f"the merger raised {type(e).__name__}")
        return Merged(None, check, classify(code))
    conflict = outcome.outcome is MergeOutcome.CONFLICT
    check = gate.check(run, story_id, "merge", not conflict,
                       f"conflicts in {list(outcome.conflicts)}" if conflict else f"merged at {outcome.revision}")
    return Merged(outcome, check, classify(FailureCode.MERGE_CONFLICT) if conflict else None)


def affected_preserve(plan, story_id: str, committed: frozenset[str]) -> Mapping[str, tuple[str, str]]:
    """criterion id -> (story, spec) of every PRESERVE obligation of a committed story the merge could affect."""
    return {o.criterion_id: (o.story_id, o.product_proof_spec_id) for o in plan.obligations
            if o.role is ObligationRole.PRESERVE and o.story_id in committed and o.story_id != story_id}


def reprove(run, story_id: str, plan, specs, *, merged: str, implementer: Party, verifier: Party,
            implementer_root: str, verifier_root: str, env, committed: frozenset[str]) -> tuple[list[Proof], list[int]]:
    """Every obligation the merge could affect, proved again at the merged revision; the gate/check rows it wrote."""
    proofs, checks = [], []
    affected = affected_preserve(plan, story_id, committed)
    mine = [(o.criterion_id, o.product_proof_spec_id, o.role) for o in plan.obligations if o.story_id == story_id]
    others = [(o.criterion_id, o.product_proof_spec_id, o.role) for o in plan.obligations if o.criterion_id in affected]
    for cid, spec_id, role in mine + others:   # each with the role the plan gives it; the point is POST_MERGE
        p = prove(run, story_id, cid, specs[spec_id], role, implementer=implementer, verifier=verifier,
                  candidate=merged, implementer_root=implementer_root, verifier_root=verifier_root, env=env,
                  point=MeasurementPoint.POST_MERGE)
        proofs.append(p)
        checks.append(gate.check(run, story_id, f"post-merge:{cid}", p.failure is None,
                                 "re-proved at the merged revision" if p.failure is None else p.failure.code.value))
        if p.failure is not None:
            break
    return proofs, checks
