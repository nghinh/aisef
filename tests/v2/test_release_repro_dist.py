"""validation/qualification/repro_dist.py: two sdists of the same files built at different times, by different owners,
re-pack to one digest — contents and modes unchanged, every time the epoch."""

from __future__ import annotations

import gzip
import io
import os
import pathlib
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import repro_dist as R  # noqa: E402

FILES = {"pkg-1.0/PKG-INFO": (b"Name: pkg\n", 0o644), "pkg-1.0/pkg/__init__.py": (b"", 0o644),
         "pkg-1.0/bin/run": (b"#!/bin/sh\n", 0o755)}
EPOCH = 1_790_000_000


def sdist(path: pathlib.Path, mtime: float, uid: int, order) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as t:
        for name in order:
            data, mode = FILES[name]
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime, info.uid, info.uname = len(data), mode, mtime, uid, f"user{uid}"
            t.addfile(info, io.BytesIO(data))
    with open(path, "wb") as f, gzip.GzipFile(filename=path.name, mode="wb", fileobj=f, mtime=int(mtime)) as gz:
        gz.write(buf.getvalue())


class ReproDist(unittest.TestCase):
    def test_two_builds_re_pack_to_one_digest_with_contents_and_modes_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = pathlib.Path(t, "a.tar.gz"), pathlib.Path(t, "b.tar.gz")
            sdist(a, 1_800_000_000.25, 501, sorted(FILES))
            sdist(b, 1_800_000_777.75, 0, sorted(FILES, reverse=True))
            self.assertNotEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(R.normalize(a, EPOCH), R.normalize(b, EPOCH))
            raw = a.read_bytes()
            self.assertEqual(int.from_bytes(raw[4:8], "little"), EPOCH)      # the gzip header carries the epoch
            self.assertEqual(raw[3] & 0x08, 0)                                # and no file name
            with tarfile.open(a) as tar:
                members = tar.getmembers()
                self.assertEqual([m.name for m in members], sorted(FILES))
                self.assertEqual({m.name: (tar.extractfile(m).read(), m.mode) for m in members}, FILES)
                self.assertEqual({(m.mtime, m.uid, m.gid, m.uname, m.gname) for m in members}, {(EPOCH, 0, 0, "", "")})

    def test_the_epoch_is_required(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(R.main(["x.tar.gz"]), 2)
        with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "soon"}, clear=True):
            self.assertEqual(R.main(["x.tar.gz"]), 2)


if __name__ == "__main__":
    unittest.main()
