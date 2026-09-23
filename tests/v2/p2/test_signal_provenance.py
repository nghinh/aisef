"""SIG-PROBE-1..10 — ARCHITECTURE-EXCEPTION-V2-003: signal provenance after dispatch (RFC §9.3, §10.2, §10.3).

The controller knows one thing mechanically: whether *it* sent the signal that ended the subject's process. Its own
signal ledger — the P4 owned process range (§17.1), the single authority — decides; the signal number never does.

* before DISPATCHED: unchanged by this amendment (V2-002) — UNRUNNABLE / ENVIRONMENT (SIG-PROBE-1);
* after DISPATCHED, the ledger holds the signal: an interruption, no ProbeResult at all (SIG-PROBE-2);
* after DISPATCHED, it does not: EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL), routed INTEGRATION and never
  retried, at every measurement point (SIG-PROBE-4..7; SIG-PROBE-3, the os.abort() subject, lives in
  test_signal_provenance_abort.py: every abort makes macOS show a crash dialog, so it runs once per suite and is in no
  mutation kill set — SIG-PROBE-4 and the faked ranges here cover the same path);
* the old rule and a DEVELOPER route must fail conformance (SIG-PROBE-8, -9), and the same physical exit must take
  different paths for different ledgers (SIG-PROBE-10).
"""

import os
import pathlib
import signal
import sys
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, Enforcement, EventType as T, MeasurementPoint, ObligationRole, Owner, ParentExpectation,
    ProbeExecutionStatus, StoryAdmissionDisposition as D,
)
from aisef2.control import budget  # noqa: E402
from aisef2.control.owner import FailureCode, Retryability, classify  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.journal.event import JournalError  # noqa: E402
from aisef2.plan.obligation import PlanObligation  # noqa: E402
from aisef2.plan.story_admission import classify as admit  # noqa: E402
from aisef2.probe import python_callable as pc  # noqa: E402
from aisef2.probe.protocol import ProbeInterrupted, ProbeRecord, RevisionRef, run_probe  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from tests.v2.p2.test_python_callable import P, checkout, env, faked, spec  # noqa: E402

POSIX = os.name == "posix"
NCS = IndeterminateReason.NON_CONTROLLER_SIGNAL
I = BehaviorVerdict.INDETERMINATE
SHA = "89abcdef0123456789abcdef0123456789abcdef"
SUBJECTS = {
    "app/__init__.py": "",
    "app/abort.py": "import os\n\n\ndef f():\n    os.abort()\n",
    "app/selfterm.py": "import os\nimport signal\n\n\ndef f():\n    os.kill(os.getpid(), signal.SIGTERM)\n",
    "app/hold.py": "import time\n\n\ndef f():\n    time.sleep(3600)\n",
}


class _Subjects(unittest.TestCase):
    """A real checkout whose subjects end their own process by a signal."""

    @classmethod
    def setUpClass(cls):
        cls.at = RevisionRef(SHA, checkout(SUBJECTS))

    def see(self, locator, probe=P, window=10):
        return probe.observe(spec(locator, {"returns": 1}, window=window), self.at, env())

    def result(self, locator, probe=P):
        s = spec(locator, {"returns": 1})
        return run_probe(probe, s, self.at, env()).result


class BeforeDispatch(_Subjects):
    def test_SIG_PROBE_1_a_signal_before_dispatch_is_still_unrunnable_environment(self):
        """V2-002 unchanged: the observation mechanism failed before it could observe anything."""
        with faked(returncode=-9):  # nothing was printed: the harness died before READY
            faked_result = self.result("app.abort:f")
        self.assertIs(faked_result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertFalse(hasattr(faked_result, "behavior_verdict"))
        for point in MeasurementPoint:
            r = route(faked_result, spec("app.abort:f"), point, ObligationRole.INTRODUCE)
            self.assertEqual((r.failure.code, r.failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))
        if POSIX:  # the same, with a real harness that signals itself before printing READY
            kill = "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"
            with mock.patch.object(pc, "HARNESS", kill):
                real = self.result("app.abort:f")
            self.assertIs(real.status, ProbeExecutionStatus.UNRUNNABLE)
            self.assertRegex(real.detail, r"killed by signal 9 before READY$")


@unittest.skipUnless(POSIX, "a process that ends itself by a signal (POSIX; Windows has no signal exit)")
class AfterDispatch(_Subjects):
    def test_SIG_PROBE_4_a_subject_that_signals_itself_is_executed_and_indeterminate(self):
        observed = self.see("app.selfterm:f")
        self.assertEqual((observed.kind.value, observed.verdict), ("NON_CONTROLLER_SIGNAL", None))
        self.assertIn(f"signal {int(signal.SIGTERM)} after DISPATCHED", observed.detail)
        self.assertEqual(self.result("app.selfterm:f"), Executed(I, NCS))

    def test_SIG_PROBE_2_a_controller_stop_is_an_interruption_with_no_result(self):
        """The controller stops its own observation mid-flight: no ProbeResult, no verdict, no owner."""
        stops = []

        def stop_it(run):
            stops.append(run)
            threading.Timer(0.5, run.release).start()  # the controller's own ladder: it goes into the ledger
        probe = PythonCallableProbe(on_range=stop_it)
        with self.assertRaises(ProbeInterrupted) as interrupted:
            run_probe(probe, spec("app.hold:f", {"returns": 1}, window=60), self.at, env())
        self.assertTrue(stops and stops[0].ledger)
        self.assertEqual(interrupted.exception.stage, stops[0].ledger[-1]["stage"])
        self.assertIn("what the subject did is not known", interrupted.exception.detail)
        self.assertFalse(stops[0].members())  # the range is empty: nothing of the observation survives

    def test_SIG_PROBE_10_the_ledger_decides_not_the_signal_number(self):
        """One physical exit, two ledgers, two paths — the proof that this is provenance, not signal matching."""
        quiet, stopped = [], [{"stage": "terminate", "signal": "SIGTERM"}]
        with faked("READY", "DISPATCHED", returncode=-int(signal.SIGTERM), ledger=quiet):
            without = self.result("app.selfterm:f")
        self.assertEqual(without, Executed(I, NCS))
        with faked("READY", "DISPATCHED", returncode=-int(signal.SIGTERM), ledger=stopped):
            with self.assertRaises(ProbeInterrupted):
                self.result("app.selfterm:f")


class Routing(unittest.TestCase):
    """SIG-PROBE-5..7: one owner at every measurement point — INTEGRATION, never retried, no budget."""

    def setUp(self):
        self.spec = spec("app.abort:f", {"returns": 1})
        self.result = Executed(I, NCS)

    RULE = ("§9.3, §10.3 (V2-003): executed, then a signal the controller did not send — the behavioural truth the "
            "contract needs cannot be derived, and no cause may be invented")

    def test_SIG_PROBE_5_at_the_candidate_it_charges_no_budget(self):
        r = route(self.result, self.spec, MeasurementPoint.CANDIDATE, ObligationRole.INTRODUCE)
        self.assertEqual((r.failure.code, r.failure.owner, r.failure.retryability, r.failure.budget),
                         (FailureCode.NON_CONTROLLER_SIGNAL, Owner.INTEGRATION, Retryability.NOT_RETRYABLE, None))
        self.assertIsNone(r.disposition)
        self.assertEqual(r.rule, self.RULE + " — the product criterion is not proved, and no developer budget is "
                                             "charged")

    def test_SIG_PROBE_7_after_merge_it_is_integration_and_never_retried(self):
        r = route(self.result, self.spec, MeasurementPoint.POST_MERGE, ObligationRole.VERIFY)
        self.assertEqual((r.failure.code, r.failure.owner, r.failure.retryability, r.failure.budget),
                         (FailureCode.NON_CONTROLLER_SIGNAL, Owner.INTEGRATION, Retryability.NOT_RETRYABLE, None))
        self.assertEqual(r.rule, self.RULE + " — a regression after merge is never inferred without evidence")
        parent = route(self.result, self.spec, MeasurementPoint.PARENT, ObligationRole.VERIFY)
        self.assertEqual(parent.rule, self.RULE + " — at the parent it fails closed as PROBE_INVALID, so no story is "
                                                  "admitted on it")

    def test_the_taxonomy_fixes_owner_and_retryability_and_the_journal_holds_them(self):
        c = classify(FailureCode.NON_CONTROLLER_SIGNAL)
        self.assertEqual((c.owner, c.retryability, c.budget), (Owner.INTEGRATION, Retryability.NOT_RETRYABLE, None))
        from aisef2.journal.event import carried
        filled = carried(T.FAILURE_OBSERVED.value, {"story_id": "S1", "code": "NON_CONTROLLER_SIGNAL", "detail": ""})
        self.assertEqual((filled["owner"], filled["retryable"]), ("INTEGRATION", False))  # from the taxonomy alone
        with self.assertRaisesRegex(JournalError, "never from the call site"):
            carried(T.FAILURE_OBSERVED.value, {"story_id": "S1", "code": "NON_CONTROLLER_SIGNAL", "detail": "",
                                               "owner": "DEVELOPER", "retryable": True})


class Admission(unittest.TestCase):
    """SIG-PROBE-6: at the parent it fails closed through PROBE_INVALID, owner INTEGRATION; nothing is admitted."""

    def decision(self, role=ObligationRole.INTRODUCE):
        s = spec("app.abort:f", {"returns": 1})
        record = ProbeRecord.create(spec_id=s.id, semantic_hash=s.semantic_hash, probe_id=s.probe_id,
                                    probe_digest=s.probe_digest, revision=SHA, enforcement=Enforcement.PARTIAL,
                                    result=Executed(I, NCS))
        obligation = PlanObligation(
            criterion_id="C1", product_proof_spec_id=s.id, story_id="S1", role=role,
            expected_parent=ParentExpectation.UNCONSTRAINED if role is ObligationRole.VERIFY
            else (ParentExpectation.SATISFIED_AT_PARENT if role is ObligationRole.PRESERVE
                  else ParentExpectation.UNSATISFIED_AT_PARENT),
            depends_on=(), ownership_rationale="the criterion this story is measured by")
        return s, admit(obligation, record, s, revision=SHA, enforcement=Enforcement.PARTIAL,
                        introducer_committed=False)

    def test_SIG_PROBE_6_the_parent_disposition_is_probe_invalid_and_integration(self):
        for role in ObligationRole:
            with self.subTest(role=role.value):
                _, decision = self.decision(role)
                self.assertIs(decision.disposition, D.PROBE_INVALID)
                self.assertEqual((decision.failure.code, decision.failure.owner),
                                 (FailureCode.NON_CONTROLLER_SIGNAL, Owner.INTEGRATION))
                self.assertNotIn(decision.disposition, (D.READY, D.PRE_SATISFIED))

    def test_no_developer_or_provider_budget_is_reachable_from_it(self):
        _, decision = self.decision()
        self.assertIsNone(decision.failure.budget)
        self.assertIs(decision.failure.retryability, Retryability.NOT_RETRYABLE)
        self.assertIsNot(decision.failure.owner, Owner.DEVELOPER)
        self.assertIsNot(decision.failure.owner, Owner.ENVIRONMENT)


class Conformance(unittest.TestCase):
    """SIG-PROBE-8, -9: the removed rule and a DEVELOPER route must fail F5 / F2 conformance."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "validation" / "v2"))
        import freeze_conformance as fc
        self.fc = fc
        self.rfc = fc.RFC((ROOT / fc.RFC_REL).read_text(encoding="utf-8"))

    def test_SIG_PROBE_8_restoring_signal_after_dispatch_to_unrunnable_fails_F5(self):
        self.assertEqual(self.fc._signal_provenance_matches_rfc(self.rfc)["state"], self.fc.PASS)
        from aisef2.probe.protocol import Observation, ObservationKind as K

        def old_rule(run):  # every post-DISPATCH signal is a harness failure, as before V2-003
            return Observation(K.HARNESS_FAILED, detail="the harness process was killed by signal mid-observation")
        with mock.patch.object(pc, "_ended_without_result", old_rule):
            got = self.fc._signal_provenance_matches_rfc(self.rfc)
        self.assertEqual(got["state"], self.fc.FAIL)
        self.assertTrue(any("interruption" in p or "became" in p for p in got["problems"]), got)

    def test_SIG_PROBE_9_routing_the_reason_to_developer_or_environment_fails_F2(self):
        self.assertEqual(self.fc._routing_matches_rfc(self.rfc)["state"], self.fc.PASS)
        from aisef2.control import routing as rt
        for owner_code in (FailureCode.CONTRACT_UNSATISFIED, FailureCode.PROBE_UNRUNNABLE):  # DEVELOPER, ENVIRONMENT
            rows = dict(rt._EXECUTED)
            for key, row in list(rows.items()):
                if key[2] is NCS:
                    rows[key] = (owner_code, *row[1:])
            with self.subTest(routed_to=classify(owner_code).owner.value), mock.patch.object(rt, "_EXECUTED", rows):
                got = self.fc._routing_matches_rfc(self.rfc)
                self.assertEqual(got["state"], self.fc.FAIL)
                self.assertTrue(got["problems"])


class Budgets(unittest.TestCase):
    """SIG-PROBE-5, at the journal: the failure consumes no retry budget of any owner."""

    def test_a_non_controller_signal_failure_is_not_retryable_from_the_journal(self):
        from tests.v2.p4.world import SHA as PARENT
        import tempfile
        from aisef2.runtime.run_scope import RunScope
        from tests.v2.p4.test_run_scope import plan, spec as run_spec
        with tempfile.TemporaryDirectory(prefix="aisef2-ncs-") as d:
            run = RunScope(d, "run-ncs", spec=run_spec, clock=lambda: 1.0)
            self.addCleanup(run.lease.release)
            run.begin()
            plan(run)
            run.append(T.STORY_BEGIN, {"story_id": "S1", "parent": PARENT})
            run.append(T.STORY_ADMITTED, {"story_id": "S1", "parent": PARENT, "admitted": True,
                                          "developer_call_permitted": True, "dispositions": {"C1": "READY"}})
            failure = run.append(T.FAILURE_OBSERVED, {"story_id": "S1",
                                                      "code": FailureCode.NON_CONTROLLER_SIGNAL.value,
                                                      "detail": "signal 6, not the controller's"})
            self.assertEqual((failure.data["owner"], failure.data["retryable"]), ("INTEGRATION", False))
            limits = {o: 5 for o in Owner}
            charge = budget.charge(run.events, "S1", limits)
            self.assertFalse(charge.retry)
            self.assertIsNone(charge.budget)
            self.assertIn("not retryable", charge.reason)
            run._writer.close()


if __name__ == "__main__":
    unittest.main()
