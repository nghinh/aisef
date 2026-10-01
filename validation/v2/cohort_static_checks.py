"""C2-P10 / WP-2.10.1 — Q0 static rules over the evaluation-cohort machinery (`aisef2/cohort/`). Each is a calibrated
checker (validation/v2/checker_calibration.py).

* **COHORT_CONFINED** — nothing Q4, Q5, the probes, the compiler or any other consumer runs imports the machinery: no
  Python module of the repository outside `ALLOWED_IMPORTERS` (the package itself, this checker, the profile freeze,
  the C2-P10 record builders and the C2-P10 tests) imports `aisef2.cohort` — by `import`, `from`, a relative import,
  or `importlib.import_module` / `__import__` with a literal name.
* **COHORT_BOUNDARY** — the machinery reaches only the standard library and `ALLOWED_DEPENDENCIES` (identity grades,
  RunSpec, PlanQualityPolicy, canonical content): never the journal, so a cohort state is carried in no event (F1),
  and never orchestration, admission, probes, control or engineering quality.
* **DEVELOPMENT_REGRESSION_BOUND** — every DEVELOPMENT_REGRESSION entry (RFC §30) carries exactly the frozen identity
  its files hold: the requirements file's sha256, the workload record's sha256, and the record's plan baseline and
  plan hash. Fails closed on an empty registry and on a registry without the P10 LedgerLock workload record.
* **NO_COHORT_RECORD** — no cohort exists: no JSON or JSON-lines file of the tree (tracked or not ignored) holds,
  at any depth, an object whose `schema` is the preregistration schema — every persisted preregistration or cohort
  carries one. A file that does not parse is searched for the schema id as text.

    python -P validation/v2/cohort_static_checks.py --check
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PACKAGE = "aisef2.cohort"
COHORT_DIR = "aisef2/cohort"
ALLOWED_IMPORTERS = ("aisef2/cohort/", "validation/v2/cohort_static_checks.py", "validation/v2/profile_freeze.py",
                     "validation/qualification/c2_p10_", "tests/v2/test_c2_p10_")
ALLOWED_DEPENDENCIES = ("aisef2.arch.enums", "aisef2.plan.obligation", "aisef2.product.contract",
                        "aisef2.runtime.capability", "aisef2.runtime.runspec", "aisef2.cohort")
P10_WORKLOAD = "closure-evidence/v2/P10/WORKLOAD.json"
RULES = ("COHORT_CONFINED", "COHORT_BOUNDARY", "DEVELOPMENT_REGRESSION_BOUND", "NO_COHORT_RECORD")
SOURCE_RULES = RULES[:2]


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _listed(root: pathlib.Path, *patterns: str) -> list[str]:
    """The tree's files: tracked, or untracked and not ignored (a record written but not yet committed counts)."""
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *patterns],
                         cwd=root, capture_output=True, check=True).stdout.decode("utf-8")
    return sorted({p for p in out.split("\0") if p and (root / p).is_file()})


# --------------------------------------------------------------------------------------- source rules

def _imported(path: str, tree: ast.Module) -> list[tuple[int, str]]:
    """(line, absolute module) of every import in `tree`, relative imports resolved against `path`."""
    package = path.rsplit("/", 1)[0].split("/") if "/" in path else []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = ".".join(package[:len(package) - n.level + 1]) if n.level else ""
            module = ".".join(p for p in (base, n.module or "") if p)
            out += [(n.lineno, module)] + [(n.lineno, f"{module}.{a.name}") for a in n.names]
        elif isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", None)) in (
                "import_module", "__import__") and n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str):
            out.append((n.lineno, n.args[0].value))
    return out


def _names_cohort(module: str) -> bool:
    return module == PACKAGE or module.startswith(PACKAGE + ".")


def _outside(module: str) -> bool:
    """Whether the machinery may not import `module`: neither the standard library nor an allowed dependency."""
    if any(module == d or module.startswith(d + ".") for d in ALLOWED_DEPENDENCIES):
        return False
    top = module.split(".")[0]
    return top not in sys.stdlib_module_names or top in ("aisef", "aisef2")


def violations(path: str, source: str, rules: tuple[str, ...] = SOURCE_RULES) -> list[str]:
    """One finding per import line and rule."""
    found: dict[tuple[str, int], str] = {}
    for line, m in _imported(path, ast.parse(source)):
        if "COHORT_CONFINED" in rules and not path.startswith(ALLOWED_IMPORTERS) and _names_cohort(m):
            found.setdefault(("COHORT_CONFINED", line), f"COHORT_CONFINED {path}:{line} imports {PACKAGE}: nothing "
                             "outside the machinery, its checks and its tests imports it")
        if "COHORT_BOUNDARY" in rules and path.startswith(COHORT_DIR + "/") and _outside(m):
            found.setdefault(("COHORT_BOUNDARY", line), f"COHORT_BOUNDARY {path}:{line} imports {m}: the machinery "
                             f"reaches only the standard library and {', '.join(ALLOWED_DEPENDENCIES)}")
    return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------------------- registry binding

def binding_problems(root: pathlib.Path, entries) -> list[str]:
    out = [] if entries else ["DEVELOPMENT_REGRESSION_BOUND the registry is empty (RFC §30: LedgerLock is in it)"]
    if not any(e.get("workload_record") == P10_WORKLOAD for e in entries):
        out.append(f"DEVELOPMENT_REGRESSION_BOUND no entry is bound to {P10_WORKLOAD}")
    for e in entries:
        label = e.get("label")
        try:
            record = json.loads((root / e["workload_record"]).read_text(encoding="utf-8"))
            facts = {"requirements_sha256": _sha(root / e["requirements_source"]),
                     "workload_record_sha256": _sha(root / e["workload_record"]),
                     "plan_baseline": record["plan"]["baseline"], "plan_hash": record["plan"]["plan_hash"]}
        except (KeyError, TypeError, ValueError, OSError) as x:
            out.append(f"DEVELOPMENT_REGRESSION_BOUND {label}: its sources cannot be read ({x!r})")
            continue
        out += [f"DEVELOPMENT_REGRESSION_BOUND {label}: {k} is {e.get(k)!r}, its file holds {v!r}"
                for k, v in facts.items() if e.get(k) != v]
    return out


# --------------------------------------------------------------------------------------- census

def _holds(value, schema: str, where: str = "$") -> list[str]:
    if isinstance(value, dict):
        here = [where] if value.get("schema") == schema else []
        return here + [w for k, v in value.items() for w in _holds(v, schema, f"{where}.{k}")]
    if isinstance(value, list):
        return [w for i, v in enumerate(value) for w in _holds(v, schema, f"{where}[{i}]")]
    return []


def census(root: pathlib.Path, files: list[str]) -> list[str]:
    """Every place in `files` (relative to `root`) that holds a preregistration or a cohort record."""
    from aisef2.cohort.preregistration import SCHEMA
    found = []
    for rel in files:
        raw = (root / rel).read_bytes().decode("utf-8", errors="replace")
        try:
            docs = [json.loads(line) for line in raw.splitlines() if line.strip()] if rel.endswith(".jsonl") \
                else [json.loads(raw)]
        except ValueError:
            found += [f"{rel} (unparsed; names {SCHEMA})"] if SCHEMA in raw else []
            continue
        found += [f"{rel} {w}" for i, d in enumerate(docs) for w in _holds(d, SCHEMA, f"${i}" if len(docs) > 1 else "$")]
    return found


def census_problems(found: list[str]) -> list[str]:
    return [f"NO_COHORT_RECORD {f}: holds a preregistration — no cohort is authorized" for f in found]


# --------------------------------------------------------------------------------------- the checker

def check(root: pathlib.Path = ROOT, rules: tuple[str, ...] = RULES) -> list[str]:
    out = []
    source_rules = tuple(r for r in rules if r in SOURCE_RULES)
    if source_rules:
        for rel in _listed(root, "*.py"):
            out += violations(rel, (root / rel).read_text(encoding="utf-8"), source_rules)
        if "COHORT_BOUNDARY" in rules and not (root / COHORT_DIR).is_dir():
            out.append(f"COHORT_BOUNDARY {COHORT_DIR} does not exist")
    if "DEVELOPMENT_REGRESSION_BOUND" in rules:
        from aisef2.cohort.preregistration import DEVELOPMENT_REGRESSION
        out += binding_problems(root, DEVELOPMENT_REGRESSION)
    if "NO_COHORT_RECORD" in rules:
        out += census_problems(census(root, _listed(root, "*.json", "*.jsonl")))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rules = tuple(a for a in argv if a in RULES) or RULES
    problems = check(ROOT, rules)
    for p in problems:
        print(f"FAIL  {p}")
    print(f"cohort static checks: {'FAIL' if problems else 'PASS'} ({len(rules)} rules)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
