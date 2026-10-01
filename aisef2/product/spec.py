"""RFC §8 — `ProductProofSpec` (F4) and `semantic_hash` (F9, the first of the four cited identities).

* A spec holds **no plan fact**: no story id, no plan id, no parent expectation. Its fields are exactly the RFC's,
  and a frozen, slotted dataclass cannot grow one.
* `semantic_hash` answers *what was proved*: the probe's identity and digest, the probe input compiled from the
  contract (subject, stimulus, observable **and `subject_absence`**), and `candidate_expectation`. It excludes the
  contract's prose and every id, so a reworded rationale forces re-approval but does not invalidate product evidence
  (§5.1, §35).
* `id` is `"PPS-"` + the digest of every other field, compiler identity included.
* Both are verified on construction; a spec is minted only by the compiler (`aisef2.product.compiler`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aisef2.arch.enums import BehaviorVerdict
from aisef2.product.contract import _SEAL, ContractError, content_of, digest, freeze, plain, require_str_fields

SPEC_PREFIX = "PPS-"
#: The probe input is the contract's semantics and nothing else.
PROBE_INPUT_KEYS = ("observable", "stimulus", "subject", "subject_absence")
#: A contract is met by a probe verdict equal to this; INDETERMINATE can never be an expectation.
EXPECTATIONS = (BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED)


@dataclass(frozen=True, slots=True)
class ProductProofSpec:
    id: str
    contract_id: str
    probe_id: str
    probe_digest: str
    probe_input: Mapping[str, Any]
    candidate_expectation: BehaviorVerdict
    compiler_id: str
    compiler_digest: str
    semantic_hash: str

    def __post_init__(self) -> None:
        require_str_fields(self, skip=("id", "semantic_hash"))
        if self.candidate_expectation not in EXPECTATIONS:
            raise ContractError("candidate_expectation must be SATISFIED or REFUTED")
        if not isinstance(self.probe_input, Mapping) or tuple(sorted(self.probe_input)) != PROBE_INPUT_KEYS:
            raise ContractError(f"probe_input must hold exactly {PROBE_INPUT_KEYS}")
        object.__setattr__(self, "probe_input", freeze(self.probe_input))
        if self.semantic_hash is _SEAL:
            object.__setattr__(self, "semantic_hash", semantic_hash(self))
        elif self.semantic_hash != semantic_hash(self):
            raise ContractError("semantic_hash does not bind this spec's semantics")
        if self.id is _SEAL:
            object.__setattr__(self, "id", spec_id(self))
        elif self.id != spec_id(self):
            raise ContractError("spec id does not address this spec's content")

    @classmethod
    def create(cls, **content: Any) -> "ProductProofSpec":
        return cls(id=_SEAL, **content, semantic_hash=_SEAL)

    def to_json(self) -> dict:
        return plain(self)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ProductProofSpec":
        return cls(**{**data, "candidate_expectation": BehaviorVerdict(data["candidate_expectation"])})


def semantic_hash(spec: ProductProofSpec) -> str:
    """What was proved: probe identity and digest, the compiled probe input, and the expectation."""
    return digest({"probe_id": spec.probe_id, "probe_digest": spec.probe_digest, "probe_input": spec.probe_input,
                   "candidate_expectation": spec.candidate_expectation})


def spec_id(spec: ProductProofSpec) -> str:
    return SPEC_PREFIX + digest(content_of(spec, without="id"))
