"""Candidate proof and independent verification (RFC §16, WP-6.2). The implementer's probe and the verifier's probe
are the same spec on the same candidate, run in two checkouts the story owns, each inside a process range the story's
scope holds while it runs. Both records are journaled; `proof/verified` cites them. Instrument identity is compared
on the sealed records' comparability digest (probe id, probe digest, enforcement, semantic hash): a mismatch is
PROBE_MISMATCH, a disagreement VERIFIER_DISAGREEMENT — both INTEGRATION, never arbitrated, never re-run to agreement.
The product verdict is read through the binding (`bound_result`) and routed on contract satisfaction by measurement
point (§10.3); no raw verdict is named here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from aisef2.arch.enums import ContractSatisfaction, EventType as T, MeasurementPoint, ObligationRole, ProbeExecutionStatus
from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.control.routing import route
from aisef2.errors import InvariantError
from aisef2.journal.event import Event
from aisef2.journal.format2 import ResourceKind
from aisef2.journal.format3 import verified_payload
from aisef2.probe.protocol import ExecutionEnv, Probe, ProbeRecord, RevisionRef, bound_result, run_probe
from aisef2.product.contract import plain
from aisef2.product.outcome import contract_satisfaction
from aisef2.product.spec import ProductProofSpec
from aisef2.runtime.story_scope import StoryScope


@dataclass(frozen=True, slots=True)
class Proof:
    criterion_id: str
    spec_id: str
    implementer_seq: int
    verifier_seq: int
    verified_seq: int | None       # None when the two records could not become a proof (mismatch)
    agreement: bool
    satisfaction: ContractSatisfaction | None   # the bound implementer result's, when it executed and they agree
    failure: Classification | None


class Ranged:
    """A process range under a name of its own within the attempt: the journal admits a resource name once per attempt
    (§17.1), and a probe or a runner names its range after the spec or the story alone. Release goes through the
    range itself (a second release after the harness's own is a no-op)."""

    kind = ResourceKind.PROCESS_RANGE

    def __init__(self, process_range, name: str) -> None:
        self._range, self.name = process_range, name

    def release(self) -> None:
        self._range.release()


class Party:
    """One party's probe run: the probe evaluates in the party's own checkout; its process range is acquired into the
    story's scope when it starts and released when the probe returns (§17.1)."""

    def __init__(self, scope: StoryScope, make_probe: Callable[[Callable], Probe], label: str) -> None:
        self.scope, self._make, self.label = scope, make_probe, label

    def run(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv, *, under: str) -> ProbeRecord:
        held: list = []

        def on_range(process_range) -> None:
            held.append(self.scope.acquire(Ranged(process_range, f"{process_range.name} [{under} {self.label}]")))

        try:
            return run_probe(self._make(on_range), spec, at, env)
        finally:
            for r in reversed(held):
                if self.scope.held[-1:] == (r.name,):   # only the top of the stack is released early (§17.1)
                    self.scope.release(r)


def prove(run, story_id: str, criterion_id: str, spec: ProductProofSpec, role: ObligationRole | None, *,
          implementer: Party, verifier: Party, candidate: str, implementer_root: str, verifier_root: str,
          env: ExecutionEnv, point: MeasurementPoint) -> Proof:
    """Two independent records of `spec` at `candidate`, journaled and bound into one proof or one typed failure."""
    if point is MeasurementPoint.PARENT:
        raise InvariantError("the parent is measured by StoryAdmission, never by a proof (§13)")
    under = f"{criterion_id}/{point.value}"
    a = implementer.run(spec, RevisionRef(candidate, implementer_root), env, under=under)
    seq_a = run.append(T.PROBE_EVALUATED, {"story_id": story_id, "criterion_id": criterion_id, "record": plain(a)}).seq
    b = verifier.run(spec, RevisionRef(candidate, verifier_root), env, under=under)
    seq_b = run.append(T.PROBE_EVALUATED, {"story_id": story_id, "criterion_id": criterion_id, "record": plain(b)}).seq
    if a.comparability != b.comparability:
        return Proof(criterion_id, spec.id, seq_a, seq_b, None, False, None, classify(FailureCode.PROBE_MISMATCH))
    payload = verified_payload(story_id=story_id, criterion_id=criterion_id, spec_id=spec.id,
                               semantic_hash=spec.semantic_hash, candidate=candidate, implementer=plain(a),
                               verifier=plain(b))
    verified: Event = run.append(T.PROOF_VERIFIED, payload, source_seqs=(seq_a, seq_b))
    if not payload["agreement"]:
        return Proof(criterion_id, spec.id, seq_a, seq_b, verified.seq, False, None,
                     classify(FailureCode.VERIFIER_DISAGREEMENT))
    bound = bound_result(a, spec=spec, revision=candidate, enforcement=a.enforcement)
    routed = route(bound, spec, point, role)
    # at the candidate and after the merge nothing but the contract decides (§10.3): satisfaction is defined for
    # every executed probe, and only for one
    satisfaction = contract_satisfaction(bound, spec) if bound.status is ProbeExecutionStatus.EXECUTED else None
    return Proof(criterion_id, spec.id, seq_a, seq_b, verified.seq, True, satisfaction, routed.failure)


def obligations_of(plan, story_id: str) -> Mapping[str, tuple[str, ObligationRole]]:
    """criterion id -> (spec id, role) of a story's obligations, in plan order."""
    return {o.criterion_id: (o.product_proof_spec_id, o.role) for o in plan.obligations if o.story_id == story_id}
