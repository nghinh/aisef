"""WP-1.3 — two-axis outcomes, the derived ContractSatisfaction, subject-absence semantics (RFC §10; F2).

Kill set for contract_satisfaction (must be fully killed — F2), on_subject_absent and Executed's invariants.
NEG-1/2/3 run on the committed corpus specs; their StoryAdmission dispositions belong to WP-2.4.
"""

import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, ContractSatisfaction, ProbeExecutionStatus  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.product.outcome import (  # noqa: E402
    Executed, IndeterminateReason, InvalidSpec, Unrunnable, contract_satisfaction, on_subject_absent,
)
from aisef2.product.spec import ProductProofSpec  # noqa: E402

SPECS = ROOT / "tests" / "v2" / "fixtures" / "p1" / "corpus" / "specs"
_s = importlib.util.spec_from_file_location("p1_ks_outcome", ROOT / "validation" / "v2" / "kernel_static_checks.py")
ks = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ks)

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT


def spec(cid):
    return ProductProofSpec.from_json(json.loads((SPECS / f"{cid}.json").read_text(encoding="utf-8")))


class _Spec:
    def __init__(self, expectation):
        self.candidate_expectation = expectation


class TwoAxes(unittest.TestCase):
    def test_six_legal_states_are_exactly_these(self):
        states = {(r.status, getattr(r, "behavior_verdict", None))
                  for r in (Executed(S), Executed(R), Executed(I, PA), Unrunnable("x"), InvalidSpec("y"))}
        states.add((None, None))  # not attempted
        self.assertEqual(len(states), 6)
        self.assertEqual({s for s, _ in states}, set(ProbeExecutionStatus) | {None})

    def test_the_verdict_exists_only_inside_executed(self):
        for r in (Unrunnable("harness missing"), InvalidSpec("not evaluable")):
            with self.subTest(result=type(r).__name__):
                self.assertFalse(hasattr(r, "behavior_verdict"))
                with self.assertRaises(TypeError):
                    type(r)("x", behavior_verdict=S)
        self.assertIs(Executed(S).status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(Unrunnable("x").status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(InvalidSpec("x").status, ProbeExecutionStatus.INVALID_SPEC)

    def test_indeterminate_requires_a_typed_reason_and_only_it_carries_one(self):
        with self.assertRaisesRegex(InvariantError, "^INDETERMINATE requires a typed IndeterminateReason$"):
            Executed(I)
        with self.assertRaises(InvariantError):
            Executed(I, "PRECONDITION_ABSENT")
        for v in (S, R):
            with self.subTest(verdict=v), self.assertRaisesRegex(InvariantError, "^only INDETERMINATE carries a reason$"):
                Executed(v, PA)
        with self.assertRaisesRegex(InvariantError, "^an executed probe reports a BehaviorVerdict$"):
            Executed("SATISFIED")
        self.assertIs(Executed(I, PA).reason, PA)
        self.assertIsNone(Executed(S).reason)


class Satisfaction(unittest.TestCase):
    TABLE = {(S, S): ContractSatisfaction.SATISFIED, (R, S): ContractSatisfaction.UNSATISFIED,
             (S, R): ContractSatisfaction.UNSATISFIED, (R, R): ContractSatisfaction.SATISFIED}

    def test_satisfied_iff_the_verdict_equals_the_expectation(self):
        for (verdict, expectation), want in self.TABLE.items():
            with self.subTest(verdict=verdict, expectation=expectation):
                self.assertIs(contract_satisfaction(Executed(verdict), _Spec(expectation)), want)

    def test_indeterminate_stays_indeterminate_whatever_the_expectation(self):
        for expectation in (S, R):
            with self.subTest(expectation=expectation):
                self.assertIs(contract_satisfaction(Executed(I, PA), _Spec(expectation)),
                              ContractSatisfaction.INDETERMINATE)

    def test_it_is_undefined_for_a_probe_that_did_not_execute(self):
        for r in (Unrunnable("x"), InvalidSpec("y"), None, "EXECUTED", object()):
            with self.subTest(result=r), self.assertRaisesRegex(
                    InvariantError, "^contract satisfaction is undefined for a probe that did not execute$"):
                contract_satisfaction(r, _Spec(S))

    def test_it_is_derived_never_stored(self):
        for obj in (Executed(S), spec("BC-VERSION")):
            self.assertFalse(hasattr(obj, "contract_satisfaction"))
            self.assertFalse(hasattr(obj, "satisfaction"))


class Polarity(unittest.TestCase):
    def test_NEG_1_forbidden_behaviour_present_at_the_parent_is_UNSATISFIED_never_SATISFIED(self):
        s = spec("BC-QUIET-STDOUT")  # MUST_NOT_HOLD, REQUIRES_SUBJECT
        observed = Executed(S)       # the CLI does write to stdout
        self.assertIs(s.candidate_expectation, R)
        self.assertIs(contract_satisfaction(observed, s), ContractSatisfaction.UNSATISFIED)
        # the raw verdict says SATISFIED; routing on it would have declared the story PRE_SATISFIED
        self.assertIs(observed.behavior_verdict, S)

    def test_NEG_2_forbidden_module_absent_and_decidable_is_SATISFIED(self):
        s = spec("BC-NO-TELEMETRY")  # MUST_NOT_HOLD, ABSENCE_IS_DECIDABLE
        observed = on_subject_absent(s)
        self.assertEqual(observed, Executed(R))
        self.assertIs(contract_satisfaction(observed, s), ContractSatisfaction.SATISFIED)

    def test_NEG_3_subject_required_but_absent_is_INDETERMINATE_PRECONDITION_ABSENT(self):
        s = spec("BC-QUIET-STDOUT")
        observed = on_subject_absent(s)
        self.assertEqual(observed, Executed(I, PA))
        self.assertIs(contract_satisfaction(observed, s), ContractSatisfaction.INDETERMINATE)

    def test_absence_follows_the_declaration_not_the_polarity(self):
        self.assertEqual(on_subject_absent(spec("BC-LICENSE")), Executed(R))      # MUST_HOLD, decidable
        self.assertIs(contract_satisfaction(on_subject_absent(spec("BC-LICENSE")), spec("BC-LICENSE")),
                      ContractSatisfaction.UNSATISFIED)
        self.assertEqual(on_subject_absent(spec("BC-VERSION")), Executed(I, PA))  # MUST_HOLD, requires subject

    def test_subject_absence_is_an_observation_never_unrunnable(self):
        for cid in ("BC-QUIET-STDOUT", "BC-NO-TELEMETRY", "BC-VERSION", "BC-LICENSE"):
            with self.subTest(spec=cid):
                self.assertIs(on_subject_absent(spec(cid)).status, ProbeExecutionStatus.EXECUTED)

    def test_an_undeclared_absence_is_refused(self):
        s = spec("BC-LICENSE")
        forged = type("S", (), {"probe_input": {**s.probe_input, "subject_absence": "INFERRED"}})()
        with self.assertRaises(ValueError):
            on_subject_absent(forged)


class NoRawVerdictRouting(unittest.TestCase):
    def test_no_planning_or_control_module_names_the_raw_verdict(self):
        self.assertEqual(ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)), [])

    def test_the_rule_sees_each_spelling(self):
        for src in ("from aisef2.arch.enums import BehaviorVerdict\n",
                    "def f(r):\n    return r.behavior_verdict\n",
                    "import aisef2.arch.enums as E\n\ndef f(v):\n    return v is E.BehaviorVerdict.REFUTED\n",
                    "def f(r):\n    return getattr(r, 'behavior_verdict')\n"):
            with self.subTest(src=src):
                self.assertTrue(ks.violations("aisef2/control/x.py", src, ("NO_RAW_VERDICT_ROUTING",)))
        self.assertEqual(ks.violations("aisef2/product/x.py", "from aisef2.arch.enums import BehaviorVerdict\n",
                                       ("NO_RAW_VERDICT_ROUTING",)), [])


if __name__ == "__main__":
    unittest.main()
