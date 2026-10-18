import contextlib
import io
import pathlib
import tempfile
import unittest

from treesum.__main__ import main
from treesum.snapshot import build, dumps


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "a.txt").write_bytes(b"a")
        (self.root / "b.txt").write_bytes(b"b")

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_to_stdout(self):
        code, out, _ = run(["build", str(self.root)])
        self.assertEqual((code, out), (0, dumps(build(self.root))))

    def test_build_to_file_inside_dir_excludes_itself(self):
        snap = self.root / "snap.sum"
        code, out, _ = run(["build", str(self.root), "-o", str(snap)])
        self.assertEqual((code, out), (0, ""))
        expected = {k: v for k, v in build(self.root).items() if k != "snap.sum"}     # 5.3: FILE inside DIR is not an entry
        self.assertEqual(snap.read_text(), dumps(expected))
        self.assertNotIn("snap.sum", snap.read_text())
        self.assertEqual(run(["verify", str(self.root), str(snap)])[:2], (0, ""))

    def test_verify_reports_sorted_differences(self):
        snap = self.root / "snap.sum"
        run(["build", str(self.root), "-o", str(snap)])
        (self.root / "a.txt").write_bytes(b"changed")
        (self.root / "b.txt").unlink()
        (self.root / "c.txt").write_bytes(b"new")
        code, out, _ = run(["verify", str(self.root), str(snap)])
        self.assertEqual((code, out), (1, "changed a.txt\nremoved b.txt\nadded c.txt\n"))

    def test_misuse_exits_2(self):
        self.assertEqual(run([])[0], 2)
        self.assertEqual(run(["verify", str(self.root), str(self.root / "absent.sum")])[0], 2)
        self.assertEqual(run(["build", str(self.root / "a.txt")])[0], 2)
        self.assertEqual(run(["verify", str(self.root), str(self.root / "absent.sum")])[1], "")


if __name__ == "__main__":
    unittest.main()
