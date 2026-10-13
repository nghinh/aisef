"""reach.py --out R.json (--base SHA [--head SHA] | --watch W.json) [--files F...] [--plain] [--control [A...]]

Which of the CHANGED functions does each kill file EXECUTE? The dependency basis a standing mutation result needs:
`read_set.py` says which files a kill file opens, and every kill file opens `aisef2/runtime/process_range.py` — importing a
module is not executing a function of it. This tool records the execution.

    {"commit", "base", "head", "tool", "python", "platform", "watch": {file: [name]}, "watch_size", "modules": {file: status},
     "diff": {...},
     "kill_files": {kf: {"executed": [[file, name]], "executed_in_children": [[file, name]], "loaded": [file],
                         "module_statements_executed": [file], "outcome", "seconds", "processes",
                         "children": {"hooked", "unhooked_python", "other"}}},
     "not_passed": {...}, "not_measured": {...}, "complete", "limits": [...]}

The watch list. `git diff --no-renames base head` over `aisef2/**.py` and `validation/v2/cleanup_authority.py`: every
function or method, by (file, qualified name — `Class.method`, `outer.<locals>.inner`, the name `co_qualname` carries)
that is new or whose OWN code differs from base. Own code: the def's decorators, arguments, annotations and body, where
a nested def stands only by what the enclosing code evaluates at the def (decorators, defaults, annotations — the last
only without `from __future__ import annotations`): the nested def's body is its own entry. Anything that makes the two
ASTs differ counts, a docstring or a constant included, and each name carries its kind (`new`, `changed`, `docstring`:
only the docstring differs) — because a mistake has a fixed direction: a function watched that need not be only makes a
target re-measured. Comments and layout are not in the AST. A name defined twice in a file (a property's getter and
setter) is one entry: changed when the multiset of its definitions differs. A function removed at head is listed
(`diff.removed_functions`), not watched: it cannot run. `--watch W.json` takes `{file: [names]}` (or `{"watch": {...}}`).

Module-level statements are not functions: they run once, when the module is imported (a class body's statements, a
def's decorators and defaults too). Each watched file's `<module>` code is watched as well and recorded as `loaded`;
`modules` says whether the file's statements that run at import are `new`, `changed`, `docstring`, `unchanged` or
`unknown` (a hand list), and `module_statements_executed` is `loaded` without the `unchanged`: importing a file whose
import-time statements changed IS executing changed code; importing one whose did not is only loading it. The name a def
binds is not such a statement: adding a def changes the module's namespace, visible without running the function only
to code that enumerates the namespace (`dir`, `inspect.getmembers`).

Not covered by execution: a kill file that READS the source of a changed file (an AST scan, a grep invariant, a hash)
executes none of it. That is read_set.py's `opened`; the two records answer different questions and a consumer needs both.

The recorder. The runner's own `mutation._run_file` runs the kill file alone (its argv, environment allowlist,
ProcessRange, judgement, leftovers settled only through validation/v2/cleanup_authority.py) on a fresh copy of its tree
(`mutation._pristine`, `_new_tree`), with one addition to the environment: PYTHONPATH naming a directory of this run that
holds a `sitecustomize.py`. Every Python process that loads it — the test process and each child that inherits
PYTHONPATH — installs a `sys.monitoring` PY_START callback (Python 3.12+; refused earlier). For a code object that is
not in the watch list the callback returns DISABLE, so it never fires again for that code object. For one that is, it
appends one line to the process's own file with one `os.write`, at the FIRST hit — a process SIGKILLed right after the
call has recorded it — and then also returns DISABLE. Per hit the file is opened and closed again: the recorder holds
no file descriptor, so a test that counts or closes descriptors does not see it. A forked child registers itself and
restarts the events, so it records its own first hits. A kill file's own `<module>` is watched as a witness: a PASS
whose own import was not seen is not measured (the hook never ran). The audit hook only counts child launches.

Outcome. A kill file that does not PASS is NOT put under `kill_files` (its partial record would "clear" functions it
never got to run): it is under `not_passed`, the output says so, `complete` is false and the exit status is 1. Files not
reached when the runner stops on a leftover it cannot prove are under `not_measured`. The other kill files stand.

`--plain` runs the kill files with no hook (no PYTHONPATH) and writes only outcome and seconds: the baseline for control
(g) and for the overhead. `--control` runs the controls on a toy tree first (each has an expected outcome, verified; any
failure: exit 1, nothing recorded) and, with a watch source, embeds them in the record.

Controls: a. a watched function called ⇒ recorded; b. the module imported, nothing called ⇒ NOT executed, `loaded`;
c. called only in a child Python process that inherits PYTHONPATH ⇒ recorded; d. called in a child with its own `env=`
without PYTHONPATH ⇒ NOT recorded, the child counted `unhooked_python` (the limit, shown); e. called from a thread ⇒
recorded; f. a process SIGKILLed right after the call ⇒ recorded; g. the recorder changes no kill file's PASS/FAIL (a
passing and a failing toy, hooked and plain); h. the qualified names of methods, nested defs, generators, coroutines and
a property setter, taken from the AST by this tool, are the ones the interpreter reports; i. a forked child records its
own first hit although its parent's first hit had disabled the event.

Limits — what a result recorded here is not (also in the output, `limits`):
  * Python processes only: a child that is not Python (git, sh) runs code nobody sees (`children.other`).
  * A child Python process is seen only when it loads our sitecustomize: it must inherit PYTHONPATH and not run with
    -I, -E or -S. A test that builds its own `env=` starts a child this recorder cannot see (`children.unhooked_python`),
    and so does a child of one. A child launched by something that raises no `subprocess.Popen` / `os.posix_spawn` /
    `os.spawn` / `os.system` audit event (`_posixsubprocess` called directly, multiprocessing's spawn) is not counted.
  * C-level calls, and code with no file of the tree (exec/compile, dataclass-generated methods): not matched.
  * A hit is lost when the process has no free file descriptor at that moment (retried at the next call).
  * What "executed" says: the function's code object started. Not a line, a branch, or that its result was used.
  * One-sided: the tool says a function WAS executed, never that one was NOT executed outside the children it hooked.
    The claim a consumer may draw is exactly: for the kill files and children measured, these changed functions ran;
    a target whose kill files ran none of them (and loaded no file whose module statements changed) has no changed
    code in its measured behaviour.
  * The unmutated tree: a mutant may execute what the original does not.
  * Scope: only `aisef2/**.py` and validation/v2/cleanup_authority.py are watched; other changed files of the runner's
    tree are listed in `diff.outside_scope`. Data files, environment and timing are not code (read_set.py's job).
  * The environment differs from the runner's by PYTHONPATH (and `sys.path` with it): a test that asserts on either
    fails here and is recorded as not passed. Measured on POSIX (macOS, Linux); Windows is not exercised.

Exit: 0 every kill file PASSed and was measured; 1 some did not, or a control failed; 2 refused before anything ran
(Python < 3.12, a checkout that differs from HEAD inside mutation.COPY, --head not HEAD, a bad path, no git).
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import pathlib
import sys
import tempfile
import textwrap
import time

sys.dont_write_bytecode = True   # the recorder never writes a .pyc into the repository it runs from
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import cleanup_authority as ca  # noqa: E402
from validation.v2 import mutation as M  # noqa: E402
from validation.v21 import read_set as RS  # noqa: E402

TOOL = "validation/v21/reach.py"
SCOPE = ("aisef2", "validation/v2/cleanup_authority.py")   # git pathspecs of the watch list
MODULE = "<module>"
POSIX = os.name == "posix"

# ---- the watch list ---------------------------------------------------------------------------------------------


class _Elide(ast.NodeTransformer):
    """A def stands in the code around it only by what that code evaluates where the def stands: its decorators,
    defaults and annotations. Its body is that function's own code (its own entry), its name is only bound. Class
    bodies stay: their statements run when the enclosing scope does. `deferred`: the module says
    `from __future__ import annotations`, so annotations are not evaluated where the def stands."""

    def __init__(self, deferred: bool):
        self.deferred = deferred

    def _def(self, node):
        a = node.args
        notes = [] if self.deferred else [x.annotation for x in (*a.posonlyargs, *a.args, a.vararg, *a.kwonlyargs, a.kwarg)
                                          if x and x.annotation] + ([node.returns] if node.returns else [])
        parts = [*node.decorator_list, *a.defaults, *(d for d in a.kw_defaults if d), *notes,
                 *(ast.Constant(ast.dump(t)) for t in getattr(node, "type_params", ()))]
        return [ast.Expr(value=x) for x in parts]   # a def with nothing to evaluate leaves no statement

    visit_FunctionDef = visit_AsyncFunctionDef = _def


def _no_docstrings(tree: ast.AST) -> ast.AST:
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            f = n.body[0]
            if isinstance(f, ast.Expr) and isinstance(f.value, ast.Constant) and isinstance(f.value.value, str):
                n.body = n.body[1:] or [ast.Pass()]
    return tree


def own(node: ast.AST, deferred: bool) -> tuple[str, str]:
    """(the AST text of `node`'s own code, the same without docstrings). For a def: its decorators, arguments,
    annotations and body, nested defs by what they evaluate (see _Elide); for a module: its statements."""
    n = copy.deepcopy(node)
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        body = _Elide(deferred).visit(ast.Module(body=n.body, type_ignores=[]))
        n.body = body.body or [ast.Pass()]
    else:
        n = _Elide(deferred).visit(n)
    return ast.dump(n), ast.dump(_no_docstrings(n))


_SCOPES = (ast.stmt, ast.excepthandler, ast.match_case)   # where a def can stand: never inside an expression


def functions(src: str) -> tuple[dict[str, list[tuple[str, str]]], tuple[str, str]]:
    """({qualified name: sorted own-code texts of every def of that name}, own-code texts of the module's statements)."""
    tree = ast.parse(src)
    deferred = any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
                   for n in tree.body)
    out: dict[str, list[tuple[str, str]]] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = prefix + ch.name
                out.setdefault(q, []).append(own(ch, deferred))
                walk(ch, q + ".<locals>.")
            elif isinstance(ch, ast.ClassDef):
                walk(ch, prefix + ch.name + ".")
            elif isinstance(ch, _SCOPES):
                walk(ch, prefix)
    walk(tree, "")
    return {q: sorted(v) for q, v in out.items()}, own(tree, deferred)


def changed(base_src: str | None, head_src: str) -> dict:
    """What differs between two versions of one file: `names` {name: new | changed | docstring} — new or whose own
    code differs, `docstring` when only a docstring does —, `unchanged`, `removed`, and `module`: the statements that
    run at import (new / changed / docstring / unchanged). `base_src` None: a new file."""
    new, new_mod = functions(head_src)
    old, old_mod = functions(base_src) if base_src is not None else ({}, None)
    names = {}
    for q, v in sorted(new.items()):
        o = old.get(q)
        if o != v:
            names[q] = "new" if o is None else ("docstring" if [x[1] for x in o] == [x[1] for x in v] else "changed")
    module = ("new" if old_mod is None else "unchanged" if old_mod == new_mod else
              "docstring" if old_mod[1] == new_mod[1] else "changed")
    return {"names": names, "unchanged": sorted(set(new) - set(names)), "removed": sorted(set(old) - set(new)),
            "module": module}


def _py(p: str) -> bool:
    return p.endswith(".py")


def watch_from_diff(root: pathlib.Path, base: str, head: str) -> tuple[dict, dict, dict]:
    """(watch {file: [names]}, modules {file: status}, diff) of `git diff --no-renames base head` over SCOPE; `diff`
    says each name's kind (new / changed / docstring) and what else differs."""
    status = RS._git(root, "diff", "--name-status", "--no-renames", base, head, "--", *SCOPE).splitlines()
    watch, modules, diff = {}, {}, {"files": {}, "deleted_files": [], "removed_functions": {}}
    for line in status:
        code, _, path = line.partition("\t")
        if not _py(path):
            continue
        if code.startswith("D"):
            diff["deleted_files"].append(path)
            continue
        old = None if code.startswith("A") else RS._git(root, "show", f"{base}:{path}")
        c = changed(old, RS._git(root, "show", f"{head}:{path}"))
        diff["files"][path] = {"status": code, "module": c["module"], "unchanged": len(c["unchanged"]),
                               "names": c["names"]}
        if c["removed"]:
            diff["removed_functions"][path] = c["removed"]
        if c["names"] or c["module"] != "unchanged":
            watch[path], modules[path] = sorted(c["names"]), c["module"]
    diff["deleted_files"].sort()
    # changed files of the runner's tree the tool does not watch: named, never silently dropped
    parts = [p for p in M.COPY if (root / p).exists()]
    every = RS._git(root, "diff", "--name-only", "--no-renames", base, head, "--", *parts).splitlines()
    diff["outside_scope"] = sorted(p for p in every if p not in diff["files"] and p not in diff["deleted_files"])
    return dict(sorted(watch.items())), dict(sorted(modules.items())), diff


def watch_from_file(path: pathlib.Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc = doc.get("watch", doc) if isinstance(doc, dict) else doc
    ok = isinstance(doc, dict) and all(isinstance(k, str) and isinstance(v, list) and all(isinstance(n, str) for n in v)
                                       for k, v in doc.items())
    if not ok or any(k.startswith("/") or "\\" in k or ".." in k.split("/") for k in doc):
        RS.refuse(f"--watch {path}: want {{relative file with '/': [qualified names]}}")
    return {k: sorted(set(v) - {MODULE}) for k, v in sorted(doc.items())}


# ---- the hook ---------------------------------------------------------------------------------------------------

#: The sitecustomize every hooked process runs. Never raises into the process: an exception here would break the code
#: under test. Per process one file `<pid>-<ns>.rch`: `P pid ppid start_ns words` (it ran the hook), `H file name` (a
#: watched code object started, once per process), `C event python hooked` (it started a child).
HOOK = r'''import os, sys, time

_EV, _ROOTS, _WATCH = @EVENTS@, @ROOTS@, @WATCH@
_HOOK = os.path.dirname(os.path.abspath(__file__))
_o, _w, _c, _pid, _fsdecode, _fspath = os.open, os.write, os.close, os.getpid, os.fsdecode, os.fspath
_norm, _join, _isabs, _nc = os.path.normpath, os.path.join, os.path.isabs, os.path.normcase
_mon = sys.monitoring
_DISABLE = _mon.DISABLE
_CWD0 = os.getcwd()
_LAUNCH = ("subprocess.Popen", "os.posix_spawn", "os.spawn", "os.system")
_W = {}   # absolute file, under every spelling of the tree -> (file relative to the tree, watched names)
for _r in _ROOTS:
    for _rel, _names in _WATCH.items():
        _W[_nc(_norm(_join(_r, _rel)))] = (_rel, frozenset(_names))
_st, _seen = {"path": None}, set()


def _append(line, create=False):
    fd = _o(_st["path"], os.O_WRONLY | os.O_APPEND | (os.O_CREAT | os.O_EXCL if create else 0), 0o600)
    try:
        _w(fd, line.encode("utf-8", "surrogateescape"))
    finally:
        _c(fd)


def _words():
    a = list(getattr(sys, "orig_argv", None) or sys.argv)[:4]
    return " ".join("<code>" if i and a[i - 1] == "-c" else w for i, w in enumerate(a))[:200].replace("\t", " ").replace("\n", " ")


def _register():
    ns, pid = time.time_ns(), _pid()
    _st["path"] = _join(_EV, "%d-%d.rch" % (pid, ns))
    _seen.clear()
    _append("P\t%d\t%d\t%d\t%s\n" % (pid, os.getppid(), ns, _words()), True)


def _start(code, offset):
    try:
        fn = code.co_filename
        hit = _W.get(_nc(_norm(fn if _isabs(fn) else _join(_CWD0, fn))))
        if hit is None:
            return _DISABLE
        rel, names = hit
        q = code.co_qualname
        if q not in names:
            return _DISABLE
    except Exception:
        return _DISABLE
    if (rel, q) in _seen:
        return _DISABLE
    try:
        _append("H\t%s\t%s\n" % (rel, q))
    except Exception:   # no free descriptor, no space: the event stays on, the next call tries again
        return None
    _seen.add((rel, q))
    return _DISABLE


def _isolated(argv):
    for a in list(argv)[1:]:
        a = _fsdecode(a)
        if a in ("-c", "-m") or not a.startswith("-"):
            return False
        if not a.startswith("--") and set(a[1:]) & set("IES"):
            return True
    return False


def _has_hook(env):
    for k, v in (os.environ if env is None else env).items():
        if _fsdecode(k) == "PYTHONPATH":
            return _HOOK in [_norm(x) for x in _fsdecode(v).split(os.pathsep)]
    return False


def _launch(event, a):
    py = hooked = 0
    if event != "os.system":
        if event == "subprocess.Popen":
            exe, argv, env = a[0], a[1], a[3]
        elif event == "os.posix_spawn":
            exe, argv, env = a
        else:   # os.spawn: mode, path, args, env
            exe, argv, env = a[1:]
        e = _fspath(exe)
        e = _fsdecode(e) if isinstance(e, bytes) else e
        py = int(os.path.basename(e).lower().startswith("python") or e == sys.executable)
        hooked = int(bool(py and isinstance(argv, (list, tuple)) and _has_hook(env) and not _isolated(argv)))
    _append("C\t%s\t%d\t%d\n" % (event, py, hooked))


def _audit(event, a):
    if event in _LAUNCH:
        try:
            _launch(event, a)
        except Exception:
            pass


_tool = None
for _t in (3, 4, 1, 2, 5, 0):   # the first monitoring tool id not in use
    try:
        _mon.use_tool_id(_t, "aisef-reach")
        _tool = _t
        break
    except ValueError:
        continue
if _tool is not None:
    _mon.register_callback(_tool, _mon.events.PY_START, _start)
    _mon.set_events(_tool, _mon.events.PY_START)


def _forked():
    try:
        _register()
        if _tool is not None:
            _mon.restart_events()   # what the parent's first hits disabled is this process's to record again
    except Exception:
        pass


sys.addaudithook(_audit)
os.register_at_fork(after_in_child=_forked)
try:
    _register()
except Exception:
    pass
try:   # a sitecustomize this one shadows still runs
    from importlib.machinery import PathFinder as _pf
    _spec = _pf.find_spec("sitecustomize", [p for p in sys.path if _norm(os.path.abspath(p or ".")) != _HOOK])
    if _spec is not None and _spec.loader is not None:
        import importlib.util as _u
        _spec.loader.exec_module(_u.module_from_spec(_spec))
except Exception:
    pass
'''


def hook_source(events: pathlib.Path, tree: pathlib.Path, watch: dict) -> str:
    w = {f: sorted({*names, MODULE}) for f, names in watch.items()}
    return (HOOK.replace("@EVENTS@", repr(str(events))).replace("@ROOTS@", repr(RS._roots(tree)))
            .replace("@WATCH@", repr(w)))


def merge(events: pathlib.Path) -> dict:
    """What every process of one kill-file run wrote under `events`. The test process is the earliest hooked one: every
    other hooked process descends from it."""
    procs: dict[int, tuple[int, int, str]] = {}   # pid -> (start_ns, ppid, words)
    hits: dict[int, set[tuple[str, str]]] = {}
    kids = {"python": 0, "python_unhooked": 0, "other": 0}
    bad = 0
    for f in sorted(events.glob("*.rch")):
        pid = None
        for line in f.read_bytes().decode("utf-8", "surrogateescape").split("\n"):
            kind, _, rest = line.partition("\t")
            try:
                if kind == "P":
                    p, ppid, ns, words = rest.split("\t", 3)
                    pid = int(p)
                    if pid not in procs or int(ns) < procs[pid][0]:
                        procs[pid] = (int(ns), int(ppid), words)
                    hits.setdefault(pid, set())
                elif kind == "H" and pid is not None:
                    rel, q = rest.split("\t", 1)
                    hits[pid].add((rel, q))
                elif kind == "C":
                    _, py, hooked = rest.split("\t")
                    kids["python"] += int(py)
                    kids["python_unhooked"] += int(py) - int(hooked)
                    kids["other"] += 1 - int(py)
                elif line:
                    bad += 1
            except ValueError:
                bad += 1
    test = min(procs, key=lambda p: (procs[p][0], p)) if procs else None
    everywhere = {h for hs in hits.values() for h in hs}
    in_children = {h for p, hs in hits.items() if p != test for h in hs}
    return {"executed": sorted([r, q] for r, q in everywhere if q != MODULE),
            "executed_in_children": sorted([r, q] for r, q in in_children if q != MODULE),
            "loaded": sorted({r for r, q in everywhere if q == MODULE}),
            "processes": len(procs), "unparsed_lines": bad,
            "children": {"hooked": max(len(procs) - 1, 0), "unhooked_python": kids["python_unhooked"],
                         "other": kids["other"]}}


# ---- the recorder -----------------------------------------------------------------------------------------------


def need_monitoring() -> None:
    if sys.version_info < (3, 12) or not hasattr(sys, "monitoring"):
        RS.refuse(f"sys.monitoring needs Python 3.12+; this is {sys.version.split()[0]}")


def record(root, files, watch: dict, modules: dict | None = None, *, hooked: bool = True, progress=None) -> dict:
    """The document (without commit/base/head) of kill files `files` (paths relative to `root`) against `watch`."""
    need_monitoring()
    root = pathlib.Path(root).resolve()
    modules = modules if modules is not None else {f: "unknown" for f in watch}
    kill_files, not_passed, not_measured = {}, {}, {}
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aisef-reach-", ignore_cleanup_errors=True) as t:
        scratch = pathlib.Path(t)
        pristine, digest = M._pristine(root, scratch / "pristine")
        tg = M._Target(None, scratch, ca.establish(scratch), "reach-" + M._worker(root), tests=list(files))
        real_env, stopped = M._env, None
        try:
            for i, rel in enumerate(files):
                if stopped:
                    not_measured[rel] = f"not reached: {stopped}"
                    continue
                if not (pristine / rel).is_file():
                    not_measured[rel] = "not a file of the runner's tree (outside mutation.COPY or missing)"
                    continue
                events, hook = scratch / f"events-{i}", scratch / f"hook-{i}"
                events.mkdir()
                hook.mkdir()
                tg.pristine = pristine   # a tree of its own per kill file, by the runner's helper; no residue check
                M._new_tree(tg)
                tg.pristine = None
                tree = tg.tree
                if hooked:
                    # the kill file's own import is a witness: the hook ran in the process that loaded it
                    src = hook_source(events, tree, {**watch, rel: watch.get(rel, [])})
                    (hook / "sitecustomize.py").write_text(src, encoding="utf-8")
                    M._env = lambda run, token, h=hook: {**real_env(run, token), "PYTHONPATH": str(h)}
                rows: list[dict] = []
                try:
                    row = M._run_file(tg, rel, rows, failfast=False, role="reach")
                except M._Stop as e:
                    row, stopped = rows[-1] if rows else {}, str(e)
                    row.setdefault("outcome", "INFRA")
                    row["why"] = str(e)
                finally:
                    M._env = real_env
                entry = {"outcome": row.get("outcome"), "seconds": row.get("seconds")}
                for k in ("why", "leaked", "residual"):
                    if row.get(k):
                        entry[k] = row[k]
                if row.get("first"):
                    entry["first"] = row["first"]
                if hooked:
                    got = merge(events)
                    witness = rel in got["loaded"]
                    got["loaded"] = [f for f in got["loaded"] if f != rel]
                    got["module_statements_executed"] = [f for f in got["loaded"]
                                                         if modules.get(f, "unknown") != "unchanged"]
                    entry = {**got, **entry}
                else:
                    witness = True
                if entry["outcome"] == "PASS" and witness:
                    kill_files[rel] = entry
                else:
                    if entry["outcome"] == "PASS":
                        entry["why"] = "its own import was not seen: the hook did not run in its process: nothing measured"
                    not_passed[rel] = entry
                if progress:
                    progress(i, len(files), rel, entry)
        finally:
            M._env = real_env
            if tg.holder is not None:
                tg.holder.cleanup()
    complete = not not_passed and not not_measured and len(kill_files) == len(files)
    doc = {"tool": TOOL, "tree_sha256": digest, "python": sys.version.split()[0], "platform": sys.platform,
           "mode": "hooked" if hooked else "plain", "complete": complete,
           "seconds": round(time.monotonic() - began, 2), "kill_files": kill_files}
    if not_passed:
        doc["not_passed"] = not_passed
    if not_measured:
        doc["not_measured"] = not_measured
    if not complete:
        doc["note"] = (f"{len(not_passed)} kill file(s) did not PASS or were not seen to load and {len(not_measured)} were "
                       f"not run: none of them is under kill_files, so none of them is measured and none clears anything "
                       f"(a partial record would clear functions the file never got to run)")
    return doc


LIMITS = [
    "Python processes only: a child that is not Python (git, sh) runs code nobody sees (children.other)",
    "a child Python process is seen only when it inherits PYTHONPATH and runs without -I, -E, -S: a test that builds its "
    "own env= starts a child this recorder cannot see (children.unhooked_python), and so does a child of one; a child "
    "launched with no subprocess.Popen/os.posix_spawn/os.spawn/os.system audit event is not counted either way",
    "not matched: C-level calls, code with no file of the tree (exec, compile, dataclass-generated methods)",
    "a hit is lost when the process has no free file descriptor at that moment (retried at the next call)",
    "a function executed before the hook is installed (the interpreter start) is not seen: none of the watched ones can be",
    "'executed' says the function's code object started; not a line, a branch, or that its result was used",
    "one-sided: a function WAS executed in the kill files and children measured; never that one was NOT executed "
    "outside the children hooked. A target whose kill files ran none of the watched functions and loaded no file "
    "whose module statements changed has no changed code in its measured behaviour",
    "module-level statements are not functions: `loaded` is the import; `module_statements_executed` is the import of "
    "a file whose module statements (or class bodies) are new or changed",
    "the unmutated tree: a mutant may execute what the original does not",
    "scope: aisef2/**.py and validation/v2/cleanup_authority.py; other changed files of the runner's tree are in "
    "diff.outside_scope; data files, environment and timing are not code",
    "a kill file that READS the source of a changed file (an AST scan, a grep invariant, a hash) executes none of it: "
    "that is read_set.py's `opened`; a consumer needs both records",
    "a def adds a name to its module's namespace: visible without running the function only to code that enumerates "
    "it (dir, inspect.getmembers); not an import-time statement here",
    "the environment differs from the runner's by PYTHONPATH (and sys.path with it): a test that asserts on either "
    "fails here and is recorded as not passed",
    "measured on POSIX (macOS, Linux); Windows is not exercised",
]


# ---- controls ---------------------------------------------------------------------------------------------------

_TOY_BASE = "def unwatched():\n    return 3\n"
_TOY = '''
def unwatched():
    return 3


def watched():
    return 1


def never_called():
    return 2


def watched_child():
    return 4


def watched_thread():
    return 5


def watched_killed():
    return 6


class Toy:
    def method(self):
        return 7

    @property
    def prop(self):
        return 8

    @prop.setter
    def prop(self, value):
        pass


def outer():
    def inner():
        return 9
    return inner()


def gen():
    yield 10


async def coro():
    return 11
'''
_TOY_FILE = "aisef2/toy.py"
_T = "tests/v2/test_{}.py"
_KILL = {
    "a": """
        import unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self): self.assertEqual(toy.watched(), 1)
        """,
    "b": """
        import unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self): self.assertEqual(toy.unwatched(), 3)   # imported, a function not watched called
        """,
    "c": """
        import subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # inherits the environment, PYTHONPATH with it
                subprocess.run([sys.executable, "-c", "from aisef2 import toy; toy.watched_child()"], check=True)
        """,
    "d": """
        import os, subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # its own environment: no PYTHONPATH, so the hook is not loaded
                subprocess.run([sys.executable, "-c", "from aisef2 import toy; toy.watched_child()"], check=True,
                               env={"PATH": os.environ["PATH"]})
        """,
    "e": """
        import threading, unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self):
                t = threading.Thread(target=toy.watched_thread)
                t.start()
                t.join()
        """,
    "f": """
        import subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # the child reports the call has returned, then waits; this test kills the child it started
                code = ("import sys; from aisef2 import toy; toy.watched_killed(); print('called', flush=True); "
                        "sys.stdin.read()")
                p = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(p.stdout.readline().strip(), "called")
                    p.kill()
                    self.assertEqual(p.wait(), -9)
                finally:
                    p.stdin.close()
                    p.stdout.close()
        """,
    "g_pass": """
        import unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self): self.assertEqual(toy.watched(), 1)
        """,
    "g_fail": """
        import unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self): self.assertEqual(toy.watched(), 99)
        """,
    "h": """
        import asyncio, unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self):
                t = toy.Toy()
                t.method()
                t.prop = 1
                self.assertEqual((toy.outer(), list(toy.gen()), asyncio.run(toy.coro())), (9, [10], 11))
        """,
    "i": """
        import os, unittest
        from aisef2 import toy
        class K(unittest.TestCase):
            def test(self):   # the parent's first hit disabled the event; the forked child must record its own
                toy.watched()
                pid = os.fork()
                if pid == 0:
                    try:
                        toy.watched()
                    finally:
                        os._exit(0)
                self.assertEqual(os.waitpid(pid, 0)[1], 0)
        """,
}
CONTROLS = {
    "a": "a watched function called in the test process is recorded",
    "b": "a module imported with none of its watched functions called is NOT executed (it is loaded)",
    "c": "a watched function called only in a child Python process that inherits PYTHONPATH is recorded",
    "d": "called in a child with its own env= is NOT recorded, and the child is counted unhooked_python",
    "e": "a watched function called from a thread is recorded",
    "f": "a process SIGKILLed right after the call has recorded it",
    "g": "the recorder changes no kill file's PASS/FAIL (a passing and a failing toy, hooked and plain)",
    "h": "the qualified names this tool derives from the AST are the ones the interpreter reports",
    "i": "a forked child records its own first hit although its parent's first hit disabled the event",
}
_G, _F = _T.format("g_pass"), _T.format("g_fail")


def _toy_tree(base: pathlib.Path) -> pathlib.Path:
    root = base / "root"
    for rel, text in {_TOY_FILE: _TOY, "aisef2/__init__.py": "", "tests/v2/__init__.py": "",
                      **{_T.format(k): textwrap.dedent(v) for k, v in _KILL.items()}}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def run_controls(which=None) -> dict:
    """Run the controls on a toy tree (the runner's own `_run_file`, the real hook) and verify each one's stated
    outcome. {"controls": {x: {"what", "expected", "got", "ok"}}, "ok", "seconds"}."""
    need_monitoring()
    which = [k for k in sorted(which or CONTROLS) if POSIX or k != "i"]   # i forks
    began = time.monotonic()
    c = changed(_TOY_BASE, _TOY)   # everything but `unwatched`, by this tool's own diff
    watch, modules, toy = {_TOY_FILE: sorted(c["names"])}, {_TOY_FILE: c["module"]}, _TOY_FILE
    names = {k: _T.format(k) for k in "abcdefhi"}
    out: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="aisef-reach-controls-", ignore_cleanup_errors=True) as t:
        root = _toy_tree(pathlib.Path(t))
        files = [names[k] for k in "abcdefhi" if k in which] + ([_G, _F] if "g" in which else [])
        hooked = record(root, files, watch, modules)
        plain = record(root, [_G, _F], watch, modules, hooked=False) if "g" in which else {}

    def row(doc, f):
        return (doc.get("kill_files", {}).get(f) or doc.get("not_passed", {}).get(f) or {})

    def kids(k):
        c_ = row(hooked, names[k])["children"]
        return c_["hooked"], c_["unhooked_python"]

    def same(f):   # outcome hooked/plain, and for a failure the signature of its first failing test
        h, p = row(hooked, f), row(plain, f)
        return [h.get("outcome"), p.get("outcome")] + ([] if M.signature(h.get("first")) == M.signature(p.get("first"))
                                                       else ["first differs"])
    exp = {
        "a": ([[toy, "watched"]], lambda: row(hooked, names["a"])["executed"]),
        "b": (([], [toy]), lambda: (row(hooked, names["b"])["executed"], row(hooked, names["b"])["loaded"])),
        "c": (([[toy, "watched_child"]], (1, 0)), lambda: (row(hooked, names["c"])["executed"], kids("c"))),
        "d": (([], (0, 1)), lambda: (row(hooked, names["d"])["executed"], kids("d"))),
        "e": ([[toy, "watched_thread"]], lambda: row(hooked, names["e"])["executed"]),
        "f": (([[toy, "watched_killed"]], "PASS"),
              lambda: (row(hooked, names["f"])["executed"], row(hooked, names["f"])["outcome"])),
        "g": ([["PASS", "PASS"], ["FAIL", "FAIL"]], lambda: [same(_G), same(_F)]),
        "h": (sorted([toy, q] for q in ("Toy.method", "Toy.prop", "outer", "outer.<locals>.inner", "gen", "coro")),
              lambda: row(hooked, names["h"])["executed"]),
        "i": (([[toy, "watched"]], [[toy, "watched"]]),
              lambda: (row(hooked, names["i"])["executed"], row(hooked, names["i"])["executed_in_children"])),
    }
    for k in which:
        want, get = exp[k]
        try:
            got = get()
        except (KeyError, IndexError, TypeError) as e:   # the run did not produce the row: the control fails
            got = f"no result: {type(e).__name__}: {e}"
        want, got = json.loads(json.dumps(want)), json.loads(json.dumps(got))   # as written: tuples are lists
        out[k] = {"what": CONTROLS[k], "expected": want, "got": got, "ok": got == want}
    return {"controls": out, "ok": all(v["ok"] for v in out.values()), "seconds": round(time.monotonic() - began, 2)}


# ---- command line -------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None, root: pathlib.Path = ROOT) -> int:
    ap = argparse.ArgumentParser(prog="reach.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--base", help="the snapshot the standing results were measured at (a commit)")
    ap.add_argument("--head", default="HEAD", help="the snapshot measured; must be HEAD (default)")
    ap.add_argument("--watch", type=pathlib.Path, help="a watch list given by hand: {file: [qualified names]}")
    ap.add_argument("--files", nargs="+", metavar="F", help="kill files (default: every file of V21_TARGETS)")
    ap.add_argument("--plain", action="store_true", help="no hook: only outcome and seconds (baseline, overhead)")
    ap.add_argument("--control", nargs="*", default=None, choices=sorted(CONTROLS), metavar="X",
                    help="run the controls (all, or the named ones) on a toy tree first; a failure stops the run")
    a = ap.parse_args(argv)
    need_monitoring()
    doc: dict = {}
    if a.control is not None:
        ctl = run_controls(a.control)
        for k, v in ctl["controls"].items():
            print(f"control {k}: {'ok' if v['ok'] else 'FAILED'}  {v['what']}", file=sys.stderr)
            if not v["ok"]:
                print(f"    expected {v['expected']!r}\n    got      {v['got']!r}", file=sys.stderr)
        doc["controls"] = ctl
        if not ctl["ok"] or not (a.base or a.watch):
            if a.out:
                a.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
            return 0 if ctl["ok"] else 1
    if bool(a.base) == bool(a.watch):
        RS.refuse("exactly one of --base and --watch (and --out) is required")
    if not a.out:
        RS.refuse("--out is required")
    files = list(dict.fromkeys(a.files or RS.kill_files()))
    if bad := [f for f in files if f.startswith("/") or "\\" in f or ".." in f.split("/")]:
        RS.refuse(f"not a path relative to the root with '/': {bad[0]!r}")
    head = RS.head_of(root, None if a.head == "HEAD" else a.head)
    if a.base:
        base = RS._git(root, "rev-parse", "--verify", f"{a.base}^{{commit}}")
        watch, modules, diff = watch_from_diff(root, base, head)
    else:
        base, watch, diff = None, watch_from_file(a.watch), {"files": "by hand"}
        modules = {f: "unknown" for f in watch}

    def progress(i, n, rel, e):
        k = e.get("children", {})
        print(f"[{i + 1}/{n}] {e['outcome']:7s} {e['seconds']}s executed={len(e.get('executed', []))} "
              f"loaded={len(e.get('loaded', []))} children={k} {rel}", file=sys.stderr, flush=True)
    try:
        got = record(root, files, watch, modules, hooked=not a.plain, progress=progress)
    except (ca.Unproven, OSError) as e:
        RS.refuse(f"the runner stopped before any kill file: {e}")
    out = {"commit": head, "base": base, "head": head, **got, "watch": watch, "watch_size": sum(map(len, watch.values())),
           "modules": modules, "diff": diff, "limits": LIMITS, **doc}
    a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"{len(got['kill_files'])}/{len(files)} kill files measured in {got['seconds']}s -> {a.out}"
          + (f"\n{got['note']}" if got.get("note") else ""), file=sys.stderr)
    return 0 if got["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
