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
`ruling:<id>@<sha256>` for the owner's Option C targets — and only when the basis commit IS the pinned full v2.2.0
sha (BASE). Any other basis is a calibration run: `calibration@<sha>`, never "v2.2.0-accepted". Every rev is resolved
with `rev-parse --verify --end-of-options <rev>^{commit}`; an abbreviated hex rev that a ref shadows is refused, and
every git child runs with GIT_NO_REPLACE_OBJECTS=1 and no graft file. A failing git command is UNRESOLVED, never an
empty diff or a clean tree. An entry is reused only if the BASIS's own tables (RECORDS, PHASE_TARGETS, SUPERSEDED,
V21_RETIRED) read it (I7); its source digest is checked with the basis's own `source_digest`; worker (W) platform
evidence is read at the basis, from histories whose log and record are their own `<stem>.log`/`<stem>.record.json`.

Observations (`--observations DIR`, validation/v23/observe.py records; an input only — the owner ruling of 2026-11-21
approves the recorder for development, not as a VERIFIED_REUSE authority). `observations` maps a kill file F to its
O(F) (§2.9 D3) as observe.load() returns it. R0 admits O(F) only when observe.verify() finds its witness files are the
bytes recorded and the record is what they derive to, and it is bound to: head (commit), head's kill file bytes, head's
runner tree (`tree_sha256`, mutation._pristine's digest recomputed from git), head's runner (mutation.py) and recorder
(observe.py, which must also be the module the engine re-derives with), a PASS, the claim's family AND the entry's own
flavor (unproven: inadmissible), the entry's own interpreter minor read from its frames (unproven: inadmissible) on
CPython, the runner's environment allowlist (plus PYTHONPATH and the marker; nothing else), and no read of the checkout
outside the tree. Any incompleteness (a missing or changed witness file, lost events, unparsed lines, cut strings,
untraced or unaccounted processes, truncated traces, tracer errors, fd-relative access, a process that did not exit
normally under the audit backend) is R1. With `observations=None` R0-R3 cannot be excluded: a target is INVALIDATED
("no observation of F; R1 cannot be excluded") whenever Δ is not empty, and Δ = ∅ gives VERIFIED_REUSE. Tier R (E_full)
is not available in this increment.

The static boundary holds with or without observations: an observed read set alone never yields reuse. Besides R4-R6
and R8 over S(F), R2 also fires, before any observation, for a Δ path some file of S(F) names by a literal path (string
constants only: one constant, consecutive constants joined as a path, a parent directory and its name, a listed
directory, a directory constant) or that holds, as whole components at any depth, the literal part of a path
construction (`/`, `+`, os.path.join, Path(...), joinpath, f-strings, after any non-literal anchor; one level of names
bound to a literal path substituted) — a mutant's branch may read it although the unmutated run did not. R5 judges a
directory that appears or vanishes (a namespace package) like a module file; with observations, any open R8 site in
what F ran refuses tier S for any Δ ≠ ∅ (a computed import on a mutant's branch may load a file S(F) does not hold).
An observed lookup of a path whose existence or kind (file / directory / none) differs between basis and head is R2
too; observed paths are compared case- and normalization-folded.

Declared limitations (§2.7, §2.9 residual):
- C code that reads tree files is seen only through os_trace; a SIGKILLed recorder can lose its `lost` count.
- Hash-only reads (kernel_digest, mechanism_digest) are data reads; no DIGEST-READ discount exists.
- Tamper detection (I7) is anchored to git history: it proves the entry equals what was committed, not who measured.
- Legacy env is unbound (runner-1 imports ran with TIMEOUT 120, before ENV_KEEP/SETTLE_S); `posix` means measured on
  a POSIX host, not killed on every POSIX flavor; row evidence needs tails that keep their traceback frames.
- Before the basis, legacy records carry no kill-file, generator or platform identity (no retro-tagging).
- RESOLVED_SITES is empty: any dynamic site (R8) in S(F) makes tier S unavailable for that kill file.
- A path built with no literal directory part (`ROOT / name`, a parameter, `"%s" % x`, `str.format`, `"/".join`) or
  through more than one level of names is not bounded statically: only the observation sees it, and only for the
  unmutated run (docs/v2.3/amendments/A3-OBSERVE-SOUNDNESS.md).
- S(F) literal naming (D2 b) is the static rule of v21_snapshot_delta._info/_names plus whole-constant directories
  of two or more components; data a kill file reaches by other means is R2/R3's (observed), never S(F)'s.
- R5-R8 judge Δ ∩ S(F) (the frozen §2.9 letter; W1-DESIGN Amendment A1's narrowing is withdrawn) plus what an
  observation saw loaded or load-opened. Cost: one new or changed tests/v2 file re-opens every target whose S(F)
  reaches registry's TESTS_V2, i.e. every target that passes I6.
- R6 also fires when the layout of a Δ file's module code differs in any way: the exact text of every statement
  outside function bodies (module level, class bodies, compound statements), each one's start line, and the full
  text, in order, of every name defined more than once in one module or class scope (the last one binds;
  reach.changed() compares a name's defs as a sorted multiset). A function-body-only change of the same line count
  stays with I1 / R7.
- I4 "additive" is only new TestCase classes made of plain test_* methods; any other new top-level segment of a
  tests/ file in S(F) (load_tests, setUpModule, a fixture, an import, a module statement) is INVALIDATED (I4).
Only VERIFIED_REUSE carries an acceptance basis, and only when it rests on no observation: a reuse that needed one
(Δ ≠ ∅) carries `observation:<sha256 of the observation digests>@<basis>` and evidence.authority "none" (owner ruling
2026-11-21). Every other state names the run's basis commit as evidence.run_base.
Read-only: git and the repository; the only write is --json OUT (and a temporary extraction of each commit's
aisef2/ and validation/v2/, v21_snapshot_delta.Rev, removed afterwards).
"""

from __future__ import annotations

import argparse
import ast
import bisect
import collections
import concurrent.futures
import contextlib
import dataclasses
import functools
import hashlib
import json
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as S2  # noqa: E402  (closure, blob, _git: frozen, called)
from validation.qualification import v21_snapshot_delta as SD  # noqa: E402  (Rev, _segments, _info, _names, ...)
from validation.v21 import reach  # noqa: E402  (changed(): own code vs import-time statements)
from validation.v23 import observe as OBS  # noqa: E402  (verify(): an observation's witness and derivation)

TOOL = "validation/v23/impact.py"
STATES = ("MEASURED", "VERIFIED_REUSE", "INVALIDATED", "UNRESOLVED")
#: v2.2.0, in full: the owner-approved release gate accepted every live entry here (the only "v2.2.0-accepted" basis)
BASE = "da3ea33f3b695aaca73e87a704145a0193aced23"
#: rules switched off — always empty; tests patch it to show that each rule is load-bearing (N14)
_OFF: frozenset = frozenset()
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
#: what an observation-based reuse carries instead of an acceptance basis (owner ruling 2026-11-21)
OBSERVATION_AUTHORITY = ("none: the F5 recorder is approved for development only, not as a VERIFIED_REUSE authority "
                         "(owner ruling 2026-11-21)")
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


class Run(list):
    """classify()'s states, sorted, with the revs it was given and the shas it resolved them to ONCE, at the start of
    the run (None: not resolved). report() reads these and never resolves a name again, so a ref that moves during a
    run cannot bind the states to a commit they were not computed on."""
    base: str = ""
    head: str = ""
    base_sha: str | None = None
    head_sha: str | None = None


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


class GitError(RuntimeError):
    """A git command failed: what it would have said is unknown (never an empty diff or a clean tree)."""


def _git(root: pathlib.Path, *args: str) -> bytes:
    r = S2._git(root, *args)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args[:3])} failed (rc {r.returncode}): {r.stderr.decode('utf-8', 'replace')[:200]}")
    return r.stdout


@contextlib.contextmanager
def _pinned_git(tmp: pathlib.Path):
    """Every git child (the frozen s2/v21_snapshot_delta calls included: they inherit os.environ) ignores replace
    refs and grafts: the bytes of a commit are what its sha names."""
    pin = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_GRAFT_FILE": str(tmp / "no-grafts")}   # a file never created
    saved = {k: os.environ.get(k) for k in pin}
    os.environ.update(pin)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _blob(root: pathlib.Path, sha: str, path: str) -> bytes | None:
    """`path`'s bytes at commit `sha` (never cached: records reach 100 MB)."""
    if S2.blob(root, sha, path) is None:
        return None
    return _git(root, "cat-file", "blob", f"{sha}:{path}")


def _rev(root: pathlib.Path, rev: str) -> str | None:
    r = S2._git(root, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}")
    return r.stdout.decode().strip() if r.returncode == 0 and r.stdout.strip() else None


def _shadowed(rev: str, sha: str) -> str | None:
    """Why `rev` does not name the commit it spells: an abbreviated sha that a ref of the same name shadows."""
    if re.fullmatch(r"[0-9a-fA-F]{4,40}", rev) and not sha.startswith(rev.lower()):
        return f"{rev} is shadowed by a ref: it resolves to {sha}, not to the commit it abbreviates"
    return None


def _on(rule: str) -> bool:
    return rule not in _OFF


def _fold(p: str) -> str:
    """A path as the coarsest volume compares it: NFKC, case folded, format characters (HFS+'s ignorables) dropped.
    Two names one supported volume takes for the same (exact on ext4; case- and normalization-insensitive on APFS, ext4
    casefold, HFS+) fold alike. In a MEMBERSHIP test (is any spelling of p among what was read or listed) folding can
    only match more paths. Never compare two folded ANSWERS for equality: two different spellings fold alike, so a
    change between them would be hidden (Review 2, R2-1); the lookup check compares `_Ctx.spellings` instead."""
    p = "".join(c for c in unicodedata.normalize("NFKC", p) if unicodedata.category(c) != "Cf")
    return unicodedata.normalize("NFKC", p.casefold())


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
    the module-level statements — their exact source texts in statement order (two defs of one name swapped change
    which one binds). None: unparsable, or the target is not there."""
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
    return [segs[i][1] for i in sorted(keep)]


def segment_texts(src: str | None) -> dict[str, str]:
    """I4 (§2.2): top-level name -> the exact source texts of its segments; the docstring, imports and every other
    statement under one bracketed name each."""
    out: dict[str, str] = {}
    try:
        segs = segments(src) if src is not None else []
    except SyntaxError:
        return {"<unparsable>": src or ""}
    for x, text, _ in _keyed(segs):
        out[x] = out.get(x, "") + text
    return out


def _keyed(segs):
    """(I4 segment name, text, node) of each top-level statement: its names, else `<docstring>` / `<other statements>`."""
    for i, (names, text, n) in enumerate(segs):
        doc = i == 0 and isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
        for x in names or ("<docstring>" if doc else "<other statements>",):
            yield x, text, n


def _test_class(n: ast.stmt) -> bool:
    """A plain `unittest.TestCase` subclass whose body is only test_* methods that evaluate nothing where they stand
    (no decorator, default, annotation or type parameter)."""
    def plain(f) -> bool:
        if not isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef):
            return False
        a = f.args
        return (f.name.startswith("test_") and not f.decorator_list and not a.defaults and not any(a.kw_defaults) and f.returns is None
                and not getattr(f, "type_params", None)
                and not any(x.annotation for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg) if x))
    return (isinstance(n, ast.ClassDef) and not n.decorator_list and not n.keywords and not getattr(n, "type_params", None)
            and [ast.unparse(x) for x in n.bases] in (["unittest.TestCase"], ["TestCase"]) and all(map(plain, n.body)))


def not_additive(old: set[str], src: str | None) -> list[str]:
    """I4 (§2.2): the top-level segments of `src` that are new since the segment names `old` and are not a plain
    TestCase class of test_* methods. A load_tests, setUpModule or tearDownModule def, a class with setUpClass, setUp,
    tearDown, __init_subclass__ or an attribute, an import or a module statement decides which tests run and what
    they see: never an additive test change."""
    try:
        segs = segments(src) if src is not None else []
    except SyntaxError:
        return ["<unparsable>"]
    return sorted({k for k, _, n in _keyed(segs) if k not in old and not _test_class(n)})


def _start(n: ast.stmt) -> tuple[int, int]:
    """(line, UTF-8 column) where statement `n`'s text starts, its decorators included."""
    if decs := getattr(n, "decorator_list", None):
        d = min(decs, key=lambda x: (x.lineno, x.col_offset))
        return d.lineno, max(d.col_offset - 1, 0)   # the "@"
    return n.lineno, n.col_offset


def layout(src: str) -> tuple[list[tuple[int, bytes]], dict[str, list[bytes]]]:
    """R6 (D4): ([(start line, exact bytes with every function BODY cut out)] of every statement outside function
    bodies — module level, class bodies, compound statements —, {scope-qualified name: [exact bytes of each def or
    class of it, in order]} for every name defined more than once in one module or class scope)."""
    text = _lf(src)
    data, tree = text.encode("utf-8"), ast.parse(text)
    lines = data.splitlines(keepends=True)
    at = [0]
    for x in lines:
        at.append(at[-1] + len(x))
    cuts = []
    for f in ast.walk(tree):
        if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef):
            line, col = _start(f.body[0])
            col = col if lines[line - 1][:col].strip() else 0   # a body on its own lines: cut whole lines
            cuts.append((at[line - 1] + col, at[f.end_lineno - 1] + f.end_col_offset))
    kept: list[tuple[int, int]] = []
    for a, z in sorted(cuts):
        if not kept or a >= kept[-1][1]:   # a nested def's body lies inside its enclosing body
            kept.append((a, z))

    def cut(a: int, z: int) -> bytes:
        out, i = [], a
        for c0, c1 in kept:
            if a <= c0 and c1 <= z:
                out += [data[i:c0], b"\0"]
                i = c1
        return b"".join([*out, data[i:z]])

    seq: list[tuple[int, bytes]] = []
    defs: dict[str, list[bytes]] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for n in ast.iter_child_nodes(node):
            if isinstance(n, ast.excepthandler | ast.match_case):
                walk(n, prefix)
            if not isinstance(n, ast.stmt):
                continue
            line = _start(n)[0]
            a, z = at[line - 1], at[n.end_lineno - 1] + n.end_col_offset
            seq.append((line, cut(a, z)))
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                defs.setdefault(prefix + n.name, []).append(data[a:z])
            if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                walk(n, prefix + n.name + "." if isinstance(n, ast.ClassDef) else prefix)
    walk(tree, "")
    return seq, {k: v for k, v in defs.items() if len(v) > 1}


def layout_changed(a: str, b: str) -> str | None:
    """R6 (D4): why the module code of two versions of one file is not laid out the same, or None."""
    (sa, da), (sb, db) = layout(a), layout(b)
    if sa != sb:
        i = next((i for i, (x, y) in enumerate(zip(sa, sb, strict=False)) if x != y), min(len(sa), len(sb)))
        return f"the module-level statements changed at line {(sb[i] if i < len(sb) else sa[i])[0]}"
    k = next((k for k in sorted(set(da) | set(db)) if da.get(k) != db.get(k)), None)
    return f"the definitions of {k} changed order or text: another one binds" if k else None


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
#: name-taking import entry points and loaders: a site unless every argument (module name AND file path) is a literal
#: and the name is absolute; referenced other than by a call, or named by a string constant, always (Review 2, R2-2)
_DYN_IMPORT = {"import_module", "spec_from_file_location", "SourceFileLoader", "SourcelessFileLoader",
               "ExtensionFileLoader", "run_path", "run_module", "find_spec", "find_module", "find_loader", "get_loader",
               "resolve_name", "module_from_spec", "exec_module", "load_module", "load_source", "spec_from_loader",
               "zipimporter", "loadTestsFromName", "loadTestsFromNames"}
#: a site wherever the name occurs: an import in any form, a test walk, the import path's hooks
_DYN_ANY = {"__import__", "discover", "meta_path", "path_hooks", "path_importer_cache"}
_DYN_BUILTIN = {"exec", "eval", "compile", "globals", "vars", "locals", "dir"}
#: modules whose members hide a site when bound under another name (`as`), or are read by getattr
_LOADERS = {"importlib", "pkgutil", "runpy", "zipimport", "imp", "builtins", "sys", "unittest", "subprocess", "os",
            "asyncio", "pty"}
#: a launch runs code S(F) need not hold (a script, `-c` text, stdin, another PYTHONPATH): always a site (R2-2)
_SPAWNERS = ("subprocess", "os", "asyncio", "pty")
_LAUNCH = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput", "system", "popen",
           "posix_spawn", "posix_spawnp", "create_subprocess_exec", "create_subprocess_shell"}


def _launch(owner, name) -> bool:
    """`owner.name(...)` starts a process (os.exec*/spawn*, subprocess.*, asyncio.create_subprocess_*, pty.spawn)."""
    name = str(name)
    return owner in _SPAWNERS and (name in _LAUNCH or name.startswith(("exec", "spawn"))) and (
        owner != "asyncio" or name.startswith("create_subprocess"))


def _module_of(p: str) -> str | None:
    """The dotted module a tree file provides: `x.py`, `x/__init__.py`, or an extension/bytecode module `x.*.so`,
    `x.pyd`, `x.dylib`, `x.pyc` (an extension module takes precedence over a source module of the same name)."""
    d, base = posixpath.split(p)
    if base.endswith(".py"):
        stem = base[:-3]
    elif base.endswith((".so", ".pyd", ".dylib", ".pyc")) and "__pycache__" not in p.split("/"):
        stem = base.split(".", 1)[0]
    else:
        return None
    return f"{d}/{stem}".lstrip("/").replace("/", ".").removesuffix(".__init__")


def _literal(x: ast.AST) -> bool:
    return isinstance(x, ast.Constant) and isinstance(x.value, str)


def dynamic_sites(src: str, path: str) -> list[tuple[str, str, int, str]]:
    """R8: (file, enclosing qualname, line, ast.dump) of every computed-name site: a call that may load or run code by
    a name or path not written as a literal, and every way of reaching such a call under another name (Review 2,
    R2-2: the spellings are enumerated; an unlisted one is the residual R8-SPELLINGS)."""
    out = []
    tree = ast.parse(_lf(src))
    called = {id(c.func) for c in ast.walk(tree) if isinstance(c, ast.Call)}

    def visit(node, qual):
        for ch in ast.iter_child_nodes(node):
            q = qual
            if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                q = f"{qual}.{ch.name}" if qual else ch.name
            hit = False
            if isinstance(ch, ast.Call):
                f = ch.func
                name = getattr(f, "attr", None) or getattr(f, "id", None)
                v = getattr(f, "value", None)
                owner = getattr(v, "id", None) or getattr(v, "attr", None)
                args = [*ch.args, *(k.value for k in ch.keywords)]
                if name in _DYN_ATTR:
                    i = _DYN_ATTR[name]
                    hit = len(ch.args) <= i or not _literal(ch.args[i]) or getattr(ch.args[0], "id", None) in _LOADERS
                elif name in _DYN_IMPORT or owner == "resources":   # importlib.resources imports the package it names
                    hit = not ch.args or not all(_literal(x) for x in args) or ch.args[0].value.startswith(".")
                elif (isinstance(f, ast.Name) and name in _DYN_BUILTIN) or name == "getmembers" or owner == "runpy" \
                        or (owner in ("pickle", "marshal") and name in ("load", "loads")):
                    hit = True
                elif _launch(owner, name):
                    hit = True
            elif isinstance(ch, ast.Name | ast.Attribute):
                name, v = (ch.id, None) if isinstance(ch, ast.Name) else (ch.attr, ch.value)
                hit = (name in _DYN_ANY or (name in _DYN_IMPORT and id(ch) not in called)
                       or (name == "path" and getattr(v, "id", None) == "sys")
                       or (id(ch) not in called and _launch(getattr(v, "id", None), name)))
            elif isinstance(ch, ast.Constant):
                hit = isinstance(ch.value, str) and ch.value in _DYN_IMPORT | _DYN_ANY
            elif isinstance(ch, ast.Import | ast.ImportFrom):
                mod = getattr(ch, "module", None) or ""
                hit = any(
                    a.name == "*" or (a.asname and (mod or a.name).split(".")[0] in _LOADERS)
                    or mod.startswith("importlib.resources") or _launch(mod.split(".")[0], a.name)
                    or (mod == "sys" and a.name in {"path"} | _DYN_ANY) for a in ch.names)
            elif isinstance(ch, ast.Subscript) and isinstance(ch.value, ast.Attribute) and ch.value.attr == "__dict__":
                hit = True
            if hit:
                out.append((path, qual, getattr(ch, "lineno", 0), ast.dump(ch)))
            visit(ch, q)
    visit(tree, "")
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


_PYVER = re.compile(r"[/\\][Pp]ython(3\.\d+|3\d\d?)[/\\]")


def python_of(entry: dict) -> str | None:
    """The interpreter minor version the entry's own traceback frames name (`.../python3.N/...`, or a Windows
    `\\Python3NN\\`): None when they name none, or more than one."""
    found = {v if "." in v else f"{v[0]}.{v[1:]}" for t in _tails(entry) for v in _PYVER.findall(t)}
    return min(found) if len(found) == 1 else None


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
    """W: canonical-entry digest -> [(history, families, flavors)] over every mutation-workers history committed at
    `sha` (the basis, for legacy entries: a history added later proves nothing about a measurement accepted there)
    whose log and record are its own siblings `<stem>.log` / `<stem>.record.json`, are the bytes it recorded, and
    carry R markers; and the refused histories."""
    out: dict[str, list] = {}
    refused = []
    for p in sorted(S2._files(root, sha)):
        if not (p.startswith("closure-evidence/") and "/mutation-workers/" in p and p.endswith(".history.json")):
            continue
        stem = p.removesuffix(".history.json")
        try:
            h = json.loads(_blob(root, sha, p))
            if h["log"]["path"] != f"{stem}.log" or (h.get("record") and h["record"]["path"] != f"{stem}.record.json"):
                raise ValueError("its log or record is not its own sibling file")
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


def tree_digest(root: pathlib.Path, sha: str, copy, records) -> str | None:
    """mutation._pristine's digest of the runner tree commit `sha` gives: sha256 over (path, sha256 of the bytes) of
    every file under a COPY root, the runner's records and `__pycache__` left out, in pathlib's order (by parts), from
    git's bytes. None when those are not what a copy of a clean checkout holds (a symlink or a submodule under COPY)."""
    rec = {posixpath.normpath(r) for r in records}
    items = []
    for line in _git(root, "ls-tree", "-r", "-z", "--full-tree", sha, "--", *copy).split(b"\0"):
        if not line:
            continue
        meta, _, path = line.decode("utf-8", "surrogateescape").partition("\t")
        mode, typ, obj = meta.split()
        if "__pycache__" in path.split("/") or path in rec:
            continue
        if typ != "blob" or mode not in ("100644", "100755"):
            return None
        items.append((path, obj))
    h = hashlib.sha256()
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as cat:
        for path, obj in sorted(items, key=lambda x: x[0].split("/")):
            cat.stdin.write(obj.encode() + b"\n")
            cat.stdin.flush()
            head = cat.stdout.readline().split()
            if len(head) != 3 or head[1] != b"blob":
                raise GitError(f"git cat-file: {obj} is not a blob")
            data = cat.stdout.read(int(head[2]))
            cat.stdout.read(1)
            h.update(path.encode("utf-8", "surrogateescape") + b"\0" + hashlib.sha256(data).digest())
        cat.stdin.close()
        if cat.wait() != 0:
            raise GitError("git cat-file --batch failed")
    return h.hexdigest()


def string_constants(tree: ast.AST) -> list[str]:
    """Every str constant of a parsed file but the docstrings (no run reads a docstring as a path)."""
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


_JOIN = {"join", "joinpath", "Path", "PurePath", "PosixPath", "PurePosixPath", "WindowsPath", "PureWindowsPath"}


def _operands(n: ast.AST) -> list | None:
    """A path construction flattened to [(part, separator before it)]: "/" for `/`, os.path.join, Path(...) and
    joinpath; "" for `+` and f-string parts (a walrus stands for its value). None when `n` is not one."""
    if isinstance(n, ast.NamedExpr):
        return _operands(n.value)
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div | ast.Add):
        sep = "/" if isinstance(n.op, ast.Div) else ""
        right = _operands(n.right) or [(n.right, "")]
        return (_operands(n.left) or [(n.left, "")]) + [(right[0][0], sep)] + right[1:]
    if isinstance(n, ast.JoinedStr):
        return [(v, "") for v in n.values]
    if isinstance(n, ast.Call) and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) in _JOIN:
        head = [(n.func.value, "")] if getattr(n.func, "attr", None) == "joinpath" else []
        return head + [(a, "/" if head or i else "") for i, a in enumerate(n.args)]
    return None


def _literal_text(ops: list, bound: dict) -> tuple[str, bool] | None:
    """(the literal text of a construction after its leading non-literal parts — an anchor such as ROOT —, whether a
    computed part follows it); None when no literal part follows the anchor."""
    text, started = "", False
    for node, sep in ops:
        node = node.value if isinstance(node, ast.NamedExpr) else node
        lit = (node.value if isinstance(node, ast.Constant) and isinstance(node.value, str)
               else bound.get(node.id) if isinstance(node, ast.Name) else None)
        if lit is not None:
            text += (sep if started else "") + lit
            started = True
        elif started:
            return (text if sep == "/" else text.rsplit("/", 1)[0] if "/" in text else ""), True
    return (text, False) if started else None


def _bindings(tree: ast.AST):
    """(target, value) of every binding of a value: `=` (each target, a tuple unpacked pairwise), annotated `:=`-less
    and augmented assignments, and the walrus."""
    def pairs(t, v):
        if isinstance(t, ast.Tuple | ast.List) and isinstance(v, ast.Tuple | ast.List) and len(t.elts) == len(v.elts):
            for x, y in zip(t.elts, v.elts, strict=True):
                yield from pairs(x, y)
        else:
            yield t, v
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                yield from ((x, y, len(n.targets) == 1) for x, y in pairs(t, n.value))
        elif isinstance(n, ast.AnnAssign | ast.NamedExpr) and n.value is not None:
            yield n.target, n.value, True
        elif isinstance(n, ast.AugAssign):
            yield n.target, n.value, False


def computed_dirs(tree: ast.AST) -> set[str]:
    """R2 (static): the literal text of every path construction in one file, after its leading non-literal parts — an
    anchor such as ROOT, `Path(m.__file__).parent`, a parameter — (`ROOT / "aisef2" / name`, `f"{ROOT}/docs/{x}.json"`,
    `os.path.join(HERE, "fixtures", n)`, `Path(x.__file__).parent / "data" / "one.txt"`, `DATA / n` where
    `DATA = ROOT / "aisef2"`; the text up to the first computed part): any file whose path holds that text as whole
    components, at any depth, may be the one a run reads — the anchor may be any directory. A name bound to a literal
    path (`=`, an annotated assignment, the walrus, a tuple unpacked pairwise; one level, in either order) is
    substituted; a literal path bound any other way (an attribute, several targets, `+=`) counts as such a text when
    it is a construction or a constant of two or more components."""
    bound: dict[str, str] = {}
    loose: set[str] = set()
    for _ in range(2):   # names bound to a literal path (one level, in either order)
        for t, v, single in _bindings(tree):
            ops = _operands(v)
            got = ((v.value, False) if isinstance(v, ast.Constant) and isinstance(v.value, str) else
                   _literal_text(ops, bound) if ops else None)
            if not got or not (d := SD._norm(got[0])):
                continue
            if single and isinstance(t, ast.Name) and not got[1]:
                bound[t.id] = d
            elif ops is not None or "/" in d:   # a construction, or a constant of two or more components
                loose.add(d)
    out = set(loose)
    for n in ast.walk(tree):
        if (ops := _operands(n)) and (got := _literal_text(ops, bound)) and (d := SD._norm(got[0])):
            out.add(d)
    return out


def _holds(p: str, text: str) -> bool:
    """`p` holds `text` as whole consecutive components (folded): text "data/one.txt" is held by aisef2/data/one.txt
    and by x/data/one.txt/y."""
    return f"/{_fold(text)}/" in f"/{_fold(p)}/"


# ------------------------------------------------------------------------------------------------- the engine


class _Ctx:
    def __init__(self, root: pathlib.Path, B, H, observations):
        self.root, self.B, self.H, self.obs = root, B, H, observations
        self.label = "v2.2.0-accepted" if B.sha == BASE else "calibration"   # D2: only the pinned full sha
        self.copy = tuple(H.copy)
        self.delta = self._delta()
        self.settings = (settings_digest(B.text(MUTATION_REL)), settings_digest(H.text(MUTATION_REL)))
        self._S: dict = {}
        self._c: dict = {}
        self._listing = None
        self._texts: dict = {}

    @functools.cached_property
    def workers(self) -> dict:
        return workers_at(self.root, self.B.sha)[0]   # legacy entries: W evidence as committed at the basis

    def _in_copy(self, p: str) -> bool:
        return any(p == c or p.startswith(c + "/") for c in self.copy)

    @functools.cached_property
    def head_tree(self) -> str | None:
        """R0: the digest of head's runner tree (mutation._pristine's rule, from git)."""
        return tree_digest(self.root, self.H.sha, self.H.copy, self.H.m.RECORDS.values())

    def blob_sha(self, path: str) -> str | None:
        return self.cache(("blobsha", path), lambda: _sha(b) if (b := _blob(self.root, self.H.sha, path)) is not None
                          else None)

    def spellings(self, R, p: str) -> frozenset:
        """R2: every (exact path, "file" or "dir") of commit R's runner tree that folds as `p` does ("" is the tree;
        a dir is a path a file lies under). When these sets are equal at basis and head, a lookup of p gets one answer
        at both on any volume whose name equivalence the fold covers. One folded kind compared would not see a
        directory renamed to another spelling that folds alike (Review 2, R2-1)."""
        def index():
            out = collections.defaultdict(set)
            for f in self.copy_files(R):
                parts = f.split("/")
                out[_fold(f)].add((f, "file"))
                for k in range(len(parts)):
                    out[_fold("/".join(parts[:k]))].add(("/".join(parts[:k]), "dir"))
            return out
        return frozenset(self.cache(("spellings", R.sha), index).get("" if p in ("", ".") else _fold(p), ()))

    def admissible(self, F: str, O: dict, claim: str, plat: dict, entry_py: str | None) -> tuple[str | None, list]:
        """R0: why O(F) is not admissible for an entry measured on `plat` with interpreter `entry_py`, or None; and
        R1: what its witness lacks (observe.verify)."""
        refused, gaps = self.cache(("verify", F), lambda: OBS.verify(O))
        kf, p, tc = O.get("kill_file") or {}, O.get("platform") or {}, O.get("toolchain") or {}
        m = self.H.m
        env, given = set(O.get("env") or {}), {*m._FRESH, m.TOKEN, "PYTHONPATH", OBS.MARK}
        allowed = given | set(m.ENV_KEEP)
        checks = (
            (O.get("format") == OBS.FORMAT, "it is not an observation record"),
            (refused is None, refused),
            (O.get("commit") == self.H.sha, f"it observed another tree: commit {O.get('commit')} is not head"),
            (kf.get("path") == F and kf.get("sha256") == self.blob_sha(F), "the kill file it ran is not head's bytes"),
            (O.get("tree_sha256") is not None and O.get("tree_sha256") == self.head_tree,
             "its tree_sha256 is not head's runner tree"),
            (O.get("runner_sha256") == self.blob_sha(MUTATION_REL), "it was not run by head's runner"),
            (O.get("observe_sha256") == self.blob_sha(OBS.TOOL) == OBS.own_sha256(),
             "it was not recorded by head's recorder (or the engine's recorder is not head's)"),
            (O.get("outcome") == "PASS", f"its outcome is not PASS ({O.get('outcome')})"),
            (p.get("family") == claim, f"it ran on {p.get('family')}, the claim is {claim}"),
            (claim != "posix" or plat.get("flavor") is not None, "the entry's own flavor is unproven"),
            (p.get("flavor") == plat.get("flavor"),
             f"it ran on {p.get('flavor')}, the entry was measured on {plat.get('flavor')}"),
            (entry_py is not None, "the entry's own interpreter is unproven"),
            (O.get("python") == entry_py and tc.get("implementation") == "cpython",
             f"python {O.get('python')} ({tc.get('implementation')}) is not the entry's CPython {entry_py}"),
            (given <= env <= allowed, f"its environment is not the runner's: {sorted((given - env) | (env - allowed))}"),
            (not O.get("outside_tree"), "a process opened the checkout outside the run's tree"),
        )
        return next((why for ok, why in checks if not ok), None), gaps

    def named(self, F: str) -> dict[str, str]:
        """R2 (static): the Δ paths a file of S(F) names by a literal path or reaches by a computed one."""
        def compute():
            out: dict[str, str] = {}
            for g in sorted(x for x in self.S(F) if x.endswith(".py") and self._in_copy(x)):
                for R in (self.B, self.H):
                    for p, how in self._names(R, g).items():
                        out.setdefault(p, f"{g} names it by {how}")
            return out
        return self.cache(("named", F), compute)

    def _names(self, R, g: str) -> dict[str, str]:
        def compute():
            src = R.text(g)
            if src is None:
                return {}
            try:
                tree = ast.parse(_lf(src))
            except SyntaxError:
                return dict.fromkeys(self.delta, "an unparsable file")
            consts = string_constants(tree)
            short = frozenset(SD._norm(c) for c in consts if c and len(c) < 300 and "\n" not in c
                              and not any(w in c for w in SD._WILD))
            info = ("\n".join(consts), short, SD._info(self.root, R.sha, g)[2])
            up = g.split("/")
            anchors = sorted({"/".join(up[:k]) for k in range(len(up))})
            dirs = sorted(computed_dirs(tree))
            out = {}
            for p in self.delta:
                if p == g:
                    continue
                how = SD._names(info, g, p)
                under = [d for d in short if "/" in d for a in anchors if p.startswith((f"{a}/{d}" if a else d) + "/")]
                how = how or (f"a directory constant {under[0]!r}" if under else None)
                comp = [d for d in dirs if _holds(p, d)]
                how = how or (f"a path construction holding {comp[0]!r}" if comp else None)
                if how:
                    out[p] = how
            return out
        return self.cache(("names", R.sha, g), compute)

    def _delta(self) -> dict[str, str]:
        """D1: path -> A/D/M, every path under a COPY root added, removed, whose LF-sha256 differs, or whose mode
        differs (the runner's copy keeps modes)."""
        if self.B.sha == self.H.sha:
            return {}
        raw = _git(self.root, "diff", "--raw", "--no-renames", "-z", self.B.sha, self.H.sha, "--",
                   *self.copy).decode("utf-8", "replace").split("\0")
        out = {}
        for meta, path in zip(raw[0::2], raw[1::2], strict=False):
            mode_a, mode_b, *_, status = meta.lstrip(":").split()
            if status[:1] == "M" and mode_a == mode_b:   # a mode change is a change: the runner copies modes
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

    def _dotted(self, R, g: str) -> set[str]:
        """D2 (c): module files named by dotted import strings in the .py file `g`."""
        def compute():
            files, out = S2._files(self.root, R.sha), set()
            for c in SD._info(self.root, R.sha, g)[1]:
                m = _DOTTED.match(c)
                if m and m[1].split(".")[0] in S2.ROOTS:
                    parts = m[1].split(".")
                    out.update(f for k in range(2, len(parts) + 1) if (f := S2._module_file(files, ".".join(parts[:k]))))
            return out
        return self.cache(("dotted", R.sha, g), compute)

    def _literal(self, R, g: str) -> set[str]:
        """D2 (b): COPY paths the .py file `g` names (v21_snapshot_delta._names), and every file under a directory it
        names by one whole constant of two or more components."""
        def compute():
            info = SD._info(self.root, R.sha, g)
            text, consts, calls = info
            files = self.copy_files(R)
            out = {p for p in files if p != g and (p.rsplit("/", 1)[-1] in text or calls) and SD._names(info, g, p)}
            up = g.split("/")
            for c in (c for c in consts if "/" in c):
                for a in {"/".join(up[:k]) for k in range(len(up))}:
                    d = f"{a}/{c}" if a else c
                    i = bisect.bisect_left(files, d + "/")
                    while i < len(files) and files[i].startswith(d + "/"):
                        out.add(files[i])
                        i += 1
            return out
        return self.cache(("literal", R.sha, g), compute)

    def _discovery(self, R, F: str) -> list[str]:
        """D2 (d): every __init__.py under F's directory and every file there with F's basename (`-s dirname(F)`)."""
        d, name = posixpath.dirname(F), posixpath.basename(F)
        return [p for p in S2._files(self.root, R.sha) if p.startswith(d + "/") and posixpath.basename(p) in ("__init__.py", name)]

    def _grow(self, R, out: set[str], todo: list[str], literal: bool) -> set[str]:
        files = S2._files(self.root, R.sha)
        while todo:
            f = todo.pop()
            if f in out or f not in files:
                continue
            new = (set(S2.closure(self.root, R.sha, (f,))) | {f}) - out if f.endswith(".py") else {f}
            out |= new
            for g in sorted(x for x in new if x.endswith(".py") and self._in_copy(x)):
                todo += [x for x in (self._dotted(R, g) | (self._literal(R, g) if literal else set())) if x not in out]
        return out

    def S(self, F: str) -> frozenset[str]:
        """S(F) at basis ∪ now (§2.9 D2): s2 closure, literal paths (D2 b), dotted import strings (D2 c) and the
        discovery set (D2 d), to a fixpoint. R4-R8, I4, the D2 check and the R1 scan all read it."""
        if F not in self._S:
            self.prefetch()
            self._S[F] = frozenset(set().union(*(self._grow(R, set(), [F, *self._discovery(R, F)], True)
                                                 for R in (self.B, self.H))))
        return self._S[F]

    def prefetch(self) -> None:
        """Every s2.closure the import-reached parts need, in parallel (each call runs one git show per file it
        visits; the frozen function is called, never changed)."""
        if self._c.get("prefetched"):
            return
        self._c["prefetched"] = True
        jobs = sorted({(R.sha, f) for R in (self.B, self.H) for F in {f for k in self.H.m.TARGETS.values() for f in k}
                       for f in [F, *self._discovery(R, F)] if f.endswith(".py") and f in S2._files(self.root, R.sha)})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda j: S2.closure(self.root, j[0], (j[1],)), jobs))
            texts = sorted({(sha, f) for sha, g in jobs for f in S2.closure(self.root, sha, (g,))
                            if f.endswith(".py") and self._in_copy(f)})
            list(ex.map(lambda j: SD._raw(self.root, *j), texts))

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

    def layout(self, p: str) -> str | None:
        a, b = self.B.text(p), self.H.text(p)
        return self.cache(("layout", p), lambda: layout_changed(a, b) if a is not None and b is not None else None)

    def modules_named(self, R, f: str) -> set[str]:
        """R5: the dotted names `f`'s imports and import strings name. s2_mutation_record.closure cannot be called for
        this: its import loop is inline and yields only the files `_module_file` resolves (a module before a
        package), so it neither returns names nor sees a package or extension module that would shadow one (N22).
        The loop below reads the same nodes for their names only."""
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

    def judge(self, rel: str, entry: dict, base_entry: dict | None, absent: str = "") -> State:
        """`base_entry`: the same (record, target, k) entry as the BASIS's tables read it, or None (`absent` says why).
        Each rule is skipped only when the test-only `_OFF` names it (N14)."""
        name = entry["target"]
        mut = entry.get("mutants") if isinstance(entry.get("mutants"), int) else 0
        compared: list[str] = []
        ev: dict = {"record": rel, "entry_sha256": _sha(canonical(entry))}
        basis = f"{self.label}@{self.B.sha}"

        def done(state, comp="", reason="", **extra):
            if state in ("MEASURED", "VERIFIED_REUSE"):   # F3: only a reuse carries an acceptance basis
                return State(name, state, comp, reason, basis, list(compared), {**ev, **extra}, mut)
            return State(name, state, comp, reason, "", list(compared), {**ev, **extra, "run_base": self.B.sha}, mut)

        # I7 (+ D3: live at the basis)
        if _on("I7"):
            if base_entry is None:
                return done("INVALIDATED", "I7", absent or f"record entry has no committed counterpart in {rel} at the basis")
            if canonical(base_entry) != canonical(entry):
                return done("INVALIDATED", "I7", "record entry differs from its committed bytes")
        compared.append("I7")
        # I6
        plat = platform_of(entry, self.workers)
        ev["platform"] = plat
        claim = "windows" if name in WINDOWS_CLAIM else "posix"
        if _on("I6"):
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
        if self.B.m.source_digest(src_b) != entry.get("source_sha256"):   # the basis's own currency rule
            why = self.option_c(name, entry, src_b, plat)
            claims = name in getattr(self.H.m, "VERIFIED_REUSE", {}) or name in getattr(self.B.m, "VERIFIED_REUSE", {})
            if why and _on("I8" if claims else "I1"):
                return done("INVALIDATED", "I8" if claims else "I1",
                            f"entry was not current at its basis and no pinned ruling covers it: {why}")
            if not why:
                basis = (f"ruling:{RULING_ID}@{RULING_SHA256}" if self.label == "v2.2.0-accepted"
                         else f"calibration@{self.B.sha}+ruling:{RULING_ID}@{RULING_SHA256}")
                compared.append("I8")
        sb, sh = target_slice(self.B.m, src_b, func), target_slice(self.H.m, src_h, func)
        if sb is None or sh is None:
            return done("UNRESOLVED", "I1", f"target not found or source unparsable at {'basis' if sb is None else 'head'}")
        if sb != sh and _on("I1"):
            diff = sorted(set(sb) ^ set(sh))
            return done("INVALIDATED", "I1", f"target slice changed: {diff[0].splitlines()[0][:80]!r}" if diff
                        else "target slice changed: the same statements in another order")
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
        if dropped and _on("I3"):
            return done("INVALIDATED", "I3", f"kill file dropped from the kill set: {', '.join(dropped)}")
        if recorded != list(current):
            ev["kill_set"] = "kill-set-superset" if set(recorded) != set(current) else "kill-set-reordered"
        compared.append("I3")
        kill = list(current)
        # I4: exact segment texts (§2.2)
        additive = sorted(p for p, s in self.delta.items() if p.startswith("tests/") and s == "A")   # no old segment
        if any(p.startswith("tests/") and s != "A" for p, s in self.delta.items()):
            for F in kill:
                for p in sorted(x for x in self.S(F) if x.startswith("tests/") and self.delta.get(x, "A") != "A"):
                    a, b = segment_texts(self.B.text(p)), segment_texts(self.H.text(p))
                    gone = sorted(k for k in a if b.get(k) != a[k]) or not_additive(set(a), self.H.text(p))
                    if (gone or self.delta[p] == "D") and _on("I4"):
                        return done("INVALIDATED", "I4", f"kill test changed: {p} ({', '.join(gone[:3]) or 'removed'})")
                    additive.append(p)
        compared.append("I4")
        # I5
        if not (src_b == src_h and self.B.generator == self.H.generator
                and self.B.enums(rel_t) == self.H.enums(rel_t)):
            gb, gh = self.generated(self.B, rel_t, func), self.generated(self.H, rel_t, func)
            if isinstance(gb, str) or isinstance(gh, str):   # a failure is an identity not computed
                return done("UNRESOLVED", "I5", f"generator cannot run: {gb if isinstance(gb, str) else gh}")
            if gb != gh and _on("I5"):
                return done("INVALIDATED", "I5", f"generator output differs: {len(gb)} mutants at the basis, {len(gh)} now")
        compared.append("I5")
        # I9
        sb9, sh9 = self.settings
        if sb9 != sh9 and _on("I9"):
            return done("INVALIDATED", "I9", f"runner settings changed: {', '.join(k for k in I9_NAMES if sb9.get(k) != sh9.get(k))}")
        compared.append("I9")
        if additive:
            ev["additive_test_changes"] = sorted(set(additive))
        # §2.9
        if not self.delta:
            return done("VERIFIED_REUSE")
        fired = self.rules(name, kill, claim, ev, plat, python_of(entry))
        if fired:
            return done(*fired)
        if self.obs is not None:   # the reuse rests on observations (Δ ≠ ∅): never an acceptance basis (PROV-1)
            basis = f"observation:{_sha(canonical(ev.get('observation') or {}))}@{self.B.sha}"
            ev["authority"] = OBSERVATION_AUTHORITY
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
            (self.B.m.source_digest(src_b) == scope["current_source_sha256"] == st["current_source_sha256"],
             "basis source is not the ruling's current digest"),
            (entry.get("tree_sha256") == scope["worker_tree_sha256"], "recorded tree is not the ruling's worker tree"),
            (prov is not None and self.B.m.source_digest(prov.decode("utf-8", "replace")) == scope["measured_source_sha256"],
             "the measurement commit's own source is not the measured digest"),
            ([entry.get("mutants"), entry.get("killed"), len(entry.get("survivors") or [])]
             == [out.get("mutants"), out.get("killed"), out.get("survivors")], "outcome is not the ruling's"),
            (plat["family"] == "posix" and plat["flavor"] != "darwin", "platform contradicts the ruling's linux"),
        ]
        return next((why for ok, why in checks if not ok), None)

    def rules(self, name: str, kill: list[str], claim: str, ev: dict, plat: dict | None = None,
              entry_py: str | None = None) -> tuple | None:
        """§2.9 R4, R5, R6, R2 (static); R0/D2/R1/R2/R3 (or the no-observation default); R8, R7. None: nothing
        fires."""
        delta = self.delta
        # R4 discovery
        for F in kill if _on("R4") else ():
            d, base = posixpath.dirname(F), posixpath.basename(F)
            hit = [p for p in delta if p != F and p.startswith(d + "/") and posixpath.basename(p) in ("__init__.py", base)]
            if hit:
                return "INVALIDATED", "R4", f"{F} discovers {sorted(hit)[0]} ({delta[sorted(hit)[0]]})"
        # R5 import resolution, R6 import-time statements and layout, over Δ ∩ S(F) (the frozen §2.9 letter)
        code = sorted(p for p in delta if p.endswith(".py"))
        for rule in ("R5", "R6"):
            for F in kill:
                if fired := self._static(rule, F, code):
                    return fired
        # R2 (static; `_OFF` key R2S): a Δ path S(F) names by a literal or computed path — what a mutant's branch may
        # read although the unmutated run did not
        for F in kill if _on("R2S") else ():
            if hit := sorted(self.named(F).items()):
                p, how = hit[0]
                return "INVALIDATED", "R2", f"S({F}) reaches {p} by a path ({how}): any run of F, a mutant's included, may read it"
        # R0, D2, R1, R2, R3
        data_tokens: set[str] = set()
        ran: dict[str, frozenset[str]] = {}
        if self.obs is None:
            if _on("R1"):
                return "INVALIDATED", "R1", f"no observation of {kill[0] if kill else '<no kill file>'}; R1 cannot be excluded"
            ran = {F: self.S(F) for F in kill}
        else:
            ev["observation"] = {}
        for F in kill if self.obs is not None else ():
            O = self.obs.get(F)
            if not isinstance(O, dict) and _on("R0"):
                return "UNRESOLVED", "R0", f"no admissible observation of {F}"
            O = O if isinstance(O, dict) else {}
            bad, gaps = self.admissible(F, O, claim, plat or {}, entry_py)
            if bad and _on("R0"):
                return "UNRESOLVED", "R0", f"no admissible observation of {F}: {bad}"
            ev["observation"][F] = _sha(canonical(OBS.public(O)))
            opened = O.get("opened") or {}
            opened = dict(opened) if isinstance(opened, dict) else dict.fromkeys(opened, "data")
            loads = {p for p, tag in opened.items() if tag == "load" and p.endswith(".py")}   # the import system's reads
            data = set(opened) - loads   # everything else, a "load" of a non-.py file included, is read as data
            miss = sorted((set(O.get("loaded") or []) | {p for p in opened if p.endswith(".py")}) - self.S(F))
            if miss and _on("D2"):
                return "UNRESOLVED", "D2", f"S({F}) misses {miss[0]}"
            ch = O.get("children") or {}
            unseen = (ch.get("unhooked_python") or 0) + (ch.get("other") or 0)
            static = [] if O.get("os_trace") else [w for f in sorted(self.S(F)) if f.endswith(".py")
                                                   for w in R1_UNSEEN if w in self.both(f)]
            why = ([f"lost {O['lost']}"] if O.get("lost") else []) + (
                [f"unparsed_lines {O['unparsed_lines']}"] if O.get("unparsed_lines") else []) + (
                [f"{unseen} unhooked or other children"] if unseen and not O.get("os_trace") else []) + (
                [f"static scan: {static[0]}"] if static else []) + gaps + [
                f"{k} {v}" for k, v in sorted((O.get("completeness") or {}).items())
                if v and k not in ("lost", "unparsed_lines")]
            if why and _on("R1"):
                n = unseen + (1 if len(why) > bool(unseen and not O.get("os_trace")) else 0)
                return ("INVALIDATED", "R1",
                        f"{F} has {n} unobserved processes: any path of the tree may be read or run ({'; '.join(why)})")
            fdata, fopened = {_fold(x) for x in data}, {_fold(x) for x in opened}   # any spelling of p (SND-8)
            for p in sorted(delta) if _on("R2") else ():
                if _fold(p) in fdata or (delta[p] == "D" and _fold(p) in fopened):
                    return "INVALIDATED", "R2", f"{F} reads {p} as data" if delta[p] != "D" else f"{F} opened {p}, now removed"
            for p in sorted(data) if _on("R2") and delta else ():   # a lookup's answer: existence and kind, any spelling
                if (was := self.spellings(self.B, p)) != (now := self.spellings(self.H, p)):
                    def said(s, p=p):
                        return ", ".join(k if x == p else f"{k} {x}" for x, k in sorted(s)) or "absent"
                    return "INVALIDATED", "R2", f"{F} looked up {p}, which was {said(was)} and is {said(now)}"
            listed = {_fold(SD._norm(x)) for x in O.get("listed") or []}
            by = {SD._norm(k): frozenset(v) for k, v in (O.get("listed_by") or {}).items()}
            registry_changed = SD.REGISTRY in delta
            for p in sorted(delta) if _on("R3") else ():
                above = [x for x in ("/".join(p.split("/")[:i]) for i in range(len(p.split("/")))) if _fold(x) in listed]
                if above and not SD._discounted(p, above, by, None if registry_changed else self.listing_changed()):
                    return "INVALIDATED", "R3", f"{F} lists {above[-1] or '.'}, which holds {p}"
            data_tokens |= {w for p in data for w in _WORD.findall(self.H.text(p) or "")}
            # S(F) plus what F's processes loaded or load-opened (more than S(F) only when the D2 check is off)
            ran[F] = self.S(F) | set(O.get("loaded") or []) | loads
            if fired := self._r5(F, ran[F] - self.S(F)) or self._r6(F, ran[F] - self.S(F), code):
                return fired
        # R8, then R7 (tier S), over S(F) and what F's processes ran. R8 holds for any Δ ≠ ∅ (Review 1, A3-SND-2): a
        # computed-name site may load, on a mutant's branch, a file S(F) does not hold — its change is seen by nothing
        unref = []
        for F in kill:
            S = ran[F]
            open_sites = [s for f in sorted(S) if f.endswith(".py") for R in (self.B, self.H) for s in self.sites(R, f)
                          if (s[0], s[1], s[3]) not in RESOLVED_SITES]
            if open_sites and _on("R8"):
                f, q, line, _ = open_sites[0]
                return "INVALIDATED", "R8", f"S({F}) has a computed-name site at {f}:{line} ({q or '<module>'}): tier S unavailable"
            defs = []
            for p in (x for x in code if x in S):
                c = self.changed(p)
                if isinstance(c, str):
                    return "UNRESOLVED", "I2", c
                defs += [(p, q) for q in [*c["names"], *c["removed"]]]
            for p, q in defs:
                b = q.rsplit(".", 1)[-1]
                hits = [sum(self.refs(R, f)[b] for f in S if f.endswith(".py")) - self._defs(R, p, q) for R in (self.B, self.H)]
                if (max(hits) > 0 or b in data_tokens) and _on("I2"):
                    return "INVALIDATED", "I2", f"{p}::{q} changed and is referenced in S({F})"
                unref.append(f"{p}::{q}")
        if unref:
            ev["unreferenced_changes"] = sorted(set(unref))
        return None

    def dirs_moved(self) -> dict[str, str]:
        """Directories under COPY that exist (hold a file) at one of basis and head only: dir -> "added"/"removed"."""
        def compute():
            def dirs(R):
                return {"/".join(x[:k]) for f in self.copy_files(R) for x in [f.split("/")] for k in range(1, len(x))}
            b, h = dirs(self.B), dirs(self.H)
            return {**dict.fromkeys(sorted(h - b), "added"), **dict.fromkeys(sorted(b - h), "removed")}
        return self.cache("dirs_moved", compute)

    def _r5(self, F: str, files) -> tuple | None:
        """R5: an added or removed module file (source or extension module), or an added or removed directory (a
        namespace package: Review 1, A3-SND-1), whose dotted name `files` import."""
        moved = [(p, _module_of(p), "added" if s == "A" else "removed") for p, s in sorted(self.delta.items())
                 if s in "AD" and _module_of(p)]
        moved += [(d, d.replace("/", "."), how) for d, how in self.dirs_moved().items()]
        if not moved or not _on("R5"):
            return None
        named = set().union(*(self.modules_named(R, f) for R in (self.B, self.H) for f in files if f.endswith(".py")))
        for p, mod, how in moved:
            if any(x == mod or x.startswith(mod + ".") for x in named):
                return "INVALIDATED", "R5", f"{F} imports {mod}, whose {'file' if mod != p.replace('/', '.') else 'directory'} {p} was {how}"
        return None

    def _r6(self, F: str, files, code: list[str]) -> tuple | None:
        for p in (x for x in code if x in files) if _on("R6") else ():
            c = self.changed(p)
            if isinstance(c, str):
                return "UNRESOLVED", "R6", c
            if c["module"] != "unchanged":
                return "INVALIDATED", "R6", f"import-time statements of {p} changed ({c['module']}) in S({F})"
            if why := self.layout(p):
                return "INVALIDATED", "R6", f"{p}: {why} in S({F})"
        return None

    def _static(self, rule: str, F: str, code: list[str]) -> tuple | None:
        """R5 or R6 over Δ ∩ S(F), before any observation: one result per (rule, kill file)."""
        return self.cache((rule, F), lambda: self._r5(F, self.S(F)) if rule == "R5" else self._r6(F, self.S(F), code))

    def both(self, f: str) -> str:
        if f not in self._texts:
            self._texts[f] = (self.B.text(f) or "") + "\0" + (self.H.text(f) or "")
        return self._texts[f]

    def _defs(self, R, p: str, q: str) -> int:
        src = R.text(p)
        return self.cache(("defs", R.sha, p), lambda: _qualdefs(src) if src is not None else collections.Counter())[q]


def _doc(root: pathlib.Path, sha: str, rel: str, docs: dict) -> dict:
    """The record `rel` at `sha`, parsed once per blob (the basis and head share most of them)."""
    bid = S2.blob(root, sha, rel)
    if bid is None:
        raise ValueError("missing")
    if bid not in docs:
        docs[bid] = json.loads(_blob(root, sha, rel))
    return docs[bid]


def _live(root: pathlib.Path, R, docs: dict) -> tuple[list[tuple[str, dict]], list[State]]:
    """The entries mutation.check() reads at commit R by R's own tables, and a state for each phase target with no
    readable entry."""
    live, bad = [], []
    for phase, rel in R.m.RECORDS.items():
        targets = R.m.PHASE_TARGETS.get(phase)
        if not targets:
            continue
        try:
            doc = _doc(root, R.sha, rel, docs)
            old = set(R.m.superseded(doc, phase))
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
    with tempfile.TemporaryDirectory(prefix="aisef-f5-") as tmp, _pinned_git(pathlib.Path(tmp)):
        H = SD.Rev(root, _rev(root, head), pathlib.Path(tmp))
        B = H if _rev(root, base) == H.sha else SD.Rev(root, _rev(root, base), pathlib.Path(tmp))
        return _Ctx(root, B, H, None).S(kill_file)


def classify(root, base: str = BASE, head: str = "HEAD", *, observations: dict | None = None) -> Run:
    """The F5 state of every live target, sorted. Never raises: what cannot be computed is UNRESOLVED."""
    root = pathlib.Path(root).resolve()
    run = Run()
    run.base, run.head = base, head
    with tempfile.TemporaryDirectory(prefix="aisef-f5-") as tmp, _pinned_git(pathlib.Path(tmp)):
        try:
            run += _classify(root, base, head, observations, pathlib.Path(tmp), run)
        except Exception as e:   # noqa: BLE001  — the engine fails closed, never open
            run[:] = [State("<all>", "UNRESOLVED", "engine", f"{type(e).__name__}: {e}")]
    return run


def _classify(root, base, head, observations, tmp, run: Run) -> list[State]:
    try:
        top = S2._git(root, "rev-parse", "--show-toplevel")
    except OSError as e:
        return [State("<all>", "UNRESOLVED", "basis", f"git unavailable: {e}")]
    if top.returncode != 0:
        return [State("<all>", "UNRESOLVED", "basis", "not a git repository")]
    head_sha = _rev(root, head)
    if head_sha is None:
        return [State("<all>", "UNRESOLVED", "basis", f"head {head} is not a commit")]
    if why := _shadowed(head, head_sha):
        return [State("<all>", "UNRESOLVED", "basis", f"head {why}")]
    run.head_sha = head_sha
    try:
        H = SD.Rev(root, head_sha, tmp)
    except SystemExit as e:
        return [State("<all>", "UNRESOLVED", "basis", f"the head's harness cannot be loaded: {e}")]
    docs: dict = {}

    def stopped(component: str, reason: str) -> list[State]:
        live, bad = _live(root, H, docs)
        out = [State(t["target"], "UNRESOLVED", component, reason, mutants=t.get("mutants") or 0) for _, t in live]
        return sorted(out + [dataclasses.replace(s, state="UNRESOLVED", component=component, reason=reason) for s in bad],
                      key=lambda s: s.target)
    shallow = S2._git(root, "rev-parse", "--is-shallow-repository")
    if shallow.returncode != 0 or shallow.stdout.strip() != b"false":
        return stopped("basis", "shallow clone (or git cannot tell): the basis history cannot be proven")
    base_sha = _rev(root, base)
    if base_sha is None:
        return stopped("basis", f"basis commit {base} unavailable")
    if why := _shadowed(base, base_sha):
        return stopped("basis", f"basis {why}")
    run.base_sha = base_sha
    try:
        dirty = _dirty(root, head_sha, H.copy)
    except GitError as e:
        return stopped("dirty", f"the working tree's state cannot be read: {e}")
    if dirty:
        return stopped("dirty", f"dirty tree: {dirty[0]}" + (f" (+{len(dirty) - 1} more)" if len(dirty) > 1 else ""))
    try:
        B = H if base_sha == head_sha else SD.Rev(root, base_sha, tmp)
        if not S2._files(root, B.sha) or not S2._files(root, H.sha):
            raise GitError("git ls-tree listed no file")
        ctx = _Ctx(root, B, H, observations)
    except (SystemExit, GitError) as e:
        return stopped("basis", f"the basis cannot be read: {e}")
    if any(p.endswith(".py") for p in ctx.delta) or (observations is not None and ctx.delta):
        ctx.prefetch()   # before any record is read: each git child is forked from this process, small only now
    live, bad = _live(root, H, docs)
    out = list(bad)
    # D3: the counterpart of a head entry is the same (record, target, k) entry as the BASIS's own tables read it
    base_entries: dict[str, dict[str, list]] = {}
    for rel, t in (live if B is H else _live(root, B, docs)[0]):
        base_entries.setdefault(rel, {}).setdefault(t.get("target"), []).append(t)

    def absent(rel: str, target: str, k: int) -> str:
        try:
            held = sum(x.get("target") == target for x in _doc(root, B.sha, rel, docs)["targets"])
        except (ValueError, KeyError, TypeError):
            held = 0
        if held > k:
            return f"record entry is not live at the basis: the basis's tables do not read it in {rel}"
        return f"record entry has no committed counterpart in {rel} at the basis"
    taken: collections.Counter = collections.Counter()
    for rel, t in live:
        cands = base_entries.get(rel, {}).get(t["target"], [])
        k = taken[rel, t["target"]]
        taken[rel, t["target"]] += 1
        try:
            out.append(ctx.judge(rel, t, cands[k], "") if k < len(cands) else
                       ctx.judge(rel, t, None, absent(rel, t["target"], k)))
        except Exception as e:   # noqa: BLE001
            out.append(State(t["target"], "UNRESOLVED", "engine", f"{type(e).__name__}: {e}", mutants=t.get("mutants") or 0))
    return sorted(out, key=lambda s: (s.target, s.evidence.get("record", "")))


def _dirty(root: pathlib.Path, head_sha: str, copy) -> list[str]:
    """COPY paths whose working-tree bytes are not head's, and untracked or ignored files there (`__pycache__` aside:
    the runner leaves it out). A failing git command raises GitError: never read as a clean tree."""
    changed = _git(root, "diff", "--name-only", "-z", head_sha, "--", *copy).decode("utf-8", "replace")
    other = _git(root, "ls-files", "--others", "-z", "--", *copy).decode("utf-8", "replace")
    return sorted({p for p in changed.split("\0") + other.split("\0") if p and "__pycache__" not in p.split("/")})


# ------------------------------------------------------------------------------------------------------- report


def report(states: Run, observations=None) -> dict:
    """The state table of one classify() run, headed by the shas THAT run resolved (F2: no name is resolved here)."""
    base_sha, head_sha = states.base_sha, states.head_sha
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
    return {"base": {"rev": states.base, "sha": base_sha}, "head": {"rev": states.head, "sha": head_sha},
            "run": "v2.2.0-accepted" if base_sha == BASE else
                   "calibration (the basis is not the pinned v2.2.0 commit)" if base_sha else "no basis commit resolved",
            "rules_off": sorted(_OFF),
            "generated_by": {"tool": TOOL, "sha256": _sha(_lf(me.read_text(encoding="utf-8")).encode())},
            "observations": None if observations is None else {k: _sha(canonical(OBS.public(v)))
                                                                for k, v in sorted(observations.items())},
            "observation_authority": None if observations is None else OBSERVATION_AUTHORITY,
            "counts": counts, "by_component": dict(sorted(by.items())), "platform": dict(sorted(plat.items())),
            "states": [dataclasses.asdict(s) for s in states]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--classify", action="store_true", required=True)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--json", type=pathlib.Path, help="write the state table here (the only write)")
    ap.add_argument("--affected", action="store_true", help="print only INVALIDATED and UNRESOLVED, with reasons")
    ap.add_argument("--observations", type=pathlib.Path, metavar="DIR",
                    help="observe.py records (an input only: each is verified and bound to head and the entry)")
    a = ap.parse_args(argv)
    begun = time.monotonic()
    obs = OBS.load(a.observations) if a.observations else None
    states = classify(ROOT, a.base, a.head, observations=obs)
    doc = report(states, obs)
    if a.json:
        with open(a.json, "x", encoding="utf-8") as f:   # never overwrites
            f.write(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    if a.affected:
        for s in states:
            if s.state in ("INVALIDATED", "UNRESOLVED"):
                print(f"{s.state:<12} {s.component:<7} {s.target}: {s.reason}")
    else:
        print(f"F5 impact  base {doc['base']['sha']}  head {doc['head']['sha']}  run: {doc['run']}")
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
