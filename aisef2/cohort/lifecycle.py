"""RFC §28 — the evaluation cohort: SEALED -> EVALUATING -> EXPOSED -> DEVELOPMENT, one way, with typed refusals.

1. Running the preregistered repetitions never demotes (`record_run`).
2. A change to a frozen input while results are unread invalidates the completed runs; the cohort then refuses every
   run and every read, and only a fresh preregistration can seal the workload again (`observe_inputs`, `seal`).
3. Mechanised demotion: `read_results` sets `results_read_at`; any change to a frozen input after it moves the cohort
   to EXPOSED with `exposed_reason` recorded (`observe_inputs`).
4. An EXPOSED or DEVELOPMENT cohort backs no generalization, and its workload never seals again (`seal`).
5. An OPAQUE aggregate grade bars sealing, and so does a DEVELOPMENT_REGRESSION workload (RFC §30): the cohort's own
   constructor checks both, so no construction path skips them.
6. A generalization rests on at least two independently sealed workloads and states its sample size per workload and
   in total (`generalization`).

The identity fields RFC §28 lists (`id`, `preregistration_hash`, `frozen_inputs`, `planned_runs`, `threshold`,
`plan_quality_policy`) are read from the frozen preregistration, so they cannot disagree with it. The machine reads no
clock: `results_read_at` is the caller's timestamp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from aisef2.cohort import preregistration as P
from aisef2.cohort.preregistration import CohortRefused, Refusal
from aisef2.plan.obligation import PlanQualityPolicy
from aisef2.runtime.runspec import q6_eligible


class CohortState(Enum):  # RFC §28 — cohort-local, carried in no event
    SEALED = "SEALED"
    EVALUATING = "EVALUATING"
    EXPOSED = "EXPOSED"
    DEVELOPMENT = "DEVELOPMENT"


#: the one way: each state's only successor; DEVELOPMENT has none
NEXT = {CohortState.SEALED: CohortState.EVALUATING, CohortState.EVALUATING: CohortState.EXPOSED,
        CohortState.EXPOSED: CohortState.DEVELOPMENT}
DEMOTED = (CohortState.EXPOSED, CohortState.DEVELOPMENT)
MIN_WORKLOADS = 2


@dataclass(frozen=True)
class EvaluationCohort:
    preregistration: Mapping[str, Any]
    state: CohortState
    runs_completed: tuple[str, ...] = ()
    results_read_at: float | None = None
    exposed_reason: str | None = None
    invalidated_runs: tuple[str, ...] = ()    # completed runs a frozen-input change invalidated (rule 2)
    stale_inputs: tuple[str, ...] = ()        # the frozen inputs that changed while results were unread (rule 2)

    def __post_init__(self) -> None:
        record = P.validate(self.preregistration)
        if not q6_eligible(P.runspec_of(record["execution_profile"])):
            raise CohortRefused(Refusal.OPAQUE_PROFILE, "an OPAQUE aggregate_min_grade never seals (RFC §28 rule 5)")
        why = P.development_regression(record)
        if why:
            raise CohortRefused(Refusal.DEVELOPMENT_REGRESSION, why)
        object.__setattr__(self, "preregistration", record)
        if not isinstance(self.state, CohortState):
            raise CohortRefused(Refusal.COHORT_INCONSISTENT, "state is a CohortState")
        for name in ("runs_completed", "invalidated_runs", "stale_inputs"):
            v = getattr(self, name)
            if not isinstance(v, tuple) or not all(isinstance(x, str) and x for x in v) or len(set(v)) != len(v):
                raise CohortRefused(Refusal.COHORT_INCONSISTENT, f"{name} is a tuple of distinct names")
        if len(self.runs_completed) > self.planned_runs:
            raise CohortRefused(Refusal.COHORT_INCONSISTENT, "more runs than were preregistered")
        t = self.results_read_at
        if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)):
            raise CohortRefused(Refusal.COHORT_INCONSISTENT, "results_read_at is a finite timestamp or None")
        if self.state is CohortState.SEALED and (self.runs_completed or t is not None):
            raise CohortRefused(Refusal.COHORT_INCONSISTENT, "a SEALED cohort has run nothing and read nothing")
        reason = self.exposed_reason
        if self.state in DEMOTED:
            if not (isinstance(reason, str) and reason.strip()):
                raise CohortRefused(Refusal.COHORT_INCONSISTENT, f"{self.state.value} records its exposed_reason")
        elif reason is not None:
            raise CohortRefused(Refusal.COHORT_INCONSISTENT, f"{self.state.value} has no exposed_reason")

    @property
    def id(self) -> str:
        return self.preregistration["cohort_id"]

    @property
    def preregistration_hash(self) -> str:
        return P.preregistration_hash(self.preregistration)

    @property
    def frozen_inputs(self) -> Mapping[str, str]:
        return MappingProxyType(P.frozen_inputs(self.preregistration))

    @property
    def planned_runs(self) -> int:
        return self.preregistration["run_count"]

    @property
    def threshold(self) -> str:
        return self.preregistration["thresholds"]["delivery"]

    @property
    def plan_quality_policy(self) -> PlanQualityPolicy:
        return P.policy_of(self.preregistration["plan_quality_policy"])

    @property
    def workload(self) -> dict[str, str]:
        return P.workload_identity(self.preregistration)


def seal(preregistration: Mapping[str, Any], prior: Iterable[EvaluationCohort] = ()) -> EvaluationCohort:
    """Seal a preregistered workload. Refused for every bar of the constructor, and for a workload an earlier cohort
    holds: demoted (an EXPOSED or DEVELOPMENT workload never seals again), observed (its results were read), or still
    live. Only an earlier cohort invalidated before any read leaves room — for a fresh preregistration."""
    cohort = EvaluationCohort(preregistration, CohortState.SEALED)
    for p in prior:
        if not P.shared(p.workload, cohort.workload):
            continue
        if p.state in DEMOTED:
            raise CohortRefused(Refusal.WORKLOAD_DEMOTED, f"{p.id} is {p.state.value}: its workload never seals again")
        if p.results_read_at is not None:
            raise CohortRefused(Refusal.WORKLOAD_OBSERVED, f"{p.id} read its results at {p.results_read_at}")
        if not p.stale_inputs:
            raise CohortRefused(Refusal.WORKLOAD_ALREADY_SEALED, f"{p.id} still holds the workload ({p.state.value})")
        if p.preregistration_hash == cohort.preregistration_hash:
            raise CohortRefused(Refusal.PREREGISTRATION_REUSED, f"{p.id} was invalidated under this preregistration")
    return cohort


def advance(cohort: EvaluationCohort, to: CohortState, reason: str | None = None) -> EvaluationCohort:
    """One step forward along RFC §28's one way; the step to EXPOSED records why (`reason`)."""
    if NEXT.get(cohort.state) is not to:
        raise CohortRefused(Refusal.NOT_FORWARD,
                            f"{cohort.state.value} -> {getattr(to, 'value', to)}: one way, one step at a time")
    return replace(cohort, state=to, exposed_reason=cohort.exposed_reason or reason)


def _live(cohort: EvaluationCohort) -> None:
    if cohort.state is not CohortState.EVALUATING:
        raise CohortRefused(Refusal.NOT_EVALUATING, f"{cohort.id} is {cohort.state.value}")
    if cohort.stale_inputs:
        raise CohortRefused(Refusal.PREREGISTRATION_STALE,
                            f"{', '.join(cohort.stale_inputs)} changed: a fresh preregistration is required")


def record_run(cohort: EvaluationCohort, run_id: str) -> EvaluationCohort:
    """One preregistered repetition — never a demotion (rule 1)."""
    _live(cohort)
    if run_id in cohort.runs_completed:
        raise CohortRefused(Refusal.RUN_DUPLICATE, f"{run_id} is already recorded")
    if len(cohort.runs_completed) >= cohort.planned_runs:
        raise CohortRefused(Refusal.RUNS_COMPLETE, f"all {cohort.planned_runs} preregistered runs are recorded")
    return replace(cohort, runs_completed=(*cohort.runs_completed, run_id))


def read_results(cohort: EvaluationCohort, at: float) -> EvaluationCohort:
    """Reading results sets results_read_at (the first read stands); from then on a frozen-input change demotes."""
    _live(cohort)
    return cohort if cohort.results_read_at is not None else replace(cohort, results_read_at=at)


def observe_inputs(cohort: EvaluationCohort, current: Mapping[str, str]) -> EvaluationCohort:
    """Rules 2 and 3, given each frozen input's hash as measured now (a name missing or added is a change)."""
    frozen = cohort.frozen_inputs
    changed = sorted(k for k in {*frozen, *current} if frozen.get(k) != current.get(k))
    if not changed or cohort.state in DEMOTED:
        return cohort
    if cohort.results_read_at is not None:
        return replace(cohort, state=CohortState.EXPOSED, exposed_reason=(
            f"frozen inputs changed after results were read at {cohort.results_read_at}: {', '.join(changed)}"))
    return replace(cohort, runs_completed=(), invalidated_runs=cohort.invalidated_runs + cohort.runs_completed,
                   stale_inputs=tuple(sorted({*cohort.stale_inputs, *changed})))


def _complete(c: EvaluationCohort) -> bool:
    """A completed sealed evaluation: still EVALUATING, never invalidated, results read, every planned run recorded."""
    return c.state is CohortState.EVALUATING and not c.stale_inputs and c.results_read_at is not None \
        and len(c.runs_completed) == c.planned_runs


def generalization(cohorts: Iterable[EvaluationCohort]) -> dict:
    """Rule 6: the statement a generalization may make — at least MIN_WORKLOADS independently sealed workloads, each a
    completed evaluation, with the sample size per workload and in total. Anything less is refused."""
    cohorts = [*cohorts]
    why = [f"{c.id} is not a completed sealed evaluation" for c in cohorts if not _complete(c)]
    why += [f"{a.id} and {b.id} are one workload (same {', '.join(P.shared(a.workload, b.workload))})"
            for i, a in enumerate(cohorts) for b in cohorts[i + 1:] if P.shared(a.workload, b.workload)]
    if len(cohorts) < MIN_WORKLOADS:
        why.append(f"{len(cohorts)} sealed workload(s); a generalization requires at least {MIN_WORKLOADS}")
    if why:
        raise CohortRefused(Refusal.GENERALIZATION_REFUSED, "; ".join(why))
    per = [{"cohort": c.id, "preregistration_hash": c.preregistration_hash, "sample_size": len(c.runs_completed)}
           for c in cohorts]
    return {"workloads": per, "workload_count": len(per), "sample_size_total": sum(w["sample_size"] for w in per)}
