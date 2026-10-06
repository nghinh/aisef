"""V2.1 (B-03c): the limits of the two authorities 2.1 adds, enforced statically over aisef2 — `aisef bundle migrate`
(aisef2/app/bundle_cli.py::migrate) and the review reproducer's verification (aisef2/app/review_verify.py::verify).

Owner ruling B-03c: migrate creates a new bundle and never approves it; verify checks by probe and returns its result
under the policy; neither commits or merges the product, nor makes a second final decision path. The release
inventory (release_inventory.py) names both PRODUCT_TRUTH authorities; these rules keep them inside those limits, each
violation reported as `RULE rel:line explanation`:

* **MIGRATE_NEVER_APPROVES** — nothing migrate reaches in aisef2/app calls `bundle_cli.approve`, constructs a
  ContractApproval other than by re-loading one of the input's (`ContractApproval(**a) for a in data["approvals"]`),
  or writes approvals (an `approvals` key or keyword, or a call that grows `...["approvals"]`).
* **NO_COMMIT_OR_MERGE** — nothing migrate or verify reaches in aisef2/app runs git, commits, merges, writes a gate row
  or decision, classifies, reviews, runs a story or appends a control event to a journal.
* **VERIFY_THROUGH_BINDING_AND_CALIBRATION** — verify runs a probe, and every `run_probe` in it is the record
  `bound_result` binds (PROBE-BIND-1), after a calibration lookup that returns when the class is not calibrated.
* **ONE_DECISION_PATH** — across aisef2, verify is named only by `Reviewer._verify` (aisef2/app/adapters.py),
  `review_verify.blocks` only by `Reviewer.review` and migrate only by `bundle_cli.main`; every Finding the Reviewer
  builds is corroborated only as `(...) if <what blocks() answered> else ()` (or never): a finding blocks only when
  blocks() said so, through the kernel's review gate row and its one decision (story_runner._attempt).

"Reaches" is the static closure over names that resolve (imports, module definitions), followed inside aisef2/app;
a call through an object (`entry.factory()`, `self.x`) is not followed — the behavioural tests (test_v21_identity
Migrate, test_v21_review, test_v21_review_chain) cover what those do at run time.

    python -P validation/qualification/authority_limits.py     # exit 1 on any violation
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification.release_inventory import _opa  # noqa: E402 — old_path_audit's AST helpers

opa = _opa()

APP = "aisef2/app/"
MIGRATE, VERIFY, BLOCKS = "aisef2.app.bundle_cli.migrate", "aisef2.app.review_verify.verify", "aisef2.app.review_verify.blocks"
#: what each of them is named by, and nothing else in aisef2
ONLY_NAMED_BY = {VERIFY: ("aisef2/app/adapters.py", "Reviewer._verify"), BLOCKS: ("aisef2/app/adapters.py", "Reviewer.review"),
                 MIGRATE: ("aisef2/app/bundle_cli.py", "main")}
REVIEWER, FINDING = ("aisef2/app/adapters.py", "Reviewer"), "aisef2.orchestrate.adapters.Finding"
APPROVE, APPROVAL = "aisef2.app.bundle_cli.approve", "aisef2.product.approval.ContractApproval"
RUN_PROBE, BOUND, CALIBRATION_FOR = ("aisef2.probe.protocol.run_probe", "aisef2.probe.protocol.bound_result",
                                     "aisef2.probe.calibration.calibration_for")
EVENT_TYPE = "aisef2.arch.enums.EventType"
#: what a migration or a verification never reaches
DECIDING = {"aisef2.orchestrate.workspace.git", "aisef2.orchestrate.workspace.commit_all",
            "aisef2.orchestrate.workspace.GitMerger", "aisef2.app.run.git", "aisef2.orchestrate.merge.merge",
            "aisef2.orchestrate.merge.reprove", "aisef2.orchestrate.gate.check", "aisef2.orchestrate.gate.decision",
            "aisef2.control.owner.classify", "aisef2.plan.story_admission.classify", "aisef2.orchestrate.review.review",
            "aisef2.orchestrate.story_runner.run_story"}


class _Module:
    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.tree = rel, ast.parse(text)
        self.imports = opa._imports(self.tree, rel)
        self.defs = opa._defs(self.tree)
        self.local = {name for name, _ in self.defs if "." not in name}

    def name(self, node: ast.AST) -> str | None:
        """The qualified name a reference (a Name or an Attribute chain) resolves to, or None."""
        dotted = opa._dotted(node)
        return opa._qualify(dotted, self.imports, self.rel, self.local) if dotted else None

    def scopes(self):
        """(scope name, node) for each top-level statement, a class's methods by `Class.method`."""
        for n in self.tree.body:
            if isinstance(n, ast.ClassDef):
                for m in n.body:
                    yield (f"{n.name}.{m.name}", m) if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) else (n.name, m)
            else:
                yield (n.name if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<module>"), n


def _modules(root: pathlib.Path, sources: dict[str, str]) -> dict[str, _Module]:
    rels = set(opa._py_files(root, ("aisef2/",))) | set(sources)
    return {rel: _Module(rel, sources[rel] if rel in sources else (root / rel).read_text(encoding="utf-8"))
            for rel in sorted(rels)}


def _loads(node: ast.AST):
    return (n for n in ast.walk(node) if isinstance(n, (ast.Name, ast.Attribute)) and isinstance(n.ctx, ast.Load))


# ponytail: names only, no points-to analysis; an object's method is not followed (module docstring)
def _closure(mods: dict[str, _Module], index: dict, starts: tuple[str, ...]) -> list[tuple[str, str, ast.AST]]:
    """(qualified name, rel, node) of every definition of aisef2/app that `starts` reach through resolved names."""
    seen, todo = set(), list(starts)
    while todo:
        q = todo.pop()
        if q in seen or q not in index:
            continue
        seen.add(q)
        rel, node = index[q]
        todo += [r for n in _loads(node) if (r := mods[rel].name(n)) in index and index[r][0].startswith(APP)]
    return [(q, *index[q]) for q in sorted(seen)]


def _short(q: str) -> str:
    return q.removeprefix("aisef2.app.")


def _is_approvals(n: ast.AST) -> bool:
    return isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == "approvals"


def _reloaded(node: ast.AST) -> set[str]:
    """The names a scope binds to each element of a `...["approvals"]`: the input's approvals, re-loaded."""
    return {g.target.id for g in ast.walk(node) if isinstance(g, (ast.comprehension, ast.For))
            and isinstance(g.target, ast.Name) and _is_approvals(g.iter)}


def _approves(m: _Module, n: ast.AST, reloaded: set[str]) -> str | None:
    if isinstance(n, ast.Call):
        callee = m.name(n.func)
        if callee == APPROVE:
            return "calls bundle_cli.approve"
        if callee == APPROVAL and not (not n.args and len(n.keywords) == 1 and n.keywords[0].arg is None
                                       and isinstance(n.keywords[0].value, ast.Name) and n.keywords[0].value.id in reloaded):
            return "creates a ContractApproval (a migration only re-loads the input's: ContractApproval(**a))"
        if any(k.arg == "approvals" for k in n.keywords) and (callee == "dict" or getattr(n.func, "attr", None) == "update"):
            return "writes the approvals"
        if isinstance(n.func, ast.Attribute) and n.func.attr in ("append", "extend", "insert") and _is_approvals(n.func.value):
            return "writes the approvals"
    if isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "approvals" for k in n.keys):
        return "writes an 'approvals' key"
    if _is_approvals(n) and isinstance(n.ctx, ast.Store):
        return "writes an 'approvals' key"
    return None


def _decides(m: _Module, n: ast.Call) -> str | None:
    callee = m.name(n.func) or ""
    if callee in DECIDING or callee.startswith("aisef2.orchestrate.workspace.GitMerger."):
        return f"calls {callee}"
    if n.args and isinstance(n.args[0], (ast.List, ast.Tuple)) and n.args[0].elts \
            and isinstance(n.args[0].elts[0], ast.Constant) and n.args[0].elts[0].value == "git":
        return "runs git"
    if isinstance(n.func, ast.Attribute) and n.func.attr == "append" and n.args \
            and isinstance(n.args[0], ast.Attribute) and m.name(n.args[0].value) == EVENT_TYPE:
        return f"appends the control event {n.args[0].attr} to a journal"
    return None


def _verify_rule(m: _Module, node: ast.AST) -> list[str]:
    rule = "VERIFY_THROUGH_BINDING_AND_CALIBRATION"
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
    bound = {id(n.args[0]) for n in calls if n.args and m.name(n.func) == BOUND}
    guards = [g.lineno for g in ast.walk(node) if isinstance(g, ast.If) and any(isinstance(s, ast.Return) for s in g.body)
              and any(isinstance(c, ast.Call) and m.name(c.func) == CALIBRATION_FOR for c in ast.walk(g.test))]
    probes = [n for n in calls if m.name(n.func) == RUN_PROBE]
    if not probes:
        return [f"{rule} {m.rel}:{node.lineno} verify runs no probe: a confirmation is the kernel's probe's, never the finding's"]
    out = []
    for n in probes:
        if id(n) not in bound:
            out.append(f"{rule} {m.rel}:{n.lineno} verify reads run_probe's record unbound: every run_probe is "
                       "bound_result's first argument (PROBE-BIND-1)")
        if not any(ln < n.lineno for ln in guards):
            out.append(f"{rule} {m.rel}:{n.lineno} verify runs the probe with no calibration lookup before it that "
                       "returns when the class is not calibrated at the bytes that run")
    return out


def _empty(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Tuple) and not node.elts


def _gated(arg: ast.AST | None, line: int, assigned: dict[str, list[tuple[int, str | None]]]) -> bool:
    """`arg` is `()`, or `(...) if N else ()` with N last bound, before `line`, to what review_verify.blocks answered."""
    if _empty(arg):
        return True
    if not (isinstance(arg, ast.IfExp) and _empty(arg.orelse) and isinstance(arg.test, ast.Name)):
        return False
    before = [callee for ln, callee in assigned.get(arg.test.id, []) if ln < line]
    return bool(before) and before[-1] == BLOCKS


def _corroboration(mods: dict[str, _Module]) -> list[str]:
    rule, (rel, cls) = "ONE_DECISION_PATH", REVIEWER
    m = mods.get(rel)
    node = next((n for n in m.tree.body if isinstance(n, ast.ClassDef) and n.name == cls), None) if m else None
    if node is None:
        return [f"{rule} {rel}:1 {cls} is missing"]
    out, built = [], 0
    for meth in (f for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))):
        assigned: dict[str, list] = {}
        for a in sorted((a for a in ast.walk(meth) if isinstance(a, ast.Assign)), key=lambda a: a.lineno):
            for t in (t for t in a.targets if isinstance(t, ast.Name)):
                assigned.setdefault(t.id, []).append((a.lineno, m.name(a.value.func) if isinstance(a.value, ast.Call) else None))
        for n in ast.walk(meth):
            if isinstance(n, ast.Call) and m.name(n.func) == FINDING:
                built += 1
                arg = n.args[2] if len(n.args) > 2 else next((k.value for k in n.keywords if k.arg == "corroborated_by"), None)
                if not _gated(arg, n.lineno, assigned):
                    out.append(f"{rule} {rel}:{n.lineno} {cls}.{meth.name} corroborates a Finding other than by what "
                               "review_verify.blocks answered: a finding blocks only when blocks() says so")
    if not built:
        out.append(f"{rule} {rel}:{node.lineno} {cls} builds no Finding: the review's one path is gone (re-aim the rule)")
    return out


def check(root: pathlib.Path = ROOT, sources: dict[str, str] | None = None) -> list[str]:
    """Every violation of the four rules over aisef2 at `root`, `sources` (rel -> text) read in place of those files."""
    mods = _modules(root, sources or {})
    index = {f"{opa._module_name(rel)}.{name}": (rel, node) for rel, m in mods.items() for name, node in m.defs}
    out = []
    for q in (MIGRATE, VERIFY):
        if q not in index:
            out.append(f"{'MIGRATE_NEVER_APPROVES' if q == MIGRATE else 'VERIFY_THROUGH_BINDING_AND_CALIBRATION'} "
                       f"{q.rsplit('.', 1)[0].replace('.', '/')}.py:1 {_short(q)} is missing")
    for q, rel, node in _closure(mods, index, (MIGRATE,)):
        reloaded = _reloaded(node)
        out += [f"MIGRATE_NEVER_APPROVES {rel}:{n.lineno} {_short(q)} {why}: what migrate reaches re-binds the plan "
                "and never approves" for n in ast.walk(node) if (why := _approves(mods[rel], n, reloaded))]
    for q, rel, node in _closure(mods, index, (MIGRATE, VERIFY)):
        out += [f"NO_COMMIT_OR_MERGE {rel}:{n.lineno} {_short(q)} {why}: what migrate or verify reaches never commits, "
                "merges or decides" for n in ast.walk(node) if isinstance(n, ast.Call) and (why := _decides(mods[rel], n))]
    if VERIFY in index:
        rel, node = index[VERIFY]
        out += _verify_rule(mods[rel], node)
    named = set()
    for rel, m in mods.items():
        for scope, node in m.scopes():
            for n in _loads(node):
                q = m.name(n)
                if q not in ONLY_NAMED_BY:
                    continue
                named.add(q)
                if (rel, scope) != ONLY_NAMED_BY[q]:
                    want = "::".join(ONLY_NAMED_BY[q])
                    out.append(f"ONE_DECISION_PATH {rel}:{n.lineno} {scope} names {_short(q)}: only {want} does")
    out += [f"ONE_DECISION_PATH {ONLY_NAMED_BY[q][0]}:1 {ONLY_NAMED_BY[q][1]} no longer names {_short(q)}: the one path is "
            "gone (re-aim the rule)" for q in ONLY_NAMED_BY if q not in named]
    out += _corroboration(mods)
    return list(dict.fromkeys(out))


def main(argv: list[str] | None = None) -> int:
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("authority limits: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
