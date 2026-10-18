"""requirements-delta §3 (JSON output), unittest."""
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


class JsonOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.doc = self.root / "doc.md"
        self.doc.write_text("latency 250 ms uncited\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_json_format_prints_one_document(self):
        code, out, _ = run(["--format", "json", "--root", str(self.doc)])
        self.assertEqual(code, 1)
        doc = json.loads(out)
        self.assertEqual(list(doc), ["findings", "accepted_targets", "accepted_placeholders"])
        self.assertEqual(list(doc["findings"][0]), ["file", "line", "figure", "reason", "text"])
        self.assertEqual(doc["findings"][0]["figure"], "250 ms")

    def test_json_format_with_no_finding_exits_0(self):
        self.doc.write_text("target: under 900 ms\n", encoding="utf-8")
        code, out, _ = run(["--format", "json", "--root", str(self.doc)])
        self.assertEqual((code, json.loads(out)), (0, {"findings": [], "accepted_targets": 1, "accepted_placeholders": 0}))

    def test_report_is_the_same_document_in_both_formats(self):
        rep = self.root / "out" / "report.json"
        code, out, _ = run(["--format", "json", "--root", str(self.doc), "--report", str(rep)])
        written = rep.read_text(encoding="utf-8")
        self.assertEqual(written, json.dumps(json.loads(out), indent=2))
        self.assertFalse(written.endswith("\n"))
        rep.unlink()
        code, out, _ = run(["--root", str(self.doc), "--report", str(rep)])
        self.assertEqual((code, rep.read_text(encoding="utf-8")), (1, written))
        self.assertIn("uncited", out)


if __name__ == "__main__":
    unittest.main()
