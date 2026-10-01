"""Invariant VIII — Memory Is Context, Never Evidence (RFC §4 row VIII; WP-5.5).

Anything an agent or a model reads about the harness — a prior-run summary, session history, introspection, notes,
a retrieved explanation, its own memory — is context. Only harness-produced typed records are evidence. This is the
evidence-origin boundary: `admit` accepts exactly the closed set of record types the harness itself constructs
(each a frozen dataclass sealed or validated at its construction site) and refuses everything else with an
`InvariantError` — a `Context`, a string, a mapping, a list, an object of any other type, including a subclass or a
look-alike dataclass claiming to be evidence. It is about admission, not about a model's internals: nothing here
inspects a model. `admit` fails closed: in a process where VIII is not armed it admits nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aisef2.arch.enums import InvariantId
from aisef2.errors import InvariantError
from aisef2.invariants.registry import require_armed

__all__ = ["Context", "EvidenceField", "admit", "harness_records"]


@dataclass(frozen=True)
class Context:
    """What an agent or model read or wrote about the harness. It carries no authority: context, never evidence."""
    text: str
    source: str     # where it came from: "model", "session-history", "prior-run-summary", "notes", "introspection"


def harness_records() -> tuple[type, ...]:
    """The closed set of harness-produced typed records an evidence field may hold."""
    from aisef2.control.budget import Charge
    from aisef2.journal.event import Event
    from aisef2.probe.protocol import ProbeRecord
    from aisef2.product.outcome import Executed, InvalidSpec, Unrunnable
    from aisef2.quality.adequacy import Assembly, EngineeringTestAdequacy
    from aisef2.quality.relevance import RelevanceResult
    from aisef2.quality.test_execution import ResultSet, RunnerReport, TestExecution
    from aisef2.quality.vacuity import VacuityResult
    from aisef2.runtime.capability import CapabilityIdentity
    from aisef2.runtime.runspec import RunSpec
    return (Event, ProbeRecord, Executed, Unrunnable, InvalidSpec, TestExecution, RunnerReport, ResultSet,
            RelevanceResult, VacuityResult, EngineeringTestAdequacy, Assembly, CapabilityIdentity, RunSpec, Charge)


def admit(value: Any) -> Any:
    """`value` itself when it is a harness-produced typed record; InvariantError otherwise (VIII)."""
    require_armed(InvariantId.VIII)
    if isinstance(value, Context):
        raise InvariantError(f"context from {value.source!r} is never evidence (VIII): only harness-produced typed "
                             "records enter an evidence field", invariant=InvariantId.VIII.value)
    if type(value) not in harness_records():
        raise InvariantError(f"{type(value).__name__} is not a harness-produced typed record: an evidence field admits "
                             "only those, never text, a mapping, a list or a look-alike (VIII)",
                             invariant=InvariantId.VIII.value)
    return value


@dataclass(frozen=True)
class EvidenceField:
    """A typed evidence field: what it holds was admitted on construction."""
    value: Any

    def __post_init__(self) -> None:
        admit(self.value)
