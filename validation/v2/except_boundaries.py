"""Static audit of every `except` boundary in the V2 kernel (RFC §4; WP-5.5): an invariant violation is uncontainable.

`InvariantError` derives from `BaseException`, so an `except Exception` boundary structurally cannot hold it. Every
boundary that could — a bare `except`, `except BaseException`, a tuple holding one, a class related to
`InvariantError` by subclassing, a `contextlib.suppress(...)` of one — must re-raise it: an earlier
`except InvariantError: raise` handler in the same `try`, or a body that ends in a bare `raise`. A name the audit
cannot resolve to an exception class fails closed: it is treated as a boundary that could hold the violation.
Helper wrappers and decorators that absorb exceptions are `try` statements like any other, wherever they sit, so
they are audited with the rest. The audit records every boundary with its disposition:

* `RERAISES`   — an `except InvariantError: raise` handler precedes it, or its own body ends in `raise`;
* `STRUCTURAL` — what it catches cannot hold an `InvariantError` (checked against the live class hierarchy);
* a violation  — anything else.

    python -P validation/v2/except_boundaries.py            # exit 1 on any violation
"""

from __future__ import annotations

import ast
import builtins
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.errors import InvariantError  # noqa: E402

KERNEL = "aisef2"
RERAISES, STRUCTURAL = "RERAISES", "STRUCTURAL"


def _could_hold(cls: object) -> bool:
    """Whether a handler for `cls` could hold an InvariantError or one of its subclasses."""
    return isinstance(cls, type) and issubclass(cls, BaseException) and (
        issubclass(InvariantError, cls) or issubclass(cls, InvariantError))


def _local_classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def _resolve(name: str, module: object | None, local: dict[str, ast.ClassDef]) -> object | None:
    """The class a caught name denotes: a builtin, a class of the audited module (its bases resolved in turn), or an
    attribute of the imported module; None when it cannot be resolved."""
    head = name.split(".")[0]
    if name in local:
        bases = [_resolve(ast.unparse(b), module, local) for b in local[name].bases]
        if any(b is None for b in bases):
            return None
        return type(name, tuple(b for b in bases if isinstance(b, type)), {})
    if hasattr(builtins, head) and "." not in name:
        return getattr(builtins, head)
    if module is not None:
        obj: object = module
        for part in name.split("."):
            if not hasattr(obj, part):
                return None
            obj = getattr(obj, part)
        return obj
    return None


def _caught(node: ast.AST | None) -> list[str] | None:
    """The names a handler catches; [] for a bare except; None for a form the audit does not model."""
    if node is None:
        return []
    if isinstance(node, ast.Tuple):
        parts = [_caught(e) for e in node.elts]
        return None if any(p is None for p in parts) else [n for p in parts for n in p]
    if isinstance(node, (ast.Name, ast.Attribute)):
        return [ast.unparse(node)]
    return None


def _reraises_all(handler: ast.ExceptHandler) -> bool:
    last = handler.body[-1]
    return isinstance(last, ast.Raise) and last.exc is None


def _is_invariant_reraise(handler: ast.ExceptHandler) -> bool:
    names = _caught(handler.type)
    return names == ["InvariantError"] and _reraises_all(handler)


def _disposition(handler: ast.ExceptHandler, preceded: bool, module: object | None, local: dict) -> tuple[str, str | None]:
    """(disposition, problem) for one handler."""
    caught = _caught(handler.type)
    if preceded or _reraises_all(handler):
        return RERAISES, None
    if caught == []:
        return "BARE", "bare except does not re-raise InvariantError"
    what = ast.unparse(handler.type)
    if caught is None:
        return "UNKNOWN", f"except {what}: a catch pattern the audit does not model; it could hold an InvariantError"
    holds = []
    for name in caught:
        cls = _resolve(name, module, local)
        if cls is None:
            return "UNKNOWN", f"except {what}: {name!r} cannot be resolved to an exception class; it could hold an InvariantError"
        if _could_hold(cls):
            holds.append(name)
    if holds:
        return "HOLDS", f"except {what}: could hold an InvariantError ({', '.join(holds)}) and does not re-raise it"
    return STRUCTURAL, None


def audit_source(rel: str, source: str, module: object | None = None) -> tuple[list[dict], list[str]]:
    """Every boundary of one module with its disposition, and the violations among them."""
    tree = ast.parse(source, filename=rel)
    local = _local_classes(tree)
    boundaries, problems = [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Try, ast.TryStar)):
            preceded = False
            for handler in node.handlers:
                disposition, problem = _disposition(handler, preceded, module, local)
                boundaries.append({"path": rel, "line": handler.lineno, "catches": ast.unparse(handler.type) if handler.type else "<bare>",
                                   "disposition": disposition})
                if problem:
                    problems.append(f"EXCEPT_BOUNDARY {rel}:{handler.lineno} {problem}")
                if _is_invariant_reraise(handler):
                    preceded = True
        elif isinstance(node, ast.Call) and ast.unparse(node.func) in ("contextlib.suppress", "suppress"):
            names = [ast.unparse(a) for a in node.args]
            held = [n for n in names if _could_hold(_resolve(n, module, local)) or _resolve(n, module, local) is None]
            boundaries.append({"path": rel, "line": node.lineno, "catches": f"suppress({', '.join(names)})",
                               "disposition": "HOLDS" if held else STRUCTURAL})
            if held:
                problems.append(f"EXCEPT_BOUNDARY {rel}:{node.lineno} suppress({', '.join(names)}) would swallow an InvariantError")
    return boundaries, problems


def violations(rel: str, source: str) -> list[str]:
    return audit_source(rel, source, _import(rel))[1]


def _import(rel: str) -> object | None:
    if not (ROOT / rel).exists():
        return None
    name = rel[:-3].replace("/", ".")
    if name.endswith(".__init__"):
        name = name[:-9]
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def audit(root: pathlib.Path = ROOT) -> dict:
    if issubclass(InvariantError, Exception) or not issubclass(InvariantError, BaseException):
        hierarchy = ["InvariantError must derive from BaseException and not from Exception: an `except Exception` "
                     "boundary could hold it"]
    else:
        hierarchy = []
    boundaries, problems = [], list(hierarchy)
    for path in sorted((root / KERNEL).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        b, p = audit_source(rel, path.read_text(encoding="utf-8"), _import(rel) if root == ROOT else None)
        boundaries += b
        problems += p
    return {"boundaries": boundaries, "problems": problems,
            "counts": {d: sum(1 for b in boundaries if b["disposition"] == d) for d in sorted({b["disposition"] for b in boundaries})}}


def check(root: pathlib.Path = ROOT) -> list[str]:
    return audit(root)["problems"]


def main() -> int:
    result = audit()
    for p in result["problems"]:
        print(f"FAIL  {p}")
    print(f"boundaries {len(result['boundaries'])} {result['counts']}")
    print("except boundaries: " + ("FAIL" if result["problems"] else "PASS"))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
