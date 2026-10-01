"""C2-P10 / WP-2.10.1 — the cohort machinery's Q0 rules on the real tree (confinement, boundary, the LedgerLock
binding, the census) and on synthetic inputs, and the evidence record re-derived from the tree. Not a kill-test module:
it reads the git index, which the mutation runner's scratch copy does not have."""

import ast
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = _load("aisef_v2_cohort_static_checks_test", ROOT / "validation" / "v2" / "cohort_static_checks.py")


class OnTheTree(unittest.TestCase):
    def test_every_rule_passes(self):
        self.assertEqual(cs.check(ROOT), [])

    def test_nothing_outside_the_machinery_imports_it(self):
        importers = {rel for rel in cs._listed(ROOT, "*.py") if any(
            cs._names_cohort(m) for _, m in cs._imported(rel, ast.parse((ROOT / rel).read_text(encoding="utf-8"))))}
        self.assertIn("aisef2/cohort/lifecycle.py", importers)       # the scan sees an import when there is one
        self.assertEqual({r for r in importers if not r.startswith(cs.ALLOWED_IMPORTERS)}, set())
        self.assertEqual({r for r in importers if r.startswith("aisef2/") and not r.startswith("aisef2/cohort/")}, set())
        consumers = ("validation/qualification/q4", "validation/qualification/q5", "validation/qualification/p10",
                     "validation/qualification/p5_", "aisef2/probe/", "aisef2/product/", "aisef2/orchestrate/",
                     "aisef2/journal/", "tests/v2/p3/", "tests/v2/refmodel/")
        self.assertEqual({r for r in importers if r.startswith(consumers)}, set())

    def test_no_cohort_record_exists_anywhere_in_the_tree(self):
        files = cs._listed(ROOT, "*.json", "*.jsonl")
        self.assertIn("closure-evidence/v2/P10/WORKLOAD.json", files)
        self.assertEqual(cs.census(ROOT, files), [])


class Rules(unittest.TestCase):
    def test_confinement_sees_every_import_form(self):
        sources = {"from aisef2.cohort import lifecycle\n": 1, "import aisef2.cohort.preregistration as p\n": 1,
                   "from aisef2 import cohort\n": 1, "import importlib\nimportlib.import_module('aisef2.cohort')\n": 2,
                   "x = __import__('aisef2.cohort.lifecycle')\n": 1, "import aisef2.cohorts\n": 0, "import json\n": 0}
        for source, line in sources.items():
            found = cs.violations("validation/qualification/q4.py", source, ("COHORT_CONFINED",))
            self.assertEqual(found, [f"COHORT_CONFINED validation/qualification/q4.py:{line} imports aisef2.cohort: "
                                     "nothing outside the machinery, its checks and its tests imports it"] if line else [])
        self.assertTrue(cs.violations("aisef2/__init__.py", "from . import cohort\n", ("COHORT_CONFINED",)))
        self.assertTrue(cs.violations("aisef2/probe/x.py", "from ..cohort.lifecycle import seal\n", ("COHORT_CONFINED",)))
        for allowed in ("aisef2/cohort/x.py", "tests/v2/test_c2_p10_x.py", "validation/v2/profile_freeze.py",
                        "validation/qualification/c2_p10_x.py"):
            self.assertEqual(cs.violations(allowed, "from aisef2.cohort import lifecycle\n", ("COHORT_CONFINED",)), [])

    def test_the_boundary_admits_only_the_standard_library_and_the_identity_modules(self):
        for bad in ("from aisef2.journal.event import Event\n", "from ..orchestrate import gate\n",
                    "import aisef2.probe.protocol\n", "from aisef2.control.owner import classify\n", "import aisef\n",
                    "import validation\n", "from aisef2 import quality\n"):
            self.assertEqual(len(cs.violations("aisef2/cohort/x.py", bad, ("COHORT_BOUNDARY",))), 1, bad)
        good = "import json\nfrom aisef2.runtime.runspec import resolve\nfrom . import preregistration\n"
        self.assertEqual(cs.violations("aisef2/cohort/x.py", good, ("COHORT_BOUNDARY",)), [])
        self.assertEqual(cs.violations("aisef2/journal/x.py", "from aisef2.orchestrate import gate\n",
                                       ("COHORT_BOUNDARY",)), [])

    def test_the_ledgerlock_binding_fails_closed(self):
        from aisef2.cohort.preregistration import DEVELOPMENT_REGRESSION
        self.assertEqual(cs.binding_problems(ROOT, DEVELOPMENT_REGRESSION), [])
        for key in ("requirements_sha256", "plan_baseline", "plan_hash", "workload_record_sha256"):
            entry = dict(DEVELOPMENT_REGRESSION[0], **{key: "0"})
            self.assertEqual(cs.binding_problems(ROOT, [entry]), [
                f"DEVELOPMENT_REGRESSION_BOUND LedgerLock: {key} is '0', its file holds "
                f"{DEVELOPMENT_REGRESSION[0][key]!r}"])
        self.assertEqual(len(cs.binding_problems(ROOT, [])), 2)
        moved = dict(DEVELOPMENT_REGRESSION[0], requirements_source="tests/v2/fixtures/none.md")
        self.assertTrue(cs.binding_problems(ROOT, [moved])[0].startswith(
            "DEVELOPMENT_REGRESSION_BOUND LedgerLock: its sources cannot be read"))

    def test_the_census_finds_a_record_at_any_depth_and_in_any_file(self):
        schema = "aisef2.cohort.preregistration/1"
        files = {"a.json": json.dumps({"x": [{"y": {"schema": schema}}]}), "b.jsonl": '{"a": 1}\n{"schema": "%s"}\n' % schema,
                 "c.json": '{"schema": "%s", ' % schema, "d.json": json.dumps({"text": json.dumps({"schema": schema})}),
                 "e.json": json.dumps({"schema": "aisef2.cohort.preregistration/2"})}
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            for rel, text in files.items():
                (root / rel).write_text(text, encoding="utf-8")
            self.assertEqual(cs.census(root, sorted(files)), [
                "a.json $.x[0].y", "b.jsonl $1", f"c.json (unparsed; names {schema})"])


class Record(unittest.TestCase):
    def test_the_evidence_record_re_derives_from_the_tree(self):
        from validation.qualification import c2_p10_cohort as B
        self.assertEqual(B.check(), [])
        rec = json.loads((ROOT / B.OUT_REL).read_text(encoding="utf-8"))
        self.assertEqual((rec["verdict"], rec["census"]["cohort_count"], rec["census"]["cohort_records"]),
                         ("machinery qualified; cohort count = 0", 0, []))
        self.assertTrue(all(c["holds"] for c in rec["adversarial"]))
        broken = copy.deepcopy(rec)
        broken["adversarial"][0]["holds"] = False
        self.assertTrue(B.problems_of(broken))


if __name__ == "__main__":
    unittest.main()
