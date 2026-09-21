"""WP-2.3 — PlanObligation and StaticPlanAdmission (RFC §11, §12; F6). Q0/Q1 run the engine on fixtures only.

Kill set for `static_admission.py::admit` and the nine check functions. The world below is a fixture: requirements,
approved contracts, their committed spec derivation, the harness catalogue and probe calibration records.
"""

import dataclasses
import importlib.util
import inspect
import pathlib
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole as Role, ParentExpectation as PE, Polarity, SubjectAbsence  # noqa: E402
from aisef2.arch.enums import SubjectKind  # noqa: E402
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.plan import static_admission as sa  # noqa: E402
from aisef2.plan.obligation import (  # noqa: E402
    EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanError, PlanObligation, PlanQualityPolicy,
)
from aisef2.probe.calibration import ProbeCapabilityCalibration  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402

_s = importlib.util.spec_from_file_location("p2_ks_static", ROOT / "validation" / "v2" / "kernel_static_checks.py")
ks = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ks)

P = PythonCallableProbe()
BASELINE = "0123456789abcdef0123456789abcdef01234567"
ENGINE = sa.StaticPlanAdmissionEngine()


def world(*, extra_requirement=False, drop_approval_for=None, catalogue=None, calibrated=("exists", "returns")):
    reqs = {r.id: r for r in (Requirement.create(id="REQ-1", text="adds", source="req.md"),
                              Requirement.create(id="REQ-2", text="no telemetry", source="req.md"))}
    if extra_requirement:
        reqs["REQ-9"] = Requirement.create(id="REQ-9", text="uncovered", source="req.md")
    contracts = {c.id: c for c in (
        BehaviorContract.create(id="BC-ADD", requirement_ids=("REQ-1",),
                                subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"), stimulus={"args": [1, 2]},
                                observable={"returns": 3}, polarity=Polarity.MUST_HOLD,
                                subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="adds"),
        BehaviorContract.create(id="BC-NO-TEL", requirement_ids=("REQ-2",),
                                subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.telemetry:send"), stimulus={},
                                observable={"condition": "exists"}, polarity=Polarity.MUST_NOT_HOLD,
                                subject_absence=SubjectAbsence.ABSENCE_IS_DECIDABLE, rationale="forbidden"))}
    approvals = tuple(ContractApproval(rid, reqs[rid].requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
                      for c in contracts.values() for rid in c.requirement_ids if c.id != drop_approval_for)
    all_approvals = tuple(ContractApproval(rid, reqs[rid].requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
                          for c in contracts.values() for rid in c.requirement_ids)
    refs = {SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, P.digest)}
    specs = {}
    for c in contracts.values():
        s = compile_spec(c, requirements=reqs, approvals=all_approvals, probes=refs)
        specs[s.id] = s
    cals = tuple(ProbeCapabilityCalibration(P.id, P.digest, cls, "fx/pos", "fx/neg", 1.0) for cls in calibrated)
    inputs = sa.AdmissionInputs(reqs, contracts, approvals, specs, catalogue or {SubjectKind.PYTHON_CALLABLE: P}, cals)
    by_contract = {s.contract_id: s.id for s in specs.values()}
    return inputs, by_contract


INPUTS, SPEC = world()


def ob(cid, spec, story, role, expected=None, deps=()):
    return PlanObligation(cid, SPEC.get(spec, spec), story, role, expected or EXPECTED_AT_PARENT[role], tuple(deps),
                          "why this story owns it")


GOOD = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE),
        ob("C2", "BC-NO-TEL", "S1", Role.VERIFY),
        ob("C3", "BC-ADD", "S2", Role.PRESERVE, deps=("C1",)),
        ob("C4", "BC-NO-TEL", "S2", Role.INTRODUCE, deps=("C2",)))


def plan(obligations=GOOD, policy=NOT_PREREGISTERED, pid="PLAN-1"):
    return Plan.create(id=pid, baseline=BASELINE, obligations=tuple(obligations), plan_quality_policy=policy)


def failing(result):
    return {c.name: list(c.problems) for c in result.checks if not c.passed}


class Shapes(unittest.TestCase):
    def test_plan_obligation_fields_are_the_rfcs(self):
        self.assertEqual([f.name for f in dataclasses.fields(PlanObligation)],
                         ["criterion_id", "product_proof_spec_id", "story_id", "role", "expected_parent", "depends_on",
                          "ownership_rationale"])
        self.assertEqual([f.name for f in dataclasses.fields(Plan)],
                         ["id", "baseline", "obligations", "plan_quality_policy", "plan_hash"])
        self.assertEqual([f.name for f in dataclasses.fields(sa.StaticPlanAdmissionResult)],
                         ["plan_id", "engine_digest", "checks", "admitted", "result_digest"])

    def test_the_expected_parent_is_a_satisfaction_expectation_never_a_verdict(self):
        with self.assertRaisesRegex(PlanError, "never a verdict"):
            PlanObligation("C", "PPS-x", "S", Role.INTRODUCE, "REFUTED_AT_PARENT", (), "r")
        with self.assertRaisesRegex(PlanError, "tuple of criterion ids"):
            PlanObligation("C", "PPS-x", "S", Role.INTRODUCE, PE.UNSATISFIED_AT_PARENT, "C0", "r")
        with self.assertRaisesRegex(PlanError, "story_id must be non-empty"):
            PlanObligation("C", "PPS-x", " ", Role.INTRODUCE, PE.UNSATISFIED_AT_PARENT, (), "r")

    def test_plan_hash_binds_everything_and_the_baseline_is_a_full_sha(self):
        a, b = plan(), plan(GOOD[:3] + (dataclasses.replace(GOOD[3], ownership_rationale="reworded"),))
        self.assertNotEqual(a.plan_hash, b.plan_hash)
        with self.assertRaisesRegex(PlanError, "an edited plan is a new plan"):
            dataclasses.replace(a, id="PLAN-2")
        with self.assertRaisesRegex(PlanError, "full 40-hex SHA"):
            Plan.create(id="P", baseline=BASELINE[:12], obligations=GOOD, plan_quality_policy=NOT_PREREGISTERED)
        with self.assertRaisesRegex(PlanError, "at least one PlanObligation"):
            plan(())

    def test_plan_quality_policy_has_no_universal_threshold(self):
        self.assertEqual(NOT_PREREGISTERED, PlanQualityPolicy(None, None, None))
        for bad in ((1.5, None, None), (None, -1, None), (None, None, True), ("0.1", None, None)):
            with self.subTest(policy=bad), self.assertRaises(PlanError):
                PlanQualityPolicy(*bad)


class Admission(unittest.TestCase):
    def test_a_well_formed_plan_is_admitted_with_a_stable_digest(self):
        r = ENGINE.admit(plan(), INPUTS)
        self.assertTrue(r.admitted, failing(r))
        self.assertEqual([c.name for c in r.checks], [n for n, _ in sa.CHECKS])
        self.assertEqual(len(r.checks), 9)
        self.assertEqual((r.plan_id, r.engine_digest), ("PLAN-1", sa.StaticPlanAdmissionEngine.digest))
        self.assertEqual(ENGINE.admit(plan(), INPUTS), r)
        self.assertRegex(r.result_digest, "^[0-9a-f]{64}$")
        self.assertEqual(sa.require_admitted(plan(), INPUTS), r)

    def test_1_requirement_coverage(self):
        inputs, _ = world(extra_requirement=True)
        self.assertEqual(failing(ENGINE.admit(plan(), inputs)),
                         {"requirement_coverage": ["requirement REQ-9 maps to no BehaviorContract"]})

    def test_2_contract_spec_integrity(self):
        stale = {k: v for k, v in INPUTS.specs.items() if v.contract_id != "BC-ADD"}
        old = compile_spec(INPUTS.contracts["BC-ADD"], requirements=INPUTS.requirements, approvals=INPUTS.approvals,
                           probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, "0" * 64)})
        got = failing(ENGINE.admit(plan([ob("C1", old.id, "S1", Role.INTRODUCE)]),
                                   dataclasses.replace(INPUTS, specs={**stale, old.id: old})))
        self.assertRegex(got["contract_spec_integrity"][0], "^contract BC-ADD: committed specs .* differ from its derivation")
        missing = failing(ENGINE.admit(plan([ob("C2", "BC-NO-TEL", "S1", Role.VERIFY)]),
                                       dataclasses.replace(INPUTS, specs=stale)))
        self.assertRegex(missing["contract_spec_integrity"][0], r"^contract BC-ADD: committed specs \[\] differ")
        inputs, _ = world(drop_approval_for="BC-ADD")
        self.assertRegex(failing(ENGINE.admit(plan(), inputs))["contract_spec_integrity"][0],
                         "^contract BC-ADD does not compile")

    def test_3_ownership(self):
        got = failing(ENGINE.admit(plan(GOOD + (ob("C5", "BC-ADD", "S3", Role.INTRODUCE, deps=("C3",)),)), INPUTS))
        self.assertIn(f"spec {SPEC['BC-ADD']} has 2 INTRODUCE owners", got["ownership"])
        got = failing(ENGINE.admit(plan(GOOD + (ob("C2", "BC-NO-TEL", "S2", Role.VERIFY),)), INPUTS))
        self.assertIn("criterion C2 belongs to 2 stories ['S1', 'S2']", got["ownership"])

    def test_4_dependency_dag(self):
        got = failing(ENGINE.admit(plan(GOOD[:3] + (ob("C4", "BC-NO-TEL", "S2", Role.INTRODUCE, deps=("C9",)),)), INPUTS))
        self.assertEqual(got["dependency_dag"], ["criterion C4 depends on C9, which does not resolve"])
        cyclic = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE, deps=("C3",)),) + GOOD[1:]
        got = failing(ENGINE.admit(plan(cyclic), INPUTS))
        self.assertEqual(got["dependency_dag"], ["criterion dependencies form a cycle: C1 -> C3 -> C1"])
        selfdep = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE, deps=("C1",)),) + GOOD[1:]
        self.assertEqual(failing(ENGINE.admit(plan(selfdep), INPUTS))["dependency_dag"],
                         ["criterion dependencies form a cycle: C1 -> C1"])

    def test_5_contradictions(self):
        odd = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE, expected=PE.SATISFIED_AT_PARENT),) + GOOD[1:]
        self.assertIn("criterion C1: role INTRODUCE with expected SATISFIED_AT_PARENT has no §13 routing row",
                      failing(ENGINE.admit(plan(odd), INPUTS))["contradictions"])
        same_story = GOOD + (ob("C5", "BC-ADD", "S1", Role.PRESERVE),)
        self.assertIn(f"story S1 asserts incompatible parent expectations ['SATISFIED_AT_PARENT', "
                      f"'UNSATISFIED_AT_PARENT'] for spec {SPEC['BC-ADD']}",
                      failing(ENGINE.admit(plan(same_story), INPUTS))["contradictions"])
        unordered = GOOD[:2] + (ob("C3", "BC-ADD", "S2", Role.PRESERVE), ob("C4", "BC-NO-TEL", "S2", Role.INTRODUCE))
        self.assertEqual(failing(ENGINE.admit(plan(unordered), INPUTS))["contradictions"],
                         [f"story S2 PRESERVEs spec {SPEC['BC-ADD']} without being ordered after story S1, which "
                          "INTRODUCEs it"])
        before = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE, deps=("C3",)), GOOD[1],
                  ob("C3", "BC-ADD", "S2", Role.PRESERVE), ob("C4", "BC-NO-TEL", "S2", Role.INTRODUCE))
        self.assertNotIn("plan_structure", failing(ENGINE.admit(plan(before), INPUTS)))  # S1 after S2: a real order
        self.assertIn(f"story S2 PRESERVEs spec {SPEC['BC-ADD']} without being ordered after story S1, which "
                      "INTRODUCEs it", failing(ENGINE.admit(plan(before), INPUTS))["contradictions"])

    def test_6_proof_capability_catches_scenario_D_statically(self):
        class Moved(PythonCallableProbe):
            digest = "d" * 64
        got = failing(ENGINE.admit(plan(), dataclasses.replace(INPUTS, catalogue={SubjectKind.PYTHON_CALLABLE: Moved()})))
        self.assertEqual(got["proof_capability"],
                         [f"spec {SPEC[c]}: bound to {P.id}@{P.digest[:12]}, the harness has @{'d' * 12} (scenario D)"
                          for c in sorted(SPEC, key=lambda c: SPEC[c])])
        class Other(PythonCallableProbe):
            id = "probe.other"
        got = failing(ENGINE.admit(plan(), dataclasses.replace(INPUTS, catalogue={SubjectKind.PYTHON_CALLABLE: Other()})))
        self.assertIn(f"spec {SPEC['BC-ADD']}: probe {P.id} does not resolve in the harness catalogue",
                      got["proof_capability"])

    def test_7_traceability(self):
        inputs, _ = world(drop_approval_for="BC-NO-TEL")
        got = failing(ENGINE.admit(plan(), inputs))
        self.assertRegex(got["traceability"][0], "^criterion C2: contract BC-NO-TEL is not approved")
        no_contract = dataclasses.replace(INPUTS, contracts={"BC-ADD": INPUTS.contracts["BC-ADD"]})
        got = failing(ENGINE.admit(plan(), no_contract))
        self.assertIn(f"criterion C2: spec {SPEC['BC-NO-TEL']} comes from no known contract", got["traceability"])

    def test_8_plan_structure(self):
        got = failing(ENGINE.admit(plan(GOOD + (ob("C5", "PPS-nowhere", "S3", Role.VERIFY),)), INPUTS))
        self.assertEqual(got["plan_structure"],
                         ["criterion C5 is an orphan: spec PPS-nowhere is not in the committed derivation"])
        story_cycle = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE), ob("C2", "BC-NO-TEL", "S1", Role.VERIFY, deps=("C4",)),
                       ob("C3", "BC-ADD", "S2", Role.PRESERVE, deps=("C1",)), ob("C4", "BC-NO-TEL", "S2", Role.INTRODUCE))
        got = failing(ENGINE.admit(plan(story_cycle), INPUTS))
        self.assertNotIn("dependency_dag", got)
        self.assertEqual(got["plan_structure"], ["stories form a cycle: S1 -> S2 -> S1"])

    def test_9_probe_calibration(self):
        inputs, _ = world(calibrated=("exists",))
        self.assertEqual(failing(ENGINE.admit(plan(), inputs)),
                         {"probe_calibration": [f"spec {SPEC['BC-ADD']}: no ProbeCapabilityCalibration for "
                                                f"{P.id}@{P.digest[:12]} class 'returns'"]})
        wrong_digest = dataclasses.replace(INPUTS, calibrations=tuple(
            dataclasses.replace(c, probe_digest="e" * 64) for c in INPUTS.calibrations))
        self.assertEqual(len(failing(ENGINE.admit(plan(), wrong_digest))["probe_calibration"]), 2)

        class Blind(PythonCallableProbe):
            def observation_class(self, spec):
                return None
        blind = dataclasses.replace(INPUTS, catalogue={SubjectKind.PYTHON_CALLABLE: Blind()})
        self.assertIn(f"spec {SPEC['BC-ADD']}: {P.id} does not support the observation it asks for",
                      failing(ENGINE.admit(plan(), blind))["probe_calibration"])

    def test_a_plan_that_is_not_admitted_cannot_freeze(self):
        inputs, _ = world(extra_requirement=True)
        with self.assertRaisesRegex(sa.PlanNotAdmitted, r"^plan PLAN-1 is not admitted — 1\. requirement_coverage: "
                                                        r"requirement REQ-9 maps to no BehaviorContract$"):
            sa.require_admitted(plan(), inputs)


class Canonical(unittest.TestCase):
    """Problems and cycles come out in one canonical order, whatever order the plan and its inputs list things in."""

    def test_requirements_and_contracts_are_reported_sorted(self):
        inputs, _ = world(extra_requirement=True)
        reqs = {**inputs.requirements, "REQ-8": Requirement.create(id="REQ-8", text="also uncovered", source="r")}
        self.assertEqual(list(reqs)[-2:], ["REQ-9", "REQ-8"])  # listed out of order
        backwards = dataclasses.replace(inputs, requirements=reqs,
                                        contracts=dict(reversed(list(inputs.contracts.items()))), specs={})
        self.assertEqual(sa.check_requirement_coverage(plan(), backwards),
                         ["requirement REQ-8 maps to no BehaviorContract", "requirement REQ-9 maps to no BehaviorContract"])
        self.assertEqual([p.split(":")[0] for p in sa.check_contract_spec_integrity(plan(), backwards)],
                         ["contract BC-ADD", "contract BC-NO-TEL"])

    def test_a_contract_with_several_committed_specs_lists_them_sorted(self):
        extra = compile_spec(INPUTS.contracts["BC-ADD"], requirements=INPUTS.requirements, approvals=INPUTS.approvals,
                             probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, "0" * 64)})
        ids = sorted([SPEC["BC-ADD"], extra.id])
        specs = {sid: ({**INPUTS.specs, extra.id: extra})[sid] for sid in [*reversed(ids), SPEC["BC-NO-TEL"]]}
        got = sa.check_contract_spec_integrity(plan(), dataclasses.replace(INPUTS, specs=specs))
        self.assertEqual(got, [f"contract BC-ADD: committed specs {ids} differ from its derivation {SPEC['BC-ADD']}"])

    def test_stories_and_expectations_are_listed_sorted(self):
        spread = tuple(ob("C1", "BC-ADD", s, Role.INTRODUCE) for s in ("S3", "S1", "S2"))
        self.assertEqual(sa.check_ownership(plan(spread), INPUTS)[0], "criterion C1 belongs to 3 stories ['S1', 'S2', 'S3']")

    def test_specs_are_visited_sorted(self):
        order = sorted(SPEC.values())
        backwards = tuple(ob(f"C{i}", sid, "S1", Role.VERIFY) for i, sid in enumerate(reversed(order)))

        class Moved(PythonCallableProbe):
            digest = "d" * 64
        moved = dataclasses.replace(INPUTS, catalogue={SubjectKind.PYTHON_CALLABLE: Moved()})
        self.assertEqual([p.split(":")[0] for p in sa.check_proof_capability(plan(backwards), moved)],
                         [f"spec {s}" for s in order])
        uncalibrated = dataclasses.replace(INPUTS, calibrations=())
        self.assertEqual([p.split(":")[0] for p in sa.check_probe_calibration(plan(backwards), uncalibrated)],
                         [f"spec {s}" for s in order])

    def test_the_cycle_reported_does_not_depend_on_listing_order(self):
        # two cycles: A -> B -> A and Z -> Y -> Z, listed Z first; successors listed in reverse
        graph = {"Z": {"Y": None}, "Y": {"Z": None}, "B": {"A": None}, "A": {"C": None, "B": None}, "C": {}}
        self.assertEqual(sa._cycle(graph), ["A", "B", "A"])
        self.assertEqual(sa._cycle({"A": {"D": None, "B": None}, "B": {"B": None}, "D": {"D": None}}), ["B", "B"])
        self.assertEqual(sa._cycle({"A": {"M": None}, "M": {"Z": None, "B": None}, "B": {"B": None}, "Z": {"Z": None}}),
                         ["B", "B"])
        self.assertEqual(sa._cycle({"R": {"S": None}, "S": {}}), None)

    def test_story_order_is_transitive_and_a_bool(self):
        chain = (ob("C1", "BC-ADD", "S1", Role.INTRODUCE), ob("C2", "BC-NO-TEL", "S2", Role.INTRODUCE, deps=("C1",)),
                 ob("C3", "BC-ADD", "S3", Role.PRESERVE, deps=("C2",)))
        g = sa.story_graph(plan(chain))
        self.assertEqual(g, {"S1": {}, "S2": {"S1": None}, "S3": {"S2": None}})
        self.assertIs(sa.depends_on_story(g, "S3", "S1"), True)
        self.assertIs(sa.depends_on_story(g, "S1", "S3"), False)
        self.assertNotIn("contradictions", failing(ENGINE.admit(plan(chain), INPUTS)))
        diamond = {"D": {"B": None, "C": None}, "B": {"A": None}, "C": {"A": None}, "A": {}}
        self.assertIs(sa.depends_on_story(diamond, "D", "A"), True)
        self.assertIs(sa.depends_on_story({"X": {"X": None}}, "X", "Y"), False)

    def test_a_result_is_immutable(self):
        r = ENGINE.admit(plan(), INPUTS)
        self.assertTrue(all(isinstance(c.problems, tuple) for c in r.checks))
        self.assertIsInstance(r.checks, tuple)


class StaticOnly(unittest.TestCase):
    def test_the_engine_executes_no_probe_and_no_process(self):
        boom = mock.Mock(side_effect=AssertionError("executed"))
        with mock.patch.object(PythonCallableProbe, "observe", boom), \
                mock.patch.object(PythonCallableProbe, "evaluate", boom), \
                mock.patch("aisef2.probe.protocol.run_probe", boom), mock.patch.object(subprocess, "run", boom), \
                mock.patch.object(subprocess, "Popen", boom):
            self.assertTrue(ENGINE.admit(plan(), INPUTS).admitted)
        boom.assert_not_called()

    def test_the_engine_never_invents_a_parent_sha(self):
        self.assertEqual(list(inspect.signature(ENGINE.admit).parameters), ["plan", "inputs"])
        self.assertEqual([f.name for f in dataclasses.fields(sa.AdmissionInputs)],
                         ["requirements", "contracts", "approvals", "specs", "catalogue", "calibrations"])
        text = repr(ENGINE.admit(plan(), INPUTS))
        self.assertEqual(set(re.findall(r"\b[0-9a-f]{40}\b", text)) - {BASELINE}, set())

    def test_CAL_2_no_plan_freeze_path_requires_spec_falsifiability(self):
        self.assertTrue(sa.require_admitted(plan(), INPUTS).admitted)  # no SpecFalsifiabilityEvidence exists here
        for p in sorted((ROOT / "aisef2" / "plan").rglob("*.py")):
            names = {n for n, _ in ks._names(ks.ast.parse(p.read_text(encoding="utf-8")))}
            with self.subTest(module=p.name):
                self.assertFalse({"SpecFalsifiabilityEvidence", "falsifiability_problems"} & names)

    def test_engine_and_result_are_distinct(self):
        r = ENGINE.admit(plan(), INPUTS)
        self.assertNotIsInstance(r, sa.StaticPlanAdmissionEngine)
        self.assertFalse(hasattr(ENGINE, "admitted"))
        with self.assertRaisesRegex(InvariantError, "exactly when every check passed"):
            dataclasses.replace(r, admitted=False)
        with self.assertRaisesRegex(InvariantError, "does not bind this result"):
            dataclasses.replace(r, plan_id="PLAN-2")
        with self.assertRaisesRegex(InvariantError, "nine checks, in order"):
            dataclasses.replace(r, checks=r.checks[:8])
        with self.assertRaisesRegex(InvariantError, "admits a Plan against AdmissionInputs"):
            ENGINE.admit(plan().obligations, INPUTS)
        self.assertRegex(sa.StaticPlanAdmissionEngine.digest, "^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
