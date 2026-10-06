"""Plan semantics (owner decision before P2 authorization): the plan states subject absence exactly as the RFC does,
and cites the current approved architecture baseline.

PLANSEM-1 / PLANSEM-2 are the regressions that keep the 'missing subject => REFUTED' simplification from returning.
"""

import copy
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("plan_validate_sem", ROOT / "validation" / "v2" / "plan_validate.py")
pv = importlib.util.module_from_spec(_s)
_s.loader.exec_module(pv)


class ProbeAbsenceSemantics(unittest.TestCase):
    def setUp(self):
        self.m = pv.load()

    def test_the_committed_plan_is_clean(self):
        self.assertEqual(pv.check_f_probe_absence_semantics(self.m), [])
        self.assertEqual(pv.validate(self.m), [])

    def test_PLANSEM_1_restoring_missing_subject_REFUTED_fails(self):
        problems = pv.check_f_probe_absence_semantics(pv.apply_fixture(self.m, "PLANSEM-1"))
        self.assertTrue(any("asserts a global missing-subject => REFUTED" in p for p in problems), problems)
        self.assertTrue(pv.validate(pv.apply_fixture(self.m, "PLANSEM-1")))

    def test_PLANSEM_2_dropping_the_subject_absence_distinction_fails(self):
        problems = pv.check_f_probe_absence_semantics(pv.apply_fixture(self.m, "PLANSEM-2"))
        self.assertIn("PLANSEM: WP-2.1 acceptance cases do not distinguish REQUIRES_SUBJECT from ABSENCE_IS_DECIDABLE",
                      problems)

    def test_each_probe_abs_case_carries_its_rfc_expectation(self):
        cases = {c["id"]: c for c in next(p for p in self.m["work_packages"] if p["id"] == "WP-2.1")["acceptance_cases"]}
        self.assertEqual(list(cases), ["PROBE-ABS-1", "PROBE-ABS-2", "PROBE-ABS-3", "PROBE-ABS-4", "PROBE-ABS-5"])
        for cid, path, bad in (("PROBE-ABS-1", "status", "EXECUTED"), ("PROBE-ABS-2", "behavior_verdict", "REFUTED"),
                               ("PROBE-ABS-3", "contract_satisfaction", "SATISFIED"),
                               ("PROBE-ABS-4", "contract_satisfaction", "UNSATISFIED")):
            with self.subTest(case=cid):
                m = copy.deepcopy(self.m)
                wp = next(p for p in m["work_packages"] if p["id"] == "WP-2.1")
                next(c for c in wp["acceptance_cases"] if c["id"] == cid)["expect"][path] = bad
                self.assertTrue(any(cid in p for p in pv.check_f_probe_absence_semantics(m)))
        m = copy.deepcopy(self.m)
        next(p for p in m["work_packages"] if p["id"] == "WP-2.1")["acceptance_cases"].pop()
        self.assertIn("PLANSEM: WP-2.1 lacks acceptance case PROBE-ABS-5", pv.check_f_probe_absence_semantics(m))

    def test_every_plan_document_is_scanned_and_only_an_explicit_scope_may_state_it(self):
        with tempfile.TemporaryDirectory() as t:
            docs = pathlib.Path(t)
            for f in pv.DOCS.glob("*.md"):
                shutil.copy(f, docs / f.name)
            (docs / "note.md").write_text("| x | subject absent ⇒ `EXECUTED`+`REFUTED` |\n", encoding="utf-8")
            self.assertTrue(any("note.md" in p for p in pv.check_f_probe_absence_semantics(self.m, docs)))
            (docs / "note.md").write_text("absent subject -> REFUTED (scoped to ProductProofSpec PPS-x: an existence "
                                          "observable)\n", encoding="utf-8")
            self.assertEqual(pv.check_f_probe_absence_semantics(self.m, docs), [])

    def test_the_evidence_tables_are_generated_from_the_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            docs = pathlib.Path(t)
            for f in pv.DOCS.iterdir():
                if f.is_file():
                    shutil.copy(f, docs / f.name)
            ep = docs / "AISEF-V2-CYCLE1-EVIDENCE-PLAN.md"
            text = ep.read_text(encoding="utf-8")
            row = next(ln for ln in text.splitlines() if ln.startswith("| `P2-PROBE-PROTOCOL.json`"))
            ep.write_text(text.replace(row, "| `P2-PROBE-PROTOCOL.json` | hand-edited |"), encoding="utf-8")
            saved, pv.DOCS = pv.DOCS, docs
            try:
                drift = pv.generate(self.m, write=False)
            finally:
                pv.DOCS = saved
        self.assertIn("AISEF-V2-CYCLE1-EVIDENCE-PLAN.md: generated block(s) differ", drift)


class ArchitectureBaseline(unittest.TestCase):
    def test_the_plan_cites_the_amended_baseline(self):
        m = pv.load()
        self.assertEqual(pv.check_g_baseline(m), [])
        ab = m["architecture_baseline"]
        through_v2_006 = ["closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-001.json",
                          "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-002.json",
                          "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-003.json",
                          "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-005.json",   # V2-004: superseded, never applied
                          "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-006.json"]
        self.assertEqual([a["record"] for a in ab["amendments"]],
                         through_v2_006 + ["closure-evidence/v2/v2.1/AISEF-V2-RFC-AMENDMENT-V2-007.json"])   # 2.1
        self.assertEqual(ab["original_rfc_normative_digest"],
                         "8f0d522d9db0322c3aff5df2b5e0d568dce0a422f466dc610c7a6a9acdba8e3f")
        # history: the 2.0.0 plan cited the lineage ending at V2-006
        at_2_0_0 = json.loads(subprocess.run(["git", "show", "v2.0.0:docs/implementation/v2/cycle1-manifest.json"],
                                             cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout)
        self.assertEqual([a["record"] for a in at_2_0_0["architecture_baseline"]["amendments"]], through_v2_006)

    def test_WP_0_1_names_the_manifest_its_checker_writes_and_keeps_the_2_0_one(self):
        """2.1: WP-0.1's checker writes the v2.1 manifest; the 2.0 manifest it wrote in Cycle 1 is kept, as history."""
        spec = importlib.util.spec_from_file_location("fm_for_plan_semantics", ROOT / "validation" / "v2" / "freeze_manifest.py")
        fm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fm)
        wp = next(p for p in pv.load()["work_packages"] if p["id"] == "WP-0.1")
        self.assertEqual(wp["evidence_artifact"], fm.MANIFEST_REL)
        self.assertEqual(wp["files_expected"], ["validation/v2/freeze_manifest.py", fm.MANIFEST_REL, fm.HISTORY_MANIFEST_REL])
        at_2_0_0 = json.loads(subprocess.run(["git", "show", "v2.0.0:docs/implementation/v2/cycle1-manifest.json"],
                                             cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout)
        old = next(p for p in at_2_0_0["work_packages"] if p["id"] == "WP-0.1")
        self.assertEqual((old["evidence_artifact"], old["files_expected"]),
                         (fm.HISTORY_MANIFEST_REL, ["validation/v2/freeze_manifest.py", fm.HISTORY_MANIFEST_REL]))
        self.assertEqual(fm.history_problems(ROOT), [])

    def test_citing_the_pre_exception_baseline_fails(self):
        m = pv.load()
        m["architecture_baseline"]["rfc_normative_digest"] = m["architecture_baseline"]["original_rfc_normative_digest"]
        self.assertTrue(any(p.startswith("BASELINE: plan cites rfc_normative_digest") for p in pv.check_g_baseline(m)))
        m = pv.load()
        m["architecture_baseline"]["amendments"] = []
        self.assertIn("BASELINE: plan amendments differ from the approval lineage", pv.check_g_baseline(m))


if __name__ == "__main__":
    unittest.main()
