"""V2.1 mutation survivors, batch T00b: what `aisef bundle init | seal | approve` print and read through the CLI
(`aisef2/app/bundle_cli.py::main`).

The report each command prints is what an operator or a script continues from: the directory `init` created and the
steps to take next (the example's own readme: git init + commit the repo, seal, explain, approve, lint, run --check),
the bundle file `seal` and `approve` wrote, which contract the human approved and under which identity, and — for
`seal --keep-approvals-from` — the carry-over of an earlier bundle's still-binding approvals, an authority decision
whose CLI wiring (the file's `approvals` key) no test reached because `seal()` is called directly elsewhere.

Each assertion compares the printed report with its source of truth (the example file, the path given to --out, the
contract id and approver given on the command line, the approvals the written bundle holds), never with a literal."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def _json(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


class _Tool(unittest.TestCase):
    """The CLI driven through `bundle_cli.main` and its stdout read back as JSON (no test methods of its own)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def tool(self, *argv) -> tuple[int, dict]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bundle_cli.main([str(a) for a in argv])
        try:
            return code, json.loads(out.getvalue())
        except ValueError:
            self.fail(f"exit {code}: stdout is not JSON: {out.getvalue()!r} stderr: {err.getvalue()!r}")

    def example(self, name: str) -> pathlib.Path:
        """`init` of the shipped example, its repository committed: the baseline `seal` reads."""
        d = self.tmp / name
        self.assertEqual(self.tool("init", "--example", name, "--out", d)[0], 0)
        _git(d / "repo", "init", "-q", "-b", "main")
        _git(d / "repo", "add", "-A")
        _git(d / "repo", "commit", "-q", "-m", "baseline")
        return d

    def seal(self, d: pathlib.Path, out: str, *extra, authoring: pathlib.Path | None = None) -> dict:
        code, report = self.tool("seal", authoring or d / "authoring.json", "--repo", d / "repo", *extra,
                                 "--out", d / out)
        self.assertEqual(code, 0, report)
        return report


class InitReport(_Tool):
    """`init` prints the directory it created and the example's own next steps, for every shipped example.

    Pins aisef2/app/bundle_cli.py::main [111, 112, 129, 130]. The operator who reads the report is told where the
    files are and that repo/ must become a git repository whose commit is the baseline `seal` reads; a script that
    continues from the printed directory reads the key `written`, the instructions are under `next`."""

    def test_the_report_is_the_directory_created_and_the_examples_readme(self):
        names = sorted(p.stem for p in bundle_cli.EXAMPLES.glob("*.json"))
        self.assertTrue(names)
        for name in names:
            with self.subTest(name):
                out = self.tmp / name
                code, report = self.tool("init", "--example", name, "--out", out)
                self.assertEqual(code, 0, report)
                readme = _json(bundle_cli.EXAMPLES / f"{name}.json")["readme"]
                # the two keys a script reads; a further key in the report would not break either of them
                self.assertEqual(pathlib.Path(report.get("written", "")), out, report)
                self.assertEqual(report.get("next"), readme, report)
                # what `written` names is the directory `init` created
                self.assertTrue((pathlib.Path(report["written"]) / "authoring.json").is_file())


class SealReport(_Tool):
    """`seal` prints the bundle file it wrote next to the plan hash, the spec count and the approvals still to give.

    Pins aisef2/app/bundle_cli.py::main [114, 131]. A script chaining seal into approve reads `written` for the
    file to approve."""

    def test_the_report_names_the_bundle_file_it_wrote(self):
        d = self.example("calc-1-story")
        report = self.seal(d, "b0.json")
        self.assertIn("written", report)
        self.assertEqual(pathlib.Path(report["written"]), d / "b0.json")
        self.assertEqual(_json(report["written"])["plan"]["plan_hash"], report["plan_hash"])    # the file it names
        self.assertEqual(sorted(x["contract"] for x in report["to_approve"]), ["BC-ADD"])


class ApproveReport(_Tool):
    """`approve` prints the file it wrote, the contract the human approved and the identity that approved it, and the
    written bundle holds exactly those approvals.

    Pins aisef2/app/bundle_cli.py::main [116, 117, 118, 133, 134, 135]. The report is the human's immediate
    acknowledgement of what their approval bound; the bundle is the record, and the two must agree for each step."""

    def setUp(self) -> None:
        super().setUp()
        self.d = self.example("calc-3-stories")
        sealed = self.seal(self.d, "b0.json")
        self.contracts = sorted({x["contract"] for x in sealed["to_approve"]})
        self.assertGreaterEqual(len(self.contracts), 2, sealed)

    def approve(self, src: str, contract: str, approver: str, out: str) -> dict:
        code, report = self.tool("approve", self.d / src, "--contract", contract, "--approver", approver,
                                 "--out", self.d / out)
        self.assertEqual(code, 0, report)
        return report

    def test_the_report_names_the_bundle_file_it_wrote(self):
        report = self.approve("b0.json", self.contracts[0], "human:alice", "b1.json")
        self.assertIn("written", report)
        self.assertEqual(pathlib.Path(report["written"]), self.d / "b1.json")
        self.assertTrue((self.d / "b1.json").is_file())

    def test_the_report_states_which_contract_was_approved_and_by_whom_as_the_bundle_records_it(self):
        first, second = self.contracts[0], self.contracts[1]
        one = self.approve("b0.json", first, "human:alice", "b1.json")
        two = self.approve("b1.json", second, "human:bob", "b2.json")     # a different approver: `by` follows --approver
        self.assertEqual((one.get("approved"), one.get("by")), (first, "human:alice"))
        self.assertEqual((two.get("approved"), two.get("by")), (second, "human:bob"))
        self.assertEqual(sorted({x["contract"] for x in one["still_to_approve"]}),
                         [c for c in self.contracts if c != first])
        # the report and the record agree: the approvals the step added are of the contract it names, by the identity it names
        for report, bundle_file, others in ((one, "b1.json", {}), (two, "b2.json", {first: "human:alice"})):
            held = {}
            for a in _json(self.d / bundle_file)["approvals"]:
                held.setdefault(a["contract_id"], set()).add(a["approver"])
            self.assertEqual(held[report["approved"]], {report["by"]}, held)
            for contract, approver in others.items():
                self.assertEqual(held[contract], {approver}, held)        # an earlier step's approval is not re-signed
            self.assertEqual(set(held), {report["approved"], *others}, held)


class KeepApprovalsFromCli(_Tool):
    """`seal --keep-approvals-from OLD` reads OLD's `approvals` and keeps those that still bind both hashes.

    Pins aisef2/app/bundle_cli.py::main [113]. Which approvals survive a re-seal is an authority decision. Through
    the CLI the file's approvals reach `seal()`: a still-binding approval is kept (and nothing is asked again), an
    approval of an edited contract is dropped and named, and seal itself never mints an approval."""

    def setUp(self) -> None:
        super().setUp()
        self.d = self.example("calc-1-story")
        self.seal(self.d, "b0.json")
        code, done = self.tool("approve", self.d / "b0.json", "--contract", "BC-ADD", "--approver", "human:owner",
                               "--out", self.d / "approved.json")
        self.assertEqual((code, done["still_to_approve"]), (0, []), done)
        self.approved = _json(self.d / "approved.json")["approvals"]
        self.assertTrue(self.approved)

    def test_a_still_binding_approval_is_carried_over(self):
        report = self.seal(self.d, "b2.json", "--keep-approvals-from", self.d / "approved.json")
        self.assertEqual((report["approvals_kept"], report["approvals_dropped"], report["to_approve"]),
                         (len(self.approved), [], []), report)
        self.assertEqual(_json(self.d / "b2.json")["approvals"], self.approved)

    def test_without_the_option_seal_mints_no_approval(self):
        report = self.seal(self.d, "plain.json")
        self.assertEqual((report["approvals_kept"], report["approvals_dropped"]), (0, []))
        self.assertEqual([x["contract"] for x in report["to_approve"]], ["BC-ADD"])
        self.assertEqual(_json(self.d / "plain.json")["approvals"], [])

    def test_the_approval_of_an_edited_contract_is_dropped_and_named(self):
        edited = _json(self.d / "authoring.json")
        edited["contracts"][0]["observable"]["returns"] = 6        # a different claim is a different contract
        path = self.d / "authoring-edited.json"
        path.write_text(json.dumps(edited), encoding="utf-8")
        report = self.seal(self.d, "b3.json", "--keep-approvals-from", self.d / "approved.json", authoring=path)
        self.assertEqual(report["approvals_kept"], 0)
        self.assertEqual(report["approvals_dropped"], ["BC-ADD/R-1"])
        self.assertEqual([x["contract"] for x in report["to_approve"]], ["BC-ADD"])
        self.assertEqual(_json(self.d / "b3.json")["approvals"], [])


if __name__ == "__main__":
    unittest.main()
