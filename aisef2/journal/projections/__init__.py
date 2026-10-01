"""RFC §21 (F11) — the six control-critical projections, a closed list: only these may be cited by a gate.

`project(journal, projection)` is what a gate reads: the projection folded from the journal itself, and only for a
`ControlProjection` member. A gate never reads a cache — not even a checked one (`fold.resume`), because a row
re-sealed over a wrong state with the right head is indistinguishable from an honest one: a cache is never
sufficient evidence. There is no seventh entry, and no reporting projection is reachable from here.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from aisef2.arch.enums import ControlProjection
from aisef2.journal.compat import Journal
from aisef2.journal.fold import Projection, ProjectionError, fold
from aisef2.journal.projections.budgets import Budgets
from aisef2.journal.projections.failure_owner import FailureOwner
from aisef2.journal.projections.qualification_counters import QualificationCounters
from aisef2.journal.projections.retry_target import RetryTarget
from aisef2.journal.projections.story_state import StoryState
from aisef2.journal.projections.terminal_state import TerminalState

PROJECTIONS: Mapping[ControlProjection, Projection] = MappingProxyType({
    ControlProjection.STORY_STATE: StoryState(),
    ControlProjection.FAILURE_OWNER: FailureOwner(),
    ControlProjection.BUDGETS: Budgets(),
    ControlProjection.RETRY_TARGET: RetryTarget(),
    ControlProjection.TERMINAL_STATE: TerminalState(),
    ControlProjection.QUALIFICATION_COUNTERS: QualificationCounters(),
})


def project(journal: Journal, projection: ControlProjection) -> Any:
    """The state a gate may cite: one of the six, folded from `journal`."""
    if not isinstance(projection, ControlProjection):
        raise ProjectionError(f"a gate cites one of the six control-critical projections (F11), by ControlProjection "
                              f"— not {projection!r}")
    return fold(PROJECTIONS[projection], journal.events)
