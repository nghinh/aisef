"""The invariant registry (`aisef/invariants.yaml`) as data.

The registry is the contract the Assurance Kernel is checked against
(`docs/ASSURANCE-KERNEL.md`, systematic hardening v1 Phase 1). It is written in a
deliberately small YAML subset so this stdlib-only package can read it without a
YAML library: two-space indentation, `key: value` mappings, `- item` lists (a
list item may itself be a mapping written on the following lines), and plain or
double-quoted scalars. Nothing else is accepted; a file that needs more has
outgrown the registry format and the loader says so instead of guessing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "invariants.yaml"
#: `key:` followed by a space or the end of the line — what makes a list item a mapping.
_KEY_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:(\s|$)")
STATUSES = ("PROVEN", "PARTIAL", "MISSING")
FIELDS = ("invariant_id", "domain", "statement", "why", "severity_if_violated", "enforcement_points",
          "deterministic_tests", "model_tests", "fault_injection_tests", "linked_defects", "status")


class RegistryError(ValueError):
    """The registry file is outside the accepted subset or violates the schema."""


@dataclass
class Invariant:
    invariant_id: str
    domain: str
    statement: str
    why: str
    severity_if_violated: str
    enforcement_points: list[str] = field(default_factory=list)
    deterministic_tests: list[str] = field(default_factory=list)
    model_tests: list[str] = field(default_factory=list)
    fault_injection_tests: list[str] = field(default_factory=list)
    linked_defects: list[str] = field(default_factory=list)
    status: str = "MISSING"

    @property
    def family(self) -> str:
        seg = self.invariant_id.split("-")[1].split(".")[0]
        return seg[:1]            # an owner-named id (INV-TDD-NOP-PROOF) sits in the family its first letter names


# ------------------------------------------------------------ a YAML subset

def _scalar(raw: str):
    s = raw.strip()
    if s.startswith('"'):
        return json.loads(s)
    if s in ("[]",):
        return []
    if s in ("null", "~"):
        return None
    return s


def _parse_block(lines: list[str], i: int, indent: int):
    """Parse a mapping or list starting at line ``i`` with the given indent.
    Returns (value, next_index)."""
    if i >= len(lines):
        return {}, i
    first = lines[i][indent:]
    if first.startswith("- "):
        out: list = []
        while i < len(lines):
            line = lines[i]
            cur = len(line) - len(line.lstrip(" "))
            if cur < indent or not line.strip():
                if not line.strip():
                    i += 1
                    continue
                break
            if cur != indent or not line[indent:].startswith("- "):
                raise RegistryError(f"line {i + 1}: expected a list item at indent {indent}")
            body = line[indent + 2:]
            if _KEY_LINE.match(body):
                # a mapping written as `- key: value` with the rest on following lines
                # (a scalar such as `tests/x.py::Class` also contains colons; only a bare key qualifies)
                item, j = _parse_block([" " * (indent + 2) + body] + lines[i + 1:], 0, indent + 2)
                out.append(item)
                i = i + 1 + (j - 1)
            else:
                out.append(_scalar(body))
                i += 1
        return out, i
    out_map: dict = {}
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        cur = len(line) - len(line.lstrip(" "))
        if cur < indent:
            break
        if cur != indent:
            raise RegistryError(f"line {i + 1}: unexpected indent {cur} (expected {indent})")
        body = line[indent:]
        if body.startswith("- "):
            break
        key, sep, rest = body.partition(":")
        if not sep:
            raise RegistryError(f"line {i + 1}: expected `key: value`")
        key = key.strip()
        if rest.strip():
            out_map[key] = _scalar(rest)
            i += 1
            continue
        # value is a nested block on the following lines
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or (len(lines[j]) - len(lines[j].lstrip(" "))) <= indent:
            out_map[key] = []
            i = j
            continue
        child_indent = len(lines[j]) - len(lines[j].lstrip(" "))
        value, i = _parse_block(lines, j, child_indent)
        out_map[key] = value
    return out_map, i


def parse(text: str) -> dict:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    if any("\t" in ln for ln in lines):
        raise RegistryError("tabs are not part of the registry subset")
    value, _ = _parse_block(lines, 0, 0)
    if not isinstance(value, dict):
        raise RegistryError("the registry must be a mapping at top level")
    return value


# ------------------------------------------------------------ the registry

def load(path: Path | str = REGISTRY) -> list[Invariant]:
    data = parse(Path(path).read_text(encoding="utf-8"))
    rows = data.get("invariants")
    if not isinstance(rows, list) or not rows:
        raise RegistryError("`invariants` must be a non-empty list")
    out: list[Invariant] = []
    seen: set[str] = set()
    for n, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise RegistryError(f"invariant #{n} is not a mapping")
        missing = [f for f in FIELDS if f not in row]
        if missing:
            raise RegistryError(f"invariant #{n} ({row.get('invariant_id', '?')}) lacks {missing}")
        if row["status"] not in STATUSES:
            raise RegistryError(f"{row['invariant_id']}: status must be one of {STATUSES}")
        if row["invariant_id"] in seen:
            raise RegistryError(f"duplicate invariant_id {row['invariant_id']}")
        seen.add(row["invariant_id"])
        out.append(Invariant(**{k: row[k] for k in FIELDS}))
    return out


def by_family(invs: list[Invariant]) -> dict[str, list[Invariant]]:
    fam: dict[str, list[Invariant]] = {}
    for inv in invs:
        fam.setdefault(inv.family, []).append(inv)
    return fam


def render_markdown(invs: list[Invariant], *, families: dict[str, str]) -> str:
    """`docs/INVARIANTS.md` from the registry — one section per family, one table row per invariant."""
    counts = {s: sum(1 for i in invs if i.status == s) for s in STATUSES}
    out = ["# AISEF invariants (systematic hardening v1, Phase 1)", "",
           "Rendered from `aisef/invariants.yaml` by `validation/render_hardening_docs.py` — edit the YAML, not this file. "
           "An invariant is PROVEN when deterministic, model and fault tests exist and are green; PARTIAL when some "
           "enforcement or test is missing; MISSING when the kernel does not enforce it yet. Test names are the "
           "regression that would go red if the invariant broke; `(RED)` marks an expected-failure reproducer of "
           "a registered, unfixed defect.", "",
           f"**Status count:** {counts['PROVEN']} PROVEN · {counts['PARTIAL']} PARTIAL · {counts['MISSING']} MISSING "
           f"of {len(invs)} invariants.", ""]
    for fam, rows in by_family(invs).items():
        out += [f"## {fam}. {families.get(fam, fam)}", "",
                "| id | statement | why | severity | enforcement | deterministic tests | model tests | fault tests | defects | status |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for inv in rows:
            cell = lambda xs: "<br>".join(f"`{x}`" for x in xs) if xs else "—"  # noqa: E731
            out.append("| " + " | ".join([
                inv.invariant_id, inv.statement.replace("|", "\\|"), inv.why.replace("|", "\\|"), inv.severity_if_violated,
                cell(inv.enforcement_points), cell(inv.deterministic_tests), cell(inv.model_tests),
                cell(inv.fault_injection_tests), ", ".join(inv.linked_defects) or "—", f"**{inv.status}**",
            ]) + " |")
        out.append("")
    return "\n".join(out)
