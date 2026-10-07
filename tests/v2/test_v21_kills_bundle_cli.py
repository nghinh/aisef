"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/bundle_cli.py's V2.1 mutation targets, each class
named by the target and the mutants it kills. In the kill set of exactly the targets it kills (validation/v2/mutation.py)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402


class Coverage(unittest.TestCase):
    """coverage — "L312 string 'clause' emptied", "L313 dict entry 1 dropped", "L313 dict entry 2 dropped", "L315 string
    'limit' emptied", "L315 string \"clauses are the ones ...\" emptied": the B5 report groups each requirement's
    criteria by the clause their facts declare, lists the criteria that cite no requirement of the bundle, and states
    its own limit (it does not read the requirements document)."""

    def test_the_report_is_by_requirement_and_clause_with_the_strays_and_its_limit(self):
        b = {"requirements": [{"id": "R1"}, {"id": "R2"}, {"id": "R3"}],
             "facts": {"C1": {"requirement": "R1", "clause": "R1.a"}, "C2": {"requirement": "R1", "clause": "R1.b"},
                       "C3": {"requirement": "R1", "clause": "R1.a"}, "C4": {"requirement": "R2"},
                       "C5": {"requirement": "R9", "clause": "R9.a"}}}
        self.assertEqual(bundle_cli.coverage(b), {
            "requirements": {"R1": {"status": "COVERED", "clauses": {"R1.a": ["C1", "C3"], "R1.b": ["C2"]},
                                    "criteria": ["C1", "C2", "C3"]},
                             "R2": {"status": "COVERED", "clauses": {None: ["C4"]}, "criteria": ["C4"]},
                             "R3": {"status": "UNCOVERED", "clauses": {}, "criteria": []}},
            "criteria_citing_no_requirement_of_the_bundle": ["C5"],
            "limit": "clauses are the ones the criteria's facts declare; AISEF does not parse the requirements document"})


class Init(unittest.TestCase):
    """init — "L360 True->False" (`out.mkdir(parents=False)`), "L362 string ' exists: init writes a new directory and never
    into one' emptied": init makes the directory it is given, parents included, and refuses one that exists, saying so."""

    def setUp(self) -> None:
        import tempfile
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name)

    def test_init_makes_a_nested_new_directory_and_refuses_an_existing_one_saying_why(self):
        out = self.tmp / "work" / "projects" / "calc"
        bundle_cli.init("calc-1-story", out)
        self.assertTrue((out / "authoring.json").is_file())
        self.assertTrue(any((out / "repo").rglob("*.py")))
        with self.assertRaises(bundle_cli.B.BundleError) as c:
            bundle_cli.init("calc-1-story", out)
        self.assertEqual(str(c.exception), f"{out} exists: init writes a new directory and never into one")


if __name__ == "__main__":
    unittest.main()
