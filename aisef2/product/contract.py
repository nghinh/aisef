"""RFC §7 — `BehaviorContract` and `Subject` (F4), with the content identity every later object cites.

* `contract_hash` binds every field, `subject_absence` and `rationale` included: any edit — even to prose — yields a
  different contract, so the approval that bound the old hash no longer applies (§6).
* A contract with a hash that does not match its content cannot be constructed; build one with `BehaviorContract.create`.
* A contract names the product, never a test (§7): a locator, stimulus or observable that names a test file, test
  function, test directory or test runner is rejected.
* `rationale` is prose for human review. No control path reads it (invariant I; static check in
  `validation/v2/kernel_static_checks.py`); identity and serialisation reach it only through the generic field walk.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, fields
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind


class ContractError(ValueError):
    """The object is not a valid behaviour contract."""


# --------------------------------------------------------------------------------------- canonical identity

def freeze(value: Any) -> Any:
    """Deep, immutable copy of JSON-shaped data: mappings become read-only, sequences tuples."""
    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            raise ContractError("mapping keys must be strings")
        return MappingProxyType({k: freeze(value[k]) for k in sorted(value)})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("non-finite numbers have no canonical form")
    if value is None or isinstance(value, (str, int, float)):  # bool is an int
        return value
    raise ContractError(f"{type(value).__name__} is not JSON-shaped data")


def plain(value: Any) -> Any:
    """The JSON form of a frozen value, of an enum, or of a dataclass (by its fields, never by attribute name)."""
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [plain(v) for v in value]
    return value


def canonical(value: Any) -> str:
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def content_of(obj: Any, *, without: str) -> dict:
    """Every field of a dataclass except its own identity field."""
    return {k: v for k, v in plain(obj).items() if k != without}


# --------------------------------------------------------------------------------------- no developer artefacts

# ponytail: recognition by name — a developer artefact with a product-like name is not caught here; resolving the
# locator against the revision's declared test roots belongs to the probe layer (WP-2.1).
_TEST_ARTEFACT = re.compile(
    r"(^|[/\\.])tests?([/\\.:]|$)"          # a tests/ or test/ directory or package
    r"|(^|[/\\.])test_\w*"                   # test_x.py, pkg.test_x
    r"|\w_tests?\.py\b"                      # x_test.py
    r"|(^|[/\\.])conftest\b"                 # pytest configuration
    r"|::\s*test|::\s*Test"                  # a pytest node id
    r"|(^|[/\\.\s])(pytest|unittest|nose2?)([/\\.\s:]|$)",
    re.IGNORECASE)


def names_test_artefact(value: Any) -> list[str]:
    """Every string in `value` (keys included) that names a developer-controlled test artefact."""
    if isinstance(value, Mapping):
        return [s for k, v in value.items() for s in names_test_artefact(k) + names_test_artefact(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in names_test_artefact(v)]
    return [value] if isinstance(value, str) and _TEST_ARTEFACT.search(value) else []


# --------------------------------------------------------------------------------------- shapes

@dataclass(frozen=True, slots=True)
class Subject:
    kind: SubjectKind
    locator: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SubjectKind):
            raise ContractError("Subject.kind must be a SubjectKind")
        if not isinstance(self.locator, str) or not self.locator.strip():
            raise ContractError("Subject.locator must be a non-empty string")
        if names_test_artefact(self.locator):
            raise ContractError(f"a contract names the product, never a test: {self.locator!r}")


@dataclass(frozen=True, slots=True)
class BehaviorContract:
    id: str
    requirement_ids: tuple[str, ...]
    subject: Subject
    stimulus: Mapping[str, Any]
    observable: Mapping[str, Any]
    polarity: Polarity
    subject_absence: SubjectAbsence
    rationale: str
    contract_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ContractError("contract id must be a non-empty string")
        ids = tuple(self.requirement_ids) if isinstance(self.requirement_ids, (list, tuple)) else None
        if not ids or not all(isinstance(r, str) and r.strip() for r in ids):
            raise ContractError("a contract must cite at least one requirement id")
        object.__setattr__(self, "requirement_ids", ids)
        if not isinstance(self.subject, Subject):
            raise ContractError("subject must be a Subject")
        if not isinstance(self.polarity, Polarity):
            raise ContractError("polarity must be a Polarity")
        if not isinstance(self.subject_absence, SubjectAbsence):
            raise ContractError("subject_absence must be declared explicitly as a SubjectAbsence; it is never inferred")
        for name in ("stimulus", "observable"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ContractError(f"{name} must be a mapping")
            named = names_test_artefact(value)
            if named:
                raise ContractError(f"a contract names the product, never a test: {name} names {named}")
            object.__setattr__(self, name, freeze(value))
        require_str_fields(self, skip=("contract_hash",))
        if self.contract_hash is _SEAL:
            object.__setattr__(self, "contract_hash", contract_hash(self))
        elif self.contract_hash != contract_hash(self):
            raise ContractError("contract_hash does not bind this content — an edited contract is a new contract")

    @classmethod
    def create(cls, **content: Any) -> "BehaviorContract":
        """The only way to mint a contract_hash: computed from the validated content, never supplied."""
        return cls(**content, contract_hash=_SEAL)

    def to_json(self) -> dict:
        return plain(self)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "BehaviorContract":
        d = dict(data)
        d["subject"] = Subject(SubjectKind(d["subject"]["kind"]), d["subject"]["locator"])
        d["polarity"], d["subject_absence"] = Polarity(d["polarity"]), SubjectAbsence(d["subject_absence"])
        d["requirement_ids"] = tuple(d["requirement_ids"])
        return cls(**d)


#: Private: asks __post_init__ to compute the hash from validated content (`BehaviorContract.create`).
_SEAL: Any = object()


def require_str_fields(obj: Any, skip: tuple[str, ...] = ()) -> None:
    """Type-check every `str` field generically — so no prose field is ever read by name."""
    for f in fields(obj):
        if f.name not in skip and f.type == "str" and not isinstance(getattr(obj, f.name), str):
            raise ContractError(f"{type(obj).__name__}.{f.name} must be a string")


def contract_hash(contract: BehaviorContract) -> str:
    """sha256 over the canonical form of every field but the hash itself — `subject_absence` and `rationale` bound."""
    return digest(content_of(contract, without="contract_hash"))
