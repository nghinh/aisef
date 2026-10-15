"""What is known about an Open Code Review binary, in three classes that are never merged. A verification tool, not
product code: nothing in aisef2/ imports it and no decision of a run reads its output.

    python3 -P validation/v21/ocr/inspect_binary.py EXE [--out FILE]
    python3 -P validation/v21/ocr/inspect_binary.py EXE --source DIR --modcache DIR [--ldflags "..."] [--out FILE]

(a) DECLARED  — what the binary prints for `version`: its own word. Asked the way the review stage asks it
    (`aisef2.app.adapters._declared`: clean environment, empty HOME). The strings are injected by the builder at link time
    (-ldflags -X); with `-trimpath` the Go toolchain does not even record those flags in the build info
    (cmd/go/internal/load/pkg.go, issue 52372), so nothing in the file says what they were set from.
(b) EMBEDDED  — the build info the Go toolchain stamped into the file, read with `go version -m` (it reads the file; it
    never runs it): Go version, GOOS/GOARCH, -trimpath, the VCS revision, time and modified flag it saw in the checkout,
    the module graph with its h1 hashes. Metadata the builder's toolchain wrote: a bit stronger than (a) because the go
    command, not the person building, fills the vcs.* fields — and still carried by the very file under test.
(c) REBUILT   — the sha256 of a build made HERE from a checkout of the pinned commit (offline, a module cache the
    operator provides), compared with the binary's. Only a byte-identical rebuild, or a signed upstream release artifact
    that was compared, is evidence of how the bytes were built. Without --source the section says NOT_PERFORMED and why.

The sha256 of the file is a fact about the bytes, whatever their origin; it is what the operator's pin names and what the
review stage checks before the binary runs. This tool adds nothing to a run's decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters, review_ocr  # noqa: E402

#: the strings `version` prints, which the binary must hold as data (they are not computed)
DECLARED_STRINGS = (b"v1.12.12", b"182898c", b"2026-10-05T00:00:00Z")
#: the sentinels the Go toolchain puts around the module-info string it stamps into a binary (runtime/debug/mod.go
#: infoStart and infoEnd): the lines `go version -m` prints lie between them, and the stamp is in the file twice
INFO_START = bytes.fromhex("3077af0c9274080241e1c107e6d618e6")
INFO_END = bytes.fromhex("f932433186182072008242104116d8f2")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_buildinfo(text: str) -> dict:
    """`go version -m` output: {go, path, mod, settings: {key: value}, deps: [[path, version, sum]]}."""
    out: dict = {"go": None, "path": None, "mod": None, "settings": {}, "deps": []}
    for n, line in enumerate(text.splitlines()):
        if n == 0:
            out["go"] = line.rsplit(": ", 1)[-1].strip()
            continue
        parts = line.strip("\t").split("\t")
        kind, rest = parts[0], parts[1:]
        if kind == "path":
            out["path"] = rest[0]
        elif kind == "mod":
            out["mod"] = rest
        elif kind == "dep":
            out["deps"].append(rest)
        elif kind == "build":
            key, _, value = rest[0].partition("=")
            out["settings"][key] = value
    return out


def embedded(exe: pathlib.Path) -> dict:
    """(b): the build info, read by the Go toolchain without running the file."""
    go = shutil.which("go")
    if go is None:
        return {"status": "NOT_AVAILABLE", "why": "no `go` on PATH"}
    r = subprocess.run([go, "version", "-m", str(exe)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if r.returncode != 0:
        return {"status": "NOT_AVAILABLE", "why": f"go version -m exited {r.returncode}: {r.stderr.strip()[:200]}"}
    info = parse_buildinfo(r.stdout)
    s = info["settings"]
    deps = sorted("\t".join(d) for d in info["deps"])
    return {"status": "READ", "tool": subprocess.run([go, "version"], capture_output=True, text=True, encoding="utf-8",
                                                      timeout=30).stdout.strip(),
            "go": info["go"], "path": info["path"], "module": info["mod"], "settings": s,
            "dependencies": len(deps), "dependencies_sha256": hashlib.sha256("\n".join(deps).encode("utf-8")).hexdigest(),
            "vcs_revision_is_the_pinned_commit": s.get("vcs.revision") == review_ocr.OCR["commit"],
            "vcs_modified": s.get("vcs.modified"), "trimpath": s.get("-trimpath"),
            "ldflags_recorded": "-ldflags" in s,
            "note": "with -trimpath the toolchain omits -ldflags from the build info: the flags that set (a) are not here"}


def held_as_data(data: bytes) -> dict:
    """Per string `version` prints: how often the file holds it, and how often OUTSIDE the stamped build info. The build
    info alone already carries `v1.12.12` (the `mod` line) and the first seven characters of `vcs.revision`, so `s in
    data` could not tell a string the builder set (-ldflags -X) from one the toolchain wrote; only an occurrence outside
    the stamp is the binary holding the string as data of its own. A stamp that is not closed counts as inside."""
    outside, pos = [], 0
    while (a := data.find(INFO_START, pos)) != -1:
        b = data.find(INFO_END, a)
        outside.append(data[pos:a])
        pos = len(data) if b == -1 else b + len(INFO_END)
    rest = b"\0".join([*outside, data[pos:]])
    return {s.decode(): {"in_file": data.count(s), "outside_build_info": rest.count(s)} for s in DECLARED_STRINGS}


def declared(exe: pathlib.Path) -> dict:
    """(a): the binary's own word, asked as the review stage asks (and the strings it holds as data of its own)."""
    seen, why = adapters._declared(str(exe), review_ocr.VERSION_TIMEOUT_S)
    return {"as_asked_by": "aisef2.app.adapters._declared (clean environment, empty HOME, cwd = that HOME)",
            "declared": seen, "accepted_by_the_gate": why is None, "why_not": why,
            "strings_held_as_data": held_as_data(exe.read_bytes())}


def codesign(exe: pathlib.Path) -> dict | None:
    if sys.platform != "darwin" or shutil.which("codesign") is None:
        return None
    r = subprocess.run(["codesign", "-dv", "--verbose=2", str(exe)], capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    return {"output": [ln for ln in r.stderr.splitlines() if not ln.startswith("Executable=")]}


def rebuild(exe: pathlib.Path, source: pathlib.Path, modcache: pathlib.Path, ldflags: str, build: dict) -> dict:
    """(c): build `./cmd/opencodereview` from `source` as the binary's own build info says it was built (GOOS, GOARCH,
    CGO_ENABLED, -trimpath) — offline, from `modcache` — and compare the bytes. `ldflags` is given by the operator:
    the binary does not record them."""
    pinned = review_ocr.OCR["commit"]
    git = lambda *a: subprocess.run(["git", "-C", str(source), *a], capture_output=True, text=True,  # noqa: E731
                                    encoding="utf-8", timeout=60)
    head, dirty = git("rev-parse", "HEAD"), git("status", "--porcelain")
    if head.returncode != 0:
        return {"status": "NOT_PERFORMED", "why": f"{source} is not a git checkout"}
    problems = []
    if head.stdout.strip() != pinned:
        problems.append(f"HEAD is {head.stdout.strip()[:12]}, not the pinned {pinned[:12]}")
    if dirty.stdout.strip():
        problems.append("the checkout has uncommitted changes")
    count = sum(1 for p in modcache.rglob("*") if p.is_file()) if modcache.is_dir() else 0
    if count == 0:
        problems.append(f"the module cache {modcache} holds no file: no dependency can be resolved offline")
    if problems:
        return {"status": "NOT_PERFORMED", "why": "; ".join(problems)}
    s = build["settings"]
    out = pathlib.Path(tempfile.mkdtemp(prefix="aisef-ocr-rebuild-")) / "ocr"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(out.parent), "GOMODCACHE": str(modcache),
           "GOPROXY": "off", "GOFLAGS": "-mod=readonly", "GOTOOLCHAIN": "local", "GOSUMDB": "off",
           "CGO_ENABLED": s.get("CGO_ENABLED", "0"), "GOOS": s.get("GOOS", ""), "GOARCH": s.get("GOARCH", "")}
    argv = ["go", "build", "-trimpath", "-buildvcs=true", *(["-ldflags", ldflags] if ldflags else []), "-o", str(out),
            "./cmd/opencodereview"]
    r = subprocess.run(argv, cwd=source, env=env, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    if r.returncode != 0:
        return {"status": "BUILD_FAILED", "argv": argv, "stderr_tail": r.stderr[-800:]}
    mine, theirs = sha256(out), sha256(exe)
    return {"status": "IDENTICAL" if mine == theirs else "DIFFERENT", "argv": argv, "ldflags_given": ldflags,
            "rebuilt_sha256": mine, "binary_sha256": theirs, "rebuilt_size": out.stat().st_size}


def record(exe: pathlib.Path, source: pathlib.Path | None, modcache: pathlib.Path | None, ldflags: str) -> dict:
    b = embedded(exe)
    return {
        "record": "Open Code Review binary: what is declared, what is embedded, what was rebuilt (never merged)",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": {"path": "validation/v21/ocr/inspect_binary.py",
                 "tree": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                                        encoding="utf-8").stdout.strip(),
                 "platform": platform.platform()},
        "pin": dict(review_ocr.OCR),
        "binary": {"path": str(exe), "size_bytes": exe.stat().st_size, "sha256": sha256(exe), "codesign": codesign(exe)},
        "a_declared": declared(exe),
        "b_embedded": b,
        "c_rebuilt": (rebuild(exe, source, modcache or pathlib.Path("/nonexistent"), ldflags, b)
                      if source is not None and b.get("status") == "READ"
                      else {"status": "NOT_PERFORMED", "why": "no --source checkout given"}),
        "what_this_is_not": ["a comparison with an upstream release artifact (none is pinned, none was fetched)",
                             "evidence of how the bytes were built unless c_rebuilt is IDENTICAL"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("exe", type=pathlib.Path)
    ap.add_argument("--source", type=pathlib.Path, help="a git checkout of the pinned commit")
    ap.add_argument("--modcache", type=pathlib.Path, help="a Go module cache holding every dependency (offline)")
    ap.add_argument("--ldflags", default="", help="the -ldflags the build used (not recorded in the binary)")
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args(argv)
    doc = json.dumps(record(a.exe.resolve(), a.source, a.modcache, a.ldflags), indent=1, ensure_ascii=False) + "\n"
    if a.out:
        a.out.write_text(doc, encoding="utf-8")
    else:
        sys.stdout.write(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
