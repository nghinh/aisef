"""RFC §11, §29 — the planning plane: `PlanObligation` (F6), `Plan` and `PlanQualityPolicy`.

* A `PlanObligation` ties one criterion of one story to one `ProductProofSpec` with an `ObligationRole` and a
  `ParentExpectation` — an expected **ContractSatisfaction** at the parent, never a raw verdict (F6).
* `depends_on` names the criterion ids that must complete first (board resolution §1); the story order is induced
  from it.
* `ownership_rationale` is prose for human review: no control path reads it (invariant I). Identity reaches it only
  through the generic field walk, like every other prose field.
* `plan_hash` binds every field; a `Plan` with a hash that does not match its content cannot be constructed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from aisef2.arch.enums import ObligationRole, ParentExpectation
from aisef2.product.contract import _SEAL, ContractError, content_of, digest, require_str_fields

FULL_SHA = re.compile(r"[0-9a-f]{40}")


class PlanError(ContractError):
    """The object is not a valid plan."""


@dataclass(frozen=True, slots=True)
class PlanObligation:
    criterion_id: str
    product_proof_spec_id: str
    story_id: str
    role: ObligationRole
    expected_parent: ParentExpectation
    depends_on: tuple[str, ...]
    ownership_rationale: str

    def __post_init__(self) -> None:
        require_str_fields(self)
        for f in ("criterion_id", "product_proof_spec_id", "story_id"):
            if not getattr(self, f).strip():
                raise PlanError(f"PlanObligation.{f} must be non-empty")
        if not isinstance(self.role, ObligationRole):
            raise PlanError("role must be an ObligationRole")
        if not isinstance(self.expected_parent, ParentExpectation):
            raise PlanError("expected_parent must be a ParentExpectation — an expected satisfaction, never a verdict")
        deps = tuple(self.depends_on) if isinstance(self.depends_on, (list, tuple)) else None
        if deps is None or not all(isinstance(d, str) and d.strip() for d in deps):
            raise PlanError("depends_on must be a tuple of criterion ids")
        object.__setattr__(self, "depends_on", deps)


@dataclass(frozen=True, slots=True)
class PlanQualityPolicy:
    """§29: thresholds belong to the evaluation protocol; None means none is preregistered."""
    max_pre_satisfied_introduce_ratio: float | None
    max_fully_pre_satisfied_stories: int | None
    max_unattributed_plan_drift: int | None

    def __post_init__(self) -> None:
        r = self.max_pre_satisfied_introduce_ratio
        if r is not None and (isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r)
                              or not 0 <= r <= 1):
            raise PlanError("max_pre_satisfied_introduce_ratio is a ratio in [0, 1] or None")
        for name in ("max_fully_pre_satisfied_stories", "max_unattributed_plan_drift"):
            v = getattr(self, name)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
                raise PlanError(f"{name} is a non-negative count or None")


NOT_PREREGISTERED = PlanQualityPolicy(None, None, None)

#: The expected parent state each role is routed with in RFC §13's disposition table. A pair outside it has no
#: StoryAdmission row, so StaticPlanAdmission rejects it (fail closed; no meaning is derived for it).
EXPECTED_AT_PARENT = {ObligationRole.INTRODUCE: ParentExpectation.UNSATISFIED_AT_PARENT,
                      ObligationRole.PRESERVE: ParentExpectation.SATISFIED_AT_PARENT,
                      ObligationRole.VERIFY: ParentExpectation.UNCONSTRAINED}


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    baseline: str
    obligations: tuple[PlanObligation, ...]
    plan_quality_policy: PlanQualityPolicy
    plan_hash: str

    def __post_init__(self) -> None:
        require_str_fields(self, skip=("plan_hash",))
        if not FULL_SHA.fullmatch(self.baseline):
            raise PlanError(f"a plan's baseline is a full 40-hex SHA: {self.baseline!r}")
        obligations = tuple(self.obligations) if isinstance(self.obligations, (list, tuple)) else None
        if not obligations or not all(isinstance(o, PlanObligation) for o in obligations):
            raise PlanError("a plan holds at least one PlanObligation")
        object.__setattr__(self, "obligations", obligations)
        if not isinstance(self.plan_quality_policy, PlanQualityPolicy):
            raise PlanError("plan_quality_policy must be a PlanQualityPolicy")
        if self.plan_hash is _SEAL:
            object.__setattr__(self, "plan_hash", plan_hash(self))
        elif self.plan_hash != plan_hash(self):
            raise PlanError("plan_hash does not bind this content — an edited plan is a new plan")

    @classmethod
    def create(cls, **content: Any) -> "Plan":
        return cls(**content, plan_hash=_SEAL)


def plan_hash(plan: Plan) -> str:
    return digest(content_of(plan, without="plan_hash"))
