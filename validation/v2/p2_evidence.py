"""P2 evidence records — computed from the code, never written by hand, with a --check twin.

Same contract as `p1_evidence.py`: every record carries `properties`, named facts measured on the implementation, and
`--check` re-derives each record and fails if it differs from the committed one **or** if any property is false.
Records hold outcomes only (statuses, verdicts, satisfactions, owners) — never a temporary path or a duration — so a
rebuild is byte-identical.

    python -P validation/v2/p2_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p2_evidence.py --check    # fail on drift or on a false property
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Callable
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHA = "89abcdef0123456789abcdef0123456789abcdef"
#: The fixture product every WP-2.1 observation runs against (the same shape the tests use).
PRODUCT = {
    "app/__init__.py": "",
    "app/calc.py": "def add(a, b):\n    return a + b\n\n\ndef boom():\n    raise ValueError('no')\n",
    "app/die.py": "import os\nos._exit(3)\n",
    "app/hang.py": "while True:\n    pass\n",
    "app/broken.py": "import not_a_real_dependency_xyz\n\n\ndef f():\n    return 1\n",
}
LAYOUTS = {
    "no tests": {},
    "tests/ at the root": {"tests/__init__.py": "", "tests/test_calc.py": "from app.calc import add\n"},
    "tests inside the package": {"app/tests/__init__.py": "", "app/tests/test_calc.py": "import app.calc\n"},
    "broken tests": {"tests/test_calc.py": "def (:\n", "conftest.py": "raise SystemExit(4)\n",
                     "app/test_calc.py": "import no_such_module\n"},
}


def _module(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _rfc_text() -> str:
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    return (ROOT / fc.RFC_REL).read_text(encoding="utf-8")


@contextlib.contextmanager
def _checkout(files: dict):
    with tempfile.TemporaryDirectory(prefix="aisef2-evidence-") as d:
        for rel, text in files.items():
            p = pathlib.Path(d, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        yield d


def _outcome(record, spec) -> dict:
    from aisef2.arch.enums import MeasurementPoint, ObligationRole, ProbeExecutionStatus
    from aisef2.control.routing import route
    from aisef2.product.outcome import contract_satisfaction
    r = record.result
    executed = r.status is ProbeExecutionStatus.EXECUTED
    routed = route(r, spec, MeasurementPoint.CANDIDATE, ObligationRole.INTRODUCE)
    return {"status": r.status.value,
            "behavior_verdict": r.behavior_verdict.value if executed else None,
            "reason": r.reason.value if executed and r.reason else None,
            "contract_satisfaction": contract_satisfaction(r, spec).value if executed else None,
            "owner_at_candidate": routed.failure.owner.value if routed.failure else None,
            "enforcement": record.enforcement.value}


# --------------------------------------------------------------------------------------- WP-2.1

def probe_protocol() -> dict:
    from aisef2.arch.enums import (BehaviorVerdict as V, Enforcement, Polarity, ProbeExecutionStatus as PES,
                                   SubjectAbsence as SA, SubjectKind)
    from aisef2.probe import python_callable as pc
    from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    from aisef2.product.spec import ProductProofSpec
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    probe = pc.PythonCallableProbe()
    exists = {"condition": "exists"}

    def spec(locator, observable=None, stimulus=None, *, expectation=V.SATISFIED, absence=SA.ABSENCE_IS_DECIDABLE):
        return ProductProofSpec.create(
            contract_id="BC-EVIDENCE", probe_id=probe.id, probe_digest=probe.digest,
            probe_input={"subject": {"kind": "python_callable", "locator": locator}, "stimulus": stimulus or {},
                         "observable": observable or exists, "subject_absence": absence.value},
            candidate_expectation=expectation, compiler_id="evidence", compiler_digest="e" * 64)

    def env(timeout=20.0, required=Enforcement.PARTIAL, interpreter=sys.executable):
        return ExecutionEnv(interpreter, timeout, required)

    def run(s, root, e=None):
        return _outcome(run_probe(probe, s, RevisionRef(SHA, root), e or env()), s)

    with _checkout(PRODUCT) as product, _checkout({"README.md": "no product yet\n"}) as empty:
        abs_cases = {
            "PROBE-ABS-2": {"REQUIRES_SUBJECT, module absent": run(spec("app.calc:add", {"returns": 3}, {"args": [1, 2]},
                                                                        absence=SA.REQUIRES_SUBJECT), empty),
                            "REQUIRES_SUBJECT, attribute absent": run(spec("app.calc:gone", absence=SA.REQUIRES_SUBJECT),
                                                                      product)},
            "PROBE-ABS-3": {"positive existence, absent": run(spec("app.telemetry:send"), product)},
            "PROBE-ABS-4": {"negative existence, absent": run(spec("app.telemetry:send", expectation=V.REFUTED), product)},
            "PROBE-ABS-5": {"must exist": run(spec("app.telemetry:send"), product),
                            "must not exist": run(spec("app.telemetry:send", expectation=V.REFUTED), product),
                            "requires subject": run(spec("app.telemetry:send", absence=SA.REQUIRES_SUBJECT), product)},
        }
        s = spec("app.calc:add")
        faults = {
            "interpreter absent": run(s, product, env(interpreter=os.path.join(empty, "no-python"))),
            "cannot inspect (checkout missing)": run(s, os.path.join(empty, "gone")),
            "probe timeout": run(spec("app.hang:f"), product, env(timeout=1.5)),
        }
        injected = {"tool absent (injected: exit 127, no protocol output)":
                        dict(return_value=subprocess.CompletedProcess([], 127, stdout="", stderr="")),
                    "sandbox cannot execute (injected: PermissionError)": dict(side_effect=PermissionError("denied")),
                    "killed by signal before READY (injected)":
                        dict(return_value=subprocess.CompletedProcess([], -9, stdout="", stderr=""))}
        for name, kw in injected.items():
            with mock.patch("aisef2.probe.python_callable.subprocess.run", **kw):
                faults[name] = run(s, product)
        present = {
            "exists": run(spec("app.calc:add"), product),
            "returns 3": run(spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}), product),
            "returns 4 (wrong)": run(spec("app.calc:add", {"returns": 4}, {"args": [1, 2]}), product),
            "raises ValueError": run(spec("app.calc:boom", {"raises": "ValueError"}), product),
            "present, own import fails (REQUIRES_SUBJECT)": run(spec("app.broken:f", absence=SA.REQUIRES_SUBJECT), product),
            "present, ends the process": run(spec("app.die:f"), product),
            "resolves only outside the revision (REQUIRES_SUBJECT)": run(spec("json:dumps", absence=SA.REQUIRES_SUBJECT),
                                                                         product),
        }
        with mock.patch("aisef2.probe.python_callable.subprocess.run", side_effect=AssertionError("ran")):
            refused = {
                "unsupported observation class": run(spec("app.calc:add", {"stdout": "x"}), product),
                "path locator": run(spec("app/calc.py:add"), product),
                "developer test artefact": run(spec("tests.test_calc:test_add"), product),
                "spec bound to another digest": run(ProductProofSpec.create(**{
                    **{f: getattr(spec("app.calc:add"), f) for f in ("contract_id", "probe_id", "probe_input",
                                                                      "candidate_expectation", "compiler_id",
                                                                      "compiler_digest")},
                    "probe_digest": "0" * 64}), product),
                "FULL enforcement required": run(s, product, env(required=Enforcement.FULL)),
            }
    layouts = {}
    layout_specs = {"exists": spec("app.calc:add"), "absent": spec("app.telemetry:send"),
                    "requires absent": spec("app.telemetry:send", absence=SA.REQUIRES_SUBJECT),
                    "returns": spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}),
                    "raises": spec("app.calc:boom", {"raises": "ValueError"})}
    for name, extra in LAYOUTS.items():
        with _checkout({**PRODUCT, **extra}) as root:
            layouts[name] = {k: run(v, root) for k, v in layout_specs.items()}
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import aisef2.probe.python_callable as m; "
            "print(m.PythonCallableProbe.digest)")
    other = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8").stdout.strip()
    req = Requirement.create(id="REQ-E", text="adds", source="docs/req.md")
    contract = BehaviorContract.create(id="BC-ADD", requirement_ids=("REQ-E",),
                                       subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"),
                                       stimulus={"args": [1, 2]}, observable={"returns": 3},
                                       polarity=Polarity.MUST_HOLD, subject_absence=SA.REQUIRES_SUBJECT, rationale="adds")
    approvals = [ContractApproval(req.id, req.requirement_hash, contract.id, contract.contract_hash, "human:owner", 1.0,
                                  ())]
    compiled = compile_spec(contract, requirements={req.id: req}, approvals=approvals,
                            probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(probe.id, probe.digest)})
    conformance = fc.evaluate(*fc.load_inputs())
    f5 = next(x for x in conformance["subchecks"] if x["id"] == "F5.probe_protocol")

    every = [o for group in (abs_cases, {"faults": faults}, {"present": present}, {"refused": refused}, layouts)
             for o in group.values() for o in o.values()]
    first = next(iter(layouts.values()))
    e, i, u = PES.EXECUTED.value, "INDETERMINATE", PES.UNRUNNABLE.value
    return {
        "record": "AISEF V2 — P2 PROBE PROTOCOL", "work_package": "WP-2.1", "rfc_sections": ["9", "10.2", "24"],
        "frozen_items": ["F5"],
        "probe": {"id": probe.id, "digest": probe.digest, "sources": list(pc.PROBE_SOURCES),
                  "enforcement": probe.enforcement().value, "weakest_path": pc.WEAKEST_PATH,
                  "harness_preconditions": list(probe.harness_preconditions()),
                  "observation_classes": list(pc.CLASSES)},
        "implementation_notes": {
            "probe_result_core": "unchanged from P1 (Executed / Unrunnable / InvalidSpec); enforcement is bound by "
                                 "ProbeRecord, which run_probe returns for every evaluation",
            "api_shape": "a probe reports a typed Observation; protocol.classify_failure alone maps it to a ProbeResult",
            "second_kind": "a file_artifact prototype written only against the protocol runs in "
                           "tests/v2/p2/test_probe_protocol.py (SecondKindPrototype); it ships no code",
        },
        "residuals": [
            "probe timeout is UNRUNNABLE / ENVIRONMENT even when the subject is what hangs — RFC §9 lists timeout as a "
            "harness failure; a hanging product is therefore not charged to DEVELOPER",
            "a harness process killed by a signal mid-observation is UNRUNNABLE: the probe cannot tell the subject "
            "from the environment killing it",
            "enforcement PARTIAL: " + pc.WEAKEST_PATH,
        ],
        "acceptance_cases": abs_cases,
        "fault_injection": faults,
        "present_subjects": present,
        "refusals": refused,
        "layout_invariance": layouts,
        "f5_conformance": {"state": f5["state"], "detail": f5["detail"]},
        "properties": {
            "PROBE_ABS_1_harness_failure_is_unrunnable_environment_no_verdict": all(
                o["status"] == u and o["behavior_verdict"] is None and o["owner_at_candidate"] == "ENVIRONMENT"
                for o in faults.values()),
            "PROBE_ABS_2_requires_subject_absent_is_indeterminate_precondition_absent": all(
                (o["status"], o["behavior_verdict"], o["reason"]) == (e, i, "PRECONDITION_ABSENT")
                for o in abs_cases["PROBE-ABS-2"].values()),
            "PROBE_ABS_3_positive_existence_absent_is_unsatisfied": all(
                o["status"] == e and o["contract_satisfaction"] == "UNSATISFIED" for o in abs_cases["PROBE-ABS-3"].values()),
            "PROBE_ABS_4_negative_existence_absent_is_satisfied": all(
                o["status"] == e and o["contract_satisfaction"] == "SATISFIED" for o in abs_cases["PROBE-ABS-4"].values()),
            "PROBE_ABS_5_one_absence_not_forced_to_one_satisfaction":
                {k: o["contract_satisfaction"] for k, o in abs_cases["PROBE-ABS-5"].items()}
                == {"must exist": "UNSATISFIED", "must not exist": "SATISFIED", "requires subject": "INDETERMINATE"},
            "subject_absence_never_unrunnable": all(o["status"] == e for c in abs_cases.values() for o in c.values()),
            "present_subject_is_observed": [present[k]["behavior_verdict"] for k in present] ==
                ["SATISFIED", "SATISFIED", "REFUTED", "SATISFIED", "REFUTED", "REFUTED", "INDETERMINATE"],
            "unsupported_class_refused_not_degraded": refused["unsupported observation class"]["status"] == "INVALID_SPEC",
            "developer_path_rejected": refused["path locator"]["status"] == "INVALID_SPEC"
                and refused["developer test artefact"]["status"] == "INVALID_SPEC",
            "stale_digest_binding_refused": refused["spec bound to another digest"]["status"] == "INVALID_SPEC",
            "insufficient_enforcement_refused_not_degraded": refused["FULL enforcement required"]["status"] == u,
            "enforcement_bound_into_every_result": all(o["enforcement"] == "PARTIAL" for o in every),
            "digest_stable_across_processes": other == probe.digest,
            "digest_bound_into_the_spec": (compiled.probe_id, compiled.probe_digest) == (probe.id, probe.digest),
            "layout_invariance": all(v == first for v in layouts.values()) and len(layouts) == len(LAYOUTS),
            "f5_probe_protocol_equals_rfc": f5["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-2.2

CALIBRATION_REL = "closure-evidence/v2/P2-CALIBRATION.json"
FIXTURES_REL = "tests/v2/fixtures/calibration"


def calibration() -> dict:
    import time
    from aisef2.arch.enums import BehaviorVerdict as V, Enforcement
    from aisef2.probe import calibration as cal
    from aisef2.probe import python_callable as pc
    from aisef2.probe.protocol import HarnessProbe, Observation, ObservationKind as K
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    probe = pc.PythonCallableProbe()
    env = cal.calibration_env(sys.executable)
    base = ROOT / FIXTURES_REL / "python_callable"
    committed = json.loads((ROOT / CALIBRATION_REL).read_text(encoding="utf-8")) if (ROOT / CALIBRATION_REL).exists() \
        else {}
    kept = {(c["probe_id"], c["probe_digest"], c["observation_class"], c["positive_fixture"], c["negative_fixture"]):
            c["demonstrated_at"] for c in committed.get("calibrations", [])}

    def clock_for(cls):  # a re-demonstration of an unchanged record keeps its timestamp; anything else is new
        key = (probe.id, probe.digest, cls, f"{FIXTURES_REL}/python_callable/{cls}/positive",
               f"{FIXTURES_REL}/python_callable/{cls}/negative")
        return lambda: kept.get(key, time.time())

    records = [cal.calibrate(probe, cls, base / cls / "positive", base / cls / "negative", env, clock_for(cls),
                             names=(f"{FIXTURES_REL}/python_callable/{cls}/positive",
                                    f"{FIXTURES_REL}/python_callable/{cls}/negative"))
               for cls in pc.CLASSES]

    class Fixed(HarnessProbe):
        digest, verdict = "f" * 64, None

        def enforcement(self):
            return Enforcement.PARTIAL

        def harness_preconditions(self):
            return ("none",)

        def observation_class(self, spec):
            return probe.observation_class(spec)

        def observe(self, spec, at, env):
            return Observation(K.OBSERVED, self.verdict)

    def rejection(verdict, name):
        fixed = type(name, (Fixed,), {"id": f"probe.{name}", "verdict": verdict})()
        out = {}
        for cls in pc.CLASSES:
            try:
                cal.calibrate(fixed, cls, base / cls / "positive", base / cls / "negative", env, time.time)
                out[cls] = "QUALIFIED"
            except cal.NotQualified as e:
                out[cls] = "REJECTED: " + str(e).split(": ", 1)[1]
        return out
    always_refuted, always_satisfied = rejection(V.REFUTED, "always_refuted"), rejection(V.SATISFIED, "always_satisfied")
    table = {f"{e.value} expected, {o.value} observed": cal.demonstrates_contrast(e, o)
             for e in (V.SATISFIED, V.REFUTED) for o in V}
    conformance = fc.evaluate(*fc.load_inputs())
    f5 = next(x for x in conformance["subchecks"] if x["id"] == "F5.calibration_contracts")
    plan_sources = sorted((ROOT / "aisef2" / "plan").rglob("*.py")) if (ROOT / "aisef2" / "plan").exists() else []
    plan_names = sorted({n for p in plan_sources for n, _ in ks._names(ks.ast.parse(p.read_text(encoding="utf-8")))})
    return {
        "record": "AISEF V2 — P2 CALIBRATION", "work_package": "WP-2.2", "rfc_sections": ["9.1", "9.1.1", "9.1.2"],
        "frozen_items": ["F5"],
        "rule": "a counterexample produces the verdict opposite to candidate_expectation; a ProbeCapabilityCalibration "
                "exists only when the positive fixture is observed SATISFIED and the negative one REFUTED",
        "calibrations": [{"probe_id": r.probe_id, "probe_digest": r.probe_digest,
                          "observation_class": r.observation_class, "positive_fixture": r.positive_fixture,
                          "negative_fixture": r.negative_fixture, "demonstrated_at": r.demonstrated_at}
                         for r in records],
        "contrast_table": table,
        "CAL_1_always_refuted_probe": always_refuted,
        "always_satisfied_probe": always_satisfied,
        "spec_falsifiability": {"mechanisms": list(cal.MECHANISMS),
                                "plan_freeze_prerequisite": False,
                                "planning_modules_scanned": [p.relative_to(ROOT).as_posix() for p in plan_sources]},
        "f5_conformance": {"state": f5["state"], "detail": f5["detail"]},
        "properties": {
            "contrast_for_both_polarities": table == {
                "SATISFIED expected, SATISFIED observed": False, "SATISFIED expected, REFUTED observed": True,
                "SATISFIED expected, INDETERMINATE observed": False, "REFUTED expected, SATISFIED observed": True,
                "REFUTED expected, REFUTED observed": False, "REFUTED expected, INDETERMINATE observed": False},
            "reference_probe_qualified_for_every_class": [r.observation_class for r in records] == list(pc.CLASSES)
                and all((r.probe_id, r.probe_digest) == (probe.id, probe.digest) for r in records),
            "CAL_1_always_refuted_prohibition_probe_rejected": all(v.startswith("REJECTED: positive fixture")
                                                                    for v in always_refuted.values()),
            "always_satisfied_probe_rejected_for_must_hold": all(v.startswith("REJECTED: negative fixture")
                                                                  for v in always_satisfied.values()),
            "spec_falsifiability_not_a_plan_freeze_input": "SpecFalsifiabilityEvidence" not in plan_names
                and "falsifiability_problems" not in plan_names,
            "f5_calibration_contracts_equal_rfc": f5["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-2.3

def static_admission() -> dict:
    import dataclasses
    import re
    from aisef2.arch.enums import ObligationRole as Role, ParentExpectation as PE, SubjectKind
    from aisef2.plan import static_admission as sa
    from aisef2.probe.python_callable import PythonCallableProbe
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    w = _module("aisef_v2_p2_admission_world", "tests/v2/p2/test_static_admission.py")  # the Q0/Q1 fixture world
    engine, inputs, plan, ob, good = sa.StaticPlanAdmissionEngine(), w.INPUTS, w.plan, w.ob, w.GOOD

    def failed(p, i=inputs):
        return sorted(c.name for c in engine.admit(p, i).checks if not c.passed)

    class Moved(PythonCallableProbe):
        digest = "d" * 64
    cases = {
        "1 an approved requirement with no contract": failed(plan(), w.world(extra_requirement=True)[0]),
        "2 a committed spec that is not the derivation": failed(
            plan(good[1:2]), dataclasses.replace(inputs, specs={k: v for k, v in inputs.specs.items()
                                                                if v.contract_id != "BC-ADD"})),
        "3 duplicate INTRODUCE ownership for one spec": failed(plan(good + (ob("C5", "BC-ADD", "S3", Role.INTRODUCE,
                                                                               deps=("C3",)),))),
        "4 a cyclic dependency DAG": failed(plan((ob("C1", "BC-ADD", "S1", Role.INTRODUCE, deps=("C3",)),) + good[1:])),
        "5 a PRESERVE ordered before its INTRODUCE": failed(plan(good[:2] + (
            ob("C3", "BC-ADD", "S2", Role.PRESERVE), ob("C4", "BC-NO-TEL", "S2", Role.INTRODUCE)))),
        "5 a role/expectation pair with no §13 row": failed(plan(
            (ob("C1", "BC-ADD", "S1", Role.INTRODUCE, expected=PE.SATISFIED_AT_PARENT),) + good[1:])),
        "6 a probe digest that does not match (scenario D, statically)": failed(
            plan(), dataclasses.replace(inputs, catalogue={SubjectKind.PYTHON_CALLABLE: Moved()})),
        "7 a contract without approval": failed(plan(), w.world(drop_approval_for="BC-NO-TEL")[0]),
        "8 an orphan obligation": failed(plan(good + (ob("C5", "PPS-nowhere", "S3", Role.VERIFY),))),
        "9 a missing probe calibration": failed(plan(), w.world(calibrated=("exists",))[0]),
    }
    want = {"1 an approved requirement with no contract": ["requirement_coverage"],
            "2 a committed spec that is not the derivation": ["contract_spec_integrity"],
            "3 duplicate INTRODUCE ownership for one spec": ["contradictions", "ownership"],
            "4 a cyclic dependency DAG": ["dependency_dag", "plan_structure"],
            "5 a PRESERVE ordered before its INTRODUCE": ["contradictions"],
            "5 a role/expectation pair with no §13 row": ["contradictions"],
            "6 a probe digest that does not match (scenario D, statically)": ["contract_spec_integrity",
                                                                              "proof_capability"],
            "7 a contract without approval": ["contract_spec_integrity", "traceability"],
            "8 an orphan obligation": ["plan_structure"],
            "9 a missing probe calibration": ["probe_calibration"]}
    good_result = engine.admit(plan(), inputs)
    calls = []
    with mock.patch.object(PythonCallableProbe, "observe", side_effect=lambda *a: calls.append("observe")), \
            mock.patch("subprocess.run", side_effect=lambda *a, **k: calls.append("subprocess")):
        engine.admit(plan(), inputs)
    shas = set(re.findall(r"\b[0-9a-f]{40}\b", repr(good_result))) - {w.BASELINE}
    plan_names = sorted({n for p in sorted((ROOT / "aisef2" / "plan").rglob("*.py"))
                         for n, _ in ks._names(ks.ast.parse(p.read_text(encoding="utf-8")))})
    conformance = fc.evaluate(*fc.load_inputs())
    f6 = next(x for x in conformance["subchecks"] if x["id"] == "F6.plan_obligation_shape")
    rfc_checks = re.findall(r"^\d\. ", _rfc_text().split("## 12. StaticPlanAdmission")[1].split("## 13.")[0], re.M)
    return {
        "record": "AISEF V2 — P2 STATIC ADMISSION", "work_package": "WP-2.3", "rfc_sections": ["11", "12"],
        "frozen_items": ["F6"],
        "engine": {"digest": sa.StaticPlanAdmissionEngine.digest, "sources": list(sa.ENGINE_SOURCES),
                   "checks": [n for n, _ in sa.CHECKS]},
        "well_formed_plan": {"admitted": good_result.admitted, "result_digest": good_result.result_digest,
                             "checks_passed": [c.name for c in good_result.checks if c.passed]},
        "adversarial": cases,
        "implementation_notes": {
            "depends_on": "criterion ids that must complete first (board resolution §1); the story order is induced "
                          "from them",
            "role_expectation_pairs": "a pair outside RFC §13's table (e.g. INTRODUCE with SATISFIED_AT_PARENT) has no "
                                      "StoryAdmission row; check 5 rejects it — fail closed, no meaning derived",
            "freeze": "require_admitted re-derives admission at freeze time; a stored result is never taken on trust",
        },
        "f6_conformance": {"state": f6["state"], "detail": f6["detail"]},
        "properties": {
            "nine_checks_implemented_in_rfc_order": len(sa.CHECKS) == 9 == len(rfc_checks)
                and [c.number for c in good_result.checks] == list(range(1, 10)),
            "well_formed_plan_admitted": good_result.admitted,
            "each_check_rejects_its_case": cases == want,
            "result_digest_stable": engine.admit(plan(), inputs).result_digest == good_result.result_digest,
            "no_probe_executes_in_the_engine": calls == [],
            "no_future_parent_sha_invented": shas == set(),
            "CAL_2_no_plan_freeze_path_needs_spec_falsifiability":
                sa.require_admitted(plan(), inputs).admitted
                and not {"SpecFalsifiabilityEvidence", "falsifiability_problems"} & set(plan_names)
                and [f.name for f in dataclasses.fields(sa.AdmissionInputs)] ==
                ["requirements", "contracts", "approvals", "specs", "catalogue", "calibrations"],
            "planning_code_never_names_the_raw_verdict": ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)) == [],
            "f6_plan_obligation_equals_rfc": f6["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-2.4

def story_admission() -> dict:
    import itertools
    from aisef2.arch.enums import (BehaviorVerdict as V, EventType, MeasurementPoint, ObligationRole as Role,
                                   StoryAdmissionDisposition as D)
    from aisef2.control import routing
    from aisef2.errors import InvariantError
    from aisef2.plan import story_admission as sa
    from aisef2.plan.obligation import EXPECTED_AT_PARENT
    from aisef2.probe.protocol import RevisionRef
    from aisef2.product.outcome import Executed, IndeterminateReason, InvalidSpec, Unrunnable
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    t = _module("aisef_v2_p2_story_world", "tests/v2/p2/test_story_admission.py")
    rp = _module("aisef_v2_p2_story_probes", "tests/v2/p2/test_story_admission_probes.py")
    pa = IndeterminateReason.PRECONDITION_ABSENT

    def row(role, result, expectation=V.SATISFIED, committed=False):
        d = t.decide(role, result, expectation, committed=committed)
        return {"disposition": d.disposition.value, "owner": d.failure.owner.value if d.failure else None,
                "satisfaction": d.satisfaction.value if d.satisfaction else None}
    rfc_rows = {
        "INTRODUCE expecting UNSATISFIED_AT_PARENT, measured UNSATISFIED": row(Role.INTRODUCE, Executed(V.REFUTED)),
        "INTRODUCE expecting UNSATISFIED_AT_PARENT, measured SATISFIED": row(Role.INTRODUCE, Executed(V.SATISFIED)),
        "PRESERVE expecting SATISFIED_AT_PARENT, measured SATISFIED": row(Role.PRESERVE, Executed(V.SATISFIED)),
        "PRESERVE expecting SATISFIED_AT_PARENT, measured UNSATISFIED": row(Role.PRESERVE, Executed(V.REFUTED)),
        "VERIFY, measured SATISFIED": row(Role.VERIFY, Executed(V.SATISFIED)),
        "VERIFY, measured UNSATISFIED": row(Role.VERIFY, Executed(V.REFUTED)),
        "INTRODUCE, INDETERMINATE(PRECONDITION_ABSENT)": row(Role.INTRODUCE, Executed(V.INDETERMINATE, pa)),
        "PRESERVE, INDETERMINATE(PRECONDITION_ABSENT)": row(Role.PRESERVE, Executed(V.INDETERMINATE, pa)),
        "VERIFY, INDETERMINATE(PRECONDITION_ABSENT)": row(Role.VERIFY, Executed(V.INDETERMINATE, pa)),
        "any, probe UNRUNNABLE": row(Role.INTRODUCE, Unrunnable("x")),
        "any, probe INVALID_SPEC": row(Role.PRESERVE, InvalidSpec("x")),
        "PRESERVE measured UNSATISFIED, introducing story committed": row(Role.PRESERVE, Executed(V.REFUTED),
                                                                          committed=True),
    }
    key = (MeasurementPoint.PARENT, sa.ContractSatisfaction.INDETERMINATE, pa, Role.INTRODUCE)
    with mock.patch.dict(routing._EXECUTED, {k: v for k, v in routing._EXECUTED.items() if k != key}, clear=True):
        bare = row(Role.INTRODUCE, Executed(V.INDETERMINATE, pa))
    neg = {"NEG-1 forbidden behaviour present, INTRODUCE": row(Role.INTRODUCE, Executed(V.SATISFIED), V.REFUTED),
           "NEG-2 forbidden behaviour absent (decidable), INTRODUCE": row(Role.INTRODUCE, Executed(V.REFUTED), V.REFUTED),
           "NEG-3 required subject absent, INTRODUCE": row(Role.INTRODUCE, Executed(V.INDETERMINATE, pa), V.REFUTED),
           "NEG-3 required subject absent, PRESERVE": row(Role.PRESERVE, Executed(V.INDETERMINATE, pa), V.REFUTED),
           "NEG-3 required subject absent, VERIFY": row(Role.VERIFY, Executed(V.INDETERMINATE, pa), V.REFUTED)}
    results = [Executed(V.SATISFIED), Executed(V.REFUTED), Executed(V.INDETERMINATE, pa), Unrunnable("x"),
               InvalidSpec("y")]
    total = [t.decide(r, x, e).disposition in set(D) for r, e, x in itertools.product(Role, (V.SATISFIED, V.REFUTED),
                                                                                      results)]
    real = {
        "INTRODUCE, required subject absent": [d.value for d in rp.dispositions(rp.admit(
            [rp.ob("C1", rp.ADD, Role.INTRODUCE)], rp.EMPTY))],
        "INTRODUCE, already implemented": [d.value for d in rp.dispositions(rp.admit(
            [rp.ob("C1", rp.ADD, Role.INTRODUCE)], rp.IMPLEMENTED))],
        "PRESERVE, regressed": [d.value for d in rp.dispositions(rp.admit(
            [rp.ob("C1", rp.ADD, Role.PRESERVE)], rp.REGRESSED))],
        "INTRODUCE forbidden module, present": [d.value for d in rp.dispositions(rp.admit(
            [rp.ob("C1", rp.NO_TEL, Role.INTRODUCE)], rp.TELEMETRY))],
        "INTRODUCE forbidden module, absent": [d.value for d in rp.dispositions(rp.admit(
            [rp.ob("C1", rp.NO_TEL, Role.INTRODUCE)], rp.EMPTY))],
    }
    with tempfile.TemporaryDirectory() as gone:
        faults = {name: [d.value for d in rp.dispositions(rp.admit([rp.ob("C1", rp.ADD, Role.INTRODUCE)],
                                                                   rp.IMPLEMENTED, **kw))]
                  for name, kw in (("parent checkout failure", {"root": os.path.join(gone, "missing")}),
                                   ("probe unrunnable", {"interpreter": os.path.join(gone, "python")}))}
    sink = sa.MemorySink()
    refused_before = _raises_invariant(lambda: sa.request_developer(sink, "S1"), InvariantError)
    early = sa.ordering_problems([(EventType.PROVIDER_REQUEST, {"story_id": "S1"}),
                                  (EventType.STORY_ADMITTED, {"story_id": "S1", "developer_call_permitted": True})])
    abbreviated = _raises_invariant(lambda: RevisionRef("0f1e2d3c4b5a", os.path.abspath("x")), InvariantError)
    conformance = fc.evaluate(*fc.load_inputs())
    f7 = next(x for x in conformance["subchecks"] if x["id"] == "F7.dispositions")
    return {
        "record": "AISEF V2 — P2 STORY ADMISSION", "work_package": "WP-2.4", "rfc_sections": ["13"],
        "frozen_items": ["F7"],
        "rfc_rows": rfc_rows, "bare_indeterminate": bare, "neg_cases": neg, "real_parent": real,
        "fault_injection": faults,
        "open_items": ["§22 names no failure code for PLAN_CONTRADICTION: it blocks the story and charges no owner; an "
                       "owner, if any, is the owner's decision"],
        "f7_conformance": {"state": f7["state"], "detail": f7["detail"]},
        "properties": {
            "every_rfc_row_reproduced": [v["disposition"] for v in rfc_rows.values()] == [
                "READY", "PRE_SATISFIED", "READY", "PRECONDITION_BROKEN", "READY", "READY", "READY",
                "PRECONDITION_BROKEN", "PRECONDITION_BROKEN", "PROBE_UNRUNNABLE", "PROBE_INVALID", "PLAN_CONTRADICTION"],
            "disposition_table_total": all(total) and len(total) == 30,
            "unadmissible_role_expectation_pairs_fail_closed": all(
                _raises_invariant(lambda r=r, e=e: t.decide(r, Executed(V.SATISFIED), expected=e), InvariantError)
                for r in Role for e in sa.ParentExpectation if EXPECTED_AT_PARENT[r] is not e),
            "probe_unrunnable_is_environment": rfc_rows["any, probe UNRUNNABLE"]["owner"] == "ENVIRONMENT"
                and all(v == ["PROBE_UNRUNNABLE"] for v in faults.values()),
            "invalid_spec_is_probe_invalid_integration": rfc_rows["any, probe INVALID_SPEC"] ==
                {"disposition": "PROBE_INVALID", "owner": "INTEGRATION", "satisfaction": None},
            "preserve_unsatisfied_is_precondition_broken": rfc_rows[
                "PRESERVE expecting SATISFIED_AT_PARENT, measured UNSATISFIED"]["disposition"] == "PRECONDITION_BROKEN",
            "bare_indeterminate_is_probe_invalid_never_developer": bare["disposition"] == "PROBE_INVALID"
                and bare["owner"] != "DEVELOPER",
            "neg_1_2_3": [v["disposition"] for v in neg.values()] == ["READY", "PRE_SATISFIED", "READY",
                                                                     "PRECONDITION_BROKEN", "PRECONDITION_BROKEN"],
            "real_probe_at_the_parent": real == {
                "INTRODUCE, required subject absent": ["READY"], "INTRODUCE, already implemented": ["PRE_SATISFIED"],
                "PRESERVE, regressed": ["PRECONDITION_BROKEN"], "INTRODUCE forbidden module, present": ["READY"],
                "INTRODUCE forbidden module, absent": ["PRE_SATISFIED"]},
            "abbreviated_parent_sha_refused": abbreviated,
            "no_provider_request_before_admission": refused_before and early != [] and sink.events == (),
            "routes_on_satisfaction_never_the_raw_verdict": ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)) == [],
            "f7_dispositions_equal_rfc": f7["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-2.5

def plan_drift() -> dict:
    from aisef2.arch.enums import ContractSatisfaction as CS, EventType
    from aisef2.plan import drift as dr
    from aisef2.plan import story_admission as sa
    from aisef2.plan.obligation import PlanQualityPolicy
    sc = _module("aisef_v2_p2_drift_scenarios", "tests/v2/p2/test_drift_scenarios.py")
    t = _module("aisef_v2_p2_drift_world", "tests/v2/p2/test_drift.py")
    from aisef2.probe.protocol import RevisionRef

    def run(plan, completed):
        sink = sa.MemorySink()
        adm = sa.admit_story(plan, "S2", RevisionRef(sc.REV1, sc.AFTER_S1), specs=sc.SPECS, probes={sc.P.id: sc.P},
                             env=sc.ENV, committed_stories=frozenset({"S1"}), sink=sink)
        cont = dr.continue_story(plan, adm, completed, sink)
        refused = False
        if adm.developer_call_permitted:
            sa.request_developer(sink, "S2", {"criteria": list(cont.developer_work)})
        else:
            refused = _raises_invariant(lambda: sa.request_developer(sink, "S2"), Exception)
        return {"dispositions": {o.criterion_id: o.decision.disposition.value for o in adm.obligations},
                "developer_call_permitted": adm.developer_call_permitted,
                "already_satisfied": cont.already_satisfied, "developer_work": list(cont.developer_work),
                "verify_at_candidate": list(cont.verify_at_candidate),
                "drift": [{"criterion_id": d.criterion_id, "attributed_to": d.attributed_to,
                           "candidates": list(d.candidates)} for d in cont.drift],
                "developer_request_refused": refused,
                "provider_requests": sum(1 for e, _ in sink.events if e is EventType.PROVIDER_REQUEST),
                "budget_problems": dr.budget_problems(sink.events),
                "ordering_problems": sa.ordering_problems(sink.events)}
    mul_s1 = sc.completed_s1(sc.MUL)
    a = run(sc.ScenarioA.PLAN, {sc.MUL.id: mul_s1})
    k = run(sc.ScenarioK.PLAN, {sc.MUL.id: mul_s1})
    flips = {"S1 flips the spec": dr.attribute(t.PLAN, "S3", t.B.id, [t.flip("S1")])[0],
             "a non-upstream story flips it": dr.attribute(t.PLAN, "S3", t.B.id, [t.flip("S0")])[0],
             "two upstream stories flip it": dr.attribute(t.PLAN, "S3", t.B.id, [t.flip("S1"), t.flip("S2")])[0],
             "nothing measured": dr.attribute(t.PLAN, "S3", t.B.id, [dr.CompletedStory("S2", None, CS.SATISFIED)])[0]}
    q = t.Quality()
    q.setUp()
    quality = {"not preregistered": q.q(t.NOT_PREREGISTERED).verdict,
               "ratio 0.5 preregistered at 0.5": q.q(PlanQualityPolicy(0.5, None, None)).verdict,
               "ratio 0.5 preregistered at 0.4": q.q(PlanQualityPolicy(0.4, None, None)).verdict}
    return {
        "record": "AISEF V2 — P2 PLAN DRIFT", "work_package": "WP-2.5", "rfc_sections": ["14", "29"],
        "frozen_items": ["F7"],
        "scenario_A_early_upstream_implementation": a,
        "scenario_K_fully_pre_satisfied_story": k,
        "attribution_cases": flips,
        "plan_quality_verdicts": quality,
        "implementation_decisions": [
            "attribution: the introducer is the completed upstream (DAG) story measured not SATISFIED at its parent "
            "and SATISFIED at its merge; none or several such stories -> UNATTRIBUTED with the candidates kept "
            "(RFC §36 leaves tie-breaks to the implementation; a tie never blames one story)",
            "the measurements are inputs; running probes at completed stories' revisions belongs to orchestration (P5)",
            "developer budget is charged by provider/request events, each naming the criteria it works on; "
            "budget_problems rejects any that names a criterion not admitted READY",
        ],
        "properties": {
            "scenario_A_pre_satisfied_and_attributed_upstream": a["dispositions"] == {"C2": "PRE_SATISFIED",
                                                                                     "C3": "READY"}
                and a["drift"] == [{"criterion_id": "C2", "attributed_to": "S1", "candidates": ["S1"]}],
            "scenario_A_continues_on_the_remainder": a["developer_work"] == ["C3"] and not a["already_satisfied"]
                and a["verify_at_candidate"] == ["C2", "C3"],
            "scenario_K_story_already_satisfied_developer_skipped": k["already_satisfied"]
                and not k["developer_call_permitted"] and k["developer_request_refused"] and k["provider_requests"] == 0,
            "scenario_K_every_obligation_still_verified": k["verify_at_candidate"] == ["C2"],
            "pre_satisfied_charges_no_developer_budget": a["budget_problems"] == [] == k["budget_problems"]
                and "C2" not in a["developer_work"],
            "no_provider_request_before_admission": a["ordering_problems"] == [] == k["ordering_problems"],
            "unattributed_when_none_or_ambiguous": flips == {
                "S1 flips the spec": "S1", "a non-upstream story flips it": "UNATTRIBUTED",
                "two upstream stories flip it": "UNATTRIBUTED", "nothing measured": "UNATTRIBUTED"},
            "plan_quality_not_claimed_without_preregistered_thresholds": quality == {
                "not preregistered": "NOT_CLAIMED", "ratio 0.5 preregistered at 0.5": "PASS",
                "ratio 0.5 preregistered at 0.4": "FAIL"},
        },
    }


def _raises_invariant(fn, exc) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-2.1": ("closure-evidence/v2/P2-PROBE-PROTOCOL.json", probe_protocol, "aisef2/probe/protocol.py"),
    "WP-2.2": (CALIBRATION_REL, calibration, "aisef2/probe/calibration.py"),
    "WP-2.3": ("closure-evidence/v2/P2-STATIC-ADMISSION.json", static_admission, "aisef2/plan/static_admission.py"),
    "WP-2.4": ("closure-evidence/v2/P2-STORY-ADMISSION.json", story_admission, "aisef2/plan/story_admission.py"),
    "WP-2.5": ("closure-evidence/v2/P2-PLAN-DRIFT.json", plan_drift, "aisef2/plan/drift.py"),
}


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def problems_of(record: dict) -> list[str]:
    props = record.get("properties") or {}
    out = [] if props else [f"{record.get('work_package')}: record carries no properties"]
    return out + [f"{record.get('work_package')}: property {k} is false" for k, v in props.items() if v is not True]


def check(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    for rel, build, needs in BUILDERS.values():
        if not (root / needs).exists():
            continue
        fresh = build()
        out += problems_of(fresh)
        committed = root / rel
        if not committed.exists():
            out.append(f"{rel} is missing")
        elif committed.read_text(encoding="utf-8") != render(fresh):
            out.append(f"{rel} is stale: regenerate it")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
    else:
        problems = []
        for rel, build, needs in BUILDERS.values():
            if (ROOT / needs).exists():
                record = build()
                problems += problems_of(record)
                if not problems_of(record):
                    (ROOT / rel).write_text(render(record), encoding="utf-8")
                    print(f"wrote {rel}")
    for p in problems:
        print(f"FAIL  {p}")
    print("p2 evidence: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
