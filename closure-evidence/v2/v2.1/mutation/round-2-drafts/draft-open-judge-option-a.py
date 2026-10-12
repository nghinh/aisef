"""DRAFT, not part of the suite: what would pin the host guard's pseudo-filesystem exemption IF the owner decides that a
writable devpts / mqueue mount is not host storage wherever it is mounted (option (a) of the R02 question)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2 import test_v21_kills3_T06a as t06a  # noqa: E402


class PseudoFilesystemsAreNotHostStorage(unittest.TestCase):
    def judged_with(self, fs: str, at: str = "/tmp/x") -> list[str]:
        rep, tries = t06a.measured("host")
        rep["inside"]["mounts"].append(t06a.mount(at, fs, "rw"))      # /tmp is a mount target: nothing is 'beyond'
        return t06a.judged(rep, tries)

    def test_a_writable_devpts_below_a_named_target_is_not_named(self):
        self.assertEqual(self.judged_with("devpts"), [])

    def test_a_writable_mqueue_below_a_named_target_is_not_named(self):
        self.assertEqual(self.judged_with("mqueue"), [])

    def test_control_a_writable_ext4_at_the_same_place_is_named(self):
        said = self.judged_with("ext4")
        self.assertEqual(len(said), 1, said)
        self.assertIn("/tmp/x", said[0])


if __name__ == "__main__":
    unittest.main()
