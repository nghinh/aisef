import pathlib
import tempfile
import unittest

from treesum.digest import file_sha256

HELLO = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"


class Digest(unittest.TestCase):
    def test_hello_example(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "h.txt"
            p.write_bytes(b"hello\n")
            self.assertEqual(file_sha256(str(p)), HELLO)
            self.assertEqual(file_sha256(p), HELLO)          # 1.2: a pathlib.Path too
            self.assertIsInstance(file_sha256(p), str)

    def test_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                file_sha256(pathlib.Path(d) / "absent")


if __name__ == "__main__":
    unittest.main()
