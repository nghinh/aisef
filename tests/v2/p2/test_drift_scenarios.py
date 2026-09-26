"""WP-2.5 — adversarial scenarios A and K with the reference probe on real revisions (RFC §14; board resolution §15).

A · an upstream story implements downstream behaviour early: PRE_SATISFIED + PLAN_DRIFT attributed through the DAG to
    that story; the downstream story continues on what remains, and charges no developer budget for the rest.
K · a fully pre-satisfied story: STORY_ALREADY_SATISFIED, the developer call skipped, every obligation still to be
    verified at the candidate.
"""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import (  # noqa: E402
    BehaviorVerdict, Enforcement, EventType, ObligationRole as Role, StoryAdmissionDisposition as D, SubjectAbsence,
)
from aisef2.errors import InvariantError  # noqa: E402
from aisef2.plan import drift as dr  # noqa: E402
from aisef2.plan import story_admission as sa  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe  # noqa: E402
from aisef2.probe.python_callable import PythonCallableProbe  # noqa: E402
from aisef2.product.outcome import contract_satisfaction  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402

P = PythonCallableProbe()
ENV = ExecutionEnv(sys.executable, 20, Enforcement.PARTIAL)
REV0, REV1 = "a0" * 20, "a1" * 20


def spec(name, returns, args):
    return ProductProofSpec.create(contract_id=f"BC-{name}", probe_id=P.id, probe_digest=P.digest,
                                   probe_input={"subject": {"kind": "python_callable", "locator": f"app.calc:{name}"},
                                                "stimulus": {"args": args}, "observable": {"returns": returns, "within_s": 10},
                                                "subject_absence": SubjectAbsence.REQUIRES_SUBJECT.value},
                                   candidate_expectation=BehaviorVerdict.SATISFIED, compiler_id="t",
                                   compiler_digest="c" * 64)


ADD, MUL, DIV = spec("add", 3, [1, 2]), spec("mul", 6, [2, 3]), spec("div", 2, [6, 3])
SPECS = {s.id: s for s in (ADD, MUL, DIV)}


def checkout(source):
    d = tempfile.mkdtemp(prefix="aisef2-rev-")
    pathlib.Path(d, "app").mkdir()
    pathlib.Path(d, "app", "__init__.py").write_text("", encoding="utf-8")
    pathlib.Path(d, "app", "calc.py").write_text(source, encoding="utf-8")
    return d


BASELINE = checkout("def unrelated():\n    return 0\n")
# S1 was to add `add`; its developer also wrote `mul`, which the plan gave to S2.
AFTER_S1 = checkout("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")


def ob(cid, s, story, deps=()):
    return PlanObligation(cid, s.id, story, Role.INTRODUCE, EXPECTED_AT_PARENT[Role.INTRODUCE], tuple(deps), "why")


def measure(s, sha, root):
    return contract_satisfaction(run_probe(P, s, RevisionRef(sha, root), ENV).result, s)


def completed_s1(s):
    """What the spec measured on either side of S1: at S1's parent (the baseline) and at S1's merge."""
    return [dr.CompletedStory("S1", measure(s, REV0, BASELINE), measure(s, REV1, AFTER_S1))]


class ScenarioA(unittest.TestCase):
    PLAN = Plan.create(id="PLAN-A", baseline=REV0, plan_quality_policy=NOT_PREREGISTERED, obligations=(
        ob("C1", ADD, "S1"), ob("C2", MUL, "S2", deps=("C1",)), ob("C3", DIV, "S2", deps=("C1",))))

    def test_early_upstream_implementation_is_pre_satisfied_attributed_and_charges_no_budget(self):
        sink = sa.MemorySink()
        adm = sa.admit_story(self.PLAN, "S2", RevisionRef(REV1, AFTER_S1), specs=SPECS, probes={P.id: P}, env=ENV,
                             committed_stories=frozenset({"S1"}), sink=sink)
        self.assertEqual([o.decision.disposition for o in adm.obligations], [D.PRE_SATISFIED, D.READY])
        self.assertTrue(adm.developer_call_permitted)
        cont = dr.continue_story(self.PLAN, adm, {MUL.id: completed_s1(MUL)}, sink)
        self.assertEqual(cont.drift, (dr.PlanDrift("S2", "C2", MUL.id, "S1", ("S1",)),))
        self.assertEqual((cont.already_satisfied, cont.developer_work, cont.verify_at_candidate),
                         (False, ("C3",), ("C2", "C3")))
        sa.request_developer(sink, "S2", {"criteria": list(cont.developer_work)})
        self.assertEqual(dr.budget_problems(sink.events) + sa.ordering_problems(sink.events), [])
        self.assertEqual([t for t, _ in sink.events], [EventType.PROBE_EVALUATED, EventType.PROBE_EVALUATED,
                                                       EventType.STORY_ADMITTED, EventType.STORY_PLAN_DRIFT,
                                                       EventType.PROVIDER_REQUEST])


class ScenarioK(unittest.TestCase):
    PLAN = Plan.create(id="PLAN-K", baseline=REV0, plan_quality_policy=NOT_PREREGISTERED, obligations=(
        ob("C1", ADD, "S1"), ob("C2", MUL, "S2", deps=("C1",))))

    def test_a_fully_pre_satisfied_story_skips_the_developer_and_still_verifies(self):
        sink = sa.MemorySink()
        adm = sa.admit_story(self.PLAN, "S2", RevisionRef(REV1, AFTER_S1), specs=SPECS, probes={P.id: P}, env=ENV,
                             committed_stories=frozenset({"S1"}), sink=sink)
        self.assertEqual(([o.decision.disposition for o in adm.obligations], adm.admitted, adm.developer_call_permitted),
                         ([D.PRE_SATISFIED], True, False))
        cont = dr.continue_story(self.PLAN, adm, {MUL.id: completed_s1(MUL)}, sink)
        self.assertEqual((cont.already_satisfied, cont.developer_work, cont.verify_at_candidate),
                         (True, (), ("C2",)))
        with self.assertRaises(InvariantError):
            sa.request_developer(sink, "S2")
        self.assertNotIn(EventType.PROVIDER_REQUEST, [t for t, _ in sink.events])
        # "never make correct code wrong": the candidate is proved against the same spec, expecting SATISFIED
        self.assertIs(measure(MUL, REV1, AFTER_S1), sa.ContractSatisfaction.SATISFIED)
        self.assertIs(MUL.candidate_expectation, BehaviorVerdict.SATISFIED)


if __name__ == "__main__":
    unittest.main()
