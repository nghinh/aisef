"""WP-0.3 — F1–F11 conformance: definite states, RFC-extracted references, and no pass by absence."""

import copy
import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("freeze_conformance", ROOT / "validation" / "v2" / "freeze_conformance.py")
fc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(fc)


class Conformance(unittest.TestCase):
    def setUp(self):
        self.rfc, self.code, self.manifest = fc.load_inputs()
        self.result = fc.evaluate(self.rfc, self.code, self.manifest)

    def _items(self, result):
        return {i["id"]: i["state"] for i in result["items"]}

    def _sub(self, result, sid):
        return next(s for s in result["subchecks"] if s["id"] == sid)

    # ------------------------------------------------------------------ the committed state

    def test_exactly_F1_to_F11_each_with_a_definite_state(self):
        self.assertEqual([i["id"] for i in self.result["items"]], fc.FROZEN_IDS)
        for i in self.result["items"]:
            self.assertIn(i["state"], (fc.PASS, fc.PENDING, fc.FAIL), i["id"])

    def test_no_problems_and_committed_record_current(self):
        self.assertEqual(fc.problems_of(self.result), [])
        self.assertEqual((ROOT / fc.OUT_REL).read_text(encoding="utf-8"), fc.render(self.result))

    def test_every_required_now_subcheck_passes(self):
        for s in self.result["subchecks"]:
            if s["required_now"]:
                self.assertEqual(s["state"], fc.PASS, s["id"])

    def test_pending_only_for_later_phases_and_always_names_its_package(self):
        for s in self.result["subchecks"]:
            if s["state"] == fc.PENDING:
                self.assertFalse(s["required_now"], s["id"])
                self.assertTrue(s["implemented_by"].startswith("WP-"), s["id"])

    def test_no_item_passes_while_pending(self):
        for i in self.result["items"]:
            if i["state"] == fc.PASS:
                self.assertEqual(i["pending_on"], [], i["id"])

    # ------------------------------------------------------------------ adversarial

    def test_an_added_owner_member_fails_F3(self):
        code = copy.deepcopy(self.code)
        code["Owner"][0].append("AUDITOR")
        r = fc.evaluate(self.rfc, code, self.manifest)
        self.assertEqual(self._items(r)["F3"], fc.FAIL)
        self.assertIn("AUDITOR", self._sub(r, "F3.owner_set")["extra"])

    def test_a_renamed_enum_member_fails_its_item(self):
        code = copy.deepcopy(self.code)
        names = code["StoryAdmissionDisposition"][0]
        names[names.index("PRE_SATISFIED")] = "ALREADY_SATISFIED"
        self.assertEqual(self._items(fc.evaluate(self.rfc, code, self.manifest))["F7"], fc.FAIL)

    def test_a_changed_event_type_fails_F1(self):
        code = copy.deepcopy(self.code)
        vals = code["EventType"][1]
        vals[vals.index("run/end")] = "run/finish"
        self.assertEqual(self._items(fc.evaluate(self.rfc, code, self.manifest))["F1"], fc.FAIL)

    def test_a_seventh_control_projection_fails_F11(self):
        code = copy.deepcopy(self.code)
        code["ControlProjection"][1].append("cost_estimate")
        self.assertEqual(self._items(fc.evaluate(self.rfc, code, self.manifest))["F11"], fc.FAIL)

    def test_a_reworded_invariant_title_fails_F10(self):
        code = copy.deepcopy(self.code)
        t = code["__invariant_titles__"][1]
        t[t.index("IX:No Developer Artefact Is Executed At The Parent Revision")] = "IX:No Developer Code At Parent"
        self.assertEqual(self._items(fc.evaluate(self.rfc, code, self.manifest))["F10"], fc.FAIL)

    def test_absent_implementation_of_a_reached_phase_is_FAIL_not_PENDING(self):
        r = fc.evaluate(self.rfc, None, self.manifest)  # aisef2.arch.enums gone
        self.assertTrue(r["ratchet_violations"])
        self.assertEqual(self._sub(r, "F3.owner_set")["state"], fc.FAIL)
        self.assertEqual(self._items(r)["F3"], fc.FAIL)
        self.assertNotIn(fc.PASS, {i["state"] for i in r["items"]})

    def test_later_phase_symbol_present_without_evaluation_is_FAIL_not_PASS(self):
        real = fc.symbol_present
        with mock.patch.object(fc, "symbol_present",
                               lambda m, a: True if m == "aisef2.runtime.run_scope" else real(m, a)):
            r = fc.evaluate(self.rfc, self.code, self.manifest)
        self.assertEqual(self._sub(r, "F8.scopes_and_lifetime_order")["state"], fc.FAIL)
        self.assertEqual(self._items(r)["F8"], fc.FAIL)

    def test_unextractable_rfc_reference_is_FAIL_never_vacuous_PASS(self):
        broken = self.rfc.replace("class Owner(Enum):", "class OwnerRemoved(Enum):", 1)
        self.assertNotEqual(broken, self.rfc, "fixture edit did not apply")
        r = fc.evaluate(broken, self.code, self.manifest)
        self.assertEqual(self._sub(r, "F3.owner_set")["state"], fc.FAIL)
        self.assertIn("could not be extracted", self._sub(r, "F3.owner_set")["detail"])

    def test_advancing_the_phase_turns_pending_into_ratchet_failures(self):
        with mock.patch.object(fc, "CURRENT_PHASE", "P3"):
            r = fc.evaluate(self.rfc, self.code, self.manifest)
        self.assertEqual(self._sub(r, "F11.projections_implemented")["state"], fc.FAIL)
        self.assertIn("F11.projections_implemented", r["ratchet_violations"])

    def test_F6_plan_obligation_is_compared_field_by_field(self):
        self.assertEqual(self._sub(self.result, "F6.plan_obligation_shape")["state"], fc.PASS)
        broken = self.rfc.replace("    expected_parent: ParentExpectation\n", "    expected_parent: BehaviorVerdict\n"
                                  "    parent_verdict: BehaviorVerdict\n", 1)
        self.assertNotEqual(broken, self.rfc, "fixture edit did not apply")
        self.assertEqual(self._sub(fc.evaluate(broken, self.code, self.manifest), "F6.plan_obligation_shape")["state"],
                         fc.FAIL)

    def test_V2_001_the_old_candidate_routing_fails_F2(self):
        """ARCHITECTURE-EXCEPTION-V2-001 reproducer: PRECONDITION_ABSENT at the candidate charged to PLAN."""
        from aisef2.arch.enums import ContractSatisfaction, MeasurementPoint, StoryAdmissionDisposition
        from aisef2.control import routing
        from aisef2.control.owner import FailureCode
        from aisef2.product.outcome import IndeterminateReason
        key = (MeasurementPoint.CANDIDATE, ContractSatisfaction.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT,
               None)
        old = (FailureCode.PRECONDITION_BROKEN, StoryAdmissionDisposition.PRECONDITION_BROKEN, None, "§10 old row")
        with mock.patch.dict(routing._EXECUTED, {key: old}):
            sub = self._sub(fc.evaluate(self.rfc, self.code, self.manifest), "F2.owner_routing_table")
        self.assertEqual(sub["state"], fc.FAIL)
        self.assertTrue(any("CANDIDATE" in p and "DEVELOPER" in p for p in sub["problems"]), sub["problems"])

    def test_F2_reference_is_read_from_the_rfc_10_3_table(self):
        row = "| CANDIDATE | `INDETERMINATE(PRECONDITION_ABSENT)` | any admitted | the implementation did not establish " \
              "the subject the contract requires | DEVELOPER |"
        self.assertIn(row, self.rfc)
        sub = self._sub(fc.evaluate(self.rfc.replace(row, row.replace("| DEVELOPER |", "| PLAN |")), self.code,
                                    self.manifest), "F2.owner_routing_table")
        self.assertEqual(sub["state"], fc.FAIL)

    def test_a_present_shape_is_compared_field_by_field(self):
        broken = self.rfc.replace("    rationale: str      # prose", "    reasoning: str      # prose", 1)
        self.assertNotEqual(broken, self.rfc, "fixture edit did not apply")
        sub = self._sub(fc.evaluate(broken, self.code, self.manifest), "F4.behavior_contract_shape")
        self.assertEqual(sub["state"], fc.FAIL)
        self.assertIn("rationale", sub["implemented"])

    def test_F5_probe_protocol_is_compared_member_by_member_with_signatures(self):
        self.assertEqual(self._sub(self.result, "F5.probe_protocol")["state"], fc.PASS)
        sig = "def evaluate(self, spec: ProductProofSpec, at: RevisionRef, env: ExecutionEnv) -> ProbeResult: ..."
        self.assertIn(sig, self.rfc)
        sub = self._sub(fc.evaluate(self.rfc.replace(sig, sig.replace(", env: ExecutionEnv", "")), self.code,
                                    self.manifest), "F5.probe_protocol")
        self.assertEqual(sub["state"], fc.FAIL)
        self.assertIn(["evaluate", ["self", "spec", "at", "env"]], sub["implemented"])
        from typing import Protocol
        from aisef2.probe import protocol

        class Drifted(Protocol):
            id: str
            digest: str

            def enforcement(self): ...

            def harness_preconditions(self): ...

            def evaluate(self, spec, at, env, extra_path): ...
        with mock.patch.object(protocol, "Probe", Drifted):
            sub = self._sub(fc.evaluate(self.rfc, self.code, self.manifest), "F5.probe_protocol")
        self.assertEqual(sub["state"], fc.FAIL)
        with mock.patch.object(protocol, "Probe", type("NotAProtocol", (), {})):
            self.assertIn("is not a typing.Protocol",
                          self._sub(fc.evaluate(self.rfc, self.code, self.manifest), "F5.probe_protocol")["detail"])

    def test_F5_calibration_contracts_are_compared_field_by_field_with_the_mechanism_literal(self):
        self.assertEqual(self._sub(self.result, "F5.calibration_contracts")["state"], fc.PASS)
        for old, new in (("    observation_class: str                  # the class",
                          "    observation_kind: str                  # the class"),
                         ('"fixture_construction", "other_qualified"', '"fixture_construction"')):
            broken = self.rfc.replace(old, new, 1)
            self.assertNotEqual(broken, self.rfc, "fixture edit did not apply")
            with self.subTest(edit=new):
                self.assertEqual(self._sub(fc.evaluate(broken, self.code, self.manifest),
                                           "F5.calibration_contracts")["state"], fc.FAIL)

    # ------------------------------------------------------------------ references really come from the RFC

    def test_lifetime_order_reference_is_lease_first_and_lease_last(self):
        order = fc.RFC(self.rfc).lifetime_order()
        self.assertEqual(len(order["begin"]), 5)
        self.assertEqual(len(order["shutdown"]), 6)
        self.assertIn("run lease", order["begin"][0])
        self.assertIn("run lease", order["shutdown"][-1])

    def test_product_proof_spec_reference_carries_no_plan_fact(self):
        fields = fc.RFC(self.rfc).dataclasses["ProductProofSpec"]
        for forbidden in ("story_id", "plan_id", "expected_parent", "required_at_baseline"):
            self.assertNotIn(forbidden, fields)


if __name__ == "__main__":
    unittest.main()
