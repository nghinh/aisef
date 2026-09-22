"""WP-3.5 — the six reference models import nothing of the implementation they check (RFC §21, §27 Q1).

Rule: a module under `tests/v2/refmodel/` imports only the Python standard library and its own package (relative
imports, or `tests.v2.refmodel.*`). No `aisef2` — so neither `aisef2.journal.projections` nor `aisef2.journal.fold`,
nor anything they could re-export — no other `tests` module, and no `importlib`, `__import__`, `exec`, `eval` or
`compile`, which would reach the implementation dynamically. Fails closed: the package must hold all six models.
This is the V1 policy model's AST no-import discipline, applied to the projections' reference models.

    python -P validation/v2/refmodel_independence.py      # exit 1 on any violation
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = "tests/v2/refmodel"
MODELS = ("story_state", "failure_owner", "budgets", "retry_target", "terminal_state", "qualification_counters")
_DYNAMIC = {"importlib", "__import__", "exec", "eval", "compile"}


def _allowed(module: str) -> bool:
    top = module.split(".")[0]
    if module == "tests.v2.refmodel" or module.startswith("tests.v2.refmodel."):
        return True
    return top in sys.stdlib_module_names and top != "importlib"


def violations(rel: str, source: str) -> list[str]:
    out = []
    for n in ast.walk(ast.parse(source, filename=rel)):
        if isinstance(n, ast.Import):
            out += [f"REFMODEL_INDEPENDENT {rel}:{n.lineno} imports {a.name}" for a in n.names if not _allowed(a.name)]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and not _allowed(n.module or ""):
            out.append(f"REFMODEL_INDEPENDENT {rel}:{n.lineno} imports {n.module}")
        elif isinstance(n, ast.Name) and n.id in _DYNAMIC or isinstance(n, ast.Attribute) and n.attr in _DYNAMIC:
            out.append(f"REFMODEL_INDEPENDENT {rel}:{n.lineno} uses {getattr(n, 'id', getattr(n, 'attr', ''))}")
    return out


def check(root: pathlib.Path = ROOT) -> list[str]:
    pkg = root / PACKAGE
    missing = [m for m in ("__init__", *MODELS) if not (pkg / f"{m}.py").is_file()]
    out = [f"REFMODEL_INDEPENDENT {PACKAGE}: missing {m}.py" for m in missing]
    for path in sorted(pkg.rglob("*.py")) if pkg.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        out += violations(rel, path.read_text(encoding="utf-8"))
    return out


def main() -> int:
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("refmodel independence: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
