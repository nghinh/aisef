import pathlib
import tempfile
import unittest

from treesum.digest import file_sha256
from treesum.snapshot import build


class Build(unittest.TestCase):
    def test_recursive_with_slash_keys(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "sub" / "dir").mkdir(parents=True)
            (root / "b.txt").write_bytes(b"b")
            (root / "sub" / "dir" / "file.txt").write_bytes(b"x")
            snap = build(root)
            self.assertEqual(sorted(snap), ["b.txt", "sub/dir/file.txt"])
            self.assertEqual(snap["sub/dir/file.txt"], file_sha256(root / "sub" / "dir" / "file.txt"))

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build(d), {})

    def test_not_a_directory(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "f.txt"
            f.write_bytes(b"")
            with self.assertRaises(NotADirectoryError):
                build(f)
            with self.assertRaises(NotADirectoryError):
                build(pathlib.Path(d) / "nowhere")


if __name__ == "__main__":
    unittest.main()
