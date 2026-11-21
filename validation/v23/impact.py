"""F5 static impact engine (AISEF v2.3 W1a, increment 1): the evidence state of every live mutation target.

    python3 -P validation/v23/impact.py --classify [--base REV] [--head REV] [--json OUT] [--affected]

The frozen design is docs/v2.3/W1-DESIGN.md (§1, §2.1-§2.5, §2.7, §2.9, §9, §10). Every live target — the entries
`mutation.check()` reads: RECORDS x PHASE_TARGETS minus superseded, at `head` — gets exactly one of four states:

    MEASURED        measured in v2.3 by the F5-aware runner (no v2.3 record exists yet: never produced here)
    VERIFIED_REUSE  not measured in v2.3; every impact input re-derived now is unchanged since the basis
    INVALIDATED     an impact input changed inside the impact set, the entry differs from its committed bytes, or the
                    platform contradicts the claim — must be re-measured
    UNRESOLVED      no identity can be computed (no git, shallow clone, basis missing, dirty tree, no platform
                    evidence, unparsable source, malformed record) — never current

Decision procedure, first failing rule wins (§2.3): basis/dirty -> I7 tamper -> I6 platform -> I1 target slice (the
entry was current at its basis, or the pinned Option C ruling covers it: I8) -> I3 kill set -> I4 kill-test closure
-> I5 generator output -> I9 runner settings -> §2.9 rules R4, R5, R6, then R0/D2/R1/R2/R3, then R8 and R7 (tier S).

"Now" is `head` read from git; any path under a COPY root whose working-tree bytes differ from `head`, or an
untracked/ignored file there (the runner copies those too; `__pycache__` excepted), makes every target UNRESOLVED.
Legacy entries (all of v2.2 and earlier) are never MEASURED: basis `v2.2.0-accepted@<base>`, or
`ruling:<id>@<sha256>` for the owner's Option C targets.

Observations. `observations` maps a kill file F to its O(F) (§2.9 D3) as a dict: commit (the head sha), platform
(`posix`/`windows`), python (`3.N`), witness, outcome (`PASS`), opened ({path: "load"|"data"}; a list = all data),
loaded, listed, listed_by ({dir: [files]}), children ({hooked, unhooked_python, other}), lost, unparsed_lines,
os_trace, outside_tree. With `observations=None` (no recorder exists yet) R0-R3 cannot be excluded: a target is
INVALIDATED ("no observation of F; R1 cannot be excluded") whenever Δ is not empty — an unobserved process may read
any path of the tree — and Δ = ∅ gives VERIFIED_REUSE. Tier R (E_full) is not available in this increment.

Declared limitations (§2.7, §2.9 residual):
- C code that reads tree files is seen only through os_trace; a SIGKILLed recorder can lose its `lost` count.
- Hash-only reads (kernel_digest, mechanism_digest) are data reads; no DIGEST-READ discount exists.
- Tamper detection (I7) is anchored to git history: it proves the entry equals what was committed, not who measured.
- Legacy env is unbound (runner-1 imports ran with TIMEOUT 120, before ENV_KEEP/SETTLE_S); `posix` means measured on
  a POSIX host, not killed on every POSIX flavor; row evidence needs tails that keep their traceback frames.
- Before the basis, legacy records carry no kill-file, generator or platform identity (no retro-tagging).
- RESOLVED_SITES is empty: any dynamic site (R8) in S(F) makes tier S unavailable for that kill file.
- S(F) literal naming (D2 b) is the static rule of v21_snapshot_delta._info/_names plus whole-constant directories
  of two or more components; data a kill file reaches by other means is R2/R3's (observed), never S(F)'s.
Read-only: git and the repository; the only write is --json OUT (and a temporary extraction of each commit's
aisef2/ and validation/v2/, v21_snapshot_delta.Rev, removed afterwards).
"""

from __future__ import annotations

import argparse
import ast
import bisect
import collections
import dataclasses
import functools
import hashlib
import json
import pathlib
import posixpath
import re
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as S2  # noqa: E402  (closure, blob, _git: frozen, called)
from validation.qualification import v21_snapshot_delta as SD  # noqa: E402  (Rev, _segments, _info, _names, ...)
from validation.v21 import reach  # noqa: E402  (changed(): own code vs import-time statements)

TOOL = "validation/v23/impact.py"
STATES = ("MEASURED", "VERIFIED_REUSE", "INVALIDATED", "UNRESOLVED")
BASE = "da3ea33f"   # v2.2.0: the owner-approved release gate accepted every live entry here
MUTATION_REL = "validation/v2/mutation.py"
#: §2.4.2: the claim belongs to the target; these three are Win32-native, every other target is posix
WINDOWS_CLAIM = frozenset({"aisef2/app/client.py::_is_gone", "aisef2/runtime/process_range.py::_win_liveness",
                           "aisef2/runtime/process_range.py::pid_alive"})
#: I8: Option C is honoured only through this file, pinned by its sha256 (the mutation.py table is not a basis)
RULING_ID = "AISEF-V2.2-B1-MUTATION-EVIDENCE-REUSE-RULING"
RULING_REL = "closure-evidence/v2/v2.2/B1-MUTATION-EVIDENCE-REUSE-RULING.json"
RULING_SHA256 = "694b66021313f574eca42502bc1214a4d0a9e292831c2abd21536765feffbc22"
#: I9: the runner's verdict-affecting constants and code (W1's own mutation.py edits must not touch these)
I9_NAMES = ("TIMEOUT", "BRACKET", "ENV_KEEP", "_FRESH", "SETTLE_S", "CLASSES", "mutant_class", "_run_file",
            "_classify", "_confirmed", "null_mutant", "_env")
#: R8: (file, enclosing qualname, ast.dump of the call) -> domain function. Frozen; empty in this increment.
RESOLVED_SITES: dict = {}
#: R1: without os_trace, S(F) must name none of these (launch or read paths the hook does not see)
R1_UNSEEN = ("_posixsubprocess", "multiprocessing", "os.fork", "os.exec", "os.spawn", "os.fwalk", "dir_fd=",
             "os.access", "os.readlink", "RLIMIT_NOFILE")

_TOK = r"""(?:(?<=[\s"'(=,:\[])|^)"""   # a path token starts a line or follows a space, quote, bracket, = , :
_DARWIN = re.compile(_TOK + r"""(?:/opt/homebrew/|/Users/[^/\s"'<>]+/|/private/(?:tmp|var)/|/var/folders/)"""
                     r"""|Python\.framework/Versions/""", re.M)
_LINUX = re.compile(_TOK + r"""(?:/usr/lib/python3\.\d+/|/home/[^/\s"'<>.][^/\s"'<>]*/|/root/)""", re.M)
_DOTTED = re.compile(r"^(?:-m\s+)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)(?::[A-Za-z_]\w*)?$")
_WORD = re.compile(r"[A-Za-z_]\w*")


@dataclasses.dataclass(frozen=True)
class State:
    target: str
    state: str
    component: str = ""
    reason: str = ""
    basis: str = ""
    compared: list = dataclasses.field(default_factory=list)
    evidence: dict = dataclasses.field(default_factory=dict)
    mutants: int = 0


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _blob(root: pathlib.Path, sha: str, path: str) -> bytes | None:
    """`path`'s bytes at commit `sha` (never cached: records reach 100 MB)."""
    if S2.blob(root, sha, path) is None:
        return None
    return S2._git(root, "cat-file", "blob", f"{sha}:{path}").stdout


def _rev(root: pathlib.Path, rev: str) -> str | None:
    r = S2._git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return r.stdout.decode().strip() if r.returncode == 0 and r.stdout.strip() else None


# ---------------------------------------------------------------------------------------------- source segments


def _defines(n: ast.stmt) -> tuple[str, ...]:
    if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return (n.name,)
    if isinstance(n, ast.Assign):
        return tuple(x.id for t in n.targets for x in ast.walk(t) if isinstance(x, ast.Name))
    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
        return (n.target.id,)
    if isinstance(n, ast.Import | ast.ImportFrom):
        return ("<imports>",)
    return ()   # a module-level statement


def segments(src: str, tree: ast.Module | None = None) -> list[tuple[tuple[str, ...], str, ast.stmt]]:
    """(names it defines, exact source text with decorators, node) of every top-level statement (§2.2)."""
    src = _lf(src)
    lines = src.splitlines(keepends=True)
    out = []
    for n in (tree or ast.parse(src)).body:
        start = min([d.lineno for d in getattr(n, "decorator_list", [])] + [n.lineno])
        out.append((_defines(n), "".join(lines[start - 1:n.end_lineno]), n))
    return out


def _idents(node: ast.AST) -> set[str]:
    """Names a segment refers to (I1 follows Name and Attribute; strings are tier S's, R7). A `__main__` guard does not
    run at import, so it reaches nothing."""
    if isinstance(node, ast.If) and ast.unparse(node.test) in ("__name__ == '__main__'", "'__main__' == __name__"):
        return set()
    return {x.id if isinstance(x, ast.Name) else x.attr for x in ast.walk(node) if isinstance(x, ast.Name | ast.Attribute)}


@functools.lru_cache(maxsize=64)
def _parsed(src: str):
    tree = ast.parse(_lf(src))
    return segments(src, tree), tree


def target_slice(m, src: str, func: str) -> list[str] | None:
    """I1: the target's top-level segment, every same-module segment it reaches by name (transitively), the imports and
    the module-level statements — as sorted exact source texts. None: unparsable, or the target is not there."""
    try:
        segs, tree = _parsed(src)
    except SyntaxError:
        return None
    script, _, inner = func.partition("/")
    if inner:
        anchor = m._script(tree, script)
    else:
        found = m._root(tree, func)
        anchor = found[0] if found else None
    if anchor is None:
        return None
    top = next((i for i, (_, _, n) in enumerate(segs) if any(x is anchor for x in ast.walk(n))), None)
    if top is None:
        return None
    by_name: dict[str, list[int]] = {}
    for i, (names, _, _) in enumerate(segs):
        for x in names:
            by_name.setdefault(x, []).append(i)
    keep = {top} | {i for i, (names, _, _) in enumerate(segs) if names in ((), ("<imports>",))}
    todo = list(keep)
    while todo:
        for ref in _idents(segs[todo.pop()][2]):
            for j in by_name.get(ref, ()):
                if j not in keep:
                    keep.add(j)
                    todo.append(j)
    return sorted(segs[i][1] for i in keep)


def settings_digest(src: str | None) -> dict[str, str]:
    """I9: name -> sha256 of its exact segment text in mutation.py (absent names say so)."""
    found: dict[str, str] = {}
    try:
        for names, text, _ in segments(src or ""):
            for x in names:
                if x in I9_NAMES:
                    found[x] = found.get(x, "") + text
    except SyntaxError:
        return {"<unparsable>": _sha((src or "").encode())}
    return {x: _sha(found[x].encode()) if x in found else "<absent>" for x in I9_NAMES}


def name_refs(src: str) -> collections.Counter:
    """R7 references of one file: Name, Attribute, alias, keyword, def and class names, and whole-word tokens of
    string constants."""
    c: collections.Counter = collections.Counter()
    for x in ast.walk(ast.parse(_lf(src))):
        if isinstance(x, ast.Name):
            c[x.id] += 1
        elif isinstance(x, ast.Attribute):
            c[x.attr] += 1
        elif isinstance(x, ast.alias):
            c.update(x.name.split("."))
            if x.asname:
                c[x.asname] += 1
        elif isinstance(x, ast.keyword) and x.arg:
            c[x.arg] += 1
        elif isinstance(x, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            c[x.name] += 1
        elif isinstance(x, ast.Constant) and isinstance(x.value, str):
            c.update(_WORD.findall(x.value))
    return c


def _qualdefs(src: str) -> collections.Counter:
    """qualname -> number of defs, named exactly as reach.functions names them."""
    out: collections.Counter = collections.Counter()

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef):
                out[prefix + ch.name] += 1
                walk(ch, prefix + ch.name + ".<locals>.")
            elif isinstance(ch, ast.ClassDef):
                walk(ch, prefix + ch.name + ".")
            elif isinstance(ch, reach._SCOPES):
                walk(ch, prefix)
    walk(ast.parse(_lf(src)), "")
    return out


_DYN_ATTR = {"getattr": 1, "hasattr": 1, "setattr": 1, "delattr": 1, "attrgetter": 0, "methodcaller": 0}
_DYN_IMPORT = {"import_module", "spec_from_file_location"}
_DYN_BUILTIN = {"exec", "eval", "compile", "globals", "vars", "locals", "dir", "__import__"}
_LAUNCH = {"run", "Popen", "call", "check_call", "check_output", "system", "posix_spawn", "spawnv", "execv"}


def _literal(x: ast.AST) -> bool:
    return isinstance(x, ast.Constant) and isinstance(x.value, str)


def dynamic_sites(src: str, path: str) -> list[tuple[str, str, int, str]]:
    """R8: (file, enclosing qualname, line, ast.dump) of every computed-name site."""
    out = []

    def visit(node, qual):
        for ch in ast.iter_child_nodes(node):
            q = qual
            if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                q = f"{qual}.{ch.name}" if qual else ch.name
            hit = False
            if isinstance(ch, ast.Call):
                f = ch.func
                name = getattr(f, "attr", None) or getattr(f, "id", None)
                owner = getattr(getattr(f, "value", None), "id", None)
                if name in _DYN_ATTR:
                    i = _DYN_ATTR[name]
                    hit = len(ch.args) <= i or not _literal(ch.args[i])
                elif name in _DYN_IMPORT:
                    hit = not ch.args or not _literal(ch.args[0])
                elif (isinstance(f, ast.Name) and name in _DYN_BUILTIN) or name == "getmembers" or owner == "runpy" \
                        or (owner in ("pickle", "marshal") and name in ("load", "loads")):
                    hit = True
                elif name in _LAUNCH and owner in ("subprocess", "os") and ch.args:
                    argv = ch.args[0]
                    elts = argv.elts if isinstance(argv, ast.List | ast.Tuple) else [argv]
                    hit = not all(_literal(e) or ast.unparse(e) == "sys.executable" for e in elts)
            elif isinstance(ch, ast.Subscript) and isinstance(ch.value, ast.Attribute) and ch.value.attr == "__dict__":
                hit = True
            elif isinstance(ch, ast.ImportFrom) and any(a.name == "*" for a in ch.names):
                hit = True
            if hit:
                out.append((path, qual, getattr(ch, "lineno", 0), ast.dump(ch)))
            visit(ch, q)
    visit(ast.parse(_lf(src)), "")
    return out


# --------------------------------------------------------------------------------------------- platform (I6)


def _tails(entry: dict):
    for r in entry.get("results") or []:
        for f in (r.get("files") or []) if isinstance(r, dict) else []:
            if isinstance(f, dict) and isinstance(f.get("tail"), str):
                yield f["tail"]
    for k in ("t0", "original"):
        for f in entry.get(k) or []:
            if isinstance(f, dict) and isinstance(f.get("tail"), str):
                yield f["tail"]


def markers(texts, escaped: bool = False) -> tuple[set[str], set[str]]:
    """(families, flavors) the texts prove (§2.4.3 R-family, R-flavor). `escaped`: also JSON-escaped frames (a log)."""
    fam: set[str] = set()
    fl: set[str] = set()
    for t in texts:
        if 'File "<tree>/' in t or (escaped and 'File \\"<tree>/' in t):
            fam.add("posix")
        if 'File "<tree>\\' in t or (escaped and 'File \\"<tree>\\\\' in t):
            fam.add("windows")
        if _DARWIN.search(t):
            fl.add("darwin")
        if _LINUX.search(t):
            fl.add("linux")
    return fam, fl


def platform_of(entry: dict, workers: dict) -> dict:
    """{family, flavor, by, contradiction}: the first tier that yields a value wins (R-family, R-flavor, W);
    contradictory evidence is named, never resolved."""
    fam, fl = markers(_tails(entry))
    ws = workers.get(_sha(canonical(entry)), [])
    wfam = set().union(*(w[1] for w in ws)) if ws else set()
    wfl = set().union(*(w[2] for w in ws)) if ws else set()
    why = ("both <tree>/ and <tree>\\ frames" if len(fam) > 1 else
           "both darwin and linux markers" if len(fl) > 1 else
           "a posix flavor marker in a windows entry" if fam == {"windows"} and fl else
           "worker evidence disagrees with itself" if len(wfam) > 1 or len(wfl) > 1 else
           "worker evidence disagrees with the rows" if (fam and wfam and fam != wfam) or (fl and wfl and fl != wfl)
           else None)
    family = fam or ({"posix"} if fl else set()) or wfam
    by = "R-family" if fam else "R-flavor" if fl else f"W:{ws[0][0]}" if wfam else None
    return {"family": min(family) if len(family) == 1 else None, "flavor": min(fl or wfl) if len(fl or wfl) == 1 else None,
            "by": by, "contradiction": why}


def workers_at(root: pathlib.Path, sha: str) -> tuple[dict, list[str]]:
    """W: canonical-entry digest -> [(history, families, flavors)] over every committed mutation-workers history whose
    log and record are the bytes it recorded and whose artifacts carry R markers; and the refused histories."""
    out: dict[str, list] = {}
    refused = []
    for p in sorted(S2._files(root, sha)):
        if not (p.startswith("closure-evidence/") and "/mutation-workers/" in p and p.endswith(".history.json")):
            continue
        try:
            h = json.loads(_blob(root, sha, p))
            log = _blob(root, sha, h["log"]["path"])
            rec = _blob(root, sha, h["record"]["path"]) if h.get("record") else None
            if log is None or _sha(log) != h["log"]["sha256"] or (h.get("record") and (rec is None or _sha(rec) != h["record"]["sha256"])):
                raise ValueError("log or record is not the bytes the history recorded")
            if rec is None:
                continue
            targets = json.loads(rec)["targets"]
        except (ValueError, KeyError, TypeError) as e:
            refused.append(f"{p}: {e}")
            continue
        fam, fl = markers([log.decode("utf-8", "replace"), *(t for e in targets for t in _tails(e))], escaped=True)
        if not fam and not fl:
            continue   # no R markers: the worker proves nothing
        fam = fam | ({"posix"} if fl else set())
        for e in targets:
            out.setdefault(_sha(canonical(e)), []).append((p, frozenset(fam), frozenset(fl)))
    return out, refused


# ------------------------------------------------------------------------------------------------- the engine


class _Ctx:
    def __init__(self, root: pathlib.Path, B, H, observations):
        self.root, self.B, self.H, self.obs = root, B, H, observations
        self.copy = tuple(H.copy)
        self.delta = self._delta()
        self.settings = (settings_digest(B.text(MUTATION_REL)), settings_digest(H.text(MUTATION_REL)))
        self._S: dict = {}
        self._c: dict = {}
        self._listing = None
        self._texts: dict = {}

    @functools.cached_property
    def workers(self) -> dict:
        return workers_at(self.root, self.H.sha)[0]

    def _in_copy(self, p: str) -> bool:
        return any(p == c or p.startswith(c + "/") for c in self.copy)

    def _delta(self) -> dict[str, str]:
        """D1: path -> A/D/M, every path under a COPY root added, removed, or whose LF-sha256 differs."""
        if self.B.sha == self.H.sha:
            return {}
        raw = S2._git(self.root, "diff", "--name-status", "--no-renames", "-z", self.B.sha, self.H.sha, "--",
                      *self.copy).stdout.decode("utf-8", "replace").split("\0")
        out = {}
        for status, path in zip(raw[0::2], raw[1::2], strict=False):
            if status[:1] == "M":
                a, b = _blob(self.root, self.B.sha, path), _blob(self.root, self.H.sha, path)
                if a is not None and b is not None and a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n"):
                    continue
            out[path] = status[:1]
        return out

    def cache(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    # ---- S(F), §2.9 D2

    def copy_files(self, R) -> list[str]:
        return self.cache(("copy", R.sha), lambda: sorted(p for p in S2._files(self.root, R.sha) if self._in_copy(p)))

    def _named(self, R, g: str) -> set[str]:
        """D2 (b) literal paths and (c) dotted import strings in the .py file `g`."""
        def compute():
            info = SD._info(self.root, R.sha, g)
            text, consts, calls = info
            files = self.copy_files(R)
            out = {p for p in files if p != g and (p.rsplit("/", 1)[-1] in text or calls) and SD._names(info, g, p)}
            up = g.split("/")
            for c in consts:
                if c.count("/") >= 1:
                    for a in {"/".join(up[:k]) for k in range(len(up))}:
                        d = f"{a}/{c}" if a else c
                        i = bisect.bisect_left(files, d + "/")
                        while i < len(files) and files[i].startswith(d + "/"):
                            out.add(files[i])
                            i += 1
                m = _DOTTED.match(c)
                if m and m[1].split(".")[0] in S2.ROOTS:
                    parts = m[1].split(".")
                    out.update(f for k in range(2, len(parts) + 1)
                               if (f := S2._module_file(S2._files(self.root, R.sha), ".".join(parts[:k]))))
            return out
        return self.cache(("named", R.sha, g), compute)

    def _closure_at(self, R, F: str) -> set[str]:
        files = S2._files(self.root, R.sha)
        d, name = posixpath.dirname(F), posixpath.basename(F)
        out: set[str] = set()
        todo = [F, *(p for p in files if p.startswith(d + "/") and posixpath.basename(p) in ("__init__.py", name))]
        while todo:
            f = todo.pop()
            if f in out or f not in files:
                continue
            new = (set(S2.closure(self.root, R.sha, (f,))) | {f}) - out if f.endswith(".py") else {f}
            out |= new
            for g in sorted(new):
                if g.endswith(".py") and self._in_copy(g):
                    todo += [x for x in self._named(R, g) if x not in out]
        return out

    def S(self, F: str) -> frozenset[str]:
        """S(F) at basis ∪ now: s2 closure, literal paths, dotted names, discovery set, to a fixpoint."""
        if F not in self._S:
            self._S[F] = frozenset(self._closure_at(self.B, F) | self._closure_at(self.H, F))
        return self._S[F]

    # ---- per-file facts

    def changed(self, p: str) -> dict | str:
        def compute():
            a, b = self.B.text(p), self.H.text(p)
            if b is None:
                return {"names": {}, "removed": [], "module": "removed"}
            try:
                return reach.changed(a, b)
            except SyntaxError as e:
                return f"unparsable {p}: {e}"
        return self.cache(("changed", p), compute)

    def modules_named(self, R, f: str) -> set[str]:
        def compute():
            src = R.text(f)
            try:
                tree = ast.parse(src or "")
            except SyntaxError:
                return {"<unparsable>"}
            pkg = ".".join(f.split("/")[:-1])
            out = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    out.update(a.name for a in n.names)
                elif isinstance(n, ast.ImportFrom):
                    base = n.module or ""
                    if n.level:
                        up = pkg.split(".")[: len(pkg.split(".")) - (n.level - 1)]
                        base = ".".join(up + ([base] if base else []))
                    out.update([base, *(f"{base}.{a.name}" for a in n.names)])
                elif isinstance(n, ast.Constant) and isinstance(n.value, str) and (m := _DOTTED.match(n.value.strip())):
                    out.add(m[1])
            return out
        return self.cache(("mods", R.sha, f), compute)

    def refs(self, R, f: str) -> collections.Counter:
        def compute():
            src = R.text(f)
            try:
                return name_refs(src) if src is not None else collections.Counter()
            except SyntaxError:
                return collections.Counter({"<unparsable>": 1})
        return self.cache(("refs", R.sha, f), compute)

    def sites(self, R, f: str) -> list:
        def compute():
            src = R.text(f)
            try:
                return dynamic_sites(src, f) if src is not None else []
            except SyntaxError:
                return [(f, "", 0, "<unparsable>")]
        return self.cache(("sites", R.sha, f), compute)

    def listing_changed(self):
        if self._listing is None:
            self._listing = (SD._listing_rule(self.B, self.H)[0],)
        return self._listing[0]

    # ---- the procedure

    def judge(self, rel: str, entry: dict, base_entry: dict | None) -> State:
        name = entry["target"]
        mut = entry.get("mutants") if isinstance(entry.get("mutants"), int) else 0
        compared: list[str] = []
        ev: dict = {"record": rel, "entry_sha256": _sha(canonical(entry))}
        basis = f"v2.2.0-accepted@{self.B.sha}"

        def done(state, comp="", reason="", **extra):
            return State(name, state, comp, reason, basis, list(compared), {**ev, **extra}, mut)

        # I7
        if base_entry is None:
            return done("INVALIDATED", "I7", f"record entry has no committed counterpart in {rel} at the basis")
        if canonical(base_entry) != canonical(entry):
            return done("INVALIDATED", "I7", "record entry differs from its committed bytes")
        compared.append("I7")
        # I6
        plat = platform_of(entry, self.workers)
        ev["platform"] = plat
        claim = "windows" if name in WINDOWS_CLAIM else "posix"
        if plat["contradiction"]:
            return done("INVALIDATED", "I6", f"contradictory platform evidence: {plat['contradiction']}")
        if plat["family"] is None:
            return done("UNRESOLVED", "I6", "no platform evidence")
        if plat["family"] != claim:
            return done("INVALIDATED", "I6", f"measured on {plat['family']}, the claim is {claim}")
        compared.append("I6")
        # I1 (+ I8)
        rel_t, _, func = name.partition("::")
        src_b, src_h = self.B.text(rel_t), self.H.text(rel_t)
        if src_b is None:
            return done("INVALIDATED", "I1", f"{rel_t} does not exist at the basis")
        if src_h is None:
            return done("INVALIDATED", "I1", f"{rel_t} was removed")
        if self.H.m.source_digest(src_b) != entry.get("source_sha256"):
            why = self.option_c(name, entry, src_b, plat)
            if why:
                claims = name in getattr(self.H.m, "VERIFIED_REUSE", {}) or name in getattr(self.B.m, "VERIFIED_REUSE", {})
                return done("INVALIDATED", "I8" if claims else "I1",
                            f"entry was not current at its basis and no pinned ruling covers it: {why}")
            basis = f"ruling:{RULING_ID}@{RULING_SHA256}"
            compared.append("I8")
        sb, sh = target_slice(self.B.m, src_b, func), target_slice(self.H.m, src_h, func)
        if sb is None or sh is None:
            return done("UNRESOLVED", "I1", f"target not found or source unparsable at {'basis' if sb is None else 'head'}")
        if sb != sh:
            diff = sorted(set(sb) ^ set(sh))
            return done("INVALIDATED", "I1", f"target slice changed: {diff[0].splitlines()[0][:80]!r}")
        compared.append("I1")
        # I3
        current = self.H.m.TARGETS.get(name)
        recorded = entry.get("kill_tests")
        if current is None:
            return done("INVALIDATED", "I3", "not a current mutation target")
        if not isinstance(recorded, list):
            return done("UNRESOLVED", "I3", "record entry names no kill set")
        killers = {r["killed_by"]["file"] for r in entry.get("results") or []
                   if isinstance(r, dict) and r.get("class", "KILLED" if r.get("killed") else "") == "KILLED"
                   and isinstance(r.get("killed_by"), dict) and "file" in r["killed_by"]}
        dropped = sorted((set(recorded) | killers) - set(current))
        if dropped:
            return done("INVALIDATED", "I3", f"kill file dropped from the kill set: {', '.join(dropped)}")
        if recorded != list(current):
            ev["kill_set"] = "kill-set-superset" if set(recorded) != set(current) else "kill-set-reordered"
        compared.append("I3")
        kill = list(current)
        # I4
        additive = []
        if any(p.startswith("tests/") for p in self.delta):
            for F in kill:
                for p in sorted(x for x in self.S(F) if x.startswith("tests/") and x in self.delta):
                    a, b = SD._segments(self.B.text(p)), SD._segments(self.H.text(p))
                    gone = sorted(k for k in a if b.get(k) != a[k])
                    if gone or self.delta[p] == "D":
                        return done("INVALIDATED", "I4", f"kill test changed: {p} ({', '.join(gone[:3]) or 'removed'})")
                    additive.append(p)
        compared.append("I4")
        # I5
        if not (src_b == src_h and self.B.generator == self.H.generator
                and self.B.enums(rel_t) == self.H.enums(rel_t)):
            gb, gh = self.generated(self.B, rel_t, func), self.generated(self.H, rel_t, func)
            if isinstance(gb, str) or isinstance(gh, str):   # a failure is an identity not computed
                return done("UNRESOLVED", "I5", f"generator cannot run: {gb if isinstance(gb, str) else gh}")
            if gb != gh:
                return done("INVALIDATED", "I5", f"generator output differs: {len(gb)} mutants at the basis, {len(gh)} now")
        compared.append("I5")
        # I9
        sb9, sh9 = self.settings
        if sb9 != sh9:
            return done("INVALIDATED", "I9", f"runner settings changed: {', '.join(k for k in I9_NAMES if sb9.get(k) != sh9.get(k))}")
        compared.append("I9")
        if additive:
            ev["additive_test_changes"] = sorted(set(additive))
        # §2.9
        if not self.delta:
            return done("VERIFIED_REUSE")
        fired = self.rules(name, kill, claim, ev)
        if fired:
            return done(*fired)
        return done("VERIFIED_REUSE")

    def generated(self, R, rel: str, func: str) -> list | str:
        def compute():
            try:
                found = R.m.mutants(R.text(rel), func, R.enums(rel))
                out = []
                for d, src in found:
                    got = R.m._root(ast.parse(src), func)
                    out.append([d, ast.unparse(got[0]) if got else "<missing>"])
                return out
            except (SystemExit, Exception) as e:
                return f"{type(e).__name__}: {e}"
        return self.cache(("gen", R.sha, rel, func), compute)

    def option_c(self, name: str, entry: dict, src_b: str, plat: dict) -> str | None:
        """I8: why the pinned Option C ruling does not cover this entry, or None when it does."""
        raws = [_blob(self.root, R.sha, RULING_REL) for R in (self.B, self.H)]
        if any(r is None or _sha(r) != RULING_SHA256 for r in raws):
            return f"{RULING_REL} is absent or not the pinned {RULING_SHA256[:12]}"
        doc = json.loads(raws[1])
        scope = doc["disposition"]["VERIFIED_REUSE"].get(name)
        st = doc["source_transition"]
        if scope is None:
            return "the target is not in the pinned ruling's scope"
        rel = name.split("::")[0]
        prov = _blob(self.root, scope["measured_on"], rel) if _rev(self.root, scope["measured_on"]) else None
        out = scope.get("original_outcome", {})
        checks = [
            (entry.get("source_sha256") == scope["measured_source_sha256"] == st["measured_source_sha256"],
             "recorded source is not the ruling's measured digest"),
            (self.H.m.source_digest(src_b) == scope["current_source_sha256"] == st["current_source_sha256"],
             "basis source is not the ruling's current digest"),
            (entry.get("tree_sha256") == scope["worker_tree_sha256"], "recorded tree is not the ruling's worker tree"),
            (prov is not None and self.H.m.source_digest(prov.decode("utf-8", "replace")) == scope["measured_source_sha256"],
             "the measurement commit's own source is not the measured digest"),
            ([entry.get("mutants"), entry.get("killed"), len(entry.get("survivors") or [])]
             == [out.get("mutants"), out.get("killed"), out.get("survivors")], "outcome is not the ruling's"),
            (plat["family"] == "posix" and plat["flavor"] != "darwin", "platform contradicts the ruling's linux"),
        ]
        return next((why for ok, why in checks if not ok), None)

    def rules(self, name: str, kill: list[str], claim: str, ev: dict) -> tuple | None:
        """§2.9 R4, R5, R6; R0/D2/R1/R2/R3 (or the no-observation default); R8, R7. None: nothing fires."""
        delta = self.delta
        # R4 discovery
        for F in kill:
            d, base = posixpath.dirname(F), posixpath.basename(F)
            hit = [p for p in delta if p != F and p.startswith(d + "/") and posixpath.basename(p) in ("__init__.py", base)]
            if hit:
                return "INVALIDATED", "R4", f"{F} discovers {sorted(hit)[0]} ({delta[sorted(hit)[0]]})"
        # R5 import resolution
        moved = sorted(p for p, s in delta.items() if s in "AD" and p.endswith(".py"))
        if moved:
            for F in kill:
                named = set().union(*(self.modules_named(R, f) for R in (self.B, self.H) for f in self.S(F) if f.endswith(".py")))
                for p in moved:
                    mod = p[:-3].replace("/", ".").removesuffix(".__init__")
                    if any(x == mod or x.startswith(mod + ".") for x in named):
                        return "INVALIDATED", "R5", f"{F} imports {mod}, whose file {p} was {'added' if delta[p] == 'A' else 'removed'}"
        # R6 import-time statements
        code = sorted(p for p in delta if p.endswith(".py"))
        for F in kill:
            for p in (x for x in code if x in self.S(F)):
                c = self.changed(p)
                if isinstance(c, str):
                    return "UNRESOLVED", "R6", c
                if c["module"] != "unchanged":
                    return "INVALIDATED", "R6", f"import-time statements of {p} changed ({c['module']}) in S({F})"
        # R0, D2, R1, R2, R3
        if self.obs is None:
            return "INVALIDATED", "R1", f"no observation of {kill[0] if kill else '<no kill file>'}; R1 cannot be excluded"
        data_tokens: set[str] = set()
        ev["observation"] = {}
        py = f"{sys.version_info.major}.{sys.version_info.minor}"
        for F in kill:
            O = self.obs.get(F)
            if not isinstance(O, dict):
                return "UNRESOLVED", "R0", f"no admissible observation of {F}"
            bad = ("it observed another tree" if O.get("commit") != self.H.sha else
                   "its outcome is not PASS" if O.get("outcome") != "PASS" else
                   "it has no witness" if not O.get("witness") else
                   f"it ran on {O.get('platform')}, the claim is {claim}" if O.get("platform") != claim else
                   f"python {O.get('python')} is not the runner's {py}" if O.get("python") != py else
                   "a process opened the checkout outside the run's tree" if O.get("outside_tree") else None)
            if bad:
                return "UNRESOLVED", "R0", f"no admissible observation of {F}: {bad}"
            ev["observation"][F] = _sha(canonical(O))
            opened = O.get("opened") or {}
            opened = dict(opened) if isinstance(opened, dict) else dict.fromkeys(opened, "data")
            miss = sorted((set(O.get("loaded") or []) | {p for p in opened if p.endswith(".py")}) - self.S(F))
            if miss:
                return "UNRESOLVED", "D2", f"S({F}) misses {miss[0]}"
            ch = O.get("children") or {}
            unseen = (ch.get("unhooked_python") or 0) + (ch.get("other") or 0)
            static = [] if O.get("os_trace") else [w for f in sorted(self.S(F)) if f.endswith(".py")
                                                   for w in R1_UNSEEN if w in self.both(f)]
            if O.get("lost") or O.get("unparsed_lines") or (unseen and not O.get("os_trace")) or static:
                n = unseen + (1 if static or O.get("lost") or O.get("unparsed_lines") else 0)
                return "INVALIDATED", "R1", f"{F} has {n} unobserved processes: any path of the tree may be read or run"
            for p in sorted(delta):
                if opened.get(p) == "data" or (delta[p] == "D" and p in opened):
                    return "INVALIDATED", "R2", f"{F} reads {p} as data" if delta[p] != "D" else f"{F} opened {p}, now removed"
            listed = {SD._norm(x) for x in O.get("listed") or []}
            by = {SD._norm(k): frozenset(v) for k, v in (O.get("listed_by") or {}).items()}
            registry_changed = SD.REGISTRY in delta
            for p in sorted(delta):
                above = [x for x in ("/".join(p.split("/")[:i]) for i in range(len(p.split("/")))) if x in listed]
                if above and not SD._discounted(p, above, by, None if registry_changed else self.listing_changed()):
                    return "INVALIDATED", "R3", f"{F} lists {above[-1] or '.'}, which holds {p}"
            data_tokens |= {w for p, tag in opened.items() if tag == "data" and not p.endswith(".py")
                            for w in _WORD.findall(self.H.text(p) or "")}
        # R8, then R7 (tier S)
        unref = []
        for F in kill if code else ():
            S = self.S(F)
            defs = []
            for p in (x for x in code if x in S):
                c = self.changed(p)
                defs += [(p, q) for q in [*c["names"], *c["removed"]]]
            if not defs:
                continue
            open_sites = [s for f in sorted(S) if f.endswith(".py") for R in (self.B, self.H) for s in self.sites(R, f)
                          if (s[0], s[1], s[3]) not in RESOLVED_SITES]
            if open_sites:
                f, q, line, _ = open_sites[0]
                return "INVALIDATED", "R8", f"S({F}) has a computed-name site at {f}:{line} ({q or '<module>'}): tier S unavailable"
            for p, q in defs:
                b = q.rsplit(".", 1)[-1]
                hits = [sum(self.refs(R, f)[b] for f in S if f.endswith(".py")) - self._defs(R, p, q) for R in (self.B, self.H)]
                if max(hits) > 0 or b in data_tokens:
                    return "INVALIDATED", "I2", f"{p}::{q} changed and is referenced in S({F})"
                unref.append(f"{p}::{q}")
        if unref:
            ev["unreferenced_changes"] = sorted(set(unref))
        return None

    def both(self, f: str) -> str:
        if f not in self._texts:
            self._texts[f] = (self.B.text(f) or "") + "\0" + (self.H.text(f) or "")
        return self._texts[f]

    def _defs(self, R, p: str, q: str) -> int:
        src = R.text(p)
        return self.cache(("defs", R.sha, p), lambda: _qualdefs(src) if src is not None else collections.Counter())[q]


def _live(root: pathlib.Path, H) -> tuple[list[tuple[str, dict]], list[State]]:
    """The entries mutation.check() reads at head, and a state for each phase target with no readable entry."""
    live, bad = [], []
    for phase, rel in H.m.RECORDS.items():
        targets = H.m.PHASE_TARGETS.get(phase)
        if not targets:
            continue
        try:
            raw = _blob(root, H.sha, rel)
            if raw is None:
                raise ValueError("missing")
            doc = json.loads(raw)
            old = set(H.m.superseded(doc, phase))
            entries = [t for t in doc["targets"] if t["target"] not in old]
        except (ValueError, KeyError, TypeError) as e:
            bad += [State(t, "UNRESOLVED", "record", f"{rel} is unreadable: {e}") for t in sorted(targets)]
            continue
        live += [(rel, t) for t in entries]
        seen = {t["target"] for t in entries}
        bad += [State(t, "INVALIDATED", "record", f"{t} has no mutation result in {rel}") for t in sorted(targets) if t not in seen]
    return live, bad


def kill_closure(root, base: str, head: str, kill_file: str) -> frozenset[str]:
    """S(F) (§2.9 D2) at `base` ∪ `head`, for inspection."""
    root = pathlib.Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="aisef-f5-") as tmp:
        H = SD.Rev(root, _rev(root, head), pathlib.Path(tmp))
        B = H if _rev(root, base) == H.sha else SD.Rev(root, _rev(root, base), pathlib.Path(tmp))
        return _Ctx(root, B, H, None).S(kill_file)


def classify(root, base: str = BASE, head: str = "HEAD", *, observations: dict | None = None) -> list[State]:
    """The F5 state of every live target, sorted. Never raises: what cannot be computed is UNRESOLVED."""
    root = pathlib.Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="aisef-f5-") as tmp:
        try:
            return _classify(root, base, head, observations, pathlib.Path(tmp))
        except Exception as e:   # noqa: BLE001  — the engine fails closed, never open
            return [State("<all>", "UNRESOLVED", "engine", f"{type(e).__name__}: {e}")]


def _classify(root, base, head, observations, tmp) -> list[State]:
    try:
        top = S2._git(root, "rev-parse", "--show-toplevel")
    except OSError as e:
        return [State("<all>", "UNRESOLVED", "basis", f"git unavailable: {e}")]
    if top.returncode != 0:
        return [State("<all>", "UNRESOLVED", "basis", "not a git repository")]
    head_sha = _rev(root, head)
    if head_sha is None:
        return [State("<all>", "UNRESOLVED", "basis", f"head {head} is not a commit")]
    try:
        H = SD.Rev(root, head_sha, tmp)
    except SystemExit as e:
        return [State("<all>", "UNRESOLVED", "basis", f"the head's harness cannot be loaded: {e}")]
    live, bad = _live(root, H)
    stop = None
    base_sha = _rev(root, base)
    if S2._git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == b"true":
        stop = ("basis", "shallow clone: the basis history cannot be proven")
    elif base_sha is None:
        stop = ("basis", f"basis commit {base} unavailable")
    elif dirty := _dirty(root, head_sha, H.copy):
        stop = ("dirty", f"dirty tree: {dirty[0]}" + (f" (+{len(dirty) - 1} more)" if len(dirty) > 1 else ""))
    if stop:
        out = [State(t["target"], "UNRESOLVED", *stop, mutants=t.get("mutants") or 0) for _, t in live]
        return sorted(out + [dataclasses.replace(s, state="UNRESOLVED", component=stop[0], reason=stop[1]) for s in bad],
                      key=lambda s: s.target)
    try:
        B = H if base_sha == head_sha else SD.Rev(root, base_sha, tmp)
    except SystemExit as e:
        stop = ("basis", f"the basis harness cannot be loaded: {e}")
        return sorted([State(t["target"], "UNRESOLVED", *stop, mutants=t.get("mutants") or 0) for _, t in live]
                      + [dataclasses.replace(s, state="UNRESOLVED", component=stop[0], reason=stop[1]) for s in bad],
                      key=lambda s: s.target)
    ctx = _Ctx(root, B, H, observations)
    base_entries: dict[str, dict[str, list]] = {}
    out = list(bad)
    for rel in sorted({r for r, _ in live}):
        same = S2.blob(root, B.sha, rel) == S2.blob(root, H.sha, rel)
        base_entries[rel] = {}
        doc = None if same else json.loads(_blob(root, B.sha, rel) or b'{"targets": []}')
        for t in (doc["targets"] if doc is not None else [t for r, t in live if r == rel]):
            base_entries[rel].setdefault(t.get("target"), []).append(t)
    taken: collections.Counter = collections.Counter()
    for rel, t in live:
        cands = base_entries[rel].get(t["target"], [])
        k = taken[rel, t["target"]]
        taken[rel, t["target"]] += 1
        try:
            out.append(ctx.judge(rel, t, cands[k] if k < len(cands) else None))
        except Exception as e:   # noqa: BLE001
            out.append(State(t["target"], "UNRESOLVED", "engine", f"{type(e).__name__}: {e}", mutants=t.get("mutants") or 0))
    return sorted(out, key=lambda s: (s.target, s.evidence.get("record", "")))


def _dirty(root: pathlib.Path, head_sha: str, copy) -> list[str]:
    """COPY paths whose working-tree bytes are not head's, and untracked or ignored files there (`__pycache__` aside:
    the runner leaves it out)."""
    changed = S2._git(root, "diff", "--name-only", "-z", head_sha, "--", *copy).stdout.decode("utf-8", "replace")
    other = S2._git(root, "ls-files", "--others", "-z", "--", *copy).stdout.decode("utf-8", "replace")
    return sorted({p for p in changed.split("\0") + other.split("\0") if p and "__pycache__" not in p.split("/")})


# ------------------------------------------------------------------------------------------------------- report


def report(states: list[State], root, base: str, head: str, observations=None) -> dict:
    root = pathlib.Path(root).resolve()
    counts = {s: {"n": 0, "mutants": 0} for s in STATES}
    by: dict[str, dict] = {}
    plat: collections.Counter = collections.Counter()
    for s in states:
        counts.setdefault(s.state, {"n": 0, "mutants": 0})
        counts[s.state]["n"] += 1
        counts[s.state]["mutants"] += s.mutants
        k = f"{s.state} {s.component}".strip()
        by.setdefault(k, {"n": 0, "mutants": 0})
        by[k]["n"] += 1
        by[k]["mutants"] += s.mutants
        p = s.evidence.get("platform")
        if p:
            plat[f"{p['family'] or 'unknown'}/{p['flavor'] or 'unproven'}" if not p["contradiction"] else "contradictory"] += 1
    me = pathlib.Path(__file__).resolve()
    return {"base": {"rev": base, "sha": _rev(root, base)}, "head": {"rev": head, "sha": _rev(root, head)},
            "generated_by": {"tool": TOOL, "sha256": _sha(_lf(me.read_text(encoding="utf-8")).encode())},
            "observations": None if observations is None else {k: _sha(canonical(v)) for k, v in sorted(observations.items())},
            "counts": counts, "by_component": dict(sorted(by.items())), "platform": dict(sorted(plat.items())),
            "states": [dataclasses.asdict(s) for s in states]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--classify", action="store_true", required=True)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--json", type=pathlib.Path, help="write the state table here (the only write)")
    ap.add_argument("--affected", action="store_true", help="print only INVALIDATED and UNRESOLVED, with reasons")
    a = ap.parse_args(argv)
    begun = time.monotonic()
    states = classify(ROOT, a.base, a.head)
    doc = report(states, ROOT, a.base, a.head)
    if a.json:
        a.json.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if a.affected:
        for s in states:
            if s.state in ("INVALIDATED", "UNRESOLVED"):
                print(f"{s.state:<12} {s.component:<7} {s.target}: {s.reason}")
    else:
        print(f"F5 impact  base {doc['base']['sha']}  head {doc['head']['sha']}")
        for s, c in doc["counts"].items():
            print(f"  {s:<15} {c['n']:>5} targets {c['mutants']:>7} mutants")
        for k, c in doc["by_component"].items():
            print(f"    {k:<26} {c['n']:>5} {c['mutants']:>7}")
        for k, n in doc["platform"].items():
            print(f"  platform {k:<22} {n:>5}")
    print(f"elapsed {time.monotonic() - begun:.1f} s", file=sys.stderr)
    return 0 if all(s.state in ("MEASURED", "VERIFIED_REUSE") for s in states) else 1


if __name__ == "__main__":
    sys.exit(main())
