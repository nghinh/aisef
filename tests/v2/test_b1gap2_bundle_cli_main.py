"""Kill tests for mutation survivors of `aisef2/app/bundle_cli.py::main` (B1 gap wave 2).

What `aisef bundle` promises on its output channels, beyond parsed-JSON equality:

* the reports `seal`, `approve`, `continue` and `migrate` print are canonical JSON text
  (json.dumps indent=1, sort_keys=True): a script or operator diffing one report against
  another reads order-stable bytes, so the raw stdout — not its parse — is asserted;
* a non-64-hex `--expect-anchor` is a usage error whose message tells the operator what
  the value is (the message is the kill route here: there is no other observable);
* `migrate` whose written file cannot be read back records `file_sha256: null` under its
  own key in `candidate`, still prints the report and still exits 0 (the bundle was written).

Each mutant under test lives in `main` itself, downstream of the collaborators
(`seal`, `approve`, `continue_from`, `migrate`), so those are stubbed per test: the file
stays fast and hermetic (no git, no run, no provider) while every asserted byte still
flows through the mutated lines."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


def call(*argv) -> tuple[int, str, str]:
    """(exit status, stdout, stderr) of `aisef bundle ARGV`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class Work(unittest.TestCase):
    """A scratch directory per test: a JSON input for `_read` and the path a command writes."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(t.cleanup)
        self.work = pathlib.Path(t.name).resolve()
        self.src = self.work / "in.json"
        self.src.write_text("{}", encoding="utf-8")     # _read parses it; the stubbed collaborator never looks
        self.out = self.work / "out.json"

    def assertCanonical(self, raw: str) -> None:
        """`raw` is byte-for-byte the canonical form the CLI promises: sorted keys, indent 1, one newline."""
        self.assertTrue(raw, "nothing was printed")
        self.assertEqual(raw, json.dumps(json.loads(raw), indent=1, sort_keys=True) + "\n")


class SealReportIsCanonicalText(Work):
    # kills: L1125 True->False
    def test_the_seal_report_is_printed_with_sorted_keys(self):
        # a report key that sorts before "written": under the mutant, insertion order leaks into stdout
        with mock.patch.object(bundle_cli, "seal", return_value=({"stub": 1}, {"alpha": 1})):
            code, raw, err = call("seal", self.src, "--out", self.out)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(raw), {"written": str(self.out), "alpha": 1})
        self.assertCanonical(raw)


class ApproveReportIsCanonicalText(Work):
    # kills: L1132 True->False
    def test_the_approve_report_is_printed_with_sorted_keys(self):
        doc = {"requirements": [], "approvals": [], "contracts": []}    # the least bundle `unapproved` reads
        with mock.patch.object(bundle_cli, "approve", return_value=doc):
            code, raw, err = call("approve", self.src, "--contract", "BC-X",
                                  "--approver", "human:t", "--out", self.out)
        self.assertEqual((code, err), (0, ""))
        printed = json.loads(raw)
        self.assertEqual((printed["approved"], printed["by"], printed["still_to_approve"]),
                         ("BC-X", "human:t", []))
        self.assertCanonical(raw)


class ContinueExpectAnchorIsExplained(Work):
    # kills: L1136 string '--expect-anchor is the 64-hex evidence anchor the run printed' emptied
    def test_a_non_hex_anchor_is_a_usage_error_that_says_what_the_value_is(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as c:
            bundle_cli.main(["continue", str(self.src), "--from-run", str(self.work),
                             "--out", str(self.out), "--expect-anchor", "not-hex"])
        self.assertEqual(c.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        # the message is the only observable this refusal has (owner precedent: the error
        # text is a test-asserted observable); the smallest stable substring the mutant destroys:
        self.assertIn("64-hex evidence anchor the run printed", err.getvalue())
        self.assertFalse(self.out.exists())


class ContinueReportIsCanonicalText(Work):
    # kills: L1140 True->False
    def test_the_continue_report_is_printed_with_sorted_keys(self):
        with mock.patch.object(bundle_cli, "continue_from", return_value=({"stub": 1}, {"alpha": 1})):
            code, raw, err = call("continue", self.src, "--from-run", self.work, "--out", self.out)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(raw), {"written": str(self.out), "alpha": 1})
        self.assertCanonical(raw)


def _migrate_stub() -> tuple[dict, dict]:
    """A fresh (candidate, report) per test: main mutates report['candidate'] in place."""
    return {"stub": 1}, {"alpha": 1, "candidate": {}, "needs_owner_reapproval": None}


class MigrateWhenTheWrittenFileCannotBeReadBack(Work):
    """The fallback of `aisef bundle migrate` when the file it just wrote cannot be read for hashing
    (the bundle was written at that point: the report must still come, under its promised keys)."""

    def unreadable(self) -> tuple[int, str, str]:
        with mock.patch.object(bundle_cli, "migrate", return_value=_migrate_stub()), \
                mock.patch.object(pathlib.Path, "read_bytes", side_effect=OSError("unreadable")):
            return call("migrate", self.src, "--out", self.out)

    # kills: L1157 string 'file_sha256' emptied
    def test_the_fallback_records_file_sha256_as_null_under_its_own_key(self):
        code, raw, err = self.unreadable()
        self.assertEqual((code, err), (0, ""))
        candidate = json.loads(raw)["candidate"]
        self.assertIn("file_sha256", candidate)
        self.assertIsNone(candidate["file_sha256"])
        self.assertNotIn("", candidate)

    # kills: L1157 string 'candidate' emptied
    def test_an_unreadable_written_file_is_not_a_refusal(self):
        code, raw, err = self.unreadable()
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertTrue(self.out.exists())              # the bundle was written before the hash was tried
        self.assertEqual(json.loads(raw)["written"], str(self.out))     # and the report still printed


class MigrateReportIsCanonicalText(Work):
    # kills: L1164 True->False
    def test_the_migrate_report_is_printed_with_sorted_keys(self):
        with mock.patch.object(bundle_cli, "migrate", return_value=_migrate_stub()):
            code, raw, err = call("migrate", self.src, "--out", self.out)
        self.assertEqual((code, err), (0, ""))
        printed = json.loads(raw)
        self.assertEqual(printed["written"], str(self.out))
        self.assertEqual(printed["candidate"]["file_sha256"],
                         hashlib.sha256(self.out.read_bytes()).hexdigest())     # the bytes as written
        self.assertCanonical(raw)


if __name__ == "__main__":
    unittest.main()
