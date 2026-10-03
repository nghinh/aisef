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


class FrozenCandidate(unittest.TestCase):
    """validation/qualification/release_rc.py: the production publish job publishes the frozen RC's bytes only, and
    builds take the frozen RC's epoch once there is one."""

    def test_only_the_frozen_files_byte_for_byte_pass(self):
        from validation.qualification import release_rc as rc
        import hashlib
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            (d / "aisef-2.0.0-py3-none-any.whl").write_bytes(b"wheel")
            (d / "aisef-2.0.0.tar.gz").write_bytes(b"sdist")
            frozen = {"artifacts": {"sha256": {"aisef-2.0.0-py3-none-any.whl": hashlib.sha256(b"wheel").hexdigest(),
                                               "aisef-2.0.0.tar.gz": hashlib.sha256(b"sdist").hexdigest()}}}
            self.assertEqual(rc.verify_dist(frozen, d), [])
            (d / "aisef-2.0.0.tar.gz").write_bytes(b"sdist, rebuilt")
            self.assertTrue(rc.verify_dist(frozen, d))
            (d / "aisef-2.0.0.tar.gz").write_bytes(b"sdist")
            (d / "extra.whl").write_bytes(b"x")
            self.assertTrue(rc.verify_dist(frozen, d))

    def test_the_epoch_is_the_frozen_candidate_s_once_frozen(self):
        from validation.qualification import release_rc as rc
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            with mock.patch.object(rc, "ROOT", root), mock.patch.object(rc, "_git", return_value=b"1700000000\n"):
                self.assertEqual(rc.epoch(), 1700000000)                  # before the freeze: the commit's time
                (root / rc.OUT_REL).parent.mkdir(parents=True)
                (root / rc.OUT_REL).write_text('{"rc": {"source_date_epoch": 1790000000}}', encoding="utf-8")
                self.assertEqual(rc.epoch(), 1790000000)


if __name__ == "__main__":
    unittest.main()
