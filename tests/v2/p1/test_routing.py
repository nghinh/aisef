"""WP-1.4 — Owner taxonomy and the owner routing table (RFC §22, §10; F2, F3).

Kill set for TAXONOMY, classify, flatten, the routing table and route: every owner and every retryability is pinned
here, and the §10 constraints are proved over the whole legal outcome space, for every corpus spec and both sites.
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

from aisef2.arch.enums import BehaviorVerdict, ContractSatisfaction, Owner, ProbeExecutionStatus  # noqa: E402
from aisef2.control import routing  # noqa: E402
from aisef2.control.owner import TAXONOMY, FailureCode, classify, flatten  # noqa: E402
from aisef2.control.routing import STORY_ADMISSION, Site, UnroutableOutcome, route  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, InvalidSpec, Unrunnable, contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

SPECS = {p.stem: ProductProofSpec.from_json(json.loads(p.read_text(encoding="utf-8")))
         for p in sorted((ROOT / "tests/v2/fixtures/p1/corpus/specs").glob("*.json"))}
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
RESULTS = [None, Unrunnable("harness"), InvalidSpec("spec"), Executed(S), Executed(R), Executed(I, PA)]
EXPECTED = {  # code -> (owner, retryable): the taxonomy, pinned
    FailureCode.PROBE_UNRUNNABLE: (Owner.ENVIRONMENT, True),
    FailureCode.PROBE_INVALID_SPEC: (Owner.INTEGRATION, False),
    FailureCode.CONTRACT_UNSATISFIED: (Owner.DEVELOPER, True),
    FailureCode.PRECONDITION_ABSENT: (Owner.PLAN, False),
    FailureCode.MISSING_CREDENTIAL: (Owner.ENVIRONMENT, True),
    FailureCode.INVALID_CREDENTIAL: (Owner.PROVIDER, False),
    FailureCode.UNKNOWN: (Owner.INTEGRATION, False),
}


def owner(r):
    return r.failure.owner if r.failure else None


def everything():
    for site, result, (cid, spec) in itertools.product(Site, RESULTS, SPECS.items()):
        yield site, result, cid, spec, route(result, spec, site)


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
                self.assertEqual((c.owner, c.retryable), (own, retry))
                self.assertIs(c.budget, own if retry else None)
                self.assertIn("§", c.rule)

    def test_credentials_are_split_and_the_invalid_one_never_retries(self):
        missing, invalid = classify(FailureCode.MISSING_CREDENTIAL), classify(FailureCode.INVALID_CREDENTIAL)
        self.assertFalse(invalid.retryable)
        self.assertNotEqual((missing.owner, missing.retryable), (invalid.owner, invalid.retryable))

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


class RoutingTable(unittest.TestCase):
    def test_total_over_the_legal_space(self):
        rows = list(everything())
        self.assertEqual(len(rows), len(Site) * len(RESULTS) * len(SPECS))

    def test_every_route_cites_its_rfc_basis(self):
        for site, result, cid, _s, r in everything():
            with self.subTest(site=site, spec=cid, result=result):
                self.assertRegex(r.rule, r"^§1[03][:.]? .{8,}")
        rules = {route(res, SPECS["BC-VERSION"], site).rule for site in Site for res in RESULTS}
        self.assertEqual(len(rules), 5)

    def test_the_rows(self):
        must_hold, must_not = SPECS["BC-VERSION"], SPECS["BC-QUIET-STDOUT"]
        cand, par = Site.CANDIDATE, Site.PARENT
        self.assertIsNone(route(None, must_hold, cand).failure)
        self.assertIsNone(route(None, must_hold, cand).decided_by)
        for site in Site:
            self.assertIs(route(Unrunnable("x"), must_hold, site).failure.code, FailureCode.PROBE_UNRUNNABLE)
            self.assertIs(route(InvalidSpec("x"), must_hold, site).failure.code, FailureCode.PROBE_INVALID_SPEC)
            self.assertIsNone(route(Unrunnable("x"), must_hold, site).decided_by)
        self.assertIsNone(route(Executed(S), must_hold, cand).failure)
        self.assertIs(route(Executed(R), must_hold, cand).failure.code, FailureCode.CONTRACT_UNSATISFIED)
        self.assertIs(route(Executed(S), must_not, cand).failure.code, FailureCode.CONTRACT_UNSATISFIED)
        self.assertIsNone(route(Executed(R), must_not, cand).failure)
        self.assertIs(route(Executed(I, PA), must_hold, cand).failure.code, FailureCode.PRECONDITION_ABSENT)
        for result in (Executed(S), Executed(R), Executed(I, PA)):
            with self.subTest(parent=result):
                r = route(result, must_not, par)
                self.assertIsNone(r.failure)
                self.assertEqual(r.decided_by, STORY_ADMISSION)
        self.assertIsNone(route(Executed(S), must_hold, cand).decided_by)

    def test_REFUTED_never_routes_to_ENVIRONMENT(self):
        for site, result, cid, _s, r in everything():
            if isinstance(result, Executed):
                with self.subTest(site=site, spec=cid, verdict=result.behavior_verdict):
                    self.assertIsNot(owner(r), Owner.ENVIRONMENT)

    def test_only_UNRUNNABLE_routes_to_ENVIRONMENT_and_never_to_DEVELOPER(self):
        for site, result, cid, _s, r in everything():
            unrunnable = isinstance(result, Unrunnable)
            with self.subTest(site=site, spec=cid, result=result):
                self.assertEqual(owner(r) is Owner.ENVIRONMENT, unrunnable)
                if unrunnable:
                    self.assertIsNot(owner(r), Owner.DEVELOPER)

    def test_no_did_not_run_to_developer_edge(self):
        for site, result, cid, _s, r in everything():
            if result is None or result.status is not ProbeExecutionStatus.EXECUTED:
                with self.subTest(site=site, spec=cid, result=result):
                    self.assertIsNot(owner(r), Owner.DEVELOPER)

    def test_routing_depends_on_satisfaction_never_on_the_raw_verdict(self):
        seen = {}
        for site, result, _cid, spec, r in everything():
            if isinstance(result, Executed):
                key = (site, contract_satisfaction(result, spec), result.reason)
                seen.setdefault(key, set()).add(r)
        self.assertTrue(seen)
        for key, routes in seen.items():
            with self.subTest(key=key):
                self.assertEqual(len(routes), 1)
        self.assertEqual({k[1] for k in seen}, set(ContractSatisfaction))

    def test_an_unmapped_outcome_fails_closed_and_never_defaults_to_DEVELOPER(self):
        spec = SPECS["BC-VERSION"]
        for bad in (object(), "EXECUTED", BehaviorVerdict.SATISFIED):
            with self.subTest(result=bad), self.assertRaisesRegex(UnroutableOutcome, "is not a typed probe result"):
                route(bad, spec, Site.CANDIDATE)
        with self.assertRaisesRegex(UnroutableOutcome, "unknown routing site"):
            route(Executed(S), spec, "CANDIDATE")
        with mock.patch.dict(routing._CANDIDATE, clear=True), \
                self.assertRaisesRegex(UnroutableOutcome, "^no routing row for UNSATISFIED with reason None$"):
            route(Executed(R), spec, Site.CANDIDATE)
        self.assertTrue(issubclass(UnroutableOutcome, InvariantError))


class RetryabilityIsTyped(unittest.TestCase):
    def test_only_the_taxonomy_decides_retryability(self):
        ks = _static()
        self.assertEqual(ks.check(ROOT, ("RETRYABLE_ONLY_IN_TAXONOMY",)), [])
        self.assertTrue(ks.violations("aisef2/control/routing.py", "x = dict(retryable=True)\n",
                                      ("RETRYABLE_ONLY_IN_TAXONOMY",)))
        self.assertEqual(ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)), [])


def _static():
    s = importlib.util.spec_from_file_location("p1_ks_routing", ROOT / "validation" / "v2" / "kernel_static_checks.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


if __name__ == "__main__":
    unittest.main()
