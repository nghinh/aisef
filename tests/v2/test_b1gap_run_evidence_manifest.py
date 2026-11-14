"""B1 gap kill tests for aisef2/app/run.py::evidence_manifest.

The probe-observations group of the manifest is listed in name order, like every other group, so that the
same directory is always the same document whatever order the file system enumerates it in
(test_v21_r3_detail_artifact.py pins the four sibling groups; this file pins the one it omits).

Pins aisef2/app/run.py::evidence_manifest."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import diagnostics  # noqa: E402
from aisef2.app import run as R  # noqa: E402


class ProbeObservationsOrder(unittest.TestCase):
    # Kills: L433 sorted() -> list()
    def test_probe_observations_group_is_listed_in_name_order(self):
        """Twelve probe-observation artifacts created out of name order (1 in 479,001,600 for the directory
        enumeration to come out sorted by luck) are listed in the manifest in name order."""
        scrambled = (7, 2, 11, 5, 0, 9, 3, 10, 1, 8, 4, 6)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            folder = out / diagnostics.ARTIFACT_DIR
            folder.mkdir()
            for n in scrambled:                                  # created out of order
                (folder / f"f{n:02d}.json").write_bytes(b"x")
            listed = list(R.evidence_manifest(out)["files"])
            members = [k for k in listed if k.startswith(f"{diagnostics.ARTIFACT_DIR}/")]
            self.assertEqual(len(members), 12)
            self.assertEqual(members, sorted(members))


if __name__ == "__main__":
    unittest.main()
