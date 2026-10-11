"""V2.1 (owner B-03 survivor audit, cluster `lint`): `aisef bundle lint` reports a bundle whose criteria disagree about
the TYPE of their `clause` fact; it does not die printing its own report.

`lint` promises a verdict and why: a bundle whose facts do not hold is NOT_READY (exit 1) and says so, either through the
kernel's own load check (admission `load`, once every contract is approved) or, before that, through what is still to be
approved. A criterion without its clause was already reported that way; two criteria of ONE requirement, one declaring
"1.1" and the other not (or a number, a list), made `coverage()` hold a clause dict with `None` beside a string,
`json.dumps(..., sort_keys=True)` cannot order those, and the operator got `refused: TypeError` with exit 2 and no
report. A clause that is not hashable (a list) died one step earlier, in `coverage()` itself.

Every bundle is the shipped calc-3-stories example, sealed and approved, with the facts of its criteria edited the way
`seal` lets them through (it does not validate facts)."""

from __future__ import annotations

import contextlib
import copy
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

MISSING = object()      # the clause fact is not there at all
ADD, ADD_PRESERVED = "C-ADD", "C-ADD-3"      # the two criteria of requirement R-1 (clause "1.1" in the example)


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def run_main(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bundle_cli.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class LintReportsClauseFactsThatDoNotHold(unittest.TestCase):
    sealed: dict        # calc-3-stories, sealed, nothing approved
    approved: dict      # the same, every contract approved: READY as it is

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        d = pathlib.Path(t.name) / "calc"
        bundle_cli.init("calc-3-stories", d)
        git(d / "repo", "init", "-q", "-b", "main")
        git(d / "repo", "add", "-A")
        git(d / "repo", "commit", "-q", "-m", "baseline")
        cls.sealed, _ = bundle_cli.seal(json.loads((d / "authoring.json").read_text(encoding="utf-8")), repo=d / "repo")
        cls.approved = cls.sealed
        for c in [c["id"] for c in cls.sealed["contracts"]]:
            cls.approved = bundle_cli.approve(cls.approved, c, "human:t", 1.0)

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def lint(self, base: dict, clauses: dict, *, exit_code: int = 1) -> tuple[dict, str]:
        """`aisef bundle lint` of `base` with the clause fact of each criterion in `clauses` set (MISSING: removed):
        the report it printed, after checking it exited NOT_READY (1; or `exit_code`) with nothing on stderr."""
        doc = copy.deepcopy(base)
        for cid, value in clauses.items():
            if value is MISSING:
                del doc["facts"][cid]["clause"]
            else:
                doc["facts"][cid]["clause"] = value
        path = self.tmp / "bundle.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, out, err = run_main("lint", path)
        self.assertEqual((code, err), (exit_code, ""), out)
        return json.loads(out), out

    def groups(self, report: dict) -> dict:
        return report["coverage"]["requirements"]["R-1"]["clauses"]

    def test_the_bundle_as_sealed_and_approved_is_ready(self):      # the baseline every case below edits
        path = self.tmp / "bundle.json"
        path.write_text(json.dumps(self.approved), encoding="utf-8")
        code, out, err = run_main("lint", path)
        self.assertEqual((code, err, json.loads(out)["verdict"]), (0, "", "READY"))
        self.assertEqual(self.groups(json.loads(out)), {"1.1": [ADD, ADD_PRESERVED]})

    def test_every_criterion_of_the_requirement_without_its_clause_is_reported(self):      # already reported before
        report, _ = self.lint(self.approved, {ADD: MISSING, ADD_PRESERVED: MISSING})
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["load"])
        self.assertEqual(self.groups(report), {"null": [ADD, ADD_PRESERVED]})

    def test_one_criterion_without_its_clause_beside_one_that_declares_it_is_reported_the_same_way(self):
        report, _ = self.lint(self.approved, {ADD_PRESERVED: MISSING})
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["load"])
        self.assertEqual(self.groups(report), {"1.1": [ADD], "null": [ADD_PRESERVED]})
        self.assertEqual(report["coverage"]["requirements"]["R-1"]["criteria"], [ADD, ADD_PRESERVED])

    def test_the_same_before_the_contracts_are_approved(self):      # admission is "not run": still a report, still NOT_READY
        report, _ = self.lint(self.sealed, {ADD_PRESERVED: MISSING})
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertTrue(report["to_approve"])
        self.assertTrue(report["admission"].startswith("not run"), report["admission"])
        self.assertEqual(self.groups(report), {"1.1": [ADD], "null": [ADD_PRESERVED]})

    def test_a_clause_that_is_not_a_string_beside_one_that_is_is_reported_under_what_it_is(self):
        for value in (None, 2, 1.5, True, ["1.1"], {"n": 1}):
            with self.subTest(clause=value):
                report, _ = self.lint(self.approved, {ADD_PRESERVED: value})
                self.assertEqual(report["verdict"], "NOT_READY")
                self.assertEqual([f["check"] for f in report["admission"]["failed"]], ["load"])
                self.assertEqual(self.groups(report), {"1.1": [ADD], json.dumps(value): [ADD_PRESERVED]})

    def test_a_clause_that_cannot_be_a_dict_key_is_reported_alone_as_well(self):      # a list/object died in coverage()
        for value in (["1.1"], {"n": 1}):
            with self.subTest(clause=value):
                report, _ = self.lint(self.approved, {ADD: value, ADD_PRESERVED: value})
                self.assertEqual(report["verdict"], "NOT_READY")
                self.assertEqual(self.groups(report), {json.dumps(value): [ADD, ADD_PRESERVED]})

    def test_equal_objects_written_in_another_key_order_are_one_clause(self):
        report, _ = self.lint(self.approved, {ADD: {"b": 1, "a": 2}, ADD_PRESERVED: {"a": 2, "b": 1}})
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual(self.groups(report), {'{"a": 2, "b": 1}': [ADD, ADD_PRESERVED]})

    def test_a_value_json_cannot_write_is_keyed_by_its_text_not_a_traceback(self):      # in-process callers of lint()
        facts = {"C1": {"requirement": "R1", "clause": b"x"}, "C2": {"requirement": "R1", "clause": "1.1"}}
        report = bundle_cli.coverage({"requirements": [{"id": "R1"}], "facts": facts})
        self.assertEqual(report["requirements"]["R1"]["clauses"], {json.dumps("b'x'"): ["C1"], "1.1": ["C2"]})
        json.dumps(report, sort_keys=True, default=str)      # printable, as main prints it

    def test_two_criteria_of_different_non_string_types_are_both_reported(self):
        report, _ = self.lint(self.approved, {ADD: 7, ADD_PRESERVED: MISSING})
        self.assertEqual(report["verdict"], "NOT_READY")
        self.assertEqual(self.groups(report), {"7": [ADD], "null": [ADD_PRESERVED]})

    def test_clauses_that_already_printed_print_as_they_did(self):      # no change of JSON for inputs that were handled
        # numbers that order among themselves keep their numeric order ("2" before "10"), not the text order
        report, _ = self.lint(self.approved, {ADD: 10, ADD_PRESERVED: 2})
        self.assertEqual(list(self.groups(report)), ["2", "10"])
        # strings (a bundle that is READY) keep their own order
        report, _ = self.lint(self.approved, {ADD: "b", ADD_PRESERVED: "a"}, exit_code=0)
        self.assertEqual((report["verdict"], list(self.groups(report))), ("READY", ["a", "b"]))


if __name__ == "__main__":
    unittest.main()
