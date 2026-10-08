"""V2.1 campaign 2: the comparison table of every change after the snapshot the campaign measures (owner rule
2026-10-08: campaign 2 is measured at 5719f1f; every later change on v2.1/foundation needs a table — file, affected
targets, related tests/harness, evidence to re-measure — and no result of the snapshot is attached to a newer head
without sufficient grounds).

    python -P validation/qualification/v21_snapshot_delta.py --base 5719f1f [--head HEAD] --write OUT_DIR
    python -P validation/qualification/v21_snapshot_delta.py --check OUT_DIR

--write: OUT_DIR/DELTA.json (machine) and OUT_DIR/DELTA.md (the table). --check: the table's head is HEAD or an
ancestor of it; both files are byte for byte what base..head derives now; and no file changed after the table's head
(outside OUT_DIR) is anything but evidence/doc with no record binding it — otherwise the table is stale.

Each commit's harness is read from that commit (its validation/v2/mutation.py: V21_TARGETS, COPY, the generator), never
from the working tree. Every file of `git diff -M --name-status base head` (both sides of a rename) gets its kinds and
the V2.1 targets it affects (RULES). Every V2.1 target of either side gets the verdict of
validation/qualification/v21_mutation_record.proof, applied to a result measured at base: the target file is
byte-identical, the kill set is the head's, no tests/ file of the kill tests' closure (s2_mutation_record.closure, the
base kill set at both commits) changed, and the head's generator yields the base's mutants. The generator is run only
when its inputs differ (its source, the module, the enum members): it is deterministic, so identical inputs give the
identical list. What those rules do not bind (the runner's code, data the kill tests read) is reported beside the
verdict, never folded into it.
"""

from __future__ import annotations

import argparse
import ast
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

TOOL_REL = "validation/qualification/v21_snapshot_delta.py"
HARNESS = ("validation/v2/mutation.py", "validation/v2/execution_order.py", "validation/v2/owned_run.py",
           "validation/v2/cleanup_authority.py")
#: the definitions mutation.mutants() runs (with ast and copy of the same interpreter)
GENERATOR = ("_SWAP", "_inert", "_script", "_root", "mutants")
MANIFEST_PREFIX = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST"
CALIBRATION = "validation/v2/checker_calibration.py"
KNOWN_BAD = "tests/v2/fixtures/known_bad/"
EVIDENCE = "evidence/doc"
RULES = {
    "product": "a file under aisef2/: every target of that module (the module digest is whole-file); every target of a "
               "module that imports it from aisef2 (its enum members are generator input); every target whose kill "
               "tests' closure holds it (code outside tests/: reported by the proof, not counted)",
    "kill_file": "in a V2.1 target's kill set at base or head: that target",
    "kill_closure": "in the closure of a target's kill files (s2_mutation_record.closure, at base or head) without "
                    "being one: that target; under tests/ the proof counts it, elsewhere it reports it",
    "harness": "validation/v2/mutation.py, execution_order.py, owned_run.py, cleanup_authority.py and their closure: "
               "every V2.1 target, stated as such; the proof's rules do not bind the runner's code",
    "copy_data": "outside tests/ and the harness, inside mutation.COPY, and named in a tests/ file of a target's "
                 "kill-test closure (its repository path in the text, or a parent directory of two components or more "
                 "and the rest of the path or the basename, each as a whole quoted string): that target; outside the "
                 "proof's rules. A path built otherwise (a glob, a format string) is not found",
    EVIDENCE: "none of the above: no target",
    "verdict": "v21_mutation_record.proof for a result measured at base, at head",
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


def _named(B: Rev, H: Rev, path: str, closure_files: set[str]) -> list[str]:
    """The tests/ files of the kill-test closures that name `path`: its repository path in their text, or a parent
    directory (two components or more) and the rest of the path, or its basename, each as a whole quoted string."""
    parts = path.split("/")
    pairs = [("/".join(parts[:k]), r) for k in range(2, len(parts)) for r in {"/".join(parts[k:]), parts[-1]}]

    def quoted(s: str, x: str) -> bool:
        return any(q + x + e + q in s for q in "\"'" for e in ("", "/"))

    return sorted(f for f in closure_files if f.startswith("tests/") and any(
        (s := R.text(f)) and (path in s or any(quoted(s, d) and quoted(s, r) for d, r in pairs)) for R in (B, H)))


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
            manifests.append((doc.get("revision", 0), p, doc))
    man_rel, man = (manifests[-1][1], manifests[-1][2]) if manifests else (None, {})
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


def build(root: pathlib.Path, base: str, head: str) -> tuple[dict, str]:
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
            return _build(B, H)
    finally:
        S2._git = git


def _build(B: Rev, H: Rev) -> tuple[dict, str]:
    root = B.root
    targets = sorted(set(B.targets) | set(H.targets))
    verdicts = {t: verdict(B, H, t) for t in targets}
    kc = _kill_closures(B, H)
    tclosure = {t: {g for f in {*B.targets.get(t, []), *H.targets.get(t, [])} for g in kc[f]} for t in targets}
    harness = S2.closure(root, B.sha, HARNESS) | S2.closure(root, H.sha, HARNESS)
    copy = tuple(dict.fromkeys(B.copy + H.copy))
    rows = []
    for ch in _changes(root, B.sha, H.sha):
        kinds, affected, related = [], {}, set()
        for p in [x for x in (ch.get("from"), ch["path"]) if x]:
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
            if p not in harness and not p.startswith("tests/") and any(p == c or p.startswith(c + "/") for c in copy):
                namers = _named(B, H, p, {g for c in kc.values() for g in c})
                if namers:
                    kinds.append("copy_data")
                    related.update(namers)
                    for t in targets:
                        if tclosure[t] & set(namers):
                            affected.setdefault(t, []).append("data its kill tests read (outside the proof's rules)")
        row = {**ch, "kinds": list(dict.fromkeys(kinds)) or [EVIDENCE],
               "targets": {t: list(dict.fromkeys(w)) for t, w in sorted(affected.items())},
               "tests_or_harness": sorted(related)}
        if ch["path"].endswith(".py") or ch.get("from", "").endswith(".py"):
            row["names_changed"] = changed_names(B.text(ch.get("from", ch["path"])), H.text(ch["path"]))
        rows.append(row)
    records = _records(B, H, rows)
    for row in rows:
        paths = {row["path"], row.get("from")}
        row["remeasure"] = sorted(t for t in row["targets"] if verdicts[t]["reasons"])
        row["records"] = [r["record"] for r in records if any(paths & set(x.get("files", [])) for x in r["reasons"])]
    affected = {t for r in rows for t in r["targets"]}
    for t in targets:
        notes = [r["path"] for r in rows if "data its kill tests read (outside the proof's rules)" in r["targets"].get(t, [])]
        if notes:
            verdicts[t]["outside_the_proof"] = [f"data its kill tests read changed: {', '.join(notes)}"]
    doc = {
        "record": "AISEF V2.1 — SNAPSHOT DELTA (owner rule 2026-10-08)",
        "tool": {"path": TOOL_REL, "sha256": hashlib.sha256((HERE / "v21_snapshot_delta.py").read_bytes()).hexdigest()},
        "base": B.sha, "head": H.sha, "rules": RULES,
        "counts": {"files": len(rows), "targets_at_base": len(B.targets), "targets_at_head": len(H.targets),
                   "affected_targets": len(affected),
                   "remeasure": sum(1 for v in verdicts.values() if v["verdict"].startswith("re-measure")),
                   "stand": sum(1 for v in verdicts.values() if v["verdict"].startswith(f"a {B.sha[:7]}")),
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
        names = f" names: {', '.join(r['names_changed'])}" if r.get("names_changed") else ""
        lines.append(f"| {name} ({r['status']}) | {', '.join(r['kinds'])}{_cell(names)} | {_cell(tcell)} | "
                     f"{_cell(_short(r['tests_or_harness'], 4)) or '—'} | {_cell('; '.join(ev)) or '—'} |")
    lines += ["", "## Targets (affected, or re-measured)", "", "| target | verdict | outside the proof's rules |", "|---|---|---|"]
    affected = {t for r in doc["files"] for t in r["targets"]}
    for t, v in doc["targets"].items():
        if t in affected or v["reasons"]:
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
    new, md = build(root, base, head)
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
            bad = sorted(r["path"] for r in full["files"] if r["path"] in later and (r["kinds"] != [EVIDENCE] or r["records"]))
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
    a = ap.parse_args(argv)
    if a.write:
        if not a.base:
            ap.error("--write needs --base")
        doc, md = build(ROOT, a.base, a.head)
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
