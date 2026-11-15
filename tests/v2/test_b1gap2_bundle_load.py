"""B1 gap wave 2: mutation kill tests for aisef2/app/bundle.py::load.

Each test pins one surviving mutant of the v2.2 release-gate campaign, named verbatim in the comment above it.
Offline and hermetic: the bundle fixture is built in memory; no repo, no client, no provider, no network."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

KERNEL_LINE = "the bundle's kernel objects do not load: KeyError: 'id'"


class BundleLoadKills(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = e2e.project_bundle("a" * 40)

    def refused(self, doc) -> str:
        """load(doc) refuses with a BundleError; a raw kernel exception escaping instead is the mutant."""
        with self.assertRaises(bundle.BundleError) as c:
            bundle.load(doc)
        return str(c.exception)

    def two_kernel_problems_read_as_two_lines(self) -> None:
        """G7 (bundle.py L169): every kernel-object problem is raised, one per line."""
        msg = self.refused({**self.doc, "requirements": [{"no_id": 1}, {"no_id": 2}]})
        self.assertEqual(msg, KERNEL_LINE + "\n" + KERNEL_LINE)

    def two_compile_problems_read_as_two_lines(self) -> None:
        """G7 at the compile stage: every non-compiling contract is named, one per line."""
        req_id = self.doc["requirements"][0]["id"]
        c2 = e2e.BehaviorContract.create(
            id="BC-2", requirement_ids=(req_id,),
            subject=e2e.Subject(e2e.SubjectKind.PYTHON_CALLABLE, "app.calc:sub"),
            stimulus={"args": [2, 3]}, observable={"returns": -1, "within_s": 10},
            polarity=e2e.Polarity.MUST_HOLD, subject_absence=e2e.SubjectAbsence.REQUIRES_SUBJECT,
            rationale="a second contract, so two compile failures are raised together")
        msg = self.refused({**self.doc, "contracts": [self.doc["contracts"][0], c2.to_json()], "approvals": []})
        self.assertEqual(msg.count("does not compile"), 2, msg)
        self.assertIn("\n", msg)

    # kills: L186 element 1 dropped
    def test_an_approval_of_the_wrong_shape_is_refused_not_a_typeerror(self):
        msg = self.refused({**self.doc, "approvals": [{}]})
        self.assertIn("TypeError", msg)

    # kills: L192 element 0 dropped
    def test_a_plan_missing_its_keys_is_refused_not_a_keyerror(self):
        msg = self.refused({**self.doc, "plan": {}})
        self.assertIn("KeyError: 'obligations'", msg)

    # kills: L192 element 1 dropped
    def test_a_plan_quality_policy_of_the_wrong_shape_is_refused_not_a_typeerror(self):
        msg = self.refused({**self.doc, "plan": {**self.doc["plan"], "plan_quality_policy": {}}})
        self.assertIn("TypeError", msg)

    # kills: L177 element 2 dropped
    def test_a_requirement_whose_hash_does_not_bind_is_refused_not_a_contracterror(self):
        bad = {**self.doc["requirements"][0], "requirement_hash": "0" * 64}
        msg = self.refused({**self.doc, "requirements": [bad]})
        self.assertIn("ContractError", msg)

    # kills: L189 conditional negated
    def test_two_kernel_problems_are_both_raised_not_only_the_first(self):
        self.two_kernel_problems_read_as_two_lines()

    # kills: L189 Eq->NotEq
    def test_two_kernel_problems_are_both_raised_whichever_way_one_is_counted(self):
        self.two_kernel_problems_read_as_two_lines()

    # kills: L189 string '\n' emptied
    def test_two_kernel_problems_are_separated_by_a_newline_not_fused(self):
        self.two_kernel_problems_read_as_two_lines()

    # kills: L204 conditional negated
    def test_two_compile_problems_are_both_raised_not_only_the_first(self):
        self.two_compile_problems_read_as_two_lines()

    # kills: L204 Eq->NotEq
    def test_two_compile_problems_are_both_raised_whichever_way_one_is_counted(self):
        self.two_compile_problems_read_as_two_lines()

    # kills: L204 string '\n' emptied
    def test_two_compile_problems_are_separated_by_a_newline_not_fused(self):
        self.two_compile_problems_read_as_two_lines()

    # kills: L193 string ': ' emptied — the refusal message is the kill route (owner precedent: the exception message
    # is a test-asserted observable); 'PlanError: plan_hash' is the smallest stable substring the mutant destroys.
    def test_the_kernel_load_refusal_separates_the_type_name_from_its_message(self):
        msg = self.refused({**self.doc, "plan": {**self.doc["plan"], "plan_hash": "0" * 64}})
        self.assertIn("PlanError: plan_hash", msg)


if __name__ == "__main__":
    unittest.main()
