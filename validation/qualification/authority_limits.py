"""V2.1 (B-03c): the limits of the two authorities 2.1 adds, enforced statically over aisef2 — `aisef bundle migrate`
(aisef2/app/bundle_cli.py::migrate) and the review reproducer's verification (aisef2/app/review_verify.py::verify).

Owner ruling B-03c: migrate creates a new bundle and never approves it; verify checks by probe and returns its result
under the policy; neither commits or merges the product, nor makes a second final decision path. The release
inventory (release_inventory.py) names both PRODUCT_TRUTH authorities; these rules keep them inside those limits, each
violation reported as `RULE rel:line explanation`:

* **MIGRATE_NEVER_APPROVES** — nothing migrate reaches in aisef2/app calls `bundle_cli.approve`, constructs a
  ContractApproval other than by re-loading one of the input's — `ContractApproval(**a)` as the element of a one-loop
  comprehension `for a in data["approvals"]` (so `a` cannot be rebound) — copies one with changes
  (`dataclasses.replace`, `copy.replace`), or writes approvals: an `approvals` key or keyword, a store, delete or
  mutating method call (update, append, ...; setattr) on the approvals, on a part of them, or on a name bound to them
  or to a part of them.
* **NO_COMMIT_OR_MERGE** — nothing migrate or verify reaches in aisef2/app calls or names git, a commit, a merge, a
  gate row or decision, a classification, a review or a story run, builds a `git` command, or appends a control event
  to a journal.
* **VERIFY_THROUGH_BINDING_AND_CALIBRATION** — verify runs a probe, and every `run_probe(probe, spec, ...)` in it is the
  record `bound_result` binds (PROBE-BIND-1), after a lookup that returns when the run is not calibrated — an earlier
  statement of the probe's block, `if calibration_for(calibrations(), E.probe_id, executing(E.factory), cls) is None:
  return ...`, where `probe = E.factory()` and `cls` is the observation class of `spec`, each name bound once.
* **ONE_DECISION_PATH** — across aisef2, verify is named only by `Reviewer._verify` (aisef2/app/adapters.py),
  `review_verify.blocks` only by `Reviewer.review` and migrate only by `bundle_cli.main`; every Finding the Reviewer
  builds is corroborated only as `(...) if N else ()` (or never), N bound only by `N = review_verify.blocks(...)`, an
  earlier statement of the Finding's block: a finding blocks only when blocks() said so, through the kernel's review
  gate row and its one decision (story_runner._attempt).

"Reaches" is the static closure over names that resolve — imports, module definitions and module-level aliases,
followed through every re-export (`from aisef2.app.adapters import commit_all` is workspace.commit_all) — inside
aisef2/app. Known ceiling: a call through an object (`entry.factory()`, `self.x`) or through a value computed at run
time (getattr, a table of functions) is not followed; the behavioural tests (test_v21_identity Migrate,
test_v21_review, test_v21_review_chain) cover what those do at run time.

    python -P validation/qualification/authority_limits.py     # exit 1 on any violation
"""

from __future__ import annotations

import ast
import pathlib
import re
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
EXECUTING, CALIBRATIONS = "aisef2.probe.calibration.executing", "aisef2.app.run.calibrations"
EVENT_TYPE = "aisef2.arch.enums.EventType"
#: an approval copied with changes is a new approval; a method or builtin that changes what it is called on
REPLACE = {"dataclasses.replace", "copy.replace"}
MUTATORS = {"update", "append", "extend", "insert", "pop", "popitem", "setdefault", "clear", "remove", "sort", "reverse",
            "__setitem__", "__delitem__", "__setattr__", "__delattr__", "__init__"}
SETATTR = {"setattr", "delattr", "object.__setattr__", "object.__delattr__"}
#: what a migration or a verification never reaches
DECIDING = {"aisef2.orchestrate.workspace.git", "aisef2.orchestrate.workspace.commit_all", "aisef2.orchestrate.workspace.GitMerger",
            "aisef2.orchestrate.merge.merge", "aisef2.orchestrate.merge.reprove", "aisef2.orchestrate.gate.check",
            "aisef2.orchestrate.gate.decision", "aisef2.control.owner.classify", "aisef2.plan.story_admission.classify",
            "aisef2.orchestrate.review.review", "aisef2.orchestrate.story_runner.run_story"}
GIT_COMMAND = re.compile(r"git(\s|$)")


class _Module:
    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.tree = rel, ast.parse(text)
        self.imports = opa._imports(self.tree, rel)
        self.defs = opa._defs(self.tree)
        self.local = {name for name, _ in self.defs if "." not in name}
        for n in self.tree.body:     # a module-level alias (`git = W.git`) binds and re-exports like an import
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                    and n.targets[0].id not in self.local and (dotted := opa._dotted(n.value)):
                self.imports[n.targets[0].id] = opa._qualify(dotted, self.imports, rel, self.local)
        self.world: dict[str, _Module] = {}     # module name -> _Module, every module of the tree (set by _modules)

    def name(self, node: ast.AST) -> str | None:
        """The qualified name a reference (a Name or an Attribute chain) resolves to, re-exports followed, or None."""
        dotted = opa._dotted(node)
        return _resolve(self.world, opa._qualify(dotted, self.imports, self.rel, self.local)) if dotted else None

    def scopes(self):
        """(scope name, node) for each top-level statement, a class's methods by `Class.method`."""
        for n in self.tree.body:
            if isinstance(n, ast.ClassDef):
                for m in n.body:
                    yield (f"{n.name}.{m.name}", m) if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) else (n.name, m)
            else:
                yield (n.name if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) else "<module>"), n


def _resolve(world: dict[str, _Module], q: str) -> str:
    """`q` where it is defined: while q is <module>.<attr>[...] and <module> does not define <attr> but imports it (or
    aliases it), the import's target takes its place — to a fixed point."""
    seen = set()
    while q not in seen:
        seen.add(q)
        parts = q.split(".")
        i = next((i for i in range(len(parts) - 1, 0, -1) if ".".join(parts[:i]) in world), None)
        if i is None:
            return q
        m, attr = world[".".join(parts[:i])], parts[i]
        if attr in m.local or attr not in m.imports:
            return q
        q = ".".join([m.imports[attr], *parts[i + 1:]])
    return q


def _modules(root: pathlib.Path, sources: dict[str, str]) -> dict[str, _Module]:
    rels = set(opa._py_files(root, ("aisef2/",))) | set(sources)
    mods = {rel: _Module(rel, sources[rel] if rel in sources else (root / rel).read_text(encoding="utf-8"))
            for rel in sorted(rels)}
    world = {opa._module_name(rel): m for rel, m in mods.items()}
    for m in mods.values():
        m.world = world
    return mods


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


def _precedes(fn: ast.AST, stmt: ast.stmt, node: ast.AST) -> bool:
    """`stmt` runs before `node` on every path to it: an earlier statement of a block a later statement of which holds
    `node`."""
    for blk in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(blk, field, None)
            if isinstance(body, list) and any(s is stmt for s in body):
                i = next(i for i, s in enumerate(body) if s is stmt)
                return any(x is node for s in body[i + 1:] for x in ast.walk(s))
    return False


def _only(fn: ast.AST, name: str) -> ast.AST | None:
    """The value of `name`'s one binding in `fn` when that binding is a plain `name = value`, else None."""
    stores = [t for t in ast.walk(fn) if isinstance(t, ast.Name) and t.id == name and isinstance(t.ctx, ast.Store)]
    return next((a.value for a in ast.walk(fn) if isinstance(a, ast.Assign) and len(stores) == 1
                 and any(t is stores[0] for t in a.targets)), None)


def _is_approvals(n: ast.AST) -> bool:
    """`n` is `X["approvals"]` or `X.get("approvals", ...)`."""
    if isinstance(n, ast.Subscript):
        return isinstance(n.slice, ast.Constant) and n.slice.value == "approvals"
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and bool(n.args) \
        and isinstance(n.args[0], ast.Constant) and n.args[0].value == "approvals"


def _holds(n: ast.AST | None, held: set[str]) -> bool:
    """`n` holds the approvals or a part of them: it reads them, or names what holds them."""
    return n is not None and any(_is_approvals(x) or isinstance(x, ast.Name) and x.id in held for x in ast.walk(n))


def _bindings(node: ast.AST):
    """(target, source) of every binding in `node`: =, :=, augmented, annotated, a loop."""
    for n in ast.walk(node):
        if isinstance(n, ast.Assign):
            yield from ((t, n.value) for t in n.targets)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            yield n.target, n.value
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            yield n.target, n.iter


def _held(node: ast.AST) -> set[str]:
    """Every name `node` binds to the approvals or to a part of them, an approval among them (a write through one is a
    write of the approvals) — to a fixed point."""
    held: set[str] = set()
    while True:
        more = {t.id for target, source in _bindings(node) if _holds(source, held)
                for t in ast.walk(target) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
        if more <= held:
            return held
        held |= more


def _reloads(node: ast.AST) -> set[int]:
    """The `ContractApproval(**a)` calls (by id) that re-load an approval of the input: each the element of a
    comprehension whose one loop is `for a in X["approvals"]` — `a` is then the input's element and nothing rebinds it."""
    return {id(c.elt) for c in ast.walk(node) if isinstance(c, (ast.ListComp, ast.GeneratorExp, ast.SetComp))
            and len(c.generators) == 1 and isinstance(g := c.generators[0], ast.comprehension)
            and isinstance(g.target, ast.Name) and _is_approvals(g.iter) and isinstance(c.elt, ast.Call)
            and not c.elt.args and len(c.elt.keywords) == 1 and c.elt.keywords[0].arg is None
            and isinstance(c.elt.keywords[0].value, ast.Name) and c.elt.keywords[0].value.id == g.target.id}


def _approves(m: _Module, n: ast.AST, reloads: set[int], held: set[str]) -> str | None:
    if isinstance(n, ast.Call):
        callee = m.name(n.func)
        if callee == APPROVE:
            return "calls bundle_cli.approve"
        if callee == APPROVAL and id(n) not in reloads or callee in REPLACE and n.args and _holds(n.args[0], held):
            return "creates a ContractApproval (a migration only re-loads the input's: ContractApproval(**a))"
        if any(k.arg == "approvals" for k in n.keywords) and (callee == "dict" or getattr(n.func, "attr", None) == "update"):
            return "writes the approvals"
        if isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS and (
                _holds(n.func.value, held) or n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "approvals"):
            return "writes the approvals"
        if callee in SETATTR and n.args and _holds(n.args[0], held):
            return "writes the approvals"
    if isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "approvals" for k in n.keys):
        return "writes an 'approvals' key"
    if isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, (ast.Store, ast.Del)):
        if _is_approvals(n):
            return "writes an 'approvals' key"
        if _holds(n.value, held):
            return "writes the approvals"
    return None


def _decides(m: _Module, node: ast.AST) -> list[tuple[int, str]]:
    """(line, why) of each place in `node` that reaches a commit, a merge or a decision."""
    funcs = {id(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}
    out = []
    for n in ast.walk(node):
        if isinstance(n, (ast.Name, ast.Attribute)) and isinstance(n.ctx, ast.Load):
            if (q := m.name(n)) in DECIDING:     # a method of GitMerger names GitMerger on its way
                out.append((n.lineno, f"{'calls' if id(n) in funcs else 'names'} {q}"))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and GIT_COMMAND.match(n.value):
            out.append((n.lineno, "runs git"))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append" and n.args \
                and isinstance(n.args[0], ast.Attribute) and m.name(n.args[0].value) == EVENT_TYPE:
            out.append((n.lineno, f"appends the control event {n.args[0].attr} to a journal"))
    return out


def _calibrated_before(m: _Module, fn: ast.AST, probe: ast.Call) -> bool:
    """`probe` (`run_probe(P, S, ...)`, `P = E.factory()`) comes after the refusal `if calibration_for(calibrations(),
    E.probe_id, executing(E.factory), C) is None: return ...` (or `if not calibration_for(...)`), an earlier statement of
    its block, with C bound to the observation class of S — every one of those names bound once."""
    if len(probe.args) < 2 or not all(isinstance(a, ast.Name) and _only(fn, a.id) is not None for a in probe.args[:2]):
        return False
    made, spec = _only(fn, probe.args[0].id), probe.args[1].id
    if not (isinstance(made, ast.Call) and isinstance(made.func, ast.Attribute) and made.func.attr == "factory"
            and isinstance(made.func.value, ast.Name) and _only(fn, made.func.value.id) is not None):
        return False
    entry = made.func.value.id
    for g in ast.walk(fn):
        if not (isinstance(g, ast.If) and any(isinstance(s, ast.Return) for s in g.body) and _precedes(fn, g, probe)):
            continue
        t = g.test
        look = (t.left if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Is)
                and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value is None
                else t.operand if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) else None)
        if not (isinstance(look, ast.Call) and m.name(look.func) == CALIBRATION_FOR and len(look.args) == 4
                and not look.keywords):
            continue
        table, pid, ex, cls = look.args
        observed = _only(fn, cls.id) if isinstance(cls, ast.Name) else None
        if isinstance(table, ast.Call) and m.name(table.func) == CALIBRATIONS and not table.args and not table.keywords \
                and opa._dotted(pid) == f"{entry}.probe_id" and isinstance(ex, ast.Call) and m.name(ex.func) == EXECUTING \
                and len(ex.args) == 1 and opa._dotted(ex.args[0]) == f"{entry}.factory" \
                and isinstance(observed, ast.Call) and getattr(observed.func, "attr", None) == "observation_class" \
                and any(isinstance(a, ast.Name) and a.id == spec for a in observed.args):
            return True
    return False


def _verify_rule(m: _Module, node: ast.AST) -> list[str]:
    rule = "VERIFY_THROUGH_BINDING_AND_CALIBRATION"
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
    bound = {id(n.args[0]) for n in calls if n.args and m.name(n.func) == BOUND}
    probes = [n for n in calls if m.name(n.func) == RUN_PROBE]
    if not probes:
        return [f"{rule} {m.rel}:{node.lineno} verify runs no probe: a confirmation is the kernel's probe's, never the finding's"]
    out = []
    for n in probes:
        if id(n) not in bound:
            out.append(f"{rule} {m.rel}:{n.lineno} verify reads run_probe's record unbound: every run_probe is "
                       "bound_result's first argument (PROBE-BIND-1)")
        if not _calibrated_before(m, node, n):
            out.append(f"{rule} {m.rel}:{n.lineno} verify runs the probe with no calibration lookup before it that "
                       "returns when the class is not calibrated at the bytes that run")
    return out


def _empty(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Tuple) and not node.elts


def _gated(m: _Module, meth: ast.AST, finding: ast.Call, arg: ast.AST | None) -> bool:
    """`arg` is `()`, or `(...) if N else ()` where every binding of N up to `finding` is `N = review_verify.blocks(...)`
    and one is an earlier statement of the Finding's block."""
    if _empty(arg):
        return True
    if not (isinstance(arg, ast.IfExp) and _empty(arg.orelse) and isinstance(arg.test, ast.Name)):
        return False
    binds = [t for t in ast.walk(meth) if isinstance(t, ast.Name) and t.id == arg.test.id and isinstance(t.ctx, ast.Store)
             and t.lineno <= finding.end_lineno]
    asked = [a for a in ast.walk(meth) if isinstance(a, ast.Assign) and len(a.targets) == 1
             and any(a.targets[0] is t for t in binds) and isinstance(a.value, ast.Call) and m.name(a.value.func) == BLOCKS]
    return bool(asked) and len(asked) == len(binds) and any(_precedes(meth, a, finding) for a in asked)


def _corroboration(mods: dict[str, _Module]) -> list[str]:
    rule, (rel, cls) = "ONE_DECISION_PATH", REVIEWER
    m = mods.get(rel)
    node = next((n for n in m.tree.body if isinstance(n, ast.ClassDef) and n.name == cls), None) if m else None
    if node is None:
        return [f"{rule} {rel}:1 {cls} is missing"]
    out, built = [], 0
    for meth in (f for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for n in ast.walk(meth):
            if isinstance(n, ast.Call) and m.name(n.func) == FINDING:
                built += 1
                arg = n.args[2] if len(n.args) > 2 else next((k.value for k in n.keywords if k.arg == "corroborated_by"), None)
                if not _gated(m, meth, n, arg):
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
        m = mods[rel]
        reloads, held = _reloads(node), _held(node)
        out += [f"MIGRATE_NEVER_APPROVES {rel}:{n.lineno} {_short(q)} {why}: what migrate reaches re-binds the plan "
                "and never approves" for n in ast.walk(node) if (why := _approves(m, n, reloads, held))]
    for q, rel, node in _closure(mods, index, (MIGRATE, VERIFY)):
        out += [f"NO_COMMIT_OR_MERGE {rel}:{line} {_short(q)} {why}: what migrate or verify reaches never commits, "
                "merges or decides" for line, why in _decides(mods[rel], node)]
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
