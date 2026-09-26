"""RFC §12 — StaticPlanAdmission: the engine (harness code) and the result (a project's plan-time record).

* **Engine and result are distinct types.** `StaticPlanAdmissionEngine` is harness code — its rules are checked in Q0
  and its behaviour qualified in Q1 on fixtures, never on a project. `StaticPlanAdmissionResult` is what a concrete
  project gets when it runs the engine at plan time, before plan freeze.
* **No probe runs and no future parent SHA is invented.** The engine reads committed objects only — the plan, the
  approved requirements, contracts and approvals, the committed spec derivation, the harness probe catalogue and the
  probe calibration records. The only revision it knows is the plan's baseline, and it never asks for another.
* **Nine checks** (§12), each a function below. Check 9 requires `ProbeCapabilityCalibration` only;
  `SpecFalsifiabilityEvidence` is not an input and cannot be (CAL-2).
* **A plan freezes only if admitted** (`require_admitted`), and admission is re-derived at freeze time, so a result
  cannot outlive an edit to the plan or its inputs.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass
from typing import Callable, Mapping

from aisef2.arch.enums import ObligationRole, SubjectKind
from aisef2.errors import InvariantError
from aisef2.plan.obligation import EXPECTED_AT_PARENT, Plan, PlanError, PlanObligation
from aisef2.probe.calibration import ProbeCapabilityCalibration, calibration_for
from aisef2.probe.protocol import Probe, ProbeRegistry
from aisef2.product.approval import ContractApproval, Requirement, require_approved
from aisef2.product.compiler import ProbeRef, compile_spec
from aisef2.product.contract import BehaviorContract, ContractError, content_of, digest
from aisef2.product.spec import ProductProofSpec

ENGINE_SOURCES = ("plan/static_admission.py", "plan/obligation.py")


def _engine_digest() -> str:
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for rel in ENGINE_SOURCES:
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionInputs:
    """Everything the engine may read. Committed objects only: no revision other than the plan's baseline. The
    catalogue holds any objects satisfying the frozen `Probe` protocol; what observation class a spec asks of a probe
    is the harness registry's (PROBE-META-1), never a probe base class's."""
    requirements: Mapping[str, Requirement]
    contracts: Mapping[str, BehaviorContract]
    approvals: tuple[ContractApproval, ...]
    specs: Mapping[str, ProductProofSpec]
    catalogue: Mapping[SubjectKind, Probe]
    calibrations: tuple[ProbeCapabilityCalibration, ...]
    registry: ProbeRegistry


@dataclass(frozen=True, slots=True)
class CheckResult:
    number: int
    name: str
    passed: bool
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StaticPlanAdmissionResult:
    plan_id: str
    engine_digest: str
    checks: tuple[CheckResult, ...]
    admitted: bool
    result_digest: str

    def __post_init__(self) -> None:
        if [c.number for c in self.checks] != list(range(1, len(CHECKS) + 1)):
            raise InvariantError("a result carries the nine checks, in order")
        if self.admitted is not all(c.passed for c in self.checks):
            raise InvariantError("admitted is true exactly when every check passed")
        if self.result_digest != digest(content_of(self, without="result_digest")):
            raise InvariantError("result_digest does not bind this result")


class PlanNotAdmitted(PlanError):
    """StaticPlanAdmission did not admit the plan; it cannot freeze."""


# --------------------------------------------------------------------------------------- the nine checks

def _spec_of(o: PlanObligation, inputs: AdmissionInputs) -> ProductProofSpec | None:
    return inputs.specs.get(o.product_proof_spec_id)


def _probes_by_id(inputs: AdmissionInputs) -> dict[str, Probe]:
    return {p.id: p for p in inputs.catalogue.values()}


def check_requirement_coverage(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """1. every approved Requirement maps to at least one BehaviorContract."""
    return [f"requirement {rid} maps to no BehaviorContract" for rid in sorted(inputs.requirements)
            if not any(rid in c.requirement_ids for c in inputs.contracts.values())]


def check_contract_spec_integrity(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """2. every contract compiles, and to exactly the committed spec (--check against the committed derivation)."""
    refs = {kind: ProbeRef(p.id, p.digest) for kind, p in inputs.catalogue.items()}
    out = []
    for cid in sorted(inputs.contracts):
        committed = [s for s in inputs.specs.values() if s.contract_id == cid]
        try:
            fresh = compile_spec(inputs.contracts[cid], requirements=inputs.requirements,
                                 approvals=inputs.approvals, probes=refs)
        except ContractError as e:
            out.append(f"contract {cid} does not compile: {e}")
            continue
        if [s.id for s in committed] != [fresh.id]:
            out.append(f"contract {cid}: committed specs {sorted(s.id for s in committed)} differ from its derivation "
                       f"{fresh.id}")
    return out


def check_ownership(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """3. every criterion has exactly one story; INTRODUCE ownership is unique per spec."""
    stories: dict[str, dict[str, None]] = {}
    introduce: dict[str, int] = {}
    for o in plan.obligations:
        stories.setdefault(o.criterion_id, {})[o.story_id] = None
        if o.role is ObligationRole.INTRODUCE:
            introduce[o.product_proof_spec_id] = introduce.get(o.product_proof_spec_id, 0) + 1
    return ([f"criterion {c} belongs to {len(s)} stories {sorted(s)}" for c, s in sorted(stories.items()) if len(s) != 1]
            + [f"spec {s} has {n} INTRODUCE owners" for s, n in sorted(introduce.items()) if n > 1])


def _cycle(graph: dict[str, dict[str, None]]) -> list[str] | None:
    """One cycle of `graph` (node -> ordered successors), or None if it is acyclic. Visits in sorted order, so the
    cycle reported does not depend on the order the plan listed its obligations in."""
    state: dict[str, int] = {}
    for start in sorted(graph):
        if state.get(start):
            continue
        stack, path = [(start, iter(sorted(graph.get(start, ()))))], [start]
        state[start] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                path.pop()
            elif state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            elif not state.get(nxt):
                state[nxt] = 1
                stack.append((nxt, iter(sorted(graph.get(nxt, ())))))
                path.append(nxt)


def check_dependency_dag(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """4. every depends_on resolves to a criterion of the plan, and the criterion graph is acyclic."""
    criteria = {o.criterion_id for o in plan.obligations}
    out = [f"criterion {o.criterion_id} depends on {d}, which does not resolve"
           for o in plan.obligations for d in o.depends_on if d not in criteria]
    graph: dict[str, dict[str, None]] = {}
    for o in plan.obligations:
        graph.setdefault(o.criterion_id, {}).update(dict.fromkeys(d for d in o.depends_on if d in criteria))
    cycle = _cycle(graph)
    return out + ([f"criterion dependencies form a cycle: {' -> '.join(cycle)}"] if cycle else [])


def story_graph(plan: Plan) -> dict[str, dict[str, None]]:
    """story -> the stories it depends on (in the order the plan names them), induced from criterion dependencies."""
    story_of = {o.criterion_id: o.story_id for o in plan.obligations}
    graph: dict[str, dict[str, None]] = {o.story_id: {} for o in plan.obligations}
    for o in plan.obligations:
        graph[o.story_id].update(dict.fromkeys(story_of[d] for d in o.depends_on
                                               if d in story_of and story_of[d] != o.story_id))
    return graph


def depends_on_story(graph: dict[str, dict[str, None]], later: str, earlier: str) -> bool:
    """True when `later` depends, directly or transitively, on `earlier`."""
    seen, todo = set(), [later]
    while todo:
        for s in graph.get(todo.pop(), ()):
            if s == earlier:
                return True
            if s not in seen:
                seen.add(s)
                todo.append(s)
    return False


def check_contradictions(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """5. no incompatible parent expectations for one spec in one story; no PRESERVE ordered before its INTRODUCE.
    A role/expectation pair with no §13 routing row is rejected here rather than given a meaning."""
    out = [f"criterion {o.criterion_id}: role {o.role.value} with expected {o.expected_parent.value} has no §13 "
           "routing row" for o in plan.obligations if EXPECTED_AT_PARENT.get(o.role) is not o.expected_parent]
    expected: dict[tuple[str, str], dict[str, None]] = {}
    for o in plan.obligations:
        expected.setdefault((o.story_id, o.product_proof_spec_id), {})[o.expected_parent.value] = None
    out += [f"story {st} asserts incompatible parent expectations {sorted(e)} for spec {sp}"
            for (st, sp), e in sorted(expected.items()) if len(e) > 1]
    graph = story_graph(plan)
    introducer = {o.product_proof_spec_id: o.story_id for o in plan.obligations if o.role is ObligationRole.INTRODUCE}
    out += [f"story {o.story_id} PRESERVEs spec {o.product_proof_spec_id} without being ordered after story "
            f"{introducer[o.product_proof_spec_id]}, which INTRODUCEs it"
            for o in plan.obligations if o.role is ObligationRole.PRESERVE
            and o.product_proof_spec_id in introducer and introducer[o.product_proof_spec_id] != o.story_id
            and not depends_on_story(graph, o.story_id, introducer[o.product_proof_spec_id])]
    return out


def check_proof_capability(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """6. every spec's probe_id resolves in the harness catalogue and its digest matches (scenario D, statically)."""
    probes = _probes_by_id(inputs)
    out = []
    for sid in sorted(dict.fromkeys(o.product_proof_spec_id for o in plan.obligations)):
        spec = inputs.specs.get(sid)
        if spec is None:
            continue
        probe = probes.get(spec.probe_id)
        if probe is None:
            out.append(f"spec {sid}: probe {spec.probe_id} does not resolve in the harness catalogue")
        elif probe.digest != spec.probe_digest:
            out.append(f"spec {sid}: bound to {spec.probe_id}@{spec.probe_digest[:12]}, the harness has "
                       f"@{probe.digest[:12]} (scenario D)")
    return out


def check_traceability(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """7. every criterion reaches a Requirement through an approved contract."""
    out = []
    for o in plan.obligations:
        spec = _spec_of(o, inputs)
        if spec is None:
            continue
        contract = inputs.contracts.get(spec.contract_id)
        if contract is None:
            out.append(f"criterion {o.criterion_id}: spec {spec.id} comes from no known contract")
            continue
        try:
            require_approved(contract, inputs.requirements, inputs.approvals)
        except ContractError as e:
            out.append(f"criterion {o.criterion_id}: contract {contract.id} is not approved: {e}")
    return out


def check_plan_structure(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """8. stories form an explicit DAG; no orphan obligation (every obligation's spec is in the committed derivation)."""
    out = [f"criterion {o.criterion_id} is an orphan: spec {o.product_proof_spec_id} is not in the committed "
           "derivation" for o in plan.obligations if _spec_of(o, inputs) is None]
    cycle = _cycle(story_graph(plan))
    return out + ([f"stories form a cycle: {' -> '.join(cycle)}"] if cycle else [])


def check_probe_calibration(plan: Plan, inputs: AdmissionInputs) -> list[str]:
    """9. a valid ProbeCapabilityCalibration exists for every referenced probe digest and the observation class each
    spec uses (§9.1.1). SpecFalsifiabilityEvidence is not required here, and cannot be (CAL-2)."""
    probes = _probes_by_id(inputs)
    out = []
    for sid in sorted(dict.fromkeys(o.product_proof_spec_id for o in plan.obligations)):
        spec = inputs.specs.get(sid)
        probe = probes.get(spec.probe_id) if spec else None
        if probe is None or probe.digest != spec.probe_digest:
            continue  # unresolved: checks 6 and 8 say so
        cls = inputs.registry.observation_class(probe.id, probe.digest, spec)
        if cls is None:
            out.append(f"spec {sid}: {probe.id} does not support the observation it asks for")
        elif calibration_for(inputs.calibrations, probe.id, probe.digest, cls) is None:
            out.append(f"spec {sid}: no ProbeCapabilityCalibration for {probe.id}@{probe.digest[:12]} class {cls!r}")
    return out


CHECKS: tuple[tuple[str, Callable[[Plan, AdmissionInputs], list[str]]], ...] = (
    ("requirement_coverage", check_requirement_coverage),
    ("contract_spec_integrity", check_contract_spec_integrity),
    ("ownership", check_ownership),
    ("dependency_dag", check_dependency_dag),
    ("contradictions", check_contradictions),
    ("proof_capability", check_proof_capability),
    ("traceability", check_traceability),
    ("plan_structure", check_plan_structure),
    ("probe_calibration", check_probe_calibration),
)


# --------------------------------------------------------------------------------------- engine

class StaticPlanAdmissionEngine:
    """Harness code. Runs the nine checks on committed objects; executes no probe, invents no revision."""
    digest = _engine_digest()

    def admit(self, plan: Plan, inputs: AdmissionInputs) -> StaticPlanAdmissionResult:
        if not isinstance(plan, Plan) or not isinstance(inputs, AdmissionInputs):
            raise InvariantError("the engine admits a Plan against AdmissionInputs")
        checks = tuple(CheckResult(n, name, not problems, tuple(problems))
                       for n, (name, check) in enumerate(CHECKS, 1) for problems in [check(plan, inputs)])
        admitted = all(c.passed for c in checks)
        body = {"plan_id": plan.id, "engine_digest": self.digest, "checks": checks, "admitted": admitted}
        return StaticPlanAdmissionResult(**body, result_digest=digest(body))


def require_admitted(plan: Plan, inputs: AdmissionInputs,
                     engine: StaticPlanAdmissionEngine | None = None) -> StaticPlanAdmissionResult:
    """§12: a plan MUST NOT freeze unless admitted. Admission is re-derived here, never taken on trust."""
    result = (engine or StaticPlanAdmissionEngine()).admit(plan, inputs)
    if not result.admitted:
        failed = [f"{c.number}. {c.name}: {'; '.join(c.problems)}" for c in result.checks if not c.passed]
        raise PlanNotAdmitted(f"plan {plan.id} is not admitted — " + " | ".join(failed))
    return result
