"""requirements-delta §2 (the run registry), unittest."""
import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from infrastructure.ci import evidence_discipline as ed


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ed.cli_main(argv)
    return code, out.getvalue(), err.getvalue()


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.doc = self.root / "doc.md"
        self.doc.write_text("latency 250 ms (run_id bench-001)\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def registry(self, content: str) -> pathlib.Path:
        p = self.root / "registry.json"
        p.write_text(content, encoding="utf-8")
        return p

    def test_registry_error_is_a_value_error_naming_the_path(self):
        self.assertTrue(issubclass(ed.RegistryError, ValueError))
        for bad in ("not json", "[\"a\"]", "{\"valid_runs\": \"a\"}", "{\"valid_runs\": [1]}"):
            p = self.registry(bad)
            with self.assertRaises(ed.RegistryError) as cm:
                ed.load_run_registry(p)
            self.assertIn(str(p), str(cm.exception))
        with self.assertRaises(ed.RegistryError):
            ed.load_run_registry(str(self.root / "absent.json"))

    def test_registry_loads_from_str_and_path(self):
        p = self.registry(json.dumps({"valid_runs": ["bench-001", "x"]}))
        self.assertEqual(ed.load_run_registry(p), {"bench-001", "x"})
        self.assertEqual(ed.load_run_registry(str(p)), {"bench-001", "x"})

    def test_cli_registry_option(self):
        p = self.registry(json.dumps({"valid_runs": ["bench-001"]}))
        self.assertEqual(run(["--registry", str(p), "--root", str(self.doc)])[0], 0)
        p = self.registry(json.dumps({"valid_runs": ["other"]}))
        self.assertEqual(run(["--registry", str(p), "--root", str(self.doc)])[0], 1)

    def test_cli_bad_registry_exits_2_and_scans_nothing(self):
        p = self.registry("not json")
        code, out, err = run(["--registry", str(p), "--root", str(self.doc)])
        self.assertEqual((code, out), (2, ""))
        lines = err.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("run registry:"))
        self.assertIn(str(p), lines[0])
        self.assertIsInstance(code, int)


if __name__ == "__main__":
    unittest.main()
