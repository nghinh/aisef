"""V1-PF-001 after its WP-4.2 replacement (owner ruling 2026-09-30): the corrected run-history rule on the owner's
known-bad cases, the decision for the recorded recurrence, and the historical attempt left exactly as recorded."""

import json
import pathlib
import tempfile
import unittest

from validation.qualification import v1_pf_001_policy as V

rh = V.rh


class Policy(unittest.TestCase):
    def test_a_traceback_path_resolves_to_the_repository_path_even_where_its_absolute_form_exists(self):
        # CI 36788420167 (windows): the recorded D:\\a\\aisef\\aisef\\aisef\\... exists on a runner checked out there
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d).resolve()
            (root / "aisef" / "clients").mkdir(parents=True)
            (root / "aisef" / "clients" / "base.py").write_text("", encoding="utf-8")
            for raw in (str(root / "aisef" / "clients" / "base.py"), str(root).replace("/", "\\") + "\\aisef\\clients\\base.py",
                        "D:\\a\\aisef\\aisef\\aisef\\clients\\base.py"):
                self.assertEqual(V.repo_path(raw, root), "aisef/clients/base.py", raw)
            self.assertIsNone(V.repo_path("/elsewhere/other.py", root))

    def test_every_calibration_case_holds(self):
        rec = V.calibrate()
        self.assertTrue(rec["all_held"], [c for c in rec["cases"] if not c["held"]])
        ids = {c["id"] for c in rec["cases"]}
        for required in ("known_recurrence_before_WP_4_2", "exact_known_recurrence_after_WP_4_2_in_frozen_V1",
                         "same_signature_in_the_aisef2_process_path", "unknown_windows_process_cleanup_failure",
                         "changed_v1_tree_at_the_attempt", "missing_replacement_evidence"):
            self.assertIn(required, ids)

    def test_the_recorded_recurrence_is_record_only_and_its_attempt_stays_as_recorded(self):
        d = V.decide()
        self.assertEqual((d["derived_effect"], d["reasons_if_stop"]), ("RECORD_ONLY", []))
        self.assertEqual(d["history_entry_as_recorded"]["gate_effect"], "STOP")
        self.assertEqual(d["history_entry_as_recorded"]["result"], "FAIL")
        entry = V.recorded_attempt()["entry"]
        self.assertNotIn("recurrence_facts", entry)   # the facts are evaluated, never written back

    def test_record_only_is_admitted_only_for_typed_exact_facts_and_never_as_a_pass(self):
        a = V.recorded_attempt()
        policy = rh.load_policy(V.ROOT)
        e = {**a["entry"], "seq": 1, "gate_effect": "RECORD_ONLY", "recurrence_facts": V.derived_facts(a["record"])}
        self.assertEqual(rh.entry_problems([e], policy), [])
        base = json.loads((V.ROOT / rh.POLICY_REL).read_text(encoding="utf-8"))
        self.assertTrue(rh.entry_problems([e], base))                                   # no amendment: STOP
        self.assertTrue(rh.entry_problems([{**e, "recurrence_facts": None}], policy))   # untyped: STOP
        self.assertEqual(rh.entry_problems([{**e, "gate_effect": "STOP"}], policy), [])  # STOP is always admissible
        self.assertTrue(rh.entry_problems([{**e, "result": "PASS", "classification": None, "failing_tests": []}], policy))
        self.assertFalse(rh.gate_green([e], e["commit"], e["where"], e["job"], policy))


if __name__ == "__main__":
    unittest.main()
