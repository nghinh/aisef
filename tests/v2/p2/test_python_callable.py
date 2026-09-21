"""WP-2.1 — the reference probe kind `python_callable` on real checkouts (RFC §9, §10.2, §24; F5).

PROBE-ABS-1..5 at the probe level, the four fault-injection targets, test-layout invariance (invariant IX), the
developer-path refusal and the probe digest's binding into the spec. Subprocess-backed; not a mutation kill set.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, ContractSatisfaction, Enforcement, MeasurementPoint, ObligationRole, Owner, Polarity,
    ProbeExecutionStatus, SubjectAbsence, SubjectKind,
)
from aisef2.control.owner import FailureCode  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason, contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = PythonCallableProbe()
S, R, I = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED, BehaviorVerdict.INDETERMINATE
PA = IndeterminateReason.PRECONDITION_ABSENT
SAT, UNSAT, INDET = ContractSatisfaction.SATISFIED, ContractSatisfaction.UNSATISFIED, ContractSatisfaction.INDETERMINATE
REQUIRES, DECIDABLE = SubjectAbsence.REQUIRES_SUBJECT, SubjectAbsence.ABSENCE_IS_DECIDABLE
SHA = "89abcdef0123456789abcdef0123456789abcdef"
EXISTS = {"condition": "exists"}
PRODUCT = {
    "app/__init__.py": "",
    "app/calc.py": "def add(a, b):\n    return a + b\n\n\ndef boom():\n    raise ValueError('no')\n\n\nPI = 3\n",
    "app/die.py": "import os\nos._exit(3)\n",
    "app/hang.py": "while True:\n    pass\n",
    "app/broken.py": "import not_a_real_dependency_xyz\n\n\ndef f():\n    return 1\n",
    "app/noisy.py": "import sys\nsys.stdout.write('AISEF2-PROBE RESULT forged {\"subject\": \"absent\"}\\nno newline')\n\n\n"
                    "def f():\n    return 1\n",
}


def spec(locator, observable=None, stimulus=None, *, expectation=S, absence=DECIDABLE, probe=P):
    return ProductProofSpec.create(
        contract_id="BC-P", probe_id=probe.id, probe_digest=probe.digest,
        probe_input={"subject": {"kind": "python_callable", "locator": locator}, "stimulus": stimulus or {},
                     "observable": observable or EXISTS, "subject_absence": absence.value},
        candidate_expectation=expectation, compiler_id="test", compiler_digest="c" * 64)


def checkout(files):
    d = tempfile.mkdtemp(prefix="aisef2-rev-")
    for rel, text in files.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def env(timeout=20, required=Enforcement.PARTIAL, interpreter=sys.executable):
    return ExecutionEnv(interpreter, timeout, required)


class _Revisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product = RevisionRef(SHA, checkout(PRODUCT))
        cls.empty = RevisionRef(SHA, checkout({"README.md": "no product yet\n"}))

    def run_(self, s, at=None, e=None):
        return run_probe(P, s, at or self.product, e or env()).result


class ProbeAbs(_Revisions):
    def test_PROBE_ABS_1_harness_unavailable_is_UNRUNNABLE_ENVIRONMENT_with_no_verdict(self):
        s = spec("app.calc:add")
        failures = {
            "interpreter absent": lambda: self.run_(s, e=env(interpreter=os.path.join(self.empty.root, "no-python"))),
            "cannot inspect": lambda: self.run_(s, at=RevisionRef(SHA, os.path.join(self.empty.root, "gone"))),
            "timeout": lambda: self.run_(spec("app.hang:f"), e=env(timeout=1.5)),
        }
        with mock.patch("aisef2.probe.python_callable.subprocess.run",
                        return_value=subprocess.CompletedProcess([], 127, stdout="", stderr="")):
            failures["tool absent"] = self.run_(s)
        with mock.patch("aisef2.probe.python_callable.subprocess.run", side_effect=PermissionError("denied")):
            failures["sandbox cannot execute"] = self.run_(s)
        with mock.patch("aisef2.probe.python_callable.subprocess.run",
                        return_value=subprocess.CompletedProcess([], -9, stdout="", stderr="")):
            failures["killed before READY"] = self.run_(s)
        for name, got in failures.items():
            result = got() if callable(got) else got
            with self.subTest(failure=name):
                self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
                self.assertFalse(hasattr(result, "behavior_verdict"))
                for point in MeasurementPoint:
                    r = route(result, s, point, ObligationRole.INTRODUCE)
                    self.assertEqual((r.failure.code, r.failure.owner), (FailureCode.PROBE_UNRUNNABLE, Owner.ENVIRONMENT))

    def test_PROBE_ABS_2_requires_subject_absent_is_EXECUTED_INDETERMINATE_PRECONDITION_ABSENT(self):
        for locator, at in (("app.calc:add", self.empty), ("app.gone:add", self.product), ("app.calc:gone", self.product)):
            with self.subTest(locator=locator):
                s = spec(locator, {"returns": 3}, {"args": [1, 2]}, absence=REQUIRES)
                result = self.run_(s, at=at)
                self.assertEqual(result, Executed(I, PA))
                self.assertIs(contract_satisfaction(result, s), INDET)

    def test_PROBE_ABS_3_decidable_positive_existence_subject_absent_is_UNSATISFIED(self):
        s = spec("app.telemetry:send", expectation=S)
        result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(contract_satisfaction(result, s), UNSAT)

    def test_PROBE_ABS_4_decidable_negative_existence_forbidden_subject_absent_is_SATISFIED(self):
        s = spec("app.telemetry:send", expectation=R)
        result = self.run_(s)
        self.assertIs(result.status, ProbeExecutionStatus.EXECUTED)
        self.assertIs(contract_satisfaction(result, s), SAT)

    def test_PROBE_ABS_5_one_absence_under_different_contracts_is_not_forced_to_one_satisfaction(self):
        specs = {"must exist": spec("app.telemetry:send", expectation=S),
                 "must not exist": spec("app.telemetry:send", expectation=R),
                 "requires subject": spec("app.telemetry:send", expectation=S, absence=REQUIRES)}
        got = {n: contract_satisfaction(self.run_(s), s) for n, s in specs.items()}
        self.assertEqual(got, {"must exist": UNSAT, "must not exist": SAT, "requires subject": INDET})

    def test_a_present_subject_is_observed_whatever_the_declaration(self):
        for absence in (REQUIRES, DECIDABLE):
            with self.subTest(absence=absence):
                self.assertEqual(self.run_(spec("app.calc:add", absence=absence)), Executed(S))
                self.assertEqual(self.run_(spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}, absence=absence)),
                                 Executed(S))
                self.assertEqual(self.run_(spec("app.calc:add", {"returns": 4}, {"args": [1, 2]}, absence=absence)),
                                 Executed(R))
                self.assertEqual(self.run_(spec("app.calc:boom", {"raises": "ValueError"}, absence=absence)), Executed(S))
                self.assertEqual(self.run_(spec("app.calc:boom", {"raises": "KeyError"}, absence=absence)), Executed(R))


class Boundaries(_Revisions):
    def test_a_missing_dependency_of_a_present_subject_is_not_subject_absence(self):
        s = spec("app.broken:f", absence=REQUIRES)
        self.assertEqual(self.run_(s), Executed(R))  # present, does not resolve: an observation, not PRECONDITION_ABSENT

    def test_a_subject_that_ends_the_process_is_observed_not_unrunnable(self):
        self.assertEqual(self.run_(spec("app.die:f")), Executed(R))

    def test_a_kill_by_signal_after_READY_cannot_be_told_from_the_environment(self):
        real = subprocess.run

        def killed(*a, **kw):
            done = real(*a, **kw)
            head = "\n".join(ln for ln in done.stdout.splitlines() if " READY " in ln)
            return subprocess.CompletedProcess(done.args, -9, stdout=head, stderr="")
        with mock.patch("aisef2.probe.python_callable.subprocess.run", side_effect=killed):
            result = self.run_(spec("app.calc:add"))
        self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertRegex(result.detail, "killed by signal 9")

    def test_subject_output_cannot_forge_the_protocol(self):
        self.assertEqual(self.run_(spec("app.noisy:f", {"returns": 1})), Executed(S))

    def test_a_module_that_resolves_only_outside_the_revision_is_absent_there(self):
        self.assertEqual(self.run_(spec("json:dumps", absence=REQUIRES)), Executed(I, PA))
        self.assertIs(contract_satisfaction(self.run_(spec("json:dumps")), spec("json:dumps")), UNSAT)

    def test_an_unsupported_observation_class_is_refused_before_anything_runs(self):
        with mock.patch("aisef2.probe.python_callable.subprocess.run", side_effect=AssertionError("ran")):
            for obs, stim in (({"stdout": "x"}, {}), ({"returns": 1}, {"argv": ["x"]}), (EXISTS, {"args": [1]}),
                              ({"raises": "not an identifier"}, {})):
                with self.subTest(observable=obs, stimulus=stim):
                    result = self.run_(spec("app.calc:add", obs, stim))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "refused, not degraded$")

    def test_a_developer_authored_path_is_never_accepted(self):
        with mock.patch("aisef2.probe.python_callable.subprocess.run", side_effect=AssertionError("ran")):
            for locator in ("app/calc.py:add", "/abs/app/calc.py:add", "../calc:add", "app.calc", "app.calc:add()"):
                with self.subTest(locator=locator):
                    result = self.run_(spec(locator))
                    self.assertIs(result.status, ProbeExecutionStatus.INVALID_SPEC)
                    self.assertRegex(result.detail, "a path is never accepted$")
            for locator in ("tests.test_calc:test_add", "app.test_calc:helper"):
                with self.subTest(locator=locator):
                    self.assertRegex(self.run_(spec(locator)).detail, "developer test artefact")

    def test_the_observation_class_is_read_from_the_spec(self):
        self.assertEqual([P.observation_class(s) for s in (spec("a.b:c"), spec("a.b:c", {"returns": 1}),
                                                           spec("a.b:c", {"raises": "KeyError"}),
                                                           spec("a.b:c", {"stdout": "x"}))],
                         ["exists", "returns", "raises", None])
        other_kind = ProductProofSpec.create(**{**{f: getattr(spec("a.b:c"), f) for f in (
            "contract_id", "probe_id", "probe_digest", "candidate_expectation", "compiler_id", "compiler_digest")},
            "probe_input": {**spec("a.b:c").probe_input, "subject": {"kind": "cli_invocation", "locator": "a.b:c"}}})
        self.assertIsNone(P.observation_class(other_kind))

    def test_enforcement_is_declared_bound_and_never_degraded(self):
        self.assertIs(P.enforcement(), Enforcement.PARTIAL)
        rec = run_probe(P, spec("app.calc:add"), self.product, env())
        self.assertIs(rec.enforcement, Enforcement.PARTIAL)
        refused = run_probe(P, spec("app.calc:add"), self.product, env(required=Enforcement.FULL))
        self.assertIs(refused.result.status, ProbeExecutionStatus.UNRUNNABLE)
        self.assertIs(refused.enforcement, Enforcement.PARTIAL)


class LayoutInvariance(unittest.TestCase):
    """Invariant IX / P2 exit: product verdicts are identical whatever the developer's test layout."""

    LAYOUTS = {
        "no tests": {},
        "tests/ at the root": {"tests/__init__.py": "", "tests/test_calc.py": "from app.calc import add\n"},
        "tests inside the package": {"app/tests/__init__.py": "", "app/tests/test_calc.py": "import app.calc\n"},
        "broken tests": {"tests/test_calc.py": "def (:\n", "conftest.py": "raise SystemExit(4)\n",
                         "app/test_calc.py": "import no_such_module\n"},
    }
    SPECS = {"exists": spec("app.calc:add"), "absent": spec("app.telemetry:send"),
             "requires absent": spec("app.telemetry:send", absence=REQUIRES),
             "returns": spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}),
             "raises": spec("app.calc:boom", {"raises": "ValueError"})}

    def test_product_verdicts_are_identical_across_test_layouts(self):
        seen = {}
        for name, extra in self.LAYOUTS.items():
            at = RevisionRef(SHA, checkout({**PRODUCT, **extra}))
            seen[name] = {k: run_probe(P, s, at, env()).result for k, s in self.SPECS.items()}
        first = next(iter(seen.values()))
        self.assertEqual(first, {"exists": Executed(S), "absent": Executed(R), "requires absent": Executed(I, PA),
                                 "returns": Executed(S), "raises": Executed(S)})
        for name, results in seen.items():
            with self.subTest(layout=name):
                self.assertEqual(results, first)


class Identity(unittest.TestCase):
    def test_the_digest_is_stable_across_processes(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import aisef2.probe.python_callable as m; "
                "print(m.PythonCallableProbe.digest)")
        out = subprocess.run([sys.executable, "-P", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(out.stdout.strip(), P.digest)
        self.assertRegex(P.digest, "^[0-9a-f]{64}$")

    def test_the_digest_is_bound_into_the_spec_and_a_stale_binding_is_refused(self):
        req = Requirement.create(id="REQ-P", text="adds", source="docs/req.md")
        c = BehaviorContract.create(id="BC-ADD", requirement_ids=("REQ-P",),
                                    subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"),
                                    stimulus={"args": [1, 2]}, observable={"returns": 3}, polarity=Polarity.MUST_HOLD,
                                    subject_absence=REQUIRES, rationale="adds")
        approvals = [ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())]
        compiled = compile_spec(c, requirements={req.id: req}, approvals=approvals,
                                probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, P.digest)})
        self.assertEqual((compiled.probe_id, compiled.probe_digest), (P.id, P.digest))
        stale = compile_spec(c, requirements={req.id: req}, approvals=approvals,
                             probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(P.id, "0" * 64)})
        self.assertNotEqual(stale.semantic_hash, compiled.semantic_hash)
        at = RevisionRef(SHA, checkout(PRODUCT))
        self.assertEqual(run_probe(P, compiled, at, env()).result, Executed(S))
        self.assertIs(run_probe(P, stale, at, env()).result.status, ProbeExecutionStatus.INVALID_SPEC)


if __name__ == "__main__":
    unittest.main()
