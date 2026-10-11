"""Mutation survivors of `aisef2/app/bundle_cli.py::lint` and `::migrate` (batch T03a, owner directive B-03).

What an operator and the next tool read from `aisef bundle lint` and `aisef bundle migrate`, asserted through the
shipped entry point (`bundle_cli.main`) or the public function, against an oracle that is not the code under test:
the input bundle, the written bundle, the loader's own refusal, the authoring document.

* `lint`: READY is the permission to run. A bundle the loader refuses is NOT_READY with exit 1 — the verdict path —
  and the report says which check failed and why (it names `aisef bundle migrate`); the diagnostics
  `criteria_without_calibration` / `criteria_without_contract` agree with check 9 and with the plan; an unapproved
  bundle says admission was not run; coverage by criteria's facts is part of the verdict, not only admission check 1.
* `migrate`: one door (a document that is not a bundle of this format is a MigrationError, exit 2, no traceback)
  and a report that states the plan hash it replaced and the one it wrote.

Offline; no provider; no run."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402
from aisef2.app import calibrations as shipped  # noqa: E402

LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"
CALC3 = ("BC-ADD", "BC-MUL", "BC-TOTAL", "BC-STDLIB")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def run_main(*argv) -> tuple[int, str, str]:
    """(exit status, stdout, stderr) of `aisef bundle ARGV`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def _ok(code: int, err: str, what: str) -> None:
    if code != 0:
        raise AssertionError(f"{what}: exit {code}: {err}")


def build_calc3(tmp: pathlib.Path) -> dict:
    """calc-3-stories from `init` to a lint-ready bundle by the shipped commands only: its authoring document, the
    sealed bundle (nothing approved) and the bundle with every contract approved."""
    d = tmp / "calc-3-stories"
    code, _, err = run_main("init", "--example", "calc-3-stories", "--out", d)
    _ok(code, err, "init")
    git(d / "repo", "init", "-q", "-b", "main")
    git(d / "repo", "add", "-A")
    git(d / "repo", "commit", "-q", "-m", "baseline")
    code, _, err = run_main("seal", d / "authoring.json", "--repo", d / "repo", "--out", d / "b0.json")
    _ok(code, err, "seal")
    cur = d / "b0.json"
    for n, c in enumerate(CALC3, 1):
        code, _, err = run_main("approve", cur, "--contract", c, "--approver", "human:example-owner",
                                "--out", d / f"b{n}.json")
        _ok(code, err, f"approve {c}")
        cur = d / f"b{n}.json"
    return {"dir": d, "authoring": json.loads((d / "authoring.json").read_text(encoding="utf-8")),
            "sealed": d / "b0.json", "approved": cur}


def plan_order(bundle_path: pathlib.Path) -> list[str]:
    """The criterion ids of a bundle file's plan, in the plan's own order."""
    doc = json.loads(bundle_path.read_text(encoding="utf-8"))
    return [o["criterion_id"] for o in doc["plan"]["obligations"]]


def lint_of(path: pathlib.Path, calibrations=None) -> tuple[int, dict, str]:
    """`aisef bundle lint PATH` (with the shipped calibrations table replaced by `calibrations`, when given):
    (exit status, the printed report — {} when it printed none, as a refused input does —, stderr)."""
    if calibrations is None:
        code, out, err = run_main("lint", path)
    else:
        with mock.patch.object(shipped, "CALIBRATIONS", calibrations):
            code, out, err = run_main("lint", path)
    return code, json.loads(out) if out.strip() else {}, err


class _Calc3(unittest.TestCase):
    """The calc-3-stories bundle, built once per test class (a base: it holds no test)."""

    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.calc3 = build_calc3(pathlib.Path(tmp.name))


# ------------------------------------------------------------------------------------------------------- lint


class LintOfABundleTheLoaderRefuses(unittest.TestCase):
    """The 2.0.0 LedgerLock bundle is fully approved, every requirement is covered and no criterion is stray; what
    holds it back is that this release's loader refuses it (its plan names specs this release does not compile).
    That is NOT_READY with exit status 1 — the documented status of a verdict, never `refused input` (2) and never
    READY, which is the permission to run — and the report carries the loader's own refusal, which names the command
    to run next, under the check `load`. The criteria it cannot match to a contract are all listed.

    Pins aisef2/app/bundle_cli.py::lint [34, 35, 42, 43, 44, 45, 50, 51, 53, 54, 55]."""

    def setUp(self) -> None:
        self.doc = json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))
        with self.assertRaises(B.BundleError) as c:
            B.load(self.doc)        # the oracle: what `aisef run` would say at load
        self.refusal = str(c.exception)
        self.code, self.report, self.err = lint_of(LEDGERLOCK_2_0_0)

    def test_only_the_load_holds_the_verdict_back(self):
        self.assertEqual(self.code, 1, self.err)        # a verdict, not a refused input (2)
        # preconditions, so that the verdict below can come from nowhere but the admission
        self.assertEqual(self.report["to_approve"], [])
        self.assertEqual({v["status"] for v in self.report["coverage"]["requirements"].values()}, {"COVERED"})
        self.assertEqual(self.report["coverage"]["criteria_citing_no_requirement_of_the_bundle"], [])
        self.assertEqual(self.report["verdict"], "NOT_READY")
        self.assertNotIn("refused", self.err)

    def test_the_report_names_the_failed_check_load_with_the_loaders_own_refusal(self):
        self.assertEqual(self.code, 1, self.err)
        admission = self.report["admission"]
        self.assertIs(admission["admitted"], False)
        self.assertEqual(len(admission["failed"]), 1)       # one failed check, in the shape R.admit's entries have
        entry = admission["failed"][0]
        self.assertEqual(entry["check"], "load")            # the reason code of a refusal of the loader
        self.assertEqual(entry["problems"], [self.refusal])
        self.assertIn("aisef bundle migrate", entry["problems"][0])

    def test_every_criterion_is_without_a_contract_and_none_is_uncalibrated(self):
        ids = [o["criterion_id"] for o in self.doc["plan"]["obligations"]]
        self.assertEqual(self.code, 1, self.err)
        self.assertIn("criteria_without_contract", self.report)
        self.assertIn("criteria_without_calibration", self.report)
        # the set of ids is the contract; their order in the report is not promised (the plan's order and the sorted
        # order are both deterministic, and nothing reads the list)
        self.assertEqual(sorted(self.report["criteria_without_contract"]), sorted(ids))
        # a criterion without a contract has no class to be calibrated: the two lists never share an id
        self.assertEqual(self.report["criteria_without_calibration"], [])


class LintOfAReadyBundle(_Calc3):
    """READY: nothing left that check 9 or a missing contract would refuse, so both diagnostic lists are present
    and empty (docs/v2.1/evidence/cli-integration-*.out shows this report).

    Pins aisef2/app/bundle_cli.py::lint [11, 12, 29, 32, 41]."""

    def test_both_diagnostic_lists_are_present_and_empty(self):
        code, report, err = lint_of(self.calc3["approved"])
        self.assertEqual(code, 0, err)
        self.assertEqual(report["verdict"], "READY")
        self.assertIn("criteria_without_calibration", report)
        self.assertIn("criteria_without_contract", report)
        self.assertEqual(report["criteria_without_calibration"], [])
        self.assertEqual(report["criteria_without_contract"], [])


class LintOfAnInstallWithoutCalibrations(_Calc3):
    """`calibrations()` is `()` for an install without the shipped table, and check 9 then names every spec. The
    diagnostic `criteria_without_calibration` agrees with the check that decides: it lists the criteria whose
    class is not calibrated (all of them here) and only those.

    Pins aisef2/app/bundle_cli.py::lint [11, 29, 41, 48]."""

    def test_every_criterion_is_listed_and_check_9_is_what_refuses(self):
        ids = plan_order(self.calc3["sealed"])
        code, report, err = lint_of(self.calc3["approved"], ())
        self.assertEqual(code, 1, err)
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["9. probe_calibration"])
        self.assertIn("criteria_without_calibration", report)
        self.assertEqual(sorted(report["criteria_without_calibration"]), sorted(ids))
        self.assertEqual(report["criteria_without_contract"], [])

    def test_only_the_criteria_of_the_uncalibrated_class_are_listed(self):
        kinds = {c["id"]: c["subject"]["kind"] for c in self.calc3["authoring"]["contracts"]}
        stdlib = sorted(cr["id"] for s in self.calc3["authoring"]["stories"].values() for cr in s["criteria"]
                        if kinds[cr["contract"]] == "file_artifact")
        self.assertTrue(stdlib and len(stdlib) < len(plan_order(self.calc3["sealed"])))     # a proper, non-empty part
        rows = tuple(r for r in shipped.CALIBRATIONS if r["probe_id"] != "probe.file_artifact")
        code, report, err = lint_of(self.calc3["approved"], rows)
        self.assertEqual(code, 1, err)
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["9. probe_calibration"])
        self.assertEqual(sorted(report["criteria_without_calibration"]), stdlib)


class LintWithAnUnapprovedContract(_Calc3):
    """A contract nobody approved does not compile, so admission is not run: the report's `admission` is present,
    is not an admission outcome (a str, never a dict `ready` could read `admitted` from) and names what to do —
    `approve` the contracts, then `lint` again.

    Pins aisef2/app/bundle_cli.py::lint [14, 20]."""

    def test_admission_is_present_as_text_naming_the_two_commands(self):
        code, report, err = lint_of(self.calc3["sealed"])
        self.assertEqual(code, 1, err)
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual(sorted(x["contract"] for x in report["to_approve"]), sorted(CALC3))
        self.assertIn("admission", report)
        self.assertIsInstance(report["admission"], str)
        # the cause is named "unapproved", which holds the word "approve": it must not stand for the instruction
        told = report["admission"].replace("unapproved", "")
        self.assertIn("approve", told)
        self.assertIn("lint", told)


class LintCoverageByFactsIsPartOfTheVerdict(_Calc3):
    """Admission check 1 asks that a contract cites each requirement; lint's coverage asks that a plan criterion's
    facts cite it. A requirement an approved contract cites and no criterion proves passes admission and is
    UNCOVERED: the bundle is NOT_READY (exit 1), whose only cause is coverage — the docstring's "every requirement
    is covered".

    Pins aisef2/app/bundle_cli.py::lint [36]."""

    def test_a_requirement_no_criterion_proves_keeps_a_fully_admitted_bundle_from_ready(self):
        a = json.loads(json.dumps(self.calc3["authoring"]))
        a["requirements"].append({"id": "R-9", "text": "something nobody proves", "source": "docs/requirements.md#9"})
        c9 = json.loads(json.dumps(a["contracts"][0]))      # BC-ADD again, as a contract of R-9 no criterion uses
        c9["id"], c9["requirement_ids"] = "BC-9", ["R-9"]
        a["contracts"].append(c9)
        doc, _ = bundle_cli.seal(a, repo=self.calc3["dir"] / "repo")
        for c in (*CALC3, "BC-9"):
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        path = self.calc3["dir"] / "with-r9.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, report, err = lint_of(path)
        self.assertEqual(code, 1, err)
        self.assertEqual(report["to_approve"], [])
        self.assertTrue(report["admission"]["admitted"], report["admission"])     # so the verdict is coverage's alone
        self.assertEqual(report["coverage"]["requirements"]["R-9"]["status"], "UNCOVERED")
        self.assertEqual({k for k, v in report["coverage"]["requirements"].items() if v["status"] == "UNCOVERED"}, {"R-9"})
        self.assertEqual(report["verdict"], "NOT_READY")


# ---------------------------------------------------------------------------------------------------- migrate


class MigrateRefusesADocumentThatIsNotABundleOfThisFormat(unittest.TestCase):
    """The format check is `migrate`'s one door: a document that is not an object of this release's bundle format
    is refused as `MigrationError` (not a parent class, not an AttributeError) naming the format; through the
    command the refusal is `refused: ...` on stderr, exit 2, and nothing is written at --out.

    Pins aisef2/app/bundle_cli.py::migrate [3, 62]."""

    def setUp(self) -> None:
        self.doc = json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))

    def test_each_non_bundle_is_a_migration_error_naming_the_format(self):
        no_format = {k: v for k, v in self.doc.items() if k != "format"}
        cases = {"a list": [], "a string": "x", "null": None, "a number": 7, "an empty object": {},
                 "an object of another format": {**self.doc, "format": "aisef-v2-project/0"},
                 "a bundle without a format": no_format}
        for name, data in cases.items():
            with self.subTest(name):
                with self.assertRaises(bundle_cli.MigrationError) as c:
                    bundle_cli.migrate(data)
                self.assertIn(B.FORMAT, str(c.exception))

    def test_the_command_refuses_with_exit_2_and_says_it_is_not_a_bundle_of_the_format(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            src, out = t / "not-a-bundle.json", t / "migrated.json"
            src.write_text("[]", encoding="utf-8")
            code, stdout, err = run_main("migrate", src, "--out", out)
            self.assertEqual(code, 2, err)
            self.assertEqual(stdout, "")
            self.assertFalse(out.exists())
            self.assertTrue(err.startswith("refused:"), err)
            self.assertNotIn("Traceback", err)
            self.assertIn(B.FORMAT, err)
            # the cause class: the document is not a project bundle (the fragment B.load's own refusal is pinned by)
            self.assertIn("not a project bundle", err)


class MigrateStatesTheTwoPlanHashes(unittest.TestCase):
    """The plan is re-bound, so its hash changes; the report is the operator's statement of which plan hash a 2.0.0
    run recorded and which one the migrated bundle (and every later run) carries: `plan_hash` is
    {from: the input plan's hash, to: the written plan's hash}, the oracle being the input and the output bundle.

    Pins aisef2/app/bundle_cli.py::migrate [19, 37, 39, 40, 53, 54]."""

    def setUp(self) -> None:
        self.doc = json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8"))

    def test_the_report_gives_the_hash_it_replaced_and_the_one_it_wrote(self):
        out, report = bundle_cli.migrate(json.loads(json.dumps(self.doc)))
        self.assertNotEqual(self.doc["plan"]["plan_hash"], out["plan"]["plan_hash"])     # the plan did change
        self.assertEqual(report["plan_hash"]["from"], self.doc["plan"]["plan_hash"])
        self.assertEqual(report["plan_hash"]["to"], out["plan"]["plan_hash"])
        self.assertEqual(B.load(out).plan.plan_hash, report["plan_hash"]["to"])

    def test_the_command_prints_the_same_pair_for_the_file_it_wrote(self):
        with tempfile.TemporaryDirectory() as t:
            out = pathlib.Path(t) / "migrated.json"
            code, stdout, err = run_main("migrate", LEDGERLOCK_2_0_0, "--out", out)
            self.assertEqual(code, 0, err)
            written = json.loads(out.read_text(encoding="utf-8"))
        printed = json.loads(stdout)["plan_hash"]
        self.assertEqual(printed["from"], self.doc["plan"]["plan_hash"])
        self.assertEqual(printed["to"], written["plan"]["plan_hash"])


if __name__ == "__main__":
    unittest.main()
