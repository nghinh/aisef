"""Reproducible release artifacts (V2.0 charter G2, §11, §18: the RC's wheel and sdist digests are frozen, and a
rebuild of the exact RC must give them again).

    SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) python -m build
    python -P validation/qualification/repro_dist.py dist/*.tar.gz
    python -P validation/qualification/repro_dist.py --toolchain             # the build's toolchain record, JSON
    python -P validation/qualification/repro_dist.py --perturb SRC DST      # the contract's perturbed copy

The wheel is already reproducible under SOURCE_DATE_EPOCH (setuptools clamps its zip timestamps; measured: two builds,
one digest). The sdist is not: setuptools writes the build time into its members (PKG-INFO, egg-info, directories) and
into the gzip header. This re-packs it with every member sorted by name, its mtime set to SOURCE_DATE_EPOCH, its
owner fields cleared, no pax extras, its contents unchanged (checked), and a gzip header carrying the epoch and no
file name. Each member's mode is git's: 0755 for a directory or a file with any execute bit, else 0644. setuptools
takes the mode from the filesystem and git records only 100644 / 100755, so keeping it made the sdist depend on the
build tree's permission bits (BUILD-REPRO-01; docs/v2.3/drafts/BUILD-REPRO-CONTRACT.md is the contract).
"""

from __future__ import annotations

import compileall
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
import pathlib
import platform
import shutil
import sys
import tarfile
import zlib


def normalize(path: pathlib.Path, epoch: int) -> str:
    """Re-pack the sdist at `path` in place; its new sha256."""
    with tarfile.open(path, "r:gz") as src:
        members = sorted(src.getmembers(), key=lambda m: m.name)
        contents = {m.name: src.extractfile(m).read() for m in members if m.isfile()}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as out:
        for m in members:
            m.mtime, m.uid, m.gid, m.uname, m.gname, m.pax_headers = epoch, 0, 0, "", "", {}
            m.mode = 0o755 if m.isdir() or m.mode & 0o111 else 0o644
            data = contents.get(m.name)
            out.addfile(m, io.BytesIO(data) if data is not None else None)
    tar = buf.getvalue()
    with tarfile.open(fileobj=io.BytesIO(tar)) as check:   # the contents survive the re-pack, exactly
        if {m.name: check.extractfile(m).read() for m in check.getmembers() if m.isfile()} != contents:
            raise SystemExit(f"{path}: the re-packed sdist does not hold the same files")
    out_bytes = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out_bytes, mtime=epoch, compresslevel=9) as gz:
        gz.write(tar)
    path.write_bytes(out_bytes.getvalue())
    return hashlib.sha256(out_bytes.getvalue()).hexdigest()


def toolchain() -> dict:
    """What each build records (the contract): the interpreter, the runtime and compile-time zlib (the deflate the
    gzip and zip streams come from), the build frontend, the runner image, the OS/kernel/arch. No host name."""
    try:
        frontend = importlib.metadata.version("build")
    except importlib.metadata.PackageNotFoundError:
        frontend = None
    image = " ".join(os.environ.get(k, "") for k in ("ImageOS", "ImageVersion")).strip() or None
    return {"python": sys.version, "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION, "zlib_compiled": zlib.ZLIB_VERSION,
            "build": frontend, "image": image, "platform": platform.platform()}


def perturb(src: pathlib.Path, dst: pathlib.Path) -> None:
    """The contract's perturbed tree: a copy of `src` at `dst` whose files carry non-git permission bits (0600, or
    0700 if it has an execute bit; directories 0700) and which holds __pycache__/, a stale aisef.egg-info/ (an older
    version, a file a later commit removed), dist/ and build/, as a used working tree does. `src`'s .git and its own
    top-level dist/, build/ and *.egg-info are not copied: a build in `dst` that wrote nothing must not find `src`'s
    outputs and pass the digest check."""
    def ignore(d: str, names: list[str]) -> list[str]:
        top = d == os.fspath(src)
        return [n for n in names if n == ".git" or top and (n in ("dist", "build") or n.endswith(".egg-info"))]

    shutil.copytree(src, dst, symlinks=True, ignore=ignore)
    compileall.compile_dir(dst, quiet=2)
    egg = dst / "aisef.egg-info"
    egg.mkdir(exist_ok=True)
    (egg / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: aisef\nVersion: 0.0.0\n", encoding="utf-8")
    (egg / "SOURCES.txt").write_text("README.md\npyproject.toml\naisef/removed_by_a_later_commit.py\n", encoding="utf-8")
    (dst / "dist").mkdir(exist_ok=True)
    (dst / "dist" / "aisef-0.0.0-py3-none-any.whl").write_bytes(b"stale")
    (dst / "build" / "lib" / "aisef").mkdir(parents=True, exist_ok=True)
    (dst / "build" / "lib" / "aisef" / "removed_by_a_later_commit.py").write_text("", encoding="utf-8")
    for p in [*dst.rglob("*"), dst]:
        if not p.is_symlink():
            p.chmod(0o700 if p.is_dir() or p.stat().st_mode & 0o111 else 0o600)


def main(argv: list[str]) -> int:
    if argv == ["--toolchain"]:
        print(json.dumps(toolchain(), sort_keys=True))
        return 0
    if argv[:1] == ["--perturb"]:
        if len(argv) != 3:
            print("usage: repro_dist.py --perturb SRC DST", file=sys.stderr)
            return 2
        perturb(pathlib.Path(argv[1]), pathlib.Path(argv[2]))
        return 0
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch or not epoch.isdigit():
        print("repro_dist: SOURCE_DATE_EPOCH (the commit time) is required", file=sys.stderr)
        return 2
    for p in argv:
        print(f"{normalize(pathlib.Path(p), int(epoch))}  {pathlib.Path(p).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
