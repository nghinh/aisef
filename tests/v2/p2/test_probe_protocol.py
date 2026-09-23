"""WP-2.1 — the probe protocol (RFC §9, §24; F5). Pure tests with in-memory probes: no subprocess.

Kill set for `protocol.py::classify_failure` and `protocol.py::run_probe`. The in-memory `FileArtifactProbe` is a second
probe kind written only against the protocol — the prototype that shows the protocol is not shaped around
python_callable (a kind that did not fit would be an F5 contradiction, not a refactor).
"""

import dataclasses
import inspect
import os
import pathlib
import sys
import tempfile
import typing
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, ProbeExecutionStatus, SubjectAbsence,
)
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ProbeMetadata, ProbeRegistry, bound_result,
    ExecutionEnv, HarnessProbe, Observation, ObservationKind, Probe, ProbeRecord, RevisionRef, classify_failure,
    run_probe,
)
from aisef2.product.outcome import (  # noqa: E402
    Executed, IndeterminateReason, InvalidSpec, Unrunnable, contract_satisfaction,
)
from aisef2.product.contract import digest  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
K = ObservationKind
SHA = "0123456789abcdef0123456789abcdef01234567"
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE


def spec(*, absence=DECIDABLE, expectation=S, probe=("probe.fake", "f" * 64), kind="file_artifact",
         locator="src/app/telemetry.py", observable=None):
    return ProductProofSpec.create(
        contract_id="BC-T", probe_id=probe[0], probe_digest=probe[1],
        probe_input={"subject": {"kind": kind, "locator": locator}, "stimulus": {},
                     "observable": observable or {"condition": "exists"}, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


class Fake(HarnessProbe):
    """Reports a fixed observation; counts how often it was asked."""
    id, digest = "probe.fake", "f" * 64

    def __init__(self, observation=None, level=Enforcement.FULL):
        self.observation, self.level, self.calls = observation or Observation(K.OBSERVED, S), level, 0

    def enforcement(self):
        return self.level

    def harness_preconditions(self):
        return ("nothing",)


    def observe(self, spec, at, env):
        self.calls += 1
        return self.observation


class FileArtifactProbe(HarnessProbe):
    """Second-kind prototype, protocol only: file_artifact with the `exists` observable, looking at a checkout."""
    id, digest = "probe.file_artifact.prototype", "a" * 64

    def enforcement(self):
        return Enforcement.PARTIAL

    def harness_preconditions(self):
        return ("checkout: the revision's checkout is a readable directory",)

    def asks(self, spec):
        return "exists" if dict(spec.probe_input["observable"]) == {"condition": "exists"} else None

    def observe(self, spec, at, env):
        if self.asks(spec) is None:
            return Observation(K.UNSUPPORTED, detail="only exists")
        if not os.path.isdir(at.root):
            return Observation(K.HARNESS_FAILED, detail="cannot inspect: no checkout")
        path = os.path.join(at.root, spec.probe_input["subject"]["locator"])
        if not os.path.exists(path):
            return Observation(K.SUBJECT_ABSENT, R, detail="positive observable over an absent file")
        return Observation(K.OBSERVED, S)


AT = RevisionRef(SHA, os.path.abspath("checkout"))


def record(**over):
    s = spec()
    fields = dict(spec_id=s.id, semantic_hash=s.semantic_hash, probe_id=Fake.id, probe_digest=Fake.digest,
                  revision=SHA, enforcement=Enforcement.PARTIAL, result=Executed(S))
    return ProbeRecord.create(**{**fields, **over})
ENV = ExecutionEnv(sys.executable, 5, Enforcement.PARTIAL)


class ObservationShape(unittest.TestCase):
    def test_a_harness_failure_or_refusal_carries_no_verdict_and_says_why(self):
        for kind in (K.HARNESS_FAILED, K.UNSUPPORTED):
            with self.subTest(kind=kind):
                for v in (S, R, I):
                    with self.assertRaisesRegex(InvariantError, "carries no verdict"):
                        Observation(kind, v, "x")
                with self.assertRaisesRegex(InvariantError, "says why"):
                    Observation(kind)
                self.assertIsNone(Observation(kind, detail="x").verdict)

    def test_a_non_controller_signal_carries_no_verdict_says_why_and_is_indeterminate(self):
        """§9.3 (V2-003): an exit by a signal the controller did not send is not an observation of the subject —
        no verdict, a reason — and the only mapping classifies it EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL),
        beside HARNESS_FAILED -> UNRUNNABLE and UNSUPPORTED -> INVALID_SPEC."""
        for v in (S, R, I):
            with self.assertRaisesRegex(InvariantError, "carries no verdict"):
                Observation(K.NON_CONTROLLER_SIGNAL, v, "signal 6")
        with self.assertRaisesRegex(InvariantError, "says why"):
            Observation(K.NON_CONTROLLER_SIGNAL)
        s = spec()
        self.assertEqual(classify_failure(s, Observation(K.NON_CONTROLLER_SIGNAL, detail="signal 6")),
                         Executed(I, IndeterminateReason.NON_CONTROLLER_SIGNAL))
        self.assertIs(classify_failure(s, Observation(K.HARNESS_FAILED, detail="x")).status,
                      ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(classify_failure(s, Observation(K.UNSUPPORTED, detail="x")).status,
                      ProbeExecutionStatus.INVALID_SPEC)

    def test_an_observed_subject_is_decided(self):
        for v in (None, I):
            with self.subTest(verdict=v), self.assertRaisesRegex(InvariantError, "SATISFIED or REFUTED"):
                Observation(K.OBSERVED, v)
        self.assertIs(Observation(K.OBSERVED, R).verdict, R)

    def test_absence_observations_are_decided_or_none(self):
        with self.assertRaisesRegex(InvariantError, "SATISFIED, REFUTED or none"):
            Observation(K.SUBJECT_ABSENT, I)
        for v in (None, S, R):
            self.assertIs(Observation(K.SUBJECT_ABSENT, v).verdict, v)
        with self.assertRaisesRegex(InvariantError, "typed kind"):
            Observation("OBSERVED", S)


class SubjectDeadline(unittest.TestCase):
    """RFC §9.2 (ARCHITECTURE-EXCEPTION-V2-002): a subject that exceeds its window is observed, never a harness failure."""

    def test_an_expired_window_carries_the_specs_verdict_and_has_no_default(self):
        for v in (None, I):
            with self.subTest(verdict=v), self.assertRaisesRegex(InvariantError, "there is no default$"):
                Observation(K.SUBJECT_DEADLINE, v)
        self.assertIs(Observation(K.SUBJECT_DEADLINE, S).verdict, S)

    def test_TIME_5_a_subject_deadline_is_EXECUTED_with_whatever_verdict_the_spec_assigned(self):
        for absence in (REQUIRES, DECIDABLE):
            for v in (S, R):
                with self.subTest(absence=absence, verdict=v):
                    r = classify_failure(spec(absence=absence), Observation(K.SUBJECT_DEADLINE, v, "window expired"))
                    self.assertEqual(r, Executed(v))
                    self.assertIsNot(r.status, ProbeExecutionStatus.UNRUNNABLE)

    def test_TIME_1_a_harness_timeout_is_UNRUNNABLE(self):
        self.assertEqual(classify_failure(spec(), Observation(K.HARNESS_FAILED, detail="harness timeout")),
                         Unrunnable("harness timeout"))


class Binding(unittest.TestCase):
    """PROBE-BIND-1/2: a decision reads a result only from a sealed record bound to its spec, revision and level."""

    def test_PROBE_BIND_1_a_bare_result_is_never_read(self):
        for bare in (Executed(S), Unrunnable("x"), InvalidSpec("y"), None, "EXECUTED"):
            with self.subTest(bare=bare), self.assertRaisesRegex(InvariantError, "^a decision reads a ProbeRecord, "
                                                                                 "never a bare ProbeResult$"):
                bound_result(bare, spec=spec(), revision=SHA, enforcement=Enforcement.PARTIAL)

    def test_a_record_releases_its_result_only_for_its_spec_revision_and_level(self):
        rec, s = record(), spec()
        self.assertEqual(bound_result(rec, spec=s, revision=SHA, enforcement=Enforcement.PARTIAL), Executed(S))
        other = spec(locator="src/app/other.py")
        with self.assertRaisesRegex(InvariantError, f"^the record answers {s.id}, not {other.id}$"):
            bound_result(rec, spec=other, revision=SHA, enforcement=Enforcement.PARTIAL)
        with self.assertRaisesRegex(InvariantError, f"^the record was measured at {SHA[:12]}, not {'f' * 12}$"):
            bound_result(rec, spec=s, revision="f" * 40, enforcement=Enforcement.PARTIAL)

    def test_PROBE_BIND_2_enforcement_changes_identity_and_blocks_reuse(self):
        partial, full = record(enforcement=Enforcement.PARTIAL), record(enforcement=Enforcement.FULL)
        self.assertNotEqual(partial.record_digest, full.record_digest)
        self.assertNotEqual(partial.comparability, full.comparability)
        with self.assertRaisesRegex(InvariantError, "^the record ran under PARTIAL, not FULL: not comparable"):
            bound_result(partial, spec=spec(), revision=SHA, enforcement=Enforcement.FULL)
        with self.assertRaisesRegex(InvariantError, "^the record ran under FULL, not PARTIAL: not comparable"):
            bound_result(full, spec=spec(), revision=SHA, enforcement=Enforcement.PARTIAL)

    def test_a_sealed_record_cannot_lose_or_swap_its_binding(self):
        rec = record()
        for field, value in (("enforcement", Enforcement.FULL), ("result", Executed(R)), ("revision", "f" * 40),
                             ("probe_digest", "e" * 64), ("spec_id", "PPS-other")):
            with self.subTest(field=field), self.assertRaisesRegex(InvariantError, "an edited record is a new record$"):
                dataclasses.replace(rec, **{field: value})
        self.assertRegex(rec.record_digest, "^[0-9a-f]{64}$")
        self.assertEqual(record(), rec)
        self.assertEqual(rec.comparability, record(revision="f" * 40, result=Executed(R)).comparability)
        self.assertNotEqual(rec.comparability, record(probe_digest="e" * 64).comparability)
        self.assertNotEqual(rec.comparability, record(semantic_hash="h" * 64).comparability)
        self.assertNotEqual(rec.comparability, record(probe_id="probe.other").comparability)
        # the identity is named, not positional: persisted evidence compares it across versions
        self.assertEqual(rec.comparability, digest({"semantic_hash": rec.semantic_hash, "probe_id": rec.probe_id,
                                                    "probe_digest": rec.probe_digest,
                                                    "enforcement": rec.enforcement}))


class Registry(unittest.TestCase):
    """PROBE-META-1: observation classes come from harness metadata keyed by probe identity and digest."""

    def test_the_class_is_the_registered_metadatas_for_that_exact_digest(self):
        reg = ProbeRegistry([ProbeMetadata("probe.fake", "f" * 64, lambda s: "exists")])
        self.assertEqual(reg.observation_class("probe.fake", "f" * 64, spec()), "exists")
        self.assertIsNone(reg.observation_class("probe.fake", "e" * 64, spec()))
        self.assertIsNone(reg.observation_class("probe.other", "f" * 64, spec()))
        self.assertIsNone(ProbeRegistry().observation_class("probe.fake", "f" * 64, spec()))

    def test_a_registry_holds_typed_metadata_once_per_digest(self):
        m = ProbeMetadata("probe.fake", "f" * 64, lambda s: "exists")
        with self.assertRaisesRegex(InvariantError, "registered twice$"):
            ProbeRegistry([m, m])
        with self.assertRaisesRegex(InvariantError, "^the registry holds ProbeMetadata$"):
            ProbeRegistry([("probe.fake", "f" * 64)])

    def test_PROBE_META_1_a_protocol_only_probe_runs_without_the_base_class(self):
        class Bare:  # satisfies the frozen Probe protocol; inherits nothing from the harness
            id, digest = "probe.bare", "b" * 64

            def enforcement(self):
                return Enforcement.PARTIAL

            def harness_preconditions(self):
                return ()

            def evaluate(self, spec, at, env):
                return Executed(R)
        probe = Bare()
        self.assertIsInstance(probe, Probe)
        self.assertNotIsInstance(probe, HarnessProbe)
        rec = run_probe(probe, spec(probe=("probe.bare", "b" * 64)), AT, ENV)
        self.assertEqual(bound_result(rec, spec=spec(probe=("probe.bare", "b" * 64)), revision=SHA,
                                      enforcement=Enforcement.PARTIAL), Executed(R))


class ClassifyFailure(unittest.TestCase):
    def test_a_harness_failure_is_UNRUNNABLE_with_no_verdict(self):
        r = classify_failure(spec(), Observation(K.HARNESS_FAILED, detail="interpreter absent"))
        self.assertEqual(r, Unrunnable("interpreter absent"))
        self.assertFalse(hasattr(r, "behavior_verdict"))

    def test_an_unsupported_request_is_INVALID_SPEC(self):
        self.assertEqual(classify_failure(spec(), Observation(K.UNSUPPORTED, detail="no such class")),
                         InvalidSpec("no such class"))

    def test_an_observation_is_EXECUTED_with_its_verdict(self):
        for v in (S, R):
            with self.subTest(verdict=v):
                self.assertEqual(classify_failure(spec(), Observation(K.OBSERVED, v)), Executed(v))

    def test_requires_subject_absent_is_INDETERMINATE_whatever_the_probe_offered(self):
        for offered in (None, S, R):
            with self.subTest(offered=offered):
                self.assertEqual(classify_failure(spec(absence=REQUIRES), Observation(K.SUBJECT_ABSENT, offered)),
                                 Executed(I, PA))

    def test_decidable_absence_takes_the_observables_verdict_never_a_default(self):
        for v in (S, R):
            with self.subTest(verdict=v):
                self.assertEqual(classify_failure(spec(absence=DECIDABLE), Observation(K.SUBJECT_ABSENT, v)),
                                 Executed(v))
        with self.assertRaisesRegex(InvariantError, "there is no default"):
            classify_failure(spec(absence=DECIDABLE), Observation(K.SUBJECT_ABSENT))

    def test_absence_is_never_UNRUNNABLE(self):
        for absence in (REQUIRES, DECIDABLE):
            with self.subTest(absence=absence):
                r = classify_failure(spec(absence=absence), Observation(K.SUBJECT_ABSENT, R))
                self.assertIs(r.status, ProbeExecutionStatus.EXECUTED)

    def test_only_a_typed_observation_is_classified(self):
        for bad in (None, "OBSERVED", Executed(S), Unrunnable("x")):
            with self.subTest(bad=bad), self.assertRaisesRegex(InvariantError, "typed Observation"):
                classify_failure(spec(), bad)


class RunProbe(unittest.TestCase):
    def test_enforcement_and_identity_are_bound_into_every_record(self):
        for obs in (Observation(K.OBSERVED, S), Observation(K.HARNESS_FAILED, detail="x"),
                    Observation(K.UNSUPPORTED, detail="y"), Observation(K.SUBJECT_ABSENT, R)):
            with self.subTest(kind=obs.kind):
                s = spec()
                rec = run_probe(Fake(obs, Enforcement.PARTIAL), s, AT, ENV)
                self.assertEqual((rec.spec_id, rec.semantic_hash, rec.probe_id, rec.probe_digest, rec.revision,
                                  rec.enforcement), (s.id, s.semantic_hash, Fake.id, Fake.digest, SHA,
                                                     Enforcement.PARTIAL))
                self.assertEqual(rec.result, classify_failure(s, obs))

    def test_it_refuses_rather_than_degrades(self):
        for level, required in ((Enforcement.PARTIAL, Enforcement.FULL), (Enforcement.UNAVAILABLE, Enforcement.PARTIAL),
                                (Enforcement.UNAVAILABLE, Enforcement.FULL)):
            with self.subTest(level=level, required=required):
                probe = Fake(level=level)
                rec = run_probe(probe, spec(), AT, ExecutionEnv(sys.executable, 5, required))
                self.assertEqual(probe.calls, 0)
                self.assertIs(rec.result.status, ProbeExecutionStatus.UNRUNNABLE)
                self.assertEqual(rec.result.detail, f"enforcement {level.value} cannot honour the required "
                                                    f"{required.value}; refused, not degraded")
                self.assertIs(rec.enforcement, level)

    def test_a_level_at_or_above_the_requirement_runs(self):
        for level, required in ((Enforcement.FULL, Enforcement.FULL), (Enforcement.FULL, Enforcement.PARTIAL),
                                (Enforcement.PARTIAL, Enforcement.PARTIAL)):
            with self.subTest(level=level, required=required):
                probe = Fake(level=level)
                rec = run_probe(probe, spec(), AT, ExecutionEnv(sys.executable, 5, required))
                self.assertEqual((probe.calls, rec.result), (1, Executed(S)))

    def test_a_spec_bound_to_another_probe_or_digest_is_refused_unlooked(self):
        for bound in (("probe.other", "f" * 64), ("probe.fake", "e" * 64)):
            with self.subTest(bound=bound):
                probe = Fake()
                rec = run_probe(probe, spec(probe=bound), AT, ENV)
                self.assertEqual(probe.calls, 0)
                self.assertEqual(rec.result, InvalidSpec(f"the spec is bound to {bound[0]}@{bound[1][:12]}, "
                                                         f"not probe.fake@{'f' * 12}"))

    def test_a_developer_test_artefact_in_the_probe_input_is_refused_unlooked(self):
        for locator in ("tests/test_app.py", "app.tests.helpers:x", "pkg.test_cli:main", "src/app_test.py"):
            with self.subTest(locator=locator):
                probe = Fake()
                rec = run_probe(probe, spec(locator=locator), AT, ENV)
                self.assertEqual(probe.calls, 0)
                self.assertIs(rec.result.status, ProbeExecutionStatus.INVALID_SPEC)
                self.assertRegex(rec.result.detail, "^the probe input names a developer test artefact .*invariant IX")

    def test_a_probe_must_answer_with_a_typed_result_and_a_typed_level(self):
        class Rogue(Fake):
            def evaluate(self, spec, at, env):
                return BehaviorVerdict.SATISFIED
        with self.assertRaisesRegex(InvariantError, "returned BehaviorVerdict, not a ProbeResult"):
            run_probe(Rogue(), spec(), AT, ENV)
        with self.assertRaisesRegex(InvariantError, "real enforcement level"):
            run_probe(Fake(level="FULL"), spec(), AT, ENV)
        with self.assertRaisesRegex(InvariantError, "^not a probe$"):
            run_probe(object(), spec(), AT, ENV)
        for args in ((spec().to_json(), AT, ENV), (spec(), SHA, ENV), (spec(), AT, {"interpreter": "x"})):
            with self.subTest(args=type(args[0]).__name__), self.assertRaisesRegex(InvariantError, "runs a ProductProofSpec"):
                run_probe(Fake(), *args)

    def test_a_record_holds_a_typed_result_and_level(self):
        with self.assertRaisesRegex(InvariantError, "typed ProbeResult"):
            record(result=S)
        with self.assertRaisesRegex(InvariantError, "enforcement level"):
            record(enforcement="FULL")


class ApiShape(unittest.TestCase):
    """Invariant IX: the probe API has no way to take a developer-authored path, command or test."""

    def test_the_protocol_members_and_signature_are_the_rfcs(self):
        self.assertEqual(list(typing.get_type_hints(Probe)), ["id", "digest"])
        self.assertEqual(list(inspect.signature(Probe.evaluate).parameters), ["self", "spec", "at", "env"])
        self.assertEqual([m for m in ("enforcement", "harness_preconditions", "evaluate") if hasattr(Probe, m)],
                         ["enforcement", "harness_preconditions", "evaluate"])
        self.assertIsInstance(Fake(), Probe)

    def test_revision_and_env_carry_no_developer_input(self):
        self.assertEqual([f.name for f in dataclasses.fields(RevisionRef)], ["sha", "root"])
        self.assertEqual([f.name for f in dataclasses.fields(ExecutionEnv)],
                         ["interpreter", "timeout_s", "required_enforcement"])
        for extra in ("test_path", "command", "script"):
            with self.subTest(extra=extra), self.assertRaises(TypeError):
                ExecutionEnv(sys.executable, 5, Enforcement.FULL, **{extra: "tests/test_x.py"})

    def test_a_revision_is_a_full_sha(self):
        for bad in (SHA[:12], SHA.upper(), SHA + "0", "", None):
            with self.subTest(sha=bad), self.assertRaisesRegex(InvariantError, "full 40-hex SHA"):
                RevisionRef(bad, os.path.abspath("checkout"))
        for root in ("", "checkout", "./checkout", None):
            with self.subTest(root=root), self.assertRaisesRegex(InvariantError, "as an absolute path"):
                RevisionRef(SHA, root)

    def test_an_env_requires_real_enforcement_and_a_positive_timeout(self):
        with self.assertRaisesRegex(InvariantError, "FULL or PARTIAL"):
            ExecutionEnv(sys.executable, 5, Enforcement.UNAVAILABLE)
        for t in (0, -1, True, "5"):
            with self.subTest(timeout=t), self.assertRaisesRegex(InvariantError, "positive number"):
                ExecutionEnv(sys.executable, t, Enforcement.FULL)

    def test_evaluate_is_classify_failure_of_observe(self):
        obs = Observation(K.SUBJECT_ABSENT, R)
        self.assertEqual(Fake(obs).evaluate(spec(absence=REQUIRES), AT, ENV), Executed(I, PA))
        self.assertEqual(Fake(obs).evaluate(spec(absence=DECIDABLE), AT, ENV), Executed(R))


class SecondKindPrototype(unittest.TestCase):
    """The protocol carries a second kind unchanged; the RFC's own file examples (§7, NEG-2) go through it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.at = RevisionRef(SHA, self.dir.name)
        self.probe = FileArtifactProbe()

    def tearDown(self):
        self.dir.cleanup()

    def run_(self, s):
        return run_probe(self.probe, s, self.at, ENV).result

    def test_file_X_must_exist_and_a_forbidden_module_must_not(self):
        ident = (self.probe.id, self.probe.digest)
        must, must_not = spec(probe=ident, expectation=S), spec(probe=ident, expectation=R)
        requires = spec(probe=ident, absence=REQUIRES)
        got = {n: contract_satisfaction(self.run_(s), s) for n, s in (("must", must), ("must_not", must_not),
                                                                      ("requires", requires))}
        self.assertEqual(got, {"must": ContractSatisfaction.UNSATISFIED, "must_not": ContractSatisfaction.SATISFIED,
                               "requires": ContractSatisfaction.INDETERMINATE})
        path = pathlib.Path(self.dir.name, "src/app/telemetry.py")
        path.parent.mkdir(parents=True)
        path.write_text("")
        got = {n: contract_satisfaction(self.run_(s), s) for n, s in (("must", must), ("must_not", must_not))}
        self.assertEqual(got, {"must": ContractSatisfaction.SATISFIED, "must_not": ContractSatisfaction.UNSATISFIED})

    def test_its_harness_failure_and_refusal_are_typed_the_same_way(self):
        ident = (self.probe.id, self.probe.digest)
        gone = RevisionRef(SHA, os.path.join(self.dir.name, "missing"))
        self.assertIs(run_probe(self.probe, spec(probe=ident), gone, ENV).result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(self.run_(spec(probe=ident, observable={"size": 3})).status, ProbeExecutionStatus.INVALID_SPEC)


if __name__ == "__main__":
    unittest.main()
