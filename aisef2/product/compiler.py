"""RFC §8, F4 — the pure compile `ProductProofSpec = f(approved BehaviorContract)`.

* **Pure.** Output depends only on the contract, the approvals and requirements it is checked against, and the probe
  catalogue. The compiler's own identity (`COMPILER_DIGEST`) is fixed at import from the source of the modules that
  decide the output; it is a content address, not a version label.
* **Gated.** An unapproved contract cannot be compiled (§6): `require_approved` runs first, every time.
* **Polarity.** `candidate_expectation` is SATISFIED for MUST_HOLD and REFUTED for MUST_NOT_HOLD (§8); nothing else.
* It reads the contract's semantics — subject, stimulus, observable, polarity, subject_absence — and never its prose.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass
from typing import Iterable, Mapping

from aisef2.arch.enums import BehaviorVerdict, Polarity, SubjectKind
from aisef2.product.approval import ContractApproval, Requirement, require_approved
from aisef2.product.contract import BehaviorContract, ContractError
from aisef2.product.spec import ProductProofSpec

COMPILER_ID = "aisef2.product.compiler/1"
_PACKAGE = pathlib.Path(__file__).resolve().parents[1]
#: The modules whose source decides a compiled spec; their LF-normalised bytes are the compiler's identity.
COMPILER_SOURCES = ("product/compiler.py", "product/spec.py", "product/contract.py", "product/approval.py")


def _compiler_digest() -> str:
    h = hashlib.sha256()
    for rel in COMPILER_SOURCES:
        h.update(f"aisef2/{rel}\n".encode())
        h.update((_PACKAGE / rel).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


COMPILER_DIGEST = _compiler_digest()


class CompileError(ContractError):
    """The contract cannot be compiled into a product proof spec."""


@dataclass(frozen=True, slots=True)
class ProbeRef:
    """A probe's identity as the compiler binds it: id and content digest (§9, §23)."""
    probe_id: str
    probe_digest: str


def expectation_for(polarity: Polarity) -> BehaviorVerdict:
    if polarity is Polarity.MUST_HOLD:
        return BehaviorVerdict.SATISFIED
    if polarity is Polarity.MUST_NOT_HOLD:
        return BehaviorVerdict.REFUTED
    raise CompileError(f"no candidate expectation for polarity {polarity!r}")


def compile_spec(contract: BehaviorContract, *, requirements: Mapping[str, Requirement],
                 approvals: Iterable[ContractApproval], probes: Mapping[SubjectKind, ProbeRef]) -> ProductProofSpec:
    require_approved(contract, requirements, approvals)
    probe = probes.get(contract.subject.kind)
    if probe is None:
        raise CompileError(f"no probe declared for subject kind {contract.subject.kind.value}")
    return ProductProofSpec.create(
        contract_id=contract.id,
        probe_id=probe.probe_id,
        probe_digest=probe.probe_digest,
        probe_input={"subject": {"kind": contract.subject.kind.value, "locator": contract.subject.locator},
                     "stimulus": contract.stimulus, "observable": contract.observable,
                     "subject_absence": contract.subject_absence.value},
        candidate_expectation=expectation_for(contract.polarity),
        compiler_id=COMPILER_ID,
        compiler_digest=COMPILER_DIGEST,
    )
