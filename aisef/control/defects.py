"""Canonical defect register — what is outstanding now, at what severity.

`docs/DEFECT-REGISTER.json` is the repository-local, version-controlled answer
to closure criterion **G2.3** (`docs/PROJECT-CLOSURE-GATE.md` §5, owner ruling
6): *zero OPEN P0/P1 defects*.  GitHub Issues are explicitly **not** canonical
— closure must not depend on an external tracker being reachable — so the file
lives in the repository, and this module is its only reader.  The closure
probe and any report go through here, so the gate and the prose cannot give
two answers to one question.

Boundary with `docs/FAILURE-TAXONOMY.md`
---------------------------------------

* the taxonomy answers *what went wrong and what did we learn* — 133 closed
  rows of symptom, root cause, lesson, fix;
* this register answers *what is outstanding now, at what severity*.

A defect sits in the register while open and in the taxonomy once understood,
and a register row references its taxonomy row by id (``taxonomy``) instead of
restating it.  Nothing is copied either way.  A third kind of item — work that
is *wanted* but whose absence is not a wrong result, the contract's §7
POST_CLOSE list and `docs/ROADMAP-POST-1.0.md` — is not a defect and does not
belong here; entering it would make two lists answer "what is outstanding" and
they would drift.

One severity scale, by reference
--------------------------------

P0–P3 are defined in `docs/EXTERNAL-VALIDATION-v1.1.0.md` §"Finding
classification" (P0 includes **incorrect gate result**).  They are not
redefined here, and a register naming another source — or editing which
severities block — is an error rather than obeyed: two severity scales in one
project is how they drift apart.

Absent is not empty
-------------------

A missing file raises `RegisterAbsent`, which closure maps to `UNRUNNABLE`
(blocks); a present file with no rows reads as an empty register, which is a
real PASS.  Conflating them is the failure the whole contract guards against,
so they are different exception/return shapes and not one falsy value.

Validation is on read, and it is strict.  An unknown severity, a missing id, a
duplicate id or a mistyped field name raises — never a silently skipped row.  A
register that drops the one row nobody could parse reads greener than no
register at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterable

from .gate import CHECK_NAMES

#: Repository-relative, like `conformance.REPORT_PATH`.
PATH = Path("docs") / "DEFECT-REGISTER.json"
SEVERITY_SOURCE = "docs/EXTERNAL-VALIDATION-v1.1.0.md#finding-classification"
SEVERITIES = ("P0", "P1", "P2", "P3")
#: G2.3 PASS condition: no OPEN row at these severities.
BLOCKING = ("P0", "P1")
STATUSES = ("OPEN", "CLOSED")
REQUIRED = ("id", "severity", "status", "title", "evidence")


class RegisterError(ValueError):
    """The register is present but cannot be read as a register."""


class RegisterAbsent(FileNotFoundError):
    """There is no register file — UNRUNNABLE at closure, not an empty PASS."""


@dataclass(frozen=True)
class Defect:
    """One outstanding defect.  ``introduced``/``fixed`` are a version or a
    commit **where known**, and empty when they are not — a guess recorded as a
    fact is worse than a blank."""

    id: str
    severity: str
    status: str
    title: str
    introduced: str = ""
    fixed: str = ""
    evidence: str = ""
    #: The `gate.CHECK_NAMES` entry this defect bears on, when it bears on one.
    #: Validated against that table so a row cannot name a check that does not
    #: exist, and so a caller asking a narrower question (is this a false pass
    #: in a *deterministic* check?) reads `gate.CHECK_KIND`, not a second table.
    check: str = ""
    #: `docs/FAILURE-TAXONOMY.md` row id — a pointer, never a copy.
    taxonomy: int | None = None
    notes: str = ""

    @property
    def blocks(self) -> bool:
        return self.status == "OPEN" and self.severity in BLOCKING


_FIELDS = frozenset(f.name for f in fields(Defect))


def read(path: Path | str = PATH) -> tuple[Defect, ...]:
    """Rows of the register, ordered by (severity, id) whatever the file order.

    Deterministic on purpose: the order a hand-editor happens to append in must
    not change what a report prints or what a digest covers.
    """
    p = Path(path)
    if not p.is_file():
        raise RegisterAbsent(
            f"{p}: no defect register — closure reads this as UNRUNNABLE, "
            "which is not the same fact as a register with nothing open")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegisterError(f"{p.name}: not readable as JSON — {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("defects"), list):
        raise RegisterError(f"{p.name}: expected an object carrying a `defects` list")
    scale = raw.get("severity_scale")
    if (not isinstance(scale, dict) or scale.get("source") != SEVERITY_SOURCE
            or tuple(scale.get("blocking") or ()) != BLOCKING):
        raise RegisterError(
            f"{p.name}: `severity_scale` must be source={SEVERITY_SOURCE!r} "
            f"blocking={list(BLOCKING)} — the scale is reused by reference, not redefined here")
    out: dict[str, Defect] = {}
    for i, entry in enumerate(raw["defects"]):
        d = _row(p.name, i, entry)
        if d.id in out:
            raise RegisterError(f"{p.name}: duplicate defect id {d.id!r} — an id names one defect, for good")
        out[d.id] = d
    return tuple(sorted(out.values(), key=lambda d: (d.severity, d.id)))


def blocking(rows: Iterable[Defect]) -> tuple[Defect, ...]:
    """The rows that fail G2.3: OPEN, at a blocking severity."""
    return tuple(d for d in rows if d.blocks)


def _row(name: str, i: int, entry) -> Defect:
    where = f"{name}: defects[{i}]"
    if not isinstance(entry, dict):
        raise RegisterError(f"{where}: expected an object")
    unknown = sorted(set(entry) - _FIELDS)
    if unknown:
        raise RegisterError(
            f"{where}: unknown field(s) {unknown} — a mistyped field name must not drop its value")
    for f in REQUIRED:
        if not str(entry.get(f) or "").strip():
            raise RegisterError(f"{where}: `{f}` is required")
    did = str(entry["id"])
    if entry["severity"] not in SEVERITIES:
        raise RegisterError(
            f"{where} ({did}): unknown severity {entry['severity']!r} — "
            f"the scale is {list(SEVERITIES)}, from {SEVERITY_SOURCE}")
    if entry["status"] not in STATUSES:
        raise RegisterError(f"{where} ({did}): unknown status {entry['status']!r} — one of {list(STATUSES)}")
    check = str(entry.get("check") or "")
    if check and check not in CHECK_NAMES:
        raise RegisterError(f"{where} ({did}): `check` {check!r} is not a gate check")
    if entry["status"] == "OPEN" and str(entry.get("fixed") or "").strip():
        raise RegisterError(f"{where} ({did}): OPEN yet carries `fixed` — one of the two is wrong")
    tax = entry.get("taxonomy")
    if tax is not None and (isinstance(tax, bool) or not isinstance(tax, int) or tax < 1):
        raise RegisterError(f"{where} ({did}): `taxonomy` must be a FAILURE-TAXONOMY.md row id")
    return Defect(**entry)
