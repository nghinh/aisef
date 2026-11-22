"""F5 recorder (AISEF v2.3 W1a): one observed, unmutated run of ONE kill file, and its observation record O(F).

    python3 -P validation/v23/observe.py --kill-file F [--kill-file F2 ...] --out DIR [--backend auto|strace|audit]
    python3 -P validation/v23/observe.py --verify DIR

Owner ruling 2026-11-21: approved for development, NOT approved as a VERIFIED_REUSE authority. Nothing here is read by
validation/v2/mutation.py or by any release gate; validation/v23/impact.py reads an observation only as an input
(`--observations DIR`), and an observed read set alone never yields reuse there (docs/v2.3/amendments/A3-OBSERVE-
SOUNDNESS.md states what the record proves and what it cannot).

The run. HEAD's own committed runner (validation/v2/mutation.py of the HEAD commit, loaded by v21_snapshot_delta.Rev)
makes the tree with its `_pristine` (so `tree_sha256` is that function's digest) and `_new_tree`, and runs the kill file
once with its `_run_file`: its argv (`unittest discover -v -s <dir> -t tests -p <file>`), its environment allowlist,
ProcessRange, its judgement, its leftovers settled through cleanup_authority only. Two additions to the environment:
PYTHONPATH naming a directory outside the tree that holds a `sitecustomize.py` (HOOK) and the marker `AISEF_OBSERVE`
(a nonce baked into that hook). A checkout that differs from HEAD inside the runner's COPY is refused.

Backends.
  * strace (Linux; `auto` picks it when strace is on PATH): the kill-test process tree runs under `strace -f -ff -y`
    (forks, vforks, clone/clone3 followed; one trace file per task) tracing %file, %process, getdents(64) and fchdir.
    The hook still runs in every Python process it reaches: it tags reads (`load`: the import system's source read;
    `data`: every other) and tells the interpreter's own walk to find code from a test's listing. The trace is the
    ground truth for completeness: an access the trace shows and the hook does not account for in the same process is
    a data read (or a listing by `<native>`); a process with no hook record is observed for data only.
  * audit (any POSIX host; the only one on darwin): the hook alone — audit events (open, os.listdir/scandir, exec,
    compile, import, subprocess/exec/spawn/fork events, path-changing os/shutil events) plus wrappers of os.stat,
    os.lstat, os.access, os.readlink and os.open (dir_fd). A non-Python child, a Python child that will not load the
    hook (env without PYTHONPATH or the marker, -I/-E/-S), a hooked record no launch accounts for, a launch with no
    record, a hooked process that did not reach normal exit, and a listing through an fd are each an incompleteness.
    Absence of an event is never proof of absence: an incomplete record makes impact.py's R1 fire.

Output. DIR/<kill file with / as __>/ holds the witness — manifest.json (provenance), log.txt (the kill file's output),
hook/*.ev, strace/tr.* — and observation.json: `derive()` of the witness (a pure function of those files) plus the
sha256 of every witness file. `verify()` re-hashes the witness and re-derives the record: a missing or changed witness
file is an incompleteness (R1), a record that is not what its witness says is refused (R0). Raw traces hold host paths
and stay in scratch; observation.json holds tree-relative paths, digests and versions only.
"""

from __future__ import annotations

import argparse
import ast
import collections
import contextlib
import hashlib
import json
import os
import pathlib
import platform
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import v21_snapshot_delta as SD  # noqa: E402  (Rev: the commit's own runner)
from validation.v21 import read_set as RS  # noqa: E402  (_roots, _rel, _unesc, NATIVE)

TOOL = "validation/v23/observe.py"
FORMAT = "aisef-v23-observation/1"
MARK = "AISEF_OBSERVE"
RECORD = "observation.json"
STRACE_EVENTS = "%file,%process,?getdents,getdents64,fchdir,?io_uring_setup,?pidfd_getfd,?process_vm_readv"
#: calls through which a run can read a file outside the traced channel: any occurrence is an incompleteness
_UNSEEN = {"io_uring_setup", "pidfd_getfd", "process_vm_readv"}
#: a path through another process's (or its own) cwd, root or fd: a name of the tree no rule can map
_ALIAS = re.compile(r"^/proc/[^/]+/(?:cwd|root)(?:/|$)|^/(?:proc/[^/]+|dev)/fd/\d+/")

#: The sitecustomize of every observed Python process. Never raises out of a hook (an exception from an audit hook would
#: abort the audited call): what it fails to write is counted (`L`/`E` lines). One line per event in the process's own
#: file `<pid>-<random>.ev`: `S|F pid ppid argv` (an interpreter start, argv = repr of sys.orig_argv[1:] | a forked
#: child, argv `-`), `o load|data <path>`, `s <path>`
#: (a lookup; `w <path>`: one made by the interpreter's walk to find code), `l own|run <path> <callers...>` (a listing;
#: `own`: that walk — the import system filling a directory cache, unittest discovering the start directory), `m <path>` (code
#: of that file executed or compiled), `C <event> <python> <hooked> <argv>` (a launch), `d <event>` (an fd-relative
#: access), `L n` (n events lost before this line), `E n` (normal exit, n lost at the end). Paths absolute, \ \t \n
#: escaped. `a <path>`: a new name (symlink, hard link) made for that path.
HOOK = r'''import os, sys, _thread
_EV, _NONCE, _ROOTS, _MARK = @EVENTS@, @NONCE@, @ROOTS@, @MARK@
_HOOK = os.path.dirname(os.path.abspath(__file__))
_o, _w, _pid, _ppid, _cwd, _rand = os.open, os.write, os.getpid, os.getppid, os.getcwd, os.urandom
_join, _norm, _isabs, _fspath, _fsdecode, _nc, _dn = (os.path.join, os.path.normpath, os.path.isabs, os.fspath,
                                                     os.fsdecode, os.path.normcase, os.path.dirname)
_st, _tl = {"fd": None, "lost": 0}, _thread._local()
_LAUNCH = ("subprocess.Popen", "_posixsubprocess.fork_exec", "os.posix_spawn", "os.spawn", "os.system", "os.exec",
           "os.fork", "os.forkpty")
_HELPERS = ("genericpath", "posixpath", "ntpath")   # stdlib path helpers between a walk and its stat (frozen or not)
_DIRFD = {"os.remove": (1,), "os.rmdir": (1,), "os.mkdir": (2,), "os.rename": (2, 3), "os.replace": (2, 3),
          "os.link": (2, 3), "os.symlink": (2,), "os.chmod": (2,), "os.chown": (3,), "os.utime": (3,)}
_PATHS = set(_DIRFD) | {"os.truncate", "os.chflags", "os.lchflags", "os.listxattr", "os.getxattr", "os.setxattr",
                        "os.removexattr", "shutil.copyfile", "shutil.copymode", "shutil.copystat", "shutil.copytree",
                        "shutil.rmtree", "shutil.move", "shutil.chown", "os.walk", "os.fwalk", "glob.glob",
                        "glob.glob/2", "pathlib.Path.glob", "pathlib.Path.rglob", "os.mkfifo", "os.mknod"}


def _esc(s):
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


def _raw(line):
    try:
        if _st["lost"]:
            _w(_st["fd"], b"L\t%d\n" % _st["lost"])
            _st["lost"] = 0
        _w(_st["fd"], line.encode("utf-8", "surrogateescape"))
    except Exception:
        _st["lost"] += 1


def _start(kind):
    _tl.busy = True   # the open of our own file is not an event of the process (a forked child's would land in its
    try:              # parent's file: the fd is the parent's until this returns)
        _st["fd"] = _o(_join(_EV, "%d-%s.ev" % (_pid(), _rand(6).hex())),
                       os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        _st["lost"] = 0
        argv = repr([_fsdecode(_fspath(x)) for x in sys.orig_argv[1:]]) if kind == "S" else "-"
        _raw("%s\t%d\t%d\t%s\n" % (kind, _pid(), _ppid(), _esc(argv)))
    except Exception:   # no file of its own: every event of this process is lost, and its record is missing
        _st["fd"], _st["lost"] = None, _st["lost"] + 1
    finally:
        _tl.busy = False


def _where(p):
    if p is None:
        p = "."
    p = _fspath(p)
    if isinstance(p, bytes):
        p = _fsdecode(p)
    return _norm(p if _isabs(p) else _join(_cwd(), p)) if p else None


def _path(kind, p):
    if isinstance(p, int):
        return
    w = _where(p)
    if w is not None:
        _raw(kind + "\t" + _esc(w) + "\n")


def _caller():
    f = sys._getframe(1)
    while f is not None and f.f_code.co_filename == _caller.__code__.co_filename:
        f = f.f_back
    return f


def _loading(f):
    """The import system reading a module's source: FileLoader.get_data called by SourceLoader.get_code."""
    return (f is not None and f.f_code.co_name == "get_data" and "importlib" in f.f_code.co_filename
            and f.f_back is not None and f.f_back.f_code.co_name == "get_code")


def _intree(n):
    w = None if n.startswith("<") else _where(n)
    return bool(w) and any(_nc(w).startswith(r + os.sep) for r in _ROOTS)


def _own(f):
    """The interpreter's own walk to find code: the import system filling a directory cache, or the unittest loader's
    walk of the start directory under `discover` (before runTests) — the call made by that stdlib code itself or
    through stdlib path helpers only. Any other frame between them (tree code: a load_tests, a test) makes it a run."""
    if f is None:
        return False
    c = f.f_code
    if c.co_name == "_fill_cache" and "importlib" in c.co_filename and not _intree(c.co_filename):
        return True
    for _ in range(3):
        if f is None:
            return False
        c = f.f_code
        if (c.co_name in ("_find_tests", "_find_test_path") and c.co_filename.endswith("loader.py")
                and not _intree(c.co_filename)):
            names = set()
            while f is not None:
                names.add(f.f_code.co_name)
                f = f.f_back
            return "_do_discovery" in names and "runTests" not in names
        n = c.co_filename
        if (n[8:-1] if n.startswith("<frozen ") else os.path.basename(n).removesuffix(".py")) not in _HELPERS \
                or _intree(n):
            return False
        f = f.f_back
    return False


def _callers(f):
    out = []
    while f is not None and len(out) < 4:
        n, f = f.f_code.co_filename, f.f_back
        w = None if n.startswith("<") else _where(n)
        if w and w not in out and any(_nc(w).startswith(r + os.sep) for r in _ROOTS):
            out.append(w)
    return out or ["<native>"]


def _isolated(argv):
    """Whether the interpreter options before the program (-c, -m, a script) hold -I, -E or -S. -W and -X take a
    value (attached, or the next argument), as does --check-hash-based-pycs."""
    args = [_fsdecode(_fspath(x)) for x in list(argv)[1:]]
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if a in ("-", "--") or not a.startswith("-"):
            return False
        if a.startswith("--"):
            i += a == "--check-hash-based-pycs"
            continue
        for j, ch in enumerate(a[1:], 1):
            if ch in "IES":
                return True
            if ch in "cm":
                return False
            if ch in "WX":
                i += j == len(a) - 1
                break
    return False


def _has_hook(env):
    env = os.environ if env is None else env
    got = {_fsdecode(k): _fsdecode(v) for k, v in env.items()}
    return (got.get(_MARK) == _NONCE
            and _HOOK in [_norm(x) for x in got.get("PYTHONPATH", "").split(os.pathsep) if x])


def _of_popen(name):
    """The os.posix_spawn or _posixsubprocess.fork_exec subprocess.Popen makes itself (method `name`) for a launch it
    already reported (one child, two events)."""
    f = _caller()
    fn = getattr(getattr(sys.modules.get("subprocess"), "Popen", None), name, None)
    return f is not None and fn is not None and f.f_code is getattr(fn, "__code__", None)


def _launch(event, a):
    if event == "_posixsubprocess.fork_exec" and getattr(_tl, "fe", False):
        _tl.fe = False   # 3.14+: the interpreter's own event of the launch _fork_exec already reported
        return
    if (event == "os.posix_spawn" and _of_popen("_posix_spawn")) or (
            event == "_posixsubprocess.fork_exec" and _of_popen("_execute_child")):
        return
    if event in ("os.fork", "os.forkpty"):
        _raw("C\t%s\t1\t1\t-\n" % event)
        return
    if event == "os.system":
        _raw("C\tos.system\t0\t0\t%s\n" % _esc(repr(a[0])))
        return
    if event == "subprocess.Popen":
        exe, argv, env = a[0], a[1], a[3]
        if a[2] is not None:
            _path("s", a[2])   # the child's cwd: a lookup of that directory
    elif event == "_posixsubprocess.fork_exec":   # (executable list, argv, env)
        exe, argv, env = (a[0][0] if a[0] else None), a[1], a[2]
    elif event == "os.spawn":
        exe, argv, env = a[1], a[2], a[3]
    else:   # os.posix_spawn, os.exec: path, argv, env
        exe, argv, env = a[0], a[1], a[2]
    if isinstance(argv, (str, bytes)):
        argv = [argv]
    e = _fsdecode(_fspath(exe)) if exe is not None else ""
    py = int(os.path.basename(e).lower().startswith("python") or e == sys.executable)
    hooked = int(bool(py and isinstance(argv, (list, tuple)) and _has_hook(env) and not _isolated(argv)))
    _raw("C\t%s\t%d\t%d\t%s\n" % (event, py, hooked, _esc(repr([_fsdecode(_fspath(x)) for x in argv]))))


def _dispatch(event, a):
    if event == "open":
        _path("o\t" + ("load" if _loading(_caller()) else "data"), a[0])
    elif event in ("os.listdir", "os.scandir"):
        p = a[0] if a else None
        if isinstance(p, int):
            _raw("d\t%s\n" % event)
            return
        f = _caller()
        w = _where(p)
        if w is not None:
            _raw("l\t%s\t%s\t%s\n" % ("own" if _own(f) else "run", _esc(w), "\t".join(_esc(c) for c in _callers(f))))
    elif event == "exec":
        n = getattr(a[0], "co_filename", None)
        if isinstance(n, str) and n and not n.startswith("<"):
            _path("m", n)
    elif event in ("compile", "import"):
        n = a[1] if len(a) > 1 else None
        if isinstance(n, (str, bytes)) and n and not _fsdecode(n).startswith("<"):
            _path("m", n)
    elif event == "os.chdir":
        _path("s", a[0])
    elif event in _LAUNCH:
        _launch(event, a)
    elif event == "sqlite3.connect":
        _path("o\tdata", a[0])
    elif event in _PATHS:
        if event in ("os.symlink", "os.link") and len(a) > 1 and not isinstance(a[0], int):
            src, dst = _fsdecode(_fspath(a[0])), (None if isinstance(a[1], int) else _where(a[1]))
            rel = event == "os.symlink" and not _isabs(src) and dst is not None
            _raw("a\t%s\n" % _esc(_norm(_join(_dn(dst), src)) if rel else _where(src)))   # a new name for it
        for i, x in enumerate(a):
            if i in _DIRFD.get(event, ()) and isinstance(x, int) and x >= 0:   # -1: no dir_fd given
                _raw("d\t%s\n" % event)
            elif isinstance(x, (str, bytes, os.PathLike)):
                _path("s", x)


def _audit(event, a):
    if getattr(_tl, "busy", False):
        return
    _tl.busy = True
    try:
        _dispatch(event, a)
    except Exception:
        _st["lost"] += 1
    finally:
        _tl.busy = False


def _wrap(f, kind):
    def g(path, *a, **k):
        if not getattr(_tl, "busy", False):
            _tl.busy = True
            try:
                if k.get("dir_fd") is not None:
                    _raw("d\t%s\n" % f.__name__)
                elif kind == "s":
                    _path("w" if _own(_caller()) else "s", path)
                elif kind == "p":   # posix_spawn: what its file actions open, the child reads
                    for x in k.get("file_actions") or ():
                        if x and x[0] == getattr(os, "POSIX_SPAWN_OPEN", None):
                            _path("o\tdata", x[2])
            except Exception:
                _st["lost"] += 1
            finally:
                _tl.busy = False
        return f(path, *a, **k)
    return g


def _fork_exec(f):
    """_posixsubprocess.fork_exec: CPython raises its audit event only from 3.14, so a launch by it alone
    (multiprocessing's spawnv_passfds) is reported here, on every version; the interpreter's own event, raised inside
    the call, is then the same launch and ignored (once). Unparsable arguments: a launch of an unknown program."""
    def g(*a, **k):
        _audit("_posixsubprocess.fork_exec", (a[1], a[0], a[5]) if len(a) > 5 else ((), (), None))
        _tl.fe = True
        try:
            return f(*a, **k)
        finally:
            _tl.fe = False
    return g


def _exit():
    if _st["fd"] is not None:
        _raw("E\t%d\n" % _st["lost"])


if os.environ.get(_MARK) == _NONCE:
    _start("S")
    os.register_at_fork(after_in_child=lambda: _start("F"))
    import atexit
    atexit.register(_exit)
    for _n, _k in (("stat", "s"), ("lstat", "s"), ("access", "s"), ("readlink", "s"), ("statvfs", "s"),
                   ("pathconf", "s"), ("open", "d"), ("posix_spawn", "p"), ("posix_spawnp", "p")):
        _old = getattr(os, _n, None)
        if _old is None:
            continue
        _new = _wrap(_old, _k)
        setattr(os, _n, _new)
        for _s in (os.supports_dir_fd, os.supports_fd, os.supports_follow_symlinks, os.supports_effective_ids):
            if _old in _s:
                _s.add(_new)
    try:
        import _posixsubprocess
        _posixsubprocess.fork_exec = _fork_exec(_posixsubprocess.fork_exec)
    except ImportError:   # no POSIX fork_exec on this host
        pass
    sys.addaudithook(_audit)
try:   # a sitecustomize this one shadows still runs
    from importlib.machinery import PathFinder as _pf
    _spec = _pf.find_spec("sitecustomize", [p for p in sys.path if _norm(os.path.abspath(p or ".")) != _HOOK])
    if _spec is not None and _spec.loader is not None:
        import importlib.util as _u
        _spec.loader.exec_module(_u.module_from_spec(_spec))
except Exception:
    pass
'''


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def own_sha256() -> str:
    """sha256 of this file's bytes: the recorder (and parser) a record names."""
    return _sha(pathlib.Path(__file__).read_bytes())


SITE = "sitecustomize.py"   # the witness's copy of the hook every observed process ran


def hook_source(events: pathlib.Path, roots, nonce: str) -> str:
    """The hook for one run: its events directory, the tree's spellings (`RS._roots(tree)`) and the nonce."""
    return (HOOK.replace("@EVENTS@", repr(str(events))).replace("@NONCE@", repr(nonce))
            .replace("@ROOTS@", repr(tuple(roots))).replace("@MARK@", repr(MARK)))


def identity() -> dict:
    """The host as a platform and a toolchain: OS family/flavor, kernel, arch, python. No host name, no user."""
    sp = sys.platform
    return {"platform": {"family": "windows" if os.name == "nt" else "posix",
                         "flavor": "darwin" if sp == "darwin" else "linux" if sp.startswith("linux") else None,
                         "sys_platform": sp, "release": platform.release(), "machine": platform.machine(),
                         "kernel": platform.version()},
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "toolchain": {"implementation": sys.implementation.name, "version": platform.python_version()}}


def _version(argv: list[str]) -> str | None:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or r.stderr).splitlines()[0].strip() if r.returncode == 0 and (r.stdout or r.stderr) else None


# ------------------------------------------------------------------------------------------------- parsers


def _hook(d: pathlib.Path) -> tuple[list[dict], int]:
    """Every hooked process record under `d` and the number of lines that are not the hook's grammar."""
    procs, bad = [], 0
    for f in sorted(d.glob("*.ev")) if d.is_dir() else ():
        lines = f.read_bytes().decode("utf-8", "surrogateescape").split("\n")
        if lines[-1] == "":
            lines.pop()
        else:
            bad += 1   # the last line has no newline: cut short
            lines.pop()
        head = lines[0].split("\t") if lines else []
        if len(head) not in (3, 4) or head[0] not in ("S", "F") or not (head[1].isdigit() and head[2].isdigit()):
            bad += max(len(lines), 1)   # not a process record: nothing in it can be attributed
            continue
        p = {"kind": head[0], "pid": int(head[1]), "ppid": int(head[2]), "o": collections.Counter(),
             "s": collections.Counter(), "w": collections.Counter(), "l": [], "m": set(), "C": [], "lost": 0, "fd": 0,
             "ended": False, "a": [], "argv": RS._unesc(head[3]) if len(head) == 4 and head[0] == "S" else None}
        for line in lines[1:]:
            k, _, rest = line.partition("\t")
            a = rest.split("\t")
            if k == "o" and len(a) == 2 and a[0] in ("load", "data"):
                p["o"][a[0], RS._unesc(a[1])] += 1
            elif k == "s" and len(a) == 1 and a[0]:
                p["s"][RS._unesc(a[0])] += 1
            elif k == "w" and len(a) == 1 and a[0]:
                p["w"][RS._unesc(a[0])] += 1
            elif k == "l" and len(a) >= 3 and a[0] in ("own", "run"):
                p["l"].append((a[0] == "own", RS._unesc(a[1]), [RS._unesc(c) for c in a[2:]]))
            elif k == "m" and len(a) == 1 and a[0]:
                p["m"].add(RS._unesc(a[0]))
            elif k == "C" and len(a) == 4 and a[1] in ("0", "1") and a[2] in ("0", "1"):
                p["C"].append((a[0], int(a[1]), int(a[2]), RS._unesc(a[3])))
            elif k in ("L", "E") and len(a) == 1 and a[0].isdigit():
                p["lost"] += int(a[0])
                p["ended"] = p["ended"] or k == "E"
            elif k == "d" and len(a) == 1:
                p["fd"] += 1
            elif k == "a" and len(a) == 1 and a[0]:
                p["a"].append(RS._unesc(a[0]))
            else:
                bad += 1
        procs.append(p)
    return procs, bad


_SC = re.compile(r"^(?P<name>[a-z_0-9]+)\((?P<args>.*)\)\s+=\s+(?P<ret>-?\d+|\?|0x[0-9a-fA-F]+)(?P<rest>.*)$")
_STR = re.compile(r'(?:(?P<dfd>AT_FDCWD|-?\d+)(?:<(?P<dp>(?:[^>\\]|\\.)*)>)?,\s*)?"(?P<s>(?:[^"\\]|\\.)*)"(?P<cut>\.\.\.)?')
_FDARG = re.compile(r"^(?P<fd>-?\d+)<(?P<p>(?:[^>\\]|\\.)*)>")
_RETFD = re.compile(r"^<(?P<p>(?:[^>\\]|\\.)*)>")
_OPEN = {"open", "openat", "openat2", "creat"}
_EXEC = {"execve", "execveat"}
_LIST = {"getdents", "getdents64"}
_CLONE = {"clone", "clone3", "fork", "vfork"}
_ESC1 = {"n": b"\n", "t": b"\t", "r": b"\r", "v": b"\v", "f": b"\f", "a": b"\a", "b": b"\b", "e": b"\x1b"}


def _c(s: str) -> str:
    """A C string as strace prints it, decoded (\\ooo, \\xhh and the named escapes)."""
    out, i = bytearray(), 0
    while i < len(s):
        if s[i] != "\\" or i + 1 == len(s):
            out += s[i].encode("utf-8", "surrogateescape")
            i += 1
            continue
        n = s[i + 1]
        if n == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", s[i + 2:i + 4]):
            out.append(int(s[i + 2:i + 4], 16))
            i += 4
        elif n in "01234567":
            m = re.match(r"[0-7]{1,3}", s[i + 1:])
            out.append(int(m[0], 8) & 0xFF)
            i += 1 + len(m[0])
        else:
            out += _ESC1.get(n, n.encode("utf-8", "surrogateescape"))
            i += 2
    return out.decode("utf-8", "surrogateescape")


def parse_strace(lines: list[str]) -> dict:
    """One task's trace file (`strace -f -ff -y`): its events [(kind, dfd, dirpath, string, reached, segment)] or
    listings, the tasks it created, the cwds it named, the new names it made for paths (`alias`: symlink/link), how
    many images it exec'd (a segment is the part of the trace one image ran: it ends at each successful exec), whether
    it ended (`+++`), and what could not be read (unparsed lines, cut strings, an fd with no decoded path, a call
    outside the traced channel)."""
    t = {"ev": [], "created": [], "cwds": set(), "end": False, "bad": 0, "cut": 0, "nofd": 0, "dirs": set(),
         "alias": [], "execs": 0, "unseen": 0}
    pending, active, seg = None, {}, 0
    for line in lines:
        if line.endswith(" <unfinished ...>"):
            pending = line[: -len(" <unfinished ...>")]
            continue
        if line.startswith("<... ") and " resumed>" in line:
            if pending is None:
                t["bad"] += 1
                continue
            line, pending = pending + line.split(" resumed>", 1)[1], None
        if line.startswith("+++ ") and line.endswith(" +++"):
            t["end"] = True
            continue
        if line.startswith("--- ") and line.endswith(" ---") or not line:
            continue
        m = _SC.match(line)
        if not m:
            t["bad"] += 1
            continue
        name, args, ret, rest = m["name"], m["args"], m["ret"], m["rest"]
        ok = ret not in ("?",) and not ret.startswith("-")
        if name in _UNSEEN:
            t["unseen"] += 1
            continue
        strs = [x for x in _STR.finditer(args.split("[", 1)[0] if name in _EXEC else args)]
        if any(x["cut"] for x in strs):
            t["cut"] += 1
        if name in _LIST:
            fd = _FDARG.match(args)
            if not fd:
                t["nofd"] += 1
                continue
            p = _c(fd["p"])
            if active.get(fd["fd"]) != p:   # the first read of this open of the directory: one listing
                active[fd["fd"]] = p
                t["ev"].append(("l", None, p, "", None, seg))
            continue
        if name in _CLONE:
            if ok and ret.isdigit():
                t["created"].append((int(ret), "CLONE_THREAD" in args))
            continue
        if name == "fchdir":
            fd = _FDARG.match(args)
            if ok and fd:
                t["cwds"].add(_c(fd["p"]))
            elif ok:
                t["nofd"] += 1
            continue
        if name == "getcwd":
            if ok and strs:
                t["cwds"].add(_c(strs[0]["s"]))
            continue
        for x in strs:
            if x["dfd"] == "AT_FDCWD" and x["dp"] is not None:
                t["cwds"].add(_c(x["dp"]))
            elif x["dfd"] is not None and x["dp"] is None and not x["s"].startswith("/"):
                t["nofd"] += 1

        def ev(kind, x, reached=None, found_dir=False, seg=seg):
            t["ev"].append((kind, x["dfd"], _c(x["dp"]) if x["dp"] is not None else None, _c(x["s"]), reached, seg))
            if found_dir:
                t["dirs"].add(len(t["ev"]) - 1)   # a lookup that found a directory
        if name == "chdir":   # whether the directory exists decides the call: a lookup (never the import
            for x in strs[:1]:   # system's, never discounted), and (done) a new cwd
                ev("s", x)
                if ok:
                    t["ev"].append(("cd", None, None, _c(x["s"]), None, seg))
            continue
        if name in ("symlink", "symlinkat", "link", "linkat") and len(strs) >= 2:
            old, new = strs[0], strs[-1]   # symlink: the link's text, then the link; link: the file, then its name
            t["alias"].append((name.startswith("symlink"), old["dfd"], _c(old["dp"]) if old["dp"] is not None else None,
                               _c(old["s"]), new["dfd"], _c(new["dp"]) if new["dp"] is not None else None, _c(new["s"])))
        if name in ("readlink", "readlinkat"):
            strs = strs[:1]   # the second string is the link's text, not a path looked up
        elif name in ("symlink", "symlinkat"):
            strs = strs[-1:]   # the first string is the new link's text
        kind = "x" if name in _EXEC else "o" if name in _OPEN else "s"
        if kind == "o" and "O_DIRECTORY" in args:   # a directory opened: whether it exists (a lookup the hook's
            if ok:                                     # listing line does not account for: data); then listings
                active[ret] = None   # a new open of a directory: its first getdents is a new listing
            for x in strs:
                ev("s", x)
            continue
        r = _RETFD.match(rest) if ok else None
        reached = _c(r["p"]) if r and kind == "o" else None   # the file the kernel opened (a symlink resolved)
        if kind == "o" and ok:
            active.pop(ret, None)   # that fd number now names a file, not the directory a listing was read from
        for x in strs:
            ev(kind, x, reached, kind == "s" and ok and ("S_IFDIR" in args or "S_IFDIR" in rest))
        if kind == "x" and ok:
            seg += 1   # a new image runs in this task from here on
            t["execs"] += 1
    if pending is not None:
        t["bad"] += 1
    return t


def _strace(d: pathlib.Path) -> dict[int, dict]:
    tasks = {}
    for f in sorted(d.glob("tr.*")) if d.is_dir() else ():
        tid = f.name.rsplit(".", 1)[1]
        if not tid.isdigit():
            continue
        tasks[int(tid)] = parse_strace(f.read_bytes().decode("utf-8", "surrogateescape").splitlines())
    return tasks


# ------------------------------------------------------------------------------------------------- derive

_TESTID = re.compile(r"^(\w+) \(([\w.]+)\)[^\n]*?(?:\n[^\n]*?)? \.\.\. (ok|FAIL|ERROR|skipped|expected failure|"
                     r"unexpected success)", re.M)


def _resolve(dfd, dp, s, cwds) -> list[str]:
    """Every absolute path the string may name: itself, under its directory fd, or under every cwd the trace shows (a
    relative path in a call that takes no directory fd; a superset, never a guess)."""
    if s.startswith("/"):
        return [posixpath.normpath(s)]
    if dp is not None and dp.startswith("/"):
        return [posixpath.normpath(posixpath.join(dp, s) if s else dp)]
    if dfd is not None and dfd != "AT_FDCWD" and dp is None:
        return []   # an fd with no decoded path: counted as `nofd`
    return [posixpath.normpath(posixpath.join(c, s)) for c in sorted(cwds)] if s else []


def _tail(argv: str) -> str | None:
    """repr of a launch's argv without argv[0] (what the child's own sys.orig_argv[1:] says; argv[0] may be rewritten
    by a launcher stub), or None when it is not a list of strings."""
    try:
        v = ast.literal_eval(argv)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    return repr(list(v[1:])) if isinstance(v, list) and v and all(isinstance(x, str) for x in v) else None


def _accounting(procs: list[dict], root_pid) -> tuple[int, int, dict | None]:
    """audit: (records no hooked launch accounts for, hooked launches no record accounts for, the root record). The
    root is the one interpreter start whose pid is the pid the runner launched. Every other record is matched to the
    launch that made it, by identity — its parent's pid (an exec: its own pid) and its argv; a fork by its parent —
    never by a net count, so a missing record cannot be hidden by a surplus one."""
    pids = {p["pid"] for p in procs}
    roots = [p for p in procs if p["kind"] == "S" and p["pid"] == root_pid and p["ppid"] not in pids]
    root = roots[0] if root_pid is not None and len(roots) == 1 else None
    want: collections.Counter = collections.Counter()
    for p in procs:
        for e, py, h, a in p["C"]:
            if py and h:
                want[("F", p["pid"], None) if e in ("os.fork", "os.forkpty") else
                     ("x" if e == "os.exec" else "S", p["pid"], _tail(a))] += 1
    surplus = 0
    for p in procs:
        if p is root:
            continue
        keys = ([("F", p["ppid"], None)] if p["kind"] == "F" else
                [("x", p["pid"], p["argv"]), ("S", p["ppid"], p["argv"])] if p["argv"] is not None else [])
        k = next((k for k in keys if want[k] > 0), None)
        if k is None:
            surplus += 1
        else:
            want[k] -= 1
    return surplus, sum(want.values()), root


def derive(wdir) -> dict:
    """The observation record of witness directory `wdir`: a pure function of its files (verify() recomputes it)."""
    wdir = pathlib.Path(wdir)
    man = json.loads((wdir / "manifest.json").read_text(encoding="utf-8"))
    tree, checkout = pathlib.Path(man["tree"]), pathlib.Path(man["checkout"])
    roots, croots = RS._roots(tree), RS._roots(checkout)
    log = (wdir / "log.txt").read_text(encoding="utf-8", errors="replace") if (wdir / "log.txt").is_file() else ""
    procs, hook_bad = _hook(wdir / "hook")
    strace = man.get("backend") == "strace"
    tasks = _strace(wdir / "strace") if strace else {}
    outside, aliases = [False], [0]

    def rel(p: str) -> str | None:
        if _ALIAS.match(p):
            aliases[0] += 1   # the tree reached through /proc/<pid>/cwd|root or an fd: not a name any rule maps
        r = RS._rel(p, roots)
        if r is None:
            outside[0] = outside[0] or RS._rel(p, croots) is not None
            return None
        return None if "__pycache__" in r.split("/") else r

    def alias(target: str) -> None:
        """A new name made for `target`: reads through it are not reads of a tree path. Counted when the target is in
        the tree or holds it (lexically: a superset of what the name can reach, not a resolution)."""
        n = posixpath.normpath(target)
        if RS._rel(n, roots) is not None or any(r.startswith(n.rstrip("/") + "/") for r in roots):
            aliases[0] += 1

    opened: dict[str, str] = {}
    loaded, listed, by = set(), set(), collections.defaultdict(set)

    def data(p):
        if (r := rel(p)) is not None:
            opened[r] = "data"

    def listing(p, callers):
        if (r := rel(p)) is not None:
            listed.add(r)
            by[r].update(c for c in (rel(x) if x != RS.NATIVE else RS.NATIVE for x in callers) if c)

    pids = collections.defaultdict(list)
    for p in procs:
        pids[p["pid"]].append(p)
        for (tag, x), _n in p["o"].items():
            if (r := rel(x)) is not None and opened.get(r) != "data":
                opened[r] = tag
        for x in p["s"]:
            data(x)
        for own, x, callers in p["l"]:
            if not own:
                listing(x, callers)
        for x in p["m"]:
            if (r := rel(x)) is not None:
                loaded.add(r)
        for x in p["a"]:
            alias(x)
    # fd-relative access: unknown paths for the hook alone; under strace -y the trace names every such fd's path
    # (an fd it cannot name is counted below), so the hook's `d` lines are not an incompleteness there
    row = man.get("row") or {}
    comp = {"lost": sum(p["lost"] for p in procs), "unparsed_lines": hook_bad,
            "fd_relative": 0 if strace else sum(p["fd"] for p in procs),
            "untraced_children": 0, "unaccounted_processes": 0, "missing_trace_files": 0, "truncated_trace_files": 0,
            "truncated_strings": 0, "unterminated_processes": 0, "aliases": 0, "unobservable_calls": 0,
            "cwd_unresolved": 0, "kill_file_unseen": 0, "tests_unparsed": 0,
            "tracer_errors": sum(1 for x in log.splitlines() if x.startswith("strace: ")),
            "tracer_exit": int(strace and row.get("exit") != 0)}
    launches = [c for p in procs for c in p["C"]]
    kids = {"hooked": max(len(procs) - 1, 0), "unhooked_python": sum(1 for _, py, h, _ in launches if py and not h),
            "other": sum(1 for _, py, _, _ in launches if not py), "traced": 0,
            "launched": sorted({_sha(a.encode())[:16] for e, py, h, a in launches if not h})}
    if not strace:
        surplus, deficit, root = _accounting(procs, row.get("pid"))
        comp["missing_trace_files"] += int(root is None)   # the kill file's own process left no record of its own
        comp["untraced_children"] = kids["unhooked_python"] + kids["other"]
        comp["unaccounted_processes"] = surplus + deficit
        comp["unterminated_processes"] = sum(1 for p in procs if not p["ended"])
    else:
        creators = {c: (tid, thread) for tid, t in tasks.items() for c, thread in t["created"]}
        top = [tid for tid in tasks if tid not in creators]
        comp["missing_trace_files"] += int(not tasks) + sum(1 for c in creators if c not in tasks)
        comp["missing_trace_files"] += int(len(top) != 1 or not any(p["kind"] == "S" for p in pids.get(top[0], [])))
        comp["untraced_children"] = sum(1 for c in creators if c not in tasks)
        comp["unaccounted_processes"] = max(len(top) - 1, 0)
        comp["truncated_trace_files"] = sum(1 for t in tasks.values() if not t["end"])
        comp["truncated_strings"] = sum(t["cut"] for t in tasks.values())
        comp["unparsed_lines"] += sum(t["bad"] for t in tasks.values())
        comp["fd_relative"] += sum(t["nofd"] for t in tasks.values())
        comp["unobservable_calls"] = sum(t["unseen"] for t in tasks.values())

        def tgid(tid: int) -> int:
            seen = set()
            while tid in creators and creators[tid][1] and tid not in seen:
                seen.add(tid)
                tid = creators[tid][0]
            return tid
        cwds = {str(tree)} | {c for t in tasks.values() for c in t["cwds"]}
        cds = sorted({e[3] for t in tasks.values() for e in t["ev"] if e[0] == "cd"})
        for _ in cds:   # chained relative chdirs: every cwd they may reach, to a fixpoint (a superset, never a guess)
            new = {posixpath.normpath(posixpath.join(c, x)) for x in cds for c in cwds} - cwds
            if not new or len(cwds) > 4096:
                comp["cwd_unresolved"] += int(bool(new))
                break
            cwds |= new
        for t in tasks.values():
            for is_sym, odfd, odp, os_, ndfd, ndp, ns in t["alias"]:
                if is_sym and not os_.startswith("/"):   # a relative link text: against the link's own directory
                    for n in _resolve(ndfd, ndp, ns, cwds):
                        alias(posixpath.join(posixpath.dirname(n), os_))
                else:
                    for n in _resolve(odfd, odp, os_, cwds):
                        alias(n)
        groups = collections.defaultdict(list)
        for tid in tasks:
            groups[tgid(tid)].append(tid)
        kids["traced"] = max(len(groups) - 1, 0)
        comp["unaccounted_processes"] += sum(1 for pid in pids if pid not in groups)   # a hooked process never traced
        for g, tids in groups.items():
            hp = pids.get(g, [])   # the hook's records of this process: counted by tree-relative path
            made = {p["kind"] for p in hp}

            def hooked(tid: int, seg: int, g=g, made=made) -> bool:
                """Whether the image that ran segment `seg` of task `tid` ran the hook. Before any exec: a forked
                child that ran it (`F`). After exactly one exec: the interpreter start it recorded (`S`). After more
                than one, which image recorded what is unknown: none did. A thread: its leader's last image."""
                n = tasks[tid]["execs"]
                if tid != g:
                    return seg == 0 and g in tasks and hooked(g, tasks[g]["execs"])
                return "F" in made if seg == 0 else seg == 1 == n and "S" in made

            def rels(xs):
                return collections.Counter(r for x in xs if (r := rel(x)) is not None)
            ho = rels(x for p in hp for (_, x), n in p["o"].items() for _ in range(n))
            hs = rels(x for p in hp for k in ("s", "w") for x, n in p[k].items() for _ in range(n))
            hl = rels(x for p in hp for _, x, _ in p["l"])
            mine = set(rels([x for p in hp for x in p["m"]] + [x for p in hp for (tag, x) in p["o"] if tag == "load"]))
            so, ss, sl, sdirs = collections.Counter(), collections.Counter(), collections.Counter(), set()
            for tid in tids:
                t = tasks[tid]
                for i, (k, dfd, dp, s, reached, seg) in enumerate(t["ev"]):
                    if k == "cd":
                        continue
                    h = hooked(tid, seg)   # an image that never ran the hook is observed for data only
                    if k == "l":
                        if (r := rel(dp)) is not None:
                            if h:
                                sl[r] += 1
                            else:
                                listed.add(r)
                                by[r].add(RS.NATIVE)
                        continue
                    if k == "x":
                        for p in _resolve(dfd, dp, s, cwds):
                            data(p)
                        continue
                    names = {r for p in _resolve(dfd, dp, s, cwds) if (r := rel(p)) is not None}
                    for r in names:
                        if not h:
                            opened[r] = "data"
                            continue
                        (so if k == "o" else ss)[r] += 1
                        if i in t["dirs"]:
                            sdirs.add(r)
                    if reached is not None and (r := rel(reached)) is not None and r not in names:
                        opened[r] = "data"   # a symlink's target: read through another name
            for r, n in so.items():
                if n > ho[r]:
                    opened[r] = "data"
            for r, n in sl.items():
                if n > hl[r]:
                    listed.add(r)
                    by[r].add(RS.NATIVE)
            for r, n in ss.items():
                if n > hs[r] and not (r in mine or r in sdirs):
                    opened[r] = "data"   # a lookup the hook did not make: data, unless the import system's
    tests = [[m[2], m[3]] for m in _TESTID.finditer(log)]
    unparsed = max((row.get("ran") or 0) - len(tests), 0)
    comp["aliases"] = aliases[0]
    comp["kill_file_unseen"] = int((man.get("kill_file") or {}).get("path") not in loaded)   # F's own code never ran
    comp["tests_unparsed"] = unparsed + int(not tests)
    return {"format": FORMAT, "tool": TOOL, "commit": man.get("commit"), "kill_file": man.get("kill_file"),
            "tree_sha256": man.get("tree_sha256"), "runner_sha256": man.get("runner_sha256"),
            "observe_sha256": man.get("observe_sha256"), "backend": man.get("backend"), "os_trace": strace,
            "platform": man.get("platform"), "python": man.get("python"), "toolchain": man.get("toolchain"),
            "tools": man.get("tools"), "env": man.get("env"), "outcome": row.get("outcome"),
            "tests": {"module": man.get("module"), "ran": row.get("ran"), "ids": sorted(tests),
                      "ids_unparsed": unparsed},
            "opened": dict(sorted(opened.items())), "loaded": sorted(loaded), "listed": sorted(listed),
            "listed_by": {d: sorted(v) for d, v in sorted(by.items())}, "children": kids,
            "lost": comp["lost"], "unparsed_lines": comp["unparsed_lines"], "outside_tree": outside[0],
            "completeness": comp}


def witness_files(wdir) -> dict[str, str]:
    wdir = pathlib.Path(wdir)
    return {p.relative_to(wdir).as_posix(): _sha(p.read_bytes())
            for p in sorted(wdir.rglob("*")) if p.is_file() and p.relative_to(wdir).as_posix() != RECORD}


def finish(wdir) -> dict:
    """Write observation.json (derive() + the witness digests; never overwrites) and return it as load() would."""
    wdir = pathlib.Path(wdir)
    rec = {**derive(wdir), "witness": {"files": witness_files(wdir)}}
    with open(wdir / RECORD, "x", encoding="utf-8") as f:
        f.write(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return load_one(wdir)


def load_one(wdir) -> dict:
    rec = json.loads((pathlib.Path(wdir) / RECORD).read_text(encoding="utf-8"))
    if isinstance(rec, dict) and isinstance(rec.get("witness"), dict):
        rec["witness"]["dir"] = str(pathlib.Path(wdir).resolve())   # where verify() reads it; never in a digest
    return rec


def load(d) -> dict[str, dict]:
    """kill file -> observation, for every `<d>/*/observation.json` (or `d` itself). Two records of one kill file are
    both refused (a record that says so)."""
    d = pathlib.Path(d)
    out: dict = {}
    for f in [d / RECORD] if (d / RECORD).is_file() else sorted(d.glob(f"*/{RECORD}")):
        try:
            rec = load_one(f.parent)
            key = rec["kill_file"]["path"]
        except (OSError, ValueError, KeyError, TypeError):
            continue   # not a record: its kill file stays without an observation (R0)
        out[key] = {"format": "duplicate"} if key in out else rec
    return out


def public(rec: dict) -> dict:
    """The record without where its witness lies on this host (what a digest or a report holds)."""
    w = rec.get("witness")
    return {**rec, "witness": {k: v for k, v in w.items() if k != "dir"}} if isinstance(w, dict) else rec


def verify(rec: dict) -> tuple[str | None, list[str]]:
    """(why the record is refused — it is not what its witness says —, the witness's incompleteness). A missing,
    added or changed witness file is an incompleteness: what it held is not known."""
    w = rec.get("witness") if isinstance(rec, dict) else None
    if not isinstance(w, dict) or not isinstance(w.get("files"), dict) or not w.get("dir"):
        return "it has no witness", []
    d = pathlib.Path(w["dir"])
    now = witness_files(d) if d.is_dir() else {}
    gaps = ([f"witness file {x} is missing" for x in sorted(set(w["files"]) - set(now))]
            + [f"witness file {x} is not the bytes recorded (truncated or changed)" for x in sorted(w["files"])
               if x in now and now[x] != w["files"][x]]
            + [f"witness file {x} was not recorded" for x in sorted(set(now) - set(w["files"]))])
    if gaps:
        return None, gaps
    try:
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        hook = man.get("hook") or {}
        ran = (d / SITE).read_text(encoding="utf-8") if (d / SITE).is_file() else None
        if ran is None or ran != hook_source(pathlib.Path(hook["events"]), hook["roots"], hook["nonce"]):
            return "the hook it ran is not this recorder's hook (or its copy is missing)", []
        if man.get("backend") == "strace" and (man.get("tools") or {}).get("strace_events") != STRACE_EVENTS:
            return "its trace was not taken with this recorder's syscall set", []
        again = derive(d)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return f"its witness cannot be derived again: {type(e).__name__}: {e}", []
    mine = {k: v for k, v in rec.items() if k != "witness"}
    if canonical(again) != canonical(mine):
        key = next((k for k in sorted(set(again) | set(mine)) if canonical(again.get(k)) != canonical(mine.get(k))), "?")
        return f"its record is not what its witness says ({key})", []
    return None, []


# ------------------------------------------------------------------------------------------------- record


def _stray_dirs(root: pathlib.Path, head: str, copy, pristine: pathlib.Path) -> list[str]:
    """Directories of the runner's tree that no file of HEAD under COPY implies (an empty directory, or one that
    holds only an ignored `__pycache__`: the copy keeps it, the tree digest covers files only)."""
    from validation.v23 import impact
    files = impact._git(root, "ls-tree", "-r", "-z", "--name-only", "--full-tree", head, "--", *copy)
    want = {"/".join(x[:k]) for f in files.decode("utf-8", "surrogateescape").split("\0") if f
            for x in [f.split("/")] for k in range(1, len(x))}
    return sorted({q.relative_to(pristine).as_posix() for q in pristine.rglob("*") if q.is_dir()} - want)


@contextlib.contextmanager
def _patched(obj, **values):
    saved = {k: getattr(obj, k) for k in values}
    for k, v in values.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(obj, k, v)


def record(root, kill_file: str, out, backend: str = "auto") -> pathlib.Path:
    """Observe one unmutated run of `kill_file` at `root`'s HEAD; the witness directory (with observation.json)."""
    from validation.v23 import impact   # here, not at import: impact imports this module
    root = pathlib.Path(root).resolve()
    strace = shutil.which("strace") if backend in ("auto", "strace") and sys.platform.startswith("linux") else None
    if backend == "strace" and not strace:
        raise SystemExit("refused: --backend strace needs strace on a Linux host")
    backend = "strace" if strace else "audit"
    head = impact._rev(root, "HEAD")
    if head is None:
        raise SystemExit(f"refused: {root} has no HEAD commit")
    wdir = pathlib.Path(out) / kill_file.replace("/", "__")
    wdir.mkdir(parents=True)   # never into an existing observation
    with tempfile.TemporaryDirectory(prefix="aisef-observe-", ignore_cleanup_errors=True) as t, \
            impact._pinned_git(pathlib.Path(t)):
        rev = SD.Rev(root, head, pathlib.Path(t) / "rev")
        M = rev.m   # the HEAD commit's own runner
        if dirty := impact._dirty(root, head, M.COPY):
            raise SystemExit(f"refused: the checkout differs from HEAD inside the runner's COPY: {dirty[0]}")
        scratch = pathlib.Path(t) / "run"
        scratch.mkdir()
        pristine, digest = M._pristine(root, scratch / "pristine")
        if stray := _stray_dirs(root, head, M.COPY, pristine):
            raise SystemExit(f"refused: the runner's tree holds a directory no file of HEAD implies: {stray[0]}")
        if not (pristine / kill_file).is_file():
            raise SystemExit(f"refused: {kill_file} is not a file of the runner's tree")
        tg = M._Target(None, scratch, M.ca.establish(scratch), "observe-" + M._worker(root), tests=[kill_file])
        tg.pristine = pristine
        M._new_tree(tg)
        tg.pristine = None
        tree = tg.tree
        hook, site, trace = wdir / "hook", pathlib.Path(t) / "site", wdir / "strace"
        hook.mkdir()
        site.mkdir()
        nonce, hroots = os.urandom(12).hex(), RS._roots(tree)
        for d in (site, wdir):   # the one the processes import, and the witness's copy (verify() recomputes it)
            (d / SITE).write_text(hook_source(hook, hroots, nonce), encoding="utf-8")
        seen_env: dict[str, str] = {}
        logs: list[str] = []
        real_env, real_summary = M._env, M._summary

        def env(run, token):
            e = {**real_env(run, token), "PYTHONPATH": str(site), MARK: nonce}
            seen_env.update(e)
            return e

        def summary(text):
            logs.append(text)
            return real_summary(text)
        import aisef2.runtime.process_range as PR
        if strace:
            trace.mkdir()
        started: list[int | None] = []

        class Observed(PR.ProcessRange):
            def __init__(self, name, argv, **kw):
                if strace:
                    argv = [strace, "-f", "-ff", "-y", "-s", "8192", "-o", str(trace / "tr"), "-e",
                            f"trace={STRACE_EVENTS}", "--", *argv]
                super().__init__(name, argv, **kw)

            def start(self):
                out = super().start()
                started.append(self.target_pid)   # the root's identity (audit): the pid the runner launched
                return out
        rows: list[dict] = []
        with _patched(M, _env=env, _summary=summary), _patched(PR, ProcessRange=Observed):
            try:
                row = M._run_file(tg, kill_file, rows, failfast=False, role="observe")
            except M._Stop as e:
                row = rows[-1] if rows else {}
                row.setdefault("outcome", "INFRA")
                row["why"] = str(e)
            finally:
                if tg.holder is not None:
                    tg.holder.cleanup()
        (wdir / "log.txt").write_text(logs[-1] if logs else "", encoding="utf-8")
        name = pathlib.PurePosixPath(kill_file)
        man = {"format": FORMAT, "tool": TOOL, "commit": head, "tree": str(tree), "checkout": str(root),
               "tree_sha256": digest, "kill_file": {"path": kill_file, "sha256": _sha((pristine / kill_file).read_bytes())},
               "module": ".".join(name.with_suffix("").parts[1:]),
               "runner_sha256": _sha(impact._blob(root, head, impact.MUTATION_REL) or b""),
               "observe_sha256": own_sha256(), "backend": backend,
               "hook": {"events": str(hook), "roots": list(hroots), "nonce": nonce},
               "tools": {"strace": _version([strace, "-V"]) if strace else None, "git": _version(["git", "--version"]),
                         "strace_events": STRACE_EVENTS if strace else None},
               **identity(), "env": {k: _sha(v.encode("utf-8", "surrogateescape")) for k, v in sorted(seen_env.items())},
               "row": {**{k: row.get(k) for k in ("outcome", "exit", "seconds", "ran", "why", "residual", "leaked")},
                       "pid": started[-1] if started else None}}
        (wdir / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    finish(wdir)
    return wdir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="observe.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--kill-file", action="append", default=[], metavar="F")
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--backend", choices=("auto", "strace", "audit"), default="auto")
    ap.add_argument("--verify", type=pathlib.Path, metavar="DIR")
    a = ap.parse_args(argv)
    if a.verify:
        bad = 0
        for f, rec in sorted(load(a.verify).items()):
            refused, gaps = verify(rec)
            gaps += [f"{k} {v}" for k, v in sorted((rec.get("completeness") or {}).items()) if v]
            bad += bool(refused or gaps or rec.get("outcome") != "PASS")
            print(f"{'OK ' if not (refused or gaps) else 'BAD'} {f}: {refused or '; '.join(gaps) or rec.get('outcome')}")
        return 1 if bad else 0
    if not a.kill_file or not a.out:
        ap.error("--kill-file and --out are required (or --verify DIR)")
    if bad := [f for f in a.kill_file if f.startswith("/") or "\\" in f or ".." in f.split("/")]:
        ap.error(f"not a path relative to the root with '/': {bad[0]!r}")
    rc = 0
    for f in a.kill_file:
        rec = load_one(record(ROOT, f, a.out, a.backend))
        gaps = [f"{k} {v}" for k, v in sorted(rec["completeness"].items()) if v]
        rc |= int(bool(gaps) or rec["outcome"] != "PASS")
        print(f"{rec['outcome']} {f} backend={rec['backend']} opened={len(rec['opened'])} loaded={len(rec['loaded'])} "
              f"listed={len(rec['listed'])} {'complete' if not gaps else 'INCOMPLETE: ' + '; '.join(gaps)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
