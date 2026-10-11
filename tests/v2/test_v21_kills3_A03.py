"""V2.1 (B-03, survivor audit A03) — `aisef bundle migrate` refuses an obligation whose spec no release compiles, and
says by what rule.

The refusal is read by the operator (`refused: ...` on stderr, exit 2) and by nothing else: no code parses it. What the
operator needs from it is not only "unknown": which criteria, which releases were tried, and the rule the spec failed —
a spec is known only when a release compiles it from one of THIS bundle's approved contracts (the module docstring's
own requirement; `aisef2/app/bundle.py` states the same rule in B.load's refusal). Without the rule the refusal reads
as a release mismatch (`... no known release (2.0.0['C-ADD']`), not as "the plan names a spec none of your approved
contracts compiles to". The rule is asserted by its term (`approved contract`), not by its sentence or its position.

Pins aisef2/app/bundle_cli.py::migrate [74].
Offline; no provider, no run, no repository.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402
from aisef2.arch.enums import ObligationRole, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.compiler import ProbeRef, compile_spec  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402

CRITERION = "C-ADD"


def _approved_add():
    """One requirement, its approved contract, and the spec id this release compiles it to."""
    req = Requirement.create(id="R-ADD", text="app.calc.add(a, b) returns the sum of a and b", source="docs/requirements.md 1.1")
    contract = BehaviorContract.create(
        id="BC-ADD", requirement_ids=(req.id,), subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"),
        stimulus={"args": [2, 3]}, observable={"returns": 5, "within_s": 10}, polarity=Polarity.MUST_HOLD,
        subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="the requirement's own example")
    approval = ContractApproval(req.id, req.requirement_hash, contract.id, contract.contract_hash, "human:fixture-owner", 1.0, ())
    e = catalog.active()[SubjectKind.PYTHON_CALLABLE]
    spec_id = compile_spec(contract, requirements={req.id: req}, approvals=[approval],
                           probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(e.probe_id, e.probe_digest)}).id
    return req, contract, approval, spec_id


def _bundle(named_spec_id: str) -> dict:
    """A one-story bundle whose only obligation names `named_spec_id` (its contract is approved and compiles)."""
    req, contract, approval, _ = _approved_add()
    plan = Plan.create(id="PLAN-CALC", baseline="a" * 40, plan_quality_policy=NOT_PREREGISTERED, obligations=(
        PlanObligation(CRITERION, named_spec_id, "S1", ObligationRole.INTRODUCE, EXPECTED_AT_PARENT[ObligationRole.INTRODUCE],
                       (), "S1 introduces addition"),))
    return bundle.dump(
        name="calc", description="A calculator.", requirements_path="docs/requirements.md",
        requirements_sha256=hashlib.sha256(b"# requirements\n").hexdigest(), product_roots=("app", "tests"),
        requirements=(req,), contracts=(contract,), approvals=(approval,), plan=plan,
        facts={CRITERION: {"requirement": "R-ADD", "section": "1", "clause": "1.1",
                           "clause_text": "app.calc.add(a, b) returns the sum of a and b", "subject": "app.calc:add"}},
        stories={"S1": {"depends_on": [], "tests": ["tests/test_add.py"]}})


def _migrate_command(doc: dict) -> tuple[int, str, bool]:
    """(exit status, stderr, whether the output file was written) of `aisef bundle migrate` on `doc`."""
    with tempfile.TemporaryDirectory() as t:
        src, out = pathlib.Path(t) / "old.json", pathlib.Path(t) / "new.json"
        src.write_text(json.dumps(doc), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            status = bundle_cli.main(["migrate", str(src), "--out", str(out)])
        return status, err.getvalue(), out.exists()


class UnknownSpecRefusal(unittest.TestCase):
    """An obligation whose spec no known release compiles from one of the bundle's approved contracts is refused, never
    guessed; the refusal names the criterion, the releases tried and — between them — the rule the spec failed."""

    def test_the_fixture_migrates_when_the_obligation_names_the_spec_its_contract_compiles_to(self):
        status, err, written = _migrate_command(_bundle(_approved_add()[3]))
        self.assertEqual((status, written), (0, True), err)

    def test_the_refusal_names_the_criterion_the_releases_tried_and_the_rule(self):
        """Pins aisef2/app/bundle_cli.py::migrate [74]: besides the criterion and the releases tried, the refusal states
        the rule a spec failed (it is compiled by no release from the bundle's approved contracts). The mutant drops
        that clause and with it the closing parenthesis: the refusal then names a release mismatch and no rule."""
        status, err, written = _migrate_command(_bundle("PPS-" + "f" * 64))
        self.assertEqual((status, written), (2, False))
        self.assertIn(CRITERION, err)
        for release in bundle_cli.RELEASES:
            self.assertIn(release, err)
        self.assertIn("approved contract", err)


if __name__ == "__main__":
    unittest.main()
