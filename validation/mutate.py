"""Phase 13 — targeted mutation testing of decision-critical kernel code (development-only, stdlib).

    python3 validation/mutate.py --targets validation/mutation-targets.json --workers 4 \
        --out closure-evidence/hardening/mutation-results.json

A target names a module, a function and the test files that must kill any mutant of it. Every mutant is one
AST change at one site (operators below). Each mutant runs in its own copy of the repository (the working
tree is never touched): the mutated source replaces the module in the copy, the target's tests run there
with pytest, a non-zero exit KILLS the mutant, exit 0 means it SURVIVED. Mutants listed in the targets file
under "equivalent" (with a justification) are reported separately and never count as survivors.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE = shutil.ignore_patterns(".git", "closure-evidence", ".aisef", "_bmad-output", "__pycache__", ".pytest_cache",
                                "node_modules", "*.egg-info", "dist", "build", ".venv", "landingpage", "references", "spike")

CMP_FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
            ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
#: decision vocabulary swaps — attribute or name pairs that flip a verdict's meaning
NAME_SWAPS = {"PASSED": "FAILED", "FAILED": "PASSED", "UNRUNNABLE": "FAILED", "NOT_APPLICABLE": "PASSED",
              "REVIEW_UNRUNNABLE": "REVIEW_BLOCK", "True": "False", "False": "True"}
STR_SWAPS = {"pass": "block", "block": "pass", "stuck": "block", "review": "security", "test": "lint"}


class _Site(ast.NodeTransformer):
    """Apply exactly one operator at the n-th eligible site inside the target function."""

    def __init__(self, op: str, index: int):
        self.op, self.index, self.seen, self.applied, self.where = op, index, 0, False, ""

    def _take(self, node, desc: str) -> bool:
        if self.applied or self.seen != self.index:
            self.seen += 1
            return False
        self.seen += 1
        self.applied, self.where = True, f"line {getattr(node, 'lineno', '?')}: {desc}"
        return True

    # operators
    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.op == "CMP" and len(node.ops) == 1 and type(node.ops[0]) in CMP_FLIP:
            if self._take(node, f"{type(node.ops[0]).__name__} → {CMP_FLIP[type(node.ops[0])].__name__}"):
                node.ops = [CMP_FLIP[type(node.ops[0])]()]
        return node

    def visit_If(self, node):
        if self.op == "NOT" and self._take(node, "negate if-condition"):
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        self.generic_visit(node)
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self.op == "ANDOR" and self._take(node, "and ↔ or"):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_Constant(self, node):
        if self.op == "BOOL" and isinstance(node.value, bool) and self._take(node, f"{node.value} → {not node.value}"):
            return ast.copy_location(ast.Constant(value=not node.value), node)
        if self.op == "STR" and isinstance(node.value, str) and node.value in STR_SWAPS and self._take(node, f"{node.value!r} → {STR_SWAPS[node.value]!r}"):
            return ast.copy_location(ast.Constant(value=STR_SWAPS[node.value]), node)
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if self.op == "VERDICT" and node.attr in NAME_SWAPS and node.attr not in ("True", "False") and self._take(node, f".{node.attr} → .{NAME_SWAPS[node.attr]}"):
            node.attr = NAME_SWAPS[node.attr]
        return node

    def visit_Name(self, node):
        if self.op == "VERDICT" and node.id in NAME_SWAPS and node.id not in ("True", "False") and self._take(node, f"{node.id} → {NAME_SWAPS[node.id]}"):
            node.id = NAME_SWAPS[node.id]
        return node

    def visit_AugAssign(self, node):
        if self.op == "INCR" and isinstance(node.op, (ast.Add, ast.Sub)) and self._take(node, "+= n → += 0 (no increment)"):
            node.value = ast.Constant(value=0)
        return node

    def visit_Return(self, node):
        self.generic_visit(node)
        if self.op == "RET" and node.value is not None and isinstance(node.value, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            if self._take(node, "return X → return not X"):
                node.value = ast.UnaryOp(op=ast.Not(), operand=node.value)
        return node

    def visit_Expr(self, node):
        # drop a statement-level call: `s.invalidate_dependent()`, `evidence.record(...)`, `run_log(...)` — the
        # "evidence invalidation / recording removed" mutation
        if self.op == "DROPCALL" and isinstance(node.value, ast.Call):
            name = ast.unparse(node.value.func)
            if not name.endswith(("run_log", "print", "_log")) and self._take(node, f"drop call {name}(...)"):
                return ast.copy_location(ast.Pass(), node)
        return node


OPERATORS = ("CMP", "NOT", "ANDOR", "BOOL", "STR", "VERDICT", "INCR", "RET", "DROPCALL")


def _function(tree: ast.Module, qualname: str) -> ast.AST | None:
    parts = qualname.split(".")
    scope: ast.AST = tree
    for part in parts:
        found = next((n for n in ast.walk(scope) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part), None)
        if found is None:
            return None
        scope = found
    return scope


def mutants_for(module: Path, qualname: str, operators=OPERATORS) -> list[dict]:
    src = module.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = _function(tree, qualname)
    if fn is None:
        raise SystemExit(f"{module}: no function {qualname}")
    out = []
    for op in operators:
        index = 0
        while True:
            t2 = copy.deepcopy(tree)
            fn2 = _function(t2, qualname)
            site = _Site(op, index)
            site.visit(fn2)
            if not site.applied:
                break
            ast.fix_missing_locations(t2)
            mutated = ast.unparse(t2)
            mid = hashlib.sha1(f"{module}:{qualname}:{op}:{index}".encode()).hexdigest()[:10]
            out.append({"id": mid, "module": str(module.relative_to(ROOT)), "function": qualname, "operator": op,
                        "site": site.where, "source": mutated})
            index += 1
    return out


def _run_mutant(args) -> dict:
    mutant, tests, copy_dir, timeout = args
    target = Path(copy_dir) / mutant["module"]
    original = target.read_text(encoding="utf-8")
    t0 = time.time()
    try:
        target.write_text(mutant["source"], encoding="utf-8")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "AISEF_MODEL_TRACES": "300", "AISEF_DIFF_TRACES": "6"}
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider", *tests],
                               cwd=copy_dir, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, env=env)
            status = "KILLED" if r.returncode != 0 else "SURVIVED"
            tail = (r.stdout + r.stderr).strip().splitlines()[-1:] if r.returncode else []
        except subprocess.TimeoutExpired:
            status, tail = "KILLED", ["timeout (treated as killed: the mutant hung the suite)"]
    finally:
        target.write_text(original, encoding="utf-8")
    return {k: v for k, v in mutant.items() if k != "source"} | {"status": status, "seconds": round(time.time() - t0, 1), "last_line": tail[0] if tail else ""}


def _worker(batch) -> list[dict]:
    copy_dir = tempfile.mkdtemp(prefix="aisef-mut-")
    try:
        shutil.copytree(ROOT, copy_dir, ignore=IGNORE, dirs_exist_ok=True)
        return [_run_mutant((m, tests, copy_dir, timeout)) for m, tests, timeout in batch]
    finally:
        shutil.rmtree(copy_dir, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", default=str(ROOT / "closure-evidence/hardening/mutation-results.json"))
    ap.add_argument("--only", help="run only mutants of this module::function")
    ap.add_argument("--list", action="store_true", help="list mutants without running")
    a = ap.parse_args(argv)
    spec = json.loads(Path(a.targets).read_text(encoding="utf-8"))
    equivalent = {e["id"]: e["why"] for e in spec.get("equivalent", [])}
    jobs, catalog = [], []
    for t in spec["targets"]:
        key = f"{t['module']}::{t['function']}"
        if a.only and a.only != key:
            continue
        for m in mutants_for(ROOT / t["module"], t["function"], t.get("operators", OPERATORS)):
            m["kills_expected_by"] = t["tests"]
            m["decision"] = t.get("decision", "")
            catalog.append(m)
            if m["id"] not in equivalent:
                jobs.append((m, t["tests"], a.timeout))
    if a.list:
        for m in catalog:
            print(m["id"], m["module"], m["function"], m["operator"], m["site"], "(equivalent)" if m["id"] in equivalent else "")
        print(len(catalog), "mutants")
        return 0
    t0 = time.time()
    batches = [jobs[i::a.workers] for i in range(a.workers)] if a.workers > 1 else [jobs]
    rows: list[dict] = []
    if a.workers > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for part in ex.map(_worker, batches):
                rows.extend(part)
    else:
        rows = _worker(batches[0])
    by_id = {r["id"]: r for r in rows}
    result_rows = []
    for m in catalog:
        row = {k: v for k, v in m.items() if k != "source"}
        if m["id"] in equivalent:
            row |= {"status": "EQUIVALENT", "why": equivalent[m["id"]]}
        else:
            row |= {k: by_id[m["id"]][k] for k in ("status", "seconds", "last_line")}
        result_rows.append(row)
    counts = {s: sum(1 for r in result_rows if r["status"] == s) for s in ("KILLED", "SURVIVED", "EQUIVALENT")}
    out = {"program": "AISEF SYSTEMATIC HARDENING PROGRAM v1", "phase": 13, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "targets": [f"{t['module']}::{t['function']}" for t in spec["targets"]], "operators": list(OPERATORS),
           "mutations_generated": len(result_rows), **{k.lower(): v for k, v in counts.items()},
           "survivors": [r for r in result_rows if r["status"] == "SURVIVED"],
           "elapsed_s": round(time.time() - t0, 1), "workers": a.workers, "rows": result_rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("mutations_generated", "killed", "survived", "equivalent", "elapsed_s")}))
    for r in out["survivors"]:
        print("SURVIVED", r["id"], r["module"], r["function"], r["operator"], r["site"])
    return 1 if counts["SURVIVED"] else 0


if __name__ == "__main__":
    sys.exit(main())
