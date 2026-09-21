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


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-2.1": ("closure-evidence/v2/P2-PROBE-PROTOCOL.json", probe_protocol, "aisef2/probe/protocol.py"),
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
