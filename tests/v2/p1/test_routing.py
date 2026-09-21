"""WP-1.4 — Owner taxonomy and the owner routing table (RFC §22, §10, §10.3; F2 as amended by V2-001, F3).

Kill set for TAXONOMY, classify, flatten, the routing table and route: every owner and every retryability is pinned
here, and the §10/§10.3 constraints are proved over the whole legal space — every measurement point, every outcome,
every corpus spec, every obligation role. OWNER-MP-1..4 and CRED-1..4 are the owner's regression cases (P1 review).
"""

import importlib.util
import itertools
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, MeasurementPoint, ObligationRole, Owner, ProbeExecutionStatus,
    StoryAdmissionDisposition,
)
from aisef2.control import routing  # noqa: E402
from aisef2.control.owner import TAXONOMY, FailureCode, Retryability, classify, flatten  # noqa: E402
from aisef2.control.routing import STORY_ADMISSION, UnroutableOutcome, route  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.product.outcome import (  # noqa: E402
    Executed, IndeterminateReason, InvalidSpec, Unrunnable, contract_satisfaction, on_subject_absent,
)
from aisef2.product.spec import ProductProofSpec  # noqa: E402

SPECS = {p.stem: ProductProofSpec.from_json(json.loads(p.read_text(encoding="utf-8")))
         for p in sorted((ROOT / "tests/v2/fixtures/p1/corpus/specs").glob("*.json"))}
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
PARENT, CANDIDATE, POST_MERGE = MeasurementPoint.PARENT, MeasurementPoint.CANDIDATE, MeasurementPoint.POST_MERGE
RESULTS = [None, Unrunnable("harness"), InvalidSpec("spec"), Executed(S), Executed(R), Executed(I, PA)]
RT, NR, BP = Retryability.RETRYABLE, Retryability.NOT_RETRYABLE, Retryability.RESOLVED_BY_POLICY
EXPECTED = {  # code -> (owner, retryability): the taxonomy, pinned
    FailureCode.PROBE_UNRUNNABLE: (Owner.ENVIRONMENT, RT),
    FailureCode.PROBE_INVALID_SPEC: (Owner.INTEGRATION, NR),
    FailureCode.CONTRACT_UNSATISFIED: (Owner.DEVELOPER, RT),
    FailureCode.SUBJECT_ABSENT_AT_CANDIDATE: (Owner.DEVELOPER, RT),
    FailureCode.PRECONDITION_BROKEN: (Owner.PLAN, NR),
    FailureCode.POST_MERGE_REGRESSION: (Owner.INTEGRATION, NR),
    FailureCode.POST_MERGE_SUBJECT_LOST: (Owner.INTEGRATION, NR),
    FailureCode.MISSING_CREDENTIAL: (Owner.ENVIRONMENT, BP),
    FailureCode.INVALID_CREDENTIAL: (Owner.ENVIRONMENT, NR),
    FailureCode.PROVIDER_UNAVAILABLE: (Owner.PROVIDER, RT),
    FailureCode.UNKNOWN: (Owner.INTEGRATION, NR),
}
REQUIRES_SUBJECT = SPECS["BC-QUIET-STDOUT"]  # MUST_NOT_HOLD, REQUIRES_SUBJECT


def owner(r):
    return r.failure.owner if r.failure else None


def everything():
    for point, result, (cid, spec), role in itertools.product(MeasurementPoint, RESULTS, SPECS.items(), ObligationRole):
        yield point, result, cid, spec, role, route(result, spec, point, role)


class Taxonomy(unittest.TestCase):
    def test_owner_set_is_exactly_the_frozen_F3_set(self):
        self.assertEqual([o.value for o in Owner],
                         ["PLAN", "DEVELOPER", "ENVIRONMENT", "PROVIDER", "REVIEW", "SECURITY", "INTEGRATION"])

    def test_every_code_has_exactly_its_pinned_owner_and_retryability(self):
        self.assertEqual(set(TAXONOMY), set(FailureCode))
        for code, (own, retry) in EXPECTED.items():
            with self.subTest(code=code.value):
                c = classify(code)
                self.assertIs(c.code, code)
                self.assertEqual((c.owner, c.retryability), (own, retry))
                self.assertIs(c.budget, None if retry is NR else own)
                self.assertIn("§", c.rule)

    def test_no_retry_count_lives_in_the_taxonomy(self):
        for c in TAXONOMY.values():
            self.assertIsInstance(c.retryability, Retryability)
        self.assertNotIn("count", " ".join(f.lower() for f in type(next(iter(TAXONOMY.values()))).__slots__))

    def test_untyped_codes_fail_closed(self):
        for bad in ("UNKNOWN", None, 3, Owner.DEVELOPER):
            with self.subTest(code=bad), self.assertRaisesRegex(InvariantError, "is not a typed failure code"):
                classify(bad)
        with mock.patch.dict(TAXONOMY, clear=True), self.assertRaises(InvariantError):
            classify(FailureCode.UNKNOWN)

    def test_foreign_values_flatten_to_UNKNOWN_and_are_kept_as_data(self):
        err = ConnectionResetError("peer")
        self.assertEqual(flatten(err), (FailureCode.UNKNOWN, err))
        self.assertEqual(flatten("ECONNRESET"), (FailureCode.UNKNOWN, "ECONNRESET"))
        self.assertEqual(flatten(FailureCode.INVALID_CREDENTIAL), (FailureCode.INVALID_CREDENTIAL, None))
        self.assertIs(classify(flatten("anything")[0]).owner, Owner.INTEGRATION)


class Credentials(unittest.TestCase):
    """CRED-1..4 (owner decision, P1 review): credentials are execution configuration, not provider failure."""

    def test_CRED_1_missing_credential_never_consumes_developer_budget(self):
        c = classify(FailureCode.MISSING_CREDENTIAL)
        self.assertIs(c.owner, Owner.ENVIRONMENT)
        self.assertIsNot(c.budget, Owner.DEVELOPER)
        self.assertIs(c.retryability, Retryability.RESOLVED_BY_POLICY)

    def test_CRED_2_invalid_credential_never_consumes_developer_or_provider_budget(self):
        c = classify(FailureCode.INVALID_CREDENTIAL)
        self.assertIs(c.owner, Owner.ENVIRONMENT)
        self.assertNotIn(c.budget, (Owner.DEVELOPER, Owner.PROVIDER))

    def test_CRED_3_invalid_credential_is_non_retryable(self):
        c = classify(FailureCode.INVALID_CREDENTIAL)
        self.assertIs(c.retryability, Retryability.NOT_RETRYABLE)
        self.assertIsNone(c.budget)

    def test_CRED_4_provider_outage_is_distinct_from_invalid_credential(self):
        outage, invalid = classify(FailureCode.PROVIDER_UNAVAILABLE), classify(FailureCode.INVALID_CREDENTIAL)
        self.assertIsNot(outage.code, invalid.code)
        self.assertIs(outage.owner, Owner.PROVIDER)
        self.assertIsNot(invalid.owner, Owner.PROVIDER)
        self.assertEqual({c.code for c in TAXONOMY.values() if c.owner is Owner.PROVIDER},
                         {FailureCode.PROVIDER_UNAVAILABLE})


class OwnerByMeasurementPoint(unittest.TestCase):
    """OWNER-MP-1..4 (RFC §10.3, ARCHITECTURE-EXCEPTION-V2-001): a REQUIRES_SUBJECT contract, subject absent."""

    def setUp(self):
        self.absent = on_subject_absent(REQUIRES_SUBJECT, observed=None)
        self.assertEqual(self.absent, Executed(I, PA))

    def test_OWNER_MP_1_parent_INTRODUCE_is_READY_with_no_failure_owner(self):
        r = route(self.absent, REQUIRES_SUBJECT, PARENT, ObligationRole.INTRODUCE)
        self.assertIsNone(r.failure)
        self.assertIs(r.disposition, StoryAdmissionDisposition.READY)
        self.assertEqual(r.decided_by, STORY_ADMISSION)

    def test_OWNER_MP_2_candidate_after_admitted_INTRODUCE_is_DEVELOPER_never_PLAN(self):
        r = route(self.absent, REQUIRES_SUBJECT, CANDIDATE, ObligationRole.INTRODUCE)
        self.assertIs(r.failure.code, FailureCode.SUBJECT_ABSENT_AT_CANDIDATE)
        self.assertIs(owner(r), Owner.DEVELOPER)
        for role in ObligationRole:
            self.assertIs(owner(route(self.absent, REQUIRES_SUBJECT, CANDIDATE, role)), Owner.DEVELOPER)

    def test_OWNER_MP_3_post_merge_disappearance_is_INTEGRATION(self):
        r = route(self.absent, REQUIRES_SUBJECT, POST_MERGE, ObligationRole.INTRODUCE)
        self.assertIs(r.failure.code, FailureCode.POST_MERGE_SUBJECT_LOST)
        self.assertIs(owner(r), Owner.INTEGRATION)

    def test_OWNER_MP_4_harness_cannot_inspect_is_ENVIRONMENT_everywhere(self):
        for point, role in itertools.product(MeasurementPoint, ObligationRole):
            with self.subTest(point=point, role=role):
                self.assertIs(owner(route(Unrunnable("sandbox missing"), REQUIRES_SUBJECT, point, role)),
                              Owner.ENVIRONMENT)

    def test_parent_PRESERVE_or_VERIFY_over_an_absent_subject_is_PRECONDITION_BROKEN_PLAN(self):
        for role in (ObligationRole.PRESERVE, ObligationRole.VERIFY):
            with self.subTest(role=role):
                r = route(self.absent, REQUIRES_SUBJECT, PARENT, role)
                self.assertIs(r.failure.code, FailureCode.PRECONDITION_BROKEN)
                self.assertIs(owner(r), Owner.PLAN)
                self.assertIs(r.disposition, StoryAdmissionDisposition.PRECONDITION_BROKEN)

    def test_the_reason_alone_never_decides_the_owner(self):
        owners = {owner(route(self.absent, REQUIRES_SUBJECT, p, r)) for p, r in itertools.product(MeasurementPoint,
                                                                                                  ObligationRole)}
        self.assertEqual(owners, {None, Owner.PLAN, Owner.DEVELOPER, Owner.INTEGRATION})

    def test_a_parent_PRECONDITION_ABSENT_without_a_role_fails_closed(self):
        with self.assertRaisesRegex(UnroutableOutcome, "^no routing row for PARENT INDETERMINATE"):
            route(self.absent, REQUIRES_SUBJECT, PARENT)


class RoutingTable(unittest.TestCase):
    def test_total_over_the_legal_space(self):
        rows = list(everything())
        self.assertEqual(len(rows), len(MeasurementPoint) * len(RESULTS) * len(SPECS) * len(ObligationRole))

    def test_every_route_cites_its_rfc_basis(self):
        for point, result, cid, _s, role, r in everything():
            with self.subTest(point=point, spec=cid, result=result, role=role):
                self.assertRegex(r.rule, r"^§1[03](\.3)?[:,]? .{8,}|^§10\.3 \(V2-001\): .{8,}")
        rules = {route(res, SPECS["BC-VERSION"], p, ObligationRole.PRESERVE).rule
                 for p in MeasurementPoint for res in RESULTS}
        self.assertEqual(len(rules), 11)  # parent SATISFIED/UNSATISFIED share the StoryAdmission row

    def test_the_rows(self):
        must_hold, must_not = SPECS["BC-VERSION"], SPECS["BC-QUIET-STDOUT"]
        for point in MeasurementPoint:
            self.assertEqual(route(None, must_hold, point), routing.Route(None, None, None, route(None, must_hold,
                                                                                                    point).rule))
            self.assertIs(route(Unrunnable("x"), must_hold, point).failure.code, FailureCode.PROBE_UNRUNNABLE)
            self.assertIs(route(InvalidSpec("x"), must_hold, point).failure.code, FailureCode.PROBE_INVALID_SPEC)
            self.assertIsNone(route(Unrunnable("x"), must_hold, point).decided_by)
        self.assertIsNone(route(Executed(S), must_hold, CANDIDATE).failure)
        self.assertIsNone(route(Executed(S), must_hold, CANDIDATE).decided_by)
        self.assertIs(route(Executed(R), must_hold, CANDIDATE).failure.code, FailureCode.CONTRACT_UNSATISFIED)
        self.assertIs(route(Executed(S), must_not, CANDIDATE).failure.code, FailureCode.CONTRACT_UNSATISFIED)
        self.assertIsNone(route(Executed(R), must_not, CANDIDATE).failure)
        self.assertIsNone(route(Executed(S), must_hold, POST_MERGE).failure)
        self.assertIs(route(Executed(R), must_hold, POST_MERGE).failure.code, FailureCode.POST_MERGE_REGRESSION)
        for result in (Executed(S), Executed(R)):
            with self.subTest(parent=result):
                r = route(result, must_not, PARENT, ObligationRole.INTRODUCE)
                self.assertEqual((r.failure, r.disposition, r.decided_by), (None, None, STORY_ADMISSION))

    def test_REFUTED_never_routes_to_ENVIRONMENT(self):
        for point, result, cid, _s, role, r in everything():
            if isinstance(result, Executed):
                with self.subTest(point=point, spec=cid, verdict=result.behavior_verdict, role=role):
                    self.assertIsNot(owner(r), Owner.ENVIRONMENT)

    def test_only_UNRUNNABLE_routes_to_ENVIRONMENT_and_never_to_DEVELOPER(self):
        for point, result, cid, _s, role, r in everything():
            unrunnable = isinstance(result, Unrunnable)
            with self.subTest(point=point, spec=cid, result=result, role=role):
                self.assertEqual(owner(r) is Owner.ENVIRONMENT, unrunnable)
                if unrunnable:
                    self.assertIsNot(owner(r), Owner.DEVELOPER)

    def test_no_did_not_run_to_developer_edge(self):
        for point, result, cid, _s, role, r in everything():
            if result is None or result.status is not ProbeExecutionStatus.EXECUTED:
                with self.subTest(point=point, spec=cid, result=result, role=role):
                    self.assertIsNot(owner(r), Owner.DEVELOPER)

    def test_routing_depends_on_satisfaction_never_on_the_raw_verdict(self):
        seen = {}
        for point, result, _cid, spec, role, r in everything():
            if isinstance(result, Executed):
                seen.setdefault((point, role, contract_satisfaction(result, spec), result.reason), set()).add(r)
        self.assertTrue(seen)
        for key, routes in seen.items():
            with self.subTest(key=key):
                self.assertEqual(len(routes), 1)
        self.assertEqual({k[2] for k in seen}, set(ContractSatisfaction))

    def test_an_unmapped_outcome_fails_closed_and_never_defaults_to_DEVELOPER(self):
        spec = SPECS["BC-VERSION"]
        for bad in (object(), "EXECUTED", BehaviorVerdict.SATISFIED):
            with self.subTest(result=bad), self.assertRaisesRegex(UnroutableOutcome, "is not a typed probe result"):
                route(bad, spec, CANDIDATE)
        with self.assertRaisesRegex(UnroutableOutcome, "^unknown measurement point 'CANDIDATE'$"):
            route(Executed(S), spec, "CANDIDATE")
        with self.assertRaisesRegex(UnroutableOutcome, "^unknown obligation role 'INTRODUCE'$"):
            route(Executed(S), spec, CANDIDATE, "INTRODUCE")
        with mock.patch.dict(routing._EXECUTED, clear=True), self.assertRaisesRegex(
                UnroutableOutcome, "^no routing row for CANDIDATE UNSATISFIED with reason None and role None$"):
            route(Executed(R), spec, CANDIDATE)
        self.assertTrue(issubclass(UnroutableOutcome, InvariantError))


class RetryabilityIsTyped(unittest.TestCase):
    def test_only_the_taxonomy_decides_retryability(self):
        ks = _static()
        self.assertEqual(ks.check(ROOT, ("RETRYABLE_ONLY_IN_TAXONOMY",)), [])
        for src in ("x = dict(retryable=True)\n", "def f(c):\n    c.retryability = 'RETRYABLE'\n"):
            with self.subTest(src=src):
                self.assertTrue(ks.violations("aisef2/control/routing.py", src, ("RETRYABLE_ONLY_IN_TAXONOMY",)))
        self.assertEqual(ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)), [])


def _static():
    s = importlib.util.spec_from_file_location("p1_ks_routing", ROOT / "validation" / "v2" / "kernel_static_checks.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


if __name__ == "__main__":
    unittest.main()
