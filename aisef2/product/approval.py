"""RFC §6 — requirement authority: `Requirement` and `ContractApproval`.

* `Requirement.text` is prose. No control path reads it (invariant I); only its hash is used.
* A `ContractApproval` binds the exact `requirement_hash` **and** `contract_hash`; an edit to either object invalidates
  it. `require_approved` is the gate the compiler calls: a contract with any cited requirement lacking a valid
  approval cannot be compiled.
* Approval authority belongs to a human. In cycle 1 a human identity is written `human:<name>`; anything else — a
  model or agent identity included — cannot approve. Model reviews are advisory references only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from aisef2.product.contract import _SEAL, BehaviorContract, ContractError, content_of, digest, require_str_fields

HUMAN_PREFIX = "human:"


class UnapprovedContract(ContractError):
    """A contract lacks a valid approval binding both hashes; it cannot be compiled."""


@dataclass(frozen=True, slots=True)
class Requirement:
    id: str
    text: str
    source: str
    requirement_hash: str

    def __post_init__(self) -> None:
        require_str_fields(self, skip=("requirement_hash",))
        if self.requirement_hash is _SEAL:
            object.__setattr__(self, "requirement_hash", requirement_hash(self))
        elif self.requirement_hash != requirement_hash(self):
            raise ContractError("requirement_hash does not bind this content")

    @classmethod
    def create(cls, **content: Any) -> "Requirement":
        return cls(**content, requirement_hash=_SEAL)


def requirement_hash(requirement: Requirement) -> str:
    return digest(content_of(requirement, without="requirement_hash"))


@dataclass(frozen=True, slots=True)
class ContractApproval:
    requirement_id: str
    requirement_hash: str
    contract_id: str
    contract_hash: str
    approver: str
    approved_at: float
    model_reviews: tuple[str, ...]

    def __post_init__(self) -> None:
        require_str_fields(self)
        if not self.approver.startswith(HUMAN_PREFIX) or not self.approver[len(HUMAN_PREFIX):].strip():
            raise ContractError(f"approval authority belongs to a human identity ({HUMAN_PREFIX}<name>), "
                                f"not {self.approver!r}")
        if isinstance(self.approved_at, bool) or not isinstance(self.approved_at, (int, float)) \
                or not math.isfinite(self.approved_at):
            raise ContractError("approved_at must be a finite timestamp")
        reviews = tuple(self.model_reviews) if isinstance(self.model_reviews, (list, tuple)) else None
        if reviews is None or not all(isinstance(r, str) for r in reviews):
            raise ContractError("model_reviews must be a tuple of journal references")
        object.__setattr__(self, "model_reviews", reviews)


def binding_problems(approval: ContractApproval, requirement: Requirement, contract: BehaviorContract) -> list[str]:
    out = []
    if (approval.requirement_id, approval.requirement_hash) != (requirement.id, requirement.requirement_hash):
        out.append(f"approval does not bind requirement {requirement.id} at its current hash")
    if (approval.contract_id, approval.contract_hash) != (contract.id, contract.contract_hash):
        out.append(f"approval does not bind contract {contract.id} at its current hash")
    return out


def require_approved(contract: BehaviorContract, requirements: Mapping[str, Requirement],
                     approvals: Iterable[ContractApproval]) -> None:
    """Raise unless every requirement the contract cites has an approval binding both current hashes."""
    approvals = tuple(approvals)
    missing = []
    for rid in contract.requirement_ids:
        req = requirements.get(rid)
        if req is None:
            missing.append(f"{rid}: requirement unknown")
            continue
        if not any(not binding_problems(a, req, contract) for a in approvals):
            missing.append(f"{rid}: no approval binds requirement_hash and contract_hash")
    if missing:
        raise UnapprovedContract(f"contract {contract.id} is not approved: " + "; ".join(missing))
