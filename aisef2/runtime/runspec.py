"""RFC §23, §24 — RunSpec (F9; P4-LIFETIME-SEMANTICS.md §5).

`runspec_hash` binds every capability's identity tuple, grade and enforcement level, and the resolved settings with
their layer provenance — including the full revision SHA, the authoritative source identity. An execution locator (the
checkout path, the journal path) is never a setting: a setting whose value is an absolute path is refused, so the
filesystem location cannot become identity. Two runs are comparable only with the same capability tuples, grades and
enforcement (§23); OPAQUE anywhere bars Q6 and sealed cohorts.
"""

from __future__ import annotations

import hashlib
import ntpath
import posixpath
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from aisef2.arch.enums import IdentityGrade as G
from aisef2.product.contract import canonical, freeze
from aisef2.runtime.capability import CapabilityIdentity

_SHA = re.compile(r"[0-9a-f]{40}")
_ORDER = (G.OPAQUE, G.ATTESTED, G.VERIFIED)


class RunSpecError(ValueError):
    """A RunSpec that would bind something that is not identity, or miss something that is."""


@dataclass(frozen=True)
class RunSpec:
    capabilities: tuple[CapabilityIdentity, ...]
    aggregate_min_grade: G
    settings: Mapping[str, Any]           # resolved, with per-value layer provenance
    runspec_hash: str

    @property
    def revision(self) -> str:
        return self.settings["revision"]["value"]

    def resolved(self) -> dict:
        """The `run/spec-resolved` payload (format 2)."""
        return {"runspec_hash": self.runspec_hash, "aggregate_min_grade": self.aggregate_min_grade.value,
                "capabilities": [c.name for c in self.capabilities], "revision": self.revision}


def _is_locator(value: Any) -> bool:
    return isinstance(value, str) and (posixpath.isabs(value) or ntpath.isabs(value) or value.startswith("~"))


def runspec_hash(capabilities: Iterable[CapabilityIdentity], aggregate: G, settings: Mapping[str, Any]) -> str:
    content = {"capabilities": [c.content() for c in sorted(capabilities, key=lambda c: c.name)],
               "aggregate_min_grade": aggregate.value, "settings": settings}
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def resolve(capabilities: Iterable[CapabilityIdentity], settings: Mapping[str, Mapping[str, Any]],
            revision: str) -> RunSpec:
    """Freeze a RunSpec. `settings` maps each key to {"value", "layer"}; `revision` is the full source SHA."""
    caps = tuple(sorted(capabilities, key=lambda c: c.name))
    if not caps:
        raise RunSpecError("a RunSpec names at least one capability (the kernel itself is one)")
    names = [c.name for c in caps]
    if len(set(names)) != len(names):
        raise RunSpecError(f"a capability is named once: {names}")
    if not isinstance(revision, str) or not _SHA.fullmatch(revision):
        raise RunSpecError(f"revision {revision!r}: the full 40-hex SHA is the authoritative identity")
    if "revision" in settings:
        raise RunSpecError("the revision is given as the revision, not as a setting")
    resolved: dict[str, Any] = {"revision": {"value": revision, "layer": "run"}}
    for key, v in settings.items():
        if not isinstance(v, Mapping) or set(v) != {"value", "layer"} or not isinstance(v["layer"], str):
            raise RunSpecError(f"setting {key!r} carries its value and the layer it came from, nothing else")
        if _is_locator(v["value"]):
            raise RunSpecError(f"setting {key!r} is an absolute path: an execution locator is never identity")
        resolved[key] = {"value": v["value"], "layer": v["layer"]}
    frozen = freeze(resolved)
    aggregate = min((c.grade for c in caps), key=_ORDER.index)
    return RunSpec(caps, aggregate, frozen, runspec_hash(caps, aggregate, frozen))


def comparable(a: RunSpec, b: RunSpec) -> tuple[bool, list[str]]:
    """Same resolved capability tuples, grades and enforcement identity (§23); the reasons when not."""
    why = []
    ca, cb = {c.name: c for c in a.capabilities}, {c.name: c for c in b.capabilities}
    for name in sorted(set(ca) | set(cb)):
        x, y = ca.get(name), cb.get(name)
        if x is None or y is None:
            why.append(f"{name}: only in one run")
            continue
        if x.grade is not y.grade:
            why.append(f"{name}: grade {x.grade.value} vs {y.grade.value}")
        if x.enforcement is not y.enforcement:
            why.append(f"{name}: enforcement {x.enforcement.value} vs {y.enforcement.value}")
        for key in sorted(set(x.tuple_) | set(y.tuple_)):
            if x.tuple_.get(key) != y.tuple_.get(key):
                why.append(f"{name}: {key} differs")
    return not why, why


def q6_eligible(spec: RunSpec) -> bool:
    """OPAQUE anywhere bars Q6 qualification and sealed cohorts (§23)."""
    return spec.aggregate_min_grade is not G.OPAQUE

