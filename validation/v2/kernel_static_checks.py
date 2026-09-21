"""P1 static checks over the V2 kernel (`aisef2/`). Each rule is a Q0 checker, calibrated separately.

* **NO_PROSE_CONTROL** (invariant I, WP-1.1) — no kernel code reads `Requirement.text`, `BehaviorContract.rationale`
  or `PlanObligation.ownership_rationale`: no attribute named `text`, `rationale` or `ownership_rationale`, and no
  `getattr` of those names. Identity and serialisation walk dataclass fields generically and never name them.
* **NO_RAW_VERDICT_ROUTING** (RFC §10.1, WP-1.3) — planning and control code (`aisef2/plan`, `aisef2/control`,
  `aisef2/orchestrate`) never names `BehaviorVerdict` or reads `.behavior_verdict`: it routes on the derived
  `ContractSatisfaction`, because the raw verdict is polarity-inverted for every negative contract.
* **RETRYABLE_ONLY_IN_TAXONOMY** (RFC §22, WP-1.4) — retryability is fixed once in `aisef2/control/owner.py`; no
  other kernel module assigns, passes or keys a `retryable` or `retryability`.

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
RULES = ("NO_PROSE_CONTROL", "NO_RAW_VERDICT_ROUTING", "RETRYABLE_ONLY_IN_TAXONOMY")


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
