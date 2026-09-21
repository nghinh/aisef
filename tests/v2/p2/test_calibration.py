"""WP-2.2 — calibration demonstrates CONTRAST to the candidate expectation (RFC §9.1; F5). CAL-1 and its mirror.

Kill set for `calibration.py::demonstrates_contrast` and `calibration.py::calibrate`: in-memory probes over temporary
fixtures, no subprocess. The committed python_callable fixtures are exercised in test_calibration_fixtures.py.
"""

import dataclasses
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Enforcement  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.probe.calibration import (  # noqa: E402
    CONTRAST, FIXTURE_REVISION, MECHANISMS, NotQualified, ProbeCapabilityCalibration, SpecFalsifiabilityEvidence,
    calibrate, calibration_for, demonstrates_contrast, falsifiability_problems, fixture_spec,
)
from aisef2.probe.protocol import ExecutionEnv, HarnessProbe, Observation, ObservationKind  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
ENV = ExecutionEnv(sys.executable, 5, Enforcement.PARTIAL)
REQUEST = {"subject": {"kind": "file_artifact", "locator": "LICENSE"}, "stimulus": {},
           "observable": {"condition": "exists"}, "subject_absence": "ABSENCE_IS_DECIDABLE"}


class Looks(HarnessProbe):
    """Honest: SATISFIED where the checkout has the subject, REFUTED where it does not."""
    id, digest = "probe.looks", "1" * 64
    level = Enforcement.PARTIAL

    def enforcement(self):
        return self.level

    def harness_preconditions(self):
        return ("checkout",)

    def observation_class(self, spec):
        return "exists" if dict(spec.probe_input["observable"]) == {"condition": "exists"} else None

    def observe(self, spec, at, env):
        present = os.path.exists(os.path.join(at.root, spec.probe_input["subject"]["locator"]))
        return Observation(ObservationKind.OBSERVED, S if present else R)


class AlwaysRefuted(Looks):
    """CAL-1: the probe a fixed-verdict calibration would have qualified for every MUST_NOT_HOLD contract."""
    id = "probe.always_refuted"

    def observe(self, spec, at, env):
        return Observation(ObservationKind.OBSERVED, R)


class AlwaysSatisfied(Looks):
    id = "probe.always_satisfied"

    def observe(self, spec, at, env):
        return Observation(ObservationKind.OBSERVED, S)


class CannotLook(Looks):
    id = "probe.cannot_look"

    def observe(self, spec, at, env):
        return Observation(ObservationKind.HARNESS_FAILED, detail="no harness")


class _Fixtures(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.pos, self.neg = self.fixture("positive", present=True), self.fixture("negative", present=False)

    def tearDown(self):
        self.dir.cleanup()

    def fixture(self, name, *, present, request=REQUEST):
        d = pathlib.Path(self.dir.name, name)
        (d / "checkout").mkdir(parents=True)
        (d / "request.json").write_text(json.dumps(request), encoding="utf-8")
        if present:
            (d / "checkout" / "LICENSE").write_text("MIT\n", encoding="utf-8")
        return d

    def cal(self, probe, cls="exists", pos=None, neg=None):
        return calibrate(probe, cls, pos or self.pos, neg or self.neg, ENV, lambda: 1234.5)


class Contrast(unittest.TestCase):
    def test_the_counterexample_must_produce_the_opposite_verdict(self):
        self.assertEqual(CONTRAST, {S: R, R: S})
        table = {(S, R): True, (R, S): True, (S, S): False, (R, R): False, (S, I): False, (R, I): False}
        for (expectation, observed), want in table.items():
            with self.subTest(expectation=expectation, observed=observed):
                self.assertIs(demonstrates_contrast(expectation, observed), want)

    def test_an_expectation_is_satisfied_or_refuted(self):
        for bad in (I, "SATISFIED", None):
            with self.subTest(expectation=bad), self.assertRaisesRegex(InvariantError,
                                                                        "^a candidate expectation is SATISFIED or REFUTED$"):
                demonstrates_contrast(bad, R)

    def test_CAL_1_a_fixed_REFUTED_rule_would_have_passed_the_always_refuted_probe(self):
        # the rejected design: "a MUST_NOT_HOLD probe must be observed producing REFUTED"
        must_not_hold_expectation = R
        always = R
        self.assertIs(always, must_not_hold_expectation)            # the fixed rule: qualified
        self.assertFalse(demonstrates_contrast(must_not_hold_expectation, always))  # contrast: rejected


class Calibrate(_Fixtures):
    def test_an_honest_probe_is_qualified_for_its_class(self):
        rec = self.cal(Looks())
        self.assertEqual(rec, ProbeCapabilityCalibration("probe.looks", "1" * 64, "exists", str(self.pos),
                                                         str(self.neg), 1234.5))
        named = calibrate(Looks(), "exists", self.pos, self.neg, ENV, lambda: 7, names=("fx/pos", "fx/neg"))
        self.assertEqual((named.positive_fixture, named.negative_fixture, named.demonstrated_at), ("fx/pos", "fx/neg", 7.0))

    def test_CAL_1_an_always_REFUTED_prohibition_probe_is_rejected(self):
        with self.assertRaisesRegex(NotQualified, r"^probe\.always_refuted@1{12} is not qualified for 'exists': "
                                                  r"positive fixture observed .*REFUTED.* no contrast with a REFUTED "
                                                  r"expectation$"):
            self.cal(AlwaysRefuted())

    def test_an_always_SATISFIED_probe_is_rejected_for_MUST_HOLD(self):
        with self.assertRaisesRegex(NotQualified, r"negative fixture observed .*SATISFIED.* no contrast with a "
                                                  r"SATISFIED expectation$"):
            self.cal(AlwaysSatisfied())

    def test_swapped_fixtures_qualify_nothing(self):
        with self.assertRaisesRegex(NotQualified, "positive fixture .*; negative fixture "):
            self.cal(Looks(), pos=self.neg, neg=self.pos)

    def test_a_probe_that_cannot_look_is_not_qualified(self):
        with self.assertRaisesRegex(NotQualified, "positive fixture observed Unrunnable.*; negative fixture observed "
                                                  "Unrunnable"):
            self.cal(CannotLook())

    def test_refusing_to_run_is_not_a_demonstration(self):
        probe = Looks()
        probe.level = Enforcement.UNAVAILABLE
        with self.assertRaisesRegex(NotQualified, "Unrunnable"):
            self.cal(probe)

    def test_the_fixture_must_ask_for_the_class_being_calibrated(self):
        other = self.fixture("other", present=True, request={**REQUEST, "observable": {"size": 1}})
        with self.assertRaisesRegex(NotQualified, r"positive fixture asks for None, not 'exists'"):
            self.cal(Looks(), pos=other)
        with self.assertRaisesRegex(NotQualified, r"asks for 'exists', not 'returns'"):
            self.cal(Looks(), cls="returns")

    def test_the_fixture_spec_is_bound_to_the_probe_and_answers_no_contract(self):
        s = fixture_spec(Looks(), self.pos)
        self.assertEqual((s.probe_id, s.probe_digest, s.contract_id), ("probe.looks", "1" * 64, "CALIBRATION:positive"))
        self.assertEqual(dict(s.probe_input["observable"]), {"condition": "exists"})
        self.assertEqual(FIXTURE_REVISION, "0" * 40)


class Records(_Fixtures):
    def test_a_record_qualifies_only_its_probe_digest_and_class(self):
        rec = self.cal(Looks())
        self.assertIs(calibration_for([rec], "probe.looks", "1" * 64, "exists"), rec)
        for key in (("probe.other", "1" * 64, "exists"), ("probe.looks", "2" * 64, "exists"),
                    ("probe.looks", "1" * 64, "returns")):
            with self.subTest(key=key):
                self.assertIsNone(calibration_for([rec], *key))
        self.assertIsNone(calibration_for([dataclasses.asdict(rec)], "probe.looks", "1" * 64, "exists"))

    def test_the_record_shapes_are_the_rfcs(self):
        self.assertEqual([f.name for f in dataclasses.fields(ProbeCapabilityCalibration)],
                         ["probe_id", "probe_digest", "observation_class", "positive_fixture", "negative_fixture",
                          "demonstrated_at"])
        self.assertEqual([f.name for f in dataclasses.fields(SpecFalsifiabilityEvidence)],
                         ["spec_id", "semantic_hash", "mechanism", "counterexample_ref", "observed"])
        self.assertEqual(MECHANISMS, ("controlled_product_mutation", "fixture_construction", "other_qualified"))


class Falsifiability(unittest.TestCase):
    def spec(self, expectation):
        return ProductProofSpec.create(contract_id="BC-F", probe_id="probe.looks", probe_digest="1" * 64,
                                       probe_input=REQUEST, candidate_expectation=expectation, compiler_id="t",
                                       compiler_digest="c" * 64)

    def test_evidence_must_contrast_with_the_specs_expectation(self):
        for expectation, observed, ok in ((S, R, True), (R, S, True), (S, S, False), (R, R, False)):
            s = self.spec(expectation)
            ev = SpecFalsifiabilityEvidence(s.id, s.semantic_hash, "fixture_construction", "fx/counter", observed)
            with self.subTest(expectation=expectation, observed=observed):
                self.assertEqual(falsifiability_problems(ev, s) == [], ok)
        s = self.spec(R)
        wrong = SpecFalsifiabilityEvidence("PPS-other", s.semantic_hash, "fixture_construction", "fx", S)
        self.assertEqual(falsifiability_problems(wrong, s), ["the evidence is for another spec or another semantic_hash"])

    def test_the_evidence_is_typed(self):
        s = self.spec(S)
        for kw, msg in (({"mechanism": "vibes"}, "mechanism must be one of"), ({"observed": "REFUTED"}, "BehaviorVerdict"),
                        ({"counterexample_ref": ""}, "journal or fixture locator")):
            args = {"spec_id": s.id, "semantic_hash": s.semantic_hash, "mechanism": "fixture_construction",
                    "counterexample_ref": "fx", "observed": R, **kw}
            with self.subTest(kw=kw), self.assertRaisesRegex(InvariantError, msg):
                SpecFalsifiabilityEvidence(**args)


if __name__ == "__main__":
    unittest.main()
