"""WP-1.3 — two-axis outcomes, the derived ContractSatisfaction, subject-absence semantics (RFC §10; F2).

Kill set for contract_satisfaction (must be fully killed — F2), on_subject_absent and Executed's invariants.
NEG-1/2/3 run on the committed corpus specs; their StoryAdmission dispositions belong to WP-2.4.
Subject absence (owner decision "FINAL P1 HYGIENE BEFORE P2"): cases A-D and PROBE-ABS-2..5 at the level of the
helper; the probe-level PROBE-ABS-1..5 belong to WP-2.1. P1 has no probe, so the one physical observation is a
fixture: the existence observable evaluated over a subject that is not there.
"""

import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, ProbeExecutionStatus, SubjectAbsence,
)
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


def variant(cid, *, expectation=None, absence=None):
    """The corpus spec `cid` with another polarity (candidate expectation) or absence declaration — same subject."""
    s = spec(cid)
    probe_input = {**s.probe_input, "subject_absence": (absence or SubjectAbsence(s.probe_input["subject_absence"])).value}
    return ProductProofSpec.create(contract_id=s.contract_id, probe_id=s.probe_id, probe_digest=s.probe_digest,
                                   probe_input=probe_input, candidate_expectation=expectation or s.candidate_expectation,
                                   compiler_id=s.compiler_id, compiler_digest=s.compiler_digest)


def existence_observed(present):
    """Fixture observation for the existence observable ({"condition": "exists"}): a stand-in for the WP-2.1 probe."""
    return S if present else R


#: One physical fact — src/app/telemetry.py is not there — as the existence observable sees it.
ABSENT = existence_observed(False)
NO_VERDICT = "^REQUIRES_SUBJECT: an absent subject has no verdict; reporting one is vacuous$"
NO_DEFAULT = ("^ABSENCE_IS_DECIDABLE: the verdict is what the probe observed on the spec's observable; "
              "there is no default$")


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
        s = spec("BC-NO-TELEMETRY")  # MUST_NOT_HOLD, ABSENCE_IS_DECIDABLE, existence observable
        observed = on_subject_absent(s, observed=ABSENT)
        self.assertEqual(observed, Executed(R))
        self.assertIs(contract_satisfaction(observed, s), ContractSatisfaction.SATISFIED)

    def test_NEG_3_subject_required_but_absent_is_INDETERMINATE_PRECONDITION_ABSENT(self):
        s = spec("BC-QUIET-STDOUT")
        observed = on_subject_absent(s, observed=None)
        self.assertEqual(observed, Executed(I, PA))
        self.assertIs(contract_satisfaction(observed, s), ContractSatisfaction.INDETERMINATE)

    def test_subject_absence_is_an_observation_never_unrunnable(self):
        for cid, seen in (("BC-QUIET-STDOUT", None), ("BC-NO-TELEMETRY", ABSENT), ("BC-VERSION", None),
                          ("BC-LICENSE", ABSENT)):
            with self.subTest(spec=cid):
                self.assertIs(on_subject_absent(spec(cid), observed=seen).status, ProbeExecutionStatus.EXECUTED)

    def test_an_undeclared_absence_is_refused(self):
        s = spec("BC-LICENSE")
        forged = type("S", (), {"probe_input": {**s.probe_input, "subject_absence": "INFERRED"}})()
        for seen in (None, ABSENT):
            with self.subTest(observed=seen), self.assertRaises(ValueError):
                on_subject_absent(forged, observed=seen)


class SubjectAbsenceSemantics(unittest.TestCase):
    """RFC §10.2. One physical absence of src/app/telemetry.py, read under different contract semantics."""

    POSITIVE = variant("BC-NO-TELEMETRY", expectation=S)   # "the module MUST exist", ABSENCE_IS_DECIDABLE
    NEGATIVE = spec("BC-NO-TELEMETRY")                     # "the module MUST NOT exist", ABSENCE_IS_DECIDABLE
    REQUIRES = variant("BC-NO-TELEMETRY", absence=SubjectAbsence.REQUIRES_SUBJECT)

    def test_the_variants_differ_only_where_they_claim_to(self):
        self.assertEqual(self.POSITIVE.probe_input, self.NEGATIVE.probe_input)
        self.assertEqual((self.POSITIVE.candidate_expectation, self.NEGATIVE.candidate_expectation), (S, R))
        self.assertEqual({**self.REQUIRES.probe_input, "subject_absence": "ABSENCE_IS_DECIDABLE"},
                         dict(self.NEGATIVE.probe_input))
        self.assertEqual(self.NEGATIVE.probe_input["observable"], {"condition": "exists"})

    def test_A_PROBE_ABS_3_same_absence_positive_existence_contract_is_UNSATISFIED(self):
        result = on_subject_absent(self.POSITIVE, observed=ABSENT)
        self.assertEqual(result, Executed(R))
        self.assertIs(contract_satisfaction(result, self.POSITIVE), ContractSatisfaction.UNSATISFIED)

    def test_B_PROBE_ABS_4_same_absence_negative_existence_contract_is_SATISFIED(self):
        result = on_subject_absent(self.NEGATIVE, observed=ABSENT)
        self.assertEqual(result, Executed(R))
        self.assertIs(contract_satisfaction(result, self.NEGATIVE), ContractSatisfaction.SATISFIED)

    def test_C_PROBE_ABS_2_requires_subject_is_INDETERMINATE_PRECONDITION_ABSENT(self):
        result = on_subject_absent(self.REQUIRES, observed=None)
        self.assertEqual(result, Executed(I, PA))
        self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(contract_satisfaction(result, self.REQUIRES), ContractSatisfaction.INDETERMINATE)
        self.assertEqual(on_subject_absent(spec("BC-VERSION"), observed=None), Executed(I, PA))  # MUST_HOLD too

    def test_C_requires_subject_refuses_a_verdict_it_cannot_have(self):
        for seen in (S, R, I):
            with self.subTest(observed=seen), self.assertRaisesRegex(InvariantError, NO_VERDICT):
                on_subject_absent(self.REQUIRES, observed=seen)

    def test_PROBE_ABS_5_one_absence_is_not_forced_to_one_satisfaction(self):
        got = {}
        for name, s in (("positive", self.POSITIVE), ("negative", self.NEGATIVE), ("requires", self.REQUIRES)):
            seen = None if s is self.REQUIRES else ABSENT
            got[name] = contract_satisfaction(on_subject_absent(s, observed=seen), s)
        self.assertEqual(got, {"positive": ContractSatisfaction.UNSATISFIED,
                               "negative": ContractSatisfaction.SATISFIED,
                               "requires": ContractSatisfaction.INDETERMINATE})

    def test_D_the_decidable_verdict_is_the_observation_never_the_declaration(self):
        for s in (self.POSITIVE, self.NEGATIVE, spec("BC-LICENSE")):
            for seen in (S, R):
                with self.subTest(spec=s.candidate_expectation, observed=seen):
                    self.assertEqual(on_subject_absent(s, observed=seen), Executed(seen))

    def test_D_decidable_absence_has_no_default_verdict(self):
        for seen in (None, I):
            with self.subTest(observed=seen), self.assertRaisesRegex(InvariantError, NO_DEFAULT):
                on_subject_absent(self.NEGATIVE, observed=seen)
        with self.assertRaises(TypeError):
            on_subject_absent(self.NEGATIVE)  # the P1 one-argument form, which inferred REFUTED, is gone
        with self.assertRaises(TypeError):
            on_subject_absent(self.NEGATIVE, R)  # the observation is named, never positional

    def test_D_no_kernel_code_infers_a_decided_verdict_from_the_absence_declaration(self):
        rule = ("NO_VERDICT_FROM_ABSENCE_DECLARATION",)
        self.assertEqual(ks.check(ROOT, rule), [])
        for src in (_P1_HELPER,
                    "from aisef2.arch.enums import BehaviorVerdict, SubjectAbsence\ndef f(s):\n"
                    "    if s.subject_absence is SubjectAbsence.ABSENCE_IS_DECIDABLE:\n"
                    "        return BehaviorVerdict.REFUTED\n",
                    "from aisef2.arch.enums import BehaviorVerdict as V, SubjectAbsence\ndef f(s):\n"
                    "    if SubjectAbsence(s.probe_input['subject_absence']) is SubjectAbsence.REQUIRES_SUBJECT:\n"
                    "        return None\n    return V.REFUTED\n",
                    "from aisef2.arch import enums\ndef f(d):\n"
                    "    return {'ABSENCE_IS_DECIDABLE': enums.BehaviorVerdict('SATISFIED')}[d]\n",
                    "from aisef2.arch.enums import BehaviorVerdict\nNO = BehaviorVerdict.REFUTED\ndef f(s):\n"
                    "    return NO if s.probe_input['subject_absence'] == 'ABSENCE_IS_DECIDABLE' else None\n",
                    "from aisef2.arch.enums import BehaviorVerdict\ndef f(s):\n"
                    "    return getattr(BehaviorVerdict, 'REFUTED') if getattr(s, 'subject_absence') else None\n"):
            with self.subTest(src=src[-60:]):
                self.assertTrue(ks.violations("aisef2/product/x.py", src, rule))
        for src in ("from aisef2.arch.enums import BehaviorVerdict, SubjectAbsence\ndef f(s):\n"
                    "    if s.subject_absence is SubjectAbsence.REQUIRES_SUBJECT:\n"
                    "        return BehaviorVerdict.INDETERMINATE\n",
                    "from aisef2.arch.enums import BehaviorVerdict\ndef observe(present):\n"
                    "    return BehaviorVerdict.SATISFIED if present else BehaviorVerdict.REFUTED\n"
                    "KEYS = ('observable', 'subject_absence')\n"):
            with self.subTest(legal=src[-60:]):
                self.assertEqual(ks.violations("aisef2/product/x.py", src, rule), [])


#: The P1 helper as accepted at 112f1d3 — a global ABSENCE_IS_DECIDABLE -> REFUTED. It must stay rejected.
_P1_HELPER = """from aisef2.arch.enums import BehaviorVerdict, SubjectAbsence
from aisef2.product.outcome import Executed, IndeterminateReason


def on_subject_absent(spec):
    return {
        SubjectAbsence.REQUIRES_SUBJECT: Executed(BehaviorVerdict.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT),
        SubjectAbsence.ABSENCE_IS_DECIDABLE: Executed(BehaviorVerdict.REFUTED),
    }[SubjectAbsence(spec.probe_input["subject_absence"])]
"""


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
