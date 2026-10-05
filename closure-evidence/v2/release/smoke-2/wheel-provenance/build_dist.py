"""Offline build like `python -m build`: sdist from the checkout, then the wheel FROM the unpacked sdist.

    PYTHONPATH=<setuptools dir> python3 -P build_dist.py <checkout> <out-dir>
"""
import hashlib
import os
import pathlib
import sys
import tarfile

src, out = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve()
dist, unpack = out / "dist", out / "unpacked"
dist.mkdir(parents=True)
unpack.mkdir()

from setuptools import build_meta  # noqa: E402

os.chdir(src)
sdist = build_meta.build_sdist(str(dist))
with tarfile.open(dist / sdist) as t:
    t.extractall(unpack, filter="data")
os.chdir(unpack / sdist[: -len(".tar.gz")])
wheel = build_meta.build_wheel(str(dist))
for name in (sdist, wheel):
    print(hashlib.sha256((dist / name).read_bytes()).hexdigest(), name)
