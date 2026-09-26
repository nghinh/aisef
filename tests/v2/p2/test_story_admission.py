"""WP-2.4 — StoryAdmission and its disposition set (RFC §13; F7). In-memory probes; no subprocess.

Kill set for `story_admission.py::classify` (and `admit_story`, `ordering_problems`). Every §13 row is reproduced on the
derived ContractSatisfaction; the real-probe cases are in test_story_admission_probes.py.
"""

import itertools
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, EventType, MeasurementPoint, ObligationRole as Role, Owner,
    ParentExpectation as PE, StoryAdmissionDisposition as D, SubjectAbsence,
)
from aisef2.control import routing  # noqa: E402
from aisef2.control.owner import FailureCode, Retryability  # noqa: E402
from aisef2.control.routing import UnroutableOutcome  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.plan import story_admission as sa  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, HarnessProbe, Observation, ObservationKind as K, ProbeRecord, RevisionRef,
)
from aisef2.product.outcome import Executed, IndeterminateReason, InvalidSpec, Unrunnable  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
PARENT = RevisionRef("fedcba9876543210fedcba9876543210fedcba98", os.path.abspath("parent"))
ENV = ExecutionEnv(sys.executable, 5, Enforcement.PARTIAL)


def spec(name, expectation=S, absence=SubjectAbsence.REQUIRES_SUBJECT):
    return ProductProofSpec.create(contract_id=f"BC-{name}", probe_id="probe.fake", probe_digest="f" * 64,
                                   probe_input={"subject": {"kind": "python_callable", "locator": f"app.{name}:f"},
                                                "stimulus": {}, "observable": {"condition": "exists"},
                                                "subject_absence": absence.value},
                                   candidate_expectation=expectation, compiler_id="t", compiler_digest="c" * 64)


def ob(cid, s, story, role, expected=None, deps=()):
    return PlanObligation(cid, s.id, story, role, expected or EXPECTED_AT_PARENT[role], tuple(deps), "why")


class Fake(HarnessProbe):
    """Reports, per spec id, a fixed observation."""
    id, digest = "probe.fake", "f" * 64

    def __init__(self, seen):
        self.seen = seen

    def enforcement(self):
        return Enforcement.PARTIAL

    def harness_preconditions(self):
        return ("none",)

    def observe(self, spec, at, env):
        return self.seen[spec.id]


def record(s, result, *, revision=PARENT.sha, enforcement=Enforcement.PARTIAL):
    return ProbeRecord.create(spec_id=s.id, semantic_hash=s.semantic_hash, probe_id=s.probe_id,
                              probe_digest=s.probe_digest, revision=revision, enforcement=enforcement, result=result)


def decide(role, result, expectation=S, expected=None, committed=False):
    s = spec("x", expectation)
    return sa.classify(ob("C", s, "S1", role, expected), record(s, result), s, revision=PARENT.sha,
                       enforcement=Enforcement.PARTIAL, introducer_committed=committed)


class Table(unittest.TestCase):
    def test_each_rfc_row_on_the_derived_satisfaction(self):
        rows = [  # (role, candidate expectation, result, disposition, owner)
            (Role.INTRODUCE, S, Executed(R), D.READY, None),
            (Role.INTRODUCE, S, Executed(S), D.PRE_SATISFIED, None),
            (Role.PRESERVE, S, Executed(S), D.READY, None),
            (Role.PRESERVE, S, Executed(R), D.PRECONDITION_BROKEN, Owner.PLAN),
            (Role.VERIFY, S, Executed(S), D.READY, None),
            (Role.VERIFY, S, Executed(R), D.READY, None),
            (Role.INTRODUCE, S, Executed(I, PA), D.READY, None),
            (Role.PRESERVE, S, Executed(I, PA), D.PRECONDITION_BROKEN, Owner.PLAN),
            (Role.VERIFY, S, Executed(I, PA), D.PRECONDITION_BROKEN, Owner.PLAN),
        ]
        for role, exp, result, want, owner in rows:
            with self.subTest(role=role, result=result):
                d = decide(role, result, exp)
                self.assertIs(d.disposition, want)
                self.assertEqual(d.failure.owner if d.failure else None, owner)
                self.assertRegex(d.rule, "§1[03]")
        self.assertEqual(decide(Role.PRESERVE, Executed(R)).rule,
                         "§13: PRESERVE expecting SATISFIED_AT_PARENT, measured UNSATISFIED")
        self.assertIs(decide(Role.PRESERVE, Executed(R)).failure.code, FailureCode.PRECONDITION_BROKEN)
        self.assertEqual(decide(Role.INTRODUCE, Executed(I, PA)).rule,
                         routing._EXECUTED[(MeasurementPoint.PARENT, ContractSatisfaction.INDETERMINATE, PA,
                                            Role.INTRODUCE)][3])

    def test_the_raw_verdict_is_never_the_key(self):
        # NEG-1: MUST_NOT_HOLD (expectation REFUTED), forbidden behaviour present: raw SATISFIED -> UNSATISFIED -> READY
        d = decide(Role.INTRODUCE, Executed(S), expectation=R)
        self.assertEqual((d.disposition, d.satisfaction), (D.READY, ContractSatisfaction.UNSATISFIED))
        # NEG-2: forbidden behaviour absent, decidable: raw REFUTED -> SATISFIED -> PRE_SATISFIED, no budget charged
        d = decide(Role.INTRODUCE, Executed(R), expectation=R)
        self.assertEqual((d.disposition, d.satisfaction, d.failure), (D.PRE_SATISFIED, ContractSatisfaction.SATISFIED,
                                                                       None))
        # the same raw verdict, opposite dispositions, by expectation
        self.assertIsNot(decide(Role.PRESERVE, Executed(R), S).disposition, decide(Role.PRESERVE, Executed(R), R).disposition)

    def test_NEG_3_absent_required_subject_by_role(self):
        self.assertIs(decide(Role.INTRODUCE, Executed(I, PA), expectation=R).disposition, D.READY)
        for role in (Role.PRESERVE, Role.VERIFY):
            with self.subTest(role=role):
                d = decide(role, Executed(I, PA), expectation=R)
                self.assertEqual((d.disposition, d.failure.code), (D.PRECONDITION_BROKEN, FailureCode.PRECONDITION_BROKEN))

    def test_probe_status_rows(self):
        self.assertEqual(decide(Role.INTRODUCE, Unrunnable("x")).rule,
                         "§13: probe UNRUNNABLE -> PROBE_UNRUNNABLE, owner ENVIRONMENT")
        self.assertEqual(decide(Role.INTRODUCE, InvalidSpec("x")).rule, "§13: probe INVALID_SPEC -> PROBE_INVALID")
        d = decide(Role.INTRODUCE, Unrunnable("interpreter absent"))
        self.assertEqual((d.disposition, d.failure.code, d.failure.owner, d.satisfaction),
                         (D.PROBE_UNRUNNABLE, FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT, None))
        self.assertIs(d.failure.retryability, Retryability.RETRYABLE)
        d = decide(Role.PRESERVE, InvalidSpec("not evaluable"))
        self.assertEqual((d.disposition, d.failure.code, d.failure.owner), (D.PROBE_INVALID, FailureCode.PROBE_INVALID_SPEC,
                                                                            Owner.INTEGRATION))
        for role in Role:
            with self.subTest(role=role):
                self.assertIs(decide(role, Unrunnable("x")).disposition, D.PROBE_UNRUNNABLE)
                self.assertIsNot(decide(role, Unrunnable("x")).failure.owner, Owner.DEVELOPER)

    def test_a_preserve_that_contradicts_the_plans_own_record_is_PLAN_CONTRADICTION(self):
        d = decide(Role.PRESERVE, Executed(R), committed=True)
        self.assertEqual((d.disposition, d.failure.code, d.satisfaction),
                         (D.PLAN_CONTRADICTION, FailureCode.PLAN_CONTRADICTION, ContractSatisfaction.UNSATISFIED))
        self.assertEqual(d.rule, "§13: a PRESERVE measured UNSATISFIED whose introducing story already committed")
        for role, result in ((Role.PRESERVE, Executed(S)), (Role.INTRODUCE, Executed(R)), (Role.VERIFY, Executed(R))):
            with self.subTest(role=role):
                self.assertIsNot(decide(role, result, committed=True).disposition, D.PLAN_CONTRADICTION)

    def test_PLAN_OWNER_1_a_plan_contradiction_always_carries_PLAN(self):
        for expectation in (S, R):
            with self.subTest(expectation=expectation):
                d = decide(Role.PRESERVE, Executed(R if expectation is S else S), expectation, committed=True)
                self.assertEqual((d.disposition, d.failure.owner), (D.PLAN_CONTRADICTION, Owner.PLAN))

    def test_PLAN_OWNER_2_a_plan_contradiction_consumes_no_retry_budget(self):
        failure = decide(Role.PRESERVE, Executed(R), committed=True).failure
        self.assertIs(failure.retryability, Retryability.NOT_RETRYABLE)
        self.assertIsNone(failure.budget)  # owner PLAN; no DEVELOPER, ENVIRONMENT or PROVIDER budget is charged
        self.assertNotIn(failure.budget, (Owner.DEVELOPER, Owner.ENVIRONMENT, Owner.PROVIDER))

    def test_PROBE_BIND_1_a_bare_result_is_never_classified(self):
        s = spec("x")
        with self.assertRaisesRegex(InvariantError, "^a decision reads a ProbeRecord, never a bare ProbeResult$"):
            sa.classify(ob("C", s, "S1", Role.INTRODUCE), Executed(R), s, revision=PARENT.sha,
                        enforcement=Enforcement.PARTIAL, introducer_committed=False)
        other = spec("y")
        for rec, msg in ((record(other, Executed(R)), f"answers {other.id}, not {s.id}"),
                         (record(s, Executed(R), revision="0" * 40), "measured at 000000000000")):
            with self.subTest(msg=msg), self.assertRaisesRegex(InvariantError, msg):
                sa.classify(ob("C", s, "S1", Role.INTRODUCE), rec, s, revision=PARENT.sha,
                            enforcement=Enforcement.PARTIAL, introducer_committed=False)

    def test_PROBE_BIND_2_a_record_under_other_enforcement_is_not_reused(self):
        s = spec("x")
        partial = record(s, Executed(R))
        with self.assertRaisesRegex(InvariantError, "ran under PARTIAL, not FULL: not comparable"):
            sa.classify(ob("C", s, "S1", Role.INTRODUCE), partial, s, revision=PARENT.sha,
                        enforcement=Enforcement.FULL, introducer_committed=False)
        self.assertNotEqual(partial.comparability, record(s, Executed(R), enforcement=Enforcement.FULL).comparability)

    def test_an_indeterminate_with_no_declared_routing_is_PROBE_INVALID_never_developer(self):
        key = (MeasurementPoint.PARENT, ContractSatisfaction.INDETERMINATE, PA, Role.INTRODUCE)
        rows = {k: v for k, v in routing._EXECUTED.items() if k != key}
        with mock.patch.dict(routing._EXECUTED, rows, clear=True):
            d = decide(Role.INTRODUCE, Executed(I, PA))
        self.assertEqual((d.disposition, d.failure.code, d.satisfaction),
                         (D.PROBE_INVALID, FailureCode.PROBE_INVALID_SPEC, ContractSatisfaction.INDETERMINATE))
        self.assertIsNot(d.failure.owner, Owner.DEVELOPER)
        self.assertIn("no declared routing", d.rule)

    def test_the_table_is_total_over_admissible_obligations_and_closed_elsewhere(self):
        results = [Executed(S), Executed(R), Executed(I, PA), Unrunnable("x"), InvalidSpec("y")]
        for role, expectation, result in itertools.product(Role, (S, R), results):
            with self.subTest(role=role, expectation=expectation, result=result):
                self.assertIn(decide(role, result, expectation).disposition, set(D))
        for role, expected in itertools.product(Role, PE):
            if EXPECTED_AT_PARENT[role] is expected:
                continue
            msg = f"^§13 has no row for {role.value} expecting {expected.value} measured SATISFIED$"
            with self.subTest(role=role, expected=expected), self.assertRaisesRegex(UnroutableOutcome, msg):
                decide(role, Executed(S), expected=expected)
        self.assertEqual(set(sa.TABLE.values()) | {D.PROBE_UNRUNNABLE, D.PROBE_INVALID, D.PLAN_CONTRADICTION}, set(D))


class Story(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = spec("a"), spec("b"), spec("c", R)
        self.specs = {s.id: s for s in (self.a, self.b, self.c)}
        self.sink = sa.MemorySink()

    def admit(self, obligations, seen, story="S2", committed=frozenset(), probes=None):
        plan = Plan.create(id="PLAN", baseline=PARENT.sha, obligations=tuple(obligations),
                           plan_quality_policy=NOT_PREREGISTERED)
        return sa.admit_story(plan, story, PARENT, specs=self.specs,
                              probes=probes if probes is not None else {"probe.fake": Fake(seen)}, env=ENV,
                              committed_stories=committed, sink=self.sink)

    def test_ready_and_pre_satisfied_with_remaining_work_permit_the_developer_call(self):
        r = self.admit([ob("C1", self.a, "S2", Role.INTRODUCE), ob("C2", self.b, "S2", Role.INTRODUCE)],
                       {self.a.id: Observation(K.OBSERVED, S), self.b.id: Observation(K.SUBJECT_ABSENT, R)})
        self.assertEqual([x.decision.disposition for x in r.obligations], [D.PRE_SATISFIED, D.READY])
        self.assertEqual((r.admitted, r.developer_call_permitted, r.parent_sha), (True, True, PARENT.sha))
        self.assertEqual([x.record.enforcement for x in r.obligations], [Enforcement.PARTIAL] * 2)

    def test_all_pre_satisfied_is_admitted_without_a_developer_call(self):
        r = self.admit([ob("C1", self.a, "S2", Role.INTRODUCE)], {self.a.id: Observation(K.OBSERVED, S)})
        self.assertEqual((r.admitted, r.developer_call_permitted), (True, False))

    def test_any_blocker_blocks_the_story(self):
        for blocker in (Observation(K.HARNESS_FAILED, detail="no interpreter"), Observation(K.UNSUPPORTED, detail="?")):
            with self.subTest(blocker=blocker.kind):
                r = self.admit([ob("C1", self.a, "S2", Role.INTRODUCE), ob("C2", self.b, "S2", Role.VERIFY)],
                               {self.a.id: Observation(K.OBSERVED, R), self.b.id: blocker})
                self.assertEqual((r.admitted, r.developer_call_permitted), (False, False))
        r = self.admit([ob("C1", self.a, "S1", Role.INTRODUCE), ob("C3", self.a, "S2", Role.PRESERVE, deps=("C1",))],
                       {self.a.id: Observation(K.OBSERVED, R)}, committed=frozenset({"S1"}))
        self.assertEqual([x.decision.disposition for x in r.obligations], [D.PLAN_CONTRADICTION])
        self.assertFalse(r.admitted)

    def test_a_plan_contradiction_permits_no_developer_call(self):
        r = self.admit([ob("C1", self.a, "S1", Role.INTRODUCE), ob("C3", self.a, "S2", Role.PRESERVE, deps=("C1",)),
                        ob("C4", self.b, "S2", Role.INTRODUCE)],
                       {self.a.id: Observation(K.OBSERVED, R), self.b.id: Observation(K.OBSERVED, R)},
                       committed=frozenset({"S1"}))
        self.assertEqual([x.decision.disposition for x in r.obligations], [D.PLAN_CONTRADICTION, D.READY])
        self.assertEqual((r.admitted, r.developer_call_permitted), (False, False))
        with self.assertRaisesRegex(InvariantError, "story/admitted has not permitted one"):
            sa.request_developer(self.sink, "S2")
        self.assertNotIn(EventType.PROVIDER_REQUEST, [t for t, _ in self.sink.events])

    def test_only_this_storys_obligations_run(self):
        seen = {self.a.id: Observation(K.OBSERVED, R), self.b.id: Observation(K.OBSERVED, S)}
        r = self.admit([ob("C1", self.a, "S1", Role.INTRODUCE), ob("C2", self.b, "S2", Role.INTRODUCE)], seen)
        self.assertEqual([x.criterion_id for x in r.obligations], ["C2"])
        with self.assertRaisesRegex(InvariantError, "story S9 has no obligation"):
            self.admit([ob("C1", self.a, "S1", Role.INTRODUCE)], seen, story="S9")

    def test_the_parent_is_a_full_sha_revision(self):
        plan = Plan.create(id="PLAN", baseline=PARENT.sha, obligations=(ob("C1", self.a, "S2", Role.INTRODUCE),),
                           plan_quality_policy=NOT_PREREGISTERED)
        with self.assertRaisesRegex(InvariantError, "full 40-hex SHA"):
            RevisionRef(PARENT.sha[:12], PARENT.root)
        with self.assertRaisesRegex(InvariantError, "exact frozen parent, by full SHA"):
            sa.admit_story(plan, "S2", PARENT.sha[:12], specs=self.specs, probes={}, env=ENV,
                           committed_stories=frozenset(), sink=self.sink)

    def test_a_probe_missing_from_the_catalogue_is_PROBE_INVALID(self):
        r = self.admit([ob("C1", self.a, "S2", Role.INTRODUCE)], {}, probes={})
        self.assertEqual((r.obligations[0].decision.disposition, r.obligations[0].record.enforcement),
                         (D.PROBE_INVALID, Enforcement.UNAVAILABLE))
        self.assertEqual(r.obligations[0].record.result, InvalidSpec("probe probe.fake is not in the harness catalogue"))
        self.assertIsInstance(r.obligations, tuple)


class Ordering(unittest.TestCase):
    def test_events_record_each_evaluation_then_the_admission(self):
        sink = sa.MemorySink()
        s = spec("a")
        plan = Plan.create(id="PLAN", baseline=PARENT.sha, obligations=(ob("C1", s, "S1", Role.INTRODUCE),),
                           plan_quality_policy=NOT_PREREGISTERED)
        sa.admit_story(plan, "S1", PARENT, specs={s.id: s}, probes={"probe.fake": Fake({s.id: Observation(K.OBSERVED, R)})},
                       env=ENV, committed_stories=frozenset(), sink=sink)
        self.assertEqual([t for t, _ in sink.events], [EventType.PROBE_EVALUATED, EventType.STORY_ADMITTED])
        self.assertEqual(sink.events[1][1], {"story_id": "S1", "parent": PARENT.sha, "admitted": True,
                                             "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
        from aisef2.product.contract import plain
        rec = sa.admit_story(plan, "S1", PARENT, specs={s.id: s},
                             probes={"probe.fake": Fake({s.id: Observation(K.OBSERVED, R)})}, env=ENV,
                             committed_stories=frozenset(), sink=sa.MemorySink()).obligations[0].record
        self.assertEqual(sink.events[0][1], {"story_id": "S1", "criterion_id": "C1", "record": plain(rec)})
        sa.request_developer(sink, "S1", {"model": "m"})
        self.assertEqual(sink.events[-1], (EventType.PROVIDER_REQUEST, {"story_id": "S1", "model": "m"}))
        self.assertEqual(sa.ordering_problems(sink.events), [])

    def test_no_provider_request_before_the_storys_admission(self):
        sink = sa.MemorySink()
        with self.assertRaisesRegex(InvariantError, "^no developer call for S1: story/admitted has not permitted one$"):
            sa.request_developer(sink, "S1")
        self.assertEqual(sink.events, ())
        early = [(EventType.PROVIDER_REQUEST, {"story_id": "S1"}),
                 (EventType.STORY_ADMITTED, {"story_id": "S1", "developer_call_permitted": True})]
        self.assertEqual(sa.ordering_problems(early),
                         ["event 0: provider/request for S1 before a story/admitted permitting it"])
        other = [(EventType.STORY_ADMITTED, {"story_id": "S0", "developer_call_permitted": True}),
                 (EventType.PROVIDER_REQUEST, {"story_id": "S1"})]
        self.assertEqual(len(sa.ordering_problems(other)), 1)

    def test_an_admission_that_does_not_permit_a_call_refuses_one(self):
        for permitted in (False, None):
            sink = sa.MemorySink()
            sink.emit(EventType.STORY_ADMITTED, {"story_id": "S1", "developer_call_permitted": permitted})
            with self.subTest(permitted=permitted), self.assertRaises(InvariantError):
                sa.request_developer(sink, "S1")
        with self.assertRaisesRegex(InvariantError, "typed EventType"):
            sa.MemorySink().emit("provider/request", {})


if __name__ == "__main__":
    unittest.main()
