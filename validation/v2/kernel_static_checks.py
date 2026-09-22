"""P1 static checks over the V2 kernel (`aisef2/`). Each rule is a Q0 checker, calibrated separately.

* **NO_PROSE_CONTROL** (invariant I, WP-1.1) — no kernel code reads `Requirement.text`, `BehaviorContract.rationale`
  or `PlanObligation.ownership_rationale`: no attribute named `text`, `rationale` or `ownership_rationale`, and no
  `getattr` of those names. Identity and serialisation walk dataclass fields generically and never name them.
* **NO_RAW_VERDICT_ROUTING** (RFC §10.1, WP-1.3) — planning and control code (`aisef2/plan`, `aisef2/control`,
  `aisef2/orchestrate`) never names `BehaviorVerdict` or reads `.behavior_verdict`: it routes on the derived
  `ContractSatisfaction`, because the raw verdict is polarity-inverted for every negative contract.
* **RETRYABLE_ONLY_IN_TAXONOMY** (RFC §22, WP-1.4) — retryability is fixed once in `aisef2/control/owner.py`; no
  other kernel module assigns, passes or keys a `retryable` or `retryability`.
* **NO_VERDICT_FROM_ABSENCE_DECLARATION** (RFC §10.2, P1 hygiene) — a decided verdict is observed, never inferred
  from `SubjectAbsence`: no kernel scope (a function, or module/class level) that reads the absence declaration —
  a `SubjectAbsence` member, its value as a string, or the `subject_absence` field — also names
  `BehaviorVerdict.SATISFIED` or `REFUTED`, directly, by alias, by value lookup or through a module-level name bound
  to one. Catches the table form, the branch form and the early-return form alike; `INDETERMINATE` stays legal,
  because REQUIRES_SUBJECT decides INDETERMINATE(PRECONDITION_ABSENT) by itself. Ceiling: a call into another scope
  that returns a fixed verdict is not seen; `on_subject_absent`'s behavioural tests (and WP-2.1's probe tests) are
  what cover that.
* **RESULT_ONLY_THROUGH_BINDING** (PROBE-BIND-1, P2 correction) — a decision never reads a bare probe result: outside
  `aisef2/probe/protocol.py`, which defines `ProbeRecord` and `bound_result`, no kernel module reads an attribute
  named `result` (nor `getattr(x, "result")`). Every read goes through `bound_result(record, spec=, revision=,
  enforcement=)`. The rule also runs over the evidence builders (tests/v2/p2/test_probe_binding.py).

    python -P validation/v2/kernel_static_checks.py            # all rules; exit 1 on any violation
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
KERNEL = "aisef2"
PROSE = {"text", "rationale", "ownership_rationale"}
ROUTING_PACKAGES = ("aisef2/plan/", "aisef2/control/", "aisef2/orchestrate/")
RAW_VERDICT = {"BehaviorVerdict", "behavior_verdict"}
TAXONOMY_MODULE = "aisef2/control/owner.py"
_RETRY_NAMES = {"retryable", "retryability"}
RULES = ("NO_PROSE_CONTROL", "NO_RAW_VERDICT_ROUTING", "RETRYABLE_ONLY_IN_TAXONOMY",
         "NO_VERDICT_FROM_ABSENCE_DECLARATION", "RESULT_ONLY_THROUGH_BINDING")
BINDING_MODULE = "aisef2/probe/protocol.py"
ABSENCE_MEMBERS = {"REQUIRES_SUBJECT", "ABSENCE_IS_DECIDABLE"}
ABSENCE_FIELD = "subject_absence"
DECIDED_VERDICTS = {"SATISFIED", "REFUTED"}
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _scope_nodes(scope: ast.AST):
    """The nodes of one scope, not descending into nested functions (each is its own scope)."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _SCOPES):
            stack.extend(ast.iter_child_nodes(n))


def _verdict_aliases(tree: ast.Module) -> set[str]:
    out = {"BehaviorVerdict"}
    for n in ast.walk(tree):
        if isinstance(n, ast.alias) and n.name.rsplit(".", 1)[-1] == "BehaviorVerdict" and n.asname:
            out.add(n.asname)
    return out


def _decided_verdict(n: ast.AST, verdicts: set[str], bound: set[str]) -> bool:
    def is_verdict(v: ast.AST) -> bool:
        return getattr(v, "id", None) in verdicts or getattr(v, "attr", None) == "BehaviorVerdict"

    def decided(c: ast.AST) -> bool:
        return isinstance(c, ast.Constant) and c.value in DECIDED_VERDICTS
    return (isinstance(n, ast.Attribute) and n.attr in DECIDED_VERDICTS and is_verdict(n.value)
            or isinstance(n, ast.Subscript) and is_verdict(n.value) and decided(n.slice)
            or isinstance(n, ast.Call) and is_verdict(n.func) and n.args and decided(n.args[0])
            or isinstance(n, ast.Call) and getattr(n.func, "id", "") == "getattr" and len(n.args) > 1
            and is_verdict(n.args[0]) and decided(n.args[1])
            or isinstance(n, ast.Name) and n.id in bound)


def _reads_absence_declaration(n: ast.AST) -> bool:
    """A member (by attribute or value string), or a read of the field (attribute, subscript key, getattr)."""
    def field(c: ast.AST) -> bool:
        return isinstance(c, ast.Constant) and c.value == ABSENCE_FIELD
    return (isinstance(n, ast.Attribute) and n.attr in ABSENCE_MEMBERS | {ABSENCE_FIELD}
            or isinstance(n, ast.Constant) and n.value in ABSENCE_MEMBERS
            or isinstance(n, ast.Subscript) and field(n.slice)
            or isinstance(n, ast.Call) and getattr(n.func, "id", "") == "getattr" and len(n.args) > 1 and field(n.args[1]))


def _verdict_from_absence(rel: str, tree: ast.Module) -> list[str]:
    verdicts = _verdict_aliases(tree)
    bound = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None
             and any(_decided_verdict(v, verdicts, set()) for v in ast.walk(n.value))
             for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    out = []
    for scope in [tree, *(n for n in ast.walk(tree) if isinstance(n, _SCOPES))]:
        nodes = list(_scope_nodes(scope))
        if any(_reads_absence_declaration(n) for n in nodes):
            out += [f"NO_VERDICT_FROM_ABSENCE_DECLARATION {rel}:{n.lineno} a decided BehaviorVerdict in a scope that "
                    "reads the SubjectAbsence declaration" for n in nodes if _decided_verdict(n, verdicts, bound)]
    return out


def _names(node: ast.AST) -> list[tuple[str, int]]:
    """Every identifier a node mentions, with its line: names, attributes, import aliases, getattr strings, keywords."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append((n.id, n.lineno))
        elif isinstance(n, ast.Attribute):
            out.append((n.attr, n.lineno))
        elif isinstance(n, ast.alias):
            out.append((n.name.rsplit(".", 1)[-1], getattr(n, "lineno", 0)))
            if n.asname:
                out.append((n.asname, getattr(n, "lineno", 0)))
        elif isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("getattr", "setattr", "hasattr") \
                and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
            out.append((n.args[1].value, n.lineno))
        elif isinstance(n, ast.keyword) and n.arg:
            out.append((n.arg, getattr(n, "lineno", 0) or getattr(n.value, "lineno", 0)))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier():
            out.append((n.value, n.lineno))
    return out


def violations(rel: str, source: str, rules: tuple[str, ...] = RULES) -> list[str]:
    tree = ast.parse(source, filename=rel)
    out = []
    if "NO_PROSE_CONTROL" in rules:
        for n in ast.walk(tree):
            hit = None
            if isinstance(n, ast.Attribute) and n.attr in PROSE:
                hit = n.attr
            elif isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("getattr", "hasattr") and len(n.args) > 1 \
                    and isinstance(n.args[1], ast.Constant) and n.args[1].value in PROSE:
                hit = n.args[1].value
            if hit:
                out.append(f"NO_PROSE_CONTROL {rel}:{n.lineno} reads prose field {hit!r}")
    if "NO_RAW_VERDICT_ROUTING" in rules and rel.startswith(ROUTING_PACKAGES):
        for name, line in _names(tree):
            if name in RAW_VERDICT:
                out.append(f"NO_RAW_VERDICT_ROUTING {rel}:{line} planning/control code names {name!r}")
    if "RETRYABLE_ONLY_IN_TAXONOMY" in rules and rel != TAXONOMY_MODULE:
        for n in ast.walk(tree):
            line = getattr(n, "lineno", 0)
            decided = (
                isinstance(n, ast.keyword) and n.arg in _RETRY_NAMES
                or isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and any(
                    getattr(t, "id", getattr(t, "attr", None)) in _RETRY_NAMES
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))
                or isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value in _RETRY_NAMES for k in n.keys)
            )
            if decided:
                out.append(f"RETRYABLE_ONLY_IN_TAXONOMY {rel}:{line or '?'} decides retryability outside the taxonomy")
    if "NO_VERDICT_FROM_ABSENCE_DECLARATION" in rules:
        out += _verdict_from_absence(rel, tree)
    if "RESULT_ONLY_THROUGH_BINDING" in rules and rel != BINDING_MODULE:
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == "result" or isinstance(n, ast.Call) \
                    and getattr(n.func, "id", "") == "getattr" and len(n.args) > 1 \
                    and isinstance(n.args[1], ast.Constant) and n.args[1].value == "result":
                out.append(f"RESULT_ONLY_THROUGH_BINDING {rel}:{n.lineno} reads a probe result without its binding "
                           "(use bound_result)")
    return sorted(set(out))


def check(root: pathlib.Path = ROOT, rules: tuple[str, ...] = RULES) -> list[str]:
    out = []
    for path in sorted((root / KERNEL).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        out += violations(rel, path.read_text(encoding="utf-8"), rules)
    return out


def main(argv: list[str] | None = None) -> int:
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("kernel static checks: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
