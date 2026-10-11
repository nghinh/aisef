"""read_set.py --out R.json [--commit SHA] [--files F...] [--control no-stat|no-children|own-walk]...

The recorder of the read-set `validation/qualification/v21_snapshot_delta.py --read-set R.json` consumes: for every kill
file, which files of the runner's tree it opened or looked up, and which directories it listed.

    {"commit": "<HEAD's full sha>", "kill_files": {"<kill file>": {"opened": [path], "listed": [dir],
                                                                   "listed_by": {dir: [file]}, "listed_via": {dir: [file]}}}}

Every path is relative to the root of the tree the run used ("." is the root; what lies outside it is left out),
written with "/", sorted, unique; a kill file's own path is among its `opened` (its import opens it).

Who listed it. Every listing event (os.listdir, os.scandir — which every glob, rglob and walk of the stdlib goes
through) also records the files of the tree on the Python stack at the event: the stdlib, site-packages, frozen and
string code are not files of the tree and take no slot, a file is counted once, at most four, innermost first.
`listed_by` is, for each listed directory, the sorted union over the events of the INNERMOST of them: the repository
code that made the listing (the stdlib frames of glob/pathlib between it and the OS are not a file of the tree).
`listed_via` is the union over the events of all (up to four) files recorded: the lister and the code that called it,
for reading only. They differ on purpose: at 2b90242 `tests/v2` is listed by `aisef2/invariants/registry.py` alone
(`listed_by`, every kill file: `test_directories`, reached from every `tests/v2/**/__init__.py` through `arm`), while
`listed_via` also names those `__init__.py` files, the callers of `arm`; a rule on the whole stack could never say
"this listing is that function's". A listing with no file of the tree on its stack (the interpreter's own machinery
under --control own-walk, C code, `-c` or frozen code, a thread whose own frames are the stdlib's) is attributed to
["<native>"]: a name no consumer takes for a file. A child Python process that runs the hook is attributed by its own
stack; a listing by a child that does not run it is not recorded at all (it is not in `listed` either: limits).
`opened` and `listed` are unchanged by it; a consumer that does not know `listed_by` ignores it.

What it does. For each kill file of `--files` (default: every distinct file of `mutation.V21_TARGETS`):
  * a fresh copy of the runner's tree: `mutation._pristine` (the COPY parts of this checkout, no __pycache__, no live
    record) then `mutation._new_tree`, the runner's own helpers; a clean checkout is required (the record says "at
    HEAD"), and `--commit` must be HEAD;
  * the kill file alone, by the runner's own `mutation._run_file` (its argv — `unittest discover -s <dir> -t tests -p
    <file>` —, its environment allowlist, ProcessRange, its judgement, its leftovers settled and signalled only through
    validation/v2/cleanup_authority.py), with one addition to the environment: PYTHONPATH naming a directory of this
    run that holds a `sitecustomize.py`. That file turns bytecode writing off (the -B of the delta tool's text: every
    read is of a source, never a stale .pyc) and installs an audit hook taking `open`, `os.listdir`, `os.scandir`
    (and `sqlite3.connect`), and wraps `os.stat` / `os.lstat` (no audit event: a lookup of a path is a read of its
    existence). Every Python process that loads it — the test process, and each child Python process that inherits
    PYTHONPATH — appends to its own file under the run's scratch directory; the files are merged when the kill file
    ends. The run's tree, the hook and the events live under one temporary directory, removed at the end; nothing is
    written inside the repository except --out; nothing is signalled that this run did not start.

What it leaves out on purpose (each has a control, `--control own-walk`, to see it): directory listings and lookups
made by the interpreter's own machinery to FIND the code — the import system filling a path entry's cache
(`FileFinder._fill_cache`: it lists every sys.path directory, root included), and unittest's loader walking the start
directory under the runner's `discover` (the listing and an isfile/isdir of every sibling; never during a test).
Recorded, they would make every kill file "list the root" and so read every file. What they decide is only which file is
found by name, and every file the run then loads is opened (and recorded). The files the loader and the importer DO
read (package `__init__.py`, modules) are `open` events and stay.

Outcome. Each kill file's row carries `outcome` (PASS, FAIL, TIMEOUT, INFRA: the runner's judgement) and `seconds`.
A kill file that does not PASS — or never opened itself — is NOT put under `kill_files` (its partial reads would
"clear" files it never got to read: the consumer does not look at the outcome): it is recorded under `not_passed`
(outcome, seconds, what it read before, why), stays "not measured" for the consumer, the output says so (`complete` is
false, `note`) and the exit status is 1. So is a kill file that is not a file of the runner's tree, and the files not
reached when the runner stops on a leftover it cannot prove (RESIDUAL_OWNERSHIP_UNKNOWN: nothing more runs): both are
under `not_measured` with the reason. The other kill files of the record are each measured on a tree of their own and
stand.

Limits — what a read-set recorded here is not (also in the output, `limits`, with the measured counts):
  * Python processes only. A child that is not Python (git, sh, a shell command) reads files nobody sees. Counted per
    kill file: `children.other` (and `unobserved`).
  * A child Python process is seen only when it loads our sitecustomize: it must inherit PYTHONPATH and not run with
    -I, -E or -S. A test that builds its own environment (`env={...}` without PYTHONPATH, or `{**os.environ,
    "PYTHONPATH": X}`) starts a child this recorder cannot see; so does a child of such a child. Counted per kill
    file from the launch events of the hooked processes (subprocess.Popen, os.posix_spawn, os.spawn, os.system):
    `children.python_unhooked`; `children.hooked` is the number of child processes that did run the hook. A child
    launched by something that raises no such event (`_posixsubprocess` called directly) is not counted either way.
    Measured over the kill files of V21_TARGETS at 875c85e by grep of each file's own text (not its helpers):
    23 of 45 mention subprocess, Popen, ProcessRange, os.system/fork/exec/spawn or multiprocessing; 11 of those pass
    `env=`; 3 name PYTHONPATH (test_s2_kills, test_v21_continue_integrity, test_c2_cli_verdicts). Measured by the
    recorder at 180df1c on 5 of those 23 (continue_integrity, c2_cli_verdicts, bundle_tools, identity, s2_kills):
    4791 child launches, 672 of them Python, of which 337 (50%) unhooked; 4119 not Python (git); 358 child processes
    ran the hook. Four of the five start children it cannot see; only c2_cli_verdicts (0 started) has none. So a
    read of a child that those files start through a constructed environment, and every read of a git child, is NOT
    in their read-set, and a file only such a child reads is reported "not read" for them: a measured read-set is a
    lower bound for those kill files. The other 18 that mention subprocess are not measured here.
  * Not seen even in a hooked process: reads that raise no event and go through no wrapped call (a C library opening
    a file itself, `os.access`, `os.readlink`, `os.fwalk`/`dir_fd`/fd-relative calls, `DirEntry.stat`, a stat made by
    the import system through its private `posix.stat`, `from os import stat` bound before the hook), a stat or an
    open relative to a directory fd (`dir_fd`: the path alone says nothing; the stat is left out), and a path spelled
    through a symlink inside the tree (made relative lexically, `..` collapsed without resolving). Paths with a
    `__pycache__` part are left out: the import system's failed lookups of a cache the runner's tree does not have.
  * The kill file runs against the UNMUTATED tree. A mutant of a target may read what the original does not.
  * The environment differs from the runner's by PYTHONPATH (and `sys.path` with it) and `sys.dont_write_bytecode`:
    a test that asserts on either fails here and is recorded as not passed. A chained pre-existing `sitecustomize`
    still runs, after ours.
  * Measured on POSIX (macOS). Windows is not exercised.

Exit: 0 every kill file PASSed and was measured; 1 some did not (the record is written); 2 refused before anything ran
(a checkout that differs from HEAD inside mutation.COPY, --commit not HEAD, a path that is not relative, no git, the
runner could not start): nothing is written.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True   # the recorder never writes a .pyc into the repository it runs from
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import cleanup_authority as ca  # noqa: E402
from validation.v2 import mutation as M  # noqa: E402

TOOL = "validation/v21/read_set.py"
CONTROLS = ("no-stat", "no-children", "own-walk")
#: controls that make the output a diagnostic, not a record: they see LESS than the recorder does
UNDER = ("no-stat", "no-children")

#: The sitecustomize every hooked process runs. Never raises (an exception from an audit hook would abort the audited
#: call). One line per event, in this process's own file: `P pid ppid` (it ran the hook), `o|s|l <path>` (opened,
#: looked up, listed; absolute, normalised, \ and newline escaped), `C <event> <python> <hooked>` (it started a child).
HOOK = r'''import os, sys, _thread

sys.dont_write_bytecode = True
_EV, _STAT, _KIDS, _OWN, _ROOTS = @EVENTS@, @STAT@, @CHILDREN@, @OWN@, @ROOTS@
_HOOK = os.path.dirname(os.path.abspath(__file__))
_o, _w, _pid, _cwd = os.open, os.write, os.getpid, os.getcwd
_join, _norm, _isabs, _fspath, _fsdecode = os.path.join, os.path.normpath, os.path.isabs, os.fspath, os.fsdecode
_nc = os.path.normcase
_st, _tl = {"pid": None, "fd": None}, _thread._local()


def _emit(line):
    pid = _pid()
    if _st["pid"] != pid:
        fd = _o(_join(_EV, "%d.ev" % pid), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        _w(fd, b"P\t%d\t%d\n" % (pid, os.getppid()))
        _st["fd"], _st["pid"] = fd, pid
    _w(_st["fd"], line.encode("utf-8", "surrogateescape"))


def _where(p):
    if p is None:
        p = "."
    if isinstance(p, int):
        return None
    p = _fspath(p)
    if isinstance(p, bytes):
        p = _fsdecode(p)
    return _norm(p if _isabs(p) else _join(_cwd(), p)) if p else None


def _own(f):
    """The interpreter's own walk to find code: the import system filling a directory cache, or the unittest loader's
    walk of the start directory under `discover` (before runTests), `f` being the frame that made the call."""
    c = f.f_code
    if c.co_name == "_fill_cache" and "importlib" in c.co_filename:
        return True
    for _ in range(3):
        if f is None:
            return False
        c = f.f_code
        if c.co_name in ("_find_tests", "_find_test_path") and c.co_filename.endswith("loader.py"):
            names = set()
            while f is not None:
                names.add(f.f_code.co_name)
                f = f.f_back
            return "_do_discovery" in names and "runTests" not in names
        f = f.f_back
    return False


def _run(fn, *args):
    """fn(*args) unless this thread is already inside the hook (its own os.open raises `open`); never raises."""
    if getattr(_tl, "busy", False):
        return
    _tl.busy = True
    try:
        fn(*args)
    except Exception:
        pass
    finally:
        _tl.busy = False


def _callers(f):
    """The files of the tree on the stack from frame `f` outward, innermost first, distinct, at most 4: stdlib,
    site-packages, frozen and string code are not under the tree. None of them: `<native>`."""
    out = []
    try:
        while f is not None and len(out) < 4:
            n, f = f.f_code.co_filename, f.f_back
            w = None if n.startswith("<") else _where(n)
            if w and w not in out and any(_nc(w).startswith(r + os.sep) for r in _ROOTS):
                out.append(w)
    except Exception:   # a relative name and a cwd that is gone: what is not known is not discounted
        out.append("<native>")
    return out or ["<native>"]


def _esc(s):
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


def _note(kind, p):
    w = _where(p)
    if w is None:
        return
    f = None
    if kind != "o":
        f = sys._getframe(1)
        while f is not None and f.f_code.co_filename == _note.__code__.co_filename:   # the frame of the code that made the call
            f = f.f_back
        if f is not None and not _OWN and _own(f):
            return
    line = kind + "\t" + _esc(w)
    if kind == "l":   # who listed it: the files of the tree on this thread's stack
        line += "".join("\t" + _esc(c) for c in _callers(f))
    _emit(line + "\n")


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
    _emit("C\t%s\t%d\t%d\n" % (event, py, hooked))


def _dispatch(event, a):
    if event in ("open", "sqlite3.connect"):
        _note("o", a[0])
    elif event in ("os.listdir", "os.scandir"):
        _note("l", a[0])
    elif event in ("subprocess.Popen", "os.posix_spawn", "os.spawn", "os.system"):
        _launch(event, a)


def _audit(event, a):
    _run(_dispatch, event, a)


if _STAT:
    def _wrap(f):
        def g(path, *a, **k):
            if k.get("dir_fd") is None:   # relative to an fd: the path alone says nothing
                _run(_note, "s", path)
            return f(path, *a, **k)
        return g
    for _n in ("stat", "lstat"):
        _old, _new = getattr(os, _n), _wrap(getattr(os, _n))
        setattr(os, _n, _new)
        for _s in (os.supports_dir_fd, os.supports_fd, os.supports_follow_symlinks, os.supports_effective_ids):
            if _old in _s:
                _s.add(_new)
sys.addaudithook(_audit)
if not _KIDS:   # control: children do not inherit the hook
    os.environ.pop("PYTHONPATH", None)
try:   # a sitecustomize this one shadows still runs
    from importlib.machinery import PathFinder as _pf
    _spec = _pf.find_spec("sitecustomize", [p for p in sys.path if _norm(os.path.abspath(p or ".")) != _HOOK])
    if _spec is not None and _spec.loader is not None:
        import importlib.util as _u
        _spec.loader.exec_module(_u.module_from_spec(_spec))
except Exception:
    pass
'''


def _roots(tree: pathlib.Path) -> tuple[str, ...]:
    """The tree under both its spellings, normalised: what a path of the tree starts with (merge and the hook)."""
    return tuple(dict.fromkeys(os.path.normcase(os.path.normpath(str(p))) for p in (tree, tree.resolve())))


def hook_source(events: pathlib.Path, tree: pathlib.Path, controls=()) -> str:
    return (HOOK.replace("@EVENTS@", repr(str(events))).replace("@STAT@", repr("no-stat" not in controls))
            .replace("@CHILDREN@", repr("no-children" not in controls)).replace("@OWN@", repr("own-walk" in controls))
            .replace("@ROOTS@", repr(_roots(tree))))


def _rel(path: str, roots: tuple[str, ...]) -> str | None:
    """`path` relative to the tree ("." the root) under any of its spellings; None outside it."""
    n = os.path.normcase(path)
    for r in roots:
        if n == r:
            return "."
        if n.startswith(r + os.sep):
            return path[len(r) + 1:].replace(os.sep, "/")
    return None


_ESC = re.compile(r"\\([\\nt])")
_UNESC = {"\\": "\\", "n": "\n", "t": "\t"}
NATIVE = "<native>"   # listed_by: a listing with no file of the tree on its stack


def _unesc(s: str) -> str:
    return _ESC.sub(lambda m: _UNESC[m[1]], s)


def merge(events: pathlib.Path, tree: pathlib.Path) -> dict:
    """What every process of one kill-file run wrote under `events`: opened, listed (and by which files of the tree:
    the innermost one of each listing, `listed_by`, and up to four of its stack, `listed_via`), children counts."""
    roots = _roots(tree)
    opened, listed, chains = set(), set(), {}
    kids = {"started": 0, "python": 0, "python_unhooked": 0, "other": 0}
    files = sorted(events.glob("*.ev"))
    for f in files:
        for line in f.read_bytes().decode("utf-8", "surrogateescape").split("\n"):
            kind, _, rest = line.partition("\t")
            if kind in ("o", "s", "l"):
                path, *callers = rest.split("\t") if kind == "l" else [rest]
                rel = _rel(_unesc(path), roots)
                if rel is not None and "__pycache__" not in rel.split("/"):   # a cache lookup, never a file of the tree
                    (listed if kind == "l" else opened).add(rel)
                    if kind == "l":
                        by = [r for c in callers if (r := _rel(_unesc(c), roots)) and "__pycache__" not in r.split("/")]
                        chains.setdefault(rel, set()).add(tuple(by) or (NATIVE,))   # no caller recorded: not discounted
            elif kind == "C":
                _, py, hooked = rest.split("\t")
                kids["started"] += 1
                kids["python"] += int(py)
                kids["python_unhooked"] += int(py) - int(hooked)
                kids["other"] += 1 - int(py)
    # `hooked`: processes that ran the hook, less the kill file's own; `unobserved`: started and not seen
    kids["hooked"] = max(len(files) - 1, 0)
    kids["unobserved"] = kids["python_unhooked"] + kids["other"]
    return {"opened": sorted(opened), "listed": sorted(listed), "children": kids,
            "listed_by": {d: sorted({c[0] for c in cs}) for d, cs in sorted(chains.items())},
            "listed_via": {d: sorted({f for c in cs for f in c}) for d, cs in sorted(chains.items())}}


def record(root, files, controls=(), progress=None) -> dict:
    """The read-set document (without `commit`) of kill files `files` (paths relative to `root`)."""
    root = pathlib.Path(root).resolve()
    kill_files, not_passed, not_measured = {}, {}, {}
    began = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aisef-readset-", ignore_cleanup_errors=True) as t:
        scratch = pathlib.Path(t)
        pristine, digest = M._pristine(root, scratch / "pristine")
        tg = M._Target(None, scratch, ca.establish(scratch), "readset-" + M._worker(root), tests=list(files))
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
                tree = tg.tree   # the run's, even when the runner rebuilds it after the run: the hook names this one
                (hook / "sitecustomize.py").write_text(hook_source(events, tree, controls), encoding="utf-8")
                M._env = lambda run, token, h=hook: {**real_env(run, token), "PYTHONPATH": str(h)}
                rows: list[dict] = []
                try:
                    row = M._run_file(tg, rel, rows, failfast=False, role="readset")
                except M._Stop as e:
                    row, stopped = rows[-1] if rows else {}, str(e)
                    row.setdefault("outcome", "INFRA")
                    row["why"] = str(e)
                finally:
                    M._env = real_env
                got = merge(events, tree)
                entry = {"opened": got["opened"], "listed": got["listed"], "listed_by": got["listed_by"],
                         "listed_via": got["listed_via"], "outcome": row.get("outcome"), "seconds": row.get("seconds"),
                         "children": got["children"]}
                for k in ("why", "leaked", "residual"):
                    if row.get(k):
                        entry[k] = row[k]
                if entry["outcome"] == "PASS" and rel in entry["opened"]:
                    kill_files[rel] = entry
                else:
                    if entry["outcome"] == "PASS":
                        entry["why"] = "its own path is not among the files it opened: nothing measured"
                    not_passed[rel] = entry
                if progress:
                    progress(i, len(files), rel, entry)
                shutil.rmtree(events, ignore_errors=True)
        finally:
            M._env = real_env
            if tg.holder is not None:
                tg.holder.cleanup()
    every = {**kill_files, **not_passed}
    kids = {k: sum(e["children"][k] for e in every.values()) for k in ("started", "python", "python_unhooked", "other", "hooked")}
    complete = not not_passed and not not_measured and len(kill_files) == len(files)
    doc = {"tool": TOOL, "tree_sha256": digest, "python": sys.version.split()[0], "platform": sys.platform,
           "controls": list(controls), "complete": complete, "seconds": round(time.monotonic() - began, 2),
           "kill_files": kill_files}
    if not_passed:
        doc["not_passed"] = not_passed
    if not_measured:
        doc["not_measured"] = not_measured
    if not complete:
        doc["note"] = (f"{len(not_passed)} kill file(s) did not PASS or never opened themselves and {len(not_measured)} were "
                       f"not run: none of them is under kill_files, so none of them is measured and none clears anything "
                       f"(a partial read-set would clear what the file never got to read)")
    if set(controls) & set(UNDER):
        doc["note"] = f"a control run ({', '.join(controls)}): sees less than the recorder; not a record"
    doc["limits"] = {
        "measured_children": {**kids, "kill_files_with_unobserved_children": sorted(
            f for f, e in every.items() if e["children"]["unobserved"])},
        "text": ["Python processes only: a non-Python child (git, sh) reads files nobody sees (children.other)",
                 "a child Python process is seen only when it inherits PYTHONPATH and runs without -I, -E, -S: a test "
                 "that builds its own environment starts a child that is not hooked (children.python_unhooked), and "
                 "so does a child of one",
                 "not seen: reads with no event and no wrapped call (C libraries, os.access, os.readlink, os.fwalk, "
                 "dir_fd, DirEntry.stat, the import system's private stat), symlinks inside the tree",
                 "listed_by names the innermost file of the tree on the stack of each listing (listed_via: up to four): "
                 "what that file's function does with the listing is not recorded, and a listing with no file of the "
                 "tree on its stack is '<native>'; a directory listed by a child that is not hooked is not in `listed`",
                 "the unmutated tree: a mutant may read what the original does not",
                 "the interpreter's own walk to find code is left out (--control own-walk records it)"]}
    return doc


def refuse(why: str):
    print(f"refused: {why}", file=sys.stderr)
    raise SystemExit(2)


def _git(root: pathlib.Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        refuse(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def head_of(root: pathlib.Path, commit: str | None) -> str:
    """HEAD's full sha, when `commit` (if given) is HEAD and the COPY parts of the checkout are HEAD's bytes."""
    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if commit and _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}") != head:
        refuse(f"--commit {commit} is not HEAD ({head}): the tree measured is the checkout's")
    live = {os.path.normpath(p) for p in M.RECORDS.values()}   # _pristine leaves them out
    paths = [p for p in M.COPY if (root / p).exists()]
    status = _git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths).splitlines()
    dirty = [ln.strip() for ln in status
             if os.path.normpath(ln.strip().split(None, 1)[1].split(" -> ")[-1].strip('"')) not in live]
    if dirty:
        refuse(f"the checkout differs from HEAD {head[:12]} inside mutation.COPY ({len(dirty)} path(s), first: "
               f"{dirty[0]!r}): a read-set says 'at HEAD'")
    return head


def kill_files() -> list[str]:
    return sorted({f for ks in M.V21_TARGETS.values() for f in ks} - set(M.NOT_KILL_FILES))


def main(argv: list[str] | None = None, root: pathlib.Path = ROOT) -> int:
    ap = argparse.ArgumentParser(prog="read_set.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--commit", help="the full sha the record is of; must be HEAD (default: HEAD)")
    ap.add_argument("--files", nargs="+", metavar="F", help="kill files (default: every file of V21_TARGETS)")
    ap.add_argument("--control", action="append", choices=CONTROLS, default=[],
                    help="switch a channel to see what it contributes: no-stat, no-children (diagnostic, not a "
                         "record), own-walk (record the interpreter's own walk to find code)")
    a = ap.parse_args(argv)
    files = list(dict.fromkeys(a.files or kill_files()))
    if bad := [f for f in files if f.startswith("/") or "\\" in f or ".." in f.split("/")]:
        refuse(f"not a path relative to the root with '/': {bad[0]!r}")
    head = head_of(root, a.commit)

    def progress(i, n, rel, e):
        k = e["children"]
        print(f"[{i + 1}/{n}] {e['outcome']:7s} {e['seconds']}s opened={len(e['opened'])} listed={len(e['listed'])} "
              f"children={k['started']} (hooked {k['hooked']}, unobserved {k['unobserved']}) {rel}", file=sys.stderr, flush=True)
    try:
        doc = record(root, files, a.control, progress)
    except (ca.Unproven, OSError) as e:   # establish / pristine failed before any file
        refuse(f"the runner stopped before any kill file: {e}")
    out = {"commit": head, **doc} if not set(a.control) & set(UNDER) else doc
    a.out.write_text(json.dumps(out, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{len(doc['kill_files'])}/{len(files)} kill files measured in {doc['seconds']}s -> {a.out}"
          + (f"\n{doc['note']}" if doc.get("note") else ""), file=sys.stderr)
    return 0 if doc["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
