"""WP-6.1 — the generated V1 proof-mode -> V2 migration table, with a `--check` twin (RFC §31; an adapter under F6).

V1 judged every acceptance criterion by one per-criterion *proof mode* (`aisef/control/obligation.py::Mode`:
`CHANGE_REQUIRED`, `PRESERVE_REQUIRED`, `NEGATIVE_INVARIANT`). V2 splits that label into three independent
declarations: the plan's `ObligationRole` (§11), the contract's `Polarity` (§7) and the contract's `SubjectAbsence`
(§7, §10.2). This module derives, from the frozen V1 kernel read as source, what each V1 mode determines and what it
never carried — and it never fills the gap:

* `ObligationRole` follows from the mode's transition table (`EXPECTED`): V1 RED at the parent is
  `UNSATISFIED_AT_PARENT`, GREEN is `SATISFIED_AT_PARENT`, and the role is the inverse of the frozen
  `EXPECTED_AT_PARENT` (§11 / §13).
* `Polarity` follows from the mode's own definition in the kernel docstring — `NEGATIVE_INVARIANT` is defined as a
  prohibition, the other two as a behaviour. The quote is verified against the V1 source on every run, and the table
  records that V1 never checked a criterion's test against it: the contract author declares polarity (F4).
* `SubjectAbsence` is **never inferred** — not from polarity, the mode's name, its transition, wording, history or a
  default. V1 declared none, so every row is `HUMAN_DECLARATION_REQUIRED` and `UNMAPPED` until an explicit typed
  declaration exists. The only path to `MAPPED` is such a declaration (`declarations=`); none exists in cycle 1.

An unknown V1 mode is a failure, never a defaulted row; a historical alias resolves only through the explicit
`ALIASES` table (exact key, no case folding, no fuzzy match); the outputs are byte-identical whatever the discovery
order. The inventory (§4 of the authorization) is mechanical: every representation of a V1 proof mode still in the
repository — enums, constants, config, prompts, serialized evidence forms, policy records, parser compatibility — is
discovered and classified by rule; a representation no rule classifies fails the generation.

    python -P validation/v2/gen_migration_table.py            # write the table and the document
    python -P validation/v2/gen_migration_table.py --check    # exit 1 on drift, a hand edit, an unknown mode, a defaulted row
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole, ParentExpectation, Polarity, SubjectAbsence  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT  # noqa: E402

V1_OBLIGATION = "aisef/control/obligation.py"
V1_NORMALIZE = "aisef/control/normalize.py"
DOC_REL = "docs/implementation/v2/v1-proofmode-migration.md"
TABLE_REL = "closure-evidence/v2/P6-MIGRATION-TABLE.json"

MAPPED, UNMAPPED = "MAPPED", "UNMAPPED"
HUMAN_DECLARATION_REQUIRED = "HUMAN_DECLARATION_REQUIRED"
UNKNOWN_V1_MODE = "UNKNOWN_V1_MODE"
#: inventory classifications (authorization §4) — a closed set; anything else fails the generation
ACTIVE, HISTORICAL, ALIAS, UNMAPPED_REPR, NOT_A_MODE = ("ACTIVE_V1_MODE", "HISTORICAL_ONLY", "ALIAS", "UNMAPPED",
                                                        "NOT_A_PROOF_MODE")
CLASSIFICATIONS = (ACTIVE, HISTORICAL, ALIAS, UNMAPPED_REPR, NOT_A_MODE)
DIMENSIONS = ("obligation_role", "polarity", "subject_absence")
#: typed provenance of a V2 field's value — read by `problems`, so a value with no source is a defaulted row
V1_TRANSITION, V1_DEFINITION, HUMAN_DECLARATION, NO_SOURCE = "V1_TRANSITION", "V1_DEFINITION", "HUMAN_DECLARATION", "NONE"


class MigrationError(Exception):
    """The V1 input cannot be read as the generator requires: fail closed, generate nothing."""


class Kind(Enum):
    """What a V1 mode's definition says a criterion states — the only carrier of polarity V1 ever had."""
    BEHAVIOUR = "BEHAVIOUR"
    PROHIBITION = "PROHIBITION"


@dataclass(frozen=True)
class Definition:
    kind: Kind
    quote: str    # verbatim from the kernel docstring line that defines the mode; `read_v1` verifies it is there


#: Each V1 mode's definition, transcribed as a typed fact and cited; a quote that is not on the mode's definition
#: line of the frozen kernel fails the generation. V1's planner prompt (`aisef/phases/plan.py`) says the same:
#: "NEGATIVE_INVARIANT — a prohibition ... Never write such a criterion as if it had to fail first."
V1_DEFINITIONS: dict[str, Definition] = {
    "CHANGE_REQUIRED": Definition(Kind.BEHAVIOUR, "this story contributes the behaviour"),
    "PRESERVE_REQUIRED": Definition(Kind.BEHAVIOUR, "this story must not break what it inherits"),
    "NEGATIVE_INVARIANT": Definition(Kind.PROHIBITION, "a prohibition that holds before and after"),
}
POLARITY_OF = {Kind.BEHAVIOUR: Polarity.MUST_HOLD, Kind.PROHIBITION: Polarity.MUST_NOT_HOLD}
#: What a V1 side at the parent states in V2 terms (§11): RED = the criterion is not satisfied there.
PARENT_SIDE = {"RED": ParentExpectation.UNSATISFIED_AT_PARENT, "GREEN": ParentExpectation.SATISFIED_AT_PARENT}
#: Historical names of a mode -> the Mode member. None exist: the enum entered the kernel in commit 35d5178
#: (2026-09-20, TDD proof policy V2) with these three members and was never renamed. A lookup here is exact.
ALIASES: dict[str, str] = {}
TRANSITION = re.compile(r"^(RED|GREEN) -> (RED|GREEN)$")
RATIONALE_REF = ("RFC §31 (proof modes -> ObligationRole + Polarity on the contract); §7 and §10.2 (SubjectAbsence is "
                 "declared, never inferred from polarity); §11 (ParentExpectation per role)")


# ------------------------------------------------------------------------------------------- the V1 kernel as input

@dataclass(frozen=True)
class V1Kernel:
    members: tuple[str, ...]        # `Mode` members in declaration order
    transitions: dict[str, str]     # `EXPECTED`: member -> "RED -> GREEN"
    doc_lines: tuple[str, ...]      # the module docstring, for citation checks
    sha256: str                     # LF-normalised, so the identity is the same on every checkout


def _lf(path: pathlib.Path) -> str:
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def read_v1(root: pathlib.Path = ROOT) -> V1Kernel:
    path = root / V1_OBLIGATION
    if not path.exists():
        raise MigrationError(f"{V1_OBLIGATION} is missing: no V1 kernel to read")
    src = _lf(path)
    tree = ast.parse(src)
    mode = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Mode"), None)
    if mode is None:
        raise MigrationError(f"{V1_OBLIGATION} has no Mode enum")
    members = tuple(n.targets[0].id for n in mode.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant))
    expected = next((n.value for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "EXPECTED"), None)
    if not isinstance(expected, ast.Dict):
        raise MigrationError(f"{V1_OBLIGATION} has no EXPECTED transition table")
    transitions = {}
    for i, k in enumerate(expected.keys):
        v = expected.values[i]
        if not (isinstance(k, ast.Attribute) and isinstance(k.value, ast.Name) and k.value.id == "Mode"
                and isinstance(v, ast.Constant) and isinstance(v.value, str)):
            raise MigrationError(f"{V1_OBLIGATION}: EXPECTED is not keyed by Mode members with string transitions")
        transitions[k.attr] = v.value
    doc = ast.get_docstring(tree) or ""
    return V1Kernel(members, transitions, tuple(doc.splitlines()), hashlib.sha256(src.encode("utf-8")).hexdigest())


def cited(kernel: V1Kernel, mode: str, quote: str) -> bool:
    """The kernel docstring defines `mode` on exactly one line, and that line carries the quote."""
    lines = [ln for ln in kernel.doc_lines if ln.strip().startswith(mode + " ")]
    return len(lines) == 1 and quote in lines[0]


# ------------------------------------------------------------------------------------------------------ derivation

def resolve(name: str, members: Iterable[str], aliases: Mapping[str, str] = ALIASES) -> str | None:
    """The Mode member `name` denotes: itself, or the target of an explicit alias entry; None otherwise. Exact keys
    only — no case folding, no stripping, no similarity."""
    known = list(members)
    if name in known:
        return name
    if name in aliases:
        target = aliases[name]
        if target not in known:
            raise MigrationError(f"alias {name!r} -> {target!r}: the target is not a V1 mode")
        return target
    return None


def declared(declaration: SubjectAbsence | None) -> SubjectAbsence | str:
    """SubjectAbsence from an explicit declaration and nothing else: this function has no other input to read."""
    if declaration is None:
        return HUMAN_DECLARATION_REQUIRED
    if not isinstance(declaration, SubjectAbsence):
        raise MigrationError(f"a SubjectAbsence declaration is a SubjectAbsence member, not {declaration!r}")
    return declaration


def _value(v: object) -> object:
    return v.value if isinstance(v, Enum) else v


def _unknown(name: str, why: str) -> dict:
    return {"v1_mode": name, "source": None, "transition": None, "definition": None, "expected_parent": None,
            "obligation_role": None, "polarity": None, "subject_absence": None,
            "obligation_role_source": NO_SOURCE, "polarity_source": NO_SOURCE, "subject_absence_source": NO_SOURCE,
            "status": UNMAPPED, "reason": UNKNOWN_V1_MODE, "missing": list(DIMENSIONS),
            "derivation": {"unknown": why}, "rationale_ref": RATIONALE_REF}


def derive(modes: Iterable[str], kernel: V1Kernel, definitions: Mapping[str, Definition] = V1_DEFINITIONS, *,
           aliases: Mapping[str, str] = ALIASES,
           declarations: Mapping[str, SubjectAbsence] | None = None) -> list[dict]:
    """One row per distinct name in `modes`, in canonical order. A name that is no mode and no alias is an UNMAPPED
    row with reason UNKNOWN_V1_MODE — kept, never dropped, never defaulted."""
    declarations = dict(declarations or {})
    rows = []
    for name in sorted(set(modes)):
        mode = resolve(name, kernel.members, aliases)
        if mode is None:
            rows.append(_unknown(name, "neither a Mode member of the V1 kernel nor an entry of the alias table"))
            continue
        transition, definition = kernel.transitions.get(mode), definitions.get(mode)
        if transition is None or definition is None or not cited(kernel, mode, definition.quote):
            rows.append(_unknown(name, f"{mode} is a Mode member without a transition in EXPECTED, without a cited "
                                       "definition, or its citation is not on the kernel's definition line"))
            continue
        sides = TRANSITION.match(transition)
        if sides is None or sides.group(2) != "GREEN":
            rows.append(_unknown(name, f"{mode}: EXPECTED transition {transition!r} is not a V1 transition "
                                       "(<RED|GREEN> -> GREEN)"))
            continue
        expected = PARENT_SIDE[sides.group(1)]
        role = next(r for r, e in EXPECTED_AT_PARENT.items() if e is expected)
        polarity = POLARITY_OF[definition.kind]
        absence = declared(declarations.get(mode))
        values = {"obligation_role": role, "polarity": polarity, "subject_absence": absence}
        missing = [d for d in DIMENSIONS if not isinstance(values[d], Enum)]
        rows.append({
            "v1_mode": name, "source": f"{V1_OBLIGATION}::Mode.{mode}" + ("" if name == mode else f" (alias {name!r})"),
            "transition": {"parent": sides.group(1), "candidate": sides.group(2), "source": f"{V1_OBLIGATION}::EXPECTED"},
            "definition": {"kind": definition.kind.value, "quote": definition.quote,
                           "source": f"{V1_OBLIGATION} module docstring, the {mode} line"},
            "expected_parent": expected.value, "obligation_role": role.value, "polarity": polarity.value,
            "subject_absence": _value(absence),
            "obligation_role_source": V1_TRANSITION, "polarity_source": V1_DEFINITION,
            "subject_absence_source": HUMAN_DECLARATION if isinstance(absence, Enum) else NO_SOURCE,
            "status": UNMAPPED if missing else MAPPED,
            "reason": HUMAN_DECLARATION_REQUIRED if missing else None, "missing": missing,
            "derivation": {
                "obligation_role": f"EXPECTED[{mode}] = {transition!r}: parent {sides.group(1)} -> "
                                   f"{expected.value}; the role whose EXPECTED_AT_PARENT is that (§11) -> {role.value}",
                "polarity": f"the kernel defines {mode} as '{definition.quote}' -> {definition.kind.value} -> "
                            f"{polarity.value}; V1 never verified a criterion's test against it",
                "subject_absence": ("from an explicit typed declaration" if isinstance(absence, Enum) else
                                    "V1 declared none; nothing here infers it (not from polarity, name, transition, "
                                    "wording, history or a default)"),
            },
            "rationale_ref": RATIONALE_REF,
        })
    return rows


def without_v1_source(rows: list[dict]) -> list[dict]:
    """Every (ObligationRole, Polarity) pair no V1 mode produces — V2 contracts V1 could not express."""
    produced = {(r["obligation_role"], r["polarity"]) for r in rows}
    out = []
    for role in ObligationRole:
        for polarity in Polarity:
            if (role.value, polarity.value) not in produced:
                out.append({"obligation_role": role.value, "polarity": polarity.value, "loss": _loss_code(role, polarity)})
    return out


def _loss_code(role: ObligationRole, polarity: Polarity) -> str:
    if role is ObligationRole.VERIFY:
        return "V1_HAS_NO_UNCONSTRAINED_PARENT"
    if role is ObligationRole.INTRODUCE and polarity is Polarity.MUST_NOT_HOLD:
        return "V1_COULD_NOT_INTRODUCE_A_PROHIBITION"
    return "V1_NO_SOURCE"


LOSS_STATEMENTS = {
    "V1_NO_SUBJECT_ABSENCE_DECLARATION": "V1 declared no SubjectAbsence for any criterion: every row needs a human "
                                         "declaration on the V2 contract (RFC §7, §10.2); nothing infers it",
    "V1_POLARITY_UNVERIFIED": "V1 carried polarity only in each mode's definition and never checked a criterion's "
                              "test against it: the V2 contract author declares polarity (F4)",
    "V1_HAS_NO_UNCONSTRAINED_PARENT": "no V1 mode leaves the parent unconstrained (VERIFY / UNCONSTRAINED)",
    "V1_COULD_NOT_INTRODUCE_A_PROHIBITION": "no V1 mode expressed INTRODUCE + MUST_NOT_HOLD (RFC case NEG-1): V1 "
                                            "planners were told never to write a prohibition as CHANGE_REQUIRED",
    "V1_NO_SOURCE": "no V1 mode produces this pair",
}


def loss_report(rows: list[dict], missing_pairs: list[dict]) -> list[dict]:
    known = [r["v1_mode"] for r in rows if r["reason"] != UNKNOWN_V1_MODE]
    out = [{"code": "V1_NO_SUBJECT_ABSENCE_DECLARATION", "dimension": "subject_absence", "affects": known},
           {"code": "V1_POLARITY_UNVERIFIED", "dimension": "polarity", "affects": known}]
    for code in dict.fromkeys(p["loss"] for p in missing_pairs):
        out.append({"code": code, "dimension": "obligation_role+polarity",
                    "affects": [f"{p['obligation_role']}+{p['polarity']}" for p in missing_pairs if p["loss"] == code]})
    for entry in out:
        entry["statement"] = LOSS_STATEMENTS[entry["code"]]
    return out


# ------------------------------------------------------------------------------------------------------- inventory

SCAN_DIRS = ("aisef", "tests", "docs", "validation", "closure-evidence")
V2_DIRS = ("aisef2", "tests/v2", "validation/v2", "closure-evidence/v2", "docs/implementation/v2")
TEXT = {".py", ".md", ".json", ".yaml", ".yml", ".txt", ".toml", ".cfg"}
TOKEN = re.compile(rb"\b[A-Z][A-Z0-9_]*_(?:REQUIRED|INVARIANT)\b")
EVIDENCE_KEYS = ("proof_mode", "expected_transition", "mode")


def _kind(rel: str) -> str:
    if rel.startswith("aisef/kit/prompts/"):
        return "prompt"
    if rel.startswith("aisef/") and rel.endswith((".yaml", ".yml")):
        return "config"
    if rel.startswith("aisef/"):
        return "code"
    if rel.startswith("tests/fixtures/"):
        return "fixture"
    if rel.startswith("tests/"):
        return "test"
    if rel.startswith("docs/"):
        return "doc"
    if rel.startswith("validation/"):
        return "validation"
    return "evidence" if rel.endswith(".json") else "evidence-text"


def _files(root: pathlib.Path, dirs: Iterable[str] = SCAN_DIRS, exclude: Iterable[str] = V2_DIRS):
    for d in dirs:
        for p in sorted((root / d).rglob("*")):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and p.suffix in TEXT and "__pycache__" not in rel \
                    and not any(rel == v or rel.startswith(v + "/") for v in exclude):
                yield rel, p.read_bytes()


def _enums(root: pathlib.Path) -> list[tuple[str, str, list[str]]]:
    """(module, class, member values) for every Enum class under aisef/."""
    out = []
    for p in sorted((root / "aisef").rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        for node in ast.walk(ast.parse(_lf(p))):
            if isinstance(node, ast.ClassDef) and any("Enum" in ast.unparse(b) for b in node.bases):
                values = [n.value.value for n in node.body if isinstance(n, ast.Assign)
                          and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
                out.append((rel, node.name, values))
    return out


def _walk_values(obj, key_filter: tuple[str, ...], found: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in key_filter and isinstance(v, str):
                found[(k, v)] = found.get((k, v), 0) + 1
            _walk_values(v, key_filter, found)
    elif isinstance(obj, list):
        for x in obj:
            _walk_values(x, key_filter, found)


def _constants(path: pathlib.Path) -> list[tuple[str, ast.AST]]:
    """(name, value) of every module-level single-name assignment of the V1 obligation module."""
    return [(n.targets[0].id, n.value) for n in ast.parse(_lf(path)).body if isinstance(n, ast.Assign)
            and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)]


def _ident(e: dict) -> str:
    return e["kind"] + " " + (e.get("where") or e.get("token") or e.get("name") or f"{e.get('key')}={e.get('value')}")


def _upper(path: pathlib.Path) -> bool:
    """`ac_proof` of the V1 parser folds the mode token with `.upper()` — the compatibility fact the inventory cites."""
    if not path.exists():
        return False
    for node in ast.walk(ast.parse(_lf(path))):
        if isinstance(node, ast.FunctionDef) and node.name == "ac_proof":
            return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "upper"
                       for n in ast.walk(node))
    return False


def inventory(root: pathlib.Path, kernel: V1Kernel) -> tuple[list[dict], list[str]]:
    """Every representation of a V1 proof mode still in the repository, classified by rule; and the problems: a
    representation no rule classifies (fail closed), or a V1 mode string inside the V2 kernel."""
    members = set(kernel.members)
    entries, problems = [], []
    enum_of = {}
    for rel, name, values in _enums(root):
        for v in values:
            enum_of.setdefault(v, f"{rel}::{name}")
        if members & set(values):
            entries.append({"kind": "enum", "where": f"{rel}::{name}", "members": values, "classification": ACTIVE,
                            "reason": "the V1 kernel's proof-mode enum: the migration input"})
        elif "Mode" in name:
            entries.append({"kind": "enum", "where": f"{rel}::{name}", "members": values, "classification": NOT_A_MODE,
                            "reason": "an enum named like a mode with no proof-mode member (name collision)"})
    for name, value in _constants(root / V1_OBLIGATION):
        refs = [n.attr for n in ast.walk(value) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == "Mode"]
        if refs:
            entries.append({"kind": "constant", "where": f"{V1_OBLIGATION}::{name}", "carries": refs, "classification": ACTIVE,
                            "reason": "a kernel table keyed by Mode members" + (": the transition input" if name == "EXPECTED" else "")})
        elif name.isupper():
            entries.append({"kind": "constant", "where": f"{V1_OBLIGATION}::{name}", "classification": NOT_A_MODE,
                            "reason": "a constant of the kernel's obligation module that names no Mode member "
                                      "(story types, owner routing)"})
    tokens: dict[bytes, list[str]] = {}
    evidence: dict[tuple[str, str], int] = {}
    policy = []
    for rel, data in _files(root):
        for tok in set(TOKEN.findall(data)):
            tokens.setdefault(tok, []).append(rel)
        if rel.endswith(".json"):
            try:
                doc = json.loads(data)
            except ValueError:
                problems.append(f"inventory: {rel} is not JSON")
                continue
            _walk_values(doc, EVIDENCE_KEYS, evidence)
            record = doc.get("record") if isinstance(doc, dict) else None
            if isinstance(record, str) and "POLICY" in record:
                policy.append((rel, record, bool(members & {t.decode() for t in TOKEN.findall(data)})))
    for tok, files in tokens.items():
        name = tok.decode()
        if name in members:
            entries.append({"kind": "token", "token": name, "classification": ACTIVE, "carried_by": [
                {"path": f, "kind": _kind(f)} for f in sorted(files)]})
        elif name in enum_of:
            entries.append({"kind": "token", "token": name, "where": enum_of[name], "classification": NOT_A_MODE,
                            "reason": "a member of a V1 enum that is not the proof-mode enum", "files": len(files)})
        else:
            problems.append(f"inventory: token {name!r} ({len(files)} files) matches no classification rule")
    for (key, value), n in evidence.items():
        e = {"kind": "evidence_value", "key": key, "value": value, "occurrences": n}
        if key == "proof_mode" and value in members or key == "mode" and value in members:
            e.update(classification=ACTIVE, reason="a serialized V1 proof mode")
        elif key == "proof_mode":
            e.update(classification=UNMAPPED_REPR, reason="a proof_mode value the V1 kernel does not know: V1 refused "
                                                         "it (PLAN_METADATA_MISSING); nothing to migrate")
        elif key == "expected_transition" and value in kernel.transitions.values():
            e.update(classification=NOT_A_MODE, reason="derived from the mode by EXPECTED; not an input")
        elif key == "mode":
            e.update(classification=NOT_A_MODE, reason="a different 'mode' vocabulary (not a proof mode)")
        else:
            problems.append(f"inventory: evidence value {key}={value!r} matches no classification rule")
            continue
        entries.append(e)
    for rel, record, carries in policy:
        entries.append({"kind": "policy_record", "where": rel, "record": record,
                        "classification": ACTIVE if carries else HISTORICAL,
                        "reason": "a policy record naming the active modes" if carries else
                        "a policy record from before the per-criterion modes (the superseded whole-story policy)"})
    if _upper(root / V1_NORMALIZE):
        entries.append({"kind": "grammar", "where": f"{V1_NORMALIZE}::ac_proof", "classification": NOT_A_MODE,
                        "reason": "V1's plan parser folds the mode token to upper case before the kernel; a "
                                  "case-folded spelling is neither a mode value nor an alias of this table"})
    else:
        problems.append(f"inventory: {V1_NORMALIZE}::ac_proof with its case folding is not where the citation says")
    for name, target in ALIASES.items():
        entries.append({"kind": "alias", "name": name, "target": target, "classification": ALIAS})
    found = {t.decode() for rel, data in _files(root, ("aisef2",), ()) for t in TOKEN.findall(data)}
    v2_hits = [m for m in kernel.members if m in found]
    if v2_hits:
        problems.append(f"inventory: V1 proof modes appear inside the V2 kernel: {v2_hits}")
    entries.sort(key=lambda e: (e["classification"], _ident(e)))
    problems.sort()
    return entries, problems


# ----------------------------------------------------------------------------------------------------- the table

def generate(root: pathlib.Path = ROOT) -> dict:
    kernel = read_v1(root)
    rows = derive(kernel.members, kernel)
    missing_pairs = without_v1_source(rows)
    entries, problems = inventory(root, kernel)
    return {
        "record": "AISEF V2 — P6 MIGRATION TABLE",
        "work_package": "WP-6.1",
        "rfc": "§31 (mechanical, generated, --checked); §7, §10.2 (SubjectAbsence declared, never inferred); §11 (F6, read only)",
        "generator": "validation/v2/gen_migration_table.py",
        "rule": "generated; never hand-edited; --check regenerates and fails on drift, a hand edit, an unknown V1 mode "
                "or a row whose V2 value has no typed source",
        "inputs": {
            "v1": {"path": V1_OBLIGATION, "sha256_lf": kernel.sha256, "mode_members": list(kernel.members),
                   "transitions": dict(kernel.transitions), "read_as": "source (AST); nothing under aisef/ is imported or written"},
            "v2": {"ObligationRole": [m.value for m in ObligationRole], "ParentExpectation": [m.value for m in ParentExpectation],
                   "Polarity": [m.value for m in Polarity], "SubjectAbsence": [m.value for m in SubjectAbsence],
                   "EXPECTED_AT_PARENT": {r.value: e.value for r, e in EXPECTED_AT_PARENT.items()}},
        },
        "aliases": dict(ALIASES),
        "rows": rows,
        "v2_without_v1_source": missing_pairs,
        "loss_report": loss_report(rows, missing_pairs),
        "inventory": entries,
        "inventory_problems": problems,
        "declarations": "none in cycle 1: SubjectAbsence is declared per contract by its author (F4); the table holds no default",
    }


def problems(table: dict) -> list[str]:
    """What makes a table (fresh or committed) unacceptable: an unknown mode, a defaulted or inconsistent row, an
    inventory problem. Read from the typed fields only."""
    out = list(table.get("inventory_problems") or [])
    v2 = {"obligation_role": {m.value for m in ObligationRole}, "polarity": {m.value for m in Polarity},
          "subject_absence": {m.value for m in SubjectAbsence}}
    rows = table.get("rows")
    if not isinstance(rows, list) or not rows:
        return out + ["the table has no rows"]
    for r in rows:
        name = r.get("v1_mode")
        if r.get("status") not in (MAPPED, UNMAPPED):
            out.append(f"row {name}: status {r.get('status')!r} is neither MAPPED nor UNMAPPED")
        if r.get("reason") == UNKNOWN_V1_MODE:
            out.append(f"row {name}: unknown V1 mode — no mapping and no default; declare it or remove it from the input")
            continue
        missing = [d for d in DIMENSIONS if r.get(d) not in v2[d]]
        for d in DIMENSIONS:
            if r.get(d) in v2[d] and r.get(f"{d}_source") not in (V1_TRANSITION, V1_DEFINITION, HUMAN_DECLARATION):
                out.append(f"row {name}: {d} = {r.get(d)!r} has no typed source: a silently defaulted value")
            if r.get(d) is not None and r.get(d) not in v2[d] and r.get(d) != HUMAN_DECLARATION_REQUIRED:
                out.append(f"row {name}: {d} = {r.get(d)!r} is not a V2 value")
        if r.get("subject_absence") in v2["subject_absence"] and r.get("subject_absence_source") != HUMAN_DECLARATION:
            out.append(f"row {name}: subject_absence {r.get('subject_absence')!r} was not declared: inferred or defaulted")
        if r.get("status") == MAPPED and missing:
            out.append(f"row {name}: MAPPED while {missing} still need a declaration")
        if r.get("status") == UNMAPPED and not missing:
            out.append(f"row {name}: UNMAPPED although every dimension holds a V2 value")
        if set(r.get("missing") or []) != set(missing):
            out.append(f"row {name}: 'missing' {r.get('missing')!r} does not match the row's own fields {missing!r}")
    return out


def render_json(table: dict) -> str:
    return json.dumps(table, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def render_doc(table: dict) -> str:
    rows = table["rows"]
    lines = [
        "# V1 proof modes -> V2 obligations: the generated migration table (RFC §31, WP-6.1)", "",
        f"Generated by `{table['generator']}` from the frozen V1 kernel read as source (`{V1_OBLIGATION}`, sha256 "
        f"`{table['inputs']['v1']['sha256_lf']}`) and the frozen V2 vocabularies — do not hand-edit; `--check` regenerates "
        "both this document and `" + TABLE_REL + "` and fails on any difference, on an unknown V1 mode and on a row "
        "whose V2 value has no typed source.", "",
        "This is a migration adapter, not new semantics: `ObligationRole`, `ParentExpectation`, `Polarity` and "
        "`SubjectAbsence` are read from F4/F6 as frozen. `SubjectAbsence` is never inferred — not from polarity, the "
        "mode's name, its transition, its wording, history or a default — so every row stays `UNMAPPED` with "
        "`HUMAN_DECLARATION_REQUIRED` until the V2 contract's author declares it; V1 declared none.", "",
        "## Migration table", "",
        "| V1 mode | V1 transition | V1 definition | ObligationRole | expected at parent | Polarity | SubjectAbsence | status | reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        t, d = r["transition"], r["definition"]
        lines.append(f"| `{r['v1_mode']}` | {t['parent'] + ' -> ' + t['candidate'] if t else '-'} | "
                     f"{d['kind'] + ': ' + repr(d['quote']) if d else '-'} | {r['obligation_role'] or '-'} | "
                     f"{r['expected_parent'] or '-'} | {r['polarity'] or '-'} | {r['subject_absence'] or '-'} | "
                     f"**{r['status']}** | {r['reason'] or '-'} |")
    lines += ["", "Derivation, per row (recorded; never read for control):", ""]
    for r in rows:
        lines.append(f"- `{r['v1_mode']}` — source `{r['source']}`")
        for d in DIMENSIONS:
            lines.append(f"  - {d} ({r[d + '_source']}): {r['derivation'].get(d, r['derivation'].get('unknown'))}")
    lines += ["", "## V2 contracts no V1 mode could express", "",
              "| ObligationRole | Polarity | loss |", "|---|---|---|"]
    lines += [f"| {p['obligation_role']} | {p['polarity']} | `{p['loss']}` |" for p in table["v2_without_v1_source"]]
    lines += ["", "## Loss report — what V1 did not carry", ""]
    lines += [f"- `{e['code']}` ({e['dimension']}; affects {', '.join(e['affects']) or 'none'}): {e['statement']}"
              for e in table["loss_report"]]
    lines += ["", "## Alias table", "",
              ("none — the `Mode` enum entered the kernel with these three members and was never renamed; "
               "resolution is by exact key only" if not table["aliases"] else "")]
    lines += [f"- `{k}` -> `{v}`" for k, v in sorted(table["aliases"].items())]
    lines += ["", "## Inventory of V1 proof-mode representations (authorization §4)", "",
              "Discovered mechanically over `aisef/`, `tests/`, `docs/`, `validation/` and `closure-evidence/` "
              "(the V2 harness directories excluded); classified by rule; an unclassifiable representation fails the "
              "generation.", ""]
    for c in CLASSIFICATIONS:
        mine = [e for e in table["inventory"] if e["classification"] == c]
        lines.append(f"### {c} ({len(mine)})")
        lines.append("")
        for e in mine:
            what = e.get("token") or e.get("where") or e.get("value") or e.get("name")
            detail = e.get("reason") or (f"-> {e['target']}" if "target" in e else "a V1 proof mode")
            if "where" in e and "token" in e:
                detail += f" ({e['where']})"
            extra = f" — carried by {len(e['carried_by'])} files" if "carried_by" in e else \
                f" — {e['occurrences']} occurrences" if "occurrences" in e else ""
            lines.append(f"- {e['kind']} `{what}`{(' (' + e['key'] + ')') if 'key' in e else ''}: {detail}{extra}")
        lines.append("")
    lines += [f"Inventory problems: {table['inventory_problems'] or 'none'}", "",
              f"Declarations: {table['declarations']}", ""]
    return "\n".join(lines)


def compare(table: dict, committed_json: str | None, committed_doc: str | None) -> list[str]:
    """The committed outputs are exactly what the generator writes: any hand edit or staleness is drift."""
    out = []
    if committed_json is None:
        out.append(f"{TABLE_REL} is missing: run the generator")
    elif committed_json != render_json(table):
        out.append(f"{TABLE_REL} drifted from its generator: hand-edited or stale")
    if committed_doc is None:
        out.append(f"{DOC_REL} is missing: run the generator")
    elif committed_doc != render_doc(table):
        out.append(f"{DOC_REL} drifted from its generator: hand-edited or stale")
    return out


def _read(path: pathlib.Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def check(root: pathlib.Path = ROOT) -> list[str]:
    try:
        table = generate(root)
    except MigrationError as e:
        return [f"generation refused: {e}"]
    out = problems(table)
    committed_json = _read(root / TABLE_REL)
    out += compare(table, committed_json, _read(root / DOC_REL))
    if committed_json is not None:
        try:
            out += [f"committed {p}" for p in problems(json.loads(committed_json))]
        except ValueError:
            out.append(f"{TABLE_REL} is not JSON")
    return out


def write(root: pathlib.Path = ROOT) -> list[str]:
    table = generate(root)
    found = problems(table)
    if found:
        return found
    for rel, text in ((TABLE_REL, render_json(table)), (DOC_REL, render_doc(table))):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode("utf-8"))
    return []


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        found = check()
        for p in found:
            print(f"FAIL  {p}")
        print("migration table: " + ("FAIL" if found else "PASS"))
        return 1 if found else 0
    try:
        found = write()
    except MigrationError as e:
        found = [f"generation refused: {e}"]
    for p in found:
        print(f"FAIL  {p}")
    if found:
        print("migration table: NOT WRITTEN")
        return 1
    print(f"wrote {TABLE_REL} and {DOC_REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
