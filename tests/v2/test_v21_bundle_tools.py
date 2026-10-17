"""V2.1 (B, goal 3): an outsider makes a project bundle and checks a run with the shipped commands only — no kernel
API. On 2.0.0 a bundle needed `aisef2` constructors to compute every requirement, contract and plan hash and every
spec id (360° usability W1: "AISEF 2.0 runs bundles; it does not author them").

The path, per shipped example: `aisef bundle init` -> a git repository of its files -> `seal` (hashes and spec ids
derived, nothing approved) -> `explain` -> `approve` one contract at a time as `human:<name>` -> `lint` READY ->
`aisef run --check` ready (exit 0), offline. And what the tools refuse: an agent approver, an overwrite, an
edited contract keeping its approval, an uncovered requirement, a criterion of a contract that is not there."""

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

from aisef2.app import bundle, bundle_cli, cli  # noqa: E402
from tests.v2.test_app_run import SETTINGS  # noqa: E402

CONTRACTS = {"calc-1-story": ["BC-ADD"], "calc-3-stories": ["BC-ADD", "BC-MUL", "BC-TOTAL", "BC-STDLIB"]}


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


class Tool(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def tool(self, *argv) -> tuple[int, dict | str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bundle_cli.main([str(a) for a in argv])
        try:
            return code, json.loads(out.getvalue())
        except ValueError:
            return code, out.getvalue() + err.getvalue()

    def example(self, name: str) -> pathlib.Path:
        d = self.tmp / name
        self.assertEqual(self.tool("init", "--example", name, "--out", d)[0], 0)
        git(d / "repo", "init", "-q", "-b", "main")
        git(d / "repo", "add", "-A")
        git(d / "repo", "commit", "-q", "-m", "baseline")
        return d


class Outsider(Tool):
    def test_each_example_from_init_to_a_ready_check(self):
        for name, contracts in CONTRACTS.items():
            with self.subTest(name):
                d = self.example(name)
                code, sealed = self.tool("seal", d / "authoring.json", "--repo", d / "repo", "--out", d / "b0.json")
                self.assertEqual(code, 0, sealed)
                self.assertEqual(sorted(x["contract"] for x in sealed["to_approve"]), sorted(contracts))
                code, report = self.tool("lint", d / "b0.json")
                self.assertEqual((code, report["verdict"]), (1, "NOT_READY"))
                code, told = self.tool("explain", d / "b0.json")
                self.assertEqual(code, 0)
                rows = [r for story in told["stories"].values() for r in story]
                self.assertTrue(rows and all(r["calibrated"] and not r["approved"] for r in rows), rows)
                current = d / "b0.json"
                for n, c in enumerate(contracts, 1):
                    code, done = self.tool("approve", current, "--contract", c, "--approver", "human:example-owner",
                                           "--out", d / f"b{n}.json")
                    self.assertEqual(code, 0, done)
                    current = d / f"b{n}.json"
                self.assertEqual(done["still_to_approve"], [])
                code, report = self.tool("lint", current)
                self.assertEqual((code, report["verdict"]), (0, "READY"), report)
                self.assertTrue(report["admission"]["admitted"])
                self.assertEqual({v["status"] for v in report["coverage"]["requirements"].values()}, {"COVERED"})
                (d / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                    code = cli.run(["--check", "--project", str(current), "--settings", str(d / "settings.json"),
                                    "--repo", str(d / "repo")])
                self.assertEqual(code, 0, out.getvalue())
                self.assertTrue(json.loads(out.getvalue())["ready"])

    def test_seal_derives_what_the_kernel_compiles(self):
        d = self.example("calc-3-stories")
        self.tool("seal", d / "authoring.json", "--repo", d / "repo", "--out", d / "b.json")
        doc = json.loads((d / "b.json").read_text(encoding="utf-8"))
        for c in CONTRACTS["calc-3-stories"]:
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        project = bundle.load(doc)     # compile_spec again, gated: the ids seal minted are the ids the kernel compiles
        self.assertEqual({o.product_proof_spec_id for o in project.plan.obligations}, set(project.specs))
        self.assertEqual(project.plan.baseline, git(d / "repo", "rev-parse", "HEAD").strip())


class Refusals(Tool):
    def setUp(self) -> None:
        super().setUp()
        self.d = self.example("calc-1-story")
        self.tool("seal", self.d / "authoring.json", "--repo", self.d / "repo", "--out", self.d / "b.json")
        self.doc = json.loads((self.d / "b.json").read_text(encoding="utf-8"))

    def test_an_approver_that_is_not_a_human_identity_is_refused(self):
        code, err = self.tool("approve", self.d / "b.json", "--contract", "BC-ADD", "--approver", "agent:dev",
                              "--out", self.d / "x.json")
        self.assertEqual(code, 2)
        self.assertIn("human", err)
        self.assertFalse((self.d / "x.json").exists())

    def test_no_tool_overwrites_a_file(self):
        code, err = self.tool("seal", self.d / "authoring.json", "--repo", self.d / "repo", "--out", self.d / "b.json")
        self.assertEqual(code, 2)
        self.assertIn("never overwrite", err)
        self.assertEqual(self.tool("init", "--out", self.d)[0], 2)

    def test_an_edited_contract_loses_its_approval_on_reseal(self):
        approved = bundle_cli.approve(self.doc, "BC-ADD", "human:t", 1.0)
        a = json.loads((self.d / "authoring.json").read_text(encoding="utf-8"))
        a["contracts"][0]["observable"]["returns"] = 6        # a different claim is a different contract
        exposed = bundle_cli.exposure_of(approved)      # the bundle the approvals come from: nothing is exposed in this release's own
        doc, report = bundle_cli.seal(a, repo=self.d / "repo", approvals=approved["approvals"], exposed=exposed)
        self.assertEqual(report["approvals_dropped"], ["BC-ADD/R-1"])
        self.assertEqual([x["contract"] for x in report["to_approve"]], ["BC-ADD"])
        same, kept = bundle_cli.seal(json.loads((self.d / "authoring.json").read_text(encoding="utf-8")),
                                     repo=self.d / "repo", approvals=approved["approvals"], exposed=exposed)
        self.assertEqual((kept["approvals_kept"], kept["to_approve"]), (1, []))

    def test_an_uncovered_requirement_is_named_where_admission_refuses_it(self):
        a = json.loads((self.d / "authoring.json").read_text(encoding="utf-8"))
        a["requirements"].append({"id": "R-9", "text": "something nobody proves", "source": "docs/requirements.md#9"})
        doc, _ = bundle_cli.seal(a, repo=self.d / "repo")
        report = bundle_cli.lint(bundle_cli.approve(doc, "BC-ADD", "human:t", 1.0))
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["1. requirement_coverage"])   # the kernel's own
        self.assertEqual(report["coverage"]["requirements"]["R-9"]["status"], "UNCOVERED")

    def test_a_criterion_naming_an_absent_contract_or_a_closed_key_is_refused_with_its_path(self):
        a = json.loads((self.d / "authoring.json").read_text(encoding="utf-8"))
        a["stories"]["S1"]["criteria"][0]["contract"] = "BC-NONE"
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(a, repo=self.d / "repo")
        self.assertIn("$.stories.S1.criteria[0].contract", str(c.exception))
        a = json.loads((self.d / "authoring.json").read_text(encoding="utf-8"))
        a["stories"]["S1"]["criteria"][0]["spec"] = "PPS-x"
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(a, repo=self.d / "repo")
        self.assertIn("$.stories.S1.criteria[0]", str(c.exception))

    def test_without_a_repository_head_cannot_be_resolved(self):
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.seal(json.loads((self.d / "authoring.json").read_text(encoding="utf-8")))
        self.assertIn("HEAD", str(c.exception))


class Schema(unittest.TestCase):
    """docs/v2.1/bundle-authoring.schema.json names exactly the keys the tool accepts (it documents; the tool decides)."""

    def test_the_schema_and_the_tool_agree_on_every_closed_key_set(self):
        s = json.loads((ROOT / "docs/v2.1/bundle-authoring.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(s["required"]), sorted(bundle_cli.AUTHORING_KEYS))
        self.assertEqual(s["properties"]["format"]["const"], bundle_cli.AUTHORING_FORMAT)
        self.assertEqual(sorted(s["$defs"]["contract"]["required"]), sorted(bundle_cli.CONTRACT_KEYS))
        self.assertEqual(sorted(s["$defs"]["criterion"]["required"]), sorted(bundle_cli.CRITERION_KEYS))
        self.assertEqual(sorted(s["$defs"]["criterion"]["properties"]["facts"]["required"]), sorted(bundle.FACT_FIELDS))


if __name__ == "__main__":
    unittest.main()
