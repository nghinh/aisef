"""The typed contracts the orchestration path composes (WP-6.2). Every adapter answers with a typed object or raises
a typed refusal; no prose it produces is ever read for control (invariant VII). Confinement for the reviewer and the
scanner is a `ReadOnlyScope` the runner derives from the story's own checkout — there is no parameter that grants or
withholds it (§25)."""

from __future__ import annotations

import os
import pathlib
import stat
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from aisef2.errors import InvariantError
from aisef2.journal.format2 import OperationOutcome
from aisef2.probe.protocol import FULL_SHA
from aisef2.runtime.story_scope import Resource


class ProviderOutage(Exception):
    """The provider could not be reached or answered with an outage: owner PROVIDER (§25)."""


class CapabilityUnrunnable(Exception):
    """A review or security capability cannot run for a local or environment reason: ENVIRONMENT (§25, V2-005)."""


class ResourceUnavailable(Exception):
    """A resource the story needs could not be acquired: ENVIRONMENT (§17.1, V2-005)."""


@dataclass(frozen=True, slots=True)
class Implemented:
    """What the developer capability did: the candidate it produced (a full SHA) when it completed."""
    outcome: OperationOutcome
    candidate: str | None
    detail: str

    def __post_init__(self) -> None:
        if self.outcome not in (OperationOutcome.COMPLETED, OperationOutcome.FAILED):
            raise InvariantError("a developer answer is COMPLETED or FAILED")
        if (self.outcome is OperationOutcome.COMPLETED) != (self.candidate is not None):
            raise InvariantError("a completed developer answer names its candidate; a failed one names none")
        if self.candidate is not None and not FULL_SHA.fullmatch(self.candidate):
            raise InvariantError("a candidate is an immutable reference: a full SHA, never a branch or a tag")


@runtime_checkable
class Developer(Protocol):
    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str) -> Implemented: ...


@dataclass(frozen=True, slots=True)
class Finding:
    """A reviewer's or scanner's finding, typed: whether it blocks, and the independent authorities that corroborate
    it (a scanner, a human, a failing test) — a model review alone never blocks (§25, D-002)."""
    id: str
    blocking: bool
    corroborated_by: tuple[str, ...]

    @property
    def blocks(self) -> bool:
        return self.blocking and bool(self.corroborated_by)


@dataclass(frozen=True, slots=True)
class Reviewed:
    outcome: OperationOutcome
    findings: tuple[Finding, ...]
    detail: str


@dataclass(frozen=True, slots=True)
class ReadOnlyScope:
    """The reviewer's and the scanner's confinement: the story's own verification checkout, made read-only by the
    runner. Built only by `confine`; it carries no switch to widen it."""
    story_id: str
    root: str

    def read(self, rel: str) -> bytes:
        return (pathlib.Path(self.root) / rel).read_bytes()

    def files(self) -> tuple[str, ...]:
        root = pathlib.Path(self.root)
        return tuple(sorted(str(p.relative_to(root)).replace(os.sep, "/") for p in root.rglob("*")
                            if p.is_file() and ".git" not in p.parts))


def confine(story_id: str, checkout: str) -> ReadOnlyScope:
    """Derive the read-only scope from a checkout the story owns: every file and directory loses its write bits."""
    root = pathlib.Path(checkout)
    if not root.is_dir():
        raise InvariantError(f"a read-only scope is derived from an existing checkout, not {checkout!r}")
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        mode = stat.S_IMODE(p.stat().st_mode)
        os.chmod(p, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return ReadOnlyScope(story_id, str(root))


def unconfine(scope: ReadOnlyScope) -> None:
    """Give the write bits back so the checkout can be released."""
    for p in pathlib.Path(scope.root).rglob("*"):
        if ".git" in p.parts:
            continue
        os.chmod(p, stat.S_IMODE(p.stat().st_mode) | stat.S_IWUSR)


@runtime_checkable
class Reviewer(Protocol):
    def review(self, scope: ReadOnlyScope, criteria: tuple[str, ...]) -> Reviewed: ...


@dataclass(frozen=True, slots=True)
class Scanned:
    """What a scanner's typed report says once its tool ran: `executed` is the tool's own (§25: ran-and-found is
    EXECUTED); the findings come from the adapter's reading of its machine report, never from text."""
    executed: bool
    findings: tuple[Finding, ...]


@runtime_checkable
class Scanner(Protocol):
    name: str

    def argv(self, scope: ReadOnlyScope, report: str) -> tuple[str, ...]: ...

    def read(self, report: str, exit_code: int | None) -> Scanned: ...


class MergeOutcome(Enum):
    MERGED = "MERGED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class Merge:
    outcome: MergeOutcome
    revision: str | None
    conflicts: tuple[str, ...]

    def __post_init__(self) -> None:
        if (self.outcome is MergeOutcome.MERGED) != (self.revision is not None):
            raise InvariantError("a merge names its merged revision; a conflict names none")


@runtime_checkable
class Merger(Protocol):
    def base(self) -> str: ...

    def merge(self, candidate: str) -> Merge: ...

    def revert(self, merged: str) -> None: ...


@runtime_checkable
class Workspace(Protocol):
    def scratch(self, name: str) -> Resource: ...

    def checkout(self, name: str, revision: str) -> Resource: ...

    def move(self, checkout: Resource, revision: str) -> None: ...

    def diff(self, base: str, candidate: str) -> str: ...
