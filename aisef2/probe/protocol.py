"""RFC §9, §24 — the probe protocol (F5) and the one place a probe's observation becomes a `ProbeResult`.

* **Observation harness vs subject.** A probe declares what must function for it to look at all
  (`harness_preconditions()`) separately from what it looks at (the spec's subject). A harness failure — interpreter
  missing, tool absent, sandbox unable to execute, checkout not inspectable, timeout — is `UNRUNNABLE`, owner
  ENVIRONMENT. Absence of the subject is never `UNRUNNABLE`: it is an observation, and what it means is decided by the
  spec (`SubjectAbsence` + observable, §10.2), through `on_subject_absent`.
* **The API shape carries the split.** A probe does not build results. Its `observe()` reports a typed `Observation`
  — HARNESS_FAILED, UNSUPPORTED, SUBJECT_ABSENT or OBSERVED — and `classify_failure` alone turns that into a
  `ProbeResult`. A harness failure cannot carry a verdict, and subject absence cannot be reported as one.
* **Enforcement is bound into every result** (§24). `run_probe` is the entry point: it returns a `ProbeRecord` holding
  the result, the spec it answers, the probe identity, the revision and the enforcement level the probe ran under. It
  refuses — `UNRUNNABLE`, never a weaker observation — when the probe cannot honour the required level, and it
  refuses a spec compiled for another probe or digest (`INVALID_SPEC`).
* **Harness-owned** (invariant IX). `evaluate(spec, at, env)` takes a spec compiled from an approved contract (its
  locator names the product, never a test), a revision (a full SHA and the harness's checkout of it) and an
  environment the harness builds. None of them has a field for a developer-supplied path, command or test, and a spec
  whose probe input names a test artefact is refused before any probe looks.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Protocol, runtime_checkable

from aisef2.arch.enums import BehaviorVerdict, Enforcement, SubjectAbsence
from aisef2.errors import InvariantError
from aisef2.product.contract import names_test_artefact
from aisef2.product.outcome import RESULT_TYPES, Executed, InvalidSpec, ProbeResult, Unrunnable, on_subject_absent
from aisef2.product.spec import ProductProofSpec

FULL_SHA = re.compile(r"[0-9a-f]{40}")
#: Enforcement levels in the order a requirement is met: a probe honours a requirement at or below its own level.
_RANK = {Enforcement.UNAVAILABLE: 0, Enforcement.PARTIAL: 1, Enforcement.FULL: 2}


@dataclass(frozen=True, slots=True)
class RevisionRef:
    """The revision a probe looks at: its full commit SHA and the harness's checkout of it (an absolute path, so what
    a probe sees never depends on the working directory it runs in)."""
    sha: str
    root: str

    def __post_init__(self) -> None:
        if not isinstance(self.sha, str) or not FULL_SHA.fullmatch(self.sha):
            raise InvariantError(f"a revision is named by its full 40-hex SHA, never abbreviated: {self.sha!r}")
        if not isinstance(self.root, str) or not os.path.isabs(self.root):
            raise InvariantError("a revision needs the harness's checkout of it, as an absolute path")


@dataclass(frozen=True, slots=True)
class ExecutionEnv:
    """What the harness gives a probe to run with. Built by the harness; carries no developer input."""
    interpreter: str
    timeout_s: float
    required_enforcement: Enforcement

    def __post_init__(self) -> None:
        if not isinstance(self.required_enforcement, Enforcement) or \
                self.required_enforcement is Enforcement.UNAVAILABLE:
            raise InvariantError("a run requires FULL or PARTIAL enforcement")
        if not isinstance(self.timeout_s, (int, float)) or isinstance(self.timeout_s, bool) or self.timeout_s <= 0:
            raise InvariantError("a probe timeout is a positive number of seconds")


class ObservationKind(Enum):
    HARNESS_FAILED = "HARNESS_FAILED"   # the probe could not look (§9)             -> UNRUNNABLE
    UNSUPPORTED = "UNSUPPORTED"         # the spec asks what this probe cannot see  -> INVALID_SPEC
    SUBJECT_ABSENT = "SUBJECT_ABSENT"   # it looked; the subject is not there (§10.2)
    OBSERVED = "OBSERVED"               # it looked at the subject and decided


@dataclass(frozen=True, slots=True)
class Observation:
    """What a probe saw. `verdict`, for SUBJECT_ABSENT, is what the spec's observable observes over the absent subject;
    whether it counts is the spec's declaration, applied by `classify_failure`, never by the probe."""
    kind: ObservationKind
    verdict: BehaviorVerdict | None = None
    detail: str = ""
    DECIDED: ClassVar[tuple] = (BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObservationKind):
            raise InvariantError("an observation has a typed kind")
        if self.kind in (ObservationKind.HARNESS_FAILED, ObservationKind.UNSUPPORTED):
            if self.verdict is not None:
                raise InvariantError(f"{self.kind.value} carries no verdict: the probe did not observe the subject")
            if not self.detail:
                raise InvariantError(f"{self.kind.value} says why")
        elif self.kind is ObservationKind.OBSERVED and self.verdict not in self.DECIDED:
            raise InvariantError("an observed subject yields SATISFIED or REFUTED")
        elif self.kind is ObservationKind.SUBJECT_ABSENT and self.verdict not in (None, *self.DECIDED):
            raise InvariantError("an observation over an absent subject is SATISFIED, REFUTED or none")


@runtime_checkable
class Probe(Protocol):
    id: str
    digest: str

    def enforcement(self) -> Enforcement: ...

    def harness_preconditions(self) -> tuple[str, ...]: ...

    def evaluate(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> ProbeResult: ...


class HarnessProbe:
    """Base for every probe: `evaluate` is fixed as classify_failure(spec, observe(...)). Subclasses implement
    `observe` and never construct a `ProbeResult`.

    `observation_class(spec)` names the class of observation a spec asks for (§9.1.1: calibration is per class), or
    None when this probe does not support it. It is harness API, not part of the frozen `Probe` protocol."""
    id: str
    digest: str

    def enforcement(self) -> Enforcement:
        raise NotImplementedError

    def harness_preconditions(self) -> tuple[str, ...]:
        raise NotImplementedError

    def observation_class(self, spec: ProductProofSpec) -> str | None:
        raise NotImplementedError

    def observe(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> Observation:
        raise NotImplementedError

    def evaluate(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> ProbeResult:
        return classify_failure(spec, self.observe(spec, at, env))


def classify_failure(spec: ProductProofSpec, observation: Observation) -> ProbeResult:
    """RFC §9, §10.2: the only mapping from what a probe saw to a `ProbeResult`.

    HARNESS_FAILED -> UNRUNNABLE; UNSUPPORTED -> INVALID_SPEC; OBSERVED -> EXECUTED + the observed verdict;
    SUBJECT_ABSENT -> `on_subject_absent`: REQUIRES_SUBJECT drops whatever the probe offered (no vacuous verdict),
    ABSENCE_IS_DECIDABLE takes the observable's verdict over the absent subject.
    """
    if not isinstance(observation, Observation):
        raise InvariantError("a probe reports a typed Observation")
    if observation.kind is ObservationKind.HARNESS_FAILED:
        return Unrunnable(observation.detail)
    if observation.kind is ObservationKind.UNSUPPORTED:
        return InvalidSpec(observation.detail)
    if observation.kind is ObservationKind.SUBJECT_ABSENT:
        decidable = SubjectAbsence(spec.probe_input["subject_absence"]) is SubjectAbsence.ABSENCE_IS_DECIDABLE
        return on_subject_absent(spec, observed=observation.verdict if decidable else None)
    return Executed(observation.verdict)


@dataclass(frozen=True, slots=True)
class ProbeRecord:
    """A probe result bound to what it answers and how it was obtained (§10.1: the journal records the result and the
    spec id; §24: the enforcement level enters every result)."""
    spec_id: str
    semantic_hash: str
    probe_id: str
    probe_digest: str
    revision: str
    enforcement: Enforcement
    result: ProbeResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, RESULT_TYPES):
            raise InvariantError("a probe record holds a typed ProbeResult")
        if not isinstance(self.enforcement, Enforcement):
            raise InvariantError("a probe record names the enforcement level it ran under")


def run_probe(probe: Probe, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> ProbeRecord:
    """Run `probe` on `spec` at `at`: refuse a spec bound elsewhere, refuse to degrade, bind the enforcement level."""
    if not isinstance(probe, Probe):
        raise InvariantError("not a probe")
    if not isinstance(spec, ProductProofSpec) or not isinstance(at, RevisionRef) or not isinstance(env, ExecutionEnv):
        raise InvariantError("a probe runs a ProductProofSpec at a RevisionRef in an ExecutionEnv")
    level = probe.enforcement()
    if not isinstance(level, Enforcement):
        raise InvariantError("a probe declares its real enforcement level")
    named = names_test_artefact(dict(spec.probe_input))
    if named:
        result = InvalidSpec(f"the probe input names a developer test artefact {named[0]!r}; refused (invariant IX)")
    elif (spec.probe_id, spec.probe_digest) != (probe.id, probe.digest):
        result = InvalidSpec(f"the spec is bound to {spec.probe_id}@{spec.probe_digest[:12]}, "
                             f"not {probe.id}@{probe.digest[:12]}")
    elif level is Enforcement.UNAVAILABLE or _RANK[level] < _RANK[env.required_enforcement]:
        result = Unrunnable(f"enforcement {level.value} cannot honour the required "
                            f"{env.required_enforcement.value}; refused, not degraded")
    else:
        result = probe.evaluate(spec, at, env)
        if not isinstance(result, RESULT_TYPES):
            raise InvariantError(f"{probe.id} returned {type(result).__name__}, not a ProbeResult")
    return ProbeRecord(spec.id, spec.semantic_hash, probe.id, probe.digest, at.sha, level, result)
