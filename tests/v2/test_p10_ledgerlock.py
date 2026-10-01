"""P10 / QP-10 — the LedgerLock recorder (validation/qualification/p10.py): the owner's independence tests P10-1..5,
the sealed-cohort rejection tests P10-6..9, and the workload's typed fit with the cycle-1 kernel. Nothing here runs a
model or touches the LedgerLock repository's working tree; the workload build reads frozen evidence and asks the
kernel's own compiler and admission engine.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.plan.obligation import NOT_PREREGISTERED, PlanQualityPolicy  # noqa: E402
from validation.qualification import p10  # noqa: E402

E = [  # a small journal: one story admitted with a PRE_SATISFIED INTRODUCE criterion, drift, then committed
    {"seq": 0, "type": "run/begin", "data": {"journal_format": 3, "run_id": "r"}},
    {"seq": 1, "type": "plan/frozen", "data": {"plan_id": "P", "plan_hash": "a" * 64, "roles": {"C1": "INTRODUCE", "C2": "PRESERVE"}}},
    {"seq": 2, "type": "story/begin", "data": {"story_id": "S1", "parent": "b" * 40}},
    {"seq": 3, "type": "story/admitted", "data": {"story_id": "S1", "admitted": True, "developer_call_permitted": False, "dispositions": {"C1": "PRE_SATISFIED", "C2": "READY"}}},
    {"seq": 4, "type": "story/plan-drift", "data": {"story_id": "S1", "criterion_id": "C1", "attributed_to": "UNATTRIBUTED"}},
    {"seq": 5, "type": "gate/decision", "data": {"gate": "story", "passed": True}},
    {"seq": 6, "type": "story/commit", "data": {"story_id": "S1", "revision": "c" * 40}},
    {"seq": 7, "type": "story/end", "data": {"story_id": "S1"}},
    {"seq": 8, "type": "run/end", "data": {}},
]
ROLES = {"C1": "INTRODUCE", "C2": "PRESERVE"}


class VerdictIndependence(unittest.TestCase):
    def test_P10_1_delivery_verdict_is_derived_without_any_plan_quality_input(self):
        import inspect
        params = inspect.signature(p10.delivery_verdict_of).parameters
        self.assertEqual(set(params), {"events", "plan_admitted"})          # no policy, no threshold, no metric enters
        self.assertEqual(p10.delivery_verdict_of(E, plan_admitted=True), "PASS")
        failed = E[:6] + [{"seq": 6, "type": "story/rollback", "data": {"story_id": "S1"}}]
        self.assertEqual(p10.delivery_verdict_of(failed, plan_admitted=True), "FAIL")
        self.assertEqual(p10.delivery_verdict_of(E, plan_admitted=False), "NOT_REACHED")
        self.assertEqual(p10.delivery_verdict_of(E[:4], plan_admitted=True), "NOT_REACHED")   # no gate decision reached

    def test_P10_2_a_plan_quality_verdict_does_not_change_the_product_proof_or_the_delivery_verdict(self):
        metrics = p10.plan_quality_metrics(E, ROLES)
        strict = PlanQualityPolicy(0.0, 0, 0)
        self.assertEqual(p10.plan_quality_verdict_of(metrics, strict, policy_preregistered_at=1.0, run_started_at=2.0), "FAIL")
        self.assertEqual(p10.delivery_verdict_of(E, plan_admitted=True), "PASS")              # unchanged by the plan-quality FAIL
        proofs = [e for e in E if e["type"] in ("proof/verified", "probe/evaluated")]          # the verdict reads none of these back
        self.assertEqual(proofs, [])
        v = p10.RunVerdict("PASS", "FAIL")
        self.assertEqual((v.delivery_verdict, v.plan_quality_verdict), ("PASS", "FAIL"))      # RFC §29: representable, mandatory

    def test_P10_3_plan_drift_is_recorded_while_delivery_PASS_remains_PASS(self):
        metrics = p10.plan_quality_metrics(E, ROLES)
        self.assertEqual((metrics["unattributed_plan_drift"], metrics["pre_satisfied_introduce"], metrics["fully_pre_satisfied_stories"]), (1, 1, 1))
        self.assertEqual(p10.delivery_verdict_of(E, plan_admitted=True), "PASS")
        self.assertEqual(p10.RunVerdict("PASS", "NOT_CLAIMED").plan_quality_verdict, "NOT_CLAIMED")

    def test_P10_4_absence_of_preregistered_thresholds_is_NOT_CLAIMED_whatever_the_metrics(self):
        metrics = p10.plan_quality_metrics(E, ROLES)
        self.assertEqual(p10.plan_quality_verdict_of(metrics, NOT_PREREGISTERED, policy_preregistered_at=1.0, run_started_at=2.0), "NOT_CLAIMED")
        partial = PlanQualityPolicy(0.5, None, 3)
        self.assertEqual(p10.plan_quality_verdict_of(metrics, partial, policy_preregistered_at=1.0, run_started_at=2.0), "NOT_CLAIMED")
        perfect = p10.plan_quality_metrics(E[:4], ROLES)                     # excellent-looking metrics still claim nothing
        self.assertEqual(p10.plan_quality_verdict_of(perfect, NOT_PREREGISTERED, policy_preregistered_at=None, run_started_at=2.0), "NOT_CLAIMED")

    def test_P10_5_a_post_hoc_threshold_cannot_turn_NOT_CLAIMED_into_PASS_or_FAIL_for_the_same_run(self):
        metrics = p10.plan_quality_metrics(E, ROLES)
        lenient = PlanQualityPolicy(1.0, 10, 10)
        self.assertEqual(p10.plan_quality_verdict_of(metrics, lenient, policy_preregistered_at=None, run_started_at=2.0), "NOT_CLAIMED")
        self.assertEqual(p10.plan_quality_verdict_of(metrics, lenient, policy_preregistered_at=2.0, run_started_at=2.0), "NOT_CLAIMED")
        self.assertEqual(p10.plan_quality_verdict_of(metrics, lenient, policy_preregistered_at=3.0, run_started_at=2.0), "NOT_CLAIMED")
        self.assertEqual(p10.plan_quality_verdict_of(metrics, lenient, policy_preregistered_at=1.0, run_started_at=2.0), "PASS")


class SealedCohortRejection(unittest.TestCase):
    def test_P10_6_LedgerLock_to_SEALED_is_rejected(self):
        with self.assertRaises(p10.SealingRefused):
            p10.LEDGERLOCK.seal()
        with self.assertRaises(p10.SealingRefused):
            p10.LEDGERLOCK.transition(p10.CohortState.SEALED)
        self.assertIs(p10.LEDGERLOCK.transition("DEVELOPMENT"), p10.LEDGERLOCK)

    def test_P10_7_LedgerLock_to_HOLDOUT_is_rejected(self):
        with self.assertRaises(p10.SealingRefused):
            p10.LEDGERLOCK.transition("HOLDOUT")
        with self.assertRaises(p10.SealingRefused):
            p10.LEDGERLOCK.transition("EVALUATING")
        # a development workload of any name is terminal; a sealed workload moves forward only
        other = p10.Workload("W-sealed", "SEALED_HOLDOUT", p10.CohortState.SEALED)
        self.assertEqual(other.transition("EVALUATING").state, p10.CohortState.EVALUATING)
        with self.assertRaises(p10.SealingRefused):
            other.transition("EXPOSED")

    def test_P10_8_LedgerLock_cannot_support_a_generalization_claim_other_than_NONE(self):
        v = p10.RunVerdict("NOT_REACHED", "NOT_CLAIMED")
        ok = p10.Recorder().record(benchmark_class=p10.BENCHMARK_CLASS, generalization_claim="NONE", cohort_state="DEVELOPMENT", verdict=v)
        self.assertEqual(ok["generalization_claim"], "NONE")
        for claim in ("POSITIVE", "PARTIAL", "", None, True):
            with self.assertRaises(p10.ClaimRefused):
                p10.Recorder().record(benchmark_class=p10.BENCHMARK_CLASS, generalization_claim=claim, cohort_state="DEVELOPMENT", verdict=v)
        with self.assertRaises(p10.ClaimRefused):
            p10.Recorder().record(benchmark_class="SEALED_HOLDOUT", generalization_claim="NONE", cohort_state="DEVELOPMENT", verdict=v)
        with self.assertRaises(p10.ClaimRefused):
            p10.Recorder().record(benchmark_class=p10.BENCHMARK_CLASS, generalization_claim="NONE", cohort_state="SEALED", verdict=v)

    def test_P10_9_a_recorder_cannot_emit_sample_size_or_a_single_score(self):
        v = p10.RunVerdict("PASS", "NOT_CLAIMED")
        for key in ("qualification_sample_size", "generalization_sample_size", "sample_size", "sealed", "holdout", "overall_verdict", "score"):
            with self.assertRaises(p10.ClaimRefused):
                p10.Recorder().record(benchmark_class=p10.BENCHMARK_CLASS, generalization_claim="NONE", cohort_state="DEVELOPMENT", verdict=v, **{key: 1})
        with self.assertRaises(p10.ClaimRefused):
            p10.overall_verdict(v)
        self.assertEqual(p10.RunVerdict.__slots__, ("delivery_verdict", "plan_quality_verdict"))     # no third field can exist
        with self.assertRaises(AttributeError):
            object.__setattr__(v, "overall", "PASS")
        with self.assertRaises(p10.ClaimRefused):
            p10.RunVerdict("PASS", "PASS-ISH")
        with self.assertRaises(p10.ClaimRefused):
            p10.Recorder().record(benchmark_class=p10.BENCHMARK_CLASS, generalization_claim="NONE", cohort_state="DEVELOPMENT", verdict={"delivery_verdict": "PASS"})


class WorkloadFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = p10.build_workload(p10.LEDGERLOCK_PLAN_COMMIT)

    def test_the_77_frozen_criteria_are_all_present_with_their_v1_modes_and_roles(self):
        rows = p10.v1_rows()
        self.assertEqual(len(rows), 77)
        self.assertEqual(sorted(p10.V2), sorted(r["ac_id"] for r in rows))
        self.assertEqual(self.w["plan"]["v1_modes"], {"CHANGE_REQUIRED": 66, "PRESERVE_REQUIRED": 7, "NEGATIVE_INVARIANT": 4})
        self.assertEqual(self.w["plan"]["obligations_by_role"], {"INTRODUCE": 66, "PRESERVE": 11, "VERIFY": 0})
        self.assertEqual(self.w["plan"]["stories"], 16)

    def test_every_criterion_has_one_typed_answer_from_the_kernel(self):
        statuses = {e["v2_status"] for e in self.w["criteria"]}
        self.assertEqual(statuses, {"COMPILED", "REFUSED_BY_COMPILER", "UNSUPPORTED_OBSERVATION", "REFUSED_BY_CONTRACT_RULE"})
        for e in self.w["criteria"]:
            if e["v2_status"] != "COMPILED":
                self.assertTrue(e["typed_refusal"], e["ac_id"])
        self.assertEqual(sum(self.w["counts_by_v2_status"].values()), 77)
        self.assertEqual(len(self.w["expressible_by_cycle1_probe"]), 10)

    def test_the_plan_is_not_admitted_and_the_engine_says_why(self):
        sa = self.w["static_admission"]
        self.assertFalse(sa["admitted"])
        failing = {c["name"] for c in sa["checks"] if not c["passed"]}
        self.assertEqual(failing, {"contract_spec_integrity", "plan_structure", "probe_calibration"})
        self.assertEqual(len(sa["checks"]), 9)


if __name__ == "__main__":
    unittest.main()
