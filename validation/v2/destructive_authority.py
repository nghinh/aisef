"""INV-MUTATION-AUTHORITY — the destructive-call-site ledger and its checker (owner authorization of 2026-09-24 §4–§5).

    Mutation, fault injection, test failure, probe result, or implementation-under-test output MUST NOT expand
    host-side destructive authority. Authority to kill, delete, clean, release, terminate, or mutate external
    resources MUST come exclusively from an independently established controller view.

Every call under aisef2/, validation/v2/ and tests/v2/ that signals a process, terminates a job or removes a path is
discovered mechanically (AST, never grep) and must be bound by one row of `destructive_sites.json` — and so is every
destructive callable handed over *by reference* to a cleanup or callback registration (`addCleanup(shutil.rmtree, d)`,
`partial(os.kill, pid)`, `stack.callback(...)`, `atexit.register(...)`, `weakref.finalize(...)`), through an alias
bound in the same scope (`callback = os.kill; register(callback, pid)`) or called through one (`callback(pid)`)
(WP52-001): the action still happens, so the site does not disappear from the authority model. The registrars are a
closed taxonomy; a destructive reference handed to any other call, or passed by keyword, fails closed. A row is not an
allowlist entry: it declares the site's *authority source* — one of a closed set of narrow classes — and the checker
validates, as far as the source allows statically, that the target is still derived that way (a handle the controller
created, a pid taken from such a handle, a group the controller created, the authority's own host table, a path the
scope or the test created, …). A site with no row, a row with no site, a declared source the derivation no longer
matches, an ambiguous derivation, or a destructive API the taxonomy does not know: each fails, closed.

The runtime half of the invariant is `cleanup_authority.py`: what code under mutation reports is a claim, proved or
refused there, never permission. This module is stdlib only and imports nothing from aisef2.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_REL = "validation/v2/destructive_sites.json"
SCOPES = ("aisef2", "validation/v2", "tests/v2")

#: destructive callables, by the kind of target they act on
TAXONOMY = {
    "process": {"kill", "terminate", "send_signal", "TerminateProcess", "pthread_kill"},
    "process_group": {"killpg"},
    "job": {"TerminateJobObject"},
    "path": {"rmtree", "unlink", "remove", "rmdir", "removedirs"},
}
CALLABLES = {name: kind for kind, names in TAXONOMY.items() for name in names}
#: argv[0] of a subprocess call, or a token in a shell string, that would be a destructive host action
SHELL_DESTRUCTIVE = ("kill", "pkill", "killall", "rm", "rmdir", "taskkill")
SPAWNERS = {"run", "Popen", "call", "check_call", "check_output", "system"}
#: process/host APIs the taxonomy does not model: their presence fails the check, closed
UNSUPPORTED_IMPORTS = {"psutil"}
#: callback registrations the harness models: registrar -> (index of the callable, index of the target it is given)
REGISTRARS = {"addCleanup": (0, 1), "callback": (0, 1), "partial": (0, 1), "register": (0, 1), "finalize": (1, 2)}
DESTRUCTIVE_MODULES = ("os", "shutil", "signal")
#: destructive callables that also exist as methods (Popen.kill, Path.unlink, ...): the receiver is then the target
METHOD_FORMS = {"kill", "terminate", "send_signal", "unlink", "remove", "rmdir"}
#: the closed set of authority sources a row may declare (§4: no KNOWN_SAFE, ALLOWLISTED, LEGACY, TRUSTED)
AUTHORITY_SOURCES = {
    "CONTROLLER_CREATED_HANDLE": "a Popen / job handle the controller itself created, still held",
    "CONTROLLER_CREATED_PID": "the pid read from a Popen the controller created (never from a table or a report)",
    "CONTROLLER_CREATED_PROCESS_GROUP": "the group the controller created (its anchor's session, or its own)",
    "INDEPENDENT_HOST_TABLE": "cleanup_authority's own reading of the host, proved by ancestry, birth and leadership",
    "SCOPE_OWNED_PATH": "a directory a scope owns because the controller created it and registered it",
    "TEST_CREATED_HANDLE": "a Popen the test itself started",
    "TEST_CREATED_PATH": "a path the test itself created (temporary directory, or a file it wrote)",
    "DELEGATION": "a call to a method of the same object that is itself a ledgered site",
    "GUARD_NEGATIVE_PROBE": "an attempt the V1 preventive guard must refuse, on a path that must not exist",
    "LIVENESS_PROBE_SIGNAL_0": "kill(pid, 0): a liveness question, no signal is delivered",
    "COLLECTION_METHOD": "list.remove on an in-memory collection: not a host resource",
}
#: what the target expression may be bound to, per class (a call whose source names one of these created the object)
HANDLE_CREATORS = ("Popen(", "ProcessRange(", "CreateJobObjectW(")
PATH_CREATORS = ("mkdtemp(", "TemporaryDirectory(", "copytree(")


class Site:
    def __init__(self, path: str, scope: str, callable_: str, target: str, node: ast.Call, kind: str,
                 func: ast.AST | None, cls: ast.ClassDef | None, module: ast.Module, parents: dict):
        self.path, self.scope, self.callable, self.target, self.node = path, scope, callable_, target, node
        self.kind, self.func, self.cls, self.module, self.parents = kind, func, cls, module, parents

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.path, self.scope, self.callable, self.target)


# ------------------------------------------------------------------------------------------------ discovery

def _parents(tree: ast.Module) -> dict:
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _enclosing(node: ast.AST, parents: dict):
    func = cls = None
    names = []
    n = node
    while n in parents:
        n = parents[n]
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if func is None:
                func = n
            if not isinstance(n, ast.Lambda):
                names.append(n.name)
        elif isinstance(n, ast.ClassDef):
            if cls is None:
                cls = n
            names.append(n.name)
    return func, cls, ".".join(reversed(names)) or "<module>"


def _shell_destructive(call: ast.Call) -> str | None:
    """A subprocess/os.system call whose command is a destructive host tool (argv[0] or a shell-string token)."""
    name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", None)
    if name not in SPAWNERS or not call.args:
        return None
    a0 = call.args[0]
    if isinstance(a0, (ast.List, ast.Tuple)) and a0.elts and isinstance(a0.elts[0], ast.Constant):
        head = str(a0.elts[0].value).split("/")[-1]
        return ast.unparse(a0)[:80] if head in SHELL_DESTRUCTIVE else None
    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
        toks = a0.value.split()
        return a0.value[:80] if toks and toks[0].split("/")[-1] in SHELL_DESTRUCTIVE else None
    return None


def _aliases(tree: ast.Module, parents: dict) -> dict[tuple[int, str], str]:
    """Every `callback = os.kill` in the module, keyed by (id of the enclosing function, class or module, name):
    the destructive callable the name stands for in that scope. Computed once per module."""
    out = {}
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        v = n.value
        if isinstance(v, ast.Attribute) and v.attr in CALLABLES and isinstance(v.value, ast.Name) \
                and v.value.id in DESTRUCTIVE_MODULES:
            func, cls, _ = _enclosing(n, parents)
            if func is None and cls is not None:
                continue  # a class-level name: visible neither in its methods nor at module level
            holder = func if func is not None else tree
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[(id(holder), t.id)] = ast.unparse(v)
    return out


def _alias(name: str | None, holders: list, aliases: dict) -> str | None:
    """The destructive callable `name` stands for in the enclosing function, class or module, if any."""
    for holder in holders:
        found = aliases.get((id(holder), name))
        if found:
            return found
    return None


def _destructive_ref(expr: ast.AST, holders: list, aliases: dict) -> tuple[str, str | None] | None:
    """A destructive callable passed by reference (not called): `shutil.rmtree` / `os.kill`, a bound method `c.kill`
    (its receiver is the target), or a name aliased to one in the enclosing scopes. -> (callable text, receiver)."""
    if isinstance(expr, ast.Attribute) and expr.attr in CALLABLES:
        if isinstance(expr.value, ast.Name) and expr.value.id in DESTRUCTIVE_MODULES:
            return ast.unparse(expr), None
        return ast.unparse(expr), ast.unparse(expr.value)
    if isinstance(expr, ast.Name):
        aliased = _alias(expr.id, holders, aliases)
        if aliased:
            return f"{expr.id}={aliased}", None
    return None


def _references(node: ast.Call, name: str | None, holders: list, aliases: dict) -> list[tuple[str, str, str]]:
    """Destructive callables handed to this call by reference -> (callable text, target text, kind); kind is
    'callback_unmodelled' when the registrar is outside REGISTRARS or the callable travels by keyword (fail closed)."""
    out = []
    for i, arg in enumerate(node.args):
        ref = _destructive_ref(arg, holders, aliases)
        if ref is None:
            continue
        callable_, receiver = ref
        kind = CALLABLES[callable_.split("=")[-1].split(".")[-1]]
        if name in REGISTRARS and REGISTRARS[name][0] == i:
            j = REGISTRARS[name][1]
            target = receiver or (ast.unparse(node.args[j]) if len(node.args) > j else "")
            out.append((f"{name}->{callable_}", target, kind))
        else:
            out.append((f"{name}->{callable_}", receiver or "", "callback_unmodelled"))
    for kw in node.keywords:
        ref = _destructive_ref(kw.value, holders, aliases)
        if ref is not None:
            out.append((f"{name}->{kw.arg}={ref[0]}", ref[1] or "", "callback_unmodelled"))
    return out


def discover(root: pathlib.Path = ROOT) -> tuple[list[Site], list[str]]:
    """Every destructive call site under the scopes — direct calls, calls through an alias, and destructive callables
    handed over by reference — and the problems discovery itself raises (unsupported APIs)."""
    sites, problems = [], []
    for base in SCOPES:
        for p in (root / base).rglob("*.py"):
            rel = p.relative_to(root).as_posix()
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
            parents = _parents(tree)
            aliases = _aliases(tree, parents)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for m in mods:
                        if m.split(".")[0] in UNSUPPORTED_IMPORTS:
                            problems.append(f"{rel}:{node.lineno}: imports {m}: a process API the taxonomy does not "
                                            "cover — fail closed")
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                func, cls, scope = _enclosing(node, parents)
                holders = [h for h in (func, tree) if h is not None]  # a class-level name is not visible in a method
                for callable_, target, kind in _references(node, name, holders, aliases):
                    sites.append(Site(rel, scope, callable_, target, node, kind, func, cls, tree, parents))
                aliased = _alias(name, holders, aliases) if isinstance(f, ast.Name) and name not in CALLABLES else None
                if aliased:  # `callback(pid)` where `callback = os.kill`: the direct call, through its alias
                    sites.append(Site(rel, scope, f"{name}={aliased}", ast.unparse(node.args[0]) if node.args else "",
                                      node, CALLABLES[aliased.split(".")[-1]], func, cls, tree, parents))
                    continue
                if name in CALLABLES:
                    kind = CALLABLES[name]
                    if name == "remove" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Subscript):
                        kind = "collection"  # list.remove on an in-memory value: declared, never a host resource
                    if isinstance(f, ast.Attribute) and name in METHOD_FORMS \
                            and not (isinstance(f.value, ast.Name) and f.value.id in DESTRUCTIVE_MODULES):
                        target = ast.unparse(f.value)  # a method: the receiver is the target
                    else:
                        target = ast.unparse(node.args[0]) if node.args else ""
                    sites.append(Site(rel, scope, ast.unparse(f), target, node, kind, func, cls, tree, parents))
                else:
                    shell = _shell_destructive(node)
                    if shell:
                        sites.append(Site(rel, scope, "shell:" + shell, "", node, "shell", func, cls, tree, parents))
    sites.sort(key=lambda s: (s.path, s.node.lineno))  # one order, whatever the file system's or the walk's
    problems.sort()
    return sites, problems


# ------------------------------------------------------------------------------------------------ derivation shapes

def _root(expr: str) -> str:
    """The name the target is derived from: `self._anchor.pid` -> `self._anchor`; `c` -> `c`;
    `sorted((c / 'x').glob('*'))[0]` -> `c` (the first name that is not a builtin or a module)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return expr
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self":
            return f"self.{n.attr}"
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id not in ("sorted", "list", "str", "pathlib", "os", "shutil", "signal"):
            return n.id
    return expr


def _bindings(site: Site, name: str) -> list[str]:
    """Source texts bound to `name` in the enclosing function, then class, then module (`self.x` in any method)."""
    out = []
    holders = [h for h in (site.func, site.cls, site.module) if h is not None]
    for holder in holders:
        for n in ast.walk(holder):
            if isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if any(ast.unparse(t) == name for t in targets) and n.value is not None:
                    out.append(ast.unparse(n.value))
                for t in targets:  # `a, b = x, y`: the element bound to `name`
                    if isinstance(t, ast.Tuple) and isinstance(n.value, ast.Tuple):
                        for elt, val in zip(t.elts, n.value.elts, strict=False):
                            if ast.unparse(elt) == name:
                                out.append(ast.unparse(val))
            elif isinstance(n, ast.withitem) and n.optional_vars is not None and ast.unparse(n.optional_vars) == name:
                out.append(ast.unparse(n.context_expr))
    return out


def _parameter_annotation(site: Site, name: str) -> str | None:
    if site.func is None or isinstance(site.func, ast.Lambda):
        return None
    for a in site.func.args.args + site.func.args.kwonlyargs:
        if a.arg == name:
            return ast.unparse(a.annotation) if a.annotation is not None else ""
    return None


def _callee_creates(site: Site, binding: str, creators: tuple[str, ...]) -> bool:
    """`x = helper(...)` / `x = self.helper(...)`: the helper, in this module or class, creates the object itself."""
    callee = binding.split("(")[0].split(".")[-1]
    for holder in (site.cls, site.module):
        if holder is None:
            continue
        for n in ast.walk(holder):
            if isinstance(n, ast.FunctionDef) and n.name == callee:
                return any(c in ast.unparse(n) for c in creators)
    return False


def _created(site: Site, name: str, creators: tuple[str, ...]) -> bool:
    bindings = _bindings(site, name)
    return any(any(c in b for c in creators) or _callee_creates(site, b, creators) for b in bindings)


def _in_assert_raises(site: Site) -> bool:
    n = site.node
    while n in site.parents:
        n = site.parents[n]
        if isinstance(n, ast.With) and any("assertRaises" in ast.unparse(i.context_expr) for i in n.items):
            return True
    return False


def _module_text(root: pathlib.Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _stdlib_only(root: pathlib.Path, rel: str) -> bool:
    tree = ast.parse(_module_text(root, rel))
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            top = (n.names[0].name if isinstance(n, ast.Import) else (n.module or "")).split(".")[0]
            if top not in sys.stdlib_module_names:
                return False
    return True


def validate(site: Site, row: dict, root: pathlib.Path, rows_by_key: dict) -> list[str]:
    """The declared authority source still matches the derivation of the site's target."""
    src, where = row["authority_source"], f"{site.path}:{site.node.lineno} [{site.scope}] {site.callable}({site.target})"
    out = []
    target_root = _root(site.target) if site.target else ""
    if src not in AUTHORITY_SOURCES:
        return [f"{where}: authority source {src!r} is not one of the closed set {sorted(AUTHORITY_SOURCES)}"]
    if src in ("CONTROLLER_CREATED_HANDLE", "TEST_CREATED_HANDLE"):
        if site.kind not in ("process", "job"):
            out.append(f"{where}: a handle authority acts on a process or a job, not on a {site.kind}")
        if not _created(site, target_root, HANDLE_CREATORS):
            out.append(f"{where}: target {target_root!r} is not bound in its scope to a handle the "
                       f"{'controller' if src.startswith('CONTROLLER') else 'test'} created ({HANDLE_CREATORS})")
    elif src == "CONTROLLER_CREATED_PID":
        if not site.target.endswith(".pid") or site.kind not in ("process", "process_group"):
            out.append(f"{where}: a controller-created pid is read as `<handle>.pid` and signalled")
        ann = _parameter_annotation(site, target_root)
        if not (ann == "subprocess.Popen" or _created(site, target_root, HANDLE_CREATORS)):
            out.append(f"{where}: {target_root!r} is neither a subprocess.Popen parameter nor bound to a handle "
                       "the controller created")
    elif src == "CONTROLLER_CREATED_PROCESS_GROUP":
        if site.target == "self.group":
            assigns = [n for n in ast.walk(site.module) if isinstance(n, ast.Assign)
                       and any(ast.unparse(t) == "self.group" for t in n.targets)]
            in_adopt = [n for n in assigns if any(isinstance(p, ast.FunctionDef) and p.name == "adopt"
                                                  for p in _ancestors(n, site.parents))]
            calls = [ast.unparse(n.args[0]) for n in ast.walk(site.module) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == "adopt" and n.args]
            if len(assigns) != 1 or len(in_adopt) != 1 or not calls or any(c != "self._anchor.pid" for c in calls):
                out.append(f"{where}: self.group must be assigned only by adopt(), and adopt() called only with "
                           f"self._anchor.pid (assignments {len(assigns)}, adopt calls {calls})")
        elif site.target == "os.getpgrp()":
            pr = _module_text(root, "aisef2/runtime/process_range.py")
            if '"start_new_session": True' not in pr:
                out.append(f"{where}: the anchor's own group is its own only when the controller starts it with "
                           "start_new_session=True (aisef2/runtime/process_range.py)")
        else:
            out.append(f"{where}: a controller-created group is `self.group` (adopted from the anchor) or the "
                       "anchor's own `os.getpgrp()`; {site.target!r} is neither")
    elif src == "INDEPENDENT_HOST_TABLE":
        if site.path != "validation/v2/cleanup_authority.py":
            out.append(f"{where}: only cleanup_authority.py reads the independent host table")
        elif not _stdlib_only(root, site.path):
            out.append(f"{where}: cleanup_authority.py imports beyond the stdlib — its view is no longer independent")
        if not any(("owned(" in b or "mine.get(" in b or "_proved(" in b or "prove_member(" in b)
                   for b in _bindings(site, target_root)):
            out.append(f"{where}: {target_root!r} is not bound from the authority's own proof "
                       "(owned()/mine.get()/prove_member())")
    elif src == "SCOPE_OWNED_PATH":
        if site.target != "self.path" or site.cls is None:
            out.append(f"{where}: a scope-owned path is `self.path` of a resource class")
        else:
            init = next((n for n in site.cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
            if init is None or "self.path" not in ast.unparse(init):
                out.append(f"{where}: {site.cls.name}.__init__ does not bind self.path")
            constructions = [n for n in ast.walk(ast.parse(_module_text(root, site.path)))
                             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == site.cls.name]
            for base in ("aisef2",):
                for p in sorted((root / base).rglob("*.py")):
                    if p.name == pathlib.Path(site.path).name:
                        continue
                    t = ast.parse(p.read_text(encoding="utf-8"))
                    constructions += [n for n in ast.walk(t) if isinstance(n, ast.Call)
                                      and getattr(n.func, "id", getattr(n.func, "attr", "")) == site.cls.name]
            if constructions:
                out.append(f"{where}: {site.cls.name} is constructed in aisef2 ({len(constructions)}x) — the origin of "
                           "its path must be declared before it may be released")
    elif src == "TEST_CREATED_PATH":
        if site.kind != "path":
            out.append(f"{where}: a test-created path authority acts on a path")
        via = row.get("derivation_via")
        created = _created(site, target_root, PATH_CREATORS + ("self.dir",))
        wrote = site.func is not None and any(f"{target_root}.{m}(" in ast.unparse(site.func)
                                              for m in ("write_text", "write_bytes", "touch", "mkdir"))
        parameter = _parameter_annotation(site, target_root) is not None or (
            isinstance(site.func, ast.Lambda) and any(a.arg == target_root for a in site.func.args.args))
        via_ok = bool(via) and parameter and site.cls is not None and any(
            isinstance(n, ast.FunctionDef) and n.name == via and any(c in ast.unparse(n) for c in PATH_CREATORS)
            for n in site.cls.body)
        if target_root == "self.dir" or "self.dir" in site.target:
            created = created or (site.cls is not None and any(
                isinstance(n, ast.FunctionDef) and n.name == "setUp" and any(c in ast.unparse(n) for c in PATH_CREATORS)
                for n in site.cls.body))
        if not (created or wrote or via_ok):
            out.append(f"{where}: {target_root!r} is not a path this test created (no temporary directory, no write "
                       f"of it in the function, no creating helper {via!r})")
    elif src == "DELEGATION":
        if not site.callable.startswith("self.") or site.cls is None:
            out.append(f"{where}: a delegation is `self.<method>()` on the same object")
        else:
            method = site.callable.split(".")[1]
            key = (site.path, f"{site.cls.name}.{method}")
            if not any(k[0] == key[0] and k[1] == key[1] for k in rows_by_key):
                out.append(f"{where}: delegates to {site.cls.name}.{method}, which is not a ledgered site")
    elif src == "GUARD_NEGATIVE_PROBE":
        if not _in_assert_raises(site):
            out.append(f"{where}: a guard probe is issued inside `with self.assertRaises(...)`; this one is not")
        if "never_exists" not in site.target and "ABSENT" not in site.target:
            out.append(f"{where}: a guard probe targets a path that must never exist; {site.target!r} does not say so")
    elif src == "LIVENESS_PROBE_SIGNAL_0":
        args = site.node.args
        if not (site.callable == "os.kill" and len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value == 0):
            out.append(f"{where}: a liveness probe is os.kill(pid, 0) with a literal 0")
    elif src == "COLLECTION_METHOD":
        recv = site.node.func.value if isinstance(site.node.func, ast.Attribute) else None
        if site.kind != "collection" or not isinstance(recv, ast.Subscript) or site.callable.split(".")[-1] != "remove":
            out.append(f"{where}: a collection method is `.remove()` on a subscripted in-memory value")
    return out


def _ancestors(node: ast.AST, parents: dict):
    n = node
    while n in parents:
        n = parents[n]
        yield n


# ------------------------------------------------------------------------------------------------ the check

def load_ledger(root: pathlib.Path = ROOT) -> list[dict]:
    return json.loads((root / LEDGER_REL).read_text(encoding="utf-8"))["sites"]


def check(root: pathlib.Path = ROOT) -> list[str]:
    sites, problems = discover(root)
    try:
        rows = load_ledger(root)
    except FileNotFoundError:
        return problems + [f"{LEDGER_REL} is missing"]
    by_key: dict[tuple, dict] = {}
    for r in rows:
        k = (r["path"], r["scope"], r["callable"], r["target"])
        if k in by_key:
            problems.append(f"ledger: duplicate row for {k}")
        by_key[k] = r
        missing = [f for f in ("target_kind", "authority_source", "justification", "enforcement") if not r.get(f)]
        if missing:
            problems.append(f"ledger row {k}: missing {missing}")
    seen: dict[tuple, int] = {}
    for s in sites:
        seen[s.key] = seen.get(s.key, 0) + 1
        row = by_key.get(s.key)
        if row is None:
            problems.append(f"{s.path}:{s.node.lineno} [{s.scope}] {s.callable}({s.target}): destructive site with no "
                            "ledger row — its authority source is undeclared")
            continue
        if row["target_kind"] != s.kind:
            problems.append(f"{s.path}:{s.node.lineno}: ledger says target_kind {row['target_kind']!r}, the site acts "
                            f"on a {s.kind}")
        if s.kind == "shell":
            problems.append(f"{s.path}:{s.node.lineno}: a shell-level destructive command ({s.callable}) has no "
                            "statically verifiable authority — fail closed")
        if s.kind == "callback_unmodelled":
            problems.append(f"{s.path}:{s.node.lineno}: a destructive callable handed by reference to a registration "
                            f"the taxonomy does not model ({s.callable}) — its target cannot be derived; fail closed")
        problems += validate(s, row, root, by_key)
    for k, r in by_key.items():
        if k not in seen:
            problems.append(f"ledger row {k} points to a site that no longer exists")
        elif seen[k] != r.get("occurrences", 1):
            problems.append(f"ledger row {k}: occurrences {r.get('occurrences', 1)}, found {seen[k]}")
    return problems


def audit(root: pathlib.Path = ROOT) -> list[dict]:
    """The audit table (§1): every site, its declared authority and the checker's verdict on it."""
    sites, _ = discover(root)
    by_key = {(r["path"], r["scope"], r["callable"], r["target"]): r for r in load_ledger(root)}
    out = []
    for s in sites:
        row = by_key.get(s.key)
        probs = validate(s, row, root, by_key) if row else ["no ledger row"]
        out.append({"file": s.path, "line": s.node.lineno, "scope": s.scope, "operation": s.callable,
                    "target": s.target, "target_kind": s.kind,
                    "authority_source": row["authority_source"] if row else None,
                    "derivation": row.get("justification") if row else None,
                    "independently_established": bool(row) and not probs and row["authority_source"] not in
                    ("GUARD_NEGATIVE_PROBE", "LIVENESS_PROBE_SIGNAL_0", "COLLECTION_METHOD"),
                    "verdict": "PASS" if row and not probs else "FAIL", "problems": probs})
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--audit" in argv:
        for r in audit():
            print(f"{r['verdict']:4} {r['file']}:{r['line']} [{r['scope']}] {r['operation']}({r['target']}) "
                  f"<- {r['authority_source']}" + (f"  !! {r['problems']}" if r["problems"] else ""))
        return 0
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("destructive authority: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
