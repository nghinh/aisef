"""Plan-level adversarial tests for the Cycle-1 implementation plan (PLANDEP-1..5).

Each negative case removes one required dependency, barrier or document fact and asserts that plan validation
fails. The clean manifest must pass every check. This is validation of the *plan*, not of V2 code — no V2
implementation exists.
"""

import importlib.util
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("plan_validate", ROOT / "validation" / "v2" / "plan_validate.py")
pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pv)


def _failing_checks(m):
    return {name for name, fn in pv.CHECKS if fn(m)}


class CleanPlan(unittest.TestCase):
    def test_clean_manifest_passes_every_check(self):
        m = pv.load()
        self.assertEqual(pv.validate(m), [])

    def test_counts_unchanged(self):
        m = pv.load()
        self.assertEqual(len(m["work_packages"]), 37)

    def test_every_frozen_item_covered(self):
        m = pv.load()
        for f in m["architecture_baseline"]["frozen_items"]:
            self.assertTrue(any(f in p["frozen_items"] for p in m["work_packages"]), f)

    def test_guard_is_ancestor_of_every_non_exempt_package(self):
        m = pv.load()
        by = {p["id"]: p for p in m["work_packages"]}
        for pid in by:
            if pid in ("WP-0.1", "WP-0.4"):
                continue
            self.assertIn("WP-0.4", pv.explicit_ancestors(pid, by), pid)

    def test_p0_order_is_exactly_as_required(self):
        m = pv.load()
        lv = pv.levels(m)
        order = sorted((p["id"] for p in m["work_packages"] if p["phase"] == "P0"), key=lambda k: lv[k])
        self.assertEqual(order, ["WP-0.1", "WP-0.4", "WP-0.2", "WP-0.3", "WP-0.5"])

    def test_orchestration_requires_wp_2_5_explicitly(self):
        m = pv.load()
        by = {p["id"]: p for p in m["work_packages"]}
        self.assertIn("WP-2.5", pv.explicit_ancestors("WP-6.2", by))

    def test_generated_documents_in_sync(self):
        self.assertEqual(pv.generate(pv.load(), write=False), [])


class PlanDep(unittest.TestCase):
    def test_PLANDEP_1_remove_guard_ancestry_from_a_P1_package(self):
        m = pv.apply_fixture(pv.load(), "PLANDEP-1")
        self.assertIn("C guard_ancestry", _failing_checks(m))
        self.assertTrue(any("WP-1.1" in e for e in pv.check_c_guard_ancestry(m)))

    def test_PLANDEP_2_P3_runnable_before_P2_exit(self):
        m = pv.apply_fixture(pv.load(), "PLANDEP-2")
        errs = pv.check_b_barriers(m)
        self.assertIn("B phase_barrier_completeness", _failing_checks(m))
        # caught independently of the declared barrier: WP-3.1 runnable before P2 completes
        self.assertTrue(any("WP-3.1 is runnable" in e and "before P2" in e for e in errs), errs)

    def test_PLANDEP_3_remove_wp_2_5_from_orchestration(self):
        m = pv.apply_fixture(pv.load(), "PLANDEP-3")
        self.assertIn("D orchestration_semantics", _failing_checks(m))
        self.assertTrue(any("WP-2.5" in e for e in pv.check_d_orchestration(m)))

    def test_PLANDEP_4_QP_8_before_QP_7(self):
        m = pv.apply_fixture(pv.load(), "PLANDEP-4")
        self.assertIn("E qualification_chain", _failing_checks(m))
        self.assertTrue(any("QP-8 can start without QP-7" in e for e in pv.check_e_qualification_chain(m)))

    def test_PLANDEP_5_hand_edited_dependency_table_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = pathlib.Path(tmp)
            for f in pv.DOCS.iterdir():
                shutil.copy(f, docs / f.name)
            graph = docs / "AISEF-V2-CYCLE1-DEPENDENCY-GRAPH.md"
            text = graph.read_text(encoding="utf-8")
            edited = text.replace("| `WP-6.2` | P6 | 27 | `WP-6.1`, `WP-4.6`, `WP-5.5`, `WP-2.5` |",
                                  "| `WP-6.2` | P6 | 27 | `WP-6.1`, `WP-4.6`, `WP-5.5` |")
            self.assertNotEqual(text, edited, "fixture edit did not apply")
            graph.write_text(edited, encoding="utf-8")
            saved = pv.DOCS
            pv.DOCS = docs
            try:
                drift = pv.generate(pv.load(saved / "cycle1-manifest.json"), write=False)
            finally:
                pv.DOCS = saved
            self.assertTrue(any("DEPENDENCY-GRAPH" in d for d in drift), drift)

    def test_PLANDEP_5b_hand_edited_prose_block_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = pathlib.Path(tmp)
            for f in pv.DOCS.iterdir():
                shutil.copy(f, docs / f.name)
            plan = docs / "AISEF-V2-CYCLE1-IMPLEMENTATION-PLAN.md"
            text = plan.read_text(encoding="utf-8")
            edited = text.replace("**Length 32 packages.**", "**Length 19 packages.**", 1)
            self.assertNotEqual(text, edited, "fixture edit did not apply")
            plan.write_text(edited, encoding="utf-8")
            saved = pv.DOCS
            pv.DOCS = docs
            try:
                drift = pv.generate(pv.load(saved / "cycle1-manifest.json"), write=False)
            finally:
                pv.DOCS = saved
            self.assertTrue(any("IMPLEMENTATION-PLAN" in d for d in drift), drift)


if __name__ == "__main__":
    unittest.main()
