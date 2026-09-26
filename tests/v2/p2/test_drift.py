"""WP-2.5 — PRE_SATISFIED and PLAN_DRIFT (RFC §14, §29). In-memory; the real-probe scenarios A and K are in
test_drift_scenarios.py. Kill set for `drift.py::attribute`, `continue_story`, `budget_problems` and `plan_quality`."""

import importlib.util
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction as CS, Enforcement, EventType, ObligationRole as Role,
    StoryAdmissionDisposition as D,
)
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.plan import drift as dr  # noqa: E402
from aisef2.plan import story_admission as sa  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation, PlanQualityPolicy  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, Observation, ObservationKind as K, RevisionRef  # noqa: E402

_t = importlib.util.spec_from_file_location("p2_story_world_for_drift",
                                            ROOT / "tests" / "v2" / "p2" / "test_story_admission.py")
w = importlib.util.module_from_spec(_t)
_t.loader.exec_module(w)

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
PARENT = RevisionRef("fedcba9876543210fedcba9876543210fedcba98", os.path.abspath("parent"))
ENV = ExecutionEnv(sys.executable, 5, Enforcement.PARTIAL)
A, B, C = w.spec("a"), w.spec("b"), w.spec("c")
SPECS = {s.id: s for s in (A, B, C)}


def ob(cid, s, story, role, deps=()):
    return PlanObligation(cid, s.id, story, role, EXPECTED_AT_PARENT[role], tuple(deps), "why")


# S1 -> S2 -> S3 ; S0 is unrelated to S3
PLAN = Plan.create(id="PLAN", baseline=PARENT.sha, plan_quality_policy=NOT_PREREGISTERED, obligations=(
    ob("C0", C, "S0", Role.INTRODUCE),
    ob("C1", A, "S1", Role.INTRODUCE),
    ob("C2", B, "S2", Role.INTRODUCE, deps=("C1",)),
    ob("C3", A, "S3", Role.PRESERVE, deps=("C2",)),
    ob("C4", C, "S3", Role.VERIFY, deps=("C2",)),
    ob("C5", B, "S3", Role.VERIFY, deps=("C2",)),
))


def admitted(story, seen, sink=None):
    return sa.admit_story(PLAN, story, PARENT, specs=SPECS, probes={"probe.fake": w.Fake(seen)}, env=ENV,
                          committed_stories=frozenset(), sink=sink or sa.MemorySink())


def flip(story):
    return dr.CompletedStory(story, CS.UNSATISFIED, CS.SATISFIED)


class Attribution(unittest.TestCase):
    def test_attributed_to_the_upstream_story_that_flipped_the_spec(self):
        self.assertEqual(dr.attribute(PLAN, "S3", B.id, [flip("S2")]), ("S2", ("S2",)))
        self.assertEqual(dr.attribute(PLAN, "S3", B.id, [flip("S1")]), ("S1", ("S1",)))  # transitive upstream

    def test_unattributed_when_none_can_be_identified(self):
        cases = {
            "nothing completed": [],
            "a story that is not upstream": [flip("S0")],
            "upstream, but not measured at its parent": [dr.CompletedStory("S2", None, CS.SATISFIED)],
            "upstream, already satisfied before it": [dr.CompletedStory("S2", CS.SATISFIED, CS.SATISFIED)],
            "upstream, not satisfied after it": [dr.CompletedStory("S2", CS.UNSATISFIED, CS.UNSATISFIED)],
            "upstream, merge not measured": [dr.CompletedStory("S2", CS.UNSATISFIED, None)],
            "upstream, merge indeterminate": [dr.CompletedStory("S2", CS.UNSATISFIED, CS.INDETERMINATE)],
        }
        for name, completed in cases.items():
            with self.subTest(case=name):
                self.assertEqual(dr.attribute(PLAN, "S3", B.id, completed), (dr.UNATTRIBUTED, ()))
        self.assertEqual(dr.attribute(PLAN, "S3", B.id, [dr.CompletedStory("S2", CS.INDETERMINATE, CS.SATISFIED)]),
                         ("S2", ("S2",)))

    def test_a_tie_is_never_resolved_by_blaming_one_story(self):
        self.assertEqual(dr.attribute(PLAN, "S3", B.id, [flip("S2"), flip("S1")]), (dr.UNATTRIBUTED, ("S1", "S2")))


class Continuation(unittest.TestCase):
    def test_a_story_with_nothing_pre_satisfied_continues_on_everything(self):
        sink = sa.MemorySink()
        adm = admitted("S3", {A.id: Observation(K.OBSERVED, S), C.id: Observation(K.OBSERVED, R),
                              B.id: Observation(K.OBSERVED, S)}, sink)
        self.assertEqual([o.decision.disposition for o in adm.obligations], [D.READY, D.READY, D.READY])
        adm2 = admitted("S2", {B.id: Observation(K.OBSERVED, S)}, sink)
        self.assertEqual([o.decision.disposition for o in adm2.obligations], [D.PRE_SATISFIED])
        cont = dr.continue_story(PLAN, adm, {}, sink)
        self.assertEqual((cont.already_satisfied, cont.developer_work, cont.verify_at_candidate, cont.drift),
                         (False, ("C3", "C4", "C5"), ("C3", "C4", "C5"), ()))

    def test_pre_satisfied_is_recorded_attributed_and_never_developer_work(self):
        plan = Plan.create(id="PLAN", baseline=PARENT.sha, plan_quality_policy=NOT_PREREGISTERED, obligations=(
            ob("C1", A, "S1", Role.INTRODUCE), ob("C2", B, "S2", Role.INTRODUCE, deps=("C1",)),
            ob("C6", C, "S2", Role.INTRODUCE, deps=("C1",))))
        sink = sa.MemorySink()
        adm = sa.admit_story(plan, "S2", PARENT, specs=SPECS, env=ENV, committed_stories=frozenset({"S1"}), sink=sink,
                             probes={"probe.fake": w.Fake({B.id: Observation(K.OBSERVED, S),
                                                           C.id: Observation(K.SUBJECT_ABSENT, R)})})
        cont = dr.continue_story(plan, adm, {B.id: [flip("S1")]}, sink)
        self.assertEqual((cont.already_satisfied, cont.developer_work, cont.verify_at_candidate),
                         (False, ("C6",), ("C2", "C6")))
        self.assertEqual(cont.drift, (dr.PlanDrift("S2", "C2", B.id, "S1", ("S1",)),))
        self.assertEqual(sink.events[-1], (EventType.STORY_PLAN_DRIFT, {"story_id": "S2", "criterion_id": "C2",
                                                                        "spec_id": B.id, "attributed_to": "S1",
                                                                        "candidates": ["S1"]}))
        sa.request_developer(sink, "S2", {"criteria": list(cont.developer_work)})
        self.assertEqual(dr.budget_problems(sink.events), [])
        charged = [e for e in sink.events if e[0] is EventType.PROVIDER_REQUEST][0][1]["criteria"]
        self.assertNotIn("C2", charged)

    def test_a_fully_pre_satisfied_story_skips_the_developer_and_still_verifies_everything(self):
        sink = sa.MemorySink()
        adm = admitted("S2", {B.id: Observation(K.OBSERVED, S)}, sink)
        self.assertEqual((adm.admitted, adm.developer_call_permitted), (True, False))
        cont = dr.continue_story(PLAN, adm, {}, sink)
        self.assertEqual((cont.already_satisfied, cont.developer_work, cont.verify_at_candidate),
                         (True, (), ("C2",)))
        self.assertEqual(cont.drift[0].attributed_to, dr.UNATTRIBUTED)
        with self.assertRaises(InvariantError):
            sa.request_developer(sink, "S2", {"criteria": ["C2"]})
        self.assertEqual([t for t, _ in sink.events if t is EventType.PROVIDER_REQUEST], [])

    def test_a_blocked_story_does_not_continue(self):
        adm = admitted("S3", {A.id: Observation(K.OBSERVED, R), C.id: Observation(K.OBSERVED, S),
                              B.id: Observation(K.OBSERVED, S)})
        self.assertFalse(adm.admitted)
        with self.assertRaisesRegex(InvariantError, "^story S3 was not admitted; it does not continue$"):
            dr.continue_story(PLAN, adm, {}, sa.MemorySink())


class Budget(unittest.TestCase):
    def test_a_developer_request_may_charge_only_ready_criteria(self):
        admitted_event = (EventType.STORY_ADMITTED, {"story_id": "S2", "developer_call_permitted": True,
                                                     "dispositions": {"C2": "PRE_SATISFIED", "C6": "READY"}})
        self.assertEqual(dr.budget_problems([admitted_event, (EventType.PROVIDER_REQUEST,
                                                              {"story_id": "S2", "criteria": ["C6"]})]), [])
        self.assertEqual(dr.budget_problems([admitted_event, (EventType.PROVIDER_REQUEST,
                                                              {"story_id": "S2", "criteria": ["C6", "C2"]})]),
                         ["event 1: provider/request charges C2, which is PRE_SATISFIED"])
        self.assertEqual(dr.budget_problems([(EventType.PROVIDER_REQUEST, {"story_id": "S9", "criteria": ["C1"]})]),
                         ["event 0: provider/request charges C1, which is not admitted"])
        self.assertEqual(dr.budget_problems([admitted_event, (EventType.PROVIDER_REQUEST, {"story_id": "S2"})]), [])


class Quality(unittest.TestCase):
    def setUp(self):
        self.s2 = admitted("S2", {B.id: Observation(K.OBSERVED, S)})                        # 1 INTRODUCE, pre-satisfied
        self.s1 = admitted("S1", {A.id: Observation(K.OBSERVED, R)})                        # 1 INTRODUCE, ready
        self.drift = (dr.PlanDrift("S2", "C2", B.id, dr.UNATTRIBUTED, ()),)

    def q(self, policy):
        return dr.plan_quality(policy, (self.s1, self.s2), PLAN, self.drift)

    def test_the_three_metrics(self):
        got = self.q(NOT_PREREGISTERED)
        self.assertEqual((got.pre_satisfied_introduce_ratio, got.fully_pre_satisfied_stories,
                          got.unattributed_plan_drift), (0.5, 1, 1))

    def test_only_stories_whose_every_obligation_is_pre_satisfied_count_as_full(self):
        got = dr.plan_quality(NOT_PREREGISTERED, (self.s1, self.s2, self.s1), PLAN, ())
        self.assertEqual((got.fully_pre_satisfied_stories, got.pre_satisfied_introduce_ratio), (1, 1 / 3))

    def test_no_preregistered_threshold_means_not_claimed(self):
        self.assertEqual(self.q(NOT_PREREGISTERED).verdict, "NOT_CLAIMED")

    def test_each_preregistered_threshold_is_applied(self):
        self.assertEqual(self.q(PlanQualityPolicy(0.5, None, None)).verdict, "PASS")
        self.assertEqual(self.q(PlanQualityPolicy(0.4, None, None)).verdict, "FAIL")
        self.assertEqual(self.q(PlanQualityPolicy(None, 1, None)).verdict, "PASS")
        self.assertEqual(self.q(PlanQualityPolicy(None, 0, None)).verdict, "FAIL")
        self.assertEqual(self.q(PlanQualityPolicy(None, None, 1)).verdict, "PASS")
        self.assertEqual(self.q(PlanQualityPolicy(None, None, 0)).verdict, "FAIL")
        self.assertEqual(self.q(PlanQualityPolicy(1.0, 5, 0)).verdict, "FAIL")

    def test_no_introduce_obligation_has_no_ratio(self):
        s3 = admitted("S3", {A.id: Observation(K.OBSERVED, S), C.id: Observation(K.OBSERVED, S),
                             B.id: Observation(K.OBSERVED, S)})
        got = dr.plan_quality(PlanQualityPolicy(0.0, None, None), (s3,), PLAN, ())
        self.assertEqual((got.pre_satisfied_introduce_ratio, got.fully_pre_satisfied_stories, got.verdict),
                         (None, 0, "PASS"))


if __name__ == "__main__":
    unittest.main()
