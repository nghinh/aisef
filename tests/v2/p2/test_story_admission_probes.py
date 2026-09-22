"""WP-2.4 — StoryAdmission with the reference probe on real parent checkouts (RFC §13, §9, §10.2).

NEG-1/2/3 analogues on python_callable, and the two fault-injection targets: parent checkout failure and an unrunnable
probe — both PROBE_UNRUNNABLE, owner ENVIRONMENT, never a developer outcome.
"""

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, Enforcement, ObligationRole as Role, Owner, StoryAdmissionDisposition as D, SubjectAbsence,
)
from aisef2.plan import story_admission as sa  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = PythonCallableProbe()
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED


def spec(locator, observable, stimulus=None, *, expectation=S, absence=SubjectAbsence.REQUIRES_SUBJECT):
    return ProductProofSpec.create(contract_id=f"BC-{locator}", probe_id=P.id, probe_digest=P.digest,
                                   probe_input={"subject": {"kind": "python_callable", "locator": locator},
                                                "stimulus": stimulus or {}, "observable": {**observable, "within_s": 10},
                                                "subject_absence": absence.value},
                                   candidate_expectation=expectation, compiler_id="t", compiler_digest="c" * 64)


ADD = spec("app.calc:add", {"returns": 3}, {"args": [1, 2]})                     # MUST_HOLD, REQUIRES_SUBJECT
NO_TEL = spec("app.telemetry:send", {"condition": "exists"}, expectation=R,
              absence=SubjectAbsence.ABSENCE_IS_DECIDABLE)                        # a forbidden module MUST NOT exist
SPECS = {s.id: s for s in (ADD, NO_TEL)}


def checkout(files):
    d = tempfile.mkdtemp(prefix="aisef2-parent-")
    for rel, text in files.items():
        p = pathlib.Path(d, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


EMPTY = {"app/__init__.py": ""}
IMPLEMENTED = {"app/__init__.py": "", "app/calc.py": "def add(a, b):\n    return a + b\n"}
REGRESSED = {"app/__init__.py": "", "app/calc.py": "def add(a, b):\n    return a - b\n"}
TELEMETRY = {"app/__init__.py": "", "app/telemetry.py": "def send():\n    pass\n"}


def admit(obligations, files, *, story="S1", interpreter=sys.executable, root=None):
    plan = Plan.create(id="PLAN", baseline=SHA, obligations=tuple(obligations), plan_quality_policy=NOT_PREREGISTERED)
    parent = RevisionRef(SHA, root or checkout(files))
    return sa.admit_story(plan, story, parent, specs=SPECS, probes={P.id: P},
                          env=ExecutionEnv(interpreter, 20, Enforcement.PARTIAL), committed_stories=frozenset(),
                          sink=sa.MemorySink())


def ob(cid, s, role, story="S1"):
    return PlanObligation(cid, s.id, story, role, EXPECTED_AT_PARENT[role], (), "why")


def dispositions(result):
    return [o.decision.disposition for o in result.obligations]


class RealParent(unittest.TestCase):
    def test_introduce_over_an_absent_required_subject_is_READY(self):  # NEG-3 analogue
        r = admit([ob("C1", ADD, Role.INTRODUCE)], EMPTY)
        self.assertEqual((dispositions(r), r.developer_call_permitted), ([D.READY], True))

    def test_preserve_over_an_absent_required_subject_is_PRECONDITION_BROKEN(self):
        r = admit([ob("C1", ADD, Role.PRESERVE)], EMPTY)
        self.assertEqual(dispositions(r), [D.PRECONDITION_BROKEN])
        self.assertIs(r.obligations[0].decision.failure.owner, Owner.PLAN)

    def test_early_implementation_is_PRE_SATISFIED_and_a_regression_breaks_the_precondition(self):
        self.assertEqual(dispositions(admit([ob("C1", ADD, Role.INTRODUCE)], IMPLEMENTED)), [D.PRE_SATISFIED])
        self.assertEqual(dispositions(admit([ob("C1", ADD, Role.PRESERVE)], IMPLEMENTED)), [D.READY])
        self.assertEqual(dispositions(admit([ob("C1", ADD, Role.PRESERVE)], REGRESSED)), [D.PRECONDITION_BROKEN])

    def test_forbidden_module_present_is_READY_and_absent_is_PRE_SATISFIED(self):  # NEG-1 / NEG-2 analogues
        self.assertEqual(dispositions(admit([ob("C1", NO_TEL, Role.INTRODUCE)], TELEMETRY)), [D.READY])
        self.assertEqual(dispositions(admit([ob("C1", NO_TEL, Role.INTRODUCE)], EMPTY)), [D.PRE_SATISFIED])

    def test_parent_checkout_failure_and_an_unrunnable_probe_are_environment(self):
        gone = os.path.join(tempfile.mkdtemp(), "not-checked-out")
        for name, kw in (("parent checkout failure", {"root": gone}),
                         ("probe unrunnable", {"interpreter": os.path.join(gone, "python")})):
            with self.subTest(fault=name):
                r = admit([ob("C1", ADD, Role.INTRODUCE)], IMPLEMENTED, **kw)
                d = r.obligations[0].decision
                self.assertEqual((d.disposition, d.failure.owner, r.admitted, r.developer_call_permitted),
                                 (D.PROBE_UNRUNNABLE, Owner.ENVIRONMENT, False, False))


if __name__ == "__main__":
    unittest.main()
