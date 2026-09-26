"""The explicit compatibility / migration seam (WP-6.2; removed by WP-6.3). A story planned from V1 proof modes reaches
the V2 path only through here: each mode is resolved against the generated migration table (WP-6.1, RFC §31), and a
row the table leaves HUMAN_DECLARATION_REQUIRED is refused unless a typed SubjectAbsence declaration is given for it.
The refusal happens before the story begins — no journal event, no provider request. Nothing else in `aisef2` reads
the table or a V1 name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence

HUMAN_DECLARATION_REQUIRED = "HUMAN_DECLARATION_REQUIRED"


class SeamRefusal(Exception):
    """A legacy criterion cannot enter the V2 path: the table has no row, or the row needs a declaration."""

    def __init__(self, criterion_id: str, mode: str, reason: str) -> None:
        super().__init__(f"{criterion_id} ({mode}): {reason}")
        self.criterion_id, self.mode, self.reason = criterion_id, mode, reason


@dataclass(frozen=True, slots=True)
class Legacy:
    criterion_id: str
    mode: str
    role: ObligationRole
    polarity: Polarity
    subject_absence: SubjectAbsence


def resolve(criterion_id: str, mode: str, table: Mapping, declaration: SubjectAbsence | None) -> Legacy:
    """One V1 mode through the table: role and polarity from the row, absence only from the typed declaration."""
    row = next((r for r in table["rows"] if r["v1_mode"] == mode), None)
    if row is None:
        raise SeamRefusal(criterion_id, mode, "no row in the migration table")
    if row["subject_absence"] == HUMAN_DECLARATION_REQUIRED or row["reason"] == HUMAN_DECLARATION_REQUIRED:
        if not isinstance(declaration, SubjectAbsence):
            raise SeamRefusal(criterion_id, mode, HUMAN_DECLARATION_REQUIRED)
        absence = declaration
    else:
        absence = SubjectAbsence(row["subject_absence"])
    return Legacy(criterion_id, mode, ObligationRole(row["obligation_role"]), Polarity(row["polarity"]), absence)


def admit_legacy(modes: Mapping[str, str], table: Mapping | None,
                 declarations: Mapping[str, SubjectAbsence]) -> tuple[Legacy, ...]:
    """Every legacy criterion of a story, all resolved or none: the first refusal stops the story before it begins."""
    if not modes:
        return ()
    if table is None:
        raise SeamRefusal(next(iter(modes)), modes[next(iter(modes))], "no migration table")
    return tuple(resolve(cid, mode, table, declarations.get(cid)) for cid, mode in sorted(modes.items()))
