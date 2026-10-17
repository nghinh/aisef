"""V2.1 (B-03c): the limits of the two authorities 2.1 adds, enforced statically over aisef2 — `aisef bundle migrate`
(aisef2/app/bundle_cli.py::migrate) and the review reproducer's verification (aisef2/app/review_verify.py::verify).

Owner ruling B-03c: migrate creates a new bundle and never approves it; verify checks by probe and returns its result
under the policy; neither commits or merges the product, nor makes a second final decision path. The release
inventory (release_inventory.py) names both PRODUCT_TRUTH authorities; these rules keep them inside those limits, each
violation reported as `RULE rel:line explanation`:

* **MIGRATE_NEVER_APPROVES** — nothing migrate reaches in aisef2/app calls `bundle_cli.approve`, names ContractApproval
  (outside an annotation) other than to re-load one of the input's — `ContractApproval(**a)` as the element of a
  one-loop comprehension `for a in data["approvals"]`, `data` the function's first parameter and never rebound (so
  `a` cannot be rebound) — copies one with changes
  (`dataclasses.replace`, `copy.replace`), or writes approvals: an `approvals` key or keyword, a store, delete or
  mutating method call (update, append, ...; setattr, operator.setitem) on the approvals, on a part of them, on a name bound to them or
  to a part of them, or with the key "approvals" among its arguments. A parameter of a reached function is bound to the
  approvals when a call in the closure passes them (or a part of them) to it. The one write there is: a migration may
  leave an approval out of the bundle it builds (owner decision 2026-10-15, item 1 — an approval whose contract is
  evaluated differently since is not carried over), as the value of the key `approvals` in a dict display: a
  comprehension of one loop `[a for a in data["approvals"] if ...]` whose element is the loop's own name, `data` as
  above. A filter holds some of the input's own approvals and nothing else: it puts none in and changes none.
* **NO_COMMIT_OR_MERGE** — module-based: nothing migrate or verify reaches in aisef2/app names (calls or not) anything
  of a deciding module — the kernel's git, merge, gate, review and story runner (aisef2.orchestrate), the owner's
  control (aisef2.control), the journal (aisef2.journal), story admission (aisef2.plan.story_admission) — or a control
  event (aisef2.arch.enums.EventType), and no string holds `git` as a word (a command, a path to it, git.exe).
  Fail-closed: what they name elsewhere in aisef2 is the explicit list REACHES (data types, compile_spec, the probe
  protocol, the calibration lookup), in the standard library the modules STDLIB lists; a new name fails until it is
  shown to decide nothing and listed, as do a module named as a value (what is called on it is not followed), a name
  aisef2/app does not define and a DYNAMIC builtin (eval, exec, __import__, getattr, ...).
* **VERIFY_THROUGH_BINDING_AND_CALIBRATION** — verify runs a probe, and every `run_probe(probe, spec, ...)` in it is the
  record `bound_result` binds (PROBE-BIND-1), after a lookup that refuses when the run is not calibrated — an earlier
  statement of the probe's block, `if calibration_for(calibrations(), E.probe_id, executing(E.factory), cls) is None:
  return Verification(UNVERIFIABLE, ...)`, where `probe = E.factory()` and `cls` is the observation class of `spec`,
  each name bound once; nothing verify reaches observes (`.observe`) outside run_probe.
* **ONE_DECISION_PATH** — across aisef2 (the modules that define them never named as a value), verify is named only by `Reviewer._verify` (aisef2/app/adapters.py),
  `review_verify.blocks` only by `Reviewer.review` and migrate only by `bundle_cli.main`; in aisef2/app a Finding is
  built only by a Reviewer method, corroborated only as `(...) if N else ()` (or never) with every binding of N
  `N = review_verify.blocks(...)` and one an earlier statement of the Finding's block, or by `RuffScanner.read`,
  never blocking (its `blocking` a false constant); nothing in aisef2/app copies one with another `blocking` or
  `corroborated_by` (dataclasses.replace, setattr): a finding blocks only when blocks() said so, through the kernel's
  review gate row and its one decision (story_runner._attempt).

"Reaches" is the static closure over names that resolve — imports, module definitions and module-level bindings
(an alias `save = W.commit_all` or `save: object = W.commit_all` is followed like an import; any other binding, a
store into it or a call on it at module level joins the closure with what it names), followed through every re-export (`from aisef2.app.adapters import
commit_all` is workspace.commit_all) — inside aisef2/app. Known ceiling: a call through an object (`entry.factory()`,
`self.x`) is not followed, nor what a reached class's `__init__` does with an argument (`K(out["approvals"])`); the
analysis is flow-insensitive except
that a binding of the corroboration name after its Finding counts only inside a loop that holds both; the behavioural
tests (test_v21_identity Migrate — `test_migration_rebinds_the_plan_and_nothing_else` asserts the input unchanged and
the output's approvals equal to the input's —, test_v21_review, test_v21_review_chain) cover what those do at run time.

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
SCANNER = ("aisef2/app/adapters.py", "RuffScanner.read")
FINDING_FIELDS = ("blocking", "corroborated_by")     # what a copy with changes must not set
APPROVE, APPROVAL = "aisef2.app.bundle_cli.approve", "aisef2.product.approval.ContractApproval"
RUN_PROBE, BOUND, CALIBRATION_FOR = ("aisef2.probe.protocol.run_probe", "aisef2.probe.protocol.bound_result",
                                     "aisef2.probe.calibration.calibration_for")
EXECUTING, CALIBRATIONS = "aisef2.probe.calibration.executing", "aisef2.app.run.calibrations"
VERIFICATION, UNVERIFIABLE = "aisef2.app.review_verify.Verification", "aisef2.app.review_verify.UNVERIFIABLE"
EVENT_TYPE = "aisef2.arch.enums.EventType"
#: an approval copied with changes is a new approval; a method or builtin that changes what it is called on
REPLACE = {"dataclasses.replace", "copy.replace"}
MUTATORS = {"update", "append", "extend", "insert", "pop", "popitem", "setdefault", "clear", "remove", "sort", "reverse",
            "__setitem__", "__delitem__", "__setattr__", "__delattr__", "__init__"}
SETATTR = {"setattr", "delattr", "object.__setattr__", "object.__delattr__", "operator.setitem", "operator.delitem"}
#: where deciding lives — a migration or a verification names nothing in these (module, or one definition)
DECIDING = ("aisef2.orchestrate", "aisef2.control", "aisef2.journal", "aisef2.plan.story_admission", EVENT_TYPE)
#: everything outside aisef2/app migrate and verify may name: each decides nothing (data types and their constructors,
#: the compiler, the probe protocol and catalog, the calibration lookup). Fail-closed: anything else is a violation
REACHES = {
    "aisef2.arch.enums.BehaviorVerdict", "aisef2.arch.enums.Enforcement", "aisef2.arch.enums.ObligationRole",
    "aisef2.arch.enums.ParentExpectation", "aisef2.arch.enums.Polarity", "aisef2.arch.enums.SubjectAbsence",
    "aisef2.arch.enums.SubjectKind",
    "aisef2.plan.obligation.Plan", "aisef2.plan.obligation.PlanObligation", "aisef2.plan.obligation.PlanQualityPolicy",
    "aisef2.probe.calibration.ProbeCapabilityCalibration", "aisef2.probe.calibration.calibration_for",
    "aisef2.probe.calibration.executing", "aisef2.probe.catalog.active", "aisef2.probe.catalog.registry",
    "aisef2.probe.protocol.ExecutionEnv", "aisef2.probe.protocol.RevisionRef", "aisef2.probe.protocol.bound_result",
    "aisef2.probe.protocol.run_probe",
    "aisef2.product.approval.ContractApproval", "aisef2.product.approval.Requirement",
    "aisef2.product.approval.binding_problems",     # a pure check of an approval's binding (approve, a known-bad edit)
    "aisef2.product.compiler.COMPILER_DIGEST", "aisef2.product.compiler.COMPILER_ID", "aisef2.product.compiler.ProbeRef",
    "aisef2.product.compiler.compile_spec", "aisef2.product.compiler.expectation_for",
    "aisef2.product.contract.BehaviorContract", "aisef2.product.contract.ContractError", "aisef2.product.contract.Subject",
    "aisef2.product.contract.plain", "aisef2.product.outcome.Executed", "aisef2.product.spec.ProductProofSpec",
}
#: the standard library migrate and verify may name — fail-closed like REACHES (subprocess, os, importlib, shutil fail)
STDLIB = ("dataclasses", "hashlib", "json", "pathlib", "re", "typing")
#: builtins that run code or reach a name computed at run time
DYNAMIC = {"__import__", "eval", "exec", "compile", "globals", "locals", "vars", "getattr", "breakpoint"}
#: `git` as a word anywhere in a string (`git`, `/usr/bin/git`, `git.exe`, `sh -c "cd x && git ..."`)
GIT_COMMAND = re.compile(r"(^|[\s/\\&;|'\"])git(\.exe)?(\s|$|['\"])")


def _top(body: list):
    """Every statement of a module's level, inside its if/try/with/loop blocks too (not inside a def or a class)."""
    for n in body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield n
            for field in ("body", "orelse", "finalbody", "handlers"):
                yield from _top(getattr(n, field, []))


class _Module:
    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.tree = rel, ast.parse(text)
        self.imports = opa._imports(self.tree, rel)
        self.defs = opa._defs(self.tree)
        self.local = {name for name, _ in self.defs if "." not in name}
        #: a module-level name -> every module-level statement that binds it to, stores into or calls on a value that
        #: is not an alias (`T = {...}`, `T["k"] = ...`, `T |= ...`, `T.update(...)`)
        self.bound: dict[str, list[ast.stmt]] = {}
        for n in _top(self.tree.body):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, (ast.AnnAssign, ast.AugAssign)) \
                and n.value else [n.value.func] if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) else []
            dotted = opa._dotted(n.value) if isinstance(n, (ast.Assign, ast.AnnAssign)) else None
            for t in dict.fromkeys(t.id for target in targets for t in ast.walk(target) if isinstance(t, ast.Name)):
                if t in self.local or t in self.imports:     # a definition or an import (first, as _qualify reads it)
                    continue
                if dotted and isinstance(targets[0], ast.Name) and len(targets) == 1:
                    # an alias (`git = W.git`, `save: object = W.commit_all`) binds and re-exports like an import
                    self.imports[t] = opa._qualify(dotted, self.imports, rel, self.local)
                else:
                    self.bound.setdefault(t, []).append(n)
        self.local |= set(self.bound)
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


def _refs(m: _Module, node: ast.AST):
    """(reference, the part of it that names, what that resolves to) for each whole Load reference in `node` — a Name
    or an Attribute chain not inside a longer one. The part is its shortest prefix that is not a module (`W.GitMerger`
    of `W.GitMerger.merge`, `EventType` of `EventType.X`), or the whole when every prefix is a module."""
    inner = {id(n.value) for n in _loads(node) if isinstance(n, ast.Attribute)}
    for n in _loads(node):
        if id(n) in inner:
            continue
        chain, x = [], n
        while isinstance(x, ast.Attribute):
            chain.append(x)
            x = x.value
        chain.append(x)
        for part in reversed(chain):
            if (q := m.name(part)) is None or q not in m.world:
                break
        if q is not None:
            yield n, part, q


def _under(q: str, prefixes) -> bool:
    return any(q == p or q.startswith(p + ".") for p in prefixes)


def _annotations(node: ast.AST) -> set[int]:
    """The ids of every node inside an annotation in `node` (an annotation names a type; it builds nothing)."""
    anns = []
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            anns += [x.annotation for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg) if x is not None]
            anns.append(n.returns)
        elif isinstance(n, ast.AnnAssign):
            anns.append(n.annotation)
    return {id(x) for ann in anns if ann is not None for x in ast.walk(ann)}


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


def _held(node: ast.AST, params=()) -> set[str]:
    """Every name `node` binds to the approvals or to a part of them, an approval among them (a write through one is a
    write of the approvals), `params` (its parameters a call passes them to) among them — to a fixed point."""
    held: set[str] = set(params)
    while True:
        more = {t.id for target, source in _bindings(node) if _holds(source, held)
                for t in ast.walk(target) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
        if more <= held:
            return held
        held |= more


def _input(node: ast.AST) -> list[str]:
    """The function's first parameter as a one-name list — empty when `node` is no function or rebinds it: the name
    of the input a migration is given, never another document."""
    first = _params(node)[:1] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else []
    if first and any(isinstance(t, ast.Name) and t.id == first[0] and isinstance(t.ctx, ast.Store) for t in ast.walk(node)):
        first = []
    return first


def _filters(node: ast.AST) -> set[int]:
    """The ids of the comprehensions in `node` that hold some of the input's own approvals untouched: one loop
    `for a in D["approvals"]` (D as in `_reloads`), its element the loop's own name. Any `if` is allowed: a filter
    leaves approvals out, and puts none in or changes none."""
    first = _input(node)
    return {id(c) for c in ast.walk(node) if isinstance(c, ast.ListComp) and len(c.generators) == 1
            and isinstance(g := c.generators[0], ast.comprehension) and not g.is_async and isinstance(g.target, ast.Name)
            and _is_approvals(g.iter) and isinstance(g.iter, ast.Subscript) and isinstance(g.iter.value, ast.Name)
            and g.iter.value.id in first and isinstance(c.elt, ast.Name) and c.elt.id == g.target.id}


def _reloads(node: ast.AST) -> set[int]:
    """The callees (by id) of the `ContractApproval(**a)` calls that re-load an approval of the input: each the element
    of a comprehension whose one loop is `for a in D["approvals"]`, D the function's first parameter and never rebound
    in it — `a` is then the input's element and nothing rebinds it."""
    first = _input(node)
    return {id(c.elt.func) for c in ast.walk(node) if isinstance(c, (ast.ListComp, ast.GeneratorExp, ast.SetComp))
            and len(c.generators) == 1 and isinstance(g := c.generators[0], ast.comprehension)
            and isinstance(g.target, ast.Name) and _is_approvals(g.iter) and isinstance(g.iter, ast.Subscript)
            and isinstance(g.iter.value, ast.Name) and g.iter.value.id in first and isinstance(c.elt, ast.Call)
            and not c.elt.args and len(c.elt.keywords) == 1 and c.elt.keywords[0].arg is None
            and isinstance(c.elt.keywords[0].value, ast.Name) and c.elt.keywords[0].value.id == g.target.id}


def _params(fn: ast.AST) -> list[str]:
    a = fn.args
    return [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg) if x is not None]


def _passed(mods: dict[str, _Module], closure: list[tuple[str, str, ast.AST]]) -> dict[str, set[str]]:
    """Each reached function's parameters that a call in the closure passes the approvals (or a part of them) to — a
    starred or `**` argument that holds them reaches every parameter — to a fixed point."""
    fns = {q: node for q, _, node in closure if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    passed: dict[str, set[str]] = {q: set() for q in fns}
    while True:
        more = False
        for q, rel, node in closure:
            held = _held(node, passed.get(q, ()))
            for c in ast.walk(node):
                if not (isinstance(c, ast.Call) and (callee := mods[rel].name(c.func)) in fns):
                    continue
                params = _params(fns[callee])
                spread = any(isinstance(a, ast.Starred) for a in c.args) or any(k.arg is None for k in c.keywords)
                given = [*c.args, *(k.value for k in c.keywords)]
                got = set(params) if spread and any(_holds(a, held) for a in given) else \
                    {p for p, a in zip(params, c.args, strict=False) if _holds(a, held)} | \
                    {k.arg for k in c.keywords if k.arg in params and _holds(k.value, held)}
                if not got <= passed[callee]:
                    passed[callee] |= got
                    more = True
        if not more:
            return passed


def _names_key(n: ast.Call) -> bool:
    """A call given the key "approvals" among its arguments (`out.update(dict.fromkeys(["approvals"]))`)."""
    return any(isinstance(x, ast.Constant) and x.value == "approvals"
               for a in (*n.args, *(k.value for k in n.keywords)) for x in ast.walk(a))


def _created(m: _Module, node: ast.AST) -> list[int]:
    """The lines where `node` names ContractApproval (a call, an alias, `ContractApproval.__new__`, ...) other than in an
    annotation or as the callee of a re-load."""
    skip = _reloads(node) | _annotations(node)
    return [n.lineno for n, _, q in _refs(m, node) if _under(q, (APPROVAL,)) and id(n) not in skip]


def _approves(m: _Module, n: ast.AST, held: set[str], filters: set[int] = frozenset()) -> str | None:
    if isinstance(n, ast.Call):
        callee = m.name(n.func)
        if callee == APPROVE:
            return "calls bundle_cli.approve"
        if callee in REPLACE and n.args and _holds(n.args[0], held):
            return "creates a ContractApproval (a migration only re-loads the input's: ContractApproval(**a))"
        if any(k.arg == "approvals" for k in n.keywords) and (callee == "dict" or getattr(n.func, "attr", None) == "update"):
            return "writes the approvals"
        if isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS and (_holds(n.func.value, held) or _names_key(n)):
            return "writes the approvals"
        if callee in SETATTR and (n.args and _holds(n.args[0], held) or _names_key(n)):
            return "writes the approvals"
    if isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "approvals" and id(v) not in filters
                                       for k, v in zip(n.keys, n.values, strict=True)):
        return "writes an 'approvals' key"
    if isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, (ast.Store, ast.Del)):
        if _is_approvals(n):
            return "writes an 'approvals' key"
        if _holds(n.value, held):
            return "writes the approvals"
    return None


def _decides(m: _Module, node: ast.AST, index: dict) -> list[tuple[int, str]]:
    """(line, why) of each place in `node` that names a deciding module, a control event, what REACHES does not list,
    a module as a value, a standard-library module STDLIB does not list or a DYNAMIC builtin, or builds a git
    command."""
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
    funcs = {id(n.func) for n in calls}
    appended = {id(a) for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                for a in (*n.args, *(k.value for k in n.keywords))}
    out = []
    for n, part, q in _refs(m, node):
        head = (opa._dotted(n) or "").split(".")[0]
        if _under(q, (EVENT_TYPE,)) and id(n) in appended:
            out.append((n.lineno, f"appends the control event {getattr(n, 'attr', q)} to a journal"))
        elif _under(q, DECIDING):     # a method of GitMerger names GitMerger on its way
            out.append((n.lineno, f"{'calls' if id(part) in funcs else 'names'} {q}"))
        elif q in m.world or q == "aisef2":
            out.append((n.lineno, f"names the module {q} as a value: what is called on it is not followed"))
        elif not q.startswith("aisef2."):
            if head in m.imports and q.split(".")[0] not in STDLIB:
                out.append((n.lineno, f"names {q}, outside the standard library STDLIB lists"))
            elif head not in m.imports and q in DYNAMIC:
                out.append((n.lineno, f"calls {q}: what it reaches is computed at run time"))
        elif _under(q, ("aisef2.app",)):
            if q not in index:     # what aisef2/app defines is followed by the closure
                out.append((n.lineno, f"names {q}, which aisef2/app does not define"))
        elif q not in REACHES:
            out.append((n.lineno, f"names {q}, which REACHES does not list: list it only once it is shown to decide nothing"))
    out += [(n.lineno, "runs git") for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and GIT_COMMAND.search(n.value)]
    return out


def _refuses(m: _Module, s: ast.stmt) -> bool:
    """`s` is `return Verification(UNVERIFIABLE, ...)`: the run is refused, never confirmed."""
    v = s.value if isinstance(s, ast.Return) else None
    return isinstance(v, ast.Call) and m.name(v.func) == VERIFICATION and bool(v.args) and m.name(v.args[0]) == UNVERIFIABLE


def _calibrated_before(m: _Module, fn: ast.AST, probe: ast.Call) -> bool:
    """`probe` (`run_probe(P, S, ...)`, `P = E.factory()`) comes after the refusal `if calibration_for(calibrations(),
    E.probe_id, executing(E.factory), C) is None: return Verification(UNVERIFIABLE, ...)` (or `if not
    calibration_for(...)`), an earlier statement of
    its block, with C bound to the observation class of S — every one of those names bound once."""
    if len(probe.args) < 2 or not all(isinstance(a, ast.Name) and _only(fn, a.id) is not None for a in probe.args[:2]):
        return False
    made, spec = _only(fn, probe.args[0].id), probe.args[1].id
    if not (isinstance(made, ast.Call) and isinstance(made.func, ast.Attribute) and made.func.attr == "factory"
            and isinstance(made.func.value, ast.Name) and _only(fn, made.func.value.id) is not None):
        return False
    entry = made.func.value.id
    for g in ast.walk(fn):
        if not (isinstance(g, ast.If) and any(_refuses(m, s) for s in g.body) and _precedes(fn, g, probe)):
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


def _verify_rule(m: _Module, node: ast.AST, closure: list[tuple[str, str, ast.AST]]) -> list[str]:
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
    out += [f"{rule} {rel}:{n.lineno} {_short(q)} observes outside run_probe: the probe's observation is only the record "
            "run_probe returns and bound_result binds" for q, rel, fn in closure for n in _loads(fn)
            if isinstance(n, ast.Attribute) and n.attr == "observe"]
    return out


def _empty(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Tuple) and not node.elts


def _gated(m: _Module, meth: ast.AST, finding: ast.Call, arg: ast.AST | None) -> bool:
    """`arg` is `()`, or `(...) if N else ()` where every binding of N up to `finding`, and every one in a loop that holds
    `finding` (it runs before the next), is `N = review_verify.blocks(...)` and one is an earlier statement of the
    Finding's block."""
    if _empty(arg):
        return True
    if not (isinstance(arg, ast.IfExp) and _empty(arg.orelse) and isinstance(arg.test, ast.Name)):
        return False
    looped = {id(x) for loop in ast.walk(meth) if isinstance(loop, (ast.For, ast.AsyncFor, ast.While))
              and any(x is finding for x in ast.walk(loop)) for x in ast.walk(loop)}
    binds = [t for t in ast.walk(meth) if isinstance(t, ast.Name) and t.id == arg.test.id and isinstance(t.ctx, ast.Store)
             and (t.lineno <= finding.end_lineno or id(t) in looped)]
    asked = [a for a in ast.walk(meth) if isinstance(a, ast.Assign) and len(a.targets) == 1
             and any(a.targets[0] is t for t in binds) and isinstance(a.value, ast.Call) and m.name(a.value.func) == BLOCKS]
    return bool(asked) and len(asked) == len(binds) and any(_precedes(meth, a, finding) for a in asked)


def _arg(call: ast.Call, i: int, name: str) -> ast.AST | None:
    return call.args[i] if len(call.args) > i else next((k.value for k in call.keywords if k.arg == name), None)


def _corroboration(mods: dict[str, _Module]) -> list[str]:
    """Every Finding aisef2/app builds: a Reviewer method's, gated by blocks(); RuffScanner.read's, never blocking;
    none elsewhere."""
    rule, (rel, cls) = "ONE_DECISION_PATH", REVIEWER
    m = mods.get(rel)
    node = next((n for n in m.tree.body if isinstance(n, ast.ClassDef) and n.name == cls), None) if m else None
    if node is None:
        return [f"{rule} {rel}:1 {cls} is missing"]
    out, built = [], 0
    for r, mod in mods.items():
        if not r.startswith(APP):
            continue
        skip = _annotations(mod.tree)
        calls = {id(c.func): c for c in ast.walk(mod.tree) if isinstance(c, ast.Call)}
        for scope, top in mod.scopes():
            out += [f"{rule} {r}:{c.lineno} {scope} copies a Finding with another blocking or corroboration: only {cls}'s "
                    f"methods (corroborated by blocks()) and {SCANNER[1]} (never blocking) build one"
                    for c in ast.walk(top) if isinstance(c, ast.Call) and mod.name(c.func) in REPLACE | SETATTR
                    and (any(k.arg in FINDING_FIELDS for k in c.keywords)
                         or any(isinstance(a, ast.Constant) and a.value in FINDING_FIELDS for a in c.args))]
            for n, _, q in _refs(mod, top):
                if q != FINDING or id(n) in skip:
                    continue
                call = calls.get(id(n))
                if call is not None and r == rel and scope.startswith(f"{cls}.") and scope != cls:
                    built += 1
                    if not _gated(mod, top, call, _arg(call, 2, "corroborated_by")):
                        out.append(f"{rule} {r}:{n.lineno} {scope} corroborates a Finding other than by what "
                                   "review_verify.blocks answered: a finding blocks only when blocks() says so")
                elif call is not None and (r, scope) == SCANNER:
                    blocking = _arg(call, 1, "blocking")
                    if not (isinstance(blocking, ast.Constant) and not blocking.value):
                        out.append(f"{rule} {r}:{n.lineno} {scope} builds a Finding that may block: a scanner's finding "
                                   "is informational and never blocks")
                else:
                    out.append(f"{rule} {r}:{n.lineno} {scope} {'builds' if call is not None else 'names'} a Finding: only "
                               f"{cls}'s methods (corroborated by blocks()) and {SCANNER[1]} (never blocking) build one")
    if not built:
        out.append(f"{rule} {rel}:{node.lineno} {cls} builds no Finding: the review's one path is gone (re-aim the rule)")
    return out


def check(root: pathlib.Path = ROOT, sources: dict[str, str] | None = None) -> list[str]:
    """Every violation of the four rules over aisef2 at `root`, `sources` (rel -> text) read in place of those files."""
    mods = _modules(root, sources or {})
    index = {f"{opa._module_name(rel)}.{name}": (rel, node) for rel, m in mods.items() for name, node in m.defs}
    for rel, m in mods.items():     # a module-level binding joins the closure with what its value names
        for name, stmts in m.bound.items():
            index.setdefault(f"{opa._module_name(rel)}.{name}", (rel, ast.Module(body=stmts, type_ignores=[])))
    out = []
    for q in (MIGRATE, VERIFY):
        if q not in index:
            out.append(f"{'MIGRATE_NEVER_APPROVES' if q == MIGRATE else 'VERIFY_THROUGH_BINDING_AND_CALIBRATION'} "
                       f"{q.rsplit('.', 1)[0].replace('.', '/')}.py:1 {_short(q)} is missing")
    migrate = _closure(mods, index, (MIGRATE,))
    passed = _passed(mods, migrate)
    for q, rel, node in migrate:
        m, held, filters = mods[rel], _held(node, passed.get(q, ())), _filters(node)
        whys = [(line, "creates a ContractApproval (a migration only re-loads the input's: ContractApproval(**a))")
                for line in _created(m, node)] + [(n.lineno, why) for n in ast.walk(node)
                                                  if (why := _approves(m, n, held, filters))]
        out += [f"MIGRATE_NEVER_APPROVES {rel}:{line} {_short(q)} {why}: what migrate reaches re-binds the plan and never "
                "approves" for line, why in sorted(whys, key=lambda w: w[0])]
    for q, rel, node in _closure(mods, index, (MIGRATE, VERIFY)):
        out += [f"NO_COMMIT_OR_MERGE {rel}:{line} {_short(q)} {why}: what migrate or verify reaches never commits, "
                "merges or decides" for line, why in _decides(mods[rel], node, index)]
    if VERIFY in index:
        rel, node = index[VERIFY]
        out += _verify_rule(mods[rel], node, _closure(mods, index, (VERIFY,)))
    named, holders = set(), {q.rsplit(".", 1)[0] for q in ONLY_NAMED_BY} | {FINDING.rsplit(".", 1)[0]}
    for rel, m in mods.items():
        for scope, node in m.scopes():
            out += [f"ONE_DECISION_PATH {rel}:{n.lineno} {scope} names the module {_short(q)} as a value: what is called "
                    "on it is not followed" for n, _, q in _refs(m, node) if q in holders
                    and (rel.startswith(APP) or q != FINDING.rsplit(".", 1)[0])]
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
