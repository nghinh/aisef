"""RFC §23, §24 — capability identity grades (F9; P4-LIFETIME-SEMANTICS.md §5).

* **VERIFIED** binds a sha256 digest AISEF computed over the artefact it executes (`verified`). A version label is
  metadata: without the digest the grade is refused.
* **ATTESTED** binds provider, endpoint, declared model, fixed route, client and a locally measured preflight
  fingerprint (and the deployment when the provider exposes one). The fingerprint is a drift detector, not proof.
* **OPAQUE** binds what is known; it bars Q6 and sealed cohorts (`runspec.q6_eligible`).

No fallback: a capability whose digest cannot be computed is not quietly declared ATTESTED or VERIFIED — the caller
states OPAQUE, and the RunSpec's aggregate says so.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from aisef2.arch.enums import Enforcement, IdentityGrade as G
from aisef2.product.contract import canonical

_HEX64 = re.compile(r"[0-9a-f]{64}")
ATTESTED_BINDING = ("provider", "endpoint", "declared_model", "route", "client", "fingerprint")
ATTESTED_OPTIONAL = ("deployment",)


class CapabilityError(ValueError):
    """A capability identity that does not bind what its grade requires."""


@dataclass(frozen=True)
class CapabilityIdentity:
    name: str
    grade: G
    tuple_: Mapping[str, str]     # the binding below, by grade
    enforcement: Enforcement

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise CapabilityError("a capability has a name")
        if not isinstance(self.grade, G) or not isinstance(self.enforcement, Enforcement):
            raise CapabilityError(f"{self.name}: grade is an IdentityGrade and enforcement an Enforcement")
        if not isinstance(self.tuple_, Mapping) or not all(isinstance(k, str) and isinstance(v, str)
                                                            for k, v in self.tuple_.items()):
            raise CapabilityError(f"{self.name}: the identity tuple maps names to strings")
        t = dict(self.tuple_)
        if self.grade is G.VERIFIED and not _HEX64.fullmatch(t.get("digest", "")):
            raise CapabilityError(f"{self.name}: VERIFIED binds a locally computed sha256 digest; a version label "
                                  "is metadata, not identity (§23)")
        if self.grade is G.ATTESTED:
            missing = [k for k in ATTESTED_BINDING if not t.get(k)]
            unknown = sorted(set(t) - set(ATTESTED_BINDING) - set(ATTESTED_OPTIONAL))
            if missing or unknown:
                raise CapabilityError(f"{self.name}: ATTESTED binds {list(ATTESTED_BINDING)} (and deployment when "
                                      f"exposed): missing {missing}, not in the binding {unknown}")
            if not _HEX64.fullmatch(t["fingerprint"]):
                raise CapabilityError(f"{self.name}: the preflight fingerprint is a locally measured sha256")
        object.__setattr__(self, "tuple_", MappingProxyType(dict(sorted(t.items()))))

    def content(self) -> dict:
        return {"name": self.name, "grade": self.grade.value, "tuple": dict(self.tuple_),
                "enforcement": self.enforcement.value}

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical(self.content()).encode("utf-8")).hexdigest()

    def resolved(self) -> dict:
        """The `capability/resolved` payload (format 2)."""
        return {"name": self.name, "grade": self.grade.value, "enforcement": self.enforcement.value,
                "binding": dict(self.tuple_), "identity": self.identity}


def digest_of(artefact: bytes | str | os.PathLike) -> str:
    """sha256 over bytes, a file, or a directory tree (sorted relative paths and contents). A missing path raises."""
    if isinstance(artefact, bytes):
        return hashlib.sha256(artefact).hexdigest()
    path = pathlib.Path(artefact)
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise CapabilityError(f"{path} does not exist: there is nothing to digest (no fallback grade)")
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        h.update(f.relative_to(path).as_posix().encode("utf-8") + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def verified(name: str, artefact: bytes | str | os.PathLike, enforcement: Enforcement,
             **metadata: str) -> CapabilityIdentity:
    return CapabilityIdentity(name, G.VERIFIED, {**metadata, "digest": digest_of(artefact)}, enforcement)


def attested(name: str, *, provider: str, endpoint: str, declared_model: str, route: str, client: str,
             preflight: Mapping, enforcement: Enforcement, deployment: str | None = None) -> CapabilityIdentity:
    """`preflight` is the locally measured response (declared model id, limits, tool-calling behaviour)."""
    binding = {"provider": provider, "endpoint": endpoint, "declared_model": declared_model, "route": route,
               "client": client, "fingerprint": hashlib.sha256(canonical(dict(preflight)).encode("utf-8")).hexdigest()}
    if deployment:
        binding["deployment"] = deployment
    return CapabilityIdentity(name, G.ATTESTED, binding, enforcement)


def opaque(name: str, enforcement: Enforcement, **known: str) -> CapabilityIdentity:
    return CapabilityIdentity(name, G.OPAQUE, known, enforcement)
