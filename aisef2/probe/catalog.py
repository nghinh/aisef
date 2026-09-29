"""WP-2.0.1 — the harness-owned probe catalog: the one place a probe implementation is registered for Cycle 2.

Not part of the frozen `Probe` protocol (F5) and not on the orchestration path: `story_runner` keeps its own probe
factory, and nothing in control imports this module. Qualification and admission harnesses build their
`ProbeRegistry` (PROBE-META-1) and their `SubjectKind -> Probe` catalogue from `CATALOG`, so a probe that is not
registered here has no observation class, no calibration and no admission — fail-closed in both directions
(Q0 rule PROBE_CATALOG_CLOSURE, validation/v2/probe_static_checks.py).

Two facts the catalog binds mechanically:

* **one active probe per subject kind** — the frozen compiler contract (F4) binds a contract to the one probe declared
  for its subject kind (`compile_spec(..., probes: Mapping[SubjectKind, ProbeRef])`). A second probe identity for the
  same kind (owner DECISION-6) supersedes as the *active* entry; the earlier identity stays registered, so evidence
  bound to it keeps its observation class (`registry()`) while nothing new compiles against it (`catalogue()`).
* **DESIGN-CHECK-1** — a probe whose subject runs in a process of its own (`child_of_harness`) never carries its
  protocol on the subject's stdout: the entry must declare a dedicated channel, and the declaration is refused at
  construction otherwise.

Every declaration here is a fact about the probe's *source* that a Q0 rule reads (the child script's channel, the
stimulus shape that scopes the closed-vocabulary rules); a wrong declaration is caught by the rule it scopes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from aisef2.arch.enums import SubjectKind
from aisef2.errors import InvariantError
from aisef2.probe import cli_invocation as ci
from aisef2.probe import process_effect as pe
from aisef2.probe import python_callable as pc
from aisef2.probe.protocol import Probe, ProbeMetadata, ProbeRegistry

#: Where the subject runs relative to the harness script the probe launches.
SUBJECT_PROCESS = ("in_harness_process", "child_of_harness")
#: How the harness script reports READY / DISPATCHED / RESULT to the probe.
PROTOCOL_CHANNEL = ("captured_stdout", "fd3", "marker_file")
#: The shape of a spec's stimulus for this probe; "scenario" scopes the closed-vocabulary rules.
STIMULUS_SHAPE = ("none", "call", "invocation", "scenario")
_ID = re.compile(r"probe\.[a-z][a-z0-9_]*")
_HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    probe_id: str
    probe_digest: str
    subject_kind: SubjectKind
    classes: tuple[str, ...]
    metadata: ProbeMetadata
    factory: Callable[..., Probe]
    module: str            # repository-relative source of the probe
    fixture_root: str      # tests/v2/fixtures/calibration/<fixture_root>/<class>/{positive,negative}/
    subject_process: str
    protocol_channel: str
    stimulus_shape: str
    cycle: int
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.probe_id, str) or not _ID.fullmatch(self.probe_id):
            raise InvariantError(f"a probe id is probe.<name>: {self.probe_id!r}")
        if not isinstance(self.probe_digest, str) or not _HEX64.fullmatch(self.probe_digest):
            raise InvariantError(f"{self.probe_id}: a probe digest is 64 hex characters")
        if not isinstance(self.subject_kind, SubjectKind):
            raise InvariantError(f"{self.probe_id}: subject_kind is a SubjectKind")
        if not self.classes or len(set(self.classes)) != len(self.classes) \
                or not all(isinstance(c, str) and c for c in self.classes):
            raise InvariantError(f"{self.probe_id}: observation classes are a non-empty tuple of distinct names")
        if not isinstance(self.metadata, ProbeMetadata) \
                or (self.metadata.probe_id, self.metadata.probe_digest) != (self.probe_id, self.probe_digest):
            raise InvariantError(f"{self.probe_id}: the registered metadata carries this entry's id and digest")
        if not callable(self.factory):
            raise InvariantError(f"{self.probe_id}: the factory constructs the probe")
        if self.subject_process not in SUBJECT_PROCESS or self.protocol_channel not in PROTOCOL_CHANNEL \
                or self.stimulus_shape not in STIMULUS_SHAPE:
            raise InvariantError(f"{self.probe_id}: subject_process, protocol_channel and stimulus_shape are closed "
                                 "vocabularies")
        if self.subject_process == "child_of_harness" and self.protocol_channel == "captured_stdout":
            raise InvariantError(f"{self.probe_id}: DESIGN-CHECK-1 — a subject that owns stdout cannot share it with "
                                 "the harness protocol; declare fd3 or marker_file")
        if not isinstance(self.cycle, int) or isinstance(self.cycle, bool) or self.cycle < 1:
            raise InvariantError(f"{self.probe_id}: cycle is a positive integer")


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(pc.PROBE_ID, pc.DIGEST, SubjectKind.PYTHON_CALLABLE, pc.CLASSES, pc.METADATA, pc.PythonCallableProbe,
                 "aisef2/probe/python_callable.py", "python_callable", "in_harness_process", "captured_stdout",
                 "call", 1),
    CatalogEntry(ci.PROBE_ID, ci.DIGEST, SubjectKind.CLI_INVOCATION, ci.CLASSES, ci.METADATA, ci.CliInvocationProbe,
                 "aisef2/probe/cli_invocation.py", "cli_invocation", "child_of_harness", "marker_file", "invocation", 2),
    CatalogEntry(pe.PROBE_ID, pe.DIGEST, SubjectKind.PROCESS_EFFECT, pe.CLASSES, pe.METADATA, pe.ProcessEffectProbe,
                 "aisef2/probe/process_effect.py", "process_effect", "child_of_harness", "marker_file", "scenario", 2),
)


def problems_of(entries: tuple[CatalogEntry, ...]) -> list[str]:
    """What makes a set of entries not a catalog: a repeated identity, or a subject kind with two active probes."""
    out = []
    seen: set[tuple[str, str]] = set()
    for e in entries:
        key = (e.probe_id, e.probe_digest)
        if key in seen:
            out.append(f"{e.probe_id}@{e.probe_digest[:12]} is registered twice")
        seen.add(key)
    for kind in SubjectKind:
        active = [e.probe_id for e in entries if e.active and e.subject_kind is kind]
        if len(active) > 1:
            out.append(f"{kind.value}: {len(active)} active probes ({', '.join(active)}); the compiler binds one "
                       "probe per subject kind (F4)")
    return out


def _closed(entries: tuple[CatalogEntry, ...]) -> tuple[CatalogEntry, ...]:
    problems = problems_of(entries)
    if problems:
        raise InvariantError("; ".join(problems))
    return entries


_closed(CATALOG)


def registry(entries: tuple[CatalogEntry, ...] = CATALOG) -> ProbeRegistry:
    """Every registered identity, active or superseded: a spec bound to any of them resolves its observation class."""
    return ProbeRegistry([e.metadata for e in _closed(entries)])


def active(entries: tuple[CatalogEntry, ...] = CATALOG) -> dict[SubjectKind, CatalogEntry]:
    return {e.subject_kind: e for e in _closed(entries) if e.active}


def catalogue(entries: tuple[CatalogEntry, ...] = CATALOG, **harness) -> dict[SubjectKind, Probe]:
    """The compiler's and the admission engine's catalogue: the one active probe per subject kind, constructed with
    the harness-owned keyword arguments (`on_range`, `scratch`, ...) every probe of this catalog accepts."""
    return {kind: e.factory(**harness) for kind, e in active(entries).items()}


def probes_by_id(entries: tuple[CatalogEntry, ...] = CATALOG, **harness) -> dict[str, Probe]:
    """Every registered probe by id, for story admission (which resolves a spec's probe by id)."""
    return {e.probe_id: e.factory(**harness) for e in _closed(entries)}


def entry_for(module: str, entries: tuple[CatalogEntry, ...] = CATALOG) -> CatalogEntry | None:
    return next((e for e in entries if e.module == module), None)
