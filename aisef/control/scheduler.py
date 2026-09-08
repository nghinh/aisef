"""Story execution scheduler: epics run sequentially, stories within an epic
run in parallel waves.

Epics are **always sequential** — a later epic typically depends on schemas,
APIs, or components created by an earlier one, so overlapping epics invites
silent breakage.

Within an epic, stories are grouped into **waves**. Stories enter the same wave
when both conditions hold:

1. **No mutual dependency** — all ``depends_on`` are satisfied by prior waves.
2. **No write-scope overlap** — two stories that both modify
   ``src/models/user.py`` would overwrite each other if run in parallel.

Condition 2 is often forgotten and is the hardest-to-trace failure mode: the
dependency graph looks clean, but two stories still overwrite each other
because they touch the same file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


class CycleError(ValueError):
    """Dependency graph contains a cycle — cannot schedule."""


class UnknownDependencyError(ValueError):
    """Story depends on an id that does not exist."""


#: Statuses treated as done — no need to re-run (supports resume).
DONE_STATUSES = frozenset({"done", "skipped"})


@dataclass(frozen=True)
class Story:
    id: str
    epic_id: str = ""
    title: str = ""
    depends_on: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    status: str = "pending"

    @property
    def is_done(self) -> bool:
        return self.status in DONE_STATUSES


def _norm(p: str) -> PurePosixPath:
    return PurePosixPath(p.strip().strip("/"))


def paths_overlap(a: str, b: str) -> bool:
    """True when two paths touch the same directory-tree region.

    Compared by **path segments**, not string prefix: ``src/api`` and
    ``src/apidocs`` are distinct regions even though one is a string prefix of
    the other.
    """
    pa, pb = _norm(a), _norm(b)
    return pa == pb or pa in pb.parents or pb in pa.parents


def scopes_conflict(a: Story, b: Story) -> bool:
    """True when two stories write to overlapping regions.

    A story without ``write_scope`` is treated as **touching everything** — safer
    than guessing it is harmless.
    """
    if not a.write_scope or not b.write_scope:
        return True
    return any(paths_overlap(x, y) for x in a.write_scope for y in b.write_scope)


def _validate(stories: list[Story]) -> dict[str, Story]:
    by_id: dict[str, Story] = {}
    for s in stories:
        if s.id in by_id:
            raise ValueError(f"duplicate story id: {s.id}")
        by_id[s.id] = s

    for s in stories:
        for dep in s.depends_on:
            if dep not in by_id:
                raise UnknownDependencyError(f"{s.id} depends on {dep!r} which does not exist")
    return by_id


def build_waves(stories: list[Story], *, max_parallel: int | None = None) -> list[list[Story]]:
    """Split stories of **one** epic into parallel execution waves.

    Stories already ``done`` are treated as satisfied constraints and excluded
    from the result — so resuming after a mid-run stop picks up where it left
    off.

    ``max_parallel`` caps the number of stories per wave, to stay within machine
    capacity or model call limits.
    """
    if max_parallel is not None and max_parallel < 1:
        raise ValueError("max_parallel must be >= 1")

    by_id = _validate(stories)
    satisfied = {s.id for s in stories if s.is_done}
    remaining = [s for s in stories if not s.is_done]

    waves: list[list[Story]] = []
    while remaining:
        ready = [s for s in remaining if all(d in satisfied for d in s.depends_on)]
        if not ready:
            stuck = sorted(s.id for s in remaining)
            raise CycleError(f"dependency cycle or deadlock among: {', '.join(stuck)}")

        # Greedy assignment: accept a story if its write scope does not conflict
        # with already-picked stories. Sorting by id keeps results stable across runs.
        wave: list[Story] = []
        for s in sorted(ready, key=lambda s: s.id):
            if max_parallel is not None and len(wave) >= max_parallel:
                break
            if any(scopes_conflict(s, picked) for picked in wave):
                continue  # deferred to a later wave
            wave.append(s)

        waves.append(wave)
        chosen = {s.id for s in wave}
        satisfied |= chosen
        remaining = [s for s in remaining if s.id not in chosen]

    return waves


@dataclass
class EpicPlan:
    """Execution plan for a single epic."""

    epic_id: str
    waves: list[list[Story]] = field(default_factory=list)

    @property
    def story_count(self) -> int:
        return sum(len(w) for w in self.waves)

    @property
    def max_width(self) -> int:
        """Maximum number of parallel stories in any single wave."""
        return max((len(w) for w in self.waves), default=0)


def plan_epics(
    stories: list[Story],
    *,
    max_parallel: int | None = None,
    epic_order: list[str] | None = None,
) -> list[EpicPlan]:
    """Schedule the entire project: epics sequential, waves parallel within each.

    Cross-epic dependencies are considered satisfied when the target epic
    precedes the current one in execution order — that is exactly why epics
    must be sequential.
    """
    _validate(stories)

    groups: dict[str, list[Story]] = {}
    for s in stories:
        groups.setdefault(s.epic_id, []).append(s)

    order = epic_order or sorted(groups)
    unknown = [e for e in order if e not in groups]
    if unknown:
        raise ValueError(f"epic has no stories: {', '.join(unknown)}")

    plans: list[EpicPlan] = []
    for epic_id in order:
        local = groups[epic_id]
        local_ids = {s.id for s in local}
        # Cross-epic dependencies are guaranteed by epic ordering; remove them
        # from the local graph so they are not treated as deadlocks.
        trimmed = [
            Story(
                id=s.id,
                epic_id=s.epic_id,
                title=s.title,
                depends_on=tuple(d for d in s.depends_on if d in local_ids),
                write_scope=s.write_scope,
                status=s.status,
            )
            for s in local
        ]
        plans.append(EpicPlan(epic_id, build_waves(trimmed, max_parallel=max_parallel)))
    return plans


def describe(plans: list[EpicPlan]) -> str:
    """Human-readable execution schedule summary."""
    lines = []
    for p in plans:
        if not p.waves:
            lines.append(f"{p.epic_id}: (done)")
            continue
        lines.append(f"{p.epic_id}: {p.story_count} stories · {len(p.waves)} waves · max width {p.max_width}")
        for i, wave in enumerate(p.waves, 1):
            lines.append(f"  wave {i}: " + ", ".join(s.id for s in wave))
    return "\n".join(lines)
