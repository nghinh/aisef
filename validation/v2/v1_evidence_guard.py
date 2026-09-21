"""WP-0.4 — V1 evidence guard.

**Protected set:** every git-tracked file under `closure-evidence/`, excluding `closure-evidence/v2/`. Git-ignored
local artefacts under `closure-evidence/` (e.g. `differential-p12-*.rows.jsonl`) are not tracked evidence and are
outside the detective check's scope; the preventive layer still refuses writes anywhere under the protected
directory.

Two layers, graded honestly:

* **PREVENTIVE** — `install()` registers an interpreter audit hook that refuses, inside the current Python
  process, any open-for-write, rename/replace, remove, rmdir, truncate, chmod, link, symlink or rmtree whose
  target resolves into the protected directory. The test suite arms it at discovery time
  (`tests/v2/test_v1_evidence_guard.py`). It does **not** cover subprocesses, other processes, or a module
  run on its own without the arming import, and a symlinked alias with an absolute path can evade its fast path.
* **DETECTIVE** — `check()` compares the repository with `V1-EVIDENCE-BASELINE.json` using git objects, so a
  Windows `autocrlf` checkout compares correctly: (1) the baseline agrees with the V1 closure revision;
  (2) HEAD's protected entries equal the baseline (a *committed* mutation fails); (3) the working tree has no
  modified, deleted or untracked-and-not-ignored file in the protected set.

**Overall grade: DETECTIVE.** The preventive layer covers only in-process Python writes, and a claim is graded by
its weakest path. A detected mutation fails closed; the mutated file is never valid evidence, and restoring it is
maintenance, not proof.

    python -P validation/v2/v1_evidence_guard.py --baseline   # write the baseline (refuses on a dirty tree)
    python -P validation/v2/v1_evidence_guard.py --check      # detective check; exit 1 on any violation
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTECTED_DIR = "closure-evidence"
EXCLUDED_DIR = "closure-evidence/v2"
PATHSPEC = [PROTECTED_DIR, f":!{EXCLUDED_DIR}"]
BASELINE_REL = "closure-evidence/v2/V1-EVIDENCE-BASELINE.json"

#: The V1 closure revision: "AISEF V1 — W1 qualification final verdict". No later commit may touch the protected
#: set, and the baseline must agree with this revision entry for entry.
V1_CLOSE = "b0d87c6f5f59a43dd72844a1aef72b678de865f1"

ENFORCEMENT = {
    "preventive_layer": "in-process audit hook: refuses write-intent open, rename/replace, remove, rmdir, truncate, "
                        "chmod, link, symlink and rmtree into closure-evidence/ (excluding v2/)",
    "preventive_scope": "Python code inside a process where the hook is armed (the test suite, at discovery)",
    "preventive_does_not_cover": ["subprocesses and other processes",
                                  "a test module run on its own without the arming import",
                                  "an absolute path through a symlinked alias of the protected directory",
                                  "a relative path whose dir_fd the platform cannot resolve (resolved on Linux and "
                                  "macOS only)"],
    "detective_layer": "git-object comparison against this baseline: baseline == V1 closure revision, "
                       "HEAD == baseline, and a clean working tree for the protected set",
    "detective_wiring": "CI step after the unit suite; any violation exits non-zero",
    "overall_grade": "DETECTIVE",
    "why_detective": "the preventive layer covers in-process Python writes only; a claim is graded by its weakest "
                     "path (RFC §24). A detected mutation fails closed and the mutated file is never valid evidence; "
                     "restoration is maintenance, not proof.",
}


def _git(*args: str, root: pathlib.Path = ROOT, text: bool = True) -> str | bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=text, check=True).stdout


def tracked_entries(rev: str, root: pathlib.Path = ROOT) -> dict[str, str]:
    """path -> blob id for every tracked protected file at `rev`."""
    out = _git("ls-tree", "-r", "-z", rev, "--", PROTECTED_DIR, root=root)
    entries = {}
    for rec in out.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        if path.startswith(EXCLUDED_DIR + "/"):
            continue
        entries[path] = meta.split()[2]
    return entries


def _last_commits(root: pathlib.Path) -> dict[str, str]:
    """path -> the most recent commit touching it, in one pass over history."""
    out = _git("log", "--format=@%H", "--name-only", "--", *PATHSPEC, root=root)
    last: dict[str, str] = {}
    commit = ""
    for line in out.splitlines():
        if line.startswith("@"):
            commit = line[1:]
        elif line and line not in last:
            last[line] = commit
    return last


def _blob_sha256(blobs: list[str], root: pathlib.Path) -> dict[str, str]:
    """blob id -> sha256 of its canonical (committed) bytes, streamed through one `git cat-file --batch`."""
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=root, input="\n".join(blobs).encode() + b"\n",
                          capture_output=True, check=True)
    data, i, out = proc.stdout, 0, {}
    for blob in blobs:
        nl = data.index(b"\n", i)
        size = int(data[i:nl].split()[2])
        start = nl + 1
        out[blob] = hashlib.sha256(data[start:start + size]).hexdigest()
        i = start + size + 1
    return out


def working_tree_changes(root: pathlib.Path = ROOT) -> list[str]:
    out = _git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *PATHSPEC, root=root)
    return [r for r in out.split("\0") if r]


def build_baseline(root: pathlib.Path = ROOT, source: str = V1_CLOSE) -> dict:
    changes = working_tree_changes(root)
    if changes:
        raise RuntimeError(f"refusing to baseline a dirty protected set: {changes[:5]}")
    head = _git("rev-parse", "HEAD", root=root).strip()
    at_source, at_head = tracked_entries(source, root), tracked_entries("HEAD", root)
    if at_source != at_head:
        raise RuntimeError("refusing to baseline: HEAD's protected set differs from the V1 closure revision")
    last = _last_commits(root)
    shas = _blob_sha256(sorted(set(at_head.values())), root)
    files = [{"path": p, "blob": b, "sha256": shas[b], "last_commit": last.get(p, "")}
             for p, b in sorted(at_head.items())]
    listing = "".join(f"{f['path']}\t{f['blob']}\n" for f in files)
    return {
        "baseline": "AISEF V1 EVIDENCE BASELINE",
        "work_package": "WP-0.4",
        "protected_scope": "every git-tracked file under closure-evidence/, excluding closure-evidence/v2/",
        "excluded": [EXCLUDED_DIR + "/"],
        "not_in_detective_scope": "git-ignored local artefacts under closure-evidence/ (not tracked evidence)",
        "source_revision": _git("rev-parse", source, root=root).strip(),
        "source_revision_role": "AISEF V1 — W1 qualification final verdict (V1 closure)",
        "generated_at_head": head,
        "head_equals_source_for_protected_set": True,
        "file_count": len(files),
        "files_digest_sha256": hashlib.sha256(listing.encode()).hexdigest(),
        "files_digest_rule": "sha256 over sorted lines '<path>\\t<blob>\\n'",
        "comparison_key": "git blob id (platform-independent; a Windows autocrlf checkout compares correctly)",
        "enforcement": ENFORCEMENT,
        "files": files,
    }


def check(root: pathlib.Path = ROOT, baseline_rel: str = BASELINE_REL, source: str = V1_CLOSE) -> list[str]:
    path = root / baseline_rel
    if not path.exists():
        return [f"{baseline_rel} is missing"]
    base = json.loads(path.read_text(encoding="utf-8"))
    expected = {f["path"]: f["blob"] for f in base["files"]}
    problems: list[str] = []
    listing = "".join(f"{p}\t{b}\n" for p, b in sorted(expected.items()))
    if hashlib.sha256(listing.encode()).hexdigest() != base.get("files_digest_sha256"):
        problems.append("baseline is internally inconsistent: files_digest_sha256 does not match its entries")
    try:
        at_source = tracked_entries(source, root)
    except subprocess.CalledProcessError:
        problems.append(f"V1 closure revision {source[:12]} is not available; cannot verify the baseline")
        at_source = None
    if at_source is not None and at_source != expected:
        problems.append("baseline does not agree with the V1 closure revision (the baseline itself was altered)")
    at_head = tracked_entries("HEAD", root)
    for p in sorted(set(expected) | set(at_head)):
        if p not in at_head:
            problems.append(f"committed deletion of protected evidence: {p}")
        elif p not in expected:
            problems.append(f"committed addition to protected evidence: {p}")
        elif at_head[p] != expected[p]:
            problems.append(f"committed mutation of protected evidence: {p}")
    for rec in working_tree_changes(root):
        problems.append(f"working-tree change to protected evidence: {rec}")
    return problems


# --------------------------------------------------------------------------------------- preventive layer

_armed: dict[str, object] = {}
_local = threading.local()
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
#: event -> [(index of a target path, index of the dir_fd that path is relative to, or None)]. The audit
#: argument layouts are CPython's. A relative path with a dir_fd is relative to that directory, NOT the cwd —
#: `shutil.rmtree` removes `closure-evidence` inside a throwaway repo exactly this way.
_PATH_EVENTS = {"os.remove": [(0, 1)], "os.rmdir": [(0, 1)], "os.truncate": [(0, None)],
                "os.chmod": [(0, 2)], "os.rename": [(0, 2), (1, 3)], "os.link": [(1, 3)],
                "os.symlink": [(1, 2)], "shutil.rmtree": [(0, 1)]}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(p))


def _fd_dir(fd: int) -> str | None:
    """The directory a dir_fd refers to, where the platform can say; None otherwise."""
    try:
        if sys.platform.startswith("linux"):
            return os.readlink(f"/proc/self/fd/{fd}")
        if sys.platform == "darwin":
            import fcntl
            return fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0].decode()
    except (OSError, AttributeError, ValueError):
        pass
    return None


def _is_protected(raw: object, base: str, excluded: str, dir_fd: object = None) -> bool:
    if isinstance(raw, int):
        return False
    try:
        p = os.fsdecode(os.fspath(raw))
    except TypeError:
        return False
    if os.path.isabs(p):
        if PROTECTED_DIR not in p:
            return False  # fast path; see ENFORCEMENT["preventive_does_not_cover"]
        full = _norm(p)
    elif isinstance(dir_fd, int):
        anchor = _fd_dir(dir_fd)
        if anchor is None:
            return False  # unresolvable dir_fd: left to the detective layer
        full = _norm(os.path.join(anchor, p))
    else:
        full = _norm(os.path.join(os.getcwd(), p))
    inside = full == base or full.startswith(base + os.sep)
    in_excluded = full == excluded or full.startswith(excluded + os.sep)
    return inside and not in_excluded


def install(mode: str = "enforce", log: pathlib.Path | None = None, root: pathlib.Path = ROOT) -> None:
    """Arm the preventive layer for this process. Idempotent. `mode` is 'enforce' or 'record' (measurement)."""
    if _armed:
        return
    base, excluded = _norm(str(root / PROTECTED_DIR)), _norm(str(root / EXCLUDED_DIR))
    _armed.update(mode=mode, log=log)

    def hook(event: str, args: tuple) -> None:
        if getattr(_local, "busy", False):
            return
        targets: list[tuple[object, object]] = []
        if event == "open":
            path, fmode, flags = (list(args) + [None, None, None])[:3]
            writes = (isinstance(flags, int) and flags & _WRITE_FLAGS) or \
                     (isinstance(fmode, str) and any(c in fmode for c in "wax+"))
            if writes:
                targets.append((path, None))
        elif event in _PATH_EVENTS:
            for pi, fi in _PATH_EVENTS[event]:
                if pi < len(args):
                    targets.append((args[pi], args[fi] if fi is not None and fi < len(args) else None))
        else:
            return
        _local.busy = True
        try:
            hit = next((t for t, fd in targets if _is_protected(t, base, excluded, fd)), None)
            if hit is None:
                return
            if _armed["mode"] == "record":
                if _armed["log"] is not None:
                    with open(_armed["log"], "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"event": event, "path": os.fsdecode(os.fspath(hit))}) + "\n")
                return
            raise PermissionError(f"V1 evidence is frozen: refusing {event} on {os.fsdecode(os.fspath(hit))}")
        finally:
            _local.busy = False

    sys.addaudithook(hook)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--baseline" in argv:
        b = build_baseline()
        (ROOT / BASELINE_REL).write_text(json.dumps(b, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE_REL}: {b['file_count']} protected files, source {b['source_revision'][:12]}")
        return 0
    problems = check()
    for p in problems[:50]:
        print(f"FAIL  {p}")
    if len(problems) > 50:
        print(f"... and {len(problems) - 50} more")
    print(f"V1 evidence guard ({ENFORCEMENT['overall_grade']}): " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
