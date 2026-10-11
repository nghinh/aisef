"""V2.1 campaign 2: the comparison table of every change after the snapshot the campaign measures (owner rule
2026-10-08: campaign 2 is measured at 5719f1f; every later change on v2.1/foundation needs a table — file, affected
targets, related tests/harness, evidence to re-measure — and no result of the snapshot is attached to a newer head
without sufficient grounds).

    python -P validation/qualification/v21_snapshot_delta.py --base 5719f1f [--head HEAD] [--read-set R.json] --write OUT_DIR
    python -P validation/qualification/v21_snapshot_delta.py --check OUT_DIR

--write: OUT_DIR/DELTA.json (machine) and OUT_DIR/DELTA.md (the table). --check: the table's head is HEAD or an
ancestor of it; both files are byte for byte what base..head derives now (with the read-set the table records, its
sha256 unchanged); the reuse criteria of v21_mutation_record (criteria_sha256: proof, which verdict() re-implements per
commit) are the ones the table was derived beside; and no file changed after the table's head (outside OUT_DIR) is
anything but evidence/doc or code outside mutation.COPY that reaches no target, with no record binding it — otherwise
the table is stale (a read-set measured at the table's head says nothing of a later file).

Data the kill tests read cannot be found completely by reading their source (a path joined at run time, held by a
module, picked by a glob). Every changed file inside mutation.COPY that the other rules leave open for a target is
therefore, per kill file: read (a measured read-set says so) — the target's base result is then no ground at head:
re-measure it; not read (a measured read-set of that kill file omits it); or not measured — "inside COPY, read-set not
measured", and the target's base result stands only PROVISIONALLY until a measured read-set clears it. A kill file not
measured whose closure names the file (found statically) is reported as one that may read it, and is provisional all the
same; a measured kill file is decided by the measurement alone. --read-set R.json is that measurement, recorded
elsewhere (not by this tool): {"commit": "<the head's full sha>", "kill_files": {"<kill file>": {"opened": [paths],
"listed": [dirs]}}}, every path relative to the root of the tree the run used ("." is the root; what lies outside the
tree is left out). The recording run (after the campaign: it runs every kill file) runs each kill file alone at head
with -B in the runner's tree (no __pycache__) with an audit hook taking `open`, `os.listdir` and `os.scandir` events,
and os.stat / os.lstat wrapped (they raise no audit event), in its own process and every child Python process; each
path is made relative to the tree's resolved root. A kill file opened or looked up p, or listed a directory above p: it
reads p — unless the entry also holds `"listed_by": {directory: [file]}` (the file of the tree that made the listings
of each directory: its innermost frame on the stack; "<native>" when none is of the tree) and every file named for
each such directory is aisef2/invariants/registry.py (the discount: _listing_rule, RULES["data"]). A record is refused when a path is
absolute, written with a backslash or holds an empty, "." or ".." part, or when a kill file's own path is not among
the files it opened (its import opens it: a record without it measured nothing); a record without `listed_by` is
accepted and discounts nothing. A kill file missing from the record stays not measured; a file that does not exist at
head (deleted, a rename's source) is never cleared by a run at head.

Each commit's harness is read from that commit (its validation/v2/mutation.py: V21_TARGETS, COPY, the generator), never
from the working tree. Every file of `git diff -M --name-status base head` (both sides of a rename) gets its kinds and
the V2.1 targets it affects (RULES). Every V2.1 target of either side gets the verdict of
validation/qualification/v21_mutation_record.proof, applied to a result measured at base: the target file is
byte-identical, the kill set is the head's, no tests/ file of the kill tests' closure (s2_mutation_record.closure, the
base kill set at both commits) changed, and the head's generator yields the base's mutants. The generator is run only
when its inputs differ (its source, the module, the enum members): it is deterministic, so identical inputs give the
identical list. What those rules do not bind (the runner's code, data the kill tests read, data whose reading is not
measured) is reported beside the verdict, in every target's row, never folded into it.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import functools
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as S2  # noqa: E402
from validation.qualification import v21_mutation_record as MR  # noqa: E402

TOOL_REL = "validation/qualification/v21_snapshot_delta.py"
PROOF_REL = "validation/qualification/v21_mutation_record.py"
#: the reuse criteria verdict() re-implements (v21_mutation_record.criteria_sha256 of this file)
PROOF = ROOT / PROOF_REL
HARNESS = ("validation/v2/mutation.py", "validation/v2/execution_order.py", "validation/v2/owned_run.py",
           "validation/v2/cleanup_authority.py")
#: the definitions mutation.mutants() runs (with ast and copy of the same interpreter)
GENERATOR = ("_SWAP", "_inert", "_script", "_root", "mutants")
MANIFEST_PREFIX = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST"
CALIBRATION = "validation/v2/checker_calibration.py"
KNOWN_BAD = "tests/v2/fixtures/known_bad/"
EVIDENCE = "evidence/doc"
CODE = "code"
DATA, UNMEASURED, UNREAD = "copy_data", "copy_unmeasured", "copy_unread"
#: kinds a change after the table's head may have and still be covered by it (--check builds base..HEAD without a
#: read-set: one measured at the table's head says nothing of a later file)
COVERED = frozenset({EVIDENCE, CODE})
#: why a target is in a data file's row: its kill tests read it (measured) or may (found statically)
READ = {"measured": "data its kill tests read (measured; outside the proof's rules)",
        "found statically": "data its kill tests may read (found statically; outside the proof's rules)"}
NOTE = {"measured": "data its kill tests read changed (measured)",
        "found statically": "data its kill tests may read changed (found statically)"}
LISTING = frozenset({"glob", "iglob", "rglob", "iterdir", "listdir", "scandir", "walk", "fwalk"})
#: the one file whose listings of a directory a kill file's read-set may not count as a read of what lies in it:
#: `test_directories` there lists TESTS_V2 with glob("test_*.py") and rglob("test_*.py") and keeps only the set of the
#: directories that hold a test module (every kill file imports tests/v2/__init__.py, whose arm() calls it). A file
#: under TESTS_V2 can change that set only when it is, or lies under, an entry named test_*.py that is the first or
#: last of its directory; a new or changed file anywhere else cannot.
REGISTRY, REGISTRY_FN = "aisef2/invariants/registry.py", "test_directories"
TESTS_V2, TEST_MODULE = "tests/v2", "test_*.py"   # registry.TESTS_V2, and the pattern test_directories globs for
RULES = {
    "product": "a file under aisef2/: every target of that module (the module digest is whole-file); every target of a "
               "module that imports it from aisef2 (its enum members are generator input); every target whose kill "
               "tests' closure holds it (code outside tests/: reported by the proof, not counted)",
    "kill_file": "in a V2.1 target's kill set at base or head: that target",
    "kill_closure": "in the closure of a target's kill files (s2_mutation_record.closure, at base or head) without "
                    "being one: that target; under tests/ the proof counts it, elsewhere it reports it",
    "harness": "validation/v2/mutation.py, execution_order.py, owned_run.py, cleanup_authority.py and their closure: "
               "every V2.1 target, stated as such in the file's row and in every target's row; the proof's rules do "
               "not bind the runner's code",
    "data": "a file inside mutation.COPY outside the harness is data to every target it is not the module of; per "
            "kill file of such a target whose closure does not hold it, measured: read when the measured read-set "
            "says so (opened or looked up, or a directory above it listed — except under tests/v2 when every "
            "listing of each such directory is attributed (listed_by) to aisef2/invariants/registry.py, whose "
            "test_directories keeps only the set of directories holding a test_*.py: then the file is read through "
            "the listing only when it is, or lies in a directory named, test_*.py and the directory holding that "
            "entry is in that set at base and not at head or the reverse — a first or last test module; off, and "
            "the table says why, when test_directories differs between base and head or registry.py lists "
            "elsewhere), not read when it omits it and the file "
            "exists at head, else not measured; not measured: may read when found statically in a file of "
            "that closure inside COPY (no other file is in the runner's tree), tests/ or not, at base or head — the "
            "whole path in its text; its path split into consecutive parts, each a whole string constant, from the "
            "repository root or a directory above that file; a parent directory of two components or more and the "
            "rest or the basename; or the file lists a directory (a call of glob, iglob, rglob, iterdir, listdir, "
            "scandir, walk or fwalk whose receiver and arguments name it: their string constants joined in source "
            "order up to the first part with *, ? or [, from the root or a directory above that file) that is the "
            "parent directory, or any directory above when it lists recursively (rglob, walk, fwalk, a ** pattern) "
            "— and not measured all the same",
    DATA: "inside COPY, read by <kill files> (read_set.read_by: measured — their targets' base results are no ground "
          "at head: re-measure them (counts.data_read) —, or found statically: they may read it, and are not "
          "measured): their targets; outside the proof's rules",
    UNMEASURED: "inside COPY, read-set not measured (found statically or not): for every target with such a kill file, "
                "its base result stands only PROVISIONALLY until a measured read-set clears the file; "
                "read_set.provisional counts them (provisional_except: the targets of the build it does not hold)",
    UNREAD: "inside COPY and not read by any kill file the other rules leave open (measured read-set): no target",
    CODE: "a .py or .sh file or a #! script that no rule above ties to a target by code (not under aisef2/, no kill "
          "file, in no kill closure, not the harness); inside COPY it is data as well",
    EVIDENCE: "none of the above (outside COPY, not code): no target",
    "verdict": "v21_mutation_record.proof for a result measured at base, at head (re-implemented per commit; "
               "proof.criteria_sha256 is the one it was derived beside)",
    "records": "manifest: a new revision when a target, a kill set or a target module changed, or a file it binds by "
               "sha256 differs at head; T0: every (module, null mutant, kill file) pair a head target needs with no "
               "PASS row in the manifest's T0 record, or whose kill file changed since the sweep, and that base did "
               "not already need; execution order: kill sets, targets, null mutants, the T0 pairs, execution_order.py "
               "or the T0 record changed; Q0: checker_calibration.py, a validation/v2 module, a checker's source or a "
               "known-bad fixture changed",
}


class Rev:
    """One commit, with its own mutation module (validation/v2 and aisef2 of that commit, extracted to `tmp`)."""

    def __init__(self, root: pathlib.Path, rev: str, tmp: pathlib.Path):
        self.root = root
        self.sha = S2._git(root, "rev-parse", "--verify", f"{rev}^{{commit}}").stdout.decode().strip()
        if not self.sha:
            raise SystemExit(f"{rev}: not a commit of {root}")
        self.dir = tmp / self.sha
        trees = [p for p in ("aisef2", "validation/v2") if any(f.startswith(p + "/") for f in S2._files(root, self.sha))]
        raw = S2._git(root, "archive", "--format=tar", self.sha, *trees).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            t.extractall(self.dir, filter="data")
        path = self.dir / "validation/v2/mutation.py"
        if not path.is_file():
            raise SystemExit(f"{self.sha[:12]} has no validation/v2/mutation.py")
        name = f"_v21_delta_mutation_{self.sha}"
        spec = importlib.util.spec_from_file_location(name, path)
        self.m = importlib.util.module_from_spec(spec)
        saved, ca = list(sys.path), sys.modules.pop("cleanup_authority", None)
        sys.modules[name] = self.m   # dataclasses look their module up there
        try:
            spec.loader.exec_module(self.m)
        finally:
            sys.path[:] = saved
            sys.modules.pop("cleanup_authority", None)
            if ca is not None:
                sys.modules["cleanup_authority"] = ca
        self.targets: dict[str, list[str]] = {t: list(k) for t, k in self.m.V21_TARGETS.items()}
        self.copy = tuple(self.m.COPY)
        seg = _segments(_text(root, self.sha, "validation/v2/mutation.py"))
        self.generator = hashlib.sha256("\n\n".join(seg.get(n, f"<no {n}>") for n in GENERATOR).encode()).hexdigest()
        self._enums: dict[str, dict] = {}
        self._nulls: dict[tuple[str, str], str] = {}
        self._imports: dict[str, frozenset[str]] = {}

    def blob(self, path: str) -> str | None:
        return S2.blob(self.root, self.sha, path)

    def text(self, path: str) -> str | None:
        return _text(self.root, self.sha, path)

    def enums(self, rel: str) -> dict:
        if rel not in self._enums:
            self._enums[rel] = self.m._enum_members(self.text(rel), self.dir)
        return self._enums[rel]

    def null(self, target: str) -> str:
        """sha256 of the target's null mutant (mutation.null_mutant: it depends on the function only through a
        `SCRIPT/` prefix)."""
        rel, func = target.split("::")
        key = (rel, func.partition("/")[0] if "/" in func else "")
        if key not in self._nulls:
            self._nulls[key] = hashlib.sha256(self.m.null_mutant(self.text(rel), func).encode()).hexdigest()
        return self._nulls[key]

    def mutant_list(self, target: str) -> tuple[str, ...] | str:
        rel, func = target.split("::")
        try:
            return tuple(d for d, _ in self.m.mutants(self.text(rel), func, self.enums(rel)))
        except SystemExit as e:
            return str(e)

    def imports(self, rel: str) -> frozenset[str]:
        """The aisef2 files `rel` imports at module level (the ones mutation._enum_members reads)."""
        if rel not in self._imports:
            src = self.text(rel)
            mods = [n.module for n in ast.parse(src).body if isinstance(n, ast.ImportFrom)
                    and (n.module or "").startswith("aisef2")] if src else []
            self._imports[rel] = frozenset(m.replace(".", "/") + ".py" for m in mods)
        return self._imports[rel]


@functools.cache
def _raw(root: pathlib.Path, sha: str, path: str) -> bytes | None:
    return None if S2.blob(root, sha, path) is None else S2._git(root, "show", f"{sha}:{path}").stdout


def _text(root: pathlib.Path, sha: str, path: str) -> str | None:
    raw = _raw(root, sha, path)
    return None if raw is None else raw.decode("utf-8", "replace")


def _segments(src: str | None) -> dict[str, str]:
    """Top-level name -> the AST dump of its definitions (functions, classes, assignments); imports, the docstring and
    every other statement under one bracketed name each."""
    out: dict[str, str] = {}
    try:
        body = ast.parse(src).body if src is not None else []
    except SyntaxError:
        return {"<unparsable>": src}
    for i, n in enumerate(body):
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names = [n.name]
        elif isinstance(n, ast.Assign):
            names = [x.id for x in n.targets if isinstance(x, ast.Name)] or ["<other statements>"]
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names = [n.target.id]
        elif isinstance(n, ast.Import | ast.ImportFrom):
            names = ["<imports>"]
        elif i == 0 and isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            names = ["<docstring>"]
        else:
            names = ["<other statements>"]
        for name in names:
            out[name] = out.get(name, "") + ast.dump(n)
    return out


def changed_names(a: str | None, b: str | None) -> list[str]:
    sa, sb = _segments(a), _segments(b)
    return sorted(k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k))


def _changes(root: pathlib.Path, base: str, head: str) -> list[dict]:
    out = S2._git(root, "diff", "-M", "-z", "--name-status", base, head).stdout.decode("utf-8", "replace").split("\0")
    rows, i = [], 0
    while i < len(out) and out[i]:
        status = out[i]
        if status[0] in "RC":
            rows.append({"path": out[i + 2], "status": status, "from": out[i + 1]})
            i += 3
        else:
            rows.append({"path": out[i + 1], "status": status})
            i += 2
    return sorted(rows, key=lambda r: r["path"])


def _sha256(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _bindings(doc, out=None) -> dict[str, str]:
    """Every (repository path -> sha256) a manifest binds: {"path", "sha256"} objects and {path: sha256} maps."""
    out = {} if out is None else out
    if isinstance(doc, dict):
        if isinstance(doc.get("path"), str) and isinstance(doc.get("sha256"), str):
            out[doc["path"]] = doc["sha256"]
        for k, v in doc.items():
            if "/" in k and isinstance(v, str) and len(v) == 64:
                out[k] = v
            _bindings(v, out)
    elif isinstance(doc, list):
        for v in doc:
            _bindings(v, out)
    return out


def verdict(B: Rev, H: Rev, t: str) -> dict:
    """v21_mutation_record.proof for a result of `t` measured at B, used at H."""
    base7 = B.sha[:7]
    if t not in H.targets:
        return {"verdict": "not a V2.1 target at head: nothing to re-measure", "reasons": [], "other_code_changed": []}
    if t not in B.targets:
        return {"verdict": f"re-measure: not a V2.1 target at {base7}, so no result of it exists",
                "reasons": [f"not a V2.1 target at {base7}"], "other_code_changed": []}
    rel = t.split("::")[0]
    out = []
    if B.blob(rel) != H.blob(rel):
        out.append("the target file changed since it was measured")
    if B.targets[t] != H.targets[t]:
        out.append("its kill set is not the current one")
    kill = tuple(B.targets[t])
    files = closure(B.root, H.sha, kill) | closure(B.root, B.sha, kill)
    changed = sorted(f for f in files if B.blob(f) != H.blob(f))
    tests = [f for f in changed if f.startswith("tests/")]
    if tests:
        out.append(f"kill tests changed: {', '.join(tests)}")
    row: dict = {}
    if not out:
        if B.generator == H.generator and B.enums(rel) == H.enums(rel):
            row["generator"] = "same inputs (generator source, module source, enum members)"
        else:
            lb, lh = B.mutant_list(t), H.mutant_list(t)
            row["generator"] = f"run at both: {len(lb)} and {len(lh)} mutants"
            if lb != lh:
                out.append("its mutants are not the current generator's")
    return {"verdict": f"re-measure: {'; '.join(out)}" if out else f"a {base7} result can stand at head",
            "reasons": out, "other_code_changed": [f for f in changed if not f.startswith("tests/") and f != rel], **row}


def closure(root: pathlib.Path, sha: str, start: tuple[str, ...]) -> frozenset[str]:
    """s2_mutation_record.closure(root, sha, start), as the union of its one-file closures: a breadth-first closure
    from a set is the union of the closures from its members, and each one-file closure is computed (and cached) once."""
    return frozenset().union(*(S2.closure(root, sha, (f,)) for f in start))


def _kill_closures(B: Rev, H: Rev) -> dict[str, frozenset[str]]:
    """kill file -> its closure at base | at head (one closure per file: the closure of a set is the union)."""
    files = {f for R in (B, H) for k in R.targets.values() for f in k}
    return {f: S2.closure(B.root, B.sha, (f,)) | S2.closure(B.root, H.sha, (f,)) for f in sorted(files)}


def _norm(s: str) -> str:
    s = s.strip()
    while s.startswith("./"):
        s = s[2:]
    return "" if s == "." else s.strip("/")


_WILD = "*?["


def _strings(node: ast.AST) -> list[str]:
    return [_norm(n.value) for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and len(n.value) < 300 and "\n" not in n.value]


@functools.cache
def _info(root: pathlib.Path, sha: str, path: str) -> tuple[str, frozenset[str], tuple]:
    """`path` at `sha`: (its text, its string constants, its directory listings) — the last two for a .py file only.
    A listing is a call of glob, iglob, rglob, iterdir, listdir, scandir, walk or fwalk whose receiver and arguments
    hold string constants (the directory it lists can only be named there): (those strings joined by "/" in source
    order up to the first part with *, ? or [ — the directory —, whether it lists recursively: rglob, walk, fwalk or a
    ** pattern). `ROOT / "docs" / "sub"` and `.glob("sub/*.json")` on `ROOT / "docs"` both list docs/sub."""
    text = _text(root, sha, path) or ""
    try:
        tree = ast.parse(text) if path.endswith(".py") else None
    except SyntaxError:
        tree = None
    consts, calls = set(), []
    for n in ast.walk(tree) if tree else ():
        if isinstance(n, ast.Constant):
            consts.update(s for s in _strings(n) if s and not any(c in s for c in _WILD))
        elif isinstance(n, ast.Call) and (name := getattr(n.func, "attr", None) or getattr(n.func, "id", None)) in LISTING:
            nodes = [x for part in [getattr(n.func, "value", None), *n.args, *(k.value for k in n.keywords)] if part
                     for x in ast.walk(part) if isinstance(x, ast.Constant) and isinstance(x.value, str)]
            joined = "/".join(s for x in sorted(nodes, key=lambda x: (x.lineno, x.col_offset)) if (s := _norm(x.value)))
            parts = joined.split("/")
            listed = "/".join(parts[:next((i for i, x in enumerate(parts) if any(c in x for c in _WILD)), len(parts))])
            if listed:
                calls.append((listed, name in ("rglob", "walk", "fwalk") or "**" in joined))
    return text, frozenset(consts), tuple(calls)


def _names(info: tuple, f: str, p: str) -> str | None:
    """How the file `f` (its _info) names the repository path `p`, or None (RULES["data"])."""
    text, consts, calls = info
    if p in text:
        return "its path"
    parts = p.split("/")
    n = len(parts)
    up = f.split("/")
    anchors = {"/".join(up[:k]) for k in range(len(up))}   # the root and every directory above f (ROOT, __file__)

    reach = {i for i in range(n) if "/".join(parts[:i]) in anchors}   # parts[:j]: an anchor, then constants
    for i in range(n):
        if i in reach:
            reach |= {j for j in range(i + 1, n + 1) if "/".join(parts[i:j]) in consts}
    if n in reach:
        return "its path parts"
    if any("/".join(parts[:k]) in consts and ("/".join(parts[k:]) in consts or parts[-1] in consts) for k in range(2, n)):
        return "a parent directory and its name"
    parent = "/".join(parts[:-1])
    for listed, deep in calls:
        for a in anchors:
            d = f"{a}/{listed}" if a else listed
            if parent == d or (deep and p.startswith(d + "/")):
                return "a directory it lists"
    return None


def _read_set(path: pathlib.Path, head: str) -> dict[str, tuple[frozenset[str], frozenset[str], dict]]:
    """kill file -> (paths it opened or looked up, directories it listed, directory -> the files of the tree that made
    its listings (`listed_by`; {} in a record without it)), from a recorded read-set of `head`."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path}: cannot be read: {e!r}") from None
    kf = doc.get("kill_files") if isinstance(doc, dict) else None
    if not isinstance(kf, dict) or not all(isinstance(v, dict) and all(
            isinstance(v.get(x), list) and all(isinstance(s, str) for s in v[x]) for x in ("opened", "listed")) and (
            "listed_by" not in v or isinstance(v["listed_by"], dict) and all(
                isinstance(c, list) and all(isinstance(s, str) for s in c) for c in v["listed_by"].values()))
            for v in kf.values()):
        raise SystemExit(f"{path}: not a read-set: {{\"commit\", \"kill_files\": {{kill file: {{\"opened\": [path], "
                         f"\"listed\": [directory], [\"listed_by\": {{directory: [file]}}]}}}}}}")
    if doc.get("commit") != head:
        raise SystemExit(f"{path}: measured at {str(doc.get('commit'))[:12]}, not at the head {head[:12]}")
    out = {}
    for k, v in kf.items():
        by = v.get("listed_by", {})
        bad = [s for s in (*v["opened"], *v["listed"], *by, *(c for cs in by.values() for c in cs))
               if s.strip().startswith("/") or "\\" in s or (n := _norm(s)) and {"", ".", ".."} & set(n.split("/"))]
        if bad:
            raise SystemExit(f"{path}: {k}: {bad[0]!r} is not a path relative to the tree root (the recorder makes every "
                             f"path relative to the root of the tree it ran in and leaves out what lies outside it)")
        out[k] = (frozenset(map(_norm, v["opened"])), frozenset(map(_norm, v["listed"])), {})
        for d, cs in by.items():
            out[k][2][_norm(d)] = out[k][2].get(_norm(d), frozenset()) | frozenset(map(_norm, cs))
        if k not in out[k][0]:
            raise SystemExit(f"{path}: {k}: its own path is not among the files it opened (its import opens it): the "
                             f"record measured nothing of it")
    return out


def _test_dirs(files) -> frozenset[str]:
    """The directories registry.test_directories returns for a tree holding `files`: the parent of every entry under
    TESTS_V2 named test_*.py — a file or a directory (glob matches both), a name in any case (a stricter match)."""
    n = len(TESTS_V2.split("/"))
    return frozenset("/".join(parts[:i]) for f in files if f.startswith(TESTS_V2 + "/")
                     for parts in [f.split("/")] for i in range(n, len(parts))
                     if fnmatch.fnmatchcase(parts[i].lower(), TEST_MODULE))


def _lists(call: ast.Call) -> bool:
    """A call of one of LISTING (`ast.walk`, the syntax tree's, is not one)."""
    f = call.func
    name = getattr(f, "attr", None) or getattr(f, "id", None)
    return name in LISTING and not (name == "walk" and getattr(getattr(f, "value", None), "id", None) == "ast")


def _listing_rule(B: Rev, H: Rev) -> tuple[frozenset[str] | None, str]:
    """The discount of REGISTRY's listings (RULES["data"]): (the directories whose membership of test_directories()'s
    result differs between base and head, why the rule holds) — or (None, why it is off for this run). Off when
    REGISTRY has no single test_directories, when it lists a directory anywhere outside it (a file-level attribution
    could not tell the two apart), or when that function's AST differs between base and head (what the rule was
    written for is not what ran at base)."""
    dumps = []
    for R in (B, H):
        try:
            tree = ast.parse(R.text(REGISTRY) or "")
        except SyntaxError:
            return None, f"{REGISTRY} does not parse at {R.sha[:7]}"
        fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == REGISTRY_FN]
        if len(fns) != 1:
            return None, f"{REGISTRY} has no single {REGISTRY_FN} at {R.sha[:7]}"
        inside = {id(n) for n in ast.walk(fns[0])}
        other = [n.lineno for n in ast.walk(tree) if id(n) not in inside and isinstance(n, ast.Call) and _lists(n)]
        if other:
            return None, f"{REGISTRY} lists a directory outside {REGISTRY_FN} at {R.sha[:7]} (line {other[0]})"
        dumps.append(ast.dump(fns[0]))
    if dumps[0] != dumps[1]:
        return None, f"{REGISTRY_FN} in {REGISTRY} differs between {B.sha[:7]} and {H.sha[:7]}"
    changed = _test_dirs(S2._files(B.root, B.sha)) ^ _test_dirs(S2._files(H.root, H.sha))
    return changed, (f"{REGISTRY_FN} in {REGISTRY} is the same at {B.sha[:7]} and {H.sha[:7]} and lists nowhere else "
                     f"there; {TESTS_V2} directories whose membership of its result changes: {len(changed)}")


def _discounted(p: str, above: list[str], by: dict, changed: frozenset[str] | None) -> bool:
    """True when `p` is not read through the listings of the directories `above` it: the rule holds for this run,
    every file named for each of them is REGISTRY, they are TESTS_V2 or under it as `p` is, and p is no test module
    (nor under a directory named like one) whose directory's membership of test_directories()'s result changes."""
    under = TESTS_V2 + "/"
    if changed is None or not p.startswith(under) or not all(d == TESTS_V2 or d.startswith(under) for d in above):
        return False
    parts = p.split("/")
    return all(by.get(d) == {REGISTRY} for d in above) and not any(
        fnmatch.fnmatchcase(parts[i].lower(), TEST_MODULE) and "/".join(parts[:i]) in changed
        for i in range(len(TESTS_V2.split("/")), len(parts)))


def _data(B: Rev, H: Rev, p: str, kc: dict[str, frozenset[str]], measured: dict | None,
          copy: tuple[str, ...], changed: frozenset[str] | None = None) -> tuple[dict, set, set]:
    """For the changed file `p` inside COPY: (kill file -> how it reads p, the kill files not measured, the kill files
    a measured read-set clears), over the kill files whose closure does not hold p. A measured kill file is decided by
    the measurement; one not measured (or measured at head while p is not there) is not measured, and may read p when
    found statically. Only the closure's files inside COPY are looked into: no other file is in the runner's tree.
    `changed`: _listing_rule's directories (None: the discount is off)."""
    root, read, unmeasured, cleared = B.root, {}, set(), set()
    names: dict[str, str | None] = {}
    parts = p.split("/")
    for k, files in kc.items():
        if p in files:
            continue
        if measured is not None and k in measured:
            opened, listed, by = measured[k]
            above = [d for d in ("/".join(parts[:i]) for i in range(len(parts))) if d in listed]
            if p in opened or above and not _discounted(p, above, by, changed):
                read[k] = "measured"
                continue
            if p in S2._files(root, H.sha):
                cleared.add(k)
                continue
        unmeasured.add(k)
        for f in sorted(x for x in files if any(x == c or x.startswith(c + "/") for c in copy)):
            if f not in names:
                names[f] = next((h for R in (B, H) if (h := _names(_info(root, R.sha, f), f, p))), None)
            if names[f]:
                read[k] = f"found statically: {f} names {names[f]}"
                break
    return read, unmeasured, cleared


def _records(B: Rev, H: Rev, rows: list[dict]) -> list[dict]:
    root, out = B.root, []
    both = sorted(set(B.targets) & set(H.targets))
    added, removed = sorted(set(H.targets) - set(B.targets)), sorted(set(B.targets) - set(H.targets))
    kill_changed = [t for t in both if B.targets[t] != H.targets[t]]
    module_changed = [t for t in both if B.blob(t.split("::")[0]) != H.blob(t.split("::")[0])]
    harness_file = ["validation/v2/mutation.py"]
    target_reasons = [r for r in (
        {"why": f"{len(added)} target(s) added", "targets": added, "files": harness_file} if added else None,
        {"why": f"{len(removed)} target(s) removed", "targets": removed, "files": harness_file} if removed else None,
        {"why": f"{len(kill_changed)} kill set(s) changed", "targets": kill_changed,
         "files": sorted({*harness_file, *(f for t in kill_changed for f in set(B.targets[t]) ^ set(H.targets[t]))})}
        if kill_changed else None) if r]
    # the requalification manifest whose snapshot is this base (the latest revision), read at head
    manifests = []
    for p in sorted(f for f in S2._files(root, H.sha) if f.startswith(MANIFEST_PREFIX) and f.endswith(".json")):
        try:
            doc = json.loads(H.text(p))
        except ValueError:
            continue
        if doc.get("snapshot") == B.sha:
            manifests.append((doc.get("revision") or 0, p, doc))
    man_rel, man = max(manifests, key=lambda x: x[:2])[1:] if manifests else (None, {})
    reasons = list(target_reasons)
    if module_changed:
        reasons.append({"why": f"{len(module_changed)} target module(s) changed: mutant counts and nulls re-derived",
                        "targets": module_changed, "files": sorted({t.split("::")[0] for t in module_changed})})
    for p, sha in sorted(_bindings(man).items()):
        if _sha256(_raw(root, H.sha, p)) != sha:
            reasons.append({"why": f"{p}: its sha256 at head is not the one the manifest binds", "files": [p]})
    bound_kill = set(man.get("versions", {}).get("kill_files", {}))
    unbound = sorted({f for k in H.targets.values() for f in k} - bound_kill) if man else []
    if unbound:
        reasons.append({"why": f"kill files the manifest does not bind: {', '.join(unbound)}", "files": unbound})
    out.append({"record": man_rel, "action": "a new manifest revision", "rederive": bool(reasons), "reasons": reasons,
                **({} if man_rel else {"note": f"no {MANIFEST_PREFIX}*.json at head has snapshot {B.sha[:12]}"})})
    t0_rel = man.get("t0", {}).get("path")
    pairs: list[dict] = []
    if t0_rel and H.text(t0_rel):
        rec = json.loads(H.text(t0_rel))
        rows_t0 = {(r["module"], r["null"], r["file"]): r for r in rec["rows"]}

        def needed(R: Rev) -> dict[tuple, list[str]]:
            need: dict[tuple, list[str]] = {}
            for t, kill in R.targets.items():
                rel = t.split("::")[0]
                for f in kill:
                    r = rows_t0.get((rel, R.null(t), f))
                    ok = r and not r.get("error") and [x["outcome"] for x in r["rows"] if x.get("role") == "t0"] == ["PASS"]
                    why = "no PASS T0 row" if not ok else \
                        "the kill file changed since the sweep" if S2.blob(root, rec["measured_on"], f) != R.blob(f) else None
                    if why:
                        need.setdefault((rel, R.null(t), f, why), []).append(t)
            return need
        at_base, at_head = needed(B), needed(H)
        pairs = [{"module": k[0], "null": k[1], "file": k[2], "why": k[3], "targets": sorted(v)}
                 for k, v in sorted(at_head.items()) if k not in at_base]
        out.append({"record": t0_rel, "action": "measure these T0 pairs (a new sweep record)", "rederive": bool(pairs),
                    "reasons": [{"why": f"{p['why']}: {p['module']} null {p['null'][:16]} x {p['file']}",
                                 "targets": p["targets"], "files": [p["file"]]} for p in pairs],
                    "already_needed_at_base": len(at_base)})
    eo_rel = man.get("execution_order", {}).get("path")
    if eo_rel:
        eo = list(target_reasons)
        null_changed = [t for t in both if t not in module_changed and B.null(t) != H.null(t)]
        if null_changed:
            eo.append({"why": f"{len(null_changed)} null mutant(s) changed", "targets": null_changed, "files": harness_file})
        if module_changed:
            eo.append({"why": f"{len(module_changed)} target module(s) changed (their null mutants)",
                       "targets": module_changed, "files": sorted({t.split("::")[0] for t in module_changed})})
        if pairs:
            eo.append({"why": f"{len(pairs)} T0 pair(s) to measure", "files": sorted({p["file"] for p in pairs})})
        for p in ("validation/v2/execution_order.py", t0_rel):
            if p and B.blob(p) != H.blob(p):
                eo.append({"why": f"{p} changed", "files": [p]})
        out.append({"record": eo_rel, "action": "re-derive the table (execution_order.py --write)", "rederive": bool(eo),
                    "reasons": eo})
    src = H.text(CALIBRATION)
    if src:
        consts = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        q0_rel = next((n.value.value for n in ast.parse(src).body if isinstance(n, ast.Assign)
                       and [getattr(x, "id", None) for x in n.targets] == ["OUT_REL"]), None)
        hits = sorted(p for r in rows for p in [r["path"], r.get("from")] if p and (
            p == CALIBRATION or p.startswith(KNOWN_BAD) or p in consts
            or (p.startswith("validation/v2/") and p.count("/") == 2 and p.endswith(".py"))))
        out.append({"record": q0_rel, "action": "re-derive the Q0 checker calibration", "rederive": bool(hits),
                    "reasons": [{"why": f"{p}: a checker, its source or its known-bad fixture changed", "files": [p]}
                                for p in hits],
                    **({"note": "not written at head"} if q0_rel and H.blob(q0_rel) is None else {})})
    return out


def build(root: pathlib.Path, base: str, head: str, read_set: pathlib.Path | None = None) -> tuple[dict, str]:
    git = S2._git
    shown: dict[tuple, object] = {}

    def memo(r: pathlib.Path, *args: str):
        """`git show <full sha>:<path>` names an immutable object: asked once per build (s2_mutation_record.closure
        asks it once per closure). Every other git call passes through."""
        if args[0] == "show" and len(args) == 2 and len(args[1].split(":", 1)[0]) == 40:
            key = (str(r), args[1])
            if key not in shown:
                shown[key] = git(r, *args)
            return shown[key]
        return git(r, *args)
    S2._git = memo
    try:
        with tempfile.TemporaryDirectory() as tmp:
            B, H = Rev(root, base, pathlib.Path(tmp)), Rev(root, head, pathlib.Path(tmp))
            rs = None
            if read_set is not None:
                path = pathlib.Path(read_set)
                rel = path.resolve().relative_to(root.resolve()).as_posix() if path.resolve().is_relative_to(
                    root.resolve()) else str(path)
                rs = {"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "commit": H.sha,
                      "measured": _read_set(path, H.sha)}
            return _build(B, H, rs)
    finally:
        S2._git = git


def _build(B: Rev, H: Rev, rs: dict | None = None) -> tuple[dict, str]:
    root = B.root
    measured = rs["measured"] if rs else None
    changed, why = _listing_rule(B, H) if rs else (None, "")
    targets = sorted(set(B.targets) | set(H.targets))
    verdicts = {t: verdict(B, H, t) for t in targets}
    kc = _kill_closures(B, H)
    tclosure = {t: {g for f in {*B.targets.get(t, []), *H.targets.get(t, [])} for g in kc[f]} for t in targets}
    harness = S2.closure(root, B.sha, HARNESS) | S2.closure(root, H.sha, HARNESS)
    copy = tuple(dict.fromkeys(B.copy + H.copy))
    unmeasured_n = dict.fromkeys(targets, 0)
    rows = []
    for ch in _changes(root, B.sha, H.sha):
        kinds, affected, related, data = [], {}, set(), None
        sides = [x for x in (ch.get("from"), ch["path"]) if x]
        for p in sides:
            if p.startswith("aisef2/"):
                kinds.append("product")
                for t in targets:
                    if t.split("::")[0] == p:
                        affected.setdefault(t, []).append("module digest: a target of this module")
                        related.update(f for R in (B, H) for f in R.targets.get(t, []))
                    elif any(p in R.imports(t.split("::")[0]) for R in (B, H)):
                        affected.setdefault(t, []).append("its module imports this file (enum members: generator input)")
            for t in targets:
                kb, kh = p in B.targets.get(t, []), p in H.targets.get(t, [])
                if kb or kh:
                    kinds.append("kill_file")
                    affected.setdefault(t, []).append("in its kill set" if kb and kh else
                                                      "added to its kill set" if kh else "removed from its kill set")
                    related.add(p)
            via = {f for f, c in kc.items() if p in c and f != p}
            if via:
                kinds.append("kill_closure")
                related.update(via)
                for t in targets:
                    if p in tclosure[t] and not any(p in R.targets.get(t, []) for R in (B, H)):
                        affected.setdefault(t, []).append("in its kill tests' closure" + (
                            "" if p.startswith("tests/") else " (code outside tests/: reported, not counted)"))
            if p in harness:
                kinds.append("harness")
                related.add("mutation harness")
                for t in targets:
                    affected.setdefault(t, []).append("harness change (every V2.1 target)")
            if p not in harness and any(p == c or p.startswith(c + "/") for c in copy):
                read, unmeasured, cleared = _data(B, H, p, kc, measured, copy, changed)
                data = data or {"read_by": {}, "not_measured": set(), "cleared": set(), "provisional": set()}
                data["read_by"] |= {k: w for k, w in read.items() if k not in data["read_by"]}
                data["not_measured"] |= unmeasured
                data["cleared"] |= cleared
                for t in targets:   # its own module is the target-file rule's
                    kill = {*B.targets.get(t, []), *H.targets.get(t, [])}
                    if p != t.split("::")[0]:
                        if kill & set(read):
                            how = "measured" if "measured" in {read[k] for k in kill & set(read)} else "found statically"
                            affected.setdefault(t, []).append(READ[how])
                        if kill & unmeasured:
                            data["provisional"].add(t)
                related.update(read)
        if data:
            hit = any(set(READ.values()) & set(w) for w in affected.values())
            kinds += [DATA] * hit + [UNMEASURED] * bool(data["provisional"]) + [UNREAD] * (
                not hit and not data["provisional"] and bool(data["cleared"]))
            for t in data["provisional"]:
                unmeasured_n[t] += 1
            data = {"read_by": dict(sorted(data["read_by"].items())), "not_measured": sorted(data["not_measured"]),
                    "cleared": sorted(data["cleared"] - data["not_measured"] - set(data["read_by"])),
                    "provisional": len(data["provisional"]),
                    "provisional_except": sorted(set(targets) - data["provisional"])}
        if not {"product", "kill_file", "kill_closure", "harness"} & set(kinds) and any(
                x.endswith((".py", ".sh")) or any((R.text(x) or "").startswith("#!") for R in (B, H)) for x in sides):
            kinds.insert(0, CODE)
        row = {**ch, "kinds": list(dict.fromkeys(kinds)) or [EVIDENCE],
               "targets": {t: list(dict.fromkeys(w)) for t, w in sorted(affected.items())},
               "tests_or_harness": sorted(related), **({"read_set": data} if data else {})}
        if ch["path"].endswith(".py") or ch.get("from", "").endswith(".py"):
            row["names_changed"] = changed_names(B.text(ch.get("from", ch["path"])), H.text(ch["path"]))
        rows.append(row)
    records = _records(B, H, rows)
    for row in rows:
        paths = {row["path"], row.get("from")}
        row["remeasure"] = sorted(t for t in row["targets"] if verdicts[t]["reasons"])
        row["records"] = [r["record"] for r in records if any(paths & set(x.get("files", [])) for x in r["reasons"])]
    affected = {t for r in rows for t in r["targets"]}
    b7 = B.sha[:7]
    hpaths = [r["path"] for r in rows if "harness" in r["kinds"]]
    for t in targets:
        v, out = verdicts[t], []
        v["read_set_not_measured"] = n = unmeasured_n[t]
        v["data_read"] = sum(1 for r in rows if READ["measured"] in r["targets"].get(t, []))
        if t not in H.targets:
            continue
        if hpaths:
            out.append(f"harness change: {', '.join(hpaths)} changed since {b7} (the runner's code; the proof's rules "
                       f"do not bind it)")
        for how in READ:
            notes = [r["path"] for r in rows if READ[how] in r["targets"].get(t, [])]
            if notes:
                out.append(f"{NOTE[how]}: {', '.join(notes)}" + (
                    f" — the {b7} result is no ground at head (the proof's rules do not cover data): re-measure it"
                    if how == "measured" and not v["reasons"] else ""))
        if n:
            out.append(f"inside mutation.COPY, read-set not measured: {n} changed file(s) — " + (
                "a re-measure at head reads them as they are" if v["reasons"] else
                f"the {b7} result stands only PROVISIONALLY until a measured read-set (an audit-hook run of its kill "
                f"files: --read-set) clears them"))
        if out:
            v["outside_the_proof"] = out
    stand = [t for t, v in verdicts.items() if v["verdict"].startswith(f"a {b7}")]
    doc = {
        "record": "AISEF V2.1 — SNAPSHOT DELTA (owner rule 2026-10-08)",
        "tool": {"path": TOOL_REL, "sha256": hashlib.sha256((HERE / "v21_snapshot_delta.py").read_bytes()).hexdigest()},
        "proof": {"path": PROOF_REL, "criteria_sha256": MR.criteria_sha256(PROOF)},
        "base": B.sha, "head": H.sha, "rules": RULES,
        "read_set": {**{k: rs[k] for k in ("path", "sha256", "commit")}, "kill_files": len(measured),
                     "listing_discount": {"applies": changed is not None, "why": why,
                                          "attributed": sum(1 for v in measured.values() if v[2])}} if rs else None,
        "counts": {"files": len(rows), "targets_at_base": len(B.targets), "targets_at_head": len(H.targets),
                   "affected_targets": len(affected),
                   "remeasure": sum(1 for v in verdicts.values() if v["verdict"].startswith("re-measure")),
                   "stand": len(stand), "provisional": sum(1 for t in stand if unmeasured_n[t]),
                   "data_read": sum(1 for t in stand if verdicts[t]["data_read"]),
                   "not_at_head": sum(1 for t in targets if t not in H.targets),
                   "remeasure_not_reached_by_any_file": sorted(t for t in targets if verdicts[t]["reasons"] and t not in affected)},
        "harness_changed": [{"path": r["path"], "names_changed": r.get("names_changed", [])}
                            for r in rows if "harness" in r["kinds"]],
        "files": rows, "targets": verdicts, "records": records,
    }
    return doc, markdown(doc)


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _short(items: list[str], n: int = 6) -> str:
    return ", ".join(f"`{x}`" for x in items[:n]) + (f" +{len(items) - n} more (DELTA.json)" if len(items) > n else "")


def markdown(doc: dict) -> str:
    b7, h7, c = doc["base"][:7], doc["head"][:7], doc["counts"]
    every = c["targets_at_head"] + c["not_at_head"]
    lines = [f"# V2.1 snapshot delta {b7} → {h7}", "",
             f"Derived by `{TOOL_REL}` (`--check` re-derives it byte for byte): base `{doc['base']}`, head "
             f"`{doc['head']}`. {c['files']} files changed; {c['targets_at_head']} V2.1 targets at head "
             f"({c['targets_at_base']} at base); {c['affected_targets']} affected; **{c['remeasure']} re-measure**, "
             f"{c['stand']} can stand by the proof's rules (`v21_mutation_record.proof`), {c['not_at_head']} not a "
             f"target at head.", ""]
    rs = doc["read_set"]
    lines.append(f"Read-set of the kill files: measured at `{rs['commit'][:12]}` (`{rs['path']}`, sha256 `{rs['sha256'][:16]}`, "
                 f"{rs['kill_files']} kill files)." if rs else "Read-set of the kill files: **not measured** (no `--read-set`).")
    if rs:
        ld = rs["listing_discount"]
        if not ld["applies"]:
            lines.append(f"**Listing discount off** (every changed file under a directory a kill file listed is read by "
                         f"it): {ld['why']}.")
        elif not ld["attributed"]:
            lines.append("Listing discount: the record has no `listed_by` for any kill file, so every changed file under "
                         "a directory a kill file listed is read by it.")
        else:
            lines.append(f"Listings by `{REGISTRY}` (`{REGISTRY_FN}`: only the set of directories holding a "
                         f"`{TEST_MODULE}`) read a changed file of `{TESTS_V2}` only as the first or last test module of "
                         f"a directory (`listed_by` in {ld['attributed']} of {rs['kill_files']} kill files): {ld['why']}.")
    n_un = sum(1 for r in doc["files"] if UNMEASURED in r["kinds"])
    if c["provisional"]:
        lines.append(f"**{c['provisional']} of the {c['stand']} that can stand do so only PROVISIONALLY**: {n_un} changed "
                     f"files inside `mutation.COPY` may be read by their kill tests and that reading is not measured; a "
                     f"measured read-set (an audit-hook run of the kill files at head, after the campaign: `--read-set`) "
                     f"clears them or names the targets they reach.")
    if c["data_read"]:
        lines.append(f"**{c['data_read']} of the {c['stand']} that can stand by the proof's rules have kill tests that read "
                     f"changed data inside `mutation.COPY` (measured)**: the proof's rules do not cover data, so a {b7} "
                     f"result is no ground for them at head; re-measure them.")
    for h in doc["harness_changed"]:
        lines.append(f"Harness changed: `{h['path']}` (top-level names changed: "
                     f"{', '.join(h['names_changed']) or 'none'}). The proof's rules do not bind the runner's code; "
                     f"every V2.1 target is listed as affected by it.")
    if c["remeasure_not_reached_by_any_file"]:
        lines.append(f"Re-measure found by the proof only (no file row reaches it): {_short(c['remeasure_not_reached_by_any_file'])}")
    lines += ["", "## Files", "", "| file | kind | targets | tests/harness | evidence to re-measure |", "|---|---|---|---|---|"]
    for r in doc["files"]:
        name = f"`{r['from']}` → `{r['path']}`" if r.get("from") else f"`{r['path']}`"
        ts = list(r["targets"])
        if ts and len(ts) == every and "harness" in r["kinds"]:
            tcell = f"every V2.1 target ({len(ts)}): harness change"
        else:
            whys = sorted({w for t in ts for w in r["targets"][t]})
            tcell = f"{len(ts)}: {_short(ts)} — {'; '.join(whys)}" if ts else "—"
        ev = ([f"re-measure {len(r['remeasure'])}: {_short(r['remeasure'])}"] if r["remeasure"] else []) + \
             [f"re-derive `{x}`" for x in r["records"] if x]
        if ts and not r["remeasure"]:
            ev.insert(0, "no target re-measured by the proof's rules")
        rd = [t for t in ts if READ["measured"] in r["targets"][t] and t not in r["remeasure"]]
        if rd:
            ev.append(f"read by their kill tests (measured; outside the proof's rules): re-measure {len(rd)}: {_short(rd)}")
        d = r.get("read_set")
        if d and d["provisional"]:
            who = "every target" if d["provisional"] == every else \
                f"{d['provisional']} targets (every target but {_short(d['provisional_except'], 3)})"
            tcell = (tcell if ts else "") + ("; " if ts else "") + f"provisional: {who}"
            ev.append(f"the {b7} results stand only PROVISIONALLY for {who} until a measured read-set (an audit-hook "
                      f"run of the kill files) clears it")
        label = {DATA: f"{DATA} (read by {_short(list(d['read_by']), 3)})" if d else DATA,
                 UNMEASURED: f"{UNMEASURED} (inside COPY, read-set not measured: {len(d['not_measured'])} kill files)"
                 if d else UNMEASURED, UNREAD: f"{UNREAD} (inside COPY, read by no kill file: measured)"}
        kinds = ", ".join(label.get(k, k) for k in r["kinds"])
        names = f" names: {', '.join(r['names_changed'])}" if r.get("names_changed") else ""
        lines.append(f"| {name} ({r['status']}) | {_cell(kinds)}{_cell(names)} | {_cell(tcell)} | "
                     f"{_cell(_short(r['tests_or_harness'], 4)) or '—'} | {_cell('; '.join(ev)) or '—'} |")
    lines += ["", "## Targets (affected, or re-measured)", "", "| target | verdict | outside the proof's rules |", "|---|---|---|"]
    affected = {t for r in doc["files"] for t in r["targets"]}
    for t, v in doc["targets"].items():
        if t in affected or v["reasons"] or v["read_set_not_measured"]:
            out = "; ".join(v.get("outside_the_proof", []) + ([f"other code changed: {', '.join(v['other_code_changed'])}"]
                                                              if v["other_code_changed"] else []))
            lines.append(f"| `{t}` | {_cell(v['verdict'])} | {_cell(out) or '—'} |")
    lines += ["", "## Records", "", "| record | re-derive | why |", "|---|---|---|"]
    for r in doc["records"]:
        why = "; ".join(x["why"] + (f" ({_short(x['targets'], 4)})" if x.get("targets") else "") for x in r["reasons"])
        lines.append(f"| `{r['record']}` | {'yes: ' + r['action'] if r['rederive'] else 'no'} | "
                     f"{_cell(why or r.get('note', '—'))}{_cell(' — ' + r['note']) if why and r.get('note') else ''} |")
    return "\n".join(lines) + "\n"


def check(root: pathlib.Path, out_dir: pathlib.Path) -> list[str]:
    """[] when the table at `out_dir` is what its base..head derives now and HEAD holds no later change it misses."""
    try:
        doc = json.loads((out_dir / "DELTA.json").read_text(encoding="utf-8"))
        base, head = doc["base"], doc["head"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"{out_dir}/DELTA.json cannot be read: {e!r}"]
    if S2._git(root, "merge-base", "--is-ancestor", head, "HEAD").returncode != 0:
        return [f"the table's head {head[:12]} is not HEAD or an ancestor of it"]
    proof = MR.criteria_sha256(PROOF)
    if (doc.get("proof") or {}).get("criteria_sha256") != proof:
        return [f"{PROOF_REL}: its reuse criteria (criteria_sha256 {proof[:16]}) are not the ones the table was derived "
                f"beside: verdict() re-implements proof() — compare the two before re-deriving the table"]
    rs = doc.get("read_set")
    if rs:
        path = root / rs["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != rs["sha256"]:
            return [f"the read-set the table records ({rs['path']}) is missing or not the file it was built from"]
    new, md = build(root, base, head, root / rs["path"] if rs else None)
    out = [f"{out_dir}/{name} is not what {base[:12]}..{head[:12]} derives now"
           for name, text in (("DELTA.json", S2._render(new)), ("DELTA.md", md))
           if not (out_dir / name).is_file() or (out_dir / name).read_text(encoding="utf-8") != text]
    now = S2._git(root, "rev-parse", "HEAD").stdout.decode().strip()
    if now != head:
        inside = out_dir.resolve().is_relative_to(root.resolve())
        rel = out_dir.resolve().relative_to(root.resolve()).as_posix() + "/" if inside else None
        later = {r["path"] for r in _changes(root, head, now) if not (rel and r["path"].startswith(rel))}
        if later:
            full, _ = build(root, base, now)
            bad = sorted(r["path"] for r in full["files"] if r["path"] in later and (not set(r["kinds"]) <= COVERED or r["records"]))
            if bad:
                out.append(f"stale: HEAD {now[:12]} has changes after the table's head {head[:12]} that it does not "
                           f"cover: {', '.join(bad)}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", metavar="OUT_DIR")
    mode.add_argument("--check", metavar="OUT_DIR")
    ap.add_argument("--base", help="--write: the snapshot the campaign measures")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--read-set", metavar="READSET.json", type=pathlib.Path,
                    help="--write: the files each kill file opened or listed, recorded at the head (module docstring)")
    a = ap.parse_args(argv)
    if a.write:
        if not a.base:
            ap.error("--write needs --base")
        doc, md = build(ROOT, a.base, a.head, a.read_set)
        out = pathlib.Path(a.write)
        out.mkdir(parents=True, exist_ok=True)
        (out / "DELTA.json").write_text(S2._render(doc), encoding="utf-8")
        (out / "DELTA.md").write_text(md, encoding="utf-8")
        print(json.dumps(doc["counts"], indent=1))
        return 0
    problems = check(ROOT, pathlib.Path(a.check))
    for p in problems:
        print(f"FAIL  {p}")
    print("v2.1 snapshot delta: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
