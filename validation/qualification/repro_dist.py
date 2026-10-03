"""Reproducible release artifacts (V2.0 charter G2, §11, §18: the RC's wheel and sdist digests are frozen, and a
rebuild of the exact RC must give them again).

    SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) python -m build
    python -P validation/qualification/repro_dist.py dist/*.tar.gz

The wheel is already reproducible under SOURCE_DATE_EPOCH (setuptools clamps its zip timestamps; measured: two builds,
one digest). The sdist is not: setuptools writes the build time into its members (PKG-INFO, egg-info, directories) and
into the gzip header. This re-packs it with every member sorted by name, its mtime set to SOURCE_DATE_EPOCH, its
owner fields cleared, its mode and contents unchanged (checked), no pax extras, and a gzip header carrying the epoch
and no file name.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import pathlib
import sys
import tarfile


def normalize(path: pathlib.Path, epoch: int) -> str:
    """Re-pack the sdist at `path` in place; its new sha256."""
    with tarfile.open(path, "r:gz") as src:
        members = sorted(src.getmembers(), key=lambda m: m.name)
        contents = {m.name: src.extractfile(m).read() for m in members if m.isfile()}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as out:
        for m in members:
            m.mtime, m.uid, m.gid, m.uname, m.gname, m.pax_headers = epoch, 0, 0, "", "", {}
            data = contents.get(m.name)
            out.addfile(m, io.BytesIO(data) if data is not None else None)
    tar = buf.getvalue()
    with tarfile.open(fileobj=io.BytesIO(tar)) as check:   # contents and modes survive the re-pack, exactly
        if {m.name: check.extractfile(m).read() for m in check.getmembers() if m.isfile()} != contents:
            raise SystemExit(f"{path}: the re-packed sdist does not hold the same files")
    out_bytes = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out_bytes, mtime=epoch, compresslevel=9) as gz:
        gz.write(tar)
    path.write_bytes(out_bytes.getvalue())
    return hashlib.sha256(out_bytes.getvalue()).hexdigest()


def main(argv: list[str]) -> int:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch or not epoch.isdigit():
        print("repro_dist: SOURCE_DATE_EPOCH (the commit time) is required", file=sys.stderr)
        return 2
    for p in argv:
        print(f"{normalize(pathlib.Path(p), int(epoch))}  {pathlib.Path(p).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
