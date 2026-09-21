"""PLAN-FINDING-001 — prove the change to tests/hardening/test_state_model.py alters only its output destination.

Structural proof: parse the file at a base revision and in the working tree, remove exactly the three permitted
differences — the module docstring, the added `import tempfile`, and the value bound to `RESULTS` — and require
the two syntax trees to be identical. Every assertion, every test method, every control path and every call is
then provably unchanged.

    python -P validation/v2/prove_state_model_fix.py [BASE_REV]
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = "tests/hardening/test_state_model.py"


def _normalise(tree: ast.Module) -> tuple[ast.Module, list[str]]:
    removed: list[str] = []
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body.pop(0)
        removed.append("module docstring")
    out = []
    for node in body:
        if isinstance(node, ast.Import) and [a.name for a in node.names] == ["tempfile"]:
            removed.append("import tempfile")
            continue
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["RESULTS"]:
            node = ast.Assign(targets=node.targets, value=ast.Name(id="__RESULTS_DESTINATION__", ctx=ast.Load()))
            removed.append("value bound to RESULTS")
        out.append(node)
    tree.body = out
    return tree, removed


def _assertions(tree: ast.AST) -> list[str]:
    found = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"):
            found.append(ast.dump(n))
        elif isinstance(n, ast.Assert):
            found.append(ast.dump(n))
    return sorted(found)


def _tests(tree: ast.AST) -> list[str]:
    return sorted(f"{c.name}.{f.name}" for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
                  for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith("test"))


def prove(base: str) -> dict:
    old_src = subprocess.run(["git", "show", f"{base}:{TARGET}"], cwd=ROOT, capture_output=True, encoding="utf-8",
                             check=True).stdout
    new_src = (ROOT / TARGET).read_text(encoding="utf-8")
    old, new = ast.parse(old_src), ast.parse(new_src)
    old_n, old_removed = _normalise(ast.parse(old_src))
    new_n, new_removed = _normalise(ast.parse(new_src))
    return {
        "target": TARGET,
        "base_revision": subprocess.run(["git", "rev-parse", base], cwd=ROOT, capture_output=True, encoding="utf-8",
                                        check=True).stdout.strip(),
        "permitted_differences": ["module docstring", "import tempfile", "value bound to RESULTS"],
        "normalised_from_base": old_removed,
        "normalised_from_working_tree": new_removed,
        "normalised_trees_identical": ast.dump(old_n) == ast.dump(new_n),
        "assertions_identical": _assertions(old) == _assertions(new),
        "assertion_count": len(_assertions(new)),
        "test_methods_identical": _tests(old) == _tests(new),
        "test_methods": _tests(new),
        "writes_into_closure_evidence": "closure-evidence" in ast.unparse(
            next(n for n in new.body if isinstance(n, ast.Assign)
                 and [getattr(t, "id", None) for t in n.targets] == ["RESULTS"]).value),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = prove(argv[0] if argv else "HEAD")
    print(json.dumps(result, indent=1))
    ok = (result["normalised_trees_identical"] and result["assertions_identical"]
          and result["test_methods_identical"] and not result["writes_into_closure_evidence"]
          and "value bound to RESULTS" in result["normalised_from_working_tree"])
    print("PROOF:", "HOLDS" if ok else "DOES NOT HOLD")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
