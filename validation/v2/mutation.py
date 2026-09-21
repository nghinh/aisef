"""V2 mutation testing — AST mutants of one kernel function, each run against the tests that must kill it.

A mutant is **killed** when its kill tests fail (or time out) and **survives** when they pass. A survivor is a gap in
the tests unless it is individually audited as equivalent in `AUDITED`, with a reason; targets listed in
`NO_AUDIT` (the ContractSatisfaction mapping, frozen under F2) must be killed outright.

Kill tests are semantic by design. `compiler_digest` addresses the compiler's own source, so any mutant of the
compiler changes every spec id; tests that compare against committed specs would "kill" every mutant for that
reason alone, so they are never in a kill set.

The record binds each target's module source (LF-normalised sha256): editing a target makes the record stale and
`--check` fails until the mutation run is repeated.

    python -P validation/v2/mutation.py run [target ...]   # run; writes closure-evidence/v2/P1-MUTATION.json
    python -P validation/v2/mutation.py --check            # record current, every target fully killed or audited
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_REL = "closure-evidence/v2/P1-MUTATION.json"
TIMEOUT = 120

#: target "path::function" -> the test files that must kill its mutants (semantic tests only; see module doc).
_CONTRACT_TESTS = ["tests/v2/p1/test_contract.py"]
TARGETS: dict[str, list[str]] = {
    # WP-1.1: contract_hash and the canonical identity it is made of
    "aisef2/product/contract.py::contract_hash": _CONTRACT_TESTS,
    "aisef2/product/contract.py::content_of": _CONTRACT_TESTS,
    "aisef2/product/contract.py::plain": _CONTRACT_TESTS,
    "aisef2/product/contract.py::canonical": _CONTRACT_TESTS,
    "aisef2/product/contract.py::digest": _CONTRACT_TESTS,
    "aisef2/product/contract.py::freeze": _CONTRACT_TESTS,
    # WP-1.2: the compiler and the spec identities (semantic kill set only; never the committed corpus)
    "aisef2/product/compiler.py::compile_spec": ["tests/v2/p1/test_spec_compiler.py"],
    "aisef2/product/compiler.py::expectation_for": ["tests/v2/p1/test_spec_compiler.py"],
    "aisef2/product/spec.py::semantic_hash": ["tests/v2/p1/test_spec_compiler.py"],
    "aisef2/product/spec.py::spec_id": ["tests/v2/p1/test_spec_compiler.py"],
    # WP-1.3: the F2 satisfaction derivation (no audits accepted), subject absence, the EXECUTED invariants
    "aisef2/product/outcome.py::contract_satisfaction": ["tests/v2/p1/test_outcome.py"],
    "aisef2/product/outcome.py::on_subject_absent": ["tests/v2/p1/test_outcome.py"],
    "aisef2/product/outcome.py::__post_init__": ["tests/v2/p1/test_outcome.py"],
    # WP-1.4: the taxonomy and the routing table are data; both are mutated like functions
    "aisef2/control/owner.py::TAXONOMY": ["tests/v2/p1/test_routing.py"],
    "aisef2/control/owner.py::classify": ["tests/v2/p1/test_routing.py"],
    "aisef2/control/owner.py::flatten": ["tests/v2/p1/test_routing.py"],
    "aisef2/control/routing.py::_EXECUTED": ["tests/v2/p1/test_routing.py"],
    "aisef2/control/routing.py::route": ["tests/v2/p1/test_routing.py"],
}
#: Targets whose survivors may not be audited away.
NO_AUDIT: set[str] = {"aisef2/product/outcome.py::contract_satisfaction"}
#: (target, mutant description) -> why the mutant is equivalent. Empty until a survivor is examined by hand.
AUDITED: dict[tuple[str, str], str] = {}
#: What a run copies into its scratch tree.
COPY = ("aisef2", "tests/v2", "validation/v2", "docs/architecture", "docs/implementation/v2", "closure-evidence/v2")

_SWAP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn,
         ast.NotIn: ast.In, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt}


def source_digest(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _enum_members(module_src: str, root: pathlib.Path) -> dict[str, list[str]]:
    """Enum classes visible to the module (its own and those it imports from aisef2), by name -> members."""
    out: dict[str, list[str]] = {}
    tree = ast.parse(module_src)
    sources = [tree]
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("aisef2"):
            dep = root / (n.module.replace(".", "/") + ".py")
            if dep.exists():
                sources.append(ast.parse(dep.read_text(encoding="utf-8")))
    for t in sources:
        for c in ast.walk(t):
            if isinstance(c, ast.ClassDef) and any(getattr(b, "id", "") == "Enum" for b in c.bases):
                out[c.name] = [s.targets[0].id for s in c.body if isinstance(s, ast.Assign)
                               and isinstance(s.targets[0], ast.Name)]
    return out


def _inert(func: ast.AST, doc: ast.AST | None) -> set[int]:
    """Nodes that cannot change behaviour: the docstring and every annotation (postponed, never evaluated)."""
    inert = [doc] if doc is not None else []
    a = func.args
    inert += [x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x and x.annotation]
    inert += [func.returns] if func.returns else []
    inert += [n.annotation for n in ast.walk(func) if isinstance(n, ast.AnnAssign)]
    return {id(n) for root in inert for n in ast.walk(root)}


def _root(tree: ast.Module, name: str) -> tuple[ast.AST, set[int]] | None:
    """A function named `name` (minus its docstring and annotations), or the value of a module-level assignment
    to `name` — so a routing table or a taxonomy held as data is a mutation target like a function is."""
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name:
            doc = n.body[0] if n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str) else None
            return n, _inert(n, doc)
    for n in tree.body:
        if isinstance(n, ast.Assign):
            names = [getattr(x, "id", None) for x in n.targets]
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            names = [getattr(n.target, "id", None)]
        else:
            continue
        if name in names:
            return n.value, set()
    return None


def mutants(module_src: str, func: str, enums: dict[str, list[str]]) -> list[tuple[str, str]]:
    """(description, mutated module source) for every mutation site inside the function or table `func`."""
    tree = ast.parse(module_src)
    found = _root(tree, func)
    if found is None:
        raise SystemExit(f"function or module-level table {func} not found")
    target, skip = found
    sites = [n for n in ast.walk(target) if n is not target and id(n) not in skip]
    out = []

    def emit(desc: str, node: ast.AST, apply) -> None:
        t2 = copy.deepcopy(tree)
        f2, skip2 = _root(t2, func)
        twin = [n for n in ast.walk(f2) if n is not f2 and id(n) not in skip2][sites.index(node)]
        if apply(twin, f2) is not False:
            out.append((f"L{getattr(node, 'lineno', getattr(target, 'lineno', 0))} {desc}",
                        ast.unparse(ast.fix_missing_locations(t2))))

    for node in sites:
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in _SWAP:
                    emit(f"{type(op).__name__}->{_SWAP[type(op)].__name__}", node,
                         lambda n, _f, i=i: n.ops.__setitem__(i, _SWAP[type(n.ops[i])]()))
        elif isinstance(node, ast.BoolOp):
            emit(f"{type(node.op).__name__} swapped", node,
                 lambda n, _f: setattr(n, "op", ast.Or() if isinstance(n.op, ast.And) else ast.And()))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            emit("not removed", node, lambda n, _f: setattr(n, "op", ast.UAdd()))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            emit(f"{node.value}->{not node.value}", node, lambda n, _f: setattr(n, "value", not n.value))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            emit(f"string {node.value!r} emptied", node, lambda n, _f: setattr(n, "value", ""))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in enums:
            for alt in enums[node.value.id]:
                if alt != node.attr:
                    emit(f"{node.value.id}.{node.attr}->{alt}", node, lambda n, _f, alt=alt: setattr(n, "attr", alt))
        elif isinstance(node, ast.Dict):
            for i in range(len(node.keys)):
                emit(f"dict entry {i} dropped", node,
                     lambda n, _f, i=i: (n.keys.pop(i), n.values.pop(i)))
        elif isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) > 1:
            for i in range(len(node.elts)):
                emit(f"element {i} dropped", node, lambda n, _f, i=i: n.elts.pop(i))
        elif isinstance(node, ast.If):
            emit("condition negated", node, lambda n, _f: setattr(n, "test", ast.UnaryOp(ast.Not(), n.test)))
        elif isinstance(node, ast.IfExp):
            emit("conditional negated", node, lambda n, _f: setattr(n, "test", ast.UnaryOp(ast.Not(), n.test)))
        elif isinstance(node, ast.Return) and node.value is not None:
            emit("returns None", node, lambda n, _f: setattr(n, "value", ast.Constant(None)))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("sorted", "tuple") and len(node.args) == 1:
            emit(f"{node.func.id}() -> list()", node, lambda n, _f: setattr(n, "func", ast.Name("list", ast.Load())))
    return out


def _run_tests(root: pathlib.Path, tests: list[str]) -> bool:
    """True when every kill test passes."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    for rel in tests:
        path = pathlib.PurePosixPath(rel)
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(path.parent), "-t", "tests", "-p", path.name]
        try:
            r = subprocess.run(cmd, cwd=root, capture_output=True, encoding="utf-8", timeout=TIMEOUT, env=env)
        except subprocess.TimeoutExpired:
            return False
        if r.returncode != 0:
            return False
    return True


def run_target(root: pathlib.Path, target: str, tests: list[str]) -> dict:
    rel, func = target.split("::")
    with tempfile.TemporaryDirectory() as t:
        work = pathlib.Path(t) / "tree"
        for part in COPY:
            src = root / part
            if src.is_dir():
                shutil.copytree(src, work / part, ignore=shutil.ignore_patterns("__pycache__"))
            elif src.exists():
                (work / part).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, work / part)
        path = work / rel
        original = path.read_text(encoding="utf-8")
        if not _run_tests(work, tests):
            return {"target": target, "error": "kill tests fail on the unmutated tree", "mutants": []}
        results = []
        for desc, src in mutants(original, func, _enum_members(original, work)):
            path.write_text(src, encoding="utf-8")
            killed = not _run_tests(work, tests)
            results.append({"mutant": desc, "killed": killed})
        path.write_text(original, encoding="utf-8")
    survivors = [r["mutant"] for r in results if not r["killed"]]
    return {"target": target, "kill_tests": tests, "source_sha256": source_digest(original),
            "mutants": len(results), "killed": len(results) - len(survivors),
            "survivors": survivors, "results": results}


def target_problems(t: dict, root: pathlib.Path = ROOT) -> list[str]:
    """The verdict on one target's result: unchanged since the run, mutants generated, every survivor accounted for."""
    if t.get("error"):
        return [f"{t['target']}: {t['error']}"]
    out = []
    rel = t["target"].split("::")[0]
    if source_digest((root / rel).read_text(encoding="utf-8")) != t["source_sha256"]:
        out.append(f"{t['target']}: target changed since the mutation run — re-run it")
    if t["mutants"] == 0:
        out.append(f"{t['target']}: no mutants generated — a run that cannot say NO proves nothing")
    for m in t["survivors"]:
        if t["target"] in NO_AUDIT:
            out.append(f"{t['target']}: survivor {m!r} (must be fully killed; audits not accepted)")
        elif (t["target"], m) not in AUDITED:
            out.append(f"{t['target']}: unaudited survivor {m!r}")
    return out


def problems_of(record: dict, root: pathlib.Path = ROOT) -> list[str]:
    seen = {t["target"] for t in record["targets"]}
    out = [f"{t} has no mutation result" for t in TARGETS if t not in seen]
    return out + [p for t in record["targets"] for p in target_problems(t, root)]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = ROOT / OUT_REL
    if argv[:1] == ["run"]:
        chosen = argv[1:] or list(TARGETS)
        record = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
            "record": "AISEF V2 — P1 MUTATION", "tool": "validation/v2/mutation.py", "targets": []}
        kept = [t for t in record["targets"] if t["target"] not in chosen and t["target"] in TARGETS]
        fresh = [run_target(ROOT, t, TARGETS[t]) for t in chosen]
        record["targets"] = sorted(kept + fresh, key=lambda t: t["target"])
        out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        for t in fresh:
            print(f"{t['target']}: {t.get('killed')}/{t.get('mutants')} killed; survivors {t.get('survivors')}"
                  + (f" ERROR {t['error']}" if t.get("error") else ""))
    record = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"targets": []}
    problems = problems_of(record)
    for p in problems:
        print(f"FAIL  {p}")
    print("mutation: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
