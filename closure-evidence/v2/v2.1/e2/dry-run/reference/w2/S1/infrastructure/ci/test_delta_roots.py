"""requirements-delta §1 (directory roots), unittest."""
import contextlib
import io
import pathlib
import tempfile
import unittest

from infrastructure.ci import evidence_discipline as ed


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ed.cli_main(argv)
    return code, out.getvalue(), err.getvalue()


class Roots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "docs"
        for rel in ("b.md", "a.md", "sub/c.ts", "sub/d.tsx", "node_modules/v.md", "build/w.md", "dist/x.md",
                    ".hidden/y.md", "notes.txt"):
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"uncited {rel}: 250 ms\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_directory_walked_sorted_and_filtered(self):
        code, out, _ = run(["--root", str(self.root)])
        self.assertEqual(code, 1)
        reported = [line.split(":")[0] for line in out.splitlines() if not line.startswith("    ")]
        rel = [str(pathlib.Path(p).relative_to(self.root)) for p in reported]
        self.assertEqual(rel, ["a.md", "b.md", "sub/c.ts", "sub/d.tsx"])

    def test_file_root_scanned_whatever_its_suffix(self):
        code, out, _ = run(["--root", str(self.root / "notes.txt")])
        self.assertEqual(code, 1)
        self.assertIn("notes.txt:1:", out)

    def test_missing_root_is_an_error(self):
        missing = str(self.root / "nowhere" / "README.md")
        code, out, err = run(["--root", missing])
        self.assertEqual((code, out), (2, ""))
        self.assertIn(missing, err)
        self.assertEqual(len(err.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
