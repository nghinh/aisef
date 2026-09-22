"""WP-4.5 — typed retry budgets as projections (RFC §17, §22; P4-LIFETIME-SEMANTICS.md §6). Kill set for
`aisef2/control/budget.py` and `RunScope.retry`.

SS-64 (a cap reached inside one budget stops there; it never falls through to another), D-006 (a credential or
environment rejection never consumes the developer's budget), PRE_SATISFIED and PLAN_CONTRADICTION consume no
developer budget, only typed chargeable outcomes charge their declared budget, and the journal rebuilt from scratch
gives the same budget state and the same decisions as the live run. No side counter: static check.
"""

import ast
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ControlProjection as P, EventType as T, Owner  # noqa: E402
from aisef2.control import budget  # noqa: E402
from aisef2.control.owner import TAXONOMY, FailureCode  # noqa: E402
from aisef2.journal.fold import ProjectionError, fold  # noqa: E402
from aisef2.journal.format2 import reconstruct  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from aisef2.runtime.run_scope import RetryRefused, RunScope  # noqa: E402
from tests.v2.p4.test_run_scope import spec  # noqa: E402
from tests.v2.p4.world import SHA  # noqa: E402

LIMITS = {Owner.PROVIDER: 2, Owner.DEVELOPER: 3, Owner.ENVIRONMENT: 1}


class Budgets(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-budget-")
        self.addCleanup(self._d.cleanup)
        self.run = RunScope(self._d.name, "run-b", spec=spec, clock=lambda: 1.0)
        self.addCleanup(self.run.lease.release)
        self.run.begin()
        self.run.append(T.PLAN_FROZEN, {"plan_id": "PLAN-B", "plan_hash": "b" * 64,
                                        "roles": {"C1": "INTRODUCE", "C2": "INTRODUCE"}})

    def attempt(self, story="S1", dispositions=None):
        d = dispositions or {"C1": "READY", "C2": "READY"}
        blocked = any(v in ("PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "PROBE_UNRUNNABLE", "PROBE_INVALID")
                      for v in d.values())
        self.run.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
        self.run.append(T.STORY_ADMITTED, {"story_id": story, "parent": SHA, "admitted": not blocked,
                                           "developer_call_permitted": not blocked and "READY" in d.values(),
                                           "dispositions": d})

    def fail(self, code, story="S1"):
        extra = {"original": "OSError"} if code is FailureCode.UNKNOWN else {}
        return self.run.append(T.FAILURE_OBSERVED, {"story_id": story, "code": code.value, "detail": "", **extra})

    def retry_and_restart(self, story="S1"):
        self.run.retry(story, LIMITS)
        self.run.append(T.STORY_DISPOSE, {"story_id": story})
        self.run.append(T.STORY_END, {"story_id": story})
        self.attempt(story)

    def spent(self, story="S1"):
        return self.run.state(P.BUDGETS)["retries"].get(story, {})

    def test_SS_64_a_cap_reached_in_one_budget_stops_there_and_never_falls_through(self):
        self.attempt()
        for _ in range(2):
            self.fail(FailureCode.PROVIDER_UNAVAILABLE)
            self.retry_and_restart()
        self.fail(FailureCode.PROVIDER_UNAVAILABLE)
        before = self.run.events
        with self.assertRaises(RetryRefused) as stop:
            self.run.retry("S1", LIMITS)
        c = stop.exception.charge
        self.assertEqual((c.retry, c.budget, c.spent, c.limit), (False, "PROVIDER", 2, 2))
        self.assertEqual(c.reason, "the PROVIDER budget is spent (2 of 2): the story stops; no other budget is "
                                   "consulted")
        self.assertEqual(self.run.events, before)  # nothing was written
        self.assertEqual(self.spent(), {"PROVIDER": 2})  # the developer budget is untouched
        for other in ({**LIMITS, Owner.DEVELOPER: 0}, {**LIMITS, Owner.DEVELOPER: 99}, {Owner.PROVIDER: 2}):
            with self.subTest(limits=other):  # whatever the other budgets allow, the provider's cap decides
                self.assertFalse(budget.charge(self.run.events, "S1", other).retry)
        self.fail(FailureCode.CONTRACT_UNSATISFIED)  # a developer failure is charged to its own budget, from 0
        dev = budget.charge(self.run.events, "S1", LIMITS)
        self.assertEqual((dev.retry, dev.budget, dev.spent, dev.limit), (True, "DEVELOPER", 0, 3))

    def test_D_006_a_credential_or_environment_rejection_never_consumes_the_developer_budget(self):
        self.attempt()
        self.run.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        developer_before = dict(budget.developer_spend(self.run.events, "S1"))
        self.fail(FailureCode.INVALID_CREDENTIAL)
        c = budget.charge(self.run.events, "S1", LIMITS)
        self.assertEqual((c.retry, c.budget), (False, None))
        self.assertEqual(c.reason, f"the failure at seq {c.failure_seq} is not retryable: it charges no budget (§22)")
        with self.assertRaises(RetryRefused):
            self.run.retry("S1", LIMITS)
        with self.assertRaisesRegex(ProjectionError, "cites a non-retryable failure: no budget to charge"):
            self.run.append(T.STORY_RETRY, {"story_id": "S1"}, source_seqs=(self.run.events[-1].seq,))
        self.fail(FailureCode.MISSING_CREDENTIAL)  # retryable by policy: its own ENVIRONMENT budget
        env = budget.charge(self.run.events, "S1", LIMITS)
        self.assertEqual((env.retry, env.budget), (True, "ENVIRONMENT"))
        self.run.retry("S1", LIMITS)
        self.assertEqual(self.spent(), {"ENVIRONMENT": 1})
        self.assertEqual(dict(budget.developer_spend(self.run.events, "S1")), developer_before)
        self.assertNotIn("DEVELOPER", self.spent())

    def test_PRE_SATISFIED_and_PLAN_CONTRADICTION_consume_no_developer_budget(self):
        self.attempt(dispositions={"C1": "PRE_SATISFIED", "C2": "READY"})
        self.run.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C2"]})
        with self.assertRaisesRegex(ProjectionError, r"charges \['C1'\], not admitted READY"):
            self.run.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1"]})
        self.assertEqual(dict(budget.developer_spend(self.run.events, "S1")), {"C2": 1})
        self.attempt("S2", {"C1": "PLAN_CONTRADICTION"})
        with self.assertRaisesRegex(ProjectionError, "provider/request for story S2 in state BEGIN"):
            self.run.append(T.PROVIDER_REQUEST, {"story_id": "S2", "criteria": ["C1"]})  # a blocked story stays BEGIN
        self.fail(FailureCode.PLAN_CONTRADICTION, "S2")
        c = budget.charge(self.run.events, "S2", LIMITS)
        self.assertEqual((c.retry, c.budget, c.spent), (False, None, 0))
        self.assertEqual(dict(budget.developer_spend(self.run.events, "S2")), {})
        self.assertEqual(self.spent("S2"), {})

    def test_only_a_typed_chargeable_outcome_charges_its_declared_budget(self):
        for n, code in enumerate(FailureCode):
            story = f"S-{n}"
            with self.subTest(code=code.value):
                self.attempt(story)
                self.fail(code, story)
                c = budget.charge(self.run.events, story, {o: 5 for o in Owner})
                want = TAXONOMY[code].budget
                self.assertEqual(c.budget, want.value if want else None)
                self.assertIs(c.retry, want is not None)
                if want is not None:
                    self.run.retry(story, {o: 5 for o in Owner})
                    self.assertEqual(self.spent(story), {want.value: 1})

    def test_no_approved_count_is_no_retry_and_no_failure_is_nothing_to_retry(self):
        self.attempt()
        self.assertEqual(budget.charge(self.run.events, "S1", LIMITS),
                         budget.Charge("S1", False, None, 0, None, None, "S1 has no failure to retry"))
        self.assertEqual(budget.charge(self.run.events, "S9", LIMITS).reason, "S9 has no failure to retry")
        self.fail(FailureCode.PROVIDER_UNAVAILABLE)
        c = budget.charge(self.run.events, "S1", {Owner.DEVELOPER: 3})
        self.assertEqual((c.retry, c.limit, c.reason), (False, None, "no approved retry count for the PROVIDER budget"))
        c = budget.charge(self.run.events, "S1", {Owner.PROVIDER: None})
        self.assertFalse(c.retry)
        c = budget.charge(self.run.events, "S1", {Owner.PROVIDER: 1})
        self.assertEqual((c.retry, c.reason), (True, "retry against the PROVIDER budget (1 of 1)"))
        self.assertEqual(c.failure_seq, self.run.events[-1].seq)

    def test_the_journal_rebuilt_from_scratch_gives_the_same_budgets_and_the_same_decisions(self):
        self.attempt()
        self.run.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ["C1", "C2"]})
        self.fail(FailureCode.PROVIDER_UNAVAILABLE)
        self.retry_and_restart()
        self.fail(FailureCode.CONTRACT_UNSATISFIED)
        self.retry_and_restart()
        self.attempt("S2")
        self.fail(FailureCode.INVALID_CREDENTIAL, "S2")
        rebuilt = reconstruct(self.run.journal_path.read_bytes().decode("utf-8")).events
        self.assertEqual(rebuilt, self.run.events)
        for p in (P.BUDGETS, P.RETRY_TARGET):
            with self.subTest(projection=p.value):
                self.assertEqual(fold(PROJECTIONS[p], rebuilt), self.run.state(p))
        for story in ("S1", "S2", "S3"):
            self.assertEqual(budget.charge(rebuilt, story, LIMITS), budget.charge(self.run.events, story, LIMITS))
        self.assertEqual(self.spent(), {"PROVIDER": 1, "DEVELOPER": 1})

    def test_the_budget_module_keeps_no_counter(self):
        tree = ast.parse(pathlib.Path(budget.__file__).read_text(encoding="utf-8"))
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, (ast.AugAssign, ast.Global, ast.Nonlocal))])
        import importlib.util
        s = importlib.util.spec_from_file_location("aisef_v2_ks_budget", ROOT / "validation/v2/kernel_static_checks.py")
        ks = importlib.util.module_from_spec(s)
        s.loader.exec_module(ks)
        self.assertEqual(ks.check(ROOT, ("NO_SIDE_RETRY_COUNTER",)), [])
        injected = "def on_failure(state, story):\n    state.retries[story] = state.retries[story] + 1\n"
        self.assertEqual(ks.violations("aisef2/control/budget.py", injected, ("NO_SIDE_RETRY_COUNTER",)),
                         ["NO_SIDE_RETRY_COUNTER aisef2/control/budget.py:2 counts 'retries' beside the journal (§22: "
                          "budgets are projections)"])


if __name__ == "__main__":
    unittest.main()
